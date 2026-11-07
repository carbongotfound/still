using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
namespace Still;
static class PageScript
{
 // ExecuteScriptAsync counts as a click: the page gets ~5 s of user activation and can open pop-ups, go full screen
 // or start sound with nobody touching it. DevTools' Runtime.evaluate runs Still's own scripts without that.
 // Returns the result as JSON like ExecuteScriptAsync: "null" for undefined, errors and pages that are mid-navigation.
 public static async Task<string> RunAsync(this CoreWebView2 core, string script)
 {
  string reply;
  try { reply = await core.CallDevToolsProtocolMethodAsync("Runtime.evaluate", JsonSerializer.Serialize(new { expression = script, returnByValue = true })); }
  catch (Exception ex) when (ex is ArgumentException or COMException) { return "null"; }
  using var doc = JsonDocument.Parse(reply);
  var r = doc.RootElement;
  return !r.TryGetProperty("exceptionDetails", out _) && r.TryGetProperty("result", out var result) && result.TryGetProperty("value", out var value) ? value.GetRawText() : "null";
 }

 // Runs in a world of Still's own: it shares the page's DOM but none of its scripts, so a page can't change the browser's
 // built-in functions under Still's checks, or see them. window here is Still's and lasts as long as the document.
 sealed class World { public Task<long>? Id; }
 static readonly ConditionalWeakTable<CoreWebView2, World> worlds = new();
 static async Task<long> NewWorld(CoreWebView2 core)
 {
  using var tree = JsonDocument.Parse(await core.CallDevToolsProtocolMethodAsync("Page.getFrameTree", "{}"));
  string frame = tree.RootElement.GetProperty("frameTree").GetProperty("frame").GetProperty("id").GetString() ?? "";
  using var made = JsonDocument.Parse(await core.CallDevToolsProtocolMethodAsync("Page.createIsolatedWorld", JsonSerializer.Serialize(new { frameId = frame, worldName = "Still", grantUniveralAccess = false })));
  return made.RootElement.GetProperty("executionContextId").GetInt64();
 }
 /// The evaluation's reply, or an empty element when the page can't run anything right now.
 public static async Task<JsonElement> EvaluateInOwnWorld(this CoreWebView2 core, string script, bool byValue = true)
 {
  var world = worlds.GetOrCreateValue(core);
  for (int tries = 0; ; tries++) {
   var made = world.Id ??= NewWorld(core);
   try {
    using var reply = JsonDocument.Parse(await core.CallDevToolsProtocolMethodAsync("Runtime.evaluate", JsonSerializer.Serialize(new { expression = script, returnByValue = byValue, contextId = await made })));
    return reply.RootElement.Clone();
   } catch (Exception ex) when (ex is ArgumentException or COMException) {
    if (world.Id == made) world.Id = null; // a new document: the world went with the old one
    if (tries > 0) return default;
   }
  }
 }
 /// RunAsync, in Still's own world.
 public static async Task<string> RunInOwnWorld(this CoreWebView2 core, string script)
 {
  var r = await core.EvaluateInOwnWorld(script);
  return r.ValueKind == JsonValueKind.Object && !r.TryGetProperty("exceptionDetails", out _) && r.TryGetProperty("result", out var result) && result.TryGetProperty("value", out var value) ? value.GetRawText() : "null";
 }
}
