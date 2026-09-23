#!/bin/sh
# Drop empty optional Caddy env vars so the Caddyfile placeholder defaults apply.
# An explicitly empty CADDY_EXTRA_SITE_ADDRESS makes Caddy refuse to start.
if [ -z "${CADDY_EXTRA_SITE_ADDRESS:-}" ]; then
  unset CADDY_EXTRA_SITE_ADDRESS
fi
if [ -z "${CADDY_EXTRA_UPSTREAM:-}" ]; then
  unset CADDY_EXTRA_UPSTREAM
fi
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
