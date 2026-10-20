#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG_DIR="${SINGBOX_CONFIG_DIR:-/etc/sing-box}"
CONFIG_PATH="${SINGBOX_CONFIG_PATH:-${CONFIG_DIR}/config.json}"
WORK_DIR="${CONFIG_WORK_DIR:-/tmp/happ-sing-box}"
URIS_FILE="${WORK_DIR}/uris.txt"
URIS_SELECTED="${WORK_DIR}/uris.selected.txt"
SELECTED_INDEX_FILE="${WORK_DIR}/selected.uri_index"
PROXYLINK_FILE="${WORK_DIR}/proxylink.json"
PROXYLINK_ENRICHED="${WORK_DIR}/proxylink.enriched.json"
NEW_CONFIG="${WORK_DIR}/config.new.json"

mkdir -p "${WORK_DIR}" "${CONFIG_DIR}"

log() {
  printf '[generate-config] %s\n' "$*" >&2
}

fetch_uris() {
  if [[ -n "${SUBSCRIPTION_FILE:-}" ]]; then
    log "using subscription file ${SUBSCRIPTION_FILE}"
    sub-fetch >"${URIS_FILE}"
    return
  fi
  if [[ -z "${SUBSCRIPTION_URL:-}" ]]; then
    log "SUBSCRIPTION_URL or SUBSCRIPTION_FILE is required"
    exit 1
  fi
  log "fetching subscription"
  sub-fetch >"${URIS_FILE}"
}

selected_uri_index() {
  local idx=0
  if [[ -f "${SELECTED_INDEX_FILE}" ]]; then
    idx="$(tr -dc '0-9' <"${SELECTED_INDEX_FILE}" | head -c 8 || true)"
    [[ -n "${idx}" ]] || idx=0
  fi
  printf '%s' "${idx}"
}

pick_selected_uri() {
  if [[ ! -s "${URIS_FILE}" ]]; then
    log "subscription produced no URIs"
    exit 1
  fi
  local idx
  idx="$(selected_uri_index)"
  python3 "${SCRIPT_DIR}/uri_list.py" pick \
    "${URIS_FILE}" \
    "${idx}" \
    "${URIS_SELECTED}"
  log "using URI index ${idx} ($(wc -l <"${URIS_FILE}") available)"
}

convert_outbounds() {
  pick_selected_uri
  if [[ ! -s "${URIS_SELECTED}" ]]; then
    log "selected URI is empty"
    exit 1
  fi
  log "converting selected URI with proxylink"
  proxylink -file "${URIS_SELECTED}" -format singbox -o "${PROXYLINK_FILE}"
  log "merging transport fields from share URI"
  python3 "${SCRIPT_DIR}/enrich_outbound_from_uri.py" \
    "${URIS_SELECTED}" \
    "${PROXYLINK_FILE}" \
    "${PROXYLINK_ENRICHED}"
}

merge_config() {
  python3 "${SCRIPT_DIR}/merge_singbox_config.py" \
    "${PROXYLINK_ENRICHED}" \
    "${NEW_CONFIG}"
}

validate_config() {
  sing-box check -c "${NEW_CONFIG}"
}

install_config() {
  if [[ -f "${CONFIG_PATH}" ]] && cmp -s "${NEW_CONFIG}" "${CONFIG_PATH}"; then
    log "config unchanged"
    rm -f "${NEW_CONFIG}"
    return 0
  fi
  mv "${NEW_CONFIG}" "${CONFIG_PATH}"
  log "installed ${CONFIG_PATH}"
  touch "${WORK_DIR}/config.changed"
}

main() {
  fetch_uris
  convert_outbounds
  merge_config
  validate_config
  install_config
}

main "$@"
