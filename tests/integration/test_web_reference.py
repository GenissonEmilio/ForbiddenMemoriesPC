"""Regression tests for the separately attributed BT3 web reference. No retail data."""
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "reference/tenkaichi3"
sys.path.insert(0, str(REFERENCE / "port/tools"))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


build = module("bt3_web_build", REFERENCE / "port/web/build.py")
link = module("bt3_web_link", REFERENCE / "port/web/link.py")


class WebTests(unittest.TestCase):
    def test_cache_tracks_headers_options_compiler_and_transform(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            header = root / "nested.h"; source = root / "fixture.c"
            header.write_text("#define VALUE 1\n")
            source.write_text('#include "nested.h"\nint value(void) { return VALUE; }\n')
            unit = ("pc_fixture", source, ["-I" + str(root)], False, True, "c")
            def key(compiler="compiler 1", selected=unit):
                text = subprocess.check_output(["gcc", "-E", str(source)], text=True)
                return build.stamp(selected, text, compiler)
            first = key()
            self.assertEqual(first, key())
            header.write_text("#define VALUE 2\n")
            self.assertNotEqual(first, key())
            self.assertNotEqual(key(), key("compiler 2"))
            other = (*unit[:2], ["-DOPTION=1"], *unit[3:])
            self.assertNotEqual(key(), key(selected=other))
            real = Path.read_bytes
            def changed(path):
                return real(path) + (b"\n# new pass" if path.name == "irweb.py" else b"")
            before = key()
            with patch.object(Path, "read_bytes", changed):
                self.assertNotEqual(before, key())

    def test_missing_manifest_and_bad_target_have_actionable_errors(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(link, "OBJ", Path(folder)):
            for target, message in (("web", "build.py first"), ("wrong", "Unknown target")):
                error = io.StringIO()
                with patch.object(sys, "argv", ["link.py", target]), contextlib.redirect_stderr(error):
                    self.assertEqual(link.main(), 2)
                self.assertIn(message, error.getvalue())

    def test_clean_build_generates_data_and_propagates_failure(self):
        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 7 if command[-1].endswith("gen_data_web.py") else 0,
                                               stdout="", stderr="")
        with tempfile.TemporaryDirectory() as folder, patch.object(build, "OBJ", Path(folder)), \
             patch.object(build, "shaders"), patch.object(build, "units", return_value=[]), \
             patch.object(build.subprocess, "run", side_effect=run), \
             patch.object(sys, "argv", ["build.py"]):
            self.assertEqual(build.main(), 7)
            self.assertTrue((Path(folder) / "objects.txt").is_file())

    def test_cloudflare_packaging_on_linux(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cloud = root / "cloudflare"; cloud.mkdir()
            shutil.copy2(REFERENCE / "cloudflare/build.sh", cloud / "build.sh")
            web = root / "port/build/web"; web.mkdir(parents=True)
            names = "index.html net.js net.css bt3-jspi.js bt3-jspi.wasm bt3-async.js bt3-async.wasm icon-180.png icon-192.png icon-512.png manifest.webmanifest".split()
            for name in names:
                (web / name).write_bytes(b"synthetic asset")
            disc = root / "disc"; disc.mkdir()
            payload = bytes(range(256)) * 8192 + b"last sector"
            (disc / "bt3-usa.iso").write_bytes(payload)
            for _ in range(2):
                subprocess.run(["bash", str(cloud / "build.sh")], check=True, capture_output=True, text=True)
                pieces = sorted((cloud / "public/disc").glob("*.bin"))
                self.assertEqual(b"".join(p.read_bytes() for p in pieces), payload)
                self.assertEqual(len(pieces), 3)
                self.assertFalse(list((cloud / "public").rglob("*.iso")))

    @unittest.skipUnless(shutil.which("emcc") and shutil.which("node"), "Emscripten and Node required")
    def test_real_wasm_ir_and_incremental_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); obj = root / "obj"; obj.mkdir()
            header = root / "value.h"; header.write_text("#define VALUE 2\n")
            source = root / "fixture.c"
            source.write_text('#include "value.h"\nvolatile float a=1.0f;\n'
                              'int main(void) { float b=a+(float)VALUE; return b==(float)(VALUE+1) ? 0:1; }\n')
            unit = ("pc_fixture", source, ["-std=gnu99"], False, True, "c")
            with patch.object(build, "OBJ", obj):
                self.assertEqual(build.to_ir(unit), ("pc_fixture", None, True))
                self.assertEqual(build.to_ir(unit), ("pc_fixture", None, False))
                header.write_text("#define VALUE 4\n")
                self.assertEqual(build.to_ir(unit), ("pc_fixture", None, True))
                subprocess.run([sys.executable, str(build.WEB / "irweb.py"), "sigs", str(obj / "sigs.json"),
                                str(obj / "pc_fixture.raw.ll")], check=True)
                self.assertEqual(build.to_obj(("pc_fixture", True, True)), ("pc_fixture", None))
            output = root / "fixture.js"
            subprocess.run(["emcc", "-O2", str(obj / "pc_fixture.o"), str(build.WEB / "src/web_float.c"),
                            str(REFERENCE / "port/src/softfloat_ps2.c"), str(REFERENCE / "src/port/vu0_a.c"),
                            "-DREF_VU0_EXTERN_ARITH", "-I" + str(REFERENCE / "include"),
                            "-I" + str(REFERENCE / "port/src"), "-sENVIRONMENT=node", "-o", str(output)], check=True)
            subprocess.run(["node", str(output)], check=True)


if __name__ == "__main__":
    unittest.main()
