using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
namespace Still;

// Clicking an extension works like Chrome: its popup opens, or the click reaches the extension's own
// chrome.action.onClicked handlers, and a side panel it opens (chrome.sidePanel) docks on the right of the window.
// The engine has neither of the last two, so Still adds a small adapter to each extension's service worker.
public partial class MainWindow
{
 WebView2? extensionBridge, sidePanelView;
 string? sidePanelExtension;
 TaskCompletionSource<JsonElement?>? bridgeReply;
 internal static readonly Dictionary<string, string?> ExtensionIcons = [];

 // Runs first in the extension's service worker. Records click listeners and side panel calls, and answers
 // Still's bridge page with what the extension asked to open.
 const string ExtensionShim = """
 (() => {
  if (self.__stillShim) return; self.__stillShim = true;
  const clicks = [], panels = new Map(), action = chrome.action || chrome.browserAction, sp = chrome.sidePanel;
  let opened = null, openOnClick = false;
  if (action?.onClicked) {
   const ev = action.onClicked, add = ev.addListener.bind(ev), remove = ev.removeListener.bind(ev);
   ev.addListener = f => { clicks.push(f); try { add(f); } catch {} };
   ev.removeListener = f => { const i = clicks.indexOf(f); if (i >= 0) clicks.splice(i, 1); try { remove(f); } catch {} };
  }
  if (sp) {
   const setOptions = sp.setOptions?.bind(sp), setBehavior = sp.setPanelBehavior?.bind(sp);
   sp.setOptions = async o => { if (o?.path) panels.set(o.tabId ?? 'all', o.path); try { return await setOptions?.(o); } catch {} };
   sp.setPanelBehavior = async b => { if (b && 'openPanelOnActionClick' in b) openOnClick = !!b.openPanelOnActionClick; try { return await setBehavior?.(b); } catch {} };
   sp.open = async o => { opened = o || {}; };
  }
  chrome.runtime.onMessage.addListener((m, sender, reply) => {
   if (m?.__still !== 'click' || sender.id !== chrome.runtime.id) return;
   (async () => {
    const tab = m.tab; opened = openOnClick ? { tabId: tab?.id } : null;
    for (const f of [...clicks]) try { await f(tab); } catch (e) { console.error(e); }
    await new Promise(r => setTimeout(r, 300));
    const path = opened && (panels.get(opened.tabId) || panels.get('all') || chrome.runtime.getManifest().side_panel?.default_path);
    reply({ listeners: clicks.length, panel: path || null });
   })();
   return true;
  });
 })();
 """;
 const string ExtensionBridge = """
 (async () => {
  const url = new URLSearchParams(location.search).get('url');
  let tab;
  try { const all = await chrome.tabs.query({}); tab = all.find(t => t.url === url) || all.find(t => t.active); } catch {}
  let r = null;
  try { r = await chrome.runtime.sendMessage({ __still: 'click', tab }); } catch {}
  chrome.webview.postMessage({ kind: 'still-extension-click', listeners: r?.listeners ?? 0, panel: r?.panel ?? null });
 })();
 """;

 static string? ExtensionFolder(string id)
 {
  try { return File.ReadAllText(Path.Combine(App.DataRoot, "Extensions", id + ".path")).Trim(); } catch (IOException) { return null; }
 }

 /// A file a manifest names, as a full path inside the extension's folder. Anything else is refused.
 internal static string InsideExtension(string folder, string file)
 {
  string name = file.TrimStart('/'), root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(folder)) + Path.DirectorySeparatorChar;
  if (name.Length > 0 && !name.Any(c => c is '\\' or ':' || char.IsControl(c)) && !name.Split('/').Contains("..")
      && Path.GetFullPath(Path.Combine(root, name)) is var full && full.StartsWith(root, StringComparison.OrdinalIgnoreCase)) return full;
  throw new InvalidDataException("This extension's manifest names a file outside its folder.");
 }

 /// Adds the adapter to an installed extension folder. Returns true when the service worker changed
 /// (the extension must be reloaded to pick it up).
 internal static bool PatchExtension(string folder)
 {
  string manifestPath = Path.Combine(folder, "manifest.json");
  var manifest = JsonNode.Parse(File.ReadAllText(manifestPath)) as JsonObject ?? throw new InvalidDataException("Invalid extension manifest.");
  if (manifest["background"]?["service_worker"]?.GetValue<string>() is { } named) InsideExtension(folder, named); // before anything is written
  Directory.CreateDirectory(Path.Combine(folder, "still-adapter"));
  File.WriteAllText(Path.Combine(folder, "still-adapter", "shim.js"), ExtensionShim);
  File.WriteAllText(Path.Combine(folder, "still-adapter", "bridge.js"), ExtensionBridge);
  File.WriteAllText(Path.Combine(folder, "still-adapter", "bridge.html"), "<!doctype html><meta charset=utf-8><script src=bridge.js></script>");
  if (manifest["background"] is not JsonObject background) return false;
  if (background["service_worker"]?.GetValue<string>() is { } worker) {
   if (Path.GetFileName(worker) == "still-adapter-sw.js") return false;
   // Next to the original, so its relative importScripts paths still resolve.
   string dir = Path.GetDirectoryName(worker.TrimStart('/'))?.Replace('\\', '/') ?? "", wrapper = (dir.Length > 0 ? dir + "/" : "") + "still-adapter-sw.js";
   string original = JsonSerializer.Serialize("/" + worker.TrimStart('/'));
   File.WriteAllText(Path.Combine(folder, wrapper), background["type"]?.GetValue<string>() == "module"
    ? $"import '/still-adapter/shim.js';\nimport {original};\n"
    : $"importScripts('/still-adapter/shim.js', {original});\n");
   background["service_worker"] = wrapper;
  } else if (background["scripts"] is JsonArray scripts) { // Manifest V2 background page
   if (scripts.Any(s => s?.GetValue<string>() == "still-adapter/shim.js")) return false;
   scripts.Insert(0, "still-adapter/shim.js");
  } else return false;
  File.WriteAllText(manifestPath, manifest.ToJsonString());
  return true;
 }

 async Task ExtensionAction(string id, double[]? anchor)
 {
  if (GetExtensionPage(id, true) is { } popup) { await ShowExtensionPopup(popup, anchor); return; }
  if (ExtensionFolder(id) is not { } folder) return;
  var core = await ManagementCore();
  try {
   if (PatchExtension(folder) && (await core.Profile.GetBrowserExtensionsAsync()).FirstOrDefault(e => e.Id == id) is { IsEnabled: true } extension) {
    await extension.EnableAsync(false); await extension.EnableAsync(true); // load the adapted service worker
   }
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException or JsonException) { App.Log(ex); }
  JsonElement? reply = null;
  try {
   if (extensionBridge == null) {
    extensionBridge = new WebView2 { Visibility = Visibility.Hidden };
    WebHost.Children.Add(extensionBridge);
    var env = await App.BrowserEnvironment; var options = env.CreateCoreWebView2ControllerOptions(); options.ProfileName = "Default";
    await extensionBridge.EnsureCoreWebView2Async(env, options);
    extensionBridge.CoreWebView2.WebMessageReceived += (_, e) => {
     try { using var doc = JsonDocument.Parse(e.WebMessageAsJson); if (doc.RootElement.GetProperty("kind").GetString() == "still-extension-click") bridgeReply?.TrySetResult(doc.RootElement.Clone()); }
     catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException) { }
    };
   }
   bridgeReply = new();
   extensionBridge.CoreWebView2.Navigate($"chrome-extension://{id}/still-adapter/bridge.html?url={Uri.EscapeDataString(active?.Url ?? "")}");
   reply = await bridgeReply.Task.WaitAsync(TimeSpan.FromSeconds(6));
  } catch (Exception ex) when (ex is TimeoutException or InvalidOperationException or System.Runtime.InteropServices.COMException) { }
  if (reply?.GetProperty("panel").GetString() is { Length: > 0 } panel) { await OpenSidePanel(id, panel); return; }
  if (reply?.GetProperty("listeners").GetInt32() > 0) return; // the extension handled the click itself (opened a tab, ran a script…)
  if (GetExtensionPage(id) is { } page) await NewTab(page, false, false);
  else Toast("This extension has nothing to open.");
 }

 async Task OpenSidePanel(string id, string path)
 {
  if (path.Contains("..") || path.Contains(':') || path.Contains('\\')) return;
  string url = $"chrome-extension://{id}/{path.TrimStart('/')}";
  if (sidePanelView?.CoreWebView2 is { } current && sidePanelExtension == id) { current.Navigate(url); return; }
  CloseSidePanel();
  sidePanelExtension = id;
  var view = sidePanelView = new WebView2 { DefaultBackgroundColor = System.Drawing.Color.White, Width = 1, Height = 1 };
  pageCanvas?.Children.Add(view);
  ShellPublish(); // the shell makes room and reports where the panel goes
  try {
   var env = await App.BrowserEnvironment; var options = env.CreateCoreWebView2ControllerOptions(); options.ProfileName = "Default";
   await view.EnsureCoreWebView2Async(env, options);
  } catch (Exception ex) { App.Log(ex); CloseSidePanel(); Toast("Couldn't open the side panel."); return; }
  if (sidePanelView != view) return;
  var core = view.CoreWebView2;
  core.Settings.AreDefaultContextMenusEnabled = true;
  core.NewWindowRequested += (_, e) => { e.Handled = true; string link = e.Uri; Dispatcher.BeginInvoke(async () => await NewTab(link, false, false)); };
  core.WindowCloseRequested += (_, _) => Dispatcher.BeginInvoke(() => { if (sidePanelView == view) CloseSidePanel(); });
  core.Navigate(url);
 }

 void CloseSidePanel()
 {
  if (sidePanelView is { } view) { pageCanvas?.Children.Remove(view); view.Dispose(); }
  sidePanelView = null; sidePanelExtension = null;
  ShellPublish();
 }

 void PlaceSidePanel(double x, double y, double width, double height)
 {
  if (sidePanelView is not { } view) return;
  view.Width = Math.Max(1, width); view.Height = Math.Max(1, height);
  System.Windows.Controls.Canvas.SetLeft(view, x); System.Windows.Controls.Canvas.SetTop(view, y);
  pageCanvas?.UpdateLayout(); RestorePageWindow();
 }

 object? SidePanelData() => sidePanelExtension is { } id ? new { id, name = ExtensionDisplayName(id), icon = ExtensionIcon(id) } : null;
 object PinnedExtensionsData() => Prefs.PinnedExtensions.Where(id => ExtensionFolder(id) != null).Select(id => new { id, name = ExtensionDisplayName(id), icon = ExtensionIcon(id) }).ToArray();

 static string ExtensionDisplayName(string id)
 {
  try { var folder = ExtensionFolder(id)!; using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "manifest.json"))); return ExtensionName(doc.RootElement, folder); }
  catch (Exception) { return "Extension"; }
 }

 // The toolbar icon as a data URL: the action icon, else the extension icon, nearest to 32 px.
 static string? ExtensionIcon(string id)
 {
  if (ExtensionIcons.TryGetValue(id, out var cached)) return cached;
  string? result = null;
  try {
   var folder = ExtensionFolder(id)!;
   using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "manifest.json"))); var m = doc.RootElement;
   string? file = null;
   foreach (var key in new[] { "action", "browser_action", "page_action" })
    if (m.TryGetProperty(key, out var a) && a.TryGetProperty("default_icon", out var icon)) { file = Pick(icon); if (file != null) break; }
   if (file == null && m.TryGetProperty("icons", out var icons)) file = Pick(icons);
   if (file != null) {
    string path = InsideExtension(folder, file);
    string type = Path.GetExtension(path).ToLowerInvariant() switch { ".svg" => "image/svg+xml", ".jpg" or ".jpeg" => "image/jpeg", ".webp" => "image/webp", _ => "image/png" };
    if (new FileInfo(path).Length < 512 * 1024) result = $"data:{type};base64," + Convert.ToBase64String(File.ReadAllBytes(path));
   }
  } catch (Exception) { }
  return ExtensionIcons[id] = result;
  static string? Pick(JsonElement icon) => icon.ValueKind == JsonValueKind.String ? icon.GetString()
   : icon.ValueKind == JsonValueKind.Object ? icon.EnumerateObject().Where(p => int.TryParse(p.Name, out _)).OrderBy(p => Math.Abs(int.Parse(p.Name) - 32)).Select(p => p.Value.GetString()).FirstOrDefault() : null;
 }

 // Chrome Web Store pages: Chrome's own (disabled) "Add to Chrome" button becomes "Add to Still".
 const string StoreButtonScript = """
 (() => {
  if (location.host !== 'chromewebstore.google.com' || window.top !== window) return;
  const label = /^(Add to Chrome|Remove from Chrome)$/;
  const fix = () => {
   for (const b of document.querySelectorAll('button')) {
    if (b.dataset.still || !label.test(b.innerText.trim())) continue;
    const mine = b.cloneNode(true);
    for (const a of ['jsaction', 'jscontroller', 'jsname', 'disabled']) mine.removeAttribute(a);
    mine.dataset.still = '1'; b.dataset.still = 'hidden'; b.style.display = 'none';
    const text = [...mine.querySelectorAll('*')].reverse().find(e => label.test(e.textContent.trim())) || mine;
    text.textContent = 'Add to Still';
    mine.addEventListener('click', e => { e.preventDefault(); e.stopImmediatePropagation(); window.chrome?.webview?.postMessage({ kind: 'still-store-add' }); }, true);
    b.after(mine);
   }
  };
  new MutationObserver(fix).observe(document, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', fix);
 })();
 """;
}
