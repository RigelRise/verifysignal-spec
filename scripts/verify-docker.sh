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
docker_platform="linux/amd64"
container_core_dir="${VERIFYSIGNAL_CORE_DIR:-/w/verifysignal}"
container_spec_dir="${VERIFYSIGNAL_SPEC_DIR:-/w/$repo_name}"
container_core_node_modules="$(mktemp -d "${TMPDIR:-/tmp}/verifysignal-spec-core-node-modules.XXXXXX")"
trap 'rm -rf -- "$container_core_node_modules"' EXIT

case "$container_core_dir" in
  /w/*) ;;
  *)
    echo "VERIFYSIGNAL_CORE_DIR must be a direct /w sibling path inside the verifier container." >&2
    exit 2
    ;;
esac
core_repo_name="${container_core_dir#/w/}"
case "$core_repo_name" in
  ""|*/*|.|..)
    echo "VERIFYSIGNAL_CORE_DIR must identify one direct sibling checkout under /w." >&2
    exit 2
    ;;
esac
if [ ! -f "$parent/$core_repo_name/package-lock.json" ]; then
  echo "Pinned Core checkout is unavailable at $parent/$core_repo_name." >&2
  exit 2
fi

export VERIFYSIGNAL_CORE_DIR="$container_core_dir"
export VERIFYSIGNAL_SPEC_DIR="$container_spec_dir"

docker build --platform "$docker_platform" -q -t "$image" -f "$repo_root/Dockerfile.verify" "$repo_root" >/dev/null

# Mounting the PARENT is deliberate: tests/integration/test_authenticated_project_dogfood.py and the
# real-artifact install resolve the Core checkout by identity, and they SKIP when it is absent. A
# container that mounted only this repo would report a clean green having never run them.
# Forward the pin variables when set. product-truth.yml pins all three repos at job level, and a
# suite that behaves differently under a pin than under a scan is environment-dependent — which is
# the defect this whole change is about. To reproduce that job's environment locally:
#   VERIFYSIGNAL_CORE_DIR=/w/<core-dirname> \
#   VERIFYSIGNAL_SPEC_DIR=/w/<spec-dirname> \
#   VERIFYSIGNAL_BACKEND_DIR=/w/<backend-dirname> scripts/verify-docker.sh
# The paths are container-side (/w is the mounted parent), which is why they are not derived here.
pins=()
for var in VERIFYSIGNAL_CORE_DIR VERIFYSIGNAL_SPEC_DIR VERIFYSIGNAL_BACKEND_DIR; do
  if [ -n "${!var:-}" ]; then pins+=(-e "$var=${!var}"); fi
done

docker run --rm --platform "$docker_platform" \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
  "${pins[@]}" \
  -v "$parent":/w \
  -v "$container_core_node_modules:$VERIFYSIGNAL_CORE_DIR/node_modules" \
  -w "/w/$repo_name" \
  "$image" \
  sh -c 'npm ci --prefix "$VERIFYSIGNAL_CORE_DIR" --no-audit --no-fund --silent && python3 -m venv /tmp/v && /tmp/v/bin/pip install -q -e ".[dev]" && exec /tmp/v/bin/python -m pytest "$@"' -- "$@"
