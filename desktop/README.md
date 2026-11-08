# Windows 原型（历史开发版）

入口：`python control_panel.py`。仅支持 Windows，不能在 macOS 上直接运行。需 Python 3.10+、中文 OCR 系统语言组件以及项目所需依赖。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python control_panel.py
```

依赖清单按源码使用情况整理，尚未在全新 Windows 环境完成安装验收。原机的第三方 vendor 目录没有随源码发布。

自动移动使用 Interception；需用户自行安装兼容驱动并完成其安装要求。此处不包含驱动、安装器或内核组件。没有安装驱动时，普通模拟按键可能无法使角色移动。

默认流程依赖窗口化游戏及校准尺寸 1920 × 1080。截图后端、输入支持和遮挡行为以实际客户端及设备测试为准。请先单轮验证，不要将原机实测结果理解为换机即用。

花种列表为实时扫描；燃薪虫按照“引燃 → 充分燃烧”循环，能量不足时聚能。通用任务、自动刷异色仍未形成完整可用流程。当前开发重点是安卓版。
