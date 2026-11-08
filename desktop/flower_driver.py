"""Direct Win32 input and automatic screenshots for the Roco Kingdom PC client.

Run from an interactive Windows desktop session. Requires Pillow for screenshots.
Coordinates are relative to the game window's client area.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time

from game_capture import POINT, client_box, visible_windows, window_frame, world_hud_visible


user32 = ctypes.WinDLL("user32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
VK_F3 = 0x72
VIRTUAL_KEYS = {"esc": 0x1B, "f3": VK_F3, "tab": 0x09, "enter": 0x0D,
                "space": 0x20,
                "x": 0x58, "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
                "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
                "5": 0x35, "f": 0x46}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", wintypes.DWORD), ("pointerId", wintypes.DWORD),
        ("frameId", wintypes.DWORD), ("pointerFlags", wintypes.DWORD),
        ("sourceDevice", wintypes.HANDLE), ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", POINT), ("ptHimetricLocation", POINT),
        ("ptPixelLocationRaw", POINT), ("ptHimetricLocationRaw", POINT),
        ("dwTime", wintypes.DWORD), ("historyCount", wintypes.DWORD),
        ("InputData", ctypes.c_int32), ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", ctypes.c_uint64), ("ButtonChangeType", wintypes.DWORD),
    ]


class POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO), ("touchFlags", wintypes.DWORD),
        ("touchMask", wintypes.DWORD), ("rcContact", wintypes.RECT),
        ("rcContactRaw", wintypes.RECT), ("orientation", wintypes.DWORD),
        ("pressure", wintypes.DWORD),
    ]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetProcessDPIAware.argtypes = ()
user32.SetProcessDPIAware.restype = wintypes.BOOL
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = (POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
user32.SetWindowPos.restype = wintypes.BOOL
user32.IsZoomed.argtypes = (wintypes.HWND,)
user32.IsZoomed.restype = wintypes.BOOL
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL
user32.mouse_event.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, ULONG_PTR)
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.keybd_event.argtypes = (ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, ULONG_PTR)
user32.InitializeTouchInjection.argtypes = (wintypes.DWORD, wintypes.DWORD)
user32.InitializeTouchInjection.restype = wintypes.BOOL
user32.InjectTouchInput.argtypes = (wintypes.DWORD, ctypes.POINTER(POINTER_TOUCH_INFO))
user32.InjectTouchInput.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
user32.SetWindowPos.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL


def send(*events: INPUT) -> None:
    inputs = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError(ctypes.get_last_error(), f"SendInput sent {sent}/{len(inputs)} events")


def focus(hwnd: int) -> None:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE: input needs a visible client
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    if user32.GetForegroundWindow() != hwnd:
        user32.keybd_event(0x12, 0x38, 0, 0)  # ALT briefly grants foreground activation
        user32.keybd_event(0x12, 0x38, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    if user32.GetForegroundWindow() != hwnd:
        raise RuntimeError("Could not focus the game window. Bring it to the foreground and retry.")


def press_key(name: str) -> None:
    try:
        vk = VIRTUAL_KEYS[name.casefold()]
    except KeyError:
        raise ValueError(f"Unsupported key: {name}") from None
    scan_code = user32.MapVirtualKeyW(vk, 0)
    if not scan_code:
        raise RuntimeError(f"Could not map {name} to a keyboard scan code")
    send(INPUT(type=INPUT_KEYBOARD,
               u=INPUT_UNION(ki=KEYBDINPUT(wScan=scan_code, dwFlags=KEYEVENTF_SCANCODE))))
    time.sleep(0.06)
    send(INPUT(type=INPUT_KEYBOARD,
               u=INPUT_UNION(ki=KEYBDINPUT(wScan=scan_code,
                                            dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP))))


def hold_key(name: str, seconds: float) -> None:
    vk = VIRTUAL_KEYS[name.casefold()]
    scan_code = user32.MapVirtualKeyW(vk, 0)
    send(INPUT(type=INPUT_KEYBOARD,
               u=INPUT_UNION(ki=KEYBDINPUT(wScan=scan_code, dwFlags=KEYEVENTF_SCANCODE))))
    try:
        time.sleep(seconds)
    finally:
        send(INPUT(type=INPUT_KEYBOARD,
                   u=INPUT_UNION(ki=KEYBDINPUT(wScan=scan_code,
                                                dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP))))


def click(hwnd: int, x: int, y: int) -> None:
    left, top, right, bottom = client_box(hwnd)
    if not (0 <= x < right - left and 0 <= y < bottom - top):
        raise ValueError(f"Click ({x}, {y}) is outside client area {right-left}x{bottom-top}")
    screen_left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    screen_top = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
    screen_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    screen_height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
    if screen_width < 2 or screen_height < 2:
        raise RuntimeError("Invalid virtual desktop dimensions")
    abs_x = round((left + x - screen_left) * 65535 / (screen_width - 1))
    abs_y = round((top + y - screen_top) * 65535 / (screen_height - 1))
    send(INPUT(type=INPUT_MOUSE,
               u=INPUT_UNION(mi=MOUSEINPUT(dx=abs_x, dy=abs_y,
                                           dwFlags=MOUSEEVENTF_MOVE |
                                                   MOUSEEVENTF_ABSOLUTE |
                                                   MOUSEEVENTF_VIRTUALDESK))))
    time.sleep(0.12)
    actual = POINT()
    if not user32.GetCursorPos(ctypes.byref(actual)):
        raise OSError(ctypes.get_last_error(), "GetCursorPos failed")
    owner = user32.GetAncestor(user32.WindowFromPoint(actual), 2)  # GA_ROOT
    print(f"Mouse target: expected=({left+x},{top+y}) actual=({actual.x},{actual.y}) game_window={owner == hwnd}")
    send(INPUT(type=INPUT_MOUSE, u=INPUT_UNION(mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTDOWN))))
    time.sleep(0.25)
    print(f"Windows left-button state while held: {bool(user32.GetAsyncKeyState(0x01) & 0x8000)}")
    send(INPUT(type=INPUT_MOUSE, u=INPUT_UNION(mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTUP))))


def capture(hwnd: int, output: Path) -> tuple[int, int]:
    left, top, right, bottom = client_box(hwnd)
    output.parent.mkdir(parents=True, exist_ok=True)
    window_frame(hwnd).save(output)
    return right - left, bottom - top


def click_post(hwnd: int, x: int, y: int) -> None:
    left, top, right, bottom = client_box(hwnd)
    if not (0 <= x < right - left and 0 <= y < bottom - top):
        raise ValueError(f"Click ({x}, {y}) is outside client area {right-left}x{bottom-top}")
    point = (y << 16) | (x & 0xFFFF)
    for message, buttons in ((0x0200, 0), (0x0201, 1), (0x0202, 0)):
        if not user32.PostMessageW(hwnd, message, buttons, point):
            raise OSError(ctypes.get_last_error(), f"PostMessageW failed: {message:#x}")
        time.sleep(0.04)


def click_legacy(hwnd: int, x: int, y: int) -> None:
    left, top, right, bottom = client_box(hwnd)
    if not (0 <= x < right - left and 0 <= y < bottom - top):
        raise ValueError(f"Click ({x}, {y}) is outside client area {right-left}x{bottom-top}")
    if not user32.SetCursorPos(left + x, top + y):
        raise OSError(ctypes.get_last_error(), "SetCursorPos failed")
    time.sleep(0.2)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.25)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def touch(hwnd: int, x: int, y: int) -> None:
    left, top, right, bottom = client_box(hwnd)
    if not (0 <= x < right - left and 0 <= y < bottom - top):
        raise ValueError(f"Touch ({x}, {y}) is outside client area {right-left}x{bottom-top}")
    if ctypes.sizeof(POINTER_INFO) != 96 or ctypes.sizeof(POINTER_TOUCH_INFO) != 144:
        raise RuntimeError("Unexpected Windows touch structure layout")
    sx, sy = left + x, top + y

    def exposed() -> bool:
        return user32.GetAncestor(user32.WindowFromPoint(POINT(sx, sy)), 2) == hwnd

    raised = False
    if user32.GetForegroundWindow() != hwnd or not exposed():
        try:
            focus(hwnd)
        except RuntimeError:
            pass
    if not exposed():
        if not user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 3):
            raise OSError(ctypes.get_last_error(), "Could not raise covered game window")
        raised = True
    try:
        if raised:
            focus(hwnd)
        if not exposed():
            raise RuntimeError(f"Game click target ({x}, {y}) is covered")
        if not user32.InitializeTouchInjection(1, 3):  # TOUCH_FEEDBACK_NONE
            raise OSError(ctypes.get_last_error(), "InitializeTouchInjection failed")
        contact = POINTER_TOUCH_INFO()
        contact.pointerInfo.pointerType = 2  # PT_TOUCH
        contact.pointerInfo.pointerId = 0
        contact.pointerInfo.ptPixelLocation = POINT(sx, sy)
        contact.rcContact = wintypes.RECT(sx - 2, sy - 2, sx + 2, sy + 2)
        contact.touchMask = 7  # CONTACTAREA | ORIENTATION | PRESSURE
        contact.orientation = 90
        contact.pressure = 512
        contact.pointerInfo.pointerFlags = 0x00010000 | 0x0002 | 0x0004  # DOWN|INRANGE|INCONTACT
        if not user32.InjectTouchInput(1, ctypes.byref(contact)):
            raise OSError(ctypes.get_last_error(), "InjectTouchInput DOWN failed")
        time.sleep(0.08)
        contact.pointerInfo.pointerFlags = 0x00040000  # UP
        if not user32.InjectTouchInput(1, ctypes.byref(contact)):
            raise OSError(ctypes.get_last_error(), "InjectTouchInput UP failed")
    finally:
        if raised:
            user32.SetWindowPos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, 3)


def swipe(hwnd: int, x1: int, y1: int, x2: int, y2: int, duration: float = 0.55) -> None:
    left, top, right, bottom = client_box(hwnd)
    for x, y in ((x1, y1), (x2, y2)):
        if not (0 <= x < right - left and 0 <= y < bottom - top):
            raise ValueError(f"Swipe point ({x}, {y}) is outside client area")
    if not user32.InitializeTouchInjection(1, 3):
        raise OSError(ctypes.get_last_error(), "InitializeTouchInjection failed")
    contact = POINTER_TOUCH_INFO()
    contact.pointerInfo.pointerType = 2
    contact.pointerInfo.pointerId = 0
    contact.touchMask = 7
    contact.orientation = 90
    contact.pressure = 512

    def frame(x: int, y: int, flags: int) -> None:
        sx, sy = left + x, top + y
        contact.pointerInfo.ptPixelLocation = POINT(sx, sy)
        contact.rcContact = wintypes.RECT(sx - 2, sy - 2, sx + 2, sy + 2)
        contact.pointerInfo.pointerFlags = flags
        if not user32.InjectTouchInput(1, ctypes.byref(contact)):
            raise OSError(ctypes.get_last_error(), f"InjectTouchInput frame failed at ({x}, {y})")

    frame(x1, y1, 0x00010000 | 0x0002 | 0x0004)
    steps = 24
    for i in range(1, steps + 1):
        time.sleep(duration / steps)
        x = round(x1 + (x2 - x1) * i / steps)
        y = round(y1 + (y2 - y1) * i / steps)
        frame(x, y, 0x00020000 | 0x0002 | 0x0004)
    frame(x2, y2, 0x00040000)


def ensure_game_size(hwnd: int) -> None:
    """Restore the calibrated 1920x1080 client before reading or tapping UI."""
    left, top, right, bottom = client_box(hwnd)
    current_width, current_height = right - left, bottom - top
    if (current_width, current_height) == (1920, 1080):
        return
    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.2)
        left, top, right, bottom = client_box(hwnd)
        current_width, current_height = right - left, bottom - top
    outer = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(outer)):
        raise OSError(ctypes.get_last_error(), "GetWindowRect failed")
    outer_width = 1920 + (outer.right - outer.left - current_width)
    outer_height = 1080 + (outer.bottom - outer.top - current_height)
    screen_width, screen_height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    if outer_width > screen_width or outer_height > screen_height:
        raise RuntimeError("Game needs a display large enough for a 1920x1080 client")
    x = max(0, min(outer.left, screen_width - outer_width))
    y = max(0, min(outer.top, screen_height - outer_height))
    if not user32.SetWindowPos(hwnd, 0, x, y, outer_width, outer_height, 0x0014):
        raise OSError(ctypes.get_last_error(), "SetWindowPos failed")
    time.sleep(0.35)
    left, top, right, bottom = client_box(hwnd)
    if (right - left, bottom - top) != (1920, 1080):
        raise RuntimeError(f"Could not set game client to 1920x1080: {right-left}x{bottom-top}")
    print("Game client resized to 1920x1080 for calibrated controls", flush=True)


def ensure_flower_page(hwnd: int) -> None:
    ensure_game_size(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        left, top, _, _ = client_box(hwnd)
        exposed = next(((x, y) for x, y in ((1800, 600), (1850, 800),
                                           (1400, 800), (1700, 800),
                                           (950, 800), (100, 800))
                        if user32.GetAncestor(user32.WindowFromPoint(
                            POINT(left + x, top + y)), 2) == hwnd), None)
        if exposed is None:
            raise RuntimeError("Game activation area is covered")
        for attempt in range(3):
            click_legacy(hwnd, *exposed)
            time.sleep(0.3)
            try:
                focus(hwnd)
                break
            except RuntimeError:
                if attempt == 2:
                    raise
    else:
        focus(hwnd)

    def state() -> str:
        frame = window_frame(hwnd).crop((0, 0, 1760, 320))
        if world_hud_visible(frame):
            return "world"
        # The selected 稀兽花种 tab has dark lettering at this fixed point.
        # Row/button colors vary with scrolling and must not classify the page.
        challenge = max(frame.getpixel((450, 55))) < 90
        return "challenge" if challenge else "other_manual"

    current = state()
    if current == "world":
        for attempt in range(3):
            focus(hwnd)
            press_key("f3")
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                time.sleep(0.2)
                current = state()
                if current != "world":
                    break
            if current != "world":
                break
            print(f"F3 did not open the manual yet; retry {attempt + 1}/3", flush=True)
    if current == "other_manual":
        for _ in range(3):
            touch(hwnd, 155, 285)
            time.sleep(0.6)
            current = state()
            if current == "challenge":
                break
    if current != "challenge":
        raise RuntimeError(f"Could not reach flower page; observed state={current}")


def find_game(title_fragment: str) -> tuple[int, str]:
    exact = [(hwnd, title) for hwnd, title in visible_windows()
             if title.strip() == "洛克王国：世界"]
    if len(exact) == 1:
        return exact[0]
    matches = [(hwnd, title) for hwnd, title in visible_windows()
               if title_fragment.casefold() in title.casefold()
               and "辅助" not in title and "助手" not in title]
    if len(matches) != 1:
        names = ", ".join(repr(title) for _, title in matches) or "none"
        raise RuntimeError(f"Expected one game window matching {title_fragment!r}; found {names}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="洛克王国", help="unique part of game window title")
    sub = parser.add_subparsers(dest="command", required=True)
    capture_parser = sub.add_parser("capture", help="capture game without sending input")
    capture_parser.add_argument("output", type=Path)
    key_parser = sub.add_parser("f3", help="press F3, then capture")
    key_parser.add_argument("output", type=Path)
    click_parser = sub.add_parser("click", help="experimental SendInput click, then capture")
    click_parser.add_argument("x", type=int)
    click_parser.add_argument("y", type=int)
    click_parser.add_argument("output", type=Path)
    post_parser = sub.add_parser("click-post", help="experimental window-message click, then capture")
    post_parser.add_argument("x", type=int)
    post_parser.add_argument("y", type=int)
    post_parser.add_argument("output", type=Path)
    legacy_parser = sub.add_parser("click-legacy", help="experimental mouse_event click, then capture")
    legacy_parser.add_argument("x", type=int)
    legacy_parser.add_argument("y", type=int)
    legacy_parser.add_argument("output", type=Path)
    touch_parser = sub.add_parser("touch", help="touch a foreground game window, then capture")
    touch_parser.add_argument("x", type=int)
    touch_parser.add_argument("y", type=int)
    touch_parser.add_argument("output", type=Path)
    touch_menu_parser = sub.add_parser("touch-menu", help="from world: activate, open F3 manual, touch second icon")
    touch_menu_parser.add_argument("output", type=Path)
    swipe_parser = sub.add_parser("flower-swipe", help="ensure flower page, swipe list up, then capture")
    swipe_parser.add_argument("output", type=Path)
    open_parser = sub.add_parser("flower-open", help="ensure flower page, then capture")
    open_parser.add_argument("output", type=Path)
    scan_parser = sub.add_parser("flower-scan", help="reset flower list to top and capture successive swipes")
    scan_parser.add_argument("directory", type=Path)
    teleport_parser = sub.add_parser("flower-teleport", help="scroll to top and teleport to Xiao Pi Qiu")
    teleport_parser.add_argument("output", type=Path)
    activate_parser = sub.add_parser("activate", help="activate game by clicking its exposed blank area")
    activate_parser.add_argument("output", type=Path)
    sequence_parser = sub.add_parser("sequence", help="send scan-code keys in one focus session, then capture")
    sequence_parser.add_argument("output", type=Path)
    sequence_parser.add_argument("keys", nargs="+")
    fifth_parser = sub.add_parser("select-fifth", help="activate game and select fifth pet")
    fifth_parser.add_argument("output", type=Path)
    cycle_parser = sub.add_parser("battle-cycle", help="confirm warning and cast ignite then full combustion")
    cycle_parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    user32.SetProcessDPIAware()
    hwnd, title = find_game(args.title)
    if args.command == "f3":
        focus(hwnd)
        press_key("f3")
        time.sleep(0.8)
    elif args.command == "sequence":
        focus(hwnd)
        for key in args.keys:
            press_key(key)
            time.sleep(0.5)
    elif args.command == "select-fifth":
        left, top, _, _ = client_box(hwnd)
        point = POINT(left + 1700, top + 800)
        if user32.GetAncestor(user32.WindowFromPoint(point), 2) != hwnd:
            raise RuntimeError("Game activation point is covered; no input sent")
        click_legacy(hwnd, 1700, 800)
        focus(hwnd)
        press_key("5")
        time.sleep(0.8)
    elif args.command == "battle-cycle":
        args.directory.mkdir(parents=True, exist_ok=True)
        touch(hwnd, 1110, 890)
        time.sleep(3)
        capture(hwnd, args.directory / "ready.png")
        touch(hwnd, 355, 420)
        time.sleep(0.8)
        touch(hwnd, 320, 560)
        time.sleep(0.8)
        capture(hwnd, args.directory / "after_pair.png")
        print("Sent ignite then full combustion")
        return 0
    elif args.command == "click":
        focus(hwnd)
        click(hwnd, args.x, args.y)
        time.sleep(0.5)
    elif args.command == "click-post":
        focus(hwnd)
        click_post(hwnd, args.x, args.y)
        time.sleep(0.5)
    elif args.command == "click-legacy":
        focus(hwnd)
        click_legacy(hwnd, args.x, args.y)
        time.sleep(0.5)
    elif args.command == "activate":
        left, top, right, bottom = client_box(hwnd)
        point = POINT(left + 1700, top + 800)
        if user32.GetAncestor(user32.WindowFromPoint(point), 2) != hwnd:
            raise RuntimeError("Game's blank activation point is covered; no click sent")
        click_legacy(hwnd, 1700, 800)
        time.sleep(0.2)
        if user32.GetForegroundWindow() != hwnd:
            raise RuntimeError("Game did not become foreground after activation click")
    elif args.command == "touch":
        if user32.GetForegroundWindow() != hwnd:
            left, top, _, _ = client_box(hwnd)
            point = POINT(left + args.x, top + args.y)
            if user32.GetAncestor(user32.WindowFromPoint(point), 2) != hwnd:
                raise RuntimeError("Target point is covered; no touch sent")
        touch(hwnd, args.x, args.y)
        time.sleep(0.5)
    elif args.command == "touch-menu":
        ensure_flower_page(hwnd)
    elif args.command == "flower-open":
        ensure_flower_page(hwnd)
    elif args.command == "flower-swipe":
        ensure_flower_page(hwnd)
        swipe(hwnd, 900, 850, 900, 250)
        time.sleep(0.6)
    elif args.command == "flower-scan":
        ensure_flower_page(hwnd)
        if user32.GetForegroundWindow() != hwnd:
            raise RuntimeError("Game lost focus before scanning")
        args.directory.mkdir(parents=True, exist_ok=True)
        previous = None
        for index in range(16):
            path = args.directory / f"{index:02}.png"
            capture(hwnd, path)
            from PIL import Image
            with Image.open(path) as saved:
                header = saved.convert("RGB")
                if not (all(c > 180 for c in header.getpixel((1000, 100)))
                        and all(c > 180 for c in header.getpixel((120, 290)))):
                    raise RuntimeError(f"Flower page disappeared at {path.name}; scan stopped")
                digest = saved.crop((300, 150, 1800, 1000)).convert("L").resize((150, 85))
                pixels = list(digest.get_flattened_data())
            if previous is not None:
                diff = sum(abs(a - b) for a, b in zip(previous, pixels)) / len(pixels)
                print(f"{path.name}: content difference {diff:.2f}")
                if diff < 1.0:
                    break
            else:
                print(f"{path.name}: top of list")
            previous = pixels
            swipe(hwnd, 900, 780, 900, 430, duration=0.6)
            time.sleep(0.55)
        return 0
    elif args.command == "flower-teleport":
        ensure_flower_page(hwnd)
        from PIL import Image
        def digest() -> list[int]:
            frame = window_frame(hwnd).crop((300, 150, 1800, 1000))
            return list(frame.convert("L").resize((150, 85)).get_flattened_data())

        for attempt in range(12):
            previous = digest()
            swipe(hwnd, 900, 300, 900, 850, duration=0.55)
            time.sleep(0.5)
            current = digest()
            diff = sum(abs(a - b) for a, b in zip(previous, current)) / len(current)
            print(f"scroll-to-top {attempt + 1}: difference {diff:.2f}")
            if diff < 1.0:
                break
        else:
            raise RuntimeError("Could not confirm top of flower list; no teleport sent")
        touch(hwnd, 1650, 450)
        time.sleep(2.5)
    width, height = capture(hwnd, args.output)
    print(f"{title.strip()} | {width}x{height} | saved {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
