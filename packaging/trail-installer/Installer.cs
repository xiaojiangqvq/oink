using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: AssemblyTitle("指针尾迹增强版安装程序")]
[assembly: AssemblyDescription("基于 Oink 0.3.4 的第三方修改版；个人覆盖安装工具")]
[assembly: AssemblyCompany("Personal local modification")]
[assembly: AssemblyProduct("Personal Pointer Trail Installer")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

internal sealed class Package : IDisposable
{
    private static readonly string[] Required = {
        "manifest.json", "Run-Patch.ps1", "Patch-Common.ps1", "Upgrade-TrailPatch.ps1",
        "Install-TrailPatch.ps1", "Restore-OriginalOink.ps1",
        "payload/oink.exe", "payload/oink-agent.exe", "payload/oink-build.json", "payload/report-manifest.json"
    };
    private static readonly HashSet<string> Allowed = new HashSet<string>(Required.Concat(new[] {
        "使用说明.txt", "LICENSE", "LICENSE-ADDITIONAL-TERMS.md", "NOTICE", "THIRD_PARTY_LICENSES.md",
        "third-party-licenses.json", "modified-source.zip", "source-changes.patch", "installer-source.zip"
    }), StringComparer.Ordinal);
    private readonly Stream resource;
    private readonly ZipArchive zip;
    private readonly Dictionary<string, ZipArchiveEntry> entries;
    internal readonly Dictionary<string, object> Manifest;
    internal string PatchId { get { return (string)Manifest["patch_id"]; } }

    private static string Hash(Stream stream)
    {
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }

    internal static string HashFile(string path)
    {
        using (var stream = File.OpenRead(path)) return Hash(stream);
    }

    internal Package()
    {
        resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip");
        if (resource == null) throw new InvalidDataException("安装包资源缺失。");
        if (Hash(resource) != BuildInfo.ArchiveSha256) throw new InvalidDataException("安装包完整性校验失败。");
        resource.Position = 0;
        zip = new ZipArchive(resource, ZipArchiveMode.Read, false, Encoding.UTF8);
        entries = new Dictionary<string, ZipArchiveEntry>(StringComparer.Ordinal);
        long total = 0;
        foreach (var entry in zip.Entries)
        {
            if (!Allowed.Contains(entry.FullName) || entries.ContainsKey(entry.FullName))
                throw new InvalidDataException("安装包包含未允许的文件或重复路径。");
            if (entry.Length < 0 || entry.Length > 256L * 1024 * 1024)
                throw new InvalidDataException("安装包文件过大。");
            total = checked(total + entry.Length);
            if (total > 512L * 1024 * 1024) throw new InvalidDataException("安装包解压大小超过上限。");
            entries.Add(entry.FullName, entry);
        }
        foreach (var name in Required)
            if (!entries.ContainsKey(name)) throw new InvalidDataException("安装包文件缺失：" + name);
        Manifest = Json(ReadText("manifest.json"));
        if (Convert.ToInt32(Manifest["schema"]) != 1 || (string)Manifest["base_version"] != "0.3.4" ||
            Convert.ToInt32(Manifest["base_build"]) != 108 || (string)Manifest["architecture"] != "x64" ||
            (string)Manifest["kind"] != "personal-oink-movement-trail-patch")
            throw new InvalidDataException("安装包版本信息不兼容。");
        var files = Manifest["files"] as Dictionary<string, object>;
        string[] payload = { "oink.exe", "oink-agent.exe", "oink-build.json", "report-manifest.json" };
        if (files == null || files.Count != payload.Length || payload.Any(p => !files.ContainsKey(p)))
            throw new InvalidDataException("安装包校验清单不完整。");
        foreach (var name in payload)
            using (var stream = entries["payload/" + name].Open())
                if (Hash(stream) != (string)files[name]) throw new InvalidDataException("程序文件校验失败：" + name);
        foreach (var name in new[] { "oink-build.json", "report-manifest.json" })
            if ((string)Json(ReadText("payload/" + name))["source_tree_sha256"] != (string)Manifest["source_tree_sha256"])
                throw new InvalidDataException("程序来源信息不一致。");
    }

    internal static Dictionary<string, object> Json(string text)
    {
        var serializer = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024, RecursionLimit = 100 };
        var value = serializer.DeserializeObject(text) as Dictionary<string, object>;
        if (value == null) throw new InvalidDataException("JSON 记录格式错误。");
        return value;
    }

    private string ReadText(string name)
    {
        if (entries[name].Length > 1024 * 1024) throw new InvalidDataException("JSON 记录过大。");
        using (var stream = entries[name].Open())
        using (var reader = new StreamReader(stream, new UTF8Encoding(false, true))) return reader.ReadToEnd();
    }

    internal static void NoReparse(string path)
    {
        string current = Path.GetFullPath(path);
        if (current.StartsWith(@"\\", StringComparison.Ordinal) || current.Substring(2).Contains(":"))
            throw new IOException("请选择本机普通文件夹。");
        while (!String.IsNullOrEmpty(current))
        {
            if ((File.Exists(current) || Directory.Exists(current)) &&
                (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("安装工作目录不能包含链接或重解析点。");
            current = Path.GetDirectoryName(current);
        }
    }

    internal void Extract(string destination)
    {
        destination = Path.GetFullPath(destination);
        NoReparse(destination);
        if (Directory.Exists(destination) || File.Exists(destination))
            throw new IOException("安装工作目录已经存在，请重新运行安装程序。");
        Directory.CreateDirectory(destination);
        string root = destination.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        foreach (var pair in entries)
        {
            string path = Path.GetFullPath(Path.Combine(destination, pair.Key.Replace('/', Path.DirectorySeparatorChar)));
            if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("非法安装路径。");
            NoReparse(path);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            using (var input = pair.Value.Open())
            using (var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                input.CopyTo(output);
                output.Flush(true);
            }
        }
        var hashes = (Dictionary<string, object>)Manifest["files"];
        foreach (var pair in hashes)
            if (HashFile(Path.Combine(destination, "payload", pair.Key)) != (string)pair.Value)
                throw new IOException("解压后的程序文件校验失败。");
    }

    public void Dispose() { zip.Dispose(); resource.Dispose(); }
}

internal sealed class InstallerForm : Form
{
    private readonly Button install = new Button();
    private readonly Button restore = new Button();
    private readonly Button open = new Button();
    private readonly Button logs = new Button();
    private readonly Label status = new Label();
    private readonly Label restoreNote = new Label();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly bool? previewPointer;
    private bool customPointer;
    private bool working;
    private string workDirectory;

    internal InstallerForm(bool? previewPointer = null)
    {
        this.previewPointer = previewPointer;
        Text = "指针尾迹增强版安装程序";
        Font = new Font("Microsoft YaHei UI", 10F);
        BackColor = Color.FromArgb(249, 250, 252);
        ClientSize = new Size(650, 415);
        MinimumSize = Size;
        MaximumSize = Size;
        MaximizeBox = false;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;

        var heading = new Label { Text = "让指针更容易找到", Font = new Font(Font.FontFamily, 22F, FontStyle.Bold),
            AutoSize = false, Bounds = new Rectangle(32, 25, 585, 48), ForeColor = Color.FromArgb(35, 40, 52) };
        var subtitle = new Label { Text = "基于 Oink 0.3.4 的第三方修改版", AutoSize = false,
            Bounds = new Rectangle(34, 79, 580, 28), ForeColor = Color.FromArgb(104, 111, 128) };
        var description = new Label { Text = "覆盖安装到现有 Oink，保留配对、屏幕布局和设置。\n安装后可在应用里选择尾迹模式、颜色和指针样式。\n\n适用于 Windows x64 · Oink 0.3.4（build 108）",
            AutoSize = false, Bounds = new Rectangle(34, 129, 580, 108), ForeColor = Color.FromArgb(60, 67, 82) };
        install.Text = "安装 / 更新增强版";
        install.Bounds = new Rectangle(34, 256, 254, 45);
        install.BackColor = Color.FromArgb(226, 68, 119);
        install.ForeColor = Color.White;
        install.FlatStyle = FlatStyle.Flat;
        install.FlatAppearance.BorderSize = 0;
        install.Click += async (sender, args) => await Run("Upgrade");
        restore.Text = "恢复原版";
        restore.Bounds = new Rectangle(302, 256, 145, 45);
        restore.Click += async (sender, args) => await Run("Restore");
        open.Text = "打开 Oink";
        open.Bounds = new Rectangle(461, 256, 154, 45);
        open.Enabled = false;
        open.Click += (sender, args) => OpenOink();
        progress.Bounds = new Rectangle(34, 316, 581, 7);
        progress.Visible = false;
        status.Text = "无需先卸载。安装会短暂退出 Oink，请使用本机键鼠。";
        status.Bounds = new Rectangle(34, 339, 581, 45);
        status.ForeColor = Color.FromArgb(94, 102, 119);
        logs.Text = "查看日志与源代码";
        logs.FlatStyle = FlatStyle.Flat;
        logs.FlatAppearance.BorderSize = 0;
        logs.ForeColor = Color.FromArgb(98, 107, 124);
        logs.Bounds = new Rectangle(428, 378, 191, 28);
        logs.Visible = false;
        logs.Click += (sender, args) => { if (workDirectory != null) Process.Start("explorer.exe", Quote(workDirectory)); };
        restoreNote.Text = "恢复程序会保留当前 Windows 指针样式。要恢复原样，\n请先在增强版的设置中将指针样式选为“系统”。";
        restoreNote.Bounds = new Rectangle(34, 386, 581, 40);
        restoreNote.Font = new Font(Font.FontFamily, 9F);
        restoreNote.ForeColor = Color.FromArgb(94, 102, 119);
        restoreNote.Visible = false;
        Controls.AddRange(new Control[] { heading, subtitle, description, install, restore, open, progress, status, logs, restoreNote });
        Activated += (sender, args) => RefreshRestoreNote();
        RefreshRestoreNote();
        FormClosing += (sender, args) => {
            if (working) { args.Cancel = true; status.Text = "正在完成安装或恢复，请稍候。"; }
        };
    }

    private static bool HasCustomPointerPreference()
    {
        try {
            string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Oink", "settings.json");
            Package.NoReparse(path);
            if (!File.Exists(path) || new FileInfo(path).Length > 1024 * 1024) return false;
            var settings = Package.Json(File.ReadAllText(path, Encoding.UTF8));
            object local, style;
            if (!settings.TryGetValue("local", out local)) return false;
            var values = local as Dictionary<string, object>;
            return values != null && values.TryGetValue("pointer_style", out style) &&
                style is string && (string)style != "system";
        } catch { return false; }
    }

    private void RefreshRestoreNote()
    {
        bool desired = previewPointer ?? HasCustomPointerPreference();
        if (desired == customPointer) return;
        customPointer = desired;
        MinimumSize = MaximumSize = Size.Empty;
        ClientSize = new Size(650, desired ? 460 : 415);
        MinimumSize = MaximumSize = Size;
        restoreNote.Visible = desired;
        restore.Text = desired ? "恢复原版程序" : "恢复原版";
        logs.Top = ClientSize.Height - 37;
    }

    internal static string Quote(string value)
    {
        if (value.Contains("\"") || value.Contains("\0") || value.EndsWith("\\", StringComparison.Ordinal))
            throw new ArgumentException("Invalid process argument.");
        return "\"" + value + "\"";
    }

    internal static bool IsAdministrator()
    {
        using (var identity = WindowsIdentity.GetCurrent())
            return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
    }

    private async Task Run(string action)
    {
        if (working) return;
        RefreshRestoreNote();
        working = true;
        install.Enabled = restore.Enabled = open.Enabled = false;
        progress.Style = ProgressBarStyle.Marquee;
        progress.Visible = true;
        status.Text = "正在校验安装包。随后请确认 Windows 管理员权限提示。";
        try
        {
            await Task.Run(() => { using (var package = new Package()) { } });
            string runId = Guid.NewGuid().ToString("N");
            string directory = Path.Combine(Worker.Root, runId);
            string userData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Oink");
            status.Text = action == "Restore" ? "正在恢复原版，请勿打开 Oink。" : "正在覆盖安装，请勿打开 Oink。";
            int code = await Task.Run(() => {
                // Elevate this embedded-resource executable, never a script in a
                // user-writable extraction directory. Only the elevated worker
                // extracts executable content into a protected directory.
                var start = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location,
                    "--worker " + action + " " + Quote(userData) + " " + runId) {
                    UseShellExecute = true, Verb = "runas", WindowStyle = ProcessWindowStyle.Hidden
                };
                using (var process = Process.Start(start)) {
                    if (process == null) throw new IOException("无法启动安装工作进程。");
                    process.WaitForExit();
                    return process.ExitCode;
                }
            });
            if (Directory.Exists(directory)) { workDirectory = directory; logs.Visible = true; }
            if (code != 0)
            {
                string reason = "操作未完成，原有配置已保留。";
                string result = Path.Combine(directory, "logs", action + "-latest.json");
                if (File.Exists(result)) {
                    var record = Package.Json(File.ReadAllText(result, Encoding.UTF8));
                    object message;
                    if (record.TryGetValue("message", out message)) reason = Convert.ToString(message);
                }
                status.Text = "操作未完成。可点击“查看日志与源代码”查看详情。";
                MessageBox.Show(this, "安装或恢复未完成。\n\n" + reason + "\n\n日志位置：\n" + directory,
                    Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            status.Text = action == "Restore" ?
                (customPointer ? "已恢复原版程序，配对、布局及当前 Windows 指针样式已保留。" : "已恢复原版，配对和布局已保留。") :
                "安装完成，配对和布局已保留。请点击“打开 Oink”。";
            open.Enabled = !IsAdministrator();
            if (!open.Enabled) status.Text += " 请从开始菜单打开 Oink。";
        }
        catch (Exception error)
        {
            var windowsError = error as System.ComponentModel.Win32Exception;
            if (windowsError != null && windowsError.NativeErrorCode == 1223) {
                status.Text = "已取消管理员权限提示，没有开始修改程序。";
            } else {
                status.Text = "操作未完成，请查看提示。";
                MessageBox.Show(this, error.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }
        finally
        {
            working = false;
            progress.Visible = false;
            install.Enabled = restore.Enabled = true;
        }
    }

    private void OpenOink()
    {
        if (IsAdministrator()) { MessageBox.Show(this, "请从 Windows 开始菜单正常打开 Oink。", Text); return; }
        string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Oink", "oink.exe");
        try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
        catch (Exception error) { MessageBox.Show(this, error.Message, Text); }
    }
}

internal static class Worker
{
    internal static string Root {
        get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Oink", "custom-trail-installer"); }
    }

    private static void VerifyProtectedDirectory(string path)
    {
        Package.NoReparse(path);
        var acl = Directory.GetAccessControl(path);
        var privileged = new HashSet<string>(new[] { "S-1-5-18", "S-1-5-32-544",
            "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464" });
        if (!privileged.Contains(((SecurityIdentifier)acl.GetOwner(typeof(SecurityIdentifier))).Value))
            throw new IOException("安装目录所有者不符合受保护安装要求。");
        var raw = new RawSecurityDescriptor(acl.GetSecurityDescriptorBinaryForm(), 0);
        if (raw.DiscretionaryAcl == null) throw new IOException("安装目录缺少保护权限。");
        var write = FileSystemRights.Write | FileSystemRights.Delete | FileSystemRights.DeleteSubdirectoriesAndFiles |
            FileSystemRights.ChangePermissions | FileSystemRights.TakeOwnership;
        foreach (FileSystemAccessRule rule in acl.GetAccessRules(true, true, typeof(SecurityIdentifier)))
            if (rule.AccessControlType == AccessControlType.Allow && (rule.PropagationFlags & PropagationFlags.InheritOnly) == 0 &&
                (rule.FileSystemRights & write) != 0 && !privileged.Contains(((SecurityIdentifier)rule.IdentityReference).Value))
                throw new IOException("安装目录允许非管理员修改，无法继续。");
    }

    internal static int Run(string action, string userData, string runId)
    {
        if (!InstallerForm.IsAdministrator()) throw new UnauthorizedAccessException("安装工作进程需要正常的 Windows 管理员授权。");
        if ((action != "Upgrade" && action != "Restore") || !Regex.IsMatch(runId, "^[a-f0-9]{32}$"))
            throw new ArgumentException("安装操作参数无效。");
        Package.NoReparse(userData);
        string install = Path.GetDirectoryName(Root);
        if (!Directory.Exists(install)) throw new IOException("请先安装 Oink 0.3.4（build 108），再使用增强版覆盖安装。");
        VerifyProtectedDirectory(Path.GetDirectoryName(install));
        VerifyProtectedDirectory(install);
        if (!Directory.Exists(Root)) {
            var acl = new DirectorySecurity();
            acl.SetSecurityDescriptorSddlForm("O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;GRGX;;;BU)");
            Directory.CreateDirectory(Root, acl);
        }
        VerifyProtectedDirectory(Root);
        string directory = Path.Combine(Root, runId);
        using (var package = new Package()) package.Extract(directory);
        VerifyProtectedDirectory(directory);
        string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
        var start = new ProcessStartInfo(powershell,
            "-NoProfile -ExecutionPolicy Bypass -File " + InstallerForm.Quote(Path.Combine(directory, "Run-Patch.ps1")) +
            " -Action " + action + " -Elevated -UserDataPath " + InstallerForm.Quote(Path.GetFullPath(userData))) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
            WorkingDirectory = directory
        };
        using (var process = new Process { StartInfo = start }) {
            var output = new StringBuilder();
            process.OutputDataReceived += (sender, args) => { if (args.Data != null) lock (output) output.AppendLine(args.Data); };
            process.ErrorDataReceived += (sender, args) => { if (args.Data != null) lock (output) output.AppendLine(args.Data); };
            process.Start();
            process.BeginOutputReadLine(); process.BeginErrorReadLine();
            process.WaitForExit();
            File.WriteAllText(Path.Combine(directory, "launcher.log"), output.ToString(), new UTF8Encoding(false));
            return process.ExitCode;
        }
    }
}

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 4 && args[0] == "--worker") return Worker.Run(args[1], args[2], args[3]);
            if (args.Length == 2 && args[0] == "--verify-package")
            {
                using (var package = new Package()) {
                    var report = new Dictionary<string, object> { { "verified", true }, { "patch_id", package.PatchId },
                        { "source_tree_sha256", package.Manifest["source_tree_sha256"] }, { "archive_sha256", BuildInfo.ArchiveSha256 } };
                    File.WriteAllText(args[1], new JavaScriptSerializer().Serialize(report), new UTF8Encoding(false));
                }
                return 0;
            }
            if (args.Length == 2 && args[0] == "--extract-package") {
                using (var package = new Package()) package.Extract(args[1]);
                return 0;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && (args[0] == "--render-preview" || args[0] == "--render-preview-custom-pointer")) {
                using (var form = new InstallerForm(args[0] == "--render-preview-custom-pointer" ? true : (bool?)null)) {
                    form.ShowInTaskbar = false; form.Opacity = 0; form.Show();
                    using (var bitmap = new Bitmap(form.Width, form.Height)) {
                        form.DrawToBitmap(bitmap, new Rectangle(0, 0, bitmap.Width, bitmap.Height));
                        bitmap.Save(args[1], System.Drawing.Imaging.ImageFormat.Png);
                    }
                    form.Close();
                }
                return 0;
            }
            if (args.Length != 0) throw new ArgumentException("不支持的安装参数。");
            if (!Environment.Is64BitOperatingSystem || !Environment.Is64BitProcess)
                throw new PlatformNotSupportedException("本安装程序需要 Windows x64。");
            Application.Run(new InstallerForm());
            return 0;
        }
        catch (Exception error)
        {
            if (args.Length == 0) MessageBox.Show(error.Message, "指针尾迹增强版安装程序", MessageBoxButtons.OK, MessageBoxIcon.Error);
            else Console.Error.WriteLine(error.ToString());
            return 1;
        }
    }
}
