"""A local stand-in for the brain, used by the Windows smoke test.

It accepts the device token, remembers the latest game image, and sends three
MP3 sentences: two back to back, a barge-in, then one more. The overlay has to
queue them, cut the line, and resume.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import time
from pathlib import Path

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_TONE = Path(__file__).with_name("ci_tone.mp3").read_bytes()
_TOKEN = "ci-buddy-token"


def _send_frame(conn, opcode: int, payload: bytes) -> None:
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += struct.pack("!H", length)
    else:
        header.append(127)
        header += struct.pack("!Q", length)
    conn.sendall(bytes(header) + payload)


def _read_frame(conn, buf: bytearray):
    while True:
        if len(buf) >= 2:
            length = buf[1] & 0x7F
            offset = 2
            if length == 126 and len(buf) >= 4:
                length = struct.unpack("!H", buf[2:4])[0]
                offset = 4
            elif length == 127 and len(buf) >= 10:
                length = struct.unpack("!Q", buf[2:10])[0]
                offset = 10
            masked = bool(buf[1] & 0x80)
            need = offset + (4 if masked else 0) + length
            if len(buf) >= need:
                if masked:
                    mask = buf[offset:offset + 4]
                    offset += 4
                    data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(buf[offset:offset + length]))
                else:
                    data = bytes(buf[offset:offset + length])
                opcode = buf[0] & 0x0F
                del buf[:need]
                return opcode, data
        chunk = conn.recv(65536)
        if not chunk:
            return None
        buf += chunk


def _audio(seq: int, index: int) -> bytes:
    header = json.dumps({"seq": seq, "i": index, "text": "tone", "kind": "turn"}).encode("utf-8")
    return struct.pack("<I", len(header)) + header + _TONE


def _write_report(path: str, report: dict) -> None:
    if path:
        Path(path).write_text(json.dumps(report), encoding="utf-8")


def _handshake(conn) -> bool:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = conn.recv(1)
        if not chunk:
            return False
        header += chunk
        if len(header) > 16384:
            return False
    text = header.decode("latin1", "replace")
    if f"X-Buddy-Token: {_TOKEN}" not in text and f"token={_TOKEN}" not in text.split("\r\n", 1)[0]:
        conn.sendall(b"HTTP/1.1 401 Unauthorized\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
        return False
    key = ""
    for line in text.split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()
    accept = base64.b64encode(hashlib.sha1((key + _GUID).encode("ascii")).digest()).decode("ascii")
    conn.sendall(
        (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "\r\n"
        ).encode("ascii")
    )
    return True


def _serve(conn, report: dict) -> None:
    if not _handshake(conn):
        return
    buf = bytearray()
    conn.settimeout(30)
    while not report.get("resumed"):
        frame = _read_frame(conn, buf)
        if frame is None:
            return
        opcode, payload = frame
        if opcode == 8:
            return
        if opcode == 9:
            _send_frame(conn, 10, payload)
            continue
        if opcode != 1:
            continue
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            continue
        kind = message.get("type")
        if kind == "hello":
            _send_frame(conn, 1, json.dumps({"type": "ready", "ears": False}).encode("utf-8"))
        elif kind == "game":
            image = str(message.get("image") or "")
            if image.startswith("data:image/"):
                report["images"] = int(report.get("images") or 0) + 1
            if message.get("react") and image.startswith("data:image/") and not report.get("resumed"):
                report["reacts"] = int(report.get("reacts") or 0) + 1
                _send_frame(conn, 1, json.dumps({"type": "thinking", "seq": 1, "kind": "turn"}).encode("utf-8"))
                _send_frame(conn, 2, _audio(1, 0))
                _send_frame(conn, 2, _audio(1, 1))
                report["clips"] = 2
                time.sleep(0.35)
                _send_frame(conn, 1, json.dumps({"type": "barge", "seq": 2, "why": "barge"}).encode("utf-8"))
                report["barge"] = True
                _send_frame(conn, 1, json.dumps({"type": "thinking", "seq": 2, "kind": "turn"}).encode("utf-8"))
                _send_frame(conn, 2, _audio(2, 0))
                report["clips"] = 3
                report["resumed"] = True
                _send_frame(conn, 1, json.dumps({"type": "reply_done", "seq": 2, "n": 1}).encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port-file", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    import socket
    report = {"images": 0, "reacts": 0, "clips": 0, "barge": False, "resumed": False}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(4)
    port = sock.getsockname()[1]
    Path(args.port_file).write_text(str(port), encoding="ascii")
    sock.settimeout(5)
    deadline = time.time() + 240
    try:
        while time.time() < deadline and not report.get("resumed"):
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                _write_report(args.report, report)
                continue
            try:
                _serve(conn, report)
            except Exception as exc:
                report["error"] = str(exc)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
                _write_report(args.report, report)
    finally:
        _write_report(args.report, report)
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
