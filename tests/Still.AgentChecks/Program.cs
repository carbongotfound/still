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

var map = new Dictionary<string, string> { ["session"] = "session_id when type=init", ["text"] = "content when type=message,role=assistant", ["delta"] = "delta", ["tool"] = "tool_name when type=tool_use", ["toolArgs"] = "parameters" };
var gemini = Read("manifest-jsonl.jsonl", e => AgentStream.Fields(e, map));
Check(gemini.OfType<AgentEvent.Session>().Count() == 1, "Manifest jsonl: session");
Check(gemini.OfType<AgentEvent.ToolCall>().Single().Name == "mcp_still_open_tab", "Manifest jsonl: tool call");
Check(gemini.OfType<AgentEvent.Message>().Select(m => m.Text).SequenceEqual(["The title is ", "Example Domain."]), "Manifest jsonl: only assistant text");
Check(gemini.OfType<AgentEvent.Message>().All(m => m.Join == ""), "Manifest jsonl: streamed pieces join into one reply");

Console.WriteLine(failed == 0 ? "PASSED" : $"FAILED {failed}");
return failed == 0 ? 0 : 1;
