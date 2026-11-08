"""List Windows game windows and capture a client-area screenshot.

This helper only reads the screen. It does not click or send keys.
Requires Windows and Pillow.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys

from PIL import Image


def world_hud_visible(image: Image.Image) -> bool:
    """Recognize the F3 keycap, away from changing world scenery."""
    pixels = [image.getpixel((x, y))
              for x in range(1428, 1465)
              for y in range(90, 115)]
    pale = sum(min(rgb) > 215 and max(rgb) - min(rgb) < 35 for rgb in pixels)
    glyph = sum(max(rgb) < 100 for rgb in pixels)
    return pale >= 300 and glyph >= 20


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
user32.PrintWindow.restype = wintypes.BOOL

VENDOR = Path(__file__).resolve().parent / "vendor"
for _path in (VENDOR, VENDOR / "win32", VENDOR / "win32" / "lib",
              VENDOR / "pythonwin"):
    if _path.is_dir():
        sys.path.insert(0, str(_path))
_dll_directory = (os.add_dll_directory(str(VENDOR / "pywin32_system32"))
                  if (VENDOR / "pywin32_system32").is_dir() else None)
import win32gui  # noqa: E402
import win32ui  # noqa: E402


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (ENUM_WINDOWS_PROC, wintypes.LPARAM)
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(POINT))
user32.ClientToScreen.restype = wintypes.BOOL


def visible_windows() -> list[tuple[int, str]]:
    windows: list[tuple[int, str]] = []

    @ENUM_WINDOWS_PROC
    def callback(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if title:
                windows.append((hwnd, title))
        return True

    if not user32.EnumWindows(callback, 0) and ctypes.get_last_error():
        raise OSError(ctypes.get_last_error(), "EnumWindows failed")
    return windows


def client_box(hwnd: int) -> tuple[int, int, int, int]:
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError(ctypes.get_last_error(), "GetClientRect failed")
    origin = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise OSError(ctypes.get_last_error(), "ClientToScreen failed")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise ValueError("The selected window has no visible client area")
    return origin.x, origin.y, origin.x + width, origin.y + height


def window_frame(hwnd: int) -> Image.Image:
    """Capture the game's client pixels without desktop-window occlusion."""
    left, top, right, bottom = client_box(hwnd)
    width, height = right - left, bottom - top
    source = win32gui.GetWindowDC(hwnd)
    if not source:
        raise OSError(ctypes.get_last_error(), "GetWindowDC failed")
    window_dc = win32ui.CreateDCFromHandle(source)
    memory_dc = window_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(window_dc, width, height)
        memory_dc.SelectObject(bitmap)
        # PW_CLIENTONLY | PW_RENDERFULLCONTENT. Both flags are needed for
        # this DirectX client; the traditional PrintWindow flags yield white.
        if not user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 3):
            raise OSError(ctypes.get_last_error(), "PrintWindow failed")
        image = Image.frombuffer("RGB", (width, height), bitmap.GetBitmapBits(True),
                                 "raw", "BGRX", 0, 1).copy()
        return image
    finally:
        memory_dc.DeleteDC()
        window_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, source)
        if bitmap.GetHandle():
            win32gui.DeleteObject(bitmap.GetHandle())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list visible window titles")
    parser.add_argument("--title", default="洛克王国", help="part of the game window title")
    parser.add_argument("--output", type=Path, help="path for the captured PNG")
    args = parser.parse_args()

    # Prevent Windows display scaling from shifting capture coordinates.
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass

    windows = visible_windows()
    if args.list:
        for hwnd, title in windows:
            print(f"{hwnd:>10}  {title}")
        return 0

    matches = [(hwnd, title) for hwnd, title in windows if args.title.casefold() in title.casefold()]
    if not matches:
        print(f"No visible window title contains {args.title!r}. Try --list.", file=sys.stderr)
        return 2
    if len(matches) > 1:
        print("More than one window matches. Use a more specific --title:", file=sys.stderr)
        for _, title in matches:
            print(f"  {title}", file=sys.stderr)
        return 2

    hwnd, title = matches[0]
    box = client_box(hwnd)
    output = args.output or Path.cwd() / "game_capture.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    window_frame(hwnd).save(output)
    print(f"Saved {title!r} client area ({box[2] - box[0]}x{box[3] - box[1]}) to {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
