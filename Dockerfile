# syntax=docker/dockerfile:1

ARG PROXYLINK_COMMIT=44929c0984944870297c260dc43a4aa9262f9e1c
ARG SINGBOX_LX_TAG=v1.14.3-lx.21

FROM rust:1.88-bookworm AS rust-build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM golang:1.23-bookworm AS go-build
ENV GOTOOLCHAIN=auto
ARG PROXYLINK_COMMIT
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone https://github.com/Fanju6/Proxylink.git . \
    && git checkout "${PROXYLINK_COMMIT}"
WORKDIR /src/Proxylink
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /proxylink .

FROM golang:1.23-bookworm AS singbox-build
ENV GOTOOLCHAIN=auto
ARG SINGBOX_LX_TAG
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --recursive --branch "${SINGBOX_LX_TAG}" \
    https://github.com/Leadaxe/sing-box-lx.git .
RUN CGO_ENABLED=0 go build -trimpath \
    -tags "$(tr -d '\n' < release/DEFAULT_BUILD_TAGS_OTHERS),with_xhttp,with_purego" \
    -ldflags "-checklinkname=0 -s -w" \
    -o /sing-box ./cmd/sing-box

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates bash python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=rust-build /build/target/release/sub-fetch /usr/local/bin/sub-fetch
COPY --from=go-build /proxylink /usr/local/bin/proxylink
COPY --from=singbox-build /sing-box /usr/local/bin/sing-box

WORKDIR /opt/happ-sing-box
COPY scripts ./scripts
RUN chmod +x /opt/happ-sing-box/scripts/*.sh

ENV SINGBOX_CONFIG_DIR=/etc/sing-box \
    SINGBOX_CONFIG_PATH=/etc/sing-box/config.json \
    SINGBOX_DATA_DIR=/var/lib/sing-box \
    CONFIG_WORK_DIR=/tmp/happ-sing-box \
    SOCKS_LISTEN=0.0.0.0 \
    SOCKS_PORT=1080 \
    REFRESH_INTERVAL=3600 \
    WEBUI_PORT=8080 \
    WEBUI_LISTEN=0.0.0.0 \
    WEBUI_ENABLE=1

EXPOSE 1080 8080

ENTRYPOINT ["/opt/happ-sing-box/scripts/entrypoint.sh"]
