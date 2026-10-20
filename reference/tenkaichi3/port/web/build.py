#!/usr/bin/env python3
"""Browser build of the port (WebAssembly, Emscripten). Counterpart of undefined.py + link.py for BT3_CC=web.

    port/web/build.py            compile what changed, rewrite the IR, generate data objects
    port/web/build.py --clean    from scratch

Every C file of the 32-bit build is compiled the same way here, through LLVM IR so that port/web/irweb.py can do
what -msoft-float and the x86 calling convention did there (see irweb.py). Needs: emcc (with its LLVM), python3.
The result contains code compiled from the game: keep it local, never publish it."""
import concurrent.futures, functools, hashlib, json, os, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "port/tools"))
import portsrc, eeconst  # noqa: E402

B = ROOT / "port/build"
OBJ = B / "obj_web"
OUT = B / "web"
WEB = ROOT / "port/web"
JOBS = os.cpu_count() or 8

# clang's errors that gcc (and the PS2 compiler) only warn about; the 32-bit clang build relaxes the same
LAX = ["-Wno-error=return-mismatch", "-Wno-error=implicit-function-declaration", "-Wno-error=int-conversion",
       "-Wno-error=incompatible-pointer-types", "-Wno-error=implicit-int"]
GAME = LAX + ["-std=gnu89", "-fno-strict-aliasing", "-ffp-contract=off", "-fcommon", "-w", "-fno-builtin",
        "-include", "port_libm.h", "-Iinclude", "-Iport/include", "-include", "port_compat.h"]
NEWLIB = LAX + ["-std=gnu89", "-fno-strict-aliasing", "-ffp-contract=off", "-fno-builtin", "-w", "-Iport/include", "-include", "newlib_shim.h"]
FOPEN = ["-Dfopen=Web_Fopen"]  # the port's file opens go through port/web/target/disc_*.c
PORTC = LAX + FOPEN + ["-std=gnu99", "-fno-strict-aliasing", "-ffp-contract=off", "-fno-builtin", "-w", "-Iinclude", "-Iport/include", "-Iport/src",
         "-Iport/web/include"]
SOFT = ["-DSF_FAST_CALLS", "-include", "math.h", "-include", "stdlib.h", "-include", "port_libm.h"]
HOSTC = LAX + FOPEN + ["-std=gnu99", "-fno-strict-aliasing", "-Wall", "-Wno-unused", "-Wno-misleading-indentation", "-w", f"-I{B / 'gen/gs'}",
         "-Iport/web/include", "--use-port=sdl3"]
CXX = FOPEN + ["-std=c++17", "-DIMGUI_IMPL_OPENGL_ES3", "-fno-exceptions", "-fno-rtti", "-w", "-Iport/third_party/imgui", "-Iport/src/gs", "--use-port=sdl3"]
# Symbols x86 tolerates under two kinds and wasm-ld does not (a function and data with one name).
PER_FILE = {"main.c": ["-DMainMenu_StartBallLoops=PortWeb_OverlayArea"]}  # overlay load address: never written on PC
HW_FLOAT = {"plat_libm.c", "plat_fastvec.c"}  # compiled with hardware floating point in every build
SKIP = {"gs_gpu.c"}  # the Vulkan back end: SDL's GPU API has no browser back end; the GL one draws (port/web/src/web_stubs.c)


def strip_includes(cmd):
    out, skip = [], False
    for a in cmd:
        if skip:
            skip = False
        elif a == "-include":
            skip = True
        else:
            out.append(a)
    return out


def units():
    """(name, source, flags, eeconst?, float pass?, language) of everything the program is made of."""
    us = []
    for f in portsrc.sources():
        us.append((str(f.relative_to(ROOT / "src")).replace("/", "_")[:-2], f, GAME + PER_FILE.get(f.name, []) + [f"-I{f.parent}"], True, True, "c"))
    for f in sorted((ROOT / "port/third_party/newlib_libm").glob("*.c")):
        us.append(("nl_" + f.stem, f, NEWLIB + [f"-I{f.parent}"], True, True, "c"))
    for f in [ROOT / "src/port/vu0_a.c", ROOT / "src/port/vu0_b.c"]:
        us.append(("pc_" + f.stem, f, PORTC + SOFT + ["-include", "vu0_names.h", "-DREF_VU0_EXTERN_ARITH"], False, True, "c"))
    for f in sorted((ROOT / "port/src").glob("*.c")):
        if f.name in HW_FLOAT:
            us.append(("pc_" + f.stem, f, PORTC, False, False, "c"))
        else:
            us.append(("pc_" + f.stem, f, PORTC + SOFT, True, True, "c"))
    for f in sorted((ROOT / "port/src/gs").glob("*.c")):
        if f.name not in SKIP:
            us.append(("gs_" + f.stem, f, HOSTC, False, False, "c"))
    for f in sorted((ROOT / "port/third_party/imgui").glob("*.cpp")) + sorted((ROOT / "port/src/gs").glob("*.cpp")):
        if "sdlgpu3" not in f.name:
            us.append(("cxx_" + f.stem, f, CXX, False, False, "c++"))
    for f in sorted((WEB / "src").glob("*.c")):
        us.append(("web_" + f.stem, f, ["-std=gnu99", "-w", "-Iinclude", "-Iport/include", "-Iport/src", "-Iport/web/include", "--use-port=sdl3"], False, False, "c"))
    return us


def stamp(u, preprocessed, compiler):
    name, f, flags, ee, fl, lang = u
    # Hash the compiler's actual input, including transitive/system headers.
    # Keep the transforms and compiler identity in the key as well: changing
    # an IR pass must rebuild the objects even when the C did not change.
    h = hashlib.sha256(json.dumps([str(f), flags, ee, fl, lang, compiler]).encode())
    h.update(preprocessed.encode())
    for path in (WEB / "build.py", WEB / "irweb.py", ROOT / "port/tools/eeconst.py", ROOT / "port/tools/portsrc.py"):
        h.update(path.read_bytes())
    return h.hexdigest()


@functools.lru_cache(maxsize=None)
def compiler_identity(cc):
    path = shutil.which(cc) or cc
    return path + "\n" + subprocess.run([cc, "--version"], cwd=ROOT, capture_output=True,
                                       text=True, check=True).stdout


def to_ir(u):
    """Source -> port/build/obj_web/<name>.raw.ll (unoptimised IR)."""
    name, f, flags, ee, fl, lang = u
    raw = OBJ / f"{name}.raw.ll"
    st = OBJ / f"{name}.stamp"
    src = f
    if name[:3] not in ("pc_", "gs_", "nl_", "cxx", "web"):
        src, _, _ = portsrc.prepare(f)
    cc = "em++" if lang == "c++" else "emcc"
    r = subprocess.run([cc] + flags + ["-O2", "-E", str(src)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        return name, r.stderr, True
    preprocessed = eeconst.transform(r.stdout) if ee else r.stdout
    s = stamp(u, preprocessed, compiler_identity(cc))
    if raw.exists() and st.exists() and st.read_text() == s:
        return name, None, False
    ir = ["-Xclang", "-disable-llvm-passes", "-S", "-emit-llvm", "-O2", "-g0"]
    i = OBJ / f"{name}.i"
    i.write_text(preprocessed)
    language = "c++-cpp-output" if lang == "c++" else "cpp-output"
    r = subprocess.run([cc] + strip_includes(flags) + ir + ["-x", language, str(i), "-o", str(raw)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        return name, r.stderr, True
    st.write_text(s)
    return name, None, True


def to_obj(args):
    name, fl, changed = args
    ll, o = OBJ / f"{name}.ll", OBJ / f"{name}.o"
    if not changed and o.exists():
        return name, None
    r = subprocess.run([sys.executable, str(WEB / "irweb.py"), "fix", str(OBJ / "sigs.json"), str(OBJ / f"{name}.raw.ll"), str(ll)]
                       + ([] if fl else ["--no-float"]), capture_output=True, text=True)
    if r.returncode:
        return name, r.stderr
    r = subprocess.run(["emcc", "-O2", "-c", str(ll), "-o", str(o)], cwd=ROOT, capture_output=True, text=True)
    return name, (r.stderr if r.returncode else None)


def shaders():
    """port/build/gen/gs/shaders.h: the GLSL sources for the GL back end (the SPIR-V arrays are not needed)."""
    gen = B / "gen/gs"
    gen.mkdir(parents=True, exist_ok=True)
    arrays = []
    for src in sorted((ROOT / "port/src/gs/shaders").glob("*")):
        if src.suffix not in (".vert", ".frag"):
            continue
        base = "k" + src.stem.capitalize() + src.suffix[1:].capitalize()
        arrays.append(f"static const unsigned char {base}Spv[] = {{0}};\n")
        data = src.read_bytes() + b"\0"
        arrays.append(f"static const unsigned char {base}Glsl[] = {{" + ",".join(str(b) for b in data) + "};\n")
    text = "/* generated by port/web/build.py */\n" + "".join(arrays)
    p = gen / "shaders.h"
    if not p.exists() or p.read_text() != text:
        p.write_text(text)


def main():
    if "--clean" in sys.argv:
        shutil.rmtree(OBJ, ignore_errors=True)
    OBJ.mkdir(parents=True, exist_ok=True)
    shaders()
    us = units()
    with concurrent.futures.ThreadPoolExecutor(JOBS) as ex:
        res = list(ex.map(to_ir, us))
    bad = [(n, e) for n, e, _ in res if e]
    for n, e in bad:
        print("FAILED", n, "\n   ", "\n    ".join([l for l in e.splitlines() if "error" in l][:4]) or e.strip()[:400])
    if bad:
        print(f"{len(bad)} of {len(us)} files failed")
        return 1
    changed = {n: c for n, _, c in res}
    if any(changed.values()) or not (OBJ / "sigs.json").exists():
        r = subprocess.run([sys.executable, str(WEB / "irweb.py"), "sigs", str(OBJ / "sigs.json")] + [str(OBJ / f"{u[0]}.raw.ll") for u in us],
                           capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr)
        if r.returncode:
            return r.returncode
        changed = {n: True for n in changed}  # a signature anywhere can change any caller
    with concurrent.futures.ThreadPoolExecutor(JOBS) as ex:
        res = list(ex.map(to_obj, [(u[0], u[4], changed[u[0]]) for u in us]))
    bad = [(n, e) for n, e in res if e]
    for n, e in bad:
        print("FAILED (IR)", n, e.strip()[:600])
    if bad:
        return 1
    print(f"{len(us)} objects")
    (OBJ / "objects.txt").write_text("\n".join(str(OBJ / f"{u[0]}.o") for u in us) + "\n")
    # The linker needs this manifest on a clean checkout. It used to be a
    # separate, undocumented manual step.
    r = subprocess.run([sys.executable, str(WEB / "gen_data_web.py")], cwd=ROOT)
    if r.returncode:
        return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
