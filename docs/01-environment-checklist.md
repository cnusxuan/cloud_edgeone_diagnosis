# W1 — Environment Readiness Checklist

Machine: macOS (Apple, x86_64), checked on 2026-10-08.

| Tool | Version | Status | Used for |
|---|---|---|---|
| `curl` | 8.7.1 (LibreSSL 3.3.6, nghttp2 1.68.1) | ✅ Ready | Send requests, inspect response headers (`-I`), force HTTP version, Range requests (`-r`) |
| `dig` | 9.10.6 | ✅ Ready | DNS lookups, CNAME chain, `+trace` for full resolution path |
| `openssl` | 3.6.1 | ✅ Ready | `openssl s_client` to inspect TLS handshake and certificate chain |
| `traceroute` | system (`/usr/sbin/traceroute`) | ✅ Ready | Hop-by-hop path to a node or origin |
| `mtr` | — | ⚠️ Not installed | Continuous traceroute with per-hop loss/latency. Install: `brew install mtr` |
| `python3` | 3.14.3 | ✅ Ready | Runs `eo_diag.py` (standard library only) |
| `ping` | system | ✅ Ready | Latency and packet loss to a single IP |

## Notes found while checking

- **System `curl` has no HTTP/3 support.** Its `Features` line lists `HTTP2` but not `HTTP3`. HTTP/3 tests need a curl built with HTTP/3 (e.g. via Homebrew) or a browser; this is noted as a limitation in the W3 HTTP version comparison.
- **`curl` and `openssl` use different TLS libraries** (LibreSSL 3.3.6 vs OpenSSL 3.6.1). Error messages for the same TLS failure can differ between the two tools, and between macOS and Windows (Schannel). Read the meaning, not the exact wording.

## Quick verification commands

```bash
curl --version
dig -v
openssl version
python3 --version
which traceroute mtr
```
