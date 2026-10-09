# W3 — HTTP/1.1 vs HTTP/2 (vs HTTP/3) Performance Comparison

**Target:** `https://edgeone.ai/` (served from EdgeOne cache, ~181 KB HTML)
**Client:** macOS, Minnesota, `curl 8.7.1`, ~38 ms RTT to the edge node
**Date:** 2026-10-08

---

## TL;DR

| Scenario | HTTP/1.1 | HTTP/2 | Takeaway |
|---|---|---|---|
| Single request (curl `time_starttransfer`) | TTFB 158 ms, total 304 ms | TTFB 157 ms, total 297 ms | **No meaningful difference** |
| 20 parallel **GET** (full 181 KB each) | **20 connections**, 0.42 s | **1 connection**, 0.58 s | h2 opened 1 new connection; **h2 slower** here (preliminary, see limitations) |
| 20 parallel **HEAD** (no body) | 20 connections, 0.29 s | 1 connection, 0.29 s | Gap **closes** once payload is removed |
| HTTP/3 | — | — | Site advertises h3, but the browser used **h2** for edgeone.ai while other sites on the same network used h3. Cause unconfirmed; performance not compared |

*(All values are medians.)*

The result was not "h2 is always faster". It depends on **latency and payload size**, which matters when advising customers.

---

## Experiment 1 — Single request, per-stage timing

```bash
for v in --http1.1 --http2; do for i in 1 2 3 4 5; do
  curl -s -o /dev/null $v -w "$v dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total} ver=%{http_version}\n" https://edgeone.ai/
done; done
```

Raw results (seconds, **cumulative** from start):

| Version | dns | tcp | tls | ttfb | total |
|---|---|---|---|---|---|
| 1.1 | **0.370** | 0.481 | 0.532 | 0.584 | 0.663 |
| 1.1 | 0.003 | 0.045 | 0.093 | 0.142 | 0.227 |
| 1.1 | 0.005 | 0.121 | 0.170 | 0.219 | 0.304 |
| 1.1 | 0.008 | 0.061 | 0.109 | 0.158 | 0.319 |
| 1.1 | 0.004 | 0.048 | 0.097 | 0.151 | 0.246 |
| 2 | 0.005 | 0.057 | 0.186 | 0.239 | 0.332 |
| 2 | 0.004 | 0.053 | 0.104 | 0.157 | 0.253 |
| 2 | 0.005 | 0.111 | 0.163 | 0.214 | 0.297 |
| 2 | 0.004 | 0.051 | 0.106 | 0.156 | 0.323 |
| 2 | 0.004 | 0.059 | 0.109 | 0.157 | 0.241 |

**Reading it:** curl reports cumulative times, so per-stage cost = difference between columns (e.g. row 2: TCP ≈ 43 ms, TLS ≈ 48 ms).

**Findings**
- With one request, both versions do the same TCP + TLS handshake and transfer one file, so there's nothing for h2's multiplexing to improve.
- The first HTTP/1.1 run had a **370 ms DNS lookup** (cold cache); the rest were 3–8 ms. A single run would have wrongly suggested HTTP/1.1 is twice as slow. **Run several times and compare medians.**

---

## Experiment 2 — 20 parallel requests

```bash
for v in --http1.1 --http2; do for r in 1 2 3; do
  /usr/bin/time -p curl -s -Z $v -w "%{num_connects}\n" \
    $(for i in {1..20}; do echo -o /dev/null https://edgeone.ai/; done) 2>&1 \
  | awk -v v=$v '/^real/ {t=$2} /^[0-9]+$/ {c+=$1} END {print v, "conns=" c, "time=" t "s"}'
done; done
```

**2a. Full GET (20 × 181 KB ≈ 3.6 MB)**

| Version | New connections | Run 1 | Run 2 | Run 3 | Median |
|---|---|---|---|---|---|
| 1.1 | **20** | 0.42 s | 0.43 s | 0.34 s | **0.42 s** |
| 2 | **1** | 0.73 s | 0.58 s | 0.56 s | **0.58 s** |

**2b. HEAD only (same command with `-I`, no body)**

| Version | New connections | Run 1 | Run 2 | Run 3 | Median |
|---|---|---|---|---|---|
| 1.1 | 20 | 0.44 s | 0.29 s | 0.28 s | **0.29 s** |
| 2 | 1 | 0.36 s | 0.20 s | 0.29 s | **0.29 s** |

**Findings**
- **Connections:** HTTP/1.1 opened 20 new connections; HTTP/2 opened **1**. This is consistent with multiplexing, but per-request status, protocol version and bytes downloaded were not recorded, so it is **not yet confirmed that all 20 requests completed fully over that connection**. Treat the timing results below as preliminary observations.
- **For bulk transfer, h2 was slower** (0.58 s vs 0.42 s, consistent across all 3 runs).
- **Removing the payload closed the gap** (both 0.29 s median).

### Why? (hypotheses, not yet proven)

1. **TCP slow start.** Each new TCP connection starts with a small send window and ramps up. 20 connections ramp up in parallel (20 starting windows); one h2 connection has a single window to grow.
2. **Low latency makes handshakes cheap.** At ~38 ms RTT, opening extra connections costs little, so h2's main benefit (avoiding handshakes) is small here.
3. **TCP head-of-line blocking.** All h2 streams share one TCP connection; one lost packet stalls every stream. (HTTP/3 over QUIC is designed to remove this.)

Experiment 2b supports (1) and (2): once the transfer volume is gone, h2's disadvantage disappears. With only 3 runs and this low latency, h2 did **not** clearly win either.

### Expected (not measured)
On **high-latency or lossy** networks (e.g. mobile users far from a node), each extra handshake costs much more, so HTTP/2 should pull ahead, and HTTP/3 should handle packet loss better than both. Worth re-testing from a remote location or with simulated latency.

---

## HTTP/3

**What the site says:** `edgeone.ai` advertises HTTP/3 in every response: `alt-svc: h3=":443"; ma=2592000, ...`

**curl:** not testable. The macOS system curl's `Features` list has `HTTP2` but no `HTTP3`.

**Browser check** (Chrome 154, DevTools → Network → Protocol column, airport Wi-Fi, 2026-10-09, after several reloads):

| Requests | Protocol |
|---|---|
| `edgeone.ai` page resources (JS, CSS, favicon, analytics) | **h2** for all |
| Google sign-in requests on the same page (`web-identity`, `listaccounts`) | **h3** |
| Control: `claude.ai` API requests, same network, same time | **h3** |

**What this shows**
- The network **is not blocking HTTP/3 / QUIC across the board**: other sites negotiated `h3` on the same Wi-Fi at the same time. This makes a blanket "this Wi-Fi blocks UDP" explanation unlikely, but it does **not** rule out a problem on the UDP path to EdgeOne's specific edge IP, which can take a different route or hit different filtering (RFC 9114 §3.1 lists UDP connectivity failure as a reason HTTP/3 may not be used).
- Even so, the browser stayed on **h2** for `edgeone.ai`, despite the `alt-svc` advertisement.

**Not yet known why.** Possible explanations (none verified):
1. UDP/QUIC to this specific edge IP is blocked or unreliable on this path, even though QUIC to other destinations works.
2. Chrome races QUIC against TCP and may keep using h2 if TCP wins or if an earlier QUIC attempt to that host failed.
3. Some resources were served from Chrome's prefetch cache, so not every row reflects a fresh network negotiation.

**Next steps:** retest from a different network, and with an HTTP/3-capable curl (`curl --http3-only -I https://edgeone.ai`) to separate browser behavior from server behavior. HTTP/3 **performance** was not compared.

---

## What this means for customers

- **Don't promise "turn on HTTP/2 and everything gets faster."** Gains depend on user latency, number of requests per page, and file sizes.
- Pages with **many small resources** and users on **high-latency/mobile networks** benefit most from h2/h3.
- These tests did **not** measure how much cache hit ratio matters compared with protocol version. The HIT vs MISS observation in `01-request-layers.md` compares different resources, so it cannot support that comparison. A same-resource HIT vs MISS test is needed before advising customers on that trade-off.

## Limitations

- One client location, one target site, 3–5 runs per case; small sample, noisy.
- Same-file requests (all cache HITs); real pages mix sizes and cache states.
- curl's parallel behavior differs from browsers (browsers cap HTTP/1.1 at ~6 connections per host).
- The parallel runs did not record per-request status codes, protocol versions or bytes received, so it is not confirmed that all 20 requests completed fully. A failed request finishes fast and could make a run look quicker. A retest should log `%{http_code}`, `%{http_version}` and `%{size_download}` per request.