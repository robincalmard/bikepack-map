"""Probe v1 start-map MCP server (no ChatGPT).

Checks health → discover → initialize → tools/list → tools/call show_start_map.

Usage:
  python scripts/probe_start_mcp.py
  python scripts/probe_start_mcp.py http://127.0.0.1:8000

Exit 0 = all PASS. Needs the server running (python server.py).
Stdlib only. Tolerates broken Windows chunked framing like hello_mcp/probe.py.
"""

from __future__ import annotations

import json
import socket
import ssl
import sys
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASE = "http://127.0.0.1:8000"
TIMEOUT_S = 90
# Full server advertises handshake versions (not 2026-07-28) so ChatGPT falls back.
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


def _decode_chunked_or_raw(data: bytes) -> bytes:
    if not data:
        return data
    first = data.split(b"\r\n", 1)[0]
    try:
        int(first, 16)
    except ValueError:
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


def _raw_request(
    url: str,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
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
    parts = head_lines[0].decode("latin-1", "replace").split(" ", 2)
    status = int(parts[1]) if len(parts) >= 2 else 0

    resp_headers: dict[str, str] = {}
    for line in head_lines[1:]:
        if b":" not in line:
            continue
        k, v = line.split(b":", 1)
        resp_headers[k.decode("latin-1").lower()] = v.decode("latin-1").strip()

    body_out = rest
    cl = resp_headers.get("content-length")
    if cl is not None and cl.isdigit():
        body_out = rest[: int(cl)]
    elif resp_headers.get("transfer-encoding", "").lower() == "chunked":
        body_out = _decode_chunked_or_raw(rest)

    return status, resp_headers, body_out


def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
    return _raw_request(
        url,
        "GET",
        {"accept": "text/plain, application/json", "user-agent": "start-mcp-probe/1.0"},
    )


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
    text = body.decode("utf-8", "replace").strip()
    if text != "bikepack-map ok":
        fail("health", f"unexpected body: {text!r}")
    pass_("health", "GET / -> bikepack-map ok")

    meta = {
        "io.modelcontextprotocol/protocolVersion": DISCOVER_VERSION,
        "io.modelcontextprotocol/clientInfo": {
            "name": "openai-mcp",
            "version": "1.0.0",
        },
        "io.modelcontextprotocol/clientCapabilities": {},
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
            {"Mcp-Method": "server/discover", "Mcp-Protocol-Version": DISCOVER_VERSION},
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
    if result.get("resultType") != "complete":
        fail("discover", f"resultType={result.get('resultType')!r}")
    versions = result.get("supportedVersions") or []
    if not versions:
        fail("discover", f"empty supportedVersions: {result!r}")
    pass_("discover", f"supportedVersions={versions}")

    init_headers = {"Mcp-Protocol-Version": HANDSHAKE_VERSION}
    try:
        status, resp_headers, body = http_post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": HANDSHAKE_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "start-mcp-probe", "version": "1.0.0"},
                },
            },
            {"Mcp-Method": "initialize", **init_headers},
        )
    except Exception as exc:
        fail("initialize", f"request failed: {exc}")
    if status != 200:
        fail("initialize", f"HTTP {status}: {body[:400]!r}")
    try:
        msg = parse_sse_or_json(body)
    except Exception as exc:
        fail("initialize", f"parse: {exc}; body={body[:300]!r}")
    init_result = (msg or {}).get("result") or {}
    if not init_result:
        fail("initialize", f"no result: {msg!r}")
    session: dict[str, str] = {}
    sid = resp_headers.get("mcp-session-id")
    if sid:
        session["Mcp-Session-Id"] = sid
    pass_("initialize", f"server={init_result.get('serverInfo')}")

    try:
        status, _, body = http_post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            {"Mcp-Method": "tools/list", **init_headers, **session},
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
    tools = listed.get("tools") or []
    names = [t.get("name") for t in tools if isinstance(t, dict)]
    if "show_start_map" not in names:
        fail("tools/list", f"'show_start_map' not in {names!r}")
    if len(names) != 1:
        fail("tools/list", f"expected only show_start_map, got {names!r}")
    pass_("tools/list", f"tools={names}")

    try:
        status, _, body = http_post(
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "show_start_map",
                    "arguments": {"name": "Paris"},
                },
            },
            {
                "Mcp-Method": "tools/call",
                "Mcp-Name": "show_start_map",
                **init_headers,
                **session,
            },
        )
    except Exception as exc:
        fail("tools/call", f"request failed: {exc}")
    if status != 200:
        fail("tools/call", f"HTTP {status}: {body[:400]!r}")
    try:
        msg = parse_sse_or_json(body)
        called = (msg or {}).get("result") or {}
        text = text_from_tool_result(msg or {})
    except SystemExit:
        raise
    except Exception as exc:
        fail("tools/call", f"{exc}; body={body[:400]!r}")

    if not text.startswith("Mapped start: Paris"):
        fail("tools/call", f"unexpected text: {text!r}")

    structured = called.get("structuredContent") or {}
    places = structured.get("places") or []
    if len(places) != 1 or not places[0].get("found"):
        fail("tools/call", f"structuredContent places={places!r}")
    pin = places[0]
    if pin.get("role") != "start":
        fail("tools/call", f"expected role=start, got {pin!r}")
    if "lat" not in pin or "lon" not in pin:
        fail("tools/call", f"missing coords: {pin!r}")

    meta_out = called.get("_meta") or {}
    if "openai/outputTemplate" not in meta_out and "ui" not in meta_out:
        # Some stacks nest meta; also accept top-level on result
        fail("tools/call", f"missing widget _meta: {meta_out!r} keys={list(called.keys())}")

    pass_("tools/call", text)

    print("-" * 48)
    print("ALL PASS - start-map MCP structure looks good locally")
    print("Next: deploy this server to Render, then connect ChatGPT")
    sys.exit(0)


if __name__ == "__main__":
    main()
