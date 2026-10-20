#!/usr/bin/env python3
"""Patch Proxylink sing-box outbounds using fields from the original share URI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uri_list import load_uri_entries  # noqa: E402


def _query(uri: str) -> dict[str, list[str]]:
    parsed = urlparse(uri)
    return parse_qs(parsed.query, keep_blank_values=True)


def _first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or []
    return unquote(values[0]).strip() if values else ""


def transport_from_uri(uri: str) -> dict[str, Any] | None:
    params = _query(uri)
    network = _first(params, "type").lower() or "tcp"
    if network in ("tcp", "raw", "none"):
        return None
    if network in ("xhttp", "splithttp"):
        transport: dict[str, Any] = {"type": "xhttp"}
        path = _first(params, "path")
        if path:
            transport["path"] = path
        mode = _first(params, "mode")
        if mode:
            transport["mode"] = mode
        host = _first(params, "host")
        if host:
            transport["host"] = host
        return transport
    if network == "ws":
        transport = {"type": "ws"}
        if path := _first(params, "path"):
            transport["path"] = path
        if host := _first(params, "host"):
            transport["headers"] = {"Host": host}
        return transport
    if network == "grpc":
        transport = {"type": "grpc"}
        if service := _first(params, "serviceName") or _first(params, "service_name"):
            transport["service_name"] = service
        return transport
    if network in ("http", "h2"):
        transport = {"type": "http"}
        if path := _first(params, "path"):
            transport["path"] = path
        if host := _first(params, "host"):
            transport["host"] = host
        return transport
    if network == "httpupgrade":
        transport = {"type": "httpupgrade"}
        if path := _first(params, "path"):
            transport["path"] = path
        if host := _first(params, "host"):
            transport["host"] = host
        return transport
    return None


def flow_from_uri(uri: str) -> str:
    return _first(_query(uri), "flow")


def patch_outbound(outbound: dict[str, Any], uri: str) -> dict[str, Any]:
    ob = dict(outbound)
    transport = transport_from_uri(uri)
    if transport:
        ob["transport"] = transport
    flow = flow_from_uri(uri)
    if flow and ob.get("type") == "vless":
        ob["flow"] = flow
    return ob


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"usage: {sys.argv[0]} <uri.txt> <proxylink.json> <output.json>",
            file=sys.stderr,
        )
        return 2
    uri_path, proxylink_path, output_path = sys.argv[1:4]
    entries = load_uri_entries(uri_path)
    if not entries:
        raise SystemExit("error: no URI in input file")
    uri = entries[0].uri

    with open(proxylink_path, encoding="utf-8") as fh:
        data = json.load(fh)
    outbounds = data.get("outbounds")
    if not isinstance(outbounds, list) or not outbounds:
        raise SystemExit("error: proxylink output has no outbounds")

    data["outbounds"] = [patch_outbound(outbounds[0], uri)]
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
