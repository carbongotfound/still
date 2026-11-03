using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Windows;
using Microsoft.Web.WebView2.Core;
namespace Still;

// Lets AI agents (via Still's MCP server, `Still.exe --mcp`) control the browser.
// Off by default. Every agent must be approved by the user, a bar shows what it is doing and can stop it,
// and agents never see private tabs, saved passwords or cookies. Every call answers within a time limit,
// so an agent can never hang on a slow page, a dialog or a question the user hasn't answered yet.
public partial class MainWindow
{
 static readonly HashSet<string> approvedAgents = new(StringComparer.OrdinalIgnoreCase);
 static readonly HashSet<string> blockedAgents = new(StringComparer.OrdinalIgnoreCase);
 /// One AI at work, by run key: a chat's id for Still's own chat (so two chats on the same AI app stay apart),
 /// otherwise the outside agent's name.
 sealed class Worker
 {
  public string Name = "", Label = "", Color = "", Action = ""; // Name: the app; Label and Color: who the user sees (a companion)
  public DateTime Seen;
  public bool Paused; // the user took over: its calls wait until they hand it back
  public string SignIn = ""; // paused on a sign-in page of this site: the user signs in, then hands it back
  // For the pill: the tool running now and what it works on (a site, a search, a teammate; never what's typed),
  // the steps done since this stretch of work began, and the last few of them in the past tense.
  public string Tool = "", Target = "";
  public int Count;
  public DateTime Since;
  public readonly List<string> Recent = new();
  public (string Site, DateTime At) SignedIn; // when the user last handed back after signing in
 }
 static readonly Dictionary<string, Worker> workers = new(StringComparer.OrdinalIgnoreCase);
 static Worker Me(string who)
 {
  if (workers.TryGetValue(who, out var w)) return w;
  var run = runs.GetValueOrDefault(who);
  var c = run == null ? null : Home.Companions.FirstOrDefault(x => x.Id == run.Chat.Companion);
  return workers[who] = new() { Name = run?.Who ?? who, Label = c?.Name ?? run?.Who ?? who, Color = Hue(c) };
 }
 // The companion's color: its look's, or for one saved before looks, the old hue as in the shell's Buddy.tsx.
 static string Hue(Companion? c) => c?.Look is { Length: > 0 } look && System.Text.RegularExpressions.Regex.Match(look, "\"color\":\"(#[0-9a-fA-F]{6})\"") is { Success: true } m ? m.Groups[1].Value : c?.Color switch { "sage" => "#5c7a76", "lavender" => "#8f80aa", "apricot" => "#e8a76c", "mint" => "#8fcbbc", "blush" => "#f2a487",
  "periwinkle" => "#bbadea", "berry" => "#ed5a31", _ => "#4f7cf0" };
 /// Who's at work now: seen in the last 2 minutes, or waiting while the user took over.
 static IEnumerable<KeyValuePair<string, Worker>> AtWork() => workers.Where(w => approvedAgents.Contains(w.Value.Name) && (w.Value.Paused || w.Value.Tool.Length > 0 || DateTime.UtcNow - w.Value.Seen < TimeSpan.FromMinutes(2)));
 // One question in the agent bar at a time: letting a new agent in, or an action that needs the user's OK (uploads).
 static TaskCompletionSource<bool>? agentApproval;
 static string askClient = "", askText = "";
 static (string Client, string Ask, bool Allow, DateTime At) lastAnswer;
 // Ends an agent's running call early with this reply: a dialog or file picker opened in its tab, or the user pressed Stop.
 static readonly Dictionary<string, TaskCompletionSource<string>> agentInterrupts = new(StringComparer.OrdinalIgnoreCase);
 static bool agentServerStarted;
 internal static MainWindow Home => LastActive is { closing: false, temporary: false, incognito: false } w ? w : Windows.FirstOrDefault(w => !w.closing && !w.temporary && !w.incognito) ?? Windows.FirstOrDefault(w => !w.closing && !w.temporary) ?? Windows.First(w => !w.closing);

 // Any number of agents at once: each connection gets its own pipe instance, and calls run side by side.
 internal static void StartAgentServer(string instance)
 {
  if (agentServerStarted) return; agentServerStarted = true;
  _ = Task.Run(async () => {
   while (true) {
    NamedPipeServerStream? pipe = null;
    try {
     pipe = new NamedPipeServerStream(AgentPipe(instance), PipeDirection.InOut, NamedPipeServerStream.MaxAllowedServerInstances, PipeTransmissionMode.Byte, PipeOptions.CurrentUserOnly | PipeOptions.Asynchronous);
     await pipe.WaitForConnectionAsync();
     _ = ServeAgent(pipe);
    } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { pipe?.Dispose(); await Task.Delay(500); }
   }
  });
 }
 static async Task ServeAgent(NamedPipeServerStream pipe)
 {
  using (pipe) try {
   using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, true);
   using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true };
   while (await reader.ReadLineAsync() is { } line)
    await writer.WriteLineAsync(await Application.Current.Dispatcher.InvokeAsync(() => Home.HandleAgent(line)).Task.Unwrap());
  } catch (Exception ex) when (ex is IOException or ObjectDisposedException or InvalidOperationException or TaskCanceledException) { }
 }
 internal static string AgentPipe(string instance) => instance.Replace("Local\\", "") + "-agent";

 static readonly JsonSerializerOptions ReplyJson = new() { DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
 static string Reply(object result) => JsonSerializer.Serialize(new { ok = true, result }, ReplyJson);
 static string Fail(string message) => JsonSerializer.Serialize(new { ok = false, error = message });

 async Task<string> HandleAgent(string line)
 {
  try {
   using var doc = JsonDocument.Parse(line);
   var root = doc.RootElement;
   string client = (root.TryGetProperty("client", out var c) ? c.GetString() : null) ?? "An AI agent";
   client = new string(client.Where(ch => !char.IsControl(ch)).Take(40).ToArray());
   // Still's own chat runs say which chat they are; anyone else is known by name.
   string run = root.TryGetProperty("run", out var rn) && rn.ValueKind == JsonValueKind.String ? rn.GetString() ?? "" : "";
   string who = runs.TryGetValue(run, out var chatRun) && chatRun.Who == client ? run : client;
   string tool = root.GetProperty("tool").GetString() ?? "";
   var args = root.TryGetProperty("args", out var a) && a.ValueKind == JsonValueKind.Object ? a.Clone() : default;
   if (!Prefs.AgentsEnabled) return Fail("AI control is turned off. The user can turn it on in Still → Settings → Let other AI apps use Still.");
   if (tool == "user_confirmed") return Confirmed(client, args);
   // Don't keep the agent waiting on a bar nobody will see: its app can ask the user (elicitation), or the user is away.
   bool quick = root.TryGetProperty("elicit", out var el) && el.ValueKind == JsonValueKind.True || UserAway();
   if (blockedAgents.Contains(client)) return Fail("The user blocked this agent in Still for this session.");
   if (stoppedAgents.TryGetValue(who, out var until) && DateTime.UtcNow < until) return Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message.");
   if (Prefs.ApprovedAgents.Any(a => McpServer.AgentName(a).Equals(client, StringComparison.OrdinalIgnoreCase))) approvedAgents.Add(client); // approved once = remembered across restarts/updates
   if (!approvedAgents.Contains(client)) switch (await AskUser(client, "", quick)) {
    case false: return Fail("The user blocked this agent in Still for this session.");
    case null: return NeedsConfirm(client, "", "Waiting for the user to let you in: Still shows a bar with Allow and Block at the top of its window. Tell the user to click Allow, then call the tool again.");
   }
   var me = Me(who);
   if (DateTime.UtcNow - me.Seen > TimeSpan.FromMinutes(2) && !me.Paused) { me.Since = DateTime.UtcNow; me.Count = 0; me.Recent.Clear(); } // a new stretch of work
   me.Seen = DateTime.UtcNow;
   // The user took over: wait for them to hand it back, like a person would.
   for (var paused = DateTime.UtcNow.AddSeconds(40); me.Paused && DateTime.UtcNow < paused;) { await Task.Delay(250); me.Seen = DateTime.UtcNow; }
   if (stoppedAgents.TryGetValue(who, out until) && DateTime.UtcNow < until) return Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message.");
   if (me.Paused) return Fail(me.SignIn.Length > 0 ? SigningIn(me.SignIn) : TookOver);
   // A new companion's first chat opens with its own words: its tools (ask_user too) wait for its hello.
   if (kickoffs.Contains(who) && runs.GetValueOrDefault(who)?.Chat is { } kick) {
    for (var wait = DateTime.UtcNow.AddSeconds(1.5); !kick.Messages.Any(m => m.Role == "assistant") && DateTime.UtcNow < wait;) await Task.Delay(100);
    if (!kick.Messages.Any(m => m.Role == "assistant")) return Fail(HelloFirst);
   }
   var interrupt = agentInterrupts[who] = new(TaskCreationOptions.RunContinuationsAsynchronously);
   // The permission layer: it runs, asks in the chat, or counts down first. Take over and Stop end the wait too.
   var gate = Gate(who, tool, args, quick);
   string? refused = await Task.WhenAny(gate, interrupt.Task) == gate ? await gate : await interrupt.Task;
   if (!gate.IsCompleted) foreach (var card in runs.GetValueOrDefault(who)?.Approvals.ToList() ?? []) card.Answer.TrySetResult("stop");
   if (refused != null) { if (agentInterrupts.GetValueOrDefault(who) == interrupt) agentInterrupts.Remove(who); PublishAll(); return refused; }
   var going = runs.GetValueOrDefault(who);
   if (going?.Intent is { } intent) { going.Task.Sensitive.Add(intent); if (going.Task.Sensitive.Count > 40) going.Task.Sensitive.RemoveAt(0); SaveTask(going); }
   me.Tool = tool; me.Target = TargetOf(who, tool, args); PublishAll();
   string result;
   try {
    var working = RunTool(who, tool, args, quick);
    int limit = tool switch { "ask_user" or "run_plugin_action" or "ask_companion" => 660_000, "wait_for" => (int)Math.Clamp(N(args, "timeoutMs", 10000), 100, 30000) + 5000, "upload_file" => 60000, _ => 30000 };
    var first = await Task.WhenAny(working, interrupt.Task, Task.Delay(limit));
    result = first == working ? await working : first == interrupt.Task ? await interrupt.Task
     : Fail($"{tool} didn't finish within {limit / 1000} s, so Still stopped waiting. The page may be slow or stuck: call read_page to see where it is.");
    if (going != null) {
     if (going.Intent is { } ran) { if (first == working) ran.Outcome = result.StartsWith("{\"ok\":false", StringComparison.Ordinal) ? "failed" : "done"; going.Intent = null; } // cut off: uncertain
     Checkpoint(going, tool, result);
    }
    if (tool is "ask_companion" or "tell_companion" && me.Target.Length > 0 && !result.StartsWith("{\"ok\":false", StringComparison.Ordinal)) Did(who, (tool == "ask_companion" ? "Asked " : "Handed work to ") + me.Target);
   } finally { me.Tool = ""; me.Count++; me.Seen = DateTime.UtcNow; }
   if (agentInterrupts.GetValueOrDefault(who) == interrupt) agentInterrupts.Remove(who);
   PublishAll();
   return result;
  } catch (JsonException) { return Fail("Invalid request."); }
  catch (Exception ex) when (ex is InvalidOperationException or KeyNotFoundException or FormatException or ArgumentException or IOException or UnauthorizedAccessException or NotSupportedException or System.Runtime.InteropServices.COMException or TimeoutException) { return Fail(ex.Message); }
 }

 /// Asks the user in the agent bar ("" = may this agent control Still). Null: no answer yet; the question stays up.
 /// now: don't wait for the answer (the agent asks the user elsewhere, see NeedsConfirm).
 static async Task<bool?> AskUser(string client, string ask, bool now = false)
 {
  if (lastAnswer.Client == client && lastAnswer.Ask == ask && DateTime.UtcNow - lastAnswer.At < TimeSpan.FromMinutes(2)) return lastAnswer.Allow; // answered after the agent stopped waiting
  var deadline = Task.Delay(TimeSpan.FromSeconds(now ? 0 : 45)); // shorter than MCP apps' own tool timeouts
  while (agentApproval is { } other && !(askClient == client && askText == ask))
   if (now || await Task.WhenAny(other.Task, deadline) == deadline) return null;
  if (agentApproval == null) { agentApproval = new(TaskCreationOptions.RunContinuationsAsynchronously); askClient = client; askText = ask; PublishAll(); }
  var pending = agentApproval;
  return await Task.WhenAny(pending.Task, deadline) == pending.Task ? pending.Task.Result : null;
 }
 void AnswerAgent(bool allow)
 {
  if (agentApproval is not { } pending) return;
  Settle(askClient, askText, allow);
  agentApproval = null; askClient = askText = "";
  pending.TrySetResult(allow); PublishAll();
 }
 void Settle(string client, string ask, bool allow)
 {
  if (ask.Length == 0) {
   if (!allow) blockedAgents.Add(client);
   else { approvedAgents.Add(client); if (!Prefs.ApprovedAgents.Contains(client, StringComparer.OrdinalIgnoreCase)) Prefs.ApprovedAgents.Add(client); SaveLater(); }
  }
  lastAnswer = (client, ask, allow, DateTime.UtcNow);
  foreach (var code in confirmCodes.Where(c => c.Value.Client == client && c.Value.Ask == ask).Select(c => c.Key).ToList()) confirmCodes.Remove(code); // answered here: a code from the chat no longer counts
 }

 // The user is away from Still: the agent asks them in its own chat instead. MCP apps that support elicitation
 // ask the user themselves (the AI never sees the question); otherwise the AI passes the user's answer on.
 static readonly Dictionary<string, (string Client, string Ask, DateTime Until)> confirmCodes = [];
 string NeedsConfirm(string client, string ask, string waiting)
 {
  if (!Prefs.AgentsAskInChat) return Fail(waiting);
  foreach (var old in confirmCodes.Where(c => c.Value.Until < DateTime.UtcNow).Select(c => c.Key).ToList()) confirmCodes.Remove(old);
  string code = Convert.ToHexString(RandomNumberGenerator.GetBytes(3)).ToLowerInvariant();
  confirmCodes[code] = (client, ask, DateTime.UtcNow.AddMinutes(10));
  string question = ask.Length == 0 ? $"Allow {client} to use your Still browser? It can open, read and click pages, but never private tabs, passwords or cookies." : $"Allow {client} to {ask}?";
  return JsonSerializer.Serialize(new { ok = false, confirm = new { code, question },
   error = waiting + $" If the user isn't at Still, ask them in your chat instead: \"{question}\" Then call user_confirmed with code \"{code}\" and allow true or false, as they answer. Never answer for the user." }, ReplyJson);
 }
 string Confirmed(string client, JsonElement args)
 {
  if (!confirmCodes.Remove(S(args, "code").Trim().ToLowerInvariant(), out var c) || !c.Client.Equals(client, StringComparison.OrdinalIgnoreCase) || c.Until < DateTime.UtcNow)
   return Fail("That code isn't valid anymore (the user may have answered in Still). Call the tool again.");
  bool allow = B(args, "allow");
  if (agentApproval != null && askClient == c.Client && askText == c.Ask) AnswerAgent(allow); else Settle(c.Client, c.Ask, allow);
  Toast($"{c.Client} was {(allow ? "allowed" : "turned down")} {(c.Ask.Length == 0 ? "to use Still" : "to " + c.Ask)}, answered through its chat.");
  return Reply(new { done = allow ? "The user allowed it. Call the tool again now." : "The user said no. Don't try again unless they ask." });
 }
 [StructLayout(LayoutKind.Sequential)] struct LastInput { public uint Size, Time; }
 [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LastInput info);
 /// No keyboard or mouse for a minute (or the screen is locked), or Still is minimized: nobody will see the bar.
 static bool UserAway()
 {
  var input = new LastInput { Size = 8 };
  return GetLastInputInfo(ref input) && (uint)Environment.TickCount - input.Time > 60_000 || Windows.All(w => w.closing || w.WindowState == WindowState.Minimized);
 }

 static void PublishAll() { foreach (var w in Windows) w.ShellPublish(); }
 /// The agent bar's question, or the AI at work for the pill: the one in the page on screen, else the latest.
 object? AgentData()
 {
  if (agentApproval != null) return new { client = askClient, pending = true, action = "", ask = askText, paused = false };
  string? shown = Shown?.Id;
  var at = AtWork().OrderByDescending(w => agentTabs.GetValueOrDefault(w.Key) == shown).ThenByDescending(w => w.Value.Seen).FirstOrDefault();
  return at.Value is { } me ? new { client = me.Name, pending = false, action = me.Action, ask = "", paused = me.Paused, signIn = me.SignIn, tab = agentTabs.GetValueOrDefault(at.Key), key = at.Key,
   tool = me.Tool, target = me.Target, since = me.Since == default ? null : me.Since.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'"), count = me.Count, recent = me.Recent.ToArray() } : null;
 }
 // Take over: the agent stops at once and waits while the user drives, and the tab it works in comes to the front.
 async Task TakeOver(bool on, string key)
 {
  if (workers.GetValueOrDefault(key) is not { } me) return;
  me.Paused = on;
  TaskState(runs.GetValueOrDefault(key), on ? "paused" : "running");
  if (!on && me.SignIn.Length > 0) { me.SignedIn = (me.SignIn, DateTime.UtcNow); me.SignIn = ""; }
  if (on && agentInterrupts.Remove(key, out var running)) running.TrySetResult(Fail(TookOver));
  if (on && agentTabs.GetValueOrDefault(key) is { } id && tabs.FirstOrDefault(t => t.Id == id) is { } t) await SelectTab(t);
  PublishAll();
 }
 // Stop cancels what the agent is doing now and lets go of its tabs; it stays allowed, so its next task needs no new approval.
 void StopAgent(string key)
 {
  var me = workers.GetValueOrDefault(key);
  ReleaseAgentTabs(key); stoppedAgents[key] = DateTime.UtcNow.AddSeconds(30);
  if (agentInterrupts.Remove(key, out var running)) running.TrySetResult(Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message."));
  if (runs.TryGetValue(key, out var run)) { run.Queue.Clear(); StopRun(run); }
  workers.Remove(key); PublishAll(); PublishAiEverywhere(); Toast("Stopped " + (me?.Label ?? "the AI agent") + ".");
 }
 static readonly Dictionary<string, DateTime> stoppedAgents = new(StringComparer.OrdinalIgnoreCase);
 /// A sign-in page: AIs never type or see passwords, so this one waits, like after Take over, while the user signs in
 /// (a saved login fills from the key in the field). The tab comes to the front and its pill asks them to sign in.
 async Task AskToSignIn(string who, MainWindow w, BrowserTab t, string site)
 {
  var me = Me(who);
  if (me.Paused) return;
  me.Paused = true; me.SignIn = site;
  TaskState(runs.GetValueOrDefault(who), "paused", "site");
  if (!t.Closed) await w.SelectTab(t);
  PublishAll(); w.Toast(me.Label + " needs you to sign in to " + site + ". It never sees your password.");
 }
 static string SigningIn(string site) => "This is a sign-in page for " + site + ". AIs never type or see passwords, so Still paused you and asked the user to sign in themselves. Call your next tool again: Still holds it until they hand the tab back, then check the page with read_page.";
 // Masks inputs whose value matches a saved login's fingerprint (MainWindow.LoginPrints), then unmasks them.
 const string MaskJs = """
  const print = s => { let h = 0; for (let i = 0; i < s.length; i++) h = h * 31 + s.charCodeAt(i) | 0; return h; };
  walk(document, e => {
   if (e.localName !== 'input') return;
   if (!o.on) { if (e.hasAttribute('data-still-masked')) { e.style.removeProperty('-webkit-text-security'); e.removeAttribute('data-still-masked'); } return; }
   if (e.value && o.prints.includes(print(e.value))) { e.style.setProperty('-webkit-text-security', 'disc', 'important'); e.setAttribute('data-still-masked', ''); }
  });
  return true;
 """;
 const string HelloFirst = "Write your hello first: greet the user and say in a sentence or two what you'll do for them, then use your tools.";
 const string TookOver = "The user took over this tab for a moment, so your last action may not have finished. Call your next tool again: Still holds it until they hand the tab back, then check the page with read_page.";
 /// A dialog or file picker opened in the tab an agent is working in: its running call returns now and says so.
 static void InterruptAgent(BrowserTab t, object reply)
 {
  if (t.AgentKey is { } who && agentTabs.GetValueOrDefault(who) == t.Id && agentInterrupts.Remove(who, out var running)) running.TrySetResult(Reply(reply));
 }

 static string S(JsonElement args, string key) => args.ValueKind == JsonValueKind.Object && args.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
 static bool B(JsonElement args, string key) => args.ValueKind == JsonValueKind.Object && args.TryGetProperty(key, out var v) && (v.ValueKind == JsonValueKind.True || v.ValueKind == JsonValueKind.String && v.GetString() == "true");
 static double N(JsonElement args, string key, double fallback)
 {
  if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(key, out var v)) return fallback;
  if (v.ValueKind == JsonValueKind.Number) return v.GetDouble();
  return v.ValueKind == JsonValueKind.String && double.TryParse(v.GetString(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var d) ? d : fallback;
 }
 // An element id from read_page or find: 12, "12" or "[12]".
 static string Id(JsonElement args) => args.ValueKind == JsonValueKind.Object && args.TryGetProperty("id", out var v) ? (v.ValueKind == JsonValueKind.Number ? v.GetRawText() : v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "").Trim('[', ']', ' ') : "";

 // Shared by every agent script. Walks the page in order, into open shadow roots and same-origin frames.
 // Elements keep their ids (data-still-id) for as long as they exist, so an id from an earlier read still works.
 const string PageJs = """
  const S = window.__still || (window.__still = { n: 0 });
  const view = e => e.ownerDocument.defaultView;
  const clip = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  const walk = (root, fn) => {
   const t = (root.ownerDocument || root).createTreeWalker(root, 1);
   for (let e = t.nextNode(); e; e = t.nextNode()) {
    if (fn(e) === false) return false;
    if (e.shadowRoot && walk(e.shadowRoot, fn) === false) return false;
    if (e.localName === 'iframe' || e.localName === 'frame') { let d = null; try { d = e.contentDocument; } catch {} if (d && d.documentElement && walk(d, fn) === false) return false; }
   }
  };
  const frames = (d = document, out = []) => { for (const f of d.querySelectorAll('iframe,frame')) { try { const c = f.contentDocument; if (c && c.body) { out.push(c); frames(c, out); } } catch {} } return out; };
  const pageText = () => [document, ...frames()].map(d => d.body ? d.body.innerText : '').filter(s => s.trim()).join('\n').replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n');
  // Position in the top window's viewport, adding the offsets of any frames it sits in.
  const box = e => { const r = e.getBoundingClientRect(); let x = r.left, y = r.top; for (let w = view(e); w !== window && w.frameElement; w = w.parent) { const f = w.frameElement.getBoundingClientRect(); x += f.left + w.frameElement.clientLeft; y += f.top + w.frameElement.clientTop; } return { x, y, w: r.width, h: r.height }; };
  const Q = 'a[href],button,input:not([type=hidden]),select,textarea,summary,label[for],[role=button],[role=link],[role=checkbox],[role=radio],[role=tab],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],[role=option],[role=switch],[role=combobox],[role=textbox],[role=searchbox],[role=slider],[role=treeitem],[contenteditable=""],[contenteditable=true],[contenteditable=plaintext-only],[onclick],[tabindex]:not([tabindex="-1"])';
  const parentOf = e => e.parentElement || (e.getRootNode && e.getRootNode().host) || null;
  // Controls, plus clickable things built from plain elements (the outermost element with a pointer cursor).
  const isControl = (e, cs) => e.localName === 'label' ? !!e.control && !visible(e.control, view(e).getComputedStyle(e.control)) : e.matches(Q) || cs.cursor === 'pointer' && !!parentOf(e) && view(e).getComputedStyle(parentOf(e)).cursor !== 'pointer' && !!(e.innerText || e.getAttribute('aria-label') || '').trim();
  const visible = (e, cs) => e.getClientRects().length > 0 && cs.visibility !== 'hidden' && (+cs.opacity > 0 || e.localName === 'input');
  const editable = e => e.isContentEditable && !e.matches('a,button');
  const label = e => {
   const t = e.localName, d = e.ownerDocument;
   let s = e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby') || '').split(/\s+/).map(i => i && d.getElementById(i)?.innerText).filter(Boolean).join(' ');
   if (!s && (t === 'input' || t === 'textarea' || t === 'select')) s = e.labels?.[0]?.innerText || e.placeholder || e.title || (/^(submit|button|reset)$/.test(e.type) ? e.value : '') || e.name;
   if (!s && editable(e)) s = e.getAttribute('aria-placeholder') || e.getAttribute('data-placeholder') || e.getAttribute('placeholder') || e.title;
   if (!s && !editable(e) && t !== 'select') s = e.innerText || e.title || e.querySelector('img[alt]')?.alt || e.querySelector('svg title')?.textContent || '';
   return clip(s, 80);
  };
  const kind = e => { const r = e.getAttribute('role'), t = e.localName; return r || (t === 'a' ? 'link' : t === 'input' ? 'input[' + (e.type || 'text') + ']' : editable(e) ? 'editor' : e.matches(Q) ? t : 'clickable'); };
  const mark = e => { let id = e.getAttribute('data-still-id'); if (!id) e.setAttribute('data-still-id', id = String(++S.n)); return id; };
  const line = e => {
   const t = e.localName, l = label(e); let s = '[' + mark(e) + '] ' + kind(e) + (l ? ' "' + l + '"' : '');
   if (t === 'a') { const h = e.getAttribute('href') || '', o = e.ownerDocument.location.origin; if (h && !h.startsWith('javascript:') && h !== '#') s += ' → ' + clip(e.href.startsWith(o) ? e.href.slice(o.length) || '/' : e.href, 100); }
   if (t === 'select') s += ' =' + clip(e.selectedOptions[0]?.text, 40) + ' {' + [...e.options].slice(0, 25).map(x => clip(x.text, 30)).join('|') + (e.options.length > 25 ? '|…' : '') + '}';
   else if (e.type === 'checkbox' || e.type === 'radio') s += e.checked ? ' ✓' : ' ☐';
   else if ((t === 'input' || t === 'textarea') && e.value && e.type !== 'password') s += ' =' + clip(e.value, 60);
   else if (editable(e) && e.innerText.trim()) s += ' =' + clip(e.innerText, 60);
   const on = e.getAttribute('aria-checked') ?? e.getAttribute('aria-pressed') ?? e.getAttribute('aria-selected');
   if (on === 'true') s += ' ✓'; else if (on === 'false' && e.hasAttribute('aria-checked')) s += ' ☐';
   if (e.getAttribute('aria-expanded')) s += ' expanded=' + e.getAttribute('aria-expanded');
   if (e.disabled || e.getAttribute('aria-disabled') === 'true') s += ' (disabled)';
   return s;
  };
  const inside = (a, b) => { for (; b; b = b.parentNode || b.host) if (b === a) return true; return false; };
  const deepActive = () => { let a = document.activeElement; for (;;) { if (a && a.shadowRoot && a.shadowRoot.activeElement) { a = a.shadowRoot.activeElement; continue; } let d = null; if (a && /^i?frame$/.test(a.localName)) try { d = a.contentDocument; } catch {} if (d && d.activeElement) { a = d.activeElement; continue; } return a; } };
  const byId = id => { id = String(id); let hit = document.querySelector('[data-still-id="' + id + '"]'); if (!hit) walk(document, e => { if (e.getAttribute('data-still-id') === id) { hit = e; return false; } }); return hit; };
  const bySel = sel => { let hit = null; walk(document, e => { if (e.matches(sel)) { hit = e; return false; } }); return hit; };
  const byText = text => { const want = text.trim().toLowerCase(); let best = null; walk(document, e => { const cs = view(e).getComputedStyle(e); if (!isControl(e, cs) || !visible(e, cs)) return; const l = label(e).toLowerCase(); if (l === want) { best = e; return false; } if (!best && l.includes(want)) best = e; }); return best; };
  const target = o => o.id ? byId(o.id) : o.selector ? bySel(o.selector) : o.text ? byText(o.text) : null;
  const missing = o => ({ error: o.id ? 'gone' : 'notfound' });
  // A fingerprint of a field's text, to tell whether typing changed it.
  const sig = e => { const s = !e ? '' : e.isContentEditable ? e.innerText : String(e.value ?? ''); let h = 0; for (let i = 0; i < s.length; i++) h = h * 31 + s.charCodeAt(i) | 0; return s.length + ':' + h; };
 """;

 // read_page: header, then one line per control near the visible area (or all of them), then a page of the text.
 const string SnapshotJs = """
  const vh = innerHeight, out = [], listed = new Set(), cap = o.all ? 600 : 250; let above = 0, below = 0, more = 0;
  walk(document, e => {
   const cs = view(e).getComputedStyle(e);
   if (!isControl(e, cs) || !visible(e, cs)) return;
   const host = parentOf(e)?.closest?.('a,button'); if (host && listed.has(host)) return;
   if (!o.all) { const b = box(e); if (b.y + b.h < -vh / 2) { above++; return; } if (b.y > vh * 1.5) { below++; return; } }
   if (listed.size >= cap) { more++; return; }
   listed.add(e); out.push(line(e));
  });
  const se = document.scrollingElement || document.documentElement;
  let s = document.title + '\n' + location.href + '\nscrolled ' + Math.round(scrollY) + ' of ' + Math.max(0, se.scrollHeight - vh) + 'px\n\n' + (out.join('\n') || '(no buttons, links or fields here)');
  if (above || below || more) s += '\n… ' + [above && above + ' more above', below && below + ' more below', more && more + ' more'].filter(Boolean).join(', ') + ' (scroll, use find, or read_page all=true)';
  if (o.text) {
   const t = pageText(), from = Math.min(o.offset, t.length), part = t.slice(from, from + 8000), end = from + part.length;
   s += '\n\n--- text' + (from > 0 || end < t.length ? ' (characters ' + from + '–' + end + ' of ' + t.length + (end < t.length ? '; read_page offset=' + end + ' for more' : '') + ')' : '') + ' ---\n' + part;
  }
  return s;
 """;
 // find: controls whose label, value or link matches, then matching lines of text, from anywhere on the page.
 const string FindJs = """
  const want = o.text.trim().toLowerCase(), out = [];
  if (!want) return { error: 'empty' };
  walk(document, e => {
   const cs = view(e).getComputedStyle(e);
   if (!isControl(e, cs) || !visible(e, cs)) return;
   if ((label(e) + ' ' + (e.type === 'password' ? '' : e.value || '') + ' ' + (e.getAttribute('href') || '') + ' ' + (e.title || '')).toLowerCase().includes(want)) out.push(line(e));
   if (out.length >= 25) return false;
  });
  const text = pageText().split('\n').filter(l => l.toLowerCase().includes(want)).slice(0, 15).map(l => clip(l, 200));
  return (out.length ? out.join('\n') : 'No buttons, links or fields match.') + '\n\n--- text ---\n' + (text.length ? text.join('\n') : 'No text matches.');
 """;
 const string ClickJs = """
  const e = target(o); if (!e) return missing(o);
  e.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
  const b = box(e); if (!b.w && !b.h) return { error: 'hidden' };
  const x = b.x + b.w / 2, y = b.y + b.h / 2;
  if (e.ownerDocument === document) {
   const top = document.elementFromPoint(x, y);
   if (top && !inside(top, e) && !inside(e, top) && top.closest('label')?.control !== e) return { error: 'covered', by: line(top.closest(Q) || top) };
  }
  return { x, y, label: label(e) || kind(e) };
 """;
 // type: focuses the field and selects what's in it (so typing replaces it), or picks a dropdown option.
 const string FocusJs = """
  const e = o.id || o.selector ? target(o) : deepActive();
  if (!e || e.localName === 'body') return o.id || o.selector ? missing(o) : { error: 'nofocus' };
  if (e.localName === 'select') {
   const want = o.value.trim().toLowerCase(), opts = [...e.options];
   const opt = opts.find(x => x.value === o.value || x.text.trim().toLowerCase() === want) || opts.find(x => x.text.trim().toLowerCase().includes(want));
   if (!opt) return { error: 'nooption', options: opts.slice(0, 30).map(x => x.text.trim()).join(' | ') };
   e.value = opt.value; e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true }));
   return { done: 'Picked "' + clip(opt.text, 60) + '"' };
  }
  e.scrollIntoView({ block: 'center', behavior: 'instant' }); e.focus();
  if (e.localName === 'input' && /^(date|time|datetime-local|month|week|color|range)$/.test(e.type)) {
   Object.getOwnPropertyDescriptor(view(e).HTMLInputElement.prototype, 'value').set.call(e, o.value);
   e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true }));
   return { done: 'Set ' + (label(e) || 'the field') + ' to ' + clip(o.value, 40) };
  }
  if (e.isContentEditable) { const sel = e.ownerDocument.getSelection(); sel.selectAllChildren(e); if (o.append) sel.collapseToEnd(); }
  else if (!o.append) { if (typeof e.select === 'function') e.select(); }
  else if (typeof e.setSelectionRange === 'function') { try { e.setSelectionRange(e.value.length, e.value.length); } catch {} }
  // Rich editors (Notion and the like) only wake up for a real click: one at the end of the text, away from links.
  let at = null;
  if (e.isContentEditable && !o.clicked && e.ownerDocument === document) {
   const b = box(e), x = b.x + b.w - 3, y = b.y + b.h - 6, hit = document.elementFromPoint(x, y);
   if (b.w > 6 && b.h > 8 && hit && inside(e, hit) && !hit.closest('a')) at = { x, y };
  }
  const fb = box(e), near = e.ownerDocument === document ? { x: fb.x + Math.min(24, fb.w / 2), y: fb.y + fb.h / 2 } : null; // where the AI's cursor goes
  return { label: label(e) || kind(e), sig: sig(deepActive()), multiline: e.isContentEditable || e.localName === 'textarea', at, near };
 """;
 // scroll: an element into view, or the page (or the scrolling panel under the middle of the view) by some pixels.
 const string ScrollJs = """
  const scroller = e => { for (let n = e; n; n = parentOf(n)) { if (n === n.ownerDocument.documentElement || n === n.ownerDocument.body) break; const cs = view(n).getComputedStyle(n); if (/(auto|scroll|overlay)/.test(cs.overflowY) && n.scrollHeight > n.clientHeight + 4) return n; } return document.scrollingElement || document.documentElement; };
  let el = null;
  if (o.id || o.selector) { el = target(o); if (!el) return missing(o); if (!o.direction) { el.scrollIntoView({ block: 'center', behavior: 'instant' }); return { done: 'Scrolled to "' + (label(el) || kind(el)) + '"' }; } }
  const sc = scroller(el || document.elementFromPoint(innerWidth / 2, innerHeight / 2) || document.body);
  sc.scrollBy({ top: (o.direction === 'up' ? -1 : 1) * (o.amount || Math.round(innerHeight * .8)), behavior: 'instant' });
  const max = sc.scrollHeight - sc.clientHeight;
  return { done: 'Scrolled ' + (o.direction === 'up' ? 'up' : 'down'), at: max > 0 ? Math.round(sc.scrollTop / max * 100) + '%' : 'no scrolling here' };
 """;
 const string SigJs = "return { sig: sig(deepActive()) };";
 const string WaitJs = """
  const found = o.id ? !!byId(o.id) : o.selector ? !!bySel(o.selector) : pageText().toLowerCase().includes(o.text.toLowerCase());
  return o.gone ? !found : found;
 """;
 // upload_file by element: the file input itself, for DOM.setFileInputFiles.
 // Is this click or keystroke sensitive: buying, sending, deleting, a form that posts, a password or payment field?
 const string SensitiveJs = """
  const e = o.id || o.selector || (o.tool === 'click' && o.text) ? target(o) : deepActive();
  if (!e) return missing(o);
  if (e.localName === 'body') return { error: 'nofocus' };
  const form = e.form || (e.closest && e.closest('form'));
  const secret = x => x.type === 'password' ? 'password' : /^cc-|card.?num|cvc|cvv|security.?code|iban/i.test((x.autocomplete || '') + ' ' + (x.name || '') + ' ' + (x.id || '')) ? 'payment' : '';
  const posts = !!form && (form.method === 'post' || [...form.elements].some(secret));
  const words = (label(e) + ' ' + (e.localName === 'input' ? e.value : '')).toLowerCase();
  let why = '';
  if (o.tool === 'type') why = secret(e) === 'password' ? 'It types into a password field.' : secret(e) ? 'It types into a payment field.' : o.submit && posts ? 'It sends a form.' : '';
  else if (o.tool === 'press_key') why = /enter/i.test(o.key) && posts && e.matches('input,select') ? 'It sends a form.' : '';
  else if (/\b(buy|purchase|place order|order now|pay|checkout|check out|subscribe|book now|reserve)\b/.test(words)) why = 'It looks like a purchase.';
  else if (/\b(send|post|publish|reply|tweet|comment)\b/.test(words)) why = 'It sends something in your name.';
  else if (/\b(delete|remove|discard|trash|unsubscribe|close account|cancel order|cancel subscription)\b/.test(words)) why = 'It deletes or cancels something.';
  else if (posts && e.matches('button:not([type=button]):not([type=reset]),input[type=submit],input[type=image]')) why = 'It sends a form.';
  return { label: label(e) || kind(e), why, secret: !!secret(e), password: secret(e) === 'password' };
 """;
 const string FileInputJs = """
  const e = target(o); return e && e.localName === 'input' && e.type === 'file' ? e : e?.querySelector?.('input[type=file]') || e?.closest?.('label')?.control || null;
 """;

 static async Task<JsonElement> Js(CoreWebView2 core, string body, object o)
 {
  string json = await core.RunAsync("((o)=>{try{" + PageJs + body + "}catch(err){return {error:'script',message:String(err&&err.message||err)}}})(" + JsonSerializer.Serialize(o) + ")");
  using var doc = JsonDocument.Parse(json);
  var r = doc.RootElement.Clone();
  if (r.ValueKind == JsonValueKind.Object && r.TryGetProperty("error", out var err)) throw new PageMiss(err.GetString() is "gone" or "notfound" or "hidden" or "covered", err.GetString() switch {
   "gone" => "That element isn't on the page anymore (the page changed or it's a new page). Call read_page or find for current ids.",
   "notfound" => "Couldn't find that element on the page. Call read_page or find.",
   "hidden" => "That element is hidden right now (maybe in a closed menu). Open what contains it first, or call read_page.",
   "covered" => "Something is on top of that element: " + Str(r, "by") + ". Close or click that first (often a cookie banner or pop-up).",
   "nofocus" => "No field is focused. Pass the field's id.",
   "nooption" => "That dropdown has no matching option. Options: " + Str(r, "options"),
   "empty" => "Pass the text to look for.",
   _ => "The page's script failed: " + Str(r, "message"),
  });
  return r;
 }
 sealed class PageMiss(bool missed, string message) : InvalidOperationException(message) { public readonly bool Missed = missed; } // Missed: the element moved, vanished or is covered
 // Pages re-render under the AI: when the element is missing, wait for the page to settle and try once more.
 // Still missing: the error carries a fresh read of the page, so the AI picks again (and asks again if that step needs asking).
 static async Task<JsonElement> Settled(BrowserTab t, CoreWebView2 core, Func<Task<JsonElement>> act)
 {
  try { return await act(); }
  catch (PageMiss miss) when (miss.Missed) { await WaitLoaded(t, 3000); await Task.Delay(500); }
  try { return await act(); }
  catch (PageMiss miss) when (miss.Missed) {
   string now = (await Js(core, SnapshotJs, new { text = false, all = false, offset = 0 })).GetString() ?? "";
   throw new InvalidOperationException(miss.Message + "\n\nThe page now:\n" + now);
  }
 }
 static string Str(JsonElement e, string key) => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

 // Finds a tab the agent may use: never private tabs.
 (MainWindow window, BrowserTab tab) AgentTab(string who, JsonElement args)
 {
  // Without a tabId the agent keeps working in the tab it used last, even after the user switches to another one.
  string id = S(args, "tabId");
  if (id.Length == 0 && agentTabs.TryGetValue(who, out var last) && FindTab(last) != null) id = last;
  foreach (var w in Windows.Where(w => !w.closing)) {
   var t = id.Length > 0 ? w.tabs.FirstOrDefault(x => x.Id == id) : (w == this ? w.active : null);
   if (t != null) {
    // An incognito chat works only in the private tabs it opened. Every other agent never touches a private tab.
    if (Incognito(who) ? (t.InChat ?? t.RunChat) != who : t.Private) throw new InvalidOperationException(Incognito(who) ? "An incognito chat only uses the tabs it opened. Open one with open_tab." : "Private tabs are off-limits to agents.");
    Claim(who, w, t); return (w, t);
   }
  }
  throw new InvalidOperationException(id.Length > 0 ? "No tab with that id. Call list_tabs." : "There is no active tab.");
 }
 /// The agent's tab, ready for page work. A page paused on a dialog can't run scripts, so that comes first.
 async Task<(MainWindow w, BrowserTab t, CoreWebView2 core)> AgentPage(string who, JsonElement args)
 {
  var (w, t) = AgentTab(who, args);
  if (t.Dialog is { } d) throw new InvalidOperationException($"The page is waiting on a dialog ({DialogKind(d)}): \"{Clip(d.Args.Message, 200)}\". Answer it with handle_dialog first.");
  var core = await Core(w, t);
  // Agents work in background tabs, which never have focus; editors like Notion ignore typing without it.
  await core.CallDevToolsProtocolMethodAsync("Emulation.setFocusEmulationEnabled", "{\"enabled\":true}");
  return (w, t, core);
 }
 static BrowserTab? FindTab(string id) => Windows.Where(w => !w.closing).SelectMany(w => w.tabs).FirstOrDefault(t => t.Id == id);
 static string Clip(string s, int n) => s.Length > n ? s[..(n - 1)] + "…" : s;
 static readonly Dictionary<string, string> agentTabs = []; // run key -> the tab it is working in
 static void Claim(string who, MainWindow w, BrowserTab t)
 {
  var shown = w.Shown;
  agentTabs[who] = t.Id; t.LastActive = DateTime.UtcNow; // in use: memory saver leaves it awake
  if (t.AgentKey != who) { t.Agent = Me(who).Name; t.AgentKey = who; w.ShellPublish(); }
  if (w.Shown != shown) { w.ShowPage(); w.ShellPublish(); } // a chat shows the page its AI just moved to
 }
 /// The agent's work is done: its icon leaves the user's own tabs. Tabs it opened stay in the AI group.
 internal static void ReleaseAgentTabs(string key)
 {
  agentTabs.Remove(key);
  foreach (var w in Windows) { bool changed = false; foreach (var t in w.tabs.Where(t => t.AgentKey == key && !t.AgentGroup)) { t.Agent = t.AgentKey = null; changed = true; } if (changed) w.ShellPublish(); }
 }
 /// The window for a chat run's pages: one showing the chat, else one with the chat's tab, else the last used.
 static MainWindow? ChatRunner(string who) => runs.TryGetValue(who, out var run)
  ? run.Chat.Ephemeral ? OwnerOf(run.Chat) : Windows.FirstOrDefault(w => !w.closing && w.Showing(run.Chat)) ?? Windows.FirstOrDefault(w => !w.closing && w.tabs.Any(t => t.ChatId == run.Chat.Id)) ?? Home : null;
 // Background (the default for Still's own chat): the page belongs to the chat and shows only beside it, never in the
 // user's tab strip. Otherwise Still's chat opens it as the user's own tab, beside the chat, and other AI apps open it
 // next to the other AI tabs. An AI app's background tabs belong to it ("app:" + who) and show in the running tasks.
 const int AgentTabCap = 6; // tabs one chat (or one outside AI) may have open at once
 internal const string AppPages = "app:";
 async Task<BrowserTab> OpenAgentTab(string who, string url, bool background)
 {
  string? chat = runs.TryGetValue(who, out var run) ? who : null;
  if (Windows.SelectMany(w => w.tabs).Count(t => !t.Closed && (chat != null ? (t.RunChat ?? t.InChat) == chat : t.AgentGroup && t.AgentKey == who || t.InChat == AppPages + who)) >= AgentTabCap)
   throw new InvalidOperationException($"You already have {AgentTabCap} tabs open. Reuse one with navigate, or close one with close_tab first.");
  // An incognito chat's pages are private tabs in its own window: the private engine profile, no history, no saved
  // passwords or cookies. No other agent opens a tab in an incognito window.
  bool priv = run?.Chat.Ephemeral == true;
  if (priv ? OwnerOf(run!.Chat) != this : incognito) throw new InvalidOperationException(priv ? "The incognito window closed." : "Agents don't open tabs in an incognito window.");
  var tab = new BrowserTab { Url = url, Title = Host(url), Agent = Me(who).Name, AgentKey = who, AgentGroup = chat == null && !background, RunChat = background ? null : chat, InChat = background ? chat ?? AppPages + who : null, Private = priv, Engine = !priv && OnCompanion(who) ? CompanionEngine : null };
  if (background) tabs.Add(tab);
  else if (chat != null) tabs.Insert(active != null && tabs.IndexOf(active) is >= 0 and var at ? at + 1 : tabs.Count, tab);
  else {
   int last = tabs.FindLastIndex(t => t.AgentGroup);
   tabs.Insert(last >= 0 ? last + 1 : tabs.Count, tab);
   if (active == null || active.Url.Length == 0 && active.ChatId == null && !active.Pinned && tabs.Count == 2) await SelectTab(tab); // nothing to keep the user on
  }
  Claim(who, this, tab); ShellPublish(); SaveLater();
  await EnsureView(tab);
  if (background) { if (chat != null && active?.ChatId == chat) await SelectTab(tab); } // the chat in view splits to show it
  else if (chat != null && (Showing(run!.Chat) || active?.RunChat == chat)) { if (active?.ChatId == chat) aiOpen = true; await SelectTab(tab); }
  return tab;
 }
 static async Task<CoreWebView2> Core(MainWindow w, BrowserTab t)
 {
  if (t.View?.CoreWebView2 == null) await w.EnsureView(t);
  if (t.View?.CoreWebView2 is { IsSuspended: true } sleeping) { sleeping.Resume(); t.LastActive = DateTime.UtcNow; } // memory saver put it to sleep between steps
  return t.View?.CoreWebView2 ?? throw new InvalidOperationException("The tab couldn't be loaded.");
 }
 static async Task WaitLoaded(BrowserTab t, int ms = 15000)
 {
  var until = DateTime.UtcNow.AddMilliseconds(ms);
  await Task.Delay(250);
  while (t.Loading && DateTime.UtcNow < until) await Task.Delay(100);
 }
 /// What an agent may open: web pages, and files inside its companion's working folder (a builder tests what it made there).
 internal const string SampleHost = "sample.still.internal"; // Shell/sample, mapped into every tab
 static string WebUrl(string input, string engine, string folder = "")
 {
  var url = ResolveAddress(input, engine);
  if (Uri.TryCreate(url, UriKind.Absolute, out var u) && u.IsFile && folder.Length > 0 && Path.GetFullPath(u.LocalPath).StartsWith(Path.TrimEndingDirectorySeparator(Path.GetFullPath(folder)) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) return u.AbsoluteUri;
  if (u == null || u.Scheme is not ("http" or "https")) throw new InvalidOperationException("Agents can only open http and https pages" + (folder.Length > 0 ? ", and files in your working folder." : "."));
  return url;
 }
 string WorkFolder(string who) => Companions.FirstOrDefault(c => c.Id == runs.GetValueOrDefault(who)?.Chat.Companion)?.Folder ?? "";
 // ---- The permission layer ----
 // Every call is read, navigate, interact or sensitive: buying, sending, deleting, a form that posts, a password or
 // payment field, or anything on a site the user marked sensitive. Settings say, per site, action and companion,
 // whether it runs, asks once in each chat, or asks every time. A sensitive step allowed without asking still counts
 // down 8 seconds in the chat first. Outside AI apps keep today's behavior: allowed unless a rule for everyone or a
 // sensitive site says to ask, and then they ask in the bar at the top. Null: go ahead; otherwise the refusal for the AI.
 static readonly string[] PermissionActions = ["read", "navigate", "interact", "sensitive"];
 static string DefaultPermission(string action) => action switch { "interact" => "chat", "sensitive" => "ask", _ => "always" };
 static bool OnSite(string rule, string site) => rule.Length > 0 && (site == rule || site.EndsWith("." + rule, StringComparison.Ordinal));
 static string SiteOf(string input) => (input = input.Trim().ToLowerInvariant()).Length == 0 ? "" : Host(input.Contains("://") ? input : "https://" + input);
 static readonly HashSet<string> sessionGrants = []; // outside apps: "who action site" allowed until Still closes
 /// The rule that applies, most specific first: this companion on this site, this companion anywhere, everyone on this site, everyone anywhere.
 string? PermissionMode(string companion, string site, string action)
 {
  var rules = Prefs.Permissions.Where(p => p.Action == action).ToList();
  var rule = (companion.Length > 0 ? rules.FirstOrDefault(p => p.Companion == companion && OnSite(p.Site, site)) ?? rules.FirstOrDefault(p => p.Companion == companion && p.Site.Length == 0) : null)
   ?? rules.FirstOrDefault(p => p.Companion.Length == 0 && OnSite(p.Site, site)) ?? rules.FirstOrDefault(p => p.Companion.Length == 0 && p.Site.Length == 0);
  return rule?.Mode;
 }
 void SetPermission(string site, string action, string companion, string mode)
 {
  Prefs.Permissions.RemoveAll(p => p.Site == site && p.Action == action && p.Companion == companion);
  if (mode is "always" or "chat" or "ask") Prefs.Permissions.Add(new() { Site = site, Action = action, Companion = companion, Mode = mode });
  SaveLater();
 }
 async Task<string?> Gate(string who, string tool, JsonElement args, bool quick)
 {
  string action = tool switch {
   "read_page" or "find" or "screenshot" or "wait_for" or "web_search" or "read_url" => "read",
   "open_tab" or "navigate" or "go_back" or "go_forward" or "reload" or "switch_tab" or "close_tab" => "navigate",
   "click" or "type" or "press_key" or "scroll" or "handle_dialog" => "interact",
   _ => "" }; // list_tabs shows no page; ask_user and save_file stay in Still; upload_file asks every time on its own
  if (action.Length == 0) return null;
  string site, what, why = "";
  try {
   if (tool is "open_tab" or "navigate") { site = Host(WebUrl(S(args, "url"), Prefs.SearchEngine, WorkFolder(who))); what = "Open " + site; }
   else if (tool == "read_url") { site = Host(WebUrl(S(args, "url"), Prefs.SearchEngine)); what = "Read " + site; }
   else if (tool == "web_search") { site = Host(SearchUrl("x")); what = "Search for “" + Clip(S(args, "query"), 60) + "”"; }
   else {
    site = Host(AgentTab(who, args).tab.Url);
    what = tool switch { "scroll" => "Scroll the page", "press_key" => "Press " + S(args, "key"), "handle_dialog" => "Answer the page's dialog", "go_back" => "Go back",
     "go_forward" => "Go forward", "reload" => "Reload the page", "close_tab" => "Close a tab", "switch_tab" => "Switch tabs", _ => "Read the page" };
    if (tool is "click" or "type" or "press_key") {
     var look = await Js((await AgentPage(who, args)).core, SensitiveJs, new { tool, id = Id(args), selector = S(args, "selector"), text = S(args, "text"), key = S(args, "key"), submit = B(args, "submit") });
     string label = Str(look, "label"); why = Str(look, "why");
     // AIs never type a password: they wait while the user signs in.
     if (look.GetProperty("password").GetBoolean() && !(tool == "press_key" && S(args, "key") is "Tab" or "Escape" or "Esc") && tool != "click") {
      var (w, t) = AgentTab(who, args); await AskToSignIn(who, w, t, site);
      return Fail(SigningIn(site));
     }
     if (tool == "click") what = "Click “" + label + "”";
     else if (tool == "type") what = look.GetProperty("secret").GetBoolean() || S(args, "text").Length == 0 ? "Type into “" + label + "”" : "Type “" + Clip(S(args, "text"), 60) + "” into “" + label + "”";
    }
   }
  } catch (InvalidOperationException) { return null; } // no page or no such element: the tool itself says what's wrong
  bool marked = Prefs.SensitiveSites.Any(s => OnSite(s, site));
  if (action == "interact" && (why.Length > 0 || marked)) { action = "sensitive"; if (why.Length == 0) why = "You marked " + site + " as sensitive."; }
  var run = runs.GetValueOrDefault(who);
  // A child task (a teammate asked it) acts only where everyone up the chain may, with the approvals given in the
  // user's chat. Outside apps keep today's behavior: allowed unless you set a rule or marked the site sensitive.
  var up = run == null ? default : ExchangeOf(run.Chat);
  string mode = run != null ? Delegation.Strictest(up.Chain.Select(c => PermissionMode(c, site, action) ?? DefaultPermission(action))) : PermissionMode("", site, action) ?? (marked ? "ask" : "always"), key = action + " " + site;
  bool granted = mode == "always" || mode == "chat" && (run != null ? up.Root.Allowed.Contains(key) : sessionGrants.Contains(who + " " + key));
  if (action == "sensitive" && run?.Recheck == true) granted = false; // picked up after one that may not have finished: the user decides again
  if (run == null) {
   if (granted) return null;
   string ask = char.ToLowerInvariant(what[0]) + what[1..] + " on " + site;
   switch (await AskUser(who, ask, quick)) {
    case false: return Fail("The user said no to this. Don't try it again unless they ask.");
    case null: return NeedsConfirm(who, ask, $"Waiting for the user to allow it: Still shows Allow and Block at the top of its window. Tell the user, then call {tool} again.");
   }
   if (mode == "chat") sessionGrants.Add(who + " " + key);
   return null;
  }
  if (granted && action != "sensitive") { if (action == "interact") Audit(run.Chat, what, site, mode == "always" ? "Allowed by your settings" : "Allowed in this chat"); return null; }
  string answer = await Approve(run, what, site, action, why, countdown: granted);
  if (answer == "always" && run.Chat.Ephemeral) answer = "chat"; // an incognito chat writes no site rules
  if (answer == "always") SetPermission(site, action, "", "always");
  if (answer == "chat" && !up.Root.Allowed.Contains(key)) up.Root.Allowed.Add(key);
  Audit(run.Chat, what, site, answer switch {
   "always" => "You always allow this on " + site, "chat" => "You allowed it in this chat", "once" => "You allowed it once",
   "go" => "Went ahead after 8 seconds", "now" => "You let it go ahead", "cancel" => "You cancelled it", "stop" => "Stopped",
   "timeout" => "No answer in 10 minutes", _ => "You said no" });
  PublishAiEverywhere();
  if (answer is "always" or "chat" or "once" or "go" or "now" && action == "sensitive") {
   if (run.Recheck) { run.Recheck = false; foreach (var s in run.Task.Sensitive.Where(s => s.Outcome == null)) s.Outcome = "rechecked"; }
   run.Intent = new() { What = what, Site = site };
  }
  return answer switch {
   "always" or "chat" or "once" or "go" or "now" => null,
   "cancel" => Fail("The user cancelled this before it ran. Don't try it again unless they ask."),
   "stop" => Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message."),
   "timeout" => Fail("The user didn't answer within 10 minutes. Stop here and ask them in your reply."),
   _ => Fail("The user said no to this. Don't try it again; if you need it, ask them in your reply.") };
 }
 // A card in the chat's tray; for a sensitive step allowed without asking, 8 seconds to cancel it instead.
 static async Task<string> Approve(ChatRun run, string what, string site, string action, string why, bool countdown)
 {
  var card = new Approval(Convert.ToHexString(RandomNumberGenerator.GetBytes(4)).ToLowerInvariant(), what, site, action, why, countdown ? DateTime.UtcNow.AddSeconds(8) : null, new(TaskCreationOptions.RunContinuationsAsynchronously));
  run.Approvals.Add(card); PublishAiEverywhere();
  if (!countdown) TaskState(run, "waiting", "approval", what + " on " + site);
  var wait = Task.Delay(countdown ? TimeSpan.FromSeconds(8) : TimeSpan.FromMinutes(10));
  string answer = await Task.WhenAny(card.Answer.Task, wait) == wait ? (countdown ? "go" : "timeout") : await card.Answer.Task;
  run.Approvals.Remove(card); PublishAiEverywhere();
  if (!countdown && !run.Approvals.Any(a => a.Until == null)) TaskState(run, "running");
  return answer;
 }
 static void Audit(AiChat chat, string what, string site, string result)
 {
  chat.Audit.Add(new() { What = what, Site = site, Result = result });
  if (chat.Audit.Count > 300) chat.Audit.RemoveRange(0, chat.Audit.Count - 300);
 }
 static void Did(string who, string action)
 {
  var me = Me(who);
  me.Action = action.Length > 90 ? action[..90] + "…" : action;
  me.Recent.Add(me.Action); if (me.Recent.Count > 5) me.Recent.RemoveAt(0);
 }
 /// What a step works on, for the pill: the search, the teammate (with what it's about) or the site; never typed text.
 static string TargetOf(string who, string tool, JsonElement args)
 {
  if (tool == "web_search") return Clip(S(args, "query").Trim().ReplaceLineEndings(" "), 60);
  if (tool is "ask_companion" or "tell_companion") {
   string name = S(args, "name").Trim().TrimStart('@'), title = S(args, "title").Trim().TrimEnd('.').ReplaceLineEndings(" ");
   if (title.Length > 1 && char.IsLower(title[1])) title = char.ToLowerInvariant(title[0]) + title[1..]; // "Pricing research" reads as "about pricing research"; "SEO audit" stays
   return name.Length == 0 ? "" : title.Length == 0 ? name : name + " about " + Clip(title, 50);
  }
  if (tool is "run_plugin_action" or "get_plugin_tools" or "find_plugins" or "list_connected_plugins") return "";
  string url = S(args, "url");
  if (url.Length == 0 && agentTabs.TryGetValue(who, out var id)) url = FindTab(id)?.Url ?? "";
  return Uri.TryCreate(url, UriKind.Absolute, out var u) && u.Scheme is "http" or "https" ? Host(url) : "";
 }
 /// The AI's cursor: an arrow with its name, in its companion's color, glides to where it's about to click.
 /// It's drawn inside the page (the page's own window covers Still's), clicks pass through it, and it fades on its own.
 static async Task Pointer(string who, BrowserTab t, CoreWebView2 core, double x, double y)
 {
  var me = Me(who);
  try { await Js(core, CursorJs, new { x, y, name = me.Label, color = me.Color }); } catch (InvalidOperationException) { return; }
  if (Windows.Any(w => !w.closing && w.Shown == t)) await Task.Delay(450); // let the user see where it's going first
 }
 // Built with DOM calls and a constructed style sheet, so pages with a strict CSP or Trusted Types still show it.
 const string CursorJs = """
  const key = Symbol.for('still.cursor');
  let host = window[key];
  if (!host || !host.isConnected) {
   host = window[key] = document.createElement('still-cursor');
   host.style.cssText = 'all:initial;position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none';
   const root = host.attachShadow({ mode: 'closed' }), sheet = new CSSStyleSheet();
   sheet.replaceSync(`.c{position:fixed;left:0;top:0;opacity:0;transition:transform .45s cubic-bezier(.3,1.25,.4,1),opacity .25s;filter:drop-shadow(0 2px 3px #0005)}
    .c.on{opacity:1}.c.gone{opacity:0;transition:opacity .8s}svg{display:block;overflow:visible}
    .tag{position:absolute;left:15px;top:19px;padding:2px 8px;border-radius:999px;color:#fff;font:600 12px/18px system-ui,sans-serif;white-space:nowrap}
    .r{position:absolute;left:-12px;top:-12px;width:24px;height:24px;border-radius:50%;border:2px solid;opacity:0}.r.on{animation:r .55s ease-out}
    @keyframes r{from{transform:scale(.3);opacity:.95}to{transform:scale(1.6);opacity:0}}`);
   root.adoptedStyleSheets = [sheet];
   const c = document.createElement('div'); c.className = 'c';
   const r = document.createElement('div'); r.className = 'r';
   const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('width', '20'); svg.setAttribute('height', '22');
   const path = document.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', 'M1 1l17 8.5-7.4 2.1L7.2 20z');
   path.setAttribute('stroke', '#fff'); path.setAttribute('stroke-width', '2'); path.setAttribute('stroke-linejoin', 'round');
   const tag = document.createElement('span'); tag.className = 'tag';
   svg.append(path); c.append(r, svg, tag); root.append(c);
   host[key] = { c, r, path, tag };
   c.style.transform = `translate(${innerWidth / 2}px,${innerHeight * .6}px)`; // first time: glide in from the middle
   (document.body || document.documentElement).append(host);
   c.getBoundingClientRect();
  }
  const { c, r, path, tag } = host[key];
  path.setAttribute('fill', o.color); tag.style.background = o.color; r.style.borderColor = o.color; tag.textContent = o.name;
  c.classList.remove('gone'); c.classList.add('on');
  c.style.transform = `translate(${o.x - 1}px,${o.y - 1}px)`;
  clearTimeout(host.ripple); host.ripple = setTimeout(() => { r.classList.remove('on'); r.getBoundingClientRect(); r.classList.add('on'); }, 450);
  clearTimeout(host.fade); host.fade = setTimeout(() => c.classList.add('gone'), 6000);
  return true;
  """;
 /// What an action led to: where the agent is now, and the new tab it's in if the action opened one.
 static object Outcome(string who, BrowserTab t, string tabBefore, string done)
 {
  var opened = agentTabs.GetValueOrDefault(who) is { } id && id != tabBefore ? FindTab(id) : null;
  var now = opened ?? t;
  return new { done, url = now.Url, title = now.Title, tabId = opened?.Id, note = opened != null ? "This opened a new tab; you're working in it now." : null };
 }
 static readonly Dictionary<string, (string Code, int Vk, string Text)> Keys = new(StringComparer.OrdinalIgnoreCase) {
  ["Enter"] = ("Enter", 13, "\r"), ["Tab"] = ("Tab", 9, ""), ["Escape"] = ("Escape", 27, ""), ["Esc"] = ("Escape", 27, ""), ["Backspace"] = ("Backspace", 8, ""), ["Delete"] = ("Delete", 46, ""),
  ["ArrowUp"] = ("ArrowUp", 38, ""), ["ArrowDown"] = ("ArrowDown", 40, ""), ["ArrowLeft"] = ("ArrowLeft", 37, ""), ["ArrowRight"] = ("ArrowRight", 39, ""),
  ["Home"] = ("Home", 36, ""), ["End"] = ("End", 35, ""), ["PageUp"] = ("PageUp", 33, ""), ["PageDown"] = ("PageDown", 34, ""), ["Space"] = ("Space", 32, " "),
 };
 static async Task MouseClick(CoreWebView2 core, double x, double y)
 {
  foreach (var type in new[] { "mouseMoved", "mousePressed", "mouseReleased" })
   await core.CallDevToolsProtocolMethodAsync("Input.dispatchMouseEvent", JsonSerializer.Serialize(new { type, x, y, button = type == "mouseMoved" ? "none" : "left", clickCount = type == "mouseMoved" ? 0 : 1 }));
 }
 /// Types text one key at a time; a new line is Enter where the field has lines.
 static async Task TypeKeys(CoreWebView2 core, string text, bool multiline, Worker me)
 {
  foreach (var r in text.ReplaceLineEndings("\n").EnumerateRunes()) {
   string s = r.ToString();
   if (me.Paused) return; // the user took over mid-word
   if (s == "\n") { if (multiline) await PressKey(core, "Enter"); continue; }
   await core.CallDevToolsProtocolMethodAsync("Input.dispatchKeyEvent", JsonSerializer.Serialize(new { type = "keyDown", key = s, text = s, unmodifiedText = s }));
   await core.CallDevToolsProtocolMethodAsync("Input.dispatchKeyEvent", JsonSerializer.Serialize(new { type = "keyUp", key = s }));
  }
 }
 /// Presses a key like a person would, e.g. "Enter", "Escape", "a", "Control+A", "Shift+Tab".
 static async Task PressKey(CoreWebView2 core, string combo)
 {
  var parts = combo.Split('+', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
  if (parts.Length == 0) throw new ArgumentException("Pass a key, like Enter or Control+A.");
  int modifiers = 0;
  foreach (var m in parts[..^1]) modifiers |= m.ToLowerInvariant() switch { "alt" => 1, "ctrl" or "control" => 2, "meta" or "cmd" or "win" => 4, "shift" => 8, _ => throw new ArgumentException("Unknown modifier: " + m) };
  string key = parts[^1];
  (string code, int vk, string text) = Keys.TryGetValue(key, out var k) ? k
   : key.Length == 1 && char.IsLetterOrDigit(key[0]) ? ((char.IsLetter(key[0]) ? "Key" : "Digit") + char.ToUpperInvariant(key[0]), (int)char.ToUpperInvariant(key[0]), key)
   : key.Length == 1 ? ("", 0, key) : throw new ArgumentException("Unknown key: " + key);
  if ((modifiers & 3) != 0) text = ""; // Ctrl/Alt shortcuts type nothing
  string name = Keys.TryGetValue(key, out var named) ? named.Code : (modifiers & 8) != 0 ? key.ToUpperInvariant() : key;
  await core.CallDevToolsProtocolMethodAsync("Input.dispatchKeyEvent", JsonSerializer.Serialize(new { type = text.Length > 0 ? "keyDown" : "rawKeyDown", modifiers, key = name, code, windowsVirtualKeyCode = vk, text, unmodifiedText = text }));
  await core.CallDevToolsProtocolMethodAsync("Input.dispatchKeyEvent", JsonSerializer.Serialize(new { type = "keyUp", modifiers, key = name, code, windowsVirtualKeyCode = vk }));
 }

 async Task<string> RunTool(string who, string tool, JsonElement args, bool quick)
 {
  switch (tool) {
   case "ask_user": return await AskInChat(who, args);
   case "offer_routine": return await OfferRoutine(who, args);
   case "ask_companion" or "tell_companion" or "list_companions": return await Exchange(who, tool, args);
   case "list_connected_plugins" or "find_plugins" or "get_plugin_tools" or "run_plugin_action": return await PluginTool(who, tool, args);
   case "remember" or "recall" or "forget" or "update_knowledge" or "read_knowledge" or "open_memory_source": return Remembering(who, tool, args);
   case "load_skill": {
    // Only a skill the companion has; never matched by keyword. The step shows only when one loads.
    var run = runs.GetValueOrDefault(who);
    var mine = run == null ? null : Companions.FirstOrDefault(c => c.Id == run.Chat.Companion);
    string id = S(args, "id").Trim().TrimStart('/');
    if (mine == null || !mine.Skills.Contains(id) || Skill.All.FirstOrDefault(k => k.Id == id) is not { } skill)
     return Fail($"You don't have a skill with the id \"{id}\". Use an id from your skills listed at the start of the chat, or carry on without one.");
    Step(run!.Chat, "Used skill " + skill.Name); PublishAiEverywhere();
    return Reply(new { skill = skill.Name, instructions = skill.Body });
   }
   case "save_file": {
    if (Incognito(who)) return Fail(KeepsNothing);
    string name = string.Concat(Path.GetFileName(S(args, "name").Trim()).Split(Path.GetInvalidFileNameChars())).Trim(), content = S(args, "content");
    string ext = Path.GetExtension(name).ToLowerInvariant();
    if (ext is not (".csv" or ".tsv" or ".md" or ".json" or ".txt") || name.Length is < 5 or > 120) return Fail("Name the file with a .csv, .md, .json or .txt ending, like laptops.csv.");
    if (content.Length > 5_000_000) return Fail("That's too big: keep a file under 5 MB.");
    var run = runs.GetValueOrDefault(who);
    string folder = Path.Combine(LibraryFolder, run?.Chat.Id ?? string.Concat(who.Split(Path.GetInvalidFileNameChars())));
    Directory.CreateDirectory(folder);
    string file = Path.Combine(folder, name); string Rel() => Path.GetRelativePath(LibraryFolder, file).Replace('\\', '/');
    bool again = run?.Chat.Messages.Any(m => m.Role == "file" && m.Text == Rel()) == true; // this chat saved it before: a fix replaces it
    if (!again) for (int n = 2; File.Exists(file); n++) file = Path.Combine(folder, Path.GetFileNameWithoutExtension(name) + $" ({n})" + ext);
    await File.WriteAllTextAsync(file, content, new UTF8Encoding(ext == ".csv")); // a BOM lets Excel read a CSV's accents
    library = null;
    if (!again) run?.Chat.Messages.Add(new() { Role = "file", Text = Rel() });
    Did(who, (again ? "Updated " : "Saved ") + Path.GetFileName(file)); PublishAiEverywhere();
    return Reply(new { done = $"{(again ? "Replaced" : "Saved")} {Path.GetFileName(file)} in the user's Library. It shows in the chat as a card they can open, so don't paste its contents in your reply." });
   }
   case "list_tabs":
    return Reply(Windows.Where(w => !w.closing).SelectMany((w, wi) => w.tabs.Where(t => Incognito(who) ? (t.InChat ?? t.RunChat) == who : !t.Private).Select(t => new { tabId = t.Id, title = t.Title, url = t.Url, active = t == w.active ? true : (bool?)null, yours = agentTabs.GetValueOrDefault(who) == t.Id ? true : (bool?)null, window = wi + 1 })));
   case "web_search": return await WebSearch(who, args);
   case "read_url": return await ReadUrl(who, args);
   case "read_attachment": return ReadAttachment(who, S(args, "id"), (int)Math.Max(0, N(args, "offset", 0)));
   case "open_tab": {
    bool background = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("background", out var bg) && bg.ValueKind is JsonValueKind.True or JsonValueKind.False ? bg.GetBoolean() : runs.ContainsKey(who);
    var tab = await (ChatRunner(who) ?? this).OpenAgentTab(who, WebUrl(S(args, "url"), Prefs.SearchEngine, WorkFolder(who)), background); await WaitLoaded(tab);
    Did(who, "Opened " + Host(tab.Url)); return Reply(new { tabId = tab.Id, title = tab.Title, url = tab.Url });
   }
   case "navigate": {
    var (w, t, core) = await AgentPage(who, args); core.Navigate(WebUrl(S(args, "url"), Prefs.SearchEngine, WorkFolder(who))); await WaitLoaded(t);
    Did(who, "Went to " + Host(t.Url)); return Reply(new { tabId = t.Id, title = t.Title, url = t.Url });
   }
   case "switch_tab": {
    var (w, t) = AgentTab(who, args);
    if (B(args, "show")) { await w.SelectTab(t); w.Activate(); }
    Did(who, "Switched to " + t.Title); return Reply(new { tabId = t.Id, title = t.Title, url = t.Url });
   }
   case "close_tab": { var (w, t) = AgentTab(who, args); await w.CloseTab(t, true); agentTabs.Remove(who); Did(who, "Closed a tab"); return Reply(new { done = "Closed the tab" }); }
   case "go_back": case "go_forward": case "reload": {
    var (w, t, core) = await AgentPage(who, args);
    if (tool == "go_back") { if (!core.CanGoBack) return Fail("There's no earlier page in this tab."); core.GoBack(); }
    else if (tool == "go_forward") { if (!core.CanGoForward) return Fail("There's no later page in this tab."); core.GoForward(); }
    else core.Reload();
    await WaitLoaded(t); Did(who, tool == "reload" ? "Reloaded the page" : tool == "go_back" ? "Went back" : "Went forward"); return Reply(new { url = t.Url, title = t.Title });
   }
   case "read_page": {
    var (w, t, core) = await AgentPage(who, args);
    var page = await Js(core, SnapshotJs, new { text = !(args.ValueKind == JsonValueKind.Object && args.TryGetProperty("text", out var tx) && (tx.ValueKind == JsonValueKind.False || tx.ValueKind == JsonValueKind.String && tx.GetString() == "false")), all = B(args, "all"), offset = (int)Math.Max(0, N(args, "offset", 0)) });
    string seen = RedactLogins(core.Source, page.GetString() ?? ""), site = Host(t.Url), back = Me(who) is { SignedIn: var done } && done.Site == site && DateTime.UtcNow - done.At < TimeSpan.FromMinutes(2) ? "signed in" : "";
    if (back.Length == 0 && await core.RunAsync("[...document.querySelectorAll('input[type=password]')].some(e=>e.getClientRects().length&&!e.disabled)") == "true") { await AskToSignIn(who, w, t, site); seen += "\n\n" + SigningIn(site); }
    Did(who, "Read " + Host(t.Url)); return Reply(new { text = seen });
   }
   case "find": {
    var (w, t, core) = await AgentPage(who, args);
    var found = await Js(core, FindJs, new { text = S(args, "text") });
    Did(who, "Looked for \"" + S(args, "text") + "\""); return Reply(new { text = RedactLogins(core.Source, found.GetString() ?? "") });
   }
   case "screenshot": {
    var (w, t, core) = await AgentPage(who, args);
    // A page only paints while it's on screen: show it for a moment, then give the user their tab back.
    var previous = w.active;
    if (t != previous) { await w.SelectTab(t); await Task.Delay(200); }
    using var ms = new MemoryStream();
    var prints = LoginPrints(core.Source); // fields showing a saved login are masked in the picture
    try { if (prints.Length > 0) await Js(core, MaskJs, new { prints, on = true }); await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, ms); }
    finally { if (prints.Length > 0) await Js(core, MaskJs, new { prints, on = false }); if (previous != null && previous != t && !previous.Closed && w.active == t) await w.SelectTab(previous); }
    Did(who, "Took a screenshot"); return Reply(new { image = Convert.ToBase64String(ms.ToArray()), mimeType = "image/png" });
   }
   case "click": {
    var (w, t, core) = await AgentPage(who, args);
    var hit = await Settled(t, core, () => Js(core, ClickJs, new { id = Id(args), selector = S(args, "selector"), text = S(args, "text") }));
    double x = hit.GetProperty("x").GetDouble(), y = hit.GetProperty("y").GetDouble();
    string label = Str(hit, "label"), before = agentTabs.GetValueOrDefault(who) ?? "";
    await Pointer(who, t, core, x, y);
    t.AgentActedAt = DateTime.UtcNow;
    await MouseClick(core, x, y);
    await WaitLoaded(t, 8000);
    // The chat's step only had the element's number from the AI's call ("Clicked element 7"): name what it was. The AI
    // may have sent more calls in the same breath, so it isn't always the last step.
    string numbered = "Clicked element " + (args.TryGetProperty("id", out var raw) ? raw.ValueKind == JsonValueKind.String ? raw.GetString() : raw.GetRawText() : "");
    if (label.Length > 0 && runs.GetValueOrDefault(who)?.Chat.Messages.LastOrDefault(m => m.Role == "tool" && m.Text == numbered) is { } step) step.Text = "Clicked “" + label + "”";
    Did(who, "Clicked '" + label + "'"); return Reply(Outcome(who, t, before, "Clicked \"" + label + "\""));
   }
   case "type": {
    var (w, t, core) = await AgentPage(who, args);
    string text = S(args, "text"), before = agentTabs.GetValueOrDefault(who) ?? "";
    if (text.Trim().Length >= 4) runs.GetValueOrDefault(who)?.Typed.Add(text.Trim());
    object Q(bool clicked) => new { id = Id(args), selector = S(args, "selector"), value = text, append = B(args, "append"), clicked };
    var focus = await Settled(t, core, () => Js(core, FocusJs, Q(false)));
    t.AgentActedAt = DateTime.UtcNow;
    if (Str(focus, "done") is { Length: > 0 } picked) { Did(who, picked); return Reply(new { done = picked }); }
    if (focus.TryGetProperty("at", out var at) && at.ValueKind == JsonValueKind.Object) {
     await Pointer(who, t, core, at.GetProperty("x").GetDouble(), at.GetProperty("y").GetDouble());
     await MouseClick(core, at.GetProperty("x").GetDouble(), at.GetProperty("y").GetDouble());
     focus = await Js(core, FocusJs, Q(true)); // the click moved the caret: put it back
    }
    else if (focus.TryGetProperty("near", out var near) && near.ValueKind == JsonValueKind.Object)
     await Pointer(who, t, core, near.GetProperty("x").GetDouble(), near.GetProperty("y").GetDouble());
    async Task<bool> Unchanged() => Str(await Js(core, SigJs, new { }), "sig") == Str(focus, "sig");
    if (text.Length > 0) {
     await core.CallDevToolsProtocolMethodAsync("Input.insertText", JsonSerializer.Serialize(new { text }));
     // Some editors ignore inserted text and only take key presses: type it key by key.
     if (text.Length <= 4000 && await Unchanged()) { await Js(core, FocusJs, Q(true)); await TypeKeys(core, text, focus.GetProperty("multiline").GetBoolean(), Me(who)); }
     if (await Unchanged()) return Fail("Typed, but \"" + Str(focus, "label") + "\" didn't change. Click it first, then type without an id, or use press_key.");
    }
    else if (!B(args, "append")) await PressKey(core, "Backspace");
    if (B(args, "submit")) await PressKey(core, "Enter");
    await WaitLoaded(t, B(args, "submit") ? 8000 : 0);
    string field = Str(focus, "label");
    Did(who, "Typed into " + field); return Reply(Outcome(who, t, before, (text.Length > 0 ? "Typed into \"" : "Cleared \"") + field + "\"" + (B(args, "submit") ? " and pressed Enter" : "")));
   }
   case "press_key": {
    var (w, t, core) = await AgentPage(who, args);
    string before = agentTabs.GetValueOrDefault(who) ?? "";
    t.AgentActedAt = DateTime.UtcNow;
    await PressKey(core, S(args, "key")); await WaitLoaded(t, 8000);
    Did(who, "Pressed " + S(args, "key")); return Reply(Outcome(who, t, before, "Pressed " + S(args, "key")));
   }
   case "scroll": {
    var (w, t, core) = await AgentPage(who, args);
    var r = await Js(core, ScrollJs, new { id = Id(args), selector = S(args, "selector"), direction = S(args, "direction"), amount = Math.Clamp(N(args, "amount", 0), 0, 20000) });
    Did(who, Str(r, "done")); return Reply(new { done = Str(r, "done"), at = Str(r, "at") is { Length: > 0 } at ? at : null });
   }
   case "wait_for": {
    var (w, t, core) = await AgentPage(who, args);
    var q = new { id = Id(args), selector = S(args, "selector"), text = S(args, "text"), gone = B(args, "gone") };
    if (q.id.Length + q.selector.Length + q.text.Length == 0) return Fail("Pass an id, selector or text to wait for.");
    var until = DateTime.UtcNow.AddMilliseconds(Math.Clamp(N(args, "timeoutMs", 10000), 100, 30000));
    while (true) {
     if ((await Js(core, WaitJs, q)).ValueKind == JsonValueKind.True) { Did(who, "Waited for the page"); return Reply(new { found = !q.gone, done = q.gone ? "It's gone" : "It's there", url = t.Url }); }
     if (DateTime.UtcNow >= until) return Reply(new { found = q.gone, done = q.gone ? "Still there after waiting" : "Didn't appear in time", url = t.Url });
     await Task.Delay(250);
    }
   }
   case "handle_dialog": {
    var (w, t) = AgentTab(who, args);
    if (t.Dialog is null) return Fail("No dialog is open in this tab.");
    bool accept = !(args.ValueKind == JsonValueKind.Object && args.TryGetProperty("accept", out var ac) && (ac.ValueKind == JsonValueKind.False || ac.ValueKind == JsonValueKind.String && ac.GetString() == "false"));
    string before = agentTabs.GetValueOrDefault(who) ?? "";
    w.AnswerPageDialog(t, accept, args.ValueKind == JsonValueKind.Object && args.TryGetProperty("text", out var tx) && tx.ValueKind == JsonValueKind.String ? tx.GetString() : null);
    await WaitLoaded(t, 8000);
    Did(who, accept ? "Accepted a dialog" : "Dismissed a dialog"); return Reply(Outcome(who, t, before, accept ? "Accepted the dialog" : "Dismissed the dialog"));
   }
   case "upload_file": {
    var (w, t, core) = await AgentPage(who, args);
    string[] files = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("paths", out var p)
     ? p.ValueKind == JsonValueKind.Array ? p.EnumerateArray().Select(x => x.ValueKind == JsonValueKind.String ? x.GetString() ?? "" : "").ToArray() : [p.ValueKind == JsonValueKind.String ? p.GetString() ?? "" : ""] : [];
    files = files.Where(f => f.Trim().Length > 0).Select(f => Path.GetFullPath(Environment.ExpandEnvironmentVariables(f.Trim().Trim('"')))).Distinct().Take(12).ToArray();
    if (files.Length == 0) return Fail("Pass paths: the full paths of the files to attach.");
    if (files.FirstOrDefault(f => !File.Exists(f)) is { } missing) return Fail("There's no file at " + missing);
    object input;
    if (Id(args).Length + S(args, "selector").Length > 0) {
     using var found = JsonDocument.Parse(await core.CallDevToolsProtocolMethodAsync("Runtime.evaluate", JsonSerializer.Serialize(new { expression = "((o)=>{" + PageJs + FileInputJs + "})(" + JsonSerializer.Serialize(new { id = Id(args), selector = S(args, "selector") }) + ")" })));
     var res = found.RootElement.GetProperty("result");
     if (found.RootElement.TryGetProperty("exceptionDetails", out _) || Str(res, "subtype") != "node" || !res.TryGetProperty("objectId", out var obj)) return Fail("That isn't a file upload field. Click the page's upload button instead, then call upload_file without an id.");
     input = new { files, objectId = obj.GetString() };
    } else if (t.AgentUpload is UploadRequest picker && picker.Core == core) input = new { files = picker.Multiple ? files : files[..1], backendNodeId = picker.Node };
    else return Fail("No file picker is open. Click the page's upload button first (Still catches the picker for you), or pass the id of a file input.");
    string names = string.Join(", ", files.Select(Path.GetFileName));
    string ask = "upload " + Clip(names, 120) + " to " + Host(t.Url);
    switch (await AskUser(who, ask, quick)) {
     case false: return Fail("The user didn't allow this upload. Don't try again unless they ask.");
     case null: return NeedsConfirm(who, ask, "Waiting for the user to allow the upload: Still shows Allow and Block at the top of its window. Tell the user, then call upload_file again.");
    }
    await core.CallDevToolsProtocolMethodAsync("DOM.setFileInputFiles", JsonSerializer.Serialize(input));
    t.AgentUpload = null;
    Did(who, "Attached " + names); return Reply(new { done = "Attached " + names });
   }
   default: return Fail("Unknown tool: " + tool);
  }
 }
}
