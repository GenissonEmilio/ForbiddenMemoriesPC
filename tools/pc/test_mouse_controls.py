#!/usr/bin/env python3
"""Exercise native SDL mouse events against a local supported disc (never uploaded)."""
import argparse
import json
import re
import struct
from pathlib import Path

from yfm_control import Game

ROOT = Path(__file__).resolve().parents[2]


class Mouse:
    def __init__(self, game, commands):
        self.game, self.commands = game, commands

    def viewport(self):
        matches = re.findall(r"mouse viewport ([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) game (\d+)",
                             self.game.log_path.read_text(errors="replace"))
        assert matches, "Native SDL viewport was not reported"
        return list(map(float, matches[-1]))

    def send(self, command, after=30):
        temporary = self.commands.with_suffix(".new")
        temporary.write_text(f"{self.game.frame + 1}:{command}")
        temporary.replace(self.commands)
        self.game.step(after)

    def event(self, kind, x, y, after=30, logical=True):
        if logical:
            vx, vy, vw, vh, gw = self.viewport()
            x, y = vx + (x + (gw - 320) / 2) * vw / gw, vy + y * vh / 240
        self.send(f"{kind}:{int(x)}:{int(y)}", after)

    def toolbar(self, index, after=30):
        dimensions = re.findall(r"layout (\d+)x(\d+) logical", self.game.log_path.read_text())
        width, height = map(int, dimensions[-1])
        self.event("click", (index + .5) * width / 8, height - 22, after, logical=False)

    def card(self, slot):
        address = int.from_bytes(self.game.peek("D_800EA030", 4, offset=slot * 12), "little")
        x, y = struct.unpack("<hh", self.game.peek(address + 0x30, 4))
        return x + 26, y + 25


def run(binary, output, aspect, scale):
    output.mkdir(parents=True, exist_ok=True)
    commands = output / "events.txt"
    commands.write_text("")
    settings = {"scale": 2, "scaling": 1, "internal_scale": scale, "aspect": aspect, "menu_scale": 1}
    with Game(binary, out=output, headless=False, settings=settings,
              env={"MEMORIES_SDL_SCRIPT_FILE": str(commands), "MEMORIES_TRACE": "window",
                   "MEMORIES_NO_AUDIO": "1", "MEMORIES_SPEED": "-1"}) as game:
        mouse = Mouse(game, commands)
        def title_prompt(g):
            if not g.resident("main_menu"):
                return False
            prompt = g.u32("D_80184560")
            return bool(prompt and g.u16(prompt + 8) & 0x40)
        game.wait_until(title_prompt, timeout=6000, every=30, what="Push Start Button")
        game.press("start", after=120)
        game.wait_until(lambda g: not title_prompt(g) and not g.u8("D_80184599"),
                        timeout=1200, every=5, what="the title menu slide")
        mouse.event("click", 160, 178, after=180)
        assert game.info()["mode"] & 31 == 11, "Click must choose Options, rather than the previous menu item"

        game.goto("duel", opponent=1, deck="410,302,107,231,573")
        game.duel_ready()
        game.step(100)
        hand = [card["id"] for card in game.duel()[0]["hand"]]
        mouse.event("press", *mouse.card(2), after=8)
        mouse.event("move", 310, 30, after=8)
        mouse.event("release", 310, 30, after=100)
        assert game.phase() == 4 and [card["id"] for card in game.duel()[0]["hand"]] == hand
        assert not any(game.duel()[0]["monsters"]), "An invalid drop must leave the card in the hand"

        mouse.event("press", *mouse.card(2), after=8)
        mouse.event("move", 218, 130, after=8)
        mouse.send("shot", after=8)  # Window, including the dragged card and native controls.
        mouse.event("release", 218, 130, after=120)
        assert game.hand_cursor() == 2
        mouse.event("click", 110, 173, after=300)  # Face up.
        assert game.phase() == 8, "The game's guardian choice must still be offered"
        widget = int.from_bytes(game.peek("D_800EB0F8", 4, offset=0x30), "little")
        x, y = struct.unpack("<hh", game.peek(widget + 0x28, 4))
        selected = game.u8("gDialog_bChoice")
        bottom = struct.unpack("<h", game.peek(widget + 0x3a, 2))[0]
        step = 16 if bottom - y >= 16 else 12
        mouse.event("click", x + 20, y - selected * step + step + step // 2, after=180)
        monster = game.duel()[0]["monsters"][3]
        assert game.phase() == 5 and monster["id"] == hand[2] and not monster["face_down"]
        assert monster["flags"] & 0x200, "Click must select the second guardian star"
        game.shot("placed.png")
        mouse.send("shot", after=8)

        mouse.toolbar(7, after=30)
        assert game.turn() != 0 or game.phase() == 10, "Mouse turn button must finish the player's turn"
        game.wait_turn(("hand",), timeout=30000)
        game.play_card(0, face_up=True)
        game.wait_until(lambda g: (g.u8("D_8009B174") & 15) == 3 and not g.u16("D_8009B162"),
                        timeout=1200, what="the field cursor")
        own = game.duel()[0]["monsters"]
        column = next(i for i, card in enumerate(own) if card and not card["used_this_turn"])
        mouse.event("click", 40 + column * 58, 192, after=45)
        game.wait_until(lambda g: (g.u8("D_8009B174") & 15) == 6 and not g.u16("D_8009B162"),
                        timeout=1200, what="the attack target cursor")
        targets = [i for i, card in enumerate(game.field()[1]) if card]
        mouse.event("click", 40 + (targets[0] if targets else 0) * 58, 192, after=120)
        game._settle()
        result = game.duel()[0]["monsters"][column]
        assert result is None or result["used_this_turn"], "Clicking the field and a target must execute the attack"
        mouse.send("shot", after=8)
        report = {"passed": True, "aspect": aspect, "internal_scale": scale,
                  "checks": ["title-menu", "invalid-drop", "drag-card", "face-up", "second-guardian",
                             "fourth-zone", "end-turn", "attack-target"]}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "tmp/pc/game32/memories-pc")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/mouse-controls")
    parser.add_argument("--case", choices=("standard", "widescreen-2x"))
    args = parser.parse_args()
    reports = [run(args.binary.resolve(), args.output.resolve() / name, aspect, scale)
               for name, aspect, scale in (("standard", 1, 1), ("widescreen-2x", 2, 2))
               if not args.case or name == args.case]
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
