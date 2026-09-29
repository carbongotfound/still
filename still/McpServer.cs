using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Still;

// `Still.exe --mcp`: a Model Context Protocol server over stdio (JSON-RPC, one message per line).
// AI apps launch it; it forwards tool calls to the running Still over a current-user-only pipe.
internal static class McpServer
{
 static readonly object[] Tools = [
  Tool("list_tabs", "List the open (non-private) tabs in every Still window.", new { }),
  Tool("open_tab", "Open a new tab with a URL or search terms and wait for it to load.", new { url = Str("URL or search terms") }, "url"),
  Tool("navigate", "Load a URL or search in a tab (the active tab if tabId is omitted).", new { url = Str("URL or search terms"), tabId = Str("Tab id from list_tabs (optional)") }, "url"),
  Tool("switch_tab", "Bring a tab to the front.", new { tabId = Str("Tab id") }, "tabId"),
  Tool("close_tab", "Close a tab.", new { tabId = Str("Tab id") }, "tabId"),
  Tool("go_back", "Go back in a tab's history.", new { tabId = Str("Tab id (optional)") }),
  Tool("go_forward", "Go forward in a tab's history.", new { tabId = Str("Tab id (optional)") }),
  Tool("reload", "Reload a tab.", new { tabId = Str("Tab id (optional)") }),
  Tool("read_page", "Snapshot of a tab: title, URL, one line per visible clickable/typeable element as [id] kind \"label\" (→ link, =value, {options}), then the page text. Use the ids with click/type/scroll/wait_for. Ids change on every read.", new { text = Bool("Include page text (default true; false = elements only, fewer tokens)"), tabId = Str("Tab id (optional)") }),
  Tool("screenshot", "Take a PNG screenshot of a tab (brings it to the front).", new { tabId = Str("Tab id (optional)") }),
  Tool("click", "Click an element by id from read_page (or CSS selector, or visible text).", new { id = Str("Element id from read_page"), selector = Str("CSS selector (optional)"), text = Str("Visible text of a link or button (optional)"), tabId = Str("Tab id (optional)") }),
  Tool("type", "Type into a field by id (or CSS selector, or the focused field). On a dropdown, picks the option with that text. Optionally clear first and press Enter.", new { text = Str("Text to type, or option to pick"), id = Str("Element id from read_page"), selector = Str("CSS selector (optional)"), clear = Bool("Clear the field first"), submit = Bool("Press Enter afterwards"), tabId = Str("Tab id (optional)") }, "text"),
  Tool("scroll", "Scroll a tab up/down, or to an element id.", new { id = Str("Element id to scroll into view (optional)"), direction = new { type = "string", @enum = new[] { "up", "down" } }, amount = new { type = "number", description = "Pixels (default 800)" }, tabId = Str("Tab id (optional)") }),
  Tool("wait_for", "Wait until an element (id or CSS selector) or some text appears.", new { id = Str("Element id (optional)"), selector = Str("CSS selector (optional)"), text = Str("Text to wait for (optional)"), timeoutMs = new { type = "number", description = "Max wait, up to 30000 (default 10000)" }, tabId = Str("Tab id (optional)") }),
 ];
 static object Str(string d) => new { type = "string", description = d };
 static object Bool(string d) => new { type = "boolean", description = d };
 static object Tool(string name, string description, object properties, params string[] required) =>
  new { name, description, inputSchema = new { type = "object", properties, required } };

 public static void Run(string instance)
 {
  string client = "An AI agent";
  var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));
  var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };
  NamedPipeClientStream? pipe = null; StreamReader? pr = null; StreamWriter? pw = null;
  while (stdin.ReadLine() is { } line) {
   if (string.IsNullOrWhiteSpace(line)) continue;
   JsonNode? msg; try { msg = JsonNode.Parse(line); } catch (JsonException) { continue; }
   var id = msg?["id"]?.DeepClone(); string method = msg?["method"]?.GetValue<string>() ?? "";
   if (id == null) continue; // notifications need no reply
   object? result = null; object? error = null;
   try {
   switch (method) {
    case "initialize":
     client = msg?["params"]?["clientInfo"]?["name"]?.GetValue<string>() ?? client;
     result = new { protocolVersion = msg?["params"]?["protocolVersion"]?.GetValue<string>() ?? "2025-06-18", capabilities = new { tools = new { } },
      serverInfo = new { name = "still", version = Assembly.GetEntryAssembly()?.GetName().Version?.ToString(3) ?? "1" },
      instructions = "Control the user's Still browser. The user must approve you in Still first. Private tabs, passwords and cookies are never available." };
     break;
    case "ping": result = new { }; break;
    case "tools/list": result = new { tools = Tools }; break;
    case "tools/call": {
     string name = msg?["params"]?["name"]?.GetValue<string>() ?? "";
     var args = msg?["params"]?["arguments"] ?? new JsonObject();
     string reply;
     try {
      if (pipe is not { IsConnected: true }) {
       pipe?.Dispose(); pipe = new NamedPipeClientStream(".", MainWindow.AgentPipe(instance), PipeDirection.InOut, PipeOptions.CurrentUserOnly);
       pipe.Connect(3000); pr = new StreamReader(pipe, new UTF8Encoding(false)); pw = new StreamWriter(pipe, new UTF8Encoding(false)) { AutoFlush = true };
      }
      pw!.WriteLine(JsonSerializer.Serialize(new { client, tool = name, args }));
      reply = pr!.ReadLine() ?? throw new IOException("Still closed the connection.");
     } catch (Exception ex) when (ex is IOException or TimeoutException or UnauthorizedAccessException) {
      reply = JsonSerializer.Serialize(new { ok = false, error = "Still isn't running. Open Still (and turn on Settings → Let AI agents control Still), then try again." });
     }
     var r = JsonNode.Parse(reply)!;
     if (r["ok"]?.GetValue<bool>() != true) { result = new { content = new[] { new { type = "text", text = r["error"]?.GetValue<string>() ?? "Failed." } }, isError = true }; break; }
     var data = r["result"];
     if (data is JsonObject obj && obj["image"] is { } img) result = new { content = new object[] { new { type = "image", data = img.GetValue<string>(), mimeType = "image/png" } } };
     else result = new { content = new[] { new { type = "text", text = data?.ToJsonString(new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) ?? "{}" } } };
     break;
    }
    default: error = new { code = -32601, message = "Method not found: " + method }; break;
   }
   } catch (Exception ex) { pipe?.Dispose(); pipe = null; error = new { code = -32603, message = "Still error: " + ex.Message }; }
   stdout.WriteLine(error != null ? JsonSerializer.Serialize(new { jsonrpc = "2.0", id, error }) : JsonSerializer.Serialize(new { jsonrpc = "2.0", id, result }));
  }
 }

 [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern bool AttachConsole(int pid);

 // `Still.exe --cli <tool> [key=value ...]`: one tool call from a terminal. Prints JSON; screenshots are saved as PNG.
 public static int Cli(string instance, string[] argv)
 {
  AttachConsole(-1); // WPF exe: borrow the caller's console so output shows in a terminal
  var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };
  if (argv.Length == 0 || argv[0] is "help" or "--help" or "-h") {
   stdout.WriteLine("Usage: Still.exe --cli <tool> [key=value ...]\n\nTools:");
   foreach (var t in JsonSerializer.SerializeToNode(Tools)!.AsArray()) {
    var props = t!["inputSchema"]!["properties"]!.AsObject().Select(p => p.Key + "=");
    stdout.WriteLine($"  {t["name"]} {string.Join(" ", props)}\n      {t["description"]}");
   }
   return 0;
  }
  var args = new JsonObject();
  foreach (var a in argv.Skip(1)) {
   int eq = a.IndexOf('='); if (eq < 1) { stdout.WriteLine($"Arguments are key=value, got: {a}"); return 2; }
   string k = a[..eq].TrimStart('-'), v = a[(eq + 1)..];
   args[k] = v is "true" or "false" ? bool.Parse(v) : double.TryParse(v, out var n) && k is "amount" or "timeoutMs" ? n : v;
  }
  string reply;
  try {
   using var pipe = new NamedPipeClientStream(".", MainWindow.AgentPipe(instance), PipeDirection.InOut, PipeOptions.CurrentUserOnly);
   pipe.Connect(3000);
   var pw = new StreamWriter(pipe, new UTF8Encoding(false)) { AutoFlush = true };
   pw.WriteLine(JsonSerializer.Serialize(new { client = "Terminal agent", tool = argv[0], args }));
   reply = new StreamReader(pipe, new UTF8Encoding(false)).ReadLine() ?? throw new IOException();
  } catch (Exception ex) when (ex is IOException or TimeoutException or UnauthorizedAccessException) {
   stdout.WriteLine("Still isn't running, or Settings → Let AI agents control Still is off."); return 1;
  }
  var r = JsonNode.Parse(reply)!;
  if (r["ok"]?.GetValue<bool>() != true) { stdout.WriteLine("Error: " + (r["error"]?.GetValue<string>() ?? "Failed.")); return 1; }
  var data = r["result"];
  if (data is JsonObject obj && obj["image"] is { } img) {
   string file = Path.Combine(Path.GetTempPath(), $"still-screenshot-{DateTime.Now:yyyyMMdd-HHmmss}.png");
   File.WriteAllBytes(file, Convert.FromBase64String(img.GetValue<string>()));
   stdout.WriteLine(file); return 0;
  }
  stdout.WriteLine(data?.ToJsonString(new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) ?? "{}");
  return 0;
 }
}
