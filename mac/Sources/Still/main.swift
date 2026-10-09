// Still for Mac: a native AppKit + WebKit host for the same React interface the Windows app uses.
// The interface talks to its host through window.chrome.webview, which the bridge below provides on WebKit.
import AppKit
import SQLite3
import WebKit

let resources = Bundle.main.resourceURL!
let support: URL = {
 let url = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Still")
 try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
 return url
}()
let unavailable = "That isn't available in Still for Mac yet."

let bridge = """
(() => {
 const listeners = new Set();
 window.chrome = { webview: {
  postMessage: message => webkit.messageHandlers.still.postMessage(JSON.stringify(message)),
  addEventListener: (name, listener) => { if (name === "message") listeners.add(listener) },
  removeEventListener: (name, listener) => listeners.delete(listener)
 } };
 window.__stillReceive = data => { for (const listener of listeners) listener({ data }) };
})();
"""

/// Serves the bundled interface from still://app/ (module scripts don't load from file:// in WebKit).
final class ShellScheme: NSObject, WKURLSchemeHandler {
 let root: URL
 init(root: URL) { self.root = root.standardizedFileURL }
 func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
  guard let url = task.request.url else { return }
  let path = url.path.isEmpty || url.path == "/" ? "index.html" : String(url.path.dropFirst())
  let file = root.appendingPathComponent(path).standardizedFileURL
  guard file.path.hasPrefix(root.path), var data = try? Data(contentsOf: file) else { task.didFailWithError(URLError(.fileDoesNotExist)); return }
  if file.lastPathComponent == "index.html", let html = String(data: data, encoding: .utf8) {
   data = Data(html.replacingOccurrences(of: "'self'", with: "'self' still:").utf8)
  }
  let types = ["html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8", "svg": "image/svg+xml", "png": "image/png", "woff2": "font/woff2", "woff": "font/woff", "json": "application/json"]
  let headers = ["Content-Type": types[file.pathExtension.lowercased()] ?? "application/octet-stream", "Access-Control-Allow-Origin": "*"]
  task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)!)
  task.didReceive(data)
  task.didFinish()
 }
 func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

final class FlippedView: NSView { override var isFlipped: Bool { true } }

final class Tab: NSObject {
 var id = UUID().uuidString
 var title = "New tab", url = "", pinned = false, isPrivate = false, loading = false, muted = false
 var lastSeen = Date()
 var view: WKWebView?
 var observers: [NSKeyValueObservation] = []
}

final class Download {
 let task: WKDownload
 var path: URL?
 var status = "InProgress"
 var observer: NSKeyValueObservation?
 init(task: WKDownload) { self.task = task }
}

final class Browser: NSObject, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
 let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
 let root = FlippedView()
 var shell: WKWebView!
 var tabs: [Tab] = []
 var active: Tab?
 var prefs: [String: Any] = [:]
 var history: [[String: Any]] = [], bookmarks: [[String: Any]] = []
 var downloads: [Download] = []
 var closed: [String] = []
 var welcome = true, ready = false, focusMode = false, overlay = false
 var panel = ""
 var pageFrame = NSRect.zero
 var rules: WKContentRuleList?
 let youTube = (try? String(contentsOf: resources.appendingPathComponent("youtube.js"))) ?? ""
 var publishQueued = false, saveQueued = false, overlayVersion = 0
 var appearanceObserver: NSKeyValueObservation?
 var pendingImport: (id: String, name: String, bookmarks: [[String: Any]], history: [[String: Any]])?
 var importBusy = false, importError = "", importDone = ""

 func pref<T>(_ key: String, _ fallback: T) -> T { prefs[key] as? T ?? fallback }
 var unblocked: [String] { pref("UnblockedHosts", [String]()) }
 var downloadFolder: URL { URL(fileURLWithPath: pref("DownloadFolder", FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0].path)) }
 var stateFile: URL { support.appendingPathComponent("state.json") }
 var dark: Bool { window.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua }

 override init() {
  super.init()
  window.titleVisibility = .hidden
  window.titlebarAppearsTransparent = true
  for button in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] { window.standardWindowButton(button)?.isHidden = true }
  window.backgroundColor = .black
  window.minSize = NSSize(width: 640, height: 420)
  window.isReleasedWhenClosed = false
  window.delegate = self
  if !window.setFrameUsingName("StillMain") { window.center() }
  window.setFrameAutosaveName("StillMain")
  window.contentView = root

  let config = WKWebViewConfiguration()
  config.setURLSchemeHandler(ShellScheme(root: resources.appendingPathComponent("Shell")), forURLScheme: "still")
  config.userContentController.add(self, name: "still")
  config.userContentController.addUserScript(WKUserScript(source: bridge, injectionTime: .atDocumentStart, forMainFrameOnly: true))
  shell = WKWebView(frame: root.bounds, configuration: config)
  shell.autoresizingMask = [.width, .height]
  shell.navigationDelegate = self
  root.addSubview(shell)
  shell.load(URLRequest(url: URL(string: "still://app/index.html")!))

  load()
  applyTheme()
  appearanceObserver = NSApp.observe(\.effectiveAppearance) { [weak self] _, _ in DispatchQueue.main.async { self?.schedulePublish() } }
  compileRules()
  Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.sleepIdleTabs() }
  window.makeKeyAndOrderFront(nil)
 }

 // MARK: State

 func load() {
  var saved: [String: Any] = [:]
  if let data = try? Data(contentsOf: stateFile), let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { saved = json }
  prefs = saved["Preferences"] as? [String: Any] ?? [:]
  history = saved["History"] as? [[String: Any]] ?? []
  bookmarks = saved["Bookmarks"] as? [[String: Any]] ?? []
  welcome = saved["Welcome"] as? Bool ?? true
  if pref("RestoreTabs", true) {
   for item in saved["Tabs"] as? [[String: Any]] ?? [] {
    let tab = Tab()
    tab.id = item["Id"] as? String ?? tab.id
    tab.title = item["Title"] as? String ?? "New tab"
    tab.url = item["Url"] as? String ?? ""
    tab.pinned = item["Pinned"] as? Bool ?? false
    tabs.append(tab)
   }
  }
  if tabs.isEmpty { tabs.append(Tab()) }
  select(tabs.first { $0.id == saved["ActiveId"] as? String } ?? tabs[0])
 }

 func save() {
  let state: [String: Any] = [
   "Preferences": prefs, "History": history, "Bookmarks": bookmarks, "Welcome": welcome, "ActiveId": active?.id ?? "",
   "Tabs": tabs.filter { !$0.isPrivate }.map { ["Id": $0.id, "Title": $0.title, "Url": $0.url, "Pinned": $0.pinned] }
  ]
  guard JSONSerialization.isValidJSONObject(state), let data = try? JSONSerialization.data(withJSONObject: state, options: .prettyPrinted) else { return }
  try? data.write(to: stateFile, options: .atomic)
 }

 func saveLater() {
  if saveQueued { return }
  saveQueued = true
  DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.saveQueued = false; self.save() }
 }

 // MARK: Talking to the interface

 func send(_ message: [String: Any]) {
  guard ready, JSONSerialization.isValidJSONObject(message), let data = try? JSONSerialization.data(withJSONObject: message), let json = String(data: data, encoding: .utf8) else { return }
  shell.evaluateJavaScript("window.__stillReceive(\(json))", completionHandler: nil)
 }

 func toast(_ text: String) { send(["kind": "toast", "message": text]) }

 func schedulePublish() {
  if publishQueued { return }
  publishQueued = true
  DispatchQueue.main.async { self.publishQueued = false; self.publish() }
 }

 func publish() {
  guard ready else { return }
  let host = active?.view?.url?.host ?? ""
  let preferences: [String: Any] = [
   "theme": pref("Theme", "Dark"), "layout": pref("Layout", "Sidebar"), "search": pref("SearchEngine", "Google"),
   "restore": pref("RestoreTabs", true), "blocking": pref("Blocking", true), "downloads": downloadFolder.path,
   "sidebarWidth": pref("SidebarWidth", 240.0), "tracking": "Balanced", "memory": pref("MemorySaver", true), "autofill": false,
   "startup": false, "startupDisabled": true, "tearOff": false, "agents": false
  ]
  let tabList: [[String: Any]] = tabs.map { tab in [
   "id": tab.id, "title": tab.title, "url": tab.url, "pinned": tab.pinned, "isPrivate": tab.isPrivate, "loading": tab.loading,
   "sleeping": tab.view == nil && !tab.url.isEmpty, "blocked": 0, "muted": tab.muted, "secure": tab.url.hasPrefix("https://"), "certificateError": false
  ] }
  let source = active?.isPrivate == true && panel == "address" ? [] : history
  let visits: [[String: Any]] = source.prefix(panel == "history" || panel == "address" ? 2000 : 100).map { visit in
   ["title": visit["Title"] as? String ?? "", "url": visit["Url"] as? String ?? "", "at": visit["At"] as? String ?? ""]
  }
  let marks: [[String: Any]] = bookmarks.map { ["title": $0["Title"] as? String ?? "", "url": $0["Url"] as? String ?? ""] }
  var files: [[String: Any]] = []
  for (index, item) in downloads.enumerated() {
   files.append(["id": String(index), "name": item.path?.lastPathComponent ?? "Download", "status": item.status,
                 "bytes": item.task.progress.completedUnitCount, "total": max(0, item.task.progress.totalUnitCount)])
  }
  var state: [String: Any] = ["kind": "state", "activeId": active?.id ?? "", "dark": dark, "focusMode": focusMode, "fullScreen": false]
  state["appFullScreen"] = window.styleMask.contains(.fullScreen)
  state["maximized"] = window.isZoomed
  state["panel"] = panel
  state["profileName"] = "Default"
  state["windows"] = [[String: Any]]()
  state["secondary"] = false
  state["noExtensions"] = true
  state["incognito"] = false
  state["welcome"] = welcome
  state["version"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
  state["zoom"] = Double(active?.view?.pageZoom ?? 1)
  state["preferences"] = preferences
  state["tabs"] = tabList
  state["history"] = visits
  state["bookmarks"] = marks
  state["downloads"] = files
  state["canBack"] = active?.view?.canGoBack ?? false
  state["canForward"] = active?.view?.canGoForward ?? false
  state["siteBlocking"] = pref("Blocking", true) && !unblocked.contains(host)
  send(state)
 }

 func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
  guard message.webView === shell, let text = message.body as? String, text.utf8.count <= 65536,
        let data = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any], let op = data["op"] as? String else { return }
  handle(op, data)
  if op != "bounds" && op != "overlay" { schedulePublish() }
 }

 func handle(_ op: String, _ data: [String: Any]) {
  func text(_ key: String) -> String { data[key] as? String ?? "" }
  func number(_ key: String) -> Double { (data[key] as? NSNumber)?.doubleValue ?? 0 }
  let target = tabs.first { $0.id == text("id") } ?? active
  switch op {
  case "ready": ready = true
  case "bounds":
   let ratio = number("viewportWidth") > 0 ? shell.bounds.width / number("viewportWidth") : 1
   pageFrame = NSRect(x: number("x") * ratio, y: number("y") * ratio, width: max(1, number("width") * ratio), height: max(1, number("height") * ratio))
   layoutPages()
  case "overlay": setOverlay(data["value"] as? Bool ?? false)
  case "openPanel": openPanel(text("name"), text("value"))
  case "panel": panel = text("name")
  case "sidebarResize": prefs["SidebarWidth"] = min(360, max(190, number("width"))); saveLater()
  case "navigate": navigate(text("url"))
  case "new": newTab(text("url"), isPrivate: data["private"] as? Bool ?? false)
  case "incognitoWindow": newTab(isPrivate: true)
  case "select": if let target { select(target) }
  case "closeTab": if let target { close(target) }
  case "pin": target?.pinned.toggle(); saveLater()
  case "duplicate": if let target { newTab(target.url, isPrivate: target.isPrivate) }
  case "sleep": if let target { unload(target); if target === active { newTab() } }
  case "mute": if let target { target.muted.toggle(); target.view?.evaluateJavaScript("document.querySelectorAll('video,audio').forEach(m=>m.muted=\(target.muted))") }
  case "reorder":
   if let from = tabs.firstIndex(where: { $0.id == text("id") }), let before = tabs.first(where: { $0.id == text("before") }), tabs[from] !== before {
    let moved = tabs.remove(at: from)
    tabs.insert(moved, at: tabs.firstIndex { $0 === before }!)
    saveLater()
   }
  case "back": active?.view?.goBack()
  case "forward": active?.view?.goForward()
  case "reload": active?.view?.reload()
  case "zoom": if let view = active?.view { view.pageZoom = number("amount") == 0 ? 1 : min(3, max(0.3, view.pageZoom + number("amount"))) }
  case "find": if let view = active?.view, !text("text").isEmpty { view.find(text("text"), configuration: WKFindConfiguration()) { _ in } }
  case "bookmark": toggleBookmark()
  case "removeBookmark": bookmarks.removeAll { $0["Url"] as? String == text("url") }; saveLater()
  case "bookmarkMove":
   if let i = bookmarks.firstIndex(where: { $0["Url"] as? String == text("url") }) {
    let j = i + Int(number("delta")).signum()
    if j >= 0 && j < bookmarks.count && j != i { bookmarks.swapAt(i, j); saveLater() }
   }
  case "removeHistory": history.removeAll { $0["Url"] as? String == text("url") }; saveLater()
  case "clearHistory": history.removeAll(); save(); toast("History cleared.")
  case "clearCookies":
   WKWebsiteDataStore.default().removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) { self.toast("Cookies and website data cleared.") }
  case "siteBlocking":
   if let view = active?.view, let host = view.url?.host {
    var list = unblocked
    if let index = list.firstIndex(of: host) { list.remove(at: index) } else { list.append(host) }
    prefs["UnblockedHosts"] = list; saveLater()
    applyBlocking(view); view.reload()
   }
  case "preference": setPreference(text("key"), text("value"))
  case "welcomeDone": welcome = false; saveLater()
  case "defaultBrowser": makeDefault()
  case "chooseDownloads":
   let picker = NSOpenPanel()
   picker.canChooseDirectories = true; picker.canChooseFiles = false; picker.directoryURL = downloadFolder
   picker.beginSheetModal(for: window) { result in
    if result == .OK, let url = picker.url { self.prefs["DownloadFolder"] = url.path; self.saveLater(); self.schedulePublish() }
   }
  case "downloadsFolder": NSWorkspace.shared.open(downloadFolder)
  case "showDownload": if let path = download(text("id"))?.path { NSWorkspace.shared.activateFileViewerSelecting([path]) }
  case "openDownload": if let item = download(text("id")), item.status == "Completed", let path = item.path { NSWorkspace.shared.open(path) }
  case "cancelDownload": download(text("id"))?.task.cancel { _ in }
  case "reopen": reopen()
  case "focus": focusMode.toggle()
  case "drag": dragWindow()
  case "copyText":
   let value = text("text")
   if !value.isEmpty && value.count <= 8192 { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(value, forType: .string) }
  case "fullscreen": window.toggleFullScreen(nil)
  case "exitFullscreen": if window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) }
  case "maximize": if window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) } else { window.zoom(nil) }
  case "minimize": window.miniaturize(nil)
  case "closeWindow": window.close()
  case "externalReview": if let source = importSources().first(where: { $0.id == text("id") }) { reviewImport(source.name, source.folder) }
  case "externalChoose":
   let picker = NSOpenPanel()
   picker.canChooseDirectories = true; picker.canChooseFiles = false
   picker.message = "Choose a browser profile folder, such as Chrome's Default folder or ~/Library/Safari."
   picker.beginSheetModal(for: window) { result in if result == .OK, let url = picker.url { self.reviewImport(url.lastPathComponent, url) } }
  case "externalCancel": if !importBusy { pendingImport = nil; importError = ""; publishImport() }
  case "externalConfirm": finishImport(bookmarks: data["bookmarks"] as? Bool ?? false, history: data["history"] as? Bool ?? false)
  case "checkUpdate", "openUpdate", "releaseNotes": newTab("https://github.com/carbongotfound/still/releases/latest")
  default: toast(unavailable)
  }
 }

 func setPreference(_ key: String, _ value: String) {
  switch key {
  case "theme": if ["Light", "Dark", "System"].contains(value) { prefs["Theme"] = value; applyTheme() }
  case "layout": if ["Sidebar", "Top"].contains(value) { prefs["Layout"] = value }
  case "search": if ["DuckDuckGo", "Google", "Bing"].contains(value) { prefs["SearchEngine"] = value }
  case "restore": prefs["RestoreTabs"] = value == "true"
  case "blocking": prefs["Blocking"] = value == "true"; for tab in tabs { if let view = tab.view { applyBlocking(view) } }
  case "memory": prefs["MemorySaver"] = value == "true"
  default: toast(unavailable)
  }
  saveLater()
 }

 func applyTheme() {
  switch pref("Theme", "Dark") {
  case "Light": window.appearance = NSAppearance(named: .aqua)
  case "System": window.appearance = nil
  default: window.appearance = NSAppearance(named: .darkAqua)
  }
  window.backgroundColor = dark ? .black : .white
 }

 // MARK: Panels and page placement

 func openPanel(_ name: String, _ value: String) {
  if ["passwords", "extensions", "cookies", "security", "profiles"].contains(name) { toast(unavailable); return }
  if name == "import" { importDone = ""; publishImport() }
  panel = name
  if name != "find" { setOverlay(true) }
  send(["kind": "panel", "name": name, "value": value])
  window.makeFirstResponder(shell)
  schedulePublish()
 }

 /// While a panel is open the page is swapped for a snapshot so the interface can draw over it.
 func setOverlay(_ value: Bool) {
  overlayVersion += 1
  let version = overlayVersion
  overlay = value
  guard value else {
   layoutPages()
   send(["kind": "snapshot", "data": ""])
   if let view = active?.view { window.makeFirstResponder(view) }
   return
  }
  guard let view = active?.view, !view.isHidden else { layoutPages(); return }
  view.takeSnapshot(with: nil) { image, _ in
   guard version == self.overlayVersion else { return }
   if let tiff = image?.tiffRepresentation, let jpeg = NSBitmapImageRep(data: tiff)?.representation(using: .jpeg, properties: [.compressionFactor: 0.8]) {
    self.send(["kind": "snapshot", "data": "data:image/jpeg;base64," + jpeg.base64EncodedString()])
   }
   self.layoutPages()
  }
  // A stalled page must never keep the controls from opening.
  DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { if version == self.overlayVersion { self.layoutPages() } }
 }

 func layoutPages() {
  for tab in tabs {
   guard let view = tab.view else { continue }
   view.frame = pageFrame
   view.isHidden = tab !== active || overlay
  }
 }

 func dragWindow() {
  guard NSEvent.pressedMouseButtons & 1 == 1 else { return }
  let start = NSEvent.mouseLocation, origin = window.frame.origin
  while let event = window.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]), event.type != .leftMouseUp {
   let point = NSEvent.mouseLocation
   window.setFrameOrigin(NSPoint(x: origin.x + point.x - start.x, y: origin.y + point.y - start.y))
  }
 }

 // MARK: Tabs

 @discardableResult
 func createView(_ tab: Tab, configuration: WKWebViewConfiguration? = nil) -> WKWebView {
  let config = configuration ?? WKWebViewConfiguration()
  if configuration == nil {
   config.websiteDataStore = tab.isPrivate ? .nonPersistent() : .default()
   config.applicationNameForUserAgent = "Version/17.4 Safari/605.1.15"
   config.mediaTypesRequiringUserActionForPlayback = []
   config.preferences.isFraudulentWebsiteWarningEnabled = true
   if #available(macOS 12.3, *) { config.preferences.isElementFullscreenEnabled = true }
  }
  let view = WKWebView(frame: pageFrame, configuration: config)
  view.allowsBackForwardNavigationGestures = true
  view.allowsMagnification = true
  view.navigationDelegate = self
  view.uiDelegate = self
  tab.view = view
  tab.observers = [
   view.observe(\.title) { [weak self, weak tab] view, _ in
    if let title = view.title, !title.isEmpty { tab?.title = title; self?.schedulePublish() }
   },
   view.observe(\.url) { [weak self, weak tab] view, _ in
    if let url = view.url?.absoluteString { tab?.url = url; self?.schedulePublish(); self?.saveLater() }
   },
   view.observe(\.isLoading) { [weak self, weak tab] view, _ in tab?.loading = view.isLoading; self?.schedulePublish() },
   view.observe(\.canGoBack) { [weak self] _, _ in self?.schedulePublish() },
   view.observe(\.canGoForward) { [weak self] _, _ in self?.schedulePublish() }
  ]
  applyBlocking(view)
  root.addSubview(view)
  layoutPages()
  return view
 }

 func select(_ tab: Tab) {
  active?.lastSeen = Date()
  tab.lastSeen = Date()
  active = tab
  if tab.view == nil && !tab.url.isEmpty, let url = URL(string: tab.url) { load(url, in: createView(tab)) }
  layoutPages()
  if !overlay, let view = tab.view { window.makeFirstResponder(view) }
  saveLater()
  schedulePublish()
 }

 func newTab(_ url: String = "", isPrivate: Bool = false) {
  let tab = Tab()
  tab.isPrivate = isPrivate
  tabs.append(tab)
  select(tab)
  if url.isEmpty { if ready { openPanel("address", "") } } else { navigate(url) }
 }

 func close(_ tab: Tab) {
  guard let index = tabs.firstIndex(where: { $0 === tab }) else { return }
  if !tab.isPrivate && !tab.url.isEmpty { closed.append(tab.url) }
  unload(tab)
  tabs.remove(at: index)
  if tabs.isEmpty { newTab(); return }
  if active === tab { select(tabs[min(index, tabs.count - 1)]) }
  saveLater()
 }

 func unload(_ tab: Tab) {
  tab.observers = []
  tab.view?.removeFromSuperview()
  tab.view = nil
 }

 func reopen() { if let url = closed.popLast() { newTab(url) } }

 func toggleBookmark() {
  guard let tab = active, !tab.url.isEmpty else { return }
  if let index = bookmarks.firstIndex(where: { $0["Url"] as? String == tab.url }) { bookmarks.remove(at: index); toast("Bookmark removed.") }
  else { bookmarks.append(["Title": tab.title, "Url": tab.url]); toast("Bookmarked.") }
  saveLater()
 }

 func navigate(_ input: String) {
  let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
  guard !text.isEmpty, let url = URL(string: resolve(text)) else { return }
  guard let tab = active else { newTab(url.absoluteString); return }
  tab.url = url.absoluteString
  load(url, in: tab.view ?? createView(tab))
  select(tab)
 }

 func load(_ url: URL, in view: WKWebView) {
  if url.isFileURL { view.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent()) } else { view.load(URLRequest(url: url)) }
 }

 func resolve(_ text: String) -> String {
  if let scheme = URL(string: text)?.scheme?.lowercased(), ["http", "https", "file", "about"].contains(scheme) { return text }
  if !text.contains(" ") && (text.contains(".") || text.hasPrefix("localhost")) && URL(string: "https://" + text) != nil {
   return (text.hasPrefix("localhost") ? "http://" : "https://") + text
  }
  let query = text.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? text
  switch pref("SearchEngine", "Google") {
  case "Bing": return "https://www.bing.com/search?q=" + query
  case "DuckDuckGo": return "https://duckduckgo.com/?q=" + query
  default: return "https://www.google.com/search?q=" + query
  }
 }

 func makeDefault() {
  for scheme in ["http", "https"] {
   NSWorkspace.shared.setDefaultApplication(at: Bundle.main.bundleURL, toOpenURLsWithScheme: scheme) { error in
    if error != nil { DispatchQueue.main.async { self.toast("Choose Still in System Settings → Desktop & Dock → Default web browser.") } }
   }
  }
 }

 // MARK: Blocking

 func compileRules() {
  let domains = ((try? String(contentsOf: resources.appendingPathComponent("blocked.txt"))) ?? "")
   .split(whereSeparator: \.isNewline).map(String.init).filter { !$0.isEmpty }
  let list = domains.map { domain -> [String: Any] in [
   "trigger": ["url-filter": "^https?://([a-z0-9.-]*\\.)?" + NSRegularExpression.escapedPattern(for: domain) + "[:/]", "load-type": ["third-party"]],
   "action": ["type": "block"]
  ] }
  guard !list.isEmpty, let data = try? JSONSerialization.data(withJSONObject: list), let json = String(data: data, encoding: .utf8) else { return }
  WKContentRuleListStore.default().compileContentRuleList(forIdentifier: "still-blocking", encodedContentRuleList: json) { rules, error in
   DispatchQueue.main.async {
    if let error { NSLog("Still blocking rules: \(error)") }
    self.rules = rules
    for tab in self.tabs { if let view = tab.view { self.applyBlocking(view) } }
   }
  }
 }

 /// Tracker and ad-domain blocking plus the YouTube ad script, unless blocking is off or the site is allowed.
 func applyBlocking(_ view: WKWebView, host: String? = nil) {
  let controller = view.configuration.userContentController
  controller.removeAllContentRuleLists()
  controller.removeAllUserScripts()
  controller.addUserScript(WKUserScript(source: editedCheck, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
  guard pref("Blocking", true), !unblocked.contains(host ?? view.url?.host ?? "") else { return }
  if let rules { controller.add(rules) }
  if !youTube.isEmpty { controller.addUserScript(WKUserScript(source: youTube, injectionTime: .atDocumentStart, forMainFrameOnly: false)) }
 }

 // MARK: Memory saver

 let editedCheck = "window.__stillEdited = () => [...document.querySelectorAll('textarea,input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')].some(e => e.value && e.value !== e.defaultValue)"
 let busyCheck = "(() => [...document.querySelectorAll('video,audio')].some(m => !m.paused && !m.muted) || !!document.pictureInPictureElement || !!window.__stillEdited?.())()"

 /// Background tabs left alone for five minutes give their page back to the system, the way Safari and Chrome do,
 /// unless they're pinned, private, playing sound or holding typed text. Selecting one loads it again.
 func sleepIdleTabs() {
  guard pref("MemorySaver", true) else { return }
  let cutoff = Date().addingTimeInterval(-300)
  for tab in tabs where tab !== active && !tab.pinned && !tab.isPrivate && !tab.url.isEmpty && tab.lastSeen < cutoff {
   tab.view?.evaluateJavaScript(busyCheck) { [weak self, weak tab] result, _ in
    guard let self, let tab, tab !== self.active, (result as? Bool) == false else { return }
    self.unload(tab)
    self.schedulePublish()
   }
  }
 }

 // MARK: Import from another browser

 func importSources() -> [(id: String, name: String, folder: URL)] {
  let home = FileManager.default.homeDirectoryForCurrentUser, support = home.appendingPathComponent("Library/Application Support")
  let known: [(String, String, URL)] = [
   ("safari", "Safari", home.appendingPathComponent("Library/Safari")),
   ("chrome", "Chrome", support.appendingPathComponent("Google/Chrome/Default")),
   ("brave", "Brave", support.appendingPathComponent("BraveSoftware/Brave-Browser/Default")),
   ("edge", "Edge", support.appendingPathComponent("Microsoft Edge/Default")),
   ("arc", "Arc", support.appendingPathComponent("Arc/User Data/Default")),
   ("vivaldi", "Vivaldi", support.appendingPathComponent("Vivaldi/Default")),
   ("opera", "Opera", support.appendingPathComponent("com.operasoftware.Opera"))
  ]
  return known.filter { FileManager.default.fileExists(atPath: $0.2.path) }.map { (id: $0.0, name: $0.1, folder: $0.2) }
 }

 func publishImport() {
  var external: [String: Any] = ["busy": importBusy, "error": importError, "done": importDone, "profile": "Still",
                                 "sources": importSources().map { ["id": $0.id, "name": $0.name] }]
  if let preview = pendingImport {
   external["preview"] = ["id": preview.id, "name": preview.name, "bookmarks": preview.bookmarks.count, "history": preview.history.count,
                          "passwords": 0, "cookies": 0, "cookiesLocked": false, "skipped": 0, "warnings": [String]()]
  }
  send(["kind": "tools", "name": "import", "data": ["external": external]])
 }

 /// Reads bookmarks and history (never passwords or cookies, which macOS keeps locked to each browser) for review first.
 func reviewImport(_ name: String, _ folder: URL) {
  guard !importBusy else { return }
  importBusy = true; importError = ""; importDone = ""; pendingImport = nil
  publishImport()
  DispatchQueue.global(qos: .userInitiated).async {
   let safari = FileManager.default.fileExists(atPath: folder.appendingPathComponent("Bookmarks.plist").path) || folder.lastPathComponent == "Safari"
   let result = Result { try safari ? Browser.readSafari(folder) : Browser.readChromium(folder) }
   DispatchQueue.main.async {
    self.importBusy = false
    switch result {
    case .success(let data) where data.bookmarks.isEmpty && data.history.isEmpty: self.importError = "No bookmarks or history were found in \(name)."
    case .success(let data): self.pendingImport = (UUID().uuidString, name, data.bookmarks, data.history)
    case .failure(let error):
     let denied = (error as NSError).code == NSFileReadNoPermissionError || (error as NSError).domain == NSPOSIXErrorDomain
     self.importError = safari && denied ? "macOS keeps Safari's data private. Turn on Still in System Settings → Privacy & Security → Full Disk Access, then try again."
      : "Couldn't read \(name): \(error.localizedDescription)"
    }
    self.publishImport()
   }
  }
 }

 func finishImport(bookmarks takeBookmarks: Bool, history takeHistory: Bool) {
  guard let preview = pendingImport, !importBusy else { return }
  var added = 0, visits = 0
  if takeBookmarks {
   var have = Set(bookmarks.compactMap { $0["Url"] as? String })
   for mark in preview.bookmarks { if let url = mark["Url"] as? String, have.insert(url).inserted { bookmarks.append(mark); added += 1 } }
  }
  if takeHistory {
   let have = Set(history.compactMap { $0["Url"] as? String })
   let fresh = preview.history.filter { !have.contains($0["Url"] as? String ?? "") }
   visits = fresh.count
   history = Array((history + fresh).sorted { ($0["At"] as? String ?? "") > ($1["At"] as? String ?? "") }.prefix(5000))
  }
  pendingImport = nil
  importDone = "Imported \(added) bookmarks and \(visits) history entries from \(preview.name)."
  save()
  publishImport()
  schedulePublish()
 }

 static let stamp = ISO8601DateFormatter()

 static func readChromium(_ folder: URL) throws -> (bookmarks: [[String: Any]], history: [[String: Any]]) {
  var marks: [[String: Any]] = []
  func walk(_ node: Any?) {
   guard let node = node as? [String: Any] else { return }
   if node["type"] as? String == "url", let url = node["url"] as? String { marks.append(["Title": node["name"] as? String ?? url, "Url": url]) }
   for child in node["children"] as? [Any] ?? [] { walk(child) }
  }
  if let data = try? Data(contentsOf: folder.appendingPathComponent("Bookmarks")),
     let roots = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["roots"] as? [String: Any] {
   for root in roots.values { walk(root) }
  }
  let file = folder.appendingPathComponent("History")
  guard FileManager.default.fileExists(atPath: file.path) else { return (marks, []) }
  // Chromium counts microseconds from 1601.
  let visits = try rows(file, "SELECT url, title, last_visit_time FROM urls WHERE hidden = 0 ORDER BY last_visit_time DESC LIMIT 5000").map { row -> [String: Any] in
   ["Url": row[0], "Title": row[1].isEmpty ? row[0] : row[1], "At": stamp.string(from: Date(timeIntervalSince1970: (Double(row[2]) ?? 0) / 1_000_000 - 11_644_473_600))]
  }
  return (marks, visits)
 }

 static func readSafari(_ folder: URL) throws -> (bookmarks: [[String: Any]], history: [[String: Any]]) {
  var marks: [[String: Any]] = []
  func walk(_ node: Any?) {
   guard let node = node as? [String: Any] else { return }
   if node["WebBookmarkType"] as? String == "WebBookmarkTypeLeaf", let url = node["URLString"] as? String {
    marks.append(["Title": (node["URIDictionary"] as? [String: Any])?["title"] as? String ?? url, "Url": url])
   }
   for child in node["Children"] as? [Any] ?? [] { walk(child) }
  }
  walk(try PropertyListSerialization.propertyList(from: Data(contentsOf: folder.appendingPathComponent("Bookmarks.plist")), format: nil))
  // Safari counts seconds from 2001.
  let visits = try rows(folder.appendingPathComponent("History.db"), "SELECT i.url, COALESCE(MAX(v.title), ''), MAX(v.visit_time) FROM history_items i JOIN history_visits v ON v.history_item = i.id GROUP BY i.id ORDER BY 3 DESC LIMIT 5000").map { row -> [String: Any] in
   ["Url": row[0], "Title": row[1].isEmpty ? row[0] : row[1], "At": stamp.string(from: Date(timeIntervalSinceReferenceDate: Double(row[2]) ?? 0))]
  }
  return (marks, visits)
 }

 /// Queries a copy of a browser's database, so a running browser's lock doesn't get in the way and its file is never touched.
 static func rows(_ file: URL, _ sql: String) throws -> [[String]] {
  let temp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: true)
  defer { try? FileManager.default.removeItem(at: temp) }
  let copy = temp.appendingPathComponent(file.lastPathComponent)
  try FileManager.default.copyItem(at: file, to: copy)
  for suffix in ["-wal", "-shm", "-journal"] { try? FileManager.default.copyItem(atPath: file.path + suffix, toPath: copy.path + suffix) }
  var db: OpaquePointer?
  defer { sqlite3_close(db) }
  var statement: OpaquePointer?
  guard sqlite3_open_v2(copy.path, &db, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK, sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else {
   throw NSError(domain: "Still", code: 1, userInfo: [NSLocalizedDescriptionKey: String(cString: sqlite3_errmsg(db))])
  }
  defer { sqlite3_finalize(statement) }
  var result: [[String]] = []
  while sqlite3_step(statement) == SQLITE_ROW {
   result.append((0..<sqlite3_column_count(statement)).map { column in sqlite3_column_text(statement, column).map { String(cString: $0) } ?? "" })
  }
  return result
 }

 // MARK: WebKit delegates

 func webView(_ view: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
  if view === shell { decisionHandler(action.request.url?.scheme == "still" ? .allow : .cancel); return }
  if action.shouldPerformDownload { decisionHandler(.download); return }
  if let url = action.request.url, let scheme = url.scheme?.lowercased(), !["http", "https", "about", "data", "blob", "file"].contains(scheme) {
   // mailto:, facetime:, zoommtg: and other app links open only from a click.
   if action.navigationType == .linkActivated { NSWorkspace.shared.open(url) }
   decisionHandler(.cancel); return
  }
  if action.targetFrame?.isMainFrame == true { applyBlocking(view, host: action.request.url?.host) }
  decisionHandler(.allow)
 }

 func webView(_ view: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
  decisionHandler(response.canShowMIMEType ? .allow : .download)
 }

 func webView(_ view: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { track(download) }
 func webView(_ view: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { track(download) }

 func webView(_ view: WKWebView, didFinish navigation: WKNavigation!) {
  guard let tab = tabs.first(where: { $0.view === view }), !tab.isPrivate, let url = view.url?.absoluteString, url.hasPrefix("http") else { return }
  history.removeAll { $0["Url"] as? String == url }
  history.insert(["Title": view.title ?? url, "Url": url, "At": ISO8601DateFormatter().string(from: Date())], at: 0)
  if history.count > 5000 { history.removeLast(history.count - 5000) }
  saveLater()
  schedulePublish()
 }

 func webView(_ view: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
  let code = (error as NSError).code
  if view !== shell && code != NSURLErrorCancelled && code != 102 { toast("Couldn't open that page: \(error.localizedDescription)") }
 }

 func webViewWebContentProcessDidTerminate(_ view: WKWebView) { view.reload() }

 func webView(_ view: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
  let tab = Tab()
  tab.isPrivate = tabs.first { $0.view === view }?.isPrivate ?? false
  tabs.append(tab)
  let created = createView(tab, configuration: configuration)
  select(tab)
  return created
 }

 func webViewDidClose(_ view: WKWebView) { if let tab = tabs.first(where: { $0.view === view }) { close(tab) } }

 func webView(_ view: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
  let alert = NSAlert()
  alert.messageText = frame.request.url?.host ?? "Still"
  alert.informativeText = message
  alert.beginSheetModal(for: window) { _ in completionHandler() }
 }

 func webView(_ view: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
  let alert = NSAlert()
  alert.messageText = frame.request.url?.host ?? "Still"
  alert.informativeText = message
  alert.addButton(withTitle: "OK")
  alert.addButton(withTitle: "Cancel")
  alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
 }

 func webView(_ view: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
  let alert = NSAlert()
  alert.messageText = frame.request.url?.host ?? "Still"
  alert.informativeText = prompt
  let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
  field.stringValue = defaultText ?? ""
  alert.accessoryView = field
  alert.addButton(withTitle: "OK")
  alert.addButton(withTitle: "Cancel")
  alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
 }

 func webView(_ view: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
  let picker = NSOpenPanel()
  picker.allowsMultipleSelection = parameters.allowsMultipleSelection
  picker.canChooseDirectories = parameters.allowsDirectories
  picker.beginSheetModal(for: window) { completionHandler($0 == .OK ? picker.urls : nil) }
 }

 // MARK: Downloads

 func track(_ task: WKDownload) {
  task.delegate = self
  let item = Download(task: task)
  item.observer = task.progress.observe(\.completedUnitCount) { [weak self] _, _ in DispatchQueue.main.async { self?.schedulePublish() } }
  downloads.append(item)
  schedulePublish()
 }

 func download(_ id: String) -> Download? { Int(id).flatMap { $0 >= 0 && $0 < downloads.count ? downloads[$0] : nil } }

 func download(_ task: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
  let folder = downloadFolder
  let name = (suggestedFilename as NSString).lastPathComponent
  let base = (name as NSString).deletingPathExtension, ext = (name as NSString).pathExtension
  var url = folder.appendingPathComponent(name), count = 1
  while FileManager.default.fileExists(atPath: url.path) {
   count += 1
   url = folder.appendingPathComponent("\(base) (\(count))" + (ext.isEmpty ? "" : "." + ext))
  }
  downloads.first { $0.task === task }?.path = url
  completionHandler(url)
  schedulePublish()
 }

 func downloadDidFinish(_ task: WKDownload) { downloads.first { $0.task === task }?.status = "Completed"; schedulePublish() }
 func download(_ task: WKDownload, didFailWithError error: Error, resumeData: Data?) { downloads.first { $0.task === task }?.status = "Interrupted"; schedulePublish() }

 // MARK: Window

 func windowDidResize(_ notification: Notification) { schedulePublish() }
 func windowDidEnterFullScreen(_ notification: Notification) { schedulePublish() }
 func windowDidExitFullScreen(_ notification: Notification) { schedulePublish() }
 func windowWillClose(_ notification: Notification) { save() }

 // MARK: Menu commands

 @objc func command(_ sender: NSMenuItem) {
  guard let name = sender.representedObject as? String else { return }
  switch name {
  case "newTab": newTab()
  case "privateTab": newTab(isPrivate: true)
  case "closeTab": if let tab = active { close(tab) }
  case "reopen": reopen()
  case "address": openPanel("address", active?.url ?? "")
  case "findTab": openPanel("tabs", "")
  case "find", "history", "downloads", "settings", "bookmarks": openPanel(name, "")
  case "reload": active?.view?.reload()
  case "back": active?.view?.goBack()
  case "forward": active?.view?.goForward()
  case "bookmark": toggleBookmark()
  case "zoomIn": handle("zoom", ["amount": 0.1])
  case "zoomOut": handle("zoom", ["amount": -0.1])
  case "zoomReset": handle("zoom", ["amount": 0])
  case "fullscreen": window.toggleFullScreen(nil)
  case "nextTab", "previousTab":
   if let tab = active, let index = tabs.firstIndex(where: { $0 === tab }) { select(tabs[(index + (name == "nextTab" ? 1 : tabs.count - 1)) % tabs.count]) }
  default:
   if name.hasPrefix("tab"), let number = Int(name.dropFirst(3)), !tabs.isEmpty { select(number == 9 ? tabs[tabs.count - 1] : tabs[min(number - 1, tabs.count - 1)]) }
  }
  schedulePublish()
 }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
 var browser: Browser?
 var pending: [URL] = []

 func applicationDidFinishLaunching(_ notification: Notification) {
  let browser = Browser()
  self.browser = browser
  NSApp.mainMenu = menu(for: browser)
  for url in pending { browser.newTab(url.absoluteString) }
  pending = []
  NSApp.activate(ignoringOtherApps: true)
 }

 func application(_ application: NSApplication, open urls: [URL]) {
  guard let browser else { pending += urls; return }
  for url in urls { browser.newTab(url.absoluteString) }
  browser.window.makeKeyAndOrderFront(nil)
 }

 func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
 func applicationWillTerminate(_ notification: Notification) { browser?.save() }

 func menu(for browser: Browser) -> NSMenu {
  let main = NSMenu()
  func add(_ title: String, _ items: [NSMenuItem]) {
   let holder = NSMenuItem()
   let submenu = NSMenu(title: title)
   items.forEach(submenu.addItem)
   holder.submenu = submenu
   main.addItem(holder)
  }
  func command(_ title: String, _ name: String, _ key: String, _ modifiers: NSEvent.ModifierFlags = .command) -> NSMenuItem {
   let item = NSMenuItem(title: title, action: #selector(Browser.command(_:)), keyEquivalent: key)
   item.keyEquivalentModifierMask = modifiers
   item.target = browser
   item.representedObject = name
   return item
  }
  func standard(_ title: String, _ action: String, _ key: String, _ modifiers: NSEvent.ModifierFlags = .command) -> NSMenuItem {
   let item = NSMenuItem(title: title, action: Selector(action), keyEquivalent: key)
   item.keyEquivalentModifierMask = modifiers
   return item
  }
  add("Still", [
   standard("About Still", "orderFrontStandardAboutPanel:", ""),
   .separator(),
   command("Settings…", "settings", ","),
   .separator(),
   standard("Hide Still", "hide:", "h"),
   standard("Hide Others", "hideOtherApplications:", "h", [.command, .option]),
   .separator(),
   standard("Quit Still", "terminate:", "q")
  ])
  add("File", [
   command("New Tab", "newTab", "t"),
   command("New Private Tab", "privateTab", "n", [.command, .shift]),
   command("Reopen Closed Tab", "reopen", "t", [.command, .shift]),
   command("Open Location…", "address", "l"),
   command("Find a Tab…", "findTab", "k"),
   .separator(),
   command("Close Tab", "closeTab", "w")
  ])
  add("Edit", [
   standard("Undo", "undo:", "z"),
   standard("Redo", "redo:", "z", [.command, .shift]),
   .separator(),
   standard("Cut", "cut:", "x"),
   standard("Copy", "copy:", "c"),
   standard("Paste", "paste:", "v"),
   standard("Select All", "selectAll:", "a"),
   .separator(),
   command("Find…", "find", "f")
  ])
  add("View", [
   command("Reload Page", "reload", "r"),
   .separator(),
   command("Actual Size", "zoomReset", "0"),
   command("Zoom In", "zoomIn", "="),
   command("Zoom Out", "zoomOut", "-"),
   .separator(),
   command("Enter Full Screen", "fullscreen", "f", [.command, .control])
  ])
  add("History", [
   command("Back", "back", "["),
   command("Forward", "forward", "]"),
   .separator(),
   command("Show All History", "history", "y"),
   command("Downloads", "downloads", "l", [.command, .option])
  ])
  add("Bookmarks", [
   command("Bookmark This Page", "bookmark", "d"),
   command("Show Bookmarks", "bookmarks", "b", [.command, .option])
  ])
  var tabItems = [
   command("Show Next Tab", "nextTab", "]", [.command, .shift]),
   command("Show Previous Tab", "previousTab", "[", [.command, .shift]),
   .separator()
  ]
  for number in 1...9 { tabItems.append(command(number == 9 ? "Last Tab" : "Tab \(number)", "tab\(number)", "\(number)")) }
  tabItems += [.separator(), standard("Minimize", "performMiniaturize:", "m")]
  add("Window", tabItems)
  return main
 }
}

// The CI smoke test checks the importer with: Still --read-profile <Chromium or Safari profile folder>
if let index = CommandLine.arguments.firstIndex(of: "--read-profile"), index + 1 < CommandLine.arguments.count {
 let folder = URL(fileURLWithPath: CommandLine.arguments[index + 1])
 do {
  let data = FileManager.default.fileExists(atPath: folder.appendingPathComponent("Bookmarks.plist").path) ? try Browser.readSafari(folder) : try Browser.readChromium(folder)
  print(data.bookmarks.count, data.history.count, data.history.first?["At"] as? String ?? "")
  exit(0)
 } catch { print(error); exit(1) }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
