using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
namespace Still;

// Work in a folder: a companion's folder on the user's computer, where its AI app (whichever it is) lists, reads, creates
// and edits files with Still's tools. Nothing outside it: no "..", no path out of it, and no link or junction on the way
// (Inside). Replacing a whole file of the user's asks unless the companion is on Keep going; deleting one always asks and
// sends it to the Recycle Bin. A file it made in this chat it may replace or delete, and Allow in this chat stops the asking.
public partial class MainWindow
{
 string? nextFolder; // the next new chat's own folder ("": none), picked before it starts
 /// The folder a chat works in: its own, or else its companion's; "" for none, one that's gone, or a private window.
 string FolderOf(AiChat chat) => !chat.Ephemeral && (chat.Folder ?? Companions.FirstOrDefault(c => c.Id == chat.Companion)?.Folder) is { Length: > 0 } f && Path.IsPathFullyQualified(f) && Directory.Exists(f)
  ? Path.GetFullPath(f).TrimEnd(Path.DirectorySeparatorChar) : "";
 /// aiPicture: a picture a companion read in a chat, whose step says Read <path>: from the chat's folder, else a file attached
 /// in it, as a data: address. Null for anything else, or a picture that's gone or over 5 MB.
 string? StepPicture(string chatId, string step)
 {
  if (MyChats.FirstOrDefault(c => c.Id == chatId) is not { } chat || !step.StartsWith("Read ", StringComparison.Ordinal) || ImageMime(step) is not { } mime
   || !chat.Messages.Any(m => m is { Role: "tool", Status: null } && m.Text == step)) return null;
  string name = step[5..], path = "";
  if (FolderOf(chat) is { Length: > 0 } root) try { path = Inside(root, name); } catch (InvalidOperationException) { }
  if (!File.Exists(path) && chat.Messages.SelectMany(m => m.Files ?? []).LastOrDefault(f => f.Name == name) is { } sent && Attachment(AttachmentsHere, sent.Id) is { } file)
   path = Path.Combine(AttachmentsHere, file.Id, file.Name);
  return File.Exists(path) && new FileInfo(path).Length <= MaxImage ? $"data:{mime};base64,{Convert.ToBase64String(File.ReadAllBytes(path))}" : null;
 }
 /// What the AI hears when its folder changed since it was last told (a new session's instructions name it).
 static string FolderNote(AiChat chat, string work)
 {
  string told = chat.FolderTold ?? work;
  chat.FolderTold = work;
  return !chat.Started || told == work ? "" : "[Still] " + (work.Length > 0 ? $"The user changed your working folder to {work}: list_files, read_file, write_file, edit_file and delete_file reach the files there and nothing outside it." : "The user took away your working folder, so you can't reach their files now.") + "\n\n";
 }
 /// chatFolder: a chat's own folder, picked or given ("" with remove: none in it); with no chat, the next new chat's.
 void ChatFolder(JsonElement data)
 {
  string id = S(data, "chat"), given = S(data, "path");
  var chat = id.Length > 0 ? MyChats.FirstOrDefault(c => c.Id == id) : null;
  if (id.Length > 0 && (chat == null || chat.Ephemeral)) return;
  string? path = B(data, "remove") ? "" : Path.IsPathFullyQualified(given) && Directory.Exists(given) ? given : null;
  if (path == null) {
   var pick = new Microsoft.Win32.OpenFolderDialog { Title = chat == null ? "Pick a folder for the new chat" : "Pick a folder for this chat" };
   if (pick.ShowDialog(this) != true) return;
   path = pick.FolderName;
  }
  if (chat != null) { chat.Folder = path; SaveAiChats(); } else nextFolder = path;
  PublishAiEverywhere();
 }
 /// Everyone in the chain (the companion, and whoever it's helping) is on Keep going.
 bool KeepGoing(AiChat chat) => ExchangeOf(chat).Chain.All(c => LevelOf(Companions.FirstOrDefault(x => x.Id == c)).Programs == "auto");

 /// A path the AI gave (relative, or full and inside), as a full path inside root; throws with why it can't be.
 internal static string Inside(string root, string given)
 {
  string g = given.Trim();
  if (g is "" or "." or "/") return root;
  if (g.Replace('\\', '/').Split('/').Contains("..")) throw new InvalidOperationException("Give a path inside the working folder, like notes/todo.md, with no \"..\".");
  string full;
  try { full = Path.GetFullPath(Path.IsPathRooted(g) ? g : Path.Combine(root, g)).TrimEnd(Path.DirectorySeparatorChar); }
  catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException) { throw new InvalidOperationException("That isn't a path Still can use."); }
  if (full.Equals(root, StringComparison.OrdinalIgnoreCase)) return root;
  if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) || full.IndexOf(':', 2) >= 0) throw new InvalidOperationException("That's outside the working folder. To look at files elsewhere, ask the user with request_folder.");
  for (string at = full; at.Length > root.Length; at = Path.GetDirectoryName(at)!)
   if (Linked(at)) throw new InvalidOperationException(Path.GetRelativePath(root, at).Replace('\\', '/') + " is a link to somewhere else, so Still keeps you out of it.");
  return full;
 }
 /// A symbolic link or junction (not a OneDrive file, which is a reparse point too). Unreadable counts as one.
 static bool Linked(string path)
 {
  try { return (Directory.Exists(path) ? new DirectoryInfo(path) : (FileSystemInfo)new FileInfo(path)).LinkTarget != null; }
  catch (IOException) { return true; } catch (UnauthorizedAccessException) { return true; }
 }

 async Task<string> FolderTool(string who, string tool, JsonElement args)
 {
  if (runs.GetValueOrDefault(who) is not { } run) return Fail("Only a companion in Still's chat has a working folder.");
  string root = FolderOf(run.Chat), path = "", given = S(args, "path");
  string? why = null;
  if (root.Length > 0) try { path = Inside(root, given); } catch (InvalidOperationException ex) { why = ex.Message; }
  // A folder the user let it see, by its full path: list_files and read_file there, nothing else.
  bool look = false;
  if (path.Length == 0 && SeenFolder(run, given) is { } seen) {
   root = seen; look = true;
   try { path = Inside(root, given); } catch (InvalidOperationException ex) { return Fail(ex.Message); }
  }
  if (path.Length == 0) return Fail(why ?? (run.Chat.Ephemeral ? "Chats in a private window don't work in folders." : "This chat has no working folder. If the task needs files on the user's computer, ask for the folder with request_folder."));
  if (look && tool is not ("list_files" or "read_file")) return Fail($"You can only look in {root}: the user let you see it, not change it. To change files there, ask with request_folder and write: true.");
  string rel = look ? path : path == root ? "." : Path.GetRelativePath(root, path).Replace('\\', '/');
  if (tool != "list_files" && path == root) return Fail("Give the path of a file in the working folder, like notes/todo.md.");
  switch (tool) {
   case "list_files": {
    if (!Directory.Exists(path)) return Fail(rel + " isn't a folder. list_files with no path shows what's in the working folder.");
    var all = new DirectoryInfo(path).EnumerateFileSystemInfos().OrderBy(i => i is FileInfo).ThenBy(i => i.Name, StringComparer.OrdinalIgnoreCase).ToList();
    return Reply(new { folder = rel, items = all.Take(500).Select(i => i is FileInfo f ? f.Name + " (" + SizeText(f.Length) + ")" : i.Name + "/"), more = all.Count > 500 ? all.Count - 500 : (int?)null });
   }
   case "read_file":
    if (!File.Exists(path)) return Fail(rel + " isn't a file in the working folder. Use list_files to see what's there.");
    return ReadPage(path, rel, (long)Math.Max(0, N(args, "offset", 0)), "Tell the user what you can read.");
   case "write_file": {
    string content = S(args, "content");
    if (content.Length > 5_000_000) return Fail("That's too big: keep a file under 5 MB.");
    if (Directory.Exists(path)) return Fail(rel + " is a folder.");
    bool had = File.Exists(path);
    if (had && await MayChange(run, root, path, "Replace " + rel, "It replaces the whole file in your folder " + Path.GetFileName(root) + ".", delete: false) is { } no) return no;
    Directory.CreateDirectory(Path.GetDirectoryName(path)!);
    await File.WriteAllTextAsync(path, content, new UTF8Encoding(false));
    if (!had) run.Chat.Made.Add(path);
    return Reply(new { done = (had ? "Replaced " : "Created ") + rel });
   }
   case "edit_file": {
    if (!File.Exists(path)) return Fail(rel + " isn't a file in the working folder. Create it with write_file.");
    if (new FileInfo(path).Length > 5_000_000) return Fail(rel + " is over 5 MB, too big to edit here.");
    var bytes = await File.ReadAllBytesAsync(path);
    if (bytes.AsSpan().Contains((byte)0)) return Fail(rel + " isn't text.");
    bool bom = bytes.AsSpan().StartsWith(Encoding.UTF8.Preamble);
    string text = Encoding.UTF8.GetString(bytes, bom ? 3 : 0, bytes.Length - (bom ? 3 : 0)), old = S(args, "old"), put = S(args, "new");
    if (old.Length == 0) return Fail("Pass old: the exact text to change, as read_file shows it.");
    if (!text.Contains(old) && text.Contains("\r\n")) { old = old.ReplaceLineEndings("\r\n"); put = put.ReplaceLineEndings("\r\n"); }
    int count = (text.Length - text.Replace(old, "").Length) / old.Length;
    if (count == 0) return Fail($"That text isn't in {rel}. Read it again and copy the text exactly.");
    if (count > 1 && !B(args, "all")) return Fail($"That text is in {rel} {count} times. Pass more of the text around it, or all=true to change every one.");
    using (var f = File.Create(path)) { if (bom) f.Write(Encoding.UTF8.Preamble); f.Write(Encoding.UTF8.GetBytes(text.Replace(old, put))); }
    return Reply(new { done = $"Edited {rel}" + (count > 1 ? $" in {count} places" : "") });
   }
   case "delete_file":
    if (Directory.Exists(path)) return Fail(rel + " is a folder. Still deletes files one at a time.");
    if (!File.Exists(path)) return Fail(rel + " isn't a file in the working folder.");
    if (await MayChange(run, root, path, "Delete " + rel, "It goes to the Recycle Bin.", delete: true) is { } refused) return refused;
    if (!ToRecycleBin(path)) return Fail($"Couldn't delete {rel}. It may be open in another app.");
    run.Chat.Made.Remove(path);
    return Reply(new { done = $"Moved {rel} to the Recycle Bin" });
  }
  return Fail("Still has no tool by that name.");
 }

 /// The folder the user let this run see (until the reply ends, or for the chat) that holds this full path, if any.
 static string? SeenFolder(ChatRun run, string given)
 {
  string full;
  try { if (!Path.IsPathFullyQualified(given.Trim())) return null; full = Path.TrimEndingDirectorySeparator(Path.GetFullPath(given.Trim())); }
  catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException) { return null; }
  return run.Seen.Concat(run.Chat.Allowed.Where(a => a.StartsWith("see ", StringComparison.Ordinal)).Select(a => a[4..]))
   .FirstOrDefault(f => (full.Equals(f, StringComparison.OrdinalIgnoreCase) || full.StartsWith(f + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) && Directory.Exists(f));
 }
 /// request_folder: a companion asks to see a folder, or (write) to work in one. A card asks every time, at every level.
 /// To see: Allow once (until the reply ends), Allow for this chat, or Not now; list_files and read_file then reach it by
 /// full path, read-only. To work in: Allow makes it the chat's folder, Choose another folder lets the user pick one, Not
 /// now refuses. Never a folder that holds Still's data or apps' settings and keys (Guarded), which the user can still pick themselves.
 async Task<string> RequestFolder(string who, JsonElement args)
 {
  if (runs.GetValueOrDefault(who) is not { } run) return Fail("Only a companion in Still's chat can ask for a working folder.");
  if (run.Chat.Ephemeral) return Fail("Chats in a private window don't work in folders.");
  string given = S(args, "path").Trim(), why = CompanionMemory.Clip(S(args, "why").Trim().ReplaceLineEndings(" "), 200), path = "";
  try { if (Path.IsPathFullyQualified(given)) path = Path.TrimEndingDirectorySeparator(Path.GetFullPath(given)); }
  catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException) { }
  if (path.Length == 0 || !Directory.Exists(path)) return Fail($"There's no folder at {CompanionMemory.Clip(given, 200)}. Pass the full path of a folder that exists, like D:\\Photos\\frames, or ask the user where it is.");
  if (Guarded(path)) return Fail("That folder holds Still's data or apps' settings and keys, so Still won't offer it. Ask for the folder with the user's own files.");
  string name = Path.GetFileName(path) is { Length: > 0 } n ? n : path, work = FolderOf(run.Chat);
  if (!B(args, "write")) {
   if (work.Length > 0 && (path.Equals(work, StringComparison.OrdinalIgnoreCase) || path.StartsWith(work + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)))
    return Reply(new { done = path + " is in your working folder: list_files and read_file reach it already." });
   if (SeenFolder(run, path) != null) return Reply(new { done = "You can look in " + path + " already: list_files and read_file with full paths there." });
   string seen = await Approve(run, "See " + name, path, "see", why, countdown: false);
   Audit(run.Chat, "See " + path, name, seen switch { "once" => "You allowed it until this reply ends", "chat" => "You allowed it for this chat", "stop" => "Stopped", "timeout" => "No answer in 10 minutes", _ => "Not now" });
   if (seen == "chat") run.Chat.Allowed.Add("see " + path); else if (seen == "once") run.Seen.Add(path);
   PublishAiEverywhere();
   return seen is "once" or "chat"
    ? Reply(new { done = $"You can look in {path} {(seen == "chat" ? "for the rest of this chat" : "until you finish this reply")}: list_files and read_file with full paths there, like {Path.Combine(path, "notes.txt")}. It's read-only: to change files there, ask with request_folder and write: true." })
    : Fail(seen == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said not now. Carry on without it, or ask them in your reply.");
  }
  if (path.Equals(work, StringComparison.OrdinalIgnoreCase)) return Reply(new { done = "You already work in " + path });
  string answer = await Approve(run, "Work in " + name, path, "folder", why, countdown: false);
  if (answer == "pick") {
   var pick = new Microsoft.Win32.OpenFolderDialog { Title = "Pick a folder for this chat", InitialDirectory = path };
   if (pick.ShowDialog(this) == true) { path = Path.TrimEndingDirectorySeparator(pick.FolderName); answer = "picked"; } else answer = "deny";
  }
  Audit(run.Chat, "Work in " + path, name, answer switch { "once" => "You allowed it", "picked" => "You picked this folder", "stop" => "Stopped", "timeout" => "No answer in 10 minutes", _ => "Not now" });
  if (answer is not ("once" or "picked")) { PublishAiEverywhere(); return Fail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said not now. Carry on without the folder, or ask them in your reply."); }
  run.Chat.Folder = path; run.Chat.FolderTold = path;
  SaveAiChats(); PublishAiEverywhere();
  return Reply(new { done = $"You work in {path} now" + (answer == "picked" ? ", the folder the user picked" : "") + ": list_files, read_file, write_file, edit_file and delete_file reach the files there and nothing outside it." });
 }
 /// Still's own data, a folder of apps' settings and keys in the user's folder (AppData, .claude, .ssh…), or one holding any.
 static bool Guarded(string path)
 {
  static bool Under(string a, string b) => a.Equals(b, StringComparison.OrdinalIgnoreCase) || a.StartsWith(Path.TrimEndingDirectorySeparator(b) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
  string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
  if (new[] { App.DataRoot, App.ProfileHome, home }.Any(d => d.Length > 0 && Under(d, path))) return true; // the folder itself, or one it's in
  if (Under(path, App.DataRoot) || Under(path, App.ProfileHome)) return true;
  if (!Under(path, home)) return false;
  string first = Path.GetRelativePath(home, path).Split(Path.DirectorySeparatorChar)[0];
  return first.StartsWith('.') || first.Equals("AppData", StringComparison.OrdinalIgnoreCase);
 }

 /// Whether a replace or delete goes ahead: a file it made in this chat, Allow in this chat, or (replacing) Keep going say
 /// yes; otherwise the user answers in the chat. Null: go ahead; otherwise the refusal for the AI.
 async Task<string?> MayChange(ChatRun run, string root, string path, string what, string why, bool delete)
 {
  string key = "files " + root, site = Path.GetFileName(root);
  if (run.Chat.Made.Contains(path) || run.Chat.Allowed.Contains(key)) return null;
  if (!delete && KeepGoing(run.Chat)) { Audit(run.Chat, what, site, "Done without asking, as Keep going allows"); return null; }
  string answer = await Approve(run, what, site, "files", why, countdown: false);
  Audit(run.Chat, what, site, answer == "chat" ? "You allowed changes in this folder for this chat" : answer == "once" ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no");
  if (answer == "chat") run.Chat.Allowed.Add(key);
  PublishAiEverywhere();
  return answer is "once" or "chat" ? null : Fail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't try it again unless they ask.");
 }

 [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
 struct FileOp { public IntPtr Window; public uint Func; public string From; public string? To; public ushort Flags; public bool Aborted; public IntPtr Mappings; public string? Title; }
 [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern int SHFileOperation(ref FileOp op);
 /// To the Recycle Bin, with no dialog: FO_DELETE with FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_NOERRORUI and FOF_SILENT.
 static bool ToRecycleBin(string path)
 {
  var op = new FileOp { Func = 3, From = path + "\0\0", Flags = 0x0040 | 0x0010 | 0x0400 | 0x0004 };
  return SHFileOperation(ref op) == 0 && !op.Aborted && !File.Exists(path);
 }
}
