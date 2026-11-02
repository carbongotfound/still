using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
namespace Still;

/// One thing a companion remembers about the user.
public sealed class Fact
{
 public string Id { get; set; } = Guid.NewGuid().ToString("N")[..8];
 public string Text { get; set; } = "";
 public string Kind { get; set; } = "fact"; // fact, preference, habit, person, project, or chat (a past chat)
 public DateTime At { get; set; } = DateTime.UtcNow;
 public string Chat { get; set; } = ""; // the chat it came from; "" = setup, or the user typed it
 public string Key { get; set; } = ""; // a slot that holds one fact ("name", "interests", "chat:<id>"): a new one replaces it
}

/// Each companion's memory of the user: companions\<id>\memory.json in the profile, plain JSON on this computer, and
/// only ever put into that companion's own chats. Passwords, codes, card numbers and private tabs never go in.
static partial class CompanionMemory
{
 internal static readonly string[] Kinds = ["fact", "preference", "habit", "person", "project", "chat"];
 static readonly Dictionary<string, List<Fact>> cache = [];
 static readonly JsonSerializerOptions Indented = new() { WriteIndented = true };
 static string Folder(string id) => Path.Combine(App.DataRoot, "companions", id);
 static string FileOf(string id) => Path.Combine(Folder(id), "memory.json");

 internal static List<Fact> Of(string id)
 {
  if (id.Length == 0) return [];
  if (cache.TryGetValue(id, out var list)) return list;
  try { list = File.Exists(FileOf(id)) ? JsonSerializer.Deserialize<List<Fact>>(File.ReadAllText(FileOf(id))) ?? [] : Migrate(id); }
  catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException) { App.Log(ex); list = []; }
  return cache[id] = list;
 }

 // Before 1.9 memory was free text, one thing per line: notes every companion shared, and each one's own.
 static List<Fact> Migrate(string id)
 {
  List<Fact> list = [];
  foreach (var old in new[] { Path.Combine(App.DataRoot, "companions", "memory.md"), Path.Combine(Folder(id), "memory.md") })
   try { if (File.Exists(old)) foreach (var line in File.ReadAllLines(old)) Add(list, line.Trim().TrimStart('-', '*', ' '), "fact", "", ""); }
   catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { App.Log(ex); }
  return list;
 }

 internal static void Save(string id)
 {
  try { Directory.CreateDirectory(Folder(id)); File.WriteAllText(FileOf(id), JsonSerializer.Serialize(Of(id), Indented)); }
  catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { App.Log(ex); }
 }

 internal static void Drop(string id) { cache.Remove(id); notes.Remove(id); } // the companion is gone, folder and all

 // Knowledge files: the working notes of a companion's job, Markdown it keeps up as it works (its role's kit seeds them
 // empty). Each has a name and what it holds in its front matter. They're in its folder, so they go when it does.
 internal sealed record Note(string Id, string Name, string About, string Body);
 static readonly Dictionary<string, List<Note>> notes = [];
 static string NotesFolder(string id) => Path.Combine(Folder(id), "knowledge");
 internal static bool Equipped(string id) => Directory.Exists(NotesFolder(id));
 internal static void Seed(string id, string file, string text)
 {
  Directory.CreateDirectory(NotesFolder(id)); notes.Remove(id);
  if (!File.Exists(Path.Combine(NotesFolder(id), file + ".md"))) File.WriteAllText(Path.Combine(NotesFolder(id), file + ".md"), text);
 }
 internal static List<Note> Notes(string id)
 {
  if (notes.TryGetValue(id, out var list)) return list;
  list = [];
  try {
   if (id.Length > 0 && Directory.Exists(NotesFolder(id))) foreach (var file in Directory.EnumerateFiles(NotesFolder(id), "*.md").Order().Take(20)) {
    var (head, body) = Skill.Split(File.ReadAllText(file));
    string fid = Path.GetFileNameWithoutExtension(file);
    list.Add(new(fid, head.GetValueOrDefault("name") is { Length: > 0 } n ? n : fid, head.GetValueOrDefault("about", ""), body));
   }
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { App.Log(ex); }
  return notes[id] = list;
 }
 /// Rewrites a knowledge file's notes, keeping its name and what it holds.
 internal static Note? Write(string id, string file, string body)
 {
  if (Notes(id).FirstOrDefault(n => n.Id == file) is not { } note) return null;
  body = body.ReplaceLineEndings("\n").Trim();
  if (body.Length > 12000) body = body[..12000];
  try { File.WriteAllText(Path.Combine(NotesFolder(id), file + ".md"), $"---\nname: {note.Name}\nabout: {note.About}\n---\n\n{body}\n"); }
  catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { App.Log(ex); return null; }
  notes.Remove(id);
  return note with { Body = body };
 }
 /// The knowledge files as the companion's prompt has them, each with what it holds so far.
 internal static string NotesBrief(string id) => Notes(id) is { Count: > 0 } list
  ? "Your knowledge files, kept on the user's computer. Use what's in them. When you learn something one of them should hold, rewrite that file with update_knowledge: short and tidy, keeping what's still true.\n"
   + string.Concat(list.Select(n => $"\n## {n.Name} (file \"{n.Id}\"): {n.About}\n{(n.Body.Length == 0 ? "(Empty so far.)" : n.Body.Length > 4000 ? n.Body[..4000] + "\n(…)" : n.Body)}\n")) + "\n"
  : ""; 

 /// Keeps a fact, or freshens the one it repeats. Null when it's refused: it looks like a secret, or it's empty.
 internal static Fact? Remember(string id, string text, string kind = "fact", string chat = "", string key = "")
 {
  text = Regex.Replace(text, @"\s+", " ").Trim();
  if (id.Length == 0 || text.Length < 3 || Secret(text)) return null;
  var list = Of(id);
  var fact = Add(list, text.Length > 300 ? text[..300] + "…" : text, kind, chat, key);
  // A long memory keeps everything the user told it and the 60 latest chats.
  var chats = list.Where(f => f.Kind == "chat").OrderByDescending(f => f.At).Skip(60).ToHashSet();
  list.RemoveAll(chats.Contains);
  Save(id);
  return fact;
 }

 static Fact? Add(List<Fact> list, string text, string kind, string chat, string key)
 {
  if (text.Length < 3) return null;
  kind = Kinds.Contains(kind) ? kind : "fact";
  var words = Words(text);
  var same = key.Length > 0 ? list.FirstOrDefault(f => f.Key == key) : list.FirstOrDefault(f => f.Key.Length == 0 && (f.Kind == "chat") == (kind == "chat") && Similar(Words(f.Text), words));
  if (same != null) { same.Text = text; same.Kind = kind; same.At = DateTime.UtcNow; if (chat.Length > 0) same.Chat = chat; return same; }
  var fact = new Fact { Text = text, Kind = kind, Chat = chat, Key = key };
  list.Add(fact);
  return fact;
 }

 internal static bool Edit(string id, string factId, string text)
 {
  text = Regex.Replace(text, @"\s+", " ").Trim();
  if (Of(id).FirstOrDefault(f => f.Id == factId) is not { } f || text.Length < 3 || Secret(text)) return false;
  f.Text = text.Length > 300 ? text[..300] : text; f.At = DateTime.UtcNow; Save(id); return true;
 }

 /// Forgets facts by id, or every fact that matches the words given. Returns what it forgot.
 internal static List<Fact> Forget(string id, string factIdOrWords)
 {
  var list = Of(id); var q = Words(factIdOrWords);
  var gone = list.Where(f => f.Id == factIdOrWords || f.Key == factIdOrWords || q.Count > 0 && q.IsSubsetOf(Words(f.Text))).ToList();
  if (gone.Count > 0) { list.RemoveAll(gone.Contains); Save(id); }
  return gone;
 }

 internal static void Clear(string id) { Of(id).Clear(); Save(id); }
 internal static void ForgetChat(string id, string chat) { if (Of(id).RemoveAll(f => f.Chat == chat || f.Key == "chat:" + chat) > 0) Save(id); }

 /// The facts that fit what the user just asked, best first: shared words, then the core things (who they are, what
 /// they like), then the newest. Past chats come last, the related ones first.
 internal static List<Fact> Relevant(string id, string query, int count = 14)
 {
  var q = Words(query); var now = DateTime.UtcNow;
  double Score(Fact f) => Words(f.Text).Intersect(q).Count() * 2 + (f.Key.Length > 0 ? 3 : f.Kind is "preference" or "person" ? 1 : 0) + 1 / (1 + (now - f.At).TotalDays / 30);
  var list = Of(id);
  return [.. list.Where(f => f.Kind != "chat").OrderByDescending(Score).Take(count),
   .. list.Where(f => f.Kind == "chat").OrderByDescending(f => Words(f.Text).Intersect(q).Count()).ThenByDescending(f => f.At).Take(4)];
 }

 internal static string Brief(string id, string query)
 {
  var facts = Relevant(id, query);
  if (facts.Count == 0) return "";
  return string.Join("\n", facts.Select(f => $"- {(f.Kind == "chat" ? "A past chat: " : "")}{f.Text} ({f.At.ToLocalTime():yyyy-MM-dd}, id {f.Id})"));
 }

 /// Never kept: passwords, codes, keys, card and account numbers.
 internal static bool Secret(string text) => SecretWords().IsMatch(text) || CardNumber().IsMatch(text) || TokenLike().IsMatch(text);

 static bool Similar(HashSet<string> a, HashSet<string> b) => a.Count > 0 && b.Count > 0 && (double)a.Intersect(b).Count() / a.Union(b).Count() >= 0.75;
 static readonly HashSet<string> Stop = ["the", "and", "for", "are", "with", "that", "this", "you", "your", "they", "them", "their", "has", "have", "was", "who", "what", "when", "where", "how", "likes", "user", "user's"];
 internal static HashSet<string> Words(string text) => [.. WordRx().Matches(text.ToLowerInvariant()).Select(m => m.Value).Where(w => w.Length > 2 && !Stop.Contains(w))];

 [GeneratedRegex(@"[\p{L}\p{N}']+")] private static partial Regex WordRx();
 [GeneratedRegex(@"\b(pass ?words?|passcodes?|passwd|pass ?phrases?|pin (codes?|numbers?)|one[- ]time codes?|otp|2fa codes?|verification codes?|security codes?|cvv|cvc|cookie (values?|data|strings?)|session (cookies?|ids?|tokens?)|api ?keys?|secret keys?|private keys?|access tokens?|bearer|social security|ssn|card numbers?|account numbers?|routing numbers?|iban)\b", RegexOptions.IgnoreCase)] private static partial Regex SecretWords();
 [GeneratedRegex(@"\b(?:\d[ -]?){12,19}\b")] private static partial Regex CardNumber();
 [GeneratedRegex(@"\b(sk|pk|ghp|gho|xox[bap]|AKIA)[-_]?[A-Za-z0-9]{12,}|\b[A-Za-z0-9_\-]{32,}\b")] private static partial Regex TokenLike();
}

public partial class MainWindow
{
 /// Why something can't go into memory, or null if it can: secrets, what the AI typed into a form, anything from a private tab.
 static string? MemoryRefuses(ChatRun? run, string text)
 {
  if (CompanionMemory.Secret(text)) return "That looks like a password, a code or an account number. Still never keeps those.";
  if (Vault.Read().Any(v => v.Password.Length >= 4 && text.Contains(v.Password, StringComparison.Ordinal))) return "That's one of your saved passwords. Still never keeps those.";
  if (run?.Typed.Any(t => text.Contains(t, StringComparison.OrdinalIgnoreCase)) == true) return "That's something typed into a form on a page. Still doesn't keep form data.";
  foreach (var t in Windows.SelectMany(w => w.tabs).Where(t => t.Private))
   if (t.Title.Length >= 4 && t.Title != "Private tab" && text.Contains(t.Title, StringComparison.OrdinalIgnoreCase) || Host(t.Url) is { Length: > 3 } host && text.Contains(host, StringComparison.OrdinalIgnoreCase))
    return "That comes from a private tab. Still never keeps those.";
  return null;
 }

 /// The remember, recall and forget tools: Still's own chat only, on the memory of the companion it's with.
 string Remembering(string who, string tool, JsonElement args)
 {
  if (runs.GetValueOrDefault(who) is not { } run || Companions.FirstOrDefault(c => c.Id == run.Chat.Companion) is not { } me) return Fail("Memory belongs to Still's own companions, in their chats.");
  if (run.Chat.Ephemeral && tool != "recall") return Fail(KeepsNothing);
  if (run.Chat.From != null && tool != "recall") return Fail($"You're helping {NameOf(ExchangeOf(run.Chat).Chain[^2])}, who decides what's kept: put what's worth remembering in your reply.");
  switch (tool) {
   case "remember": {
    if (run.Chat.NoMemory) return Fail("This chat is off the record: the user asked you not to remember it.");
    string fact = S(args, "fact").Trim();
    if (MemoryRefuses(run, fact) is { } why) return Fail(why);
    if (CompanionMemory.Remember(me.Id, fact, S(args, "kind"), run.Chat.Id) is not { } kept) return Fail("Pass one short fact.");
    PublishAiEverywhere();
    return Reply(new { remembered = kept.Text, id = kept.Id });
   }
   case "update_knowledge": {
    if (run.Chat.NoMemory) return Fail("This chat is off the record: the user asked you not to keep anything from it.");
    string text = S(args, "text");
    if (MemoryRefuses(run, text) is { } why) return Fail(why);
    if (CompanionMemory.Write(me.Id, S(args, "file").Trim(), text) is not { } note) return Fail("There's no knowledge file by that id. Yours are listed at the start of the chat.");
    PublishAiEverywhere();
    return Reply(new { updated = note.Name });
   }
   case "recall":
    return Reply(new { facts = CompanionMemory.Relevant(me.Id, S(args, "query"), 12).Select(f => new { id = f.Id, text = f.Text, kind = f.Kind, date = f.At.ToLocalTime().ToString("yyyy-MM-dd") }) });
   default: {
    var gone = CompanionMemory.Forget(me.Id, S(args, "id") is { Length: > 0 } id ? id : S(args, "about"));
    PublishAiEverywhere();
    return Reply(new { forgot = gone.Select(f => f.Text) });
   }
  }
 }
}
