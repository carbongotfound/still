using System.Collections.Concurrent;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Media.Imaging;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
namespace Still;

// When a site asks for a file, Still opens a card under the button: a bar of your recent files that the site
// accepts, led by the copied image (like Opera GX), and "Open a file". Page file pickers are intercepted through
// the Chromium DevTools protocol; the card lives in Still's own UI, so the site never sees your file list,
// only the file you pick.
public partial class MainWindow
{
 sealed record UploadRequest(string Id, BrowserTab Tab, CoreWebView2 Core, int Node, bool Multiple, string Accept, string[] Files);
 UploadRequest? upload;
 static readonly string[] ImageTypes = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif"];
 static readonly Dictionary<string, string[]> MimeTypes = new() {
  ["image/*"] = [.. ImageTypes, ".svg", ".heic"], ["video/*"] = [".mp4", ".webm", ".mov", ".mkv", ".avi"], ["audio/*"] = [".mp3", ".wav", ".m4a", ".ogg", ".flac"],
  ["image/png"] = [".png"], ["image/jpeg"] = [".jpg", ".jpeg"], ["image/jpg"] = [".jpg", ".jpeg"], ["image/gif"] = [".gif"], ["image/webp"] = [".webp"], ["image/svg+xml"] = [".svg"],
  ["application/pdf"] = [".pdf"], ["text/plain"] = [".txt"], ["text/csv"] = [".csv"], ["application/json"] = [".json"], ["application/zip"] = [".zip"],
 };
 static readonly ConcurrentDictionary<string, string> thumbnails = new();

 [DllImport("user32.dll")] static extern bool IsClipboardFormatAvailable(uint format);
 [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT point);
 [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
 // Checks formats without opening the clipboard, so another app holding it can never freeze Still.
 static bool HasClipboardImage() => IsClipboardFormatAvailable(2 /*CF_BITMAP*/) || IsClipboardFormatAvailable(8 /*CF_DIB*/) || IsClipboardFormatAvailable(17 /*CF_DIBV5*/);

 async Task SetupFilePaste(BrowserTab tab, CoreWebView2 core)
 {
  var events = core.GetDevToolsProtocolEventReceiver("Page.fileChooserOpened");
  events.DevToolsProtocolEventReceived += (_, e) => Dispatcher.BeginInvoke(async () => await OfferFiles(tab, core, e.ParameterObjectAsJson));
  tab.FileChooserEvents = events;
  try {
   await core.CallDevToolsProtocolMethodAsync("Page.enable", "{}");
   await core.CallDevToolsProtocolMethodAsync("Page.setInterceptFileChooserDialog", "{\"enabled\":true}");
  } catch (Exception ex) when (ex is COMException or InvalidOperationException) { App.Log(ex); } // uploads just use the normal dialog
 }

 // The extensions a picker's accept="" allows, or null when it takes any file.
 static HashSet<string>? AcceptedTypes(string accept)
 {
  var types = new HashSet<string>();
  foreach (var token in accept.Split(',').Select(t => t.Trim().ToLowerInvariant()).Where(t => t.Length > 0)) {
   if (token.StartsWith('.')) types.Add(token);
   else if (MimeTypes.TryGetValue(token, out var known)) types.UnionWith(known);
   else return null; // a type Still doesn't know: don't hide files the site may take
  }
  return types.Count == 0 ? null : types;
 }

 async Task OfferFiles(BrowserTab tab, CoreWebView2 core, string json)
 {
  int node; bool multiple;
  try { using var d = JsonDocument.Parse(json); node = d.RootElement.GetProperty("backendNodeId").GetInt32(); multiple = d.RootElement.GetProperty("mode").GetString() == "selectMultiple"; }
  catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException) { return; }
  string accept = "";
  try {
   using var d = JsonDocument.Parse(await core.CallDevToolsProtocolMethodAsync("DOM.describeNode", JsonSerializer.Serialize(new { backendNodeId = node })));
   var attributes = d.RootElement.GetProperty("node").GetProperty("attributes").EnumerateArray().Select(a => a.GetString() ?? "").ToArray();
   for (int i = 0; i + 1 < attributes.Length; i += 2) if (attributes[i] == "accept") accept = attributes[i + 1];
  } catch (Exception ex) when (ex is COMException or InvalidOperationException or JsonException or KeyNotFoundException) { }
  var types = AcceptedTypes(accept);
  CancelUpload();
  // The copied image leads the bar, saved as a PNG so picking it is instant.
  string? copied = (types == null || types.Contains(".png")) && HasClipboardImage() ? SaveClipboardImage() : null;
  var files = await Task.Run(() => RecentFiles(types));
  var request = new UploadRequest(Guid.NewGuid().ToString("N"), tab, core, node, multiple, accept, copied == null ? files : [copied, .. files]);
  if (tab != active || closing || !shellReady) { Browse(request); return; }
  upload = request;
  var anchor = await UploadAnchor(tab, core);
  if (upload != request) return;
  object Card(bool thumbs) => new { kind = "upload", data = new { id = request.Id, multiple, anchor, files = request.Files.Select((path, i) => new {
   id = i, name = i == 0 && copied != null ? "Copied image" : Path.GetFileName(path), copied = i == 0 && copied != null,
   type = Path.GetExtension(path).TrimStart('.').ToUpperInvariant(), thumb = thumbs && ImageTypes.Contains(Path.GetExtension(path).ToLowerInvariant()) ? Thumbnail(path) : null }).ToArray() } };
  ShellSend(Card(false));
  var withThumbs = await Task.Run(() => Card(true));
  if (upload == request) ShellSend(withThumbs);
 }

 // The upload button's box in shell pixels, found under the mouse; a keyboard-opened picker anchors to the top of the page.
 async Task<double[]?> UploadAnchor(BrowserTab tab, CoreWebView2 core)
 {
  if (tab.View is not { } view || shellView == null || !GetCursorPos(out var cursor)) return null;
  var inPage = view.PointFromScreen(new Point(cursor.X, cursor.Y));
  if (inPage.X < 0 || inPage.Y < 0 || inPage.X > view.ActualWidth || inPage.Y > view.ActualHeight) return null;
  double zoom = view.ZoomFactor;
  try {
   string box = await core.ExecuteScriptAsync($"(()=>{{const e=document.elementFromPoint({inPage.X / zoom:0.#},{inPage.Y / zoom:0.#});const b=e&&e.closest('button,label,a,input,[role=button]');if(!b)return [{inPage.X / zoom:0.#}-1,{inPage.Y / zoom:0.#}-1,2,2];const r=b.getBoundingClientRect();return [r.left,r.top,r.width,r.height]}})()");
   if (JsonSerializer.Deserialize<double[]>(box) is not { Length: 4 } r) return null;
   var origin = view.TranslatePoint(new Point(0, 0), shellView);
   double scale = shellView.ZoomFactor;
   return [(origin.X + r[0] * zoom) / scale, (origin.Y + r[1] * zoom) / scale, r[2] * zoom / scale, r[3] * zoom / scale];
  } catch (Exception ex) when (ex is COMException or InvalidOperationException or JsonException) { return null; }
 }

 // The newest accepted files in Pictures, Screenshots, Desktop, Downloads and Documents (top level only, so it stays instant).
 static string[] RecentFiles(HashSet<string>? types)
 {
  string pictures = Environment.GetFolderPath(Environment.SpecialFolder.MyPictures), home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
  string[] folders = [pictures, Path.Combine(pictures, "Screenshots"), Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), Path.Combine(home, "Downloads"), Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)];
  return folders.Where(f => f.Length > 0).Distinct().Where(Directory.Exists).SelectMany(dir => {
    try { return new DirectoryInfo(dir).EnumerateFiles().Where(f => (f.Attributes & (FileAttributes.Hidden | FileAttributes.System)) == 0 && (types?.Contains(f.Extension.ToLowerInvariant()) ?? !f.Name.EndsWith(".lnk", StringComparison.OrdinalIgnoreCase) && !f.Name.EndsWith(".ini", StringComparison.OrdinalIgnoreCase))).ToArray(); }
    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return []; }
   }).OrderByDescending(f => f.LastWriteTimeUtc).Take(12).Select(f => f.FullName).ToArray();
 }

 // A small JPEG preview, cached by path and date so the card opens instantly next time.
 static string? Thumbnail(string path)
 {
  try {
   string key = path + "|" + File.GetLastWriteTimeUtc(path).Ticks;
   if (thumbnails.TryGetValue(key, out var cached)) return cached;
   var image = new BitmapImage();
   using (var stream = File.OpenRead(path)) { image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad; image.DecodePixelHeight = 180; image.StreamSource = stream; image.EndInit(); }
   image.Freeze();
   var encoder = new JpegBitmapEncoder { QualityLevel = 82 }; encoder.Frames.Add(BitmapFrame.Create(image));
   using var output = new MemoryStream(); encoder.Save(output);
   return thumbnails[key] = "data:image/jpeg;base64," + Convert.ToBase64String(output.ToArray());
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException or InvalidOperationException or ArgumentException or COMException) { return null; }
 }

 // The card's answer: the picked files, "open a file", or nothing (closed).
 void AnswerUpload(string id, int[] picked, bool browse)
 {
  if (upload is not { } request || request.Id != id) return;
  upload = null; ShellSend(new { kind = "upload", data = (object?)null });
  if (browse) { Browse(request); return; }
  Fill(request, picked.Where(i => i >= 0 && i < request.Files.Length).Distinct().Select(i => request.Files[i]).Take(request.Multiple ? 12 : 1).ToArray());
 }

 void CancelUpload() { if (upload != null) { upload = null; ShellSend(new { kind = "upload", data = (object?)null }); } }

 void Browse(UploadRequest request)
 {
  var types = AcceptedTypes(request.Accept);
  var dialog = new OpenFileDialog { Multiselect = request.Multiple, Title = "Open", Filter = types == null ? "All files|*.*" : "Supported files|*" + string.Join(";*", types) + "|All files|*.*" };
  if (dialog.ShowDialog(this) == true) Fill(request, dialog.FileNames);
 }

 async void Fill(UploadRequest request, string[] files)
 {
  if (files.Length == 0 || request.Tab.Closed || request.Tab.View?.CoreWebView2 != request.Core) return;
  try { await request.Core.CallDevToolsProtocolMethodAsync("DOM.setFileInputFiles", JsonSerializer.Serialize(new { files, backendNodeId = request.Node })); }
  catch (Exception ex) { App.Log(ex); Toast("Couldn't attach the file. Try again."); }
 }

 // Writes the clipboard image to a PNG the site can upload. Old pastes are cleaned up after a day.
 static string? SaveClipboardImage()
 {
  try {
   if (Clipboard.GetImage() is not { } image) return null;
   string dir = Path.Combine(App.DataRoot, "Clipboard");
   Directory.CreateDirectory(dir);
   foreach (var old in new DirectoryInfo(dir).EnumerateFiles().Where(f => f.CreationTimeUtc < DateTime.UtcNow.AddDays(-1))) try { old.Delete(); } catch (IOException) { }
   string file = Path.Combine(dir, "Pasted image " + DateTime.Now.ToString("yyyy-MM-dd HHmmss") + ".png");
   var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image));
   using (var stream = File.Create(file)) encoder.Save(stream);
   return file;
  } catch (Exception ex) when (ex is COMException or IOException or UnauthorizedAccessException or NotSupportedException) { App.Log(ex); return null; }
 }
}
