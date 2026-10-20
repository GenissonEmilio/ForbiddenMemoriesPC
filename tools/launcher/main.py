#!/usr/bin/env python3
"""Forbidden Memories PC — standalone, offline GTK desktop launcher."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import Library, VERSION, assets_directory, program_directory

if getattr(sys,"frozen",False):
    os.environ.pop("GTK_MODULES",None)
    os.environ["FONTCONFIG_FILE"]=str(assets_directory() / "fonts.conf")

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_foreign("cairo")
from gi.repository import Gdk, GLib, Gtk, Pango
import cairo


def style(widget, *names):
    for name in names:
        widget.get_style_context().add_class(name)
    return widget


def label(text, *names, wrap=False):
    widget = style(Gtk.Label(label=text), *names)
    widget.set_xalign(0)
    widget.set_line_wrap(wrap)
    return widget


def box(orientation=Gtk.Orientation.VERTICAL, spacing=0, margin=0, classes=()):
    widget = style(Gtk.Box(orientation=orientation, spacing=spacing), *classes)
    for name in ("top", "bottom", "start", "end"):
        getattr(widget, "set_margin_" + name)(margin)
    return widget


def eye(cr, x, y, scale, alpha=1):
    cr.save(); cr.translate(x, y); cr.scale(scale, scale)
    gold = cairo.LinearGradient(-80, -70, 80, 90)
    gold.add_color_stop_rgba(0, 1, .9, .63, alpha)
    gold.add_color_stop_rgba(.6, .82, .62, .29, alpha)
    gold.add_color_stop_rgba(1, .48, .29, .13, alpha)
    cr.set_source(gold); cr.set_line_width(3)
    cr.move_to(-80, -62); cr.line_to(80, -62); cr.line_to(0, 92); cr.close_path()
    cr.set_source_rgba(.18, .12, .1, alpha); cr.fill_preserve(); cr.set_source(gold); cr.stroke()
    for a, b, c, d in [(-60,-25,60,-25),(-44,10,44,10),(-25,48,25,48),(0,-62,-40,15),(0,-62,40,15)]:
        cr.set_source_rgba(.7,.49,.23,alpha*.3); cr.set_line_width(1)
        cr.move_to(a,b); cr.line_to(c,d); cr.stroke()
    cr.set_source(gold); cr.set_line_width(3)
    cr.move_to(-52,-13); cr.curve_to(-15,-57,21,-57,52,-13)
    cr.curve_to(17,21,-19,21,-52,-13); cr.stroke()
    cr.arc(0,-14,18,0,math.tau); cr.fill()
    cr.set_source_rgba(.08,.07,.1,alpha); cr.arc(0,-14,8,0,math.tau); cr.fill()
    cr.set_source(gold); cr.set_line_width(3)
    cr.move_to(0,6); cr.line_to(0,47); cr.move_to(0,24); cr.line_to(-17,40)
    cr.move_to(0,24); cr.line_to(17,40); cr.stroke(); cr.restore()


class Artwork(Gtk.DrawingArea):
    def __init__(self, small=False):
        super().__init__(); self.small = small
        self.set_size_request(54 if small else 270, 60 if small else 230)
        self.connect("draw", self.draw)
        self.get_accessible().set_name("Olho e Enigma do Milênio, ilustração decorativa")

    def draw(self, widget, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        if self.small:
            eye(cr, w/2, h/2-4, .29)
            return False
        glow = cairo.RadialGradient(w*.52,h*.45,10,w*.52,h*.45,160)
        glow.add_color_stop_rgba(0,.68,.4,.13,.19); glow.add_color_stop_rgba(1,.1,.1,.15,0)
        cr.set_source(glow); cr.paint()
        for cx, cy, angle in [(w*.26,h*.48,-.23),(w*.75,h*.43,.18)]:
            cr.save(); cr.translate(cx,cy); cr.rotate(angle)
            cr.rectangle(-47,-75,94,150); cr.set_source_rgba(.12,.11,.16,.9); cr.fill_preserve()
            cr.set_source_rgba(.67,.43,.24,.4); cr.set_line_width(1); cr.stroke()
            for i in range(7):
                cr.save(); cr.scale(.58,1)
                cr.arc(0,0,10+i*8,0,math.tau); cr.set_source_rgba(.6,.3,.18,.12+i*.015)
                cr.set_line_width(1.7); cr.stroke(); cr.restore()
            cr.restore()
        eye(cr,w*.51,h*.44,.92)
        return False


class Launcher:
    def __init__(self, args):
        self.args = args
        self.library = Library(args.data_dir)
        self.busy = False; self.process = None; self.closing = False; self.failed = False
        provider = Gtk.CssProvider(); provider.load_from_path(str(assets_directory() / "style.css"))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", True)
        self.window = Gtk.Window(title="Forbidden Memories PC")
        self.window.set_wmclass("forbidden-memories-pc", "ForbiddenMemoriesPC")
        self.window.set_default_size(1120, 720); self.window.set_size_request(900, 620)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_icon_from_file(str(assets_directory() / "icon.png"))
        self.window.connect("delete-event", self.close)
        header = Gtk.HeaderBar(); header.set_show_close_button(True)
        header.set_title("FORBIDDEN MEMORIES  /  PC EDITION"); self.window.set_titlebar(header)
        root = box(Gtk.Orientation.HORIZONTAL); self.window.add(root)
        sidebar_frame = style(Gtk.Box(),"sidebar")
        sidebar = box(spacing=24, margin=22); sidebar.set_size_request(205,-1)
        sidebar_frame.add(sidebar); root.pack_start(sidebar_frame, False, False, 0)
        brand = box(Gtk.Orientation.HORIZONTAL, 9)
        brand.pack_start(Artwork(True), False, False, 0)
        brand_text = box(spacing=3)
        brand_text.pack_start(label("FORBIDDEN\nMEMORIES", "brand"), False,False,0)
        brand_text.pack_start(label("P C   E D I T I O N", "small"),False,False,0)
        brand.pack_start(brand_text,False,False,0); sidebar.pack_start(brand,False,False,0)
        sidebar.pack_start(label("SUA BIBLIOTECA", "eyebrow"),False,False,8)
        self.nav = {}
        self.stack = Gtk.Stack(); self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hhomogeneous(False); self.stack.set_vhomogeneous(False)
        for key, title in [("home","◈   Início"),("controls","⌘   Controles"),("about","◇   Sobre o port")]:
            button = style(Gtk.Button(label=title),"nav")
            button.get_child().set_xalign(0)
            button.connect("clicked", lambda _, name=key: self.navigate(name))
            sidebar.pack_start(button,False,False,0); self.nav[key] = button
        sidebar.pack_start(Gtk.Box(),True,True,0)
        sidebar.pack_start(label("●  Tudo no seu computador", "small"),False,False,0)
        sidebar.pack_start(label(f"v{VERSION}   •   Linux", "small"),False,False,0)
        body = box(spacing=20,margin=30,classes=("main-content",))
        scroller = Gtk.ScrolledWindow(); scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroller.add(body); root.pack_start(scroller,True,True,0)
        body.pack_start(label("BIBLIOTECA    /    FORBIDDEN MEMORIES", "breadcrumb"),False,False,0)
        body.pack_start(self.stack,True,True,0)
        self.stack.add_named(self.home(),"home")
        self.stack.add_named(self.controls(),"controls")
        self.stack.add_named(self.about(),"about")
        footer = box(Gtk.Orientation.HORIZONTAL,spacing=15,classes=("footer",)); footer.set_margin_top(2)
        text = label("Feito para quem acredita no coração das cartas.","small")
        footer.pack_start(text,True,True,0)
        saves = style(Gtk.Button(label="Meus saves ↗"),"link"); saves.connect("clicked",self.open_saves)
        footer.pack_end(saves,False,False,0); body.pack_end(footer,False,False,0)
        self.navigate("home"); self.window.show_all()
        self.progress.hide()
        if self.library.disc:
            self.set_ready()
        else:
            self.play_button.set_sensitive(False)
            self.status.set_text("Escolha sua ROM para começar.")
        target = Gtk.TargetEntry.new("text/uri-list",0,0)
        self.drop.drag_dest_set(Gtk.DestDefaults.ALL,[target],Gdk.DragAction.COPY)
        self.drop.connect("drag-data-received", self.dropped)
        if args.rom:
            GLib.timeout_add(300,lambda: self.prepare(args.rom) or False)
        if args.screenshot and not args.rom:
            GLib.timeout_add(700,self.capture_and_exit)

    def home(self):
        page = box(spacing=22)
        hero_outer = style(Gtk.Box(),"hero")
        hero = box(Gtk.Orientation.HORIZONTAL, margin=24)
        hero_outer.add(hero)
        copy = box(spacing=12)
        copy.pack_start(label("O CORAÇÃO DAS CARTAS, NO SEU PC", "eyebrow"),False,False,0)
        copy.pack_start(label("Yu-Gi-Oh!\nForbidden Memories", "hero-title",wrap=True),False,False,0)
        copy.pack_start(label("Reviva os duelos do Egito Antigo.\nSeu próximo duelo começa aqui.","hero-subtitle"),False,False,0)
        pills = box(Gtk.Orientation.HORIZONTAL,8)
        for text in ("PORT NATIVO","722 CARTAS","OFFLINE"):
            pills.pack_start(label(text,"pill"),False,False,0)
        copy.pack_start(pills,False,False,4)
        hero.pack_start(copy,True,True,0); hero.pack_end(Artwork(),False,False,0)
        page.pack_start(hero_outer,False,False,0)
        panel_outer = style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL),"panel")
        panel = box(spacing=17,margin=22); panel_outer.pack_start(panel,True,True,0)
        heading = box(Gtk.Orientation.HORIZONTAL,12)
        heading.pack_start(label("Seu jogo", "panel-title"),True,True,0)
        heading.pack_end(label("01  /  ESCOLHA · PREPARE · JOGUE", "eyebrow"),False,False,0)
        panel.pack_start(heading,False,False,0)
        self.drop = style(Gtk.EventBox(),"drop-zone")
        inner = box(Gtk.Orientation.HORIZONTAL,16,18)
        icon = label("▣","section-title"); inner.pack_start(icon,False,False,5)
        info = box(spacing=6)
        self.file_title = label("Selecione sua ROM", "file-title")
        self.file_title.set_ellipsize(Pango.EllipsizeMode.MIDDLE); self.file_title.set_max_width_chars(38)
        info.pack_start(self.file_title,False,False,0)
        self.file_subtitle = label("BIN, IMG, RAR ou ZIP · edição americana", "muted")
        info.pack_start(self.file_subtitle,False,False,0)
        inner.pack_start(info,True,True,0)
        self.choose_button = style(Gtk.Button(label="Escolher arquivo…"),"secondary")
        self.choose_button.connect("clicked",self.choose)
        inner.pack_end(self.choose_button,False,False,0); self.drop.add(inner)
        panel.pack_start(self.drop,False,False,0)
        self.progress = Gtk.ProgressBar(); panel.pack_start(self.progress,False,False,0)
        actions = box(Gtk.Orientation.HORIZONTAL,20)
        state = box(spacing=5)
        self.status = label("Escolha sua ROM para começar.","status"); self.status.set_line_wrap(True)
        state.pack_start(self.status,False,False,0)
        state.pack_start(label("Seu arquivo fica apenas neste computador.","muted"),False,False,0)
        actions.pack_start(state,True,True,0)
        self.play_button = style(Gtk.Button(label="▶   Iniciar jogo"),"play")
        self.play_button.set_tooltip_text("Abrir Forbidden Memories nativamente no PC")
        self.play_button.connect("clicked",self.play)
        actions.pack_end(self.play_button,False,False,0); panel.pack_start(actions,False,False,0)
        page.pack_start(panel_outer,False,False,0)
        note = label("Dica: você também pode arrastar o arquivo para a área acima.","muted")
        page.pack_start(note,False,False,0)
        page.pack_start(Gtk.Box(),True,True,0)
        return page

    def controls(self):
        page=box(spacing=24)
        page.pack_start(label("Pronto para duelar?", "section-title"),False,False,0)
        page.pack_start(label("Jogue no teclado ou conecte seu controle USB/Bluetooth.\nNo jogo, F10 abre as configurações e permite trocar os botões.","muted",wrap=True),False,False,0)
        grid=Gtk.Grid(column_spacing=28,row_spacing=15); style(grid,"panel")
        rows=[("↑ ↓ ← →","Mover / escolher"),("X","Confirmar · botão ✕"),("S","Voltar · botão ○"),
              ("Z / A","Botões □ / △"),("Enter","Start"),("Q / W","L1 / R1"),("E / R","L2 / R2"),
              ("F5 / F7","Salvar / carregar estado"),("F10","Menu e configurações")]
        for i,(keys,description) in enumerate(rows):
            a=label(keys,"key"); a.set_margin_start(20); a.set_margin_top(8)
            b=label(description,"muted"); b.set_margin_end(25)
            grid.attach(a,0,i,1,1); grid.attach(b,1,i,1,1)
        page.pack_start(grid,False,False,0); page.pack_start(Gtk.Box(),True,True,0)
        return page

    def about(self):
        page=box(spacing=23)
        page.pack_start(label("Uma nova forma de reviver\nForbidden Memories.","section-title"),False,False,0)
        page.pack_start(label("O jogo original, rodando nativamente no Linux, com uma porta de entrada feita para o seu PC.\n\nEscolha seu disco uma vez. Nas próximas sessões, é só clicar em jogar.","hero-subtitle",wrap=True),False,False,0)
        page.pack_start(label("SUA ROM", "eyebrow"),False,False,0)
        page.pack_start(label("Compatível com a edição americana SLUS-01411. BIN/IMG são lidos no próprio local; RAR/ZIP são preparados em uma pasta do aplicativo. Sua ROM original não é alterada.","muted",wrap=True),False,False,0)
        page.pack_start(label("CRÉDITOS", "eyebrow"),False,False,0)
        page.pack_start(label("Launcher: GenissonEmilio. Port nativo: Unchiga e colaboradores.\nDescompilação baseada em memories-decomp.\nYu-Gi-Oh! e Forbidden Memories pertencem a seus titulares.","muted",wrap=True),False,False,0)
        install=style(Gtk.Button(label="＋  Adicionar ao menu de aplicativos"),"secondary")
        install.set_halign(Gtk.Align.START); install.connect("clicked",self.install_menu)
        page.pack_start(install,False,False,0)
        self.install_status=label("Depois disso, você pode abrir o jogo pelo menu do Linux.","muted",wrap=True)
        page.pack_start(self.install_status,False,False,0)
        page.pack_start(Gtk.Box(),True,True,0)
        return page

    def navigate(self,name):
        self.stack.set_visible_child_name(name)
        for key,button in self.nav.items():
            context=button.get_style_context()
            (context.add_class if key==name else context.remove_class)("active")

    def choose(self,*_):
        dialog=Gtk.FileChooserDialog(title="Escolha sua ROM de Forbidden Memories",parent=self.window,
                                     action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancelar",Gtk.ResponseType.CANCEL,"Selecionar ROM",Gtk.ResponseType.OK)
        selected=Gtk.FileFilter(); selected.set_name("Forbidden Memories · BIN, IMG, RAR e ZIP")
        for extension in ("bin","img","rar","zip"):
            selected.add_pattern("*."+extension); selected.add_pattern("*."+extension.upper())
        dialog.add_filter(selected)
        if dialog.run()==Gtk.ResponseType.OK:
            path=dialog.get_filename(); dialog.destroy(); self.prepare(path)
        else:
            dialog.destroy()

    def dropped(self,widget,context,x,y,selection,info,time):
        uris=selection.get_uris()
        accepted=False
        if not self.busy and not self.process and len(uris)==1:
            try:
                path,host=GLib.filename_from_uri(uris[0])
                if host and host!="localhost": raise ValueError("Escolha um arquivo deste computador.")
                self.prepare(path); accepted=True
            except (GLib.Error,ValueError) as exc:
                self.error("Confira o arquivo escolhido",str(exc))
        Gtk.drag_finish(context,accepted,False,time)

    def update_status(self,text,error=False):
        self.status.set_text(text)
        context=self.status.get_style_context()
        context.remove_class("ready"); context.remove_class("error")
        if error: context.add_class("error")
        return False

    def set_ready(self):
        self.file_title.set_text(self.library.state.get("name","Forbidden Memories"))
        self.file_subtitle.set_text("SLUS-01411  ·  Edição americana validada")
        self.status.set_text("●  Pronto para duelar")
        self.status.get_style_context().add_class("ready")
        self.play_button.set_sensitive(True)
        self.choose_button.set_label("Trocar ROM…")

    def pulse(self):
        if not self.busy: return False
        self.progress.pulse(); return True

    def prepare(self,path):
        if self.busy or self.process: return False
        self.busy=True; self.failed=False
        self.choose_button.set_sensitive(False); self.play_button.set_sensitive(False)
        self.progress.show(); self.update_status("Preparando seu jogo…")
        GLib.timeout_add(80,self.pulse)
        def worker():
            error=None
            try:
                self.library.prepare(path,lambda text: GLib.idle_add(self.update_status,text))
            except Exception as exc:
                error=str(exc)
            GLib.idle_add(self.prepared,error)
        threading.Thread(target=worker,daemon=False).start()
        return False

    def prepared(self,error):
        self.busy=False; self.progress.hide(); self.choose_button.set_sensitive(True)
        if self.closing: Gtk.main_quit(); return False
        if error:
            self.failed=True
            self.update_status("Não foi possível preparar essa ROM.",True)
            self.error("Confira o arquivo escolhido",error)
            self.play_button.set_sensitive(bool(self.library.disc))
        else:
            self.set_ready()
            if self.args.test_game: GLib.idle_add(self.play)
            elif self.args.screenshot: GLib.timeout_add(500,self.capture_and_exit)
        return False

    def play(self,*_):
        if self.busy or self.process: return False
        self.busy=True; self.play_button.set_sensitive(False); self.choose_button.set_sensitive(False)
        self.update_status("Abrindo o seu próximo duelo…")
        def worker():
            try:
                process=self.library.launch(self.args.test_game)
                GLib.idle_add(self.game_started,process,None)
            except Exception as exc:
                GLib.idle_add(self.game_started,None,str(exc))
        threading.Thread(target=worker,daemon=False).start()
        return False

    def game_started(self,process,error):
        self.busy=False
        if self.closing:
            Gtk.main_quit(); return False
        if error:
            self.failed=True; self.choose_button.set_sensitive(True); self.play_button.set_sensitive(True)
            self.update_status("Não foi possível abrir o jogo.",True); self.error("O jogo não abriu",error)
        else:
            self.process=process; self.play_button.set_label("Em jogo…")
            self.update_status("●  Duelo em andamento. Boa sorte!")
            GLib.timeout_add(300,self.watch_game)
        return False

    def watch_game(self):
        code=self.process.poll()
        if code is None: return True
        self.process=None; self.choose_button.set_sensitive(True)
        self.play_button.set_label("▶   Iniciar jogo"); self.set_ready()
        if code:
            self.failed=True
            self.update_status("O jogo encerrou com um erro.",True)
            self.error("O jogo foi encerrado",f"O jogo retornou o código {code}.\n\nOs detalhes estão em:\n{self.library.directory / 'last-game.log'}")
        elif self.args.test_game:
            if not (self.library.directory / "game-test.ppm").is_file():
                self.failed=True
            GLib.timeout_add(500,self.capture_and_exit)
        return False

    def error(self,title,text):
        if self.args.test_game or self.args.screenshot:
            print(title+": "+text,file=sys.stderr)
            if self.args.rom:
                GLib.timeout_add(100,self.capture_and_exit)
            return
        dialog=Gtk.MessageDialog(transient_for=self.window,flags=0,message_type=Gtk.MessageType.ERROR,
                                 buttons=Gtk.ButtonsType.CLOSE,text=title)
        dialog.format_secondary_text(text); dialog.run(); dialog.destroy()

    def open_saves(self,*_):
        path=self.library.player_directory / "saves"; path.mkdir(parents=True,exist_ok=True)
        Gtk.show_uri_on_window(self.window,path.as_uri(),Gdk.CURRENT_TIME)

    def install_menu(self,*_):
        try:
            self.library.install_desktop_entry()
            self.install_status.set_text("✓  Atalho criado! Procure “Forbidden Memories PC” no menu de aplicativos.")
        except OSError as exc:
            self.error("Não foi possível criar o atalho",str(exc))

    def capture_and_exit(self):
        if self.args.screenshot:
            # Draw the actual widget tree. GDK's X11 window readback can abort
            # inside Cairo 1.16 under Xvfb; widget rendering works on Wayland too.
            surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,self.window.get_allocated_width(),self.window.get_allocated_height())
            self.window.draw(cairo.Context(surface))
            output=Path(self.args.screenshot); output.parent.mkdir(parents=True,exist_ok=True)
            surface.write_to_png(str(output))
        if self.args.test_game:
            result={"passed":not self.failed,"disc":str(self.library.disc),
                    "frame_created":(self.library.directory / "game-test.ppm").is_file()}
            (self.library.directory / "launcher-test.json").write_text(json.dumps(result,indent=2)+"\n")
        Gtk.main_quit(); return False

    def close(self,*_):
        if self.busy:
            self.closing=True; self.window.hide(); return True
        Gtk.main_quit(); return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom",type=Path,help=argparse.SUPPRESS)
    parser.add_argument("--data-dir",type=Path,help=argparse.SUPPRESS)
    parser.add_argument("--screenshot",type=Path,help=argparse.SUPPRESS)
    parser.add_argument("--test-game",action="store_true",help=argparse.SUPPRESS)
    parser.add_argument("--install-shortcut",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.install_shortcut:
        print(Library(args.data_dir).install_desktop_entry()); return 0
    if args.test_game and not args.rom:
        parser.error("--test-game requires --rom")
    launcher=Launcher(args); Gtk.main()
    return int(launcher.failed)


if __name__=="__main__":
    raise SystemExit(main())
