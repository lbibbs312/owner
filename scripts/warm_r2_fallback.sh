#!/usr/bin/env sh
set -eu

BASE_URL="${1:-https://movedefense.com}"

for path in \
  "/?source=r2-warm" \
  "/app" \
  "/manifest.webmanifest" \
  "/sw.js" \
  "/static/icons/apple-touch-icon.png" \
  "/static/icons/icon-192.png" \
  "/static/icons/icon-512.png" \
  "/static/icons/icon-maskable-512.png"
do
  printf 'Warming %s%s\n' "$BASE_URL" "$path"
  curl -fsS -H "Cache-Control: no-cache" -o /dev/null "$BASE_URL$path"
done
