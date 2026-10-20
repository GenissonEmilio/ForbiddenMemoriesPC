#!/usr/bin/env python3
"""The game's data tables for the browser build: what port/tools/gen_data.py makes for x86, as WebAssembly assembly.

Same inputs (the files splat generates from the user's own SLUS_216.78 and DBZP.BIN, the INCLUDE_RODATA tables and
the VU1 microprograms) and the same layout rules (each chunk 16-byte aligned plus its PS2 address modulo 16). In a
wasm object every data symbol needs a size, and a pointer to a function in data is an index into the function
table, which the assembler only makes for a symbol declared with its signature: so the chunk is laid out here byte
by byte, sizes are computed, and functions (known from the definitions' signatures, port/build/obj_web/sigs.json)
get a .functype.

Usage: port/web/gen_data_web.py      -> port/build/gen/data_web/*.s, port/build/obj_web/data_*.o
Generated from the game: never commit or publish the output."""
import collections, json, pathlib, re, struct, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ASM = ROOT / "asm"
DST = ROOT / "port/build/gen/data_web"
OBJ = ROOT / "port/build/obj_web"
KINDS = ("data", "sdata", "rodata", "lit4", "lit8", "bss", "sbss")
WASM = {"i1": "i32", "i8": "i32", "i16": "i32", "i32": "i32", "ptr": "i32", "i64": "i64", "float": "f32", "double": "f64"}


def chunks(yaml, base=0x100000):
    out = []
    for l in yaml.read_text().splitlines():
        m = re.match(r"\s+- \[0x([0-9A-Fa-f]+), (\w+), \"?([\w/]+)\"?\]", l)
        if m and m.group(2) in KINDS:
            out.append((m.group(2), m.group(3), int(m.group(1), 16) + base))
        m = re.match(r"\s+- \{ type: (\w+), vram: 0x([0-9A-Fa-f]+), name: ([\w/]+) \}", l)
        if m and m.group(1) in KINDS:
            out.append((m.group(1), m.group(3), int(m.group(2), 16)))
    return out


def symbols():
    out = {}
    for p in (ROOT / "config/symbols").glob("*.txt"):
        if not p.name.startswith("menu"):
            for l in p.read_text().splitlines():
                m = re.match(r"(\w+)\s*=\s*0x([0-9A-Fa-f]+)", l)
                if m:
                    out[m.group(1)] = int(m.group(2), 16)
    return out


def parse_int(s):
    s = s.strip()
    neg = s.startswith("-")
    s = s.lstrip("-")
    v = int(s, 16) if s.lower().startswith("0x") else int(s, 8) if len(s) > 1 and s.startswith("0") else int(s)
    return -v if neg else v


def parse_string(s):
    """A GNU as string literal (with the quotes) -> bytes."""
    assert s[0] == '"' and s[-1] == '"', s
    s = s[1:-1]
    out, i = bytearray(), 0
    simple = {"n": 10, "t": 9, "r": 13, "b": 8, "f": 12, "a": 7, "v": 11, "\\": 92, '"': 34, "'": 39}
    while i < len(s):
        c = s[i]
        if c != "\\":
            out += c.encode("latin-1")
            i += 1
            continue
        n = s[i + 1]
        if n in simple:
            out.append(simple[n])
            i += 2
        elif n in "xX":
            j = i + 2
            while j < len(s) and s[j] in "0123456789abcdefABCDEF":
                j += 1
            out.append(int(s[i + 2:j], 16) & 0xFF)
            i = j
        elif n in "01234567":
            j = i + 1
            while j < len(s) and j < i + 4 and s[j] in "01234567":
                j += 1
            out.append(int(s[i + 1:j], 8) & 0xFF)
            i = j
        else:
            out += n.encode("latin-1")
            i += 2
    return bytes(out)


def split_args(s):
    out, cur, q = [], [], False
    for ch in s:
        if ch == '"':
            q = not q
        if ch == "," and not q:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


class Chunk:
    """A chunk laid out: a list of (offset, item) with items bytes / ('ref', symbol, addend) / ('label', name)."""

    def __init__(self, start_pad):
        self.pos = start_pad
        self.items = []
        self.labels = []  # (name, offset)
        if start_pad:
            self.items.append(bytes(start_pad))

    def raw(self, b):
        self.items.append(bytes(b))
        self.pos += len(b)

    def ref(self, sym, add):
        self.items.append(("ref", sym, add))
        self.pos += 4

    def align(self, n):
        pad = (-self.pos) % n
        if pad:
            self.raw(bytes(pad))

    def label(self, name):
        self.labels.append((name, self.pos))
        self.items.append(("label", name))


def lay_out(text, addr):
    c = Chunk(addr & 15)
    for l in text.splitlines():
        l = re.sub(r"/\*.*?\*/", "", l).rstrip()
        s = l.strip()
        if not s or s.startswith((".include", ".section", "nonmatching", "enddlabel", "endlabel")):
            continue
        m = re.match(r"(?:dlabel|glabel) (\S+)", s)
        if m:
            c.label(m.group(1))
            continue
        d, _, rest = s.partition(" ")
        args = split_args(rest)
        if d == ".word":
            for a in args:
                if a.startswith(".L"):
                    c.raw(b"\0\0\0\0")  # a label inside an assembly function (jump tables of code the port compiles from C)
                elif re.match(r"-?(0x[0-9A-Fa-f]+|\d+)$", a):
                    c.raw(struct.pack("<I", parse_int(a) & 0xFFFFFFFF))
                else:
                    m = re.match(r"([A-Za-z_.$][\w.$]*)\s*(?:([+-])\s*(0x[0-9A-Fa-f]+|\d+))?$", a)
                    if not m:
                        raise SystemExit(f"unhandled .word operand: {a}")
                    add = parse_int(m.group(3)) * (-1 if m.group(2) == "-" else 1) if m.group(3) else 0
                    c.ref(m.group(1), add)
        elif d == ".short":
            for a in args:
                c.raw(struct.pack("<H", parse_int(a) & 0xFFFF))
        elif d == ".byte":
            for a in args:
                c.raw(bytes([parse_int(a) & 0xFF]))
        elif d == ".float":
            for a in args:
                c.raw(struct.pack("<f", float(a)))
        elif d == ".double":
            for a in args:
                c.raw(struct.pack("<d", float(a)))
        elif d in (".asciz", ".ascii"):
            for a in args:
                c.raw(parse_string(a) + (b"\0" if d == ".asciz" else b""))
        elif d == ".space":
            n = parse_int(args[0])
            fill = parse_int(args[1]) & 0xFF if len(args) > 1 else 0
            c.raw(bytes([fill]) * n)
        elif d == ".align":
            c.align(1 << parse_int(args[0]))
        elif d == ".incbin":
            path = parse_string(args[0]).decode()
            data = pathlib.Path(path).read_bytes()
            off = parse_int(args[1]) if len(args) > 1 else 0
            n = parse_int(args[2]) if len(args) > 2 else len(data) - off
            c.raw(data[off:off + n])
        else:
            raise SystemExit(f"unhandled line: {s}")
    return c


def esc(b):
    return '"' + "".join(chr(x) if 32 <= x < 127 and x not in (34, 92) else f"\\{x:03o}" for x in b) + '"'


TEXT = (0x100000, 0x2BF6B0)  # the main program's code: a symbol there is a function
ABSOLUTE = {"D_3BE71C": 0x3BE71C}  # as in irweb.py: data at a fixed PS2 address, referenced by its value


def emit(c, section, sigs, functypes):
    """WebAssembly assembly of a laid-out chunk."""
    zero = all(isinstance(it, bytes) and not any(it) or (isinstance(it, tuple) and it[0] == "label") for it in c.items)
    sec = ".bss" if zero and section == "bss" else ".data"
    out = [f"\t.section\t{sec}.{c.name},\"\",@", "\t.p2align\t4"]
    ends = [o for _, o in c.labels[1:]] + [c.pos]
    sizes = {n: e - o for (n, o), e in zip(c.labels, ends)}
    for it in c.items:
        if isinstance(it, bytes):
            if sec == ".bss":
                out.append(f"\t.skip\t{len(it)}")
            else:
                for i in range(0, len(it), 64):
                    out.append(f"\t.ascii\t{esc(it[i:i + 64])}")
        elif it[0] == "label":
            n = it[1]
            out += [f"\t.globl\t{n}", f"\t.type\t{n},@object", f"\t.size\t{n}, {sizes[n]}", f"{n}:"]
        else:
            _, sym, add = it
            if sym in ABSOLUTE:
                out.append(f"\t.int32\t{(ABSOLUTE[sym] + add) & 0xFFFFFFFF:#x}")
                continue
            a = ADDR.get(sym)
            if sym not in sigs and (re.match(r"func_[0-9A-F]{8}$", sym) or (a is not None and TEXT[0] <= a < TEXT[1])):
                sigs[sym] = {"ret": "void", "params": [], "var": False}  # a library function the port stubs (link.py)
            if sym in sigs:
                functypes.add(sym)
                if add:
                    raise SystemExit(f"function reference with an offset: {sym}+{add}")
                out.append(f"\t.int32\t{sym}")
            else:
                out.append(f"\t.int32\t{sym}{add:+d}" if add else f"\t.int32\t{sym}")
    return out


def functype(name, sig):
    params = [WASM.get(t, "i32") for t in sig["params"]] + (["i32"] if sig["var"] else [])
    res = [] if sig["ret"] == "void" else [WASM.get(sig["ret"], "i32")]
    return f"\t.functype\t{name} ({', '.join(params)}) -> ({', '.join(res)})"


def all_addresses():
    """symbols() plus splat's own list (config/symbol_addrs.txt: the libraries' functions), for telling code from data."""
    out = dict(symbols())
    for p in (ROOT / "config/symbol_addrs.txt",):
        for l in p.read_text().splitlines():
            m = re.match(r"(\w+)\s*=\s*0x([0-9A-Fa-f]+)", l)
            if m:
                out.setdefault(m.group(1), int(m.group(2), 16))
    return out


ADDR = all_addresses()


def main():
    sigs = json.load(open(OBJ / "sigs.json"))
    DST.mkdir(parents=True, exist_ok=True)
    for old in DST.glob("*.s"):
        old.unlink()
    todo = []  # (file name, chunk, section kind)
    for kind, name, addr in chunks(ROOT / "config/SLUS_216.78.yaml"):
        src = ASM / "data" / f"{name}.{kind}.s"
        todo.append((f"{name.replace('/', '_')}.{kind}", lay_out(src.read_text(), addr), kind))
    for kind, name, addr in chunks(ROOT / "config/DBZP.yaml", 0x334C00):
        src = ASM / "dbzp/data" / f"{name}.{kind}.s"
        todo.append((f"dbzp_{name.replace('/', '_')}.{kind}", lay_out(src.read_text(), addr), kind))
    addr_of = symbols()
    for f in [ROOT / "src/main.c"] + sorted((ROOT / "src/sys").glob("*.c")) + sorted((ROOT / "src/battle").glob("*.c")):
        for folder, name in re.findall(r'^INCLUDE_RODATA\("([^"]+)", (\w+)\);', f.read_text(), re.M):
            if name.startswith("jtbl_"):
                continue
            src = ROOT / folder / f"{name}.s"
            text = src.read_text()
            a = addr_of.get(name, 0)
            if not a:
                m = re.search(r"dlabel D_([0-9A-F]{8})", text)
                a = int(m.group(1), 16) if m else 0
            todo.append((f"inc_{name}.rodata", lay_out(text, a), "rodata"))
    # the VU1 microprograms: one block with entry labels inside it
    for f in sorted((ROOT / "src").rglob("*.c")) + sorted((ROOT / "include").rglob("*.h")):
        for h in re.findall(r"\bD_([0-9A-F]{8})\b", f.read_text()):
            addr_of.setdefault("D_" + h, int(h, 16))
    blob = (ROOT / "assets/cod/1BF6B0.textbin.bin").read_bytes()
    start = 0x2BF6B0
    cuts = sorted({v for v in addr_of.values() if start <= v < start + len(blob)} | {start})
    names = collections.defaultdict(list)
    for k, v in addr_of.items():
        names[v].append(k)
    c = Chunk(start & 15)
    for i, cut in enumerate(cuts):
        for k in sorted(names[cut]) or [f"D_{cut:08X}"]:
            c.label(k)
        end = cuts[i + 1] if i + 1 < len(cuts) else start + len(blob)
        c.raw(blob[cut - start:end - start])
    todo.append(("vu1_micro.data", c, "data"))

    defined = set()
    for fname, ch, kind in todo:
        ch.name = re.sub(r"\W", "_", fname)
        for n, _ in ch.labels:
            if n in defined:
                raise SystemExit(f"{n} defined twice")
            defined.add(n)
    objs = []
    for fname, ch, kind in todo:
        ft = set()
        body = emit(ch, "bss" if kind in ("bss", "sbss") else "data", sigs, ft)
        s = DST / f"{fname}.s"
        s.write_text("\n".join([functype(n, sigs[n]) for n in sorted(ft)] + body) + "\n")
        o = OBJ / f"data_{fname.replace('.', '_')}.o"
        r = subprocess.run(["emcc", "-c", str(s), "-o", str(o)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"{s.name}: {r.stderr[:600]}")
        objs.append(str(o))
    (OBJ / "data_objects.txt").write_text("\n".join(objs) + "\n")
    print(f"{len(todo)} data chunks, {len(defined)} symbols -> {len(objs)} objects")


if __name__ == "__main__":
    main()
