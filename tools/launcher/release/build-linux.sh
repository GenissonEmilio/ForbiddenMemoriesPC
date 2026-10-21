#!/bin/sh
# Reproducible standalone Linux release: Python/GTK and both native ELF architectures included.
set -eu
cd -- "$(dirname -- "$0")/../../.."
VERSION=${1:-}
docker build -t forbidden-memories-launcher:jammy tools/launcher/release
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e "YFM_RELEASE_VERSION=$VERSION" \
  -v "$PWD:/src:z" -w /src forbidden-memories-launcher:jammy sh -ec '
    if [ -z "$YFM_RELEASE_VERSION" ]; then
      YFM_RELEASE_VERSION=$(PYTHONPATH=tools/launcher python3 -c "from model import VERSION; print(VERSION)")
    fi
    MEMORIES_VERSION="launcher-$YFM_RELEASE_VERSION" python3 tools/pc/build.py --target linux --release
    python3 -c '\''from pathlib import Path; assert "#define SDL_AUDIO_DRIVER_PULSEAUDIO 1" in Path("tmp/pc/sdl-m32-portable/include-config-release/build_config/SDL_build_config.h").read_text(), "Release requires the PulseAudio backend"'\''
    python3 tools/launcher/make_icon.py
    python3 -m PyInstaller --noconfirm --clean --distpath dist --workpath tmp/launcher-freeze tools/launcher/release/launcher.spec
    python3 tools/launcher/release/package_linux.py --version "$YFM_RELEASE_VERSION"
  '
