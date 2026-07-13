"""
FF8 input + screen bridge — lets the assistant "play" the game.

Sends DirectInput-compatible scancodes (SendInput with KEYEVENTF_SCANCODE)
to the focused FF8 window and captures screenshots for feedback.

Button map comes from the user's real bindings in
Documents/Square Enix/FINAL FANTASY VIII Steam/ff8input.cfg (Keyboard section).

Usage:
    python pipeline/ff8input.py buttons                 # show button -> key map
    python pipeline/ff8input.py press ok                # tap one button
    python pipeline/ff8input.py seq "down down ok"      # sequence (default 0.35s between)
    python pipeline/ff8input.py seq "up:1.0 ok" --delay 0.5   # hold 'up' 1s, then ok
    python pipeline/ff8input.py shot [out.png]          # screenshot of the FF8 window
"""

import argparse
import ctypes
import json
import pathlib
import sys
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

RECORDINGS_DIR = pathlib.Path(__file__).resolve().parent / "recordings"

# Virtual-key codes for the same physical keys as FF8_BUTTONS (for polling)
FF8_BUTTON_VKS = {
    "menu": 0x44,     # D
    "ok": 0x58,       # X
    "misc": 0x41,     # A
    "cancel": 0x57,   # W
    "toggle": 0x51,   # Q  (L1)
    "trigger": 0x45,  # E  (R1)
    "rotlt": 0x5A,    # Z  (L2)
    "rotrt": 0x43,    # C  (R2)
    "start": 0x53,    # S
    "select": 0x46,   # F
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}

# DirectInput scancodes from ff8input.cfg (Keyboard). Values >= 128 are
# extended keys (0xE0 prefix), e.g. arrows.
FF8_BUTTONS = {
    # PSX pad semantics for FF8 US: cross=confirm, circle=cancel
    "menu": 32,       # 'D'  (Triangle - menu/draw)
    "ok": 45,         # 'X'  (Cross - confirm/talk)
    "misc": 30,       # 'A'  (Square - misc/card)
    "cancel": 17,     # 'W'  (Circle - cancel)
    "toggle": 16,     # 'Q'
    "trigger": 18,    # 'E'
    "rotlt": 44,      # 'Z'  (L1)
    "rotrt": 46,      # 'C'  (R1)
    "start": 31,      # 'S'
    "select": 33,     # 'F'
    "up": 200,
    "down": 208,
    "left": 203,
    "right": 205,
}

KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUT_UNION(ctypes.Union):
    # Must list all three real members — SendInput validates cbSize against
    # the OS's true sizeof(INPUT), which is sized to the largest member
    # (MOUSEINPUT). Omitting mi/hi silently shrinks our struct and every
    # SendInput call fails with ERROR_INVALID_PARAMETER (87), returning 0.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _send_scan(code: int, keyup: bool):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if keyup else 0)
    scan = code
    if code >= 128:  # extended key (arrows...)
        scan = code - 128
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT(type=1)  # INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(0, scan, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _ff8_pids():
    """PIDs of running FF8_EN.exe processes."""
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq FF8_EN.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = line.split('","')
        if len(parts) > 1 and "FF8_EN" in parts[0]:
            pids.add(int(parts[1].strip('"')))
    return pids


def find_ff8_window():
    """Return (hwnd, title) of the FF8_EN.exe main window, or None."""
    pids = _ff8_pids()
    if not pids:
        return None
    result = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                result.append((hwnd, buf.value))
        return True

    user32.EnumWindows(enum_proc, 0)
    return result[0] if result else None


def _send_vk(vk: int, keyup: bool):
    inp = INPUT(type=1)
    inp.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if keyup else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def focus_ff8() -> bool:
    win = find_ff8_window()
    if not win:
        print("[error] FF8 window not found", file=sys.stderr)
        return False
    hwnd, title = win
    for _ in range(5):
        if user32.GetForegroundWindow() == hwnd:
            return True
        # Alt tap releases the foreground lock so SetForegroundWindow works
        _send_vk(0x12, False)  # VK_MENU down
        _send_vk(0x12, True)   # VK_MENU up
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.25)
    if user32.GetForegroundWindow() != hwnd:
        print("[error] Could not bring FF8 to foreground — not sending keys.", file=sys.stderr)
        return False
    return True


def press(button: str, hold: float = 0.08):
    code = FF8_BUTTONS[button.lower()]
    _send_scan(code, keyup=False)
    time.sleep(hold)
    _send_scan(code, keyup=True)


def run_sequence(seq: str, delay: float = 0.35):
    """seq: space-separated buttons, each optionally 'button:holdSeconds'."""
    if not focus_ff8():
        return 1
    for item in seq.split():
        if ":" in item:
            name, hold = item.split(":", 1)
            press(name, float(hold))
        else:
            press(item)
        time.sleep(delay)
    return 0


def screenshot(out_path: str, focus: bool = False) -> int:
    from PIL import ImageGrab
    if focus:
        focus_ff8()
        time.sleep(0.25)
    win = find_ff8_window()
    bbox = None
    if win:
        rect = wintypes.RECT()
        user32.GetWindowRect(win[0], ctypes.byref(rect))
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
    img = ImageGrab.grab(bbox=bbox)
    img.save(out_path)
    print(f"[ok] screenshot -> {out_path}" + (f" (window: {win[1]})" if win else " (full screen, window not found)"))
    return 0


def record(name: str, stop_button: str = "rotrt", timeout: float = 600.0) -> int:
    """Poll the FF8 keys at ~250Hz and save a press/release timeline.

    Recording starts at the first key event and stops when stop_button
    (default rotrt = R2 = 'C') is pressed.
    """
    RECORDINGS_DIR.mkdir(exist_ok=True)
    out = RECORDINGS_DIR / f"{name}.json"
    print(f"[rec] Armed. Play in the game window — recording starts on your first input.")
    print(f"[rec] Press {stop_button.upper()} (R2 / 'C' key) to stop and save.")
    state = {b: False for b in FF8_BUTTON_VKS}
    events = []
    t0 = None
    start_wall = time.perf_counter()
    while True:
        now = time.perf_counter()
        if now - start_wall > timeout:
            print("[rec] Timeout reached, saving what was captured.", file=sys.stderr)
            break
        stopped = False
        for button, vk in FF8_BUTTON_VKS.items():
            down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            if down != state[button]:
                state[button] = down
                if button == stop_button:
                    if down:
                        stopped = True
                    break
                if t0 is None:
                    t0 = now
                events.append({"b": button, "d": int(down), "t": round(now - t0, 4)})
        if stopped:
            break
        time.sleep(0.004)
    # close any still-held buttons at the end of the timeline
    if t0 is not None:
        t_end = time.perf_counter() - t0
        for button, down in state.items():
            if down and button != stop_button:
                events.append({"b": button, "d": 0, "t": round(t_end, 4)})
    out.write_text(json.dumps({"events": events}, indent=1), encoding="utf-8")
    print(f"[rec] Saved {len(events)} events ({events[-1]['t'] if events else 0:.1f}s) -> {out}")
    return 0


def replay(name: str, speed: float = 1.0) -> int:
    """Replay a recorded timeline into the focused FF8 window."""
    path = RECORDINGS_DIR / f"{name}.json"
    if not path.exists():
        print(f"[error] No recording: {path}", file=sys.stderr)
        return 1
    events = json.loads(path.read_text(encoding="utf-8"))["events"]
    if not focus_ff8():
        return 1
    print(f"[play] Replaying {len(events)} events from {name} (speed x{speed})...")
    t0 = time.perf_counter()
    for ev in events:
        target = t0 + ev["t"] / speed
        while (d := target - time.perf_counter()) > 0:
            time.sleep(min(d, 0.01))
        _send_scan(FF8_BUTTONS[ev["b"]], keyup=(ev["d"] == 0))
    print("[play] Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ff8input")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("buttons")
    p_press = sub.add_parser("press")
    p_press.add_argument("button", choices=sorted(FF8_BUTTONS))
    p_seq = sub.add_parser("seq")
    p_seq.add_argument("sequence")
    p_seq.add_argument("--delay", type=float, default=0.35)
    p_shot = sub.add_parser("shot")
    p_shot.add_argument("output", nargs="?", default="ff8_screen.png")
    p_shot.add_argument("--focus", action="store_true", help="Bring the game to front before capturing")
    p_rec = sub.add_parser("record")
    p_rec.add_argument("name")
    p_rec.add_argument("--timeout", type=float, default=600.0)
    p_play = sub.add_parser("replay")
    p_play.add_argument("name")
    p_play.add_argument("--speed", type=float, default=1.0)

    args = parser.parse_args()
    if args.command == "buttons":
        for name, code in FF8_BUTTONS.items():
            print(f"{name:8s} scan={code}")
        return 0
    if args.command == "press":
        if not focus_ff8():
            return 1
        press(args.button)
        return 0
    if args.command == "seq":
        return run_sequence(args.sequence, args.delay)
    if args.command == "shot":
        return screenshot(args.output, focus=args.focus)
    if args.command == "record":
        return record(args.name, timeout=args.timeout)
    if args.command == "replay":
        return replay(args.name, speed=args.speed)
    return 1


if __name__ == "__main__":
    sys.exit(main())
