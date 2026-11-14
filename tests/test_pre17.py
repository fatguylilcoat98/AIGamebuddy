"""pre17: hidden processes, one audio queue, and the SNES label."""
import ast
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backend_subprocess_goes_through_the_helper():
    banned = []
    for path in (ROOT / "backend").glob("*.py"):
        if path.name == "hidden_process.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {"Popen", "run", "call"}:
                owner = func.value
                if isinstance(owner, ast.Name) and owner.id == "subprocess":
                    banned.append(f"{path.name}:{node.lineno} subprocess.{func.attr}")
            if isinstance(func, ast.Name) and func.id in {"Popen", "run", "call"}:
                banned.append(f"{path.name}:{node.lineno} {func.id}()")
    assert banned == []


def test_mp3_decodes_to_samples():
    from backend.brain_link import decode_mp3
    samples, rate = decode_mp3((ROOT / "backend" / "ci_tone.mp3").read_bytes())
    assert rate > 0
    assert len(samples) > 1000
    assert max(abs(sample) for sample in samples) > 0


def test_queue_keeps_the_tail_and_applies_the_volume():
    from backend.brain_link import SampleQueue
    queue = SampleQueue()
    assert queue.enqueue(3, [1.0, -1.0, 0.5, 0.25], gain=0.5) == 4
    heard = []
    while queue.pending():
        heard.extend(queue.take(2))
    assert heard == [0.5, -0.5, 0.25, 0.125]
    assert queue.pending() == 0


def test_barge_drops_the_old_line_and_the_next_one_plays():
    from backend.brain_link import BrainLink

    class Session:
        muted = False
        volume = 80
        mouth = 0.0
        _brain_speaking = False

    link = BrainLink(Session())
    try:
        link._on_text(json.dumps({"type": "barge", "seq": 4}).encode())
        assert link._audio_stop.is_set()
        old = _frame(3, b"not-audio")
        link._on_audio(old)
        assert link._clips == []
        link._on_text(json.dumps({"type": "thinking", "seq": 4}).encode())
        assert not link._audio_stop.is_set()
    finally:
        link.close()


def test_snes_path_beats_a_nes_status_token():
    from backend.game_status import prefer_system
    rom = r"D:\roms wii\snes\Super Mario World (USA).sfc"
    assert prefer_system("nes", rom, "snes9x_libretro.dll") == "snes"
    assert prefer_system("nes", "", "") == "nes"


def test_game_jpeg_skips_black_and_shrinks(tmp_path):
    from io import BytesIO
    from PIL import Image
    from backend.frame_comment import prepare_game_jpeg
    black = Image.new("RGB", (800, 600), (0, 0, 0))
    buf = BytesIO()
    black.save(buf, format="JPEG")
    _b64, _thumb, reason = prepare_game_jpeg(buf.getvalue(), None)
    assert reason == "black"
    color = Image.new("RGB", (1280, 720), (180, 40, 40))
    buf = BytesIO()
    color.save(buf, format="JPEG")
    encoded, thumb, reason = prepare_game_jpeg(buf.getvalue(), None)
    assert reason == "send" and encoded and thumb
    again, _thumb, same = prepare_game_jpeg(buf.getvalue(), thumb)
    assert same == "same" and again == ""
    opened = Image.open(BytesIO(__import__("base64").b64decode(encoded)))
    assert opened.width == 640


def test_fake_brain_queues_then_resumes(tmp_path):
    port_file = tmp_path / "port.txt"
    report = tmp_path / "report.json"
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.fake_brain", "--port-file", str(port_file), "--report", str(report)],
        cwd=str(ROOT),
    )
    try:
        deadline = time.time() + 8
        while time.time() < deadline and not port_file.is_file():
            time.sleep(0.05)
        assert port_file.is_file()
        from backend.brain_link import _Socket
        sock = _Socket(f"ws://127.0.0.1:{port_file.read_text().strip()}", "ci-buddy-token", timeout=5)
        sock.send_text({"type": "hello", "attitude": "friendly", "history": []})
        sock.send_text({
            "type": "game",
            "text": "Here's the TV.",
            "react": True,
            "image": "data:image/jpeg;base64,aaaa",
        })
        kinds = []
        audio = 0
        deadline = time.time() + 5
        while time.time() < deadline and "reply_done" not in kinds:
            frame = sock.recv()
            if frame is None:
                continue
            opcode, payload = frame
            if opcode == 2:
                audio += 1
            elif opcode == 1:
                kinds.append(json.loads(payload.decode())["type"])
        sock.close()
        assert kinds[0] == "ready"
        assert "barge" in kinds
        assert "thinking" in kinds
        assert audio == 3
        deadline = time.time() + 3
        while time.time() < deadline and not report.is_file():
            time.sleep(0.05)
        body = json.loads(report.read_text(encoding="utf-8"))
        assert body["images"] == 1 and body["clips"] == 3 and body["resumed"] is True
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_muse_image_shape():
    node = subprocess.run(
        ["node", "-e", r"""
const {userContent} = require('./brain-patch/vision_message');
const content = userContent('Here is the TV.', 'data:image/jpeg;base64,aaaa');
if (!Array.isArray(content)) process.exit(2);
if (content[0].type !== 'text' || content[0].text !== 'Here is the TV.') process.exit(3);
if (content[1].type !== 'image_url' || content[1].image_url.url !== 'data:image/jpeg;base64,aaaa') process.exit(4);
if (userContent('just text', '') !== 'just text') process.exit(5);
const persona = require('./brain-patch/persona');
const prompt = persona.buildMuse('extreme', {game: 'stage'});
if (prompt.includes("can't see")) process.exit(6);
if (!prompt.includes('health')) process.exit(7);
if (!prompt.includes('EXTREME')) process.exit(8);
const server = require('fs').readFileSync('brain-patch/server.js', 'utf8');
if (!server.includes('include_usage')) process.exit(9);
if (!server.includes('userContent')) process.exit(10);
const call = require('fs').readFileSync('brain-patch/call.js', 'utf8');
if (!call.includes("type: 'play'") && !call.includes('m.type === \'play\'')) process.exit(11);
console.log('ok');
"""],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert node.returncode == 0, node.stderr


def _frame(seq: int, audio: bytes) -> bytes:
    header = json.dumps({"seq": seq, "i": 0, "text": "x", "kind": "turn"}).encode()
    return len(header).to_bytes(4, "little") + header + audio
