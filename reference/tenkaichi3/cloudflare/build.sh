#!/bin/bash
# Makes public/ for the Cloudflare deploy: an explicit list of files of the browser build, and the owner's disc image
# in 1 MiB pieces (public/disc/00000.bin, ...; public/disc/index.json gives the size; src/worker.js serves them only
# behind the key, the page fetches them whole). Never the LAN key, telemetry, the Node build or anything else in
# port/build/web.
set -euo pipefail
cd "$(dirname "$0")"
SRC=../port/build/web
ISO=../disc/bt3-usa.iso
PIECE=$((1024 * 1024))
ALLOW="index.html net.js net.css bt3-jspi.js bt3-jspi.wasm bt3-async.js bt3-async.wasm icon-180.png icon-192.png icon-512.png manifest.webmanifest"
mkdir -p public/disc
find public -maxdepth 1 -type f -delete
for f in $ALLOW; do
  [ -f "$SRC/$f" ] || { echo "missing $SRC/$f (build first)"; exit 1; }
  cp "$SRC/$f" public/
done
printf '/*\n  Cache-Control: no-cache\n' > public/_headers
# the disc pieces: made once (an existing piece of the right size is kept, so a redeploy does not rewrite them)
size=$(python3 -c 'import os, sys; print(os.path.getsize(sys.argv[1]))' "$ISO")
count=$(( (size + PIECE - 1) / PIECE ))
# (pieces of another size, from an older layout, go)
find public/disc -name '*.bin' -size +1024k -delete
find public/disc -name '*.bin' | while read -r p; do n=$((10#$(basename "$p" .bin))); [ "$n" -lt "$count" ] || rm "$p"; done
for ((i = 0; i < count; i++)); do
  p=$(printf 'public/disc/%05d.bin' "$i")
  want=$(( i == count - 1 ? size - i * PIECE : PIECE ))
  if [ ! -f "$p" ] || [ "$(python3 -c 'import os, sys; print(os.path.getsize(sys.argv[1]))' "$p")" != "$want" ]; then
    dd if="$ISO" of="$p" bs=1048576 skip=$i count=1 2>/dev/null
  fi
done
printf '{"size": %d, "piece": %d}\n' "$size" "$PIECE" > public/disc/index.json
n=$(ls public | wc -l | tr -d ' ')
pieces=$(ls public/disc | grep -c '\.bin$' | tr -d ' ')
[ "$n" = 13 ] || { echo "public/ has $n entries, expected 12 files and disc/"; exit 1; }
[ "$pieces" = "$count" ] || { echo "public/disc has $pieces pieces, expected $count"; exit 1; }
if find public | grep -qiE '\.iso$|\.key$|telemetry|\.env|_node'; then echo "refusing: unexpected file in public/"; exit 1; fi
echo "public/: $(du -sh public | cut -f1), $count disc pieces"
