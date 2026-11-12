'use strict';
// Buddy Brain: standalone talk app. One dependency: ws (WebSocket server).
// ONE AI (Chris, Nov 11 5:37 AM PT): Meta Muse writes every reply, streamed sentence
// by sentence. NO OpenAI, no cloud speech. Phone-call build (6:12 AM PT): the mic opens
// once and streams over one WebSocket (/ws, see call.js); local VAD + faster-whisper on
// the Dell (asr.py) hears; the voice is a free Microsoft Edge neural voice (edge-tts in
// ./.venv), one MP3 per sentence back down the same socket. Patterned on Splendor's shared
// pipeline hand-off (routes/converse.js /respond-stream) but calling Muse directly
// with Buddy's persona: no Splendor brain, memory, CLASPION or Supabase.
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const persona = require('./persona');
const { userContent } = require('./vision_message');

const E = process.env;
const PORT = Number(E.BUDDY_PORT || E.PORT || 8820);
const HOST = E.BUDDY_HOST || '127.0.0.1';
const MUSE_BASE = (E.BUDDY_MUSE_BASE || 'https://api.meta.ai/v1').replace(/\/+$/, '');
const MUSE_MODEL = (E.BUDDY_MUSE_MODEL || 'muse-spark-1.3').trim();
const MUSE_EFFORT = (E.BUDDY_MUSE_EFFORT || 'minimal').trim();
const MUSE_MAX_TOKENS = Number(E.BUDDY_MUSE_MAX_TOKENS || 400);
const MAX_REPLIES_PER_HOUR = Number(E.BUDDY_MAX_REPLIES_PER_HOUR || 400);
const TTS_VOICES = (E.BUDDY_TTS_VOICES || 'en-US-GuyNeural,en-US-ChristopherNeural').split(',').map(v => v.trim()).filter(Boolean);
const TTS_RATE = (E.BUDDY_TTS_RATE || '+5%').trim();
const TTS_PITCH = (E.BUDDY_TTS_PITCH || '+0Hz').trim();
const TTS_PY = E.BUDDY_TTS_PYTHON || path.join(__dirname, '.venv', 'bin', 'python');
const MAX_TTS_PER_HOUR = Number(E.BUDDY_MAX_TTS_PER_HOUR || 1500);
const SESSION_MAX_MIN = Number(E.BUDDY_SESSION_MAX_MIN || 20);
const ASR_PY = E.BUDDY_ASR_PYTHON || TTS_PY;
const ASR_SCRIPT = E.BUDDY_ASR_SCRIPT || path.join(__dirname, 'asr.py');
const COOKIE_DAYS = Number(E.BUDDY_COOKIE_DAYS || 14);
const PASS_HASH = (E.BUDDY_PASS_HASH || '').trim();         // scrypt$N$r$p$saltB64$hashB64
const SECRET = (E.BUDDY_SESSION_SECRET || '').trim();
const PUBLIC = path.join(__dirname, 'public');
const COOKIE = 'buddy_sess';

if (!PASS_HASH || !SECRET) console.warn('[BUDDY] login not configured: every protected request is refused');
if (!E.META_MUSE_API_KEY) console.warn('[BUDDY] META_MUSE_API_KEY missing: /api/respond returns 503 (no other model is used)');

// ── login ────────────────────────────────────────────────────────────────
function verifyPassword(pw) {
  try {
    const [alg, N, r, p, saltB64, hashB64] = PASS_HASH.split('$');
    if (alg !== 'scrypt') return false;
    const want = Buffer.from(hashB64, 'base64');
    const got = crypto.scryptSync(String(pw || ''), Buffer.from(saltB64, 'base64'), want.length,
      { N: Number(N), r: Number(r), p: Number(p), maxmem: 256 * 1024 * 1024 });
    return got.length === want.length && crypto.timingSafeEqual(got, want);
  } catch (_) { return false; }
}
function sign(v) { return crypto.createHmac('sha256', SECRET).update(v).digest('base64url'); }
function makeCookie() {
  const exp = Date.now() + COOKIE_DAYS * 86400e3;
  const v = exp + '.' + crypto.randomBytes(12).toString('base64url');
  return v + '.' + sign(v);
}
function deviceTokenOk(req, url) {
  // Overlay devices. Checked only for /ws. HTTP routes still need the login cookie.
  const expected = String(E.BUDDY_DEVICE_TOKEN || '').trim();
  if (!expected) return false;
  let presented = '';
  if (req.headers['x-buddy-token']) presented = String(req.headers['x-buddy-token']).trim();
  if (!presented) {
    const auth = String(req.headers.authorization || '');
    const match = auth.match(/^Bearer\s+(\S+)$/i);
    if (match) presented = match[1].trim();
  }
  if (!presented && url) presented = String(url.searchParams.get('token') || '').trim();
  if (!presented) return false;
  const ha = crypto.createHash('sha256').update(presented).digest();
  const hb = crypto.createHash('sha256').update(expected).digest();
  return crypto.timingSafeEqual(ha, hb);
}
function cookieOk(req) {
  if (!PASS_HASH || !SECRET) return false;
  const m = String(req.headers.cookie || '').match(new RegExp('(?:^|;\\s*)' + COOKIE + '=([^;]+)'));
  if (!m) return false;
  const parts = m[1].split('.');
  if (parts.length !== 3) return false;
  const v = parts[0] + '.' + parts[1];
  const a = Buffer.from(parts[2]); const b = Buffer.from(sign(v));
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return false;
  return Number(parts[0]) > Date.now();
}
function clientIp(req) {
  return String(req.headers['cf-connecting-ip'] || req.socket.remoteAddress || '?');
}

// ── rate limits (in memory) ──────────────────────────────────────────────
const loginFails = new Map(); // ip -> [ts]
let loginFailsAll = [];
const replies = [];
const ttsCalls = [];
function prune(arr, ms) { const c = Date.now() - ms; while (arr.length && arr[0] < c) arr.shift(); return arr; }
function loginBlocked(ip) {
  const l = prune(loginFails.get(ip) || [], 15 * 60e3);
  prune(loginFailsAll, 15 * 60e3);
  return l.length >= 8 || loginFailsAll.length >= 30;
}
function noteLoginFail(ip) {
  const l = loginFails.get(ip) || []; l.push(Date.now()); loginFails.set(ip, l); loginFailsAll.push(Date.now());
  if (loginFails.size > 1000) loginFails.delete(loginFails.keys().next().value);
}

// ── helpers ──────────────────────────────────────────────────────────────
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.json': 'application/json' };
const SEC_HEADERS = {
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
  'Permissions-Policy': 'microphone=(self), camera=()',
  'Content-Security-Policy': "default-src 'self'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'",
};
function send(res, code, body, headers) {
  res.writeHead(code, Object.assign({ 'Cache-Control': 'no-store, no-transform' }, SEC_HEADERS, headers || {}));
  res.end(body);
}
function json(res, code, obj) { send(res, code, JSON.stringify(obj), { 'Content-Type': 'application/json' }); }
function readBody(req, limit = 16 * 1024) {
  return new Promise((resolve, reject) => {
    let n = 0; const chunks = [];
    req.on('data', (c) => { n += c.length; if (n > limit) { reject(new Error('too_big')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}
function parseBody(raw, type) {
  if (/json/.test(type || '')) { try { return JSON.parse(raw || '{}'); } catch (_) { return {}; } }
  return Object.fromEntries(new URLSearchParams(raw || ''));
}
function serveFile(res, rel) {
  const p = path.normalize(path.join(PUBLIC, rel));
  if (!p.startsWith(PUBLIC + path.sep)) return send(res, 404, 'not found');
  fs.readFile(p, (err, buf) => {
    if (err) return send(res, 404, 'not found');
    const t = TYPES[path.extname(p).toLowerCase()] || 'application/octet-stream';
    const cache = /\.(png|jpg)$/.test(p) ? 'private, max-age=3600' : 'no-store, no-transform';
    send(res, 200, buf, { 'Content-Type': t, 'Cache-Control': cache });
  });
}

// ── voice: edge-tts (free Microsoft Edge neural voices), streamed MP3 ──
const { spawn } = require('child_process');
function ttsOnce(text, voice, res, onFirst) {
  return new Promise((resolve) => {
    const p = spawn(TTS_PY, [path.join(__dirname, 'tts.py'), voice, TTS_RATE, TTS_PITCH], { stdio: ['pipe', 'pipe', 'pipe'] });
    let bytes = 0, err = '';
    p.stdout.on('data', (c) => { if (!bytes) onFirst(voice); bytes += c.length; res.write(c); });
    p.stderr.on('data', (c) => { err += c; if (err.length > 2000) err = err.slice(-2000); });
    res.on('close', () => { try { p.kill(); } catch (_) {} });
    p.on('close', (code) => resolve({ bytes, code, err: err.trim().split('\n').pop() }));
    p.on('error', (e) => resolve({ bytes, code: -1, err: e.message }));
    p.stdin.end(text);
  });
}

function ttsBuffer(text, signal) {
  return new Promise(async (resolve) => {
    const t0 = Date.now();
    for (const voice of TTS_VOICES) {
      if (signal && signal.aborted) return resolve(null);
      const r = await new Promise((done) => {
        const p = spawn(TTS_PY, [path.join(__dirname, 'tts.py'), voice, TTS_RATE, TTS_PITCH], { stdio: ['pipe', 'pipe', 'pipe'] });
        const parts = []; let err = '', first = 0;
        const kill = () => { try { p.kill(); } catch (_) {} };
        if (signal) signal.addEventListener('abort', kill, { once: true });
        p.stdout.on('data', (c) => { if (!first) first = Date.now() - t0; parts.push(c); });
        p.stderr.on('data', (c) => { err += c; if (err.length > 2000) err = err.slice(-2000); });
        p.on('close', (code) => { if (signal) signal.removeEventListener('abort', kill); done({ buf: Buffer.concat(parts), code, first, err: err.trim().split('\n').pop() }); });
        p.on('error', (e) => done({ buf: Buffer.alloc(0), code: -1, err: e.message }));
        p.stdin.end(text);
      });
      if (r.buf.length > 0 && r.code === 0) { console.log('[BUDDY] tts', JSON.stringify({ voice, first_byte_ms: r.first, ms: Date.now() - t0, bytes: r.buf.length, chars: text.length })); return resolve({ buf: r.buf, voice }); }
      if (signal && signal.aborted) return resolve(null);
      console.warn('[BUDDY] tts failed', voice, r.code, r.err);
    }
    resolve(null);
  });
}

// ── Muse (Meta direct API, OpenAI-compatible chat completions, streamed) ──
const SENT_RE = /^([\s\S]*?[.!?…]+["'”’)\]]*)(\s+)/;
function cleanSpoken(t) {
  return String(t || '').replace(/[*_`#>]+/g, '').replace(/\[(.*?)\]\(.*?\)/g, '$1')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '').replace(/\s+/g, ' ').trim();
}
function takeSentence(buf, first) {
  const m = buf.match(SENT_RE);
  if (m && m[1].trim().length >= 2) return [m[1], buf.slice(m[0].length)];
  // Long first clause: speak at a comma so the first audio starts sooner.
  if (first && buf.length > 70) { const i = buf.indexOf(', ', 30); if (i > 0 && i < 110) return [buf.slice(0, i + 1), buf.slice(i + 2)]; }
  return null;
}
function museMessages(attitude, kind, text, history, game, image) {
  const msgs = [{ role: 'system', content: persona.buildMuse(attitude, { game: game || '' /* screen-watch hook */ }) }];
  const h = Array.isArray(history) ? history.slice(-16) : [];
  for (const m of h) {
    const role = m && m.role === 'assistant' ? 'assistant' : 'user';
    const c = String((m && m.content) || '').slice(0, 600).trim();
    if (c) msgs.push({ role, content: c });
  }
  const cue = kind === 'opening' ? '(' + persona.OPENING + ')' : kind === 'nudge' ? '(' + persona.NUDGE + ')' : String(text || '').slice(0, 1200);
  // The picture is only on this turn. History stays text, so shots do not pile up.
  msgs.push({ role: 'user', content: userContent(cue, image) });
  return msgs;
}
async function museStream({ attitude, kind, text, history, game, image, signal, onSentence }) {
  const t0 = Date.now();
  const r = await fetch(MUSE_BASE + '/chat/completions', {
    method: 'POST', signal,
    headers: { Authorization: 'Bearer ' + E.META_MUSE_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: MUSE_MODEL, stream: true, reasoning_effort: MUSE_EFFORT,
      max_completion_tokens: MUSE_MAX_TOKENS, store: false, stream_options: { include_usage: true },
      messages: museMessages(attitude, kind, text, history, game, image) }),
  });
  if (!r.ok) {
    const body = (await r.text().catch(() => '')).split(E.META_MUSE_API_KEY).join('[k]').slice(0, 240);
    throw Object.assign(new Error('muse_http_' + r.status), { status: r.status, detail: body });
  }
  const rd = r.body.getReader(); const dec = new TextDecoder();
  let raw = '', pend = '', full = '', ttft = null, n = 0, model = null, usage = null, finish = null;
  const emit = (s) => { const c = cleanSpoken(s); if (c) { n++; onSentence(c, Date.now() - t0); } };
  for (;;) {
    const { value, done } = await rd.read();
    if (done) break;
    raw += dec.decode(value, { stream: true });
    let i;
    while ((i = raw.indexOf('\n')) >= 0) {
      const line = raw.slice(0, i).trim(); raw = raw.slice(i + 1);
      if (!line.startsWith('data:')) continue;
      const d = line.slice(5).trim(); if (d === '[DONE]') continue;
      let j; try { j = JSON.parse(d); } catch (_) { continue; }
      if (j.model) model = j.model;
      if (j.usage) usage = j.usage;
      const ch = j.choices && j.choices[0];
      if (ch && ch.finish_reason) finish = ch.finish_reason;
      const c = ch && ch.delta && typeof ch.delta.content === 'string' ? ch.delta.content : '';
      if (!c) continue;
      if (ttft == null) ttft = Date.now() - t0;
      full += c; pend += c;
      let cut;
      while ((cut = takeSentence(pend, n === 0))) { emit(cut[0]); pend = cut[1]; }
    }
  }
  if (pend.trim()) emit(pend);
  return { text: cleanSpoken(full), muse_ttft_ms: ttft, muse_total_ms: Date.now() - t0, sentences: n, model, usage, finish };
}

// ── pages ────────────────────────────────────────────────────────────────
const LOGIN_HTML = (msg) => `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Buddy · sign in</title><link rel="stylesheet" href="/login.css"></head><body>
<form method="post" action="/login" class="card"><h1>Buddy</h1><p>Chris only.</p>
<input type="password" name="password" placeholder="Password" autocomplete="current-password" autofocus required>
<button type="submit">Sign in</button>${msg ? `<p class="err">${msg}</p>` : ''}</form></body></html>`;

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  const p = u.pathname;
  try {
    if (p === '/favicon.ico') return send(res, 204, '');
    if (p === '/healthz') return send(res, 200, 'ok', { 'Content-Type': 'text/plain' });
    if (p === '/login.css') return serveFile(res, 'login.css');
    if (p === '/login' && req.method === 'GET') return send(res, 200, LOGIN_HTML(''), { 'Content-Type': 'text/html; charset=utf-8' });
    if (p === '/login' && req.method === 'POST') {
      const ip = clientIp(req);
      if (loginBlocked(ip)) return send(res, 429, LOGIN_HTML('Too many tries. Wait 15 minutes.'), { 'Content-Type': 'text/html; charset=utf-8' });
      const b = parseBody(await readBody(req), req.headers['content-type']);
      if (PASS_HASH && SECRET && verifyPassword(b.password)) {
        console.log('[BUDDY] login ok', ip);
        return send(res, 303, '', { Location: '/', 'Set-Cookie': `${COOKIE}=${makeCookie()}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${COOKIE_DAYS * 86400}` });
      }
      noteLoginFail(ip);
      console.log('[BUDDY] login failed', ip);
      return send(res, 401, LOGIN_HTML('Wrong password.'), { 'Content-Type': 'text/html; charset=utf-8' });
    }
    if (p === '/logout') return send(res, 303, '', { Location: '/login', 'Set-Cookie': `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0` });

    // Everything below needs the login cookie.
    if (!cookieOk(req)) {
      if (p.startsWith('/api/') || p === '/token') return json(res, 401, { error: 'login_required' });
      if (req.method === 'GET' && (p === '/' || p.endsWith('.html'))) return send(res, 303, '', { Location: '/login' });
      return send(res, 401, 'login required', { 'Content-Type': 'text/plain' });
    }

    if (p === '/api/tts' && req.method === 'GET') {
      const text = cleanSpoken(u.searchParams.get('text') || '').slice(0, 500);
      if (!text) return send(res, 400, 'empty');
      prune(ttsCalls, 3600e3);
      if (ttsCalls.length >= MAX_TTS_PER_HOUR) return send(res, 429, 'rate limited');
      ttsCalls.push(Date.now());
      const t0 = Date.now(); let headed = false, used = null;
      const onFirst = (voice) => { if (!headed) { headed = true; used = voice; res.writeHead(200, Object.assign({ 'Content-Type': 'audio/mpeg', 'Cache-Control': 'no-store, no-transform', 'X-Buddy-Voice': voice }, SEC_HEADERS)); } };
      for (const voice of TTS_VOICES) {
        const r = await ttsOnce(text, voice, res, onFirst);
        if (r.bytes > 0) { console.log('[BUDDY] tts', JSON.stringify({ voice, ms: Date.now() - t0, bytes: r.bytes, chars: text.length })); return res.end(); }
        console.warn('[BUDDY] tts failed', voice, r.code, r.err);
      }
      if (!headed) return send(res, 502, 'voice unavailable');
      return res.end();
    }
    if (p === '/api/respond' && req.method === 'POST') {
      if (!E.META_MUSE_API_KEY) return json(res, 503, { error: 'muse_not_configured' });
      prune(replies, 3600e3);
      if (replies.length >= MAX_REPLIES_PER_HOUR) return json(res, 429, { error: 'rate_limited' });
      replies.push(Date.now());
      const b = parseBody(await readBody(req, 64 * 1024), 'application/json');
      const attitude = persona.normalize(b.attitude);
      const kind = ['opening', 'nudge'].includes(b.kind) ? b.kind : 'turn';
      if (kind === 'turn' && !String(b.text || '').trim()) return json(res, 400, { error: 'empty' });
      const ac = new AbortController();
      res.on('close', () => { if (!res.writableEnded) ac.abort(); });
      res.writeHead(200, Object.assign({ 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-store, no-transform', 'X-Accel-Buffering': 'no' }, SEC_HEADERS));
      const line = (o) => { try { res.write(JSON.stringify(o) + '\n'); } catch (_) {} };
      try {
        const out = await museStream({ attitude, kind, text: b.text, history: b.history, signal: ac.signal,
          onSentence: (text, ms) => line({ type: 'sentence', text, ms }) });
        if (!out.text) line({ type: 'error', error: 'muse_empty', finish: out.finish });
        line({ type: 'final', text: out.text, muse_ttft_ms: out.muse_ttft_ms, muse_total_ms: out.muse_total_ms, model: out.model, usage: out.usage, finish: out.finish });
        console.log('[BUDDY] reply', JSON.stringify({ attitude, kind, model: out.model, ttft_ms: out.muse_ttft_ms, total_ms: out.muse_total_ms, chars: out.text.length, finish: out.finish }));
      } catch (e) {
        if (e.name !== 'AbortError') { console.error('[BUDDY] muse failed', e.status || '', e.detail || e.message); line({ type: 'error', error: 'muse_failed', status: e.status || null }); }
      }
      return res.end();
    }
    if (p === '/api/config' && req.method === 'GET') {
      return json(res, 200, { attitudes: Object.fromEntries(Object.entries(persona.ATTITUDES).map(([k, v]) => [k, v.label])),
        default: persona.DEFAULT_ATTITUDE, brain: MUSE_MODEL, voices: TTS_VOICES, ears: ears.info, session_max_min: SESSION_MAX_MIN });
    }
    if (req.method === 'GET') return serveFile(res, p === '/' ? 'index.html' : p.slice(1));
    return send(res, 404, 'not found');
  } catch (e) {
    console.error('[BUDDY] error', e && e.message);
    if (!res.headersSent) json(res, 500, { error: 'server_error' });
  }
});

// ── the phone call: one WebSocket, cookie-protected ──
const { attachCall, Ears } = require('./call');
const ears = new Ears(ASR_PY, ASR_SCRIPT, {}, (...a) => console.log('[BUDDY]', ...a));
function allowedOrigin(req, origin) {
  const host = String(req.headers.host || '');
  if (!origin) return false;
  if (origin === 'https://' + host) return true;
  return /^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host) && origin === 'http://' + host;
}
function allowReply() { prune(replies, 3600e3); if (replies.length >= MAX_REPLIES_PER_HOUR || !E.META_MUSE_API_KEY) return false; replies.push(Date.now()); return true; }
const call = attachCall(server, { cookieOk, deviceTokenOk, museStream, ttsBuffer, ears, allowedOrigin, allowReply, sessionMaxMin: SESSION_MAX_MIN,
  log: (...a) => console.log('[BUDDY]', ...a) });

if (require.main === module) {
  server.listen(PORT, HOST, () => console.log(`[BUDDY] listening on ${HOST}:${PORT} brain=${MUSE_MODEL} voices=${TTS_VOICES.join('|')}`));
}
module.exports = { server, verifyPassword, museStream, takeSentence, museMessages, ears, call };
