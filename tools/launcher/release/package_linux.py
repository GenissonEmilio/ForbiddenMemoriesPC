#!/usr/bin/env python3
"""Package the frozen x86-64 GUI and isolated i386 game runtime, without any disc data."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/launcher"))
from model import VERSION


def package(version=VERSION, stage=None):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?",version):
        raise ValueError("Version must be a semantic version, such as 0.1.0")
    stage=Path(stage or ROOT / "dist/ForbiddenMemoriesPC")
    binary=ROOT / "tmp/pc/game32/memories-pc"
    if not (stage / "ForbiddenMemoriesPC").is_file() or not binary.is_file():
        raise SystemExit("Build the native game and frozen launcher before packaging")
    game=stage / "game"; game.mkdir(exist_ok=True)
    shutil.copy2(binary,game / "memories-pc")
    shutil.copy2(binary.parent / "buildid",game / "buildid")
    for name in ("mods","languages","symbols"):
        destination=game / name
        if destination.exists(): shutil.rmtree(destination)
        shutil.copytree(binary.parent / name,destination)
    runtime=stage / "runtime"; lib=runtime / "lib"; lib.mkdir(parents=True,exist_ok=True)
    sysroot=ROOT / "tmp/pc/linux-sysroot"
    loader=(sysroot / "lib/ld-linux.so.2").resolve()
    shutil.copy2(loader,runtime / "ld-linux.so.2")
    # Keep each ELF DSO once, with SONAME/version aliases beside it. Include
    # dlopen backends (audio, X11/Wayland) and Mesa's software fallback, so no
    # 32-bit packages or host compiler are needed on a clean x86-64 desktop.
    sources={}
    for base in (sysroot / "lib/i386-linux-gnu",sysroot / "usr/lib/i386-linux-gnu"):
        for source in sorted(base.rglob("*.so*")):
            if "dri" in source.parts and source.name != "swrast_dri.so": continue
            if not source.is_file(): continue
            try:
                with source.open("rb") as stream:
                    if stream.read(4)!=b"\x7fELF": continue
            except OSError: continue
            sources[source.name]=source
    for name,source in sources.items():
        actual=source.resolve()
        destination=lib / ("dri" if name=="swrast_dri.so" else "")
        destination.mkdir(exist_ok=True)
        target=destination / actual.name
        if not target.exists(): shutil.copy2(actual,target)
        alias=destination / name
        if alias!=target and not alias.exists(): alias.symlink_to(actual.name)
    shutil.copy2(ROOT / "tools/launcher/assets/icon.svg",stage / "icon.svg")
    shutil.copy2(ROOT / "LICENSE",stage / "LICENSE.txt")
    shutil.copy2(ROOT / "tools/launcher/LICENSE",stage / "LICENSE-launcher.txt")
    licenses=stage / "licenses"; licenses.mkdir(exist_ok=True)
    for path in (sysroot / "usr/share/doc").glob("*/copyright"):
        shutil.copy2(path,licenses / (path.parent.name+".txt"))
    for path in Path("/usr/share/doc").glob("*/copyright"):
        shutil.copy2(path,licenses / ("x86_64-"+path.parent.name+".txt"))
    if Path("/opt/libarchive/COPYING").is_file():
        shutil.copy2("/opt/libarchive/COPYING",licenses / "libarchive-3.8.10.txt")
    # Source/build files make the included LGPL components replaceable and
    # identify the exact distribution packages the runtime came from.
    shutil.copy2(sysroot / ".complete",licenses / "runtime-packages.txt")
    (stage / "LEIA-ME.txt").write_text(f"""FORBIDDEN MEMORIES PC {version} — Linux x86-64

1. Extraia esta pasta inteira para um local permanente.
2. Abra o executável ForbiddenMemoriesPC com dois cliques.
3. Clique em Escolher arquivo e selecione sua ROM americana SLUS-01411.
4. Clique em Iniciar jogo. Nas próximas vezes, a ROM já estará lembrada.

Para abrir pelo menu do Linux: Sobre o port > Adicionar ao menu de aplicativos.
Se o gerenciador perguntar, permita a execução do arquivo ForbiddenMemoriesPC.

Não é necessário instalar Python, GCC ou bibliotecas de 32 bits. Este pacote
inclui a interface e o jogo já compilados. Requer Linux x86-64 com glibc 2.35+
(Ubuntu 22.04+, Debian 12+, Fedora atual), uma sessão gráfica e OpenGL.
O driver gráfico do sistema é usado quando disponível; há fallback Mesa.

BIN/IMG são lidos no próprio local. RAR/ZIP, inclusive aninhados, são preparados
em ~/.local/share/ForbiddenMemoriesPC/discs. A ROM original não é alterada.
Saves e configurações ficam em ~/.local/share/ForbiddenMemoriesPC/player.
O pacote não contém ROM ou arquivos de disco. O jogo funciona offline.

Teclado: setas, X confirmar, S voltar, Enter Start. F10 abre as configurações.
Mouse: arraste uma carta para uma das cinco zonas destacadas. Escolha a face
e clique na estrela guardiã. Soltar fora das zonas cancela o arraste.
No campo, clique em Sua carta e depois no Alvo para atacar. A barra inferior
oferece confirmar, voltar, direções, marcar fusão e terminar o turno.
Os menus iniciais, escolhas de diálogo e slots de saves/decks aceitam cliques.
Algumas telas originais usam as direções e OK da barra ou o teclado/controle.
O launcher permanece aberto e volta ao estado pronto quando o jogo termina.

Código e receitas de compilação:
https://github.com/GenissonEmilio/ForbiddenMemoriesPC
Port nativo baseado em Unchiga e colaboradores; autoria e licenças preservadas.
""",encoding="utf-8")
    for path in stage.rglob("*"):
        if path.is_file() and path.suffix.lower() in (".bin",".img",".rar",".iso",".ccd",".sub",".cue"):
            raise SystemExit(f"Refusing disc data in release: {path}")
    archive=ROOT / "dist" / f"ForbiddenMemoriesPC-{version}-linux-x86_64.tar.gz"
    with tarfile.open(archive,"w:gz",compresslevel=6) as output:
        output.add(stage,arcname="ForbiddenMemoriesPC")
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent / (archive.name+".sha256")).write_text(digest+"  "+archive.name+"\n")
    print(archive)
    return archive


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version",default=VERSION)
    parser.add_argument("--stage",type=Path)
    args=parser.parse_args(); package(args.version,args.stage)
