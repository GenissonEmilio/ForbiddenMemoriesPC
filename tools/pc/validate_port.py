#!/usr/bin/env python3
"""Validate boot, ordinary inputs, a completed duel and deterministic save/load using your local disc."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from import_disc import inspect_disc, sha256

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--disc", type=Path, default=ROOT / "game/rpg-yfm.bin")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    binary, disc = args.binary.resolve(), args.disc.resolve()
    if not binary.is_file():
        parser.error(f"Native executable missing: {binary}")
    metadata = inspect_disc(disc)
    base = ROOT / "tmp/validation"; base.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="verified-", dir=base))
    output.mkdir(parents=True, exist_ok=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
    environment["MEMORIES_DISC"] = str(disc)
    cases = [
        ("first-duel", ["tools/pc/examples/control_first_duel.py", "--executable", str(binary), "--runs", "2",
                        "--out", str(output / "first-duel")]),
        ("full-duel", ["tools/pc/test_arm64_full_duel.py", "--binary", str(binary), "--disc", str(disc),
                       "--output", str(output / "full-duel")]),
        ("save-resume", ["tools/pc/test_state_resume.py", "--executable", str(binary),
                         "--out", str(output / "save-resume"), "map"]),
    ]
    report = {"executable_sha256": sha256(binary), "disc": metadata, "checks": {},
              "scope": "Native PC regression: title, name entry, story intro, deterministic first duel, "
                       "completed duel, 2000-frame save/load replay. Does not claim a full campaign playthrough."}
    for name, arguments in cases:
        print(f"Validating {name}...", flush=True)
        log = output / (name + ".log")
        with log.open("w") as stream:
            result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=environment,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=900)
        report["checks"][name] = {"passed": result.returncode == 0, "log": log.name}
        if result.returncode:
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(log.read_text(errors="replace")[-8000:], file=sys.stderr)
            return result.returncode
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Native gameplay validation passed: {output / 'report.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
