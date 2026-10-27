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
 static string agentName = "", agentAction = "";
 static DateTime agentSeen;
 // One question in the agent bar at a time: letting a new agent in, or an action that needs the user's OK (uploads).
 static TaskCompletionSource<bool>? agentApproval;
 static string askClient = "", askText = "";
 static (string Client, string Ask, bool Allow, DateTime At) lastAnswer;
 // Ends an agent's running call early with this reply: a dialog or file picker opened in its tab, or the user pressed Stop.
 static readonly Dictionary<string, TaskCompletionSource<string>> agentInterrupts = new(StringComparer.OrdinalIgnoreCase);
 static bool agentServerStarted;
 static MainWindow Home => LastActive is { closing: false } w ? w : Windows.First(w => !w.closing);

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
   string tool = root.GetProperty("tool").GetString() ?? "";
   var args = root.TryGetProperty("args", out var a) && a.ValueKind == JsonValueKind.Object ? a.Clone() : default;
   if (!Prefs.AgentsEnabled) return Fail("AI control is turned off. The user can turn it on in Still → Settings → Let other AI apps use Still.");
   if (tool == "user_confirmed") return Confirmed(client, args);
   // Don't keep the agent waiting on a bar nobody will see: its app can ask the user (elicitation), or the user is away.
   bool quick = root.TryGetProperty("elicit", out var el) && el.ValueKind == JsonValueKind.True || UserAway();
   if (blockedAgents.Contains(client)) return Fail("The user blocked this agent in Still for this session.");
   if (stoppedAgents.TryGetValue(client, out var until) && DateTime.UtcNow < until) return Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message.");
   if (Prefs.ApprovedAgents.Any(a => McpServer.AgentName(a).Equals(client, StringComparison.OrdinalIgnoreCase))) approvedAgents.Add(client); // approved once = remembered across restarts/updates
   if (!approvedAgents.Contains(client)) switch (await AskUser(client, "", quick)) {
    case false: return Fail("The user blocked this agent in Still for this session.");
    case null: return NeedsConfirm(client, "", "Waiting for the user to let you in: Still shows a bar with Allow and Block at the top of its window. Tell the user to click Allow, then call the tool again.");
   }
   agentName = client; agentSeen = DateTime.UtcNow;
   var interrupt = agentInterrupts[client] = new(TaskCreationOptions.RunContinuationsAsynchronously);
   var run = RunTool(client, tool, args, quick);
   int limit = tool switch { "wait_for" => (int)Math.Clamp(N(args, "timeoutMs", 10000), 100, 30000) + 5000, "upload_file" => 60000, _ => 30000 };
   var first = await Task.WhenAny(run, interrupt.Task, Task.Delay(limit));
   string result = first == run ? await run : first == interrupt.Task ? await interrupt.Task
    : Fail($"{tool} didn't finish within {limit / 1000} s, so Still stopped waiting. The page may be slow or stuck: call read_page to see where it is.");
   if (agentInterrupts.GetValueOrDefault(client) == interrupt) agentInterrupts.Remove(client);
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
 object? AgentData() => agentApproval != null ? new { client = askClient, pending = true, action = "", ask = askText }
  : approvedAgents.Contains(agentName) && DateTime.UtcNow - agentSeen < TimeSpan.FromMinutes(2) ? new { client = agentName, pending = false, action = agentAction, ask = "" } : null;
 // Stop cancels what the agent is doing now; it stays allowed, so its next task needs no new approval.
 void StopAgent() {
  if (agentName.Length > 0) {
   ReleaseAgentTabs(agentName); stoppedAgents[agentName] = DateTime.UtcNow.AddSeconds(30);
   if (agentInterrupts.Remove(agentName, out var running)) running.TrySetResult(Fail("The user pressed Stop. Stop what you are doing and wait for the user's next message."));
  }
  foreach (var w in Windows) if (w.aiBusy && AiClis.FirstOrDefault(c => c.Id == (w.aiChat?.Harness ?? "")) is { } cli && cli.Name == agentName) _ = w.HandleAi("aiStop", default);
  agentAction = ""; agentSeen = DateTime.MinValue; PublishAll(); Toast("Stopped " + (agentName.Length > 0 ? agentName : "the AI agent") + ".");
 }
 static readonly Dictionary<string, DateTime> stoppedAgents = new(StringComparer.OrdinalIgnoreCase);
 /// A dialog or file picker opened in the tab an agent is working in: its running call returns now and says so.
 static void InterruptAgent(BrowserTab t, object reply)
 {
  if (t.Agent is { } who && agentTabs.GetValueOrDefault(who) == t.Id && agentInterrupts.Remove(who, out var running)) running.TrySetResult(Reply(reply));
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
   if ((label(e) + ' ' + (e.value || '') + ' ' + (e.getAttribute('href') || '') + ' ' + (e.title || '')).toLowerCase().includes(want)) out.push(line(e));
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
  return { label: label(e) || kind(e), sig: sig(deepActive()), multiline: e.isContentEditable || e.localName === 'textarea', at };
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
 const string FileInputJs = """
  const e = target(o); return e && e.localName === 'input' && e.type === 'file' ? e : e?.querySelector?.('input[type=file]') || e?.closest?.('label')?.control || null;
 """;

 static async Task<JsonElement> Js(CoreWebView2 core, string body, object o)
 {
  string json = await core.RunAsync("((o)=>{try{" + PageJs + body + "}catch(err){return {error:'script',message:String(err&&err.message||err)}}})(" + JsonSerializer.Serialize(o) + ")");
  using var doc = JsonDocument.Parse(json);
  var r = doc.RootElement.Clone();
  if (r.ValueKind == JsonValueKind.Object && r.TryGetProperty("error", out var err)) throw new InvalidOperationException(err.GetString() switch {
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
 static string Str(JsonElement e, string key) => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

 // Finds a tab the agent may use: never private tabs.
 (MainWindow window, BrowserTab tab) AgentTab(string who, JsonElement args)
 {
  // Without a tabId the agent keeps working in the tab it used last, even after the user switches to another one.
  string id = S(args, "tabId");
  if (id.Length == 0 && agentTabs.TryGetValue(who, out var last) && FindTab(last) != null) id = last;
  foreach (var w in Windows.Where(w => !w.closing)) {
   var t = id.Length > 0 ? w.tabs.FirstOrDefault(x => x.Id == id) : (w == this ? w.active : null);
   if (t != null) { if (t.Private) throw new InvalidOperationException("Private tabs are off-limits to agents."); Claim(who, w, t); return (w, t); }
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
 static readonly Dictionary<string, string> agentTabs = []; // agent name -> the tab it is working in
 static void Claim(string who, MainWindow w, BrowserTab t)
 {
  agentTabs[who] = t.Id; t.LastActive = DateTime.UtcNow; // in use: memory saver leaves it awake
  if (t.Agent != who) { t.Agent = who; w.ShellPublish(); }
 }
 /// The agent's work is done: its icon leaves the user's own tabs. Tabs it opened stay in the AI group.
 internal static void ReleaseAgentTabs(string name)
 {
  agentTabs.Remove(name);
  foreach (var w in Windows) { bool changed = false; foreach (var t in w.tabs.Where(t => t.Agent == name && !t.AgentGroup)) { t.Agent = null; changed = true; } if (changed) w.ShellPublish(); }
 }
 // Opens in the background, next to the other AI tabs, so the user can keep browsing.
 async Task<BrowserTab> OpenAgentTab(string who, string url)
 {
  var tab = new BrowserTab { Url = url, Title = Host(url), Agent = who, AgentGroup = true };
  int last = tabs.FindLastIndex(t => t.AgentGroup);
  tabs.Insert(last >= 0 ? last + 1 : tabs.Count, tab);
  if (active == null || active.Url.Length == 0 && !active.Pinned && tabs.Count == 2) await SelectTab(tab); // nothing to keep the user on
  Claim(who, this, tab); ShellPublish(); SaveLater();
  await EnsureView(tab);
  return tab;
 }
 static async Task<CoreWebView2> Core(MainWindow w, BrowserTab t)
 {
  if (t.View?.CoreWebView2 == null) await w.EnsureView(t);
  return t.View?.CoreWebView2 ?? throw new InvalidOperationException("The tab couldn't be loaded.");
 }
 static async Task WaitLoaded(BrowserTab t, int ms = 15000)
 {
  var until = DateTime.UtcNow.AddMilliseconds(ms);
  await Task.Delay(250);
  while (t.Loading && DateTime.UtcNow < until) await Task.Delay(100);
 }
 static string WebUrl(string input, string engine)
 {
  var url = ResolveAddress(input, engine);
  if (!Uri.TryCreate(url, UriKind.Absolute, out var u) || u.Scheme is not ("http" or "https")) throw new InvalidOperationException("Agents can only open http and https pages.");
  return url;
 }
 void Did(string action) => agentAction = action.Length > 90 ? action[..90] + "…" : action;
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
 static async Task TypeKeys(CoreWebView2 core, string text, bool multiline)
 {
  foreach (var r in text.ReplaceLineEndings("\n").EnumerateRunes()) {
   string s = r.ToString();
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
   case "list_tabs":
    return Reply(Windows.Where(w => !w.closing).SelectMany((w, wi) => w.tabs.Where(t => !t.Private).Select(t => new { tabId = t.Id, title = t.Title, url = t.Url, active = t == w.active ? true : (bool?)null, yours = agentTabs.GetValueOrDefault(who) == t.Id ? true : (bool?)null, window = wi + 1 })));
   case "open_tab": {
    var tab = await OpenAgentTab(who, WebUrl(S(args, "url"), Prefs.SearchEngine)); await WaitLoaded(tab);
    Did("Opened " + Host(tab.Url)); return Reply(new { tabId = tab.Id, title = tab.Title, url = tab.Url });
   }
   case "navigate": {
    var (w, t, core) = await AgentPage(who, args); core.Navigate(WebUrl(S(args, "url"), Prefs.SearchEngine)); await WaitLoaded(t);
    Did("Went to " + Host(t.Url)); return Reply(new { tabId = t.Id, title = t.Title, url = t.Url });
   }
   case "switch_tab": {
    var (w, t) = AgentTab(who, args);
    if (B(args, "show")) { await w.SelectTab(t); w.Activate(); }
    Did("Switched to " + t.Title); return Reply(new { tabId = t.Id, title = t.Title, url = t.Url });
   }
   case "close_tab": { var (w, t) = AgentTab(who, args); await w.CloseTab(t, true); agentTabs.Remove(who); Did("Closed a tab"); return Reply(new { done = "Closed the tab" }); }
   case "go_back": case "go_forward": case "reload": {
    var (w, t, core) = await AgentPage(who, args);
    if (tool == "go_back") { if (!core.CanGoBack) return Fail("There's no earlier page in this tab."); core.GoBack(); }
    else if (tool == "go_forward") { if (!core.CanGoForward) return Fail("There's no later page in this tab."); core.GoForward(); }
    else core.Reload();
    await WaitLoaded(t); Did(tool == "reload" ? "Reloaded the page" : tool == "go_back" ? "Went back" : "Went forward"); return Reply(new { url = t.Url, title = t.Title });
   }
   case "read_page": {
    var (w, t, core) = await AgentPage(who, args);
    var page = await Js(core, SnapshotJs, new { text = !(args.ValueKind == JsonValueKind.Object && args.TryGetProperty("text", out var tx) && (tx.ValueKind == JsonValueKind.False || tx.ValueKind == JsonValueKind.String && tx.GetString() == "false")), all = B(args, "all"), offset = (int)Math.Max(0, N(args, "offset", 0)) });
    Did("Read " + Host(t.Url)); return Reply(new { text = page.GetString() ?? "" });
   }
   case "find": {
    var (w, t, core) = await AgentPage(who, args);
    var found = await Js(core, FindJs, new { text = S(args, "text") });
    Did("Looked for \"" + S(args, "text") + "\""); return Reply(new { text = found.GetString() ?? "" });
   }
   case "screenshot": {
    var (w, t, core) = await AgentPage(who, args);
    // A page only paints while it's on screen: show it for a moment, then give the user their tab back.
    var previous = w.active;
    if (t != previous) { await w.SelectTab(t); await Task.Delay(200); }
    using var ms = new MemoryStream();
    try { await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, ms); }
    finally { if (previous != null && previous != t && !previous.Closed && w.active == t) await w.SelectTab(previous); }
    Did("Took a screenshot"); return Reply(new { image = Convert.ToBase64String(ms.ToArray()), mimeType = "image/png" });
   }
   case "click": {
    var (w, t, core) = await AgentPage(who, args);
    var hit = await Js(core, ClickJs, new { id = Id(args), selector = S(args, "selector"), text = S(args, "text") });
    double x = hit.GetProperty("x").GetDouble(), y = hit.GetProperty("y").GetDouble();
    string label = Str(hit, "label"), before = agentTabs.GetValueOrDefault(who) ?? "";
    t.AgentActedAt = DateTime.UtcNow;
    await MouseClick(core, x, y);
    await WaitLoaded(t, 8000);
    Did("Clicked '" + label + "'"); return Reply(Outcome(who, t, before, "Clicked \"" + label + "\""));
   }
   case "type": {
    var (w, t, core) = await AgentPage(who, args);
    string text = S(args, "text"), before = agentTabs.GetValueOrDefault(who) ?? "";
    object Q(bool clicked) => new { id = Id(args), selector = S(args, "selector"), value = text, append = B(args, "append"), clicked };
    var focus = await Js(core, FocusJs, Q(false));
    t.AgentActedAt = DateTime.UtcNow;
    if (Str(focus, "done") is { Length: > 0 } picked) { Did(picked); return Reply(new { done = picked }); }
    if (focus.TryGetProperty("at", out var at) && at.ValueKind == JsonValueKind.Object) {
     await MouseClick(core, at.GetProperty("x").GetDouble(), at.GetProperty("y").GetDouble());
     focus = await Js(core, FocusJs, Q(true)); // the click moved the caret: put it back
    }
    async Task<bool> Unchanged() => Str(await Js(core, SigJs, new { }), "sig") == Str(focus, "sig");
    if (text.Length > 0) {
     await core.CallDevToolsProtocolMethodAsync("Input.insertText", JsonSerializer.Serialize(new { text }));
     // Some editors ignore inserted text and only take key presses: type it key by key.
     if (text.Length <= 4000 && await Unchanged()) { await Js(core, FocusJs, Q(true)); await TypeKeys(core, text, focus.GetProperty("multiline").GetBoolean()); }
     if (await Unchanged()) return Fail("Typed, but \"" + Str(focus, "label") + "\" didn't change. Click it first, then type without an id, or use press_key.");
    }
    else if (!B(args, "append")) await PressKey(core, "Backspace");
    if (B(args, "submit")) await PressKey(core, "Enter");
    await WaitLoaded(t, B(args, "submit") ? 8000 : 0);
    string field = Str(focus, "label");
    Did("Typed into " + field); return Reply(Outcome(who, t, before, (text.Length > 0 ? "Typed into \"" : "Cleared \"") + field + "\"" + (B(args, "submit") ? " and pressed Enter" : "")));
   }
   case "press_key": {
    var (w, t, core) = await AgentPage(who, args);
    string before = agentTabs.GetValueOrDefault(who) ?? "";
    t.AgentActedAt = DateTime.UtcNow;
    await PressKey(core, S(args, "key")); await WaitLoaded(t, 8000);
    Did("Pressed " + S(args, "key")); return Reply(Outcome(who, t, before, "Pressed " + S(args, "key")));
   }
   case "scroll": {
    var (w, t, core) = await AgentPage(who, args);
    var r = await Js(core, ScrollJs, new { id = Id(args), selector = S(args, "selector"), direction = S(args, "direction"), amount = Math.Clamp(N(args, "amount", 0), 0, 20000) });
    Did(Str(r, "done")); return Reply(new { done = Str(r, "done"), at = Str(r, "at") is { Length: > 0 } at ? at : null });
   }
   case "wait_for": {
    var (w, t, core) = await AgentPage(who, args);
    var q = new { id = Id(args), selector = S(args, "selector"), text = S(args, "text"), gone = B(args, "gone") };
    if (q.id.Length + q.selector.Length + q.text.Length == 0) return Fail("Pass an id, selector or text to wait for.");
    var until = DateTime.UtcNow.AddMilliseconds(Math.Clamp(N(args, "timeoutMs", 10000), 100, 30000));
    while (true) {
     if ((await Js(core, WaitJs, q)).ValueKind == JsonValueKind.True) { Did("Waited for the page"); return Reply(new { found = !q.gone, done = q.gone ? "It's gone" : "It's there", url = t.Url }); }
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
    Did(accept ? "Accepted a dialog" : "Dismissed a dialog"); return Reply(Outcome(who, t, before, accept ? "Accepted the dialog" : "Dismissed the dialog"));
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
    Did("Attached " + names); return Reply(new { done = "Attached " + names });
   }
   default: return Fail("Unknown tool: " + tool);
  }
 }
}
