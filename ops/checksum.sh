#!/bin/sh
# Source from backup/restore: GNU Linux and macOS SHA-256 implementations.
checksum() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
  else shasum -a 256 "$@"
  fi
}
