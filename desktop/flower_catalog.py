"""Read the flower catalog from the live PC game screen.

The catalog contains images captured in the current session. Names are OCR hints;
the actual selection is checked against the saved name image before teleporting.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from flower_driver import capture, ensure_flower_page, ensure_game_size, find_game, focus, swipe, touch, user32
from select_fire_target import content_digest, difference, frame


HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))


@dataclass
class FlowerEntry:
    id: str
    name: str
    image: str
    label: str
    page: int
    first_seen: float
    category: str = "flowers"


class LegendaryResourcesUnavailable(RuntimeError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


def catalog_category(image: Image.Image) -> str | None:
    areas = {"flowers": (425, 43, 550, 70), "leaders": (585, 43, 695, 70),
             "legends": (740, 43, 850, 70)}
    counts = {key: sum(max(image.getpixel((x, y))) < 85
                       for x in range(box[0], box[2], 2)
                       for y in range(box[1], box[3], 2))
              for key, box in areas.items()}
    key = max(counts, key=counts.get)
    return key if counts[key] >= 25 else None


def ensure_catalog_page(hwnd: int, category: str = "flowers") -> None:
    if category not in {"flowers", "legends"}:
        raise ValueError(category)
    ensure_game_size(hwnd)
    current = catalog_category(frame(hwnd))
    if current is None:
        ensure_flower_page(hwnd)
        current = "flowers"
    if current != category:
        touch(hwnd, 485 if category == "flowers" else 795, 55)
        time.sleep(0.5)
    if catalog_category(frame(hwnd)) != category:
        raise RuntimeError(f"无法打开 {category} 挑战列表")


async def _raw_text(engine, image: Image.Image, scale: int = 2) -> str:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter
    candidate = image.resize((image.width * scale, image.height * scale)).convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(candidate.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.RGBA8, candidate.width, candidate.height)
    result = await engine.recognize_async(bitmap)
    return "".join(line.text for line in result.lines)


def weekly_quota(image: Image.Image, engine=None) -> int | None:
    engine = engine or _ocr_engine()
    for scale in (2, 3, 1):
        text = asyncio.run(_raw_text(engine, image.crop((545, 137, 635, 181)), scale))
        text = re.sub(r"\s+", "", text.upper()).translate(
            str.maketrans({"I": "1", "O": "0", "Z": "2", "S": "5", "B": "8", "彐": "3"}))
        match = re.search(r"([0-3])/3", text)
        if match:
            return int(match.group(1))
    return None


def card_tops(image: Image.Image) -> list[int]:
    """Locate cards from the dark left rail, independent of timer color."""
    background = (232, 225, 209)
    occupied = []
    for y in range(1080):
        pixel = image.getpixel((309, y))
        occupied.append(max(abs(pixel[i] - background[i]) for i in range(3)) > 40)
    result: list[int] = []
    for y in range(150, 890):
        before = sum(occupied[y - 7:y + 8]) >= 9
        after = sum(occupied[y - 6:y + 9]) >= 9
        if not before and after:
            result.append(y)
    return result


def label_image(image: Image.Image, top: int) -> Image.Image:
    return image.crop((585, top + 14, 845, top + 70)).convert("RGB")


def label_distance(a: Image.Image, b: Image.Image) -> float:
    a = a.convert("L")
    b = b.convert("L")
    if a.size != (260, 56) or b.size != (260, 56):
        a, b = a.resize((260, 56)), b.resize((260, 56))
    return min(ImageStat.Stat(ImageChops.difference(
        a.crop((0, max(0, shift), 260, min(56, 56 + shift))),
        b.crop((0, max(0, -shift), 260, min(56, 56 - shift)))
    )).mean[0] for shift in range(-2, 3))


def _ocr_engine():
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
    except ImportError as exc:
        raise RuntimeError("Windows 中文 OCR 组件缺失；请使用启动器附带的 Python 环境") from exc
    engine = OcrEngine.try_create_from_language(Language("zh-CN"))
    if engine is None:
        raise RuntimeError("Windows 中文 OCR 语言包未安装")
    return engine


async def _read_name(engine, image: Image.Image) -> str:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    candidates: list[str] = []
    for scale in (1, 3):
        candidate = image if scale == 1 else image.resize((image.width * 3, image.height * 3))
        candidate = candidate.convert("RGBA")
        writer = DataWriter()
        writer.write_bytes(candidate.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.RGBA8, candidate.width, candidate.height
        )
        result = await engine.recognize_async(bitmap)
        line = "".join(part.text for part in result.lines)
        only_chinese = "".join(re.findall(r"[\u3400-\u9fff]", line))
        if only_chinese:
            candidates.append(only_chinese[:10])
    return max(candidates, key=len, default="未识别花种")


def read_name(engine, image: Image.Image) -> str:
    return asyncio.run(_read_name(engine, image))


def legendary_name(engine, label: Image.Image) -> str:
    # These are recognition references, not a selectable target list. Options
    # always come from cards actually found in the current game screen.
    names = {"wing_king": "圣羽翼王", "pal": "龙息帕尔", "moon_wolf": "银月狼王"}
    for filename, name in names.items():
        reference = HERE / "assets" / "legendary_names" / f"{filename}.png"
        if reference.is_file() and label_distance(label, Image.open(reference)) < 3.0:
            return name
    return read_name(engine, label) if engine is not None else "未识别传说精灵"


def collect_from_image(image: Image.Image, page: int, output: Path,
                       entries: list[FlowerEntry], engine=None, category: str = "flowers") -> int:
    added = 0
    for top in card_tops(image):
        label = label_image(image, top)
        if any(label_distance(label, Image.open(entry.label)) < 3.0 for entry in entries):
            continue
        identifier = hashlib.sha256(label.tobytes()).hexdigest()[:12]
        name = (legendary_name(engine, label) if category == "legends"
                else read_name(engine, label) if engine is not None else "未识别花种")
        picture_path = output / f"{identifier}.png"
        label_path = output / f"{identifier}-label.png"
        image.crop((300, top, 1802, min(top + 174, 1080))).save(picture_path)
        label.save(label_path)
        entries.append(FlowerEntry(identifier, name, str(picture_path.resolve()),
                                   str(label_path.resolve()), page, time.time(), category))
        print(f"FOUND {identifier} {name}", flush=True)
        added += 1
    return added


def reset_top(hwnd: int, category: str = "flowers") -> None:
    stalls = 0
    for _ in range(14):
        ensure_catalog_page(hwnd, category)
        before = content_digest(frame(hwnd))
        swipe(hwnd, 900, 300, 900, 850, duration=0.35)
        time.sleep(0.35)
        after = content_digest(frame(hwnd))
        stalls = stalls + 1 if difference(before, after) < 1.0 else 0
        if stalls >= 2:
            return
    raise RuntimeError("花种列表无法回到顶部")


def scan_live(output: Path, *, reset: bool = True, category: str = "flowers") -> list[FlowerEntry]:
    output.mkdir(parents=True, exist_ok=True)
    user32.SetProcessDPIAware()
    hwnd, _ = find_game("洛克王国")
    ensure_catalog_page(hwnd, category)
    if reset:
        reset_top(hwnd, category)
    engine = _ocr_engine()
    entries: list[FlowerEntry] = []
    quota = weekly_quota(frame(hwnd), engine) if category == "legends" else None
    frame(hwnd).save(output / "catalog_page.png")
    stalls = 0
    for page in range(40):
        ensure_catalog_page(hwnd, category)
        image = frame(hwnd)
        collect_from_image(image, page, output, entries, engine, category)
        before = content_digest(image)
        swipe(hwnd, 900, 780, 900, 430, duration=0.4)
        time.sleep(0.42)
        after = content_digest(frame(hwnd))
        stalls = stalls + 1 if difference(before, after) < 1.0 else 0
        print(f"SCAN {page + 1} {len(entries)} entries", flush=True)
        if stalls >= 2:
            break
    else:
        raise RuntimeError("花种列表超过扫描上限，请检查界面")
    if not entries:
        raise RuntimeError("当前挑战页未识别到任何花种")
    (output / "catalog.json").write_text(
        json.dumps({"scanned_at": time.time(), "category": category,
                    "weekly_remaining": quota, "entries": [asdict(e) for e in entries]},
                   ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"CATALOG {output / 'catalog.json'}", flush=True)
    return entries


def find_visible_match(image: Image.Image, reference: Image.Image) -> tuple[float, int]:
    options = [(label_distance(label_image(image, top), reference), top)
               for top in card_tops(image)]
    return min(options, default=(255.0, -1))


def select_and_teleport(entry: FlowerEntry, output: Path, resource: str = "blue") -> None:
    """Re-identify the selected live card on every run, then teleport."""
    output.mkdir(parents=True, exist_ok=True)
    hwnd, _ = find_game("洛克王国")
    ensure_catalog_page(hwnd, entry.category)
    if entry.category == "legends" and resource == "blue":
        quota = weekly_quota(frame(hwnd))
        if quota is None:
            raise LegendaryResourcesUnavailable("weekly_quota_unreadable", "无法确认本周传说捕捉剩余次数，请刷新或检查游戏说明")
        if quota == 0:
            raise LegendaryResourcesUnavailable("weekly_quota_exhausted", "本周契约印记传说捕捉次数已用完，停止连刷")
        print(f"本周传说捕捉剩余 {quota}/3 次", flush=True)
        image = frame(hwnd)
        raw = asyncio.run(_raw_text(_ocr_engine(), image.crop((1400, 34, 1535, 82)), 3))
        raw = re.sub(r"\s+", "", raw.upper()).translate(str.maketrans(
            {"I": "1", "O": "0", "Z": "2", "B": "8", "S": "5"}))
        match = re.search(r"(?<![0-9A-Z])(\d{1,3})/120", raw)
        if match is None:
            raise LegendaryResourcesUnavailable("blue_balance_unreadable", "无法确认传说列表蓝星余额，停止以免无资源进入挑战")
        if int(match.group(1)) < 40:
            raise LegendaryResourcesUnavailable("blue_stars_insufficient", "蓝星不足 40，停止传说连刷；未切换专用印记")
    reference = Image.open(entry.label).convert("RGB")
    reset_top(hwnd, entry.category)
    stalls = 0
    best = 255.0
    for page in range(40):
        ensure_catalog_page(hwnd, entry.category)
        image = frame(hwnd)
        score, top = find_visible_match(image, reference)
        best = min(best, score)
        if score < 3.0:
            # Touch scrolling has inertia. Recheck the row after it settles;
            # otherwise the teleport button can move under the tap.
            for attempt in range(3):
                time.sleep(0.7)
                image = frame(hwnd)
                score, top = find_visible_match(image, reference)
                if score >= 3.0:
                    raise RuntimeError("目标卡片在滚动后移走，请重新扫描")
                image.save(output / "verified_target.png")
                touch(hwnd, 1650, top + 82)
                time.sleep(0.75)
                after_touch = frame(hwnd)
                if catalog_category(after_touch) is None:
                    break
                print(f"Teleport button retry {attempt + 1}", flush=True)
            else:
                raise RuntimeError("已找到目标卡片，但传送按钮没有响应")
            print(f"TARGET {entry.id} match={score:.2f} page={page}", flush=True)
            after_touch.save(output / "map_detail.png")
            touch(hwnd, 1530, 1015)
            time.sleep(3)
            capture(hwnd, output / "arrival.png")
            return
        before = content_digest(image)
        swipe(hwnd, 900, 780, 900, 430, duration=0.4)
        time.sleep(0.42)
        after = content_digest(frame(hwnd))
        stalls = stalls + 1 if difference(before, after) < 1.0 else 0
        if stalls >= 2:
            break
    raise RuntimeError(f"所选花种当前不在活动列表（最佳图像差异 {best:.1f}）；请刷新列表")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--category", choices=("flowers", "legends"), default="flowers")
    args = parser.parse_args()
    scan_live(args.output, category=args.category)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2)
