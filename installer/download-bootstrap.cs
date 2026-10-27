// Downloads only the fixed, hash-pinned installer bundled in this release.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("mergen kurulumu")]
[assembly: AssemblyProduct("mergen")]
[assembly: AssemblyCompany("mergen contributors")]
[assembly: AssemblyVersion("0.4.0.0")]
[assembly: AssemblyFileVersion("0.4.0.0")]

[DataContract] public class PackagePart {
    [DataMember] public string name;
    [DataMember] public string url;
    [DataMember] public string sha256;
    [DataMember] public long bytes;
}
[DataContract] public class Package {
    [DataMember] public string version;
    [DataMember] public string sha256;
    [DataMember] public long bytes;
    [DataMember] public List<PackagePart> parts;
}
public static class PackageFiles {
    public static string Hash(string path) {
        using (var stream = File.OpenRead(path))
        using (var hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }
    public static bool Valid(string path, long size, string hash) {
        return File.Exists(path) && new FileInfo(path).Length == size && Hash(path) == hash;
    }
    public static void Assemble(Package package, string folder, string destination, Action check) {
        string temporary = destination + ".part";
        try {
            using (var output = File.Create(temporary)) {
                var buffer = new byte[1024 * 1024];
                foreach (var part in package.parts) {
                    check();
                    string path = Path.Combine(folder, part.name);
                    if (!Valid(path, part.bytes, part.sha256)) throw new IOException("kurulum parçası doğrulanamadı");
                    using (var input = File.OpenRead(path)) {
                        int count;
                        while ((count = input.Read(buffer, 0, buffer.Length)) != 0) {
                            check(); output.Write(buffer, 0, count);
                        }
                    }
                }
            }
            check();
            if (!Valid(temporary, package.bytes, package.sha256)) throw new IOException("kurulum dosyası doğrulanamadı");
            if (File.Exists(destination)) File.Delete(destination);
            File.Move(temporary, destination);
        } finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
public class InstallerWindow : Form {
    readonly Label status = new Label();
    readonly ProgressBar progress = new ProgressBar();
    readonly Button cancel = new Button();
    volatile bool cancelled;
    volatile bool finished;
    HttpWebRequest request;
    Package package;
    string installerArguments;
    public InstallerWindow(Package value, string arguments) {
        package = value;
        installerArguments = arguments;
        Text = "mergen · kurulum " + package.version;
        ClientSize = new Size(480, 148);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 10);
        status.SetBounds(20, 18, 440, 40); status.Text = "kurulum hazırlanıyor…";
        progress.SetBounds(20, 65, 440, 20);
        cancel.SetBounds(352, 103, 108, 28); cancel.Text = "iptal";
        Controls.AddRange(new Control[] {status, progress, cancel});
        cancel.Click += delegate { Close(); };
        FormClosing += delegate { if (!finished) { cancelled = true; if (request != null) request.Abort(); } };
        Shown += delegate { var thread = new Thread(Work); thread.IsBackground = true; thread.Start(); };
    }
    void Check() { if (cancelled) throw new OperationCanceledException(); }
    void UpdateStatus(string text, int percent) {
        if (IsDisposed || !IsHandleCreated) return;
        try { BeginInvoke((Action)delegate { status.Text = text; progress.Value = Math.Max(0, Math.Min(100, percent)); }); }
        catch (InvalidOperationException) { }
    }
    void Download(PackagePart part, string path, long completed) {
        string temporary = path + ".part";
        try {
            request = (HttpWebRequest)WebRequest.Create(part.url);
            request.UserAgent = "mergen/" + package.version;
            request.Timeout = 30000; request.ReadWriteTimeout = 30000;
            using (var response = request.GetResponse())
            using (var input = response.GetResponseStream())
            using (var output = File.Create(temporary)) {
                var buffer = new byte[1024 * 1024]; long received = 0; int count;
                while ((count = input.Read(buffer, 0, buffer.Length)) != 0) {
                    Check(); received += count;
                    if (received > part.bytes) throw new IOException("kurulum parçası beklenenden büyük");
                    output.Write(buffer, 0, count);
                    UpdateStatus("kurulum indiriliyor · " + ((completed + received) * 100 / package.bytes) + "%", (int)((completed + received) * 100 / package.bytes));
                }
            }
            Check();
            if (!PackageFiles.Valid(temporary, part.bytes, part.sha256)) throw new IOException("indirilen kurulum parçası doğrulanamadı");
            if (File.Exists(path)) File.Delete(path);
            File.Move(temporary, path);
        } finally { request = null; if (File.Exists(temporary)) File.Delete(temporary); }
    }
    void Work() {
        try {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            string folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "mergen-next", "downloads", package.version);
            Directory.CreateDirectory(folder);
            using (var guard = new FileStream(Path.Combine(folder, "kurulum.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None)) {
                string installer = Path.Combine(folder, "mergen-full-setup-" + package.version + ".exe");
                UpdateStatus("hazır kurulum dosyası kontrol ediliyor…", 0);
                if (!PackageFiles.Valid(installer, package.bytes, package.sha256)) {
                    if (new DriveInfo(Path.GetPathRoot(folder)).AvailableFreeSpace < package.bytes * 2 + 268435456)
                        throw new IOException("kurulum indirmesi için en az 9 gb boş alan gerekiyor");
                    long completed = 0;
                    foreach (var part in package.parts) {
                        Check(); string path = Path.Combine(folder, part.name);
                        UpdateStatus("kurulum parçası kontrol ediliyor…", (int)(completed * 100 / package.bytes));
                        if (!PackageFiles.Valid(path, part.bytes, part.sha256)) Download(part, path, completed);
                        completed += part.bytes;
                    }
                    UpdateStatus("kurulum birleştiriliyor ve doğrulanıyor…", 100);
                    PackageFiles.Assemble(package, folder, installer, Check);
                }
                Check();
                foreach (var part in package.parts) { string path = Path.Combine(folder, part.name); if (File.Exists(path)) File.Delete(path); }
                UpdateStatus("doğrulanan kurulum açılıyor…", 100);
                var start = new ProcessStartInfo(installer, installerArguments); start.UseShellExecute = true;
                using (var process = Process.Start(start)) { process.WaitForExit(); if (process.ExitCode != 0) throw new IOException("kurulum tamamlanmadı; başlatıcıyı yeniden çalıştırabilirsin"); }
                finished = true;
                BeginInvoke((Action)delegate { Close(); });
            }
        } catch (Exception error) {
            if (cancelled) return;
            finished = true;
            try { BeginInvoke((Action)delegate { status.Text = "kurulum tamamlanamadı: " + error.Message.ToLowerInvariant(); cancel.Text = "kapat"; }); }
            catch (InvalidOperationException) { }
        }
    }
}
public static class Program {
    [STAThread] public static void Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        var forwarded = new List<string>();
        foreach (string arg in args) {
            string upper = arg.ToUpperInvariant();
            if (upper == "/VERYSILENT" || upper == "/SILENT" || upper == "/SUPPRESSMSGBOXES" || upper == "/NORESTART" ||
                upper == "/CLOSEAPPLICATIONS" || upper == "/RESTARTAPPLICATIONS" || upper == "/SP-" ||
                upper.StartsWith("/LOG=") || upper.StartsWith("/DIR="))
                forwarded.Add("\"" + arg.Replace("\"", "\\\"") + "\"");
        }
        using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("mergen.payload")) {
            var package = (Package)new DataContractJsonSerializer(typeof(Package)).ReadObject(stream);
            Application.Run(new InstallerWindow(package, String.Join(" ", forwarded.ToArray())));
        }
    }
}
