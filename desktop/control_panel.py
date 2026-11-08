"""Modern desktop control center for the Rock Kingdom helper."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image
from flower_catalog import label_distance

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))
import customtkinter as ctk

WORK = HERE.parent / "work" / "helper_runs"
BG, PANEL, CARD = "#0b1020", "#131b2f", "#1b2740"
TEXT, MUTED, ACCENT, GREEN = "#edf2ff", "#9eacc8", "#8d72ff", "#39d5b4"


class ControlPanel(ctk.CTk):
    def __init__(self, auto_scan: bool = True) -> None:
        super().__init__(fg_color=BG)
        ctk.set_appearance_mode("dark")
        self.title("星轨助手 · 洛克王国世界")
        self.geometry("1180x820")
        self.minsize(1050, 740)
        self.process = None
        self.messages = queue.Queue()
        self.active_log_path = None
        self.last_error = ""
        self.catalog_path = None
        self.category = "flowers"
        self.catalogs = {}
        self.weekly_remaining = None
        self.entries = []
        self.selected = None
        self.images = []
        self.count = ctk.StringVar(value="2")
        self.interval = ctk.StringVar(value="2")
        self.stars = ctk.StringVar(value="purple")
        self.legend_resource = ctk.StringVar(value="blue")
        self.status = ctk.StringVar(value="等待连接游戏")
        self.step_text = ctk.StringVar(value="当前步骤：等待开始")
        self.current_run = 0
        self.mini_window = None
        self.mini_bar = None
        self.mini_log = None
        self.catalog_status = ctk.StringVar(value="启动后自动读取")
        self.verified_label = Image.open(HERE / "assets" /
                                         "verified_flower_butterfly_label.png").convert("RGB")
        self.nav = {}

        sidebar = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color="#10182a")
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ctk.CTkLabel(sidebar, text="✦  星轨助手", font=("Microsoft YaHei UI", 23, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=25, pady=(28, 5))
        ctk.CTkLabel(sidebar, text="洛克王国世界 · PC 辅助", font=("Microsoft YaHei UI", 11),
                     text_color=MUTED).pack(anchor="w", padx=25, pady=(0, 32))
        for key, title in (("flowers", "✿   稀兽花种"), ("legends", "★   传说精灵"), ("shiny", "✧   异色追踪"),
                           ("tasks", "☑   任务流程"), ("settings", "⚙   关于与设置")):
            button = ctk.CTkButton(sidebar, text=title, anchor="w", height=44,
                                   corner_radius=10, fg_color="transparent", hover_color=CARD,
                                   text_color=MUTED, font=("Microsoft YaHei UI", 14),
                                   command=lambda page=key: self.show_page(page))
            button.pack(fill="x", padx=13, pady=3)
            self.nav[key] = button
        ctk.CTkLabel(sidebar, text="自动化模块持续扩展", text_color="#687896",
                     font=("Microsoft YaHei UI", 11)).pack(side="bottom", pady=25)
        self.body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.body.pack(side="left", fill="both", expand=True)
        self.show_page("flowers")
        self.after(120, self.drain)
        self.auto_refresh_id = self.after(900, self.refresh) if auto_scan else None
        if not auto_scan:
            self.load_cached_catalog()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def load_cached_catalog(self):
        prefix = "legendary-catalog-*" if self.category == "legends" else "catalog-*"
        catalogs = sorted(WORK.glob(f"{prefix}/catalog.json"), reverse=True)
        for path in catalogs:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entries = data["entries"]
            except (OSError, ValueError, KeyError):
                continue
            self.catalog_path = path
            self.entries = entries
            self.weekly_remaining = data.get("weekly_remaining")
            summaries = sorted(WORK.glob("run-*/summary.json"), reverse=True)
            for summary_path in summaries:
                try:
                    previous = json.loads(summary_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, KeyError):
                    continue
                self.selected = next((entry for entry in entries
                                      if entry["id"] == previous.get("target_id")), None)
                if self.selected is None:
                    named = [entry for entry in entries
                             if entry["name"] == previous.get("target_name")]
                    self.selected = named[0] if len(named) == 1 else None
                if self.selected:
                    break
            source = "历史截图" if data.get("source") == "screenshot" else "上次扫描"
            self.catalog_status.set(f"{source} · {len(entries)} 种")
            self.status.set("已加载上次列表；刷新可读取当前活动")
            self.step_text.set("当前步骤：等待开始 · 列表来自上次扫描")
            self.render_catalog()
            if self.selected and hasattr(self, "selected_label"):
                self.selected_label.configure(text=f"目标：{self.selected['name']} · 上次选择")
            return

    def show_page(self, page):
        if self.process and self.process.poll() is None:
            self.status.set("请先停止当前操作，再切换模块")
            return
        if page in {"flowers", "legends"} and page != self.category:
            self.catalogs[self.category] = (self.entries, self.selected, self.catalog_path,
                                            self.weekly_remaining)
            self.category = page
            self.entries, self.selected, self.catalog_path, self.weekly_remaining = self.catalogs.get(
                page, ([], None, None, None))
        for child in self.body.winfo_children():
            child.destroy()
        for key, button in self.nav.items():
            button.configure(fg_color=CARD if key == page else "transparent",
                             text_color=TEXT if key == page else MUTED)
        if page in {"flowers", "legends"}:
            self.build_flower_page()
            if self.catalog_path is None:
                self.load_cached_catalog()
            return
        title, description = {
            "shiny": ("异色追踪", "异色识别、刷新与捕捉流程将在这里管理。"),
            "tasks": ("任务流程", "日常与活动任务流程将在这里管理。"),
            "settings": ("关于与设置", "当前版本使用 Windows 原生输入、中文 OCR 和 Interception 驱动。"),
        }[page]
        ctk.CTkLabel(self.body, text=title, text_color=TEXT,
                     font=("Microsoft YaHei UI", 29, "bold")).pack(anchor="w", padx=36, pady=(38, 8))
        ctk.CTkLabel(self.body, text=description, text_color=MUTED,
                     font=("Microsoft YaHei UI", 14)).pack(anchor="w", padx=36)
        ctk.CTkLabel(self.body, text="模块开发中", text_color=ACCENT,
                     font=("Microsoft YaHei UI", 17, "bold"), fg_color=PANEL,
                     corner_radius=18, height=170).pack(fill="x", padx=36, pady=32)

    def build_flower_page(self):
        legendary = self.category == "legends"
        title = "传说精灵" if legendary else "稀兽花种"
        head = ctk.CTkFrame(self.body, fg_color="transparent")
        head.pack(fill="x", padx=30, pady=(27, 14))
        ctk.CTkLabel(head, text=title, text_color=TEXT,
                     font=("Microsoft YaHei UI", 29, "bold")).pack(side="left")
        ctk.CTkButton(head, text="↻  刷新当前活动", width=150, height=36,
                      fg_color=CARD, hover_color="#2a3b5b", command=self.refresh).pack(side="right")
        ctk.CTkLabel(self.body,
                     text=("实时读取传说精灵与本周次数。每轮核对目标、捕捉资源及周次数。" if legendary
                           else "实时读取游戏挑战页。每轮重新核对目标卡片，随后传送、挑战、捕捉。"),
                     text_color=MUTED, font=("Microsoft YaHei UI", 12)).pack(anchor="w", padx=31)
        progress_card = ctk.CTkFrame(self.body, fg_color=PANEL, corner_radius=12)
        progress_card.pack(fill="x", padx=28, pady=(12, 0))
        ctk.CTkLabel(progress_card, textvariable=self.step_text, text_color=GREEN,
                     font=("Microsoft YaHei UI", 13, "bold"), anchor="w").pack(
                         fill="x", padx=16, pady=(10, 5))
        self.progress_bar = ctk.CTkProgressBar(progress_card, height=7,
                                               progress_color=ACCENT, fg_color=CARD)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 10))
        self.progress_bar.set(0)
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=28, pady=(18, 10))
        row.grid_columnconfigure(0, weight=1)
        row.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(row, fg_color=PANEL, corner_radius=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        listing_head = ctk.CTkFrame(left, fg_color="transparent")
        listing_head.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(listing_head, text="当前传说精灵" if legendary else "当前活动花种", text_color=TEXT,
                     font=("Microsoft YaHei UI", 16, "bold")).pack(side="left")
        ctk.CTkLabel(listing_head, textvariable=self.catalog_status, text_color=MUTED,
                     font=("Microsoft YaHei UI", 11)).pack(side="right")
        self.list_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        self.render_catalog()

        right = ctk.CTkScrollableFrame(row, width=260, fg_color=PANEL, corner_radius=16)
        right.grid(row=0, column=1, sticky="ns")
        ctk.CTkLabel(right, text="连刷设置", text_color=TEXT,
                     font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", padx=19, pady=(19, 17))
        self.selected_label = ctk.CTkLabel(right, text="尚未选择目标", text_color=ACCENT,
                                           font=("Microsoft YaHei UI", 14, "bold"),
                                           wraplength=245, justify="left")
        self.selected_label.pack(anchor="w", padx=19, pady=(0, 18))
        if self.selected:
            self.selected_label.configure(text=f"目标：{self.selected['name']}")
        for label, variable in (("挑战次数", self.count), ("每轮间隔 / 秒", self.interval)):
            ctk.CTkLabel(right, text=label, text_color=MUTED,
                         font=("Microsoft YaHei UI", 12)).pack(anchor="w", padx=19, pady=(4, 5))
            ctk.CTkEntry(right, textvariable=variable, height=36, fg_color=BG,
                         border_color="#31405f").pack(fill="x", padx=19, pady=(0, 13))
        ctk.CTkLabel(right, text="捕捉方式" if legendary else "捕捉优先消耗", text_color=MUTED,
                     font=("Microsoft YaHei UI", 12)).pack(anchor="w", padx=19, pady=(4, 6))
        self.star_picker = ctk.CTkSegmentedButton(right,
                                                  values=["蓝星周次数", "专用印记"] if legendary else ["紫星", "蓝星"],
                                                  command=lambda value: (self.legend_resource.set(
                                                      "blue" if value == "蓝星周次数" else "legendary") if legendary
                                                      else self.stars.set("purple" if value == "紫星" else "blue")),
                                                  fg_color=BG, selected_color=ACCENT,
                                                  unselected_color=CARD)
        self.star_picker.pack(fill="x", padx=19, pady=(0, 5))
        self.star_picker.set(("蓝星周次数" if self.legend_resource.get() == "blue" else "专用印记")
                             if legendary else ("紫星" if self.stars.get() == "purple" else "蓝星"))
        ctk.CTkLabel(right, text=(f"上次扫描：本周剩余 {self.weekly_remaining if self.weekly_remaining is not None else '?'} / 3 次\n资源不足即停止，不自动换专用印记"
                                 if legendary else "不足时自动换另一种；都不足则停止"),
                     text_color=MUTED, font=("Microsoft YaHei UI", 10)).pack(
                         anchor="w", padx=19, pady=(0, 13))
        ctk.CTkLabel(right, text="战斗方案", text_color=MUTED,
                     font=("Microsoft YaHei UI", 12)).pack(anchor="w", padx=19)
        ctk.CTkLabel(right, text="第 5 位 · 燃薪虫\n引燃 → 充分燃烧，能量不足时聚能",
                     text_color=TEXT, justify="left", font=("Microsoft YaHei UI", 12),
                     fg_color=CARD, corner_radius=9, height=58).pack(fill="x", padx=19, pady=(6, 5))
        ctk.CTkLabel(right, text="当前按第 5 位燃薪虫出战。失败轮次会记录并尝试继续下一轮；待实测目标不能保证获胜。",
                     text_color="#f5b766", wraplength=245, justify="left",
                     font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=19)
        self.start_button = ctk.CTkButton(right, text="▶  开始自动连刷", height=44,
                                          fg_color=ACCENT, hover_color="#765fe0",
                                          font=("Microsoft YaHei UI", 15, "bold"), command=self.start)
        self.start_button.pack(fill="x", padx=19, pady=(23, 7))
        self.stop_button = ctk.CTkButton(right, text="■  停止", height=36,
                                         fg_color=CARD, state="disabled", command=self.stop)
        self.stop_button.pack(fill="x", padx=19)
        if legendary:
            ctk.CTkButton(right, text="玩法条件与攻略来源", height=30, fg_color=CARD,
                          command=self.show_legend_rules).pack(fill="x", padx=19, pady=8)

        footer = ctk.CTkFrame(self.body, fg_color=PANEL, corner_radius=14, height=128)
        footer.pack(fill="x", padx=28, pady=(0, 24))
        footer.pack_propagate(False)
        ctk.CTkLabel(footer, textvariable=self.status, text_color=GREEN,
                     font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=17, pady=(10, 5))
        self.log = ctk.CTkTextbox(footer, fg_color="transparent", text_color=MUTED,
                                  height=78, font=("Consolas", 11))
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.log.configure(state="disabled")

    def render_catalog(self):
        if not hasattr(self, "list_frame") or not self.list_frame.winfo_exists():
            return
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.images.clear()
        if not self.entries:
            ctk.CTkLabel(self.list_frame, text="正在等待实时列表…", text_color=MUTED,
                         font=("Microsoft YaHei UI", 13)).pack(pady=70)
            return
        for number, entry in enumerate(self.entries, 1):
            chosen = self.selected is not None and self.selected["id"] == entry["id"]
            card = ctk.CTkFrame(self.list_frame, fg_color="#2c3151" if chosen else CARD,
                                corner_radius=11, border_width=1,
                                border_color=ACCENT if chosen else "#273550")
            card.pack(fill="x", padx=5, pady=5)
            try:
                image = Image.open(entry["image"]).convert("RGB").crop((0, 0, 600, 174))
                image.thumbnail((270, 78))
                visual = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                self.images.append(visual)
                icon = ctk.CTkLabel(card, text="", image=visual)
                icon.pack(side="left", padx=(8, 7), pady=7)
                icon.bind("<Button-1>", lambda event, item=entry: self.select(item))
            except OSError:
                pass
            ctk.CTkButton(card, text="已选" if chosen else "选择", width=50, height=31,
                          fg_color=ACCENT if chosen else "#334767",
                          command=lambda item=entry: self.select(item)).pack(side="right", padx=9)
            verified = self.is_verified(entry)
            hint = "花衣蝶 · 已实测" if verified else entry["name"]
            ctk.CTkLabel(card, text=f"{number:02}  {hint}",
                         text_color=GREEN if verified else MUTED,
                         font=("Microsoft YaHei UI", 11)).pack(side="right", padx=5)

    def show_legend_rules(self):
        import webbrowser
        from legendary_rules import RULES_TEXT, SOURCES
        window = ctk.CTkToplevel(self)
        window.title("传说精灵 · 条件与资料")
        window.geometry("720x700")
        text = ctk.CTkTextbox(window, wrap="word", font=("Microsoft YaHei UI", 14))
        text.pack(fill="both", expand=True, padx=20, pady=20)
        text.insert("1.0", RULES_TEXT)
        text.configure(state="disabled")
        for label, url in SOURCES:
            ctk.CTkButton(window, text=label, fg_color=CARD,
                          command=lambda link=url: webbrowser.open(link)).pack(fill="x", padx=20, pady=3)
        window.lift()

    def is_verified(self, entry) -> bool:
        if entry.get("category", "flowers") != "flowers":
            return False
        try:
            with Image.open(entry["label"]) as label:
                return label_distance(self.verified_label, label) < 3.0
        except OSError:
            return False

    def select(self, entry):
        self.selected = entry
        if hasattr(self, "selected_label") and self.selected_label.winfo_exists():
            status = "已实测" if self.is_verified(entry) else "待实测"
            self.selected_label.configure(text=f"目标：{entry['name']}  ·  {status}")
        self.render_catalog()

    def launch(self, mode, command):
        if self.process and self.process.poll() is None:
            return
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(command, cwd=HERE.parent, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1,
                                        encoding="utf-8", errors="replace", env=env,
                                        creationflags=flags)
        if hasattr(self, "stop_button") and self.stop_button.winfo_exists():
            self.stop_button.configure(state="normal")
        if hasattr(self, "start_button") and self.start_button.winfo_exists():
            self.start_button.configure(state="disabled")
        threading.Thread(target=self.read_process, args=(self.process, mode), daemon=True).start()

    def refresh(self):
        if self.process and self.process.poll() is None:
            return
        prefix = "legendary-catalog" if self.category == "legends" else "catalog"
        folder = WORK / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"
        folder.mkdir(parents=True, exist_ok=True)
        self.active_log_path = folder / "scan.log"
        self.last_error = ""
        self.catalog_path = folder / "catalog.json"
        self.catalog_status.set("扫描中…")
        self.status.set("正在读取游戏里的传说精灵" if self.category == "legends" else "正在读取游戏里的当前花种")
        self.step_text.set("当前步骤：扫描游戏里的传说精灵" if self.category == "legends" else "当前步骤：扫描游戏里的活动花种")
        self.launch("scan", [sys.executable, "-u", str(HERE / "flower_catalog.py"),
                             "--output", str(folder), "--category", self.category])

    def start(self):
        if self.process and self.process.poll() is None:
            return
        if not self.selected or not self.catalog_path or not self.catalog_path.exists():
            self.status.set("请先刷新列表并选择目标")
            return
        if json.loads(self.catalog_path.read_text(encoding="utf-8")).get("source") == "screenshot":
            self.status.set("当前是历史截图示例，请先启动游戏并刷新实时列表")
            return
        try:
            count, interval = int(self.count.get()), float(self.interval.get())
            if not 1 <= count <= 100 or not 0 <= interval <= 3600:
                raise ValueError
        except ValueError:
            self.status.set("次数需为 1–100，间隔需为 0–3600 秒")
            return
        prefix = "legendary-run" if self.category == "legends" else "run"
        folder = WORK / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"
        folder.mkdir(parents=True, exist_ok=True)
        self.active_log_path = folder / "session.log"
        self.last_error = ""
        self.last_run_folder = folder
        self.current_run = 0
        self.step_text.set(f"当前步骤：准备开始 {count} 轮挑战")
        if self.progress_bar.winfo_exists():
            self.progress_bar.set(0)
        self.status.set(f"正在连刷 {count} 次 · {self.selected['name']}")
        resource = self.legend_resource.get() if self.category == "legends" else self.stars.get()
        self.append(f"开始：{self.selected['name']}，{count} 次，资源 {resource}，第 5 位燃薪虫")
        self.show_progress_window()
        self.launch("run", [sys.executable, "-u", str(HERE / "auto_flower.py"),
                            "--catalog", str(self.catalog_path), "--target-id", self.selected["id"],
                            "--runs", str(count), "--interval-seconds", str(interval),
                            "--stars", resource, "--party-slot", "5",
                            "--log-dir", str(folder)])

    def show_progress_window(self):
        if self.mini_window is not None and self.mini_window.winfo_exists():
            self.mini_window.deiconify()
            self.mini_window.lift()
            return
        width, height = 420, 270
        scale = self._get_window_scaling()
        # CTk reports the screen width in logical units, but a Toplevel's +x
        # offset is applied in physical pixels. Using the logical width put
        # this window over the game's minimap on high-DPI Windows desktops.
        physical_width = round(self.winfo_screenwidth() * scale)
        physical_mini_width = round(width * scale)
        x = max(10, physical_width - physical_mini_width - 24)
        mini = ctk.CTkToplevel(self, fg_color=BG)
        mini.title("星轨助手 · 运行进度")
        mini.geometry(f"{width}x{height}+{x}+80")
        mini.resizable(False, False)
        mini.attributes("-topmost", True)
        mini.protocol("WM_DELETE_WINDOW", self.show_main_window)
        self.mini_window = mini
        ctk.CTkLabel(mini, text="✦  星轨助手 · 连刷进度", text_color=TEXT,
                     font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w", padx=18, pady=(15, 8))
        ctk.CTkLabel(mini, textvariable=self.step_text, text_color=GREEN,
                     font=("Microsoft YaHei UI", 12, "bold"), wraplength=380,
                     justify="left").pack(anchor="w", padx=18)
        self.mini_bar = ctk.CTkProgressBar(mini, height=7,
                                            progress_color=ACCENT, fg_color=CARD)
        self.mini_bar.pack(fill="x", padx=18, pady=(10, 8))
        self.mini_bar.set(0)
        self.mini_log = ctk.CTkTextbox(mini, height=95, fg_color=PANEL,
                                        text_color=MUTED, font=("Consolas", 10))
        self.mini_log.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        self.mini_log.configure(state="disabled")
        buttons = ctk.CTkFrame(mini, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkButton(buttons, text="停止", width=90, fg_color=CARD,
                      command=self.stop).pack(side="right")
        ctk.CTkButton(buttons, text="主界面", width=90, fg_color=ACCENT,
                      command=self.show_main_window).pack(side="right", padx=(0, 8))
        self.withdraw()

    def show_main_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def read_process(self, process, mode):
        for line in process.stdout:
            self.messages.put((mode, line.rstrip()))
        self.messages.put((mode, f"__FINISHED__:{process.wait()}"))

    def drain(self):
        try:
            while True:
                mode, line = self.messages.get_nowait()
                if line.startswith("PROGRESS|"):
                    _, run, total, stage, detail = line.split("|", 4)
                    self.current_run = int(run)
                    total_count = int(total)
                    self.step_text.set(f"当前步骤：第 {run}/{total} 轮 · {detail}")
                    fraction = {"return": 0, "locate": 0.08, "approach": 0.28,
                                "battle": 0.48, "recover": 0.82,
                                "success": 1, "failed": 1, "aborted": 1,
                                "stopped": 1}.get(stage, 0)
                    if self.progress_bar.winfo_exists():
                        self.progress_bar.set((int(run) - 1 + fraction) / total_count)
                    if self.mini_bar is not None and self.mini_bar.winfo_exists():
                        self.mini_bar.set((int(run) - 1 + fraction) / total_count)
                    self.append(detail)
                    continue
                if line.startswith("__FINISHED__:"):
                    code = int(line.split(":", 1)[1])
                    if mode == "scan":
                        if code == 0 and self.catalog_path and self.catalog_path.exists():
                            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
                            self.entries = data["entries"]
                            self.weekly_remaining = data.get("weekly_remaining")
                            if self.selected:
                                old_label = Image.open(self.selected["label"])
                                self.selected = next((e for e in self.entries
                                                      if label_distance(old_label, Image.open(e["label"])) < 3.0), None)
                            suffix = (f" · 本周剩余 {self.weekly_remaining if self.weekly_remaining is not None else '?'}/3"
                                      if self.category == "legends" else "")
                            self.catalog_status.set(f"刚刚扫描 · {len(self.entries)} 种{suffix}")
                            noun = "传说精灵" if self.category == "legends" else "花种"
                            self.status.set(f"已从当前游戏读取 {len(self.entries)} 种{noun}")
                            self.step_text.set(f"当前步骤：扫描完成，已发现 {len(self.entries)} 种{noun}")
                            self.render_catalog()
                            self.attributes("-topmost", True)
                            self.lift()
                            self.focus_force()
                            self.after(600, lambda: self.attributes("-topmost", False))
                        else:
                            self.catalog_status.set("扫描失败")
                            self.status.set("扫描失败；确认游戏窗口化且挑战页可打开")
                            self.step_text.set("当前步骤：扫描失败，请查看下方日志")
                    else:
                        summary_path = getattr(self, "last_run_folder", Path()) / "summary.json"
                        if summary_path.is_file():
                            summary = json.loads(summary_path.read_text(encoding="utf-8"))
                            if summary.get("stop_reason"):
                                detail = {
                                    "stars_exhausted": "两种星星都不足",
                                    "stars_unreadable": "无法确认星星余额或消耗",
                                    "weekly_quota_unreadable": "无法确认传说捕捉周次数",
                                    "weekly_quota_exhausted": "本周传说契约捕捉次数已用完",
                                    "blue_stars_insufficient": "蓝星不足 40",
                                    "blue_balance_unreadable": "无法确认蓝星余额",
                                    "legendary_resource_unconfirmed": "无法确认传说捕捉资源",
                                }.get(summary["stop_reason"], summary["stop_reason"])
                                self.status.set(f"已停止 · {detail}")
                                self.step_text.set(f"当前步骤：{detail}")
                            elif code != 0 and summary["completed_runs"] < summary["requested_runs"]:
                                self.status.set(f"异常中断 · 已完成 {summary['completed_runs']}/{summary['requested_runs']} 轮")
                                self.step_text.set(f"当前步骤：{self.last_error or '异常中断，请查看日志'}")
                            else:
                                self.status.set(f"连刷结束 · 成功 {summary['succeeded']} / 失败 {summary['failed']}")
                                self.step_text.set(f"当前步骤：连刷结束 · 成功 {summary['succeeded']} / 失败 {summary['failed']}")
                        else:
                            self.status.set("连刷完成" if code == 0 else f"连刷停止 · 退出码 {code}")
                            self.step_text.set(f"当前步骤：{self.last_error or '已结束，请查看下方日志'}")
                    if hasattr(self, "start_button") and self.start_button.winfo_exists():
                        self.start_button.configure(state="normal")
                    if hasattr(self, "stop_button") and self.stop_button.winfo_exists():
                        self.stop_button.configure(state="disabled")
                    if mode == "run" and self.mini_window is not None and self.mini_window.winfo_exists():
                        self.mini_window.destroy()
                        self.mini_window = None
                        self.mini_bar = None
                        self.mini_log = None
                        self.show_main_window()
                    self.active_log_path = None
                else:
                    if line.startswith("Error:"):
                        self.last_error = line
                    if ": ignite" in line:
                        self.step_text.set(f"当前步骤：第 {self.current_run} 轮 · 释放引燃")
                    elif ": combustion" in line:
                        self.step_text.set(f"当前步骤：第 {self.current_run} 轮 · 释放充分燃烧")
                    elif ": gather" in line:
                        self.step_text.set(f"当前步骤：第 {self.current_run} 轮 · 能量不足，聚能")
                    elif "active pet fainted" in line:
                        self.step_text.set(f"当前步骤：第 {self.current_run} 轮 · 宠物倒下，观察 Boss 最多 2 分钟")
                    elif "Pet fainted; waiting" in line:
                        remaining = line.rsplit(",", 1)[-1].strip().replace("s remaining", "秒")
                        self.step_text.set(f"当前步骤：第 {self.current_run} 轮 · 宠物倒下，等待 Boss · 剩余 {remaining}")
                    elif "Recovery action: confirm_escape" in line:
                        self.step_text.set(f"当前步骤：第 {self.current_run} 轮 · 确认逃跑，准备下一轮")
                    elif "Selected " in line and "ball thrown" in line:
                        self.step_text.set(f"当前步骤：第 {self.current_run} 轮 · 已投专属球，等待捕捉结果")
                    self.append(line)
        except queue.Empty:
            pass
        self.after(120, self.drain)

    def append(self, line):
        if self.active_log_path is not None:
            with self.active_log_path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
        for widget in (getattr(self, "log", None), self.mini_log):
            if widget is None or not widget.winfo_exists():
                continue
            widget.configure(state="normal")
            widget.insert("end", line + "\n")
            widget.see("end")
            widget.configure(state="disabled")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.append("已请求停止。")
            self.step_text.set("当前步骤：已请求停止")

    def close(self):
        self.stop()
        if self.mini_window is not None and self.mini_window.winfo_exists():
            self.mini_window.destroy()
        self.destroy()


if __name__ == "__main__":
    panel = ControlPanel(auto_scan="--no-auto-scan" not in sys.argv)
    if "--legends" in sys.argv:
        panel.show_page("legends")
    panel.mainloop()
