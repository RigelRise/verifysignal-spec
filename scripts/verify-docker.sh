#!/usr/bin/env bash
# Run the suite against the toolchain the CI declares, instead of whatever the host has installed.
# The sibling repos are mounted too, so the cross-repo legs resolve instead of skipping.
#
# Usage: scripts/verify-docker.sh [pytest args...]
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
parent="$(dirname "$repo_root")"
repo_name="$(basename "$repo_root")"
image="verifysignal-spec-verify"

docker build -q -t "$image" -f "$repo_root/Dockerfile.verify" "$repo_root" >/dev/null

# Mounting the PARENT is deliberate: tests/integration/test_authenticated_project_dogfood.py and the
# real-artifact install resolve the Core checkout by identity, and they SKIP when it is absent. A
# container that mounted only this repo would report a clean green having never run them.
exec docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
  -v "$parent":/w \
  -w "/w/$repo_name" \
  "$image" \
  sh -c 'python3 -m venv /tmp/v && /tmp/v/bin/pip install -q -e ".[dev]" && exec /tmp/v/bin/python -m pytest "$@"' -- "$@"
