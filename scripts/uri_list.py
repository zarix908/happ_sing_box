#!/usr/bin/env python3
"""Parse sing-box-style proxy share URIs for display and selection."""

from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote


@dataclass(frozen=True)
class ProxyUriEntry:
    index: int
    scheme: str
    host: str
    name: str
    uri: str

    def to_json(self) -> dict[str, str | int]:
        return asdict(self)


_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", re.ASCII)
_HOST_RE = re.compile(
    r"^[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/#?]+@)?([^/?#]+)", re.ASCII
)


def _display_name(uri: str, scheme: str, host: str) -> str:
    if "#" in uri:
        _, _, frag = uri.rpartition("#")
        label = unquote(frag).strip()
        if label:
            return label
    if host:
        return f"{scheme} · {host}"
    return scheme or uri[:48]


def parse_uri_line(index: int, line: str) -> ProxyUriEntry | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    scheme_m = _SCHEME_RE.match(raw)
    scheme = scheme_m.group(1).lower() if scheme_m else "unknown"
    host_m = _HOST_RE.match(raw)
    host = host_m.group(1) if host_m else ""
    name = _display_name(raw, scheme, host)
    return ProxyUriEntry(index=index, scheme=scheme, host=host, name=name, uri=raw)


def load_uri_entries(path: str | Path) -> list[ProxyUriEntry]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    entries: list[ProxyUriEntry] = []
    for line in text.splitlines():
        entry = parse_uri_line(len(entries), line)
        if entry is not None:
            entries.append(entry)
    return entries


def write_selected_uri(
    uris_path: str | Path, index: int, dest: str | Path
) -> ProxyUriEntry:
    entries = load_uri_entries(uris_path)
    if not entries:
        raise ValueError("subscription produced no URIs")
    if index < 0 or index >= len(entries):
        raise IndexError(f"URI index {index} out of range (0..{len(entries) - 1})")
    chosen = entries[index]
    Path(dest).write_text(chosen.uri + "\n", encoding="utf-8")
    return chosen


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print("usage: uri_list.py pick <uris.txt> <index> <out.txt>", file=sys.stderr)
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "pick":
        _, _, uris_path, index_s, dest = sys.argv
        try:
            write_selected_uri(uris_path, int(index_s), dest)
        except (ValueError, IndexError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    print("usage: uri_list.py pick <uris.txt> <index> <out.txt>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
