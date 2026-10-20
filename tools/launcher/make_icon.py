#!/usr/bin/env python3
"""Render our code-drawn emblem to PNG, avoiding an SVG loader dependency at runtime."""
from pathlib import Path
import cairo
from main import eye

surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,256,256)
cr=cairo.Context(surface)
cr.set_source_rgb(.075,.068,.105)
cr.rectangle(0,0,256,256); cr.fill()
cr.set_source_rgb(.42,.31,.18); cr.set_line_width(4)
cr.rectangle(8,8,240,240); cr.stroke()
eye(cr,128,111,1.22)
surface.write_to_png(str(Path(__file__).parent / "assets/icon.png"))
