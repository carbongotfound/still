using System.Diagnostics;
using System.IO;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Still;

public sealed record AgentModel(string Id, string Name, string[] Efforts);
/// One run: the prompt (sent on stdin, or in a prompt file, never on the command line), the model and effort picked from
/// the adapter's own list, the folder it runs in, the command that starts Still's MCP server, and the chat's session.
public sealed record RunRequest(string Prompt, string Model, string Effort, string Folder, IReadOnlyList<string> Mcp, string? Session, bool Resume)
{
 public bool Forget { get; init; } // an incognito chat: the app saves no session (only where it has a documented option)
 public string Job { get; init; } = "chats"; // what the run is for, in an API provider's spending: chats, titles or setup
 public string PromptFile => Path.Combine(Folder, "prompt-" + (Session ?? "run") + ".txt");
}

/// An AI agent app on the user's PC that Still drives headless. Still never reads its login; it only asks the app whether
/// it is signed in. Every run goes through Still's MCP server and nothing else.
public abstract class AgentAdapter
{
 public required string Id { get; init; }        // "claude", "grok", "chatgpt" or a manifest's id
 public required string Name { get; init; }      // what the user sees: "Claude", "Grok", "ChatGPT"
 public required string App { get; init; }       // the app, for messages: "Claude Code", "Grok Build"
 public required string Command { get; init; }
 public string Maker { get; init; } = "";
 public string Installer { get; init; } = "";    // the maker's install script; "" = Still never installs it
 public string InstallCommand { get; init; } = ""; // shown for the user to copy
 public string Site { get; init; } = "";
 public bool Secondary { get; init; }            // listed under "More agents": OpenCode and manifest agents
 public string TerminalSignIn { get; init; } = ""; // the user runs this in a terminal to sign in; Still never runs it
 public bool Compatible { get; init; }           // built from the app's docs and package, not yet run live: labelled Compatible
 public virtual bool PromptOnStdin => true;
 /// Still picks the session id up front (so a stopped first run can still be resumed); otherwise the app reports it.
 public virtual bool NamesSession => false;
 /// It can run without saving the session on this computer (incognito chats): each turn is then a new session that carries the chat so far.
 public virtual bool Forgets => false;

 /// Signed in? null when the app can't say. Uses none of the user's AI usage.
 public abstract Task<bool?> Detect(string exe);
 public virtual Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", [])]);
 /// The command line for one run. It may write config files into the run's folder.
 public abstract Task<List<string>> Args(string exe, RunRequest r);
 public abstract IEnumerable<AgentEvent> Parse(JsonNode e);
 /// A line that isn't JSON. Agents with plain output speak in lines.
 public virtual IEnumerable<AgentEvent> Plain(string line) => [];
 /// Settings the app needs for a run, added to its environment. Never one of the stripped keys.
 public virtual IReadOnlyDictionary<string, string> Env { get; } = new Dictionary<string, string>();
 /// What it can't do the way the others can, said on its card instead of hidden.
 public virtual string[] Gaps => [];
 /// Login settings from the user's environment that this app keeps. Every other app loses them (ApiKeys).
 public virtual string[] Kept => [];
 /// Set when its runs bill something other than the app's own sign-in: what its card says about that.
 public virtual string Billing => "";

 public virtual Task<AgentRun> Start(string exe, RunRequest r) => CliRun.Start(this, exe, r);

 // Keys that would bill an API account instead of the app's own sign-in. Removed from every app except what it keeps (Kept), and Still never sets one.
 static readonly string[] ApiKeys = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
  "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_BASE_URL", "GOOGLE_GENAI_USE_VERTEXAI"];
 internal static bool Stripped(string key) => ApiKeys.Contains(key, StringComparer.OrdinalIgnoreCase);

 public static ProcessStartInfo Launch(string exe, string folder, IEnumerable<string> args, IReadOnlyDictionary<string, string>? env = null, string[]? keep = null)
 {
  var start = new ProcessStartInfo { WorkingDirectory = folder, UseShellExecute = false, CreateNoWindow = true };
  foreach (var key in ApiKeys.Except(keep ?? [])) start.Environment.Remove(key);
  foreach (var (key, value) in env ?? new Dictionary<string, string>()) if (!Stripped(key)) start.Environment[key] = value;
  if (exe.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) { start.FileName = exe; foreach (var a in args) start.ArgumentList.Add(a); return start; }
  // npm installs .cmd launchers, which only cmd.exe runs. Every argument is Still's own (paths, flags, ids).
  start.FileName = Path.Combine(Environment.SystemDirectory, "cmd.exe");
  start.Arguments = "/d /s /c \"" + string.Join(" ", args.Prepend(exe).Select(a => "\"" + a + "\"")) + "\"";
  return start;
 }

 /// Runs the app briefly and returns what it printed (stdout, then stderr), or null if it didn't finish in time.
 protected async Task<string?> Output(string exe, string folder, params string[] args) => await Printed(exe, folder, args) is { } p ? p[0] + "\n" + p[1] : null;
 protected async Task<string[]?> Printed(string exe, string folder, params string[] args)
 {
  Directory.CreateDirectory(folder);
  var start = Launch(exe, folder, args, keep: Kept);
  start.RedirectStandardInput = start.RedirectStandardOutput = start.RedirectStandardError = true;
  start.StandardOutputEncoding = start.StandardErrorEncoding = new UTF8Encoding(false);
  using var p = Process.Start(start)!;
  p.StandardInput.Close();
  try { return await Task.WhenAll(p.StandardOutput.ReadToEndAsync(), p.StandardError.ReadToEndAsync()).WaitAsync(TimeSpan.FromSeconds(20)); }
  catch (TimeoutException) { return null; }
  finally { try { if (!p.HasExited) p.Kill(true); } catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception) { } }
 }
}

sealed class ClaudeAdapter : AgentAdapter
{
 public override bool NamesSession => true;
 public override bool Forgets => true; // --no-session-persistence
 static readonly string[] Levels = ["low", "medium", "high", "xhigh", "max"];
 // Claude Code's own login methods stay available: products that run it may not remove or restrict them.
 public override string[] Kept => ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"];
 string billing = "";
 public override string Billing => billing;
 public override async Task<bool?> Detect(string exe)
 {
  // The setting sources a run uses: with its default ones, a login in the user's settings file reads as signed in and the run then says it isn't.
  var printed = await Printed(exe, MainWindow.AiFolder, "--setting-sources", "project,local", "auth", "status");
  billing = "";
  try {
   if (printed == null) return null;
   var status = JsonNode.Parse(printed[0]);
   billing = WhoBills(status?["apiProvider"]?.GetValue<string>(), status?["authMethod"]?.GetValue<string>(), status?["apiKeySource"]?.GetValue<string>());
   return status?["loggedIn"]?.GetValue<bool>() ?? false;
  }
  catch (Exception ex) when (ex is JsonException or ArgumentException) { return false; }
 }
 /// From what `claude auth status` says. "" = Claude's own sign-in. An auth token reads the same there as a subscription
 /// token, so this also looks whether that variable is set, never at its value.
 static string WhoBills(string? provider, string? method, string? keySource) => (provider, method) switch {
  ("bedrock", _) => "Using Amazon Bedrock from your environment. Your AWS account is billed.",
  ("vertex", _) => "Using Google Cloud from your environment. Your Google Cloud account is billed.",
  ("foundry", _) => "Using Microsoft Foundry from your environment. Your Azure account is billed.",
  (_, "third_party") => "Using a cloud provider from your environment. Your account there is billed.",
  (_, "api_key") when keySource == "ANTHROPIC_API_KEY" => "Using an API key from your environment. Your API account is billed.",
  (_, "api_key" or "api_key_helper") => "Using an API key. Your API account is billed.",
  (_, "oauth_token") when Environment.GetEnvironmentVariable("ANTHROPIC_AUTH_TOKEN") is { Length: > 0 } => "Using an auth token from your environment. The account it belongs to is billed.",
  _ => "",
 };
 public override Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", Levels), new("fable", "Fable", Levels),
  new("opus", "Opus", Levels), new("sonnet", "Sonnet", Levels), new("haiku", "Haiku", Levels)]);
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  string config = Path.Combine(r.Folder, "mcp.json");
  File.WriteAllText(config, JsonSerializer.Serialize(new { mcpServers = new { still = new { command = Environment.ProcessPath, args = r.Mcp } } }));
  List<string> args = ["-p", "--output-format", "stream-json", "--verbose", "--mcp-config", config, "--strict-mcp-config", "--allowedTools", "mcp__still", r.Resume ? "--resume" : "--session-id", r.Session!,
   "--disable-slash-commands", "--setting-sources", "project,local"]; // none of the user's own skills, commands, plugins or settings
  if (r.Forget) args.Add("--no-session-persistence");
  args.AddRange(["--tools", ""]); // none of its own: files go through Still's tools, in the working folder only (MainWindow.Folder.cs)
  if (r.Model.Length > 0) args.AddRange(["--model", r.Model]);
  if (r.Effort.Length > 0) args.AddRange(["--effort", r.Effort]);
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.Messages(e, false);
}

sealed class GrokAdapter : AgentAdapter
{
 public override bool PromptOnStdin => false;
 public override bool NamesSession => true;
 // Grok has no status command; listing models needs a sign-in and says so.
 public override async Task<bool?> Detect(string exe) => await Output(exe, MainWindow.AiFolder, "models") is { } text ? !text.Contains("not authenticated", StringComparison.OrdinalIgnoreCase) : null;
 public override async Task<AgentModel[]> Models(string exe)
 {
  List<AgentModel> list = [new("", "Default", MainWindow.Efforts)];
  foreach (System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(await Output(exe, MainWindow.AiFolder, "models") ?? "", @"^\s*[*-]\s+(\S+)", System.Text.RegularExpressions.RegexOptions.Multiline))
   list.Add(new(m.Groups[1].Value, m.Groups[1].Value, [])); // its effort levels per model aren't listed: default effort only
  return [.. list];
 }
 public override async Task<List<string>> Args(string exe, RunRequest r)
 {
  // Grok reads MCP servers from the folder's .grok/config.toml, and only starts them with --trust. Its own approval
  // prompts would stall a headless run; Still decides inside its MCP server, and Grok's own tools are off (--tools).
  await Output(exe, r.Folder, ["mcp", "add", "-s", "project", "still", Environment.ProcessPath!, "--", .. r.Mcp]);
  File.WriteAllText(r.PromptFile, r.Prompt, new UTF8Encoding(false));
  List<string> args = ["--prompt-file", r.PromptFile, "--output-format", "streaming-messages-json", "--trust", "--tools", "search_tool,use_tool", "--no-subagents", "--always-approve", r.Resume ? "-r" : "-s", r.Session!];
  if (r.Model.Length > 0) args.AddRange(["-m", r.Model]);
  if (r.Effort.Length > 0) args.AddRange(["--reasoning-effort", r.Effort]);
  return args;
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.Messages(e, true);
}

/// ChatGPT, through OpenAI's agent CLI signed in with the user's ChatGPT plan. The UI only ever calls it ChatGPT.
sealed class ChatGptAdapter : AgentAdapter
{
 public override bool Forgets => true; // exec --ephemeral
 public override async Task<bool?> Detect(string exe)
 {
  if (await Output(exe, MainWindow.AiFolder, "login", "status") is not { } text) return null;
  // An API key login would bill an API account: only a ChatGPT sign-in counts.
  return text.Contains("Logged in") && !text.Contains("Not logged in") && !text.Contains("API key", StringComparison.OrdinalIgnoreCase);
 }
 public override async Task<AgentModel[]> Models(string exe)
 {
  List<AgentModel> list = [new("", "Default", ["low", "medium", "high", "xhigh"])];
  try {
   foreach (var m in JsonNode.Parse(await Output(exe, MainWindow.AiFolder, "debug", "models") ?? "")?["models"] as JsonArray ?? [])
    if (m?["visibility"]?.GetValue<string>() == "list" && m["slug"]?.GetValue<string>() is { } slug)
     list.Add(new(slug, m["display_name"]?.GetValue<string>() ?? slug, (m["supported_reasoning_levels"] as JsonArray ?? []).Select(l => l?["effort"]?.GetValue<string>() ?? "").Where(l => l.Length > 0).ToArray()));
  } catch (JsonException) { }
  return [.. list];
 }
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  // TOML literal strings ('...') need no escaping but can't hold an apostrophe; cmd.exe eats "!".
  if (r.Mcp.Append(Environment.ProcessPath!).Any(a => a.Contains('\'') || a.Contains('!'))) throw new InvalidOperationException("ChatGPT can't run Still from a folder whose name has an apostrophe or !.");
  static string Q(string v) => "'" + v + "'";
  List<string> args = ["exec", .. r.Resume ? new[] { "resume" } : [], .. r.Forget ? new[] { "--ephemeral" } : [], "--json", "--skip-git-repo-check", "-c", "sandbox_mode='read-only'", "-c", "mcp_servers.still.tool_timeout_sec=660", // ask_user waits for the user
   // Its own approval for Still's tools can't show in a run (it turns them down: "user cancelled MCP tool call"); Still asks the user itself.
   "-c", "mcp_servers.still.default_tools_approval_mode='approve'",
   "-c", "mcp_servers.still.command=" + Q(Environment.ProcessPath!), "-c", "mcp_servers.still.args=[" + string.Join(",", r.Mcp.Select(Q)) + "]"];
  foreach (string own in new[] { "shell_tool", "unified_exec", "apps", "plugins", "browser_use", "computer_use", "in_app_browser", "multi_agent", "image_generation" }) args.AddRange(["-c", "features." + own + "=false"]); // like the other apps: Still's tools and nothing else
  if (r.Model.Length > 0) args.AddRange(["-c", "model=" + Q(r.Model)]);
  if (r.Effort.Length > 0) args.AddRange(["-c", "model_reasoning_effort=" + Q(r.Effort)]);
  if (r.Resume) args.Add(r.Session!);
  args.Add("-");
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.Codex(e);
}

/// Gemini, through Google's Gemini CLI signed in with the user's Google account. It has no sign-in command (the user runs
/// gemini once in a terminal) and no effort setting, and its own tools, skills, sub-agents and extensions stay off.
sealed class GeminiAdapter : AgentAdapter
{
 public override bool NamesSession => true;
 // It reads the run folder's settings (Still's MCP server) only in a folder it trusts: this one, for the run.
 public override IReadOnlyDictionary<string, string> Env { get; } = new Dictionary<string, string> { ["GEMINI_CLI_TRUST_WORKSPACE"] = "true" };
 public override string[] Gaps => ["To sign in, run gemini in a terminal and pick Sign in with Google.", "No effort setting, so modes pick a model only.",
  "Gemini keeps its own record of incognito chats on this computer. It has no option to turn that off."];
 static string Home => Path.Combine(Environment.GetEnvironmentVariable("GEMINI_CLI_HOME") is { Length: > 0 } h ? h : Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".gemini");
 /// Signed in with Google: its settings pick that sign-in and it has saved one. Still reads which sign-in, never the login.
 public override Task<bool?> Detect(string exe)
 {
  bool google = false;
  try {
   var settings = JsonNode.Parse(File.ReadAllText(Path.Combine(Home, "settings.json")), null, new() { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true });
   google = (settings?["security"]?["auth"]?["selectedType"] ?? settings?["selectedAuthType"])?.GetValue<string>() == "oauth-personal";
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException) { }
  return Task.FromResult<bool?>(google && File.Exists(Path.Combine(Home, "oauth_creds.json")));
 }
 // Its own model names (checked with 0.66.0); auto lets Gemini pick.
 public override Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", []), new("auto", "Auto", []), new("pro", "Pro", []),
  new("flash", "Flash", []), new("flash-lite", "Flash Lite", [])]);
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  // Still's MCP server in the run folder's settings, and a policy that denies every tool but Still's, so no shell, file,
  // web, skill or sub-agent tool runs and nothing waits on a terminal prompt. -e none: no extensions.
  string dir = Path.Combine(r.Folder, ".gemini"), policy = Path.Combine(dir, "still-policy.toml");
  Directory.CreateDirectory(dir);
  File.WriteAllText(Path.Combine(dir, "settings.json"), JsonSerializer.Serialize(new { mcpServers = new { still = new { command = Environment.ProcessPath, args = r.Mcp, trust = true, timeout = 660000 } } })); // ask_user waits for the user
  File.WriteAllText(policy, "[[rule]]\ntoolName = \"*\"\ndecision = \"deny\"\npriority = 100\n\n[[rule]]\ntoolName = \"mcp_still_*\"\ndecision = \"allow\"\npriority = 900\n");
  List<string> args = ["--output-format", "stream-json", "--allowed-mcp-server-names", "still", "-e", "none", "--policy", policy, r.Resume ? "--resume" : "--session-id", r.Session!];
  if (r.Model.Length > 0) args.AddRange(["-m", r.Model]);
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.Gemini(e);
}

/// OpenCode, on whichever provider the user set up inside it: a plan sign-in, that provider's key kept by OpenCode, or
/// OpenCode's free models. Still never sees which. Its own tools, skills and sub-agents stay off.
sealed partial class OpenCodeAdapter : AgentAdapter
{
 string version = "";
 public override string[] Gaps => ["Runs on the provider you set up in OpenCode (opencode providers login, in a terminal).",
  "OpenCode keeps its own record of incognito chats on this computer. It has no option to turn that off.",
  .. version.Length > 0 && !version.StartsWith("1.", StringComparison.Ordinal) ? new[] { $"Still was checked with OpenCode 1. This is {version}, so it may not work." } : []];
 [System.Text.RegularExpressions.GeneratedRegex(@"^[A-Za-z0-9][\w.@-]*/\S+$")] private static partial System.Text.RegularExpressions.Regex ModelLine();
 // Ready once it lists a model: its free ones need no sign-in.
 public override async Task<bool?> Detect(string exe)
 {
  if (await Printed(exe, MainWindow.AiFolder, "--version") is { } v) version = v[0].Trim();
  return await Printed(exe, MainWindow.AiFolder, "models") is { } p ? p[0].Split('\n').Any(l => ModelLine().IsMatch(l.Trim())) : null;
 }
 static readonly string[] Efforts = ["none", "minimal", "low", "medium", "high", "xhigh", "max"];
 static int Rank(string effort) => Array.IndexOf(Efforts, effort) is var i and >= 0 ? i : 99; // lowest first, as the Mac lists them
 /// Its catalog: each model's line, then its details, whose variants are its effort levels. Models without tool calls are left out.
 public override async Task<AgentModel[]> Models(string exe)
 {
  List<AgentModel> list = [new("", "Default", [])];
  if (await Printed(exe, MainWindow.AiFolder, "models", "--verbose") is not { } p) return [.. list];
  string id = ""; var details = new StringBuilder();
  void Add() {
   if (id.Length == 0) return;
   try {
    var m = JsonNode.Parse(details.ToString());
    if (m?["capabilities"]?["toolcall"]?.GetValue<bool>() == false) return;
    string name = m?["name"]?.GetValue<string>() is { Length: > 0 } n ? n : id;
    list.Add(new(id, name + " · " + id.Split('/')[0], m?["variants"] is JsonObject v ? [.. v.Select(x => x.Key).OrderBy(Rank).ThenBy(k => k, StringComparer.Ordinal)] : []));
   } catch (Exception ex) when (ex is JsonException or InvalidOperationException) { list.Add(new(id, id, [])); }
  }
  foreach (var raw in p[0].Split('\n')) {
   string line = raw.TrimEnd('\r');
   if (ModelLine().IsMatch(line)) { Add(); id = line; details.Clear(); } else details.AppendLine(line);
  }
  Add();
  return [.. list];
 }
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  // Still's MCP server in the run folder's config (v1 shape) and every tool off but Still's. Its MCP calls time out after
  // 5 seconds unless told otherwise; ask_user waits for the user.
  File.WriteAllText(Path.Combine(r.Folder, "opencode.json"), JsonSerializer.Serialize(new Dictionary<string, object> {
   ["$schema"] = "https://opencode.ai/config.json",
   ["mcp"] = new { still = new { type = "local", command = new[] { Environment.ProcessPath! }.Concat(r.Mcp), enabled = true, timeout = 660000 } },
   ["tools"] = new Dictionary<string, bool> { ["*"] = false, ["still_*"] = true } }));
  List<string> args = ["run", "--format", "json", "--dir", r.Folder, "--title", "Still"]; // a title of its own would cost a model call
  if (r.Resume && r.Session != null) args.AddRange(["--session", r.Session]);
  if (r.Model.Length > 0) args.AddRange(["-m", r.Model]);
  if (r.Effort.Length > 0) args.AddRange(["--variant", r.Effort]);
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.OpenCode(e);
}

/// Qwen Code (`qwen`), built from its docs and its 0.26.6 package, not run live: the prompt on stdin (it reads a piped
/// prompt), Claude-style stream-json, Still's MCP server in the run folder's settings, and every built-in tool off.
sealed class QwenAdapter : AgentAdapter
{
 // Its built-in tools in 0.26.6, all hidden from the model. tools.core (an allowlist of none) also turns off file, shell and
 // search tools a later version adds.
 static readonly string[] BuiltIn = ["exec", "edit", "write_file", "read_file", "zoom_image", "grep_search", "glob", "run_shell_command", "todo_write",
  "save_memory", "manage_memory", "search_memory", "agent", "skill", "exit_plan_mode", "enter_plan_mode", "web_fetch", "web_search", "image_gen",
  "list_directory", "lsp", "ask_user_question", "cron_create", "cron_list", "cron_delete", "autofix_pr", "loop_wakeup", "create_sub_session", "list_agents",
  "task_stop", "task_create", "task_update", "task_list", "team_create", "team_delete", "team_plan_approval", "request_shutdown", "send_message",
  "structured_output", "monitor", "notebook_edit", "tool_call", "tool_search", "read_mcp_resource", "advisor", "enter_worktree", "exit_worktree", "workflow",
  "artifact", "record_artifact", "record_source", "report_findings", "get_goal", "update_goal", "propose_goal", "display_image",
  "omni_downsample_image", "omni_downscale_video", "omni_downsample_audio", "omni_extract_keyframes", "omni_extract_audio", "omni_clip_video",
  "omni_convert_image", "omni_transcribe_audio", "omni_clip_image", "omni_clip_audio", "omni_caption_image", "omni_caption_audio", "omni_ocr_image",
  "omni_understand_video_segments", "omni_recall_media_memory"];
 public override bool Forgets => true; // general.chatRecording off: an incognito chat saves nothing
 public override string[] Gaps => ["To sign in, run qwen in a terminal and pick a sign-in.", "No model or effort settings in Still yet, so every mode uses the model you set in Qwen Code."];
 static string Home => Environment.GetEnvironmentVariable("QWEN_HOME") is { Length: > 0 } h ? h : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".qwen");
 // Folder trust (off unless the user turned it on): Still's own list, trusting its AI folder (incognito runs are in it
 // too), so the run folder's settings load.
 public override IReadOnlyDictionary<string, string> Env {
  get {
   string trust = Path.Combine(MainWindow.AiFolder, "qwen-trusted-folders.json");
   try { Directory.CreateDirectory(MainWindow.AiFolder); File.WriteAllText(trust, JsonSerializer.Serialize(new Dictionary<string, string> { [MainWindow.AiFolder] = "TRUST_FOLDER" })); }
   catch (IOException ex) { Still.App.Log(ex); }
   return new Dictionary<string, string> { ["QWEN_CODE_TRUSTED_FOLDERS_PATH"] = trust };
  }
 }
 /// Signed in with Qwen OAuth: its settings pick that sign-in and it has saved one. Another sign-in (an API key): it can't say.
 public override Task<bool?> Detect(string exe)
 {
  string? type = null;
  try {
   var settings = JsonNode.Parse(File.ReadAllText(Path.Combine(Home, "settings.json")), null, new() { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true });
   type = settings?["security"]?["auth"]?["selectedType"]?.GetValue<string>();
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException) { }
  return Task.FromResult<bool?>(type is null or "" ? false : type == "qwen-oauth" ? File.Exists(Path.Combine(Home, "oauth_creds.json")) : null);
 }
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  string dir = Path.Combine(r.Folder, ".qwen");
  Directory.CreateDirectory(dir);
  File.WriteAllText(Path.Combine(dir, "settings.json"), JsonSerializer.Serialize(new Dictionary<string, object> {
   ["mcpServers"] = new { still = new { command = Environment.ProcessPath, args = r.Mcp, trust = true, timeout = 660000 } }, // ask_user waits for the user
   ["permissions"] = new { allow = new[] { "mcp__still" } },
   ["tools"] = new { core = new[] { "mcp__still" }, disabled = BuiltIn },
   ["general"] = new { chatRecording = !r.Forget } }));
  List<string> args = ["--output-format", "stream-json", "--allowed-mcp-server-names", "still", "-e", "none", "--approval-mode", "default"];
  if (r.Resume && r.Session != null) args.AddRange(["--resume", r.Session]);
  if (r.Model.Length > 0) args.AddRange(["-m", r.Model]);
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.Messages(e, true);
}

/// GitHub Copilot CLI (`copilot`), built from its docs, not run live: the prompt on stdin, only its reply printed (-s),
/// Still's MCP server added for the run, every built-in tool kind denied (deny wins over any allow).
sealed class CopilotAdapter : AgentAdapter
{
 // A UUID that names no session yet starts one with that id; the same id resumes it.
 public override bool NamesSession => true;
 public override string[] Gaps => ["To sign in, run copilot login in a terminal.", "Shows its reply once it's done, not each step.",
  "Copilot keeps its own record of incognito chats on this computer.", "Effort applies on the models Copilot offers it for."];
 public override Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", ["low", "medium", "high"]), new("auto", "Auto", [])]);
 public override Task<bool?> Detect(string exe) => Task.FromResult<bool?>(null); // no status command
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  string config = Path.Combine(r.Folder, "copilot-mcp.json");
  File.WriteAllText(config, JsonSerializer.Serialize(new { mcpServers = new { still = new { type = "local", command = Environment.ProcessPath, args = r.Mcp, tools = new[] { "*" }, timeout = 660000 } } }));
  List<string> args = ["-s", "--additional-mcp-config", "@" + config, "--allow-tool", "still", "--deny-tool", "shell,write,read,url,memory",
   "--disable-builtin-mcps", "--no-ask-user", "--no-custom-instructions", "--session-id", r.Session!];
  if (r.Model.Length > 0) args.AddRange(["--model", r.Model]);
  if (r.Effort.Length > 0) args.AddRange(["--effort", r.Effort]);
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => Plain(e.ToJsonString());
 public override IEnumerable<AgentEvent> Plain(string line) => line.Trim().Length > 0 ? [new AgentEvent.Message(line, "\n")] : [];
}

/// DeepSeek Harness (`dsh`, DeepSeek's own agent), built from its docs and source (github.com/deepseek-ai/deepseek-harness),
/// not run live: the headless profile with its JSON event stream, the prompt on stdin, and a --patch overlay in the run
/// folder that adds Still's MCP server, turns its own tools off, turns its session-log upload off and lets it use the
/// sign-in or key saved in its own app. Still never reads that sign-in.
sealed class DshAdapter : AgentAdapter
{
 // Its own tools: shell, files, jobs, skills, sub-agents, workflows, web and MCP resources.
 static readonly string[] Tools = ["tool-bash", "tool-pwsh", "tool-jobs", "tool-fs", "tool-fs-search", "tool-working-directory", "tool-skill",
  "tool-agent-team", "tool-subagent-control", "tool-subagent", "tool-subagent-fork", "tool-workflow", "tool-web", "mcp-resources"];
 public override string[] Gaps => ["To sign in or add your DeepSeek key, run dsh web in a terminal.", "It is a developer preview, so it may change or break.",
  "No model or effort settings in Still yet, so every mode uses the model you set in DeepSeek Harness.", "DeepSeek Harness keeps its own record of incognito chats on this computer."];
 public override IReadOnlyDictionary<string, string> Env { get; } = new Dictionary<string, string> { ["DSH_TELEMETRY_MODE"] = "DISABLED" };
 public override Task<bool?> Detect(string exe) => Task.FromResult<bool?>(null); // no status command
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  // A patch replaces a row's whole config, so the session-log row gets one of its own. JSON is YAML, so no escaping to get wrong.
  string patch = Path.Combine(r.Folder, "still-dsh.yml");
  object[] rows = [
   new { insert = new object[] { new { id = "still-mcp", name = "@deepseek-ai/dsh-mcp-client", config = new { serverName = "still", transport = "stdio",
    command = Environment.ProcessPath, args = r.Mcp, cwd = r.Folder, toolCallTimeoutMs = 660000 } } } }, // ask_user waits for the user
   new { id = "session-log-deepseek", config = new { enabled = false } },
   .. new[] { "credentials", "authorization", "deepseek-account" }.Select(id => (object)new { id, disabled = false }),
   .. Tools.Select(id => (object)new { id, disabled = true })];
  File.WriteAllText(patch, JsonSerializer.Serialize(rows));
  List<string> args = ["--profile", "headless", "--patch", patch, "--json"];
  if (r.Resume && r.Session != null) args.AddRange(["--session-id", r.Session]);
  args.Add("-");
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.Dsh(e);
}

/// Any other agent CLI, described by a JSON file in Still's agents folder (see docs/agentic/agents.md). Placeholders in
/// its args: {prompt} (only for .exe commands; .cmd ones go through cmd.exe), {promptFile}, {model}, {effort}, {cwd},
/// {mcpConfig} (a standard mcp.json for Still) and {session}. Without {prompt} or {promptFile} the prompt goes to stdin.
sealed class ManifestAdapter : AgentAdapter
{
 sealed class Spec
 {
  public string Id { get; set; } = ""; public string Name { get; set; } = ""; public string Command { get; set; } = ""; public bool Enabled { get; set; }
  public string Site { get; set; } = ""; public string Install { get; set; } = "";
  public string[] Detect { get; set; } = []; public string Expect { get; set; } = "."; public string[] Signin { get; set; } = [];
  public string[] Run { get; set; } = []; public string[] Resume { get; set; } = []; public string[] Model { get; set; } = []; public string[] Effort { get; set; } = [];
  public string[] Models { get; set; } = [];
  public string McpFile { get; set; } = ""; // also write Still's mcp.json here, relative to the run folder (for apps that read a fixed file)
  public string Output { get; set; } = "plain"; // "stream-json" (Anthropic events), "jsonl" (with Fields) or "plain"
  public Dictionary<string, string> Fields { get; set; } = [];
 }
 Spec spec = new();

 // Written once, turned off, for the user to adapt. Not tested by Still: none of these apps is on the build PC.
 static readonly (string Name, string Json)[] Examples = [
  ("cursor-agent", """
   {
    "id": "cursor-agent", "name": "Cursor Agent", "enabled": false,
    "note": "Example, not tested by Still. Sign in with: cursor-agent login. Set enabled to true to use it.",
    "command": "cursor-agent", "site": "https://cursor.com/cli", "install": "See cursor.com/cli",
    "detect": ["status"], "expect": "(?i)logged in", "signin": ["login"],
    "mcpFile": ".cursor/mcp.json",
    "run": ["-p", "--output-format", "stream-json", "--approve-mcps", "--force"],
    "resume": ["--resume", "{session}"], "model": ["--model", "{model}"],
    "output": "stream-json"
   }
   """),
  ("aider", """
   {
    "id": "aider", "name": "Aider", "enabled": false,
    "note": "Example, not tested by Still. Aider has no MCP support, so it can chat but can't use your tabs.",
    "command": "aider", "site": "https://aider.chat", "install": "python -m pip install aider-install",
    "detect": ["--version"], "expect": "\\d+\\.\\d+",
    "run": ["--no-git", "--yes-always", "--no-pretty", "--message-file", "{promptFile}"], "model": ["--model", "{model}"],
    "output": "plain"
   }
   """),
 ];

 public static string Folder => Path.Combine(Still.App.ProfileHome, "agents");
 /// The enabled manifests. A broken file is skipped and logged; it never stops Still.
 public static List<AgentAdapter> Load()
 {
  List<AgentAdapter> found = [];
  try {
   if (!Directory.Exists(Folder)) {
    Directory.CreateDirectory(Folder);
    foreach (var (name, json) in Examples) File.WriteAllText(Path.Combine(Folder, name + ".json"), json);
   }
   foreach (var file in Directory.EnumerateFiles(Folder, "*.json").Order()) {
    try {
     var s = JsonSerializer.Deserialize<Spec>(File.ReadAllText(file), new JsonSerializerOptions { PropertyNameCaseInsensitive = true, ReadCommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true });
     if (s is not { Enabled: true } || !System.Text.RegularExpressions.Regex.IsMatch(s.Id, "^[a-z0-9-]{1,30}$") || s.Id is "claude" or "grok" or "chatgpt" or "codex" or "gemini" or "opencode" or "qwen" or "copilot" or "dsh" || s.Command.Length == 0 || s.Run.Length == 0) continue;
     found.Add(new ManifestAdapter { spec = s, Id = s.Id, Name = s.Name.Length > 0 ? s.Name : s.Id, App = s.Name.Length > 0 ? s.Name : s.Command, Command = s.Command,
      Site = s.Site, InstallCommand = s.Install, Secondary = true,
      TerminalSignIn = s.Signin.Length > 0 ? string.Join(" ", s.Signin.Prepend(s.Command.Contains(' ') ? $"& \"{s.Command}\"" : s.Command)) : "" }); // shown to run in a terminal
    } catch (Exception ex) when (ex is JsonException or IOException or NotSupportedException) { Still.App.Log(ex); }
   }
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { Still.App.Log(ex); }
  return found;
 }

 public override bool PromptOnStdin => !spec.Run.Concat(spec.Resume).Any(a => a.Contains("{prompt}") || a.Contains("{promptFile}"));
 public override async Task<bool?> Detect(string exe) =>
  spec.Detect.Length == 0 ? null : await Output(exe, MainWindow.AiFolder, spec.Detect) is { } text ? System.Text.RegularExpressions.Regex.IsMatch(text, spec.Expect) : null;
 public override Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", spec.Effort.Length > 0 ? MainWindow.Efforts : []), .. spec.Models.Select(m => new AgentModel(m, m, spec.Effort.Length > 0 ? MainWindow.Efforts : []))]);
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  bool viaCmd = !exe.EndsWith(".exe", StringComparison.OrdinalIgnoreCase);
  if (viaCmd && spec.Run.Concat(spec.Resume).Any(a => a.Contains("{prompt}"))) throw new InvalidOperationException($"{Name} runs through cmd.exe, so its manifest must use {{promptFile}} or stdin instead of {{prompt}}.");
  string config = Path.Combine(r.Folder, "mcp.json"), promptFile = r.PromptFile;
  File.WriteAllText(config, JsonSerializer.Serialize(new { mcpServers = new { still = new { command = Environment.ProcessPath, args = r.Mcp } } }));
  if (spec.McpFile.Length > 0 && Path.GetFullPath(Path.Combine(r.Folder, spec.McpFile)) is var extra && extra.StartsWith(Path.GetFullPath(r.Folder) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) {
   Directory.CreateDirectory(Path.GetDirectoryName(extra)!);
   File.Copy(config, extra, true);
  }
  File.WriteAllText(promptFile, r.Prompt, new UTF8Encoding(false));
  var values = new Dictionary<string, string> { ["{prompt}"] = r.Prompt, ["{promptFile}"] = promptFile, ["{model}"] = r.Model, ["{effort}"] = r.Effort,
   ["{cwd}"] = r.Folder, ["{mcpConfig}"] = config, ["{session}"] = r.Session ?? "" };
  string Fill(string a) => values.Aggregate(a, (s, v) => s.Replace(v.Key, v.Value));
  List<string> args = [.. spec.Run.Select(Fill)];
  if (r.Resume && r.Session != null) args.AddRange(spec.Resume.Select(Fill));
  if (r.Model.Length > 0) args.AddRange(spec.Model.Select(Fill));
  if (r.Effort.Length > 0) args.AddRange(spec.Effort.Select(Fill));
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => spec.Output switch {
  "stream-json" => AgentStream.Messages(e, true),
  "jsonl" => AgentStream.Fields(e, spec.Fields),
  _ => Plain(e.ToJsonString()),
 };
 public override IEnumerable<AgentEvent> Plain(string line) => spec.Output == "plain" && line.Trim().Length > 0 ? [new AgentEvent.Message(line, "\n")] : [];
}

/// One run of an AI: an app's process (CliRun) or Still's own loop on an API provider (ApiRun). Both speak AgentEvents.
public abstract class AgentRun(AgentAdapter adapter) : IDisposable
{
 public static readonly TimeSpan Limit = TimeSpan.FromHours(1);
 public static int Launched; // runs started since Still opened: each one uses the user's plan (tests check Quick setup uses none)
 protected readonly AgentAdapter adapter = adapter;
 protected readonly List<string> errors = [];
 public DateTime Started { get; } = DateTime.UtcNow;
 public bool Cancelled { get; protected set; }
 public bool TimedOut { get; protected set; }
 public string[] Errors { get { lock (errors) return [.. errors]; } }
 public abstract int ExitCode { get; }
 /// The run's events, in order, until it ends.
 public abstract IAsyncEnumerable<AgentEvent> Events(CancellationToken token = default);
 /// Ends it, and everything it started, right away.
 public abstract void Cancel();
 public abstract void Dispose();
 protected void Keep(string line) { lock (errors) { errors.Add(line); if (errors.Count > 40) errors.RemoveAt(0); } }

 /// Keeps what it printed when it failed, so a crash can be looked into later. Prompts are never written.
 public void SaveLog(string folder, string chatId)
 {
  try {
   string logs = Path.Combine(folder, "logs");
   Directory.CreateDirectory(logs);
   File.WriteAllLines(Path.Combine(logs, $"{DateTime.Now:yyyyMMdd-HHmmss}-{adapter.Id}.log"),
    [$"agent: {adapter.App}", $"chat: {chatId}", $"exit code: {ExitCode}", $"ran for: {DateTime.UtcNow - Started:hh\\:mm\\:ss}", "", .. Errors]);
   foreach (var old in new DirectoryInfo(logs).GetFiles("*.log").OrderByDescending(f => f.Name).Skip(20)) old.Delete();
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { Still.App.Log(ex); }
 }
}

/// A running agent app. Its process tree lives in a Job Object, so Cancel ends every child at once, and so does Still exiting.
public sealed class CliRun : AgentRun
{
 readonly Process process;
 readonly Job job = new();
 readonly Task stderr;

 CliRun(AgentAdapter adapter, Process process) : base(adapter)
 {
  this.process = process;
  job.Add(process);
  stderr = Task.Run(async () => { while (await process.StandardError.ReadLineAsync() is { } line) Keep(line); });
 }

 public static async Task<AgentRun> Start(AgentAdapter adapter, string exe, RunRequest r)
 {
  Directory.CreateDirectory(r.Folder);
  var start = AgentAdapter.Launch(exe, r.Folder, await adapter.Args(exe, r), adapter.Env, adapter.Kept);
  start.RedirectStandardInput = start.RedirectStandardOutput = start.RedirectStandardError = true;
  start.StandardOutputEncoding = start.StandardErrorEncoding = new UTF8Encoding(false);
  var run = new CliRun(adapter, Process.Start(start) ?? throw new InvalidOperationException("couldn't start it."));
  Interlocked.Increment(ref Launched);
  if (adapter.PromptOnStdin) await run.process.StandardInput.BaseStream.WriteAsync(new UTF8Encoding(false).GetBytes(r.Prompt));
  run.process.StandardInput.Close();
  return run;
 }

 public override int ExitCode => process.HasExited ? process.ExitCode : 0;

 /// Lines that aren't JSON go to Plain (and are kept for errors).
 public override async IAsyncEnumerable<AgentEvent> Events([EnumeratorCancellation] CancellationToken token = default)
 {
  using var limit = new Timer(_ => { TimedOut = true; Cancel(); }, null, Limit, Timeout.InfiniteTimeSpan);
  while (await process.StandardOutput.ReadLineAsync(token) is { } line) {
   JsonNode? e = null;
   if (line.StartsWith('{')) try { e = JsonNode.Parse(line); } catch (JsonException) { }
   if (e is not JsonObject) { Keep(line); foreach (var p in adapter.Plain(line)) yield return p; continue; }
   foreach (var ev in adapter.Parse(e)) yield return ev;
  }
  await process.WaitForExitAsync(CancellationToken.None);
  await stderr;
 }

 /// Ends the app and everything it started (Still's MCP server, shells, helpers) right away.
 public override void Cancel()
 {
  Cancelled = true;
  job.Kill();
  try { if (!process.HasExited) process.Kill(true); } catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception) { }
 }

 public override void Dispose() { process.Dispose(); job.Dispose(); }

 sealed class Job : IDisposable
 {
  [StructLayout(LayoutKind.Sequential)]
  struct Limits
  {
   public long PerProcessUserTimeLimit, PerJobUserTimeLimit; public uint LimitFlags; public nuint MinimumWorkingSetSize, MaximumWorkingSetSize;
   public uint ActiveProcessLimit; public nuint Affinity; public uint PriorityClass, SchedulingClass;
   public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount;
   public nuint ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
  }
  [DllImport("kernel32", SetLastError = true, CharSet = CharSet.Unicode)] static extern nint CreateJobObjectW(nint attributes, string? name);
  [DllImport("kernel32", SetLastError = true)] static extern bool SetInformationJobObject(nint job, int infoClass, ref Limits info, int size);
  [DllImport("kernel32", SetLastError = true)] static extern bool AssignProcessToJobObject(nint job, nint process);
  [DllImport("kernel32", SetLastError = true)] static extern bool TerminateJobObject(nint job, uint exitCode);
  [DllImport("kernel32")] static extern bool CloseHandle(nint handle);
  nint handle = CreateJobObjectW(0, null);

  public Job()
  {
   var limits = new Limits { LimitFlags = 0x2000 }; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
   if (handle != 0) SetInformationJobObject(handle, 9, ref limits, Marshal.SizeOf<Limits>()); // JobObjectExtendedLimitInformation
  }
  public void Add(Process p) { if (handle != 0) AssignProcessToJobObject(handle, p.Handle); }
  public void Kill() { if (handle != 0) TerminateJobObject(handle, 1); }
  public void Dispose() { if (handle != 0) { CloseHandle(handle); handle = 0; } }
 }
}
