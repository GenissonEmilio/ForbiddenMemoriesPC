// Online play in the browser (Dragon Net Battle): the lobby screens, the connection to the other player, and the
// session's start and end. Loaded by shell.html before the program.
//
//   The game's main menu entry "Dragon Net Battle" (port/src/gs/ui.cpp) opens these screens over the main menu.
//   Host a Match: a room with a four-letter code (a Durable Object, cloudflare/src/room.js) and the battle rules.
//   Join a Match: the code. When both are in the room, both pages load themselves again into the session
//   (?net=host|join&room=CODE...), connect (WebRTC data channel, else the room relays), and only then start the
//   program, as a session (gs/net.c: BT3_NET_SESSION; it boots straight into the versus mode, both players with
//   the same fresh save). Leaving the versus mode, or the other player leaving, loads the page back to normal.
//
// The game's packets (gs/net.c) go through Module.netSend / Module.netRecv: one packet a message, unreliable and
// unordered, as the UDP the program was written for.
(function () {
  'use strict';
  const Q = new URLSearchParams(location.search);
  const LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'; // (no I and O: not mistaken for 1 and 0)
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  let cid = store.get('bt3.cid', '');
  if (!cid) { cid = Math.random().toString(36).slice(2, 12); store.set('bt3.cid', cid); }
  const myName = () => store.get('bt3.name', 'Player').slice(0, 16) || 'Player';
  const named = () => !!(store.get('bt3.name', '') || '').trim(); // (a name was chosen: asked for before the first match)
  const wsUrl = (room, role, phase) => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/net/ws?room=${room}` +
    `&role=${role}&phase=${phase}&name=${encodeURIComponent(myName())}&cid=${cid}`;
  const newCode = () => Array.from({ length: 4 }, () => LETTERS[Math.floor(Math.random() * LETTERS.length)]).join('');
  const log = (t) => { try { (window.Module && Module.keep ? Module.keep : console.log)('net: ' + t); } catch (e) {} };

  // ---------------------------------------------------------------------------------------------------------------
  // The link to the other player in a session: the room's WebSocket for setting up, a WebRTC data channel for the
  // game's packets, and the WebSocket itself when the channel does not open (some mobile networks).
  // ---------------------------------------------------------------------------------------------------------------
  const ICE = [{ urls: ['stun:stun.cloudflare.com:3478', 'stun:stun.l.google.com:19302'] }];
  const Link = {
    ws: null, pc: null, dc: null, mode: '', queue: [], peerName: '', onState: null, keep: 0, gone: false,

    open(room, role) {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl(room, role, 'session'));
        ws.binaryType = 'arraybuffer';
        this.ws = ws;
        let settled = false, fallback = 0;
        const done = (mode) => {
          if (settled) return;
          settled = true;
          clearTimeout(fallback);
          this.mode = mode;
          log(`connected (${mode})`);
          // "still here", also while this page's game waits for the disc (gs/net.c: T_KEEP)
          this.keep = setInterval(() => this.send(new Uint8Array([0x42, 0x54, 0x33, 0x4E, 9, 0, 0, 0])), 500);
          resolve(mode);
        };
        const relay = () => { if (!settled) { try { ws.send(JSON.stringify({ t: 'relay' })); } catch (e) {} done('relay'); } };
        ws.onmessage = async (e) => {
          if (typeof e.data !== 'string') { this.push(new Uint8Array(e.data)); return; }
          const m = JSON.parse(e.data);
          if (m.t === 'peer') {
            this.peerName = m.name || '';
            this.onState && this.onState('peer', m.name);
            if (role === 'host') this.offer(ws);
            clearTimeout(fallback);
            fallback = setTimeout(relay, 8000); // no direct channel in this time: through the room
          } else if (m.t === 'sig') {
            await this.signal(ws, m, role);
          } else if (m.t === 'relay') {
            relay();
          } else if (m.t === 'left' || m.t === 'bye') {
            this.gone = true;
            if (!settled) { settled = true; reject(new Error('The other player left.')); }
            else this.onState && this.onState('left');
          }
        };
        ws.onclose = () => { if (!settled) { settled = true; reject(new Error('Could not reach the room.')); } };
        ws.onerror = () => {};
        this.ready = done;
      });
    },
    makePc(ws) {
      const pc = new RTCPeerConnection({ iceServers: ICE });
      this.pc = pc;
      pc.onicecandidate = (e) => { if (e.candidate) { log('ice out'); ws.send(JSON.stringify({ t: 'sig', ice: e.candidate.toJSON() })); } };
      pc.ondatachannel = (e) => this.useChannel(e.channel);
      pc.oniceconnectionstatechange = () => log('ice ' + pc.iceConnectionState);
      return pc;
    },
    async offer(ws) {
      const pc = this.makePc(ws);
      this.useChannel(pc.createDataChannel('bt3', { ordered: false, maxRetransmits: 0 }));
      await pc.setLocalDescription(await pc.createOffer());
      ws.send(JSON.stringify({ t: 'sig', sdp: pc.localDescription.toJSON() }));
    },
    async signal(ws, m, role) {
      try {
        if (m.sdp) {
          if (!this.pc) this.makePc(ws);
          await this.pc.setRemoteDescription(m.sdp);
          if (m.sdp.type === 'offer') {
            await this.pc.setLocalDescription(await this.pc.createAnswer());
            ws.send(JSON.stringify({ t: 'sig', sdp: this.pc.localDescription.toJSON() }));
          }
          for (const c of this.pending || []) await this.pc.addIceCandidate(c).catch((e) => log('ice add: ' + e.message));
          this.pending = null;
        } else if (m.ice) {
          log('ice in'); if (this.pc && this.pc.remoteDescription) await this.pc.addIceCandidate(m.ice).catch((e) => log('ice add: ' + e.message));
          else (this.pending = this.pending || []).push(m.ice);
        }
      } catch (e) { log('signal: ' + e.message); }
    },
    useChannel(dc) {
      dc.binaryType = 'arraybuffer';
      this.dc = dc;
      dc.onopen = () => { if (this.mode !== 'relay') this.ready && this.ready('direct'); };
      if (dc.readyState === 'open') dc.onopen(); // (the side that receives the channel may get it open already)
      dc.onmessage = (e) => this.push(new Uint8Array(e.data));
      dc.onclose = () => { if (this.mode === 'direct') { this.gone = true; this.onState && this.onState('left'); } };
    },
    push(p) {
      if (this.queue.length > 1024) this.queue.shift(); // (a page that waited long: the old ones are repeated in the new)
      this.queue.push(p);
      if (window.Module && Module.netWake) Module.netWake(); // (the game waiting for this: on at once, gs/net.c)
    },
    send(p) {
      try {
        if (this.mode === 'direct' && this.dc && this.dc.readyState === 'open') this.dc.send(p);
        else if (this.mode === 'relay' && this.ws && this.ws.readyState === 1) this.ws.send(p);
      } catch (e) {}
      return p.length;
    },
    close() {
      clearInterval(this.keep);
      try { this.ws && this.ws.send(JSON.stringify({ t: 'bye' })); } catch (e) {}
      try { this.dc && this.dc.close(); } catch (e) {}
      try { this.pc && this.pc.close(); } catch (e) {}
      try { this.ws && this.ws.close(1000); } catch (e) {}
    },
  };

  // ---------------------------------------------------------------------------------------------------------------
  // The session: this page was loaded into a match (?net=host|join&room=CODE). The program's environment for it,
  // and the connection made before the program starts.
  // ---------------------------------------------------------------------------------------------------------------
  const session = Q.get('net') === 'host' || Q.get('net') === 'join' ? { role: Q.get('net'), room: (Q.get('room') || '').toUpperCase(),
    rules: Q.get('rules') || '', other: Q.get('vs') || '' } : null;

  // what the program reads at start-up (shell.html adds it to ENV)
  function sessionEnv() {
    // (the opening movie: off unless ?movie=1. It is read whole, some 120 MB, before it can play or be skipped: on a
    // phone a long wait after the logos, and much of its memory)
    if (!session) return Q.get('movie') === '1' ? {} : { BT3_NOMOVIE: '1' };
    const env = {
      BT3_NET_SESSION: '1', BT3_NET_NAME: myName(), BT3_NET_DELAY: 'auto', BT3_NOMOVIE: '1', BT3_SOUND_TICKS: '1',
      BT3_SAVES: '/net_session', BT3_UNLOCK_ALL: '0', // (the session unlocks everything itself, the same moment on both sides)
      BT3_NET_VOICE: store.get('bt3.voice', 'default'),
    };
    if (session.role === 'host') { env.BT3_NET_HOST = '1'; env.BT3_NET_RULES = session.rules || String(3 << 8); }
    else env.BT3_NET_JOIN = '127.0.0.1:1';
    return env;
  }

  // before the program starts: the other player, connected. Resolves when the game may start.
  async function sessionConnect() {
    UI.mount();
    UI.show('connect');
    Link.onState = (what, name) => {
      if (what === 'peer') UI.connectText(`Connecting to ${name || 'your opponent'}...`);
      if (what === 'left') leave('The other player left the match.');
    };
    try {
      // (an opponent who never comes, a phone locked right after a Quick Match paired it: not forever)
      const r = await Promise.race([Link.open(session.room, session.role), new Promise((ok) => setTimeout(() => ok('late'), 45000))]);
      if (r === 'late') throw new Error('Your opponent did not connect.');
    } catch (e) {
      leave(e.message);
      return new Promise(() => {}); // (the page is going)
    }
    Module.netSend = (p) => Link.send(p);
    Module.netRecv = () => Link.queue.shift();
    Module.netHas = () => Link.queue.length > 0;
    matchLog(session.room, session.role, Link.mode);
    UI.connectText(`Preparing the battle against ${Link.peerName || 'your opponent'}...`);
    try { FS.mkdir('/net_session'); } catch (e) {}
  }

  // The match log: every 5 s, how this side is doing (the game's speed, how long it waited for the other player,
  // the line's round trip...), kept by the server for a day or two (/net/stat; cloudflare/src/room.js) so that a
  // match that went slow can be looked at afterwards. Nothing personal: the room, the side, the device kind.
  function matchLog(room, role, mode) {
    const dev = /iPhone|iPad/.test(navigator.userAgent) ? (/iPad/.test(navigator.userAgent) ? 'iPad' : 'iPhone')
      : /Android/.test(navigator.userAgent) ? 'Android' : /Mac/.test(navigator.platform) ? 'Mac' : 'PC';
    const build = (document.querySelector('script[src$="bt3-async.js"]') ? 'async' : 'jspi');
    const post = (e) => { try { fetch('/net/stat', { method: 'POST', body: JSON.stringify(e), keepalive: true }).catch(() => {}); } catch (x) {} };
    post({ ev: 'start', room, role, dev, build, link: mode, w: innerWidth, h: innerHeight, dpr: devicePixelRatio });
    let lastBlanks = 0, lastT = performance.now();
    setInterval(() => {
      const s = Module.webStats || {}, ns = (i) => { try { return Module._Web_NetStat ? Module._Web_NetStat(i) : -1; } catch (e) { return -1; } };
      const lines = Module.log.filter((l) => /blanks, /.test(l)), last = lines.length ? lines[lines.length - 1] : '';
      const speed = last ? +last.split(', ')[1].split(' ')[0] : 0;
      post({ room, role, dev, build, link: Link.mode, mode: Module._Web_GameMode ? Module._Web_GameMode() : -1,
             speed, fps: Math.round(s.fps || 0), busy: Math.round((s.busy || 0) * 100), ping: ns(0), waits: ns(3), waitMs: ns(4),
             delay: ns(6), q: Link.queue.length, hidden: document.hidden ? 1 : 0, cacheMB: Math.round((Module.webCacheBytes || 0) / 1048576) });
    }, 5000);
    addEventListener('pagehide', () => post({ ev: 'end', room, role, dev, why: Link.endWhy || '' }));
  }

  // back to the game as it normally is (the session ended, or never began)
  function leave(why) {
    Link.close();
    const u = new URL(location.href);
    for (const k of ['net', 'room', 'rules', 'vs']) u.searchParams.delete(k);
    u.searchParams.set('nomovie', '1');
    if (why) u.searchParams.set('netmsg', why); else u.searchParams.delete('netmsg');
    location.replace(u.toString());
  }

  // ---------------------------------------------------------------------------------------------------------------
  // The screens. They are drawn as the game draws its menus: into a picture of the game's own page (512 x 448), in
  // the game's lettering and colours (taken from the Versus Menu), scaled up onto the picture the same way the
  // game's is, so that they are as soft as the rest. The main menu stays behind them with its background, guides,
  // badge and message window (src/menu/menu_a.c hides its plates and title words while these are open), and the
  // message window shows their text in the game's own type (Web_NetUiSet). Driven by the controller, the keyboard,
  // the on-screen pad and taps; the room code and the name can be typed (computer keyboard, or the phone's).
  // ---------------------------------------------------------------------------------------------------------------
  const BATTLES = ['Single Battle', 'Team Battle', 'DP Battle 10', 'DP Battle 15', 'DP Battle 20'];
  const TIMES = ['60 Seconds', '90 Seconds', '180 Seconds', '240 Seconds', 'Infinite'];
  const rulesWord = (b, t) => String((b === 0 ? 0 : b === 1 ? 1 : 2) | (b >= 2 ? b - 2 : 0) << 4 | t << 8);
  const se = (id) => { try { Module._Web_MenuSe && Module._Web_MenuSe(id); } catch (e) {} };
  const PW = 512, PH = 448;               // the game's page
  const FONT = '"M PLUS Rounded 1c", "Arial Rounded MT Bold", sans-serif';
  // the Versus Menu's measures, in page pixels
  const BAR = { top: 104, pitch: 47, h: 31, right: 354, text: 48, val: 284 };

  // the game's message window: its text, in its own type (src/menu/menu_a.c, port/src/headless.c)
  let lastMsg = null;
  function gameMsg(on, text) {
    try {
      if (!Module._Web_NetUiSet) return false;
      if (text == null || text === lastMsg) { Module._Web_NetUiSet(on ? 1 : 0, 0); return true; }
      const buf = Module._Web_NetUiBuf(), t = text.slice(0, 120);
      for (let i = 0; i < t.length; i++) { const c = t.charCodeAt(i); HEAPU8[buf + i] = c < 128 ? c : 63; }
      HEAPU8[buf + t.length] = 0;
      Module._Web_NetUiSet(on ? 1 : 0, buf);
      lastMsg = text;
      return true;
    } catch (e) { return false; }
  }

  // lettering: the menu plates' (light grey in purple, or orange in dark brown when chosen) and the titles'
  // (yellow to red, a dark edge and a cream rim)
  function letters(cx, text, x, y, size, kind, align) {
    cx.save();
    cx.font = `900 ${size}px ${FONT}`;
    cx.textBaseline = 'alphabetic';
    cx.textAlign = align || 'left';
    cx.lineJoin = 'round';
    cx.miterLimit = 2;
    const sx = 1.08; // (the game's letters are wider on its page than they look on screen: its pixels are not square)
    cx.translate(x, y);
    cx.scale(sx, 1);
    const top = -size * 0.74, bot = size * 0.04;
    if (kind === 'title' || kind === 'code') {
      cx.lineWidth = size * 0.38; cx.strokeStyle = '#efe7d6'; cx.strokeText(text, 0, 0);                    // cream rim
      cx.lineWidth = size * 0.24; cx.strokeStyle = '#3d1109'; cx.strokeText(text, 0, 0);                     // dark edge
      const g = cx.createLinearGradient(0, top, 0, bot);
      g.addColorStop(0, '#f8b347'); g.addColorStop(0.3, '#fe9a2e'); g.addColorStop(0.62, '#fd5626'); g.addColorStop(1, '#c42a1d');
      cx.fillStyle = g; cx.fillText(text, 0, 0);
    } else if (kind === 'sel') {
      cx.lineWidth = size * 0.28; cx.strokeStyle = '#2d1612'; cx.strokeText(text, 0, 0);
      const g = cx.createLinearGradient(0, top, 0, bot);
      g.addColorStop(0, '#f2b47c'); g.addColorStop(0.5, '#de9761'); g.addColorStop(1, '#c76f45');
      cx.fillStyle = g; cx.fillText(text, 0, 0);
    } else if (kind === 'value' || kind === 'valsel') {
      cx.lineWidth = size * 0.22; cx.strokeStyle = kind === 'valsel' ? '#2d1612' : '#46015a'; cx.strokeText(text, 0, 0);
      cx.fillStyle = kind === 'valsel' ? '#f6efe0' : '#d2d0d6'; cx.fillText(text, 0, 0);
    } else {
      cx.save(); cx.translate(0, size * 0.1); cx.lineWidth = size * 0.24; cx.strokeStyle = 'rgba(8,60,70,.55)'; cx.strokeText(text, 0, 0); cx.restore();
      cx.lineWidth = size * 0.27; cx.strokeStyle = '#46015a'; cx.strokeText(text, 0, 0);
      cx.fillStyle = '#d6d5da'; cx.fillText(text, 0, 0);
    }
    const w = cx.measureText(text).width * sx;
    cx.restore();
    return w;
  }

  // a plate: teal with a light rim above and a dark one below, a rounded right end; the chosen one pale yellow
  function plate(cx, y, sel, right) {
    const h = BAR.h, r = h / 2, x1 = right || BAR.right;
    const path = () => { cx.beginPath(); cx.moveTo(-4, y); cx.lineTo(x1 - r, y); cx.arc(x1 - r, y + r, r, -Math.PI / 2, Math.PI / 2); cx.lineTo(-4, y + h); cx.closePath(); };
    cx.save();
    if (sel) {
      cx.shadowColor = 'rgba(255,250,150,.85)'; cx.shadowBlur = 7;
      path(); cx.fillStyle = '#e6d862'; cx.fill();
      cx.shadowBlur = 0;
      const g = cx.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, '#e8d564'); g.addColorStop(0.08, '#f9f6dc'); g.addColorStop(0.2, '#c6e0aa'); g.addColorStop(0.45, '#d3dd8c');
      g.addColorStop(0.56, '#d8d838'); g.addColorStop(0.86, '#d8d84a'); g.addColorStop(0.92, '#f8f8e6'); g.addColorStop(1, '#c9b851');
      path(); cx.fillStyle = g; cx.fill();
    } else {
      const g = cx.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, '#bcc4ce'); g.addColorStop(0.07, '#98b7bb'); g.addColorStop(0.16, '#2d7580'); g.addColorStop(0.84, '#2d737f');
      g.addColorStop(0.92, '#1e4e57'); g.addColorStop(1, '#343b3d');
      path(); cx.fillStyle = g; cx.fill();
      cx.lineWidth = 1; cx.strokeStyle = 'rgba(20,40,44,.7)'; cx.beginPath();
      cx.moveTo(x1 - r, y + 0.5); cx.arc(x1 - r, y + r, r - 0.5, -Math.PI / 2, Math.PI / 2); cx.stroke();
    }
    cx.restore();
  }

  // the menus' little orange arrows (as the main menu's ^ and v), pointing left or right, up or down
  function arrow(cx, x, y, dir, dim) {
    cx.save();
    cx.translate(x, y);
    cx.rotate({ left: Math.PI, right: 0, up: -Math.PI / 2, down: Math.PI / 2 }[dir]);
    cx.globalAlpha = dim ? 0.55 : 1;
    cx.beginPath(); cx.moveTo(-3, -6); cx.lineTo(4, 0); cx.lineTo(-3, 6);
    cx.lineJoin = 'round'; cx.lineCap = 'round';
    cx.lineWidth = 6.5; cx.strokeStyle = '#4a1c08'; cx.stroke();
    cx.lineWidth = 3.5; const g = cx.createLinearGradient(0, -6, 0, 6); g.addColorStop(0, '#ffc25a'); g.addColorStop(1, '#f07818');
    cx.strokeStyle = g; cx.stroke();
    cx.restore();
  }

  // the title's badge, in the place and look of the game's (a round picture in a black rim): a Dragon Radar. On the
  // page a circle on the screen is an ellipse (the page's pixels are wider than tall)
  function badge(cx) {
    cx.save();
    cx.translate(39, 42);
    cx.scale(1, 1.17);
    const R = 27;
    cx.beginPath(); cx.arc(0, 0, R, 0, Math.PI * 2); cx.fillStyle = '#141414'; cx.fill();
    cx.beginPath(); cx.arc(0, 0, R - 2.2, 0, Math.PI * 2);
    let g = cx.createLinearGradient(0, -R, 0, R); g.addColorStop(0, '#f1f0ec'); g.addColorStop(1, '#a9adb3');
    cx.fillStyle = g; cx.fill();
    cx.beginPath(); cx.arc(0, 0, R - 6.5, 0, Math.PI * 2); cx.fillStyle = '#2b3a2a'; cx.fill();
    cx.beginPath(); cx.arc(0, 0, R - 7.5, 0, Math.PI * 2);
    g = cx.createRadialGradient(-4, -5, 1, 0, 0, R - 7); g.addColorStop(0, '#b8f08a'); g.addColorStop(0.55, '#62c24a'); g.addColorStop(1, '#2c7d2a');
    cx.fillStyle = g; cx.fill();
    cx.save(); cx.clip();
    cx.strokeStyle = 'rgba(20,70,20,.55)'; cx.lineWidth = 0.8;
    for (let k = -2; k <= 2; k++) { cx.beginPath(); cx.moveTo(k * 6, -R); cx.lineTo(k * 6, R); cx.moveTo(-R, k * 6); cx.lineTo(R, k * 6); cx.stroke(); }
    const blip = (x, y, r) => { cx.beginPath(); cx.arc(x, y, r, 0, Math.PI * 2); cx.fillStyle = '#ffd23a'; cx.fill(); cx.lineWidth = 0.8; cx.strokeStyle = '#a3560a'; cx.stroke(); };
    blip(5, -6, 2.6); blip(-7, 5, 2.2);
    cx.beginPath(); cx.moveTo(0, -1.5); cx.lineTo(1.5, 1.5); cx.lineTo(-1.5, 1.5); cx.closePath(); cx.fillStyle = '#d0201c'; cx.fill();
    cx.restore();
    cx.beginPath(); cx.ellipse(-6, -9, 9, 5, -0.5, 0, Math.PI * 2); cx.fillStyle = 'rgba(255,255,255,.28)'; cx.fill();
    cx.beginPath(); cx.arc(0, -R + 1.2, 2.6, 0, Math.PI * 2); cx.fillStyle = '#d9d9d9'; cx.fill(); cx.lineWidth = 1; cx.strokeStyle = '#141414'; cx.stroke();
    cx.restore();
    // the line the title stands on
    const l = cx.createLinearGradient(62, 0, 470, 0);
    l.addColorStop(0, 'rgba(232,240,250,.95)'); l.addColorStop(0.7, 'rgba(232,240,250,.8)'); l.addColorStop(1, 'rgba(232,240,250,0)');
    cx.fillStyle = l; cx.fillRect(62, 54, 420, 1.6);
  }

  const UI = {
    cv: null, cx: null, screen: '', cur: 0, items: [], ws: null, code: '', peer: '',
    battle: +store.get('bt3.netBattle', 0), time: +store.get('bt3.netTime', 3),
    entry: ['', '', '', ''], slot: 0, opened: false, naming: false, nameDraft: '', wantKeyboard: null, msg: '', t0: 0,

    mount() {
      if (this.cv) return;
      const cv = document.createElement('canvas');
      cv.id = 'netcv';
      cv.width = PW; cv.height = PH;
      document.body.appendChild(cv);
      this.cv = cv;
      this.cx = cv.getContext('2d');
      // the typing fields: over the room code and the name, see-through (the letters are drawn on the picture);
      // a tap on them brings up a phone's keyboard
      const mk = (id, max, cap) => {
        const i = document.createElement('input');
        i.id = id; i.className = 'nb-type'; i.maxLength = max; i.autocomplete = 'off'; i.spellcheck = false;
        i.setAttribute('autocapitalize', cap); i.setAttribute('autocorrect', 'off'); i.enterKeyHint = 'go';
        document.body.appendChild(i);
        return i;
      };
      this.codeIn = mk('nb-code', 4, 'characters');
      this.nameIn = mk('nb-name', 16, 'words');
      this.codeIn.addEventListener('input', () => this.typedCode());
      this.nameIn.addEventListener('input', () => { this.nameDraft = this.nameIn.value.slice(0, 16); this.draw(); });
      for (const i of [this.codeIn, this.nameIn]) {
        i.addEventListener('keydown', (e) => {
          e.stopPropagation();
          const k = { Enter: 'ok', Escape: 'back', ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }[e.key];
          if (i === this.codeIn && k) { e.preventDefault(); this.act(k, true); }
          if (i === this.nameIn && (k === 'ok' || k === 'back')) { e.preventDefault(); this.endName(k === 'ok'); }
        });
      }
      this.nameIn.addEventListener('blur', () => { if (this.naming) this.endName(true); });
      cv.addEventListener('pointerdown', (e) => this.tap(e));
      // a phone's keyboard opens only from a touch: when a pad press asked for it, the end of that touch focuses
      addEventListener('touchend', () => {
        if (this.wantKeyboard) { const el = this.wantKeyboard; this.wantKeyboard = null; el.focus({ preventScroll: true }); }
      }, true);
      this.fit();
      addEventListener('resize', () => this.fit());
      if (window.visualViewport) visualViewport.addEventListener('resize', () => this.fit());
      Input.start();
      const tick = () => { requestAnimationFrame(tick); if (this.screen && this.screen !== 'toast' && this.cv.classList.contains('on')) this.draw(); };
      requestAnimationFrame(tick);
    },
    // the game's picture: 4:3 inside the canvas (gs_gl.c draws it centred)
    fit() {
      const c = document.getElementById('canvas').getBoundingClientRect();
      let w = c.width, h = c.height;
      if (w / h > 4 / 3) w = h * 4 / 3; else h = w * 3 / 4;
      const r = this.rect = { x: c.left + (c.width - w) / 2, y: c.top + (c.height - h) / 2, w, h };
      Object.assign(this.cv.style, { left: r.x + 'px', top: r.y + 'px', width: w + 'px', height: h + 'px' });
      this.place();
    },
    // page pixels to the window's
    toWin(x, y) { return { x: this.rect.x + x * this.rect.w / PW, y: this.rect.y + y * this.rect.h / PH }; },
    place() {
      const at = (el, x, y, w, h, on) => {
        const a = this.toWin(x, y), b = this.toWin(x + w, y + h);
        Object.assign(el.style, { left: a.x + 'px', top: a.y + 'px', width: (b.x - a.x) + 'px', height: (b.y - a.y) + 'px', display: on ? 'block' : 'none' });
      };
      if (!this.codeIn) return;
      at(this.codeIn, 220, BAR.top - 4, 130, BAR.h + 8, this.screen === 'join');
      at(this.nameIn, 200, BAR.top + 3 * BAR.pitch, 140, BAR.h, this.screen === 'menu' && this.naming);
    },
    say(t) {
      this.msg = t;
      if (this.screen !== 'connect') gameMsg(true, t);
    },
    open() {
      this.mount();
      this.opened = true;
      document.body.classList.add('netui-on');
      this.show('menu');
    },
    close() {
      this.opened = false;
      if (this.ws) { try { this.ws.close(1000); } catch (e) {} this.ws = null; }
      this.screen = '';
      for (const i of [this.codeIn, this.nameIn]) { i.blur(); i.style.display = 'none'; }
      document.body.classList.remove('netui-on');
      this.cv.classList.remove('on');
      gameMsg(false, null);
      lastMsg = null;
      try { Module._Web_NetMenuClosed(); } catch (e) {}
    },

    show(name) {
      this.screen = name;
      this.cv.classList.add('on');
      this.cv.classList.remove('toast');
      this.cur = 0;
      this.t0 = performance.now();
      clearInterval(this.dotTimer);
      this.root && this.root.classList.remove('nb-found');
      if (name === 'menu') {
        this.title = 'Dragon Net Battle';
        this.items = [
          { label: 'Quick Match', help: 'Fight whoever is searching right now.', act: () => this.needName(() => this.quick()) },
          { label: 'Host a Match', help: 'Open a room for your opponent to join.', act: () => this.needName(() => this.host()) },
          { label: 'Join a Match', help: "Enter your opponent's room code.", act: () => this.needName(() => this.show('join')) },
          { label: 'Player Name', value: () => this.naming ? this.nameDraft + (Math.floor(performance.now() / 400) % 2 ? '_' : ' ') : named() ? myName() : 'Not Set',
            help: 'The name shown under your gauges.', act: () => this.startName() },
        ];
      } else if (name === 'join') {
        this.title = 'Join a Match';
        this.entry = ['', '', '', ''];
        this.slot = 0;
        this.found = false;
        this.items = [{ label: 'Room Code', code: true }, { label: 'Enter the Room', help: '', act: () => this.join() }];
        this.codeIn.value = '';
        this.say('Type the room code, or use the D-pad.');
        // a keyboard at once: a computer's now; a phone's when this touch ends (or a tap on the code)
        if (!coarse()) setTimeout(() => this.codeIn.focus({ preventScroll: true }), 30);
        else this.wantKeyboard = this.codeIn;
      } else if (name === 'host') {
        this.title = 'Host a Match';
      } else if (name === 'connect') {
        this.title = 'Dragon Net Battle';
        this.items = [];
      }
      this.place();
      this.paint();
    },
    paint() {
      const it = this.items[this.cur];
      if (it && it.help) this.say(it.help);
      this.draw();
    },

    draw() {
      const cx = this.cx;
      if (!cx) return;
      cx.setTransform(1, 0, 0, 1, 0, 0);
      cx.clearRect(0, 0, PW, PH);
      if (this.screen === 'connect') {
        cx.fillStyle = '#000'; cx.fillRect(0, 0, PW, PH);
        this.drawBox(cx, this.msg);
      }
      if (!this.screen) return;
      if (this.screen === 'toast') { this.drawBox(cx, this.msg); return; }
      badge(cx);
      letters(cx, this.title, 68, 45, 31, 'title');
      if (this.screen === 'connect') {
        // a dragon ball turning while the two find each other
        const a = (performance.now() - this.t0) / 260;
        cx.save(); cx.translate(PW / 2, 190); cx.rotate(a);
        const g = cx.createRadialGradient(-9, -11, 2, 0, 0, 34); g.addColorStop(0, '#fff8d6'); g.addColorStop(0.2, '#ffd257'); g.addColorStop(0.62, '#ff951a'); g.addColorStop(1, '#c95104');
        cx.beginPath(); cx.arc(0, 0, 32, 0, Math.PI * 2); cx.fillStyle = g; cx.fill();
        cx.fillStyle = '#e3241b'; cx.font = `16px ${FONT}`; cx.textAlign = 'center';
        cx.fillText('★', -8, -2); cx.fillText('★', 8, -2); cx.fillText('★', -8, 14); cx.fillText('★', 8, 14);
        cx.restore();
        return;
      }
      this.items.forEach((it, i) => {
        const y = BAR.top + i * BAR.pitch, sel = i === this.cur;
        plate(cx, y, sel);
        const base = y + BAR.h / 2 + 8;
        letters(cx, it.label, BAR.text, base + 1, 25, sel ? 'sel' : 'plate');
        if (it.code) this.drawCode(cx, y, sel);
        if (it.show) it.show.split('').forEach((ch, k) => letters(cx, ch, 240 + k * 29, y + BAR.h / 2 + 11, 28, 'code', 'center'));
        const v = typeof it.value === 'function' ? it.value() : it.value;
        if (v !== undefined) {
          const vx = BAR.val;
          if (it.left) { arrow(cx, vx - 64, y + BAR.h / 2, 'left', !sel); arrow(cx, vx + 64, y + BAR.h / 2, 'right', !sel); }
          letters(cx, v, vx, base - 1, 15, sel ? 'valsel' : 'value', 'center');
        }
      });
    },
    drawCode(cx, y, sel) {
      const x0 = 240, step = 29, mid = y + BAR.h / 2;
      for (let i = 0; i < 4; i++) {
        const x = x0 + i * step, ch = this.entry[i];
        const on = sel && i === this.slot;
        if (ch) letters(cx, ch, x, mid + 11, 28, 'code', 'center');
        else { cx.save(); cx.fillStyle = on ? '#fff3b0' : 'rgba(225,225,230,.8)'; cx.strokeStyle = '#46015a'; cx.lineWidth = 2;
          cx.beginPath(); cx.rect(x - 8, mid + 5, 16, 4); cx.stroke(); cx.fill(); cx.restore(); }
        if (on && Math.floor((performance.now() - this.t0) / 450) % 2 === 0) { arrow(cx, x, y - 4, 'up'); arrow(cx, x, y + BAR.h + 4, 'down'); }
      }
    },
    // a message box like the game's (for the moments it is not there: before the game has started)
    drawBox(cx, text) {
      const y = 327;
      cx.save();
      const g = cx.createLinearGradient(0, y, 0, PH); g.addColorStop(0, 'rgba(27,94,126,.92)'); g.addColorStop(1, 'rgba(14,89,113,.95)');
      cx.fillStyle = g; cx.fillRect(0, y, PW, PH - y);
      cx.strokeStyle = '#dff4f6'; cx.lineWidth = 1.5;
      cx.beginPath(); cx.moveTo(0, y + 0.5); cx.lineTo(PW, y + 0.5); cx.stroke();
      cx.beginPath(); cx.moveTo(4, y - 6); cx.lineTo(4, y); cx.moveTo(4, y - 6); cx.lineTo(14, y - 6); cx.moveTo(PW - 4, y - 6); cx.lineTo(PW - 4, y); cx.moveTo(PW - 4, y - 6); cx.lineTo(PW - 14, y - 6); cx.stroke();
      cx.font = `700 13px ${FONT}`; cx.fillStyle = '#fff'; cx.shadowColor = 'rgba(0,0,0,.6)'; cx.shadowOffsetY = 1; cx.shadowBlur = 1;
      cx.save(); cx.scale(1.08, 1); cx.fillText(text || '', 26 / 1.08, y + 54); cx.restore();
      cx.restore();
    },

    tap(e) {
      if (!this.opened || this.screen === 'connect') return;
      e.preventDefault();
      const r = this.cv.getBoundingClientRect();
      const x = (e.clientX - r.left) * PW / r.width, y = (e.clientY - r.top) * PH / r.height;
      const i = Math.floor((y - BAR.top) / BAR.pitch);
      if (i < 0 || i >= this.items.length || y - BAR.top - i * BAR.pitch > BAR.h || x > BAR.right + 4) return;
      const it = this.items[i];
      if (it.left && Math.abs(x - (BAR.val - 64)) < 14) { this.cur = i; this.act('left'); return; }
      if (it.left && Math.abs(x - (BAR.val + 64)) < 14) { this.cur = i; this.act('right'); return; }
      if (it.fixed) return;
      if (i !== this.cur) { this.cur = i; se(0); this.paint(); }
      else if (!it.code) this.act('ok');
    },

    // a match needs a name: the first time, the name is asked for first, then the match goes on
    needName(then) {
      if (named()) { then(); return; }
      this.afterName = then;
      this.cur = 3;
      this.startName();
      this.say('First, enter your player name.');
    },
    startName() {
      se(1);
      this.naming = true;
      this.nameDraft = named() ? myName() : '';
      this.nameIn.value = this.nameDraft;
      this.place();
      this.say('Type your name, then press Enter.');
      if (!coarse()) setTimeout(() => { this.nameIn.focus({ preventScroll: true }); this.nameIn.select(); }, 30);
      else this.wantKeyboard = this.nameIn;
    },
    endName(keep) {
      if (!this.naming) return;
      const v = this.nameIn.value.trim().slice(0, 16);
      if (keep && !v && this.afterName) { se(7); this.say('Please enter a name.'); return; } // (a match needs one)
      this.naming = false;
      if (keep && v) store.set('bt3.name', v);
      se(keep ? 1 : 2);
      this.nameIn.blur();
      this.place();
      this.paint();
      const then = this.afterName;
      this.afterName = null;
      if (keep && v && then) setTimeout(then, 250);
    },

    typedCode() {
      const v = this.codeIn.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 4);
      if (this.codeIn.value !== v) this.codeIn.value = v;
      this.entry = [0, 1, 2, 3].map((i) => v[i] || '');
      this.slot = Math.min(v.length, 3);
      this.cur = 0;
      se(0);
      this.draw();
      if (v.length === 4) setTimeout(() => this.join(), 120);
    },

    // Quick Match: wait in the queue (cloudflare/src/room.js) until another player searches too; the server gives
    // both a room and a side, and both pages load themselves into it as after Host / Join
    quick() {
      se(1);
      this.show('quick');
      this.title = 'Quick Match';
      this.searching = 0;
      const t0 = performance.now();
      const clock = () => { const s = Math.floor((performance.now() - t0) / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
      this.items = [
        { label: 'Searching', value: clock, fixed: true },
        { label: 'Rules', value: () => 'Single Battle', fixed: true },
        { label: 'Cancel', help: '', act: () => this.quitQuick() },
      ];
      this.cur = 2;
      this.say('Looking for an opponent...');
      const ws = this.ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/net/queue?name=${encodeURIComponent(myName())}&cid=${cid}`);
      const keep = setInterval(() => { try { ws.send('ping'); } catch (e) {} }, 15000);
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.t === 'count' && !this.peer) {
          this.say(m.n > 1 ? `Looking for an opponent... (${m.n} searching)` : 'Looking for an opponent...');
        } else if (m.t === 'match') {
          this.peer = m.vs || 'Player';
          clearInterval(keep);
          se(1);
          this.say(`Opponent found: ${this.peer}! Get ready...`);
          setTimeout(() => go(m.role, m.room, m.rules, this.peer), 1500);
        }
      };
      ws.onclose = (e) => {
        clearInterval(keep);
        if (this.ws === ws && this.screen === 'quick' && !this.peer && e.code !== 1000) this.say('Lost the connection. Press Cancel and try again.');
      };
      this.peer = '';
    },
    quitQuick() {
      se(2);
      if (this.ws) { try { this.ws.close(1000); } catch (e) {} this.ws = null; }
      this.show('menu');
      this.cur = 0;
      this.paint();
    },

    // Host: a room of our own, its code, the rules, and waiting for the opponent
    host(again) {
      se(1);
      this.show('host');
      this.code = again ? this.code : newCode();
      this.items = [
        { label: 'Room Code', show: this.code, fixed: true },
        { label: 'Battle', value: () => BATTLES[this.battle], help: 'Your rules apply to both players.',
          left: () => { this.battle = (this.battle + 4) % 5; }, right: () => { this.battle = (this.battle + 1) % 5; } },
        { label: 'Time Limit', value: () => TIMES[this.time], help: 'The time limit of each battle.',
          left: () => { this.time = (this.time + 4) % 5; }, right: () => { this.time = (this.time + 1) % 5; } },
      ];
      this.cur = 1;
      this.say('Waiting for your opponent...');
      this.draw();
      this.hostWait(this.code);
    },
    hostWait(code) {
      this.peer = '';
      const ws = this.ws = new WebSocket(wsUrl(code, 'host', 'lobby'));
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.t === 'taken') { this.ws = null; this.code = newCode(); this.host(true); return; }
        if (m.t === 'peer') {
          this.peer = m.name || 'Player';
          se(1);
          this.say(`${this.peer} is here! Get ready...`);
          const rules = rulesWord(this.battle, this.time);
          setTimeout(() => {
            try { ws.send(JSON.stringify({ t: 'go', rules, name: myName() })); } catch (e) {}
            go('host', code, rules, this.peer);
          }, 1800);
        }
        if (m.t === 'left') { this.peer = ''; this.say('Waiting for your opponent...'); }
      };
      ws.onclose = () => { if (this.ws === ws && this.screen === 'host' && !this.peer) this.say('The room was lost. Please try again.'); };
    },

    join() {
      const code = this.entry.join('');
      if (code.length !== 4) { se(7); this.say('A room code has four letters.'); return; }
      if (this.ws) { try { this.ws.close(1000); } catch (e) {} }
      this.codeIn.blur();
      se(1);
      this.say(`Looking for room ${code}...`);
      const ws = this.ws = new WebSocket(wsUrl(code, 'join', 'lobby'));
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.t === 'nohost') { se(7); this.say(`There is no room ${code}.`); this.ws = null; }
        else if (m.t === 'full') { se(7); this.say(`Room ${code} is full.`); this.ws = null; }
        else if (m.t === 'peer') { this.peer = m.name || 'Player'; this.say('Room found! Get ready...'); }
        else if (m.t === 'go') go('join', code, m.rules, m.name || this.peer);
        else if (m.t === 'left') this.say('The host closed the room.');
      };
      ws.onclose = (e) => { if (this.ws === ws && e.code !== 1000 && !this.peer) this.say('Could not reach the room. Try again.'); };
    },

    // one input: up down left right ok back; a letter (typing on the join screen)
    act(k, fromField) {
      if (!this.opened || this.screen === 'connect' || (this.naming && !fromField)) return;
      if (this.screen === 'join' && this.cur === 0) {
        const ch = this.entry[this.slot];
        if (k === 'up' || k === 'down') {
          const d = k === 'up' ? 1 : -1, n = LETTERS.length;
          this.entry[this.slot] = LETTERS[((ch ? LETTERS.indexOf(ch) : d > 0 ? -1 : 0) + d + n) % n];
          se(0);
        } else if (k === 'left') { if (this.slot > 0) { this.slot--; se(0); } }
        else if (k === 'right') { if (this.slot < 3) { this.slot++; se(0); } }
        else if (k === 'ok') {
          if (!this.entry[this.slot]) this.entry[this.slot] = 'A';
          if (this.entry.every(Boolean)) this.join(); else if (this.slot < 3) { this.slot++; se(0); }
        } else if (k === 'back') {
          if (this.ws) { try { this.ws.close(1000); } catch (e) {} this.ws = null; }
          se(2); this.codeIn.blur(); this.show('menu'); this.cur = 2; this.paint(); return;
        }
        this.codeIn.value = this.entry.join('');
        this.draw();
        return;
      }
      const it = this.items[this.cur];
      if (k === 'up' || k === 'down') {
        do { this.cur = (this.cur + (k === 'up' ? this.items.length - 1 : 1)) % this.items.length; } while (this.items[this.cur].fixed);
        se(0);
        this.paint();
      } else if ((k === 'left' || k === 'right') && it && it[k]) {
        it[k]();
        se(0);
        this.paint();
        store.set('bt3.netBattle', this.battle);
        store.set('bt3.netTime', this.time);
      } else if (k === 'ok' && it) {
        if (it.act) it.act(); else if (it.right) { it.right(); se(0); this.paint(); }
      } else if (k === 'back') {
        if (this.screen === 'menu') { se(2); this.close(); }
        else if (this.screen === 'host') { se(2); this.ws && this.ws.close(1000); this.ws = null; this.show('menu'); this.cur = 1; this.paint(); }
        else if (this.screen === 'join') { se(2); this.show('menu'); this.cur = 2; this.paint(); }
        else if (this.screen === 'quick') this.quitQuick();
      }
    },
    connectText(t) { this.msg = t; this.draw(); },
    // after a match: why it ended, in a box of the game's message window's look over the start-up, for a while
    toast(t) {
      this.mount();
      this.screen = 'toast';
      this.msg = t;
      this.cv.classList.add('on', 'toast');
      this.draw();
      setTimeout(() => { if (this.screen === 'toast') { this.screen = ''; this.cv.classList.remove('on', 'toast'); this.draw(); } }, 6500);
    },
  };
  const coarse = () => matchMedia('(pointer: coarse)').matches || navigator.maxTouchPoints > 1;

  // both in the room: this page loads itself into the session
  function go(role, room, rules, vs) {
    const u = new URL(location.href);
    u.searchParams.set('net', role);
    u.searchParams.set('room', room);
    if (role === 'host') u.searchParams.set('rules', rules); else u.searchParams.delete('rules');
    u.searchParams.set('vs', vs || '');
    for (const k of ['netmsg', 'nomovie']) u.searchParams.delete(k);
    setTimeout(() => location.replace(u.toString()), role === 'join' ? 150 : 50);
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Input for the screens: controllers (standard layout), the keyboard, the on-screen pad (shell.html's Touch).
  // ---------------------------------------------------------------------------------------------------------------
  const Input = {
    held: {}, timer: 0, fresh: true,
    start() {
      if (this.timer) return;
      addEventListener('keydown', (e) => {
        if (!UI.opened || e.target.tagName === 'INPUT') return;
        // typing a room code: letters go to it, from anywhere on the join screen
        if (UI.screen === 'join' && /^[a-zA-Z]$/.test(e.key) && !e.metaKey && !e.ctrlKey) {
          e.preventDefault(); e.stopPropagation();
          UI.codeIn.value = (UI.entry.join('').slice(0, UI.slot) + e.key).toUpperCase();
          UI.typedCode();
          return;
        }
        if (UI.screen === 'join' && e.key === 'Backspace') {
          e.preventDefault(); e.stopPropagation();
          const v = UI.entry.join('');
          UI.codeIn.value = v.slice(0, -1);
          UI.typedCode();
          return;
        }
        const k = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'ok', k: 'ok', K: 'ok', ' ': 'ok',
                    Escape: 'back', Backspace: 'back', l: 'back', L: 'back', i: 'back', I: 'back' }[e.key];
        if (!k) return;
        e.preventDefault();
        e.stopPropagation();
        UI.act(k);
      }, true);
      const loop = () => {
        this.timer = requestAnimationFrame(loop);
        if (!UI.opened) { this.held = {}; this.fresh = true; if (window.BT3Touch) BT3Touch.latch = 0; return; }
        const now = performance.now(), want = {};
        for (const g of (navigator.getGamepads ? navigator.getGamepads() : [])) {
          if (!g || !g.connected) continue;
          const b = (i) => g.buttons[i] && g.buttons[i].pressed;
          const ax = g.axes[0] || 0, ay = g.axes[1] || 0;
          if (b(12) || ay < -0.6) want.up = 1;
          if (b(13) || ay > 0.6) want.down = 1;
          if (b(14) || ax < -0.6) want.left = 1;
          if (b(15) || ax > 0.6) want.right = 1;
          if (b(0) || b(9)) want.ok = 1;
          if (b(1) || b(3)) want.back = 1; // (the game's own back is Triangle)
        }
        const T = window.BT3Touch, t = T ? T.bits | (T.latch || 0) : 0;
        if (T) T.latch = 0;
        if (t & 0x10) want.up = 1;
        if (t & 0x40) want.down = 1;
        if (t & 0x80) want.left = 1;
        if (t & 0x20) want.right = 1;
        if (t & 0x4008) want.ok = 1;
        if (t & 0x3000) want.back = 1;
        if (this.fresh) { // (just opened: what is down now was pressed for the main menu; it acts once let go)
          this.fresh = false;
          for (const k in want) this.held[k] = { at: now, next: Infinity };
          return;
        }
        for (const k of ['up', 'down', 'left', 'right', 'ok', 'back']) {
          const h = this.held[k];
          if (!want[k]) { delete this.held[k]; continue; }
          if (!h) { this.held[k] = { at: now, next: now + 380 }; UI.act(k); }
          else if (k !== 'ok' && k !== 'back' && now >= h.next) { h.next = now + 110; UI.act(k); }
        }
      };
      this.timer = requestAnimationFrame(loop);
    },
  };

  // ---------------------------------------------------------------------------------------------------------------
  // What shell.html calls
  // ---------------------------------------------------------------------------------------------------------------
  window.BT3Net = {
    link: Link,
    ui: UI,
    session,
    sessionEnv,
    async beforeStart() {
      if (session) await sessionConnect();
    },
    afterStart() {
      const msg = Q.get('netmsg');
      if (msg) {
        UI.mount();
        UI.toast(msg);
        const u = new URL(location.href);
        u.searchParams.delete('netmsg');
        history.replaceState(null, '', u.toString());
      }
    },
  };

  // the program's side (gs/net.c, ui.cpp)
  window.addEventListener('DOMContentLoaded', () => {
    if (document.fonts) for (const w of ['900', '700']) document.fonts.load(`${w} 24px "M PLUS Rounded 1c"`).catch(() => {});
    Module.onNetMenu = () => {
      UI.open();
    };
    Module.onNetEvent = (what, text) => {
      log(`${what} ${text}`);
      if (what === 'arrived') { if (UI.cv) { UI.screen = ''; UI.cv.classList.remove('on'); document.body.classList.remove('netui-on'); } }
      else if (what === 'ended') { Link.endWhy = text; }
      else if (what === 'leave') leave(Link.endWhy || '');
    };
  });
})();
