# The browser build

The same port, compiled to WebAssembly: the game runs in a web page, on a computer and on a phone (iPhone and
Android), from **your own disc image**. Nothing of the game is in this repository; you build the page yourself
from your disc, and what you build is for you alone.

## What it adds

- Two builds of the same program, and the page picks one: `bt3-jspi` (Chrome, Edge: WebAssembly JSPI) and
  `bt3-async` (Safari and every iPhone browser: Asyncify).
- Phones: touch controls laid out for portrait and landscape (stick, D-pad, face buttons, shoulders, Start /
  Select, a Hide button), sound that starts on the first tap, saves kept in the browser (IndexedDB), and an
  icon for the home screen.
- Controllers through the browser (a PS5 or Xbox pad over Bluetooth or USB); two controllers play 1P vs 2P.
- Online play (Dragon Net Battle, on the main menu): Quick Match, or host a room and give its four-letter code to
  the other player. The game's own lockstep netplay (`port/src/gs/net.c`) runs over a WebRTC data channel, with
  a relay through the server when the two cannot reach each other directly. The screens are drawn in the look of
  the game's menus. Both players need a build from the same disc.
- One tap or Start skips all the boot logos; the opening movie is off unless the address has `?movie=1`.

## Building

You need Python 3, Node.js, and Emscripten (`emcc` on the path; built with 6.0), and the game's files extracted from
your disc by the normal setup:

```
python3 install.py --iso <your disc image>      # once: checks the disc, extracts what the build needs
python3 port/web/build.py                        # compiles, rewrites the IR, generates the data objects
python3 port/web/link.py web                     # -> port/build/web/bt3-jspi.{js,wasm}
python3 port/web/link.py webasync                # -> port/build/web/bt3-async.{js,wasm}
```

`build.py` also runs `gen_data_web.py`; the linker requires its `data_objects.txt` manifest.
The incremental cache hashes preprocessed source (including all included headers), the compiler version,
and the transformation scripts. Use `--clean` to discard the cached IR and objects explicitly.

**The result contains the game's code and data from your disc.** Unlike the desktop release, the browser build
takes the game's built-in data tables from the extracted files (`port/web/gen_data_web.py`), so
`port/build/web/` must never be published. It is ignored by git.

## Playing

On this computer:

```
node port/web/serve.mjs 4500 <your disc image>
```

and open http://127.0.0.1:4500. The page reads the disc image through the server with range requests; it is
never copied anywhere.

On your phone, on the same Wi-Fi:

```
node port/web/serve.mjs 4500 <your disc image> --lan
```

prints an address with a secret key (`?k=...`). Open it on the phone; requests without the key are refused.
Never forward this port to the internet.

## Your own copy on Cloudflare (optional)

`cloudflare/` deploys the page and your disc image to **your own** Cloudflare account as a Worker, behind a
secret key: anyone without the key gets 403, the disc included. It also runs the rooms for online play
(a Durable Object).

1. Put your account id in `cloudflare/wrangler.jsonc` (or a copy, `wrangler.local.jsonc`, which git ignores).
2. `bash cloudflare/build.sh` puts the build and your disc image (`disc/bt3-usa.iso`, in 1 MiB pieces) in
   `cloudflare/public/`, which git ignores.
3. From `cloudflare/`: `npx wrangler@latest secret put BT3_KEY` (a long random value), then
   `npx wrangler@latest deploy`.
4. Open `https://bt3.<your-subdomain>.workers.dev/?k=<key>` once; the page keeps a cookie.

The key is what keeps your copy of the game private: do not remove the check in `cloudflare/src/worker.js`, and
share the link only with people who own the game.

## Testing

- `node port/web/serve.mjs ...` with `?hud=1` shows frames per second and how busy the program is; with
  `?telemetry=1` the page reports both to the server (`port/build/telemetry.log`, read with
  `python3 port/web/telemetry.py`).
- `port/web/iostest.sh` opens the game in the iOS Simulator and prints the same report (the Simulator's GPU is
  much slower than a phone's: use it for layout, input and sound, not for speed).
- `?env=NAME=value,...` sets the port's switches (`BT3_HASH`, `BT3_SCALE`, ...), as the environment does on PC.

## Files

| Path | Contents |
|---|---|
| `port/web/build.py`, `irweb.py`, `link.py` | The build: compile, rewrite the IR (soft float, fixed PS2 address layout), link both targets |
| `port/web/shell.html` | The page: loading, the disc reader, touch controls, sound, saves |
| `port/web/net.js`, `net.css` | Online play: the lobby screens, rooms, Quick Match, the WebRTC link |
| `port/web/src/`, `target/`, `include/` | The browser side of the port: touch input, waits, files from the disc |
| `port/web/serve.mjs` | The local test server |
| `cloudflare/` | The optional private deploy: the Worker (key check), the rooms and Quick Match |
