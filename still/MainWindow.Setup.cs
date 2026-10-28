using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
namespace Still;

/// "Set it up with <name>": a short interview run by the user's own AI app (a few small messages on their plan), then
/// the settings it picked, each with an undo. Quick setup never comes here and never runs an AI.
public partial class MainWindow
{
 sealed class SetupTalk(string companion)
 {
  public readonly string Companion = companion;
  public string? Session;
  public bool Started, Busy, Done;
  public string Error = "";
  public readonly List<object> Turns = []; // what was said, for the welcome to show: { role, text, options }
  public readonly List<SetupChange> Changes = [];
 }
 sealed class SetupChange(string key, string label, string value, Action undo)
 {
  public readonly string Key = key, Label = label, Value = value;
  public readonly Action Undo = undo;
  public bool Undone;
 }
 static SetupTalk? setupTalk;
 static bool welcomeTalk; // setup opens straight into the interview ("set me up again")

 [GeneratedRegex(@"^\s*(please\s+)?(set\s+(me|it|still)\s+up\s+again|redo\s+(my\s+)?setup|run\s+setup\s+again)\b[\s.!?]*$", RegexOptions.IgnoreCase)] private static partial Regex SetUpAgain();

 static void PublishSetup() { foreach (var w in Windows) w.ShellSend(new { kind = "setup", data = setupTalk is not { } s ? null : new {
  busy = s.Busy, error = s.Error, done = s.Done, turns = s.Turns,
  changes = s.Changes.Select(c => new { key = c.Key, label = c.Label, value = c.Value, undone = c.Undone }) } }); }

 async Task HandleSetup(string op, JsonElement data)
 {
  string S(string k) => data.ValueKind == JsonValueKind.Object && data.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
  switch (op) {
   case "setupStart":
    setupTalk = new SetupTalk(S("companion")); welcomeTalk = false;
    await SetupAsk("Start now: say hello in one line and ask your first question.", "");
    break;
   case "setupAnswer" when setupTalk is { Busy: false } && S("text").Trim() is { Length: > 0 and <= 2000 } answer:
    await SetupAsk(answer, answer);
    break;
   case "setupUndo" when setupTalk != null:
    foreach (var c in setupTalk.Changes.Where(c => !c.Undone && (S("key").Length == 0 || c.Key == S("key")))) { c.Undo(); c.Undone = true; }
    SaveLater(); PublishAll(); PublishAiEverywhere(); PublishSetup();
    break;
   case "setupEnd": setupTalk = null; PublishSetup(); break;
  }
 }

 async Task SetupAsk(string text, string shown)
 {
  var s = setupTalk!;
  var who = Companions.FirstOrDefault(c => c.Id == s.Companion) ?? Companions.FirstOrDefault();
  var cli = AiClis.FirstOrDefault(c => c.Id == (who is { Ai.Length: > 0 } ? who.Ai : Prefs.AiHarness));
  if (shown.Length > 0) s.Turns.Add(new { role = "user", text = shown });
  if (cli == null || FindCli(cli.Command) is not { } exe) { s.Error = "No AI app is set up yet."; PublishSetup(); return; }
  s.Busy = true; s.Error = ""; PublishSetup();
  string prompt = (s.Started ? "" : SetupPrompt(who, cli) + "\n\n") + text, folder = Path.Combine(AiFolder, "setup"), said = "";
  List<string> mcp = ["--mcp", "--no-tools", "--as", cli.Name, "--this-profile", "--profile", App.DataRoot, "--profiles-root", App.ProfileHome];
  if (App.IsQa) mcp.Insert(1, "--qa");
  var (model, effort) = ForMode(cli.Id, "efficient"); // the quickest model: setup is small talk
  if (!aiModels.GetValueOrDefault(cli.Id, []).Any(m => m.Id == model)) model = effort = "";
  AgentRun? run = null; RunRequest? request = null;
  try {
   if (cli.NamesSession) s.Session ??= Guid.NewGuid().ToString();
   request = new RunRequest(prompt, model, effort, folder, mcp, s.Session, s.Started && s.Session != null);
   run = await cli.Start(exe, request);
   using var limit = new CancellationTokenSource(TimeSpan.FromSeconds(120));
   await foreach (var e in run.Events(limit.Token)) switch (e) {
    case AgentEvent.Message { Join: { } join } m: said += join + m.Text; break;
    case AgentEvent.Message m: said += (said.Length > 0 ? "\n" : "") + m.Text; break;
    case AgentEvent.Session session: s.Session ??= session.Id; break;
   }
   s.Started = s.Session != null;
   if (said.Length == 0) s.Error = run.Errors.LastOrDefault(l => l.Trim().Length > 0) is { } why && SignedOutError().IsMatch(why) ? $"{cli.Name} isn't signed in." : $"{cli.App} didn't answer.";
  } catch (Exception ex) when (ex is IOException or InvalidOperationException or OperationCanceledException or System.ComponentModel.Win32Exception) { s.Error = $"{cli.App} didn't answer."; App.Log(ex); }
  finally {
   run?.Dispose();
   try { if (request != null) File.Delete(request.PromptFile); } catch (IOException) { }
  }
  if (setupTalk != s) return; // the user left setup meanwhile
  s.Busy = false;
  if (said.Length > 0) {
   var reply = ParseObject(said);
   string Str(string k) => reply?[k] is JsonValue v && v.TryGetValue<string>(out var x) ? x.Trim() : "";
   if (reply?["done"] is JsonValue d && d.TryGetValue<bool>(out var done) && done && reply["settings"] is JsonObject settings) {
    foreach (var c in s.Changes.Where(c => !c.Undone)) c.Undo(); // a second round (the user asked for a change) starts from where they were
    s.Changes.Clear(); s.Done = true;
    SetupApply(settings, who);
    s.Turns.Add(new { role = "ai", text = Str("say") is { Length: > 0 } bye ? bye : "All set. Here's what I changed." });
    SaveLater(); PublishAll(); PublishAiEverywhere();
   } else {
    string[] options = reply?["options"] is JsonArray o ? [.. o.Select(x => x is JsonValue v && v.TryGetValue<string>(out var t) ? t.Trim() : "").Where(t => t.Length is > 0 and <= 80).Take(4)] : [];
    string line = reply == null ? said.Trim() : string.Join("\n", new[] { Str("say"), Str("question") }.Where(t => t.Length > 0));
    s.Done = false; // asked to change something, it asks back: the summary waits for the next "done"
    s.Turns.Add(new { role = "ai", text = line.Length > 1200 ? line[..1200] : line, options });
   }
  }
  PublishSetup();
 }

 static JsonObject? ParseObject(string text)
 {
  int a = text.IndexOf('{'), b = text.LastIndexOf('}');
  if (a < 0 || b <= a) return null;
  try { return JsonNode.Parse(text[a..(b + 1)]) as JsonObject; } catch (JsonException) { return null; }
 }

 string SetupPrompt(Companion? who, AgentAdapter cli) => $$"""
  You are {{who?.Name ?? "the user's companion"}}, the companion in Still, a web browser with AI built in. {{(who is { Job.Length: > 0 } ? "The user picked you as: " + who.Job : "")}}
  You're setting Still up with the user in a short, friendly chat. Ask one short question at a time, 4 to 6 in all, and adapt to what they say. Find out:
  what they mostly use the browser for, the sites they're on every day, how hands-on they want you to be when you work in tabs for them, what they'd like your help with most, and how they'd like you to talk to them. Skip anything they've already told you. Don't use any tools and don't look anything up.

  Reply with ONLY one JSON object and nothing else:
  {"say": "a short, warm reaction to their answer (or hello)", "question": "your next question", "options": ["2 to 4 short answers they can tap"]}
  Write plainly, in second person, no em dashes. Don't call Still quiet, calm or minimal.

  When you know enough, or they ask you to finish, reply instead with:
  {"say": "one line wrapping up", "done": true, "settings": {
   "name": "what they want to be called, or empty",
   "interests": ["up to 6 short topics they care about"],
   "layout": "Classic" (tabs across the top) or "Modern" (tabs down the side) or "",
   "theme": "Light", "Dark", "System" or "",
   "search": "Google", "Bing", "DuckDuckGo" or "",
   "pinned": [{"title": "Site", "url": "https://..."}] (up to 4 sites they use all day, kept as pinned tabs),
   "sites": [{"title": "Site", "url": "https://..."}] (up to 8 sites for their new tab page),
   "newTab": "companion" (you and ideas on the new tab page) or "sites" (search and their sites) or "",
   "agent": "careful" (ask before every click), "balanced" (ask once per site in a chat) or "hands-off" (just do it) or "",
   "tone": "how you should talk and act, one or two sentences, written to you",
   "memories": ["short facts worth remembering about them"]} }
  Use "" or [] for anything they didn't say: Still leaves those as they are. Buying, sending and deleting always ask, whatever they pick.

  Still right now: tabs {{(Prefs.TabLayout == "Modern" ? "down the side" : "across the top")}}, theme {{Prefs.Theme}}, search {{Prefs.SearchEngine}}. They're using {{cli.Name}}.
  """;

 /// Applies what the interview settled on. Each change keeps its own undo; anything invalid is left out.
 void SetupApply(JsonObject st, Companion? who)
 {
  var changes = setupTalk!.Changes;
  string Str(string k, int max = 200) => st[k] is JsonValue v && v.TryGetValue<string>(out var x) ? (x.Trim() is var t && t.Length > max ? t[..max] : t) : "";
  List<(string Title, string Url)> Sites(string k, int max) => st[k] is JsonArray a ? [.. a.OfType<JsonObject>()
   .Select(o => (Title: (o["title"] as JsonValue)?.ToString().Trim() ?? "", Url: (o["url"] as JsonValue)?.ToString().Trim() ?? ""))
   .Where(x => Uri.TryCreate(x.Url, UriKind.Absolute, out var u) && u.Scheme is "https" or "http" && x.Url.Length < 300)
   .Select(x => (x.Title.Length is > 0 and <= 40 ? x.Title : Host(x.Url), x.Url)).DistinctBy(x => Host(x.Item2)).Take(max)] : [];
  List<string> Texts(string k, int max, int len) => st[k] is JsonArray a ? [.. a.Select(x => x is JsonValue v && v.TryGetValue<string>(out var t) ? t.Trim() : "").Where(t => t.Length is > 1 && t.Length <= len).Take(max)] : [];
  void Theme(string t) { Prefs.Theme = t; foreach (var w in Windows) w.ApplyTheme(); }

  if (Str("layout") is "Classic" or "Modern" && Str("layout") != Prefs.TabLayout) {
   var old = Prefs.TabLayout; Prefs.TabLayout = Str("layout");
   changes.Add(new("layout", "Tabs", Prefs.TabLayout == "Modern" ? "Down the side" : "Across the top", () => Prefs.TabLayout = old));
  }
  if (Str("theme") is "Light" or "Dark" or "System" && Str("theme") != Prefs.Theme) {
   var old = Prefs.Theme; Theme(Str("theme"));
   changes.Add(new("theme", "Theme", Prefs.Theme == "System" ? "Matches your system" : Prefs.Theme, () => Theme(old)));
  }
  if (Str("search") is "Google" or "Bing" or "DuckDuckGo" && Str("search") != Prefs.SearchEngine) {
   var old = Prefs.SearchEngine; Prefs.SearchEngine = Str("search");
   changes.Add(new("search", "Search", Prefs.SearchEngine, () => Prefs.SearchEngine = old));
  }
  if (Sites("pinned", 4).Where(x => !tabs.Any(t => t.Pinned && Host(t.Url) == Host(x.Url))).ToList() is { Count: > 0 } pins) {
   // Pinned tabs wait unloaded until they're first opened, like pinned tabs after a restart.
   var added = pins.Select(x => new BrowserTab { Title = x.Title, Url = x.Url, Pinned = true }).ToList();
   tabs.InsertRange(0, added);
   changes.Add(new("pinned", "Pinned", string.Join(", ", added.Select(t => t.Title)), () => { foreach (var t in added) if (t.View == null) tabs.Remove(t); else _ = CloseTab(t, true); }));
  }
  if (Sites("sites", 8).Where(x => !state.Bookmarks.Any(b => Host(b.Url) == Host(x.Url))).ToList() is { Count: > 0 } sites) {
   var added = sites.Select(x => new Visit { Title = x.Title, Url = x.Url }).ToList();
   state.Bookmarks.InsertRange(0, added);
   changes.Add(new("sites", "Your sites", string.Join(", ", added.Select(v => v.Title)), () => state.Bookmarks.RemoveAll(added.Contains)));
  }
  if (Str("newTab") is "companion" or "sites" && Str("newTab") != Prefs.NewTab) {
   var old = Prefs.NewTab; Prefs.NewTab = Str("newTab");
   changes.Add(new("newTab", "New tab page", Prefs.NewTab == "sites" ? "Search and your sites" : $"{who?.Name ?? "Your companion"} and ideas", () => Prefs.NewTab = old));
  }
  if (Str("agent") is var level && level is "careful" or "balanced" or "hands-off") {
   // How often the AI asks before clicking and typing. Buying, sending and deleting ("sensitive") always ask.
   var old = Prefs.Permissions.Where(p => p.Site.Length == 0 && p.Companion.Length == 0 && p.Action == "interact").Select(p => p.Mode).FirstOrDefault();
   SetPermission("", "interact", "", level switch { "careful" => "ask", "hands-off" => "always", _ => "chat" });
   changes.Add(new("agent", "When I work in tabs", level switch { "careful" => "I ask before every click", "hands-off" => "I just do it, but always ask before buying, sending or deleting", _ => "I ask once per site in each chat" },
    () => { if (old == null) Prefs.Permissions.RemoveAll(p => p.Site.Length == 0 && p.Companion.Length == 0 && p.Action == "interact"); else SetPermission("", "interact", "", old); }));
  }
  if (who != null && Str("tone", 600) is { Length: > 3 } tone && tone != who.Tone) {
   var old = who.Tone; who.Tone = tone;
   changes.Add(new("tone", $"How {who.Name} talks", tone, () => who.Tone = old));
  }
  var interests = Texts("interests", 6, 40);
  if (interests.Count > 0) {
   var old = Prefs.Interests; Prefs.Interests = interests;
   changes.Add(new("interests", "Ideas about", string.Join(", ", interests), () => Prefs.Interests = old));
  }
  if (who != null) {
   // What it learned goes into the companion's memory, like anything else it remembers.
   List<string> facts = [.. Texts("memories", 8, 200)];
   if (Str("name", 40) is { Length: > 0 } name) facts.Insert(0, "Likes to be called " + name + ".");
   if (interests.Count > 0) facts.Add("Into " + string.Join(", ", interests).ToLowerInvariant() + ".");
   var kept = facts.Select((f, i) => CompanionMemory.Remember(who.Id, f, "preference", "", i == 0 && Str("name", 40).Length > 0 ? "name" : f.StartsWith("Into ") ? "interests" : "")).OfType<Fact>().ToList();
   if (kept.Count > 0) changes.Add(new("memory", $"{who.Name} remembers", string.Join(" ", kept.Select(f => f.Text)),
    () => { foreach (var f in kept) CompanionMemory.Forget(who.Id, f.Id); }));
  }
 }
}
