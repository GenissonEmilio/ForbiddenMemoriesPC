#!/usr/bin/env python3
"""Import an owned USA disc from BIN/IMG or nested RAR/ZIP, without executing archive contents."""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import sys
import zipfile

from fm_editor.disc import DiscImage, GameFilesError

ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE_SHA256 = "84a54ed74f3d0edd6d81380839f7e4ef5bfb21ecea18be9a062bd6bfa5a45c88"
MAX_BYTES = 2 * 1024**3
MAX_ENTRIES = 4096
MAX_DEPTH = 3


class ImportError_(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_name(name: str) -> Path:
    path = PurePosixPath(name.replace("\\", "/"))
    if not name or path.is_absolute() or ".." in path.parts or any(":" in p for p in path.parts):
        raise ImportError_(f"Archive entry outside its folder: {name!r}")
    if not path.parts or "\x00" in name:
        raise ImportError_(f"Invalid archive entry: {name!r}")
    return Path(*path.parts)


class Budget:
    def __init__(self, maximum=MAX_BYTES):
        self.remaining = maximum
        self.entries = MAX_ENTRIES

    def entry(self, size):
        self.entries -= 1
        if size < 0 or size > self.remaining or self.entries < 0:
            raise ImportError_("Archive exceeds the import size or entry limit")

    def consume(self, size):
        self.remaining -= size
        if self.remaining < 0:
            raise ImportError_("Archive exceeds the import size limit")


def extract_zip(source, destination, budget):
    seen = set()
    with zipfile.ZipFile(source) as archive:
        for entry in archive.infolist():
            relative = safe_name(entry.filename)
            key = relative.as_posix().casefold()
            if key in seen:
                raise ImportError_(f"Duplicate archive path: {relative}")
            seen.add(key)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ImportError_(f"Archive links are not accepted: {relative}")
            budget.entry(entry.file_size)
            target = destination / relative
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as stream, target.open("xb") as out:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    budget.consume(len(block))
                    out.write(block)


def libarchive():
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "libarchive.so.13"
    name = str(bundled) if getattr(sys, "frozen", False) and bundled.is_file() else ctypes.util.find_library("archive")
    if not name:
        raise ImportError_("RAR import needs libarchive (Linux: libarchive; Ubuntu: libarchive13). "
                           "Alternatively unpack the RAR yourself and import its IMG/BIN file.")
    lib = ctypes.CDLL(name)
    declarations = {
        "archive_read_new": (ctypes.c_void_p, []),
        "archive_read_support_filter_all": (ctypes.c_int, [ctypes.c_void_p]),
        "archive_read_support_format_all": (ctypes.c_int, [ctypes.c_void_p]),
        "archive_read_open_filename": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]),
        "archive_read_next_header": (ctypes.c_int, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]),
        "archive_entry_pathname": (ctypes.c_char_p, [ctypes.c_void_p]),
        "archive_entry_size": (ctypes.c_longlong, [ctypes.c_void_p]),
        "archive_entry_filetype": (ctypes.c_uint, [ctypes.c_void_p]),
        "archive_entry_hardlink": (ctypes.c_char_p, [ctypes.c_void_p]),
        "archive_read_data": (ctypes.c_ssize_t, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]),
        "archive_error_string": (ctypes.c_char_p, [ctypes.c_void_p]),
        "archive_read_free": (ctypes.c_int, [ctypes.c_void_p]),
    }
    for name, (result, arguments) in declarations.items():
        function = getattr(lib, name)
        function.restype, function.argtypes = result, arguments
    return lib


def extract_rar(source, destination, budget):
    lib = libarchive()
    archive = lib.archive_read_new()
    if not archive:
        raise ImportError_("Cannot allocate archive reader")
    def fail():
        message = lib.archive_error_string(archive)
        raise ImportError_(message.decode("utf-8", "replace") if message else "Cannot read RAR")
    try:
        lib.archive_read_support_filter_all(archive)
        lib.archive_read_support_format_all(archive)
        if lib.archive_read_open_filename(archive, os.fsencode(source), 65536) != 0:
            fail()
        entry = ctypes.c_void_p()
        buffer = ctypes.create_string_buffer(1024 * 1024)
        seen = set()
        while True:
            code = lib.archive_read_next_header(archive, ctypes.byref(entry))
            if code == 1:  # ARCHIVE_EOF
                break
            if code != 0:
                fail()
            name = lib.archive_entry_pathname(entry)
            if not name:
                raise ImportError_("Archive entry has no name")
            relative = safe_name(os.fsdecode(name))
            key = relative.as_posix().casefold()
            if key in seen:
                raise ImportError_(f"Duplicate archive path: {relative}")
            seen.add(key)
            kind = lib.archive_entry_filetype(entry)
            if kind not in (stat.S_IFREG, stat.S_IFDIR) or lib.archive_entry_hardlink(entry):
                raise ImportError_(f"Archive links or special files are not accepted: {relative}")
            budget.entry(lib.archive_entry_size(entry))
            target = destination / relative
            if kind == stat.S_IFDIR:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as out:
                while True:
                    count = lib.archive_read_data(archive, buffer, len(buffer))
                    if count == 0:
                        break
                    if count < 0:
                        fail()
                    budget.consume(count)
                    out.write(buffer.raw[:count])
    finally:
        lib.archive_read_free(archive)


def candidates(source, work, budget, depth=0):
    suffix = source.suffix.lower()
    if suffix in (".bin", ".img"):
        yield source
    elif suffix in (".zip", ".rar"):
        if depth >= MAX_DEPTH:
            raise ImportError_("Too many nested archives")
        stage = Path(tempfile.mkdtemp(prefix="archive-", dir=work))
        print(f"Reading archive: {source.name}", flush=True)
        (extract_zip if suffix == ".zip" else extract_rar)(source, stage, budget)
        for path in sorted(stage.rglob("*")):
            if path.is_file() and path.suffix.lower() in (".rar", ".zip", ".bin", ".img"):
                yield from candidates(path, work, budget, depth + 1)
    else:
        raise ImportError_("Choose a raw BIN/IMG disc or a RAR/ZIP containing one")


def inspect_disc(source):
    with DiscImage(source) as disc:
        if (disc.sector, disc.skip) != (2352, 24):
            raise ImportError_("The native runtime needs a raw Mode 2 disc (2352-byte sectors)")
        executable = disc.find("SLUS_014.11")
        data = disc.find("DATA/WA_MRG.MRG")
        if not executable or not data or executable[1] != 0x1D0800 or data[1] != 0x2400000:
            raise ImportError_("This is not the supported USA SLUS-01411 disc")
        payload = disc.read(*executable)
        digest = hashlib.sha256(payload).hexdigest()
        if not payload.startswith(b"PS-X EXE") or digest != EXECUTABLE_SHA256:
            raise ImportError_(f"SLUS_014.11 is modified or unsupported (SHA-256 {digest})")
        # Check all files the native runtime needs, including each file's last sector.
        for name in ("DATA/WA_MRG.MRG", "DATA/MODEL.MRG", "DATA/MASTER.XA", "DATA/MOVIE.STR",
                     "DATA/SD_BGM.DAT", "DATA/SD_SE.DAT", "DATA/SU.MRG"):
            location = disc.find(name)
            if not location or not location[1]:
                raise ImportError_(f"Disc is missing {name}")
            disc.read_sector(location[0] + (location[1] - 1) // 2048)
        return {"serial": "SLUS-01411", "executable_sha256": digest, "sector_size": disc.sector}


def import_disc(source, destination=ROOT / "game"):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ImportError_(f"File does not exist: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=destination) as temporary:
        work = Path(temporary)
        valid, errors = [], []
        for image in candidates(source, work, Budget()):
            try:
                metadata = inspect_disc(image)
                valid.append((image, metadata))
            except (GameFilesError, ImportError_, OSError, ValueError) as error:
                errors.append(f"{image.name}: {error}")
        if len(valid) != 1:
            raise ImportError_("Expected exactly one supported USA disc; found " + str(len(valid)) +
                               ("\n" + "\n".join(errors) if errors else ""))
        image, metadata = valid[0]
        target = destination / "rpg-yfm.bin"
        metadata.update(disc_sha256=sha256(image), disc_size=image.stat().st_size)
        if target.exists() and sha256(target) != metadata["disc_sha256"]:
            raise ImportError_(f"A different disc already exists at {target}; it was not overwritten")
        if not target.exists():
            staged = work / "validated-disc.bin"
            shutil.copyfile(image, staged)
            os.replace(staged, target)
        cue = destination / "rpg-yfm.cue"
        if not cue.exists():
            cue.write_text('FILE "rpg-yfm.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
        (destination / "import.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"Validated {metadata['serial']}: {target}\nSHA-256: {metadata['disc_sha256']}", flush=True)
        return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--destination", type=Path, default=ROOT / "game")
    args = parser.parse_args()
    try:
        import_disc(args.source, args.destination)
    except (ImportError_, GameFilesError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Import failed: {error}\n")


if __name__ == "__main__":
    main()
