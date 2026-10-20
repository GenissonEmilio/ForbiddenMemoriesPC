#!/usr/bin/env python3
"""LLVM IR rewriter of the browser build: what -msoft-float and the x86 calling convention gave the 32-bit build.

1. PS2 float model. WebAssembly has no soft-float mode (emcc ignores -msoft-float), so every single-precision
   operation of the game is turned into a call to the port's PS2 arithmetic (port/src/softfloat_ps2.c, through
   the float-typed wrappers of port/web/src/web_float.c): fadd / fsub / fmul / fdiv / frem, fcmp, and the
   conversions between float and integers. fneg stays (a sign flip, as __negsf2). Doubles stay native: on the PS2
   they are libgcc's IEEE software doubles, which give the same results.

2. Signatures. On x86 a call whose declared type differs from the definition (a `void` in one file, `int` in the
   other; an argument too many) still works; wasm-ld turns such a call into a trap. Every call to a function of
   the program whose type differs from its definition is rewritten to the definition's type, converting the
   arguments and the result, and the module's declaration is made to match.

Usage: irweb.py sigs OUT.json A.raw.ll ...      collect the definitions' signatures
       irweb.py fix SIGS.json IN.raw.ll OUT.ll [--no-float]
"""
import json, re, sys

FLOAT_OPS = {"fadd": "__web_fadd", "fsub": "__web_fsub", "fmul": "__web_fmul", "fdiv": "__web_fdiv", "frem": "__web_frem"}
CMP = {  # predicate -> (icmp on the result of __web_fcmp (-1 / 0 / 1), or a constant)
    "oeq": "eq", "ueq": "eq", "one": "ne", "une": "ne", "olt": "slt", "ult": "slt", "ole": "sle", "ule": "sle",
    "ogt": "sgt", "ugt": "sgt", "oge": "sge", "uge": "sge", "ord": True, "uno": False, "true": True, "false": False}
DECLS = {
    "__web_fadd": "float (float, float)", "__web_fsub": "float (float, float)", "__web_fmul": "float (float, float)",
    "__web_fdiv": "float (float, float)", "__web_frem": "float (float, float)", "__web_fcmp": "i32 (float, float)",
    "__web_f2i": "i32 (float)", "__web_f2u": "i32 (float)", "__web_f2l": "i64 (float)", "__web_f2ul": "i64 (float)",
    "__web_i2f": "float (i32)", "__web_u2f": "float (i32)", "__web_l2f": "float (i64)", "__web_ul2f": "float (i64)"}

# Data the game finds at a fixed PS2 address (the 32-bit build defines them with --defsym): the address itself.
ABSOLUTE = {"D_3BE71C": 0x3BE71C}  # end of the menu overlay; the game heap starts after it (src/sys/heap.c)

VAL = r"(%[-\w.$]+)"
RE_BIN = re.compile(r"^(\s+)" + VAL + r" = (fadd|fsub|fmul|fdiv|frem)((?: [a-z]+)*) float (\S+), (\S+?)(, !.*)?$")
RE_CMP = re.compile(r"^(\s+)" + VAL + r" = fcmp((?: [a-z]+)*?) (\w+) float (\S+), (\S+?)(, !.*)?$")
RE_F2I = re.compile(r"^(\s+)" + VAL + r" = (fptosi|fptoui) float (\S+) to (i\d+)(, !.*)?$")
RE_I2F = re.compile(r"^(\s+)" + VAL + r" = (sitofp|uitofp)((?: [a-z]+)*) (i\d+) (\S+) to float(, !.*)?$")
RE_DEFINE = re.compile(r"^define ([^@]*?)@\"?([-\w.$]+)\"?\((.*)\)[^)]*\{\s*$")
RE_DECLARE = re.compile(r"^declare ([^@]*?)@\"?([-\w.$]+)\"?\((.*)\)([^)]*)$")
RET_ATTRS = {"noundef", "signext", "zeroext", "nonnull", "noalias", "inreg", "dso_local", "hidden", "protected",
             "default", "external", "extern_weak", "weak", "linkonce_odr", "weak_odr", "linkonce", "common",
             "available_externally", "dso_preemptable", "local_unnamed_addr", "unnamed_addr", "fastcc", "ccc"}
LINKAGE_LOCAL = {"internal", "private"}
FP = {"float", "double"}


def split_top(s):
    """Splits a comma-separated list at depth 0 of (), [], {}, <>."""
    out, depth, cur, q = [], 0, [], False
    for ch in s:
        if ch == '"':
            q = not q
        elif not q and ch in "([{<":
            depth += 1
        elif not q and ch in ")]}>":
            depth -= 1
        if ch == "," and depth == 0 and not q:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def first_type(s):
    """The type at the start of a parameter or argument ('ptr noundef %0' -> 'ptr'); struct types whole."""
    s = s.strip()
    if s.startswith("{") or s.startswith("<") or s.startswith("["):
        close = {"{": "}", "<": ">", "[": "]"}[s[0]]
        depth = 0
        for i, ch in enumerate(s):
            depth += ch == s[0]
            depth -= ch == close
            if depth == 0:
                return s[:i + 1]
    return s.split()[0]


def ret_type(prefix):
    """Return type from the text between `define`/`declare`/`call` and the function name."""
    words = [w for w in re.split(r"\s+", prefix.strip()) if w and w not in RET_ATTRS and not w.startswith("#")
             and not re.match(r"(align|dereferenceable|range|nofpclass)\b", w) and not w.startswith("(")]
    return words[-1] if words else "void"


def sig_of(params):
    items = split_top(params)
    var = bool(items) and items[-1] == "..."
    types = [first_type(p) for p in items if p != "..."]
    return types, var


def collect(paths):
    sigs = {}
    for p in paths:
        for line in open(p, encoding="latin-1"):
            if not line.startswith("define "):
                continue
            m = RE_DEFINE.match(line)
            if not m:
                continue
            pre, name, params = m.groups()
            if set(pre.split()) & LINKAGE_LOCAL:
                continue
            types, var = sig_of(params)
            sigs.setdefault(name, {"ret": ret_type(pre), "params": types, "var": var, "file": str(p)})
    return sigs


def int_bits(t):
    m = re.fullmatch(r"i(\d+)", t)
    return int(m.group(1)) if m else None


def zero(t):
    if t == "ptr":
        return "null"
    if t in FP:
        return "0.000000e+00"
    if int_bits(t):
        return "0"
    return "zeroinitializer"


class Fixer:
    def __init__(self, sigs, do_float):
        self.sigs, self.do_float = sigs, do_float
        self.n = 0
        self.used = set()
        self.calls_fixed = 0
        self.float_ops = 0

    def tmp(self):
        self.n += 1
        return f"%sf.{self.n}"

    def convert(self, ind, val, src, dst, signed, out):
        """Emits instructions converting `val` of type src to dst; returns the new value."""
        if src == dst:
            return val
        bs, bd = int_bits(src), int_bits(dst)
        t = self.tmp()
        if bs and bd:
            op = "trunc" if bs > bd else ("sext" if signed else "zext")
            out.append(f"{ind}{t} = {op} {src} {val} to {dst}")
        elif src == "ptr" and bd:
            if bd == 32:
                out.append(f"{ind}{t} = ptrtoint ptr {val} to i32")
            else:
                out.append(f"{ind}{t}.p = ptrtoint ptr {val} to i32")
                return self.convert(ind, f"{t}.p", "i32", dst, False, out)
        elif bs and dst == "ptr":
            if bs != 32:
                val = self.convert(ind, val, src, "i32", signed, out)
            out.append(f"{ind}{t} = inttoptr i32 {val} to ptr")
        elif (src, dst) in (("float", "i32"), ("i32", "float"), ("double", "i64"), ("i64", "double")):
            out.append(f"{ind}{t} = bitcast {src} {val} to {dst}")
        elif (src, dst) == ("float", "double"):
            out.append(f"{ind}{t} = fpext float {val} to double")
        elif (src, dst) == ("double", "float"):
            out.append(f"{ind}{t} = fptrunc double {val} to float")
        elif src in FP or dst in FP:  # float <-> other integer widths, via the bits
            mid = "i32" if src == "float" or dst == "float" else "i64"
            v = self.convert(ind, val, src, mid, signed, out) if src not in FP else self.convert(ind, val, src, mid, signed, out)
            return self.convert(ind, v, mid, dst, signed, out)
        else:
            return zero(dst)  # aggregates: nothing sensible to pass
        return t

    def materialize(self, ind, name, t, out):
        """Defines `name` of type t with a zero value (the result of a call to a function that returns nothing)."""
        if int_bits(t):
            out.append(f"{ind}{name} = add {t} 0, 0")
        elif t == "ptr":
            out.append(f"{ind}{name} = inttoptr i32 0 to ptr")
        elif t == "float":
            out.append(f"{ind}{name} = bitcast i32 0 to float")
        elif t == "double":
            out.append(f"{ind}{name} = bitcast i64 0 to double")
        else:
            out.append(f"{ind}{name} = freeze {t} zeroinitializer")

    def fix_call(self, line, out):
        m = re.match(r"^(\s+)(?:" + VAL + r" = )?((?:tail |musttail |notail )?call )(.*?)@\"?([-\w.$]+)\"?\(", line)
        if not m:
            return False
        ind, res, kw, mid, name = m.groups()
        sig = self.sigs.get(name)
        if sig is None or sig["var"]:
            return False
        start = m.end()
        depth, i = 1, start
        while i < len(line) and depth:
            depth += line[i] in "([{<"
            depth -= line[i] in ")]}>"
            i += 1
        args, tail = line[start:i - 1], line[i:]
        fnty = None
        mm = re.match(r"^(.*?)\s*(\S+)\s*\((.*)\)\s*$", mid)
        if mm and mm.group(2) and not mm.group(2).startswith("("):
            fnty = mm.group(3)
            rty = mm.group(2)
        else:
            rty = ret_type(mid)
        arglist = split_top(args)
        atypes = [first_type(a) for a in arglist]
        if rty == sig["ret"] and atypes == sig["params"] and not (fnty is not None and "..." in fnty):
            return False
        if any(a.startswith("metadata") or "bundle" in a for a in arglist):
            return False
        new = []
        for k, pt in enumerate(sig["params"]):
            if k < len(arglist):
                a = arglist[k]
                at = atypes[k]
                aval = a.split()[-1]
                signed = " signext " in f" {a} "
                v = self.convert(ind, aval, at, pt, signed, out)
                new.append(f"{pt} {v}")
            else:
                new.append(f"{pt} {zero(pt)}")
        call = f"{kw.replace('musttail ', '').replace('tail ', '')}{sig['ret']} @{name}({', '.join(new)}){tail}"
        cr = sig["ret"]
        if res is None:
            out.append(f"{ind}{call}" if cr == "void" else f"{ind}{self.tmp()} = {call}")
        elif cr == "void":
            out.append(f"{ind}{call}")
            self.materialize(ind, res, rty, out)
        elif cr == rty:
            out.append(f"{ind}{res} = {call}")
        else:
            t = self.tmp()
            out.append(f"{ind}{t} = {call}")
            v = self.convert(ind, t, cr, rty, False, out)
            if v == zero(rty) or v == t:
                self.materialize(ind, res, rty, out)
            else:
                # rename the last converted value to the call's result name
                last = out.pop()
                out.append(last.replace(f"{v} = ", f"{res} = ", 1))
        self.calls_fixed += 1
        return True

    def fix_float(self, line, out):
        m = RE_BIN.match(line)
        if m:
            ind, res, op, _, a, b, md = m.groups()
            out.append(f"{ind}{res} = call float @{FLOAT_OPS[op]}(float {a}, float {b})")
            self.used.add(FLOAT_OPS[op])
            return True
        m = RE_CMP.match(line)
        if m:
            ind, res, _, pred, a, b, md = m.groups()
            how = CMP[pred]
            if how is True or how is False:
                out.append(f"{ind}{res} = icmp eq i32 {0 if how else 1}, 0")
            else:
                t = self.tmp()
                out.append(f"{ind}{t} = call i32 @__web_fcmp(float {a}, float {b})")
                out.append(f"{ind}{res} = icmp {how} i32 {t}, 0")
                self.used.add("__web_fcmp")
            return True
        m = RE_F2I.match(line)
        if m:
            ind, res, op, a, it, md = m.groups()
            bits = int_bits(it)
            fn = ("__web_f2i" if op == "fptosi" else "__web_f2u") if bits <= 32 else ("__web_f2l" if op == "fptosi" else "__web_f2ul")
            wide = "i32" if bits <= 32 else "i64"
            self.used.add(fn)
            if it == wide:
                out.append(f"{ind}{res} = call {wide} @{fn}(float {a})")
            else:
                t = self.tmp()
                out.append(f"{ind}{t} = call {wide} @{fn}(float {a})")
                out.append(f"{ind}{res} = trunc {wide} {t} to {it}")
            return True
        m = RE_I2F.match(line)
        if m:
            ind, res, op, _, it, a, md = m.groups()
            bits = int_bits(it)
            if bits <= 32:
                fn = "__web_i2f" if op == "sitofp" else "__web_u2f"
                wide = "i32"
            else:
                fn = "__web_l2f" if op == "sitofp" else "__web_ul2f"
                wide = "i64"
            self.used.add(fn)
            if it != wide:
                t = self.tmp()
                out.append(f"{ind}{t} = {'sext' if op == 'sitofp' else 'zext'} {it} {a} to {wide}")
                a = t
            out.append(f"{ind}{res} = call float @{fn}({wide} {a})")
            return True
        return False

    def run(self, text):
        out = []
        declared = {}
        for line in text.split("\n"):
            if "@D_" in line:
                skip = False
                for sym, addr in ABSOLUTE.items():
                    if line.startswith(f"@{sym} = external"):
                        skip = True
                    line = re.sub(rf"@{sym}\b", f"inttoptr (i32 {addr} to ptr)", line)
                if skip:
                    continue
            if line.startswith("declare "):
                m = RE_DECLARE.match(line)
                if m and m.group(2) in self.sigs and not self.sigs[m.group(2)]["var"]:
                    s = self.sigs[m.group(2)]
                    out.append(f"declare {s['ret']} @{m.group(2)}({', '.join(s['params'])})")
                    declared[m.group(2)] = True
                    continue
                if m:
                    declared[m.group(2)] = True
                out.append(line)
                continue
            if line.startswith("  ") and " call " in line or line.lstrip().startswith(("call ", "tail call ")):
                if self.fix_call(line, out):
                    continue
            if self.do_float and line.startswith("  ") and ("float" in line):
                if self.fix_float(line, out):
                    self.float_ops += 1
                    continue
            out.append(line)
        for fn in sorted(self.used):
            if fn not in declared:
                r, p = DECLS[fn].split(" ", 1)
                out.append(f"declare {r} @{fn}{p}")
        return "\n".join(out)


def main():
    if sys.argv[1] == "sigs":
        sigs = collect(sys.argv[3:])
        json.dump(sigs, open(sys.argv[2], "w"))
        print(f"{len(sigs)} functions")
    elif sys.argv[1] == "fix":
        sigs = json.load(open(sys.argv[2]))
        f = Fixer(sigs, "--no-float" not in sys.argv)
        text = open(sys.argv[3], encoding="latin-1").read()
        open(sys.argv[4], "w", encoding="latin-1").write(f.run(text))
        print(f"{sys.argv[3]}: {f.float_ops} float ops, {f.calls_fixed} calls fixed")


if __name__ == "__main__":
    main()
