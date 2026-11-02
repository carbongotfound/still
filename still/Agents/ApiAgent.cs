using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Channels;
namespace Still;

/// An API provider the user added, run by Still itself (ApiRun) with the user's own key. Only its settings live here, in
/// prefs; the key is kept apart (ApiKeyStore) and only ever goes to the provider, in its auth header. Labelled Compatible:
/// Still checks these against its own fake server, never against real endpoints.
public sealed class ApiProvider
{
 public string Id { get; set; } = "";         // "api-" and 8 letters or digits
 public string Kind { get; set; } = "openai"; // "openai" (Chat Completions) or "anthropic" (Messages)
 public string Name { get; set; } = "";
 public string Url { get; set; } = "";        // the base URL, before /chat/completions or /messages
 public List<ApiModel> Models { get; set; } = [];
 public double PriceIn { get; set; }          // per million tokens; 0 = not set
 public double PriceOut { get; set; }
 public double Limit { get; set; }            // a month's spending limit; 0 = none
 public int Context { get; set; }             // the models' context size in tokens; 0 = not known (Still assumes 128k and halves it if refused)
 public bool NoTools { get; set; }            // Test connection found the model doesn't call tools: it can chat, not use tabs
 public Dictionary<string, ApiUse> Spent { get; set; } = []; // "2026-11" → that month's use, and per job under "2026-11/titles"
 public static string Month => DateTime.Now.ToString("yyyy-MM");
 public double CostOf(long input, long output) => input / 1e6 * PriceIn + output / 1e6 * PriceOut;
 [System.Text.Json.Serialization.JsonIgnore] public bool Priced => PriceIn > 0 || PriceOut > 0;
}
public sealed class ApiModel
{
 public string Id { get; set; } = "";
 public string[] Efforts { get; set; } = [];  // only those Test connection confirmed
}
public sealed class ApiUse
{
 public long In { get; set; }
 public long Out { get; set; }
 public double Cost { get; set; }
 public int Calls { get; set; }
}

/// API keys: one DPAPI file per provider (this Windows user only) in the profile's api-keys folder, the saved-logins and
/// Composio-key pattern. Nothing else ever holds one: the shell only hears whether there is a key and its last four characters.
public static class ApiKeyStore
{
 static string Folder => Path.Combine(App.DataRoot, "api-keys");
 public static bool IdOk(string id) => id.Length is > 4 and <= 20 && id.StartsWith("api-", StringComparison.Ordinal) && id[4..].All(char.IsAsciiLetterOrDigit);
 static string FileOf(string id) => IdOk(id) ? Path.Combine(Folder, id + ".dpapi") : throw new ArgumentException("bad provider id");
 public static readonly HashSet<string> Refused = []; // the provider answered 401 or 403 with this key
 public static bool Has(string id) => IdOk(id) && File.Exists(FileOf(id));
 public static string? Read(string id)
 {
  try {
   byte[] plain = ProtectedData.Unprotect(File.ReadAllBytes(FileOf(id)), null, DataProtectionScope.CurrentUser);
   try { return Encoding.UTF8.GetString(plain); } finally { CryptographicOperations.ZeroMemory(plain); }
  } catch (Exception e) when (e is IOException or CryptographicException or UnauthorizedAccessException or ArgumentException) { return null; }
 }
 public static void Save(string id, string key)
 {
  Directory.CreateDirectory(Folder);
  byte[] plain = Encoding.UTF8.GetBytes(key);
  try { File.WriteAllBytes(FileOf(id) + ".tmp", ProtectedData.Protect(plain, null, DataProtectionScope.CurrentUser)); File.Move(FileOf(id) + ".tmp", FileOf(id), true); }
  finally { CryptographicOperations.ZeroMemory(plain); }
  Refused.Remove(id);
 }
 public static void Remove(string id) { try { File.Delete(FileOf(id)); } catch (Exception e) when (e is IOException or ArgumentException) { } Refused.Remove(id); }
 public static string End(string id) => Read(id) is { Length: >= 8 } key ? key[^4..] : "";
}

/// An API provider as one of the AIs: picked, set per mode and run like the apps, with no app to install or sign in to.
sealed class ApiAdapter : AgentAdapter
{
 public required ApiProvider Provider { get; init; }
 public static ApiAdapter Of(ApiProvider p) => new() { Provider = p, Id = p.Id, Name = p.Name, App = p.Name, Command = "", Maker = p.Kind == "anthropic" ? "Anthropic-compatible API" : "OpenAI-compatible API" };
 public override bool NamesSession => true; // the chat's transcript file
 public override bool Forgets => true; // incognito: the transcript lives in memory for the turn and is never written
 public override string[] Gaps => Provider.NoTools ? ["Can't use your tabs: Test connection found this model doesn't call tools."] : [];
 public override Task<bool?> Detect(string exe) => Task.FromResult<bool?>(ApiKeyStore.Has(Provider.Id));
 public override Task<AgentModel[]> Models(string exe) => Task.FromResult<AgentModel[]>([new("", "Default", []), .. Provider.Models.Select(m => new AgentModel(m.Id, m.Id, m.Efforts))]);
 public override Task<List<string>> Args(string exe, RunRequest r) => Task.FromResult(new List<string>());
 public override IEnumerable<AgentEvent> Parse(JsonNode e) => [];
 public override Task<AgentRun> Start(string exe, RunRequest r) => Task.FromResult<AgentRun>(ApiRun.Start(this, r));
}

sealed class ApiFailure(string message) : Exception(message);

/// Still's own agent loop for an API provider. Tools come from Still's MCP server, run as its own child exactly as the apps
/// run it (`Still --mcp`), so approvals, sensitive steps and permission modes are the same code. Replies stream; Stop ends
/// it at once; a turn takes at most MaxSteps model calls and the run the same hour as an app. The transcript, tool calls
/// included, is kept in the chat's folder (api-<session>.json), except for incognito chats, whose transcript is never written.
public sealed class ApiRun : AgentRun
{
 public const int MaxSteps = 40;
 static readonly HttpClient Http = new(new SocketsHttpHandler { AllowAutoRedirect = false, ConnectTimeout = TimeSpan.FromSeconds(20) }) { Timeout = Timeout.InfiniteTimeSpan };
 readonly ApiProvider p;
 readonly RunRequest r;
 readonly CancellationTokenSource stop = new();
 readonly Channel<AgentEvent> events = Channel.CreateUnbounded<AgentEvent>();
 Mcp? mcp;
 int exit;
 public override int ExitCode => exit;

 ApiRun(ApiAdapter a, RunRequest r) : base(a) { p = a.Provider; this.r = r; }
 internal static ApiRun Start(ApiAdapter a, RunRequest r)
 {
  var run = new ApiRun(a, r);
  Interlocked.Increment(ref Launched);
  _ = Task.Run(run.Loop);
  return run;
 }

 public override async IAsyncEnumerable<AgentEvent> Events([EnumeratorCancellation] CancellationToken token = default)
 {
  await foreach (var e in events.Reader.ReadAllAsync(token)) yield return e;
 }
 public override void Cancel() { Cancelled = true; stop.Cancel(); mcp?.Dispose(); }
 public override void Dispose() { if (!stop.IsCancellationRequested) stop.Cancel(); mcp?.Dispose(); }
 void Say(AgentEvent e) => events.Writer.TryWrite(e);

 /// The address Still may send a key to: https, or plain http only on this computer.
 public static Uri? Address(string url) =>
  Uri.TryCreate(url.Trim().TrimEnd('/'), UriKind.Absolute, out var u) && u.UserInfo.Length == 0 && u.Query.Length == 0
  && (u.Scheme == Uri.UriSchemeHttps || u.Scheme == Uri.UriSchemeHttp && u.Host is "localhost" or "127.0.0.1") ? u : null;
 static Uri At(Uri root, string path) => new(root.AbsoluteUri.TrimEnd('/') + "/" + path);
 static void Authorize(HttpRequestMessage req, string kind, string key)
 {
  if (kind == "anthropic") { req.Headers.Add("x-api-key", key); req.Headers.Add("anthropic-version", "2023-06-01"); }
  else req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", key);
 }

 async Task Loop()
 {
  using var limit = new Timer(_ => { TimedOut = true; Cancel(); }, null, Limit, Timeout.InfiniteTimeSpan);
  try { await Turn(); }
  catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
  catch (ApiFailure f) { exit = 1; Keep(f.Message); Say(new AgentEvent.Error(f.Message)); }
  catch (Exception ex) when (ex is HttpRequestException or IOException or JsonException or InvalidOperationException or TimeoutException) {
   exit = 1; string text = Plain(ex.Message); Keep(text); Say(new AgentEvent.Error("couldn't reach it: " + text));
  }
  finally { mcp?.Dispose(); events.Writer.TryComplete(); }
 }
 // A key never reaches an error, a log or the chat, even when a provider repeats it back.
 string Plain(string text) => ApiKeyStore.Read(p.Id) is { Length: > 0 } key ? text.Replace(key, "(key)") : text;

 async Task Turn()
 {
  string key = ApiKeyStore.Read(p.Id) ?? throw new ApiFailure("needs a key. Add one in Settings → Models.");
  var root = Address(p.Url) ?? throw new ApiFailure("its address must start with https:// (plain http only for localhost).");
  string model = r.Model.Length > 0 ? r.Model : p.Models.FirstOrDefault()?.Id ?? throw new ApiFailure("has no model. Add one in Settings → Models.");
  string file = Path.Combine(r.Folder, "api-" + (r.Session ?? "run") + ".json");
  JsonObject convo;
  if (r.Resume && !r.Forget) {
   if (!File.Exists(file)) throw new ApiFailure("No conversation found");
   convo = JsonNode.Parse(File.ReadAllText(file)) as JsonObject ?? throw new ApiFailure("No conversation found");
  } else convo = new JsonObject { ["in"] = 0L, ["out"] = 0L, ["cost"] = 0.0, ["messages"] = new JsonArray() };
  var messages = (JsonArray)convo["messages"]!;
  if (r.Session != null) Say(new AgentEvent.Session(r.Session));
  messages.Add(new JsonObject { ["role"] = "user", ["content"] = r.Prompt });
  JsonArray tools = [];
  if (!p.NoTools) {
   mcp = await Mcp.Start(r.Folder, r.Mcp, stop.Token);
   tools = await mcp.Tools(stop.Token);
  }
  long turnIn = 0, turnOut = 0;
  int context = p.Context > 0 ? p.Context : 128_000;
  try {
   for (int step = 0; ; step++) {
    if (step == MaxSteps) { Say(new AgentEvent.Note($"Stopped after {MaxSteps} steps in one reply. Ask again to carry on.")); break; }
    if (p.Limit > 0 && p.Spent.GetValueOrDefault(ApiProvider.Month)?.Cost >= p.Limit)
     throw new ApiFailure($"paused: this month's spending reached your limit of ${p.Limit:0.##}. Raise or turn off the limit in Settings → Models.");
    Trim(messages, context);
    Reply reply;
    try { reply = await Call(root, key, model, messages, tools); }
    catch (ApiFailure f) when (f.Message == "model") {
     if (p.Models.Count == 0 || model == p.Models[0].Id) throw new ApiFailure($"doesn't offer {model}. Pick another model in Settings → Models.");
     Say(new AgentEvent.Note($"{model} isn't available at {p.Name}, so this ran on {p.Models[0].Id}. You can pick another in Settings → Models."));
     model = p.Models[0].Id; step--; continue;
    }
    catch (ApiFailure f) when (f.Message == "context") {
     if (context <= 8000) throw new ApiFailure("this chat is too long for the model. Start a new chat.");
     context /= 2; step--; continue;
    }
    turnIn += reply.In; turnOut += reply.Out;
    Say(new AgentEvent.Spent(reply.In, reply.Out, p.CostOf(reply.In, reply.Out), r.Job));
    messages.Add(reply.Message);
    if (reply.Calls.Count == 0) break;
    var results = new List<(string Id, bool Ok, JsonArray Content)>();
    try {
     foreach (var (id, name, args) in reply.Calls) {
      Say(new AgentEvent.ToolCall(id, name, args?.DeepClone()));
      var (ok, content) = await mcp!.Call(name, args, stop.Token);
      results.Add((id, ok, content));
      Say(new AgentEvent.ToolResult(id, ok));
     }
    } finally {
     // Every call gets its answer, even when Stop came first, so the transcript stays one the provider accepts.
     foreach (var (id, _, _) in reply.Calls.Where(x => !results.Any(y => y.Id == x.Id))) results.Add((id, false, new JsonArray(new JsonObject { ["type"] = "text", ["text"] = "The user pressed Stop." })));
     AddResults(messages, results);
    }
   }
  } finally {
   double cost = p.CostOf(turnIn, turnOut);
   convo["in"] = (convo["in"]?.GetValue<long>() ?? 0) + turnIn; convo["out"] = (convo["out"]?.GetValue<long>() ?? 0) + turnOut;
   convo["cost"] = (convo["cost"]?.GetValue<double>() ?? 0) + cost;
   if (turnIn + turnOut > 0) Say(new AgentEvent.Usage($"Last reply: {AgentStream.Tokens(turnIn)} in, {AgentStream.Tokens(turnOut)} out{Money(cost)} · This chat: "
    + $"{AgentStream.Tokens(convo["in"]!.GetValue<long>())} in, {AgentStream.Tokens(convo["out"]!.GetValue<long>())} out{Money(convo["cost"]!.GetValue<double>())}"));
   if (!r.Forget) { Directory.CreateDirectory(r.Folder); File.WriteAllText(file + ".tmp", convo.ToJsonString()); File.Move(file + ".tmp", file, true); }
  }
 }
 string Money(double cost) => p.Priced ? $", about ${cost:0.00##}" : "";

 /// Leaves out the oldest turns (never the first, which has Still's instructions, or the latest) once the conversation
 /// would pass 70% of the model's context, guessing 4 characters a token. A note takes their place.
 internal static void Trim(JsonArray messages, int context)
 {
  const string Note = "(Earlier parts of this chat were left out to fit the model's context.)";
  static bool Starts(JsonNode? m) => m?["role"]?.GetValue<string>() == "user" && m["content"] is JsonValue; // a message of the user's, not tool results
  while (messages.ToJsonString().Length / 4 > context * 0.7) {
   bool noted = messages.Count > 1 && messages[1]?["content"] is JsonValue v && v.ToString() == Note;
   int from = noted ? 2 : 1, next = from + 1;
   while (next < messages.Count && !Starts(messages[next])) next++;
   if (next >= messages.Count) return; // only the first turn's message and the latest turn are left
   for (int i = next - 1; i >= from; i--) messages.RemoveAt(i);
   if (!noted) messages.Insert(1, new JsonObject { ["role"] = "assistant", ["content"] = Note });
  }
 }

 sealed record Reply(JsonObject Message, List<(string Id, string Name, JsonNode? Args)> Calls, long In, long Out);

 Task<Reply> Call(Uri root, string key, string model, JsonArray messages, JsonArray tools) => p.Kind == "anthropic" ? Anthropic(root, key, model, messages, tools) : OpenAi(root, key, model, messages, tools);
 static readonly Dictionary<string, int> Budgets = new() { ["low"] = 2048, ["medium"] = 8192, ["high"] = 24576 };

 async Task<HttpResponseMessage> Post(Uri url, string key, JsonObject body)
 {
  for (int tries = 0; ; tries++) {
   using var req = new HttpRequestMessage(HttpMethod.Post, url) { Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json") };
   Authorize(req, p.Kind, key);
   var res = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, stop.Token);
   if (res.IsSuccessStatusCode) return res;
   string text = await res.Content.ReadAsStringAsync(stop.Token);
   var status = res.StatusCode; var wait = RetryAfter(res); res.Dispose();
   if (status is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden) { ApiKeyStore.Refused.Add(p.Id); throw new ApiFailure("Key not accepted. Replace it in Settings → Models."); }
   if (status == HttpStatusCode.TooManyRequests) {
    var at = DateTime.Now + wait;
    if (tries == 2) throw new ApiFailure($"is still limiting requests. Try again after {at:t}.");
    Say(new AgentEvent.Note($"{p.Name} is limiting requests. Trying again at {at:t}."));
    await Task.Delay(wait, stop.Token);
    continue;
   }
   if (status == HttpStatusCode.NotFound || status == HttpStatusCode.BadRequest && text.Contains("model", StringComparison.OrdinalIgnoreCase) && !text.Contains("context", StringComparison.OrdinalIgnoreCase)) throw new ApiFailure("model");
   if (status == HttpStatusCode.BadRequest && (text.Contains("context", StringComparison.OrdinalIgnoreCase) || text.Contains("too long", StringComparison.OrdinalIgnoreCase))) throw new ApiFailure("context");
   throw new ApiFailure($"answered {(int)status}: {Plain(Clip(text))}");
  }
 }
 static string Clip(string s) { s = s.ReplaceLineEndings(" ").Trim(); return s.Length > 300 ? s[..300] + "…" : s; }
 static TimeSpan RetryAfter(HttpResponseMessage res)
 {
  var h = res.Headers.RetryAfter;
  var wait = h?.Delta ?? (h?.Date is { } d ? d - DateTimeOffset.Now : TimeSpan.FromSeconds(20));
  return wait < TimeSpan.FromSeconds(1) ? TimeSpan.FromSeconds(1) : wait > TimeSpan.FromMinutes(2) ? TimeSpan.FromMinutes(2) : wait;
 }
 /// Server-sent events: each data line's JSON, until [DONE] or the end.
 async IAsyncEnumerable<JsonNode> Stream(HttpResponseMessage res)
 {
  using var reader = new StreamReader(await res.Content.ReadAsStreamAsync(stop.Token));
  while (await reader.ReadLineAsync(stop.Token) is { } line) {
   if (!line.StartsWith("data:", StringComparison.Ordinal)) continue;
   string data = line[5..].Trim();
   if (data == "[DONE]") yield break;
   JsonNode? e = null;
   try { e = JsonNode.Parse(data); } catch (JsonException) { }
   if (e != null) yield return e;
  }
 }

 async Task<Reply> OpenAi(Uri root, string key, string model, JsonArray messages, JsonArray tools)
 {
  var body = new JsonObject { ["model"] = model, ["messages"] = messages.DeepClone(), ["stream"] = true, ["stream_options"] = new JsonObject { ["include_usage"] = true } };
  if (tools.Count > 0) body["tools"] = new JsonArray([.. tools.Select(t => (JsonNode)new JsonObject { ["type"] = "function", ["function"] = new JsonObject {
   ["name"] = t!["name"]!.DeepClone(), ["description"] = t["description"]?.DeepClone() ?? "", ["parameters"] = t["inputSchema"]?.DeepClone() ?? new JsonObject { ["type"] = "object" } } })]);
  if (r.Effort.Length > 0) body["reasoning_effort"] = r.Effort;
  using var res = await Post(At(root, "chat/completions"), key, body);
  var text = new StringBuilder(); var calls = new SortedDictionary<int, (string Id, string Name, StringBuilder Args)>(); long input = 0, output = 0;
  await foreach (var e in Stream(res)) {
   if (e["error"] is { } error) throw new ApiFailure("answered: " + Plain(Clip(error["message"]?.ToString() ?? error.ToJsonString())));
   if (e["usage"] is JsonObject u) { input = u["prompt_tokens"]?.GetValue<long>() ?? input; output = u["completion_tokens"]?.GetValue<long>() ?? output; }
   var delta = e["choices"] is JsonArray { Count: > 0 } choices ? choices[0]?["delta"] : null; // the usage chunk has none
   if (delta?["content"]?.GetValue<string>() is { Length: > 0 } chunk) { Say(new AgentEvent.Message(chunk, text.Length > 0 ? "" : null)); text.Append(chunk); }
   foreach (var tc in delta?["tool_calls"] as JsonArray ?? []) {
    int i = tc?["index"]?.GetValue<int>() ?? 0;
    var (id, name, args) = calls.GetValueOrDefault(i, ("", "", new StringBuilder()));
    calls[i] = (tc?["id"]?.GetValue<string>() is { Length: > 0 } nid ? nid : id, name + (tc?["function"]?["name"]?.GetValue<string>() ?? ""), args.Append(tc?["function"]?["arguments"]?.GetValue<string>() ?? ""));
   }
  }
  var message = new JsonObject { ["role"] = "assistant", ["content"] = text.Length > 0 ? text.ToString() : null };
  var list = calls.Values.Select((c, i) => (Id: c.Id.Length > 0 ? c.Id : "call_" + i, c.Name, Args: ParseArgs(c.Args.ToString()))).ToList();
  if (list.Count > 0) message["tool_calls"] = new JsonArray([.. list.Select(c => (JsonNode)new JsonObject { ["id"] = c.Id, ["type"] = "function",
   ["function"] = new JsonObject { ["name"] = c.Name, ["arguments"] = c.Args?.ToJsonString() ?? "{}" } })]);
  return new(message, list, input, output);
 }
 static JsonNode? ParseArgs(string s) { try { return s.Trim().Length == 0 ? new JsonObject() : JsonNode.Parse(s); } catch (JsonException) { return new JsonObject(); } }

 async Task<Reply> Anthropic(Uri root, string key, string model, JsonArray messages, JsonArray tools)
 {
  int budget = Budgets.GetValueOrDefault(r.Effort);
  var body = new JsonObject { ["model"] = model, ["max_tokens"] = budget + 8192, ["messages"] = messages.DeepClone(), ["stream"] = true };
  if (tools.Count > 0) body["tools"] = new JsonArray([.. tools.Select(t => (JsonNode)new JsonObject { ["name"] = t!["name"]!.DeepClone(),
   ["description"] = t["description"]?.DeepClone() ?? "", ["input_schema"] = t["inputSchema"]?.DeepClone() ?? new JsonObject { ["type"] = "object" } })]);
  if (budget > 0) body["thinking"] = new JsonObject { ["type"] = "enabled", ["budget_tokens"] = budget };
  using var res = await Post(At(root, "messages"), key, body);
  var blocks = new SortedDictionary<int, JsonObject>(); var json = new Dictionary<int, StringBuilder>(); long input = 0, output = 0; bool said = false;
  await foreach (var e in Stream(res)) {
   int i = e["index"]?.GetValue<int>() ?? 0;
   switch (e["type"]?.GetValue<string>()) {
    case "message_start": input = (e["message"]?["usage"]?["input_tokens"]?.GetValue<long>() ?? 0) + (e["message"]?["usage"]?["cache_read_input_tokens"]?.GetValue<long>() ?? 0); break;
    case "content_block_start" when e["content_block"] is JsonObject b:
     blocks[i] = (JsonObject)b.DeepClone();
     if (b["type"]?.GetValue<string>() == "tool_use") json[i] = new();
     if (b["type"]?.GetValue<string>() is "thinking" or "redacted_thinking") Say(new AgentEvent.Thinking());
     break;
    case "content_block_delta" when blocks.TryGetValue(i, out var block):
     var d = e["delta"];
     switch (d?["type"]?.GetValue<string>()) {
      case "text_delta": string chunk = d["text"]?.GetValue<string>() ?? ""; block["text"] = (block["text"]?.GetValue<string>() ?? "") + chunk; if (chunk.Length > 0) { Say(new AgentEvent.Message(chunk, said ? "" : null)); said = true; } break;
      case "input_json_delta": json[i].Append(d["partial_json"]?.GetValue<string>() ?? ""); break;
      case "thinking_delta": block["thinking"] = (block["thinking"]?.GetValue<string>() ?? "") + d["thinking"]?.GetValue<string>(); break;
      case "signature_delta": block["signature"] = d["signature"]?.GetValue<string>(); break;
     }
     break;
    case "content_block_stop" when json.TryGetValue(i, out var args) && blocks.TryGetValue(i, out var tool): tool["input"] = ParseArgs(args.ToString()); break;
    case "message_delta": output = e["usage"]?["output_tokens"]?.GetValue<long>() ?? output; break;
    case "error": throw new ApiFailure("answered: " + Plain(Clip(e["error"]?["message"]?.ToString() ?? e.ToJsonString())));
   }
  }
  var content = new JsonArray([.. blocks.Values.Where(b => b["type"]?.GetValue<string>() != "text" || (b["text"]?.GetValue<string>() ?? "").Length > 0)]);
  var calls = blocks.Values.Where(b => b["type"]?.GetValue<string>() == "tool_use").Select(b => (b["id"]?.GetValue<string>() ?? "", b["name"]?.GetValue<string>() ?? "", b["input"])).ToList();
  return new(new JsonObject { ["role"] = "assistant", ["content"] = content }, calls, input, output);
 }

 void AddResults(JsonArray messages, List<(string Id, bool Ok, JsonArray Content)> results)
 {
  static string Text(JsonArray c) => string.Join("\n", c.Select(x => x?["type"]?.GetValue<string>() == "text" ? x["text"]?.GetValue<string>() : "(An image: this provider gets text only.)"));
  if (p.Kind == "anthropic")
   messages.Add(new JsonObject { ["role"] = "user", ["content"] = new JsonArray([.. results.Select(x => (JsonNode)new JsonObject { ["type"] = "tool_result", ["tool_use_id"] = x.Id,
    ["content"] = new JsonArray([.. x.Content.Select(c => c?["type"]?.GetValue<string>() == "image"
     ? new JsonObject { ["type"] = "image", ["source"] = new JsonObject { ["type"] = "base64", ["media_type"] = c["mimeType"]?.DeepClone(), ["data"] = c["data"]?.DeepClone() } }
     : (JsonNode)new JsonObject { ["type"] = "text", ["text"] = c?["text"]?.DeepClone() ?? "" })]), ["is_error"] = !x.Ok })]) });
  else foreach (var x in results) messages.Add(new JsonObject { ["role"] = "tool", ["tool_call_id"] = x.Id, ["content"] = Text(x.Content) });
 }

 /// Checks an API provider for Settings, in plain words: the address, the key, the model, streaming and tool calls. It
 /// sends one tiny request (a second one without effort if the first is refused), which the provider may bill.
 public static async Task<(List<(string Part, bool Ok, string Text)> Checks, long In, long Out)> Test(ApiProvider p, string key, string model, CancellationToken token)
 {
  List<(string, bool, string)> checks = [];
  long input = 0, output = 0;
  if (Address(p.Url) is not { } root) { checks.Add(("Address", false, "Use an address that starts with https:// (plain http only for localhost).")); return (checks, 0, 0); }
  // The model list: reaches the address and checks the key, where the provider has one.
  List<string> listed = [];
  try {
   using var req = new HttpRequestMessage(HttpMethod.Get, At(root, "models"));
   Authorize(req, p.Kind, key);
   using var res = await Http.SendAsync(req, token).WaitAsync(TimeSpan.FromSeconds(30), token);
   checks.Add(("Address", true, $"Reached {root.Host}."));
   if (res.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden) { checks.Add(("Key", false, "Not accepted. Copy the key again from your provider and replace it.")); return (checks, 0, 0); }
   if (res.IsSuccessStatusCode) {
    checks.Add(("Key", true, "Accepted."));
    try { listed = [.. (JsonNode.Parse(await res.Content.ReadAsStringAsync(token))?["data"] as JsonArray ?? []).Select(m => m?["id"]?.GetValue<string>() ?? "").Where(m => m.Length > 0)]; } catch (JsonException) { }
   }
  } catch (Exception ex) when (ex is HttpRequestException or TimeoutException or IOException) {
   checks.Add(("Address", false, $"Couldn't reach {root.Host}. Check the base URL, and that the server is running.")); return (checks, 0, 0);
  }
  if (listed.Count > 0 && !listed.Contains(model)) { checks.Add(("Model", false, $"{model} isn't in {p.Name}'s model list. Pick one it offers.")); return (checks, 0, 0); }
  JsonArray probe = [new JsonObject { ["name"] = "still_test", ["description"] = "A harmless test tool. Call it once when asked.", ["inputSchema"] = new JsonObject { ["type"] = "object", ["properties"] = new JsonObject() } }];
  foreach (var tryEffort in new[] { "low", "" }) {
   var run = new ApiRun(ApiAdapter.Of(p), new RunRequest("", model, tryEffort, Path.GetTempPath(), [], null, false));
   using var cancel = token.Register(run.stop.Cancel);
   try {
    var reply = await run.Call(root, key, model, [new JsonObject { ["role"] = "user", ["content"] = "This is a connection test. Call the still_test tool once, then say done." }], probe);
    input += reply.In; output += reply.Out;
    if (!checks.Any(c => c.Item1 == "Key")) checks.Add(("Key", true, "Accepted."));
    checks.Add(("Model", true, $"{model} answered."));
    checks.Add(("Streaming", true, "Replies stream in as they're written."));
    checks.Add(reply.Calls.Any(c => c.Name == "still_test") ? ("Tools", true, "It calls tools, so it can use your tabs.") : ("Tools", false, "It didn't call the test tool, so it can chat but can't use your tabs."));
    checks.Add(tryEffort.Length > 0 ? ("Effort", true, "It takes an effort setting.") : ("Effort", false, "It refused an effort setting, so modes use Default effort."));
    return (checks, input, output);
   } catch (ApiFailure f) when (tryEffort.Length > 0 && !f.Message.StartsWith("Key not accepted", StringComparison.Ordinal)) { continue; } // refused with effort: once more without
   catch (ApiFailure f) {
    checks.Add(f.Message switch {
     "model" => ("Model", false, $"{p.Name} doesn't offer {model}. Pick one it offers."),
     var m when m.StartsWith("Key not accepted", StringComparison.Ordinal) => ("Key", false, "Not accepted. Copy the key again from your provider and replace it."),
     var m => ("Streaming", false, $"The request failed: {m}"),
    });
    return (checks, input, output);
   }
  }
  return (checks, input, output);
 }

 /// The models a provider lists, where it has a list (both kinds answer GET /models).
 public static async Task<List<string>> List(ApiProvider p, string key, CancellationToken token)
 {
  if (Address(p.Url) is not { } root) return [];
  using var req = new HttpRequestMessage(HttpMethod.Get, At(root, "models"));
  Authorize(req, p.Kind, key);
  using var res = await Http.SendAsync(req, token).WaitAsync(TimeSpan.FromSeconds(30), token);
  if (!res.IsSuccessStatusCode) return [];
  try { return [.. (JsonNode.Parse(await res.Content.ReadAsStringAsync(token))?["data"] as JsonArray ?? []).Select(m => m?["id"]?.GetValue<string>() ?? "").Where(m => m.Length is > 0 and <= 120).Take(300)]; }
  catch (JsonException) { return []; }
 }

 /// Still's MCP server as this run's child, spoken to over stdio like any MCP client. It asks the running Still about
 /// everything that needs the user, so approvals show in the chat as they do for the apps.
 sealed class Mcp : IDisposable
 {
  readonly Process process;
  readonly Dictionary<int, TaskCompletionSource<JsonNode>> waiting = [];
  int next;
  Mcp(Process process) => this.process = process;
  public static async Task<Mcp> Start(string folder, IReadOnlyList<string> args, CancellationToken token)
  {
   Directory.CreateDirectory(folder);
   var start = AgentAdapter.Launch(Environment.ProcessPath!, folder, args);
   start.RedirectStandardInput = start.RedirectStandardOutput = start.RedirectStandardError = true;
   start.StandardOutputEncoding = start.StandardErrorEncoding = new UTF8Encoding(false);
   start.StandardInputEncoding = new UTF8Encoding(false);
   var mcp = new Mcp(Process.Start(start) ?? throw new InvalidOperationException("couldn't start Still's tools."));
   _ = Task.Run(mcp.Read);
   _ = Task.Run(async () => { while (await mcp.process.StandardError.ReadLineAsync() is not null) { } });
   await mcp.Request("initialize", new JsonObject { ["protocolVersion"] = "2025-06-18", ["capabilities"] = new JsonObject(), ["clientInfo"] = new JsonObject { ["name"] = "Still", ["version"] = "1" } }, token);
   await mcp.Write(new JsonObject { ["jsonrpc"] = "2.0", ["method"] = "notifications/initialized" });
   return mcp;
  }
  async Task Read()
  {
   try {
    while (await process.StandardOutput.ReadLineAsync() is { } line) {
     JsonNode? m = null;
     try { m = JsonNode.Parse(line); } catch (JsonException) { }
     if (m is not JsonObject) continue;
     if (m["method"] != null && m["id"] != null) { // the server asks: a ping, or something this client doesn't offer
      await Write(m["method"]!.GetValue<string>() == "ping" ? new JsonObject { ["jsonrpc"] = "2.0", ["id"] = m["id"]!.DeepClone(), ["result"] = new JsonObject() }
       : new JsonObject { ["jsonrpc"] = "2.0", ["id"] = m["id"]!.DeepClone(), ["error"] = new JsonObject { ["code"] = -32601, ["message"] = "not supported" } });
      continue;
     }
     if (m["id"]?.GetValueKind() == JsonValueKind.Number && m["id"]!.GetValue<int>() is var id) {
      TaskCompletionSource<JsonNode>? wait;
      lock (waiting) waiting.Remove(id, out wait);
      wait?.TrySetResult(m);
     }
    }
   } catch (Exception ex) when (ex is IOException or ObjectDisposedException or InvalidOperationException) { }
   // Observed at once: after a Stop nobody waits on them.
   lock (waiting) { foreach (var w in waiting.Values) { w.TrySetException(new IOException("Still's tools stopped.")); _ = w.Task.Exception; } waiting.Clear(); }
  }
  async Task Write(JsonObject message) { await process.StandardInput.WriteLineAsync(message.ToJsonString()); await process.StandardInput.FlushAsync(); }
  async Task<JsonNode> Request(string method, JsonObject args, CancellationToken token)
  {
   var wait = new TaskCompletionSource<JsonNode>(TaskCreationOptions.RunContinuationsAsynchronously);
   int id;
   lock (waiting) { id = ++next; waiting[id] = wait; }
   await Write(new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id, ["method"] = method, ["params"] = args });
   var reply = await wait.Task.WaitAsync(token);
   if (reply["error"] is { } error) throw new IOException(error["message"]?.ToString() ?? "Still's tools refused.");
   return reply["result"] ?? new JsonObject();
  }
  public async Task<JsonArray> Tools(CancellationToken token) => (JsonArray)((await Request("tools/list", new JsonObject(), token))["tools"] as JsonArray ?? []).DeepClone();
  public async Task<(bool Ok, JsonArray Content)> Call(string name, JsonNode? args, CancellationToken token)
  {
   var result = await Request("tools/call", new JsonObject { ["name"] = name, ["arguments"] = args?.DeepClone() ?? new JsonObject() }, token);
   return (result["isError"]?.GetValue<bool>() != true, (JsonArray)(result["content"] as JsonArray ?? []).DeepClone());
  }
  public void Dispose()
  {
   try { if (!process.HasExited) process.Kill(true); } catch (Exception ex) when (ex is InvalidOperationException or System.ComponentModel.Win32Exception) { }
   process.Dispose();
  }
 }
}
