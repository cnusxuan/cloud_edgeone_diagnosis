# W3 — HTTP Status Code Troubleshooting Cheat Sheet (EdgeOne)

A reusable reference for triaging status codes on sites accelerated by EdgeOne. Each entry covers what the code means, **who generated it**, which **stage** of the request it points to, common causes, how to check, and a one-line explanation for the customer in **English and Chinese**.

**Evidence labels**
- ✅ **Verified** — reproduced against a live site with `curl` or `eo_diag.py`
- 🧪 **Simulated** — the same failure reproduced from a client (e.g. connecting to a closed port); the EdgeOne code is taken from the official docs
- 📄 **Docs** — from EdgeOne / MDN documentation, not yet reproduced

---

## Step 0: Who generated this response?

The same code can come from three places, and **the source decides where to fix it**.

| Source | How to recognize it | Where to look |
|---|---|---|
| **Origin, passed through** | Origin-specific headers present (e.g. `x-cos-*`), `Server` is the origin's software | Customer's server / app / storage |
| **EdgeOne node, standard code** | `Server: TencentEdgeOne`, no origin headers, no `EO-Cache-Status` | EdgeOne config (rules, auth, Range, CNAME) |
| **EdgeOne custom code (520–599)** | Code is in EdgeOne's reserved range | Path between EdgeOne and origin, or security rules |

Other useful headers:
- `EO-LOG-UUID` — present ⇒ the request went through EdgeOne. Give it to support along with the code, time and timezone.
- `EO-Cache-Status` — `HIT` = served from the edge node, `MISS` = fetched from origin.

**Rule of thumb:** **52x = EdgeOne couldn't get through to the origin. 50x = got through, but something broke inside the origin.** A 52x is reported by EdgeOne, but the fix is usually on the origin side (firewall, port, protocol, DNS).

---

## Quick index

| Code | One-liner | Typical source | Stage |
|---|---|---|---|
| [200](#200-ok) | OK | Origin (often via cache) | — |
| [206](#206-partial-content) | Partial content | Origin (sliced by node from cache) | — |
| [301](#301-moved-permanently) / [302](#302-found) | Redirect | Node or origin | — |
| [304](#304-not-modified) | Not modified | Node (cache revalidation) | — |
| [400](#400-bad-request) | Bad request | Node | HTTP |
| [403](#403-forbidden) | Forbidden | Node or origin | Security / auth |
| [404](#404-not-found) | Not found | Origin | — |
| [416](#416-range-not-satisfiable) | Bad range | Node | HTTP |
| [418](#418-edgeone-domain-config-not-found) | Domain config missing | Node | DNS / access |
| [423](#423-edgeone-request-loop) | Request loop | Node | Config |
| [502](#502-bad-gateway) / [503](#503-service-unavailable) / [504](#504-gateway-timeout) | Origin-side gateway errors | Origin | Inside origin |
| [520](#520-origin-reset-after-request) | Reset after request | EdgeOne custom | HTTP |
| [521](#521-origin-refused-connection) | Connection refused | EdgeOne custom | TCP |
| [522](#522-origin-connection-timeout) | Connection timeout | EdgeOne custom | TCP |
| [523](#523-origin-dns-failure) | Origin DNS failure | EdgeOne custom | DNS |
| [524](#524-origin-response-timeout) | Response timeout | EdgeOne custom | HTTP |
| [525](#525-origin-tls-handshake-failure) | TLS handshake failure | EdgeOne custom | TLS |
| [545](#545-edge-function-error) | Edge Function error | EdgeOne custom | Edge Function |
| [566](#566--567-blocked-by-security-rules) / [567](#566--567-blocked-by-security-rules) | Blocked by WAF / rules | EdgeOne custom | Security |
| [570 / 571 / 579](#570--571--579-rate-limited-by-platform) | Platform rate limiting | EdgeOne custom | Security |

---

## 2xx / 3xx

### 200 OK
✅ Verified on `https://edgeone.ai`: `Server: tencent-cos`, `EO-Cache-Status: HIT`, response headers received in ~80–90 ms (`eo_diag.py`).

- **Source:** content from origin, often served from EdgeOne cache.
- **Watch out:** 200 does not mean the content is *current*. "I updated the site but users still see the old version" **can** be a stale cached copy on the edge, but 200 + HIT alone doesn't prove it. Compare what the edge returns with what the origin returns (`ETag` / `Last-Modified` / checksum) before purging.
- **Check:** `EO-Cache-Status`, then compare edge vs origin content; purge only if the edge copy is older. If they match, look at the origin deploy or the user's browser cache.
- **Tell the customer**
  - EN: "The request succeeded. If users still see old content after an update, we'll first compare our cached copy with your server. If ours is older, purging the cache fixes it; if they're the same, we'll check whether the update reached your server or is stuck in users' browsers."
  - 中：“访问正常。如果您更新了内容但用户还看到旧版，我们会先对比节点缓存和您服务器上的版本：节点的旧，就刷新缓存；两边一样，再查更新是否真的发布到了服务器，或者卡在了用户浏览器缓存里。”

### 206 Partial Content
✅ Verified: `curl -I -r 0-99 https://edgeone.ai` → `Content-Range: bytes 0-99/185592`, `Content-Length: 100`, `HIT`.

- **Source:** origin content, sliced by the node from its cached copy.
- **Seen in:** video seeking, resumable downloads, large files.
- **Tell the customer**
  - EN: "Normal. The user downloaded only the part they needed, e.g. when skipping ahead in a video."
  - 中：“正常现象，用户只下载了需要的那一段，比如视频拖进度条。”

### 301 Moved Permanently
✅ Verified: `curl -I https://www.edgeone.ai` → `Location: https://edgeone.ai/`, `Server: TencentEdgeOne`.

- **Source:** here, generated by the EdgeOne node (no origin headers).
- **Watch out:** browsers cache 301s. A wrong 301 can stick in users' browsers even after it is fixed. Use 302 for temporary redirects.
- **Tell the customer**
  - EN: "This address has permanently moved and users are redirected automatically. Browsers remember this, so use 302 for anything temporary."
  - 中：“这个地址已经永久换成新地址，用户会被自动带过去。浏览器会记住这个跳转，临时调整建议用 302。”

### 302 Found
📄 Docs.

- **Meaning:** temporary redirect; browsers do not remember it long-term.
- **Tell the customer**
  - EN: "Users are temporarily sent to another address; this is safe to change later."
  - 中：“用户被临时带到另一个地址，之后可以随时改回来。”

### 304 Not Modified
✅ Verified: `curl -I https://edgeone.ai -H "If-Modified-Since: <Last-Modified>"` → 304, no body, `HIT`, same `x-cos-request-id` as the cached 200 (origin was not contacted).

- **Source:** EdgeOne node, answering a revalidation from cache.
- **Tell the customer**
  - EN: "The user already had this page; we just confirmed it hasn't changed, so nothing was re-downloaded. Faster and less traffic."
  - 中：“用户之前已经下载过这个页面，这次只是确认没有变化，所以不用重新下载，更快也更省流量。”

---

## 4xx

### 400 Bad Request
📄 Docs.

- **Source:** EdgeOne node, e.g. when the request method is not allowed by EdgeOne.
- **Check:** request method and format; EdgeOne HTTP restrictions.
- **Tell the customer**
  - EN: "The request itself was malformed or used a method we don't accept. This usually needs a fix in the client or app making the call."
  - 中：“请求本身格式不对，或者用了我们不支持的方法，一般需要调用方修改。”

### 403 Forbidden
📄 Docs.

- **Source:** can be **either**:
  - **EdgeOne node:** token authentication / hotlink protection failed, or compliance blocking.
  - **Origin:** the origin itself denied access (permissions, private bucket, IP allowlist).
- **Check:** origin headers present? → origin. `Server: TencentEdgeOne` and no origin headers? → EdgeOne auth or rules.
- **Watch out:** if the customer customized WAF block codes to 403, a WAF block looks like an origin 403. Check security logs.
- **Tell the customer**
  - EN: "Access was denied. We'll first check whether it was our access rules (like token auth) or your server's own permissions."
  - 中：“访问被拒绝了。我们先确认是我们这边的访问规则（比如 Token 鉴权），还是您服务器自己的权限设置。”

### 404 Not Found
✅ Verified: `/this-page-does-not-exist` → `x-cos-error-code: NoSuchKey`, `MISS`, response headers received in ~1200 ms (`eo_diag.py`).

- **Source:** origin, passed through by EdgeOne.
- **Causes:** file not uploaded, wrong path or file name (case-sensitive), file deleted.
- **Observation:** EdgeOne docs say 404 is cached for 10 s by default, but on this site 3 groups of tests (6 requests, 1–2 s apart) were all `MISS` with different origin request IDs ⇒ 404 was **not** cached here. Possibly a site-level setting or the docs' precondition (resource must be cacheable) not met. **To verify** via console or `EO-LOG-UUID`.
- **Tell the customer**
  - EN: "Your server reports the file doesn't exist; we're just passing that on. Please check the file was uploaded and the link is correct, including upper/lower case."
  - 中：“这是您服务器返回的“找不到文件”，我们只是转达。请检查文件有没有上传成功，以及链接里的文件名是否正确，包括大小写。”

### 416 Range Not Satisfiable
✅ Verified: `curl -I -r 999999999- https://edgeone.ai` → `Server: TencentEdgeOne`, `Content-Range: bytes */185592`, no origin headers.

- **Source:** EdgeOne node directly (contrast with 404 above, which carried origin headers).
- **Tell the customer**
  - EN: "The player or downloader asked for a part beyond the end of the file. The file itself is fine."
  - 中：“播放器或下载工具请求的位置超出了文件范围，文件本身没有问题。”

### 418 (EdgeOne) Domain config not found
📄 Docs.

- **Meaning:** the node has no configuration for this domain.
- **Causes:** CNAME misconfigured, request routed to a node not bound to this domain, scheduling issue.
- **Check:** `dig <domain>` and confirm the CNAME points to the EdgeOne-assigned target.
- **Tell the customer**
  - EN: "Our node doesn't recognize this domain yet. Usually the DNS (CNAME) isn't pointing to us correctly."
  - 中：“我们的节点还不认识这个域名，通常是 DNS 的 CNAME 没有正确指向我们。”

### 423 (EdgeOne) Request loop
📄 Docs.

- **Meaning:** the request bounced around too many times (`CDN-Loop` ≥ 16).
- **Causes:** origin configured to point back to EdgeOne (e.g. origin set to the accelerated domain itself).
- **Tell the customer**
  - EN: "The request is going in circles, usually because the origin address points back to us."
  - 中：“请求在兜圈子，通常是源站地址又指回了我们自己。”

---

## 50x — errors from inside the origin

### 502 Bad Gateway
✅ Simulated via `https://httpbin.org/status/502` (not via EdgeOne): `Server: gunicorn/19.9.0`.

- **Source:** usually the customer's own proxy/load balancer (Nginx, ELB) getting a bad response from their app.
- **Check:** `Server` header; customer's app health and proxy logs.
- **Tell the customer**
  - EN: "Something inside your server failed: the part that forwards requests couldn't get a valid answer from your application."
  - 中：“您服务器内部出了问题，负责转发的部分没能从后面的程序拿到正常回复。”

### 503 Service Unavailable
📄 Docs.

- **Source:** origin. Often includes `Retry-After`.
- **Causes:** overload, maintenance.
- **Tell the customer**
  - EN: "Your server says it's overloaded or under maintenance. It usually recovers on its own."
  - 中：“您的服务器表示现在忙不过来或在维护，通常过一会儿会恢复。”

### 504 Gateway Timeout
📄 Docs.

- **Source:** usually the customer's own proxy waiting too long on their app or database.
- **Tell the customer**
  - EN: "Your server's internal processing took too long, so its front-end gave up waiting."
  - 中：“您服务器内部处理太慢，前面负责转发的部分等不及了。”

---

## 52x — EdgeOne could not get through to the origin

These map one-to-one to the request stages (see `docs/01-request-layers.md`). EdgeOne's default origin-pull timeouts: **5 s** TCP connect, **15 s** HTTP response.

### 523 Origin DNS failure
🧪 Simulated: `this-origin-does-not-exist-12345.com` → `Could not resolve host`.

- **Stage:** ① DNS
- **Causes:** origin domain mistyped, DNS record deleted, domain expired.
- **Check:** `dig <origin-domain>` / `nslookup <origin-domain>`.
- **Tell the customer**
  - EN: "We can't find your server's address. Please confirm the origin domain configured with us is correct and still active."
  - 中：“我们找不到您服务器的地址，请确认在我们这里配置的源站域名是否正确、是否还在使用。”

### 521 Origin refused connection
🧪 Simulated: `127.0.0.1:81` → connection refused (RST).

- **Stage:** ② TCP (refused during handshake)
- **Causes:** web service not running, **origin port/protocol mismatch** (e.g. pulling on 443 but origin only listens on 80), firewall actively rejecting.
- **Check:** connect directly to origin IP and port; confirm origin-pull protocol and port in EdgeOne.
- **Tell the customer**
  - EN: "We reached your server, but it actively refused the connection. Usually the web service isn't running or the port doesn't match."
  - 中：“我们联系到了您的服务器，但它直接拒绝了连接，通常是网站服务没在运行，或者端口设置对不上。”

### 522 Origin connection timeout
🧪 Simulated: `10.255.255.1:80` → no response within 5 s.

- **Stage:** ② TCP (no answer to handshake)
- **Causes:** origin firewall silently dropping EdgeOne's IPs (not on allowlist), origin down or overloaded, wrong origin IP.
- **Check:** `nc -vz <origin-ip> 443` (macOS) / `Test-NetConnection <origin-ip> -Port 443` (Windows); check allowlist. Only if the origin is genuinely slow to accept connections, consider raising the TCP connect timeout (never above the client's timeout).
- **Tell the customer**
  - EN: "Our nodes can't reach your server; it isn't responding at all. The most common cause is a firewall blocking our IPs."
  - 中：“我们的节点联系不上您的服务器，它完全没有回应，最常见的原因是防火墙把我们挡在外面了。”

**521 vs 522:** 521 = refused (someone said "no"). 522 = no answer (nobody picked up).

### 525 Origin TLS handshake failure
🧪 Simulated: `https://example.com:80` → handshake failed (HTTPS spoken to an HTTP-only port).

- **Stage:** ③ TLS
- **Causes:** origin-pull set to HTTPS but origin port only speaks HTTP; incompatible TLS version/cipher; origin certificate problems (depends on whether origin cert verification is enabled — to verify).
- **Check:** `openssl s_client -connect <origin>:443 -servername <host>`; confirm origin-pull protocol.
- **Tell the customer**
  - EN: "We reached your server, but we couldn't agree on an encrypted connection, often because we're set to use HTTPS on a port that only supports HTTP."
  - 中：“我们能联系上您的服务器，但双方建立加密连接时对不上，常见原因是我们设置了 HTTPS 回源，但您那个端口不支持加密。”

**Note:** 521 and 525 share a common root cause, a wrong origin-pull port or protocol, showing up at different stages.

### 524 Origin response timeout
🧪 Simulated: `https://httpbin.org/delay/10` with a 5 s read timeout → no response.

- **Stage:** ④ HTTP (connected and request sent, no reply)
- **Causes:** slow origin processing (heavy queries, report generation, overload).
- **Check:** request the same URL directly from origin and time it. If the operation is legitimately slow, the HTTP response timeout can be raised (never above the client's timeout). Better long-term fix: make it asynchronous.
- **Tell the customer**
  - EN: "We sent your server the request, but it took too long to answer. If this operation is normally slow, we can extend the wait, but it's worth checking why it's slow."
  - 中：“请求已经发到您的服务器，但它处理太久没有回复。如果这个功能本来就慢，我们可以延长等待时间，但建议也查一下为什么这么慢。”

### 520 Origin reset after request
📄 Docs.

- **Stage:** ④ HTTP (connected, request sent, origin sent RST)
- **Causes:** origin app crashed while handling the request; origin security policy treated EdgeOne's request as suspicious; origin rate limiting.
- **Check:** origin logs at that timestamp; whether EdgeOne IPs/headers trigger origin security rules.
- **Tell the customer**
  - EN: "Our request reached your server, but it cut the connection mid-way. Often the app crashed, or a security rule blocked us."
  - 中：“我们的请求发到了您的服务器，但它中途把连接断了，常见原因是程序崩溃，或安全规则把我们拦了。”

**520 vs 521:** both are RST from origin. 521 = during the TCP handshake. 520 = after the request was sent.

### 550–555
📄 Docs list each as having the same description as 520–525. The difference between the two sets is **not stated in the docs — to confirm**.

---

## EdgeOne security & platform codes

### 545 Edge Function error
📄 Docs. The customer's Edge Function threw an error (e.g. undefined variable). Check Edge Function logs.

- EN: "The custom code running on our edge hit an error; let's check its logs."
- 中：“运行在边缘节点上的自定义代码出错了，我们一起看下日志。”

### 566 / 567 Blocked by security rules
📄 Docs.

- **566:** blocked by WAF managed rules.
- **567:** blocked by custom rules, rate limiting, or Bot management.
- Both are defaults; customers can change the block code (e.g. to 403).
- **Watch out:** "users are being blocked" right after enabling WAF is often a false positive. Roll out in observe mode first.
- EN: "Our security rules blocked this request. We'll check whether it's a real attack or a false positive and adjust the rule."
- 中：“这次请求被我们的安全规则拦了，我们会确认是真攻击还是误拦，再调整规则。”

### 570 / 571 / 579 Rate limited by platform
📄 Docs.

- **570:** platform-level fixed rate limit.
- **571:** domain-level fixed rate limit.
- **579:** dynamic rate limit, triggered when a node is under high load and requests surge abnormally.
- EN: "Traffic hit a rate limit on our platform. If this is expected traffic (e.g. a launch), let's plan capacity together."
- 中：“流量触发了平台限速。如果是正常的业务高峰（比如大促），我们一起提前做好容量规划。”

---

## Before opening a support ticket

- [ ] Status code and full response headers (`curl -I <url>`)
- [ ] `EO-LOG-UUID`
- [ ] Time and **timezone** when the error happened
- [ ] Affected URL(s), and whether all users or only some regions/ISPs
- [ ] `eo_diag.py` output against the public domain **and** against the origin directly

---

## References

- EdgeOne: Reference for Abnormal Status Codes — https://edgeone.ai/document/58009
- EdgeOne: Troubleshooting Guide for 4XX/5XX — https://www.tencentcloud.com/document/product/1145/67228
- EdgeOne: 520/524 Troubleshooting — https://www.tencentcloud.com/document/product/1145/69573
- EdgeOne: 521/522 Troubleshooting — https://www.tencentcloud.com/document/product/1145/69572
- EdgeOne: Status Code Cache TTL — https://tencentcloud.com/document/product/1145/46964
- MDN: HTTP response status codes — https://developer.mozilla.org/en-US/docs/Web/HTTP/Status