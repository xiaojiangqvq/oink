using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("指针尾迹增强版安装程序")]
[assembly: AssemblyDescription("基于 Oink 0.3.4 的第三方修改版；完整 Windows 安装程序")]
[assembly: AssemblyCompany("Personal local modification")]
[assembly: AssemblyProduct("Pointer Trail Enhanced Installer")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

internal sealed class Package : IDisposable
{
    internal const string RuntimeName = "MicrosoftEdgeWebView2RuntimeInstallerX64.exe";
    private static readonly string[] Required = { "manifest.json", "payload/Oink.msi", "payload/" + RuntimeName,
        "使用说明.txt", "LICENSE", "LICENSE-ADDITIONAL-TERMS.md", "NOTICE", "THIRD_PARTY_LICENSES.md",
        "third-party-licenses.json", "modified-source.zip", "source-changes.patch", "installer-source.zip", "WEBVIEW2-NOTICE.txt", "WebView2-LICENSE.txt" };
    private readonly Stream resource;
    private readonly ZipArchive zip;
    private readonly Dictionary<string, ZipArchiveEntry> entries;
    internal readonly Dictionary<string, object> Manifest;
    internal static string Hash(Stream stream) { using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
    internal static string HashFile(string path) { using (var stream = File.OpenRead(path)) return Hash(stream); }
    internal static Dictionary<string, object> Json(string text)
    {
        var result = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024, RecursionLimit = 100 }.DeserializeObject(text) as Dictionary<string, object>;
        if (result == null) throw new InvalidDataException("JSON 记录格式错误。");
        return result;
    }
    internal static Dictionary<string, object> ReadJson(string path)
    {
        NoReparse(path);
        if (new FileInfo(path).Length > 1024 * 1024) throw new InvalidDataException("JSON 记录过大。");
        return Json(File.ReadAllText(path, Encoding.UTF8));
    }
    internal static void WriteJson(string path, object value)
    {
        NoReparse(path);
        string staged = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try {
            using (var file = new FileStream(staged, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                byte[] bytes = new UTF8Encoding(false).GetBytes(new JavaScriptSerializer().Serialize(value));
                file.Write(bytes, 0, bytes.Length); file.Flush(true);
            }
            if (File.Exists(path)) File.Replace(staged, path, null); else File.Move(staged, path);
        } finally { if (File.Exists(staged)) File.Delete(staged); }
    }
    internal string ReadDocument(string name)
    {
        if (entries[name].Length > 1024 * 1024) throw new InvalidDataException("文档过大。");
        using (var reader = new StreamReader(entries[name].Open(), Encoding.UTF8)) return reader.ReadToEnd();
    }
    internal Package()
    {
        resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip");
        if (resource == null || Hash(resource) != BuildInfo.ArchiveSha256) throw new InvalidDataException("安装包完整性校验失败。");
        resource.Position = 0;
        zip = new ZipArchive(resource, ZipArchiveMode.Read, false, Encoding.UTF8);
        entries = new Dictionary<string, ZipArchiveEntry>(StringComparer.Ordinal);
        long total = 0;
        foreach (var entry in zip.Entries) {
            if (!Required.Contains(entry.FullName, StringComparer.Ordinal) || entries.ContainsKey(entry.FullName)) throw new InvalidDataException("安装包包含未允许或重复路径。");
            if (entry.Length < 0 || entry.Length > 768L * 1024 * 1024) throw new InvalidDataException("安装包文件过大。");
            total = checked(total + entry.Length);
            if (total > 1536L * 1024 * 1024) throw new InvalidDataException("安装包解压大小超过上限。");
            entries.Add(entry.FullName, entry);
        }
        if (entries.Count != Required.Length || Required.Any(n => !entries.ContainsKey(n))) throw new InvalidDataException("完整安装包文件缺失。");
        using (var reader = new StreamReader(entries["manifest.json"].Open(), new UTF8Encoding(false, true))) {
            if (entries["manifest.json"].Length > 1024 * 1024) throw new InvalidDataException("清单过大。");
            Manifest = Json(reader.ReadToEnd());
        }
        if (Convert.ToInt32(Manifest["schema"]) != 1 || (string)Manifest["kind"] != "third-party-oink-full-installer" ||
            (string)Manifest["architecture"] != "x64" || Convert.ToInt32(Manifest["build"]) != 109 ||
            (string)Manifest["version"] != "0.3.4-inhouse.109" || (string)Manifest["msi_version"] != "0.0.109" ||
            !Regex.IsMatch((string)Manifest["source_tree_sha256"], "^[a-f0-9]{64}$") ||
            !Regex.IsMatch((string)Manifest["source_commit"], "^[a-f0-9]{40}$") ||
            new Guid((string)Manifest["upgrade_code"]) != new Guid("4D39E4BE-6792-4CD6-B344-A5E95A270EA6")) throw new InvalidDataException("安装包版本信息不兼容。");
        new Guid((string)Manifest["product_code"]);
        var files = Manifest["files"] as Dictionary<string, object>;
        if (files == null || files.Count != 2 || !files.ContainsKey("Oink.msi") || !files.ContainsKey(RuntimeName)) throw new InvalidDataException("安装校验清单不完整。");
        foreach (var pair in files) using (var stream = entries["payload/" + pair.Key].Open())
            if (Hash(stream) != (string)pair.Value) throw new InvalidDataException("安装文件校验失败：" + pair.Key);
    }
    internal static void NoReparse(string path)
    {
        string current = Path.GetFullPath(path);
        if (current.StartsWith(@"\\", StringComparison.Ordinal) || current.Length < 3 || current.Substring(2).Contains(":")) throw new IOException("需要本机普通文件夹。");
        while (!String.IsNullOrEmpty(current)) {
            if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new IOException("安装路径不能包含链接或重解析点。");
            current = Path.GetDirectoryName(current);
        }
    }
    internal void Extract(string destination)
    {
        destination = Path.GetFullPath(destination); NoReparse(destination);
        if (Directory.Exists(destination) || File.Exists(destination)) throw new IOException("工作目录已存在。");
        Directory.CreateDirectory(destination);
        string root = destination.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        foreach (var pair in entries) {
            string path = Path.GetFullPath(Path.Combine(destination, pair.Key.Replace('/', Path.DirectorySeparatorChar)));
            if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("非法安装路径。");
            NoReparse(path); Directory.CreateDirectory(Path.GetDirectoryName(path));
            using (var input = pair.Value.Open()) using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { input.CopyTo(output); output.Flush(true); }
        }
        foreach (var pair in (Dictionary<string, object>)Manifest["files"])
            if (HashFile(Path.Combine(destination, "payload", pair.Key)) != (string)pair.Value) throw new IOException("解压文件校验失败。");
    }
    public void Dispose() { zip.Dispose(); resource.Dispose(); }
}

internal static class Native
{
    [DllImport("msi.dll", CharSet = CharSet.Unicode)] private static extern uint MsiEnumRelatedProducts(string code, uint reserved, uint index, StringBuilder product);
    [DllImport("msi.dll", CharSet = CharSet.Unicode)] private static extern uint MsiGetProductInfoEx(string code, string sid, uint context, string property, StringBuilder value, ref uint size);
    internal static int CheckProducts(Dictionary<string, object> manifest)
    {
        int count = 0;
        for (uint index = 0; ; index++) {
            var product = new StringBuilder(39);
            uint result = MsiEnumRelatedProducts(new Guid((string)manifest["upgrade_code"]).ToString("B"), 0, index, product);
            if (result == 259) break;
            if (result != 0) throw new IOException("无法读取 Windows Installer 产品状态。");
            uint size = 128; var value = new StringBuilder(129);
            if (MsiGetProductInfoEx(product.ToString(), null, 4, "VersionString", value, ref size) != 0) throw new IOException("现有 Oink 安装状态不完整，请先修复。");
            CheckVersion(value.ToString(), product.ToString(), (string)manifest["msi_version"], (string)manifest["product_code"]);
            if (++count > 1) throw new IOException("检测到多份 Oink MSI 记录，请先修复现有安装。");
        }
        return count;
    }
    internal static bool IsProductInstalled(string code)
    {
        uint size = 128; var value = new StringBuilder(129);
        return MsiGetProductInfoEx(new Guid(code).ToString("B"), null, 4, "VersionString", value, ref size) == 0;
    }
    internal static void CheckVersion(string installed, string product, string target, string expected)
    {
        int compare = new Version(installed).CompareTo(new Version(target));
        if (compare > 0) throw new IOException("已安装较新版本的 Oink，本安装程序不会降级覆盖。");
        if (compare == 0 && new Guid(product) != new Guid(expected)) throw new IOException("已安装相同构建号的其他版本，请使用更新构建的增强版。");
    }
    internal static bool HasRuntime()
    {
        using (var machine = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry32))
        using (var key = machine.OpenSubKey(@"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")) {
            Version version; return key != null && Version.TryParse(Convert.ToString(key.GetValue("pv")), out version) && version > new Version(0, 0, 0, 0);
        }
    }
    internal static void CheckWindows()
    {
        if (!Environment.Is64BitOperatingSystem || !Environment.Is64BitProcess) throw new PlatformNotSupportedException("本安装程序需要 Windows x64。");
        using (var machine = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
        using (var key = machine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion")) {
            int build; if (key == null || !Int32.TryParse(Convert.ToString(key.GetValue("CurrentBuildNumber")), out build) || build < 17763) throw new PlatformNotSupportedException("需要 Windows 10 1809 或更新的 x64 Windows。");
        }
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct TrustFile { internal uint size; [MarshalAs(UnmanagedType.LPWStr)] internal string path; internal IntPtr handle, subject; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct TrustData { internal uint size; internal IntPtr policy, sip; internal uint ui, revocation, union; internal IntPtr file; internal uint stateAction; internal IntPtr state; [MarshalAs(UnmanagedType.LPWStr)] internal string url; internal uint flags, context; }
    [DllImport("wintrust.dll", ExactSpelling = true, PreserveSig = true)] private static extern uint WinVerifyTrust(IntPtr window, ref Guid action, ref TrustData data);
    internal static void VerifyMicrosoftRuntime(string path)
    {
        var file = new TrustFile { size = (uint)Marshal.SizeOf(typeof(TrustFile)), path = path };
        IntPtr pointer = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(TrustFile)));
        try {
            Marshal.StructureToPtr(file, pointer, false);
            var data = new TrustData { size = (uint)Marshal.SizeOf(typeof(TrustData)), ui = 2, union = 1, file = pointer, flags = 0x1000 };
            var action = new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
            if (WinVerifyTrust(new IntPtr(-1), ref action, ref data) != 0) throw new IOException("微软 WebView2 安装程序的数字签名验证失败。");
            using (var certificate = new X509Certificate2(X509Certificate.CreateFromSignedFile(path)))
                if (certificate.GetNameInfo(X509NameType.SimpleName, false) != "Microsoft Corporation") throw new IOException("WebView2 安装程序不是微软签名。");
        } finally { Marshal.DestroyStructure(pointer, typeof(TrustFile)); Marshal.FreeHGlobal(pointer); }
    }
}

internal static class LegacySettings
{
    internal static bool Pending()
    {
        string marker = Path.Combine(Worker.InstallRoot, "custom-trail-installed.json");
        if (!File.Exists(marker)) return false;
        Worker.VerifyProtectedDirectory(Worker.InstallRoot);
        Worker.VerifyProtectedFile(marker);
        object id; return Package.ReadJson(marker).TryGetValue("patch_id", out id) && id is string && ((string)id).StartsWith("movement-trail-0.3.4-", StringComparison.Ordinal);
    }
    internal static bool AddMissing(Dictionary<string, object> settings)
    {
        if (!settings.ContainsKey("schema") || Convert.ToInt32(settings["schema"]) != 1) throw new IOException("设置结构不兼容。");
        object value; var local = settings.TryGetValue("local", out value) ? value as Dictionary<string, object> : null;
        if (local == null) throw new IOException("设置缺少 local。");
        var routing = local.TryGetValue("routing", out value) ? value as Dictionary<string, object> : null;
        if (routing == null) throw new IOException("设置缺少 routing。");
        if (routing.ContainsKey("cursor_trail_always")) return false;
        routing.Add("cursor_trail_always", true); return true;
    }
    internal static void MigrateOwnProfile()
    {
        if (InstallerForm.IsAdministrator()) throw new IOException("请正常打开 Oink，在键鼠设置中选择“移动即显示”尾迹模式。");
        string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Oink", "settings.json");
        if (!File.Exists(path)) throw new IOException("尚无本机设置，请打开 Oink 后选择“移动即显示”尾迹模式。");
        Package.NoReparse(path);
        // MSI stops all sessions. Stop this user's backend once more before a
        // same-user atomic preferences update; no administrator edits profiles.
        string cli = Path.Combine(Worker.InstallRoot, "oink-agent.exe");
        using (var process = Process.Start(new ProcessStartInfo(cli, "stop") { UseShellExecute = false, CreateNoWindow = true })) {
            if (process == null || !process.WaitForExit(20000) || process.ExitCode != 0) throw new IOException("后台尚未退出，请在应用里选择“移动即显示”尾迹模式。");
        }
        string before = Package.HashFile(path); var settings = Package.ReadJson(path);
        if (!AddMissing(settings)) return;
        string staged = path + ".trail-" + Guid.NewGuid().ToString("N") + ".tmp";
        try {
            Package.WriteJson(staged, settings); File.SetAccessControl(staged, File.GetAccessControl(path));
            Package.NoReparse(path);
            if (Package.HashFile(path) != before) throw new IOException("设置在安装期间发生变化，请在应用里选择“移动即显示”尾迹模式。");
            File.Replace(staged, path, null);
        } finally { if (File.Exists(staged)) File.Delete(staged); }
    }
}

internal static class Worker
{
    internal static string InstallRoot { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Oink"); } }
    internal static string Root { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "OinkTrailEnhancedInstaller"); } }
    private const string PublicAcl = "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;GRGX;;;BU)";
    private const string PrivateAcl = "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)";
    internal static void VerifyProtectedDirectory(string path)
    {
        Package.NoReparse(path); var acl = Directory.GetAccessControl(path);
        VerifyAcl(acl);
    }
    internal static void VerifyProtectedFile(string path) { Package.NoReparse(path); VerifyAcl(File.GetAccessControl(path)); }
    internal static void CheckContainers()
    {
        string data = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        Package.NoReparse(data);
        // The OS-known ProgramData folder is the trust boundary. Its ordinary
        // create-child permission is safe; delete-child/ownership/ACL control
        // by non-administrators is not. The staging child has its own DACL.
        VerifyAcl(Directory.GetAccessControl(data), true);
        if (Directory.Exists(Root)) VerifyProtectedDirectory(Root);
    }
    private static void VerifyAcl(FileSystemSecurity acl, bool container = false)
    {
        var privileged = new HashSet<string>(new[] { "S-1-5-18", "S-1-5-32-544", "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464" });
        if (!privileged.Contains(((SecurityIdentifier)acl.GetOwner(typeof(SecurityIdentifier))).Value)) throw new IOException("安装路径所有者不符合保护要求。");
        var raw = new RawSecurityDescriptor(acl.GetSecurityDescriptorBinaryForm(), 0);
        if (raw.DiscretionaryAcl == null) throw new IOException("安装路径缺少保护权限。");
        var write = FileSystemRights.Delete | FileSystemRights.DeleteSubdirectoriesAndFiles | FileSystemRights.ChangePermissions | FileSystemRights.TakeOwnership;
        if (!container) write |= FileSystemRights.Write;
        foreach (FileSystemAccessRule rule in acl.GetAccessRules(true, true, typeof(SecurityIdentifier)))
            if (rule.AccessControlType == AccessControlType.Allow && (rule.PropagationFlags & PropagationFlags.InheritOnly) == 0 && (rule.FileSystemRights & write) != 0 && !privileged.Contains(((SecurityIdentifier)rule.IdentityReference).Value)) throw new IOException("安装路径允许非管理员修改。");
    }
    private static void CreateProtected(string path, bool isPrivate)
    {
        Package.NoReparse(path);
        if (!Directory.Exists(path)) { var acl = new DirectorySecurity(); acl.SetSecurityDescriptorSddlForm(isPrivate ? PrivateAcl : PublicAcl); Directory.CreateDirectory(path, acl); }
        VerifyProtectedDirectory(path);
    }
    private static void CheckTree(string directory)
    {
        VerifyProtectedDirectory(directory);
        foreach (string file in Directory.EnumerateFiles(directory)) { Package.NoReparse(file); VerifyAcl(File.GetAccessControl(file)); }
        foreach (string child in Directory.EnumerateDirectories(directory)) CheckTree(child);
    }
    private static string ArchiveLegacy(string runId)
    {
        var names = new[] { "custom-trail-backups", "custom-trail-installer", "custom-trail-installed.json" };
        if (!names.Any(n => File.Exists(Path.Combine(InstallRoot, n)) || Directory.Exists(Path.Combine(InstallRoot, n)))) return "";
        VerifyProtectedDirectory(InstallRoot);
        string archiveRoot = Path.Combine(Root, "private-backups"); CreateProtected(archiveRoot, true);
        string archive = Path.Combine(archiveRoot, runId); CreateProtected(archive, true);
        foreach (string name in names) {
            string source = Path.GetFullPath(Path.Combine(InstallRoot, name));
            string target = Path.GetFullPath(Path.Combine(archive, name));
            if (!String.Equals(Path.GetDirectoryName(source), InstallRoot, StringComparison.OrdinalIgnoreCase) || !String.Equals(Path.GetDirectoryName(target), archive, StringComparison.OrdinalIgnoreCase)) throw new IOException("备份归档路径无效。");
            Package.NoReparse(source); Package.NoReparse(target);
            if (Directory.Exists(source)) { CheckTree(source); Directory.Move(source, target); }
            else if (File.Exists(source)) { VerifyAcl(File.GetAccessControl(source)); File.Move(source, target); }
        }
        return archive;
    }
    internal static int Run(string runId, bool acceptRuntime)
    {
        if (!InstallerForm.IsAdministrator()) throw new UnauthorizedAccessException("需要正常的 Windows 管理员授权。");
        if (!Regex.IsMatch(runId, "^[a-f0-9]{32}$")) throw new ArgumentException("操作参数无效。");
        Native.CheckWindows();
        // ProgramData itself normally allows users to create directories. We
        // create an explicitly protected child and reject hostile pre-creation.
        CheckContainers();
        CreateProtected(Root, false);
        string directory = Path.Combine(Root, runId); bool installed = false;
        var result = new Dictionary<string, object> { { "installed", false }, { "message", "安装尚未完成。" }, { "reboot_required", false } };
        try {
            using (var package = new Package()) {
                package.Extract(directory); VerifyProtectedDirectory(directory);
                int products = Native.CheckProducts(package.Manifest);
                bool repair = Native.IsProductInstalled((string)package.Manifest["product_code"]);
                if (Directory.Exists(InstallRoot)) {
                    VerifyProtectedDirectory(Path.GetDirectoryName(InstallRoot)); VerifyProtectedDirectory(InstallRoot);
                    if (products == 0 && Directory.EnumerateFileSystemEntries(InstallRoot).Any()) throw new IOException("检测到未登记的 Oink 目录，请先修复现有安装，未覆盖文件。");
                }
                if (!Native.HasRuntime()) {
                    if (!acceptRuntime) throw new IOException("缺少 WebView2，请在安装界面确认微软运行时许可后重试。");
                    string runtime = Path.Combine(directory, "payload", Package.RuntimeName); Native.VerifyMicrosoftRuntime(runtime);
                    int runtimeCode = RunProcess(runtime, "/silent /install", directory);
                    if ((runtimeCode != 0 && runtimeCode != 3010) || !Native.HasRuntime()) throw new IOException("WebView2 安装未完成（代码 " + runtimeCode + "），Oink 尚未修改。");
                }
                string msi = Path.Combine(directory, "payload", "Oink.msi");
                string log = Path.Combine(directory, "install-msi.log");
                string executable = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "msiexec.exe");
                // MSI owns its maintenance lock and major-upgrade transaction.
                // No uninstall, old patch restore, or elevated per-user setup.
                int code = RunProcess(executable, "/i " + InstallerForm.Quote(msi) + " /passive /norestart REBOOT=ReallySuppress OinkLaunch=0" + (repair ? " REINSTALL=ALL" : "") + " /L*v " + InstallerForm.Quote(log), directory);
                if (code != 0 && code != 3010) throw new IOException("Oink 安装未完成（Windows Installer 代码 " + code + "）。请查看 install-msi.log；未执行清除用户数据操作。");
                installed = true; result["installed"] = true; result["reboot_required"] = code == 3010;
                result["message"] = "完整安装已完成，原有配对、布局和设置保留。";
                try { result["legacy_archive"] = ArchiveLegacy(runId); }
                catch (Exception error) { result["message"] = "新版本已安装，但旧补丁私有备份归档未完成。现有数据保留。详情：" + error.Message; result["archive_warning"] = true; }
            }
            Package.WriteJson(Path.Combine(directory, "result.json"), result); return 0;
        } catch (Exception error) {
            result["installed"] = installed; result["message"] = (installed ? "新版本已安装；后续整理未完成：" : "安装未完成：") + error.Message;
            if (Directory.Exists(directory)) try { Package.WriteJson(Path.Combine(directory, "result.json"), result); } catch { }
            return installed ? 0 : 1;
        }
    }
    private static int RunProcess(string executable, string arguments, string directory)
    {
        using (var process = Process.Start(new ProcessStartInfo(executable, arguments) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = directory })) {
            if (process == null) throw new IOException("无法启动安装进程。"); process.WaitForExit(); return process.ExitCode;
        }
    }
}

internal sealed class InstallerForm : Form
{
    private readonly Button install = new Button(), open = new Button(), logs = new Button();
    private readonly Label status = new Label();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly CheckBox runtimeConsent = new CheckBox();
    private bool working; private string workDirectory;
    internal InstallerForm(bool previewMissingRuntime = false)
    {
        Text = "指针尾迹增强版安装程序"; Font = new Font("Microsoft YaHei UI", 10F); BackColor = Color.FromArgb(249, 250, 252);
        ClientSize = new Size(680, 520); FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen; AutoScaleMode = AutoScaleMode.Dpi;
        var heading = new Label { Text = "让指针更容易找到", Font = new Font(Font.FontFamily, 22F, FontStyle.Bold), Bounds = new Rectangle(32, 25, 610, 48) };
        var subtitle = new Label { Text = "基于 Oink 0.3.4 的第三方修改版 · 完整安装程序", Bounds = new Rectangle(34, 80, 610, 28), ForeColor = Color.FromArgb(104, 111, 128) };
        var description = new Label { Text = "新电脑可直接安装；已有 Oink 可覆盖升级，无需先卸载。\n保留设备配对、屏幕布局和设置，两台电脑分别运行即可。\n在“设置 → 键鼠”中选择尾迹模式、颜色和指针样式。\n\n适用于 Windows 10 1809 及更新版本 · x64", Bounds = new Rectangle(34, 126, 610, 120) };
        var privacy = new Label { Text = "本应用使用 WebView2。Microsoft Defender SmartScreen\n可能向微软发送安全相关信息，详见下方许可与隐私说明。", Bounds = new Rectangle(34, 252, 610, 42), ForeColor = Color.FromArgb(94, 102, 119) };
        runtimeConsent.Text = "同意微软 WebView2 运行时许可，并在缺少时安装此组件"; runtimeConsent.Bounds = new Rectangle(34, 297, 610, 28);
        runtimeConsent.Visible = previewMissingRuntime || !Native.HasRuntime(); runtimeConsent.Checked = false;
        var terms = new LinkLabel { Text = "查看 WebView2 许可、隐私与 SmartScreen 说明", Bounds = new Rectangle(34, 330, 610, 25) };
        terms.LinkClicked += (sender, args) => {
            try {
                using (var package = new Package()) using (var dialog = new Form { Text = "微软 WebView2 运行时许可", Width = 780, Height = 640, StartPosition = FormStartPosition.CenterParent }) {
                    var text = new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill, Font = new Font("Microsoft YaHei UI", 10F), Text = package.ReadDocument("WEBVIEW2-NOTICE.txt") + "\r\n\r\n" + package.ReadDocument("WebView2-LICENSE.txt") };
                    dialog.Controls.Add(text); dialog.ShowDialog(this);
                }
            } catch (Exception error) { MessageBox.Show(this, error.Message, Text); }
        };
        install.Text = "安装 / 更新增强版"; install.Bounds = new Rectangle(34, 365, 360, 46); install.BackColor = Color.FromArgb(226, 68, 119); install.ForeColor = Color.White; install.FlatStyle = FlatStyle.Flat; install.FlatAppearance.BorderSize = 0;
        install.Click += async (sender, args) => await Run();
        open.Text = "打开 Oink"; open.Bounds = new Rectangle(410, 365, 234, 46); open.Enabled = false; open.Click += (sender, args) => OpenOink();
        progress.Bounds = new Rectangle(34, 425, 610, 7); progress.Visible = false;
        status.Text = "安装会短暂退出 Oink，请使用本机键鼠。"; status.Bounds = new Rectangle(34, 443, 610, 38); status.ForeColor = Color.FromArgb(94, 102, 119);
        logs.Text = "查看日志与源代码"; logs.Bounds = new Rectangle(440, 487, 210, 26); logs.FlatStyle = FlatStyle.Flat; logs.FlatAppearance.BorderSize = 0; logs.Visible = false;
        logs.Click += (sender, args) => { if (workDirectory != null) Process.Start("explorer.exe", Quote(workDirectory)); };
        Controls.AddRange(new Control[] { heading, subtitle, description, privacy, runtimeConsent, terms, install, open, progress, status, logs });
        FormClosing += (sender, args) => { if (working) { args.Cancel = true; status.Text = "安装正在进行，请稍候。"; } };
    }
    internal static string Quote(string value) { if (value.Contains("\"") || value.Contains("\0") || value.EndsWith("\\", StringComparison.Ordinal)) throw new ArgumentException("Invalid process argument."); return "\"" + value + "\""; }
    internal static bool IsAdministrator() { using (var identity = WindowsIdentity.GetCurrent()) return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator); }
    private async Task Run()
    {
        if (working) return;
        if (!Native.HasRuntime() && !runtimeConsent.Checked) { runtimeConsent.Visible = true; MessageBox.Show(this, "此电脑需要微软 WebView2 运行时。请阅读许可并勾选同意后安装。", Text); return; }
        working = true; install.Enabled = open.Enabled = false; progress.Visible = true; progress.Style = ProgressBarStyle.Marquee;
        status.Text = "正在校验完整安装包，随后请确认 Windows 管理员权限提示。";
        try {
            bool legacy = LegacySettings.Pending();
            await Task.Run(() => { using (var package = new Package()) Native.CheckProducts(package.Manifest); });
            string runId = Guid.NewGuid().ToString("N"); string directory = Path.Combine(Worker.Root, runId); bool consent = runtimeConsent.Checked;
            int code = await Task.Run(() => {
                var start = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location, "--worker " + runId + " " + (consent ? "runtime-accepted" : "runtime-not-needed")) { UseShellExecute = true, Verb = "runas", WindowStyle = ProcessWindowStyle.Hidden };
                using (var process = Process.Start(start)) { if (process == null) throw new IOException("无法启动安装进程。"); process.WaitForExit(); return process.ExitCode; }
            });
            if (Directory.Exists(directory)) { workDirectory = directory; logs.Visible = true; }
            var result = File.Exists(Path.Combine(directory, "result.json")) ? Package.ReadJson(Path.Combine(directory, "result.json")) : null;
            if (code != 0 || result == null || !Convert.ToBoolean(result["installed"])) throw new IOException(result == null ? "安装未完成，请查看安装日志。" : Convert.ToString(result["message"]));
            string message = Convert.ToString(result["message"]);
            if (legacy) {
                try { await Task.Run(() => LegacySettings.MigrateOwnProfile()); }
                catch (Exception error) { message += "\n旧版移动即显示模式未自动迁移：" + error.Message; }
            }
            bool reboot = Convert.ToBoolean(result["reboot_required"]);
            status.Text = reboot ? "安装完成。Windows 要求重启，请重启后打开 Oink。" : "安装完成，配对和布局已保留。请点击“打开 Oink”。";
            open.Enabled = !reboot && !IsAdministrator();
            if (IsAdministrator()) message += "\n请从开始菜单正常打开 Oink。";
            if (result.ContainsKey("archive_warning") || message.Contains("未自动迁移") || reboot) MessageBox.Show(this, message + (reboot ? "\n请重启 Windows。" : ""), Text, MessageBoxButtons.OK, MessageBoxIcon.Information);
        } catch (Exception error) {
            var windows = error as System.ComponentModel.Win32Exception;
            status.Text = windows != null && windows.NativeErrorCode == 1223 ? "已取消权限提示，没有开始安装。" : "安装未完成，请查看提示和日志。";
            if (windows == null || windows.NativeErrorCode != 1223) MessageBox.Show(this, error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        } finally { working = false; progress.Visible = false; install.Enabled = true; }
    }
    private void OpenOink()
    {
        if (IsAdministrator()) { MessageBox.Show(this, "请从 Windows 开始菜单正常打开 Oink。", Text); return; }
        try { Process.Start(new ProcessStartInfo(Path.Combine(Worker.InstallRoot, "oink.exe")) { UseShellExecute = true }); }
        catch (Exception error) { MessageBox.Show(this, error.Message, Text); }
    }
}

internal static class Program
{
    private static void SelfTests(string output)
    {
        var settings = Package.Json("{\"schema\":1,\"local\":{\"routing\":{\"cursor_trail\":false}},\"unknown\":23}");
        if (!LegacySettings.AddMissing(settings) || LegacySettings.AddMissing(settings) || Convert.ToInt32(settings["unknown"]) != 23) throw new Exception("Legacy migration rule failure.");
        var explicitFalse = Package.Json("{\"schema\":1,\"local\":{\"routing\":{\"cursor_trail_always\":false}}}");
        if (LegacySettings.AddMissing(explicitFalse)) throw new Exception("Explicit preference overwritten.");
        string a = "11111111-1111-1111-1111-111111111111", b = "22222222-2222-2222-2222-222222222222";
        Native.CheckVersion("0.0.108", a, "0.0.109", b); Native.CheckVersion("0.0.109", b, "0.0.109", b);
        foreach (string version in new[] { "0.0.109", "0.0.110" }) { bool refused = false; try { Native.CheckVersion(version, a, "0.0.109", b); } catch (IOException) { refused = true; } if (!refused) throw new Exception("Version refusal failed."); }
        Package.WriteJson(output, new { passed = true, no_installation_performed = true, checks = new[] { "legacy absent-only mode migration", "explicit false preservation", "unknown preferences preservation", "upgrade and repair version rules", "same-version other product and downgrade refusal" } });
    }
    [STAThread] private static int Main(string[] args)
    {
        try {
            if (args.Length == 3 && args[0] == "--worker" && (args[2] == "runtime-accepted" || args[2] == "runtime-not-needed")) return Worker.Run(args[1], args[2] == "runtime-accepted");
            if (args.Length == 2 && args[0] == "--test-rules") { SelfTests(args[1]); return 0; }
            if (args.Length == 2 && args[0] == "--inspect-host") {
                Native.CheckWindows(); Worker.CheckContainers();
                var manifest = new Dictionary<string, object> { { "upgrade_code", "4D39E4BE-6792-4CD6-B344-A5E95A270EA6" }, { "product_code", "D4AB2013-7F00-537B-A3C6-2E8031D50E0C" }, { "msi_version", "0.0.109" } };
                Package.WriteJson(args[1], new { runtime_installed = Native.HasRuntime(), related_products = Native.CheckProducts(manifest), legacy_mode_pending = LegacySettings.Pending(), no_installation_performed = true }); return 0;
            }
            if (args.Length == 2 && args[0] == "--verify-runtime") { Native.VerifyMicrosoftRuntime(args[1]); return 0; }
            if (args.Length == 2 && args[0] == "--verify-package") { using (var package = new Package()) Package.WriteJson(args[1], new { verified = true, source_tree_sha256 = package.Manifest["source_tree_sha256"], source_commit = package.Manifest["source_commit"], archive_sha256 = BuildInfo.ArchiveSha256 }); return 0; }
            if (args.Length == 2 && args[0] == "--extract-package") { using (var package = new Package()) package.Extract(args[1]); return 0; }
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && (args[0] == "--render-preview" || args[0] == "--render-preview-missing-runtime")) { using (var form = new InstallerForm(args[0] == "--render-preview-missing-runtime")) { form.ShowInTaskbar = false; form.Opacity = 0; form.Show(); using (var bitmap = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(bitmap, new Rectangle(0, 0, bitmap.Width, bitmap.Height)); bitmap.Save(args[1], System.Drawing.Imaging.ImageFormat.Png); } form.Close(); } return 0; }
            if (args.Length != 0) throw new ArgumentException("不支持的安装参数。");
            Native.CheckWindows(); Application.Run(new InstallerForm()); return 0;
        } catch (Exception error) { if (args.Length == 0) MessageBox.Show(error.Message, "指针尾迹增强版安装程序", MessageBoxButtons.OK, MessageBoxIcon.Error); else Console.Error.WriteLine(error.ToString()); return 1; }
    }
}
