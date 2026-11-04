// web_search and read_url: the AI looks things up without a tab (ported from MainWindow.Lookup.cs). Each lookup loads in
// one hidden page (the user's own website data, never a tab, no pop-ups or sound), one at a time. It closes after a
// minute unused, so it costs nothing at rest.
import AppKit
import WebKit

// The scripts come straight from the Windows app (mac/build.sh copies them), so both stay in step.
let lookupScripts = (results: (try? String(contentsOf: resources.appendingPathComponent("lookup-Results.js"), encoding: .utf8)) ?? "",
                     readable: (try? String(contentsOf: resources.appendingPathComponent("lookup-Readable.js"), encoding: .utf8)) ?? "")

/// Like .NET's Uri.EscapeDataString: everything but letters, digits and -._~ is percent-encoded.
func escapeData(_ text: String) -> String {
 text.addingPercentEncoding(withAllowedCharacters: CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")) ?? text
}

/// The hidden page lookups load in, and the queue that keeps them one at a time.
enum Lookup {
 static var view: WKWebView?
 static var idle: Timer?
 static var busy = false
 static var waiting: [CheckedContinuation<Void, Never>] = []
 static let helper = LookupDelegate()

 @MainActor static func enter() async {
  if !busy { busy = true; return }
  await withCheckedContinuation { waiting.append($0) }
 }
 static func leave() { if waiting.isEmpty { busy = false } else { waiting.removeFirst().resume() } }
}

/// Says when the lookup page has loaded. Dialogs are accepted, pop-ups never open and nothing downloads.
final class LookupDelegate: NSObject, WKNavigationDelegate, WKUIDelegate {
 var loaded: ((Bool) -> Void)?
 func webView(_ view: WKWebView, didFinish navigation: WKNavigation!) { loaded?(true) }
 func webView(_ view: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { failed(error) }
 func webView(_ view: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { failed(error) }
 func failed(_ error: Error) { if (error as NSError).code != NSURLErrorCancelled { loaded?(false) } } // cancelled: a newer navigation took over
 func webView(_ view: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
  decisionHandler(response.canShowMIMEType ? .allow : .cancel)
 }
 func webView(_ view: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) { completionHandler() }
 func webView(_ view: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) { completionHandler(true) }
 func webView(_ view: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) { completionHandler(defaultText ?? "") }
}

extension Browser {
 func searchUrl(_ q: String) -> String {
  var engine = ["Google": "https://www.google.com/search?q=", "Bing": "https://www.bing.com/search?q="][pref("SearchEngine", "Google")] ?? "https://html.duckduckgo.com/html/?q="
  if isQa, let qa = ProcessInfo.processInfo.environment["STILL_QA_SEARCH"], !qa.isEmpty { engine = qa } // tests search a local page
  return engine + escapeData(q)
 }

 /// store: an incognito chat's window's private website data, in a page used once; otherwise the shared hidden page.
 @MainActor func lookUp(_ url: String, _ script: String, _ args: [String: Any], store: WKWebsiteDataStore? = nil) async throws -> Any? {
  await Lookup.enter()
  defer {
   Lookup.idle = Timer.scheduledTimer(withTimeInterval: 60, repeats: false) { _ in Lookup.view?.stopLoading(); Lookup.view = nil }
   Lookup.leave()
  }
  Lookup.idle?.invalidate()
  let view = (store == nil ? Lookup.view : nil) ?? {
   let config = WKWebViewConfiguration()
   config.websiteDataStore = store ?? pageStore // the profile's own website data, as in its tabs (never a private tab's)
   config.mediaTypesRequiringUserActionForPlayback = .all // never a sound
   config.applicationNameForUserAgent = "Version/17.4 Safari/605.1.15"
   config.preferences.isFraudulentWebsiteWarningEnabled = true
   let created = WKWebView(frame: NSRect(x: 0, y: 0, width: 1280, height: 900), configuration: config)
   created.navigationDelegate = Lookup.helper
   created.uiDelegate = Lookup.helper
   self.applyBlocking(created)
   if store == nil { Lookup.view = created }
   return created
  }()
  guard let address = URL(string: url) else { throw AgentError("The page didn't load.") }
  view.stopLoading()
  let loaded: Bool? = await withCheckedContinuation { done in
   let once = Once<Bool?>()
   once.action = { done.resume(returning: $0) }
   Lookup.helper.loaded = { once.fire($0) }
   view.load(URLRequest(url: address))
   DispatchQueue.main.asyncAfter(deadline: .now() + 20) { once.fire(nil) }
  }
  Lookup.helper.loaded = nil
  guard let loaded else { throw AgentError("The page took too long to load.") }
  if !loaded { throw AgentError("The page didn't load.") }
  try? await Task.sleep(nanoseconds: 350_000_000) // pages that draw their text with script
  return try await agentJs(view, script, args)
 }

 /// Where an AI's lookups load: an incognito chat's in its window's private website data.
 func lookupStore(_ who: String) throws -> WKWebsiteDataStore? {
  guard let run = runs[who], run.chat.ephemeral else { return onCompanion(who) ? companionStore : nil }
  guard let owner = ownerOf(run.chat) else { throw AgentError("The incognito window closed.") }
  return owner.privateStore
 }

 @MainActor func webSearch(_ who: String, _ args: [String: Any]) async throws -> String {
  let store = try lookupStore(who)
  let q = argText(args, "query").trimmingCharacters(in: .whitespacesAndNewlines)
  if q.isEmpty { return agentFail("Pass what to search for.") }
  let count = Int(min(10, max(1, argNumber(args, "count", 8))))
  var found = try await lookUp(searchUrl(q), lookupScripts.results, ["count": count], store: store) as? [Any] ?? []
  if found.isEmpty && pref("SearchEngine", "Google") != "DuckDuckGo" { // a consent page or a challenge
   found = try await lookUp("https://html.duckduckgo.com/html/?q=" + escapeData(q), lookupScripts.results, ["count": count], store: store) as? [Any] ?? []
  }
  did(who, "Searched “" + clipped(q, 60) + "”")
  if let run = runs[who] { run.chat.messages.append(AiMessage("search", jsonText(["q": q, "results": found]))); publishAiEverywhere() }
  return found.isEmpty ? agentFail("No results. Try other words, or open_tab the search to see the page.") : agentOk(["results": found])
 }

 @MainActor func readUrl(_ who: String, _ args: [String: Any]) async throws -> String {
  let url = try agentWebUrl(argText(args, "url"))
  let page = try await lookUp(url, lookupScripts.readable, ["offset": Int(min(1e9, max(0, argNumber(args, "offset", 0))))], store: try lookupStore(who)) as? [String: Any] ?? [:]
  let at = (page["url"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? url
  did(who, "Read " + hostName(at))
  if let run = runs[who] { run.chat.messages.append(AiMessage("read", jsonText(["url": at, "title": page["title"] as? String ?? ""]))); publishAiEverywhere() }
  return agentOk(page)
 }
}
