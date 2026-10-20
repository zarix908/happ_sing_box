#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${SINGBOX_CONFIG_PATH:-/etc/sing-box/config.json}"
REFRESH_INTERVAL="${REFRESH_INTERVAL:-3600}"
SINGBOX_DATA_DIR="${SINGBOX_DATA_DIR:-/var/lib/sing-box}"
WORK_DIR="${CONFIG_WORK_DIR:-/tmp/happ-sing-box}"
CHANGED_MARKER="${WORK_DIR}/config.changed"

mkdir -p "$(dirname "${CONFIG_PATH}")" "${SINGBOX_DATA_DIR}"

SINGBOX_PID=""
WEBUI_PID=""

stop_webui() {
  if [[ -n "${WEBUI_PID}" ]] && kill -0 "${WEBUI_PID}" 2>/dev/null; then
    kill -TERM "${WEBUI_PID}" 2>/dev/null || true
    wait "${WEBUI_PID}" 2>/dev/null || true
  fi
  WEBUI_PID=""
}

stop_singbox() {
  if [[ -n "${SINGBOX_PID}" ]] && kill -0 "${SINGBOX_PID}" 2>/dev/null; then
    kill -TERM "${SINGBOX_PID}" 2>/dev/null || true
    wait "${SINGBOX_PID}" 2>/dev/null || true
  fi
  SINGBOX_PID=""
}

start_singbox() {
  stop_singbox
  sing-box run -D "${SINGBOX_DATA_DIR}" -c "${CONFIG_PATH}" &
  SINGBOX_PID=$!
}

on_signal() {
  printf '[entrypoint] shutting down\n' >&2
  stop_singbox
  stop_webui
  exit 0
}

start_webui() {
  if [[ "${WEBUI_ENABLE:-1}" == "0" ]]; then
    return 0
  fi
  stop_webui
  python3 /opt/happ-sing-box/scripts/webui.py &
  WEBUI_PID=$!
}

trap on_signal TERM INT

if ! /opt/happ-sing-box/scripts/generate-config.sh; then
  printf '[entrypoint] initial config generation failed\n' >&2
  exit 1
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  printf '[entrypoint] missing config at %s\n' "${CONFIG_PATH}" >&2
  exit 1
fi

start_singbox
start_webui

# Initial install may touch config.changed; ignore that once at boot.
rm -f "${CHANGED_MARKER}"

watch_config_changes() {
  while true; do
    sleep 2
    if [[ -f "${CHANGED_MARKER}" ]]; then
      rm -f "${CHANGED_MARKER}"
      printf '[entrypoint] config changed; restarting sing-box\n' >&2
      start_singbox
    fi
  done
}

watch_config_changes &

while true; do
  sleep "${REFRESH_INTERVAL}"
  if /opt/happ-sing-box/scripts/generate-config.sh; then
    if [[ -f "${CHANGED_MARKER}" ]]; then
      rm -f "${CHANGED_MARKER}"
      start_singbox
    fi
  else
    printf '[entrypoint] refresh failed; keeping last valid config\n' >&2
  fi
done
