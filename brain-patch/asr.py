#!/usr/bin/env python3
"""Buddy ears: one long-lived local worker. Voice-activity detection (webrtcvad +
an adaptive loudness gate) finds the end of each utterance, then LOCAL
faster-whisper (CPU int8) turns it into text. No cloud speech service.

stdin  frames: type u8 | sid u32 | len u32 | payload
        1 = audio (16 kHz mono int16 LE)  2 = open  3 = close  4 = state JSON {"bot": bool}
stdout JSON lines: ready | speech_start | speech_end | final | drop | error
"""
import sys, os, json, struct, time, threading, collections, queue
import numpy as np

MODEL = os.environ.get('BUDDY_ASR_MODEL', 'base.en')
THREADS = int(os.environ.get('BUDDY_ASR_THREADS', '4'))
END_MS = int(os.environ.get('BUDDY_VAD_END_MS', '600'))      # silence that ends a turn
MIN_VOICED_MS = int(os.environ.get('BUDDY_VAD_MIN_MS', '350'))
MAX_UTT_S = 15
SR, FR = 16000, 320                                           # 20 ms frames
END_FRAMES = max(5, END_MS // 20)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from noise_gate import RoomEar, keep_transcript

out_lock = threading.Lock()
def emit(o):
    with out_lock:
        sys.stdout.write(json.dumps(o) + '\n'); sys.stdout.flush()

try:
    import webrtcvad
except Exception:
    webrtcvad = None
from faster_whisper import WhisperModel

t = time.time()
model = WhisperModel(MODEL, device='cpu', compute_type='int8', cpu_threads=THREADS)
model.transcribe(np.zeros(SR, np.float32), language='en', beam_size=1)   # warm up
emit({'ev': 'ready', 'model': MODEL, 'threads': THREADS, 'load_ms': int((time.time() - t) * 1000), 'vad': 'webrtcvad' if webrtcvad else 'energy', 'end_ms': END_MS})

PROMPT = 'Two friends on a couch playing video games, chatting.'
jobs = queue.Queue()
def asr_loop():
    while True:
        sid, pcm, t_end, voiced_ms = jobs.get()
        try:
            a = pcm.astype(np.float32) / 32768.0
            t0 = time.time()
            segs, info = model.transcribe(a, language='en', beam_size=1, condition_on_previous_text=False,
                                          without_timestamps=True, vad_filter=False, initial_prompt=PROMPT)
            segs = list(segs)
            text = ' '.join(s.text.strip() for s in segs).strip()
            ms = int((time.time() - t0) * 1000)
            nsp = max([s.no_speech_prob for s in segs] or [1.0]); lp = min([s.avg_logprob for s in segs] or [-9])
            if not keep_transcript(text, voiced_ms, nsp, lp):
                emit({'sid': sid, 'ev': 'drop', 'reason': 'no_words', 'text': text, 'asr_ms': ms,
                      'no_speech_prob': round(nsp, 3), 'avg_logprob': round(lp, 3)})
            else:
                emit({'sid': sid, 'ev': 'final', 'text': text, 'asr_ms': ms, 'audio_ms': int(len(a) / 16), 'voiced_ms': voiced_ms,
                      'queued_ms': int((t0 - t_end) * 1000), 'no_speech_prob': round(nsp, 3), 'avg_logprob': round(lp, 3)})
        except Exception as e:
            emit({'sid': sid, 'ev': 'error', 'error': str(e)[:200]})
threading.Thread(target=asr_loop, daemon=True).start()

class Ear:
    def __init__(self, sid):
        self.sid = sid; self.vad = webrtcvad.Vad(2) if webrtcvad else None
        self.buf = b''; self.bot = False; self.room = RoomEar()
        self.pre = collections.deque(maxlen=20)
        self.utt = None; self.sil = 0; self.voiced = 0
    def feed(self, data):
        self.buf += data
        while len(self.buf) >= FR * 2:
            fr, self.buf = self.buf[:FR * 2], self.buf[FR * 2:]
            self.frame(fr)
    def frame(self, fr):
        s = np.frombuffer(fr, np.int16)
        rms = float(np.sqrt(np.mean(s.astype(np.float32) ** 2))) + 1e-3
        try:
            sp = self.vad.is_speech(fr, SR) if self.vad else rms > self.room.gate_level()
        except Exception:
            sp = False
        # While Buddy is playing, the overlay also sends silence. Ignore the mic here too.
        self.room.gated = self.bot
        started = self.room.frame(rms, sp)
        gate = self.room.gate_level()
        voiced = (not self.bot) and sp and rms > gate
        if self.utt is None:
            self.pre.append(fr)
            if started and not self.bot:
                self.utt = list(self.pre); self.sil = 0; self.voiced = 18; self.t_start = time.time()
                emit({'sid': self.sid, 'ev': 'speech_start', 'barge': False, 'rms': int(rms), 'gate': int(gate),
                      'voiced_ms': 360})
            return
        self.utt.append(fr)
        if voiced: self.sil = 0; self.voiced += 1
        else: self.sil += 1
        if self.sil >= END_FRAMES or len(self.utt) * 20 >= MAX_UTT_S * 1000:
            keep = self.utt[:len(self.utt) - max(0, self.sil - 8)]       # trim trailing silence, keep 160 ms
            voiced_ms = self.voiced * 20; self.utt = None; self.pre.clear()
            t_end = time.time()
            emit({'sid': self.sid, 'ev': 'speech_end', 'dur_ms': len(keep) * 20, 'voiced_ms': voiced_ms, 'hangover_ms': self.sil * 20})
            if voiced_ms < MIN_VOICED_MS:
                emit({'sid': self.sid, 'ev': 'drop', 'reason': 'too_short', 'voiced_ms': voiced_ms}); return
            jobs.put((self.sid, np.frombuffer(b''.join(keep), np.int16).copy(), t_end, voiced_ms))

ears = {}
inp = sys.stdin.buffer
def readn(n):
    b = b''
    while len(b) < n:
        c = inp.read(n - len(b))
        if not c: return None
        b += c
    return b
while True:
    h = readn(9)
    if h is None: break
    typ, sid, ln = struct.unpack('<BII', h)
    pl = readn(ln) if ln else b''
    if pl is None: break
    if typ == 2: ears[sid] = Ear(sid)
    elif typ == 3: ears.pop(sid, None)
    elif typ == 1:
        e = ears.get(sid)
        if e: e.feed(pl)
    elif typ == 4:
        e = ears.get(sid)
        if e:
            try: e.bot = bool(json.loads(pl.decode()).get('bot'))
            except Exception: pass
