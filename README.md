# Pointer Trail Enhanced — third-party modification

This fork is based on [Oink v0.3.4](https://github.com/oinkvm/oink/tree/v0.3.4). Version **0.3.4-inhouse.109 (build 109)** adds a choice between the original circle gesture and any mouse movement, independent trail colors, and Windows arrow styles and sizes. It is a third-party modification, not an official Oink release or an endorsement by its authors. Original attribution and documentation follow below.

Download the full **Windows x64 installer** from [this fork's Releases](https://github.com/xiaojiangqvq/oink/releases). `PointerTrail-Setup.exe` contains the complete application MSI and Microsoft's official offline WebView2 Runtime installer; it installs the runtime only when missing. A fresh installation does not require Oink to be installed first. Direct upgrades support Oink **0.3.4 build 108** and the earlier personal movement-trail patch, preserving pairing, layout, and preferences. Install it on each Windows computer. Support for overwriting newer upstream versions is not claimed; this release has no macOS package.

**Do not uninstall before upgrading.** Normal Windows uninstallation removes local application data. Run the new installer directly and use your computer's own keyboard and mouse while the application exits for installation. Existing login-start preferences are retained; for a fresh installation, enable login startup in the app's settings if wanted. The elevated installer does not set another user's startup registry entry.

Find all added controls under **Settings → Keyboard & Mouse**. The original circle mode is the default for fresh or original installations; upgrading the earlier always-on personal patch retains movement mode unless a mode was already explicitly selected. Mode is local to the computer supplying physical mouse input. Trail color and Windows arrow style/size are local to the computer displaying them. Arrow changes also affect other Windows apps; text and resize cursor roles stay unchanged. Select **System** to restore the saved arrow; an external Windows arrow change is preserved.

The fork disables the official Windows update feed. Get future manual upgrades from [this fork's Releases](https://github.com/xiaojiangqvq/oink/releases). There is no old patch-restore button in the full installer. Matching complete source, license notices, and [build instructions](packaging/trail-installer/BUILDING.txt) accompany the release. Do not share private local backups or user data. A fresh-install test on a clean Windows computer has not yet been performed. See [Chinese usage instructions](README.zh-CN.md).

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
- **Windows:** x64, Windows 10 version 1809 (build 17763) or later, or Windows 11. Windows 10 versions before 22H2 are untested. The enhanced installer includes the official offline WebView2 Runtime and installs it when missing, including on Windows LTSC.

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
