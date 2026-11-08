"""Select the Bug/Grass flower target for the Fire pet, then teleport there.

Run from the game world or flower list. The target label is verified against
flower_target_label.png before any teleport click. UI art, row order, and
coordinates were calibrated on the 1920x1080 PC client.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from flower_driver import (capture, client_box, ensure_flower_page,
                           find_game, focus, swipe, touch, user32)
from game_capture import window_frame

TEMPLATE = Path(__file__).with_name("flower_target_label.png")


def frame(hwnd: int) -> Image.Image:
    left, top, right, bottom = client_box(hwnd)
    if (right - left, bottom - top) != (1920, 1080):
        raise RuntimeError("Flower selector needs a 1920x1080 game client")
    return window_frame(hwnd)


def content_digest(image: Image.Image) -> Image.Image:
    return image.crop((300, 150, 1800, 1000)).convert("L").resize((150, 85))


def difference(a: Image.Image, b: Image.Image) -> float:
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def find_target_label(image: Image.Image, label: Image.Image) -> tuple[float, int]:
    grey = image.convert("L")
    return min((difference(grey.crop((590, y, 730, y + 42)), label), y)
               for y in range(132, 970, 2))


def scrollbar_thumb(image: Image.Image) -> tuple[int, int] | None:
    """Locate the light draggable thumb at x=1807, if currently visible."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for y in range(135, 970):
        r, g, b = image.getpixel((1807, y))
        light = r > 240 and g > 230 and b > 215
        if light and start is None:
            start = y
        elif not light and start is not None:
            runs.append((start, y - 1))
            start = None
    if start is not None:
        runs.append((start, 969))
    return max((run for run in runs if run[1] - run[0] > 80),
               key=lambda run: run[1] - run[0], default=None)


def teleport_to_match(hwnd: int, y: int, image: Image.Image, output: Path) -> None:
    image.save(output / "verified_target.png")
    touch(hwnd, 1650, y + 52)
    time.sleep(1)
    capture(hwnd, output / "map_detail.png")
    touch(hwnd, 1530, 1015)
    time.sleep(3)
    capture(hwnd, output / "arrival.png")
    print("Teleported to verified Bug/Grass flower target", flush=True)


def select_and_teleport(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    user32.SetProcessDPIAware()
    hwnd, _ = find_game("\u6d1b\u514b\u738b\u56fd")
    ensure_flower_page(hwnd)
    label = Image.open(TEMPLATE).convert("L")

    image = frame(hwnd)
    score, y = find_target_label(image, label)
    if score < 13.0:
        teleport_to_match(hwnd, y, image, output)
        return 0

    # Drag the thumb to the top when it is visible. When already at the top,
    # the thumb is hidden above the list viewport.
    thumb = scrollbar_thumb(frame(hwnd))
    if thumb:
        focus(hwnd)
        swipe(hwnd, 1807, sum(thumb) // 2, 1807, 150, duration=0.7)
        time.sleep(0.55)

    best = (255.0, -1)
    stalls = 0
    for index in range(18):
        image = frame(hwnd)
        score, y = find_target_label(image, label)
        print(f"scroll {index}: target score {score:.1f} at y={y}", flush=True)
        if score < 13.0:
            teleport_to_match(hwnd, y, image, output)
            return 0
        if score < best[0]:
            best = (score, index)
        before = content_digest(image)
        focus(hwnd)
        thumb = scrollbar_thumb(image)
        if thumb:
            middle = sum(thumb) // 2
            swipe(hwnd, 1807, middle, 1807, min(middle + 80, 870), duration=0.6)
        else:
            swipe(hwnd, 900, 780, 900, 430, duration=0.6)
        time.sleep(0.55)
        after = content_digest(frame(hwnd))
        stalls = stalls + 1 if difference(before, after) < 1.0 else 0
        if stalls >= 3:
            raise RuntimeError(f"List stopped moving before target; best score {best}")
    raise RuntimeError(f"Target label not found; best score {best}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("work") / "fire_target")
    args = parser.parse_args()
    return select_and_teleport(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
