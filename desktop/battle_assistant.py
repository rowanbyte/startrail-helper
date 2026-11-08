"""Watch the PC game and play Fuel Bug's flower battle automatically.

Run this BEFORE entering the battle. It waits for the combat HUD, then casts
Ignite -> Full Combustion repeatedly and gathers energy when the next card is
unavailable. It stops when combat ends or its time limit is reached.

Usage:
    python battle_assistant.py --wait-seconds 120 --battle-seconds 90

The game client must be 16:9 and visible on screen. This script uses the
same Windows touch injection as flower_driver.py. Move the mouse to the upper
right corner to stop it immediately.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from flower_driver import (POINT, click_legacy, client_box, ensure_game_size, find_game, focus,
                           press_key, touch, user32)
from game_capture import window_frame, world_hud_visible
from prompt_detector import challenge_prompt


@dataclass(frozen=True)
class BattleState:
    combat: bool
    controls: bool
    ignite: bool
    combustion: bool


class CaptureResourcesUnavailable(RuntimeError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


SKILL_COST = {"ignite": 2, "combustion": 3}


def planned_action(next_skill: str, energy_remaining: int, enabled: bool) -> str:
    if energy_remaining < SKILL_COST[next_skill]:
        return "gather"
    return next_skill if enabled else "wait"


def network_overlay(image: Image.Image) -> bool:
    """Detect the centered white 网络连接中 label while game input is suspended."""
    def white_count(y: int) -> int:
        return sum(min(image.getpixel((x, y))) > 245 for x in range(880, 1040, 2))

    return white_count(610) >= 18 and white_count(620) >= 18


@lru_cache(maxsize=1)
def _energy_ocr_engine():
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    return OcrEngine.try_create_from_language(Language("zh-CN"))


async def _read_energy(image: Image.Image, engine) -> int | None:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    crop = image.crop((48, 925, 145, 1050))
    for scale in (1, 3, 5):
        candidate = crop.resize((97 * scale, 125 * scale)).convert("RGBA")
        writer = DataWriter()
        writer.write_bytes(candidate.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.RGBA8,
            candidate.width, candidate.height,
        )
        result = await engine.recognize_async(bitmap)
        recognized = " ".join(line.text for line in result.lines)
        normalized = recognized.upper()
        match = re.search(r"(?<![0-9A-Z])(\d{1,2}|[SZ])\s*/\s*[1I][0O](?!\d)", normalized)
        if match:
            amount = {"S": 5, "Z": 2}.get(match.group(1))
            amount = amount if amount is not None else int(match.group(1))
            if 0 <= amount <= 10:
                return amount
    return None


def visible_energy(image: Image.Image) -> int | None:
    try:
        engine = _energy_ocr_engine()
        return asyncio.run(_read_energy(image, engine)) if engine is not None else None
    except (ImportError, RuntimeError, OSError):
        return None


async def _capture_ocr_text(engine, image: Image.Image,
                            box: tuple[int, int, int, int], scale: int) -> str:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    crop = image.crop(box)
    candidate = crop.resize((crop.width * scale, crop.height * scale)).convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(candidate.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.RGBA8,
        candidate.width, candidate.height,
    )
    result = await engine.recognize_async(bitmap)
    return " ".join(line.text for line in result.lines).upper()


@lru_cache(maxsize=1)
def _star_digit_templates() -> dict[str, str]:
    return json.loads((Path(__file__).resolve().parent / "star_digits.json").read_text(encoding="utf-8"))


def _header_star_count(image: Image.Image, resource: str) -> int | None:
    """Read the fixed white counter glyphs without confusing the adjacent star icon."""
    left, right = ((1520, 1610) if resource == "blue" else (1729, 1795))
    image = image.convert("RGB")

    def white(x: int, y: int) -> bool:
        rgb = image.getpixel((x, y))
        return min(rgb) > 170 and max(rgb) - min(rgb) < 65

    columns = [x for x in range(left, right)
               if sum(white(x, y) for y in range(58, 73)) >= 2]
    runs: list[list[int]] = []
    for x in columns:
        if not runs or x > runs[-1][-1] + 1:
            runs.append([x])
        else:
            runs[-1].append(x)
    templates = _star_digit_templates()
    recognized = ""
    for run in runs:
        if len(run) < 4 or len(run) > 16:
            continue
        glyph = Image.new("L", (len(run), 15))
        for x in run:
            for y in range(58, 73):
                glyph.putpixel((x - run[0], y - 58), 255 if white(x, y) else 0)
        glyph = glyph.resize((12, 16), Image.Resampling.NEAREST)
        bits = "".join("1" if glyph.getpixel((x, y)) else "0"
                       for y in range(16) for x in range(12))
        scores = sorted((sum(a != b for a, b in zip(bits, pattern)), digit)
                        for digit, pattern in templates.items())
        if scores[0][0] > 45 or scores[1][0] - scores[0][0] < 4:
            return None
        recognized += scores[0][1]
    if resource == "blue":
        match = re.fullmatch(r"(\d{1,3})/\d{1,3}", recognized)
        return int(match.group(1)) if match else None
    return int(recognized) if re.fullmatch(r"\d{1,5}", recognized) else None


def capture_resource_count(image: Image.Image, resource: str) -> int | None:
    boxes = {"blue": (1480, 40, 1670, 95),
             "purple": (1685, 40, 1880, 95),
             "cost": (1080, 580, 1370, 680)}
    if resource not in boxes:
        raise ValueError(resource)
    if resource in {"blue", "purple"}:
        # Partial OCR reads (for example 340 as 40) must never decide whether
        # to switch currencies. An unknown digit is an unknown balance.
        return _header_star_count(image, resource)
    try:
        engine = _energy_ocr_engine()
        if engine is None:
            return None
        # The moving pet/background can obscure a wide OCR box. Read small
        # padded boxes in several positions, and require two matching reads.
        votes: dict[int, set[tuple[int, int, int]]] = {}
        boxes = ((1283, 602, 1329, 632), (1283, 612, 1329, 642),
                 (1288, 602, 1334, 632), (1288, 612, 1334, 642),
                 (1294, 623, 1335, 646), (1297, 623, 1335, 646))
        for left, top, right, bottom in boxes:
            crop = image.crop((left, top, right, bottom))
            for scale in (2, 4):
                padded = Image.new("RGB", (crop.width + 20, crop.height + 20), (24, 24, 24))
                padded.paste(crop, (10, 10))
                raw = asyncio.run(_capture_ocr_text(engine, padded,
                                                    (0, 0, padded.width, padded.height), scale))
                normalized = raw.translate(str.maketrans({"I": "1", "Z": "2", "O": "0", "S": "5"}))
                normalized = re.sub(r"\s+", "", normalized)
                if re.fullmatch(r"\d{1,3}", normalized):
                    value = int(normalized)
                    if value > 0:
                        votes.setdefault(value, set()).add((left, top, scale))
        winners = sorted(votes.items(), key=lambda item: len(item[1]), reverse=True)
        if winners and len(winners[0][1]) >= 2 and (
            len(winners) == 1 or len(winners[0][1]) > len(winners[1][1])
        ):
            return winners[0][0]
    except (ImportError, RuntimeError, OSError):
        return None
    return None


def active_pet_fainted(image: Image.Image) -> bool:
    """The leftmost health fill remains colored even at very low HP."""
    return not any(max(rgb) > 120 and max(rgb) - min(rgb) > 45
                   for x in range(109, 114)
                   for y in (79, 80, 81)
                   for rgb in (image.getpixel((x, y)),))


def classify(image: Image.Image, generic: bool = False) -> BattleState:
    """Recognize the visible combat HUD and enabled skill cards by pixels."""
    # Full HP has a colored fill; near-zero HP exposes the dark track.
    bar = image.getpixel((790, 82))
    colored_bar = (bar[2] < 135 and
                   ((bar[1] > 140 and bar[1] > bar[0] + 25) or
                    (bar[0] > 180 and bar[1] > 115) or
                    (bar[0] > 115 and bar[1] < 120)))
    track = [image.getpixel((x, 82)) for x in (1000, 1200)]
    dark_track = all(25 <= min(rgb) <= 75 and max(rgb) - min(rgb) < 8 for rgb in track)
    combat = ((colored_bar or dark_track) and not world_hud_visible(image)
              and not capture_visible(image))
    bottom = image.getpixel((92, 960))
    controls = combat and bottom[0] > 225 and bottom[1] > 215 and bottom[2] < 245
    fire = image.getpixel((350, 420))
    burn = image.getpixel((320, 555))
    if generic:
        ignite = controls and max(fire) > 170
        combustion = controls and max(burn) > 170
    else:
        ignite = controls and fire[0] > 205 and fire[1] > 95 and fire[2] < 150
        combustion = controls and burn[0] > 205 and burn[1] > 95 and burn[2] < 150
    return BattleState(combat, controls, ignite, combustion)


def dialog_state(image: Image.Image) -> str:
    """Classify ordinary and destined flower panels and the party dialogs."""
    def dark(x: int, y: int) -> bool:
        r, g, b = image.getpixel((x, y))
        return max(r, g, b) < 95

    def light(x: int, y: int) -> bool:
        r, g, b = image.getpixel((x, y))
        return min(r, g, b) > 210

    if light(500, 400) and light(950, 400) and light(1030, 940):
        return "flower"
    if dark(500, 400) and dark(950, 400) and light(1030, 890):
        return "preparation"
    if dark(500, 400) and light(950, 400) and light(1030, 890):
        if light(565, 490):
            return "warning"
        return "picker"
    return "other"


async def _read_challenge_button(image: Image.Image, engine) -> tuple[int, int] | None:
    """Find the actual 挑战 button in the lower panel, including shifted layouts."""
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    left, top, right, bottom = 600, 820, 1350, 1010
    crop = image.crop((left, top, right, bottom))
    scale = 3
    candidate = crop.resize((crop.width * scale, crop.height * scale)).convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(candidate.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.RGBA8,
        candidate.width, candidate.height,
    )
    result = await engine.recognize_async(bitmap)
    for line in result.lines:
        if "挑战" not in re.sub(r"\s+", "", line.text):
            continue
        words = [word for word in line.words if any(char in word.text for char in "挑战")]
        if not words:
            continue
        x1 = min(word.bounding_rect.x for word in words)
        x2 = max(word.bounding_rect.x + word.bounding_rect.width for word in words)
        y1 = min(word.bounding_rect.y for word in words)
        y2 = max(word.bounding_rect.y + word.bounding_rect.height for word in words)
        return left + round((x1 + x2) / (2 * scale)), top + round((y1 + y2) / (2 * scale))
    return None


def challenge_button(image: Image.Image) -> tuple[int, int] | None:
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view

    template = _challenge_button_template()
    area = np.asarray(image.convert("L"))[800:1035:3, 850:1400:3].astype(np.int16)
    windows = sliding_window_view(area, template.shape)
    scores = np.mean(np.abs(windows - template), axis=(-2, -1))
    iy, ix = np.unravel_index(np.argmin(scores), scores.shape)
    candidate = windows[iy, ix]
    glyph_difference = np.mean((candidate < 115) != (template < 115))
    if scores[iy, ix] < 22 and glyph_difference < 0.075:
        return 850 + int(ix) * 3 + 90, 800 + int(iy) * 3 + 20
    try:
        engine = _energy_ocr_engine()
        return asyncio.run(_read_challenge_button(image, engine)) if engine is not None else None
    except (ImportError, RuntimeError, OSError):
        return None


@lru_cache(maxsize=1)
def _challenge_button_template():
    import numpy as np
    path = Path(__file__).resolve().parent / "assets" / "challenge_button.png"
    return np.asarray(Image.open(path).convert("L"))[::3, ::3].astype(np.int16)


def frame(hwnd: int) -> Image.Image:
    # Direct callers must use physical pixels too; otherwise Windows scaling
    # can crop out the bottom buttons before this image is normalized.
    user32.SetProcessDPIAware()
    left, top, right, bottom = client_box(hwnd)
    width, height = right - left, bottom - top
    if width < 960 or height < 540 or abs(width / height - 16 / 9) > 0.02:
        raise RuntimeError(f"Unexpected game client size: {width}x{height}")
    image = window_frame(hwnd)
    if (width, height) != (1920, 1080):
        image = image.resize((1920, 1080), Image.Resampling.BILINEAR)
    return image


def scaled_point(hwnd: int, x: int, y: int) -> tuple[int, int]:
    left, top, right, bottom = client_box(hwnd)
    return round(x * (right - left) / 1920), round(y * (bottom - top) / 1080)


def tap(hwnd: int, x: int, y: int) -> None:
    touch(hwnd, *scaled_point(hwnd, x, y))


def still_exposed(hwnd: int) -> bool:
    left, top, _, _ = client_box(hwnd)
    x, y = scaled_point(hwnd, 1700, 800)
    point = POINT(left + x, top + y)
    return user32.GetAncestor(user32.WindowFromPoint(point), 2) == hwnd


def mouse_abort() -> bool:
    point = POINT()
    user32.GetCursorPos(__import__("ctypes").byref(point))
    return point.x >= user32.GetSystemMetrics(0) - 8 and point.y <= 8


def wait_for_dialog(hwnd: int, desired: str, seconds: float = 12) -> None:
    deadline = time.monotonic() + seconds
    seen = "other"
    while time.monotonic() < deadline:
        observed = dialog_state(frame(hwnd))
        if observed != seen:
            print(f"Dialog transition: {seen} -> {observed}; waiting for {desired}", flush=True)
            seen = observed
        if seen == desired:
            return
        time.sleep(0.1)
    raise RuntimeError(f"Expected {desired} panel; last observed {seen}")


def enter_battle(hwnd: int, party_slot: int = 5) -> None:
    """From the nearby flower or an open challenge panel, select a party slot."""
    if not 1 <= party_slot <= 6:
        raise ValueError("Party slot must be 1–6")
    if user32.GetForegroundWindow() != hwnd:
        focus(hwnd)
    deadline = time.monotonic() + 55
    last_state = ""
    last_action_at = 0.0
    party_selected = False
    while time.monotonic() < deadline:
        image = frame(hwnd)
        if classify(image, generic=party_slot != 5).combat:
            print(f"Entered battle with party slot {party_slot}", flush=True)
            return
        state = dialog_state(image)
        if state != last_state:
            print(f"Battle entry panel: {last_state or 'initial'} -> {state}", flush=True)
            last_state = state
        if time.monotonic() - last_action_at < 1.5:
            time.sleep(0.1)
            continue
        if state == "other":
            button = challenge_button(image)
            if button is not None:
                print(f"Final challenge button detected at {button}", flush=True)
                tap(hwnd, *button)
                last_action_at = time.monotonic()
                time.sleep(0.1)
                continue
            point = challenge_prompt(image)
            if point is None:
                time.sleep(0.1)  # loading or transition animation
                continue
            tap(hwnd, *point)
        elif state == "flower":
            button = challenge_button(image)
            tap(hwnd, *(button or (1110, 937)))
        elif state == "preparation":
            tap(hwnd, 1110, 890) if party_selected else tap(hwnd, 605, 535)
        elif state == "picker":
            slot_x = (590, 740, 890, 1035, 1190, 1330)[party_slot - 1]
            selected_color = image.getpixel((slot_x - 20, 540))
            selected = (selected_color[0] > 235 and
                        165 < selected_color[1] < 220 and
                        selected_color[2] < 130)
            if not selected:
                tap(hwnd, slot_x, 570)
                time.sleep(0.15)
            tap(hwnd, 1110, 890)
            party_selected = True
        elif state == "warning":
            tap(hwnd, 1110, 890)
            party_selected = True
        last_action_at = time.monotonic()
        time.sleep(0.1)
    raise RuntimeError(f"Battle did not start; last panel: {last_state}")


def capture_visible(image: Image.Image) -> bool:
    star = image.getpixel((1505, 60))
    left_counter = image.getpixel((1700, 65))
    right_counter = image.getpixel((1850, 65))
    purple_tab = image.getpixel((1825, 135))
    # A blue sky can match the star icon's single pixel. The capture screen
    # also has two fixed dark currency counters and a magenta currency tab.
    if (star[0] < 80 and 80 < star[1] < 180 and star[2] > 220
            and max(left_counter) < 65 and max(right_counter) < 65
            and purple_tab[0] > 210 and purple_tab[2] > 210
            and purple_tab[1] < 180):
        return True
    # Legendary captures replace the purple counter/tab. Recognize the fixed
    # capture-cost heading instead of requiring purple pixels.
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view
    template = _capture_heading_template()
    area = np.asarray(image.convert("L"))[480:800:3, 1000:1450:3].astype(np.int16)
    windows = sliding_window_view(area, template.shape)
    scores = np.mean(np.abs(windows - template), axis=(-2, -1))
    iy, ix = np.unravel_index(np.argmin(scores), scores.shape)
    glyph_difference = np.mean((windows[iy, ix] < 170) != (template < 170))
    return bool(scores[iy, ix] < 25 and glyph_difference < 0.10)


@lru_cache(maxsize=1)
def _capture_heading_template():
    import numpy as np
    path = Path(__file__).resolve().parent / "assets" / "capture_cost_heading.png"
    return np.asarray(Image.open(path).convert("L"))[::3, ::3].astype(np.int16)


@lru_cache(maxsize=1)
def _reward_heading_template():
    import numpy as np
    path = Path(__file__).resolve().parent / "assets" / "reward_heading.png"
    return np.asarray(Image.open(path).convert("L"))[::2, ::2].astype(np.int16)


def reward_visible(image: Image.Image) -> bool:
    """Find 获得奖励 across layouts with different numbers of reward rows."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view

    template = _reward_heading_template()
    area = np.asarray(image.convert("L"))[280:580:2, 200:430:2].astype(np.int16)
    windows = sliding_window_view(area, template.shape)
    scores = np.mean(np.abs(windows - template), axis=(-2, -1))
    iy, ix = np.unravel_index(np.argmin(scores), scores.shape)
    glyph_difference = np.mean((windows[iy, ix] < 170) != (template < 170))
    if scores[iy, ix] < 30 and glyph_difference < 0.12:
        return True
    try:
        engine = _energy_ocr_engine()
        if engine is None:
            return False
        for box in ((190, 430, 400, 480), (190, 500, 400, 550)):
            for scale in (1, 2):
                raw = asyncio.run(_capture_ocr_text(engine, image, box, scale))
                if "得奖" in re.sub(r"\s+", "", raw):
                    return True
    except (ImportError, RuntimeError, OSError):
        pass
    return False


def escape_confirm_visible(image: Image.Image) -> bool:
    header = image.getpixel((800, 395))
    panel = image.getpixel((800, 580))
    yes_button = image.getpixel((1200, 900))  # blank area, away from the dark 是 glyph
    return max(header) < 95 and min(panel) > 215 and min(yes_button) > 215


def finish_capture(hwnd: int, log_dir: Path, stars: str = "purple", category: str = "flowers") -> bool:
    """Use the preferred stars, falling back to the other currency if needed."""
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        image = frame(hwnd)
        if capture_visible(image):
            break
        time.sleep(0.15)
    else:
        frame(hwnd).save(log_dir / "capture_not_found.png")
        return False
    # The capture HUD remains usable when the active pet has fainted but the
    # Boss dies from a delayed effect. The HUD, not the pet HP, decides this.
    # The capture overlay appears before it accepts taps on some flowers.
    time.sleep(0.9)
    if user32.GetForegroundWindow() != hwnd:
        focus(hwnd)
    if category == "legends":
        if stars not in {"blue", "legendary"}:
            raise ValueError("传说捕捉只支持蓝星周次数或专用印记")
        panel = frame(hwnd)
        blue_icon = sum(b > 170 and b > r + 35 and g > 80
                        for x in range(1700, 1750, 2) for y in range(120, 151, 2)
                        for r, g, b in (panel.getpixel((x, y)),))
        gold_icon = sum(r > 180 and g > 100 and b < 140 and r > b + 50
                        for x in range(1800, 1855, 2) for y in range(120, 151, 2)
                        for r, g, b in (panel.getpixel((x, y)),))
        if blue_icon < 15 or gold_icon < 15:
            panel.save(log_dir / "legendary_resource_layout_unknown.png")
            raise CaptureResourcesUnavailable("legendary_resource_unconfirmed",
                                              "传说捕捉资源面板与预期不符，停止并保存截图；未投球")
        tap(hwnd, 1720 if stars == "blue" else 1825, 136)
        time.sleep(0.3)
        selected_image = frame(hwnd)
        selected_image.save(log_dir / "legendary_resource.png")
        blue_light = sum(selected_image.getpixel((1700, 136)))
        mark_light = sum(selected_image.getpixel((1850, 136)))
        if (stars == "blue" and blue_light <= mark_light) or (stars == "legendary" and mark_light <= blue_light):
            raise CaptureResourcesUnavailable("legendary_resource_unconfirmed",
                                              "无法确认所选传说捕捉资源；未投球、未改用其他印记")
        (log_dir / "capture_resource_check.json").write_text(json.dumps({
            "category": category, "preferred": stars, "selected": stars,
            "fallback_allowed": False,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return throw_and_confirm_capture(hwnd, log_dir, stars)
    if stars not in {"purple", "blue"}:
        raise ValueError(f"Invalid star currency: {stars}")
    resource_image = frame(hwnd)
    resource_image.save(log_dir / "capture_resources.png")
    balances = {color: capture_resource_count(resource_image, color)
                for color in ("blue", "purple")}
    other = "blue" if stars == "purple" else "purple"
    checked: dict[str, dict[str, int | None]] = {}
    selected: str | None = None
    for color in (stars, other):
        balance = balances[color]
        if balance is None:
            checked[color] = {"balance": balance, "cost": None}
            if color == stars:
                break  # An unreadable preferred balance is not proof of shortage.
            continue
        if balance == 0:
            checked[color] = {"balance": balance, "cost": None}
            continue
        tap(hwnd, 1825 if color == "purple" else 1720, 136)
        time.sleep(0.2)
        currency_image = frame(hwnd)
        currency_image.save(log_dir / f"{color}_currency.png")
        blue_light = sum(currency_image.getpixel((1700, 136)))
        purple_light = sum(currency_image.getpixel((1850, 136)))
        if (color == "purple" and purple_light <= blue_light) or (
            color == "blue" and blue_light <= purple_light
        ):
            raise RuntimeError(f"Could not confirm selected {color} currency")
        cost = capture_resource_count(currency_image, "cost")
        checked[color] = {"balance": balance, "cost": cost}
        if cost is None:
            # Preserve the user's choice. Let the game accept or reject the
            # capture; missing OCR must not silently change the currency.
            selected = color
            print(f"{color} cost unreadable; keeping selected currency (balance={balance})",
                  flush=True)
            break
        if balance >= cost:
            selected = color
            break
        print(f"{color} stars insufficient: balance={balance}, cost={cost}; checking {other if color == stars else 'stop'}",
              flush=True)
    (log_dir / "capture_resource_check.json").write_text(json.dumps({
        "preferred": stars, "balances": balances, "checked": checked,
        "selected": selected,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if selected is None:
        readable = all(balance is not None for balance in balances.values()) and all(
            item["cost"] is not None or item["balance"] == 0 for item in checked.values()
        )
        reason = "stars_exhausted" if readable else "stars_unreadable"
        raise CaptureResourcesUnavailable(
            reason, f"Cannot capture: blue={balances['blue']}, purple={balances['purple']}"
        )
    if selected != stars:
        print(f"Preferred {stars} stars unavailable; using {selected} stars", flush=True)
    return throw_and_confirm_capture(hwnd, log_dir, selected)


def throw_and_confirm_capture(hwnd: int, log_dir: Path, stars: str) -> bool:
    for attempt in range(4):
        tap(hwnd, 305, 343)  # first, run-exclusive ball
        time.sleep(0.4)
        selected_image = frame(hwnd)
        r, g, b = selected_image.getpixel((300, 380))
        if r > 245 and 150 < g < 225 and b < 140:
            break
        print(f"Exclusive ball selection retry {attempt + 1}", flush=True)
        time.sleep(0.4)
    else:
        selected_image.save(log_dir / "exclusive_ball_unconfirmed.png")
        return False
    selected_image.save(log_dir / "exclusive_ball.png")
    tap(hwnd, 1830, 980)  # capture
    time.sleep(0.5)
    tap(hwnd, 1200, 470)  # aim at the flower pet to throw the ball
    time.sleep(2.0)
    if capture_visible(frame(hwnd)):
        # A few large flower pets do not respond to the first throw position.
        press_key("space")
        time.sleep(0.35)
        tap(hwnd, 1200, 550)
    print(f"Selected {stars} stars and the run-exclusive ball; ball thrown", flush=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        image = frame(hwnd)
        if reward_visible(image):
            image.save(log_dir / "capture_result.png")
            print("Capture reward screen confirmed", flush=True)
            break
        time.sleep(0.2)
    else:
        frame(hwnd).save(log_dir / "capture_unconfirmed.png")
        return False
    deadline = time.monotonic() + 30
    next_tap = 0.0
    while time.monotonic() < deadline:
        image = frame(hwnd)
        r, g, b = image.getpixel((800, 1016))
        if r > 230 and g > 220 and b < 235:
            image.save(log_dir / "success.png")
            print("Capture result confirmed on success screen", flush=True)
            return True
        if time.monotonic() >= next_tap:
            tap(hwnd, 1650, 800)  # reward screens ignore taps during animation
            next_tap = time.monotonic() + 2.0
        time.sleep(0.2)
    frame(hwnd).save(log_dir / "capture_unconfirmed.png")
    return False


def run(wait_seconds: float, battle_seconds: float, log_dir: Path,
        enter: bool = False, capture: bool = False, stars: str = "purple",
        party_slot: int = 5, first_skill_only: bool = False,
        faint_wait_seconds: float = 120, category: str = "flowers") -> int:
    user32.SetProcessDPIAware()
    hwnd, title = find_game("\u6d1b\u514b\u738b\u56fd")
    ensure_game_size(hwnd)
    frame(hwnd)  # Check game aspect ratio before any input.
    log_dir.mkdir(parents=True, exist_ok=True)
    if enter:
        enter_battle(hwnd, party_slot)
    generic = party_slot != 5
    events: list[tuple[float, str, str]] = []
    observations: list[tuple[float, int, int, int, int]] = []
    next_observation = 0.0
    started = time.monotonic()
    battle_start: float | None = None
    last_action = 0.0
    next_skill = "ignite"
    energy_remaining = 10
    unavailable_since: float | None = None
    actions = 0
    reason = "wait_timeout"
    gathering = False
    gather_at = 0.0
    gather_attempts = 0
    gather_baseline: int | None = None
    cast_pending: str | None = None
    cast_at = 0.0
    cast_attempts = 0
    settle_until = 0.0
    faint_at: float | None = None
    dead_candidate_at: float | None = None
    next_faint_report = 0.0
    network_since: float | None = None

    print(f"Watching {title.strip()}. Waiting for combat...", flush=True)
    while True:
        now = time.monotonic()
        if mouse_abort():
            reason = "mouse_abort"
            break
        image = frame(hwnd)
        if network_overlay(image):
            network_since = network_since or now
            if now - network_since > 120:
                reason = "network_timeout"
                break
            time.sleep(0.25)
            continue
        if network_since is not None:
            paused = now - network_since
            started += paused
            battle_start = battle_start + paused if battle_start is not None else None
            faint_at = faint_at + paused if faint_at is not None else None
            unavailable_since = (unavailable_since + paused
                                 if unavailable_since is not None else None)
            dead_candidate_at = (dead_candidate_at + paused
                                 if dead_candidate_at is not None else None)
            cast_at += paused
            gather_at += paused
            last_action += paused
            settle_until += paused
            next_faint_report += paused
            print(f"Network connection restored after {paused:.1f}s; resuming battle", flush=True)
            network_since = None
        state = classify(image, generic=generic)
        elapsed = now - started
        if elapsed >= next_observation:
            observations.append((round(elapsed, 3), int(state.combat),
                                 int(state.controls), int(state.ignite),
                                 int(state.combustion)))
            next_observation = elapsed + 0.25
        if state.combat:
            if battle_start is None and state.controls and (state.ignite or state.combustion):
                battle_start = now
                print("Combat detected; starting skill loop", flush=True)
                events.append((now - started, "start", ""))
            pet_down = active_pet_fainted(image)
            if battle_start is None and pet_down:
                dead_candidate_at = dead_candidate_at or now
                if now - dead_candidate_at > 1.0:
                    battle_start = now
                    print("Combat detected with active pet already fainted", flush=True)
                    events.append((now - started, "start_fainted", ""))
            elif battle_start is None:
                dead_candidate_at = None
            if battle_start is not None:
                if pet_down and faint_at is None:
                    dead_candidate_at = dead_candidate_at or now
                    if now - dead_candidate_at > 1.0:
                        faint_at = now
                        next_faint_report = now + 5
                        print(f"{now - started:.2f}s: active pet fainted; waiting up to {faint_wait_seconds:g}s for Boss result",
                              flush=True)
                        events.append((now - started, "pet_fainted", ""))
                elif not pet_down:
                    dead_candidate_at = None
                    if faint_at is not None:
                        print("Active pet health returned; resuming skills", flush=True)
                        faint_at = None

        if capture_visible(image) and (battle_start is not None or capture):
            reason = "battle_ended"
            break

        if battle_start is None and now - started > wait_seconds:
            reason = "wait_timeout"
            break
        if faint_at is not None and now - faint_at > faint_wait_seconds:
            reason = "pet_fainted_timeout"
            break
        if faint_at is None and battle_start is not None and now - battle_start > battle_seconds:
            reason = "battle_timeout"
            break
        if faint_at is not None:
            if now >= next_faint_report:
                remaining = max(0, int(faint_wait_seconds - (now - faint_at)))
                print(f"Pet fainted; waiting for Boss result, {remaining}s remaining", flush=True)
                next_faint_report = now + 5
            time.sleep(0.1)
            continue

        if gathering and state.controls:
            measured = visible_energy(image)
            if measured is not None:
                energy_remaining = measured
            available = state.ignite if next_skill == "ignite" else state.combustion
            restored = (measured is not None and gather_baseline is not None
                        and measured > gather_baseline)
            if available or restored:
                print(f"{now - started:.2f}s: gather confirmed (next skill enabled)",
                      flush=True)
                events.append((now - started, "gather_confirmed", next_skill))
                gathering = False
                gather_attempts = 0
                gather_baseline = None
                unavailable_since = None
            elif now - gather_at > 2.0:
                if gather_attempts >= 3:
                    reason = "gather_unconfirmed"
                    break
                if user32.GetForegroundWindow() != hwnd:
                    focus(hwnd)
                tap(hwnd, 95, 966)
                gather_at = time.monotonic()
                gather_attempts += 1
                print(f"{gather_at - started:.2f}s: gather retry {gather_attempts}", flush=True)
                events.append((gather_at - started, "gather_retry", str(state)))
        if gathering:
            time.sleep(0.08)
            continue

        if cast_pending is not None:
            enabled = state.ignite if cast_pending == "ignite" else state.combustion
            if not state.controls or not enabled:
                events.append((now - started, "cast_confirmed", cast_pending))
                energy_remaining = max(0, energy_remaining - SKILL_COST[cast_pending])
                next_skill = "combustion" if cast_pending == "ignite" else "ignite"
                cast_pending = None
                settle_until = now + 0.2
                if first_skill_only and next_skill == "combustion":
                    reason = "first_skill_confirmed"
                    break
            elif now - cast_at > 0.5:
                if cast_attempts >= 7:
                    reason = "skill_unconfirmed"
                    break
                x, y = (355, 420) if cast_pending == "ignite" else (320, 555)
                tap(hwnd, x, y)
                cast_at = time.monotonic()
                cast_attempts += 1
                events.append((cast_at - started, "cast_retry", cast_pending))
            time.sleep(0.08)
            continue

        if state.controls and now >= settle_until and now - last_action >= 0.35:
            # The pet starts at 10 energy. Ignite costs 2 and Full Combustion
            # costs 3, so two pairs consume the bar. Gather only when the
            # next skill cannot be paid for, never after every pair.
            available = state.ignite if next_skill == "ignite" else state.combustion
            measured = visible_energy(image)
            if measured is not None:
                energy_remaining = measured
            action = planned_action(next_skill, energy_remaining, available)
            if action != "wait":
                unavailable_since = None
            else:
                unavailable_since = unavailable_since or now
                if now - unavailable_since > 5:
                    reason = "skill_unavailable_with_energy"
                    break
                time.sleep(0.08)
                continue
            positions = {"ignite": (355, 420),
                         "combustion": (320, 555),
                         "gather": (95, 966)}
            if user32.GetForegroundWindow() != hwnd:
                try:
                    focus(hwnd)
                except RuntimeError:
                    if not still_exposed(hwnd):
                        reason = "game_not_foreground"
                        break
                    click_legacy(hwnd, *scaled_point(hwnd, 1700, 800))
                    focus(hwnd)
            if action == "gather":
                gathering = True
                gather_baseline = measured
                tap(hwnd, 95, 966)
                gather_at = time.monotonic()
                gather_attempts = 1
            else:
                tap(hwnd, *positions[action])
                cast_pending = action
                cast_at = time.monotonic()
                cast_attempts = 1
            last_action = time.monotonic()
            actions += 1
            print(f"{last_action - started:.2f}s: {action}", flush=True)
            events.append((last_action - started, action,
                           f"energy={energy_remaining}; {state}"))
            if action == "gather":
                # An input is successful only when the energy digits change.
                last_action += 0.8
        time.sleep(0.08)

    final_image = frame(hwnd)
    final_image.save(log_dir / "last_frame.png")
    with (log_dir / "actions.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(("seconds", "action", "observed_state"))
        writer.writerows(events)
    with (log_dir / "observations.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(("seconds", "combat", "controls", "skill1_enabled", "skill2_enabled"))
        writer.writerows(observations)
    print(f"Stopped: {reason}; {actions} actions; log: {log_dir.resolve()}", flush=True)
    if reason == "battle_ended" and capture:
        try:
            if finish_capture(hwnd, log_dir, stars, category):
                result = 0
            else:
                reason = "capture_failed"
                result = 1
        except CaptureResourcesUnavailable as exc:
            reason = exc.reason
            result = 3
            print(str(exc), flush=True)
    else:
        result = (2 if reason in {"mouse_abort", "game_not_foreground", "wait_timeout"}
                  else 0 if reason in {"battle_ended", "first_skill_confirmed"} else 1)
    if reason in {"pet_fainted_timeout", "battle_timeout", "skill_unconfirmed",
                  "gather_unconfirmed", "skill_unavailable_with_energy"}:
        if classify(frame(hwnd)).combat:
            tap(hwnd, 1630, 985)
            time.sleep(0.7)
            frame(hwnd).save(log_dir / "after_flee.png")
            print("Battle did not complete; escape requested", flush=True)
    (log_dir / "result.json").write_text(json.dumps({
        "status": ("success" if result == 0 else "aborted" if result == 2
                   else "stopped" if result == 3 else "failed"),
        "reason": reason,
        "actions": actions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=float, default=120)
    parser.add_argument("--battle-seconds", type=float, default=90)
    parser.add_argument("--enter", action="store_true",
                        help="start the challenge at the nearby flower and select party slot 5")
    parser.add_argument("--capture", action="store_true",
                        help="after victory, spend purple stars with the run-exclusive ball")
    parser.add_argument("--first-skill-only", action="store_true",
                        help="diagnostic: stop after the first skill is confirmed")
    parser.add_argument("--runs", type=int, default=1,
                        help="number of complete challenges; default 1")
    parser.add_argument("--interval-seconds", type=float, default=0,
                        help="pause between completed challenges")
    parser.add_argument("--log-dir", type=Path,
                        default=Path("work") / "battle_runs" /
                        time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    if args.runs < 1 or args.interval_seconds < 0:
        parser.error("--runs must be >= 1 and --interval-seconds must be >= 0")
    if args.runs > 1 and not args.capture:
        parser.error("multiple runs require --capture to reach the retry screen")
    for index in range(args.runs):
        if index:
            time.sleep(args.interval_seconds)
            user32.SetProcessDPIAware()
            hwnd, _ = find_game("\u6d1b\u514b\u738b\u56fd")
            tap(hwnd, 1096, 1016)  # retry from the verified success screen
        target_dir = args.log_dir / f"run-{index + 1:03}" if args.runs > 1 else args.log_dir
        result = run(args.wait_seconds, args.battle_seconds, target_dir,
                     args.enter if index == 0 else False, args.capture,
                     first_skill_only=args.first_skill_only)
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
