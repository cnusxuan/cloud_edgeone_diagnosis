# W1 — Ticket Triage by Layer (5 simulated tickets)

> These are **simulated** tickets written to practice layer-based triage. They are modeled on common EdgeOne onboarding issues described in the official troubleshooting docs, not real customer cases. The "simulated verification" column is part of the scenario: it shows what evidence would be needed to confirm the hypothesis. **Until that evidence exists, the cause is a hypothesis, not a root cause.**

**Method**
1. Find the **first stage that fails** (DNS → TCP → TLS → HTTP). That is where to start looking, not automatically the root cause.
2. Ask: *all users or some?* and *who generated the response?*
3. Form a **hypothesis**, list the alternatives, and name the check that would confirm or rule it out.

**Request stage vs network layer:** the stage is *when* in the request it fails; the layer is *which protocol family* is involved. They usually line up, but not always (DNS happens first in time but is an application-layer protocol).

| # | Symptom | Request stage | TCP/IP layer (OSI) | Likely code | Leading hypothesis | Alternatives to rule out | Check | Simulated verification | Fix (if confirmed) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | New EdgeOne setup; **all** users get 522; customer can open the origin IP directly | ② TCP | Transport (L4) | 522 | Origin firewall/security group allows the customer's IP but **drops EdgeOne's origin-pull IPs** | Wrong origin IP/port configured in EdgeOne; origin rate limiting; network path from EdgeOne to origin | Confirm origin address/port/protocol in EdgeOne config; test from a host outside the customer network (`nc -vz <origin-ip> 443`); check firewall logs at the failure time | Origin firewall log shows SYN packets from EdgeOne origin-pull IPs **dropped** at the reported times; EdgeOne origin config matches the origin | Add EdgeOne origin-pull IP ranges to the allowlist |
| 2 | Homepage updated yesterday; users still see the old one; status 200 | ④ HTTP (cache) | Application (L7) | 200 + `HIT` | Edge nodes are serving a **cached old copy** | Origin still serves the old file (deploy didn't complete); browser cache on the user's side; a different URL/variant being cached | Fetch the page **directly from origin** and via EdgeOne, compare content (e.g. checksum/`ETag`/`Last-Modified`); check `EO-Cache-Status` | Origin returns the new `ETag`; EdgeOne returns the old `ETag` with `HIT` | Purge the URL in EdgeOne. Prevent: shorter cache TTL for HTML, versioned file names for static assets |
| 3 | After switching origin-pull from HTTP to HTTPS, every request returns 525 | ③ TLS | Session/Presentation (L5–6), carried over TCP | 525 | Origin port EdgeOne pulls from **does not actually serve HTTPS** (still plain HTTP, or no certificate) | TLS version/cipher mismatch; certificate issue if origin verification is enabled; wrong origin port | `openssl s_client -connect <origin-ip>:443 -servername <host>` against the origin | `openssl s_client` to origin:443 fails with a non-TLS reply; the origin web server has no TLS listener configured on 443 | Enable HTTPS on the origin port with a valid certificate, or align EdgeOne's origin-pull protocol/port with what the origin supports |
| 4 | Report-generation endpoint: user waits a long time, then 524; other pages fine | ④ HTTP | Application (L7) | 524 | That endpoint takes **longer than EdgeOne's 15 s** origin response timeout | Origin overloaded only at certain times; database lock; endpoint hangs instead of being slow | Time the same request **directly against origin**; check origin app logs for that request | Direct request to origin takes ~25 s and completes with 200; other endpoints respond < 1 s | Short term: raise the HTTP response timeout (never above the client's timeout). Long term: make it async (start job → notify/poll when done) |
| 5 | DNS switched to EdgeOne 2 h ago; **some** users still hit the old server | ① DNS | Application (L7) protocol, first in time | — (no error; wrong destination) | Resolvers still hold the **old record until its TTL expires** | Old record still published on another authoritative server / wrong zone edited; hard-coded IPs or `/etc/hosts` on some clients; app or proxy caching DNS beyond TTL | `dig <domain>` against several public resolvers and the authoritative servers; check the old record's TTL; ask an affected user what their machine resolves | Authoritative servers all return the new CNAME; the old A record had TTL 86400; affected users' resolvers still return the old IP | Wait for the TTL to expire and keep the old server running meanwhile. Prevent: lower the TTL days before cutover, then switch (W6 cutover plan) |

---

## Notes on the reasoning

**Ticket 1 — why not certificates?**
522 happens during the **TCP handshake**, before TLS starts, so certificates can't be the cause. "All users fail, but the customer's direct access works" points toward something that treats EdgeOne's traffic differently, and a firewall allowlist is the most common such thing. But it is still a **hypothesis** until the firewall log (or a config check) confirms it; a wrong origin address in EdgeOne would produce the same symptom.

**Ticket 2 — 200 + HIT alone doesn't prove the content is stale.**
It only proves the node answered from cache. Staleness is proven by **comparing the content** the node returns with what the origin returns. If they match, the problem is elsewhere (e.g. the user's browser cache).

**Ticket 3 — "switched to HTTPS" is a config change on two sides.**
EdgeOne now speaks TLS to the origin. If the origin's port only speaks plain HTTP (or has no certificate), the handshake fails. Same family as 521: **origin-pull port/protocol mismatch**, showing up at a different stage.

**Ticket 4 — raising the timeout treats the symptom.**
It works, but users still wait 15+ s. Recommending an async design is the SA-level answer.

**Ticket 5 — "some users" is the key word, but TTL is not the only explanation.**
Partial impact after a DNS change most often points to **TTL caching**. Before concluding that, confirm the authoritative servers really return the new record everywhere, and that affected clients aren't using hard-coded IPs. This is also the W5 gate question ("after switching to CDN, some users still hit the old origin").