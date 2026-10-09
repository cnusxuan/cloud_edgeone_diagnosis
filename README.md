# eo-diag

A zero-dependency Python tool that diagnoses an HTTP(S) request **one stage at a time** (DNS → TCP → TLS → HTTP), tells you **where it fails**, maps the failure to the **EdgeOne status code** a customer would see, and summarizes **who generated the response** (EdgeOne node or origin) and whether it was **served from cache**.

Built as a follow-up to the Week 1 (end-to-end HTTPS request layering) and Week 3 (HTTP status code troubleshooting) topics.

---

## Why stage by stage

Every request goes through four stages in a fixed order, and each stage depends on the one before it:

```
[1] DNS   find the server's IP        fail -> EdgeOne 523
[2] TCP   open a connection           refused -> 521, no response -> 522
[3] TLS   set up encryption (HTTPS)   fail -> 525
[4] HTTP  send request, get response  no response -> 524, reset -> 520
```

If DNS fails, TCP never starts; if TCP fails, TLS never starts. So the **first failing stage is where to start looking**; later stages never ran and can be ignored. The failing stage is not the root cause itself: a TCP timeout, for example, is usually caused by a firewall rule. The tool stops at the first failure and tells you which stage it was, instead of returning a single generic error.

Timeouts mirror EdgeOne's defaults for origin-pull: **5 s** for TCP connect and **15 s** for waiting on the HTTP response. A result here therefore approximates what an EdgeOne node would experience when pulling from the same server.

---

## Two ways to use it

| Run it against | What you are testing | Use when |
|---|---|---|
| The customer's **public domain** (e.g. `https://www.example.com`) | User → EdgeOne node | Users report errors or slowness; you want the status code, cache status, and `EO-LOG-UUID` |
| The customer's **origin** directly (e.g. `https://origin.example.com` or `https://1.2.3.4`) | Roughly what the EdgeOne node sees when pulling from origin | You see a 52x and need to find which stage the origin is failing at |

---

## Requirements

- Python 3.10+
- No third-party packages

## Usage

```bash
python3 eo_diag.py https://edgeone.ai
python3 eo_diag.py https://edgeone.ai/some/path?x=1
python3 eo_diag.py http://example.com:8080
```

---

## Example output

**Healthy request, served from EdgeOne cache**

```
[1/4] DNS   Resolving edgeone.ai ...
  [OK]   Resolved in 160 ms
  CNAME: edgeone.ai -> edgeone.ai.eo.dnse5.com
  IPs:   43.174.196.51
[2/4] TCP   Connecting to 43.174.196.51:443 ...
  [OK]   Connected in 48 ms
[3/4] TLS   Handshaking with edgeone.ai ...
  [OK]   TLSv1.3 handshake in 70 ms
  Cert:  edgeone.ai (issued by DigiCert, Inc.)
  Valid until: Mar 10 23:59:59 2027 GMT
[4/4] HTTP  HEAD / ...
  [OK]   HTTP/1.1 200 OK (headers received in 91 ms)

=== Summary ===
  Status:        200 - OK
  Via EdgeOne:   yes
  Cache:         HIT
  EO-LOG-UUID:   2752949607365977507  (share with support)
  Likely source: Origin (Server: tencent-cos) - served from EdgeOne cache
```

**404 passed through from origin (cache MISS)**

```
[4/4] HTTP  HEAD /this-page-does-not-exist ...
  [OK]   HTTP/1.1 404 Not Found (headers received in 1202 ms)

=== Summary ===
  Status:        404 - Not found - check the file exists on origin (path, case)
  Via EdgeOne:   yes
  Cache:         MISS
  Likely source: Origin (Server: tencent-cos)
```

In this run the cached homepage (HIT) returned headers in **~90 ms** and the missing page (MISS) in **~1200 ms**. Going back to origin is a likely contributor, but these are **different resources with different results** (200 vs 404), so the full gap cannot be attributed to the origin trip. A same-resource HIT vs MISS comparison is needed to measure that.

**Failures at each stage**

| Command | Result | EdgeOne equivalent |
|---|---|---|
| `https://this-origin-does-not-exist-12345.com` | DNS: could not resolve host | 523 |
| `http://127.0.0.1:81` | TCP: connection refused | 521 |
| `http://10.255.255.1` | TCP: no response within 5 s | 522 |
| `https://example.com:80` | TLS: handshake failed (HTTPS to an HTTP-only port) | 525 |
| `https://expired.badssl.com` | TLS: certificate has expired | — (certificate issue) |

---

## How to read the summary

| Field | Meaning |
|---|---|
| **Via EdgeOne** | `yes` if the response carries an `EO-LOG-UUID` header |
| **Cache** | `EO-Cache-Status`: `HIT` = served from the edge node, `MISS` = fetched from origin |
| **EO-LOG-UUID** | Unique ID of this request. Include it, the status code, and the time and timezone when opening a support ticket |
| **Likely source** | Who generated the response, judged in this order: (1) a 520–599 code **with** EdgeOne evidence (`EO-LOG-UUID` or `Server: TencentEdgeOne`) means the EdgeOne node; a 520–599 code **without** that evidence is reported as unknown; (2) origin-specific headers (e.g. `x-cos-*`) or a non-EdgeOne `Server` header mean the origin; (3) `Server: TencentEdgeOne` with no origin traces means the node |

**Rule of thumb:** a **52x** means EdgeOne could not reach or get an answer from the origin (the fix is usually on the origin side: firewall allowlist, port, protocol, DNS). A standard **50x** usually comes from inside the customer's own infrastructure (e.g. their Nginx could not reach their app) and EdgeOne is just passing it through.

---

## Limitations

These are known and intentional for a first version:

- **IPv4 only, first IP only.** DNS returns several IPs; the tool connects to the first one.
- **Runs from your machine's point of view.** DNS results and latency reflect your local network and resolver, not an EdgeOne node's. Slow DNS here may be your resolver, not the site (compare several domains before concluding).
- **HEAD requests only.** A few servers handle `HEAD` differently from `GET`.
- **Does not follow redirects.** A 301/302 is reported as-is; rerun with the `Location` URL.
- **HTTP/1.1 only.** HTTP/2 and HTTP/3 are not tested.
- **Timing is headers-received, not strict time to first byte.** The clock runs from sending the request until the full response header block arrives.
- **"Likely source" is a heuristic.** It relies on response headers. If a customer customizes block status codes (e.g. sets WAF blocks to return 403), an EdgeOne-generated 403 can look like an origin 403.
- **No proxy support.**

---

## Roadmap

- `--json` output so results can feed other tools or monitoring
- Test all resolved IPs and report per-IP results
- Optional `GET` mode and redirect following
- A simple GUI for non-technical teammates

---

## References

- EdgeOne: Reference for Abnormal Status Codes — https://edgeone.ai/document/58009
- EdgeOne: Troubleshooting Guide for 4XX/5XX Status Codes — https://www.tencentcloud.com/document/product/1145/67228
- EdgeOne: 520/524 Troubleshooting — https://www.tencentcloud.com/document/product/1145/69573
- EdgeOne: 521/522 Troubleshooting — https://www.tencentcloud.com/document/product/1145/69572
- MDN: HTTP response status codes — https://developer.mozilla.org/en-US/docs/Web/HTTP/Status