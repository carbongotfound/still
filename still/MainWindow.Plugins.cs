using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Still;

// Plugins: the user's apps (Gmail, Calendar, Slack…) through Composio, a third-party service, with the user's own project
// API key (ak_…, from Composio's Platform: Settings → Project Settings → API Keys). Off until they paste one. Composio's
// For You area hands out a Connect key (ck_…) for its MCP endpoint, which the API refuses: Still says so and doesn't
// keep it. The key is kept like saved logins (DPAPI, composio.dpapi) and only ever goes to Composio
// in the x-api-key header: never to a file in the clear, a log, memory, the shell, an agent, MCP or a CLI. The shell only
// hears that there is one, and its last four characters. Every app comes from Composio's own catalog, kept in
// plugin-catalog.json with each logo in Cache/PluginLogos. Companions get four small lookups (list_connected_plugins,
// find_plugins, get_plugin_tools, run_plugin_action), so no app's actions sit in their context until they need that app:
// reads go ahead, anything else asks the user first. The Mac's twin is Plugins.swift.
public partial class MainWindow
{
 internal sealed record PluginAccount(string Id, string Slug, string Name);
 // One app in Composio's catalog. Auth: managed (Composio signs in to it), none (nothing to sign in to) or custom (needs the user's own app at Composio).
 internal sealed record PluginApp(string Slug, string Name, string Logo, string[] Cats, string Auth);
 static string PluginKeyFile => Path.Combine(App.DataRoot, "composio.dpapi");
 static string PluginCatalogFile => Path.Combine(App.DataRoot, "plugin-catalog.json");
 static string PluginLogoFolder => Path.Combine(App.DataRoot, "Cache", "PluginLogos");
 static readonly string ComposioApi = (App.IsQa ? Environment.GetEnvironmentVariable("STILL_QA_COMPOSIO") : null) ?? "https://backend.composio.dev/api/v3.1";
 static readonly HttpClient ComposioHttp = new() { Timeout = TimeSpan.FromSeconds(30) };
 static string pluginStatus = "off"; // off (no key), ok, bad (Composio refused the key), down (no answer)
 static string pluginKeyProblem = ""; // the last key pasted wasn't kept: kind (not a project key), bad (refused) or down (no answer)
 static bool pluginChecking;
 static string? pluginKeyEnd; // the saved key's last four characters, all the shell ever sees of it
 static List<PluginAccount> pluginAccounts = [];
 static List<PluginApp>? pluginCatalog; // null until read from the cache or Composio
 static Dictionary<string, PluginApp> pluginBySlug = [];
 static DateTime pluginCatalogAt;
 static Task? pluginCatalogLoad;
 static readonly HashSet<string> pluginLogoTried = [];
 static string pluginConnecting = "", pluginFailed = "", pluginError = ""; // the app that didn't connect, and Composio's own words for the last failure
 // Keys Composio's API refuses in x-api-key: For You's Connect key (ck_) and the personal one its CLI uses (uak_).
 static bool NotProjectKey(string key) => key.StartsWith("ck_", StringComparison.Ordinal) || key.StartsWith("uak_", StringComparison.Ordinal);
 static bool HasPluginKey => File.Exists(PluginKeyFile);
 static string Cap(string s) => s.Length > 0 && char.IsLower(s[0]) ? char.ToUpperInvariant(s[0]) + s[1..] : s;
 static bool SlugOk(string s) => s.Length is > 0 and <= 80 && s.All(c => char.IsAsciiLetterLower(c) || char.IsAsciiDigit(c) || c is '_' or '-');
 static string PluginName(string slug, string fallback = "") => PluginCatalog().GetValueOrDefault(slug)?.Name ?? (fallback.Length > 0 ? fallback : Cap(slug));

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
  pluginKeyEnd = key[^4..];
 }
 static string KeyEnd => !HasPluginKey ? "" : pluginKeyEnd ??= PluginKey() is { Length: >= 4 } key ? key[^4..] : "";
 /// Off, cleanly: the key is gone, nothing is connected as far as Still knows, and a sign-in in progress stops. The apps stay
 /// connected in the user's Composio account, for when a key comes back.
 static void ForgetPluginKey() { try { File.Delete(PluginKeyFile); } catch (IOException) { } pluginKeyEnd = null; pluginStatus = "off"; pluginAccounts = []; pluginFailed = pluginError = pluginKeyProblem = ""; }

 /// One call to Composio, with the saved key or one being tried. Null when there's no key, or Composio refused it or didn't
 /// answer (pluginStatus says which). Other errors come back as Composio's own { error: { message } }.
 static async Task<JsonNode?> Composio(HttpMethod method, string path, object? body = null, string? trying = null)
 {
  if ((trying ?? PluginKey()) is not { } key) { pluginStatus = "off"; return null; }
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

 /// The catalog by slug: what's cached on disk until Composio's own list comes in.
 static Dictionary<string, PluginApp> PluginCatalog()
 {
  if (pluginCatalog == null) {
   try {
    var saved = JsonNode.Parse(File.ReadAllText(PluginCatalogFile));
    pluginCatalogAt = saved?["at"]?.GetValue<DateTime>() ?? default;
    SetCatalog(saved?["apps"]?.Deserialize<List<PluginApp>>() ?? []);
   } catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException or FormatException or InvalidOperationException) { SetCatalog([]); }
  }
  return pluginBySlug;
 }
 static void SetCatalog(List<PluginApp> apps) { pluginCatalog = apps.Where(a => SlugOk(a.Slug)).DistinctBy(a => a.Slug).ToList(); pluginBySlug = pluginCatalog.ToDictionary(a => a.Slug); }
 static PluginApp? CatalogApp(JsonNode? i)
 {
  string slug = Str(i, "slug").ToLowerInvariant();
  var meta = i?["meta"];
  string[] cats = (meta?["categories"] as JsonArray ?? []).Select(c => Cap((c is JsonValue v && v.TryGetValue<string>(out var s) ? s : Str(c, "name") is { Length: > 0 } n ? n : Str(c, "id")).Trim()))
   .Where(c => c.Length is > 0 and < 60).Distinct().Take(4).ToArray();
  string auth = i?["no_auth"] is JsonValue none && none.TryGetValue<bool>(out var no) && no ? "none" : i?["composio_managed_auth_schemes"] is JsonArray { Count: > 0 } ? "managed" : "custom";
  return SlugOk(slug) ? new(slug, Str(i, "name") is { Length: > 0 } name ? name : Cap(slug), Str(meta, "logo"), cats, auth) : null;
 }

 /// Composio's whole catalog, most used first, page by page. Once a day, or when asked; a list Composio can't give says why.
 static Task LoadPluginCatalog(bool force = false)
 {
  if (pluginCatalogLoad is { IsCompleted: false } running) return running;
  if (!HasPluginKey || !force && PluginCatalog().Count > 0 && DateTime.UtcNow - pluginCatalogAt < TimeSpan.FromHours(24)) return Task.CompletedTask;
  return pluginCatalogLoad = FetchCatalog();
  static async Task FetchCatalog()
  {
   var apps = new List<PluginApp>();
   string cursor = "";
   for (int page = 0; page < 40; page++) {
    var list = await Composio(HttpMethod.Get, "/toolkits?limit=500&sort_by=usage" + (cursor.Length > 0 ? "&cursor=" + Uri.EscapeDataString(cursor) : ""));
    if (list?["items"] is not JsonArray items) { pluginError = list == null ? "" : "Composio couldn't list its apps: " + ComposioError(list); PublishAiEverywhere(); return; }
    apps.AddRange(items.Select(CatalogApp).OfType<PluginApp>());
    if ((cursor = Str(list, "next_cursor")).Length == 0 || items.Count == 0) break;
   }
   SetCatalog(apps); pluginCatalogAt = DateTime.UtcNow; pluginError = "";
   try { File.WriteAllText(PluginCatalogFile + ".tmp", new JsonObject { ["at"] = pluginCatalogAt, ["apps"] = JsonSerializer.SerializeToNode(pluginCatalog) }.ToJsonString()); File.Move(PluginCatalogFile + ".tmp", PluginCatalogFile, true); }
   catch (Exception e) when (e is IOException or UnauthorizedAccessException) { App.Log(e); }
   foreach (var window in Windows) window.SendPluginCatalog();
   PublishAiEverywhere();
  }
 }
 // Sent on its own, not with every state update: it's hundreds of apps. No logo addresses: the shell only shows images it's handed.
 void SendPluginCatalog() => ShellSend(new { kind = "pluginCatalog", data = PluginCatalog().Count == 0 ? [] : pluginCatalog!.Select(a => new { slug = a.Slug, name = a.Name, cats = a.Cats, auth = a.Auth }) });

 /// Logos for the apps the page shows, as data: images (the shell loads nothing from the web). Each comes from Composio's
 /// catalog once, without the key, and stays in Cache/PluginLogos. One that doesn't load keeps its initial.
 async Task SendPluginLogos(JsonElement slugs)
 {
  var ready = new Dictionary<string, string>();
  var fetch = new List<PluginApp>();
  foreach (var slug in slugs.ValueKind == JsonValueKind.Array ? slugs.EnumerateArray().Select(s => s.ValueKind == JsonValueKind.String ? s.GetString() ?? "" : "").Distinct().Take(400) : Enumerable.Empty<string>()) {
   if (PluginCatalog().GetValueOrDefault(slug) is not { Logo.Length: > 0 } app) continue;
   string file = Path.Combine(PluginLogoFolder, slug);
   if (File.Exists(file)) { try { ready[slug] = File.ReadAllText(file); } catch (IOException) { } }
   else if (HasPluginKey && pluginLogoTried.Add(slug)) fetch.Add(app); // nothing new from the web while plugins are off
  }
  if (ready.Count > 0) ShellSend(new { kind = "pluginLogos", data = ready });
  foreach (var batch in fetch.Chunk(8)) {
   var got = await Task.WhenAll(batch.Select(FetchLogo));
   var done = batch.Zip(got).Where(p => p.Second != null).ToDictionary(p => p.First.Slug, p => p.Second!);
   if (done.Count > 0) ShellSend(new { kind = "pluginLogos", data = done });
  }
  static async Task<string?> FetchLogo(PluginApp app)
  {
   if (!(app.Logo.StartsWith("https://", StringComparison.Ordinal) || App.IsQa && app.Logo.StartsWith("http://127.0.0.1:", StringComparison.Ordinal))) return null;
   try {
    using var response = await ComposioHttp.GetAsync(app.Logo, HttpCompletionOption.ResponseHeadersRead);
    if (!response.IsSuccessStatusCode || response.Content.Headers.ContentLength > 300_000) return null;
    byte[] bytes = await response.Content.ReadAsByteArrayAsync();
    string head = Encoding.ASCII.GetString(bytes, 0, Math.Min(bytes.Length, 300));
    string type = response.Content.Headers.ContentType?.MediaType is { } t && t.StartsWith("image/", StringComparison.Ordinal) ? t
     : head.Contains("<svg", StringComparison.OrdinalIgnoreCase) ? "image/svg+xml" : bytes is [0x89, (byte)'P', (byte)'N', (byte)'G', ..] ? "image/png" : "";
    if (type.Length == 0 || bytes.Length is 0 or > 300_000) return null;
    string uri = $"data:{type};base64,{Convert.ToBase64String(bytes)}";
    Directory.CreateDirectory(PluginLogoFolder);
    await File.WriteAllTextAsync(Path.Combine(PluginLogoFolder, app.Slug), uri);
    return uri;
   } catch (Exception e) when (e is HttpRequestException or TaskCanceledException or IOException or UnauthorizedAccessException) { return null; }
  }
 }

 /// Composio's own sign-in for one app, in a Still window. True once the account is connected.
 async Task<bool> ConnectPlugin(string slug)
 {
  if (pluginConnecting.Length > 0 || slug.Length == 0) return false;
  pluginConnecting = slug; pluginFailed = pluginError = ""; PublishAiEverywhere();
  MainWindow? window = null;
  bool Failed(JsonNode? why) { if (HasPluginKey) { pluginFailed = slug; pluginError = why == null ? "" : PluginName(slug) + " didn't connect: " + ComposioError(why); } return false; }
  try {
   // An app the user set up at Composio themselves first, then Composio's own sign-in.
   var configs = await Composio(HttpMethod.Get, "/auth_configs?toolkit_slug=" + Uri.EscapeDataString(slug));
   if (configs?["items"] is not JsonArray all) return Failed(configs);
   string config = all.Where(c => Str(c, "status") != "DISABLED").OrderBy(c => c?["is_composio_managed"]?.GetValue<bool>() == true).FirstOrDefault() is { } found ? Str(found, "id") : "";
   JsonNode? made = null;
   if (config.Length == 0) config = Str((made = await Composio(HttpMethod.Post, "/auth_configs", new { toolkit = new { slug }, auth_config = new { type = "use_composio_managed_auth" } }))?["auth_config"], "id");
   if (config.Length == 0) return Failed(made);
   var link = await Composio(HttpMethod.Post, "/connected_accounts/link", new { auth_config_id = config, user_id = PluginUser });
   string url = Str(link, "redirect_url"), id = Str(link, "connected_account_id");
   if (id.Length == 0 || !(url.StartsWith("https://") || App.IsQa && url.StartsWith("http://127.0.0.1:"))) return Failed(link);
   window = new MainWindow(new BrowserTab { Url = url, Title = "Connect " + PluginName(slug) }, null) { temporary = true };
   window.Show(); window.Activate();
   for (var end = DateTime.UtcNow.AddMinutes(10); DateTime.UtcNow < end;) {
    bool closed = window.closing || !Windows.Contains(window); // closed by the user: one last look, then stop
    await Task.Delay(closed ? 0 : 1500);
    if (!HasPluginKey) return false; // the key was removed meanwhile
    var account = await Composio(HttpMethod.Get, "/connected_accounts/" + Uri.EscapeDataString(id));
    string status = Str(account, "status");
    if (status == "ACTIVE") { await RefreshPlugins(); return true; }
    if (closed) return false; // the user closed it: not an error
    if (status is "FAILED" or "EXPIRED" or "INACTIVE" || account == null) return Failed(account == null ? null : new JsonObject { ["error"] = "the sign-in didn't finish." });
   }
   return Failed(new JsonObject { ["error"] = "the sign-in took too long." });
  } finally {
   if (window is { closing: false } && Windows.Contains(window)) window.Close();
   pluginConnecting = ""; PublishAiEverywhere();
  }
 }

 async Task HandlePlugins(string op, JsonElement data)
 {
  string S(string k) => data.ValueKind == JsonValueKind.Object && data.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
  switch (op) {
   // A new key, or one replacing the saved key: checked with Composio first, and only kept if Composio takes it.
   case "pluginKey" when S("key").Trim() is { Length: >= 8 and <= 400 } key && !key.Any(char.IsWhiteSpace):
    if (NotProjectKey(key)) { pluginKeyProblem = "kind"; PublishAiEverywhere(); break; } // never sent, never kept
    pluginChecking = true; pluginKeyProblem = ""; PublishAiEverywhere();
    string before = pluginStatus;
    var tried = await Composio(HttpMethod.Get, $"/connected_accounts?user_ids={Uri.EscapeDataString(PluginUser)}&statuses=ACTIVE&limit=1", trying: key);
    pluginChecking = false;
    if (tried == null) { pluginKeyProblem = pluginStatus == "bad" ? "bad" : "down"; pluginStatus = HasPluginKey ? before : "off"; PublishAiEverywhere(); break; }
    SavePluginKey(key);
    await RefreshPlugins();
    await LoadPluginCatalog(force: true);
    break;
   case "pluginLink" when S("to") == "key":
    var page = new MainWindow(new BrowserTab { Url = (App.IsQa ? Environment.GetEnvironmentVariable("STILL_QA_COMPOSIO_PAGE") : null) ?? "https://platform.composio.dev/" }, null) { temporary = true }; page.Show(); page.Activate(); break;
   case "pluginKeyRemove": ForgetPluginKey(); PublishAiEverywhere(); break;
   case "pluginRefresh":
    SendPluginCatalog();
    await RefreshPlugins();
    if (pluginStatus == "ok") await LoadPluginCatalog(data.ValueKind == JsonValueKind.Object && data.TryGetProperty("force", out var force) && force.ValueKind == JsonValueKind.True);
    break;
   case "pluginLogos" when data.ValueKind == JsonValueKind.Object && data.TryGetProperty("slugs", out var slugs): await SendPluginLogos(slugs); break;
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
  key = HasPluginKey, keyEnd = KeyEnd, status = pluginStatus, checking = pluginChecking, problem = pluginKeyProblem, connecting = pluginConnecting, failed = pluginFailed, error = pluginError,
  connected = pluginAccounts.Select(a => new { id = a.Id, slug = a.Slug, name = a.Name }) };

 /// What a companion is told about its plugins: how to look, not what's there.
 static string PluginInstructions(Companion? who) => who == null || !HasPluginKey ? "" :
  "\nPlugins: you can work in the user's own apps (email, calendars, chat, docs and hundreds more) through Composio. "
  + "list_connected_plugins names the apps connected for you; find_plugins looks one up by name or category; get_plugin_tools loads one app's actions when you need them; run_plugin_action runs one. "
  + "Reading goes ahead; anything that sends, posts, deletes, pays or changes data waits for the user's OK, and Still asks them for you. "
  + "If you need an app that isn't connected, don't guess or work around it: run_plugin_action asks the user to connect it.\n";

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

 /// An app the companion named: its slug, or its name as the catalog or a connected account has it.
 static string? PluginSlug(string named)
 {
  string n = named.Trim(), lower = n.ToLowerInvariant();
  if (n.Length is 0 or > 80) return null;
  if (PluginCatalog().ContainsKey(lower) || pluginAccounts.Any(a => a.Slug == lower)) return lower;
  return pluginCatalog!.FirstOrDefault(a => a.Name.Equals(n, StringComparison.OrdinalIgnoreCase))?.Slug ?? pluginAccounts.FirstOrDefault(a => a.Name.Equals(n, StringComparison.OrdinalIgnoreCase))?.Slug
   ?? (lower.Replace(" ", "") is var squashed && pluginBySlug.ContainsKey(squashed) ? squashed : null);
 }

 /// All an action will carry, for its card. Past what fits, the card says how much it isn't showing.
 static string PluginWhy(JsonObject? arguments)
 {
  string all = string.Join(" · ", (arguments ?? []).Where(p => p.Value != null && p.Value.ToString().Length > 0).Select(p => p.Key + ": " + (p.Value is JsonValue v && v.TryGetValue<string>(out var s) ? s : p.Value!.ToJsonString())).OrderBy(line => line.Length)); // shortest first: a long body can't push the recipient off the card
  return all.Length <= 1200 ? all : all[..1200] + " … and " + (all.Length - 1200) + " more characters not shown";
 }

 async Task<string> PluginTool(string who, string tool, JsonElement args)
 {
  if (runs.GetValueOrDefault(who) is not { } run) return Fail("Plugins are only for Still's own companions.");
  if (run.Chat.Ephemeral) return Fail("Connected apps are off in incognito windows. Tell the user if it matters, and do it another way.");
  if (!HasPluginKey) return Fail("Plugins are off: the user hasn't added a Composio API key. Tell them they can turn plugins on in Skills & plugins.");
  // A helper works for whoever asked: an app any of them has off stays off.
  var team = ExchangeOf(run.Chat).Chain.Select(id => Companions.FirstOrDefault(c => c.Id == id)).ToList();
  bool Mine(string slug) => team.All(mate => mate?.PluginsOff.Contains(slug) != true);
  string Unavailable() => pluginStatus == "bad" ? "Composio refused the user's key. Tell them to check it in Skills & plugins." : "Composio isn't answering, so plugins are unavailable right now. Do it another way or try later.";

  if (tool == "list_connected_plugins") {
   if (pluginStatus != "ok") await RefreshPlugins();
   if (pluginStatus is "bad" or "down") return Fail(Unavailable());
   return Reply(pluginAccounts.Where(a => Mine(a.Slug)).Select(a => a.Name).Distinct().ToList());
  }
  if (tool == "find_plugins") {
   await LoadPluginCatalog();
   if (PluginCatalog().Count == 0) return Fail(Unavailable());
   string query = S(args, "query").Trim(), category = S(args, "category").Trim();
   var found = pluginCatalog!.Where(a => (query.Length == 0 || a.Name.Contains(query, StringComparison.OrdinalIgnoreCase) || a.Slug.Contains(query.Replace(" ", ""), StringComparison.OrdinalIgnoreCase))
    && (category.Length == 0 || a.Cats.Any(c => c.Contains(category, StringComparison.OrdinalIgnoreCase)))).ToList();
   return Reply(new { apps = found.Take(25).Select(a => new { name = a.Name, categories = a.Cats, connected = pluginAccounts.Any(c => c.Slug == a.Slug) && Mine(a.Slug) }), more = Math.Max(0, found.Count - 25) });
  }

  if (PluginCatalog().Count == 0) await LoadPluginCatalog();
  if (PluginSlug(S(args, "plugin")) is not { } slug) return Fail($"There's no app called “{Clip(S(args, "plugin"), 60)}”. Call find_plugins to look it up.");
  string app = PluginName(slug);
  if (!Mine(slug)) return Fail($"The user turned {app} off for you. They can turn it on in Skills & plugins.");
  if (tool == "get_plugin_tools") {
   string query = S(args, "query").Trim();
   var list = await Composio(HttpMethod.Get, $"/tools?toolkit_slug={Uri.EscapeDataString(slug)}&limit=25" + (query.Length > 0 ? "&query=" + Uri.EscapeDataString(query) : ""));
   if (list == null) return Fail(Unavailable());
   var items = list["items"] as JsonArray ?? [];
   int total = list["total_items"] is JsonValue t && t.TryGetValue<int>(out var n) ? n : items.Count;
   return Reply(new JsonObject {
    ["plugin"] = app, ["connected"] = pluginAccounts.Any(a => a.Slug == slug),
    ["actions"] = new JsonArray(items.Select(t => (JsonNode)new JsonObject {
     ["action"] = Str(t, "slug"), ["what"] = Clip(Str(t, "description"), 300), ["asksFirst"] = !PluginReads(t, Str(t, "slug"), slug), ["input"] = PluginInputs(t?["input_parameters"]) }).ToArray()),
    ["more"] = total > items.Count ? $"{total - items.Count} more: pass query to narrow it down." : null });
  }

  // run_plugin_action
  string action = S(args, "action").Trim().ToUpperInvariant();
  if (action.Length is 0 or > 120) return Fail($"Pass the action's name from get_plugin_tools, like {slug.ToUpperInvariant()}_….");
  var info = await Composio(HttpMethod.Get, "/tools/" + Uri.EscapeDataString(action));
  if (info == null) return Fail(Unavailable());
  if (Str(info["toolkit"], "slug") != slug) return Fail($"{app} has no action called {action}. Call get_plugin_tools to see its actions.");
  if (pluginAccounts.FirstOrDefault(a => a.Slug == slug) is not { } account) {
   // Not connected: a card with a button that connects it, then the work goes on.
   if (await Approve(run, "Connect " + app, app, "connect", "You sign in through Composio, in a Still window.", countdown: false) != "connect")
    return Fail($"The user didn't connect {app}. Don't ask again unless they bring it up.");
   if (!await ConnectPlugin(slug) || pluginAccounts.FirstOrDefault(a => a.Slug == slug) is not { } now) return Fail(app + " didn't get connected. Tell the user they can connect it in Skills & plugins.");
   account = now;
  }
  var arguments = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("args", out var given) && given.ValueKind == JsonValueKind.Object ? JsonNode.Parse(given.GetRawText()) : new JsonObject();
  if (!PluginReads(info, action, slug)) {
   string what = (Str(info, "name") is { Length: > 0 } name ? name : action) + " in " + app;
   string answer = await Approve(run, what, app, "plugin", PluginWhy(arguments as JsonObject), countdown: false);
   Audit(run.Chat, what, app, answer is "once" or "chat" or "always" ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no");
   PublishAiEverywhere();
   if (answer is not ("once" or "chat" or "always")) return Fail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't try it again unless they ask.");
  }
  var done = await Composio(HttpMethod.Post, "/tools/execute/" + Uri.EscapeDataString(action), new { user_id = PluginUser, connected_account_id = account.Id, arguments });
  if (done == null) return Fail("Composio isn't answering, so it didn't run. Tell the user.");
  if (done["successful"] is not JsonValue worked || !worked.TryGetValue<bool>(out var ok) || !ok) return Fail(app + ": " + ComposioError(done));
  string output = (done["data"] ?? new JsonObject()).ToJsonString();
  return Reply(output.Length > 40000 ? (object)(output[..40000] + "…") : JsonNode.Parse(output)!);
 }
}
