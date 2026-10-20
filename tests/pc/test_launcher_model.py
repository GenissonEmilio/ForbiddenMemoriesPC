"""Launcher persistence, literal process arguments and desktop integration without a ROM."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "tools/launcher"))
import model


class LauncherTests(unittest.TestCase):
    def test_successful_selection_is_remembered_without_modifying_raw_disc(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); disc=root / "Yu Gi Oh ; $(touch bad).img"
            disc.write_bytes(b"synthetic fixture")
            library=model.Library(root / "data",root)
            with patch.object(model,"inspect_disc",return_value={"serial":"SLUS-01411"}):
                self.assertEqual(library.prepare(disc),disc)
                self.assertEqual(model.Library(root / "data",root).disc,disc)
                self.assertEqual(library.verify(),disc)
            self.assertEqual(disc.read_bytes(),b"synthetic fixture")
            self.assertEqual(library.state["name"],disc.name)
            self.assertFalse((root / "bad").exists())

    def test_bad_selection_keeps_previous_disc_and_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); disc=root / "disc.bin"; disc.write_bytes(b"fixture")
            library=model.Library(root / "data",root)
            with patch.object(model,"inspect_disc",return_value={"serial":"SLUS-01411"}): library.prepare(disc)
            original=library.config.read_bytes()
            with patch.object(model,"inspect_disc",side_effect=ValueError("unsupported")):
                with self.assertRaises(ValueError): library.prepare(disc)
            self.assertEqual(library.config.read_bytes(),original)
            self.assertEqual(library.disc,disc)

    def test_archives_get_a_managed_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root / "game.rar"; source.write_bytes(b"fixture")
            library=model.Library(root / "data",root)
            def extract(path,destination):
                destination.mkdir(parents=True); target=destination / "rpg-yfm.bin"
                target.write_bytes(b"raw"); return target
            with patch.object(model,"import_disc",side_effect=extract) as importer, \
                 patch.object(model,"inspect_disc",return_value={"serial":"SLUS-01411"}):
                first=library.prepare(source); second=library.prepare(source)
            self.assertEqual(first,second)
            self.assertEqual(importer.call_count,1)
            self.assertTrue(first.is_relative_to(library.directory))

    def test_game_uses_packaged_loader_and_isolated_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root / "game").mkdir(); (root / "runtime").mkdir()
            (root / "game/memories-pc").touch(); (root / "runtime/ld-linux.so.2").touch()
            library=model.Library(root / "data",root)
            self.assertEqual(library.game_command(),[str(root / "runtime/ld-linux.so.2"),"--library-path",
                                                    str(root / "runtime/lib"),str(root / "game/memories-pc")])
            with patch.dict(os.environ,{"LD_LIBRARY_PATH":"/wrong/64bit","GI_TYPELIB_PATH":"/wrong/gtk",
                                       "MEMORIES_DISC":"wrong","MEMORIES_INPUT":"unwanted"}):
                environment=library.game_environment()
            self.assertNotIn("LD_LIBRARY_PATH",environment)
            self.assertNotIn("GI_TYPELIB_PATH",environment)
            self.assertNotIn("MEMORIES_INPUT",environment)
            self.assertEqual(environment["MEMORIES_USER_DIR"],str(root / "data/player"))
            self.assertEqual(environment["MEMORIES_PROGRAM_DIR"],str(root / "game"))
            self.assertEqual(environment["MEMORIES_LINUX_LOADER"],str(root / "runtime/ld-linux.so.2"))

    def test_broken_or_missing_state_does_not_claim_a_ready_game(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root / "launcher.json").write_text("{broken")
            library=model.Library(root,root)
            self.assertIsNone(library.disc)
            with self.assertRaises(ValueError): library.verify()
            with self.assertRaises(ValueError): library.game_command()

    def test_desktop_entry_is_graphical_and_literal(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); library=model.Library(root,root)
            with patch.object(sys,"frozen",True,create=True), patch.object(sys,"executable",str(root / 'a % b $c "d"')):
                entry=library.install_desktop_entry(root / "applications")
            text=entry.read_text()
            self.assertIn("Terminal=false",text)
            self.assertIn('%%',text)
            self.assertIn('\\$',text)
            self.assertIn('\\"d\\"',text)
            self.assertTrue(entry.stat().st_mode & 0o100)


if __name__=="__main__": unittest.main()
