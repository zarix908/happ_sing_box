#!/usr/bin/env python3
"""Merge Proxylink outbounds JSON into a runnable sing-box config."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

RESERVED_TAGS = {"proxy", "auto", "direct", "socks-in", "block", "dns-out"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def default_proxy_tag(leaf_tags: list[str]) -> str:
    if not leaf_tags:
        return "direct"
    tag = os.environ.get("OUTBOUND_TAG", "").strip()
    if tag and tag in leaf_tags:
        return tag
    return leaf_tags[0]


def load_proxylink_outbounds(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    outbounds = data.get("outbounds")
    if not isinstance(outbounds, list) or not outbounds:
        raise ValueError("proxylink output has no outbounds")
    return outbounds


def uniquify_tags(outbounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for idx, ob in enumerate(outbounds):
        tag = str(ob.get("tag") or f"node_{idx + 1}").strip()
        if not tag or tag in RESERVED_TAGS:
            tag = f"node_{idx + 1}"
        seen[tag] = seen.get(tag, 0) + 1
        if seen[tag] > 1:
            tag = f"{tag}_{seen[tag]}"
        ob = dict(ob)
        ob["tag"] = tag
        result.append(ob)
    return result


def socks_inbound() -> dict[str, Any]:
    inbound: dict[str, Any] = {
        "type": "socks",
        "tag": "socks-in",
        "listen": os.environ.get("SOCKS_LISTEN", "0.0.0.0"),
        "listen_port": env_int("SOCKS_PORT", 1080),
    }
    user = os.environ.get("SOCKS_USER", "").strip()
    password = os.environ.get("SOCKS_PASS", "").strip()
    if user or password:
        inbound["users"] = [{"username": user, "password": password}]
    return inbound


def build_config(leaf_outbounds: list[dict[str, Any]]) -> dict[str, Any]:
    leaf_tags = [ob["tag"] for ob in leaf_outbounds]
    use_urltest = env_bool("ENABLE_URLTEST", False)
    default_tag = default_proxy_tag(leaf_tags)

    if use_urltest:
        selector_members = ["auto", *leaf_tags, "direct"]
        selector_default = (
            default_tag if os.environ.get("OUTBOUND_TAG", "").strip() else "auto"
        )
        if selector_default not in selector_members:
            selector_default = "auto"
    else:
        selector_members = [*leaf_tags, "direct"]
        selector_default = default_tag

    outbounds: list[dict[str, Any]] = [
        {
            "type": "selector",
            "tag": "proxy",
            "outbounds": selector_members,
            "default": selector_default,
        },
        *leaf_outbounds,
        {"type": "direct", "tag": "direct"},
    ]

    if use_urltest:
        outbounds.insert(
            1,
            {
                "type": "urltest",
                "tag": "auto",
                "outbounds": leaf_tags[:],
                "url": os.environ.get(
                    "URLTEST_URL", "https://www.gstatic.com/generate_204"
                ),
                "interval": os.environ.get("URLTEST_INTERVAL", "5m"),
            },
        )

    return {
        "log": {
            "level": os.environ.get("SINGBOX_LOG_LEVEL", "info"),
            "timestamp": True,
        },
        "dns": {
            "servers": [{"tag": "local", "type": "local"}],
            "final": "local",
        },
        "inbounds": [socks_inbound()],
        "outbounds": outbounds,
        "route": {
            "auto_detect_interface": True,
            "final": "proxy",
            "default_domain_resolver": {"server": "local"},
        },
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <proxylink.json> <output.json>", file=sys.stderr)
        return 2

    proxylink_path, output_path = sys.argv[1], sys.argv[2]
    try:
        leaf = uniquify_tags(load_proxylink_outbounds(proxylink_path))
        config = build_config(leaf)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2)
            fh.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
