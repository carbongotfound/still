using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
namespace Still;
// Skills and plugins from GitHub or npm (Mac: SkillImport.swift). Still reads the SKILL.md files in a repository or package
// and shows them before adding any. A plugin (a folder with .claude-plugin/plugin.json), or a skill whose folder has a
// program in it (.py, .js, .sh), also brings that folder's files into the profile's plugins folder, and companions with
// its skills run those programs with run_plugin_program: only files inside it, through their interpreter, with the
// arguments as given and never a shell. It asks first unless the user set Plugin programs to Don't ask or allowed that
// plugin, and setup always asks. Never an MCP server or a hook. An added skill keeps where it came from (Source), and a
// chat that uses one or reads a program's output counts as having read from the web, so a new site asks the way it does
// after reading a page (Reach).
public partial class MainWindow
{
 static readonly HttpClient SkillHttp = new(new SocketsHttpHandler { UseCookies = false, MaxAutomaticRedirections = 3, ConnectTimeout = TimeSpan.FromSeconds(10) }) { Timeout = TimeSpan.FromSeconds(30) };
 /// What the last look found, held so Add saves exactly what the user saw.
 static (string Source, List<(string Name, string Description, string Body, SkillPack? Pack)> Skills)? skillImport;
 /// The files a plugin brings: its name, its folder in the repository ("" = the top) and each file's path from the top.
 sealed record SkillPack(string Name, string Root, List<string> Files, Func<string, string> Address);
 const int SkillFileMax = 100_000, SkillImportMax = 20, PackFilesMax = 300, PackFileMax = 5_000_000, PackBytesMax = 25_000_000;
 internal static string PluginsFolder => Path.Combine(App.DataRoot, "plugins");
 static bool IsProgram(string path) => Path.GetExtension(path).ToLowerInvariant() is ".py" or ".js" or ".mjs" or ".cjs" or ".sh";
 [GeneratedRegex(@"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})(?:/(?:tree|blob)/([A-Za-z0-9._-]{1,100})((?:/[A-Za-z0-9._-]{1,100}){0,12}))?/*$")] private static partial Regex GitHubLink();
 [GeneratedRegex(@"^(?:(?:https?://)?(?:www\.)?npmjs\.com/package/|npm:\s*|npm\s+(?:i|install)\s+)((?:@[a-z0-9][a-z0-9._~-]{0,100}/)?[a-z0-9][a-z0-9._~-]{0,100})(?:(?:/v/|@)([0-9A-Za-z.+-]{1,60}))?/*$")] private static partial Regex NpmLink();
 [GeneratedRegex(@"(?im)^\s*(?:```|~~~)\s*(?:bash|sh|shell|zsh|console|powershell|pwsh|ps1|cmd|bat)\b")] private static partial Regex ShellBlock();
 [GeneratedRegex(@"(?i)\b(?:bash|shell|powershell|terminal)\b")] private static partial Regex ShellTool();

 async Task SkillImportLook(string link)
 {
  skillImport = null;
  try {
   var (source, found) = await SkillImportFind(link.Trim().Split('?', '#')[0].Trim());
   skillImport = (source, found.Select(k => (k.Name, k.Description, k.Body, k.Pack)).ToList());
   ShellSend(new { kind = "skillImport", source, skills = found.Select((k, i) => new { key = i, name = k.Name, description = k.Description, body = k.Body, notes = k.Notes, added = k.Added }) });
  } catch (InvalidDataException ex) { ShellSend(new { kind = "skillImport", error = ex.Message }); }
  catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or InvalidOperationException or FormatException or IOException) { App.Log(ex); ShellSend(new { kind = "skillImport", error = "Couldn't reach it. Check your connection and the link, then try again." }); }
 }

 static async Task<(string Source, List<(string Name, string Description, string Body, List<string> Notes, bool Added, SkillPack? Pack)> Found)> SkillImportFind(string link)
 {
  List<(string Path, long Size)> files; string source, name, prefix = ""; Func<string, string> address;
  if (GitHubLink().Match(link) is { Success: true } gh) {
   string owner = gh.Groups[1].Value, repo = gh.Groups[2].Value is var r && r.EndsWith(".git", StringComparison.OrdinalIgnoreCase) ? r[..^4] : r, at = gh.Groups[3].Success ? gh.Groups[3].Value : "HEAD";
   prefix = gh.Groups[4].Value.Trim('/');
   if (prefix.Split('/').Any(p => p is "." or "..") || at is "." or "..") throw new InvalidDataException("That link doesn't look right.");
   if (Path.GetFileName(prefix).Equals("SKILL.md", StringComparison.OrdinalIgnoreCase)) prefix = prefix.Contains('/') ? prefix[..prefix.LastIndexOf('/')] : "";
   string tree = await SkillGet($"https://api.github.com/repos/{owner}/{repo}/git/trees/{at}?recursive=1", 8_000_000)
    ?? throw new InvalidDataException("Couldn't find that on GitHub. It may be private, or the link may be wrong.");
   files = [.. (JsonNode.Parse(tree)?["tree"]?.AsArray() ?? []).Where(n => n?["type"]?.ToString() == "blob").Select(n => (n!["path"]?.ToString() ?? "", n["size"]?.GetValue<long>() ?? 0))];
   source = $"github.com/{owner}/{repo}" + (prefix.Length > 0 ? "/" + prefix : ""); name = repo;
   address = path => $"https://raw.githubusercontent.com/{owner}/{repo}/{at}/{string.Join('/', path.Split('/').Select(Uri.EscapeDataString))}";
  } else if (NpmLink().Match(link) is { Success: true } npm) {
   string package = npm.Groups[1].Value, version = npm.Groups[2].Value;
   if (version.Length == 0) {
    string resolved = await SkillGet($"https://data.jsdelivr.com/v1/packages/npm/{package}/resolved", 100_000) ?? throw new InvalidDataException("Couldn't find that package on npm.");
    version = JsonNode.Parse(resolved)?["version"]?.ToString() ?? "";
    if (!Regex.IsMatch(version, @"^[0-9A-Za-z.+-]{1,60}$")) throw new InvalidDataException("Couldn't find that package on npm.");
   }
   string list = await SkillGet($"https://data.jsdelivr.com/v1/packages/npm/{package}@{version}?structure=flat", 8_000_000) ?? throw new InvalidDataException("Couldn't find that version on npm.");
   files = [.. (JsonNode.Parse(list)?["files"]?.AsArray() ?? []).Select(n => ((n?["name"]?.ToString() ?? "").TrimStart('/'), n?["size"]?.GetValue<long>() ?? 0))];
   source = $"npm: {package}@{version}"; name = package[(package.IndexOf('/') + 1)..];
   address = path => $"https://cdn.jsdelivr.net/npm/{package}@{version}/{string.Join('/', path.Split('/').Select(Uri.EscapeDataString))}";
  } else throw new InvalidDataException("Paste a GitHub link (github.com/owner/repo) or an npm package (npmjs.com/package/name, or npm:name).");

  string under = prefix.Length > 0 ? prefix + "/" : "";
  var skillFiles = files.Where(f => f.Path.StartsWith(under, StringComparison.Ordinal) && !f.Path.Contains("node_modules/") && Path.GetFileName(f.Path).Equals("SKILL.md", StringComparison.OrdinalIgnoreCase))
   .OrderBy(f => f.Path.Count(c => c == '/')).ThenBy(f => f.Path, StringComparer.Ordinal).Take(SkillImportMax).ToList();
  if (skillFiles.Count == 0) throw new InvalidDataException("No skills there. Still looks for SKILL.md files, the way Claude Code and other AI apps keep skills.");
  // A plugin brings its whole folder. Otherwise a skill brings its own folder when there's a program in it.
  bool plugin = files.Any(f => f.Path == under + ".claude-plugin/plugin.json");
  string pluginName = name;
  if (plugin && await SkillGet(address(under + ".claude-plugin/plugin.json"), 100_000) is { } manifest)
   try { if (JsonNode.Parse(manifest)?["name"]?.ToString() is { Length: > 0 } named) pluginName = named; } catch (JsonException) { }
  Dictionary<string, (SkillPack?, string?)> packs = [];
  (SkillPack? Pack, string? Note) PackOf(string root, string title)
  {
   if (packs.TryGetValue(root, out var known)) return known;
   string inRoot = root.Length > 0 ? root + "/" : "";
   var inside = files.Where(f => f.Path.StartsWith(inRoot, StringComparison.Ordinal) && !f.Path.Split('/').Any(p => p is ".git" or "node_modules")).ToList();
   var programs = inside.Where(f => IsProgram(f.Path)).Select(f => Path.GetFileName(f.Path)).ToList();
   return packs[root] = programs.Count == 0 ? (null, null)
    : inside.Count > PackFilesMax || inside.Sum(f => f.Size) > PackBytesMax || inside.Any(f => f.Size > PackFileMax) ? (null, "Its programs are too big to bring (over 300 files or 25 MB), so only its text comes over.")
    : (new(title, root, [.. inside.Select(f => f.Path)], address), $"It comes with {programs.Count} program{(programs.Count == 1 ? "" : "s")} ({string.Join(", ", programs.Take(3))}{(programs.Count > 3 ? "…" : "")}) that companions can run on your computer. Add it only if you trust where it's from.");
  }
  List<(string, string, string, List<string>, bool, SkillPack?)> found = [];
  foreach (var (path, size) in skillFiles) {
   if (size > SkillFileMax) continue;
   string? text = await SkillGet(address(path), SkillFileMax);
   if (text == null) continue;
   var (head, body) = SkillHead(text);
   string folder = path.Contains('/') ? path[..path.LastIndexOf('/')] : "";
   string title = head.GetValueOrDefault("name") is { Length: > 0 } n ? n : folder.Length > 0 ? folder[(folder.LastIndexOf('/') + 1)..] : name;
   if (title.Length > 60) title = title[..60];
   if (body.Trim().Length == 0) continue;
   List<string> notes = [];
   var (pack, packNote) = PackOf(plugin ? under.TrimEnd('/') : folder, plugin ? pluginName : title);
   if (packNote != null) notes.Add(packNote);
   if (pack == null && (ShellBlock().IsMatch(body) || ShellTool().IsMatch(head.GetValueOrDefault("allowed-tools", "")))) notes.Add("It runs commands on your computer, which Still's companions can't do, so parts of it may not work here.");
   int more = folder.Length == 0 ? 0 : files.Count(f => f.Path.StartsWith(folder + "/", StringComparison.Ordinal)) - 1;
   if (pack == null && more > 0) notes.Add($"Its folder has {more} more file{(more == 1 ? "" : "s")} (notes or data) that Still doesn't bring.");
   if (body.Length > 20000) notes.Add("It's long: Still keeps the first 20,000 characters.");
   bool added = Skill.All.Any(k => k.Source == source && k.Name.Equals(title, StringComparison.OrdinalIgnoreCase));
   if (added) notes.Add("Already added from here.");
   found.Add((title, head.GetValueOrDefault("description", ""), body, notes, added, pack));
  }
  if (found.Count == 0) throw new InvalidDataException("Couldn't read the skills there. Try again in a bit.");
  return (source, found);
 }

 /// An imported SKILL.md's front matter, read the way such files write it: quoted values, and a value continued on the
 /// lines under it ("description: >"). Still's own skills keep one plain line each (Skill.Split).
 static (Dictionary<string, string> Head, string Body) SkillHead(string text)
 {
  var (_, body) = Skill.Split(text);
  text = text.ReplaceLineEndings("\n"); Dictionary<string, string> head = [];
  if (!text.StartsWith("---\n") || text.IndexOf("\n---", 4) is not (var end and > 0)) return (head, body);
  string? key = null;
  foreach (var line in text[4..end].Split('\n')) {
   if (key != null && line.Length > 0 && char.IsWhiteSpace(line[0])) { head[key] = (head[key] + " " + line.Trim()).Trim(); continue; }
   key = null;
   if (line.IndexOf(':') is not (var at and > 0)) continue;
   string k = line[..at].Trim().ToLowerInvariant(), v = line[(at + 1)..].Trim();
   if (v.Length >= 2 && (v[0] == '"' && v[^1] == '"' || v[0] == '\'' && v[^1] == '\'')) v = v[1..^1];
   head[k] = v is ">" or "|" or ">-" or "|-" or ">+" or "|+" ? "" : v;
   if (head[k].Length == 0) key = k; // the value is on the lines under it
  }
  return (head, body);
 }

 /// A GET with a size cap. Test builds send it to their own server (STILL_QA_SKILL_HUB) instead of the real sites.
 static async Task<string?> SkillGet(string url, int max) => await SkillGetBytes(url, max) is { } bytes ? Encoding.UTF8.GetString(bytes) : null;
 static async Task<byte[]?> SkillGetBytes(string url, int max)
 {
  if (App.IsQa && Environment.GetEnvironmentVariable("STILL_QA_SKILL_HUB") is { Length: > 0 } hub) url = hub.TrimEnd('/') + "/" + url["https://".Length..];
  using var request = new HttpRequestMessage(HttpMethod.Get, url);
  request.Headers.UserAgent.ParseAdd("Still");
  using var response = await SkillHttp.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
  if (response.StatusCode is HttpStatusCode.Forbidden or HttpStatusCode.TooManyRequests)
   throw new InvalidDataException((url.Contains("github") ? "GitHub" : "npm") + " is limiting requests right now. Try again in an hour.");
  if (!response.IsSuccessStatusCode || response.Content.Headers.ContentLength > max) return null;
  await using var stream = await response.Content.ReadAsStreamAsync();
  var buffer = new MemoryStream(); var chunk = new byte[65536];
  for (int n; (n = await stream.ReadAsync(chunk)) > 0;) { if (buffer.Length + n > max) return null; buffer.Write(chunk, 0, n); }
  return buffer.ToArray();
 }

 async Task SkillImportAdd(JsonElement keys)
 {
  if (skillImport is not { } pending || keys.ValueKind != JsonValueKind.Array) return;
  skillImport = null; // once: a second Add while the files come does nothing
  int added = 0; Dictionary<SkillPack, string> placed = [];
  try {
   foreach (int i in keys.EnumerateArray().Where(k => k.ValueKind == JsonValueKind.Number && k.TryGetInt32(out _)).Select(k => k.GetInt32()).Distinct())
    if (i >= 0 && i < pending.Skills.Count) {
     var (name, description, body, pack) = pending.Skills[i];
     string plugin = "";
     if (pack != null && !placed.TryGetValue(pack, out plugin!)) placed[pack] = plugin = await PackPlace(pack);
     Skill.Save("", name, description, "", body, pending.Source, plugin); added++;
    }
  } catch (InvalidDataException ex) { Toast(ex.Message); }
  catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or HttpRequestException or TaskCanceledException) { App.Log(ex); Toast("Couldn't add those skills."); }
  if (added > 0) Toast(added == 1 ? "Added 1 skill. Every companion can use it." : $"Added {added} skills. Every companion can use them.");
  PublishAiEverywhere();
 }

 /// Brings a plugin's files into a new folder of its own under the profile's plugins folder (all of them or none), each
 /// path checked to stay inside it, and returns the folder's name: the plugin's id.
 static async Task<string> PackPlace(SkillPack pack)
 {
  string slug = Regex.Replace(pack.Name.ToLowerInvariant(), "[^a-z0-9]+", "-").Trim('-') is { Length: > 0 } s ? (s.Length > 40 ? s[..40].Trim('-') : s) : "plugin";
  string id = slug; for (int n = 2; Directory.Exists(Path.Combine(PluginsFolder, id)); n++) id = slug + "-" + n;
  string root = Path.Combine(PluginsFolder, id), part = root + ".part", inRoot = pack.Root.Length > 0 ? pack.Root + "/" : "";
  if (Directory.Exists(part)) Directory.Delete(part, true);
  Directory.CreateDirectory(part);
  try {
   foreach (string path in pack.Files) {
    string rel = path[inRoot.Length..], to = Path.GetFullPath(Path.Combine(part, rel));
    if (rel.Split('/').Any(p => p is "" or "." or ".." || p.IndexOfAny([':', '\\']) >= 0 || p.EndsWith('.') || p.EndsWith(' ') || Regex.IsMatch(p, @"^(con|prn|aux|nul|com\d|lpt\d)(\.|$)", RegexOptions.IgnoreCase))
     || !to.StartsWith(part + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) continue; // a name that would leave the folder, or one Windows can't keep
    byte[] data = await SkillGetBytes(pack.Address(path), PackFileMax) ?? throw new InvalidDataException("Couldn't bring the plugin's files. Try again in a bit.");
    Directory.CreateDirectory(Path.GetDirectoryName(to)!);
    await File.WriteAllBytesAsync(to, data);
   }
   Directory.Move(part, root);
  } catch { try { Directory.Delete(part, true); } catch (IOException) { } throw; }
  return id;
 }

 /// A plugin goes with its last skill: its folder, and the user's Always for it.
 void PluginRemove(string id)
 {
  if (!Regex.IsMatch(id, "^[a-z0-9-]{1,48}$")) return;
  try { if (Directory.Exists(Path.Combine(PluginsFolder, id))) Directory.Delete(Path.Combine(PluginsFolder, id), true); }
  catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { App.Log(ex); }
  if (Prefs.PluginsAllowed.Remove(id)) SaveLater();
 }

 /// A plugin's programs as a companion names them: paths inside its folder, without the folders its setup fills.
 internal static string[] Programs(string id) => Path.Combine(PluginsFolder, id) is var root && Directory.Exists(root)
  ? [.. Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories).Select(f => Path.GetRelativePath(root, f).Replace('\\', '/'))
   .Where(f => IsProgram(f) && !f.Split('/').Any(p => p.StartsWith('.') || p is "node_modules" or "__pycache__" or "venv" or "site-packages")).Order(StringComparer.Ordinal).Take(40)] : [];

 /// run_plugin_program: a program inside one of the companion's plugins, through its interpreter, with the arguments as
 /// given (never a shell), in the companion's working folder or else the plugin's. It asks first unless the companion
 /// (and anyone it's helping) is on Keep going or the user allowed this plugin; setup and install programs always ask. Stopping the chat stops it.
 async Task<string> PluginProgram(string who, JsonElement args)
 {
  var run = runs.GetValueOrDefault(who);
  var mine = run == null ? null : Companions.FirstOrDefault(c => c.Id == run.Chat.Companion);
  if (run == null || mine == null) return Fail("Only a companion in Still's chat can run its plugins' programs.");
  if (run.Chat.Ephemeral) return Fail("Plugin programs don't run in a private window.");
  string id = S(args, "plugin").Trim(), root = Path.Combine(PluginsFolder, id);
  var skill = Regex.IsMatch(id, "^[a-z0-9-]{1,48}$") ? Skill.All.FirstOrDefault(k => k.Plugin == id && k.For(mine)) : null;
  if (skill == null || !Directory.Exists(root)) return Fail($"You don't have a plugin \"{id}\". Use the plugin id load_skill gave you.");
  string full = Path.GetFullPath(Path.Combine(root, Regex.Replace(S(args, "program").Trim().Replace('\\', '/'), @"^(?:\$\{?CLAUDE_PLUGIN_ROOT\}?|\.)/", "")));
  if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) || !File.Exists(full) || !IsProgram(full))
   return Fail("That isn't one of its programs. Its programs: " + string.Join(", ", Programs(id)) + ".");
  string rel = Path.GetRelativePath(root, full).Replace('\\', '/');
  string? exe = Path.GetExtension(full).ToLowerInvariant() switch {
   ".py" => "python", ".sh" => new[] { "ProgramFiles", "ProgramW6432" }.Select(Environment.GetEnvironmentVariable).Where(d => !string.IsNullOrEmpty(d))
    .Select(d => Path.Combine(d!, "Git", "bin", "bash.exe")).FirstOrDefault(File.Exists), _ => "node" };
  if (exe == null) return Fail("It's a shell script, and this computer has no bash to run it (Git for Windows brings one). Tell the user.");
  string[] given = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("args", out var a) && a.ValueKind == JsonValueKind.Array
   ? [.. a.EnumerateArray().Select(x => x.ValueKind == JsonValueKind.String ? x.GetString()! : x.GetRawText())] : [];
  if (given.Length > 40 || given.Any(x => x.Length > 4000)) return Fail("Too many or too long arguments: 40 at most, 4,000 characters each.");
  bool setup = Regex.IsMatch(Path.GetFileNameWithoutExtension(full), "setup|install", RegexOptions.IgnoreCase);
  string what = "Run " + rel + (given.Length > 0 ? " " + Clip(string.Join(" ", given), 80) : "");
  bool auto = KeepGoing(run.Chat);
  if (setup || !auto && !Prefs.PluginsAllowed.Contains(id)) {
   string answer = await Approve(run, what, skill.Source, setup ? "plugin" : "program",
    setup ? "Setup can install other programs on your computer. It runs at your own risk." : "A program from a plugin you added. It runs on your computer with your access.", countdown: false);
   Audit(run.Chat, what, skill.Source, answer == "always" ? "You allowed this plugin" : answer == "once" ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no");
   if (answer == "always" && !setup && !Prefs.PluginsAllowed.Contains(id)) { Prefs.PluginsAllowed.Add(id); SaveLater(); }
   PublishAiEverywhere();
   if (answer is not ("once" or "always")) return Fail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't run it again unless they ask.");
  } else Audit(run.Chat, what, skill.Source, "Ran without asking, as Keep going allows");
  if (ExchangeOf(run.Chat).Root is var fromWeb) fromWeb.Read = Math.Max(fromWeb.Read, 1); // its output is someone else's text, like a page
  Step(run.Chat, "Ran " + rel); PublishAiEverywhere();
  int seconds = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("timeout", out var t) && t.TryGetDouble(out var d) ? (int)Math.Clamp(d, 5, 600) : 120;
  var start = new System.Diagnostics.ProcessStartInfo(exe) { WorkingDirectory = mine.Folder is { Length: > 0 } f && Directory.Exists(f) ? f : root, UseShellExecute = false, CreateNoWindow = true,
   RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
  start.ArgumentList.Add(full); foreach (var x in given) start.ArgumentList.Add(x);
  foreach (var key in start.Environment.Keys.Where(k => k.StartsWith("STILL_", StringComparison.OrdinalIgnoreCase)).ToList()) start.Environment.Remove(key);
  start.Environment["CLAUDE_PLUGIN_ROOT"] = root; start.Environment["PYTHONIOENCODING"] = "utf-8";
  var output = new StringBuilder();
  void Add(string? line) { if (line == null) return; lock (output) { output.AppendLine(line); if (output.Length > 60_000) output.Remove(0, output.Length - 40_000); } }
  using var p = new System.Diagnostics.Process { StartInfo = start };
  p.OutputDataReceived += (_, e) => Add(e.Data); p.ErrorDataReceived += (_, e) => Add(e.Data);
  try { p.Start(); } catch (System.ComponentModel.Win32Exception) { return Fail($"Couldn't start {Path.GetFileNameWithoutExtension(exe)}: it isn't installed on this computer, or isn't on its PATH. Tell the user."); }
  p.StandardInput.Close(); p.BeginOutputReadLine(); p.BeginErrorReadLine();
  var until = DateTime.UtcNow.AddSeconds(seconds); bool cut = false;
  while (!p.HasExited) {
   if (DateTime.UtcNow > until || run.Stopped) { cut = true; try { p.Kill(true); } catch (InvalidOperationException) { } break; }
   await Task.Delay(200);
  }
  try { await p.WaitForExitAsync(new CancellationTokenSource(5000).Token); } catch (OperationCanceledException) { } // the rest of its output
  string text; lock (output) text = output.ToString().TrimEnd();
  if (text.Length > 20_000) text = "…" + text[^20_000..];
  return Reply(new { exitCode = cut || !p.HasExited ? -1 : p.ExitCode, timedOut = cut && !run.Stopped, output = text });
 }
}
