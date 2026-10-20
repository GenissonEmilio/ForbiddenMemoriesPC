#!/usr/bin/env python3
"""The page's home-screen icon (an orange ball with four stars) and web app manifest -> port/build/web/."""
import json, math, pathlib, sys
from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parents[2] / "port/build/web"


def icon(size):
    s = 4 * size
    im = Image.new("RGB", (s, s), (11, 12, 16))
    d = ImageDraw.Draw(im)
    r = s * 0.40
    c = s / 2
    for i in range(60, 0, -1):  # the ball, lit from the top left
        t = i / 60
        col = (int(255 * (0.75 + 0.25 * (1 - t))), int(150 + 80 * (1 - t) ** 2), int(40 + 120 * (1 - t) ** 3))
        rr = r * t
        off = (1 - t) * r * 0.35
        d.ellipse([c - rr - off, c - rr - off, c + rr - off, c + rr - off], fill=col)

    def star(x, y, R):
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            q = R if k % 2 == 0 else R * 0.42
            pts.append((x + q * math.cos(a), y + q * math.sin(a)))
        d.polygon(pts, fill=(214, 34, 34))
    R = s * 0.085
    for x, y in [(-0.12, -0.12), (0.12, -0.12), (-0.12, 0.12), (0.12, 0.12)]:
        star(c + x * s, c + y * s, R)
    return im.resize((size, size), Image.LANCZOS)


# (no start_url: a Home Screen app then opens the address it was added from, with its ?k= key, which a key-locked
# server needs; the app keeps its own cookies, apart from Safari's)
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for n in (180, 192, 512):
        icon(n).save(OUT / f"icon-{n}.png")
    (OUT / "manifest.webmanifest").write_text(json.dumps({
        "name": "Budokai Tenkaichi 3", "short_name": "Tenkaichi 3", "display": "fullscreen",
        "background_color": "#000000", "theme_color": "#000000",
        "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
