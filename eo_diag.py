import socket
import ssl
import sys
import time
from urllib.parse import urlparse


# Timeouts mirror EdgeOne's origin-pull defaults
CONNECT_TIMEOUT = 5   # seconds, TCP connect
READ_TIMEOUT = 15     # seconds, waiting for the HTTP response


STATUS_HINTS = {
    200: "OK",
    206: "Partial content (Range request)",
    301: "Permanent redirect - browsers cache it; use 302 if temporary",
    302: "Temporary redirect",
    304: "Not modified - client copy is still valid",
    400: "Bad request - EdgeOne may return this for disallowed methods",
    403: "Forbidden - check token auth / hotlink protection, or origin permissions",
    404: "Not found - check the file exists on origin (path, case)",
    416: "Range not satisfiable - requested range is beyond file size",
    418: "EdgeOne: domain config not found on node - check CNAME setup",
    423: "EdgeOne: request loop detected (CDN-Loop)",
    502: "Bad gateway - usually from origin's own proxy; check backend app",
    503: "Service unavailable - origin overloaded or in maintenance",
    504: "Gateway timeout - usually origin's proxy waiting on backend",
    520: "EdgeOne: origin reset the connection after the request",
    521: "EdgeOne: origin refused the TCP connection",
    522: "EdgeOne: TCP connection to origin timed out",
    523: "EdgeOne: origin domain DNS resolution failed",
    524: "EdgeOne: origin response timed out",
    525: "EdgeOne: TLS handshake with origin failed",
    545: "EdgeOne: Edge Function error",
    566: "EdgeOne: blocked by WAF managed rules",
    567: "EdgeOne: blocked by custom rules / rate limiting / bot management",
    570: "EdgeOne: platform-level rate limiting",
    571: "EdgeOne: domain-level rate limiting",
    579: "EdgeOne: dynamic rate limiting",
}


def check_dns(host):
    print(f"[1/4] DNS   Resolving {host} ...")
    start = time.time()
    try:
        canonical, aliases, ips = socket.gethostbyname_ex(host)
    except socket.gaierror as e:
        print(f"  [FAIL] Could not resolve host ({e})")
        print("  -> If this is the origin domain, EdgeOne would return 523")
        return None
    ms = (time.time() - start) * 1000
    print(f"  [OK]   Resolved in {ms:.0f} ms")
    if ms > 1000:
        print("  [WARN] DNS is slow (>1 s) - users may see a slow first load")
    if canonical != host:
        print(f"  CNAME: {host} -> {canonical}")
    print(f"  IPs:   {', '.join(ips)}")
    return ips[0]


def check_tcp(ip, port):
    print(f"[2/4] TCP   Connecting to {ip}:{port} ...")
    start = time.time()
    try:
        sock = socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT)
    except ConnectionRefusedError:
        print("  [FAIL] Connection refused (server sent RST)")
        print("  -> If this is the origin, EdgeOne would return 521")
        return None
    except TimeoutError:
        print(f"  [FAIL] No response within {CONNECT_TIMEOUT} s")
        print("  -> If this is the origin, EdgeOne would return 522")
        return None
    except OSError as e:
        print(f"  [FAIL] {e}")
        return None
    ms = (time.time() - start) * 1000
    print(f"  [OK]   Connected in {ms:.0f} ms")
    return sock


def check_tls(sock, host):
    print(f"[3/4] TLS   Handshaking with {host} ...")
    start = time.time()
    context = ssl.create_default_context()
    try:
        tls_sock = context.wrap_socket(sock, server_hostname=host)
    except ssl.SSLCertVerificationError as e:
        print(f"  [FAIL] Certificate verification failed ({e.verify_message})")
        print("  -> Check certificate expiry, hostname match, and chain")
        return None
    except (ssl.SSLError, ConnectionResetError, TimeoutError) as e:
        print(f"  [FAIL] TLS handshake failed ({e})")
        print("  -> If this is the origin, EdgeOne would return 525")
        return None
    ms = (time.time() - start) * 1000
    cert = tls_sock.getpeercert()
    subject = dict(x[0] for x in cert["subject"])
    issuer = dict(x[0] for x in cert["issuer"])
    print(f"  [OK]   {tls_sock.version()} handshake in {ms:.0f} ms")
    print(f"  Cert:  {subject.get('commonName')} (issued by {issuer.get('organizationName')})")
    print(f"  Valid until: {cert['notAfter']}")
    return tls_sock


def check_http(sock, host, path):
    print(f"[4/4] HTTP  HEAD {path} ...")
    start = time.time()
    request = (
        f"HEAD {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: eo-diag/0.1\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    sock.settimeout(READ_TIMEOUT)
    try:
        sock.sendall(request.encode())
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    except TimeoutError:
        print(f"  [FAIL] No response within {READ_TIMEOUT} s")
        print("  -> If this is the origin, EdgeOne would return 524")
        return None
    except ConnectionResetError:
        print("  [FAIL] Connection reset after the request was sent")
        print("  -> If this is the origin, EdgeOne would return 520")
        return None
    if not data:
        print("  [FAIL] Connection closed with no response")
        return None
    ms = (time.time() - start) * 1000
    head = data.split(b"\r\n\r\n")[0].decode(errors="replace")
    lines = head.split("\r\n")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    print(f"  [OK]   {lines[0]} (first byte in {ms:.0f} ms)")
    return lines[0], headers


def analyze(status_line, headers):
    print("\n=== Summary ===")
    code = int(status_line.split()[1])
    hint = STATUS_HINTS.get(code)
    if hint is None and 550 <= code <= 555:
        hint = STATUS_HINTS.get(code - 30)
    print(f"  Status:        {code} - {hint or 'See MDN / RFC 9110'}")

    server = headers.get("server", "-")
    via_edgeone = "eo-log-uuid" in headers
    origin_marks = [k for k in headers if k.startswith("x-cos-")]
    print(f"  Via EdgeOne:   {'yes' if via_edgeone else 'no'}")

    if via_edgeone:
        cache = headers.get("eo-cache-status", "-")
        print(f"  Cache:         {cache}")
        print(f"  EO-LOG-UUID:   {headers['eo-log-uuid']}  (share with support)")

    if 520 <= code <= 599:
        source = "EdgeOne node (custom status code)"
    elif origin_marks or (server != "-" and "edgeone" not in server.lower()):
        source = f"Origin (Server: {server})"
    elif "edgeone" in server.lower():
        source = "EdgeOne node"
    else:
        source = "Unknown"
    if via_edgeone and headers.get("eo-cache-status") == "HIT":
        source += " - served from EdgeOne cache"
    print(f"  Likely source: {source}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://edgeone.ai"
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    ip = check_dns(host)
    if ip:
        sock = check_tcp(ip, port)
        if sock:
            if parsed.scheme == "https":
                sock = check_tls(sock, host)
            if sock:
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                result = check_http(sock, host, path)
                if result:
                    analyze(*result)
                sock.close()