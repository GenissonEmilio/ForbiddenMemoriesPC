// Local test server of the browser build: port/build/web/ and, at /disc.iso, the user's own disc image with HTTP
// range requests (the page reads it the way it reads a chosen file). Listens on this computer only (127.0.0.1):
// the build contains code compiled from the game, and the image is the user's.
//   node port/web/serve.mjs <port> <disc image> [--lan]
// --lan: also for the user's own phone on the same Wi-Fi. Every request from another device then needs a secret
// key: the printed address carries it once (?k=...), the server answers with a cookie, and anything without the key
// gets 403. Never forward this port to the internet.
import http from 'node:http';
import crypto from 'node:crypto';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../build/web');
const port = +(process.argv[2] || 4500), iso = process.argv[3];
const TELEMETRY = path.resolve(ROOT, '../telemetry.log');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.wasm': 'application/wasm', '.json': 'application/json',
                '.png': 'image/png', '.webmanifest': 'application/manifest+json', '.css': 'text/css' };
const lan = process.argv.includes('--lan');
const KEY_FILE = path.resolve(ROOT, '../lan.key'); // kept, so the phone's home-screen app keeps working across restarts
const key = lan ? (fs.existsSync(KEY_FILE) ? fs.readFileSync(KEY_FILE, 'utf8').trim() : crypto.randomBytes(18).toString('base64url')) : '';
if (lan) fs.writeFileSync(KEY_FILE, key, { mode: 0o600 });
const local = (req) => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress);

http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    if (lan && !local(req)) {
        const cookie = /(?:^|;\s*)bt3k=([\w-]+)/.exec(req.headers.cookie || '');
        if (url.searchParams.get('k') === key) {
            res.setHeader('Set-Cookie', `bt3k=${key}; Path=/; Max-Age=31536000; SameSite=Strict; HttpOnly`);
        } else if (!cookie || cookie[1] !== key) {
            res.writeHead(403).end('forbidden'); return;
        }
    }
    // test telemetry: the page (?telemetry=1) posts its log and frame statistics here; appended to port/build/telemetry.log
    if (url.pathname === '/telemetry' && req.method === 'POST') {
        let body = '';
        req.on('data', (c) => { body += c; if (body.length > 4e6) req.destroy(); });
        req.on('end', () => { fs.appendFile(TELEMETRY, body.replace(/\n?$/, '\n'), () => {}); res.writeHead(204).end(); });
        return;
    }
    let file, type;
    if (url.pathname === '/disc.iso') {
        if (!iso || !fs.existsSync(iso)) { res.writeHead(404).end('no disc image given to the server'); return; }
        file = iso; type = 'application/octet-stream';
    } else {
        file = path.join(ROOT, path.normalize(url.pathname === '/' ? '/index.html' : url.pathname));
        if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404).end('not found'); return; }
        type = TYPES[path.extname(file)] || 'application/octet-stream';
    }
    const fail = (e) => { console.error(`${url.pathname}: ${e.message}`); if (!res.headersSent) res.writeHead(500); res.end(String(e.message)); };
    try { fs.accessSync(file, fs.constants.R_OK); fs.closeSync(fs.openSync(file, 'r')); } catch (e) { fail(e); return; }
    const size = fs.statSync(file).size, range = /bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
    const head = { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store' };
    if (range) {
        const a = +range[1], b = range[2] ? Math.min(+range[2], size - 1) : size - 1;
        res.writeHead(206, { ...head, 'Content-Range': `bytes ${a}-${b}/${size}`, 'Content-Length': b - a + 1 });
        fs.createReadStream(file, { start: a, end: b }).on("error", fail).pipe(res);
    } else {
        res.writeHead(200, { ...head, 'Content-Length': size });
        fs.createReadStream(file).on("error", fail).pipe(res);
    }
}).listen(port, lan ? '0.0.0.0' : '127.0.0.1', () => {
    console.log(`http://127.0.0.1:${port}/  (disc image: ${iso || 'none'})`);
    if (lan) {
        for (const nets of Object.values(os.networkInterfaces())) for (const n of nets) {
            if (n.family === 'IPv4' && !n.internal) console.log(`on this Wi-Fi: http://${n.address}:${port}/?k=${key}`);
        }
    }
});
