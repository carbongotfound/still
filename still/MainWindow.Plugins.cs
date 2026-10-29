using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Still;

// Plugins: the user's apps (Gmail, Calendar, Slack…) through Composio, a third-party service, with the user's own API
// key. Off until they paste one. The key is kept like saved logins (DPAPI, composio.dpapi) and only ever goes to Composio
// in the x-api-key header: never to a file in the clear, a log, memory, the shell, an agent, MCP or a CLI. Companions get
// two tools, plugin_tools and use_plugin: reads go ahead, anything else asks the user first. The Mac's twin is Plugins.swift.
public partial class MainWindow
{
 internal sealed record PluginAccount(string Id, string Slug, string Name);
 static string PluginKeyFile => Path.Combine(App.DataRoot, "composio.dpapi");
 static readonly string ComposioApi = (App.IsQa ? Environment.GetEnvironmentVariable("STILL_QA_COMPOSIO") : null) ?? "https://backend.composio.dev/api/v3.1";
 static readonly HttpClient ComposioHttp = new() { Timeout = TimeSpan.FromSeconds(30) };
 static string pluginStatus = "off"; // off (no key), checking, ok, bad (Composio refused the key), down (no answer)
 static List<PluginAccount> pluginAccounts = [];
 static List<object> pluginFound = [];
 static string pluginConnecting = "";
 static bool HasPluginKey => File.Exists(PluginKeyFile);
 // Names for the apps people connect most; Composio's own name for the rest.
 static readonly Dictionary<string, string> PluginNames = new() {
  ["gmail"] = "Gmail", ["googlecalendar"] = "Google Calendar", ["slack"] = "Slack", ["notion"] = "Notion", ["github"] = "GitHub", ["googledrive"] = "Google Drive",
  ["linear"] = "Linear", ["hubspot"] = "HubSpot", ["googlesheets"] = "Google Sheets", ["googledocs"] = "Google Docs", ["outlook"] = "Outlook", ["jira"] = "Jira",
  ["asana"] = "Asana", ["trello"] = "Trello", ["airtable"] = "Airtable", ["salesforce"] = "Salesforce", ["zoom"] = "Zoom", ["figma"] = "Figma", ["dropbox"] = "Dropbox",
  ["calendly"] = "Calendly", ["zendesk"] = "Zendesk", ["intercom"] = "Intercom", ["linkedin"] = "LinkedIn", ["stripe"] = "Stripe" };
 static string PluginName(string slug, string fallback = "") => PluginNames.GetValueOrDefault(slug) ?? (fallback.Length > 0 ? fallback : slug.Length > 0 ? char.ToUpperInvariant(slug[0]) + slug[1..] : "");

 static string? PluginKey()
 {
  try {
   byte[] plain = ProtectedData.Unprotect(File.ReadAllBytes(PluginKeyFile), null, DataProtectionScope.CurrentUser);
   try { return Encoding.UTF8.GetString(plain); } finally { CryptographicOperations.ZeroMemory(plain); }
  } catch (Exception e) when (e is IOException or CryptographicException or UnauthorizedAccessException) { return null; }
 }
 static void SavePluginKey(string key)
 {
  byte[] plain = Encoding.UTF8.GetBytes(key);
  try { File.WriteAllBytes(PluginKeyFile + ".tmp", ProtectedData.Protect(plain, null, DataProtectionScope.CurrentUser)); File.Move(PluginKeyFile + ".tmp", PluginKeyFile, true); }
  finally { CryptographicOperations.ZeroMemory(plain); }
 }
 static void ForgetPluginKey() { try { File.Delete(PluginKeyFile); } catch (IOException) { } pluginStatus = "off"; pluginAccounts = []; pluginFound = []; }

 /// One call to Composio. Null when there's no key, or Composio refused it or didn't answer (pluginStatus says which).
 /// Other errors come back as Composio's own { error: { message } }.
 static async Task<JsonNode?> Composio(HttpMethod method, string path, object? body = null)
 {
  if (PluginKey() is not { } key) { pluginStatus = "off"; return null; }
  using var request = new HttpRequestMessage(method, ComposioApi + path);
  request.Headers.Add("x-api-key", key);
  if (body != null) request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
  try {
   using var response = await ComposioHttp.SendAsync(request);
   if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden) { pluginStatus = "bad"; return null; }
   if ((int)response.StatusCode >= 500) { pluginStatus = "down"; return null; }
   pluginStatus = "ok";
   string text = await response.Content.ReadAsStringAsync();
   return text.Trim().Length == 0 ? new JsonObject() : JsonNode.Parse(text);
  } catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException) { pluginStatus = "down"; return null; }
 }
 static string Str(JsonNode? node, string key) => node is JsonObject o && o[key] is JsonValue v && v.TryGetValue<string>(out var s) ? s : "";
 static string ComposioError(JsonNode? node) => Str(node?["error"], "message") is { Length: > 0 } m ? m : Str(node, "error") is { Length: > 0 } e ? e : "Composio couldn't do that.";

 /// Who the user is to Composio: a random id for this profile, so its connections stay its own.
 string PluginUser
 {
  get {
   if (Prefs.PluginUser.Length == 0) { Prefs.PluginUser = "still-" + Convert.ToHexString(RandomNumberGenerator.GetBytes(8)).ToLowerInvariant(); SaveLater(); }
   return Prefs.PluginUser;
  }
 }

 async Task RefreshPlugins()
 {
  if (!HasPluginKey) { pluginStatus = "off"; PublishAiEverywhere(); return; }
  var list = await Composio(HttpMethod.Get, $"/connected_accounts?user_ids={Uri.EscapeDataString(PluginUser)}&statuses=ACTIVE&limit=200");
  if (list?["items"] is JsonArray items)
   pluginAccounts = items.Select(i => new PluginAccount(Str(i, "id"), Str(i?["toolkit"], "slug"), PluginName(Str(i?["toolkit"], "slug"), Str(i?["toolkit"], "name")))).Where(a => a.Id.Length > 0 && a.Slug.Length > 0).ToList();
  else if (pluginStatus == "bad") pluginAccounts = [];
  PublishAiEverywhere();
 }

 async Task SearchPlugins(string query)
 {
  var list = await Composio(HttpMethod.Get, "/toolkits?limit=40&sort_by=usage" + (query.Length > 0 ? "&search=" + Uri.EscapeDataString(query) : ""));
  // Only apps Composio signs in to itself: one click, no developer app of the user's own.
  pluginFound = list?["items"] is JsonArray items ? items.Where(i => i?["composio_managed_auth_schemes"] is not JsonArray { Count: 0 })
   .Select(i => (object)new { slug = Str(i, "slug"), name = PluginName(Str(i, "slug"), Str(i, "name")), about = Str(i?["meta"], "description") }).ToList() : [];
  PublishAiEverywhere();
 }

 /// Composio's own sign-in for one app, in a Still window. True once the account is connected.
 async Task<bool> ConnectPlugin(string slug)
 {
  if (pluginConnecting.Length > 0 || slug.Length == 0) return false;
  pluginConnecting = slug; PublishAiEverywhere();
  MainWindow? window = null;
  try {
   var configs = await Composio(HttpMethod.Get, "/auth_configs?is_composio_managed=true&toolkit_slug=" + Uri.EscapeDataString(slug));
   if (configs == null) return false;
   string config = (configs["items"] as JsonArray)?.FirstOrDefault(c => Str(c, "status") != "DISABLED") is { } found ? Str(found, "id") : "";
   if (config.Length == 0) config = Str((await Composio(HttpMethod.Post, "/auth_configs", new { toolkit = new { slug }, auth_config = new { type = "use_composio_managed_auth" } }))?["auth_config"], "id");
   if (config.Length == 0) return false;
   var link = await Composio(HttpMethod.Post, "/connected_accounts/link", new { auth_config_id = config, user_id = PluginUser });
   string url = Str(link, "redirect_url"), id = Str(link, "connected_account_id");
   if (id.Length == 0 || !(url.StartsWith("https://") || App.IsQa && url.StartsWith("http://127.0.0.1:"))) return false;
   window = new MainWindow(new BrowserTab { Url = url, Title = "Connect " + PluginName(slug) }, null);
   window.Show(); window.Activate();
   for (var end = DateTime.UtcNow.AddMinutes(10); DateTime.UtcNow < end;) {
    bool closed = window.closing || !Windows.Contains(window); // closed by the user: one last look, then stop
    await Task.Delay(closed ? 0 : 1500);
    var account = await Composio(HttpMethod.Get, "/connected_accounts/" + Uri.EscapeDataString(id));
    string status = Str(account, "status");
    if (status == "ACTIVE") { await RefreshPlugins(); return true; }
    if (closed || status is "FAILED" or "EXPIRED" or "INACTIVE" || account == null) return false;
   }
   return false;
  } finally {
   if (window is { closing: false } && Windows.Contains(window)) window.Close();
   pluginConnecting = ""; PublishAiEverywhere();
  }
 }

 async Task HandlePlugins(string op, JsonElement data)
 {
  string S(string k) => data.ValueKind == JsonValueKind.Object && data.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
  switch (op) {
   case "pluginKey" when S("key").Trim() is { Length: >= 8 and <= 400 } key && !key.Any(char.IsWhiteSpace):
    SavePluginKey(key); pluginStatus = "checking"; PublishAiEverywhere();
    await RefreshPlugins();
    if (pluginStatus == "bad") { ForgetPluginKey(); pluginStatus = "bad"; PublishAiEverywhere(); } // a key Composio refuses isn't kept
    break;
   case "pluginLink" when (S("to") switch { "key" => "https://platform.composio.dev/", "pricing" => "https://composio.dev/pricing", _ => "" }) is { Length: > 0 } link:
    var page = new MainWindow(new BrowserTab { Url = link }, null); page.Show(); page.Activate(); break;
   case "pluginKeyRemove": ForgetPluginKey(); PublishAiEverywhere(); break;
   case "pluginRefresh": await RefreshPlugins(); break;
   case "pluginSearch": await SearchPlugins(S("query").Trim() is var q && q.Length > 100 ? q[..100] : q); break;
   case "pluginConnect": _ = ConnectPlugin(S("slug")); break; // can take minutes: the shell doesn't wait
   case "pluginDisconnect" when pluginAccounts.FirstOrDefault(a => a.Id == S("id")) is { } gone:
    var deleted = await Composio(HttpMethod.Delete, "/connected_accounts/" + Uri.EscapeDataString(gone.Id));
    if (deleted != null) pluginAccounts.Remove(gone);
    await RefreshPlugins(); break;
   case "pluginToggle" when Companions.FirstOrDefault(c => c.Id == S("companion")) is { } mate && S("slug") is { Length: > 0 } slug:
    mate.PluginsOff.Remove(slug); if (data.TryGetProperty("on", out var on) && on.ValueKind == JsonValueKind.False) mate.PluginsOff.Add(slug);
    SaveLater(); PublishAiEverywhere(); break;
  }
 }

 object PluginsPayload() => new {
  key = HasPluginKey, status = pluginStatus, connecting = pluginConnecting, found = pluginFound,
  connected = pluginAccounts.Select(a => new { id = a.Id, slug = a.Slug, name = a.Name }) };

 /// What a companion is told about its plugins.
 static string PluginInstructions(Companion? who)
 {
  if (who == null || !HasPluginKey) return "";
  var mine = pluginAccounts.Where(a => !who.PluginsOff.Contains(a.Slug)).Select(a => a.Name).Distinct().ToList();
  return "\nPlugins: you can work in the user's own apps through Composio. " + (mine.Count > 0 ? "Connected for you: " + string.Join(", ", mine) + ". " : "None are connected for you yet. ")
   + "Call plugin_tools to find a tool, then use_plugin to run it. Reading goes ahead; anything that sends, posts, deletes, pays or changes data waits for the user's OK, and Still asks them for you. "
   + "If you need an app that isn't connected, call use_plugin anyway: Still offers the user a button to connect it.\n";
 }

 // Reads go ahead. Anything else might send, post, delete, pay or change data, so it waits for the user. When in doubt, it asks.
 static readonly HashSet<string> ReadVerbs = ["GET", "LIST", "FETCH", "SEARCH", "FIND", "READ", "RETRIEVE", "QUERY", "VIEW", "DESCRIBE", "LOOKUP", "COUNT"];
 static bool PluginReads(JsonNode? tool, string slug, string toolkit)
 {
  var tags = (tool?["tags"] as JsonArray)?.Select(t => t?.ToString().ToLowerInvariant() ?? "").ToList() ?? [];
  if (tags.Any(t => t.Contains("destructive") || t is "create" or "update" or "delete" or "write" or "send")) return false;
  string prefix = toolkit.ToUpperInvariant() + "_";
  return slug.StartsWith(prefix, StringComparison.Ordinal) && ReadVerbs.Contains(slug[prefix.Length..].Split('_')[0]);
 }

 /// A tool's inputs, small enough for the AI: its own schema, or only names, types and short descriptions when that's long.
 static JsonNode? PluginInputs(JsonNode? schema)
 {
  if (schema == null || schema.ToJsonString().Length <= 3000) return schema?.DeepClone();
  var props = new JsonObject();
  if (schema["properties"] is JsonObject all) foreach (var (name, p) in all.Take(40)) props[name] = new JsonObject { ["type"] = Str(p, "type"), ["description"] = Clip(Str(p, "description"), 140) };
  return new JsonObject { ["type"] = "object", ["properties"] = props, ["required"] = schema["required"]?.DeepClone() };
 }

 async Task<string> PluginTool(string who, string tool, JsonElement args)
 {
  if (runs.GetValueOrDefault(who) is not { } run) return Fail("Plugins are only for Still's own companions.");
  if (!HasPluginKey) return Fail("Plugins are off: the user hasn't added a Composio API key. Tell them they can turn plugins on in Settings → Plugins.");
  var mate = Companions.FirstOrDefault(c => c.Id == run.Chat.Companion);
  if (tool == "plugin_tools") {
   string plugin = S(args, "plugin").Trim().ToLowerInvariant(), query = S(args, "query").Trim();
   List<string> slugs = plugin.Length > 0 ? [plugin] : pluginAccounts.Select(a => a.Slug).Where(s => mate?.PluginsOff.Contains(s) != true).Distinct().ToList();
   if (slugs.Count == 0) return Fail("No plugins are connected for you. Pass the app's name as plugin (like gmail or googlecalendar) to see its tools.");
   var result = new JsonArray();
   foreach (var slug in slugs.Take(8)) {
    var list = await Composio(HttpMethod.Get, $"/tools?toolkit_slug={Uri.EscapeDataString(slug)}&limit={(slugs.Count > 1 ? 8 : 25)}" + (query.Length > 0 ? "&query=" + Uri.EscapeDataString(query) : ""));
    if (list == null) return Fail(pluginStatus == "bad" ? "Composio refused the user's key. Tell them to check it in Settings → Plugins." : "Composio isn't answering, so plugins are unavailable right now. Do it another way or try later.");
    result.Add(new JsonObject {
     ["plugin"] = slug, ["name"] = PluginName(slug), ["connected"] = pluginAccounts.Any(a => a.Slug == slug), ["offForYou"] = mate?.PluginsOff.Contains(slug) == true,
     ["tools"] = new JsonArray((list["items"] as JsonArray ?? []).Select(t => (JsonNode)new JsonObject {
      ["tool"] = Str(t, "slug"), ["what"] = Clip(Str(t, "description"), 300), ["asksFirst"] = !PluginReads(t, Str(t, "slug"), slug), ["input"] = PluginInputs(t?["input_parameters"]) }).ToArray()) });
   }
   return Reply(result);
  }

  // use_plugin
  string slugOfTool = S(args, "tool").Trim().ToUpperInvariant();
  if (slugOfTool.Length is 0 or > 120) return Fail("Pass the tool's name from plugin_tools, like GMAIL_FETCH_EMAILS.");
  var info = await Composio(HttpMethod.Get, "/tools/" + Uri.EscapeDataString(slugOfTool));
  if (info == null) return Fail(pluginStatus == "bad" ? "Composio refused the user's key. Tell them to check it in Settings → Plugins." : "Composio isn't answering, so plugins are unavailable right now. Do it another way or try later.");
  string toolkit = Str(info["toolkit"], "slug"), app = PluginName(toolkit, Str(info["toolkit"], "name"));
  if (toolkit.Length == 0) return Fail("There's no tool called " + slugOfTool + ". Call plugin_tools to find one.");
  if (mate?.PluginsOff.Contains(toolkit) == true) return Fail($"The user turned {app} off for you. They can turn it on in Settings → Plugins.");
  if (pluginAccounts.FirstOrDefault(a => a.Slug == toolkit) is not { } account) {
   // Not connected: a card with a button that connects it, then the work goes on.
   if (await Approve(run, "Connect " + app, app, "connect", "You sign in through Composio, in a Still window.", countdown: false) != "connect")
    return Fail($"The user didn't connect {app}. Don't ask again unless they bring it up.");
   if (!await ConnectPlugin(toolkit) || pluginAccounts.FirstOrDefault(a => a.Slug == toolkit) is not { } now) return Fail(app + " didn't get connected. Tell the user they can connect it in Settings → Plugins.");
   account = now;
  }
  var arguments = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("arguments", out var given) && given.ValueKind == JsonValueKind.Object ? JsonNode.Parse(given.GetRawText()) : new JsonObject();
  if (!PluginReads(info, slugOfTool, toolkit)) {
   string what = (Str(info, "name") is { Length: > 0 } n ? n : slugOfTool) + " in " + app;
   string why = string.Join(" · ", (arguments as JsonObject ?? new JsonObject()).Where(p => p.Value is JsonValue v && v.TryGetValue<string>(out var s) && s.Length > 0).Take(3).Select(p => p.Key + ": " + Clip(p.Value!.ToString(), 60)));
   string answer = await Approve(run, what, app, "plugin", why, countdown: false);
   Audit(run.Chat, what, app, answer is "once" or "chat" or "always" ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no");
   PublishAiEverywhere();
   if (answer is not ("once" or "chat" or "always")) return Fail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't try it again unless they ask.");
  }
  var done = await Composio(HttpMethod.Post, "/tools/execute/" + Uri.EscapeDataString(slugOfTool), new { user_id = PluginUser, connected_account_id = account.Id, arguments });
  if (done == null) return Fail("Composio isn't answering, so it didn't run. Tell the user.");
  if (done["successful"] is not JsonValue worked || !worked.TryGetValue<bool>(out var ok) || !ok) return Fail(app + ": " + ComposioError(done));
  string output = (done["data"] ?? new JsonObject()).ToJsonString();
  return Reply(output.Length > 40000 ? (object)(output[..40000] + "…") : JsonNode.Parse(output)!);
 }
}
