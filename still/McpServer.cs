using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Still;

// `Still.exe --mcp`: a Model Context Protocol server over stdio (JSON-RPC, one message per line).
// AI apps launch it; it forwards tool calls to the running Still over a current-user-only pipe.
internal static class McpServer
{
 internal static readonly object[] BrowserTools = [
  Tool("list_tabs", "List the open tabs (never private ones) with their tabIds. `yours` marks the tab you're working in.", new { }),
  Tool("web_search", "Search the web and get the results (title, URL, snippet) without opening a tab. Start here for questions and research; open a tab only to click, type, sign in or show the user something.", new { query = Str("What to search for"), count = Num("How many results, up to 10 (default 8)") }, "query"),
  Tool("read_attachment", "Read a file the user attached to their message, by the id Still gave you: text and code come back as text (20000 characters at a time), PDFs as their text, images as the image itself.", new { id = Str("The attachment's id"), offset = Num("Text position to continue from, for long files") }, "id"),
  Tool("read_url", "Read a web page's main text without opening a tab (12000 characters at a time). For pages you only need to read; use open_tab when you have to click or type there.", new { url = Str("The page's URL"), offset = Num("Text position to continue from, for long pages") }, "url"),
  Tool("open_tab", "Open a URL or search terms in a new tab and work there from now on, to click, type or sign in. The user keeps their own tab and can keep browsing. Start most hands-on tasks here.", new { url = Str("URL or search terms"), background = Bool("true (the default in Still's chat): your own tab, kept out of the user's tab strip. false: open it among the user's tabs, only when they asked for it there") }, "url"),
  Tool("navigate", "Load a URL or search terms in your current tab (or tabId).", new { url = Str("URL or search terms"), tabId = Str("Tab id (optional)") }, "url"),
  Tool("switch_tab", "Work in another tab from now on. It stays in the background unless show is true.", new { tabId = Str("Tab id from list_tabs"), show = Bool("Bring it to the front (only when the user asked to see it)") }, "tabId"),
  Tool("close_tab", "Close your current tab (or tabId).", new { tabId = Str("Tab id (optional)") }),
  Tool("go_back", "Go back in your tab's history.", new { tabId = Str("Tab id (optional)") }),
  Tool("go_forward", "Go forward in your tab's history.", new { tabId = Str("Tab id (optional)") }),
  Tool("reload", "Reload your tab.", new { tabId = Str("Tab id (optional)") }),
  Tool("read_page", "See the page: title, URL and scroll position, then one line per button, link and field near the visible part as [id] kind \"label\" (→ link, =value, {options}, ✓/☐ checked), then the page text (8000 characters at a time). An id keeps working as long as its element is on the page.", new { text = Bool("Include the page text (default true). false = controls only, far fewer tokens"), all = Bool("List controls on the whole page, not just near the visible part"), offset = Num("Text position to continue from, for long pages"), tabId = Str("Tab id (optional)") }),
  Tool("find", "Search the page for text: the buttons, links and fields that match (with ids) and the matching lines of text, from anywhere on the page. Much cheaper than read_page on a big page.", new { text = Str("Text to look for"), tabId = Str("Tab id (optional)") }, "text"),
  Tool("click", "Click an element like a real mouse click (it's scrolled into view first). Says where you ended up, and whether a new tab, dialog or file picker opened.", new { id = Str("Element id from read_page or find"), text = Str("Or: visible text of the button or link"), selector = Str("Or: CSS selector"), tabId = Str("Tab id (optional)") }),
  Tool("type", "Type into a field, replacing what's in it (append=true adds instead). Without an id, types into the focused field. On a dropdown, picks the option with that text. submit=true presses Enter afterwards.", new { text = Str("Text to type, or the option to pick"), id = Str("Element id from read_page or find"), selector = Str("Or: CSS selector"), submit = Bool("Press Enter afterwards"), append = Bool("Add to the field's text instead of replacing it"), tabId = Str("Tab id (optional)") }, "text"),
  Tool("save_file", "Save a file for the user: a table as CSV, notes as Markdown, data as JSON, or plain text. It goes in their Library and shows in the chat as a card they can open, so don't paste its contents into your reply. Saving again with the same name replaces the one you saved. Up to 5 MB.", new { name = Str("File name with its ending, like laptops-under-800.csv"), content = Str("The whole file") }, "name", "content"),
  Tool("press_key", "Press a key in the page: Enter, Escape, Tab, ArrowDown, PageDown, Backspace, a letter, or a combination like Control+A or Shift+Tab.", new { key = Str("Key or combination"), tabId = Str("Tab id (optional)") }, "key"),
  Tool("scroll", "Scroll down or up (the page, or the scrolling panel in the middle of the view), or bring element id into view.", new { direction = new { type = "string", @enum = new[] { "down", "up" } }, amount = Num("Pixels (default: most of a screen)"), id = Str("Element id: scroll it into view, or with direction, scroll the panel it's in"), tabId = Str("Tab id (optional)") }),
  Tool("wait_for", "Wait until an element or some text appears (or, with gone=true, disappears), for up to timeoutMs.", new { text = Str("Text to wait for"), id = Str("Or: element id"), selector = Str("Or: CSS selector"), gone = Bool("Wait for it to disappear instead"), timeoutMs = Num("Up to 30000 (default 10000)"), tabId = Str("Tab id (optional)") }),
  Tool("handle_dialog", "Answer the alert, confirm, prompt or \"leave page?\" dialog the page is paused on (other tools tell you when one opens).", new { accept = Bool("true = OK / Leave, false = Cancel / Stay (default true)"), text = Str("For a prompt: the text to answer with"), tabId = Str("Tab id (optional)") }),
  Tool("upload_file", "Attach files to the file picker the page just opened (click its upload button first), or to a file input by id. Still asks the user to allow it.", new { paths = new { type = "array", items = new { type = "string" }, description = "Full paths of the files on this computer" }, id = Str("Element id of a file input (optional)"), tabId = Str("Tab id (optional)") }, "paths"),
  Tool("user_confirmed", "Only when Still told you to check with the user: after asking them in your chat, pass the code and their answer. Never answer for the user.", new { code = Str("The code Still gave you"), allow = Bool("true if the user said yes") }, "code"),
  Tool("screenshot", "PNG of the visible part of a tab. Costs far more tokens than read_page or find: use it only when how the page looks matters.", new { tabId = Str("Tab id (optional)") }),
 ];
 internal const string Instructions = "You're driving the user's own Still browser, signed in as them. "
  + "Look things up with web_search and read_url: they need no tab. For hands-on work, open_tab, so the user can keep browsing. "
  + "Use read_page to see a page (text=false when you only need its controls) and find to locate something on a big page; then click, type and press_key with the element ids. "
  + "Actions report where you ended up and any new tab, dialog or file picker, so read the page again only when you need to see what changed. "
  + "If Still says it's waiting for the user, tell the user what to click and stop until they reply. "
  + "Ask the user before buying anything, sending messages or posts, or deleting things. Private tabs, passwords and cookies are never available.";
 // Every tool can target another Still profile by name, or "temp": a fresh window with no cookies, logins or history.
 // Each profile is its own Still process with its own pipe. The AI sidebar's agent is locked to its own profile.
 static JsonArray BuildTools(bool lockProfile)
 {
  var list = JsonSerializer.SerializeToNode(BrowserTools)!.AsArray();
  // Still's own chat can show the user a question with options and wait for the answer.
  if (NoTools) return [];
  if (lockProfile) {
   // Still's own companions keep a memory of the user, on this computer, one per companion.
   list.Add(JsonSerializer.SerializeToNode(Tool("remember", "Keep one short, lasting fact about the user in your memory, like \"Prefers aisle seats\" or \"Sister Maya lives in Lisbon\". It's saved with today's date and this chat. A fact that repeats one you have updates it. Never pass passwords, codes, card or account numbers, form data or anything from private tabs: Still refuses them.", new { fact = Str("The fact, in one short sentence"), kind = Str("fact, preference, habit, person or project") }, "fact")));
   list.Add(JsonSerializer.SerializeToNode(Tool("recall", "Look up what you remember about the user: the facts that best match the words given, with their ids and dates. Leave query empty for the most important ones.", new { query = Str("A few words about what you're looking for") })));
   list.Add(JsonSerializer.SerializeToNode(Tool("update_knowledge", "Rewrite one of your knowledge files (listed at the start of the chat) with what it should hold now. Pass its whole new text in short, tidy Markdown, keeping what's still true. Never put passwords, codes, card or account numbers, form data or anything from private tabs in it: Still refuses them.", new { file = Str("The file's id, like \"deals\""), text = Str("The file's full new text, in Markdown") }, "file", "text")));
   list.Add(JsonSerializer.SerializeToNode(Tool("forget", "Forget a fact: pass its id from recall, or a few words that every fact to forget contains. Use it when the user asks you to forget something.", new { id = Str("The fact's id"), about = Str("Or: words in the facts to forget") })));
   list.Add(JsonSerializer.SerializeToNode(Tool("ask_user", "Ask the user a question in Still's chat and wait for the answer (up to 10 minutes). Use it when you need a decision you shouldn't make yourself, and before buying, sending or deleting anything. Offer 2-4 short options when you can; the user can also write their own answer.", new { question = Str("The question, in one short sentence"), options = new { type = "array", items = new { type = "string" }, description = "2-4 short answers to pick from" }, tabId = Str("When a page needs the user (a captcha, a code, signing in): that tab, so the card can open it for them") }, "question")));
   list.Add(JsonSerializer.SerializeToNode(Tool("offer_routine", "Offer to repeat something that clearly helped on a schedule. Still asks the user in the chat, and the routine is added to your profile only if they say yes. Offer it once, after a useful result.", new { text = Str("What to do each time, as an instruction to yourself"), time = Str("When, as HH:mm (24-hour)"), days = new { type = "array", items = new { type = "integer" }, description = "Days of the week: 0 = Sunday to 6 = Saturday" } }, "text", "time", "days")));
   // Teammates: the user's other companions, each with its own role, memory and tools (MainWindow.Ai.cs, Exchange).
   list.Add(JsonSerializer.SerializeToNode(Tool("list_companions", "List your teammates: the user's other companions, what each one does, and which one is you.", new { })));
   list.Add(JsonSerializer.SerializeToNode(Tool("ask_companion", "Ask a teammate something and wait for their reply (up to 10 minutes). They answer with their own role, memory and tools, and only they see your message. Say what you need and why, with what they need from you. The user sees the exchange.", new { name = Str("The teammate's name, from list_companions"), message = Str("What you're asking them"), title = Str("What you're asking for in a few words, as in \"asked Jonah for a pitch\": a pitch. The user sees it.") }, "name", "message")));
   list.Add(JsonSerializer.SerializeToNode(Tool("tell_companion", "Hand work over to a teammate without waiting: they do it in the background and their result comes back to this chat, where the user sees it. Give them everything they need to do it.", new { name = Str("The teammate's name, from list_companions"), message = Str("What they should do, with what they need from you"), title = Str("What you're asking for in a few words, as in \"asked Jonah for a pitch\": a pitch. The user sees it.") }, "name", "message")));
   // The user's own apps (Gmail, Calendar, Slack…) through Composio, once they connect them (MainWindow.Plugins.cs).
   list.Add(JsonSerializer.SerializeToNode(Tool("list_connected_plugins", "Names of the user's apps (plugins) connected for you, like Gmail or Slack. Names only: get_plugin_tools loads one app's actions.", new { })));
   list.Add(JsonSerializer.SerializeToNode(Tool("find_plugins", "Look up apps Still can connect through Composio, by name or category: each one's name, categories and whether it's connected for you.", new { query = Str("Words in the app's name (optional)"), category = Str("A category, like Productivity, Communication or Finance (optional)") })));
   list.Add(JsonSerializer.SerializeToNode(Tool("get_plugin_tools", "Load one app's actions, only when you need that app: each action's name, what it does, its inputs and whether it asks the user first.", new { plugin = Str("The app, like Gmail or Google Calendar"), query = Str("Words to narrow a long list, like send email (optional)") }, "plugin")));
   list.Add(JsonSerializer.SerializeToNode(Tool("run_plugin_action", "Run one action from get_plugin_tools. Reading goes ahead; anything that sends, posts, deletes, pays or changes data waits for the user's OK. If the app isn't connected, Still asks the user to connect it: don't guess.", new { plugin = Str("The app, like Gmail"), action = Str("The action's name from get_plugin_tools, like GMAIL_SEND_EMAIL"), args = new { type = "object", description = "The action's inputs, as get_plugin_tools describes them" } }, "plugin", "action")));
   return list; }
  foreach (var t in list) t!["inputSchema"]!["properties"]!["profile"] = JsonSerializer.SerializeToNode(Str("Still profile name from list_profiles (optional; defaults to the launch profile). A closed profile is opened. \"temp\" opens a separate temporary window with no cookies, logins or history, deleted after it closes."));
  list.Insert(0, JsonSerializer.SerializeToNode(Tool("list_profiles", "List Still's profiles (separate logins, cookies and tabs) and which are open. Pass a name as `profile` to any other tool, or \"temp\" for a clean temporary window.", new { })));
  return list;
 }

 /// The name the user sees for an agent: "Claude", not "claude-code".
 internal static string AgentName(string client)
 {
  string c = client.ToLowerInvariant();
  foreach (var (key, name) in new[] { ("claude", "Claude"), ("codex", "ChatGPT"), ("openai", "ChatGPT"), ("chatgpt", "ChatGPT"), ("grok", "Grok"), ("gemini", "Gemini"), ("cursor", "Cursor"), ("copilot", "Copilot"), ("windsurf", "Windsurf") })
   if (c.Contains(key)) return name;
  return client;
 }
 static object Str(string d) => new { type = "string", description = d };
 static object Bool(string d) => new { type = "boolean", description = d };
 static object Num(string d) => new { type = "number", description = d };
 static object Tool(string name, string description, object properties, params string[] required) =>
  new { name, description, inputSchema = new { type = "object", properties, required } };

 internal static string RunId = ""; // Still's own chat: which chat this server works for (--run)
 internal static bool NoTools; // --no-tools: a talk with no browser at all (setup's interview)
 public static void Run(string instance, string? forcedName = null, bool lockProfile = false)
 {
  string client = forcedName ?? "An AI agent";
  var tools = BuildTools(lockProfile);
  var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));
  var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };
  var running = new System.Collections.Concurrent.ConcurrentDictionary<string, CancellationTokenSource>();
  // Questions this server asks the user through their AI app (MCP elicitation), by request id.
  var asks = new System.Collections.Concurrent.ConcurrentDictionary<string, TaskCompletionSource<JsonNode?>>();
  bool canElicit = false; int asked = 0;
  void Send(JsonNode id, object? result, object? error) { string json = error != null ? JsonSerializer.Serialize(new { jsonrpc = "2.0", id, error }) : JsonSerializer.Serialize(new { jsonrpc = "2.0", id, result }); lock (stdout) stdout.WriteLine(json); }
  // "accept" or "decline", or null if the user closed it, didn't answer or the app couldn't ask.
  string? Elicit(string question, CancellationToken token)
  {
   string rid = "still-" + Interlocked.Increment(ref asked);
   var answer = asks[rid] = new TaskCompletionSource<JsonNode?>(TaskCreationOptions.RunContinuationsAsynchronously);
   lock (stdout) stdout.WriteLine(JsonSerializer.Serialize(new { jsonrpc = "2.0", id = rid, method = "elicitation/create", @params = new { message = question, requestedSchema = new { type = "object", properties = new { } } } }));
   try { string? action = answer.Task.WaitAsync(TimeSpan.FromMinutes(10), token).GetAwaiter().GetResult()?["action"]?.GetValue<string>(); return action is "accept" or "decline" ? action : null; }
   catch (Exception ex) when (ex is TimeoutException or OperationCanceledException) { return null; }
   finally { asks.TryRemove(rid, out _); }
  }
  while (stdin.ReadLine() is { } line) {
   if (string.IsNullOrWhiteSpace(line)) continue;
   JsonNode? msg; try { msg = JsonNode.Parse(line); } catch (JsonException) { continue; }
   var id = msg?["id"]?.DeepClone(); string method = msg?["method"]?.GetValue<string>() ?? "";
   if (method.Length == 0) { if (id is JsonValue v && v.TryGetValue<string>(out var rid) && asks.TryRemove(rid, out var answer)) answer.TrySetResult(msg?["result"]); continue; } // the app answering us
   if (method == "notifications/cancelled") { if (msg?["params"]?["requestId"]?.ToJsonString() is { } rid && running.TryRemove(rid, out var cancel)) cancel.Cancel(); continue; }
   if (id == null) continue; // other notifications need no reply
   try {
    switch (method) {
     case "initialize":
      if (forcedName == null) client = AgentName(msg?["params"]?["clientInfo"]?["name"]?.GetValue<string>() ?? client);
      canElicit = msg?["params"]?["capabilities"]?["elicitation"] != null;
      Send(id, new { protocolVersion = msg?["params"]?["protocolVersion"]?.GetValue<string>() ?? "2025-06-18", capabilities = new { tools = new { } },
       serverInfo = new { name = "still", version = Assembly.GetEntryAssembly()?.GetName().Version?.ToString(3) ?? "1" },
       instructions = Instructions + (lockProfile ? "" : " Still can have several profiles (separate logins); list_profiles shows them and every tool takes an optional profile name, or \"temp\" for a clean temporary window.") }, null);
      break;
     case "ping": Send(id, new { }, null); break;
     case "tools/list": Send(id, new { tools }, null); break;
     case "tools/call": {
      // Calls run side by side, so one slow page never holds up the next request, and the app can cancel any of them.
      string name = msg?["params"]?["name"]?.GetValue<string>() ?? "";
      var args = (msg?["params"]?["arguments"] ?? new JsonObject()).DeepClone();
      if (lockProfile) (args as JsonObject)?.Remove("profile");
      var cts = new CancellationTokenSource(); string key = id.ToJsonString(); running[key] = cts;
      string who = client;
      _ = Task.Run(() => {
       try {
        string reply = lockProfile && name == "list_profiles" ? JsonSerializer.Serialize(new { ok = false, error = "Unknown tool: list_profiles" }) : Call(instance, who, name, args.DeepClone(), cts.Token, canElicit);
        // The user isn't at Still: their AI app asks them (the AI never sees the question), then the call carries on.
        for (int tries = 0; tries < 2 && canElicit && JsonNode.Parse(reply)?["confirm"] is { } ask && Elicit(ask["question"]!.GetValue<string>(), cts.Token) is { } action; tries++) {
         var confirm = (JsonObject)args.DeepClone(); confirm["code"] = ask["code"]!.GetValue<string>(); confirm["allow"] = action == "accept";
         Call(instance, who, "user_confirmed", confirm, cts.Token);
         reply = action == "accept" ? Call(instance, who, name, args.DeepClone(), cts.Token, canElicit) : JsonSerializer.Serialize(new { ok = false, error = "The user said no. Don't try again unless they ask." });
        }
        if (!cts.IsCancellationRequested) Send(id, ToolResult(reply), null);
       } catch (OperationCanceledException) { }
       catch (Exception ex) { Send(id, null, new { code = -32603, message = "Still error: " + ex.Message }); }
       finally { running.TryRemove(key, out _); }
      });
      break;
     }
     default: Send(id, null, new { code = -32601, message = "Method not found: " + method }); break;
    }
   } catch (Exception ex) { Send(id, null, new { code = -32603, message = "Still error: " + ex.Message }); }
  }
 }
 static readonly JsonSerializerOptions Relaxed = new() { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
 /// A page read comes back as plain text (no JSON escaping, fewer tokens); other results as compact JSON.
 static object ToolResult(string reply)
 {
  var r = JsonNode.Parse(reply)!;
  if (r["ok"]?.GetValue<bool>() != true) return new { content = new[] { new { type = "text", text = r["error"]?.GetValue<string>() ?? "Failed." } }, isError = true };
  var data = r["result"];
  if (data is JsonObject obj && obj["image"] is { } img) return new { content = new object[] { new { type = "image", data = img.GetValue<string>(), mimeType = obj["mime"]?.GetValue<string>() ?? "image/png" } } };
  return new { content = new[] { new { type = "text", text = PlainText(data) } } };
 }
 static string PlainText(JsonNode? data) => data is JsonObject { Count: 1 } o && o["text"] is JsonValue v && v.TryGetValue<string>(out var text) ? text : data?.ToJsonString(Relaxed) ?? "{}";


 static string ListProfiles(string instance) => JsonSerializer.Serialize(new { ok = true, result = ProfileCatalog.Read().Select(p => new {
  name = p.Name, id = p.Id, open = IsOpen(p), launch = p.Id == ProfileCatalog.LaunchId, defaultForAgent = App.InstanceName(ProfileCatalog.Folder(p)) == instance }) });

 static bool IsOpen(BrowserProfile p) { try { using var gate = Mutex.OpenExisting(App.InstanceName(ProfileCatalog.Folder(p))); return true; } catch (WaitHandleCannotBeOpenedException) { return false; } catch (UnauthorizedAccessException) { return true; } }

 /// Sends one tool call to the Still process for the requested profile (opening it if it's closed) and returns its JSON reply.
 static string Call(string instance, string client, string tool, JsonNode args, CancellationToken cancel = default, bool elicit = false)
 {
  if (tool == "list_profiles") return ListProfiles(instance);
  string name = args is JsonObject o && o["profile"]?.GetValue<string>() is { Length: > 0 } n ? n : "";
  (args as JsonObject)?.Remove("profile");
  if (name.Equals("temp", StringComparison.OrdinalIgnoreCase)) instance = TempInstance(client);
  else if (name.Length > 0) {
   var profile = ProfileCatalog.Read().FirstOrDefault(p => string.Equals(p.Name, name, StringComparison.OrdinalIgnoreCase) || p.Id == name);
   if (profile == null) return JsonSerializer.Serialize(new { ok = false, error = $"No Still profile is named \"{name}\". Use list_profiles." });
   string folder = Path.GetFullPath(ProfileCatalog.Folder(profile));
   instance = App.InstanceName(folder);
   if (!IsOpen(profile)) {
    var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = true }; // shell launch: the window must not inherit this stdio pipe
    start.ArgumentList.Add("--profile"); start.ArgumentList.Add(folder);
    start.ArgumentList.Add("--profiles-root"); start.ArgumentList.Add(App.ProfileHome);
    if (App.IsQa) start.ArgumentList.Add("--qa");
    System.Diagnostics.Process.Start(start);
   }
  }
  for (var until = DateTime.UtcNow.AddSeconds(name.Length > 0 ? 25 : 0); ; Thread.Sleep(500)) {
   cancel.ThrowIfCancellationRequested();
   try {
    // One connection per call: calls never queue behind each other, and a cancelled call just hangs up.
    using var pipe = new NamedPipeClientStream(".", MainWindow.AgentPipe(instance), PipeDirection.InOut, PipeOptions.CurrentUserOnly | PipeOptions.Asynchronous);
    pipe.Connect(3000);
    using var reader = new StreamReader(pipe, new UTF8Encoding(false));
    using var writer = new StreamWriter(pipe, new UTF8Encoding(false)) { AutoFlush = true };
    writer.WriteLine(JsonSerializer.Serialize(new { client, tool, args, elicit, run = RunId }));
    // Still answers every call within its own time limit; this only covers a Still that froze.
    using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancel); limit.CancelAfter(TimeSpan.FromMinutes(tool is "list_tabs" or "save_file" ? 2 : 12)); // ask_user and permission cards wait up to 11 minutes
    try { return reader.ReadLineAsync(limit.Token).AsTask().GetAwaiter().GetResult() ?? throw new IOException("Still closed the connection."); }
    catch (OperationCanceledException) when (!cancel.IsCancellationRequested) { return JsonSerializer.Serialize(new { ok = false, error = "Still didn't answer in time. It may be busy; try again, or ask the user to check Still." }); }
   } catch (Exception ex) when (ex is IOException or TimeoutException or UnauthorizedAccessException) {
    if (DateTime.UtcNow < until) continue;
    return JsonSerializer.Serialize(new { ok = false, error = name.Equals("temp", StringComparison.OrdinalIgnoreCase) ? "The temporary window didn't start. Try again." : (name.Length > 0 ? $"Still profile \"{name}\" isn't reachable. " : "Still isn't running. ") + "Open it and turn on Settings → Let AI agents control Still (each profile has its own switch), then try again." });
   }
  }
 }

 static string? tempFolder;
 static readonly object tempLock = new();
 /// Opens (once per agent session) a Still window on a brand-new throwaway profile, with this agent already allowed in.
 static string TempInstance(string client) { lock (tempLock) return OpenTemp(client); }
 static string OpenTemp(string client)
 {
  if (tempFolder != null && IsOpen(tempFolder)) return App.InstanceName(tempFolder);
  string root = Path.Combine(Path.GetTempPath(), "Still-temp");
  if (Directory.Exists(root)) // sweep earlier temporary profiles whose windows are closed
   foreach (var old in Directory.GetDirectories(root)) if (!IsOpen(old)) try { Directory.Delete(old, true); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
  tempFolder = Path.Combine(root, Guid.NewGuid().ToString("N"));
  Directory.CreateDirectory(tempFolder);
  File.WriteAllText(Path.Combine(tempFolder, "state.json"), JsonSerializer.Serialize(new { UiVersion = 4, Welcome = false, Preferences = new { AgentsEnabled = true, ApprovedAgents = new[] { client } } }));
  var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = true };
  foreach (var a in new[] { "--profile", tempFolder, "--profiles-root", tempFolder, "--temp" }) start.ArgumentList.Add(a);
  if (App.IsQa) start.ArgumentList.Add("--qa");
  System.Diagnostics.Process.Start(start);
  return App.InstanceName(tempFolder);
 }
 static bool IsOpen(string folder) { try { using var gate = Mutex.OpenExisting(App.InstanceName(folder)); return true; } catch (WaitHandleCannotBeOpenedException) { return false; } catch (UnauthorizedAccessException) { return true; } }

 [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern bool AttachConsole(int pid);

 // `Still.exe --cli <tool> [key=value ...]`: one tool call from a terminal. Prints JSON; screenshots are saved as PNG.
 public static int Cli(string instance, string[] argv)
 {
  AttachConsole(-1); // WPF exe: borrow the caller's console so output shows in a terminal
  var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };
  var tools = BuildTools(false);
  if (argv.Length == 0 || argv[0] is "help" or "--help" or "-h") {
   stdout.WriteLine("Usage: Still.exe --cli <tool> as=<your name> [key=value ...]\n\nTools:");
   foreach (var t in tools) {
    var props = t!["inputSchema"]!["properties"]!.AsObject().Select(p => p.Key + "=");
    stdout.WriteLine($"  {t["name"]} {string.Join(" ", props)}\n      {t["description"]}");
   }
   return 0;
  }
  var args = new JsonObject();
  foreach (var a in argv.Skip(1)) {
   int eq = a.IndexOf('='); if (eq < 1) { stdout.WriteLine($"Arguments are key=value, got: {a}"); return 2; }
   string k = a[..eq].TrimStart('-'), v = a[(eq + 1)..];
   args[k] = v is "true" or "false" ? bool.Parse(v) : double.TryParse(v, System.Globalization.CultureInfo.InvariantCulture, out var n) && k is "amount" or "timeoutMs" or "offset" ? n : k == "paths" ? new JsonArray(v.Split(';', StringSplitOptions.RemoveEmptyEntries).Select(x => (JsonNode)x).ToArray()) : v;
  }
  // Agents must say who they are, so the user sees "Codex is using Still", not a generic name.
  if (args["as"]?.ToString() is not { Length: > 0 } who) { stdout.WriteLine("Error: say who you are with as=<your name>, for example as=Claude or as=Codex."); return 2; }
  args.Remove("as");
  string reply = Call(instance, AgentName(who), argv[0], args);
  var r = JsonNode.Parse(reply)!;
  if (r["ok"]?.GetValue<bool>() != true) { stdout.WriteLine("Error: " + (r["error"]?.GetValue<string>() ?? "Failed.")); return 1; }
  var data = r["result"];
  if (data is JsonObject obj && obj["image"] is { } img) {
   string file = Path.Combine(Path.GetTempPath(), $"still-screenshot-{DateTime.Now:yyyyMMdd-HHmmss}.png");
   File.WriteAllBytes(file, Convert.FromBase64String(img.GetValue<string>()));
   stdout.WriteLine(file); return 0;
  }
  stdout.WriteLine(PlainText(data));
  return 0;
 }
}
