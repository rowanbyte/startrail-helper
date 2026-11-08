"""Repeat a flower challenge selected from the current game catalog."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from PIL import ImageChops, ImageStat

from battle_assistant import (capture_visible, classify, escape_confirm_visible,
                              frame, network_overlay, reward_visible,
                              run as battle_run)
from flower_driver import ensure_game_size, find_game, focus, touch, user32
from flower_catalog import FlowerEntry, LegendaryResourcesUnavailable, select_and_teleport
from game_capture import world_hud_visible
from prompt_detector import challenge_prompt


class MovementKeys:
    """Physical-device input for the PC client's continuous movement controls."""

    def __init__(self) -> None:
        vendor = Path(__file__).resolve().parent / "vendor"
        if vendor.is_dir():
            for path in (vendor, vendor / "win32", vendor / "win32" / "lib"):
                sys.path.insert(0, str(path))
            os.add_dll_directory(str(vendor / "pywin32_system32"))
        try:
            import interception
        except ImportError as exc:
            raise RuntimeError("Movement requires interception-python; see README.txt") from exc
        try:
            interception.auto_capture_devices(keyboard=True, mouse=False)
        except Exception as exc:
            raise RuntimeError(
                "PC movement requires the Interception keyboard driver; see README.txt"
            ) from exc
        self.input = interception

    def hold(self, key: str, seconds: float) -> None:
        self.input.key_down(key, delay=0)
        try:
            time.sleep(seconds)
        finally:
            self.input.key_up(key, delay=0)


def is_success(image) -> bool:
    r, g, b = image.getpixel((800, 1016))
    return r > 230 and g > 220 and b < 235


def flower_prompt(image) -> bool:
    return challenge_prompt(image) is not None


def world_ready(image) -> bool:
    return world_hud_visible(image)


def recovery_action(image) -> str:
    if network_overlay(image):
        return "network_wait"
    if is_success(image):
        return "exit_success"
    if capture_visible(image):
        return "exit_capture"
    if world_ready(image):
        return "world"
    if escape_confirm_visible(image):
        return "confirm_escape"
    if classify(image).combat:
        return "request_escape"
    if reward_visible(image):
        return "dismiss_reward"
    return "wait"


def world_from_success(hwnd: int, evidence_dir: Path | None = None) -> None:
    deadline = time.monotonic() + 40
    network_since: float | None = None
    next_tap = 0.0
    targets = {"exit_success": (825, 1015), "exit_capture": (1735, 985),
               "confirm_escape": (1110, 890), "request_escape": (1630, 985),
               "dismiss_reward": (1650, 800)}
    last_action = "wait"
    while time.monotonic() < deadline:
        image = frame(hwnd)
        action = recovery_action(image)
        last_action = action
        if action == "network_wait":
            network_since = network_since or time.monotonic()
            if time.monotonic() - network_since > 120:
                raise RuntimeError("Network connection did not recover within 120 seconds")
            time.sleep(0.3)
            continue
        if network_since is not None:
            deadline += time.monotonic() - network_since
            network_since = None
        if action == "world":
            return
        if action in targets and time.monotonic() >= next_tap:
            touch(hwnd, *targets[action])
            print(f"Recovery action: {action}", flush=True)
            next_tap = time.monotonic() + 2
        time.sleep(0.2)
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        frame(hwnd).save(evidence_dir / "recovery_timeout.png")
    raise RuntimeError(f"Could not reach the game world; last recovery state: {last_action}")


def minimap_change(before, after) -> float:
    crop = (1740, 70, 1790, 175)  # terrain, away from the player arrow and markers
    delta = ImageChops.difference(before.crop(crop), after.crop(crop))
    return sum(ImageStat.Stat(delta).mean) / 3


def reach_flower(hwnd: int, movement: MovementKeys,
                 evidence_dir: Path | None = None) -> None:
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        image = frame(hwnd)
        if world_ready(image):
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("World HUD did not appear after teleport")

    if flower_prompt(image):
        print("Flower challenge prompt visible", flush=True)
        return

    origin = image
    # The Flower Butterfly teleport faces the flower. Probe forward first,
    # then extend a small square search. Stop at the first F prompt.
    search = "wwwwwddwwaaaassssddddddww"
    largest_map_change = 0.0
    for moved, direction in enumerate(search, 1):
        focus(hwnd)
        movement.hold(direction, 0.28)
        time.sleep(0.18)
        image = frame(hwnd)
        if not world_ready(image):
            if evidence_dir is not None:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                image.save(evidence_dir / "world_ui_transition.png")
            print("World HUD temporarily hidden; pausing movement until it returns", flush=True)
            transition_deadline = time.monotonic() + 30
            while time.monotonic() < transition_deadline:
                time.sleep(0.25)
                image = frame(hwnd)
                if world_ready(image) or flower_prompt(image):
                    break
            else:
                if evidence_dir is not None:
                    image.save(evidence_dir / "world_ui_timeout.png")
                raise RuntimeError("World HUD did not return within 30 seconds while approaching flower")
        if flower_prompt(image):
            print("Flower challenge prompt visible", flush=True)
            return
        largest_map_change = max(largest_map_change, minimap_change(origin, image))
        print(f"Approaching flower: {direction.upper()} step {moved}/{len(search)}", flush=True)
    if largest_map_change < 2.0:
        raise RuntimeError("No minimap change after the full approach search; check movement or screen occlusion")
    raise RuntimeError("Moved around teleport point but found no flower challenge prompt")


def run_many(runs: int, interval_seconds: float, log_dir: Path,
             target: FlowerEntry, stars: str, party_slot: int,
             faint_wait_seconds: float = 120) -> int:
    user32.SetProcessDPIAware()
    hwnd, _ = find_game("\u6d1b\u514b\u738b\u56fd")
    ensure_game_size(hwnd)
    movement = MovementKeys()
    initial_image = frame(hwnd)
    resume_current = (not world_ready(initial_image) and
                      (capture_visible(initial_image) or classify(initial_image).combat))
    if recovery_action(initial_image) in {"exit_success", "dismiss_reward"}:
        world_from_success(hwnd)
        resume_current = False
    succeeded = 0
    failed = 0
    stop_reason: str | None = None
    outcomes: list[dict[str, object]] = []

    def save_summary() -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "summary.json").write_text(json.dumps({
            "target_id": target.id,
            "target_name": target.name,
            "category": target.category,
            "requested_runs": runs,
            "completed_runs": len(outcomes),
            "succeeded": succeeded,
            "failed": failed,
            "stop_reason": stop_reason,
            "outcomes": outcomes,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def progress(index: int, stage: str, detail: str) -> None:
        print(f"PROGRESS|{index + 1}|{runs}|{stage}|{detail}", flush=True)

    for index in range(runs):
        if index:
            time.sleep(interval_seconds)
        run_dir = log_dir / f"run-{index + 1:03}"
        joining = index == 0 and resume_current
        if joining:
            progress(index, "battle", "接管当前战斗或捕捉界面")
            print("Run 1: resuming the current battle/capture", flush=True)
        else:
            progress(index, "locate", "在实时活动列表定位目标并传送")
            print(f"Run {index + 1}/{runs}: locating and teleporting", flush=True)
            try:
                if target.category == "legends":
                    select_and_teleport(target, run_dir / "teleport", resource=stars)
                else:
                    select_and_teleport(target, run_dir / "teleport")
            except LegendaryResourcesUnavailable as exc:
                stop_reason = exc.reason
                progress(index, "stopped", str(exc))
                save_summary()
                return 3
            progress(index, "approach", "走近花种并识别 F 挑战提示")
            reach_flower(hwnd, movement, run_dir / "approach")
            progress(index, "battle", "进入战斗，按能量依次出招")
        print(f"Run {index + 1}/{runs}: battle and capture", flush=True)
        result = battle_run(20, 180 if target.category == "legends" else 90,
                            run_dir / "battle", enter=not joining, capture=True,
                            stars=stars, party_slot=party_slot,
                            faint_wait_seconds=faint_wait_seconds, category=target.category)
        result_path = run_dir / "battle" / "result.json"
        battle_reason = (json.loads(result_path.read_text(encoding="utf-8")).get("reason", "unknown")
                         if result_path.is_file() else "unknown")
        if result == 3:
            stop_reason = battle_reason
            detail = ("蓝星和紫星均不足，退出捕捉并停止连刷" if battle_reason == "stars_exhausted"
                      else "无法确认传说捕捉资源，退出捕捉并停止连刷" if target.category == "legends"
                      else "无法确认星星余额或消耗，退出捕捉并停止连刷")
            progress(index, "stopped", detail)
            print(detail, flush=True)
            try:
                world_from_success(hwnd, run_dir / "recovery")
            except RuntimeError as exc:
                print(f"Could not leave capture screen automatically: {exc}", flush=True)
            outcomes.append({"run": index + 1, "status": "stopped", "reason": battle_reason})
            save_summary()
            return 3
        if result == 2:
            progress(index, "aborted", "安全停止，未继续下一轮")
            print(f"Stopped by safety condition on run {index + 1}", flush=True)
            outcomes.append({"run": index + 1, "status": "aborted", "reason": battle_reason})
            save_summary()
            return 2
        if result:
            failed += 1
            outcomes.append({"run": index + 1, "status": "failed", "reason": battle_reason})
            save_summary()
            detail = ("宠物倒下且 2 分钟内未击败 Boss" if battle_reason == "pet_fainted_timeout"
                      else "宠物倒下，无法完成捕捉" if battle_reason == "pet_fainted_before_capture"
                      else "本轮挑战失败")
            progress(index, "recover", f"{detail}；确认逃跑并恢复到世界")
            print(f"Run {index + 1}/{runs} failed; recovering for the next run", flush=True)
            world_from_success(hwnd, run_dir / "recovery")
            progress(index, "failed", "本轮已记录失败，继续下一轮")
        else:
            progress(index, "return", "捕捉成功，退出结算并返回世界")
            world_from_success(hwnd, run_dir / "recovery")
            succeeded += 1
            outcomes.append({"run": index + 1, "status": "success", "reason": battle_reason})
            save_summary()
            progress(index, "success", "挑战与捕捉成功")
            print(f"Run {index + 1}/{runs} completed", flush=True)
    print(f"Finished {runs} runs: {succeeded} success, {failed} failed", flush=True)
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--interval-seconds", type=float, default=2)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--stars", choices=("purple", "blue", "legendary"), default="purple")
    parser.add_argument("--party-slot", type=int, choices=range(1, 7), default=5)
    parser.add_argument("--faint-wait-seconds", type=float, default=120,
                        help="diagnostic override; default is 120 seconds")
    parser.add_argument("--log-dir", type=Path,
                        default=Path("work") / "auto_flower" /
                        time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    if not 1 <= args.runs <= 100:
        parser.error("--runs must be between 1 and 100")
    if args.interval_seconds < 0:
        parser.error("--interval-seconds must be nonnegative")
    if args.faint_wait_seconds <= 0:
        parser.error("--faint-wait-seconds must be positive")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    target = next((FlowerEntry(**item) for item in catalog["entries"]
                   if item["id"] == args.target_id), None)
    if target is None:
        parser.error("--target-id was not found in the live catalog")
    if target.category == "legends" and args.stars == "purple":
        parser.error("传说精灵不支持紫星，请选择 blue 或 legendary")
    if target.category == "flowers" and args.stars == "legendary":
        parser.error("稀兽花种不使用传说印记")
    return run_many(args.runs, args.interval_seconds, args.log_dir, target,
                    args.stars, args.party_slot, args.faint_wait_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2)
