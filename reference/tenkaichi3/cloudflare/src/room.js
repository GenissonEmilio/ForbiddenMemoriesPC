// An online room (Dragon Net Battle): one Durable Object per room code, holding the two players' connections
// (WebSockets, hibernated between messages). port/web/net.js is the other end.
//
//   /net/ws?room=CODE&role=host|join&phase=lobby|session&name=...&cid=...
//
// Text messages are JSON and carry the setting up: who is there ({t:'peer'}), the host's start ({t:'go'}), and the
// WebRTC offer, answer and candidates ({t:'sig'}), passed to the other player as they are. Binary messages are the
// game's own packets, passed on when the two browsers cannot reach each other directly (the relay).
//
// Lobby: the host opens the room; a second host with another cid is turned away (the code is taken), and one who
// joins a room without a host is told so. Session (after both pages loaded themselves into the match): either may
// arrive first and waits for the other.

const ROLES = ['host', 'join'];

export class Room {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  others(role) {
    return this.ctx.getWebSockets(role === 'host' ? 'join' : 'host');
  }

  info(ws) {
    try { return ws.deserializeAttachment() || {}; } catch (e) { return {}; }
  }

  // The match log (one object, '_log'): what the pages report during matches (port/web/net.js matchLog), the last
  // few thousand lines, for looking at a match that went slow. GET /net/log[?room=CODE] gives them back.
  async log(req, url) {
    const sql = this.ctx.storage.sql;
    sql.exec('CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER, room TEXT, line TEXT)');
    if (req.method === 'POST') {
      const body = (await req.text()).slice(0, 2000);
      let room = '';
      try { room = String(JSON.parse(body).room || '').slice(0, 8); } catch (e) { return new Response('bad', { status: 400 }); }
      sql.exec('INSERT INTO log (t, room, line) VALUES (?, ?, ?)', Date.now(), room, body);
      sql.exec('DELETE FROM log WHERE id <= (SELECT MAX(id) FROM log) - 20000');
      return new Response(null, { status: 204 });
    }
    const room = url.searchParams.get('room');
    const rows = room ? sql.exec('SELECT t, line FROM log WHERE room = ? ORDER BY id DESC LIMIT 3000', room).toArray()
      : sql.exec('SELECT t, line FROM log ORDER BY id DESC LIMIT 3000').toArray();
    return new Response(rows.reverse().map((r) => new Date(r.t).toISOString() + ' ' + r.line).join('\n') + '\n',
      { headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' } });
  }

  // Quick Match (one object, '_queue'): the players searching wait here on a WebSocket; as soon as two are there they
  // are paired. Each is told a new room code and a side ({t:'match', room, role, vs, rules}), and both pages then
  // load themselves into that room's session exactly as after Host / Join (port/web/net.js). The ones waiting hear
  // how many are searching ({t:'count', n}).
  waiting() {
    return this.ctx.getWebSockets('q').filter((ws) => { const o = this.info(ws); return !o.matched && ws.readyState === 1; });
  }
  count() {
    const w = this.waiting();
    for (const ws of w) { try { ws.send(JSON.stringify({ t: 'count', n: w.length })); } catch (e) {} }
  }
  async queue(req, url) {
    if (req.headers.get('Upgrade') !== 'websocket') return new Response('websocket only', { status: 426 });
    const name = (url.searchParams.get('name') || 'Player').slice(0, 16);
    const cid = (url.searchParams.get('cid') || '').slice(0, 40);
    const [client, server] = Object.values(new WebSocketPair());
    this.ctx.acceptWebSocket(server, ['q']);
    server.serializeAttachment({ q: 1, name, cid, t: Date.now() });
    // the same player again (a second tab, a reload): the older one goes
    for (const ws of this.waiting()) {
      if (ws !== server && this.info(ws).cid === cid && cid) { ws.serializeAttachment({ ...this.info(ws), matched: 1 }); try { ws.close(4000, 'replaced'); } catch (e) {} }
    }
    const others = this.waiting().filter((ws) => ws !== server).sort((a, b) => this.info(a).t - this.info(b).t);
    if (others.length) {
      const other = others[0], o = this.info(other);
      const L = 'ABCDEFGHJKLMNPQRSTUVWXYZ', room = Array.from({ length: 4 }, () => L[Math.floor(Math.random() * L.length)]).join('');
      const rules = String(3 << 8); // single battle, 240 seconds: the game's own defaults
      other.serializeAttachment({ ...o, matched: 1 });
      server.serializeAttachment({ q: 1, name, cid, t: Date.now(), matched: 1 });
      other.send(JSON.stringify({ t: 'match', room, role: 'host', vs: name, rules }));
      server.send(JSON.stringify({ t: 'match', room, role: 'join', vs: o.name, rules }));
    }
    this.count();
    return new Response(null, { status: 101, webSocket: client });
  }

  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === '/net/stat' || url.pathname === '/net/log') return this.log(req, url);
    if (url.pathname === '/net/queue') return this.queue(req, url);
    if (req.headers.get('Upgrade') !== 'websocket') return new Response('websocket only', { status: 426 });
    const role = url.searchParams.get('role');
    const phase = url.searchParams.get('phase') === 'session' ? 'session' : 'lobby';
    const name = (url.searchParams.get('name') || 'Player').slice(0, 16);
    const cid = (url.searchParams.get('cid') || '').slice(0, 40);
    if (!ROLES.includes(role)) return new Response('bad role', { status: 400 });
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.ctx.acceptWebSocket(server, [role]);
    server.serializeAttachment({ role, phase, name, cid });
    // the same role already here: the same player again (a reload) replaces it; anyone else is turned away
    for (const ws of this.ctx.getWebSockets(role)) {
      if (ws === server) continue;
      const o = this.info(ws);
      if (o.cid && o.cid === cid) { try { ws.close(4000, 'replaced'); } catch (e) {} continue; }
      server.send(JSON.stringify({ t: role === 'host' ? 'taken' : 'full' }));
      server.close(4001, 'taken');
      return new Response(null, { status: 101, webSocket: client });
    }
    const other = this.others(role).find((ws) => this.info(ws).phase === phase);
    if (!other && role === 'join' && phase === 'lobby') {
      server.send(JSON.stringify({ t: 'nohost' }));
      server.close(4002, 'no host');
      return new Response(null, { status: 101, webSocket: client });
    }
    if (other) {
      const o = this.info(other);
      server.send(JSON.stringify({ t: 'peer', name: o.name }));
      other.send(JSON.stringify({ t: 'peer', name }));
    } else {
      server.send(JSON.stringify({ t: 'wait' }));
    }
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws, msg) {
    const me = this.info(ws);
    if (me.q) { // (Quick Match: only "still here")
      if (typeof msg === 'string' && msg.includes('ping')) { try { ws.send(JSON.stringify({ t: 'pong' })); } catch (e) {} }
      return;
    }
    const to = this.others(me.role).filter((o) => this.info(o).phase === me.phase);
    if (typeof msg !== 'string') { // the game's packets (relay)
      for (const o of to) { try { o.send(msg); } catch (e) {} }
      return;
    }
    let m;
    try { m = JSON.parse(msg); } catch (e) { return; }
    if (m.t === 'ping') { ws.send(JSON.stringify({ t: 'pong', ts: m.ts })); return; }
    if (m.t === 'sig' || m.t === 'go' || m.t === 'relay' || m.t === 'bye') {
      for (const o of to) { try { o.send(msg); } catch (e) {} }
    }
  }

  async webSocketClose(ws, code) {
    const me = this.info(ws);
    if (me.q) { ws.serializeAttachment({ ...me, matched: 1 }); this.count(); return; }
    if (code === 4000 || code === 4001 || code === 4002) return; // (replaced by the same player, or turned away)
    for (const o of this.others(me.role)) {
      if (this.info(o).phase === me.phase) { try { o.send(JSON.stringify({ t: 'left' })); } catch (e) {} }
    }
  }

  async webSocketError(ws) {
    await this.webSocketClose(ws, 1006);
  }
}
