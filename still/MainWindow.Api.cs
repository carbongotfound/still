using System.IO;
using System.Net.Http;
using System.Text.Json;
namespace Still;

// API providers, in AI settings: add one (OpenAI- or Anthropic-compatible: name, base URL, key, models, prices, a monthly
// limit), check it with Test connection, and see what it costs per reply, per chat and per month. The key arrives from the
// shell once, as typed, and goes straight to ApiKeyStore; after that the shell only hears its last four characters.
// Signing in with a plan never needs any of this. The Mac's twin is ApiAgent.swift.
public partial class MainWindow
{
 static readonly Dictionary<string, string> apiKeyEnds = []; // provider id → the key's last four characters
 static readonly Dictionary<string, object> apiTests = [];   // provider id → its last Test connection, for the shell
 static string apiBusy = "", apiError = "";                  // a provider being tested or listed; the last form error
 static readonly HashSet<string> Jobs = ["chats", "titles", "setup", "test"];

 static object? Use(ApiUse? u) => u == null ? null : new { @in = u.In, @out = u.Out, cost = u.Cost, calls = u.Calls };
 static string KeyEndOf(string id) => apiKeyEnds.TryGetValue(id, out var end) ? end : apiKeyEnds[id] = ApiKeyStore.End(id);

 static object ApiPayload() => new {
  busy = apiBusy, error = apiError,
  providers = (sharedState?.Preferences.ApiProviders ?? []).Select(p => new {
   id = p.Id, kind = p.Kind, name = p.Name, url = p.Url, models = p.Models.Select(m => new { id = m.Id, efforts = m.Efforts }), priceIn = p.PriceIn, priceOut = p.PriceOut,
   limit = p.Limit, context = p.Context, noTools = p.NoTools, hasKey = ApiKeyStore.Has(p.Id), keyEnd = ApiKeyStore.Has(p.Id) ? KeyEndOf(p.Id) : "", refused = ApiKeyStore.Refused.Contains(p.Id),
   month = Use(p.Spent.GetValueOrDefault(ApiProvider.Month)), jobs = Jobs.Where(j => p.Spent.ContainsKey(ApiProvider.Month + "/" + j)).ToDictionary(j => j, j => Use(p.Spent[ApiProvider.Month + "/" + j])),
   noKey = p.NoKey, paused = p.Limit > 0 && p.Spent.GetValueOrDefault(ApiProvider.Month)?.Cost >= p.Limit, test = apiTests.GetValueOrDefault(p.Id) }) };

 /// An API call's tokens and cost, added to the provider's month and to the job it was for.
 void Spend(AgentAdapter cli, AgentEvent.Spent s)
 {
  if (cli is not ApiAdapter api) return;
  foreach (var key in new[] { ApiProvider.Month, ApiProvider.Month + "/" + (Jobs.Contains(s.Job) ? s.Job : "chats") }) {
   if (!api.Provider.Spent.TryGetValue(key, out var use)) api.Provider.Spent[key] = use = new();
   use.In += s.In; use.Out += s.Out; use.Cost += s.Cost; use.Calls++;
  }
  foreach (var old in api.Provider.Spent.Keys.Where(k => string.CompareOrdinal(k[..7], DateTime.Now.AddMonths(-12).ToString("yyyy-MM")) < 0).ToList()) api.Provider.Spent.Remove(old);
  SaveLater();
 }

 async Task HandleApi(string op, JsonElement data)
 {
  string S(string k) => data.ValueKind == JsonValueKind.Object && data.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
  bool B(string k) => data.ValueKind == JsonValueKind.Object && data.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.True;
  double D(string k) => data.ValueKind == JsonValueKind.Object && data.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number && v.GetDouble() is var d && d is >= 0 and < 1e7 ? d : 0;
  var providers = Prefs.ApiProviders;
  var p = providers.FirstOrDefault(x => x.Id == S("id"));
  apiError = "";
  switch (op) {
   case "apiSave": {
    string name = S("name").Trim(), url = S("url").Trim().TrimEnd('/'), key = S("key").Trim();
    if (name.Length is 0 or > 40) { apiError = "Give it a name, up to 40 characters."; break; }
    if (ApiRun.Address(url) == null) { apiError = "Use an address that starts with https:// (plain http only for localhost)."; break; }
    if (key.Length > 500 || key.Any(c => char.IsWhiteSpace(c) || char.IsControl(c))) { apiError = "That key has spaces or line breaks in it. Copy it again."; break; }
    if (p == null) providers.Add(p = new ApiProvider { Id = "api-" + Guid.NewGuid().ToString("N")[..8] });
    p.Kind = S("kind") == "anthropic" ? "anthropic" : "openai"; p.Name = name;
    if (p.Url != url) { p.Url = url; p.NoTools = false; apiTests.Remove(p.Id); }
    p.PriceIn = D("priceIn"); p.PriceOut = D("priceOut"); p.Limit = D("limit"); p.Context = (int)Math.Min(D("context"), 10_000_000);
    if (data.TryGetProperty("models", out var ms) && ms.ValueKind == JsonValueKind.Array) {
     var ids = ms.EnumerateArray().Select(m => m.ValueKind == JsonValueKind.String ? m.GetString()!.Trim() : "").Where(m => m.Length is > 0 and <= 120 && !m.Any(char.IsWhiteSpace) && !m.Contains('"')).Distinct().Take(300).ToList();
     p.Models = [.. ids.Select(id => p.Models.FirstOrDefault(m => m.Id == id) ?? new ApiModel { Id = id })];
    }
    if (key.Length > 0) { ApiKeyStore.Save(p.Id, key); apiKeyEnds.Remove(p.Id); p.NoKey = false; }
    else if (!ApiKeyStore.Has(p.Id)) p.NoKey = true; // no key, by choice: a local or open server
    aiClis = null; aiModels.Remove(p.Id); SaveLater();
    if (p.Models.Count == 0) await ListModels(p);
    await CheckAis(true);
    if (B("use")) UseAi(p.Id, false);                                  // setup: the AI it connects
    if (B("test") && p.Models.Count > 0) await TestApi(p, p.Models[0].Id); // setup's Test connection saves first
    break; }
   case "apiModels" when p != null: await ListModels(p); break;
   case "apiKeyRemove" when p != null:
    ApiKeyStore.Remove(p.Id); apiKeyEnds.Remove(p.Id); apiTests.Remove(p.Id); await CheckAis(true); break;
   case "apiDelete" when p != null && !runs.Values.Any(r => r.Chat.Harness == p.Id):
    ApiKeyStore.Remove(p.Id); apiKeyEnds.Remove(p.Id); apiTests.Remove(p.Id); providers.Remove(p);
    if (Prefs.AiHarness == p.Id) Prefs.AiHarness = "";
    foreach (var c in Companions.Where(c => c.Ai == p.Id)) c.Ai = "";
    aiClis = null; aiModels.Remove(p.Id); aiStatus.Remove(p.Id); SaveLater(); break;
   case "apiTest" when p != null:
    await TestApi(p, p.Models.Any(m => m.Id == S("model")) ? S("model") : p.Models.FirstOrDefault()?.Id ?? "");
    break;
  }
  PublishAiEverywhere();
 }

 /// Test connection: one tiny request to the provider, then each part's result for the shell.
 async Task TestApi(ApiProvider p, string model)
 {
  if (apiBusy.Length > 0) return;
  if ((ApiKeyStore.Read(p.Id) ?? (p.NoKey ? "" : null)) is not { } secret) { apiError = "Add a key first."; return; }
  if (model.Length == 0) { apiError = "Add a model first."; return; }
  apiBusy = p.Id; PublishAiEverywhere();
  try {
   using var limit = new CancellationTokenSource(TimeSpan.FromSeconds(90));
   var (checks, input, output) = await ApiRun.Test(p, secret, model, limit.Token);
   if (input + output > 0) Spend(ApiAdapter.Of(p), new AgentEvent.Spent(input, output, p.CostOf(input, output), "test"));
   if (checks.FirstOrDefault(c => c.Part == "Tools") is { Part: "Tools" } tools) p.NoTools = !tools.Ok;
   if (checks.FirstOrDefault(c => c.Part == "Effort") is { Part: "Effort" } effort && p.Models.FirstOrDefault(m => m.Id == model) is { } tested)
    tested.Efforts = effort.Ok ? ["low", "medium", "high"] : [];
   if (checks.Any(c => c.Part == "Key" && !c.Ok)) ApiKeyStore.Refused.Add(p.Id); else if (checks.Any(c => c.Part == "Key" && c.Ok)) ApiKeyStore.Refused.Remove(p.Id);
   apiTests[p.Id] = new { model, at = DateTime.UtcNow, checks = checks.Select(c => new { part = c.Part, ok = c.Ok, text = c.Text }) };
  } catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or TimeoutException or IOException or InvalidOperationException) {
   apiTests[p.Id] = new { model, at = DateTime.UtcNow, checks = new[] { new { part = "Address", ok = false, text = "No answer in time. Check the base URL." } } };
  } finally { apiBusy = ""; }
  aiClis = null; aiModels.Remove(p.Id); SaveLater(); await CheckAis(true);
 }

 /// Fills a provider's models from its own list, where it offers one; otherwise the user types them.
 async Task ListModels(ApiProvider p)
 {
  if ((ApiKeyStore.Read(p.Id) ?? (p.NoKey ? "" : null)) is not { } key || apiBusy.Length > 0) return;
  apiBusy = p.Id; PublishAiEverywhere();
  try {
   using var limit = new CancellationTokenSource(TimeSpan.FromSeconds(30));
   var ids = await ApiRun.List(p, key, limit.Token);
   if (ids.Count > 0) { p.Models = [.. ids.Select(id => p.Models.FirstOrDefault(m => m.Id == id) ?? new ApiModel { Id = id })]; aiModels.Remove(p.Id); SaveLater(); }
   else if (p.Models.Count == 0) apiError = $"{p.Name} didn't list its models. Type the ones you want.";
  } catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or TimeoutException or IOException) { apiError = $"Couldn't get {p.Name}'s models. Type the ones you want."; }
  finally { apiBusy = ""; }
 }
}
