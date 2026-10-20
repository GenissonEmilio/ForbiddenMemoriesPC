#!/usr/bin/env python3
"""Import your Forbidden Memories disc, build the native PC port, and validate gameplay."""
import argparse
import ctypes.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools/pc"))
from import_disc import GameFilesError, ImportError_, import_disc, inspect_disc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", "--iso", dest="rom", type=Path,
                        help="Your USA raw BIN/IMG, or a RAR/ZIP containing it (nested archives supported)")
    parser.add_argument("--check", action="store_true", help="Check the local prerequisites without building")
    parser.add_argument("--skip-test", action="store_true", help="Build without the gameplay regression suite")
    parser.add_argument("--play", action="store_true", help="Open the game after successful installation")
    args = parser.parse_args()
    target = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
    required = ["python3", "gcc", "ld", "objcopy", "nm", "readelf", "objdump"] if target == "linux" else []
    missing = [tool for tool in required if not shutil.which(tool)]
    print("Native PC target:", target, flush=True)
    if missing:
        parser.exit(1, "Missing build tools: " + ", ".join(missing) + "\n")
    if args.check:
        print("Build tools: available. CMake, Ninja and target libraries are fetched when needed.")
        print("RAR support:", "libarchive available" if ctypes.util.find_library("archive") else "unpack to BIN/IMG first")
        return 0
    try:
        disc = import_disc(args.rom) if args.rom else ROOT / "game/rpg-yfm.bin"
        inspect_disc(disc)
    except (ImportError_, GameFilesError, OSError, ValueError) as error:
        parser.exit(1, f"Disc setup failed: {error}\nUse --rom <your USA disc or RAR/ZIP>.\n")
    subprocess.run([sys.executable, "tools/pc/build.py", "--target", target], cwd=ROOT, check=True)
    binary = ROOT / {"linux": "tmp/pc/game32/memories-pc", "windows": "tmp/pc/game32/memories-pc.exe",
                     "macos": "tmp/pc/macos/memories-arm64"}[target]
    if not args.skip_test:
        subprocess.run([sys.executable, "tools/pc/validate_port.py", "--binary", str(binary), "--disc", str(disc)],
                       cwd=ROOT, check=True)
    print(f"Ready: {binary}", flush=True)
    if args.play:
        environment = dict(os.environ, MEMORIES_DISC=str(disc))
        return subprocess.run([str(binary)], cwd=ROOT, env=environment).returncode
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
