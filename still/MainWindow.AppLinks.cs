using System.Diagnostics;
using System.IO;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
namespace Still;

// Links that open an app (discord:, steam:, zoommtg:, spotify:, mailto: ...). Still asks in its permission bar,
// remembers "Allow" per site and app, and refuses schemes known to be abused to run code on Windows.
public partial class MainWindow
{
 static readonly HashSet<string> DangerousSchemes = new(StringComparer.OrdinalIgnoreCase) {
  "javascript", "vbscript", "data", "file", "shell", "res", "hcp", "its", "mk", "ms-its", "ms-msdt", "search", "search-ms",
  "ms-officecmd", "ms-cxh", "ms-cxh-full", "ms-appinstaller", "ms-excel", "ms-word", "ms-powerpoint", "ms-access", "ms-visio",
  "ms-project", "ms-publisher", "ms-spd", "ms-infopath", "ms-diagcab", "ms-rd", "microsoft-edge", "microsoft-edge-holographic", "stillurl" };
 string lastAppLink = ""; DateTime lastAppLinkAt;

 /// A pop-up, side panel or extension view: a link to an app asks in the tab in front, like one from a tab.
 void GateAppLinks(CoreWebView2 core, Func<BrowserTab?> tab)
 {
  core.LaunchingExternalUriScheme += (_, e) => { e.Cancel = true; var uri = e.Uri; var from = e.InitiatingOrigin; var clicked = e.IsUserInitiated; Dispatcher.BeginInvoke(() => { if (tab() is { } t) OpenAppLink(t, uri, from, clicked); }); };
  core.NavigationStarting += (_, e) => {
   if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var u) || u.Scheme is "http" or "https" or "about" or "data" or "blob" or "file" or "chrome-extension" or "view-source" or "edge") return;
   e.Cancel = true; var link = e.Uri; var clicked = e.IsUserInitiated; Dispatcher.BeginInvoke(() => { if (tab() is { } t) OpenAppLink(t, link, "", clicked); });
  };
 }

 async void OpenAppLink(BrowserTab tab, string uri, string from, bool clicked)
 {
  // The engine can report the same launch twice (navigation + launch event); ask once.
  if (uri == lastAppLink && DateTime.UtcNow - lastAppLinkAt < TimeSpan.FromSeconds(2)) return;
  lastAppLink = uri; lastAppLinkAt = DateTime.UtcNow;
  if (!Uri.TryCreate(uri, UriKind.Absolute, out var u) || uri.Length > 2048) return;
  string scheme = u.Scheme;
  if (DangerousSchemes.Contains(scheme)) { Toast("Still blocked a link that could run programs on this PC."); return; }
  if (AppForScheme(scheme) is not { } app) { Toast($"No app on this PC opens {scheme}: links."); return; }
  // Who asked: a frame answers for itself, not for the page around it. Only a real click by the page itself can be remembered.
  string top = Host(tab.Url), site = Uri.TryCreate(from, UriKind.Absolute, out var origin) && origin.Scheme is "http" or "https" ? Host(from) : top;
  bool own = clicked && site == top;
  if (string.IsNullOrWhiteSpace(site)) site = "This page";
  string key = site + "|" + scheme;
  if (!own || !Prefs.AllowedAppLinks.Contains(key)) {
   if (!await AskPermission(tab, site, "open " + app)) return;
   if (own && !tab.Private) { Prefs.AllowedAppLinks.Add(key); SaveLater(); }
  }
  try { Process.Start(new ProcessStartInfo(HandlerUri(uri)) { UseShellExecute = true }); }
  catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException) { Toast($"Couldn't open {app}."); }
 }

 // The link as an app's command line gets it: everything that isn't plainly part of an address is percent-encoded, so it stays
 // one argument for the app, however the app registered itself.
 internal static string HandlerUri(string uri)
 {
  var text = new System.Text.StringBuilder();
  foreach (byte b in System.Text.Encoding.UTF8.GetBytes(uri))
   if (char.IsAsciiLetterOrDigit((char)b) || ";/?:@&=+$,!'()*-._~#[]%".Contains((char)b)) text.Append((char)b); else text.Append('%').Append(b.ToString("X2"));
  return text.ToString();
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
