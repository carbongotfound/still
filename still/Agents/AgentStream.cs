using System.Text.Json.Nodes;
namespace Still;

/// One step of an agent run, the same whichever CLI produced it. Questions, approvals and files reach Still through its
/// own MCP tools (ask_user, the approval bar), so they never come through here.
public abstract record AgentEvent
{
 /// Join: when set, this continues the reply just before it (joined with Join) instead of starting a new one.
 public sealed record Message(string Text, string? Join = null) : AgentEvent;
 public sealed record Thinking : AgentEvent;
 public sealed record ToolCall(string Id, string Name, JsonNode? Args) : AgentEvent;
 public sealed record ToolResult(string Id, bool Ok) : AgentEvent;
 public sealed record Session(string Id) : AgentEvent;
 public sealed record Usage(string Text) : AgentEvent;
 public sealed record Error(string Text) : AgentEvent;
 /// A line in the chat from Still about the run (a rate limit pause, a model swapped for the default, the step cap).
 public sealed record Note(string Text) : AgentEvent;
 /// One API call's tokens and estimated cost (0 without prices), for the provider's monthly total. Job: chats, titles, setup or test.
 public sealed record Spent(long In, long Out, double Cost, string Job) : AgentEvent;
}

/// Turns each CLI's JSON lines into AgentEvents. Pure functions, so tests can feed them recorded output.
public static class AgentStream
{
 static string? Str(JsonNode? n) { try { return n?.GetValue<string>(); } catch (Exception ex) when (ex is InvalidOperationException or FormatException) { return n?.ToJsonString(); } }
 static string Pct(JsonNode? window) => window?["utilization"]?.GetValue<double>() is double u ? Math.Round(u * 100) + "%" : "?";
 public static string Tokens(long n) => n >= 1000 ? Math.Round(n / 1000.0, n >= 10000 ? 0 : 1) + "k" : n.ToString();
 static long Long(JsonNode? n) => n?.GetValue<long>() ?? 0;

 /// Claude Code (stream-json) and Grok Build (streaming-messages-json) both stream Anthropic Messages events.
 /// Grok wraps Still's tools in search_tool/use_tool; tokens are reported only where no usage window is.
 public static IEnumerable<AgentEvent> Messages(JsonNode e, bool tokenUsage)
 {
  string? type = Str(e["type"]);
  if (Str(e["session_id"]) is { Length: > 0 } session && type is "system" or "result") yield return new AgentEvent.Session(session);
  if (type == "result" && e["is_error"]?.GetValue<bool>() == true && e["result"] != null) yield return new AgentEvent.Error(Str(e["result"]) ?? "");
  if (type == "rate_limit_event" && e["rate_limit_info"]?["unifiedWindows"] is { } windows)
   yield return new AgentEvent.Usage($"5-hour limit {Pct(windows["five_hour"])} used · weekly {Pct(windows["seven_day"])}");
  else if (type == "result" && tokenUsage && e["usage"] is { } u)
   yield return new AgentEvent.Usage($"Last reply: {Tokens(Long(u["input_tokens"]) + Long(u["cache_read_input_tokens"]))} in, {Tokens(Long(u["output_tokens"]))} out");
  if (type is not ("assistant" or "user")) yield break;
  foreach (var block in e["message"]?["content"] as JsonArray ?? []) {
   switch (Str(block?["type"])) {
    case "text" when type == "assistant" && Str(block!["text"]) is { Length: > 0 } text: yield return new AgentEvent.Message(text); break;
    case "thinking" or "redacted_thinking" when type == "assistant": yield return new AgentEvent.Thinking(); break;
    case "tool_use" when type == "assistant":
     string id = Str(block!["id"]) ?? "", name = Str(block["name"]) ?? "";
     if (name == "use_tool") yield return new AgentEvent.ToolCall(id, Str(block["input"]?["tool_name"]) ?? "", block["input"]?["tool_input"]);
     else if (name != "search_tool") yield return new AgentEvent.ToolCall(id, name, block["input"]);
     break;
    case "tool_result" when type == "user": yield return new AgentEvent.ToolResult(Str(block!["tool_use_id"]) ?? "", block["is_error"]?.GetValue<bool>() != true); break;
   }
  }
 }

 /// The ChatGPT app's CLI (`exec --json`): thread, item and turn events.
 public static IEnumerable<AgentEvent> Codex(JsonNode e)
 {
  var item = e["item"];
  string kind = Str(item?["type"]) ?? "";
  switch (Str(e["type"])) {
   case "thread.started" when Str(e["thread_id"]) is { Length: > 0 } thread: yield return new AgentEvent.Session(thread); break;
   case "item.started" when kind == "mcp_tool_call": yield return new AgentEvent.ToolCall(Str(item!["id"]) ?? "", Str(item["tool"]) ?? "", item["arguments"]); break;
   case "item.completed" when kind == "mcp_tool_call": yield return new AgentEvent.ToolResult(Str(item!["id"]) ?? "", Str(item["status"]) != "failed" && item["error"] == null); break;
   case "item.completed" when kind == "reasoning": yield return new AgentEvent.Thinking(); break;
   case "item.completed" when kind == "agent_message" && Str(item!["text"]) is { Length: > 0 } text: yield return new AgentEvent.Message(text); break;
   case "turn.completed" when e["usage"] is { } u:
    yield return new AgentEvent.Usage($"Last reply: {Tokens(Long(u["input_tokens"]))} in ({Tokens(Long(u["cached_input_tokens"]))} cached), {Tokens(Long(u["output_tokens"]))} out");
    break;
   case "turn.failed" or "error":
    string message = Str(e["error"]?["message"]) ?? Str(e["message"]) ?? "failed";
    yield return new AgentEvent.Error(message.Contains("401") ? "not signed in. Sign in, then try again." : message);
    break;
  }
 }

 /// Gemini CLI (`--output-format stream-json`, checked with 0.66.0): init, the reply in message deltas, tool_use,
 /// tool_result, error and a closing result. Still's tools come as mcp_still_<tool>.
 public static IEnumerable<AgentEvent> Gemini(JsonNode e)
 {
  switch (Str(e["type"])) {
   case "init" when Str(e["session_id"]) is { Length: > 0 } session: yield return new AgentEvent.Session(session); break;
   case "message" when Str(e["role"]) == "assistant" && Str(e["content"]) is { Length: > 0 } text: yield return new AgentEvent.Message(text, e["delta"]?.GetValue<bool>() == true ? "" : null); break;
   case "tool_use": yield return new AgentEvent.ToolCall(Str(e["tool_id"]) ?? "", Bare(Str(e["tool_name"]), "mcp_still_"), e["parameters"]?.DeepClone()); break;
   case "tool_result": yield return new AgentEvent.ToolResult(Str(e["tool_id"]) ?? "", Str(e["status"]) == "success"); break;
   case "error" when Str(e["severity"]) == "error": yield return new AgentEvent.Error(Str(e["message"]) ?? "failed"); break;
   case "result":
    if (e["stats"] is { } u && Long(u["input_tokens"]) + Long(u["output_tokens"]) > 0)
     yield return new AgentEvent.Usage($"Last reply: {Tokens(Long(u["input_tokens"]))} in ({Tokens(Long(u["cached"]))} cached), {Tokens(Long(u["output_tokens"]))} out");
    if (Str(e["status"]) == "error") yield return new AgentEvent.Error(Str(e["error"]?["message"]) ?? "failed");
    break;
  }
 }

 /// OpenCode (`run --format json`, checked with 1.19.5): step_start, text (a whole part), tool_use (once it's done),
 /// step_finish with tokens, and error. Every event has the sessionID. Still's tools come as still_<tool>.
 public static IEnumerable<AgentEvent> OpenCode(JsonNode e)
 {
  var part = e["part"];
  switch (Str(e["type"])) {
   case "step_start" when Str(e["sessionID"]) is { Length: > 0 } session: yield return new AgentEvent.Session(session); break;
   case "text" when Str(part?["text"]) is { Length: > 0 } text: yield return new AgentEvent.Message(text); break;
   case "reasoning": yield return new AgentEvent.Thinking(); break;
   case "tool_use":
    string id = Str(part?["callID"]) ?? "";
    yield return new AgentEvent.ToolCall(id, Bare(Str(part?["tool"]), "still_"), part?["state"]?["input"]?.DeepClone());
    if (Str(part?["state"]?["status"]) is ("completed" or "error") and var status) yield return new AgentEvent.ToolResult(id, status == "completed");
    break;
   case "step_finish" when (part?["tokens"]) is { } t && Long(t["input"]) + Long(t["output"]) > 0:
    long cached = Long(t["cache"]?["read"]);
    yield return new AgentEvent.Usage($"Last reply: {Tokens(Long(t["input"]) + cached)} in ({Tokens(cached)} cached), {Tokens(Long(t["output"]))} out");
    break;
   case "error": yield return new AgentEvent.Error(Str(e["error"]?["data"]?["message"]) ?? Str(e["error"]?["name"]) ?? "failed"); break;
  }
 }

 /// DeepSeek Harness (`--profile headless --json`, built from its docs and source, not run live): session first, then text
 /// and thinking once each step commits, tool_call and tool_result, a final event repeating the answer (skipped), and
 /// error for a failure outside a turn. Still's tools come as mcp__still__<tool>.
 public static IEnumerable<AgentEvent> Dsh(JsonNode e)
 {
  switch (Str(e["type"])) {
   case "session" when Str(e["sessionId"]) is { Length: > 0 } session: yield return new AgentEvent.Session(session); break;
   case "text" when Str(e["text"]) is { Length: > 0 } text: yield return new AgentEvent.Message(text); break;
   case "thinking": yield return new AgentEvent.Thinking(); break;
   case "tool_call": yield return new AgentEvent.ToolCall(Str(e["callId"]) ?? "", Bare(Str(e["tool"]), "mcp__still__"), e["input"]?.DeepClone()); break;
   case "tool_result": yield return new AgentEvent.ToolResult(Str(e["callId"]) ?? "", Str(e["status"]) == "completed"); break;
   case "error": yield return new AgentEvent.Error(Str(e["message"]) ?? "failed"); break;
  }
 }

 static string Bare(string? tool, string prefix) => tool?.StartsWith(prefix, StringComparison.Ordinal) == true ? tool[prefix.Length..] : tool ?? "";

 /// A manifest agent's JSON lines, read through its field map. Each map entry is "path" or "path when key=value[,key=value]".
 public static IEnumerable<AgentEvent> Fields(JsonNode e, IReadOnlyDictionary<string, string> map)
 {
  string? Pick(string key) {
   if (!map.TryGetValue(key, out var rule)) return null;
   var parts = rule.Split(" when ", 2, StringSplitOptions.TrimEntries);
   if (parts.Length == 2 && !parts[1].Split(',', StringSplitOptions.TrimEntries).All(c => c.Split('=', 2) is [var k, var v] && Str(At(e, k)) == v)) return null;
   return Str(At(e, parts[0])) is { Length: > 0 } s ? s : null;
  }
  if (Pick("session") is { } session) yield return new AgentEvent.Session(session);
  if (Pick("tool") is { } tool) yield return new AgentEvent.ToolCall(Pick("toolId") ?? "", tool, map.TryGetValue("toolArgs", out var a) ? At(e, a)?.DeepClone() : null);
  if (Pick("text") is { } text) yield return new AgentEvent.Message(text, Pick("delta") == "true" ? "" : null);
  if (Pick("error") is { } error) yield return new AgentEvent.Error(error);
 }

 static JsonNode? At(JsonNode? node, string path)
 {
  foreach (var key in path.Split('.')) node = node is JsonObject o ? o[key] : node is JsonArray a && int.TryParse(key, out int i) && i < a.Count ? a[i] : null;
  return node;
 }
}
