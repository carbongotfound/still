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
}
