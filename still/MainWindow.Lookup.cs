using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
namespace Still;

// web_search and read_url: the AI looks things up without a tab. Each lookup loads in one hidden page (the same
// profile, never a tab, no pop-ups or sound), one at a time. It closes after a minute unused, so it costs nothing at rest.
// An incognito chat's lookups use a second one in the private engine profile, so they never touch the regular one.
public partial class MainWindow
{
 static readonly SemaphoreSlim lookupGate = new(1, 1);
 WebView2? lookupView, privateLookupView, companionLookupView, signedOutLookupView;
 DispatcherTimer? lookupIdle;

 string SearchUrl(string q) => (App.IsQa && Environment.GetEnvironmentVariable("STILL_QA_SEARCH") is { Length: > 0 } qa ? qa : Prefs.SearchEngine switch { // tests search a local page
  "Google" => "https://www.google.com/search?q=", "Bing" => "https://www.bing.com/search?q=", _ => "https://html.duckduckgo.com/html/?q=" }) + Uri.EscapeDataString(q);

 /// signedOut: a page that holds no sign-ins at all. hop: looks at each address it's sent to, and says why not.
 async Task<JsonElement> LookUp(string url, string script, object args, bool priv = false, bool companion = false, bool signedOut = false, Func<string, string?>? hop = null)
 {
  await lookupGate.WaitAsync();
  try {
   lookupIdle?.Stop();
   var view = signedOut ? signedOutLookupView : priv ? privateLookupView : companion ? companionLookupView : lookupView;
   if (view?.CoreWebView2 == null) {
    view = new WebView2 { Visibility = Visibility.Hidden }; WebHost.Children.Add(view);
    if (signedOut) signedOutLookupView = view; else if (priv) privateLookupView = view; else if (companion) companionLookupView = view; else lookupView = view;
    var env = await App.BrowserEnvironment; var options = env.CreateCoreWebView2ControllerOptions();
    options.ProfileName = signedOut ? "StillSignedOut" : priv ? privateProfile : companion ? CompanionEngine : "Default"; options.IsInPrivateModeEnabled = priv || signedOut;
    await view.EnsureCoreWebView2Async(env, options);
    var c = view.CoreWebView2; ApplyProtection(c);
    c.IsMuted = true; c.Settings.AreDefaultScriptDialogsEnabled = false;
    c.NewWindowRequested += (_, e) => e.Handled = true;
    c.ScriptDialogOpening += (_, e) => e.Accept();
    c.DownloadStarting += (_, e) => e.Cancel = true;
   }
   var core = view.CoreWebView2;
   if (signedOut) core.CookieManager.DeleteAllCookies(); // nothing from the last read either
   // Only the latest navigation counts: an earlier one cut off by this one, or this one replaced by the page's own
   // reload (Google reloads itself on a first visit), finishes as aborted and isn't this page's result. A reload that
   // fails after the page loaded (one answered with no content) leaves the loaded page showing.
   ulong latest = 0; bool? ok = null; bool shown = false, committed = false; string? refused = null;
   void NoApps(object? s, CoreWebView2LaunchingExternalUriSchemeEventArgs e) => e.Cancel = true; // nobody's looking at this page, so nothing it asks for opens an app
   void Started(object? s, CoreWebView2NavigationStartingEventArgs e)
   {
    latest = e.NavigationId; ok = null; committed = false;
    if (hop?.Invoke(e.Uri) is { } no) { e.Cancel = true; refused = no; ok = false; }
   }
   // Cancel above doesn't hold back the request a redirect makes: the other site would still get its visit. This does. Until the
   // page commits, a document request can only be that page's own; after, it's one of its frames, which aren't what this looks at.
   void Asked(object? s, CoreWebView2WebResourceRequestedEventArgs e)
   {
    if (committed || hop?.Invoke(e.Request.Uri) is not { } no) return;
    e.Response = core.Environment.CreateWebResourceResponse(new MemoryStream([]), 403, "Forbidden", "Content-Type: text/plain");
    refused = no; ok = false;
   }
   void Committed(object? s, CoreWebView2ContentLoadingEventArgs e) => committed = true;
   void Done(object? s, CoreWebView2NavigationCompletedEventArgs e) { if (e.NavigationId != latest) return; shown |= e.IsSuccess; ok = shown; }
   core.LaunchingExternalUriScheme += NoApps;
   core.NavigationStarting += Started; core.NavigationCompleted += Done; core.ContentLoading += Committed;
   if (hop != null) { core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.Document, CoreWebView2WebResourceRequestSourceKinds.All); core.WebResourceRequested += Asked; }
   try {
    core.Navigate(url);
    var until = DateTime.UtcNow.AddSeconds(20);
    for (ulong seen = ~0UL; seen != latest && refused == null && DateTime.UtcNow < until;) { // done once nothing new started during the pause
     while (ok == null) { if (DateTime.UtcNow > until) throw new InvalidOperationException("The page took too long to load."); await Task.Delay(50); }
     seen = latest; await Task.Delay(350); // pages that draw their text with script
    }
    if (refused != null) throw new InvalidOperationException(refused);
    if (ok != true) throw new InvalidOperationException("The page didn't load.");
   } finally {
    core.LaunchingExternalUriScheme -= NoApps;
    core.NavigationStarting -= Started; core.NavigationCompleted -= Done; core.ContentLoading -= Committed;
    if (hop != null) { core.WebResourceRequested -= Asked; core.RemoveWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.Document, CoreWebView2WebResourceRequestSourceKinds.All); }
   }
   return await Js(core, script, args);
  } finally {
   lookupGate.Release();
   lookupIdle ??= new DispatcherTimer(TimeSpan.FromSeconds(60), DispatcherPriority.Background, (_, _) => { lookupIdle!.Stop(); foreach (var v in new[] { lookupView, privateLookupView, companionLookupView, signedOutLookupView }.OfType<WebView2>()) { WebHost.Children.Remove(v); v.Dispose(); } lookupView = privateLookupView = companionLookupView = signedOutLookupView = null; }, Dispatcher);
   lookupIdle.Start();
  }
 }

 async Task<string> WebSearch(string who, JsonElement args)
 {
  string q = S(args, "query").Trim();
  if (q.Length == 0) return Fail("Pass what to search for.");
  int count = (int)Math.Clamp(N(args, "count", 8), 1, 10);
  var found = await LookUp(SearchUrl(q), ResultsJs, new { count }, Incognito(who), OnCompanion(who));
  if (found.GetArrayLength() == 0 && Prefs.SearchEngine != "DuckDuckGo") found = await LookUp("https://html.duckduckgo.com/html/?q=" + Uri.EscapeDataString(q), ResultsJs, new { count }, Incognito(who), OnCompanion(who)); // a consent page or a challenge
  Did(who, "Searched “" + Clip(q, 60) + "”");
  if (runs.GetValueOrDefault(who) is { } run) { run.Chat.Messages.Add(new() { Role = "search", Text = JsonSerializer.Serialize(new { q, results = found }) }); PublishAiEverywhere(); }
  return found.GetArrayLength() == 0 ? Fail("No results. Try other words, or open_tab the search to see the page.") : Reply(new { results = found });
 }

 async Task<string> ReadUrl(string who, JsonElement args, AgentStep step)
 {
  string url = WebUrl(S(args, "url"), Prefs.SearchEngine), first = Host(url);
  var chat = runs.GetValueOrDefault(who)?.Chat;
  var up = chat == null ? default : ExchangeOf(chat);
  // Signed out, unless the user named the site, the chat has used it or they said yes to it. An incognito chat's page is private already.
  step.SignedOut = chat != null && !chat.Ephemeral && !step.Allowed && !BeenTo(up.Root, first) && !up.Chain.All(c => SiteAllows(c, first, "read"));
  // A redirect, or the page's own script, may send it somewhere the gate never looked at.
  string? Hop(string to)
  {
   if (!Uri.TryCreate(to, UriKind.Absolute, out var u) || u.Scheme is not ("http" or "https")) return null;
   string host = Host(to);
   if (host == first || chat != null && BeenTo(up.Root, host)) return null;
   bool ruled = chat != null ? Delegation.Strictest(up.Chain.Select(c => PermissionMode(c, host, "read") ?? DefaultPermission("read"))) != "always" : PermissionMode("", host, "read") is not (null or "always");
   return PrivateName(host) || ruled || chat != null && !step.SignedOut ? $"That page sent Still to {host}, so it stopped there. Read {host} directly if you need it." : null;
  }
  var page = await LookUp(url, ReadableJs, new { offset = (int)Math.Max(0, N(args, "offset", 0)), signedOut = step.SignedOut }, Incognito(who), OnCompanion(who), step.SignedOut, Hop);
  string at = Str(page, "url") is { Length: > 0 } u ? u : url;
  Did(who, "Read " + Host(at));
  if (runs.GetValueOrDefault(who) is { } run) { run.Chat.Messages.Add(new() { Role = "read", Text = JsonSerializer.Serialize(new { url = at, title = Str(page, "title") }) }); PublishAiEverywhere(); }
  return Reply(page);
 }

 // Each engine's result list, with their redirect links undone. Anything pointing back at the engine itself is left out.
 const string ResultsJs = """
  const out = [], seen = new Set(), engines = /(^|\.)(google|bing|duckduckgo)\.[a-z.]+$/;
  const add = (a, snip) => {
   if (!a?.href || out.length >= o.count) return;
   let url = a.href;
   try {
    const p = new URL(url);
    if (p.searchParams.get('uddg')) url = p.searchParams.get('uddg');
    else if (p.pathname === '/url' && p.searchParams.get('q')) url = p.searchParams.get('q');
    else if (p.pathname.startsWith('/ck/') && p.searchParams.get('u')?.startsWith('a1')) url = atob(p.searchParams.get('u').slice(2).replace(/-/g, '+').replace(/_/g, '/'));
    if (!/^https?:/.test(url) || engines.test(new URL(url).hostname) || seen.has(url)) return;
   } catch { return; }
   seen.add(url);
   out.push({ title: (a.innerText || a.textContent || '').trim().split('\n')[0].slice(0, 160), url, snippet: (snip || '').replace(/\s+/g, ' ').trim().slice(0, 300) });
  };
  document.querySelectorAll('.result, .web-result').forEach(r => add(r.querySelector('a.result__a'), r.querySelector('.result__snippet')?.innerText));
  document.querySelectorAll('li.b_algo').forEach(r => add(r.querySelector('h2 a'), r.querySelector('.b_caption p, [class*=b_lineclamp]')?.innerText));
  document.querySelectorAll('#search a h3, #rso a h3').forEach(h => { const a = h.closest('a'), box = a.closest('[data-hveid]')?.parentElement?.closest('[data-hveid]') || a.closest('[data-hveid]'); add(a, box && [...box.querySelectorAll('[data-sncf], .VwiC3b, [style*=line-clamp]')].map(e => e.innerText).join(' ')); });
  return out;
 """;
 // The page's main text: menus, headers, footers and asides left out.
 const string ReadableJs = """
  document.querySelectorAll('script,style,noscript,template,svg,iframe,nav,header,footer,aside,dialog,[role=navigation],[role=banner],[role=contentinfo],[aria-hidden=true]').forEach(e => e.remove());
  const main = document.querySelector('article') || document.querySelector('main,[role=main]');
  const pick = main && main.innerText.trim().length > 400 ? main : document.body;
  const text = (pick?.innerText || '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  return { title: document.title, url: location.href, text: text.slice(o.offset, o.offset + 12000), offset: o.offset, total: text.length, more: o.offset + 12000 < text.length, ...(o.signedOut ? { signedOut: true } : {}) };
 """;
}
