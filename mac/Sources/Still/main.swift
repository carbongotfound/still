// Still for Mac: a native AppKit + WebKit host for the same React interface the Windows app uses.
// The interface talks to its host through window.chrome.webview, which the bridge below provides on WebKit.
import AppKit
import SQLite3
import WebKit

let resources = Bundle.main.resourceURL!
func argAfter(_ flag: String) -> String? {
 let args = CommandLine.arguments
 guard let index = args.firstIndex(of: flag), index + 1 < args.count else { return nil }
 return args[index + 1]
}
#if STILL_QA
let isQa = CommandLine.arguments.contains("--qa") // test builds only: the QA channel and its environment variables
#else
let isQa = false
#endif
/// The Default profile's folder. Every other profile keeps its website data apart (see pageStore).
let defaultSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Still")
/// Where every profile lives, with the agents folder (Windows: App.ProfileHome).
let profileHome: URL = (argAfter("--profiles-root") ?? argAfter("--profile")).map { URL(fileURLWithPath: $0).standardizedFileURL } ?? defaultSupport
/// The profile's folder (Windows: App.DataRoot). --profile picks another one, for tests and the MCP server a chat starts;
/// otherwise the profile chosen to open at launch.
let support: URL = {
 let url = argAfter("--profile").map { URL(fileURLWithPath: $0).standardizedFileURL } ?? Profiles.folder(Profiles.launchId)
 try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
 return url
}()
let unavailable = "That isn't available in Still for Mac yet."
/// A short random id, the way Windows writes Guid.ToString("N").
func newId() -> String { UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }

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
/// The Mac's own traffic lights stand in for the interface's window buttons, so the strips leave room for them.
let macStyle = """
(() => {
 const style = document.createElement('style');
 style.textContent = `.window-controls{display:none!important}
 html:not(.mac-fullscreen) .browser-shell:not(.is-fullscreen)>:is(.top-tab-strip,.window-bar):first-child{padding-left:84px!important}`;
 document.head.appendChild(style);
})();
"""

/// Scripts Still puts in pages run apart from the page's own (the page can't see or change them); they share its DOM.
let stillWorld = WKContentWorld.world(name: "Still")

/// Serves the bundled interface from still://app/ (module scripts don't load from file:// in WebKit).
final class ShellScheme: NSObject, WKURLSchemeHandler {
 let root: URL
 init(root: URL) { self.root = root.standardizedFileURL }
 func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
  guard let url = task.request.url else { return }
  let path = url.path.isEmpty || url.path == "/" ? "index.html" : String(url.path.dropFirst())
  let file = root.appendingPathComponent(path).standardizedFileURL
  guard file.path.hasPrefix(root.path), var data = try? Data(contentsOf: file) else { task.didFailWithError(URLError(.fileDoesNotExist)); return }
  #if STILL_QA
  qaServed.append(path) // WebKit keeps no resource timing for still:// files, so tests ask what was served
  #endif
  if file.lastPathComponent == "index.html", let html = String(data: data, encoding: .utf8) {
   data = Data(html.replacingOccurrences(of: "'self'", with: "'self' still:").utf8)
  }
  let types = ["html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8", "svg": "image/svg+xml", "png": "image/png", "woff2": "font/woff2", "woff": "font/woff", "json": "application/json",
               "wasm": "application/wasm", "glb": "model/gltf-binary", "webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"]
  let headers = ["Content-Type": types[file.pathExtension.lowercased()] ?? "application/octet-stream", "Access-Control-Allow-Origin": "*"]
  task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)!)
  task.didReceive(data)
  task.didFinish()
 }
 func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

final class FlippedView: NSView { override var isFlipped: Bool { true } }

/// A page. Spots the interface keeps open over it (pageHoles: the AI's glow and its controls) show the shell through and take its clicks.
final class PageView: WKWebView {
 var holes: (frame: CGFloat, spots: [(rect: NSRect, radius: CGFloat)])? // in points, from the page's top left
 /// A rect from the top left in this view's own coordinates (flipped or not).
 func local(_ rect: NSRect, flipped: Bool) -> NSRect { flipped ? rect : NSRect(x: rect.minX, y: bounds.height - rect.maxY, width: rect.width, height: rect.height) }
 override func hitTest(_ point: NSPoint) -> NSView? {
  if let holes, let superview {
   let p = convert(point, from: superview)
   if !local(bounds.insetBy(dx: holes.frame, dy: holes.frame), flipped: true).contains(p) || holes.spots.contains(where: { local($0.rect, flipped: isFlipped).contains(p) }) { return nil }
  }
  return super.hitTest(point)
 }
 func cut(_ value: (frame: CGFloat, spots: [(rect: NSRect, radius: CGFloat)])?) {
  holes = value
  guard let value else { layer?.mask = nil; return }
  wantsLayer = true
  let flipped = isFlipped // the mask draws in the view's own coordinates (the flip comes from a parent layer, not this one's isGeometryFlipped)
  let path = CGMutablePath()
  path.addRect(bounds.insetBy(dx: value.frame, dy: value.frame))
  for spot in value.spots { path.addRoundedRect(in: local(spot.rect, flipped: flipped), cornerWidth: spot.radius, cornerHeight: spot.radius) }
  let mask = CAShapeLayer()
  mask.path = path
  mask.fillRule = .evenOdd
  layer?.mask = mask
 }
}

final class Tab: NSObject {
 var id = UUID().uuidString
 var title = "New tab", url = "", pinned = false, isPrivate = false, loading = false, muted = false
 var ruleMuted = false // muted by the site's Autoplay and sound rule, not by the user
 var inUse = "" // "camera,mic" while the page has them on (the Permissions button's dot)
 var group = "" // a tab group's id, "" = none
 var chatId: String? // a chat tab: shows this AI chat instead of a page
 var pageOpen = false // a chat tab showing its AI's page beside the conversation
 var inChat: String? // a page an AI opened for this chat: it lives in the chat, beside the conversation, not in the tab strip
 var agentKey: String? // which AI run is at work here
 var runChat: String? // an ordinary tab Still's chat AI opened: "Open chat" opens that chat
 var favicon = ""
 var closed = false, reader = false, edited = false, media = false
 var blocked = 0
 var lastSeen = Date()
 var restoreScroll = 0.0 // where an unloaded tab was scrolled to: it reloads there
 var view: WKWebView?
 var observers: [NSKeyValueObservation] = []
 var agent: String? // the AI working in this tab right now (bot icon)
 var aiGroup = false // opened by an AI: shown together in the AI group
 var agentActedAt = Date.distantPast
 var dialog: PageDialog? // an alert/confirm/prompt the page is paused on
 var agentUpload: AgentUpload? // a file picker an AI's click opened, waiting for upload_file
 var uploadFiles: [URL]? // files upload_file is handing to the next file picker
 var loginToken = "", loginApi = "", loginFilled = false // loginApi: the page's login helper (LoginObserver.js), named at random per page
 var generatedLogin = "" // the login saved with a strong password suggested on this page
 var loginUsername: (origin: String, username: String, at: Date)? // a two-step sign-in's first step
 var hideToken: String?, hideExpires = Date.distantPast
}

final class Download {
 let task: WKDownload
 var path: URL?
 var status = "InProgress"
 var isPrivate = false
 let started = Date()
 var observer: NSKeyValueObservation?
 init(task: WKDownload) { self.task = task }
}

final class Browser: NSObject, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
 let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
 let root = FlippedView()
 var shell: WKWebView!
 var tabs: [Tab] = []
 var active: Tab?
 var downloads: [Download] = []
 var closed: [String] = [] // closed tabs' addresses, newest last (25 at most)
 var ready = false, focusMode = false, overlay = false
 var panel = ""
 var pageFrame = NSRect.zero
 var shellRatio: CGFloat = 1 // shell points per interface pixel
 let youTube = (try? String(contentsOf: resources.appendingPathComponent("youtube.js"))) ?? ""
 var publishQueued = false, overlayVersion = 0
 var appearanceObserver: NSKeyValueObservation?
 var pendingImport: (id: String, name: String, bookmarks: [[String: Any]], history: [[String: Any]], logins: BrowserLogins.Found)?
 var importBusy = false, importError = "", importDone = ""
 var importBlocked: (name: String, folder: URL)? // macOS kept Still out of this browser's folder: the panel offers to choose it
 // Windows (Windows.swift)
 let windowId = newId()
 let secondary: Bool, incognito: Bool
 let temporary: Bool // a sign-in window Still opened itself (Composio's key page, an app's sign-in): never saved, closes with the last normal window
 var closing = false
 lazy var privateStore = WKWebsiteDataStore.nonPersistent() // this window's private tabs share one throwaway session
 // Split view, the recent tabs switcher and page holes (Tabs.swift)
 var splitLeft: Tab?, splitRight: Tab?, splitRatio = 0.5
 var recent: [Tab]?, recentIndex = 0, recentHeld = false, recentAt = Date(), recentTimer: Timer?
 var pointerOnPage = false
 var holes: (tab: String, frame: CGFloat, spots: [(rect: NSRect, radius: CGFloat)]) = ("", 0, [])
 var privateHidden: [String: [String]] = [:]
 // Browser tools (Tools.swift, Vault.swift)
 var permissions: [PendingPermission] = []
 var privateSitePermissions: [String: [String: String]] = [:] // a private window's site rules, never written down
 var upload: UploadRequest?
 var loginOffer: LoginOffer?
 var importBatch: ImportBatch?
 var cookieInventory: [String: (cookie: HTTPCookie, store: WKHTTPCookieStore)] = [:] // the cookies panel's rows, by row id
 var profileConfirmation = false

 /// What every window shares lives in the store; these read and write it.
 var prefs: [String: Any] { get { store.prefs } set { store.prefs = newValue } }
 var history: [[String: Any]] { get { store.history } set { store.history = newValue } }
 var bookmarks: [[String: Any]] { get { store.bookmarks } set { store.bookmarks = newValue } }
 var welcome: Bool { get { store.welcome } set { store.welcome = newValue } }
 func pref<T>(_ key: String, _ fallback: T) -> T { prefs[key] as? T ?? fallback }
 var unblocked: [String] { pref("UnblockedHosts", [String]()) }
 var downloadFolder: URL { URL(fileURLWithPath: pref("DownloadFolder", FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0].path)) }
 var stateFile: URL { support.appendingPathComponent("state.json") }
 var dark: Bool { window.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua }

 /// The main window, or with moved a window for a tab dragged out, or an incognito window where every tab is private.
 init(moving moved: Tab? = nil, at point: NSPoint? = nil, incognito: Bool = false, temporary: Bool = false) {
  secondary = moved != nil || incognito
  self.incognito = incognito
  self.temporary = temporary
  super.init()
  browsers.append(self)
  window.titleVisibility = .hidden
  window.titlebarAppearsTransparent = true
  window.backgroundColor = .black
  window.minSize = NSSize(width: 640, height: 420)
  window.isReleasedWhenClosed = false
  window.delegate = self
  if secondary {
   window.setContentSize(NSSize(width: 1120, height: 760))
   if let point { window.setFrameTopLeftPoint(NSPoint(x: point.x - 140, y: point.y + 24)) }
   else if isQa, let main = browsers.first?.window { window.setFrameTopLeftPoint(NSPoint(x: main.frame.minX + 30, y: main.frame.maxY - 30)) } // test windows stay on the test screen
   else { window.center() }
  } else {
   if !window.setFrameUsingName("StillMain") { window.center() }
   window.setFrameAutosaveName("StillMain")
  }
  window.contentView = root

  let config = WKWebViewConfiguration()
  config.setURLSchemeHandler(ShellScheme(root: resources.appendingPathComponent("Shell")), forURLScheme: "still")
  config.mediaTypesRequiringUserActionForPlayback = [] // the intro's sound starts before the first click
  config.userContentController.add(self, name: "still")
  config.userContentController.addUserScript(WKUserScript(source: bridge, injectionTime: .atDocumentStart, forMainFrameOnly: true))
  config.userContentController.addUserScript(WKUserScript(source: macStyle, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
  shell = WKWebView(frame: root.bounds, configuration: config)
  shell.autoresizingMask = [.width, .height]
  shell.navigationDelegate = self
  shell.setValue(false, forKey: "drawsBackground") // until the interface paints, the window's own color shows, not WebKit's white
  root.addSubview(shell)
  shell.load(URLRequest(url: URL(string: "still://app/index.html")!))

  if let moved { acceptTab(moved, announce: false) } else if incognito { newTab(prompt: false) } else { load() }
  applyTheme()
  appearanceObserver = NSApp.observe(\.effectiveAppearance) { [weak self] _, _ in DispatchQueue.main.async { self?.schedulePublish() } }
  if blockingRules == nil && browsers.count == 1 { compileRules() }
  pressure.setEventHandler { [weak self] in self?.sleepIdleTabs() }
  pressure.resume()
  if !secondary {
   startAgentServer()
   startAi()
   Browser.watchRoutines()
   if isQa { startQa() }
   startUpdateChecks()
  }
  window.makeKeyAndOrderFront(nil)
  placeTrafficLights()
 }

 // MARK: State

 /// The main window's tabs from the saved state: the first saved window's (the store itself loads once, in loadStore).
 func load() {
  tabs = savedWindows().first ?? []
  if !tabs.contains(where: { $0.inChat == nil }) { tabs.append(Tab()) }
  select(tabs.first { $0.id == savedState["ActiveId"] as? String && $0.inChat == nil } ?? tabs.first { $0.inChat == nil }!)
 }

 func save() { saveAll() }
 func saveLater() { saveAllLater() }

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
  guard ready, !closing else { return }
  let shown = self.shown
  let preferences: [String: Any] = [
   "theme": pref("Theme", "System"), "search": pref("SearchEngine", "Google"),
   "restore": pref("RestoreTabs", true), "blocking": pref("Blocking", true), "downloads": downloadFolder.path,
   "tracking": pref("Tracking", "Balanced"), "memory": pref("MemorySaver", true), "autofill": pref("Autofill", true),
   "sounds": pref("Sounds", true), "osSoundsOff": UserDefaults.standard.object(forKey: "com.apple.sound.uiaudio.enabled") as? Int == 0, // "Play user interface sound effects" off
   "startup": startupEnabled, "startupDisabled": startupDisabled, "tearOff": pref("TabTearOff", false),
   "agents": pref("AgentsEnabled", false), "askInChat": pref("AgentsAskInChat", true), "isDefaultBrowser": isDefaultBrowser,
   "tabLayout": pref("TabLayout", "Classic"), "chatTitles": pref("ChatTitles", ""), "newTab": pref("NewTab", "companion"), "interests": pref("Interests", [String]()),
   "sidebarWidth": pref("SidebarWidth", 248.0)
  ]
  let tabList: [[String: Any]] = tabs.map { tab in
   var row: [String: Any] = [
    "id": tab.id, "group": tab.group, "title": tab.title, "url": tab.url, "pinned": tab.pinned, "agent": tab.agent ?? "", "aiGroup": tab.aiGroup,
    "isPrivate": tab.isPrivate, "loading": tab.loading, "sleeping": tab.view == nil && !tab.url.isEmpty, "blocked": tab.blocked, "muted": tab.muted, "inUse": tab.inUse,
    "favicon": tab.favicon, "secure": tab.url.hasPrefix("https://"), "certificateError": false
   ]
   if let chat = tab.runChat { row["runChat"] = chat }
   if let key = tab.agentKey, runs[key] != nil { row["driverChat"] = key }
   if let chat = tab.chatId { row["chatId"] = chat }
   if let chat = tab.inChat { row["inChat"] = chat }
   return row
  }
  let source = active?.isPrivate == true && panel == "address" ? [] : history
  let visits: [[String: Any]] = source.prefix(panel == "history" || panel == "address" ? 2000 : 100).map { visit in
   ["title": visit["Title"] as? String ?? "", "url": visit["Url"] as? String ?? "", "at": visit["At"] as? String ?? ""]
  }
  let marks: [[String: Any]] = bookmarks.map { ["title": $0["Title"] as? String ?? "", "url": $0["Url"] as? String ?? "", "favicon": $0["Favicon"] as? String ?? ""] }
  var files: [[String: Any]] = []
  for (index, item) in downloads.enumerated() where !item.isPrivate || active?.isPrivate == true {
   files.append(["id": String(index), "name": item.path?.lastPathComponent ?? "Download", "status": item.status, "isPrivate": item.isPrivate,
                 "bytes": item.task.progress.completedUnitCount, "total": max(0, item.task.progress.totalUnitCount)])
  }
  var state: [String: Any] = ["kind": "state", "activeId": active?.id ?? "", "dark": dark, "focusMode": focusMode, "fullScreen": contentFullScreen]
  state["appFullScreen"] = window.styleMask.contains(.fullScreen)
  state["maximized"] = window.isZoomed
  state["panel"] = panel
  state["profileName"] = Profiles.currentName
  state["secondary"] = secondary
  state["incognito"] = incognito
  state["noExtensions"] = true
  state["noAi"] = false
  state["welcome"] = welcome && !secondary && !incognito
  state["version"] = currentVersion
  state["zoom"] = Int(((shown?.view?.pageZoom ?? 1) * 100).rounded())
  state["preferences"] = preferences
  state["tabs"] = tabList
  state["history"] = visits
  state["bookmarks"] = marks
  state["downloads"] = files
  state["canBack"] = shown?.view?.canGoBack ?? false
  state["canForward"] = shown?.view?.canGoForward ?? false
  state["siteBlocking"] = pref("Blocking", true) && !unblocked.contains(shown?.view?.url?.host ?? "")
  state["mcpCommand"] = Bundle.main.executablePath ?? ""
  if let agent = agentData() { state["agent"] = agent }
  if let tab = active, let dialog = tab.dialog {
   state["dialog"] = ["id": tab.id, "kind": dialog.kind, "message": dialog.message, "defaultText": dialog.defaultText, "site": dialog.site]
  }
  state.merge(agentStateFields()) { _, new in new }
  state.merge(aiStateFields()) { _, new in new }
  state.merge(toolStateFields()) { _, new in new }
  send(state)
 }

 func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
  // Only Still's own interface, from its own origin, drives the browser.
  guard message.webView === shell, message.frameInfo.isMainFrame, message.frameInfo.securityOrigin.protocol == "still", message.frameInfo.securityOrigin.host == "app",
        let text = message.body as? String, text.utf8.count <= 65536,
        let data = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any], let op = data["op"] as? String else { return }
  handle(op, data)
  if op != "bounds" && op != "overlay" && op != "pageHoles" { schedulePublish() }
 }

 func handle(_ op: String, _ data: [String: Any]) {
  func text(_ key: String) -> String { data[key] as? String ?? "" }
  func number(_ key: String) -> Double { (data[key] as? NSNumber)?.doubleValue ?? 0 }
  let target = tabs.first { $0.id == text("id") } ?? active
  switch op {
  case "ready":
   ready = true
   publish() // the interface draws nothing until its first state
   shell.evaluateJavaScript("document.documentElement.classList.toggle('mac-fullscreen', \(window.styleMask.contains(.fullScreen)))")
   publishAi()
  case "bounds":
   if contentFullScreen { return } // keep the normal layout for when the video leaves fullscreen
   shellRatio = number("viewportWidth") > 0 ? shell.bounds.width / number("viewportWidth") : 1
   pageFrame = NSRect(x: number("x") * shellRatio, y: number("y") * shellRatio, width: max(1, number("width") * shellRatio), height: max(1, number("height") * shellRatio))
   layoutPages()
  case "overlay": setOverlay(data["value"] as? Bool ?? false)
  case "openPanel": openPanel(text("name"), text("value"))
  case "panel": panel = text("name")
  case "navigate": navigate(text("url"))
  case "new": newTab(text("url"), isPrivate: data["private"] as? Bool ?? false, prompt: text("url").isEmpty)
  case "incognitoWindow": openIncognito()
  case "select": if let target { select(target) }
  case "closeTab": if let target { close(target, force: data["force"] as? Bool ?? false) }
  case "pin": if let target { target.pinned.toggle(); if target.pinned { leaveGroup(target) }; saveLater() }
  case "duplicate": if let target { newTab(target.url, isPrivate: target.isPrivate, prompt: false) }
  case "sleep": if let target { unload(target); if target === active { newTab(prompt: false) }; saveLater() }
  case "mute": if let target { target.muted.toggle(); target.ruleMuted = false; target.view?.evaluateJavaScript(muteScript(target.muted)) }
  case "reorder":
   if let move = tabs.first(where: { $0.id == text("id") }), let before = tabs.first(where: { $0.id == text("before") }), move !== before {
    tabs.removeAll { $0 === move }
    let at = tabs.firstIndex { $0 === before }!
    tabs.insert(move, at: at)
    // Dropped between two tabs of a group, it joins; at a group's edge it stays outside, so groups stay together.
    if move.group != before.group { move.group = !move.pinned && at > 0 && tabs[at - 1].group == before.group ? before.group : "" }
    saveLater()
   }
  case "back": shown?.view?.goBack()
  case "forward": shown?.view?.goForward()
  case "reload": if let view = shown?.view { if view.isLoading { view.stopLoading() } else { view.reload() } }
  case "zoom": if let view = shown?.view { view.pageZoom = number("amount") == 0 ? 1 : min(3, max(0.3, view.pageZoom + number("amount"))) }
  case "find": if let view = shown?.view, !text("text").isEmpty { view.find(text("text"), configuration: WKFindConfiguration()) { _ in } }
  case "bookmark": toggleBookmark(tabs.first { $0.id == text("id") } ?? shown)
  case "removeBookmark": bookmarks.removeAll { $0["Url"] as? String == text("url") }; saveLater()
  case "bookmarkMove":
   if let i = bookmarks.firstIndex(where: { $0["Url"] as? String == text("url") }) {
    let j = i + Int(number("delta")).signum()
    if j >= 0 && j < bookmarks.count && j != i { bookmarks.swapAt(i, j); saveLater() }
   }
  case "bookmarkEdit":
   let address = text("url").trimmingCharacters(in: .whitespacesAndNewlines), title = text("title").trimmingCharacters(in: .whitespacesAndNewlines)
   if let i = bookmarks.firstIndex(where: { $0["Url"] as? String == text("oldUrl") }), let scheme = URL(string: address)?.scheme?.lowercased(), scheme == "http" || scheme == "https" {
    bookmarks[i]["Title"] = title.isEmpty ? address : title; bookmarks[i]["Url"] = address; saveLater()
   }
  case "exportBookmarks": exportBookmarks()
  case "pictureInPicture": closeSheet(); pictureInPicture()
  case "dialogAnswer": if let target { answerDialog(target, data["accept"] as? Bool ?? false, data["text"] as? String) }
  case "agentAnswer": answerAgent(data["allow"] as? Bool ?? false)
  case "removeHistory": history.removeAll { $0["Url"] as? String == text("url") }; saveLater()
  case "clearHistory": history.removeAll(); store.picks.removeAll(); save(); toast("History cleared.")
  case "clearCookies":
   pageStore.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) { self.toast("Cookies and website data cleared.") }
  case "siteBlocking":
   if let view = shown?.view, let host = view.url?.host {
    var list = unblocked
    if let index = list.firstIndex(of: host) { list.remove(at: index) } else { list.append(host) }
    prefs["UnblockedHosts"] = list; saveLater()
    applyBlocking(view); view.reload()
   }
  case "preference": setPreference(text("key"), text("value"))
  case "welcomeDone": welcome = false; saveLater(); applyTheme()
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
  case "focus": focusMode.toggle(); placeTrafficLights()
  case "drag": dragWindow()
  case "copyText":
   let value = text("text")
   if !isQa && !value.isEmpty && value.count <= 8192 { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(value, forType: .string) }
  case "fullscreen": window.toggleFullScreen(nil)
  case "exitFullscreen": if window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) }
  case "maximize": if window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) } else { window.zoom(nil) }
  case "minimize": window.miniaturize(nil)
  case "closeWindow": window.close()
  case "externalReview": if let source = importSources().first(where: { $0.id == text("id") }) { reviewImport(source.name, source.folder) }
  case "externalChoose":
   let picker = NSOpenPanel(), blocked = data["blocked"] as? Bool == true ? importBlocked : nil
   picker.canChooseDirectories = true; picker.canChooseFiles = false
   picker.directoryURL = blocked?.folder
   picker.message = blocked.map { "Click Open to let Still read \($0.name)'s bookmarks and history." } ?? "Choose a browser profile folder, such as Chrome's Default folder or ~/Library/Safari."
   picker.beginSheetModal(for: window) { result in if result == .OK, let url = picker.url { self.reviewImport(blocked?.folder.standardizedFileURL == url.standardizedFileURL ? blocked!.name : url.lastPathComponent, url) } }
  case "externalFullDisk": NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")!)
  case "externalCancel": if !importBusy { pendingImport = nil; importError = ""; importBlocked = nil; publishImport() }
  case "externalConfirm": finishImport(bookmarks: data["bookmarks"] as? Bool ?? false, history: data["history"] as? Bool ?? false, passwords: data["passwords"] as? Bool ?? false, autofill: data["autofill"] as? Bool ?? false)
  default: if !handleAi(op, data) && !handleAgentOps(op, data) && !handleTools(op, data) && !handlePlugins(op, data) { toast(unavailable) }
  }
 }

 func setPreference(_ key: String, _ value: String) {
  switch key {
  case "theme": if ["Light", "Dark", "System"].contains(value) { prefs["Theme"] = value; applyTheme() }
  case "search": if ["DuckDuckGo", "Google", "Bing"].contains(value) { prefs["SearchEngine"] = value }
  case "restore": prefs["RestoreTabs"] = value == "true"
  case "blocking": prefs["Blocking"] = value == "true"; for browser in browsers { for tab in browser.tabs { if let view = tab.view { browser.applyBlocking(view) } } }
  case "tracking": if ["Basic", "Balanced", "Strict"].contains(value) { prefs["Tracking"] = value } // WebKit's own tracking prevention is always on
  case "memory": prefs["MemorySaver"] = value == "true"
  case "autofill": prefs["Autofill"] = value == "true"
  case "sounds": prefs["Sounds"] = value == "true"
  case "tearOff": prefs["TabTearOff"] = value == "true"
  case "newTab": if ["companion", "sites"].contains(value) { prefs["NewTab"] = value }
  case "tabLayout": if ["Classic", "Modern"].contains(value) { prefs["TabLayout"] = value; for browser in browsers { browser.placeTrafficLights(); browser.schedulePublish() } }
  case "agents":
   prefs["AgentsEnabled"] = value == "true"
   if value != "true" { approvedAgents.removeAll(); prefs["ApprovedAgents"] = [String](); answerAgent(false) } // off = every agent asks again
  case "askInChat": prefs["AgentsAskInChat"] = value == "true"
  case "chatTitles": if value.count < 200 && (value.isEmpty || value == "off" || value.contains("/")) { prefs["ChatTitles"] = value }
  default: toast(unavailable); return
  }
  saveLater()
  publishEverywhere()
 }

 /// Light, Dark or System in every window; pages follow through the window's appearance. In QA the test's stand-in for the
 /// Mac's own setting (qaSystemTheme) decides what System means.
 func applyTheme() {
  let theme = pref("Theme", "System")
  let name: NSAppearance.Name? = theme == "Light" ? .aqua : theme == "Dark" ? .darkAqua : qaSystemTheme.map { $0 == "Light" ? .aqua : .darkAqua }
  for browser in browsers {
   browser.window.appearance = name.flatMap { NSAppearance(named: $0) }
   browser.window.backgroundColor = browser.dark || browser.welcome && !browser.secondary && !browser.incognito ? .black : .white // the first run opens dark, into the intro
   browser.schedulePublish()
  }
 }

 // MARK: Panels and page placement

 func openPanel(_ name: String, _ value: String) {
  if ["passwords", "extensions", "cookies", "security", "profiles", "import"].contains(name) {
   if name == "import" { importDone = "" }
   publishBrowserTools(name)
  }
  panel = name
  if name != "find" { setOverlay(true) }
  send(["kind": "panel", "name": name, "value": value])
  window.makeFirstResponder(shell)
  schedulePublish()
 }

 /// Closes whatever panel is open (Windows: CloseSheet).
 func closeSheet() {
  guard !panel.isEmpty else { return }
  panel = ""
  send(["kind": "panel", "name": "", "value": ""])
  schedulePublish()
 }

 /// While a panel is open the page (and its split partner) is swapped for a snapshot so the interface can draw over it.
 func setOverlay(_ value: Bool) {
  overlayVersion += 1
  let version = overlayVersion
  overlay = value
  guard value else {
   layoutPages()
   send(["kind": "snapshot", "data": "", "partner": ""])
   if let view = shown?.view { window.makeFirstResponder(view) }
   return
  }
  guard let view = shown?.view, !view.isHidden else { layoutPages(); return }
  let pair = partner?.view
  func shot(_ view: WKWebView?, _ done: @escaping (String) -> Void) {
   guard let view, !view.isHidden else { done(""); return }
   view.takeSnapshot(with: nil) { image, _ in
    guard let tiff = image?.tiffRepresentation, let jpeg = NSBitmapImageRep(data: tiff)?.representation(using: .jpeg, properties: [.compressionFactor: 0.8]) else { done(""); return }
    done("data:image/jpeg;base64," + jpeg.base64EncodedString())
   }
  }
  shot(view) { main in
   shot(pair) { partner in
    guard version == self.overlayVersion else { return }
    self.send(["kind": "snapshot", "data": main, "partner": partner])
    self.layoutPages()
   }
  }
  // A stalled page must never keep the controls from opening.
  DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { if version == self.overlayVersion { self.layoutPages() } }
 }

 /// The shown page fills the page slot; a split pair shares it, 6 points apart.
 func layoutPages() {
  let shown = self.shown, partner = self.partner
  let leftWidth = ((pageFrame.width - 6) * splitRatio).rounded()
  for tab in tabs {
   guard let view = tab.view else { continue }
   var frame = pageFrame
   if partner != nil && tab === splitLeft { frame.size.width = max(1, leftWidth) }
   if partner != nil && tab === splitRight { frame.origin.x += leftWidth + 6; frame.size.width = max(1, pageFrame.width - 6 - leftWidth) }
   if view.frame != frame { view.frame = frame }
   view.isHidden = !(tab === shown || tab === partner) || overlay
  }
  cutHoles()
 }

 func dragWindow() {
  guard NSEvent.pressedMouseButtons & 1 == 1 else { return }
  let start = NSEvent.mouseLocation, origin = window.frame.origin
  while let event = window.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]), event.type != .leftMouseUp {
   let point = NSEvent.mouseLocation
   window.setFrameOrigin(NSPoint(x: origin.x + point.x - start.x, y: origin.y + point.y - start.y))
  }
 }

 /// The traffic lights sit centered on the top strip (taller than a title bar), the way Safari and Chrome place them.
 func placeTrafficLights() {
  guard !window.styleMask.contains(.fullScreen), let close = window.standardWindowButton(.closeButton), let bar = close.superview?.superview else { return }
  let height: CGFloat = pref("TabLayout", "Classic") == "Modern" || focusMode ? 56 : 46
  bar.frame = NSRect(x: 0, y: window.frame.height - height, width: window.frame.width, height: height)
  for (index, type) in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton].enumerated() {
   guard let button = window.standardWindowButton(type) else { continue }
   button.setFrameOrigin(NSPoint(x: 16 + CGFloat(index) * 20, y: ((height - button.frame.height) / 2).rounded()))
  }
 }

 // MARK: Tabs

 @discardableResult
 func createView(_ tab: Tab, configuration: WKWebViewConfiguration? = nil) -> WKWebView {
  let config = configuration ?? WKWebViewConfiguration()
  if configuration == nil {
   config.websiteDataStore = tab.isPrivate ? privateStore : pageStore
   config.applicationNameForUserAgent = "Version/17.4 Safari/605.1.15"
   config.mediaTypesRequiringUserActionForPlayback = []
   config.preferences.isFraudulentWebsiteWarningEnabled = true
   if #available(macOS 12.3, *) { config.preferences.isElementFullscreenEnabled = true }
  }
  let view = PageView(frame: pageFrame, configuration: config)
  config.userContentController.removeScriptMessageHandler(forName: "stillPage", contentWorld: stillWorld) // a pop-up shares its opener's
  config.userContentController.add(pageMessages, contentWorld: stillWorld, name: "stillPage")
  view.allowsBackForwardNavigationGestures = true
  view.allowsMagnification = true
  view.isHidden = true
  tab.view = view
  watch(tab, view)
  applyBlocking(view)
  root.addSubview(view)
  layoutPages()
  return view
 }

 /// Hooks a page up to this window: its delegates and the title, address and loading state the strip shows.
 func watch(_ tab: Tab, _ view: WKWebView) {
  view.navigationDelegate = self
  view.uiDelegate = self
  tab.observers = [
   view.observe(\.title) { [weak self, weak tab] view, _ in
    if let title = view.title, !title.isEmpty { tab?.title = title; self?.schedulePublish() }
   },
   view.observe(\.url) { [weak self, weak tab] view, _ in
    if let url = view.url?.absoluteString { tab?.url = url; self?.schedulePublish(); self?.saveLater() }
   },
   view.observe(\.isLoading) { [weak self, weak tab] view, _ in tab?.loading = view.isLoading; self?.schedulePublish() },
   view.observe(\.canGoBack) { [weak self] _, _ in self?.schedulePublish() },
   view.observe(\.canGoForward) { [weak self] _, _ in self?.schedulePublish() },
   view.observe(\.cameraCaptureState) { [weak self, weak tab] view, _ in self?.captureChanged(tab, view) },
   view.observe(\.microphoneCaptureState) { [weak self, weak tab] view, _ in self?.captureChanged(tab, view) }
  ]
 }

 func select(_ target: Tab) {
  var tab = target
  if let app = tab.inChat, app.hasPrefix("app:") { tab.inChat = nil } // an AI app's background tab joins the user's tabs once they open it
  if let owner = tab.inChat, !tab.closed { tab.lastSeen = Date(); tab = chatTab(owner); tab.pageOpen = true } // an AI's page opens in its chat
  guard !tab.closed, tabs.contains(where: { $0 === tab }) else { return }
  if !panel.isEmpty && panel != "recent" { closeSheet() }
  cancelUpload()
  let leaving = active
  leaving?.lastSeen = Date()
  active = tab
  tab.lastSeen = Date()
  if tab.chatId != nil || leaving?.chatId != nil { publishAi() }
  if tab.view != nil { tab.restoreScroll = 0 } // still loaded: it shows exactly as it was left
  for page in [shown, partner] { if let page, page.view == nil, !page.url.isEmpty, let url = URL(string: page.url) { load(url, in: createView(page)) } }
  layoutPages()
  if !overlay, let view = shown?.view, shown === tab { window.makeFirstResponder(view) }
  saveLater()
  schedulePublish()
 }

 /// A link from another app, or a sign-in page: while setup covers this window, it opens in a window of its own, in front.
 func openOutside(_ url: String) {
  guard welcome && !secondary && !incognito else { newTab(url, prompt: false); window.makeKeyAndOrderFront(nil); return }
  let tab = Tab()
  tab.url = url
  _ = Browser(moving: tab, temporary: true)
 }

 @discardableResult
 func newTab(_ url: String = "", isPrivate: Bool = false, prompt: Bool = true) -> Tab {
  let tab = Tab()
  tab.isPrivate = isPrivate || incognito // every tab in an incognito window is private
  tab.title = tab.isPrivate ? "Private tab" : "New tab"
  tabs.append(tab)
  select(tab)
  if url.isEmpty { if prompt && ready { openPanel("address", "") } } else { navigate(url) }
  saveLater()
  return tab
 }

 /// Closing a pinned tab puts it to sleep unless forced. A chat tab takes its pages with it.
 func close(_ tab: Tab, force: Bool = false) {
  if tab.pinned && !force {
   unload(tab)
   if tab === active { if let next = tabs.first(where: { $0 !== tab && !$0.pinned && $0.inChat == nil }) { select(next) } else { newTab(prompt: false) } }
   toast("Pinned tab put to sleep."); saveLater(); schedulePublish()
   return
  }
  guard let index = tabs.firstIndex(where: { $0 === tab }) else { return }
  if !tab.isPrivate && tab.inChat == nil && !tab.url.isEmpty { closed.append(tab.url); if closed.count > 25 { closed.removeFirst() } }
  if tab === splitLeft || tab === splitRight { splitLeft = nil; splitRight = nil }
  tab.closed = true
  unload(tab)
  tabs.remove(at: index)
  if let chat = tab.chatId { for page in tabs where page.inChat == chat { page.closed = true; unload(page) }; tabs.removeAll { $0.inChat == chat } }
  let rest = tabs.filter { $0.inChat == nil }
  if rest.isEmpty { newTab(prompt: false) } else if active === tab { select(rest[min(index, rest.count - 1)]) }
  layoutPages()
  saveLater()
  schedulePublish()
 }

 func unload(_ tab: Tab) {
  releasePage(tab)
  dropPermissions(tab)
  if upload?.tab === tab { cancelUpload() }
  tab.observers = []
  tab.view?.removeFromSuperview()
  tab.view = nil
 }

 func reopen() { if let url = closed.popLast() { newTab(url, prompt: false) } else { toast("No closed tabs to reopen.") } }

 func toggleBookmark(_ target: Tab? = nil) {
  guard let tab = target ?? shown, !tab.url.isEmpty else { return }
  if let index = bookmarks.firstIndex(where: { $0["Url"] as? String == tab.url }) { bookmarks.remove(at: index); toast("Bookmark removed.") }
  else { bookmarks.append(["Title": tab.title, "Url": tab.url, "Favicon": tab.isPrivate ? "" : tab.favicon]); toast("Bookmarked.") }
  saveLater()
 }

 func navigate(_ input: String) {
  let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
  guard !text.isEmpty else { return }
  // chrome:// and edge:// pages open Still's own panels.
  let pages = ["settings": "settings", "history": "history", "favorites": "bookmarks", "bookmarks": "bookmarks", "downloads": "downloads", "version": "about", "extensions": "extensions"]
  if let scheme = ["chrome://", "edge://"].first(where: { text.lowercased().hasPrefix($0) }), let name = pages[String(text.dropFirst(scheme.count)).lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "/"))] {
   openPanel(name, ""); return
  }
  if text.lowercased().hasPrefix("view-source:") { viewSource(String(text.dropFirst(12))); return }
  guard let url = URL(string: resolve(text)) else { return }
  guard let tab = active, tab.chatId == nil else { newTab(url.absoluteString, prompt: false); return } // a chat tab keeps its chat
  tab.url = url.absoluteString
  load(url, in: tab.view ?? createView(tab))
  select(tab)
 }

 func load(_ url: URL, in view: WKWebView) {
  if url.isFileURL { view.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent()) } else { view.load(URLRequest(url: url)) }
 }

 func resolve(_ text: String) -> String {
  if let scheme = URL(string: text)?.scheme?.lowercased(), ["http", "https", "file", "about"].contains(scheme) { return text }
  if text.hasPrefix("/") || text.hasPrefix("~/") { return URL(fileURLWithPath: (text as NSString).expandingTildeInPath).absoluteString }
  if !text.contains(" ") && (text.contains(".") || text.hasPrefix("localhost")) && URL(string: "https://" + text) != nil {
   return (text.hasPrefix("localhost") || text.hasPrefix("127.0.0.1") ? "http://" : "https://") + text
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
    DispatchQueue.main.async {
     defaultBrowserChecked = .distantPast
     if error != nil { self.toast("Choose Still in System Settings → Desktop & Dock → Default web browser.") }
     publishEverywhere()
    }
   }
  }
 }

 // MARK: Blocking and page scripts

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
    blockingRules = rules
    for browser in browsers { for tab in browser.tabs { if let view = tab.view { browser.applyBlocking(view) } } }
   }
  }
 }

 /// Tracker and ad-domain blocking plus the YouTube ad script, unless blocking is off or the site is allowed;
 /// and Still's own page scripts (draft keeper, login observer, hidden elements).
 func applyBlocking(_ view: WKWebView, host: String? = nil) {
  let controller = view.configuration.userContentController
  controller.removeAllContentRuleLists()
  controller.removeAllUserScripts()
  controller.addUserScript(WKUserScript(source: editedCheck, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
  if let tab = tabs.first(where: { $0.view === view }) { addPageScripts(tab, controller) }
  guard pref("Blocking", true), !unblocked.contains(host ?? view.url?.host ?? "") else { return }
  if let blockingRules { controller.add(blockingRules) }
  if !youTube.isEmpty { controller.addUserScript(WKUserScript(source: youTube, injectionTime: .atDocumentStart, forMainFrameOnly: false)) }
 }

 // MARK: Memory saver

 let editedCheck = "window.__stillEdited = () => [...document.querySelectorAll('textarea,input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')].some(e => e.value && e.value !== e.defaultValue)"
 let busyCheck = "(() => [...document.querySelectorAll('video,audio')].some(m => !m.paused && !m.muted) || !!document.pictureInPictureElement || !!window.__stillEdited?.())()"

 let pressure = DispatchSource.makeMemoryPressureSource(eventMask: [.warning, .critical], queue: .main)

 /// Only when macOS runs short of memory do background tabs (left alone a minute or more) give their page back,
 /// unless they're pinned, private, playing sound or holding typed text. Switching tabs never unloads one.
 /// Selecting an unloaded tab loads it again, scrolled where it was.
 func sleepIdleTabs() {
  guard pref("MemorySaver", true) else { return }
  let cutoff = Date().addingTimeInterval(-60), shown = self.shown, partner = self.partner
  for tab in tabs where tab !== active && tab !== shown && tab !== partner && !tab.pinned && !tab.isPrivate && !tab.url.isEmpty && tab.lastSeen < cutoff && tab.agent == nil {
   tab.view?.evaluateJavaScript("\(busyCheck) ? -1 : scrollY") { [weak self, weak tab] result, _ in
    guard let self, let tab, tab !== self.active, tab !== self.shown, let y = result as? Double, y >= 0 else { return }
    self.unload(tab)
    tab.restoreScroll = y
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
  // Firefox names its profile folders like "x1y2z3.default-release".
  let firefox = ((try? FileManager.default.contentsOfDirectory(at: support.appendingPathComponent("Firefox/Profiles"), includingPropertiesForKeys: nil)) ?? [])
   .filter { FileManager.default.fileExists(atPath: $0.appendingPathComponent("places.sqlite").path) }.prefix(30)
   .map { ("firefox-" + $0.lastPathComponent, "Firefox · " + ($0.lastPathComponent.split(separator: ".", maxSplits: 1).last.map(String.init) ?? $0.lastPathComponent), $0) }
  return (known + firefox).filter { FileManager.default.fileExists(atPath: $0.2.path) }.map { (id: $0.0, name: $0.1, folder: $0.2) }
 }

 func publishImport() { publishBrowserTools("import") }

 /// The import panel's data: other browsers on this Mac, and a reviewed file import (Windows: ImportData).
 func importData() -> [String: Any] {
  var external: [String: Any] = ["busy": importBusy, "error": importError, "done": importDone, "profile": Profiles.currentName,
                                 "sources": importSources().map { ["id": $0.id, "name": $0.name] }]
  if let blocked = importBlocked { external["blocked"] = blocked.name }
  if let preview = pendingImport {
   external["preview"] = ["id": preview.id, "name": preview.name, "bookmarks": preview.bookmarks.count, "history": preview.history.count,
                          "passwords": preview.logins.logins.count, "cookies": 0, "cookiesLocked": false, "skipped": preview.logins.skipped, "warnings": preview.logins.warnings]
  }
  var data: [String: Any] = ["external": external]
  if let batch = importBatch {
   data["preview"] = ["id": batch.id, "kind": batch.kind, "file": batch.file, "logins": batch.logins.count, "bookmarks": batch.bookmarks.count,
                      "history": batch.history.count, "tabs": batch.tabs.count, "skipped": batch.skipped]
  }
  return data
 }

 /// Reads bookmarks, history and saved passwords (not cookies, which macOS keeps locked to each browser) for review first.
 func reviewImport(_ name: String, _ folder: URL) {
  guard !importBusy else { return }
  importBusy = true; importError = ""; importDone = ""; pendingImport = nil; importBlocked = nil
  publishImport()
  DispatchQueue.global(qos: .userInitiated).async {
   let safari = FileManager.default.fileExists(atPath: folder.appendingPathComponent("Bookmarks.plist").path) || folder.lastPathComponent == "Safari"
   let firefox = ["places.sqlite", "key4.db"].contains { FileManager.default.fileExists(atPath: folder.appendingPathComponent($0).path) }
   let result = Result { try safari ? Browser.readSafari(folder) : firefox ? Browser.readFirefox(folder) : Browser.readChromium(folder) }
   let logins: BrowserLogins.Found = safari ? ([], ["Safari keeps its passwords in the Passwords app. To bring them over, choose File → Export All Passwords there, then add the file with Passwords CSV."], 0)
    : firefox ? BrowserLogins.firefox(folder) : BrowserLogins.chromium(folder)
   DispatchQueue.main.async {
    self.importBusy = false
    switch result {
    case .success(let data) where data.bookmarks.isEmpty && data.history.isEmpty && logins.logins.isEmpty && logins.warnings.isEmpty: self.importError = "No bookmarks, history or passwords were found in \(name)."
    case .success(let data): self.pendingImport = (UUID().uuidString, name, data.bookmarks, data.history, logins)
    case .failure(let error) where Browser.denied(error as NSError):
     // macOS privacy protection: a folder the user picks in an Open panel is theirs to give, or Full Disk Access opens them all.
     self.importBlocked = (name, folder)
     self.importError = "macOS keeps \(name)'s data private until you let Still in. Choose \(name)'s folder and click Open, or turn on Full Disk Access for Still."
    case .failure(let error): self.importError = "Couldn't read \(name): \(error.localizedDescription)"
    }
    self.publishImport()
   }
  }
 }

 func finishImport(bookmarks takeBookmarks: Bool, history takeHistory: Bool, passwords takePasswords: Bool, autofill: Bool) {
  guard let preview = pendingImport, !importBusy else { return }
  var added = 0, visits = 0, saved = 0
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
  if takePasswords {
   var entries = Vault.read()
   for login in preview.logins.logins where !entries.contains(where: { $0.origin == login.origin && $0.username == login.username }) { entries.append(login); saved += 1 }
   Vault.write(entries)
   if autofill { prefs["AutoFillPasswords"] = true; prefs["OfferPasswordSave"] = true; prefs["OfferPasswordUpdate"] = true }
  }
  pendingImport = nil
  importDone = "Imported \(added) bookmarks, \(visits) history entries and \(saved) passwords from \(preview.name)."
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

 static func readFirefox(_ folder: URL) throws -> (bookmarks: [[String: Any]], history: [[String: Any]]) {
  let places = folder.appendingPathComponent("places.sqlite")
  guard FileManager.default.fileExists(atPath: places.path) else { return ([], []) }
  let marks = try rows(places, "SELECT p.url, COALESCE(b.title, '') FROM moz_bookmarks b JOIN moz_places p ON p.id = b.fk WHERE b.type = 1 LIMIT 5000").map { row -> [String: Any] in
   ["Title": row[1].isEmpty ? row[0] : row[1], "Url": row[0]]
  }
  // Firefox counts microseconds from 1970.
  let visits = try rows(places, "SELECT url, COALESCE(title, ''), last_visit_date FROM moz_places WHERE last_visit_date IS NOT NULL AND hidden = 0 ORDER BY last_visit_date DESC LIMIT 5000").map { row -> [String: Any] in
   ["Url": row[0], "Title": row[1].isEmpty ? row[0] : row[1], "At": stamp.string(from: Date(timeIntervalSince1970: (Double(row[2]) ?? 0) / 1_000_000))]
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

 /// macOS's privacy protection said no (not a missing or broken file).
 static func denied(_ error: NSError) -> Bool {
  error.domain == NSCocoaErrorDomain && [NSFileReadNoPermissionError, NSFileWriteNoPermissionError].contains(error.code)
   || error.domain == NSPOSIXErrorDomain && [Int(EPERM), Int(EACCES)].contains(error.code)
   || (error.userInfo[NSUnderlyingErrorKey] as? NSError).map(denied) == true
 }
 /// Queries a copy of a browser's database, so a running browser's lock doesn't get in the way and its file is never touched.
 static func rows(_ file: URL, _ sql: String) throws -> [[String]] { try blobs(file, sql).map { $0.map { String(decoding: $0, as: UTF8.self) } } }
 static func blobs(_ file: URL, _ sql: String) throws -> [[Data]] {
  let temp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: true)
  defer { try? FileManager.default.removeItem(at: temp) }
  let copy = temp.appendingPathComponent(file.lastPathComponent)
  // Read, then write: copying the file would also copy its metadata, which can fail on its own.
  try Data(contentsOf: file).write(to: copy)
  for suffix in ["-wal", "-shm", "-journal"] { if let part = try? Data(contentsOf: URL(fileURLWithPath: file.path + suffix)) { try? part.write(to: URL(fileURLWithPath: copy.path + suffix)) } }
  var db: OpaquePointer?
  defer { sqlite3_close(db) }
  var statement: OpaquePointer?
  guard sqlite3_open_v2(copy.path, &db, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK, sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else {
   throw NSError(domain: "Still", code: 1, userInfo: [NSLocalizedDescriptionKey: String(cString: sqlite3_errmsg(db))])
  }
  defer { sqlite3_finalize(statement) }
  var result: [[Data]] = []
  while sqlite3_step(statement) == SQLITE_ROW {
   result.append((0..<sqlite3_column_count(statement)).map { column in sqlite3_column_blob(statement, column).map { Data(bytes: $0, count: Int(sqlite3_column_bytes(statement, column))) } ?? Data() })
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

 func webView(_ view: WKWebView, didCommit navigation: WKNavigation!) {
  guard let tab = tabs.first(where: { $0.view === view }) else { return }
  if hostName(tab.url) != hostName(view.url?.absoluteString ?? "") { tab.favicon = "" }
  tab.reader = false; tab.hideToken = nil; tab.loginFilled = false; tab.loginApi = ""
  schedulePublish()
 }

 func webView(_ view: WKWebView, didFinish navigation: WKNavigation!) {
  guard let tab = tabs.first(where: { $0.view === view }) else { return }
  if tab.restoreScroll > 0 { view.evaluateJavaScript("scrollTo(0, \(tab.restoreScroll))"); tab.restoreScroll = 0 }
  updateFavicon(tab)
  applySound(tab, page: true)
  guard !tab.isPrivate, let url = view.url?.absoluteString, url.hasPrefix("http") else { return }
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

 func webViewWebContentProcessDidTerminate(_ view: WKWebView) {
  if let tab = tabs.first(where: { $0.view === view }) { releasePage(tab); dropPermissions(tab); schedulePublish() }
  view.reload()
 }

 func webView(_ view: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
  // A pop-up from an agent's click opens as the agent's own background tab.
  if let opener = tabs.first(where: { $0.view === view }), let who = opener.agent, Date().timeIntervalSince(opener.agentActedAt) < 10 {
   return openAgentTab(who, "", configuration: configuration).view
  }
  // Pop-ups on Block: a page's scripts open nothing (WebKit already stops the ones no click started).
  if let opener = tabs.first(where: { $0.view === view }), action.navigationType != .linkActivated, siteRule(opener, "Popups") == "Deny" { return nil }
  let tab = Tab()
  tab.isPrivate = incognito || tabs.first { $0.view === view }?.isPrivate ?? false
  tabs.append(tab)
  let created = createView(tab, configuration: configuration)
  select(tab)
  return created
 }

 func webViewDidClose(_ view: WKWebView) { if let tab = tabs.first(where: { $0.view === view }) { close(tab, force: true) } }

 // Page dialogs show in Still's own dialog over the page (see openDialog), where an agent can answer them too.
 func webView(_ view: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
  openDialog(view, "alert", message, "", frame) { _, _ in completionHandler() }
 }

 func webView(_ view: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
  openDialog(view, "confirm", message, "", frame) { accept, _ in completionHandler(accept) }
 }

 func webView(_ view: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
  openDialog(view, "prompt", prompt, defaultText ?? "", frame) { accept, text in completionHandler(accept ? text ?? defaultText ?? "" : nil) }
 }

 func webView(_ view: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
  guard let tab = tabs.first(where: { $0.view === view }) else { completionHandler(nil); return }
  if agentPicker(tab, parameters.allowsMultipleSelection, completionHandler) { return }
  offerFiles(tab, parameters, completionHandler)
 }

 /// Camera and microphone ask in Still's own permission bar; the answer is kept for the site (not for private tabs).
 func webView(_ view: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
  guard let tab = tabs.first(where: { $0.view === view }) else { decisionHandler(.deny); return }
  let kind = type == .camera ? "Camera" : type == .microphone ? "Microphone" : "CameraAndMicrophone"
  askPermission(tab, origin, kind) { decisionHandler($0 ? .grant : .deny) }
 }

 // MARK: Downloads

 func track(_ task: WKDownload) {
  // Automatic downloads on Block: a second download within 10 seconds of the site's last one is cancelled.
  if let tab = tabs.first(where: { $0.view === task.webView }), siteRule(tab, "MultipleAutomaticDownloads") == "Deny",
     downloads.contains(where: { $0.task.webView === task.webView && Date().timeIntervalSince($0.started) < 10 }) {
   task.cancel(); toast("Blocked more downloads from this site"); return
  }
  task.delegate = self
  let item = Download(task: task)
  item.isPrivate = incognito || tabs.first { $0.view === task.webView }?.isPrivate == true
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

 func windowDidResize(_ notification: Notification) { placeTrafficLights(); schedulePublish() }
 func windowDidEnterFullScreen(_ notification: Notification) { fullScreenChanged() }
 func windowDidExitFullScreen(_ notification: Notification) { fullScreenChanged(); placeTrafficLights() }
 func windowDidBecomeKey(_ notification: Notification) { lastActiveBrowser = self; schedulePublish() }
 func windowWillClose(_ notification: Notification) {
  closing = true
  saveAll()
  if !temporary && !incognito { closedWindows.append((at: Date(), tabs: tabs)) }
  for tab in tabs { unload(tab) }
  recentTimer?.invalidate()
  shell.configuration.userContentController.removeScriptMessageHandler(forName: "still")
  browsers.removeAll { $0 === self }
  if lastActiveBrowser === self { lastActiveBrowser = nil }
  if !temporary && browsers.allSatisfy(\.temporary) { for browser in browsers { browser.window.close() } } // a sign-in window doesn't outlive the browser (an incognito window keeps it open)
  publishEverywhere() // the other windows' window lists
 }
 func fullScreenChanged() {
  shell.evaluateJavaScript("document.documentElement.classList.toggle('mac-fullscreen', \(window.styleMask.contains(.fullScreen)))")
  schedulePublish()
 }

 // MARK: Menu commands

 @objc func command(_ sender: NSMenuItem) {
  guard let name = sender.representedObject as? String else { return }
  switch name {
  case "newTab": newTab()
  case "incognito": openIncognito()
  case "closeTab": if let tab = active { close(tab) }
  case "reopen": reopen()
  case "address": openPanel("address", active?.url ?? "")
  case "findTab": openPanel("tabs", "")
  case "find", "history", "downloads", "settings", "bookmarks", "about": openPanel(name, "")
  case "reload": handle("reload", [:])
  case "back": shown?.view?.goBack()
  case "forward": shown?.view?.goForward()
  case "bookmark": toggleBookmark()
  case "zoomIn": handle("zoom", ["amount": 0.1])
  case "zoomOut": handle("zoom", ["amount": -0.1])
  case "zoomReset": handle("zoom", ["amount": 0])
  case "fullscreen": window.toggleFullScreen(nil)
  case "nextTab": cycleTabs(1)
  case "previousTab": cycleTabs(-1)
  case "reader": closeSheet(); toggleReader()
  case "hide": closeSheet(); pickHidden()
  case "viewSource": if let url = shown?.url, !url.isEmpty { viewSource(url) }
  case "focus": handle("focus", [:])
  case "layout": setPreference("tabLayout", pref("TabLayout", "Classic") == "Modern" ? "Classic" : "Modern")
  case "pin": if let tab = active, tab.chatId == nil { handle("pin", ["id": tab.id]) }
  case "aiChat": aiShortcut("chat")
  case "aiStop": aiShortcut("stop")
  case "aiTasks": aiShortcut("tasks")
  default:
   let strip = tabs.filter { $0.inChat == nil }
   if name.hasPrefix("tab"), let number = Int(name.dropFirst(3)), !strip.isEmpty { select(number == 9 ? strip[strip.count - 1] : strip[min(number - 1, strip.count - 1)]) }
  }
  schedulePublish()
 }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
 var pending: [URL] = []
 var started = false
 /// The window the menu and keys act on.
 var current: Browser? { browsers.first { $0.window.isKeyWindow } ?? lastActiveBrowser ?? browsers.first }

 func applicationDidFinishLaunching(_ notification: Notification) {
  if isQa && qaSystemTheme == nil { qaSystemTheme = ProcessInfo.processInfo.environment["STILL_QA_SYSTEM_THEME"] ?? "Dark" }
  Profiles.holdRunningLock()
  loadStore()
  let browser = Browser()
  restoreOtherWindows()
  browser.window.makeKeyAndOrderFront(nil) // the main window, with last time's active tab, in front
  started = true
  if PluginKey.exists { Task { @MainActor in await browser.refreshPlugins() } }
  NSApp.mainMenu = menu()
  watchKeys()
  for url in pending { browser.openOutside(url.absoluteString) }
  pending = []
  if !isQa { NSApp.activate(ignoringOtherApps: true) }
 }

 func application(_ application: NSApplication, open urls: [URL]) {
  guard started, let browser = homeBrowser else { pending += urls; return } // a normal window, never a sign-in one
  for url in urls { browser.openOutside(url.absoluteString) }
 }

 func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
 func applicationWillTerminate(_ notification: Notification) {
  saveAll(); AgentRun.endAll()
  // A temporary profile is deleted as it closes (the next temp window sweeps any leftovers).
  if isTemp, support.standardizedFileURL.path.hasPrefix(FileManager.default.temporaryDirectory.appendingPathComponent("Still-temp").standardizedFileURL.path + "/") { try? FileManager.default.removeItem(at: support) }
 }
 func applicationDidBecomeActive(_ notification: Notification) { defaultBrowserChecked = .distantPast; publishEverywhere() }

 @objc func command(_ sender: NSMenuItem) { current?.command(sender) }

 /// Keys the menu can't express: Ctrl+Tab's hold-to-pick recent tabs, Esc from a page, and a click into the other half of a split.
 /// Also the pointer moving onto a page.
 func watchKeys() {
  NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .flagsChanged, .leftMouseDown, .mouseMoved]) { event in
   if event.type == .mouseMoved { self.pointerMoved(event); return event }
   guard let browser = browsers.first(where: { $0.window === event.window }) else { return event }
   switch event.type {
   case .keyDown where event.keyCode == 48 && event.modifierFlags.contains(.control): // Tab
    browser.switchRecent(event.modifierFlags.contains(.shift) ? -1 : 1)
    return nil
   case .keyDown where event.keyCode == 53: // Esc
    // Anywhere but the interface (a page, or the window itself after a click on nothing), it goes to the interface
    if (browser.window.firstResponder as? NSView)?.isDescendant(of: browser.shell) != true { browser.escape() }
    return event
   case .leftMouseDown:
    let point = browser.root.convert(event.locationInWindow, from: nil)
    if let partner = browser.partner, let view = partner.view, !view.isHidden, view.frame.contains(point) { browser.focusSplitSide(partner) }
    return event
   default: return event
   }
  }
 }

 /// The page sits over the interface's own view, so once the pointer is on the page the interface gets no more moves and
 /// keeps its hover (a tab's X stays up); WebKit takes no handed-over move or exit for it. Tell the interface instead: it
 /// drops its hover styles until the pointer comes back.
 func pointerMoved(_ event: NSEvent) {
  // A move with no window (one posted to the app) carries a screen point
  guard let window = event.window ?? NSApp.keyWindow, let browser = browsers.first(where: { $0.window === window }) else { return }
  let point = event.window == nil ? window.convertPoint(fromScreen: event.locationInWindow) : event.locationInWindow
  let onPage = sequence(first: window.contentView?.hitTest(point), next: { $0?.superview }).contains { $0 is PageView }
  if onPage, !browser.pointerOnPage { browser.send(["kind": "pointerAway"]) }
  browser.pointerOnPage = onPage
 }

 func menu() -> NSMenu {
  let main = NSMenu()
  func add(_ title: String, _ items: [NSMenuItem]) {
   let holder = NSMenuItem()
   let submenu = NSMenu(title: title)
   items.forEach(submenu.addItem)
   holder.submenu = submenu
   main.addItem(holder)
  }
  // A shifted letter is written uppercase, as a real key press reports it, so ⇧⌘K never falls through to ⌘K.
  func shifted(_ key: String, _ modifiers: NSEvent.ModifierFlags) -> String { modifiers.contains(.shift) ? key.uppercased() : key }
  func command(_ title: String, _ name: String, _ key: String, _ modifiers: NSEvent.ModifierFlags = .command) -> NSMenuItem {
   let item = NSMenuItem(title: title, action: #selector(AppDelegate.command(_:)), keyEquivalent: shifted(key, modifiers))
   item.keyEquivalentModifierMask = modifiers
   item.target = self
   item.representedObject = name
   return item
  }
  func standard(_ title: String, _ action: String, _ key: String, _ modifiers: NSEvent.ModifierFlags = .command) -> NSMenuItem {
   let item = NSMenuItem(title: title, action: Selector(action), keyEquivalent: shifted(key, modifiers))
   item.keyEquivalentModifierMask = modifiers
   return item
  }
  let left = String(UnicodeScalar(NSLeftArrowFunctionKey)!), right = String(UnicodeScalar(NSRightArrowFunctionKey)!)
  add("Still", [
   command("About Still", "about", ""), // the same About as Windows, not the bare system panel
   .separator(),
   command("Settings…", "settings", ","),
   .separator(),
   standard("Hide Still", "hide:", "h"),
   standard("Hide Others", "hideOtherApplications:", "h", [.command, .option]),
   standard("Show All", "unhideAllApplications:", ""),
   .separator(),
   standard("Quit Still", "terminate:", "q")
  ])
  add("File", [
   command("New Tab", "newTab", "t"),
   command("New Private Window", "incognito", "n", [.command, .shift]),
   command("Reopen Closed Tab", "reopen", "t", [.command, .shift]),
   command("Open Location…", "address", "l"),
   command("Find a Tab…", "findTab", "k"),
   .separator(),
   command("Close Tab", "closeTab", "w"),
   standard("Close Window", "performClose:", "w", [.command, .shift])
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
   command("Reader", "reader", "r", [.command, .shift]),
   command("Hide an Element…", "hide", "h", [.command, .shift]),
   command("View Page Source", "viewSource", "u", [.command, .option]),
   .separator(),
   command("Actual Size", "zoomReset", "0"),
   command("Zoom In", "zoomIn", "="),
   command("Zoom Out", "zoomOut", "-"),
   .separator(),
   command("Tabs on Top or on the Side", "layout", "s", [.command, .shift]),
   command("Focus Mode", "focus", "f", [.command, .shift]),
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
  add("AI", [
   command("Chat with Your AI", "aiChat", "a", [.command, .shift]),
   command("Running Tasks", "aiTasks", "k", [.command, .shift]),
   command("Stop the AI", "aiStop", ".")
  ])
  var tabItems = [
   command("Show Next Tab", "nextTab", right, [.command, .option]),
   command("Show Previous Tab", "previousTab", left, [.command, .option]),
   command("Show Next Tab", "nextTab", "]", [.command, .shift]),
   command("Show Previous Tab", "previousTab", "[", [.command, .shift]),
   command("Pin Tab", "pin", "p", [.command, .shift]),
   .separator()
  ]
  tabItems[2].isAlternate = false
  for number in 1...9 { tabItems.append(command(number == 9 ? "Last Tab" : "Tab \(number)", "tab\(number)", "\(number)")) }
  tabItems += [.separator(), standard("Minimize", "performMiniaturize:", "m"), standard("Zoom", "performZoom:", "")]
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
// AI agents: `Still --mcp` is the MCP server their apps launch; `Still --cli <tool> as=<name> key=value ...` makes one call.
if CommandLine.arguments.contains("--mcp") { Mcp.run(); exit(0) }
if let index = CommandLine.arguments.firstIndex(of: "--cli") { exit(Mcp.cli(Array(CommandLine.arguments[(index + 1)...]))) }

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
