using System.Diagnostics;
using System.IO;
using Microsoft.Win32;
namespace Still;

// Links that open an app (discord:, steam:, zoommtg:, spotify:, mailto: ...). Still asks in its permission bar,
// remembers "Allow" per site and app, and refuses schemes known to be abused to run code on Windows.
public partial class MainWindow
{
 static readonly HashSet<string> DangerousSchemes = new(StringComparer.OrdinalIgnoreCase) {
  "javascript", "vbscript", "data", "file", "shell", "res", "hcp", "its", "mk", "ms-its", "ms-msdt", "search", "search-ms",
  "ms-officecmd", "ms-cxh", "ms-cxh-full", "ms-appinstaller", "ms-excel", "ms-word", "ms-powerpoint", "ms-access", "ms-visio",
  "ms-project", "ms-publisher", "ms-spd", "ms-infopath", "ms-diagcab", "ms-rd", "microsoft-edge", "microsoft-edge-holographic" };
 string lastAppLink = ""; DateTime lastAppLinkAt;

 async void OpenAppLink(BrowserTab tab, string uri)
 {
  // The engine can report the same launch twice (navigation + launch event); ask once.
  if (uri == lastAppLink && DateTime.UtcNow - lastAppLinkAt < TimeSpan.FromSeconds(2)) return;
  lastAppLink = uri; lastAppLinkAt = DateTime.UtcNow;
  if (!Uri.TryCreate(uri, UriKind.Absolute, out var u) || uri.Length > 2048) return;
  string scheme = u.Scheme;
  if (DangerousSchemes.Contains(scheme)) { Toast("Still blocked a link that could run programs on this PC."); return; }
  if (AppForScheme(scheme) is not { } app) { Toast($"No app on this PC opens {scheme}: links."); return; }
  string site = Host(tab.Url); if (string.IsNullOrWhiteSpace(site)) site = "This page";
  string key = site + "|" + scheme;
  if (!Prefs.AllowedAppLinks.Contains(key)) {
   if (!await AskPermission(tab, site, "open " + app)) return;
   if (!tab.Private) { Prefs.AllowedAppLinks.Add(key); SaveLater(); }
  }
  try { Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true }); }
  catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException) { Toast($"Couldn't open {app}."); }
 }

 // A friendly name for the app registered for this link type, or null when nothing on the PC handles it.
 static string? AppForScheme(string scheme)
 {
  if (scheme is "mailto") return "your email app";
  if (scheme is "tel") return "your phone app";
  try {
   using var key = Registry.ClassesRoot.OpenSubKey(scheme);
   if (key?.GetValue("URL Protocol") == null) return null;
   string command = Registry.ClassesRoot.OpenSubKey(scheme + @"\shell\open\command")?.GetValue(null) as string ?? "";
   string exe = command.StartsWith('"') ? command[1..].Split('"')[0] : command.Split(' ')[0];
   if (File.Exists(exe) && FileVersionInfo.GetVersionInfo(exe).FileDescription is { Length: > 0 } description) return description;
   string label = (key.GetValue(null) as string ?? "").Replace("URL:", "").Replace(" Protocol", "").Replace(" protocol", "").Trim();
   return label.Length > 0 ? label : scheme + " app";
  } catch (Exception ex) when (ex is System.Security.SecurityException or IOException or UnauthorizedAccessException) { return null; }
 }
}
