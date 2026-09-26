using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Interop;
using System.Windows.Media.Imaging;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
namespace Still;

// Upload a copied image straight into a site's file picker, like Opera GX. While the clipboard holds an image,
// page file pickers are intercepted (Chromium DevTools protocol) and Still offers "Paste image from clipboard".
// With no image copied, sites get the normal Windows file dialog untouched.
public partial class MainWindow
{
 [DllImport("user32.dll", SetLastError = true)] static extern bool AddClipboardFormatListener(IntPtr hwnd);
 const int WM_CLIPBOARDUPDATE = 0x031D;
 bool clipboardImage;

 void WatchClipboard()
 {
  var handle = new WindowInteropHelper(this).Handle;
  HwndSource.FromHwnd(handle)?.AddHook((IntPtr _, int msg, IntPtr _, IntPtr _, ref bool _) => {
   if (msg == WM_CLIPBOARDUPDATE && HasClipboardImage() != clipboardImage) {
    clipboardImage = !clipboardImage;
    foreach (var t in tabs) if (t.View?.CoreWebView2 is { } core) _ = InterceptFilePicker(core);
   }
   return IntPtr.Zero;
  });
  AddClipboardFormatListener(handle);
  clipboardImage = HasClipboardImage();
 }

 static bool HasClipboardImage() { try { return Clipboard.ContainsImage(); } catch (COMException) { return false; } }

 async Task InterceptFilePicker(CoreWebView2 core)
 {
  try { await core.CallDevToolsProtocolMethodAsync("Page.setInterceptFileChooserDialog", clipboardImage ? "{\"enabled\":true}" : "{\"enabled\":false}"); }
  catch (Exception ex) when (ex is COMException or InvalidOperationException) { /* page closed or navigating; the next tab setup retries */ }
 }

 async Task SetupFilePaste(BrowserTab tab, CoreWebView2 core)
 {
  core.GetDevToolsProtocolEventReceiver("Page.fileChooserOpened").DevToolsProtocolEventReceived += (_, e) =>
   Dispatcher.BeginInvoke(() => OfferFiles(tab, core, e.ParameterObjectAsJson));
  try { await core.CallDevToolsProtocolMethodAsync("Page.enable", "{}"); }
  catch (Exception ex) when (ex is COMException or InvalidOperationException) { App.Log(ex); return; } // uploads just use the normal dialog
  await InterceptFilePicker(core);
 }

 void OfferFiles(BrowserTab tab, CoreWebView2 core, string json)
 {
  int node; bool multiple;
  try { using var d = JsonDocument.Parse(json); node = d.RootElement.GetProperty("backendNodeId").GetInt32(); multiple = d.RootElement.GetProperty("mode").GetString() == "selectMultiple"; }
  catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException) { return; }
  async void Fill(string[] files)
  {
   if (files.Length == 0 || tab.Closed || tab.View?.CoreWebView2 != core) return;
   try { await core.CallDevToolsProtocolMethodAsync("DOM.setFileInputFiles", JsonSerializer.Serialize(new { files, backendNodeId = node })); }
   catch (Exception ex) { App.Log(ex); Toast("Couldn't attach the file. Try again."); }
  }
  void Browse() { var dialog = new OpenFileDialog { Multiselect = multiple, Title = "Open" }; if (dialog.ShowDialog(this) == true) Fill(dialog.FileNames); }
  // The clipboard may have changed since the picker was intercepted: then it's just a normal file dialog.
  if (!HasClipboardImage()) { Browse(); return; }
  var menu = new ContextMenu { Placement = PlacementMode.MousePoint };
  AddMenu(menu, "Paste image from clipboard", () => { if (SaveClipboardImage() is { } file) Fill([file]); else Toast("The clipboard no longer has an image."); }, "Ctrl V");
  AddMenu(menu, "Choose a file…", Browse);
  menu.IsOpen = true;
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
