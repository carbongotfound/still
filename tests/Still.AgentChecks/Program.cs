// Feeds each agent CLI's recorded output (tests/fixtures/agents) through Still's parsers.
// Run: dotnet run --project tests/Still.AgentChecks -- <repo root>
using System.Text.Json.Nodes;
using Still;

string fixtures = Path.Combine(args.Length > 0 ? args[0] : ".", "tests", "fixtures", "agents");
int failed = 0;
void Check(bool ok, string name) { Console.WriteLine((ok ? "PASS: " : "FAIL: ") + name); if (!ok) failed++; }
List<AgentEvent> Read(string file, Func<JsonNode, IEnumerable<AgentEvent>> parse) =>
 [.. File.ReadLines(Path.Combine(fixtures, file)).Where(l => l.StartsWith('{')).SelectMany(l => parse(JsonNode.Parse(l)!))];

var claude = Read("claude.jsonl", e => AgentStream.Messages(e, false));
Check(claude.OfType<AgentEvent.Session>().Any(), "Claude: session id");
Check(claude.OfType<AgentEvent.ToolCall>().Any(t => t.Name.StartsWith("mcp__still__")), "Claude: Still tool calls");
Check(claude.OfType<AgentEvent.ToolResult>().Any(r => r.Ok), "Claude: tool results");
Check(claude.OfType<AgentEvent.Message>().LastOrDefault()?.Text.Contains("Example Domain") == true, "Claude: final answer");
Check(!claude.OfType<AgentEvent.Error>().Any(), "Claude: no errors on a good run");

var grok = Read("grok.jsonl", e => AgentStream.Messages(e, true));
Check(grok.OfType<AgentEvent.ToolCall>().Select(t => t.Name).SequenceEqual(["open_tab", "read_page"]), "Grok: use_tool unwrapped, search_tool hidden");
Check(grok.OfType<AgentEvent.Usage>().Any(u => u.Text.StartsWith("Last reply:")), "Grok: token usage");
Check(grok.OfType<AgentEvent.Message>().Any(), "Grok: answer");

var chatgpt = Read("chatgpt.jsonl", AgentStream.Codex);
Check(chatgpt.OfType<AgentEvent.Session>().SingleOrDefault()?.Id == "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b", "ChatGPT: thread id is the session");
Check(chatgpt.OfType<AgentEvent.ToolCall>().Count() == 2 && chatgpt.OfType<AgentEvent.ToolResult>().Count() == 2, "ChatGPT: tool calls and results");
Check(chatgpt.OfType<AgentEvent.Message>().Any(), "ChatGPT: answer");
var signedOut = AgentStream.Codex(JsonNode.Parse("""{"type":"turn.failed","error":{"message":"unexpected status 401 Unauthorized"}}""")!).Single();
Check(signedOut is AgentEvent.Error { Text: var t } && t.Contains("not signed in"), "ChatGPT: 401 means signed out");
// The ChatGPT app turning down one of Still's tools by its own approval step (what Codex prints when it can't ask: issue openai/codex#24135).
foreach (var why in new[] { "\"user cancelled MCP tool call\"", "{\"message\":\"MCP tool call requires approval, but approval policy is never\"}" }) {
 var turnedDown = AgentStream.Codex(JsonNode.Parse("""{"type":"item.completed","item":{"id":"item_1","type":"mcp_tool_call","server":"still","tool":"navigate","arguments":{},"result":null,"error":""" + why + ""","status":"failed"}}""")!).ToList();
 Check(turnedDown is [AgentEvent.ToolResult { Ok: false }, AgentEvent.Error { Text: var said }] && said.Contains("stopped Still's navigate tool") && said.Contains("approval_mode") && said.Contains("npm install -g @openai/codex"),
  "ChatGPT: its own approval turning down a Still tool says what was blocked and how to fix it (" + why + ")");
}
var ownError = AgentStream.Codex(JsonNode.Parse("""{"type":"item.completed","item":{"id":"item_2","type":"mcp_tool_call","server":"still","tool":"click","arguments":{},"result":null,"error":{"message":"tool call timed out"},"status":"failed"}}""")!).ToList();
Check(ownError is [AgentEvent.ToolResult { Ok: false }], "ChatGPT: any other failed tool is just a failed step");
Check(chatgpt.OfType<AgentEvent.Error>().Count() == 0, "ChatGPT: no errors on a good run");

var map = new Dictionary<string, string> { ["session"] = "session_id when type=init", ["text"] = "content when type=message,role=assistant", ["delta"] = "delta", ["tool"] = "tool_name when type=tool_use", ["toolArgs"] = "parameters" };
var gemini = Read("manifest-jsonl.jsonl", e => AgentStream.Fields(e, map));
Check(gemini.OfType<AgentEvent.Session>().Count() == 1, "Manifest jsonl: session");
Check(gemini.OfType<AgentEvent.ToolCall>().Single().Name == "mcp_still_open_tab", "Manifest jsonl: tool call");
Check(gemini.OfType<AgentEvent.Message>().Select(m => m.Text).SequenceEqual(["The title is ", "Example Domain."]), "Manifest jsonl: only assistant text");
Check(gemini.OfType<AgentEvent.Message>().All(m => m.Join == ""), "Manifest jsonl: streamed pieces join into one reply");

var gem = Read("gemini.jsonl", AgentStream.Gemini);
Check(gem.OfType<AgentEvent.Session>().SingleOrDefault()?.Id == "4f7f937b-f0f1-48ce-9ba7-084ff3df4ae1", "Gemini: init's session id");
Check(gem.OfType<AgentEvent.ToolCall>().SingleOrDefault()?.Name == "list_tabs", "Gemini: mcp_still_ prefix dropped from tool names");
Check(gem.OfType<AgentEvent.ToolResult>().SingleOrDefault() is { Ok: false } r && r.Id == gem.OfType<AgentEvent.ToolCall>().Single().Id, "Gemini: a failed tool result matches its call");
Check(gem.OfType<AgentEvent.Message>().Count() == 2 && gem.OfType<AgentEvent.Message>().All(m => m.Join == ""), "Gemini: streamed pieces join into one reply, the user's prompt left out");
Check(gem.OfType<AgentEvent.Usage>().SingleOrDefault()?.Text.StartsWith("Last reply: 28k in") == true, "Gemini: token usage from the result");
Check(!gem.OfType<AgentEvent.Error>().Any(), "Gemini: no errors on a good run");
Check(AgentStream.Gemini(JsonNode.Parse("""{"type":"result","status":"error","error":{"type":"FatalAuthenticationError","message":"[API Error: 401]"},"stats":{}}""")!).OfType<AgentEvent.Error>().Single().Text == "[API Error: 401]", "Gemini: an error result");
Check(!AgentStream.Gemini(JsonNode.Parse("""{"type":"error","severity":"warning","message":"slow"}""")!).Any(), "Gemini: warnings aren't errors");

var oc = Read("opencode.jsonl", AgentStream.OpenCode);
Check(oc.OfType<AgentEvent.Session>().Select(s => s.Id).Distinct().SingleOrDefault() == "ses_e622d5288ffe1XVjjLO0q4mDv2", "OpenCode: session id");
Check(oc.OfType<AgentEvent.ToolCall>().SingleOrDefault()?.Name == "list_tabs", "OpenCode: still_ prefix dropped from tool names");
Check(oc.OfType<AgentEvent.ToolResult>().SingleOrDefault() is { Ok: false }, "OpenCode: a failed tool gives a failed result");
Check(oc.OfType<AgentEvent.Message>().SingleOrDefault()?.Text.StartsWith("Done.") == true, "OpenCode: the answer");
Check(oc.OfType<AgentEvent.Usage>().Count() == 2 && oc.OfType<AgentEvent.Usage>().Last().Text.StartsWith("Last reply: 8.8k in"), "OpenCode: tokens per step");
Check(AgentStream.OpenCode(JsonNode.Parse("""{"type":"error","error":{"name":"UnknownError","data":{"message":"Session not found"}}}""")!).OfType<AgentEvent.Error>().Single().Text == "Session not found", "OpenCode: an error's message");

// A helper's permissions: the strictest rule up the chain wins (Delegation.Strictest).
Check(Delegation.Strictest(["always", "always"]) == "always", "Delegation: allowed when everyone up the chain allows it");
Check(Delegation.Strictest(["ask", "always"]) == "ask", "Delegation: the asker's Ask beats the helper's Always");
Check(Delegation.Strictest(["chat", "always"]) == "chat", "Delegation: the asker's Allow in this chat beats the helper's Always");
Check(Delegation.Strictest(["always", "chat"]) == "chat", "Delegation: the helper's own stricter rule stays");
Check(Delegation.Strictest(["chat", "always", "ask"]) == "ask", "Delegation: anyone up the chain asking means it asks");
Check(Delegation.Strictest(["always", "someday"]) == "ask", "Delegation: a mode it doesn't know asks");
Check(Delegation.Strictest([]) == "ask", "Delegation: no rule at all asks");

Console.WriteLine(failed == 0 ? "PASSED" : $"FAILED {failed}");
return failed == 0 ? 0 : 1;
