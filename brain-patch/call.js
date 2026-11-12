'use strict';
// Buddy "phone call": ONE WebSocket per session carries the mic up (16 kHz PCM,
// continuous, never toggled) and Buddy's voice down (one MP3 per sentence, played
// gaplessly by the page). Ears = local asr.py (VAD + faster-whisper on the Dell).
// Brain = Muse. Voice = edge-tts. Full duplex: the mic stays open while Buddy talks;
// echo cancellation in the browser + a louder-gate during his speech + a text echo
// guard here keep him from answering himself; real speech over him = barge-in.
const path = require('path');
const { spawn } = require('child_process');
const { WebSocketServer } = require('ws');
const persona = require('./persona');

function normText(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim(); }
function jaccard(a, b) {
  const wa = new Set(normText(a).split(' ').filter(Boolean)), wb = new Set(normText(b).split(' ').filter(Boolean));
  if (!wa.size || !wb.size) return 0; let i = 0; for (const w of wa) if (wb.has(w)) i++;
  return i / (wa.size + wb.size - i);
}
// Is this transcript just Buddy's own voice coming back through the speaker?
function isEcho(text, botText) {
  const n = normText(text), r = normText(botText); if (!n || !r) return false;
  if (r.includes(n)) return true;
  const rw = new Set(r.split(' ')); const nw = n.split(' ').filter(w => w.length >= 3);
  if (nw.length >= 2 && nw.filter(w => rw.has(w)).length / nw.length >= 0.75) return true;
  return jaccard(text, botText) >= 0.6;
}

// ── the ears: one shared local worker ──
class Ears {
  constructor(py, script, env, log) {
    this.py = py; this.script = script; this.env = env; this.log = log;
    this.subs = new Map(); this.ready = false; this.info = null; this.restarts = 0; this.start();
  }
  start() {
    const p = spawn(this.py, [this.script], { stdio: ['pipe', 'pipe', 'pipe'], env: Object.assign({}, process.env, this.env) });
    this.p = p; this.ready = false; let buf = '';
    p.stdout.on('data', (c) => {
      buf += c; let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const l = buf.slice(0, i); buf = buf.slice(i + 1); let o; try { o = JSON.parse(l); } catch (_) { continue; }
        if (o.ev === 'ready') { this.ready = true; this.info = o; this.log('ears ready', JSON.stringify(o)); for (const sid of this.subs.keys()) this.frame(2, sid); continue; }
        const s = this.subs.get(o.sid); if (s) s(o);
      }
    });
    p.stderr.on('data', (c) => { const t = String(c).trim(); if (t && !/HF_TOKEN|unauthenticated/.test(t)) this.log('ears stderr', t.slice(-300)); });
    p.stdin.on('error', () => {});
    p.on('close', (code) => { this.ready = false; this.log('ears exited', code); if (!this.closing) setTimeout(() => { this.restarts++; this.start(); }, Math.min(10000, 1000 * (1 + this.restarts))); });
  }
  frame(type, sid, payload) {
    if (!this.p || !this.p.stdin.writable) return;
    const pl = payload || Buffer.alloc(0); const h = Buffer.alloc(9);
    h.writeUInt8(type, 0); h.writeUInt32LE(sid, 1); h.writeUInt32LE(pl.length, 5);
    this.p.stdin.write(pl.length ? Buffer.concat([h, pl]) : h);
  }
  open(sid, fn) { this.subs.set(sid, fn); if (this.ready) this.frame(2, sid); }
  close(sid) { this.subs.delete(sid); this.frame(3, sid); }
  audio(sid, pcm) { if (this.ready) this.frame(1, sid, pcm); }
  state(sid, bot) { this.frame(4, sid, Buffer.from(JSON.stringify({ bot }))); }
  stop() { this.closing = true; try { this.p.kill(); } catch (_) {} }
}

function attachCall(server, d) {
  // d: { cookieOk, museStream, ttsBuffer, log, allowReply, sessionMaxMin, ears, allowedOrigin(req, origin) }
  const wss = new WebSocketServer({ noServer: true, maxPayload: 2 * 1024 * 1024 });
  let nextSid = 1; const live = new Set();
  server.on('upgrade', (req, sock, head) => {
    const u = new URL(req.url, 'http://x');
    const deny = (code, msg) => { try { sock.write(`HTTP/1.1 ${code} ${msg}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`); } catch (_) {} sock.destroy(); };
    if (u.pathname !== '/ws') return deny(404, 'Not Found');
    const tokenOk = typeof d.deviceTokenOk === 'function' && d.deviceTokenOk(req, u);
    if (!tokenOk && !d.cookieOk(req)) { d.log('ws refused: no session'); return deny(401, 'Unauthorized'); }
    if (!tokenOk && !d.allowedOrigin(req, req.headers.origin)) { d.log('ws refused: origin', req.headers.origin); return deny(403, 'Forbidden'); }
    if (live.size >= 3) return deny(429, 'Too Many Requests');
    wss.handleUpgrade(req, sock, head, (ws) => { live.add(ws); ws.on('close', () => live.delete(ws)); session(ws, nextSid++); });
  });

  function session(ws, sid) {
    const S = { attitude: persona.DEFAULT_ATTITUDE, history: [], game: '', image: '', bot: false, botText: '', botEndAt: 0, seq: 0, ac: null, replying: false,
      pendingUser: '', lastUser: '', nudges: 0, silence: null, speechEndAt: 0, hangover: 0, hearing: false, sent: 0, frames: 0, started: Date.now() };
    const tx = (o) => { if (ws.readyState === 1) ws.send(JSON.stringify(o)); };
    const log = (...a) => d.log('[call ' + sid + ']', ...a);
    const cap = setTimeout(() => { tx({ type: 'end', reason: 'session limit (' + d.sessionMaxMin + ' min) reached' }); ws.close(4000, 'cap'); }, d.sessionMaxMin * 60e3);
    const ping = setInterval(() => { try { ws.ping(); } catch (_) {} }, 15000);
    function clearSilence() { if (S.silence) { clearTimeout(S.silence); S.silence = null; } }
    function armSilence() {
      clearSilence();
      S.silence = setTimeout(() => {
        S.silence = null;
        if (S.replying || S.bot || S.hearing || S.nudges >= 4) return;
        if (S.nudges > 0 && /\?\s*["')\]]*\s*$/.test(S.botText.trim())) return;
        S.nudges++; reply('nudge');
      }, 9000);
    }
    function setBot(on) { if (S.bot === on) return; S.bot = on; d.ears.state(sid, on); if (!on) { S.audioEnd = 0; S.botEndAt = Date.now(); armSilence(); } }
    function cancelReply(why) {
      if (!S.replying && !S.bot) return false;
      S.seq++; if (S.ac) { try { S.ac.abort(); } catch (_) {} } S.ac = null; S.replying = false;
      tx({ type: 'barge', seq: S.seq, why }); setBot(false); return true;
    }

    async function reply(kind, text) {
      if (!d.allowReply()) { tx({ type: 'note', text: 'reply limit reached' }); return; }
      const seq = ++S.seq; if (S.ac) { try { S.ac.abort(); } catch (_) {} }
      const ac = new AbortController(); S.ac = ac; S.replying = true; clearSilence();
      const t0 = Date.now(); const fromEnd = kind === 'turn' && S.speechEndAt ? S.speechEndAt : 0;
      tx({ type: 'thinking', seq, kind });
      let chain = Promise.resolve(), spoken = [], idx = 0, firstAudioAt = 0, firstSentAt = 0;
      const sendAudio = (i, sent, buf) => {
        if (seq !== S.seq || ws.readyState !== 1) return;
        const h = Buffer.from(JSON.stringify({ seq, i, text: sent, kind }));
        const len = Buffer.alloc(4); len.writeUInt32LE(h.length, 0);
        ws.send(Buffer.concat([len, h, buf])); spoken.push(sent); S.botText = spoken.join(' ');
        tx({ type: 'bot', seq, text: S.botText });
        if (!firstAudioAt) { firstAudioAt = Date.now(); setBot(true); }
        // Safety net if the page never reports "done playing": ~48 kbit/s MP3 → bytes/6 ms.
        S.audioEnd = Math.max(S.audioEnd || 0, Date.now()) + buf.length / 6; if (S.botWatch) clearTimeout(S.botWatch);
        S.botWatch = setTimeout(() => { if (seq === S.seq) setBot(false); }, S.audioEnd - Date.now() + 2500);
      };
      let out = null;
      try {
        out = await d.museStream({ attitude: S.attitude, kind, text, history: S.history.slice(0, kind === 'turn' ? -1 : undefined), game: S.game, image: S.image || '', signal: ac.signal,
          onSentence: (sent) => {
            if (!firstSentAt) firstSentAt = Date.now();
            const i = idx++; const p = d.ttsBuffer(sent, ac.signal);      // start every sentence's voice right away
            chain = chain.then(() => p).then((r) => { if (r && r.buf) sendAudio(i, sent, r.buf); }).catch(() => {});
          } });
        await chain;
      } catch (e) { if (e.name !== 'AbortError') { log('muse failed', e.status || '', e.detail || e.message); tx({ type: 'note', text: 'brain unavailable' }); } }
      if (seq !== S.seq) { if (spoken.length) S.history.push({ role: 'assistant', content: spoken.join(' ') + ' —' }); return; }
      S.replying = false; S.ac = null;
      if (spoken.length) S.history.push({ role: 'assistant', content: spoken.join(' ') });
      if (S.history.length > 40) S.history.splice(0, S.history.length - 40);
      tx({ type: 'reply_done', seq, n: spoken.length, muse_ttft_ms: out && out.muse_ttft_ms });
      const m = { kind, attitude: S.attitude, sentences: spoken.length, muse_first_sentence_ms: firstSentAt ? firstSentAt - t0 : null,
        muse_ttft_ms: out && out.muse_ttft_ms, first_audio_sent_ms: firstAudioAt ? firstAudioAt - t0 : null,
        speech_end_to_first_audio_sent_ms: fromEnd && firstAudioAt ? firstAudioAt - fromEnd : null, tokens: out && out.usage && out.usage.total_tokens };
      log('reply', JSON.stringify(m)); tx(Object.assign({ type: 'metrics' }, m));
      if (!spoken.length) { setBot(false); armSilence(); }
    }

    function onEars(o) {
      if (o.ev === 'speech_start') {
        S.hearing = true; clearSilence(); S.nudges = 0; tx({ type: 'hearing', barge: o.barge });
        if (S.bot) { log('barge-in', JSON.stringify({ rms: o.rms, gate: o.gate })); cancelReply('barge'); }
        else if (S.replying) {           // they kept talking after a short pause: fold it into one turn
          cancelReply('continued');
          if (S.lastUser && S.history.length && S.history[S.history.length - 1].content === S.lastUser) { S.history.pop(); S.pendingUser = S.lastUser; }
        }
      } else if (o.ev === 'speech_end') {
        S.hearing = false; S.speechEndAt = Date.now() - (o.hangover_ms || 0); S.hangover = o.hangover_ms || 0;
        tx({ type: 'user_end', hangover_ms: o.hangover_ms, dur_ms: o.dur_ms });
      } else if (o.ev === 'final') {
        const recent = S.bot || Date.now() - S.botEndAt < 2500;
        if (recent && isEcho(o.text, S.botText)) { log('echo dropped', JSON.stringify(o.text)); tx({ type: 'echo', text: o.text }); if (S.pendingUser) flushPending(); else if (!S.bot) armSilence(); return; }
        const text = (S.pendingUser ? S.pendingUser + ' ' : '') + o.text; S.pendingUser = '';
        log('heard', JSON.stringify({ text: o.text, asr_ms: o.asr_ms, audio_ms: o.audio_ms, queued_ms: o.queued_ms }));
        tx({ type: 'user', text, asr_ms: o.asr_ms });
        S.lastUser = text; S.history.push({ role: 'user', content: text });
        reply('turn', text);
      } else if (o.ev === 'drop') {
        S.hearing = false; tx({ type: 'drop', reason: o.reason });
        if (S.pendingUser) flushPending(); else if (!S.replying && !S.bot) armSilence();
      } else if (o.ev === 'error') log('ears error', o.error);
    }
    function flushPending() {
      const t = S.pendingUser; S.pendingUser = ''; S.lastUser = t; S.history.push({ role: 'user', content: t }); reply('turn', t);
    }

    d.ears.open(sid, onEars);
    log('open');
    ws.on('message', (data, isBin) => {
      if (isBin) { S.frames++; if (data.length <= 32000) d.ears.audio(sid, data); return; }
      let m; try { m = JSON.parse(String(data)); } catch (_) { return; }
      if (m.type === 'hello') {
        S.attitude = persona.normalize(m.attitude);
        if (Array.isArray(m.history)) S.history = m.history.slice(-30).map(h => ({ role: h.role === 'assistant' ? 'assistant' : 'user', content: String(h.content || '').slice(0, 600) })).filter(h => h.content);
        tx({ type: 'ready', ears: d.ears.ready, model: d.ears.info && d.ears.info.model, end_ms: d.ears.info && d.ears.info.end_ms });
        if (!S.history.length) reply('opening'); else armSilence();
      } else if (m.type === 'play') {
        if (m.seq === S.seq || !m.on) setBot(!!m.on);
      } else if (m.type === 'attitude') S.attitude = persona.normalize(m.attitude);
      else if (m.type === 'game') {
        const note = String(m.text || '').slice(0, 400);
        if (typeof m.image === 'string' && m.image.indexOf('data:image/') === 0) S.image = m.image;
        if (note) S.game = note;
        const marker = '[Screen update] ' + (note || 'the game');
        const last = S.history.length ? S.history[S.history.length - 1] : null;
        if (last && String(last.content || '').indexOf('[Screen update]') === 0) S.history.pop();
        if (note) S.history.push({ role: 'user', content: marker });
        if (m.react && !S.replying && !S.bot && !S.hearing) reply('turn', note || "Here's the TV.");
      } else if (m.type === 'ping') tx({ type: 'pong', t: m.t });
      else if (m.type === 'lat') log('client latency', JSON.stringify(m));
    });
    ws.on('close', (code) => {
      clearTimeout(cap); clearInterval(ping); clearSilence(); if (S.botWatch) clearTimeout(S.botWatch); S.seq++; if (S.ac) { try { S.ac.abort(); } catch (_) {} }
      d.ears.close(sid); log('closed', code, JSON.stringify({ secs: Math.round((Date.now() - S.started) / 1000), frames: S.frames }));
    });
    ws.on('error', () => {});
  }
  return { wss, live };
}
module.exports = { attachCall, Ears, isEcho };
