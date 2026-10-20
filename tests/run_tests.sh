#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="${ROOT}/tests/fixtures"
WORK="${ROOT}/tests/.work"
PROXYLINK="${PROXYLINK:-proxylink}"
SING_BOX="${SING_BOX:-sing-box}"

mkdir -p "${WORK}"
rm -rf "${WORK:?}/"*

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_cmd python3
require_cmd "${PROXYLINK}"
require_cmd "${SING_BOX}"

run_generate() {
  local uris_file="$1"
  local out_config="$2"
  shift 2
  export SUBSCRIPTION_FILE="${uris_file}"
  export CONFIG_WORK_DIR="${WORK}/cfg-$$"
  export SINGBOX_CONFIG_DIR="${WORK}/etc-$$"
  export SINGBOX_CONFIG_PATH="${SINGBOX_CONFIG_DIR}/config.json"
  mkdir -p "${CONFIG_WORK_DIR}" "${SINGBOX_CONFIG_DIR}"

  (
    while [[ $# -gt 0 ]]; do
      export "$1"
      shift
    done
    cd "${ROOT}"
    cargo run --quiet --bin sub-fetch >"${CONFIG_WORK_DIR}/uris.txt"
    local pick_index="${SELECTED_URI_INDEX:-0}"
    python3 scripts/uri_list.py pick \
      "${CONFIG_WORK_DIR}/uris.txt" \
      "${pick_index}" \
      "${CONFIG_WORK_DIR}/uris.selected.txt"
    "${PROXYLINK}" -file "${CONFIG_WORK_DIR}/uris.selected.txt" -format singbox \
      -o "${CONFIG_WORK_DIR}/proxylink.json"
    python3 scripts/enrich_outbound_from_uri.py \
      "${CONFIG_WORK_DIR}/uris.selected.txt" \
      "${CONFIG_WORK_DIR}/proxylink.json" \
      "${CONFIG_WORK_DIR}/proxylink.enriched.json"
    python3 scripts/merge_singbox_config.py \
      "${CONFIG_WORK_DIR}/proxylink.enriched.json" \
      "${out_config}"
    "${SING_BOX}" check -c "${out_config}"
  )
}

echo "== default node (first URI) =="
run_generate "${FIXTURES}/sample-uris.txt" "${WORK}/sample.json"
python3 - <<'PY' "${WORK}/sample.json"
import json, sys
cfg = json.load(open(sys.argv[1]))
types = {o.get("type") for o in cfg["outbounds"]}
assert "urltest" not in types
proxy = next(o for o in cfg["outbounds"] if o.get("tag") == "proxy")
leaf = [o for o in cfg["outbounds"] if o.get("type") not in ("selector", "urltest", "direct")]
assert len(leaf) == 1
assert proxy["default"] == leaf[0]["tag"]
assert cfg["inbounds"][0]["type"] == "socks"
assert cfg["inbounds"][0]["listen_port"] == 1080
print("ok default node", leaf[0]["tag"])
PY

echo "== selected URI index =="
run_generate "${FIXTURES}/sample-uris.txt" "${WORK}/trojan.json" SELECTED_URI_INDEX=1
python3 - <<'PY' "${WORK}/trojan.json"
import json, sys
cfg = json.load(open(sys.argv[1]))
leaf = [o for o in cfg["outbounds"] if o.get("type") == "trojan"]
assert len(leaf) == 1
print("ok selected index", leaf[0]["tag"])
PY

echo "== duplicate tags =="
run_generate "${FIXTURES}/duplicate-tags.txt" "${WORK}/dup.json"
python3 - <<'PY' "${WORK}/dup.json"
import json, sys
cfg = json.load(open(sys.argv[1]))
tags = [o["tag"] for o in cfg["outbounds"] if o.get("type") == "vless"]
assert tags == ["dup", "dup_2"]
print("ok duplicate tags", tags)
PY

echo "== socks authentication =="
run_generate "${FIXTURES}/sample-uris.txt" "${WORK}/auth.json" \
  SOCKS_USER=alice SOCKS_PASS=secret
python3 - <<'PY' "${WORK}/auth.json"
import json, sys
cfg = json.load(open(sys.argv[1]))
users = cfg["inbounds"][0].get("users") or []
assert users == [{"username": "alice", "password": "secret"}]
print("ok socks auth")
PY

echo "== invalid subscription =="
if SUBSCRIPTION_FILE="${FIXTURES}/empty.txt" \
  CONFIG_WORK_DIR="${WORK}/bad" \
  cargo run --quiet --bin sub-fetch 2>/dev/null; then
  echo "expected sub-fetch to fail on empty input" >&2
  exit 1
fi
touch "${FIXTURES}/empty.txt"
if SUBSCRIPTION_FILE="${FIXTURES}/empty.txt" \
  cargo run --quiet --bin sub-fetch 2>/dev/null; then
  echo "expected sub-fetch to fail on empty file" >&2
  exit 1
fi
rm -f "${FIXTURES}/empty.txt"
echo "ok invalid subscription"

echo "all tests passed"
