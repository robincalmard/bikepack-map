"""MCP handshake + hello tool probe. Stdlib only -- no extra deps.

Usage:
  python probe.py                         # local default http://127.0.0.1:8000
  python probe.py http://127.0.0.1:8000
  python probe.py https://chatgpt-mcp-hello.onrender.com

Exit 0 = all gates PASS. Exit 1 = first FAIL (message printed).

Note: On some Windows setups, responses to paths ending in /mcp are advertised
as Transfer-Encoding: chunked without chunk framing. This probe reads until
connection close so local validation still works; prefer Render for ChatGPT.
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import urllib.parse
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:8000"
TIMEOUT_S = 90
HANDSHAKE_VERSION = "2025-11-25"
DISCOVER_VERSION = "2026-07-28"


def _base_url(argv: list[str]) -> str:
    return (argv[1] if len(argv) > 1 else DEFAULT_BASE).rstrip("/")


def _mcp_url(base: str) -> str:
    return f"{base}/mcp"


def parse_sse_or_json(body: bytes) -> Any:
    text = body.decode("utf-8", "replace").strip()
    if not text:
        return None
    if text.startswith("event:") or "\ndata:" in text or text.startswith("data:"):
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise ValueError(f"SSE body had no data line: {text[:200]!r}")
    return json.loads(text)


def _raw_request(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """HTTP/1.1 request via sockets; tolerates broken chunked (read until close)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    hdrs = {k.lower(): v for k, v in headers.items()}
    hdrs.setdefault("host", f"{host}:{port}" if parsed.port else host)
    hdrs.setdefault("connection", "close")
    if body is not None:
        hdrs["content-length"] = str(len(body))

    lines = [f"{method} {path} HTTP/1.1"]
    for key, value in hdrs.items():
        lines.append(f"{key}: {value}")
    request = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
    if body:
        request += body

    sock: socket.socket | ssl.SSLSocket = socket.create_connection(
        (host, port), timeout=TIMEOUT_S
    )
    try:
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.sendall(request)
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    finally:
        sock.close()

    if b"\r\n\r\n" not in data:
        raise RuntimeError(f"no HTTP header terminator; got {data[:200]!r}")
    head, rest = data.split(b"\r\n\r\n", 1)
    head_lines = head.split(b"\r\n")
    status_line = head_lines[0].decode("latin-1", "replace")
    parts = status_line.split(" ", 2)
    status = int(parts[1]) if len(parts) >= 2 else 0

    resp_headers: dict[str, str] = {}
    for line in head_lines[1:]:
        if b":" not in line:
            continue
        k, v = line.split(b":", 1)
        resp_headers[k.decode("latin-1").lower()] = v.decode("latin-1").strip()

    # Prefer Content-Length when present and valid.
    body_out = rest
    cl = resp_headers.get("content-length")
    if cl is not None and cl.isdigit():
        body_out = rest[: int(cl)]
    elif resp_headers.get("transfer-encoding", "").lower() == "chunked":
        # Proper chunks OR broken (body is raw JSON with TE: chunked).
        body_out = _decode_chunked_or_raw(rest)

    return status, resp_headers, body_out


def _decode_chunked_or_raw(data: bytes) -> bytes:
    if not data:
        return data
    # Proper chunked starts with hex size line.
    first = data.split(b"\r\n", 1)[0]
    try:
        int(first, 16)
    except ValueError:
        # Broken framing (common on Windows for /mcp): body is raw payload.
        return data.rstrip(b"\r\n")

    out = b""
    remaining = data
    while remaining:
        if b"\r\n" not in remaining:
            break
        size_line, remaining = remaining.split(b"\r\n", 1)
        try:
            size = int(size_line.split(b";", 1)[0], 16)
        except ValueError:
            return data.rstrip(b"\r\n")
        if size == 0:
            break
        out += remaining[:size]
        remaining = remaining[size:]
        if remaining.startswith(b"\r\n"):
            remaining = remaining[2:]
    return out


def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
    return _raw_request(
        url,
        "GET",
        {"accept": "application/json", "user-agent": "hello-mcp-probe/1.0"},
    )


def http_status_only(
    url: str,
    method: str,
    headers: dict[str, str],
    timeout_s: float = 5,
) -> tuple[int, dict[str, str]]:
    """Read status and headers only, then close. Does not wait for an SSE body."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    hdrs = {k.lower(): v for k, v in headers.items()}
    hdrs.setdefault("host", f"{host}:{port}" if parsed.port else host)
    hdrs.setdefault("connection", "close")
    lines = [f"{method} {path} HTTP/1.1"]
    for key, value in hdrs.items():
        lines.append(f"{key}: {value}")
    request = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")

    sock: socket.socket | ssl.SSLSocket = socket.create_connection(
        (host, port), timeout=timeout_s
    )
    try:
        sock.settimeout(timeout_s)
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.sendall(request)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 65536:
                break
    finally:
        sock.close()

    if b"\r\n" not in data:
        raise RuntimeError(f"no HTTP status line; got {data[:200]!r}")
    head = data.split(b"\r\n\r\n", 1)[0]
    head_lines = head.split(b"\r\n")
    parts = head_lines[0].decode("latin-1", "replace").split(" ", 2)
    status = int(parts[1]) if len(parts) >= 2 else 0
    resp_headers: dict[str, str] = {}
    for line in head_lines[1:]:
        if b":" not in line:
            continue
        k, v = line.split(b":", 1)
        resp_headers[k.decode("latin-1").lower()] = v.decode("latin-1").strip()
    return status, resp_headers


def http_post(
    url: str, payload: dict[str, Any], extra_headers: dict[str, str]
) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "accept-encoding": "identity",
        "user-agent": "openai-mcp/1.0.0",
        **{k.lower(): v for k, v in extra_headers.items()},
    }
    return _raw_request(url, "POST", headers, body)


def fail(step: str, detail: str) -> None:
    print(f"FAIL  {step}: {detail}")
    sys.exit(1)


def pass_(step: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"PASS  {step}{suffix}")


def session_header(headers: dict[str, str]) -> dict[str, str]:
    sid = headers.get("mcp-session-id")
    return {"Mcp-Session-Id": sid} if sid else {}


def text_from_tool_result(result: dict[str, Any]) -> str:
    if "error" in result:
        raise ValueError(f"JSON-RPC error: {result['error']}")
    inner = result.get("result") or {}
    content = inner.get("content") or []
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    if parts:
        return "".join(parts)
    if isinstance(inner, str):
        return inner
    raise ValueError(f"No text content in tools/call result: {result!r}")


def main() -> None:
    base = _base_url(sys.argv)
    mcp = _mcp_url(base)
    print(f"Probing {base}")
    print("-" * 48)

    try:
        status, _, body = http_get(f"{base}/")
    except Exception as exc:
        fail("health", f"request failed: {exc}")
    if status != 200:
        fail("health", f"HTTP {status}: {body[:300]!r}")
    try:
        health = json.loads(body.decode("utf-8"))
    except Exception as exc:
        fail("health", f"invalid JSON: {exc}")
    if health.get("ok") is not True or health.get("mcp") != "/mcp":
        fail("health", f"unexpected body: {health!r}")
    pass_("health", 'GET / -> {"ok": true, "mcp": "/mcp"}')

    meta = {
        "io.modelcontextprotocol/protocolVersion": DISCOVER_VERSION,
        "io.modelcontextprotocol/clientInfo": {
            "name": "openai-mcp",
            "version": "1.0.0",
        },
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    modern_headers = {
        "Mcp-Protocol-Version": DISCOVER_VERSION,
    }

    try:
        status, _, body = http_post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": "openai-mcp-discover",
                "method": "server/discover",
                "params": {"_meta": meta},
            },
            {"Mcp-Method": "server/discover", **modern_headers},
        )
    except Exception as exc:
        fail("discover", f"request failed: {exc}")
    if status != 200:
        fail("discover", f"HTTP {status}: {body[:400]!r}")
    try:
        msg = parse_sse_or_json(body)
    except Exception as exc:
        fail("discover", f"parse: {exc}; body={body[:300]!r}")
    result = (msg or {}).get("result") or {}
    versions = result.get("supportedVersions") or []
    if DISCOVER_VERSION not in versions:
        fail("discover", f"{DISCOVER_VERSION} not in supportedVersions={versions!r}")
    if result.get("resultType") != "complete":
        fail("discover", f"resultType={result.get('resultType')!r}")
    pass_("discover", f"supportedVersions includes {DISCOVER_VERSION}")

    try:
        status, _, body = http_post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {"_meta": meta},
            },
            {"Mcp-Method": "tools/list", **modern_headers},
        )
    except Exception as exc:
        fail("tools/list", f"request failed: {exc}")
    if status != 200:
        fail("tools/list", f"HTTP {status}: {body[:400]!r}")
    try:
        msg = parse_sse_or_json(body)
    except Exception as exc:
        fail("tools/list", f"parse: {exc}; body={body[:300]!r}")
    listed = (msg or {}).get("result") or {}
    if listed.get("resultType") != "complete":
        fail("tools/list", f"resultType={listed.get('resultType')!r}; body={body[:300]!r}")
    tools = listed.get("tools") or []
    names = [t.get("name") for t in tools if isinstance(t, dict)]
    if "hello" not in names:
        fail("tools/list", f"'hello' not in {names!r}")
    pass_("tools/list", f"tools={names}")

    try:
        status, _, body = http_post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "hello",
                    "arguments": {"name": "Robin"},
                    "_meta": meta,
                },
            },
            {"Mcp-Method": "tools/call", "Mcp-Name": "hello", **modern_headers},
        )
    except Exception as exc:
        fail("tools/call", f"request failed: {exc}")
    if status != 200:
        fail("tools/call", f"HTTP {status}: {body[:400]!r}")
    try:
        msg = parse_sse_or_json(body)
        called = (msg or {}).get("result") or {}
        if called.get("resultType") != "complete":
            fail("tools/call", f"resultType={called.get('resultType')!r}; body={body[:300]!r}")
        text = text_from_tool_result(msg or {})
    except SystemExit:
        raise
    except Exception as exc:
        fail("tools/call", f"{exc}; body={body[:400]!r}")
    expected = "Hello, Robin!"
    if text != expected:
        fail("tools/call", f"expected {expected!r}, got {text!r}")
    pass_("tools/call", text)

    print("-" * 48)
    print("ALL PASS - safe to connect ChatGPT to this /mcp URL")
    sys.exit(0)


if __name__ == "__main__":
    main()
