# happ-sing-box

Docker image that decrypts and fetches Happ / v2RayTun subscriptions with [hpwnr](https://github.com/Omegaplexx/hpwnr), converts supported share links through [Proxylink](https://github.com/Fanju6/Proxylink), and runs [sing-box](https://github.com/SagerNet/sing-box) with an internal SOCKS5 listener.

## Flow

```text
SUBSCRIPTION_URL
  -> sub-fetch (hpwnr fetch + sing-box-compatible URI list)
  -> proxylink (URI -> sing-box outbounds)
  -> merge_singbox_config.py (SOCKS inbound, selector; optional urltest)
  -> sing-box run
```

Supported outbound protocols depend on Proxylink (VLESS, VMess, Trojan, Shadowsocks, SOCKS, HTTP, Hysteria2, AnyTLS, TUIC, WireGuard endpoint, and more). **VLESS XHTTP** (common on Happ/Durev-style subs) needs the bundled **sing-box-lx** core and URI transport enrichment—stock sing-box drops XHTTP.

## Quick start

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Set `SUBSCRIPTION_URL` to your Happ/v2RayTun link or plain HTTPS subscription URL.

3. Build and run (publish the port yourself):

   ```bash
   docker compose build
   docker compose run --rm -p 1080:1080 happ-sing-box
   ```

   Or with plain Docker:

   ```bash
   docker build -t happ-sing-box .
   docker run --rm -p 1080:1080 --env-file .env happ-sing-box
   ```

4. Point applications at `socks5://127.0.0.1:1080` (or your published host/port).

5. Open **http://127.0.0.1:8080/** to pick which subscription URI to use (default: first in the list). Only that node is converted—no slow urltest sweep across every server.

## Environment

| Variable | Default | Description |
| --- | --- | --- |
| `SUBSCRIPTION_URL` | — | Encrypted Happ/v2RayTun link or HTTPS subscription URL |
| `SUBSCRIPTION_FILE` | — | Local subscription file (used by tests; skips network fetch) |
| `HPWNR_UA` | empty | Fetch User-Agent (`happ`, `incy`, `v2`, …) |
| `HPWNR_HWID` | empty | Sent as `X-HWID` when fetching |
| `SOCKS_LISTEN` | `0.0.0.0` | SOCKS bind address inside the container |
| `SOCKS_PORT` | `1080` | SOCKS port inside the container |
| `SOCKS_USER` / `SOCKS_PASS` | empty | Optional SOCKS credentials |
| `REFRESH_INTERVAL` | `3600` | Seconds between subscription refreshes |
| `SELECTED_URI_INDEX` | `0` | Which URI line to use (also set via Web UI) |
| `OUTBOUND_TAG` | empty | Override sing-box selector default when using multiple outbounds |
| `WEBUI_PORT` | `8080` | Node picker HTTP port |
| `WEBUI_LISTEN` | `0.0.0.0` | Web UI bind address |
| `WEBUI_ENABLE` | `1` | Set `0` to disable the Web UI |
| `ENABLE_URLTEST` | `0` | Set `1` to add urltest “auto” (probes every node) |
| `URLTEST_URL` | Google 204 | Health-check URL when `ENABLE_URLTEST=1` |
| `URLTEST_INTERVAL` | `5m` | urltest interval when enabled |
| `SINGBOX_LOG_LEVEL` | `info` | sing-box log level |

Compose exposes container port `1080` only (`expose`, not `ports`) so you choose how to publish it.

## Refresh behavior

- On startup the container generates and validates config, then starts sing-box.
- Every `REFRESH_INTERVAL` seconds it fetches again.
- sing-box restarts only when a new config differs from the current file.
- Failed refreshes keep the last good config.

## Development

Build the fetch helper (hpwnr is pulled from GitHub tag `v1.0.2`, not crates.io):

```bash
cargo build --release
```

Run fixture tests (requires `proxylink` and `sing-box` on `PATH`):

```bash
chmod +x tests/run_tests.sh
./tests/run_tests.sh
```

Generate config from a local URI list:

```bash
export SUBSCRIPTION_FILE=tests/fixtures/sample-uris.txt
export CONFIG_WORK_DIR=/tmp/happ-sing-box-dev
export SINGBOX_CONFIG_DIR=/tmp/happ-sing-box-dev/etc
./scripts/generate-config.sh
```

## Security

Use this only with subscriptions you are allowed to access. Publishing SOCKS without authentication exposes your proxy to anyone who can reach the port; set `SOCKS_USER` and `SOCKS_PASS` when exposing beyond localhost.

## License

Third-party tools (hpwnr, Proxylink, sing-box) remain under their respective licenses. This wrapper project is provided as-is.
