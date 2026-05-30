"""
Borderless circular float ball - standalone tkinter window.
No external dependencies beyond Python stdlib + tkinter.

Launch: python float_ball.py
Kill: terminate the process
"""
import tkinter as tk
import json
import urllib.request
import sys
import os

API = "http://127.0.0.1:5000"
REFRESH_MS = 30000

BG = "#0b0f19"
FILL = "#151c30"
OUTLINE = "#2a3045"
OUTLINE_WARN = "#f59e0b"
TEXT_IN = "#a5b4fc"
TEXT_OUT = "#6ee7b7"
TEXT_LABEL = "#5c6278"
SIZE = 92
KEY = "gray99"  # transparent color key


def fetch(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read())
    except:
        return None


def fmt(n):
    if n is None: return "--"
    n = int(n)
    if n >= 1_000_000: return f"{n/1e6:.1f}M"
    if n >= 10_000: return f"{n/1e4:.1f}万"
    if n >= 1_000: return f"{n/1e3:.1f}K"
    return str(n)


class FloatBall:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', KEY)

        # Position at right edge, mid-screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = sw - SIZE - 5
        y = sh // 2 - SIZE // 2
        self.root.geometry(f"{SIZE}x{SIZE}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root, width=SIZE, height=SIZE,
            bg=KEY, highlightthickness=0, bd=0,
        )
        self.canvas.pack()

        r = SIZE // 2 - 3
        cx = cy = SIZE // 2
        self.circle = self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=FILL, outline=OUTLINE, width=2, tags="circle",
        )

        # Glow effect (subtle outer ring)
        self.glow = self.canvas.create_oval(
            cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4,
            fill="", outline="#6366f1", width=1, tags="glow",
        )
        self.canvas.itemconfig(self.glow, state="hidden")

        # Labels & values — centered vertically in the ball
        self.lbl_in = self.canvas.create_text(cx, cy - 22, text="输入", fill=TEXT_LABEL,
            font=("Microsoft YaHei", 6))
        self.val_in = self.canvas.create_text(cx, cy - 8, text="--", fill=TEXT_IN,
            font=("Consolas", 11, "bold"))
        self.lbl_out = self.canvas.create_text(cx, cy + 8, text="输出", fill=TEXT_LABEL,
            font=("Microsoft YaHei", 6))
        self.val_out = self.canvas.create_text(cx, cy + 22, text="--", fill=TEXT_OUT,
            font=("Consolas", 11, "bold"))

        # Drag
        self._dx = self._dy = 0
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<Double-Button-1>", self._expand)
        self.canvas.bind("<Enter>", lambda e: self.canvas.itemconfig(self.glow, state="normal"))
        self.canvas.bind("<Leave>", lambda e: self.canvas.itemconfig(self.glow, state="hidden"))

        self.refresh()
        self.root.after(REFRESH_MS, self._tick)
        self.root.mainloop()

    def _press(self, e): self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def _expand(self, e):
        try:
            urllib.request.urlopen(f"{API}/api/expand", timeout=3)
        except:
            pass
        self.root.destroy()

    def _tick(self):
        if self.root.winfo_exists():
            self.refresh()
            self.root.after(REFRESH_MS, self._tick)

    def refresh(self):
        data = fetch(f"{API}/api/dashboard")
        if not data or not data.get("success"):
            return
        d = data["data"]
        today = d.get("daily", {}).get("today", {})
        self.canvas.itemconfig(self.val_in, text=fmt(today.get("input", 0)))
        self.canvas.itemconfig(self.val_out, text=fmt(today.get("output", 0)))

        bal = float(d["balance"].get("normal", 0))
        outline = OUTLINE_WARN if bal < 5 else OUTLINE
        self.canvas.itemconfig(self.circle, outline=outline)
        if bal < 5:
            self.canvas.itemconfig(self.glow, outline=OUTLINE_WARN)


def main():
    FloatBall()


if __name__ == "__main__":
    main()
