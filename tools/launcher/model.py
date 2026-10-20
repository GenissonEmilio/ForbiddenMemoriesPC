"""Persistent launcher state and native-game process boundary; no GUI dependencies."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE_ROOT / "tools/pc"))
from import_disc import import_disc, inspect_disc

VERSION = "0.1.0"
APPLICATION_ID = "io.github.GenissonEmilio.ForbiddenMemoriesPC"


def data_directory():
    override = os.environ.get("YFM_LAUNCHER_DATA")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))).expanduser()
    if not base.is_absolute():
        base = Path.home() / ".local/share"
    return base / "ForbiddenMemoriesPC"


def program_directory():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_ROOT


def assets_directory():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".launcher-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Library:
    def __init__(self, directory=None, program=None):
        self.directory = Path(directory or data_directory())
        self.program = Path(program or program_directory())
        self.config = self.directory / "launcher.json"
        self.state = {}
        try:
            value = json.loads(self.config.read_text())
            if isinstance(value, dict):
                self.state = value
        except (OSError, ValueError):
            pass

    @property
    def disc(self):
        path = self.state.get("disc")
        return Path(path) if isinstance(path, str) and Path(path).is_file() else None

    def prepare(self, source, progress=lambda text: None):
        source = Path(source).expanduser().resolve()
        if not source.is_file():
            raise ValueError("O arquivo escolhido não está mais disponível. Escolha sua ROM novamente.")
        progress("Conferindo o seu disco…")
        if source.suffix.lower() in (".bin", ".img"):
            disc = source
            metadata = inspect_disc(disc)
        elif source.suffix.lower() in (".rar", ".zip"):
            progress("Preparando a ROM. Isso pode levar alguns instantes…")
            stamp = f"{source}\0{source.stat().st_size}\0{source.stat().st_mtime_ns}"
            identifier = hashlib.sha256(stamp.encode()).hexdigest()[:20]
            destination = self.directory / "discs" / identifier
            disc = destination / "rpg-yfm.bin"
            if not disc.is_file():
                disc = import_disc(source, destination)
            progress("Validando a edição do jogo…")
            metadata = inspect_disc(disc)
        else:
            raise ValueError("Escolha um arquivo BIN, IMG, RAR ou ZIP da edição americana SLUS-01411.")
        state = {"disc": str(disc), "name": source.name, "serial": metadata["serial"],
                 "size": disc.stat().st_size, "mtime_ns": disc.stat().st_mtime_ns}
        atomic_json(self.config, state)
        self.state = state
        return disc

    def verify(self):
        disc = self.disc
        if not disc:
            raise ValueError("Não encontramos a ROM. Escolha seu arquivo para continuar.")
        inspect_disc(disc)
        return disc

    @property
    def player_directory(self):
        return self.directory / "player"

    def game_command(self):
        packaged = self.program / "game/memories-pc"
        binary = packaged if packaged.is_file() else self.program / "tmp/pc/game32/memories-pc"
        if not binary.is_file():
            raise ValueError("O executável do jogo não foi encontrado. Extraia o pacote completo do release.")
        loader = self.program / "runtime/ld-linux.so.2"
        if loader.is_file():
            return [str(loader), "--library-path", str(self.program / "runtime/lib"), str(binary)]
        return [str(binary)]

    def game_environment(self, test=False):
        # A frozen GTK launcher has 64-bit library/typelib overrides. Never
        # pass those to the independent 32-bit game or the host GPU driver.
        environment = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
        original_ld = environment.get("LD_LIBRARY_PATH_ORIG")
        for name in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "GI_TYPELIB_PATH", "GTK_DATA_PREFIX",
                     "GTK_EXE_PREFIX", "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR", "GIO_EXTRA_MODULES"):
            environment.pop(name, None)
        if original_ld:
            environment["LD_LIBRARY_PATH"] = original_ld
        environment.update(MEMORIES_DISC=str(self.disc), MEMORIES_USER_DIR=str(self.player_directory),
                           MEMORIES_NO_UPDATE_CHECK="1")
        if (self.program / "runtime/ld-linux.so.2").is_file():
            # /proc/self/exe points at the explicitly invoked loader. Name the
            # game's resources and preserve this loader when the game restarts.
            environment.update(MEMORIES_PROGRAM_DIR=str(self.program / "game"),
                               MEMORIES_LINUX_LOADER=str(self.program / "runtime/ld-linux.so.2"),
                               MEMORIES_LINUX_LIBRARY_PATH=str(self.program / "runtime/lib"))
        dri = self.program / "runtime/lib/dri"
        if dri.is_dir():
            # Retain the distro's GPU drivers where available; provide Mesa's
            # software rasterizer as a fallback for hosts without 32-bit DRI.
            host = ["/usr/lib/i386-linux-gnu/dri", "/usr/lib/dri", "/usr/lib32/dri"]
            environment["LIBGL_DRIVERS_PATH"] = ":".join([*host, str(dri)])
        if test:
            self.directory.mkdir(parents=True, exist_ok=True)
            environment.update(MEMORIES_HEADLESS="1", MEMORIES_NO_AUDIO="1", MEMORIES_NO_GAMEPAD="1",
                               MEMORIES_DUMP_FRAME="1200", MEMORIES_SPEED="-1",
                               MEMORIES_DUMP_PATH=str(self.directory / "game-test.ppm"))
        return environment

    def launch(self, test=False):
        self.verify()
        self.directory.mkdir(parents=True, exist_ok=True)
        command, environment = self.game_command(), self.game_environment(test)
        log = self.directory / "last-game.log"
        with log.open("w") as output:
            return subprocess.Popen(command, cwd=self.program, env=environment,
                                    stdout=output, stderr=subprocess.STDOUT, start_new_session=True)

    def install_desktop_entry(self, applications=None):
        destination = Path(applications) if applications else Path(
            os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "applications"
        destination.mkdir(parents=True, exist_ok=True)
        if getattr(sys, "frozen", False):
            command = [str(Path(sys.executable).resolve())]
        else:
            command = [sys.executable, str(SOURCE_ROOT / "tools/launcher/main.py")]
        # Desktop Entry strings use their own escaping, not shell escaping.
        def quote(value):
            value = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
            return '"' + value + '"'
        text = ("[Desktop Entry]\nType=Application\nName=Forbidden Memories PC\n"
                "Comment=Seu próximo duelo começa aqui\nTerminal=false\nCategories=Game;CardGame;\n"
                f"Exec={' '.join(quote(value) for value in command)}\n"
                f"Icon={assets_directory() / 'icon.png'}\nStartupWMClass=forbidden-memories-pc\n")
        target = destination / "io.github.GenissonEmilio.ForbiddenMemoriesPC.desktop"
        target.write_text(text)
        target.chmod(0o755)
        return target
