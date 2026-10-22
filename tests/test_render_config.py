"""Render blueprint must start the module that exists in each service root.

ChatGPT deploys failed when the map service ran `uvicorn main:app` at the
repo root, where only `server.py` exists. `main.py` lives under `hello_mcp/`.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _services(text: str) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  - "):
            current = {}
            services.append(current)
            rest = line[4:]
            if ":" in rest:
                key, value = rest.split(":", 1)
                current[key.strip()] = value.strip()
            continue
        if current is not None and line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            current[key.strip()] = value.strip()
    return services


def _uvicorn_module(start_command: str) -> str:
    parts = start_command.split()
    assert parts[0] == "uvicorn", start_command
    assert ":" in parts[1], start_command
    return parts[1].split(":", 1)[0]


def test_each_render_service_starts_a_module_that_exists() -> None:
    services = _services((ROOT / "render.yaml").read_text(encoding="utf-8"))
    by_name = {service["name"]: service for service in services}

    app = by_name["bikepack-map"]
    assert "rootDir" not in app
    assert app["startCommand"].startswith("uvicorn server:app")

    hello = by_name["chatgpt-mcp-hello"]
    assert hello["rootDir"] == "hello_mcp"
    assert hello["startCommand"].startswith("uvicorn main:app")

    for service in services:
        root = ROOT / service.get("rootDir", "")
        module = _uvicorn_module(service["startCommand"])
        assert (root / f"{module}.py").is_file(), service
