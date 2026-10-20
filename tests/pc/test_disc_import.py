"""ROM-free tests for the archive importer; all disc contents are synthetic."""
import io
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/pc"))
import import_disc as importer


class ImportTests(unittest.TestCase):
    def test_unsafe_paths(self):
        for name in ("../disc.bin", "/disc.bin", "C:\\disc.bin", "a/../../disc.bin", "a\\..\\disc.bin", "."):
            with self.subTest(name=name), self.assertRaises(importer.ImportError_):
                importer.safe_name(name)

    def test_nested_archives_and_img(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w") as archive:
                archive.writestr("YUGIOH.img", b"synthetic image")
                archive.writestr("instructions.txt", "Do not execute this document.")
            outer = root / "outer.zip"
            with zipfile.ZipFile(outer, "w") as archive:
                archive.writestr("folder/inner.zip", inner.getvalue())
            work = root / "work"; work.mkdir()
            images = list(importer.candidates(outer, work, importer.Budget()))
            self.assertEqual([p.name for p in images], ["YUGIOH.img"])
            self.assertEqual(images[0].read_bytes(), b"synthetic image")

    def test_links_duplicates_and_budget_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for case in ("link", "duplicate", "budget", "escape"):
                with self.subTest(case=case):
                    source = root / (case + ".zip")
                    with zipfile.ZipFile(source, "w") as archive:
                        if case == "link":
                            entry = zipfile.ZipInfo("link.bin")
                            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                            archive.writestr(entry, "elsewhere")
                        elif case == "duplicate":
                            archive.writestr("Disc.bin", "a"); archive.writestr("disc.bin", "b")
                        elif case == "escape":
                            archive.writestr("../escape.bin", "bad")
                        else:
                            archive.writestr("disc.bin", "too large")
                    destination = root / case; destination.mkdir()
                    with self.assertRaises(importer.ImportError_):
                        importer.extract_zip(source, destination, importer.Budget(4))
            self.assertFalse((root / "escape.bin").exists())

    def test_publish_is_idempotent_and_does_not_overwrite_other_disc(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); image = root / "source.img"; image.write_bytes(b"validated fixture")
            destination = root / "game"
            with patch.object(importer, "inspect_disc", return_value={"serial": "fixture"}):
                target = importer.import_disc(image, destination)
                self.assertEqual(target.read_bytes(), image.read_bytes())
                self.assertEqual(importer.import_disc(image, destination), target)
                image.write_bytes(b"other fixture")
                with self.assertRaises(importer.ImportError_):
                    importer.import_disc(image, destination)
            self.assertEqual(target.read_bytes(), b"validated fixture")
            self.assertFalse(list(destination.glob(".import-*")))

    def test_invalid_disc_rejected_before_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); image = root / "wrong.img"; image.write_bytes(b"not a disc")
            with self.assertRaises(importer.ImportError_):
                importer.import_disc(image, root / "game")
            self.assertFalse((root / "game/rpg-yfm.bin").exists())


if __name__ == "__main__":
    unittest.main()
