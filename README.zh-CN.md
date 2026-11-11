# 指针尾迹增强版（第三方修改）

基于 [Oink v0.3.4](https://github.com/oinkvm/oink/tree/v0.3.4)，版本 **0.3.4-inhouse.110（build 110）**。这不是 Oink 官方发行版；原项目说明、署名和许可证保留在下方。

在 **设置 → 键鼠** 中可以：

- 保留尾迹总开关，选择“快速画圈（原版）”或“移动即显示”。
- 让尾迹跟随主题，或选择预设色、自定义颜色。
- 选择 Windows 白色、黑色、反色箭头及大小；“原系统样式”可恢复之前的箭头。此设置也影响本机其他软件，文本和缩放光标不变。

## 安装

从[本分支 Releases](https://github.com/xiaojiangqvq/oink/releases) 下载 `PointerTrail-Setup.exe`，两台 Windows 电脑分别按标准安装向导操作。完整 Windows x64 安装包可直接用于新电脑，内含微软官方 WebView2 离线运行库，仅在缺少时安装。

检测到已有 Oink 时，可以选择：

- **覆盖安装（默认）**：升级并保留配对、屏幕布局和设置。
- **卸载**：移除 Oink。
- **全新安装**：先卸载旧版，再重新安装。

**“卸载”和“全新安装”会删除本机应用配置。** 希望保留现有设置时，选择“覆盖安装”，不用提前卸载。支持原版 0.3.4（build 108）和早期个人尾迹补丁升级，未承诺覆盖更新的官方版本。

完成后从开始菜单打开 Oink。现有登录启动设置会保留；新装如有需要，可在应用设置中开启。尾迹模式由连接鼠标的电脑决定，颜色和箭头由显示它们的电脑决定；早期个人补丁的移动模式会保留，已有明确选择不覆盖。

后续从[本分支 Releases](https://github.com/xiaojiangqvq/oink/releases) 手动升级，Windows 官方更新源已关闭。完整源码、许可证随发布提供；[构建说明](packaging/trail-installer/BUILDING.txt)。本次没有 macOS 安装包，也尚未完成干净 Windows 电脑的全新安装实测。

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/banner-zh-CN-dark.png">
    <img alt="Oink — Oink Is Not only a KVM。你的电脑，合而为一" src=".github/assets/banner-zh-CN-light.png" width="860">
  </picture>
</p>

# Oink — Oink Is Not only a KVM

[English](README.md) | **简体中文** | [日本語](README.ja.md) | [한국어](README.ko.md)

Oink 是 Oink Is Not only a KVM 的缩写，是一款在多台 Windows 和 Mac 设备间建立对等共享网络的现代软件。同时使用任何设备的键盘、鼠标、触摸板操控任意邻近设备，保持统一、原生的操作手感；将多台设备的音频通过连接至一台设备的扬声器或耳机播放；支持剪贴板共享和跨设备拖拽；支持局域网设备自动发现；默认加密传输。

## 安装

从[本分支的 Releases](https://github.com/xiaojiangqvq/oink/releases) 下载 Windows 修改版安装包和对应源码。[上游 Releases](https://github.com/oinkvm/oink/releases) 提供原版及其 Mac 安装包。

支持的操作系统和版本：

- **Mac（仅上游）**：Apple 芯片（arm64），macOS 14.2 及以上；Intel（x64），macOS 14.2 及以上（未经测试）。本次修改版仅提供 Windows 安装包。
- **Windows**：x64，Windows 10 1809（build 17763）及以上，或 Windows 11。22H2 之前的 Windows 10 版本未经测试。增强版安装包内含官方 WebView2 离线运行库，在系统缺少时安装，适用于 Windows LTSC 等未预装运行库的系统。

如果 SmartScreen 提示“Windows 已保护你的电脑”，仅在出现相应选项时点击 **更多信息 → 仍要运行**。UAC 可能显示发布者未知。

### 赞助

如果这个项目帮助到了你，可以考虑赞助我一些 AI 订阅费用。这些 Token 会让 Oink 发展得更好。

<a href="https://ko-fi.com/hachiwii"><img alt="Ko-fi" src="https://ko-fi.com/img/githubbutton_sm.svg" height="36"></a>

## 贡献

本项目不接受没有上下文的 PR，因为没有人能对代码进行 Review。欢迎通过 [Issues](https://github.com/oinkvm/oink/issues) 提交一切问题反馈和功能请求，在反馈问题时，最好能带上你的设备环境、诊断数据、复现流程和 AI 排查结论。在真实环境中使用和反馈是对该项目的最大贡献。

## 常见问题

**Oink 是基于 Deskflow 或兼容 Deskflow 的吗？**\
不是。Oink 是完全从零开始的项目，使用自研的对等（非客户端-服务端）协议，不兼容其他软件 KVM。

**必须指定一台设备为控制端吗？**\
不必须。Oink 采用对等网络设计，连接在任何设备上的键鼠都可以用来控制其他设备。

**支持共享触摸板手势吗？**\
支持，但 Windows 触摸板未经过测试。

**支持跨操作系统的剪贴板共享和跨设备拖拽吗？**\
支持。剪贴板会在设备间自动同步，也可以直接将文字、图片、文件从一台设备拖拽到另一台设备，甚至直接拖进 Chrome 等应用内。

**个人或商业使用 Oink 需要购买许可吗？**\
不需要。Oink 是以 GPL-3.0-only（附带附加条款）发布的自由软件，可以用于任何个人或商业用途，无需申请额外许可。如果分发 Oink 或基于它修改的版本，必须以同一许可证提供完整源码，保留原作者署名和许可声明，并标明所做的修改；按附加条款，也不得以 Oink 的名义推广衍生产品。仅供自己使用的修改、不对外分发时，没有这些义务。

## 许可证

本项目以 [GPL-3.0-only](LICENSE) 许可证发布，并附有[附加条款](LICENSE-ADDITIONAL-TERMS.md)。
