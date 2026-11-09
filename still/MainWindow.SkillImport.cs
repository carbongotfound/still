using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
namespace Still;
// Skills from GitHub or npm (Mac: SkillImport.swift). Still reads the SKILL.md files in a repository or package and shows
// them before adding any. Only their text comes over, as skills the user then gives to companions: never a script, a
// program, an MCP server or a package install. An added skill keeps where it came from (Source), and a chat that uses
// one counts as having read from the web, so a new site asks the way it does after reading a page (Reach).
public partial class MainWindow
{
 static readonly HttpClient SkillHttp = new(new SocketsHttpHandler { UseCookies = false, MaxAutomaticRedirections = 3, ConnectTimeout = TimeSpan.FromSeconds(10) }) { Timeout = TimeSpan.FromSeconds(30) };
 /// What the last look found, held so Add saves exactly what the user saw.
 static (string Source, List<(string Name, string Description, string Body)> Skills)? skillImport;
 const int SkillFileMax = 100_000, SkillImportMax = 20;
 [GeneratedRegex(@"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})(?:/(?:tree|blob)/([A-Za-z0-9._-]{1,100})((?:/[A-Za-z0-9._-]{1,100}){0,12}))?/*$")] private static partial Regex GitHubLink();
 [GeneratedRegex(@"^(?:(?:https?://)?(?:www\.)?npmjs\.com/package/|npm:\s*|npm\s+(?:i|install)\s+)((?:@[a-z0-9][a-z0-9._~-]{0,100}/)?[a-z0-9][a-z0-9._~-]{0,100})(?:(?:/v/|@)([0-9A-Za-z.+-]{1,60}))?/*$")] private static partial Regex NpmLink();
 [GeneratedRegex(@"(?im)^\s*(?:```|~~~)\s*(?:bash|sh|shell|zsh|console|powershell|pwsh|ps1|cmd|bat)\b")] private static partial Regex ShellBlock();
 [GeneratedRegex(@"(?i)\b(?:bash|shell|powershell|terminal)\b")] private static partial Regex ShellTool();

 async Task SkillImportLook(string link)
 {
  skillImport = null;
  try {
   var (source, found) = await SkillImportFind(link.Trim().Split('?', '#')[0].Trim());
   skillImport = (source, found.Select(k => (k.Name, k.Description, k.Body)).ToList());
   ShellSend(new { kind = "skillImport", source, skills = found.Select((k, i) => new { key = i, name = k.Name, description = k.Description, body = k.Body, notes = k.Notes, added = k.Added }) });
  } catch (InvalidDataException ex) { ShellSend(new { kind = "skillImport", error = ex.Message }); }
  catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or InvalidOperationException or FormatException or IOException) { App.Log(ex); ShellSend(new { kind = "skillImport", error = "Couldn't reach it. Check your connection and the link, then try again." }); }
 }

 static async Task<(string Source, List<(string Name, string Description, string Body, List<string> Notes, bool Added)> Found)> SkillImportFind(string link)
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
  List<(string, string, string, List<string>, bool)> found = [];
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
   if (ShellBlock().IsMatch(body) || ShellTool().IsMatch(head.GetValueOrDefault("allowed-tools", ""))) notes.Add("It runs commands on your computer, which Still's companions can't do, so parts of it may not work here.");
   int more = folder.Length == 0 ? 0 : files.Count(f => f.Path.StartsWith(folder + "/", StringComparison.Ordinal)) - 1;
   if (more > 0) notes.Add($"Its folder has {more} more file{(more == 1 ? "" : "s")} (scripts or notes) that Still doesn't bring.");
   if (body.Length > 20000) notes.Add("It's long: Still keeps the first 20,000 characters.");
   bool added = Skill.All.Any(k => k.Source == source && k.Name.Equals(title, StringComparison.OrdinalIgnoreCase));
   if (added) notes.Add("Already added from here.");
   found.Add((title, head.GetValueOrDefault("description", ""), body, notes, added));
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
 static async Task<string?> SkillGet(string url, int max)
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
  return Encoding.UTF8.GetString(buffer.ToArray());
 }

 void SkillImportAdd(JsonElement keys)
 {
  if (skillImport is not { } pending || keys.ValueKind != JsonValueKind.Array) return;
  int added = 0;
  try {
   foreach (int i in keys.EnumerateArray().Where(k => k.ValueKind == JsonValueKind.Number && k.TryGetInt32(out _)).Select(k => k.GetInt32()).Distinct())
    if (i >= 0 && i < pending.Skills.Count) { var (name, description, body) = pending.Skills[i]; Skill.Save("", name, description, "", body, pending.Source); added++; }
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { App.Log(ex); Toast("Couldn't add those skills."); }
  skillImport = null;
  if (added > 0) Toast(added == 1 ? "Added 1 skill. Give it to a companion to use it." : $"Added {added} skills. Give them to a companion to use them.");
  PublishAiEverywhere();
 }
}
