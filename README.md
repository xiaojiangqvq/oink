# Pointer Trail Enhanced — third-party modification

Based on [Oink v0.3.4](https://github.com/oinkvm/oink/tree/v0.3.4), version **0.3.4-inhouse.110 (build 110)** adds selectable trail triggering, independent trail colors, and Windows arrow styles/sizes. This is a third-party modification, not an official Oink release. Original attribution and documentation remain below.

Download `PointerTrail-Setup.exe` from [this fork's Releases](https://github.com/xiaojiangqvq/oink/releases) and follow the standard Windows setup wizard on each PC. Installer revision 2 includes the complete Windows x64 app and Microsoft's small WebView2 bootstrapper. **Internet is needed only if WebView2 is missing**, to download the runtime. The app remains build 110.

When Oink is already installed, choose:

- **Overwrite install (default):** upgrade while keeping pairing, layout, and settings.
- **Uninstall:** remove Oink.
- **Fresh install:** uninstall the existing application, then install again.

**Uninstall and Fresh install delete local application settings.** For an upgrade that keeps your setup, choose Overwrite install. Direct upgrades support original 0.3.4 build 108 and the earlier personal trail patch; newer upstream versions are outside this release's supported overwrite scope.

After installation, open Oink from the Start menu. All added controls are in **Settings → Keyboard & Mouse**: original fast-circle or any-movement mode, trail color, and arrow style/size. Arrow changes affect other Windows apps; text and resize cursors stay unchanged. Select System to restore the saved arrow. Mode follows the physical mouse's computer; color and arrow preferences are local to the displaying PC. Existing login-start preferences remain; enable it in settings after a fresh install if wanted.

Future upgrades are manual through [this fork's Releases](https://github.com/xiaojiangqvq/oink/releases); the official Windows update feed is disabled. Complete app and installer source are separate release downloads, not inside the EXE; license notices remain included. See [build instructions](packaging/trail-installer/BUILDING.txt). No macOS package is supplied. A fresh installation on a clean Windows PC has not yet been tested.

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/banner-dark.png">
    <img alt="Oink — Oink Is Not only a KVM. Your computers, working as one." src=".github/assets/banner-light.png" width="860">
  </picture>
</p>

# Oink — Oink Is Not only a KVM

**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

Oink, short for "Oink Is Not only a KVM", is modern software that builds a peer-to-peer sharing network across multiple Windows and Mac computers. Use the keyboard, mouse and trackpad of any device to control any nearby device, with the same native feel everywhere; play the audio of several devices through the speakers or headphones connected to one of them; share the clipboard and drag and drop between devices; discover devices on the local network automatically; all traffic is encrypted by default.

## Install

Get this modified Windows installer and matching source from [the fork's Releases](https://github.com/xiaojiangqvq/oink/releases). [Upstream releases](https://github.com/oinkvm/oink/releases) contain the original project, including its Mac packages.

Supported operating systems and versions:

- **Mac (upstream only):** Apple silicon (arm64), macOS 14.2+; Intel (x64), macOS 14.2+ (untested). This modified release supplies Windows packages only.
- **Windows:** x64, Windows 10 version 1809 (build 17763) or later, or Windows 11. Windows 10 versions before 22H2 are untested. If WebView2 is missing, including on some Windows LTSC systems, its official bootstrapper downloads the runtime during installation and needs internet access.

If SmartScreen says "Windows protected your PC", use **More info → Run anyway** only if offered. UAC may show an unknown publisher.

### Sponsor

If this project helps you, consider sponsoring some of my AI subscription costs. Those tokens help make Oink better.

<a href="https://ko-fi.com/hachiwii"><img alt="Ko-fi" src="https://ko-fi.com/img/githubbutton_sm.svg" height="36"></a>

## Contributing

This project does not accept pull requests without context, because there is no one to review the code. Please use [Issues](https://github.com/oinkvm/oink/issues) for all bug reports and feature requests. When you report a problem, please include your device environment, diagnostic data, steps to reproduce and your AI-assisted investigation's conclusions. Using Oink in real environments and sending feedback is the biggest contribution to this project.

## FAQ

**Is Oink based on, or compatible with, Deskflow?**\
No. Oink is a project started completely from scratch. It uses its own peer-to-peer (not client–server) protocol and is not compatible with other software KVMs.

**Do I have to designate one device as the controller?**\
No. Oink uses a peer-to-peer design: the keyboard and mouse connected to any device can control the other devices.

**Can I share trackpad gestures?**\
Yes, but trackpads on Windows have not been tested.

**Does it support clipboard sharing and drag and drop across operating systems?**\
Yes. The clipboard is synced across devices automatically, and you can drag text, images and files directly from one device to another — even straight into apps such as Chrome.

**Do I need to buy a license for personal or commercial use?**\
No. Oink is free software released under GPL-3.0-only with additional terms, so you can use it for any personal or commercial purpose without asking for any further license. If you distribute Oink or a modified version of it, you must provide the complete source code under the same license, keep the original author attribution and license notices, and mark your changes; under the additional terms you also may not use the Oink name to promote derived products. Modifying Oink only for your own use, without distributing it, carries none of these obligations.

## License

This project is licensed under [GPL-3.0-only](LICENSE) with [additional terms](LICENSE-ADDITIONAL-TERMS.md).
