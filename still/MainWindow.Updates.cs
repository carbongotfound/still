using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;
namespace Still;

// Automatic updates: check GitHub's latest public release (startup + every 2 hours), download the
// installer in the background, verify it against GitHub's published SHA-256, then install silently
// when Still closes, or immediately via "Restart to update". Only the installed copy updates itself.
public partial class MainWindow
{
 const string LatestRelease = "https://api.github.com/repos/carbongotfound/still/releases/latest";
 const string ReleasePage = "https://github.com/carbongotfound/still/releases/";
 record UpdateInfo(string Version, string Url, string? Installer);
 static UpdateInfo? update;
 static bool updateDownloading, updateOnExitArmed, applyWhenReady, applying;
 static int updateProgress;
 static Version CurrentVersion =>
#if STILL_QA
  Environment.GetEnvironmentVariable("STILL_QA_VERSION") is { } fake ? Version.Parse(fake) :
#endif
  Assembly.GetEntryAssembly()?.GetName().Version ?? new Version(0, 0);
 static string InstalledExe => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Still", "Still.exe");
 static bool CanSelfUpdate => string.Equals(Environment.ProcessPath, InstalledExe, StringComparison.OrdinalIgnoreCase)
#if STILL_QA
  || Environment.GetEnvironmentVariable("STILL_QA_VERSION") != null
#endif
  ;

 void StartUpdateChecks()
 {
  if (App.IsQa) return;
  var timer = new DispatcherTimer { Interval = TimeSpan.FromHours(2) };
  timer.Tick += async (_, _) => await CheckForUpdate();
  timer.Start();
  _ = Dispatcher.InvokeAsync(async () => { await Task.Delay(TimeSpan.FromSeconds(15)); await CheckForUpdate(); });
  // Install a downloaded update silently when the last window closes.
  Application.Current.Exit += (_, _) => { if (update?.Installer is { } setup && updateOnExitArmed) RunInstaller(setup, relaunch: false); };
 }

 async Task CheckForUpdate()
 {
  try {
   using var request = new HttpRequestMessage(HttpMethod.Get, LatestRelease);
   request.Headers.UserAgent.ParseAdd("Still/" + CurrentVersion.ToString(3));
   using var response = await ExtensionHttp.SendAsync(request);
   if (!response.IsSuccessStatusCode) return;
   using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
   var root = json.RootElement;
   string tag = root.GetProperty("tag_name").GetString() ?? "";
   if (!Version.TryParse(tag.TrimStart('v', 'V'), out var latest)) return;
   if (latest <= CurrentVersion) { if (update != null) { update = null; PublishAll(); } return; }
   string version = latest.ToString(3);
   if (update?.Version != version) { update = new UpdateInfo(version, ReleasePage + "tag/" + Uri.EscapeDataString(tag), null); PublishAll(); }
   if (CanSelfUpdate && update.Installer == null && !updateDownloading) await DownloadUpdate(root, version);
  } catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException or InvalidOperationException or IOException or UnauthorizedAccessException) { App.Log(ex); }
 }

 async Task DownloadUpdate(JsonElement release, string version)
 {
  var asset = release.GetProperty("assets").EnumerateArray().FirstOrDefault(a => a.GetProperty("name").GetString() == "Still-Setup-x64.exe");
  if (asset.ValueKind != JsonValueKind.Object) return;
  string url = asset.GetProperty("browser_download_url").GetString() ?? "";
  string digest = asset.TryGetProperty("digest", out var d) ? d.GetString() ?? "" : "";
  // Only official release downloads with a published SHA-256; otherwise the user updates by hand.
  if (!url.StartsWith("https://github.com/carbongotfound/still/releases/download/", StringComparison.Ordinal) || !digest.StartsWith("sha256:") || digest.Length != 71) return;
  updateDownloading = true;
  try {
   string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Still", "Updates");
   Directory.CreateDirectory(dir);
   foreach (var old in Directory.EnumerateFiles(dir, "Still-Setup-*.exe")) try { File.Delete(old); } catch (IOException) { }
   string target = Path.Combine(dir, "Still-Setup-" + version + ".exe");
   using var download = await ExtensionHttp.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
   download.EnsureSuccessStatusCode();
   var final = download.RequestMessage?.RequestUri;
   if (final == null || final.Scheme != "https" || !(final.Host == "github.com" || final.Host.EndsWith(".githubusercontent.com", StringComparison.Ordinal))) return;
   if (download.Content.Headers.ContentLength is > 300_000_000) return;
   long total = download.Content.Headers.ContentLength ?? 0, got = 0; var lastPublish = DateTime.MinValue;
   await using (var file = File.Create(target)) {
    await using var input = await download.Content.ReadAsStreamAsync();
    var buffer = new byte[81920]; int read;
    while ((read = await input.ReadAsync(buffer)) > 0) {
     await file.WriteAsync(buffer.AsMemory(0, read)); got += read;
     if (total > 0 && DateTime.UtcNow - lastPublish > TimeSpan.FromMilliseconds(300)) { updateProgress = (int)(got * 100 / total); lastPublish = DateTime.UtcNow; PublishAll(); }
    }
   }
   string hash;
   await using (var file = File.OpenRead(target)) hash = Convert.ToHexString(await SHA256.HashDataAsync(file)).ToLowerInvariant();
   if (hash != digest[7..].ToLowerInvariant()) { File.Delete(target); App.Log(new InvalidDataException("Update download failed its SHA-256 check and was deleted.")); return; }
   update = update! with { Installer = target };
   updateOnExitArmed = true; updateProgress = 100;
   PublishAll();
   if (applyWhenReady) Home.RestartToUpdate();
  } finally { updateDownloading = false; if (update?.Installer == null && applyWhenReady) { applyWhenReady = false; PublishAll(); Home.Toast("The update couldn't be downloaded. Still will try again later."); } }
 }

 static void RunInstaller(string setup, bool relaunch)
 {
  if (!File.Exists(setup) || App.IsQa) return;
  string args = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER";
  // cmd waits for the installer, then reopens Still when asked. Paths are ours (never web content).
  string command = relaunch ? $"/c \"\"{setup}\" {args} & start \"\" \"{InstalledExe}\"\"" : $"/c \"\"{setup}\" {args}\"";
  Process.Start(new ProcessStartInfo("cmd.exe", command) { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden });
 }

 void RestartToUpdate()
 {
  if (update == null || applying) return;
  if (!CanSelfUpdate) { _ = NewTab(update.Url, false, false); return; }
  // Clicked before the download finished: finish it, then update automatically.
  if (update.Installer is not { } setup) {
   applyWhenReady = true; PublishAll();
   if (!updateDownloading) _ = CheckForUpdate();
   return;
  }
  applying = true; PublishAll();
  updateOnExitArmed = false;
  foreach (var w in Windows.ToArray()) w.Save();
  RunInstaller(setup, relaunch: true);
  Application.Current.Shutdown();
 }

 object? UpdateData() => update == null ? null : new { version = update.Version, current = CurrentVersion.ToString(3), ready = update.Installer != null, progress = updateProgress, busy = applyWhenReady || applying, selfUpdate = CanSelfUpdate };
}
