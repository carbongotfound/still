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
 public string WorkFolder { get; init; } = ""; // the user's working folder: the app's own file tools, for that folder only
 public string PromptFile => Path.Combine(Folder, "prompt-" + (Session ?? "run") + ".txt");
}

/// An AI agent app on the user's PC that Still drives headless, signed in with the user's own plan. Still never reads its
/// login; it only asks the app whether it is signed in. Every run goes through Still's MCP server and nothing else.
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
 public string[] SignIn { get; init; } = [];
 public string[] Domains { get; init; } = [];    // the only sites a sign-in page may be on
 public bool Secondary { get; init; }            // a manifest agent: listed under "More agents"
 public virtual bool PromptOnStdin => true;
 /// Still picks the session id up front (so a stopped first run can still be resumed); otherwise the app reports it.
 public virtual bool NamesSession => false;

 /// Signed in? null when the app can't say. Uses none of the user's AI usage.
 public abstract Task<bool?> Detect(string exe);
 public virtual Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", [])]);
 /// The command line for one run. It may write config files into the run's folder.
 public abstract Task<List<string>> Args(string exe, RunRequest r);
 public abstract IEnumerable<AgentEvent> Parse(JsonNode e);
 /// A line that isn't JSON. Agents with plain output speak in lines.
 public virtual IEnumerable<AgentEvent> Plain(string line) => [];

 public Task<AgentRun> Start(string exe, RunRequest r) => AgentRun.Start(this, exe, r);

 // Keys that would bill an API account instead of the user's plan. The app's own sign-in is used instead.
 static readonly string[] ApiKeys = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
  "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"];

 public static ProcessStartInfo Launch(string exe, string folder, IEnumerable<string> args)
 {
  var start = new ProcessStartInfo { WorkingDirectory = folder, UseShellExecute = false, CreateNoWindow = true };
  foreach (var key in ApiKeys) start.Environment.Remove(key);
  if (exe.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) { start.FileName = exe; foreach (var a in args) start.ArgumentList.Add(a); return start; }
  // npm installs .cmd launchers, which only cmd.exe runs. Every argument is Still's own (paths, flags, ids).
  start.FileName = Path.Combine(Environment.SystemDirectory, "cmd.exe");
  start.Arguments = "/d /s /c \"" + string.Join(" ", args.Prepend(exe).Select(a => "\"" + a + "\"")) + "\"";
  return start;
 }

 /// Runs the app briefly and returns what it printed (stdout, then stderr), or null if it didn't finish in time.
 protected static async Task<string?> Output(string exe, string folder, params string[] args) => await Printed(exe, folder, args) is { } p ? p[0] + "\n" + p[1] : null;
 protected static async Task<string[]?> Printed(string exe, string folder, params string[] args)
 {
  Directory.CreateDirectory(folder);
  var start = Launch(exe, folder, args);
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
 static readonly string[] Levels = ["low", "medium", "high", "xhigh", "max"];
 public override async Task<bool?> Detect(string exe)
 {
  var printed = await Printed(exe, MainWindow.AiFolder, "auth", "status");
  try { return printed == null ? null : JsonNode.Parse(printed[0])?["loggedIn"]?.GetValue<bool>() ?? false; }
  catch (Exception ex) when (ex is JsonException or ArgumentException) { return false; }
 }
 public override Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", Levels), new("fable", "Fable", Levels),
  new("opus", "Opus", Levels), new("sonnet", "Sonnet", Levels), new("haiku", "Haiku", Levels)]);
 public override Task<List<string>> Args(string exe, RunRequest r)
 {
  string config = Path.Combine(r.Folder, "mcp.json");
  File.WriteAllText(config, JsonSerializer.Serialize(new { mcpServers = new { still = new { command = Environment.ProcessPath, args = r.Mcp } } }));
  List<string> args = ["-p", "--output-format", "stream-json", "--verbose", "--mcp-config", config, "--strict-mcp-config", "--allowedTools", "mcp__still", r.Resume ? "--resume" : "--session-id", r.Session!];
  // File tools only with a working folder, and only inside it: edits are accepted in the working directories, anything else is refused.
  if (r.WorkFolder.Length > 0) args.AddRange(["--tools", "Read,Write,Edit,Glob,Grep", "--add-dir", r.WorkFolder, "--permission-mode", "acceptEdits"]);
  else args.AddRange(["--tools", ""]);
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
   list.Add(new(m.Groups[1].Value, m.Groups[1].Value, MainWindow.Efforts));
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
  List<string> args = ["exec", .. r.Resume ? new[] { "resume" } : [], "--json", "--skip-git-repo-check", "-c", "sandbox_mode='read-only'", "-c", "mcp_servers.still.tool_timeout_sec=660", // ask_user waits for the user
   "-c", "mcp_servers.still.command=" + Q(Environment.ProcessPath!), "-c", "mcp_servers.still.args=[" + string.Join(",", r.Mcp.Select(Q)) + "]"];
  if (r.Model.Length > 0) args.AddRange(["-c", "model=" + Q(r.Model)]);
  if (r.Effort.Length > 0) args.AddRange(["-c", "model_reasoning_effort=" + Q(r.Effort)]);
  if (r.Resume) args.Add(r.Session!);
  args.Add("-");
  return Task.FromResult(args);
 }
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => AgentStream.Codex(e);
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
  public string[] Detect { get; set; } = []; public string Expect { get; set; } = "."; public string[] Signin { get; set; } = []; public string[] Domains { get; set; } = [];
  public string[] Run { get; set; } = []; public string[] Resume { get; set; } = []; public string[] Model { get; set; } = []; public string[] Effort { get; set; } = [];
  public string[] Models { get; set; } = [];
  public string McpFile { get; set; } = ""; // also write Still's mcp.json here, relative to the run folder (for apps that read a fixed file)
  public string Output { get; set; } = "plain"; // "stream-json" (Anthropic events), "jsonl" (with Fields) or "plain"
  public Dictionary<string, string> Fields { get; set; } = [];
 }
 Spec spec = new();

 // Written once, turned off, for the user to adapt. Not tested by Still: none of these apps is on the build PC.
 static readonly (string Name, string Json)[] Examples = [
  ("gemini", """
   {
    "id": "gemini", "name": "Gemini", "enabled": false,
    "note": "Example, not tested by Still. Sign in by running gemini once in a terminal. Set enabled to true to use it.",
    "command": "gemini", "site": "https://github.com/google-gemini/gemini-cli", "install": "npm install -g @google/gemini-cli",
    "detect": ["--version"], "expect": "\\d+\\.\\d+",
    "mcpFile": ".gemini/settings.json",
    "run": ["--output-format", "stream-json", "--allowed-mcp-server-names", "still", "--yolo"],
    "model": ["-m", "{model}"], "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "output": "jsonl",
    "resume": ["--resume", "{session}"],
    "fields": { "session": "session_id when type=init", "text": "content when type=message,role=assistant", "delta": "delta",
     "tool": "tool_name when type=tool_use", "toolId": "tool_id", "toolArgs": "parameters", "error": "message when type=error,severity=error" }
   }
   """),
  ("cursor-agent", """
   {
    "id": "cursor-agent", "name": "Cursor Agent", "enabled": false,
    "note": "Example, not tested by Still. Sign in with: cursor-agent login. Set enabled to true to use it.",
    "command": "cursor-agent", "site": "https://cursor.com/cli", "install": "See cursor.com/cli",
    "detect": ["status"], "expect": "(?i)logged in", "signin": ["login"], "domains": ["cursor.com"],
    "mcpFile": ".cursor/mcp.json",
    "run": ["-p", "--output-format", "stream-json", "--approve-mcps", "--force"],
    "resume": ["--resume", "{session}"], "model": ["--model", "{model}"],
    "output": "stream-json"
   }
   """),
  ("opencode", """
   {
    "id": "opencode", "name": "OpenCode", "enabled": false,
    "note": "Example, not tested by Still. Add Still to OpenCode's MCP servers yourself (command: Still.exe --mcp --as OpenCode). Set enabled to true to use it.",
    "command": "opencode", "site": "https://opencode.ai", "install": "npm install -g opencode-ai",
    "detect": ["--version"], "expect": "\\d+\\.\\d+",
    "run": ["run", "--file", "{promptFile}", "Do what the attached file asks."], "model": ["--model", "{model}"],
    "output": "plain"
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
     if (s is not { Enabled: true } || !System.Text.RegularExpressions.Regex.IsMatch(s.Id, "^[a-z0-9-]{1,30}$") || s.Id is "claude" or "grok" or "chatgpt" or "codex" || s.Command.Length == 0 || s.Run.Length == 0) continue;
     found.Add(new ManifestAdapter { spec = s, Id = s.Id, Name = s.Name.Length > 0 ? s.Name : s.Id, App = s.Name.Length > 0 ? s.Name : s.Command, Command = s.Command,
      Site = s.Site, InstallCommand = s.Install, SignIn = s.Signin, Domains = s.Domains, Secondary = true });
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

/// A running agent. Its process tree lives in a Job Object, so Cancel ends every child at once, and so does Still exiting.
public sealed class AgentRun : IDisposable
{
 public static readonly TimeSpan Limit = TimeSpan.FromHours(1);
 readonly Process process;
 readonly Job job = new();
 readonly AgentAdapter adapter;
 readonly List<string> errors = [];
 readonly Task stderr;
 public DateTime Started { get; } = DateTime.UtcNow;
 public bool Cancelled { get; private set; }
 public bool TimedOut { get; private set; }

 AgentRun(AgentAdapter adapter, Process process)
 {
  this.adapter = adapter; this.process = process;
  job.Add(process);
  stderr = Task.Run(async () => { while (await process.StandardError.ReadLineAsync() is { } line) lock (errors) { errors.Add(line); if (errors.Count > 40) errors.RemoveAt(0); } });
 }

 public static async Task<AgentRun> Start(AgentAdapter adapter, string exe, RunRequest r)
 {
  Directory.CreateDirectory(r.Folder);
  var start = AgentAdapter.Launch(exe, r.Folder, await adapter.Args(exe, r));
  start.RedirectStandardInput = start.RedirectStandardOutput = start.RedirectStandardError = true;
  start.StandardOutputEncoding = start.StandardErrorEncoding = new UTF8Encoding(false);
  var run = new AgentRun(adapter, Process.Start(start) ?? throw new InvalidOperationException("couldn't start it."));
  if (adapter.PromptOnStdin) await run.process.StandardInput.BaseStream.WriteAsync(new UTF8Encoding(false).GetBytes(r.Prompt));
  run.process.StandardInput.Close();
  return run;
 }

 public string[] Errors { get { lock (errors) return [.. errors]; } }
 public int ExitCode => process.HasExited ? process.ExitCode : 0;

 /// The run's events, in order, until the app exits. Lines that aren't JSON go to Plain (and are kept for errors).
 public async IAsyncEnumerable<AgentEvent> Events([EnumeratorCancellation] CancellationToken token = default)
 {
  using var limit = new Timer(_ => { TimedOut = true; Cancel(); }, null, Limit, Timeout.InfiniteTimeSpan);
  while (await process.StandardOutput.ReadLineAsync(token) is { } line) {
   JsonNode? e = null;
   if (line.StartsWith('{')) try { e = JsonNode.Parse(line); } catch (JsonException) { }
   if (e is not JsonObject) { lock (errors) { errors.Add(line); if (errors.Count > 40) errors.RemoveAt(0); } foreach (var p in adapter.Plain(line)) yield return p; continue; }
   foreach (var ev in adapter.Parse(e)) yield return ev;
  }
  await process.WaitForExitAsync(CancellationToken.None);
  await stderr;
 }

 /// Ends the app and everything it started (Still's MCP server, shells, helpers) right away.
 public void Cancel()
 {
  Cancelled = true;
  job.Kill();
  try { if (!process.HasExited) process.Kill(true); } catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception) { }
 }

 /// Keeps what the app printed when it failed, so a crash can be looked into later. Prompts are never written.
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

 public void Dispose() { process.Dispose(); job.Dispose(); }

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
