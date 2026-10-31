using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
namespace Still;

/// "Set it up with <name>": an interview run by the user's own AI app (small messages on their plan) that follows up on
/// what they say until it knows them, then sets Still up around them (Assets/setup.md): settings, companions from Still's
/// library, what each companion focuses on and remembers, and starter routines, off. Every change keeps an undo, and the
/// text ones can be reworded in the summary. Quick setup never comes here and never runs an AI.
public partial class MainWindow
{
 sealed class SetupTalk(string companion, JsonElement library)
 {
  public readonly string Companion = companion;
  public readonly JsonElement Library = library; // Still's companions as the welcome hires them, with their role and area
  public IEnumerable<JsonElement> Crew => Library.ValueKind == JsonValueKind.Array ? Library.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.Object) : [];
  public string? Session;
  public bool Started, Busy, Done;
  public string Error = "";
  public readonly List<object> Turns = []; // what was said, for the welcome to show: { role, text, options }
  public readonly List<SetupChange> Changes = [];
 }
 sealed class SetupChange(string key, string label, string value, Action undo, Func<string, string?>? edit = null, string owner = "")
 {
  public readonly string Key = key, Label = label;
  public readonly string Owner = owner; // the companion it's for: a companion setup hired takes what it gave it along when it goes
  public string Value = value;
  public readonly Action Undo = undo;
  public readonly Func<string, string?>? Edit = edit; // puts the user's own wording in: what's shown after, or null if none of it is kept
  public bool Undone;
 }
 static SetupTalk? setupTalk;
 static bool welcomeTalk; // setup opens straight into the interview ("set me up again")

 [GeneratedRegex(@"^\s*(please\s+)?(set\s+(me|it|still)\s+up\s+again|redo\s+(my\s+)?setup|run\s+setup\s+again)\b[\s.!?]*$", RegexOptions.IgnoreCase)] private static partial Regex SetUpAgain();

 static void PublishSetup() { foreach (var w in Windows) w.ShellSend(new { kind = "setup", data = setupTalk is not { } s ? null : new {
  busy = s.Busy, error = s.Error, done = s.Done, turns = s.Turns,
  changes = s.Changes.Select(c => new { key = c.Key, label = c.Label, value = c.Value, undone = c.Undone, editable = c.Edit != null }) } }); }

 static string Field(JsonElement e, string k) => e.ValueKind == JsonValueKind.Object && e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";

 async Task HandleSetup(string op, JsonElement data)
 {
  string S(string k) => Field(data, k);
  switch (op) {
   case "setupStart":
    setupTalk = new SetupTalk(S("companion"), data.TryGetProperty("library", out var library) ? library.Clone() : default); welcomeTalk = false;
    await SetupAsk("Start now: say hello in one line and ask your first question.", "");
    break;
   case "setupAnswer" when setupTalk is { Busy: false } && S("text").Trim() is { Length: > 0 and <= 2000 } answer:
    await SetupAsk(answer, answer);
    break;
   case "setupUndo" when setupTalk != null:
    foreach (var c in setupTalk.Changes.Where(c => !c.Undone && (S("key").Length == 0 || c.Key == S("key")))) UndoSetup(setupTalk, c);
    SaveLater(); PublishAll(); PublishAiEverywhere(); PublishSetup();
    break;
   case "setupEdit" when setupTalk?.Changes.FirstOrDefault(c => c.Key == S("key") && c is { Undone: false, Edit: not null }) is { } edited && S("value").Trim() is { Length: > 0 and <= 1000 } value:
    if (edited.Edit!(value) is { } shown) edited.Value = shown;
    else { edited.Undone = true; Toast("That looks like a password or a code, so it isn't kept."); }
    SaveLater(); PublishAll(); PublishAiEverywhere(); PublishSetup();
    break;
   case "setupEnd": setupTalk = null; PublishSetup(); break;
  }
 }

 /// Takes a change back. A companion setup hired goes with everything setup gave it.
 static void UndoSetup(SetupTalk s, SetupChange c)
 {
  c.Undo(); c.Undone = true;
  if (c.Key.StartsWith("hire:")) foreach (var x in s.Changes.Where(x => x.Owner == c.Owner)) x.Undone = true;
 }

 async Task SetupAsk(string text, string shown)
 {
  var s = setupTalk!;
  var who = Companions.FirstOrDefault(c => c.Id == s.Companion) ?? Companions.FirstOrDefault();
  var cli = AiClis.FirstOrDefault(c => c.Id == (who is { Ai.Length: > 0 } ? who.Ai : Prefs.AiHarness));
  if (shown.Length > 0) s.Turns.Add(new { role = "user", text = shown });
  if (cli == null || FindCli(cli.Command) is not { } exe) { s.Error = "No AI app is set up yet."; PublishSetup(); return; }
  s.Busy = true; s.Error = ""; PublishSetup();
  string prompt = (s.Started ? "" : await SetupPrompt(who, cli, s) + "\n\n") + text, folder = Path.Combine(AiFolder, "setup"), said = "";
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
    foreach (var c in s.Changes.Where(c => !c.Undone)) UndoSetup(s, c); // a second round (the user asked for a change) starts from where they were
    s.Changes.Clear(); s.Done = true;
    SetupApply(settings, who);
    s.Turns.Add(new { role = "ai", text = Str("say") is { Length: > 0 } bye ? bye : "All set. Here's what I set up for you." });
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

 /// One clean sentence: single spaces, a capital first letter and a full stop.
 static string Sentence(string s)
 {
  s = Regex.Replace(s, @"\s+", " ").Trim().TrimEnd(',', ';', ':', ' ');
  return s.Length == 0 ? s : char.ToUpperInvariant(s[0]) + s[1..] + (".!?".Contains(s[^1]) ? "" : ".");
 }

 /// Routine days as the profile panel shows them.
 static string Days(List<int> d) => d.Count == 7 ? "Every day" : d.SequenceEqual([1, 2, 3, 4, 5]) ? "Weekdays" : d.SequenceEqual([0, 6]) ? "Weekends" : string.Join(", ", d.Select(x => ((DayOfWeek)x).ToString()[..3]));

 async Task<string> SetupPrompt(Companion? who, AgentAdapter cli, SetupTalk s)
 {
  var crew = s.Crew.ToList();
  string Role(Companion c) => crew.FirstOrDefault(x => c.Crew.Length > 0 && Field(x, "crew") == c.Crew) is { ValueKind: JsonValueKind.Object } x ? Field(x, "role")
   : c.Job.Length > 100 ? c.Job[..100] + "..." : c.Job.Length > 0 ? c.Job : "their own companion";
  var free = crew.Where(x => !Companions.Any(c => c.Crew == Field(x, "crew"))).Select(x => $"- {Field(x, "crew")}: {Field(x, "name")}, {Field(x, "role")}, {Field(x, "area")}").ToList();
  return (await AppContent.ReadAsset("setup.md"))
   .Replace("{{name}}", who?.Name ?? "the user's companion")
   .Replace("{{picked}}", who is { Job.Length: > 0 } ? "The user picked you as: " + who.Job : "")
   .Replace("{{team}}", string.Join("\n", Companions.Select(c => $"- {c.Id}: {c.Name}, {Role(c)}")))
   .Replace("{{library}}", free.Count > 0 ? string.Join("\n", free) : "(none, they have them all)")
   .Replace("{{now}}", $"tabs {(Prefs.TabLayout == "Modern" ? "down the side" : "across the top")}, theme {Prefs.Theme}, search {Prefs.SearchEngine}")
   .Replace("{{cli}}", cli.Name);
 }

 /// Applies what the interview settled on. Each change keeps its own undo; anything invalid is left out.
 void SetupApply(JsonObject st, Companion? who)
 {
  var s = setupTalk!;
  var changes = s.Changes;
  static string Of(JsonNode? n, string k, int max = 200) => n?[k] is JsonValue v && v.TryGetValue<string>(out var x) ? (x.Trim() is var t && t.Length > max ? t[..max] : t) : "";
  static List<string> Texts(JsonNode? n, string k, int max, int len) => n?[k] is JsonArray a ? [.. a.Select(x => x is JsonValue v && v.TryGetValue<string>(out var t) ? t.Trim() : "").Where(t => t.Length is > 1 && t.Length <= len).Take(max)] : [];
  string Str(string k, int max = 200) => Of(st, k, max);
  List<(string Title, string Url)> Sites(string k, int max) => st[k] is JsonArray a ? [.. a.OfType<JsonObject>()
   .Select(o => (Title: (o["title"] as JsonValue)?.ToString().Trim() ?? "", Url: (o["url"] as JsonValue)?.ToString().Trim() ?? ""))
   .Where(x => Uri.TryCreate(x.Url, UriKind.Absolute, out var u) && u.Scheme is "https" or "http" && x.Url.Length < 300)
   .Select(x => (x.Title.Length is > 0 and <= 40 ? x.Title : Host(x.Url), x.Url)).DistinctBy(x => Host(x.Item2)).Take(max)] : [];
  void Theme(string t) { Prefs.Theme = t; foreach (var w in Windows) w.ApplyTheme(); }
  // Each one its own short sentence: an answer with two sentences becomes two memories.
  static List<string> Facts(IEnumerable<string> lines) => [.. lines.SelectMany(t => Regex.Split(t, @"\n+|(?<=[.!?])\s+(?=\p{Lu})")).Select(Sentence).Where(t => t.Length > 2).Take(8)];
  // What it learned goes into memory, like anything else a companion remembers: undo forgets it, and an edit swaps the
  // user's lines in. The summary shows what the first companion keeps.
  void Remember(string key, string label, List<Companion> to, List<string> facts, string owner = "")
  {
   List<(string Id, Fact Fact)> Keep(List<string> lines) => [.. to.Where(Companions.Contains).SelectMany(c => lines.Select(f => (c.Id, CompanionMemory.Remember(c.Id, f, "preference", "",
    f.StartsWith("Likes to be called ") ? "name" : f.StartsWith("Works on ") ? "interests" : "")))).Where(k => k.Item2 != null).Select(k => (k.Id, k.Item2!))];
   var kept = Keep(facts);
   string Shown() => string.Join("\n", kept.Where(k => k.Id == to[0].Id).Select(k => k.Fact.Text));
   void Forget() { foreach (var (id, f) in kept) CompanionMemory.Forget(id, f.Id); }
   if (kept.Any(k => k.Id == to[0].Id)) changes.Add(new(key, label, Shown(), Forget, text => { Forget(); kept = Keep(Facts([text])); return kept.Count > 0 ? Shown() : null; }, owner));
  }

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
   changes.Add(new("tone", "How I talk", tone, () => who.Tone = old, t => who.Tone = t.Length > 600 ? t[..600] : t));
  }
  var interests = Texts(st, "interests", 6, 40);
  if (interests.Count > 0) {
   var old = Prefs.Interests; Prefs.Interests = interests;
   changes.Add(new("interests", "Ideas about", string.Join(", ", interests), () => Prefs.Interests = old));
  }

  // Companions from Still's library whose work matches theirs, hired as the library hires them: routine off.
  Dictionary<string, Companion> hired = [];
  foreach (var crew in Texts(st, "hire", 3, 24))
   if (!Companions.Any(c => c.Crew == crew) && s.Crew.FirstOrDefault(x => Field(x, "crew") == crew) is { ValueKind: JsonValueKind.Object } entry) {
    var c = hired[crew] = SaveCompanion(entry);
    changes.Add(new("hire:" + crew, "New on your team", $"{Field(entry, "role")} {c.Name} · {Field(entry, "area")}", () => DropCompanion(c), owner: c.Id));
   }
  Companion? Find(string id) => hired.GetValueOrDefault(id) ?? Companions.FirstOrDefault(c => c.Id == id) ?? Companions.FirstOrDefault(c => id.Length > 0 && c.Crew == id);
  string Whose(Companion c, string mine, string theirs) => c == who ? mine : string.Format(theirs, c.Name);

  if (who != null) {
   List<string> facts = Facts(Texts(st, "memories", 8, 200));
   if (Str("name", 40) is { Length: > 0 } name) facts.Insert(0, "Likes to be called " + name + ".");
   if (interests.Count > 0) facts.Add("Works on " + string.Join(", ", interests).ToLowerInvariant() + ".");
   Remember("memory", Companions.Count > 1 ? "Your team will remember" : "I'll remember", [.. Companions.OrderBy(c => c != who)], facts);
  }
  // What each companion focuses on for them goes under its own instructions, after "For me:", so setting up again
  // replaces it.
  foreach (var o in (st["companions"] as JsonArray ?? []).OfType<JsonObject>().Take(10)) {
   if (Find(Of(o, "id", 24)) is not { } c) continue;
   if (Of(o, "instructions", 600) is { Length: > 10 } focus && c.Job.Split("\n\nFor me: ")[0] is { Length: < 900 } before) {
    var old = c.Job;
    string Focus(string t) { t = t.Length > 990 - before.Length ? t[..(990 - before.Length)] : t; c.Job = $"{before}\n\nFor me: {t}".TrimStart(); return t; }
    changes.Add(new("focus:" + c.Id, Whose(c, "What I'll focus on", "What {0} will focus on"), Focus(focus), () => c.Job = old, Focus, c.Id));
   }
   Remember("memory:" + c.Id, Whose(c, "I'll also remember", "{0} will also remember"), [c], Facts(Texts(o, "memories", 6, 200)), c.Id);
  }
  foreach (var o in (st["routines"] as JsonArray ?? []).OfType<JsonObject>().Take(3)) {
   if (Find(Of(o, "id", 24)) is not { } c) continue;
   var r = (JsonObject)o.DeepClone(); r.Remove("id"); r["on"] = false;
   if (ReadRoutines(JsonSerializer.SerializeToElement(new JsonArray(r)), []) is not [var routine]) continue;
   c.Routines.Add(routine);
   changes.Add(new("routine:" + routine.Id, Whose(c, "My routine, off for now", "{0}'s routine, off for now"), $"{Days(routine.Days)} at {routine.Time}: {routine.Text}", () => c.Routines.Remove(routine), owner: c.Id));
  }
  // What they want help with first: the welcome offers it as their first task.
  if (Str("first", 300) is { Length: > 3 } first) changes.Add(new("first", "First, I'll help with", first, () => { }, t => t));
 }
}
