using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using Microsoft.Web.WebView2.Core;
namespace Still;
public partial class MainWindow
{
 static readonly string[] BlockedDomains = [
  "doubleclick.net", "googlesyndication.com", "googleadservices.com", "adservice.google.com",
  "google-analytics.com", "googletagmanager.com", "adnxs.com", "adsrvr.org", "taboola.com",
  "outbrain.com", "scorecardresearch.com", "quantserve.com", "criteo.com", "criteo.net",
  "pubmatic.com", "rubiconproject.com", "openx.net", "casalemedia.com", "advertising.com",
  "amazon-adsystem.com", "hotjar.com", "hotjar.io", "clarity.ms", "connect.facebook.net",
  "analytics.tiktok.com", "ads.linkedin.com", "snap.licdn.com", "bat.bing.com", "ads.twitter.com"
 ];
 readonly Dictionary<string, List<string>> privateHidden = [];
 void SetupBlocking(BrowserTab tab, CoreWebView2 core)
 {
  foreach (string domain in BlockedDomains) {
   core.AddWebResourceRequestedFilter("*://" + domain + "/*", CoreWebView2WebResourceContext.All, CoreWebView2WebResourceRequestSourceKinds.All);
   core.AddWebResourceRequestedFilter("*://*." + domain + "/*", CoreWebView2WebResourceContext.All, CoreWebView2WebResourceRequestSourceKinds.All);
  }
  core.WebResourceRequested += (_, e) => {
   if (!Prefs.Blocking || !Uri.TryCreate(tab.Url, UriKind.Absolute, out var page) || Prefs.UnblockedHosts.Contains(page.Host)) return;
   if (!Uri.TryCreate(e.Request.Uri, UriKind.Absolute, out var request) || request.Host == page.Host) return;
   if (!BlockedDomains.Any(d => request.Host == d || request.Host.EndsWith("." + d, StringComparison.OrdinalIgnoreCase))) return;
   e.Response = core.Environment.CreateWebResourceResponse(new MemoryStream([]), 204, "No Content", "Content-Type: text/plain");
   tab.Blocked++;
  };
 }
 async Task InstallHiddenRules(BrowserTab tab)
 {
  if (tab.View?.CoreWebView2 is not { } core) return;
  if (tab.HideScriptId != null) core.RemoveScriptToExecuteOnDocumentCreated(tab.HideScriptId);
  var map = new Dictionary<string, List<string>>(state.Hidden);
  if (tab.Private) foreach (var pair in privateHidden) map[pair.Key] = pair.Value;
  var json = JsonSerializer.Serialize(map);
  var script = $$"""
  (() => {
    if (window !== top) return;
    const rules = {{json}};
    const selectors = rules[location.hostname] || [];
    if (!selectors.length) return;
    const install = () => {
      const style = document.createElement('style');
      style.id = 'still-hidden-rules';
      style.textContent = selectors.map(s => s + '{display:none!important}').join('\n');
      (document.head || document.documentElement).appendChild(style);
    };
    if (document.documentElement) install(); else document.addEventListener('DOMContentLoaded', install, {once:true});
  })();
  """;
  tab.HideScriptId = await core.AddScriptToExecuteOnDocumentCreatedAsync(script);
 }
 async Task PickHidden()
 {
  if (active?.View?.CoreWebView2 is not { } core || active.Url.Length == 0) return;
  var tab = active;
  tab.HideToken = Guid.NewGuid().ToString("N"); tab.HideExpires = DateTime.UtcNow.AddMinutes(2);
  var token = JsonSerializer.Serialize(tab.HideToken);
  await core.ExecuteScriptAsync($$"""
  (() => {
    if (window.__stillCancelPicker) window.__stillCancelPicker();
    let last, oldOutline;
    const toast = document.createElement('div');
    toast.textContent = 'Click an element to hide it. Esc to cancel.';
    toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:2147483647;padding:14px 20px;background:#252624;color:white;border-radius:10px;font:14px system-ui;pointer-events:none';
    document.documentElement.appendChild(toast);
    function move(e) {
      if(last) last.style.outline = oldOutline;
      last = e.target; oldOutline = last.style.outline;
      last.style.outline = '2px solid #8c9a7d';
    }
    function cleanup() {
      if(last) last.style.outline = oldOutline;
      document.removeEventListener('mousemove',move,true);
      document.removeEventListener('click',pick,true);
      document.removeEventListener('keydown',key,true);
      toast.remove(); delete window.__stillCancelPicker;
    }
    function key(e) { if(e.key === 'Escape') { e.preventDefault(); cleanup(); } }
    function pick(e) {
      e.preventDefault(); e.stopImmediatePropagation();
      const el = e.target;
      if(el === document.body || el === document.documentElement) { cleanup(); return; }
      const parts = []; let n = el;
      while(n && n !== document.body) {
        if(n.id) { parts.unshift('#'+CSS.escape(n.id)); break; }
        let part = n.tagName.toLowerCase();
        const siblings = n.parentElement ? Array.from(n.parentElement.children).filter(x => x.tagName === n.tagName) : [];
        if(siblings.length > 1) part += ':nth-of-type(' + (siblings.indexOf(n)+1) + ')';
        parts.unshift(part); n=n.parentElement;
      }
      const selector=parts.join(' > ');
      cleanup();
      if(selector && selector.length < 500) {
        const style=document.createElement('style'); style.textContent=selector+'{display:none!important}';
        document.documentElement.appendChild(style);
        window.chrome.webview.postMessage({kind:'still-hide',token:{{token}},selector,host:location.hostname});
      }
    }
    window.__stillCancelPicker=cleanup;
    document.addEventListener('mousemove',move,true);
    document.addEventListener('click',pick,true);
    document.addEventListener('keydown',key,true);
    setTimeout(cleanup,120000);
  })();
  """);
 }
 async Task ReceiveHidden(BrowserTab tab, CoreWebView2WebMessageReceivedEventArgs e)
 {
  try {
   if (tab.HideToken == null || DateTime.UtcNow > tab.HideExpires) return;
   if (!Uri.TryCreate(e.Source, UriKind.Absolute, out var source) || !Uri.TryCreate(tab.Url, UriKind.Absolute, out var page) || source.GetLeftPart(UriPartial.Authority) != page.GetLeftPart(UriPartial.Authority)) return;
   using var doc = JsonDocument.Parse(e.WebMessageAsJson);
   var root = doc.RootElement;
   if (root.GetProperty("kind").GetString() != "still-hide" || root.GetProperty("token").GetString() != tab.HideToken) return;
   string selector = root.GetProperty("selector").GetString() ?? "", host = root.GetProperty("host").GetString() ?? "";
   if (host != page.Host || selector.Length is < 1 or > 500 || selector.IndexOfAny(['{','}','\r','\n']) >= 0) return;
   tab.HideToken = null;
   var dict = tab.Private ? privateHidden : state.Hidden;
   if (!dict.ContainsKey(host)) dict[host] = [];
   if (!dict[host].Contains(selector) && dict[host].Count < 100) dict[host].Add(selector);
   SaveLater();
   foreach (var t in tabs.Where(t => t.View?.CoreWebView2 != null)) await InstallHiddenRules(t);
   Toast(tab.Private ? "Hidden for this private session." : "Hidden on this site. Restore it in site controls.");
  } catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException) { }
 }
 async Task ToggleReader()
 {
  if (active?.View?.CoreWebView2 is not { } core) return;
  var tab = active;
  if (tab.Reader) { tab.Reader = false; core.Reload(); return; }
  try {
   string readability = await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "Assets", "Readability.js"));
   await core.ExecuteScriptAsync(readability);
   string result = await core.ExecuteScriptAsync($$"""
   (() => {
    const copy = document.cloneNode(true);
    copy.querySelectorAll('nav,aside,[role="navigation"],[role="banner"]').forEach(el=>el.remove());
    const article = new Readability(copy).parse();
    if (!article || article.textContent.trim().length < 120) return false;
    const doc = new DOMParser().parseFromString(article.content,'text/html');
    doc.querySelectorAll('script,iframe,object,embed,form,input,button,style,link,meta,base,nav,aside,[role="navigation"]').forEach(el=>el.remove());
    doc.querySelectorAll('*').forEach(el=>Array.from(el.attributes).forEach(a=>{
      if(a.name.startsWith('on') || a.name==='style' || a.name==='srcdoc' || ((a.name==='href'||a.name==='src') && /^\s*(javascript|data):/i.test(a.value))) el.removeAttribute(a.name);
    }));
    const root = document.createElement('main');
    root.style.cssText='max-width:700px;margin:0 auto;padding:65px 32px 100px';
    const source=document.createElement('p');source.textContent=location.hostname+' · STILL READER';source.style.cssText='font:12px system-ui;letter-spacing:1px;opacity:.55';
    const title=document.createElement('h1');title.textContent=article.title;title.style.cssText='font:600 38px/1.2 system-ui;letter-spacing:-1px;margin:28px 0';
    const byline=document.createElement('p');byline.textContent=article.byline||'';byline.style.cssText='font:14px system-ui;opacity:.65;margin-bottom:32px';
    const hint=document.createElement('p');hint.textContent='Ctrl Shift R to return to the page';hint.style.cssText='font:12px system-ui;opacity:.55;margin-top:48px';
    root.append(source,title,byline,...doc.body.childNodes,hint);
    document.body.replaceChildren(root);
    document.body.removeAttribute('class');document.body.removeAttribute('style');
    const style=document.createElement('style');
    style.textContent='html,body{background:{{(dark ? "#000000" : "#FAFAF7")}}!important;color:{{(dark ? "#EAECE4" : "#30312D")}}!important;margin:0!important;font:19px/1.85 Georgia,serif!important} body main img{max-width:100%;height:auto} body main a{color:inherit;text-decoration:underline;text-underline-offset:3px} body main pre{overflow:auto} body main p{margin:1.25em 0}';
    document.head.querySelectorAll('style,link[rel="stylesheet"]').forEach(el=>el.remove());
    document.head.appendChild(style);
    return true;
   })();
   """);
   if (result == "true") { tab.Reader = true; Toast("Reading mode. Ctrl Shift R returns to the page."); } else Toast("This page doesn't have an article to simplify.");
  } catch (Exception ex) { App.Log(ex); Toast("Reading mode isn't available on this page."); }
 }
 async Task PictureInPicture()
 {
  if (active?.View?.CoreWebView2 is not { } core) return;
  try {
   var response = await core.CallDevToolsProtocolMethodAsync("Runtime.evaluate", JsonSerializer.Serialize(new { expression = "(async()=>{const v=[...document.querySelectorAll('video')].find(v=>v.readyState>0);if(!v)return 'No playable video found on this page';try{if(document.pictureInPictureElement){await document.exitPictureInPicture();return 'closed'}await v.requestPictureInPicture();return 'opened'}catch(e){return e.message}})()", awaitPromise = true, returnByValue = true, userGesture = true }));
   using var doc = JsonDocument.Parse(response);
   if (doc.RootElement.TryGetProperty("result", out var r) && r.TryGetProperty("value", out var val)) { string message = val.ToString(); if (message is not ("opened" or "closed")) Toast(message); }
  } catch { Toast("Floating video isn't available for this player."); }
 }
 static bool IsShortcut(Key key, ModifierKeys mods)
 {
  bool ctrl = mods.HasFlag(ModifierKeys.Control), alt = mods.HasFlag(ModifierKeys.Alt), shift = mods.HasFlag(ModifierKeys.Shift);
  return (key is Key.Escape or Key.F11) || (alt && key is Key.Left or Key.Right) || (ctrl && (key is Key.L or Key.K or Key.T or Key.W or Key.Tab or Key.R or Key.D or Key.H or Key.J or Key.F or Key.OemComma or Key.Add or Key.Subtract or Key.OemPlus or Key.OemMinus or Key.D0 || shift && key is Key.N or Key.B or Key.P or Key.S || key >= Key.D1 && key <= Key.D9));
 }
 void WindowKeyDown(object s, KeyEventArgs e)
 {
  var key = e.Key == Key.System ? e.SystemKey : e.Key;
  if (!IsShortcut(key, Keyboard.Modifiers)) return;
  // Preserve common editing shortcuts inside text inputs.
  if (e.OriginalSource is System.Windows.Controls.TextBox && key is Key.A or Key.C or Key.V or Key.X) return;
  e.Handled = true; var modifiers=Keyboard.Modifiers; Dispatcher.BeginInvoke(() => HandleShortcut(key, modifiers));
 }
 async void HandleShortcut(Key key, ModifierKeys mods)
 {
  bool ctrl = mods.HasFlag(ModifierKeys.Control), shift = mods.HasFlag(ModifierKeys.Shift), alt = mods.HasFlag(ModifierKeys.Alt);
  if(key==Key.F11){await ToggleFullScreen();return;}
  if (key == Key.Escape) {
   ShellSend(new{kind="escape"});
   if (panel.Length > 0) CloseSheet();
   else if(IsFullScreen){browserFullScreen=false;await ExitContentFullScreen();}
   else if (FindBar.Visibility == Visibility.Visible) FindBar.Visibility = Visibility.Collapsed;
   else if (active?.View?.CoreWebView2 is { } escCore) await escCore.ExecuteScriptAsync("if(window.__stillCancelPicker)window.__stillCancelPicker();if(document.fullscreenElement)document.exitFullscreen();");
   return;
  }
  if (alt && key == Key.Left) { BackClick(this, new()); return; }
  if (alt && key == Key.Right) { ForwardClick(this, new()); return; }
  if (!ctrl) return;
  if (key == Key.L) ShowAddress(active?.Url ?? "");
  else if (key == Key.K) ShowAddress("", true);
  else if (key == Key.T && shift) ReopenTab();
  else if (key == Key.T) await NewTab();
  else if (key == Key.N && shift) await NewTab("", true);
  else if (key == Key.W && active != null) await CloseTab(active);
  else if (key == Key.Tab && tabs.Count > 0) await SelectTab(tabs[(tabs.IndexOf(active!) + (shift ? -1 : 1) + tabs.Count) % tabs.Count]);
  else if (key >= Key.D1 && key <= Key.D9 && tabs.Count > 0) { int index = key == Key.D9 ? tabs.Count - 1 : Math.Min((int)key - (int)Key.D1, tabs.Count - 1); await SelectTab(tabs[index]); }
  else if (key == Key.R && shift) await ToggleReader();
  else if (key == Key.R) ReloadClick(this, new());
  else if (key == Key.D) ToggleBookmark();
  else if (key == Key.B && shift) ShowLibrary(true);
  else if (key == Key.H && shift) { CloseSheet(); await PickHidden(); }
  else if (key == Key.H) ShowLibrary(false);
  else if (key == Key.J) ShowDownloads();
  else if (key == Key.F && shift) { focusMode = !focusMode; ApplyLayout(); }
  else if (key == Key.F) ShowFind();
  else if (key == Key.P && shift && active != null) { active.Pinned = !active.Pinned; RenderTabs(); SaveLater(); }
  else if (key == Key.S && shift) { Prefs.Layout = Prefs.Layout == "Sidebar" ? "Top" : "Sidebar"; ApplyLayout(); }
  else if (key == Key.OemComma) ShowSettings();
  else if (active?.View is { } v) {
   if (key == Key.D0) v.ZoomFactor = 1;
   if (key is Key.OemPlus or Key.Add) v.ZoomFactor = Math.Min(3, v.ZoomFactor + 0.1);
   if (key is Key.OemMinus or Key.Subtract) v.ZoomFactor = Math.Max(0.3, v.ZoomFactor - 0.1);
   ShellPublish();
  }
 }
 void ShowFind()
 {
  if(shellReady){ShellOpen("find");return;}
  CloseSheet(false); FindBar.Visibility = Visibility.Visible;
  Dispatcher.BeginInvoke(() => { FindInput.Focus(); FindInput.SelectAll(); });
 }
 void CloseFind(object s, RoutedEventArgs e) { FindBar.Visibility = Visibility.Collapsed; active?.View?.Focus(); }
 async void FindNext(object s, RoutedEventArgs e) => await FindText();
 async void FindKeyDown(object s, KeyEventArgs e) { if (e.Key == Key.Enter) { e.Handled = true; await FindText(); } }
 async Task FindText()
 {
  if (active?.View?.CoreWebView2 is not { } core || FindInput.Text.Length == 0) return;
  var found = await core.ExecuteScriptAsync("window.find(" + JsonSerializer.Serialize(FindInput.Text) + ",false,false,true,false,false,false)");
  if (found != "true") Toast("No match found on this page.");
 }
}
