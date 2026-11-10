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
 // Ends an agent's running calls early with this reply: a dialog or file picker opened in its tab, or the user pressed Stop.
 static readonly Dictionary<string, List<TaskCompletionSource<string>>> agentInterrupts = new(StringComparer.OrdinalIgnoreCase);
 static void EndCalls(string who, string reply) { if (agentInterrupts.Remove(who, out var running)) foreach (var call in running) call.TrySetResult(reply); }
 /// One tool call on its way through.
 sealed class AgentStep
 {
  public AiSensitive? Intent; // the sensitive step about to run
  public string TabId = "", Site = "", Why = "", Print = ""; // what the gate saw: an approval is for exactly this
  public bool Tab; // it's about a page in a tab, not a new one
  public bool Again; // the page changed since the user was asked: the next card says so
  public bool Abandoned; // Stop, Take over or the time limit already answered the AI: nothing more of this call may reach the page
  public bool Allowed; // the user said yes to this one on a card
  public bool SignedOut; // read_url read it signed out
  public string Goes = ""; // the site open_tab, navigate or read_url is going to
  public void Live() { if (Abandoned) throw new InvalidOperationException("Stopped."); }
 }
 // These act on a page, so they take its turn: one at a time, whoever is asking. Reads run alongside, and handle_dialog
 // never waits: the step holding the turn may be stuck behind that very dialog.
 static bool TakesTurn(string tool) => tool is "click" or "type" or "press_key" or "scroll" or "navigate" or "go_back" or "go_forward" or "reload" or "close_tab" or "upload_file";
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
    await writer.WriteLineAsync(await Application.Current.Dispatcher.InvokeAsync(async () => Home.RedactReply(await Home.HandleAgent(line))).Task.Unwrap());
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
   bool elicit = root.TryGetProperty("elicit", out var el) && el.ValueKind == JsonValueKind.True, quick = elicit || UserAway();
   if (blockedAgents.Contains(client)) return Fail("The user blocked this agent in Still for this session.");
   if (stoppedAgents.TryGetValue(who, out var until) && DateTime.UtcNow < until) return Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message.");
   if (Prefs.ApprovedAgents.Any(a => McpServer.AgentName(a).Equals(client, StringComparison.OrdinalIgnoreCase))) approvedAgents.Add(client); // approved once = remembered across restarts/updates
   if (!approvedAgents.Contains(client)) switch (await AskUser(client, "", quick)) {
    case false: return Fail("The user blocked this agent in Still for this session.");
    case null: return NeedsConfirm(client, "", "Waiting for the user to let you in: Still shows a bar with Allow and Block at the top of its window. Tell the user to click Allow, then call the tool again.", elicit);
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
   var interrupt = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
   if (!agentInterrupts.TryGetValue(who, out var calling)) agentInterrupts[who] = calling = [];
   calling.Add(interrupt);
   var step = new AgentStep();
   SemaphoreSlim? turn = null;
   try {
    int limit = tool switch { "ask_user" or "run_plugin_action" or "ask_companion" => 660_000, "wait_for" => (int)Math.Clamp(N(args, "timeoutMs", 10000), 100, 30000) + 5000, "upload_file" => 60000, _ => App.IsTemp ? 80000 : 30000 };
    // An approval is for what the card showed. The page can change while it waits, so once it's this call's turn Still looks
    // again, and if it's not the same any more it goes back to asking. The same goes for what happens during the step itself.
    for (int tries = 0; ; tries++) {
     // The permission layer: it runs, asks in the chat, or counts down first. Take over and Stop end the wait too.
     var gate = Gate(who, tool, args, quick, step, elicit);
     string? refused = await Task.WhenAny(gate, interrupt.Task) == gate ? await gate : await interrupt.Task;
     if (!gate.IsCompleted) foreach (var card in runs.GetValueOrDefault(who)?.Approvals.ToList() ?? []) card.Answer.TrySetResult("stop");
     if (refused != null) return refused;
     // An AI may send several calls in one breath. Run side by side their clicks would mix, and each would read the other's
     // effects as its own, so they wait their turn. Stop or Take over while waiting: the call ends here and never acts.
     if (TakesTurn(tool)) {
      var wanted = AgentTab(who, args).tab.Turn;
      var wait = wanted.WaitAsync();
      var won = await Task.WhenAny(wait, interrupt.Task, Task.Delay(limit));
      if (won != wait) {
       _ = wait.ContinueWith(_ => wanted.Release());
       return won == interrupt.Task ? await interrupt.Task : Fail($"Another step on this page didn't finish within {limit / 1000} s, so {tool} wasn't done. Call read_page to see where it is.");
      }
      turn = wanted;
     }
     var same = StillTheSame(who, tool, args, step);
     var looked = await Task.WhenAny(same, interrupt.Task, Task.Delay(limit));
     if (looked == interrupt.Task) return await interrupt.Task;
     if (looked != same) return Fail($"Still couldn't read the page within {limit / 1000} s, so {tool} wasn't done. Call read_page to see where it is.");
     if (await same) {
      var going = runs.GetValueOrDefault(who);
      if (going != null && step.Intent is { } intent) { going.Task.Sensitive.Add(intent); if (going.Task.Sensitive.Count > 40) going.Task.Sensitive.RemoveAt(0); SaveTask(going); }
      me.Tool = tool; me.Target = TargetOf(who, tool, args); PublishAll(); PublishAiSoon();
      string result;
      try {
       var working = RunTool(who, tool, args, quick, step);
       var first = await Task.WhenAny(working, interrupt.Task, Task.Delay(limit));
       step.Abandoned = first != working;
       try {
        result = first == working ? await working : first == interrupt.Task ? await interrupt.Task
         : Fail($"{tool} didn't finish within {limit / 1000} s, so Still stopped waiting. The page may be slow or stuck: call read_page to see where it is.");
       } catch (PageChanged) when (tries < 2) {
        if (step.Intent is { } none) none.Outcome = "failed"; // nothing was sent
        goto changed;
       }
       if (going != null) {
        if (step.Intent is { } ran && first == working && !result.Contains("\"unverified\":true", StringComparison.Ordinal)) ran.Outcome = result.StartsWith("{\"ok\":false", StringComparison.Ordinal) ? "failed" : "done"; // cut off, or no sign it worked: uncertain
        Exposed(going, tool, step);
        Checkpoint(going, tool, result);
       }
       if (tool is "ask_companion" or "tell_companion" && me.Target.Length > 0 && !result.StartsWith("{\"ok\":false", StringComparison.Ordinal)) Did(who, (tool == "ask_companion" ? "Asked " : "Handed work to ") + me.Target);
      } finally { me.Tool = ""; me.Count++; me.Seen = DateTime.UtcNow; PublishAiSoon(); }
      return result;
     }
     if (tries >= 2) return Fail(KeptChanging);
     changed:
     turn?.Release(); turn = null;
     step.Again = true;
    }
   } finally {
    turn?.Release();
    if (calling.Remove(interrupt) && calling.Count == 0 && agentInterrupts.GetValueOrDefault(who) == calling) agentInterrupts.Remove(who);
    PublishAll();
   }
  } catch (JsonException) { return Fail("Invalid request."); }
  catch (Exception ex) when (ex is InvalidOperationException or KeyNotFoundException or FormatException or ArgumentException or IOException or UnauthorizedAccessException or NotSupportedException or System.Runtime.InteropServices.COMException or TimeoutException) { return Fail(ex.Message); }
 }

 /// Asks the user in the agent bar ("" = may this agent control Still). Null: no answer yet; the question stays up.
 /// now: don't wait for the answer (the agent asks the user elsewhere, see NeedsConfirm).
 static async Task<bool?> AskUser(string client, string ask, bool now = false, Task? until = null)
 {
  if (TakeAnswer(client, ask) is { } said) return said; // answered after the agent stopped waiting
  var deadline = until ?? Task.Delay(TimeSpan.FromSeconds(now ? 0 : 45)); // shorter than MCP apps' own tool timeouts
  while (agentApproval is { } other && !(askClient == client && askText == ask))
   if (now || await Task.WhenAny(other.Task, deadline) == deadline) return null;
  if (agentApproval == null) { agentApproval = new(TaskCreationOptions.RunContinuationsAsynchronously); askClient = client; askText = ask; PublishAll(); }
  var pending = agentApproval;
  if (await Task.WhenAny(pending.Task, deadline) != pending.Task) return null;
  if (!pending.Task.Result || ask.Length == 0) return pending.Task.Result;
  return TakeAnswer(client, ask) == true ? true : await AskUser(client, ask, now, deadline); // another step took that yes: this one asks for itself
 }
 /// A yes is for one step: whichever takes it first, of those waiting on the question or calling again after it. A no stands
 /// for all of them, and so does letting an app in (ask "").
 static bool? TakeAnswer(string client, string ask)
 {
  if (lastAnswer.Client != client || lastAnswer.Ask != ask || DateTime.UtcNow - lastAnswer.At >= TimeSpan.FromMinutes(2)) return null;
  bool allow = lastAnswer.Allow;
  if (allow && ask.Length > 0) lastAnswer = default;
  return allow;
 }
 /// A question's words: what follows them in ask ties a yes to the control it was about, and isn't for reading.
 static string AskShown(string ask) => ask.Split('\0')[0];
 void AnswerAgent(bool allow, bool remember = true)
 {
  if (agentApproval is not { } pending) return;
  Settle(askClient, askText, allow, remember);
  agentApproval = null; askClient = askText = "";
  pending.TrySetResult(allow); PublishAll();
 }
 void Settle(string client, string ask, bool allow, bool remember = true)
 {
  if (ask.Length == 0) {
   if (!allow) blockedAgents.Add(client);
   else { approvedAgents.Add(client); if (remember && !Prefs.ApprovedAgents.Contains(client, StringComparer.OrdinalIgnoreCase)) { Prefs.ApprovedAgents.Add(client); SaveLater(); } }
  }
  lastAnswer = (client, ask, allow, DateTime.UtcNow);
  foreach (var code in confirmCodes.Where(c => c.Value.Client == client && c.Value.Ask == ask).Select(c => c.Key).ToList()) confirmCodes.Remove(code); // answered here: a code from the chat no longer counts
 }

 // An AI app that can ask the user itself does (MCP elicitation): the app handles the code, and the AI sees neither it nor the
 // question, so it can't answer for them. Letting an app in this way lasts until Still closes. Anything else waits for Still's bar.
 static readonly Dictionary<string, (string Client, string Ask, DateTime Until)> confirmCodes = [];
 string NeedsConfirm(string client, string ask, string waiting, bool elicit)
 {
  if (!elicit || !Prefs.AgentsAskInChat) return Fail(waiting);
  foreach (var old in confirmCodes.Where(c => c.Value.Until < DateTime.UtcNow).Select(c => c.Key).ToList()) confirmCodes.Remove(old);
  string code = Convert.ToHexString(RandomNumberGenerator.GetBytes(3)).ToLowerInvariant();
  confirmCodes[code] = (client, ask, DateTime.UtcNow.AddMinutes(10));
  string question = ask.Length == 0 ? $"Allow {client} to use your Still browser? It can open, read and click pages, but never private tabs, passwords or cookies." : $"Allow {client} to {AskShown(ask)}?";
  return JsonSerializer.Serialize(new { ok = false, confirm = new { code, question }, error = waiting }, ReplyJson);
 }
 string Confirmed(string client, JsonElement args)
 {
  if (!confirmCodes.Remove(S(args, "code").Trim().ToLowerInvariant(), out var c) || !c.Client.Equals(client, StringComparison.OrdinalIgnoreCase) || c.Until < DateTime.UtcNow)
   return Fail("That code isn't valid anymore (the user may have answered in Still). Call the tool again.");
  bool allow = B(args, "allow");
  if (agentApproval != null && askClient == c.Client && askText == c.Ask) AnswerAgent(allow, false); else Settle(c.Client, c.Ask, allow, false);
  Toast($"{c.Client} was {(allow ? "allowed" : "turned down")} {(c.Ask.Length == 0 ? "to use Still" : "to " + AskShown(c.Ask))}, answered in that app.");
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
  if (agentApproval != null) return new { client = askClient, pending = true, action = "", ask = AskShown(askText), paused = false };
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
  if (on) EndCalls(key, Fail(TookOver));
  if (on && agentTabs.GetValueOrDefault(key) is { } id && tabs.FirstOrDefault(t => t.Id == id) is { } t) await SelectTab(t);
  PublishAll();
 }
 // Stop cancels what the agent is doing now and lets go of its tabs; it stays allowed, so its next task needs no new approval.
 void StopAgent(string key)
 {
  var me = workers.GetValueOrDefault(key);
  ReleaseAgentTabs(key); stoppedAgents[key] = DateTime.UtcNow.AddSeconds(30);
  EndCalls(key, Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message."));
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
  const hash = s => { let h = 0; for (let i = 0; i < s.length; i++) h = h * 31 + s.charCodeAt(i) | 0; return h; };
  walk(document, e => {
   if (e.localName !== 'input') return;
   if (!o.on) { if (e.hasAttribute('data-still-masked')) { e.style.removeProperty('-webkit-text-security'); e.removeAttribute('data-still-masked'); } return; }
   if (e.value && o.prints.includes(hash(e.value))) { e.style.setProperty('-webkit-text-security', 'disc', 'important'); e.setAttribute('data-still-masked', ''); }
  });
  return true;
 """;
 const string HelloFirst = "Write your hello first: greet the user and say in a sentence or two what you'll do for them, then use your tools.";
 const string TookOver = "The user took over this tab for a moment, so your last action may not have finished. Call your next tool again: Still holds it until they hand the tab back, then check the page with read_page.";
 /// A dialog or file picker opened in the tab an agent is working in: its running call returns now and says so.
 static void InterruptAgent(BrowserTab t, object reply)
 {
  if (t.AgentKey is { } who && agentTabs.GetValueOrDefault(who) == t.Id) EndCalls(who, Reply(reply));
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
  // The words a person can see, in reading order, through open shadow roots and same-origin frames: like innerText, which also
  // reads words that are out of sight, see-through, tiny or in a frame that doesn't show.
  const BLOCK = /^(block|flex|grid|list-item|flow-root|table|table-row|table-caption|table-row-group|table-header-group|table-footer-group)$/;
  const pageText = () => {
   const out = [];
   const visit = c => {
    if (c.nodeType === 3) {
     const pe = c.parentElement || c.parentNode?.host; if (!pe) return;
     const cs = view(pe).getComputedStyle(pe);
     if (sight(pe).kids && cs.visibility === 'visible' && parseFloat(cs.fontSize) >= 3 && !/^rgba\(.*,\s*0\)$|\/\s*0\)$/.test(cs.color)) out.push(/^(pre|break-spaces)/.test(cs.whiteSpace) ? c.data : c.data.replace(/\s+/g, ' '));
     return;
    }
    if (c.nodeType !== 1 || /^(script|style|noscript|template|select|textarea)$/.test(c.localName)) return;
    const cs = view(c).getComputedStyle(c);
    if (cs.display === 'none' || !sight(c).kids) return;
    if (c.localName === 'br') { out.push('\n'); return; }
    const block = BLOCK.test(cs.display);
    out.push(block ? '\n' : cs.display === 'table-cell' ? '\t' : '');
    if (/^i?frame$/.test(c.localName)) { let d = null; try { d = c.contentDocument; } catch {} if (d && d.body) visit(d.body); }
    else if (c.localName === 'slot') { const a = c.assignedNodes({ flatten: true }); for (const x of a.length ? a : c.childNodes) visit(x); }
    else for (const x of (c.shadowRoot || c).childNodes) visit(x);
    if (block) out.push('\n');
   };
   if (document.body) visit(document.body);
   return out.join('').replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
  };
  // Position in the top window's viewport, adding the offsets of any frames it sits in.
  const box = e => { const r = e.getBoundingClientRect(); let x = r.left, y = r.top; for (let w = view(e); w !== window && w.frameElement; w = w.parent) { const f = w.frameElement.getBoundingClientRect(); x += f.left + w.frameElement.clientLeft; y += f.top + w.frameElement.clientTop; } return { x, y, w: r.width, h: r.height }; };
  const Q = 'a[href],button,input:not([type=hidden]),select,textarea,summary,label[for],[role=button],[role=link],[role=checkbox],[role=radio],[role=tab],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],[role=option],[role=switch],[role=combobox],[role=textbox],[role=searchbox],[role=slider],[role=treeitem],[contenteditable=""],[contenteditable=true],[contenteditable=plaintext-only],[onclick],[tabindex]:not([tabindex="-1"])';
  const parentOf = e => e.parentElement || (e.getRootNode && e.getRootNode().host) || null;
  // Controls, plus clickable things built from plain elements (the outermost element with a pointer cursor).
  const isControl = (e, cs) => e.localName === 'label' ? !!e.control && !visible(e.control) : e.matches(Q) || cs.cursor === 'pointer' && !!parentOf(e) && view(e).getComputedStyle(parentOf(e)).cursor !== 'pointer' && !!(e.innerText || e.getAttribute('aria-label') || '').trim();
  // What a person can see. ok: the element shows; kids: what's inside it can show; clip: the box its insides are cut to. Out of
  // sight: no box, invisible or see-through (itself or anything around it), cut away by a box around it that clips, clipped to
  // nothing, off the page's top or left where no scrolling goes, or off its side when the page doesn't scroll sideways. Hidden
  // controls and words are how a page talks to the AI behind the user's back, so the AI gets neither. A see-through field or
  // dropdown laid over its own look still counts. ponytail: words the colour of their background, and fixed or positioned
  // things that escape a box that's cut away, are judged by the box around them in the page, not by where they're drawn.
  let SEEN = new WeakMap(); const FREE = { l: -1e9, t: -1e9, r: 1e9, b: 1e9 };
  const sight = e => {
   let s = SEEN.get(e); if (s) return s;
   const w = view(e), d = e.ownerDocument, p = parentOf(e), f = !p && w.frameElement;
   const up = p ? sight(p) : f ? { kids: sight(f).kids, clip: FREE } : { kids: true, clip: FREE };
   s = { ok: false, kids: false, clip: up.clip };
   const cs = up.kids ? w.getComputedStyle(e) : null;
   if (cs && cs.display === 'contents') s = { ok: false, kids: true, clip: up.clip };
   else if (cs && e.getClientRects().length && (cs.opacity !== '0' || /^(input|select)$/.test(e.localName)) && !/inset\(\s*(50|100)%/.test(cs.clipPath)) {
    const r = e.getBoundingClientRect(), c = cs.position === 'fixed' ? { l: 0, t: 0, r: w.innerWidth, b: w.innerHeight } : up.clip, n = (cs.clip.match(/-?[\d.]+/g) || []).map(Number);
    const page = e === d.documentElement || e === d.body, cuts = x => /^(hidden|clip)$/.test(x), scrolls = x => /^(auto|scroll|overlay)$/.test(x);
    const out = r.left >= c.r || r.right < c.l || r.top >= c.b || r.bottom < c.t || r.right + w.scrollX <= 0 || r.bottom + w.scrollY <= 0;
    const kids = !out && !(n.length === 4 && (n[1] - n[3] <= 1 || n[2] - n[0] <= 1)) && !(!page && cuts(cs.overflowX) && r.width <= 1) && !(!page && cuts(cs.overflowY) && r.height <= 1);
    const cw = Math.min(r.right, c.r) - Math.max(r.left, c.l), ch = Math.min(r.bottom, c.b) - Math.max(r.top, c.t);
    // Its insides are cut to its box where it clips; where it scrolls, scrolling can bring them into view. A page that doesn't
    // scroll sideways cuts at the window's sides (menus parked off to the side); one that doesn't scroll down still scrolls inside.
    const x = page ? (cuts(cs.overflowX) ? { l: 0, r: w.innerWidth } : { l: c.l, r: c.r }) : cuts(cs.overflowX) ? { l: Math.max(c.l, r.left), r: Math.min(c.r, r.right) } : scrolls(cs.overflowX) ? { l: FREE.l, r: FREE.r } : { l: c.l, r: c.r };
    const y = page ? { t: c.t, b: c.b } : cuts(cs.overflowY) ? { t: Math.max(c.t, r.top), b: Math.min(c.b, r.bottom) } : scrolls(cs.overflowY) ? { t: FREE.t, b: FREE.b } : { t: c.t, b: c.b };
    // A box with no size of its own (a link around a card, say) shows through what's in it.
    const big = cw > 1 && ch > 1 || (r.width <= 1 || r.height <= 1) && !!e.firstElementChild;
    s = { ok: kids && big && cs.visibility === 'visible', kids, clip: { ...x, ...y } };
   }
   SEEN.set(e, s);
   return s;
  };
  const visible = e => sight(e).ok;
  // The pop-up that holds the page's attention, if one is open: what's outside it can't be reached.
  let M; const modal = () => M !== undefined ? M : (M = [...document.querySelectorAll('[aria-modal=true],dialog[open]')].reverse().find(m => { try { return visible(m) && (m.localName !== 'dialog' || m.matches(':modal')); } catch { return false; } }) || null);
  // On top at some point a person could click. Under a pop-up or banner: false. Out of view: true, unless a pop-up is open.
  const free = e => {
   const b = box(e); let tried = 0;
   for (const [fx, fy] of [[.5, .5], [.2, .2], [.8, .2], [.2, .8], [.8, .8]]) {
    const x = b.x + b.w * fx, y = b.y + b.h * fy;
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
    tried++;
    const top = deepAt(x, y);
    if (top && (inside(top, e) || inside(e, top) || top.closest?.('label')?.control === e)) return true;
   }
   return !tried && (!modal() || inside(modal(), e));
  };
  // What read_page and find list: a control a person can see and use. Inert parts of a page don't take clicks.
  const usable = (e, cs) => isControl(e, cs) && visible(e) && !e.closest('[inert]');
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
  const byText = text => {
   const want = text.trim().toLowerCase(); let best = null, rank = -1;
   walk(document, e => {
    const cs = view(e).getComputedStyle(e); if (!usable(e, cs)) return;
    const l = label(e).toLowerCase(), m = l === want ? 2 : l.includes(want) ? 0 : -1; if (m < 0) return;
    const r = m + (free(e) ? 1 : 0); if (r > rank) { best = e; rank = r; }
    if (rank === 3) return false;
   });
   return best; // covered, it still comes back, so the click can say what's on top of it
  };
  const target = o => o.id ? byId(o.id) : o.selector ? bySel(o.selector) : o.text ? byText(o.text) : null;
  const missing = o => ({ error: o.id ? 'gone' : 'notfound' });
  // A fingerprint of a field's text, to tell whether typing changed it.
  const sig = e => { const s = !e ? '' : e.isContentEditable ? e.innerText : String(e.value ?? ''); let h = 0; for (let i = 0; i < s.length; i++) h = h * 31 + s.charCodeAt(i) | 0; return s.length + ':' + h; };
  // Where a click at this point lands, through open shadow roots and same-origin frames.
  const deepAt = (x, y) => {
   let at = document.elementFromPoint(x, y);
   for (; at;) {
    const inner = at.shadowRoot?.elementFromPoint(x, y);
    if (inner && inner !== at) { at = inner; continue; }
    if (!/^i?frame$/.test(at.localName)) return at;
    let d = null; try { d = at.contentDocument; } catch {}
    if (!d) return at;
    const r = at.getBoundingClientRect(); x -= r.left + at.clientLeft; y -= r.top + at.clientTop;
    const next = d.elementFromPoint(x, y); if (!next) return at;
    at = next;
   }
   return null;
  };
  // Exactly what a step's approval is for: the page, the control's kind and words, and where it would send things. Never what's
  // typed in a field. Form properties are read through the prototype: a field named "action" would hide the real one.
  const formProp = (f, k) => Object.getOwnPropertyDescriptor(view(f).HTMLFormElement.prototype, k).get.call(f);
  const formOf = e => { const f = e.localName === 'form' ? e : e.form; return f?.localName === 'form' ? f : e.closest?.('form') || null; };
  const print = e => {
   const page = location.origin + location.pathname + location.search;
   if (!e || e.localName === 'body' || e.localName === 'html') return JSON.stringify([page]);
   const f = formOf(e);
   return JSON.stringify([page, e.ownerDocument.location.origin, e.localName, e.type || '', e.getAttribute('role') || '', label(e), String(e.href || ''),
    f ? formProp(f, 'action') : '', f ? formProp(f, 'method') : '', e.getAttribute('formaction') || '', e.getAttribute('formmethod') || '']);
  };
  // What an action did: a watcher set up before it, kept on the window between calls. No watcher later means a new document.
  const WATCH = Symbol.for('still.watch');
  const stateOf = e => !e ? '' : JSON.stringify([e.checked, e.value, e.open, e.selectedIndex, e.control?.checked, e.control?.value]);
  const typable = e => !!e && (e.isContentEditable || e.localName === 'textarea' || e.localName === 'select' || e.localName === 'input' && !/^(button|submit|reset|image|checkbox|radio|file|color|range)$/.test(e.type));
  const watch = (e, hit, expect) => {
   // Input going into a frame from another site never shows up here, and there's no telling: it counts as arrived, and goes once.
   const sealed = /^i?frame$/.test((hit || e)?.localName);
   window[WATCH]?.stop();
   const d = e ? e.ownerDocument : document, at = new Set([window, d.defaultView, e?.getRootNode?.()].filter(Boolean));
   const W = { e, n: 0, got: sealed, reached: sealed, pressed: sealed, keyed: sealed, missed: '', submitted: false, invalid: '', blocked: '', sent: false, through: false };
   const hits = ev => { const path = ev.composedPath(); return !e || path.includes(e) || !!hit && path.includes(hit); };
   // The last check, as Still's own input arrives. Not what was approved, or not on it: the input stops here, the page never gets
   // it, and the step goes back to asking. blocked 'before': nothing reached the page yet. 'during': part of it did. The page's own
   // scripted events aren't Still's input, and once the click or key is through what follows (a label's click, say) is the page's.
   const allowed = ev => ev.type.startsWith('key') ? deepActive() === e && print(e) === expect : hits(ev) && print(e) === expect;
   const pass = ev => {
    W.got = true;
    if (!expect || W.through) return true;
    if (!ev.isTrusted) return !W.blocked;
    // It acted on the press and left: it worked, and the rest of the click isn't for whatever is under the mouse now.
    if (W.sent && e && !e.isConnected) { W.pressed = true; ev.preventDefault(); ev.stopImmediatePropagation(); return false; }
    if (!W.blocked && (ev.type === 'keydown' || !ev.type.startsWith('key')) && !allowed(ev)) W.blocked = W.sent ? 'during' : 'before';
    if (W.blocked) { ev.preventDefault(); ev.stopImmediatePropagation(); return false; }
    W.sent = true;
    if (ev.type === 'click' || ev.type === 'keydown') W.through = true;
    return true;
   };
   const ours = m => m.type === 'attributes' ? /^data-still-/.test(m.attributeName) : m.type === 'childList' && [...m.addedNodes, ...m.removedNodes].every(x => x.localName === 'still-cursor'); // the AI's cursor and read_page's ids
   const seen = new MutationObserver(list => { for (const m of list) if (!ours(m)) W.n++; });
   for (const x of new Set([document, d])) seen.observe(x, { subtree: true, childList: true, attributes: true, characterData: true });
   const on = {
    mousedown: ev => { if (pass(ev) && hits(ev)) W.pressed = true; },
    click: ev => { if (!pass(ev)) return; if (hits(ev)) W.reached = true; else if (!W.reached) W.missed = line(ev.composedPath()[0]); },
    keydown: ev => { if (pass(ev)) W.keyed = true; },
    pointerdown: pass, pointerup: pass, mouseup: pass, keypress: pass, keyup: pass,
    submit: () => { W.submitted = true; },
    invalid: ev => { if (!W.invalid) W.invalid = (label(ev.target) || kind(ev.target)) + ': ' + ev.target.validationMessage; },
   };
   for (const x of at) for (const t in on) x.addEventListener(t, on[t], true);
   W.stop = () => { seen.disconnect(); clearTimeout(W.timer); for (const x of at) for (const t in on) x.removeEventListener(t, on[t], true); if (window[WATCH] === W) delete window[WATCH]; };
   W.timer = setTimeout(W.stop, 30000);
   W.mark = () => { W.n = 0; W.url = location.href; W.state = stateOf(e); W.active = deepActive(); W.sig = sig(W.active); W.x = scrollX; W.y = scrollY; W.sel = String(getSelection()); };
   W.mark();
   return window[WATCH] = W;
  };
 """;

 // read_page: header, then one line per control near the visible area (or all of them), then a page of the text.
 const string SnapshotJs = """
  const vh = innerHeight, out = [], listed = new Set(), cap = o.all ? 600 : 250; let above = 0, below = 0, more = 0, under = 0;
  walk(document, e => {
   const cs = view(e).getComputedStyle(e);
   if (!usable(e, cs)) return;
   const host = parentOf(e)?.closest?.('a,button'); if (host && listed.has(host)) return;
   if (!o.all) { const b = box(e); if (b.y + b.h < -vh / 2) { above++; return; } if (b.y > vh * 1.5) { below++; return; } }
   if (!free(e)) { under++; return; }
   if (listed.size >= cap) { more++; return; }
   listed.add(e); out.push(line(e));
  });
  const se = document.scrollingElement || document.documentElement;
  let s = document.title + '\n' + location.href + '\nscrolled ' + Math.round(scrollY) + ' of ' + Math.max(0, se.scrollHeight - vh) + 'px\n\n' + (out.join('\n') || '(no buttons, links or fields here)');
  if (above || below || more) s += '\n… ' + [above && above + ' more above', below && below + ' more below', more && more + ' more'].filter(Boolean).join(', ') + ' (scroll, use find, or read_page all=true)';
  if (under) s += '\n… ' + under + ' more under something on top, like a pop-up or banner: close it first';
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
   if (!usable(e, cs) || !free(e)) return;
   if ((label(e) + ' ' + (e.type === 'password' ? '' : e.value || '') + ' ' + (e.getAttribute('href') || '') + ' ' + (e.title || '')).toLowerCase().includes(want)) out.push(line(e));
   if (out.length >= 25) return false;
  });
  const text = pageText().split('\n').filter(l => l.toLowerCase().includes(want)).slice(0, 15).map(l => clip(l, 200));
  return (out.length ? out.join('\n') : 'No buttons, links or fields match.') + '\n\n--- text ---\n' + (text.length ? text.join('\n') : 'No text matches.');
 """;
 const string ClickJs = """
  const e = target(o); if (!e) return missing(o);
  if (o.expect && print(e) !== o.expect) return { error: 'changed' };
  if (e.matches(':disabled') || e.closest('[aria-disabled="true"]')) return { error: 'disabled', label: label(e) || kind(e) };
  e.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
  const b = box(e); if ((!b.w && !b.h) || !e.getClientRects().length || view(e).getComputedStyle(e).visibility === 'hidden') return { error: 'hidden' };
  // A page out of view still lays out: its window has to have a size and the middle of the element has to be inside it.
  if (!innerWidth || !innerHeight) return { error: 'noview' };
  const x = b.x + b.w / 2, y = b.y + b.h / 2;
  if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return { error: 'offscreen' };
  const top = deepAt(x, y);
  if (!top) return { error: 'offscreen' };
  if (!inside(top, e) && !inside(e, top) && top.closest('label')?.control !== e) return { error: 'covered', by: line(top.closest(Q) || top) };
  SEEN = new WeakMap(); if (!visible(e)) return { error: 'hidden' };
  if (!o.again) watch(e, top, o.expect);
  return { x, y, label: label(e) || kind(e) };
 """;
 // Key presses: a watcher on whatever has focus. MarkJs: the point to measure from, after the mouse has moved over the element.
 const string WatchJs = """
  const e = deepActive();
  if (o.expect && print(e) !== o.expect) return { error: 'changed' };
  watch(e, null, o.expect); return true;
 """;
 const string MarkJs = """
  window[WATCH]?.mark(); return true;
 """;
 const string GotJs = """
  const W = window[WATCH]; return !W || W.got || W.n > 0;
 """;
 const string SeenJs = """
  const W = window[WATCH]; if (!W) return { gone: true };
  const a = deepActive(), changed = [];
  if (location.href !== W.url) changed.push('url');
  if (W.n) changed.push('page');
  if (W.e && !W.e.isConnected) changed.push('removed');
  if (stateOf(W.e) !== W.state) changed.push('state');
  if (scrollX !== W.x || scrollY !== W.y) changed.push('scroll');
  if (o.key ? a !== W.active || sig(a) !== W.sig || String(getSelection()) !== W.sel : typable(a) && (a !== W.active || a === W.e)) changed.push('focus');
  if (W.e?.closest?.('a[download]') && W.reached) changed.push('download');
  const out = { reached: W.reached, pressed: W.pressed, keyed: W.keyed, missed: W.missed, submitted: W.submitted, invalid: W.invalid, blocked: W.blocked, changed };
  if (o.last) W.stop();
  return out;
 """;
 // type: focuses the field and selects what's in it (so typing replaces it), or picks a dropdown option.
 const string FocusJs = """
  const e = o.id || o.selector ? target(o) : deepActive();
  if (!e || e.localName === 'body') return o.id || o.selector ? missing(o) : { error: 'nofocus' };
  if (o.expect && print(e) !== o.expect) return { error: 'changed' };
  S.typing = e;
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
  const from = sc.scrollTop;
  sc.scrollBy({ top: (o.direction === 'up' ? -1 : 1) * (o.amount || Math.round(innerHeight * .8)), behavior: 'instant' });
  if (sc.scrollTop === from) return { error: 'noscroll' };
  const max = sc.scrollHeight - sc.clientHeight;
  return { done: 'Scrolled ' + (o.direction === 'up' ? 'up' : 'down'), at: max > 0 ? Math.round(sc.scrollTop / max * 100) + '%' : 'no scrolling here' };
 """;
 const string SigJs = "return { sig: sig(deepActive()) };";
 // Right before typing: still the field that was approved, and the keys would go into it.
 const string SameJs = """
  const e = S.typing, a = deepActive();
  return !!e && e.isConnected && print(e) === o.expect && (!a || a.localName === 'body' || inside(e, a)) ? true : { error: 'changed' };
 """;
 const string WaitJs = """
  const found = o.id ? !!byId(o.id) : o.selector ? !!bySel(o.selector) : pageText().toLowerCase().includes(o.text.toLowerCase());
  return o.gone ? !found : found;
 """;
 // upload_file by element: the file input itself, for DOM.setFileInputFiles.
 // Is this click or keystroke sensitive: buying, sending, deleting, a form that posts, a password or payment field?
 const string SensitiveJs = """
  const e = o.tool !== 'press_key' && (o.id || o.selector || (o.tool === 'click' && o.text)) ? target(o) : deepActive();
  if (!e && o.tool !== 'press_key') return missing(o);
  if (!e || /^(body|html)$/.test(e.localName) && !e.isContentEditable) {
   if (o.tool === 'type') return { error: 'nofocus' };
   return { label: 'the page', why: '', secret: false, password: false, print: print(e) };
  }
  const form = formOf(e);
  const secret = x => x.type === 'password' ? 'password' : /^cc-|card.?num|cvc|cvv|security.?code|iban/i.test((x.autocomplete || '') + ' ' + (x.name || '') + ' ' + (x.id || '')) ? 'payment' : '';
  const posts = !!form && (formProp(form, 'method') === 'post' || e.getAttribute('formmethod')?.toLowerCase() === 'post' || [...formProp(form, 'elements')].some(secret));
  const control = e.closest?.('button,a[href],summary,input,[role=button],[role=link],[role=menuitem]') || e; // an icon inside a button is the button
  const words = (label(control) + ' ' + (control.localName === 'input' ? control.value : '')).toLowerCase();
  const enter = /(^|\+)\s*(enter|return)$/i.test(o.key || ''), writes = e.isContentEditable || e.getAttribute('role') === 'textbox';
  // Enter or Space on a button is a click. Keywords and forms are the best a page lets Still tell.
  const pressed = o.tool === 'press_key' && (enter || /^(space|spacebar| )$/i.test(o.key || '')) && control.matches('button,a[href],summary,input[type=submit],input[type=button],input[type=image],[role=button],[role=link],[role=menuitem]');
  let why = '';
  if (o.tool === 'type') why = secret(e) === 'password' ? 'It types into a password field.' : secret(e) ? 'It types into a payment field.' : o.submit && posts ? 'It sends a form.' : o.submit && writes ? 'It may send what was typed.' : '';
  else if (o.tool === 'press_key' && !pressed) why = !enter ? '' : posts && e.matches('input,select') ? 'It sends a form.' : writes || e.localName === 'textarea' && o.key.includes('+') ? 'It may send what was typed.' : '';
  else if (/\b(buy|purchase|place order|order now|pay|checkout|check out|subscribe|book now|reserve)\b/.test(words)) why = 'It looks like a purchase.';
  else if (/\b(send|post|publish|reply|tweet|comment)\b/.test(words)) why = 'It sends something in your name.';
  else if (/\b(delete|remove|discard|trash|unsubscribe|close account|cancel order|cancel subscription)\b/.test(words)) why = 'It deletes or cancels something.';
  else if (posts && control.matches('button:not([type=button]):not([type=reset]),input[type=submit],input[type=image]')) why = 'It sends a form.';
  return { label: label(e) || kind(e), why, secret: !!secret(e), password: secret(e) === 'password', print: print(e) };
 """;
 const string FileInputJs = """
  const e = target(o); return e && e.localName === 'input' && e.type === 'file' ? e : e?.querySelector?.('input[type=file]') || e?.closest?.('label')?.control || null;
 """;

 static async Task<JsonElement> Js(CoreWebView2 core, string body, object o)
 {
  string json = await core.RunInOwnWorld("((o)=>{try{" + PageJs + body + "}catch(err){return {error:'script',message:String(err&&err.message||err)}}})(" + JsonSerializer.Serialize(o) + ")");
  using var doc = JsonDocument.Parse(json);
  var r = doc.RootElement.Clone();
  if (r.ValueKind == JsonValueKind.Object && r.TryGetProperty("error", out var err) && err.GetString() == "changed") throw new PageChanged();
  if (r.ValueKind == JsonValueKind.Object && r.TryGetProperty("error", out err)) throw new PageMiss(err.GetString() is "gone" or "notfound" or "hidden" or "covered" or "disabled" or "offscreen", err.GetString() switch {
   "gone" => "That element isn't on the page anymore (the page changed or it's a new page). Call read_page or find for current ids.",
   "notfound" => "Couldn't find that element on the page. Call read_page or find.",
   "hidden" => "That element is hidden right now (maybe in a closed menu). Open what contains it first, or call read_page.",
   "covered" => "Something is on top of that element: " + Str(r, "by") + ". Close or click that first (often a cookie banner or pop-up).",
   "disabled" => "\"" + Str(r, "label") + "\" is disabled right now, so nothing was clicked. Do what it's waiting for first (often a required field).",
   "offscreen" => "That element is outside the visible page and scrolling didn't bring it in, so nothing was clicked. Call read_page.",
   "noview" => "This page has no size right now, so nothing was clicked. Call read_page, or ask the user to bring its tab to the front.",
   "noscroll" => "Nothing scrolled: it's already at the end, or there's nothing to scroll here.",
   "nofocus" => "No field is focused. Pass the field's id.",
   "nooption" => "That dropdown has no matching option. Options: " + Str(r, "options"),
   "empty" => "Pass the text to look for.",
   _ => "The page's script failed: " + Str(r, "message"),
  });
  return r;
 }
 sealed class PageMiss(bool missed, string message) : InvalidOperationException(message) { public readonly bool Missed = missed; } // Missed: the element moved, vanished or is covered
 const string KeptChanging = "The page kept changing, so Still did nothing and stopped asking. Call read_page to see it now.";
 sealed class PageChanged() : InvalidOperationException(KeptChanging); // not what the user approved any more, and nothing was sent: the step asks again
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
  // With the chat in front, a new message carries on in the chat's own page: the chat tab has no page to act on.
  if (id.Length == 0 && active?.ChatId != null) id = Windows.Where(w => !w.closing).SelectMany(w => w.tabs).Where(t => (t.InChat ?? t.RunChat) == who && !t.Closed).MaxBy(t => t.LastActive)?.Id ?? "";
  foreach (var w in Windows.Where(w => !w.closing)) {
   var t = id.Length > 0 ? w.tabs.FirstOrDefault(x => x.Id == id) : (w == this ? w.active : null);
   if (t != null) {
    // An incognito chat works only in the private tabs it opened. Every other agent never touches a private tab.
    if (Incognito(who) ? (t.InChat ?? t.RunChat) != who : t.Private) throw new InvalidOperationException(Incognito(who) ? "An incognito chat only uses the tabs it opened. Open one with open_tab." : "Private tabs are off-limits to agents.");
    if (OutOfProfile(who, t)) throw new InvalidOperationException("That tab is in the user's own browser profile, and you browse apart from it. Open a page with open_tab, or ask the user to hand you the tab.");
    Claim(who, w, t); return (w, t);
   }
  }
  throw new InvalidOperationException(id.Length > 0 ? "No tab with that id. Call list_tabs." : "There is no active tab.");
 }
 /// The agent's tab, ready for page work. A page paused on a dialog can't run scripts, so that comes first.
 async Task<(MainWindow w, BrowserTab t, CoreWebView2 core)> AgentPage(string who, JsonElement args)
 {
  var (w, t) = AgentTab(who, args);
  if (t.ChatId != null) throw new InvalidOperationException("That tab is a chat, not a page. Open a page with open_tab.");
  if (t.Dialog is { } d) throw new InvalidOperationException($"The page is waiting on a dialog ({DialogKind(d)}): \"{Clip(d.Args.Message, 200)}\". Answer it with handle_dialog first.");
  var core = await Core(w, t);
  // Agents work in background tabs, which never have focus; editors like Notion ignore typing without it.
  await core.CallDevToolsProtocolMethodAsync("Emulation.setFocusEmulationEnabled", "{\"enabled\":true}");
  return (w, t, core);
 }
 /// The companion profile keeps its sign-ins apart from the user's, so its chats stay out of the user's tabs, except one handed over.
 static bool OutOfProfile(string who, BrowserTab t) => OnCompanion(who) && t.ChatId == null && t.Engine != CompanionEngine && (t.InChat ?? t.RunChat) != who;
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
 // What an AI may name as a file. A path that reaches another computer would connect to it as soon as anything looked at it, so these go before the disk is touched.
 static bool LocalFilePath(string path) => Path.IsPathFullyQualified(path) && !path.StartsWith(@"\\") && !path.StartsWith("//") && !path.StartsWith(@"\/") && !path.StartsWith(@"/\") && !path.Any(c => char.GetUnicodeCategory(c) is System.Globalization.UnicodeCategory.Control or System.Globalization.UnicodeCategory.Format);
 static readonly string[] KeyFolders = [".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".claude", "Credentials", "Protect"];
 // Keys and Still's own data stay on this computer whatever an AI is told: only the person can pick them. A link is judged by where it leads.
 static bool OffLimitsFile(string path)
 {
  string real;
  try { real = File.ResolveLinkTarget(path, true)?.FullName ?? path; } catch (Exception ex) when (ex is FileNotFoundException or DirectoryNotFoundException) { real = path; } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return true; }
  return new[] { path, real }.Any(p => p.Split('\\', '/').Any(part => KeyFolders.Contains(part, StringComparer.OrdinalIgnoreCase)) || Within(p, App.DataRoot) || Within(p, App.ProfileHome));
  static bool Within(string p, string root) => root.Length > 0 && p.StartsWith(Path.TrimEndingDirectorySeparator(root) + "\\", StringComparison.OrdinalIgnoreCase);
 }
 /// What an agent may open: web pages, and files inside its companion's working folder (a builder tests what it made there).
 internal const string SampleHost = "sample.still.internal"; // Shell/sample, mapped into every tab
 static string WebUrl(string input, string engine, string folder = "")
 {
  if (input.Trim() is var text && (text.StartsWith(@"\\") || text.StartsWith("//") || text.StartsWith(@"\/") || text.StartsWith(@"/\"))) throw new InvalidOperationException("Agents can only open http and https pages" + (folder.Length > 0 ? ", and files in your working folder." : "."));
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
 /// On this computer or its network, going by the name or address alone.
 internal static bool IsPrivateName(string host)
 {
  host = host.Trim('[', ']').TrimEnd('.').ToLowerInvariant();
  if (System.Net.IPAddress.TryParse(host, out var ip)) return PrivateIp(ip);
  return !host.Contains('.') || new[] { ".localhost", ".local", ".internal", ".intranet", ".lan", ".home", ".corp", ".home.arpa" }.Any(end => host.EndsWith(end, StringComparison.Ordinal));
 }
 static bool PrivateIp(System.Net.IPAddress ip)
 {
  if (ip.IsIPv4MappedToIPv6) ip = ip.MapToIPv4();
  if (System.Net.IPAddress.IsLoopback(ip) || ip.IsIPv6LinkLocal || ip.IsIPv6SiteLocal || ip.IsIPv6UniqueLocal || ip.Equals(System.Net.IPAddress.IPv6Any)) return true;
  var b = ip.GetAddressBytes();
  return b.Length == 4 && (b[0] is 0 or 10 or 127 || b[0] == 169 && b[1] == 254 || b[0] == 172 && b[1] is >= 16 and <= 31 || b[0] == 192 && b[1] == 168 || b[0] == 100 && b[1] is >= 64 and <= 127);
 }
 // Tests run on local pages: there, only the names a test lists count as private.
 static bool PrivateName(string host) => App.IsQa ? (Environment.GetEnvironmentVariable("STILL_QA_PRIVATE") ?? "").Split(',').Contains(host) : IsPrivateName(host);
 static async Task<bool> PrivateHost(string host)
 {
  if (PrivateName(host)) return true;
  if (App.IsQa) return false;
  try { return (await System.Net.Dns.GetHostAddressesAsync(host).WaitAsync(TimeSpan.FromSeconds(1))).Any(PrivateIp); }
  catch (Exception ex) when (ex is System.Net.Sockets.SocketException or TimeoutException or ArgumentException) { return false; }
 }
 static readonly System.Text.RegularExpressions.Regex HostWords = new(@"[a-z0-9-]+(?:\.[a-z0-9-]+)+|localhost"), LinkTitles = new(@"\[[^\]]*\]\(");
 /// Has this chat been there, or did the user name it? A tab's title in a message is the page's words, not the user's.
 bool BeenTo(AiChat root, string host) => host == Host(SearchUrl("x")) || root.Known.Any(k => OnSite(k, host))
  || root.Messages.Any(m => m.Role == "user" && m.Who == null && HostWords.Matches(LinkTitles.Replace(m.Text.ToLowerInvariant(), "(")).Any(t => OnSite(t.Value.StartsWith("www.", StringComparison.Ordinal) ? t.Value[4..] : t.Value, host)));
 bool SiteAllows(string who, string site, string action) => Prefs.Permissions.Any(p => p.Action == action && p.Mode == "always" && OnSite(p.Site, site) && (p.Companion.Length == 0 || p.Companion == who));
 /// Page text can steer an AI: read something signed in, then carry it off in an address. So what a chat has read decides
 /// whether going somewhere takes a yes. Null: it doesn't. How careful is the user's pick (Prefs.NewSites): "ask" asks before
 /// any new site and any long address; "balanced" asks before a new site, and before a long address only off the sites the
 /// chat knows or when it carries another address on; "fewer" asks only before a long address off them. Your own network
 /// always asks.
 async Task<(string Why, bool Data)?> Reach(AiChat root, string tool, string url, string host)
 {
  if (!Uri.TryCreate(url, UriKind.Absolute, out var u) || u.Scheme is not ("http" or "https")) return null;
  int extra = u.Query.Length + u.Fragment.Length;
  bool known = BeenTo(root, host);
  if (root.Read > 0 && (extra > 200 || u.AbsolutePath.Length > 300) && (!known || Prefs.NewSites == "ask" || Onward(u))) return ("This address carries a lot of data: " + Clip(u.PathAndQuery + u.Fragment, 120), true);
  if (known) return null;
  if (await PrivateHost(host)) return ("This is on your own computer or network.", false);
  // ponytail: a few short addresses can still carry a little, and a form on an allowed site isn't an address at all. Hosts by name, so a domain rebinding after this check gets through.
  if (Prefs.NewSites != "fewer" && root.Read > 0 && (tool != "read_url" || root.Read > 1 || extra > 60)) return ("A new site for this chat, after it read from the web.", false);
  return null;
 }
 /// An address inside the address, the way a site's redirect sends what it carries on to another.
 static bool Onward(Uri u) { string s = u.PathAndQuery + u.Fragment; for (int i = 0; i < 3; i++) s = Uri.UnescapeDataString(s); return s.Contains("//"); }
 /// What this step adds to what the chat has read, and where it has been.
 static void Exposed(ChatRun run, string tool, AgentStep step)
 {
  var root = ExchangeOf(run.Chat).Root;
  string been = step.Tab ? step.Site : step.SignedOut ? "" : step.Goes;
  if (been.Length > 0 && !root.Known.Contains(been)) root.Known.Add(been);
  int signedIn = run.Chat.Ephemeral ? 1 : 2; // an incognito window holds nothing else
  root.Read = Math.Max(root.Read, tool switch {
   "read_page" or "find" or "screenshot" or "wait_for" or "click" or "type" or "press_key" or "handle_dialog" or "list_tabs" or "run_plugin_action" => signedIn,
   "read_url" => step.SignedOut ? 1 : signedIn,
   "web_search" or "read_attachment" => 1,
   _ => 0 });
 }
 /// Once it's this call's turn, right before it runs: is this still what the gate saw? The same tab on the same site, and for
 /// a click or a key the same control, doing the same thing?
 async Task<bool> StillTheSame(string who, string tool, JsonElement args, AgentStep step)
 {
  if (!step.Tab) return true;
  var t = AgentTab(who, args).tab;
  if (t.Id != step.TabId || tool != "navigate" && Host(t.Url) != step.Site) return false; // navigate's site is where it's going
  if (step.Print.Length == 0) return true;
  try {
   var look = await Js((await AgentPage(who, args)).core, SensitiveJs, Probe(tool, args));
   return Str(look, "print") == step.Print && Str(look, "why") == step.Why;
  } catch (InvalidOperationException) { return false; }
 }
 static object Probe(string tool, JsonElement args) => new { tool, id = Id(args), selector = S(args, "selector"), text = S(args, "text"), key = S(args, "key"), submit = B(args, "submit") };
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
 async Task<string?> Gate(string who, string tool, JsonElement args, bool quick, AgentStep step, bool elicit)
 {
  string action = tool switch {
   "read_page" or "find" or "screenshot" or "wait_for" or "web_search" or "read_url" => "read",
   "open_tab" or "navigate" or "go_back" or "go_forward" or "reload" or "switch_tab" or "close_tab" => "navigate",
   "click" or "type" or "press_key" or "scroll" or "handle_dialog" => "interact",
   _ => "" }; // list_tabs shows no page; ask_user and save_file stay in Still; upload_file asks every time on its own
  if (action.Length == 0) return null;
  string site, what, why = "", url = "";
  bool again = step.Again;
  step.Intent = null; step.Again = false; step.Tab = step.Allowed = step.SignedOut = false; step.Print = step.Why = step.Goes = "";
  try {
   if (tool is "open_tab" or "navigate") { url = WebUrl(S(args, "url"), Prefs.SearchEngine, WorkFolder(who)); site = Host(url); what = "Open " + site; }
   else if (tool == "read_url") { url = WebUrl(S(args, "url"), Prefs.SearchEngine); site = Host(url); what = "Read " + site; }
   else if (tool == "web_search") { site = Host(SearchUrl("x")); what = "Search for “" + Clip(S(args, "query"), 60) + "”"; }
   else {
    site = Host(AgentTab(who, args).tab.Url);
    what = tool switch { "scroll" => "Scroll the page", "press_key" => "Press " + S(args, "key"), "handle_dialog" => "Answer the page's dialog", "go_back" => "Go back",
     "go_forward" => "Go forward", "reload" => "Reload the page", "close_tab" => "Close a tab", "switch_tab" => "Switch tabs", _ => "Read the page" };
    if (tool is "click" or "type" or "press_key") {
     var page = await AgentPage(who, args);
     // Pages re-render under the AI: a control that isn't there yet is waited for here, so it's asked about like any other.
     var look = await Settled(page.t, page.core, async () => {
      var seen = await Js(page.core, SensitiveJs, Probe(tool, args));
      return seen.ValueKind == JsonValueKind.Object ? seen : throw new PageMiss(true, "The page is still loading, so nothing was done. Call read_page, then try again.");
     });
     string label = Str(look, "label"); why = step.Why = Str(look, "why"); step.Print = Str(look, "print");
     // AIs never type a password: they wait while the user signs in.
     if (look.GetProperty("password").GetBoolean() && !(tool == "press_key" && S(args, "key") is "Tab" or "Escape" or "Esc") && tool != "click") {
      var (w, t) = AgentTab(who, args); await AskToSignIn(who, w, t, site);
      return Fail(SigningIn(site));
     }
     if (tool == "click") what = "Click “" + label + "”";
     else if (tool == "type") what = look.GetProperty("secret").GetBoolean() || S(args, "text").Length == 0 ? "Type into “" + label + "”" : "Type “" + Clip(S(args, "text"), 60) + "” into “" + label + "”";
    }
   }
   if (tool is not ("open_tab" or "read_url" or "web_search")) { step.TabId = AgentTab(who, args).tab.Id; step.Site = site; step.Tab = true; }
  } catch (InvalidOperationException ex) { return Fail(ex.Message); } // no page, no such element, or the check couldn't run: without the check, nothing happens
  bool marked = Prefs.SensitiveSites.Any(s => OnSite(s, site));
  if (action == "interact" && (why.Length > 0 || marked)) { action = "sensitive"; if (why.Length == 0) why = "You marked " + site + " as sensitive."; }
  var run = runs.GetValueOrDefault(who);
  if (again) { if (run != null) Audit(run.Chat, what, site, "The page changed, so Still asked again"); why = why.Length > 0 ? "The page changed since you were asked. " + why : "The page changed since you were asked."; }
  // A child task (a teammate asked it) acts only where everyone up the chain may, with the approvals given in the
  // user's chat. Outside apps ask before a sensitive step; the rest goes unless you set a rule or marked the site sensitive.
  var up = run == null ? default : ExchangeOf(run.Chat);
  string mode = run != null ? Delegation.Strictest(up.Chain.Select(c => PermissionMode(c, site, action) ?? DefaultPermission(action))) : PermissionMode("", site, action) ?? (marked || action == "sensitive" ? "ask" : "always"), key = action + " " + site;
  bool data = false;
  if (run != null && url.Length > 0) {
   step.Goes = site;
   if (!up.Chain.All(c => SiteAllows(c, site, action)) && await Reach(up.Root, tool, url, site) is { } reach) { why = why.Length > 0 ? why + " " + reach.Why : reach.Why; data = reach.Data; if (mode == "always") mode = "chat"; }
  }
  bool granted = !data && (mode == "always" || mode == "chat" && (run != null ? up.Root.Allowed.Contains(key) : sessionGrants.Contains(who + " " + key)));
  if (action == "sensitive" && run?.Recheck == true) granted = false; // picked up after one that may not have finished: the user decides again
  if (run == null) {
   if (granted) return null;
   string ask = char.ToLowerInvariant(what[0]) + what[1..] + " on " + site + (step.Print.Length > 0 ? "\0" + step.Print : "");
   switch (await AskUser(who, ask, quick)) {
    case false: return Fail("The user said no to this. Don't try it again unless they ask.");
    case null: return NeedsConfirm(who, ask, $"Waiting for the user to allow it: Still shows Allow and Block at the top of its window. Tell the user, then call {tool} again.", elicit);
   }
   if (mode == "chat") sessionGrants.Add(who + " " + key);
   return null;
  }
  if (granted && action != "sensitive") { if (action == "interact") Audit(run.Chat, what, site, mode == "always" ? "Allowed by your settings" : "Allowed in this chat"); return null; }
  string answer = await Approve(run, what, site, action, why, countdown: granted);
  if (answer == "always" && (run.Chat.Ephemeral || site.Length == 0)) answer = "chat"; // an incognito chat writes no site rules, and a page with no site has none to write
  if (answer == "always") foreach (var companion in up.Chain) SetPermission(site, action, companion, "always"); // who the card named, and whoever they're helping: not everyone
  if (answer == "chat" && !up.Root.Allowed.Contains(key)) up.Root.Allowed.Add(key);
  step.Allowed = answer is "always" or "chat" or "once";
  Audit(run.Chat, what, site, answer switch {
   "always" => "You always allow this on " + site, "chat" => "You allowed it in this chat", "once" => "You allowed it once",
   "go" => "Went ahead after 8 seconds", "now" => "You let it go ahead", "cancel" => "You cancelled it", "stop" => "Stopped",
   "timeout" => "No answer in 10 minutes", _ => "You said no" });
  PublishAiEverywhere();
  if (answer is "always" or "chat" or "once" or "go" or "now" && action == "sensitive") {
   if (run.Recheck) { run.Recheck = false; foreach (var s in run.Task.Sensitive.Where(s => s.Outcome == null)) s.Outcome = "rechecked"; }
   step.Intent = new() { What = what, Site = site };
  }
  return answer switch {
   "always" or "chat" or "once" or "go" or "now" => null,
   "cancel" => Fail("The user cancelled this before it ran. Don't try it again unless they ask."),
   "stop" => Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message."),
   "timeout" => Fail("The user didn't answer within 10 minutes. Stop here and ask them in your reply."),
   _ => Fail("The user said no to this. Don't try it again; if you need it, ask them in your reply.") };
 }
 static string? wentAhead; // the last countdown that ran out: a Cancel for it came too late, and the user hears that
 // A card in the chat's tray; for a sensitive step allowed without asking, 8 seconds to cancel it instead.
 static async Task<string> Approve(ChatRun run, string what, string site, string action, string why, bool countdown)
 {
  var card = new Approval(Convert.ToHexString(RandomNumberGenerator.GetBytes(4)).ToLowerInvariant(), what, site, action, why, countdown ? DateTime.UtcNow.AddSeconds(8) : null, new(TaskCreationOptions.RunContinuationsAsynchronously));
  run.Approvals.Add(card); PublishAiEverywhere();
  if (!countdown) TaskState(run, "waiting", "approval", what + " on " + site);
  // The card's Cancel goes at 8 s. Half a second more, so a click already on its way still stops the step.
  await Task.WhenAny(card.Answer.Task, Task.Delay(countdown ? TimeSpan.FromSeconds(8.5) : TimeSpan.FromMinutes(10)));
  string answer = card.Answer.Task.IsCompleted ? await card.Answer.Task : countdown ? "go" : "timeout";
  if (answer == "go") wentAhead = card.Id;
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
  if (tool is "run_plugin_action" or "get_plugin_tools" or "find_plugins" or "list_connected_plugins" or "run_plugin_program") return "";
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
 static async Task MouseClick(CoreWebView2 core, double x, double y, AgentStep step)
 {
  foreach (var type in new[] { "mouseMoved", "mousePressed", "mouseReleased" }) {
   if (type == "mousePressed") { await Js(core, MarkJs, new { }); step.Live(); } // what hovering changed doesn't count as the click's doing
   await core.CallDevToolsProtocolMethodAsync("Input.dispatchMouseEvent", JsonSerializer.Serialize(new { type, x, y, button = type == "mouseMoved" ? "none" : "left", clickCount = type == "mouseMoved" ? 0 : 1 }));
  }
 }
 /// Sends input and makes sure the page got it. A page that has just loaded out of view can drop input without a word;
 /// nothing reached it, so sending it again can't do anything twice.
 static async Task Deliver(CoreWebView2 core, AgentStep step, Func<Task> send)
 {
  for (int tries = 0; tries < 8; tries++) {
   step.Live();
   await send();
   for (int i = 0; i < 4; i++) {
    if ((await Js(core, GotJs, new { })).ValueKind != JsonValueKind.False) return;
    await Task.Delay(50);
   }
   await Task.Delay(250);
  }
 }
 /// A step that ran but can't say it worked: how its chat row reads, in place of the tool's usual words. It ends with no tick.
 static string Unverified(string who, string doingWord, string words, string message)
 {
  if (runs.GetValueOrDefault(who)?.Chat.Messages.LastOrDefault(m => m is { Role: "tool", Status: "working" } && Says(m.Text, doingWord)) is { } step) { step.Text = words; step.Status = "failed"; }
  return JsonSerializer.Serialize(new { ok = false, error = message, unverified = true });
 }
 const string CheckFirst = "It may still be working: call read_page to check before trying again, and don't repeat a purchase, send or delete without checking. A canvas or video can change without Still seeing it, so take a screenshot there.";
 /// Did the action work? Its watcher says whether the event reached the element and what changed after. Null means it went
 /// through; otherwise this is the failure to send back. key: the key pressed, "" for a click.
 /// ponytail: a page that changes by itself (a clock, a carousel) reads as changed. The event still had to reach the element.
 static async Task<string?> Verdict(string who, BrowserTab t, CoreWebView2 core, string tabBefore, string urlBefore, string key, string name, AgentStep step)
 {
  DateTime from = DateTime.UtcNow.AddSeconds(-1), started = DateTime.UtcNow;
  bool Moved() => t.Closed || t.Url != urlBefore || agentTabs.GetValueOrDefault(who) != tabBefore || t.DownloadStartedAt > from;
  JsonElement seen = default;
  string[] changed = [];
  bool Flag(string f) => seen.ValueKind == JsonValueKind.Object && seen.TryGetProperty(f, out var v) && v.ValueKind == JsonValueKind.True;
  for (;;) {
   var now = await Js(core, SeenJs, new { key });
   if (step.Abandoned) return null; // its answer is already out, and the watcher may be the next step's by now
   if (now.ValueKind != JsonValueKind.Object) { if (t.Loading || Moved()) { await WaitLoaded(t, 8000); return null; } }
   else if (now.TryGetProperty("gone", out _)) { await WaitLoaded(t, 8000); break; } // a new document: it navigated
   else {
    seen = now;
    if (Str(now, "blocked").Length > 0) break;
    changed = [.. now.GetProperty("changed").EnumerateArray().Select(c => c.GetString() ?? "")];
    if (Str(now, "invalid").Length > 0 && !Flag("submitted")) break;
    if (key.Length == 0 && Str(now, "missed").Length > 0 && !Flag("pressed")) break; // it landed on something else
   }
   if (Moved() || changed.Length > 0 && !t.Loading) break;
   double waited = (DateTime.UtcNow - started).TotalMilliseconds;
   if (waited > (t.Loading ? 8000 : Flag("submitted") ? 5000 : key.Length > 0 ? (key.Contains("Enter", StringComparison.OrdinalIgnoreCase) ? 2000 : 1200) : Flag("reached") || Flag("pressed") ? 2000 : 800)) break;
   await Task.Delay(100);
  }
  if (t.Loading) await WaitLoaded(t, 8000);
  if (step.Abandoned) return null;
  if (!t.Closed) try { await Js(core, SeenJs, new { key, last = true }); } catch (InvalidOperationException) { }
  if (Str(seen, "blocked") == "before") throw new PageChanged(); // nothing reached the page: ask again
  if (Str(seen, "blocked") == "during") return Unverified(who, key.Length > 0 ? "Pressing" : "Clicking", "Stopped: the page changed", $"The page changed during the {(key.Length > 0 ? "key press" : "click")}, so Still stopped it partway. {CheckFirst}");
  bool moved = Moved() || seen.ValueKind == JsonValueKind.Object && changed.Contains("url");
  string invalid = Str(seen, "invalid"), action = key.Length > 0 ? "pressing " + key : "clicking “" + name + "”", doing = key.Length > 0 ? "Pressing" : "Clicking";
  if (key.Length == 0 && Str(seen, "missed") is { Length: > 0 } missed && !Flag("pressed")) return Fail($"The click didn't reach \"{name}\": it landed on {missed}. Call read_page to see the page now.");
  if (invalid.Length > 0 && !Flag("submitted") && !moved) return Unverified(who, doing, "Form not sent after " + action, $"The form wasn't sent: {invalid}. Fix that field first.");
  if (moved || seen.ValueKind != JsonValueKind.Object) return null;
  if (changed.Length > 0 && (key.Length > 0 || Flag("reached") || Flag("pressed"))) return null;
  if (Flag("submitted")) return Unverified(who, doing, "No change after " + action, $"The form went out, but the page didn't change in 5 seconds, so Still can't say it worked. {CheckFirst}");
  if (key.Length > 0) return Flag("keyed") ? Unverified(who, doing, "No change after " + action, $"Pressed {key}, but nothing on the page changed, so Still can't say it did anything. {CheckFirst}")
   : Fail($"The page didn't get the {key} key. Click the field first, or call read_page.");
  return Flag("reached") ? Unverified(who, doing, "No change after " + action, $"Clicked \"{name}\", but nothing on the page changed in 2 seconds, so Still can't say it worked. {CheckFirst}")
   : Fail($"The click didn't reach \"{name}\", so nothing was clicked. Call read_page to see the page now.");
 }
 /// Types text one key at a time; a new line is Enter where the field has lines.
 static async Task TypeKeys(CoreWebView2 core, string text, bool multiline, Worker me, AgentStep step)
 {
  foreach (var r in text.ReplaceLineEndings("\n").EnumerateRunes()) {
   string s = r.ToString();
   if (me.Paused || step.Abandoned) return; // the user took over mid-word
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

 async Task<string> RunTool(string who, string tool, JsonElement args, bool quick, AgentStep step)
 {
  switch (tool) {
   case "ask_user": return await AskInChat(who, args);
   case "offer_routine": return await OfferRoutine(who, args);
   case "ask_companion" or "tell_companion" or "list_companions": return await Exchange(who, tool, args);
   case "list_connected_plugins" or "find_plugins" or "get_plugin_tools" or "run_plugin_action": return await PluginTool(who, tool, args);
   case "remember" or "recall" or "forget" or "update_knowledge" or "read_knowledge" or "open_memory_source": return Remembering(who, tool, args);
   case "run_plugin_program": return await PluginProgram(who, args);
   case "load_skill": {
    // Only a skill the companion has; never matched by keyword. The step shows only when one loads.
    var run = runs.GetValueOrDefault(who);
    var mine = run == null ? null : Companions.FirstOrDefault(c => c.Id == run.Chat.Companion);
    string id = S(args, "id").Trim().TrimStart('/');
    if (mine == null || !mine.Skills.Contains(id) || Skill.All.FirstOrDefault(k => k.Id == id) is not { } skill)
     return Fail($"You don't have a skill with the id \"{id}\". Use an id from your skills listed at the start of the chat, or carry on without one.");
    if (skill.Source.Length > 0 && ExchangeOf(run!.Chat).Root is var fromWeb) fromWeb.Read = Math.Max(fromWeb.Read, 1); // someone else's text, like a page
    Step(run!.Chat, "Used skill " + skill.Name); PublishAiEverywhere();
    return Reply(new { skill = skill.Name, instructions = skill.Body, plugin = skill.Plugin.Length == 0 ? null : new { id = skill.Plugin, programs = Programs(skill.Plugin),
     howTo = "Run these with run_plugin_program: this plugin id, the program's path from this list and its arguments. Where the steps run one in a terminal, like python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/x.py\" <link>, call run_plugin_program with scripts/x.py and [\"<link>\"] instead. Other terminal commands aren't available." } });
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
    return Reply(Windows.Where(w => !w.closing).SelectMany((w, wi) => w.tabs.Where(t => Incognito(who) ? (t.InChat ?? t.RunChat) == who : !t.Private && !OutOfProfile(who, t)).Select(t => new { tabId = t.Id, title = t.Title, url = t.Url, active = t == w.active ? true : (bool?)null, yours = agentTabs.GetValueOrDefault(who) == t.Id ? true : (bool?)null, window = wi + 1 })));
   case "web_search": return await WebSearch(who, args);
   case "read_url": return await ReadUrl(who, args, step);
   case "read_attachment": return ReadAttachment(who, S(args, "id"), (int)Math.Max(0, N(args, "offset", 0)));
   case "open_tab": {
    bool background = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("background", out var bg) && bg.ValueKind is JsonValueKind.True or JsonValueKind.False ? bg.GetBoolean() : runs.ContainsKey(who);
    var tab = await (ChatRunner(who) ?? this).OpenAgentTab(who, WebUrl(S(args, "url"), Prefs.SearchEngine, WorkFolder(who)), background); await WaitLoaded(tab);
    Did(who, "Opened " + Host(tab.Url)); return Reply(new { tabId = tab.Id, title = tab.Title, url = tab.Url });
   }
   case "navigate": {
    var (w, t, core) = await AgentPage(who, args); step.Live(); core.Navigate(WebUrl(S(args, "url"), Prefs.SearchEngine, WorkFolder(who))); await WaitLoaded(t);
    if (t.ShowingError) return Fail("That page didn't load: " + Host(S(args, "url")) + ". Check the address, or try again.");
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
    step.Live();
    if (tool == "go_back") { if (!core.CanGoBack) return Fail("There's no earlier page in this tab."); core.GoBack(); }
    else if (tool == "go_forward") { if (!core.CanGoForward) return Fail("There's no later page in this tab."); core.GoForward(); }
    else core.Reload();
    await WaitLoaded(t); Did(who, tool == "reload" ? "Reloaded the page" : tool == "go_back" ? "Went back" : "Went forward"); return Reply(new { url = t.Url, title = t.Title });
   }
   case "read_page": {
    var (w, t, core) = await AgentPage(who, args);
    var page = await Js(core, SnapshotJs, new { text = !(args.ValueKind == JsonValueKind.Object && args.TryGetProperty("text", out var tx) && (tx.ValueKind == JsonValueKind.False || tx.ValueKind == JsonValueKind.String && tx.GetString() == "false")), all = B(args, "all"), offset = (int)Math.Max(0, N(args, "offset", 0)) });
    string seen = RedactLogins(core.Source, page.GetString() ?? ""), site = Host(t.Url), back = Me(who) is { SignedIn: var done } && done.Site == site && DateTime.UtcNow - done.At < TimeSpan.FromMinutes(2) ? "signed in" : "";
    if (back.Length == 0 && await core.RunInOwnWorld("[...document.querySelectorAll('input[type=password]')].some(e=>e.getClientRects().length&&!e.disabled)") == "true") { await AskToSignIn(who, w, t, site); seen += "\n\n" + SigningIn(site); }
    Did(who, "Read " + Host(t.Url)); return Reply(new { text = seen });
   }
   case "find": {
    var (w, t, core) = await AgentPage(who, args);
    var found = await Js(core, FindJs, new { text = S(args, "text") });
    Did(who, "Looked for \"" + S(args, "text") + "\""); return Reply(new { text = RedactLogins(core.Source, found.GetString() ?? "") });
   }
   case "screenshot": {
    var (w, t, core) = await AgentPage(who, args);
    // A page only paints while it's shown: one out of sight is shown under the interface, which covers the whole window,
    // just for the picture. It never comes to the front and your tab stays where it is.
    var under = t.View is { Visibility: not Visibility.Visible } hidden ? hidden : null;
    if (under != null) {
     if (core.IsSuspended) core.Resume();
     if (under.Handle != IntPtr.Zero) SetWindowPos(under.Handle, new IntPtr(1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010); // the bottom of the pile
     under.Visibility = Visibility.Visible;
     if (under.Handle != IntPtr.Zero) SetWindowPos(under.Handle, new IntPtr(1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010);
     await Task.Delay(300);
    }
    using var ms = new MemoryStream();
    var prints = LoginPrints(core.Source); // fields showing a saved login are masked in the picture
    try {
     if (prints.Length > 0 && (await Js(core, MaskJs, new { prints, on = true })).ValueKind != JsonValueKind.True) return Fail("Couldn't hide the saved login on this page, so no screenshot was taken.");
     await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, ms);
    }
    finally { if (prints.Length > 0) await Js(core, MaskJs, new { prints, on = false }); if (under != null) w.ShowPage(); }
    Did(who, "Took a screenshot"); return Reply(new { image = Convert.ToBase64String(ms.ToArray()), mimeType = "image/png" });
   }
   case "click": {
    var (w, t, core) = await AgentPage(who, args);
    var hit = await Settled(t, core, () => Js(core, ClickJs, new { id = Id(args), selector = S(args, "selector"), text = S(args, "text"), expect = step.Print }));
    double x = hit.GetProperty("x").GetDouble(), y = hit.GetProperty("y").GetDouble();
    string label = Str(hit, "label"), before = agentTabs.GetValueOrDefault(who) ?? "";
    await Pointer(who, t, core, x, y);
    t.AgentActedAt = DateTime.UtcNow;
    string urlBefore = t.Url;
    await Deliver(core, step, () => MouseClick(core, x, y, step));
    // The chat's step only had the element's number from the AI's call ("Clicking element 7"): name what it was. The AI
    // may have sent more calls in the same breath, so it isn't always the last step.
    string numbered = "Clicking element " + (args.TryGetProperty("id", out var raw) ? raw.ValueKind == JsonValueKind.String ? raw.GetString() : raw.GetRawText() : "");
    if (label.Length > 0 && runs.GetValueOrDefault(who)?.Chat.Messages.LastOrDefault(m => m.Role == "tool" && m.Text == numbered) is { } row) row.Text = "Clicking “" + label + "”";
    if (await Verdict(who, t, core, before, urlBefore, "", label, step) is { } missed) return missed;
    Did(who, "Clicked '" + label + "'"); return Reply(Outcome(who, t, before, "Clicked \"" + label + "\""));
   }
   case "type": {
    var (w, t, core) = await AgentPage(who, args);
    string text = S(args, "text"), before = agentTabs.GetValueOrDefault(who) ?? "";
    if (text.Trim().Length >= 4) runs.GetValueOrDefault(who)?.Typed.Add(text.Trim());
    object Q(bool clicked) => new { id = Id(args), selector = S(args, "selector"), value = text, append = B(args, "append"), clicked, expect = step.Print };
    var focus = await Settled(t, core, () => Js(core, FocusJs, Q(false)));
    t.AgentActedAt = DateTime.UtcNow;
    if (Str(focus, "done") is { Length: > 0 } picked) { Did(who, picked); return Reply(new { done = picked }); }
    if (focus.TryGetProperty("at", out var at) && at.ValueKind == JsonValueKind.Object) {
     await Pointer(who, t, core, at.GetProperty("x").GetDouble(), at.GetProperty("y").GetDouble());
     if (step.Print.Length > 0) await Js(core, SameJs, new { expect = step.Print });
     await MouseClick(core, at.GetProperty("x").GetDouble(), at.GetProperty("y").GetDouble(), step);
     focus = await Js(core, FocusJs, Q(true)); // the click moved the caret: put it back
    }
    else if (focus.TryGetProperty("near", out var near) && near.ValueKind == JsonValueKind.Object)
     await Pointer(who, t, core, near.GetProperty("x").GetDouble(), near.GetProperty("y").GetDouble());
    async Task<bool> Unchanged() => Str(await Js(core, SigJs, new { }), "sig") == Str(focus, "sig");
    step.Live();
    if (step.Print.Length > 0) await Js(core, SameJs, new { expect = step.Print }); // nothing typed yet: a change asks again
    if (text.Length > 0) {
     await core.CallDevToolsProtocolMethodAsync("Input.insertText", JsonSerializer.Serialize(new { text }));
     // Some editors ignore inserted text and only take key presses: type it key by key.
     if (text.Length <= 4000 && await Unchanged()) { await Js(core, FocusJs, Q(true)); await TypeKeys(core, text, focus.GetProperty("multiline").GetBoolean(), Me(who), step); }
     if (await Unchanged()) return Fail("Typed, but \"" + Str(focus, "label") + "\" didn't change. Click it first, then type without an id, or use press_key.");
    }
    else if (!B(args, "append")) await PressKey(core, "Backspace");
    string field = Str(focus, "label");
    if (B(args, "submit")) {
     string urlBefore = t.Url;
     // Already typed, so a change here stops with Enter unpressed instead of starting over.
     try {
      await Js(core, WatchJs, new { expect = step.Print }); await Deliver(core, step, () => PressKey(core, "Enter"));
      if (await Verdict(who, t, core, before, urlBefore, "Enter", field, step) is { } unsent) return unsent;
     } catch (PageChanged) { return Fail("Typed into \"" + field + "\", but the page changed before Enter, so Still didn't press it. Call read_page to see it now."); }
    }
    Did(who, "Typed into " + field); return Reply(Outcome(who, t, before, (text.Length > 0 ? "Typed into \"" : "Cleared \"") + field + "\"" + (B(args, "submit") ? " and pressed Enter" : "")));
   }
   case "press_key": {
    var (w, t, core) = await AgentPage(who, args);
    string before = agentTabs.GetValueOrDefault(who) ?? "";
    t.AgentActedAt = DateTime.UtcNow;
    string urlBefore = t.Url;
    await Js(core, WatchJs, new { expect = step.Print }); await Deliver(core, step, () => PressKey(core, S(args, "key")));
    if (await Verdict(who, t, core, before, urlBefore, S(args, "key"), "", step) is { } nothing) return nothing;
    Did(who, "Pressed " + S(args, "key")); return Reply(Outcome(who, t, before, "Pressed " + S(args, "key")));
   }
   case "scroll": {
    var (w, t, core) = await AgentPage(who, args);
    step.Live();
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
    files = files.Select(f => f.Trim().Trim('"')).Where(f => f.Length > 0).Distinct().ToArray();
    if (files.Length == 0) return Fail("Pass paths: the full paths of the files to attach.");
    if (files.Length > 12) return Fail("Attach at most 12 files at a time.");
    if (files.Any(f => !LocalFilePath(f))) return Fail("Pass full paths of files on this computer, like C:\\Users\\you\\report.pdf.");
    files = files.Select(Path.GetFullPath).Distinct().ToArray();
    if (files.Any(OffLimitsFile)) return Fail("Still doesn't let an AI attach files from that folder. The user can attach it themselves.");
    object input;
    string site = Host(t.Url);
    if (Id(args).Length + S(args, "selector").Length > 0) {
     var found = await core.EvaluateInOwnWorld("((o)=>{" + PageJs + FileInputJs + "})(" + JsonSerializer.Serialize(new { id = Id(args), selector = S(args, "selector") }) + ")", byValue: false);
     if (found.ValueKind != JsonValueKind.Object || found.TryGetProperty("exceptionDetails", out _) || !found.TryGetProperty("result", out var res) || Str(res, "subtype") != "node" || !res.TryGetProperty("objectId", out var obj)) return Fail("That isn't a file upload field. Click the page's upload button instead, then call upload_file without an id.");
     input = new { files, objectId = obj.GetString() };
    } else if (t.AgentUpload is UploadRequest picker && picker.Core == core) {
     if (!picker.Multiple && files.Length > 1) return Fail("This file picker takes one file.");
     input = new { files, backendNodeId = picker.Node };
    } else return Fail("No file picker is open. Click the page's upload button first (Still catches the picker for you), or pass the id of a file input.");
    string names = string.Join(", ", files.Select(Path.GetFileName));
    string ask = "upload " + (files.Length == 1 ? "this file: " : files.Length + " files: ") + string.Join(", ", files) + " to " + site;
    switch (await AskUser(who, ask, quick)) {
     case false: return Fail("The user didn't allow this upload. Don't try again unless they ask.");
     case null: return Fail("Waiting for the user to allow the upload: Still shows Allow and Block at the top of its window. Tell the user, then call upload_file again.");
    }
    if (Host(t.Url) != site) return Fail("The page went to another site while the user was being asked, so nothing was attached.");
    if (files.FirstOrDefault(f => !File.Exists(f)) is { } missing) return Fail("There's no file at " + missing);
    step.Live();
    await core.CallDevToolsProtocolMethodAsync("DOM.setFileInputFiles", JsonSerializer.Serialize(input));
    t.AgentUpload = null;
    Did(who, "Attached " + names); return Reply(new { done = "Attached " + names });
   }
   default: return Fail("Unknown tool: " + tool);
  }
 }
}
