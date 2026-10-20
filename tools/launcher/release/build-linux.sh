#!/bin/sh
# Reproducible standalone Linux release: Python/GTK and both native ELF architectures included.
set -eu
cd -- "$(dirname -- "$0")/../../.."
VERSION=${1:-0.1.0}
docker build -t forbidden-memories-launcher:jammy tools/launcher/release
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e "YFM_RELEASE_VERSION=$VERSION" \
  -v "$PWD:/src:z" -w /src forbidden-memories-launcher:jammy sh -ec '
    MEMORIES_VERSION="launcher-$YFM_RELEASE_VERSION" python3 tools/pc/build.py --target linux --release
    python3 tools/launcher/make_icon.py
    python3 -m PyInstaller --noconfirm --clean --distpath dist --workpath tmp/launcher-freeze tools/launcher/release/launcher.spec
    python3 tools/launcher/release/package_linux.py --version "$YFM_RELEASE_VERSION"
  '
