using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using System.Windows;
using Microsoft.Web.WebView2.Core;
namespace Still;

// Lets AI agents (via Still's MCP server, `Still.exe --mcp`) control the browser.
// Off by default. Every agent must be approved by the user for the session, a bar shows what it is
// doing and can stop it, and agents never see private tabs, saved passwords or cookies.
public partial class MainWindow
{
 static readonly HashSet<string> approvedAgents = new(StringComparer.OrdinalIgnoreCase);
 static readonly HashSet<string> blockedAgents = new(StringComparer.OrdinalIgnoreCase);
 static string agentName = "", agentAction = "";
 static DateTime agentSeen;
 static TaskCompletionSource<bool>? agentApproval;
 static bool agentServerStarted;
 static MainWindow Home => LastActive is { closing: false } w ? w : Windows.First(w => !w.closing);

 internal static void StartAgentServer(string instance)
 {
  if (agentServerStarted) return; agentServerStarted = true;
  new Thread(() => {
   while (true) {
    try {
     using var pipe = new NamedPipeServerStream(AgentPipe(instance), PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.CurrentUserOnly);
     pipe.WaitForConnection();
     using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, true);
     using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true };
     while (pipe.IsConnected && reader.ReadLine() is { } line) {
      string reply = Application.Current.Dispatcher.Invoke(() => Home.HandleAgent(line)).GetAwaiter().GetResult();
      writer.WriteLine(reply);
     }
    } catch (Exception ex) when (ex is IOException or ObjectDisposedException or InvalidOperationException or TaskCanceledException) { Thread.Sleep(200); }
   }
  }) { IsBackground = true, Name = "Still agent bridge" }.Start();
 }
 internal static string AgentPipe(string instance) => instance.Replace("Local\\", "") + "-agent";

 static string Reply(object result) => JsonSerializer.Serialize(new { ok = true, result });
 static string Fail(string message) => JsonSerializer.Serialize(new { ok = false, error = message });

 async Task<string> HandleAgent(string line)
 {
  try {
   using var doc = JsonDocument.Parse(line);
   var root = doc.RootElement;
   string client = (root.TryGetProperty("client", out var c) ? c.GetString() : null) ?? "An AI agent";
   client = new string(client.Where(ch => !char.IsControl(ch)).Take(40).ToArray());
   string tool = root.GetProperty("tool").GetString() ?? "";
   var args = root.TryGetProperty("args", out var a) && a.ValueKind == JsonValueKind.Object ? a : default;
   if (!Prefs.AgentsEnabled) return Fail("AI control is turned off. The user can turn it on in Still → Settings → Let AI agents control Still.");
   if (blockedAgents.Contains(client)) return Fail("The user blocked this agent for this session.");
   if (!approvedAgents.Contains(client)) {
    if (agentApproval == null) {
     agentApproval = new(TaskCreationOptions.RunContinuationsAsynchronously); agentName = client; PublishAll();
     var answered = await Task.WhenAny(agentApproval.Task, Task.Delay(TimeSpan.FromMinutes(2)));
     bool ok = answered == agentApproval.Task && agentApproval.Task.Result;
     agentApproval = null;
     if (ok) approvedAgents.Add(client); else blockedAgents.Add(client);
     PublishAll();
    } else await agentApproval.Task;
    if (!approvedAgents.Contains(client)) return Fail("The user did not allow this agent to control Still.");
   }
   agentName = client; agentSeen = DateTime.UtcNow;
   var result = await RunTool(tool, args);
   PublishAll();
   return result;
  } catch (JsonException) { return Fail("Invalid request."); }
  catch (Exception ex) when (ex is InvalidOperationException or KeyNotFoundException or FormatException or System.Runtime.InteropServices.COMException or TimeoutException) { return Fail(ex.Message); }
 }

 static void PublishAll() { foreach (var w in Windows) w.ShellPublish(); }
 object? AgentData() => agentApproval != null ? new { client = agentName, pending = true, action = "" }
  : approvedAgents.Contains(agentName) && DateTime.UtcNow - agentSeen < TimeSpan.FromMinutes(2) ? new { client = agentName, pending = false, action = agentAction } : null;
 void AnswerAgent(bool allow) => agentApproval?.TrySetResult(allow);
 void StopAgent() { if (agentName.Length > 0) { approvedAgents.Remove(agentName); blockedAgents.Add(agentName); } agentAction = ""; PublishAll(); Toast("The AI agent was stopped. It can't control Still again until you restart Still."); }

 static string S(JsonElement args, string key) => args.ValueKind == JsonValueKind.Object && args.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
 static double N(JsonElement args, string key, double fallback) => args.ValueKind == JsonValueKind.Object && args.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : fallback;

 // Finds a tab the agent may use: never private tabs.
 (MainWindow window, BrowserTab tab) AgentTab(JsonElement args)
 {
  string id = S(args, "tabId");
  foreach (var w in Windows.Where(w => !w.closing)) {
   var t = id.Length > 0 ? w.tabs.FirstOrDefault(x => x.Id == id) : (w == this ? w.active : null);
   if (t != null) { if (t.Private) throw new InvalidOperationException("Private tabs are off-limits to agents."); return (w, t); }
  }
  throw new InvalidOperationException(id.Length > 0 ? "No tab with that id." : "There is no active tab.");
 }
 static async Task<CoreWebView2> Core(MainWindow w, BrowserTab t)
 {
  if (t.View?.CoreWebView2 == null) await w.EnsureView(t);
  return t.View?.CoreWebView2 ?? throw new InvalidOperationException("The tab couldn't be loaded.");
 }
 static async Task WaitLoaded(BrowserTab t, int ms = 15000)
 {
  var until = DateTime.UtcNow.AddMilliseconds(ms);
  await Task.Delay(150);
  while (t.Loading && DateTime.UtcNow < until) await Task.Delay(100);
 }
 static string WebUrl(string input, string engine)
 {
  var url = ResolveAddress(input, engine);
  if (!Uri.TryCreate(url, UriKind.Absolute, out var u) || u.Scheme is not ("http" or "https")) throw new InvalidOperationException("Agents can only open http and https pages.");
  return url;
 }
 void Did(string action) => agentAction = action.Length > 90 ? action[..90] + "…" : action;

 async Task<string> RunTool(string tool, JsonElement args)
 {
  switch (tool) {
   case "list_tabs":
    return Reply(Windows.Where(w => !w.closing).SelectMany((w, wi) => w.tabs.Where(t => !t.Private).Select(t => new { id = t.Id, title = t.Title, url = t.Url, active = t == w.active, window = wi + 1 })));
   case "open_tab": {
    var tab = await NewTab(WebUrl(S(args, "url"), Prefs.SearchEngine), false, false); await WaitLoaded(tab);
    Did("Opened " + Host(tab.Url)); return Reply(new { id = tab.Id, title = tab.Title, url = tab.Url });
   }
   case "navigate": {
    var (w, t) = AgentTab(args); var core = await Core(w, t); core.Navigate(WebUrl(S(args, "url"), Prefs.SearchEngine)); await WaitLoaded(t);
    Did("Went to " + Host(t.Url)); return Reply(new { id = t.Id, title = t.Title, url = t.Url });
   }
   case "switch_tab": { var (w, t) = AgentTab(args); await w.SelectTab(t); w.Activate(); Did("Switched to " + t.Title); return Reply(new { id = t.Id }); }
   case "close_tab": { var (w, t) = AgentTab(args); await w.CloseTab(t, true); Did("Closed a tab"); return Reply(new { closed = true }); }
   case "go_back": case "go_forward": case "reload": {
    var (w, t) = AgentTab(args); var core = await Core(w, t);
    if (tool == "go_back") { if (core.CanGoBack) core.GoBack(); } else if (tool == "go_forward") { if (core.CanGoForward) core.GoForward(); } else core.Reload();
    await WaitLoaded(t); Did(tool == "reload" ? "Reloaded the page" : tool == "go_back" ? "Went back" : "Went forward"); return Reply(new { url = t.Url, title = t.Title });
   }
   case "read_page": {
    var (w, t) = AgentTab(args); var core = await Core(w, t);
    string json = await core.ExecuteScriptAsync("JSON.stringify({title:document.title,url:location.href,text:(document.body?.innerText||'').slice(0,30000),links:[...document.querySelectorAll('a[href]')].slice(0,150).map(a=>({text:(a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,80),href:a.href}))})");
    Did("Read " + Host(t.Url)); return Reply(JsonDocument.Parse(JsonSerializer.Deserialize<string>(json) ?? "{}").RootElement.Clone());
   }
   case "screenshot": {
    var (w, t) = AgentTab(args); if (t != w.active) await w.SelectTab(t); var core = await Core(w, t);
    using var ms = new MemoryStream(); await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, ms);
    Did("Took a screenshot"); return Reply(new { image = Convert.ToBase64String(ms.ToArray()), mimeType = "image/png" });
   }
   case "click": {
    var (w, t) = AgentTab(args); var core = await Core(w, t);
    string find = JsonSerializer.Serialize(new { selector = S(args, "selector"), text = S(args, "text") });
    string res = await core.ExecuteScriptAsync("((q)=>{let el=null;if(q.selector)el=document.querySelector(q.selector);if(!el&&q.text){const want=q.text.trim().toLowerCase();el=[...document.querySelectorAll('a,button,[role=button],input[type=submit],input[type=button],summary,label,[onclick]')].find(e=>(e.innerText||e.value||e.getAttribute('aria-label')||'').trim().toLowerCase().includes(want)&&e.getClientRects().length)}if(!el)return null;el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,label:(el.innerText||el.value||el.getAttribute('aria-label')||el.tagName).trim().slice(0,60)}})(" + find + ")");
    if (res == "null") throw new InvalidOperationException("Couldn't find that element on the page.");
    using var target = JsonDocument.Parse(res); double x = target.RootElement.GetProperty("x").GetDouble(), y = target.RootElement.GetProperty("y").GetDouble();
    foreach (var type in new[] { "mousePressed", "mouseReleased" })
     await core.CallDevToolsProtocolMethodAsync("Input.dispatchMouseEvent", JsonSerializer.Serialize(new { type, x, y, button = "left", clickCount = 1 }));
    await WaitLoaded(t, 5000);
    string label = target.RootElement.GetProperty("label").GetString() ?? "";
    Did("Clicked '" + label + "'"); return Reply(new { clicked = label, url = t.Url });
   }
   case "type": {
    var (w, t) = AgentTab(args); var core = await Core(w, t);
    string sel = JsonSerializer.Serialize(S(args, "selector"));
    string ok = await core.ExecuteScriptAsync("((s)=>{const el=s?document.querySelector(s):document.activeElement;if(!el)return false;el.scrollIntoView({block:'center'});el.focus();if('select' in el&&el.value!==undefined){el.select?.()}return true})(" + sel + ")");
    if (ok != "true") throw new InvalidOperationException("Couldn't find that field on the page.");
    if (args.TryGetProperty("clear", out var clr) && clr.ValueKind == JsonValueKind.True) await core.ExecuteScriptAsync("document.activeElement&&('value' in document.activeElement)&&(document.activeElement.value='')");
    await core.CallDevToolsProtocolMethodAsync("Input.insertText", JsonSerializer.Serialize(new { text = S(args, "text") }));
    if (args.TryGetProperty("submit", out var sub) && sub.ValueKind == JsonValueKind.True) {
     foreach (var type in new[] { "keyDown", "keyUp" })
      await core.CallDevToolsProtocolMethodAsync("Input.dispatchKeyEvent", JsonSerializer.Serialize(new { type, key = "Enter", code = "Enter", windowsVirtualKeyCode = 13, text = type == "keyDown" ? "\r" : "" }));
     await WaitLoaded(t, 8000);
    }
    Did("Typed into a field"); return Reply(new { typed = true, url = t.Url });
   }
   case "scroll": {
    var (w, t) = AgentTab(args); var core = await Core(w, t);
    double amount = Math.Clamp(N(args, "amount", 800), -20000, 20000) * (S(args, "direction") == "up" ? -1 : 1);
    await core.ExecuteScriptAsync("window.scrollBy(0," + amount.ToString(System.Globalization.CultureInfo.InvariantCulture) + ")");
    Did("Scrolled " + (amount < 0 ? "up" : "down")); return Reply(new { scrolled = amount });
   }
   case "wait_for": {
    var (w, t) = AgentTab(args); var core = await Core(w, t);
    string q = JsonSerializer.Serialize(new { selector = S(args, "selector"), text = S(args, "text") });
    var until = DateTime.UtcNow.AddMilliseconds(Math.Clamp(N(args, "timeoutMs", 10000), 100, 30000));
    while (DateTime.UtcNow < until) {
     if (await core.ExecuteScriptAsync("((q)=>q.selector?!!document.querySelector(q.selector):(document.body?.innerText||'').toLowerCase().includes(q.text.toLowerCase()))(" + q + ")") == "true") { Did("Waited for the page"); return Reply(new { found = true }); }
     await Task.Delay(250);
    }
    return Reply(new { found = false });
   }
   default: return Fail("Unknown tool: " + tool);
  }
 }
}
