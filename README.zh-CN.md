# 指针尾迹增强版（第三方修改）

本分支基于 [Oink v0.3.4](https://github.com/oinkvm/oink/tree/v0.3.4)，修改版版本为 **0.3.4-inhouse.109（build 109）**，增加尾迹触发方式、颜色和 Windows 箭头样式选择。它不是 Oink 官方发行版，也不代表原作者认可本修改。原项目说明与署名保留在下方。

- 保留尾迹总开关，增加“快速画圈（原版）／移动即显示”选择；停止移动后按原有动画消退。
- 尾迹可跟随主题色，也可选择预设色或自定义颜色，保留原有尾迹形状。
- 在软件内选择 Windows 箭头样式（原系统样式、白色、黑色、反色）和大小。此设置影响本机其他应用的箭头；文本光标、调整大小等角色不变。“原系统样式”恢复之前的箭头；若你已在 Windows 中另选指针，会保留该外部选择。
- 模式由实际连接鼠标的电脑决定；尾迹颜色由显示尾迹的电脑决定。两台 Windows 电脑分别安装即可各自配置。设置不会通过配对同步。

## 安装增强版

从[本分支的 Releases](https://github.com/xiaojiangqvq/oink/releases) 下载完整 **Windows x64 安装程序** `PointerTrail-Setup.exe`。它包含完整应用 MSI 和微软官方 WebView2 离线运行库，缺少运行库时才安装。新电脑可直接安装，无须先安装原版。

已有 **Oink 0.3.4（build 108）** 或早期个人尾迹补丁的电脑可直接覆盖升级，保留配对、屏幕布局和现有设置。两台 Windows 电脑分别运行安装程序即可。本版未承诺覆盖更新的官方版本，也没有提供 macOS 安装包。

**不要先卸载。** Windows 正常卸载会删除本机应用数据；升级时直接运行新安装包。双击安装程序，选择“安装 / 更新增强版”并确认 Windows 管理员权限提示。安装期间程序会退出，请使用当前电脑自己的键鼠。

完成后在 **设置 → 键鼠** 选择尾迹模式、颜色和鼠标箭头。新安装和原版升级默认使用画圈模式；早期“移动就显示”的个人补丁会保留移动模式，已有明确选择不被覆盖。现有登录启动设置会保留；新安装如需登录时启动，请在应用设置中开启，提权安装过程不会代替用户写入登录启动项。

本分支关闭 Windows 官方更新源，后续从[本分支的 Releases](https://github.com/xiaojiangqvq/oink/releases) 下载新版手动升级。完整安装程序不再提供旧补丁的“恢复原版”按钮。如需恢复之前的 Windows 箭头，请在增强版中选择“原系统样式”。

安装包包含对应完整源码、许可证和构建说明，可从安装窗口的“查看日志与源代码”打开。构建过程见[安装包构建说明](packaging/trail-installer/BUILDING.txt)。本机私有备份和用户数据不应分享。目前尚未在干净的 Windows 电脑上完成全新安装实测。

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
