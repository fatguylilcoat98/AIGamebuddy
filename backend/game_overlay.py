"""Small always-on-top Windows Game Buddy overlay.

Run the FastAPI backend first, then: python game_overlay.py
Uses only Python's standard library. Screen observation is opt-in.
"""
import json
import threading
import tkinter as tk
from tkinter import ttk
from urllib import request, error

BASE = "http://127.0.0.1:8766"
TIMEOUT = 45


def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(BASE + path, data=data,
                          headers={"Content-Type": "application/json"},
                          method="POST" if payload is not None else "GET")
    with request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode("utf-8"))


class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Game Buddy")
        self.root.geometry("340x345+950+420")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#151923")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.active = False
        self.busy = False
        self.auto = tk.BooleanVar(value=False)
        self.vision = tk.BooleanVar(value=False)
        self.speech = tk.BooleanVar(value=True)
        self.personality = tk.StringVar(value="sassy")
        self.status = tk.StringVar(value="Backend not connected")
        self._drag = None
        title = tk.Label(self.root, text="🎮 GAME BUDDY  •  drag here",
                         bg="#222b40", fg="#ffffff", font=("Segoe UI", 12, "bold"), pady=9)
        title.pack(fill="x")
        title.bind("<Button-1>", self.drag_start)
        title.bind("<B1-Motion>", self.drag_move)
        body = tk.Frame(self.root, bg="#151923", padx=12, pady=10)
        body.pack(fill="both", expand=True)
        tk.Label(body, textvariable=self.status, bg="#151923", fg="#91d7ff",
                 wraplength=300, justify="left").pack(anchor="w")
        ttk.Combobox(body, textvariable=self.personality,
                     values=("casual", "sassy", "extreme"), state="readonly").pack(fill="x", pady=6)
        tk.Checkbutton(body, text="Enable screen observation", variable=self.vision,
                       bg="#151923", fg="white", selectcolor="#29344b",
                       activebackground="#151923", activeforeground="white").pack(anchor="w")
        tk.Checkbutton(body, text="Speak replies aloud", variable=self.speech,
                       bg="#151923", fg="white", selectcolor="#29344b",
                       activebackground="#151923", activeforeground="white").pack(anchor="w")
        row = tk.Frame(body, bg="#151923")
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Start Buddy", command=self.start).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="Stop", command=self.stop).pack(side="left", expand=True, fill="x")
        ttk.Button(body, text="Look at game now", command=self.observe).pack(fill="x")
        tk.Checkbutton(body, text="Auto-look every 30 seconds (opt-in)", variable=self.auto,
                       bg="#151923", fg="white", selectcolor="#29344b",
                       activebackground="#151923", activeforeground="white").pack(anchor="w")
        self.entry = ttk.Entry(body)
        self.entry.pack(fill="x", pady=(6, 2))
        self.entry.insert(0, "Nice catch!")
        self.entry.bind("<Return>", lambda _event: self.say())
        ttk.Button(body, text="Say to Buddy", command=self.say).pack(fill="x")
        self.output = tk.Label(body, text="Ready when you are.", bg="#151923",
                               fg="#e7eaf0", wraplength=300, justify="left")
        self.output.pack(anchor="w", pady=7)
        self.root.after(30000, self.tick)

    def drag_start(self, event):
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def drag_move(self, event):
        if self._drag:
            self.root.geometry(f"+{event.x_root-self._drag[0]}+{event.y_root-self._drag[1]}")

    def work(self, fn):
        if self.busy:
            return
        self.busy = True
        self.status.set("Working…")
        def runner():
            try:
                result = fn()
                self.root.after(0, lambda: self.complete(result, None))
            except (error.URLError, ValueError, OSError) as exc:
                self.root.after(0, lambda: self.complete(None, str(exc)))
        threading.Thread(target=runner, daemon=True).start()

    def complete(self, result, problem):
        self.busy = False
        if problem:
            self.status.set("Error: " + problem[:160])
            return
        if isinstance(result, dict):
            if "running" in result:
                self.active = bool(result["running"])
            self.status.set("Buddy running" if self.active else "Buddy stopped")
            self.output.config(text=result.get("text") or result.get("observation")
                               or result.get("reason") or "Ready.")
            if result.get("error"):
                self.status.set("Error: " + result["error"][:160])

    def start(self):
        settings = {"personality": self.personality.get(),
                    "vision_enabled": self.vision.get(),
                    "speech_enabled": self.speech.get()}
        self.work(lambda: api("/buddy/start", settings))

    def stop(self):
        self.auto.set(False)
        self.work(lambda: api("/buddy/stop", {}))

    def observe(self):
        if not self.active:
            self.status.set("Start Buddy first.")
        elif not self.vision.get():
            self.status.set("Enable observation and restart Buddy first.")
        else:
            self.work(lambda: api("/buddy/observe",
                                  {"priority": 5, "question": "Describe the current gameplay briefly and identify any notable event."}))

    def say(self):
        text = self.entry.get().strip()
        if not self.active:
            self.status.set("Start Buddy first.")
        elif text:
            self.work(lambda: api("/buddy/say", {"text": text}))

    def tick(self):
        if self.auto.get() and self.active and self.vision.get() and not self.busy:
            self.observe()
        self.root.after(30000, self.tick)

    def close(self):
        self.auto.set(False)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Overlay().run()
