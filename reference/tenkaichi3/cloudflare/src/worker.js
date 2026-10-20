// The browser build on Cloudflare, locked to its owner (your own Worker, e.g. bt3.<your-subdomain>.workers.dev).
//
// Every request runs this Worker first (wrangler.jsonc: run_worker_first). It needs the secret key (Worker secret
// BT3_KEY): the link carries it once (?k=...), the answer sets a cookie, and anything without either gets 403, the
// disc pieces included. With no secret set at all, everything is 403.
//
// The game's files and the owner's disc image are the static assets (public/, made by build.sh). The image is in
// pieces of 1 MiB (disc/00000.bin, ...; disc/index.json gives the size), which the page fetches whole, several at a
// time (port/web/shell.html, pieceDisc). They never change, so the browser may keep them as long as it likes.
//
// Online play (Dragon Net Battle): /net/ws?room=CODE&... is a WebSocket to that room's Durable Object (src/room.js),
// behind the same key.
export { Room } from './room.js';

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const key = env.BT3_KEY || '';
    const cookie = /(?:^|;\s*)bt3k=([\w-]+)/.exec(req.headers.get('cookie') || '');
    // the Home Screen app's icon and manifest carry nothing of the game
    const open = /^\/(icon-\d+\.png|manifest\.webmanifest)$/.test(url.pathname);
    let setCookie = null;
    if (key && url.searchParams.get('k') === key) {
      setCookie = `bt3k=${key}; Path=/; Max-Age=31536000; SameSite=Lax; HttpOnly${url.protocol === 'https:' ? '; Secure' : ''}`; // (Safari drops Secure cookies on http: wrangler dev)
    } else if (!open && (!key || !cookie || cookie[1] !== key)) {
      return new Response('forbidden', { status: 403 });
    }
    let res;
    if (url.pathname === '/net/stat' || url.pathname === '/net/log') { // the match log (src/room.js)
      return env.ROOMS.get(env.ROOMS.idFromName('_log')).fetch(req);
    }
    if (url.pathname === '/net/queue') { // Quick Match (src/room.js)
      return env.ROOMS.get(env.ROOMS.idFromName('_queue')).fetch(req);
    }
    if (url.pathname === '/net/ws') {
      const code = url.searchParams.get('room') || '';
      if (!/^[A-Z]{4}$/.test(code)) return new Response('bad room code', { status: 400 });
      return env.ROOMS.get(env.ROOMS.idFromName(code)).fetch(req);
    }
    if (url.pathname === '/telemetry') {
      res = new Response(null, { status: 204 }); // (the test server's statistics: not kept here)
    } else {
      res = await env.ASSETS.fetch(req);
    }
    const piece = /^\/disc\/\d{5}\.bin$/.test(url.pathname) && res.status === 200;
    if (setCookie || piece) {
      res = new Response(res.body, res);
      if (setCookie) res.headers.append('Set-Cookie', setCookie);
      if (piece) res.headers.set('Cache-Control', 'private, max-age=31536000, immutable');
    }
    return res;
  },
};
