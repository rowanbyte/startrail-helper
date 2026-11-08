# 第三方依赖与素材

MIT 许可证适用于本项目自有源码，不改变第三方库或游戏素材的权利归属。

- Android Gradle Plugin、Gradle、Android SDK、JDK：由各自项目提供，遵循对应发行许可证。仓库仅包含构建所需的 Gradle Wrapper，不包含完整开发工具。
- Google ML Kit 中文文字识别：通过 Google Maven 获取，使用时需遵守 Google 对应条款。仓库没有复制完整 SDK。
- Windows 端使用 Pillow、NumPy、CustomTkinter、PyWin32、Python/WinRT 及 interception-python 等库，各自许可证以其发行项目为准。没有上传原机 vendor 包。
- Windows 键盘驱动来自 [Interception](https://github.com/oblitum/Interception)，未随本仓库分发；安装与再分发需单独遵守该项目许可证。
- `android/app/src/main/assets/` 和 `desktop/assets/` 中的小型 PNG 是从游戏 UI 裁取的识别模板，不是自有游戏美术，不纳入本项目 MIT 授权范围。游戏名称、图标、字体呈现等权利归各自权利人；如有相关权利问题，请通过仓库 Issue 联系处理。
- 账号截图、完整游戏画面、设备序列号、操作日志、签名密钥和构建产物不随源码发布。
