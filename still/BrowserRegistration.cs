using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Text;
using Microsoft.Win32;
namespace Still;

// Per-user registration as a Windows web browser (HKCU only, no elevation). Windows never lets an
// app silently make itself the default browser: the user picks Still in Settings > Default apps.
internal static class BrowserRegistration
{
 const string Client = @"Software\Clients\StartMenuInternet\Still";
 const string UrlProgId = "StillURL", HtmlProgId = "StillHTML";
 static string Exe => Environment.ProcessPath!;
 static string Open => "\"" + Exe + "\" \"%1\"";

 public static void Register()
 {
  if (App.IsQa) return;
  // Never let a second copy (dev build, portable exe) steal link handling from a working install.
  using (var current = Registry.CurrentUser.OpenSubKey(@"Software\Classes\" + UrlProgId + @"\shell\open\command")) {
   if (current?.GetValue("") is string cmd && cmd.StartsWith('"') && cmd.IndexOf('"', 1) is var end and > 1) {
    string registered = cmd[1..end];
    if (!string.Equals(registered, Exe, StringComparison.OrdinalIgnoreCase) && File.Exists(registered)) return;
   }
  }
  try {
   foreach (var (id, name) in new[] { (UrlProgId, "Still URL"), (HtmlProgId, "Still HTML Document") }) {
    using var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\" + id);
    k.SetValue("", name); k.SetValue("FriendlyTypeName", name);
    if (id == UrlProgId) k.SetValue("URL Protocol", "");
    using (var i = k.CreateSubKey("DefaultIcon")) i.SetValue("", "\"" + Exe + "\",0");
    using (var a = k.CreateSubKey("Application")) { a.SetValue("ApplicationName", "Still"); a.SetValue("ApplicationIcon", "\"" + Exe + "\",0"); a.SetValue("ApplicationCompany", "Still"); }
    using var c = k.CreateSubKey(@"shell\open\command"); c.SetValue("", Open);
   }
   using (var k = Registry.CurrentUser.CreateSubKey(Client)) {
    k.SetValue("", "Still");
    using (var i = k.CreateSubKey("DefaultIcon")) i.SetValue("", "\"" + Exe + "\",0");
    using (var c = k.CreateSubKey(@"shell\open\command")) c.SetValue("", "\"" + Exe + "\"");
    using var cap = k.CreateSubKey("Capabilities");
    cap.SetValue("ApplicationName", "Still");
    cap.SetValue("ApplicationDescription", "A quiet, pitch-black browser for Windows.");
    cap.SetValue("ApplicationIcon", "\"" + Exe + "\",0");
    using (var s = cap.CreateSubKey("StartMenu")) s.SetValue("StartMenuInternet", "Still");
    using (var u = cap.CreateSubKey("URLAssociations")) { u.SetValue("http", UrlProgId); u.SetValue("https", UrlProgId); }
    using var f = cap.CreateSubKey("FileAssociations");
    foreach (var ext in new[] { ".htm", ".html", ".shtml", ".xht", ".xhtml", ".svg", ".webp", ".pdf" }) f.SetValue(ext, HtmlProgId);
   }
   using (var r = Registry.CurrentUser.CreateSubKey(@"Software\RegisteredApplications")) r.SetValue("Still", Client + @"\Capabilities");
   // Let Explorer "Open with" list Still for web files.
   using (var app = Registry.CurrentUser.CreateSubKey(@"Software\Classes\Applications\" + Path.GetFileName(Exe) + @"\shell\open\command")) app.SetValue("", Open);
  } catch (Exception ex) when (ex is UnauthorizedAccessException or IOException or System.Security.SecurityException) { App.Log(ex); }
 }

 public static bool IsDefault
 {
  get {
   using var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice");
   return k?.GetValue("ProgId") as string == UrlProgId;
  }
 }

 // Opens Windows' Default apps page scrolled to Still, where the user confirms the choice.
 public static void OpenDefaultAppsSettings()
 {
  try { Process.Start(new ProcessStartInfo("ms-settings:defaultapps?registeredAppUser=Still") { UseShellExecute = true }); }
  catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException) { Process.Start(new ProcessStartInfo("ms-settings:defaultapps") { UseShellExecute = true }); }
 }

 // ---- Single-instance hand-off: a second Still launch (e.g. a clicked link) forwards its URL. ----
 static string PipeName(string instance) => instance.Replace("Local\\", "") + "-open";

 public static string? UrlFromArgs(string[] args)
 {
  foreach (var a in args) {
   if (a.StartsWith("--")) continue;
   if (Uri.TryCreate(a, UriKind.Absolute, out var u) && u.Scheme is "http" or "https") return u.AbsoluteUri;
   try { if (File.Exists(a)) return new Uri(Path.GetFullPath(a)).AbsoluteUri; } catch (Exception) { }
  }
  return null;
 }

 public static bool Forward(string instance, string? url)
 {
  try {
   using var pipe = new NamedPipeClientStream(".", PipeName(instance), PipeDirection.Out, PipeOptions.CurrentUserOnly);
   pipe.Connect(3000);
   var bytes = Encoding.UTF8.GetBytes(url ?? ""); pipe.Write(bytes); pipe.Flush(); return true;
  } catch (Exception ex) when (ex is TimeoutException or IOException or UnauthorizedAccessException) { return false; }
 }

 public static void Listen(string instance, Action<string> onUrl)
 {
  var thread = new Thread(() => {
   while (true) {
    try {
     using var pipe = new NamedPipeServerStream(PipeName(instance), PipeDirection.In, 1, PipeTransmissionMode.Byte, PipeOptions.CurrentUserOnly);
     pipe.WaitForConnection();
     using var ms = new MemoryStream(); var buf = new byte[4096]; int n;
     while ((n = pipe.Read(buf)) > 0 && ms.Length < 16384) ms.Write(buf, 0, n);
     var text = Encoding.UTF8.GetString(ms.ToArray());
     // Accept only a web or file URL (or empty = just bring the window forward).
     if (text.Length == 0 || Uri.TryCreate(text, UriKind.Absolute, out var u) && u.Scheme is "http" or "https" or "file") onUrl(text);
    } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ObjectDisposedException) { Thread.Sleep(200); }
   }
  }) { IsBackground = true, Name = "Still link hand-off" };
  thread.Start();
 }
}
