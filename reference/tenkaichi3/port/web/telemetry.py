#!/usr/bin/env python3
"""Reads what the page sent the test server (?telemetry=1 -> port/build/telemetry.log, one JSON object per line).

    port/web/telemetry.py              summary: frame rate, busy share, memory, sound, errors, the last log lines
    port/web/telemetry.py --since N    only samples from the last N seconds of page time
    port/web/telemetry.py --grep TEXT  log lines containing TEXT
    (only the page load that reported last; --all for every one)"""
import json, pathlib, sys

LOG = pathlib.Path(__file__).resolve().parents[2] / "port/build/telemetry.log"


def main():
    rows = []
    for line in LOG.read_text().splitlines() if LOG.exists() else []:
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    rows = [r for r in rows if "t" in r]
    if rows and "--all" not in sys.argv:  # the page load that reported last (another tab may report too)
        sid = next((r["sid"] for r in reversed(rows) if r.get("sid")), None)
        rows = [r for r in rows if r.get("sid") == sid]
    if not rows:
        print("no telemetry yet")
        return 1
    if "--since" in sys.argv:
        cut = rows[-1]["t"] - 1000 * float(sys.argv[sys.argv.index("--since") + 1])
        rows = [r for r in rows if r["t"] >= cut]
    logs = [l for r in rows for l in r.get("log", [])]
    if "--grep" in sys.argv:
        g = sys.argv[sys.argv.index("--grep") + 1]
        print("\n".join(l for l in logs if g in l))
        return 0
    fps = [r["fps"] for r in rows if r.get("fps")]
    busy = [r["busy"] for r in rows if r.get("busy")]
    last = rows[-1]
    print(f"build {last['build']}, {len(rows)} samples over {(rows[-1]['t'] - rows[0]['t']) / 1000:.0f} s")
    if fps:
        s = sorted(fps)
        print(f"presented fps: median {s[len(s) // 2]:.1f}, worst {s[0]:.1f}, best {s[-1]:.1f}")
    if busy:
        s = sorted(busy)
        print(f"busy share: median {100 * s[len(s) // 2]:.0f}%, worst {100 * s[-1]:.0f}%  (of real time the program ran; the rest it waited)")
    print(f"memory: wasm {last['memMB']} MB, C heap top {last['heapMB']} MB, file cache {last['cacheMB']} MB; sound {last['audio']}")
    print(f"canvas {last['canvas']}, view {last['view']}, touch {last['touch']}")
    bad = [l for l in logs if "error" in l.lower() or "abort" in l.lower() or "not implemented" in l]
    if bad:
        print("errors:\n  " + "\n  ".join(bad[-15:]))
    print("last log lines:\n  " + "\n  ".join(logs[-12:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
