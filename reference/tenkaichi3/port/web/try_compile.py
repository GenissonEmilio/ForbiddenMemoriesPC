#!/usr/bin/env python3
"""Feasibility check for the browser build: compiles every game source with emcc (wasm32) the way
undefined.py's compile_ee does for the 32-bit build (preprocess, eeconst, compile). Objects go to port/build/obj_web."""
import concurrent.futures, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "port/tools"))
import portsrc, eeconst

OBJ = ROOT / "port/build/obj_web"
CC = ["emcc", "-std=gnu89", "-O2", "-g0", "-fno-strict-aliasing", "-ffp-contract=off", "-fcommon", "-w",
      "-fno-builtin", "-Wno-error=return-mismatch", "-Wno-error=implicit-function-declaration", "-Wno-error=int-conversion",
      "-Wno-error=incompatible-pointer-types", "-include", "port_libm.h", "-Iinclude", "-Iport/include", "-include", "port_compat.h"]

# Symbols x86 tolerates under two kinds and wasm-ld does not (a function and data with one name).
PER_FILE = {"main.c": ["-DMainMenu_StartBallLoops=PortWeb_OverlayArea"]}  # overlay load address: never written on PC

def cc(f):
    o = OBJ / (str(f.relative_to(ROOT / "src")).replace("/", "_")[:-2] + ".o")
    src, _, _ = portsrc.prepare(f)
    extra = PER_FILE.get(f.name, [])
    r = subprocess.run(CC + extra + [f"-I{f.parent}", "-E", str(src)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        return f, r.stderr
    i = o.with_suffix(".i")
    i.write_text(eeconst.transform(r.stdout))
    c2 = []; skip = False
    for a in CC:
        if skip: skip = False
        elif a == "-include": skip = True
        else: c2.append(a)
    # LLVM IR before any optimisation: irweb.py rewrites it (float maths, signatures), emcc optimises afterwards
    r = subprocess.run(c2 + ["-Xclang", "-disable-llvm-passes", "-S", "-emit-llvm", "-x", "cpp-output", str(i),
                             "-o", str(o.with_suffix(".raw.ll"))], cwd=ROOT, capture_output=True, text=True)
    return f, (r.stderr if r.returncode else None)

if __name__ == "__main__":
    OBJ.mkdir(parents=True, exist_ok=True)
    fs = portsrc.sources()
    with concurrent.futures.ProcessPoolExecutor(10) as ex:
        res = list(ex.map(cc, fs))
    bad = [(f, e) for f, e in res if e]
    for f, e in bad:
        print("FAILED", f.relative_to(ROOT), next((l for l in e.splitlines() if "error" in l), e.strip()[:200])[:220])
    print(f"{len(fs) - len(bad)} / {len(fs)} game sources compiled")
