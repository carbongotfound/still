// The test channel (ported from MainWindow.Qa.cs). Compiled only into explicit test builds (-D STILL_QA): release builds
// have none of it. A Unix socket in the profile (its path goes in qa-pipe.txt) takes one JSON request per line and answers
// with one JSON line; tests/desktop/qa.py drives it.
import AppKit
import WebKit

/// A test setting from the environment (STILL_QA_SEARCH, STILL_QA_DISCARD_MINUTES, STILL_QA_VERSION, ...); nil outside QA.
func qaEnv(_ name: String) -> String? { isQa ? ProcessInfo.processInfo.environment[name] : nil }

#if STILL_QA
private var qaServing = false
var qaServed: [String] = [] // the still:// files the shell loaded, in order
private var qaShellErrors: [String] = []

/// The shell's uncaught errors and rejections, which the tests check stay empty.
private final class QaErrors: NSObject, WKScriptMessageHandler {
 func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
  if let text = message.body as? String, qaShellErrors.count < 100 { qaShellErrors.append(text) }
 }
}
private let qaErrorScript = """
addEventListener('error', e => webkit.messageHandlers.stillQaError.postMessage(String(e.message) + ' at ' + (e.filename || '') + ':' + (e.lineno || 0)));
addEventListener('unhandledrejection', e => webkit.messageHandlers.stillQaError.postMessage('Unhandled rejection: ' + String(e.reason && (e.reason.stack || e.reason))));
"""

// MARK: What the tests read. Browser fields the shell may rename are read only here.
private func qaTopLeft(_ w: NSWindow) -> (left: Double, top: Double) {
 (Double(w.frame.minX), Double((NSScreen.screens.first?.frame.maxY ?? w.frame.maxY) - w.frame.maxY)) // Windows' screen coordinates: y down from the top
}
private func qaVisible(_ view: WKWebView?) -> Any {
 guard let view else { return NSNull() }
 return view.window == nil ? "Collapsed" : view.isHiddenOrHasHiddenAncestor ? "Hidden" : "Visible"
}
private func qaResidentBytes() -> UInt64 {
 var info = mach_task_basic_info()
 var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
 let result = withUnsafeMutablePointer(to: &info) { $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count) } }
 return result == KERN_SUCCESS ? info.resident_size : 0
}
private func n(_ value: Any?) -> Any { value ?? NSNull() }

extension Browser {
 func startQa() {
  shell.configuration.userContentController.add(QaErrors(), name: "stillQaError")
  shell.configuration.userContentController.addUserScript(WKUserScript(source: qaErrorScript, injectionTime: .atDocumentStart, forMainFrameOnly: true))
  // Test windows open at a fixed spot (for example on a second screen), given like Windows: x,y from the top left.
  if let spot = qaEnv("STILL_QA_POS")?.split(separator: ","), spot.count == 2, let x = Double(spot[0]), let y = Double(spot[1]), let screen = NSScreen.screens.first {
   window.setFrameTopLeftPoint(NSPoint(x: x, y: screen.frame.maxY - y))
  }
  guard !qaServing else { return }
  qaServing = true
  // Test windows get their "system" theme from the test, dark unless it says.
  qaSystemTheme = qaEnv("STILL_QA_SYSTEM_THEME") ?? "Dark"
  applyTheme()
  qaListen()
 }

 func qaState() -> [String: Any] {
  let view = active?.view
  let screens = browsers.map { b -> [String: Any] in
   let spot = qaTopLeft(b.window)
   return ["id": b.windowId, "tabs": b.tabs.map(\.url), "privateTabs": b.tabs.filter(\.isPrivate).count, "secondary": b.secondary, "incognito": b.incognito, "left": spot.left, "top": spot.top]
  }
  let spot = qaTopLeft(window)
  return [
   "activeId": n(active?.id), "panel": panel, "dark": dark, "theme": pref("Theme", "System"), "aiCalls": AgentRun.launched, "startup": NSNull(),
   "fullScreen": window.styleMask.contains(.fullScreen), "browserFullScreen": false, "contentFullScreen": false,
   "windowState": window.isMiniaturized ? "Minimized" : window.isZoomed ? "Maximized" : "Normal", "focusMode": focusMode, "shellErrors": qaShellErrors, "pointerOnPage": pointerOnPage,
   "appActive": NSApp.isActive, "keyWindow": window.isKeyWindow, "responder": window.firstResponder.map { String(describing: type(of: $0)) } ?? "",
   "sidePanelUrl": NSNull(), "sidePanelWidth": NSNull(), "extensionPopup": false,
   "viewport": ["pageX": pageFrame.minX, "pageY": pageFrame.minY, "pageWidth": pageFrame.width, "pageHeight": pageFrame.height, "visible": view.map { $0.isHidden ? "Collapsed" : "Visible" } ?? "Collapsed",
                "viewWidth": n(view?.frame.width), "viewHeight": n(view?.frame.height), "hostWidth": pageFrame.width, "hostHeight": pageFrame.height, "zoom": n(view.map { Double($0.pageZoom) })] as [String: Any],
   "protection": ["reputation": n(view?.configuration.preferences.isFraudulentWebsiteWarningEnabled), "tracking": pref("Tracking", "Balanced"), "blocking": pref("Blocking", true)] as [String: Any],
   "windows": screens, "title": window.title, "width": window.frame.width, "height": window.frame.height, "left": spot.left, "top": spot.top,
   "tabs": tabs.map { t -> [String: Any] in [
    "Id": t.id, "Title": t.title, "Url": t.url, "Pinned": t.pinned, "Private": t.isPrivate, "InChat": n(t.inChat), "RunChat": n(t.runChat), "ChatId": n(t.chatId),
    "Loading": t.loading, "ready": t.view != nil, "Reader": t.reader, "Blocked": t.blocked, "favicon": !t.favicon.isEmpty, "Secure": t.url.hasPrefix("https://"),
    "CertificateError": false, "suspended": t.view == nil ? NSNull() : false, "activeDownloads": 0, "memory": NSNull(), "visible": qaVisible(t.view)
   ] },
   "history": history, "bookmarks": bookmarks, "hidden": store.hidden,
   "downloads": downloads.map { ["Path": n($0.path?.path), "status": $0.status, "bytes": $0.task.progress.completedUnitCount] as [String: Any] },
   "profilePrivate": n(active?.isPrivate), "back": n(view?.canGoBack), "forward": n(view?.canGoForward), "processMemory": qaResidentBytes()
  ]
 }

 func qaTabs() -> [String: Any] {
  [
   "layout": pref("TabLayout", "Classic"), "groups": store.groups.map { ["Id": $0.id, "Name": $0.name, "Color": $0.color, "Collapsed": $0.collapsed] }, "picks": store.picks,
   "recent": n(recent?.map(\.id)), "recentIndex": recentIndex,
   "split": ["left": n(splitLeft?.id), "right": n(splitRight?.id), "ratio": splitRatio, "partner": n(partner?.id), "leftWidth": n(splitLeft?.view?.frame.width), "rightWidth": n(splitRight?.view?.frame.width),
             "leftVisible": n(splitLeft?.view.map { !$0.isHiddenOrHasHiddenAncestor }), "rightVisible": n(splitRight?.view.map { !$0.isHiddenOrHasHiddenAncestor })] as [String: Any],
   "windows": browsers.map { b -> [String: Any] in ["id": b.windowId, "active": n(b.active?.id),
    "tabs": b.tabs.map { ["Id": $0.id, "Url": $0.url, "Group": $0.group, "wired": $0.view != nil, "visible": n($0.view.map { !$0.isHiddenOrHasHiddenAncestor && $0.window != nil })] as [String: Any] }] },
   "order": tabs.map(\.id)
  ]
 }
}

// MARK: The socket

private func qaListen() {
 let path = support.appendingPathComponent("qa.sock").path
 var addr = sockaddr_un()
 let bytes = Array(path.utf8)
 guard bytes.count < MemoryLayout.size(ofValue: addr.sun_path) else { NSLog("Still QA: the profile path is too long for a socket: \(path)"); return }
 addr.sun_family = sa_family_t(AF_UNIX)
 addr.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
 withUnsafeMutableBytes(of: &addr.sun_path) { raw in for (index, byte) in bytes.enumerated() { raw[index] = byte } }
 _ = Darwin.unlink(path)
 let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
 let mask = Darwin.umask(0o077)
 let bound = withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
 _ = Darwin.umask(mask)
 guard fd >= 0, bound == 0, Darwin.listen(fd, 8) == 0 else { NSLog("Still QA: couldn't open the test socket"); return }
 _ = signal(SIGPIPE, SIG_IGN)
 try? path.write(to: support.appendingPathComponent("qa-pipe.txt"), atomically: true, encoding: .utf8)
 Thread.detachNewThread {
  while true {
   let client = Darwin.accept(fd, nil, nil)
   if client < 0 { if errno != EINTR { Thread.sleep(forTimeInterval: 0.2) }; continue }
   var uid = uid_t(0), gid = gid_t(0)
   guard Darwin.getpeereid(client, &uid, &gid) == 0, uid == getuid() else { _ = Darwin.close(client); continue }
   Thread.detachNewThread { AgentSocket.serveClient(client, qaHandle) }
  }
 }
}

/// Runs then once the interface has loaded (the shell posts "ready"). On WebKit a page can finish first, and a script
/// run before that lands in the blank document the shell starts with. Gives up with the 30-second timeout.
private func qaWhenReady(_ b: Browser, _ tries: Int = 600, _ then: @escaping () -> Void) {
 if b.ready { then() } else if tries > 0 { DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { qaWhenReady(b, tries - 1, then) } }
}

/// Runs one request on the main thread. Every reply comes within 30 seconds, so a stuck page can't hang a test run.
private func qaHandle(_ line: String, _ reply: @escaping (String) -> Void) {
 let once = Once<String>()
 once.action = reply
 DispatchQueue.main.asyncAfter(deadline: .now() + 30) { once.fire(jsonText(["error": "timed out"])) }
 guard let request = jsonObject(line), let op = request["op"] as? String, let b = browsers.first else { once.fire(jsonText(["error": "bad request"])); return }
 func text(_ key: String) -> String { request[key] as? String ?? "" }
 let done: (Any) -> Void = { once.fire(($0 as? String) ?? qaJson($0)) }
 switch op {
 case "state": done(b.qaState())
 case "tabs": done(b.qaTabs())
 case "served": done(["files": qaServed])
 case "shellEval": qaWhenReady(b) { qaEval(b.shell, text("script"), done) }
 case "eval":
  let tab = request["tab"] != nil ? b.tabs.first { $0.id == text("tab") } : b.shown ?? b.active // the page in view, or a given tab
  guard let view = tab?.view else { done(["error": "unknown operation or no page"]); return }
  qaEval(view, text("script"), done, world: text("world") == "still" ? stillWorld : .page) // world still: where Still's own page scripts run
 case "evalTab":
  guard let view = browsers.lazy.flatMap(\.tabs).first(where: { $0.id == text("id") })?.view else { once.fire(#"{"error":"no page"}"#); return }
  qaEval(view, text("script"), done)
 case "key": done(["ok": qaKey(b, text("key"), text("mods"))])
 case "capture": qaCapture(b, text("name"), (request["scale"] as? NSNumber)?.doubleValue ?? 1, done)
 case "systemTheme":
  qaSystemTheme = text("value") == "Light" ? "Light" : "Dark"
  for browser in browsers { browser.applyTheme(); browser.schedulePublish() }
  done(["ok": true])
 case "checkUpdate": done(["update": NSNull(), "installer": NSNull(), "exists": false]) // no updater on Mac yet
 case "windowAt":
  let x = (request["x"] as? NSNumber)?.doubleValue ?? 0, y = (request["y"] as? NSNumber)?.doubleValue ?? 0
  let point = NSPoint(x: x, y: (NSScreen.screens.first?.frame.maxY ?? 0) - y)
  let found = NSApp.orderedWindows.first { w in w.frame.contains(point) && browsers.contains { $0.window === w } }
  done(["found": n(browsers.first { $0.window === found }?.windowId)])
 case "quit":
  done(["ok": true])
  DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { NSApp.terminate(nil) } // after the reply is on its way
 case "shellCdp" where qaShellInput(b, text("method"), request["parameters"] as? [String: Any] ?? [:]): done(["ok": true])
 case "stageExtension", "stageStorePackage", "stageImport", "stageExternalProfile", "shellCdp", "pageCdp":
  done(["error": "\(op) needs WebView2 (extensions or DevTools), so the Mac app has no such step"])
 default: done(["error": "unknown operation or no page"])
 }
}

/// The DevTools input calls the tests make on Windows, as real AppKit events on the interface: the mouse at CSS pixels
/// from its top left (moved, pressed, released, wheel) and typed text. Anything else isn't on the Mac.
private func qaShellInput(_ b: Browser, _ method: String, _ p: [String: Any]) -> Bool {
 let view: WKWebView = b.shell
 func number(_ key: String) -> CGFloat { CGFloat((p[key] as? NSNumber)?.doubleValue ?? 0) }
 switch method {
 case "Input.insertText":
  b.window.makeFirstResponder(view)
  view.insertText(p["text"] as? String ?? "")
 case "Input.dispatchMouseEvent":
  let at = view.convert(NSPoint(x: number("x"), y: view.isFlipped ? number("y") : view.bounds.height - number("y")), to: nil)
  let kind = p["type"] as? String ?? ""
  if kind == "mouseWheel" {
   guard let wheel = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 2, wheel1: Int32(-number("deltaY")), wheel2: Int32(-number("deltaX")), wheel3: 0) else { return false }
   wheel.location = CGPoint(x: at.x, y: (NSScreen.screens.first?.frame.maxY ?? 0) - at.y) // a wheel event has no window: WebKit reads its screen point as the window point
   guard let event = NSEvent(cgEvent: wheel) else { return false }
   view.scrollWheel(with: event)
   return true
  }
  if kind == "mouseMoved" { // through the app's own event queue and tracking areas, as a real move arrives (the cursor stays put)
   let screen = CGPoint(x: b.window.frame.minX + at.x, y: (NSScreen.screens.first?.frame.maxY ?? 0) - b.window.frame.minY - at.y)
   guard let move = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: screen, mouseButton: .left) else { return false }
   // macOS sends mouse moves only to the active app's key window (no hover in background windows), so hovering brings Still forward
   if b.window.isKeyWindow { move.postToPid(getpid()) } else {
    NSApp.activate(ignoringOtherApps: true)
    b.window.makeKeyAndOrderFront(nil)
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { move.postToPid(getpid()) }
   }
   return true
  }
  let types: [String: NSEvent.EventType] = ["mouseMoved": .mouseMoved, "mousePressed": .leftMouseDown, "mouseReleased": .leftMouseUp]
  guard let type = types[kind], let event = NSEvent.mouseEvent(with: type, location: at, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
   windowNumber: b.window.windowNumber, context: nil, eventNumber: 0, clickCount: type == .mouseMoved ? 0 : 1, pressure: type == .leftMouseDown ? 1 : 0) else { return false }
  switch type { case .leftMouseDown: view.mouseDown(with: event); case .leftMouseUp: view.mouseUp(with: event); default: view.mouseMoved(with: event) }
 default: return false
 }
 return true
}

/// Like WebView2's ExecuteScriptAsync: the script's value as JSON, and null for undefined, promises, nodes or a thrown error.
private func qaEval(_ view: WKWebView, _ script: String, _ done: @escaping (Any) -> Void, world: WKContentWorld = .page) {
 view.evaluateJavaScript(script, in: nil, in: world) { result in done(qaJson(try? result.get())) }
}

private func qaJson(_ value: Any?) -> String {
 func plain(_ value: Any) -> Any {
  let mirror = Mirror(reflecting: value) // undefined arrives as an empty optional inside the Any
  if mirror.displayStyle == .optional { return mirror.children.first.map { plain($0.value) } ?? NSNull() }
  switch value {
  case let list as [Any]: return list.map(plain)
  case let object as [String: Any]: return object.mapValues(plain)
  case let date as Date: return ISO8601DateFormatter().string(from: date)
  case is String, is NSNumber, is NSNull: return value
  default: return "\(value)"
  }
 }
 guard let value else { return "null" }
 guard let data = try? JSONSerialization.data(withJSONObject: plain(value), options: [.fragmentsAllowed, .withoutEscapingSlashes]) else { return "null" }
 return String(decoding: data, as: UTF8.self)
}

// MARK: Keys

/// Presses a shortcut given as Windows key names (WPF Key and ModifierKeys), so the same tests run on both. Control is
/// Command and Alt is Option, except where the Mac binds the command to other keys (the table below). The menu gets it
/// first, as for a real key press; otherwise it goes to the focused view. Returns false for a Command shortcut nothing has.
private var qaForward = DispatchTime.now() // when Still, brought forward for a key, is ready for keys
private var qaQueued = DispatchTime.now() // until then, keys posted earlier may still wait in the event queue
private func qaKey(_ b: Browser, _ key: String, _ mods: String) -> Bool {
 let held = Set(mods.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) })
 let ctrl = held.contains("Control"), alt = held.contains("Alt"), shift = held.contains("Shift")
 var name = key
 var flags: NSEvent.ModifierFlags = []
 switch (key, ctrl, alt, shift) {
 case ("H", true, false, false): name = "Y"; flags = [.command] // history
 case ("J", true, false, false): name = "L"; flags = [.command, .option] // downloads
 case ("B", true, false, true): name = "B"; flags = [.command, .option] // bookmarks
 case ("U", true, false, false): name = "U"; flags = [.command, .option] // view source
 case ("Left", false, true, false): name = "OemOpenBrackets"; flags = [.command] // back
 case ("Right", false, true, false): name = "OemCloseBrackets"; flags = [.command] // forward
 case ("F11", false, false, false): name = "F"; flags = [.command, .control] // full screen
 case ("Tab", true, _, _): flags = shift ? [.control, .shift] : [.control] // the recent-tab switcher keeps Control on the Mac
 default:
  if ctrl { flags.insert(.command) }
  if alt { flags.insert(.option) }
  if shift { flags.insert(.shift) }
 }
 // Virtual key code, and the character the key types.
 let letters = Dictionary(uniqueKeysWithValues: zip("ASDFHGZXCVBQWERYT123465=97-80]OU[IPLJ'K;\\,/NM.`".map(String.init),
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 50].map(UInt16.init)))
 let named: [String: (String, UInt16)] = [
  "Escape": ("\u{1b}", 53), "Tab": ("\t", 48), "Enter": ("\r", 36), "Return": ("\r", 36), "Space": (" ", 49), "Back": ("\u{7f}", 51), "Delete": ("\u{f728}", 117),
  "Left": ("\u{f702}", 123), "Right": ("\u{f703}", 124), "Down": ("\u{f701}", 125), "Up": ("\u{f700}", 126),
  "OemPeriod": (".", 47), "OemComma": (",", 43), "OemPlus": ("=", 24), "Add": ("=", 24), "OemMinus": ("-", 27), "Subtract": ("-", 27),
  "OemOpenBrackets": ("[", 33), "OemCloseBrackets": ("]", 30), "OemQuestion": ("/", 44), "F11": ("\u{f70e}", 103)
 ]
 let typed: (String, UInt16)
 if let known = named[name] { typed = known }
 else if name.count == 2, name.hasPrefix("D"), let digit = name.last.map(String.init), let code = letters[digit] { typed = (digit, code) }
 else if let code = letters[name] { typed = (shift ? name : name.lowercased(), code) }
 else { return false }
 if ["Left", "Right", "Up", "Down", "Delete", "F11"].contains(name) { flags.insert(.function) }
 if ["Left", "Right", "Up", "Down"].contains(name) { flags.insert(.numericPad) }
 guard let down = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: flags, timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: b.window.windowNumber,
                                   context: nil, characters: typed.0, charactersIgnoringModifiers: typed.0, isARepeat: false, keyCode: typed.1) else { return false }
 // A shortcut waits behind keys still queued, as a typed one would; posted, it reaches the menu bar the same way.
 let queued = qaQueued > .now()
 if !queued, NSApp.mainMenu?.performKeyEquivalent(with: down) == true { return true }
 if !queued, flags.contains(.command) { return false }
 // Queued like a real key press, so event monitors see it. Keys reach only the active app's key window, so a key brings
 // Still forward first, and the keys sent meanwhile wait their turn.
 if !b.window.isKeyWindow && qaForward < .now() {
  NSApp.activate(ignoringOtherApps: true)
  b.window.makeKeyAndOrderFront(nil)
  qaForward = .now() + 0.25
 }
 qaQueued = max(qaForward, .now()) + 0.2
 DispatchQueue.main.asyncAfter(deadline: max(qaForward, .now())) { NSApp.postEvent(down, atStart: false) }
 return true
}

// MARK: Capture

/// The window as the user sees it: every visible web view (the shell, the page, a split partner), back to front, at
/// the window's size in points (scale 2 for Retina pixels). Saved as a PNG in the profile.
private func qaCapture(_ b: Browser, _ name: String, _ scale: Double, _ done: @escaping (Any) -> Void) {
 func views(_ view: NSView) -> [WKWebView] {
  view.subviews.flatMap { sub -> [WKWebView] in sub.isHidden ? [] : (sub as? WKWebView).map { [$0] } ?? views(sub) }
 }
 let root = b.window.contentView!, size = root.bounds.size
 var shots: [(NSImage, NSRect)] = []
 func next(_ rest: ArraySlice<WKWebView>) {
  guard let view = rest.first else { finish(); return }
  view.takeSnapshot(with: nil) { image, _ in
   if let image { shots.append((image, view.convert(view.bounds, to: root))) }
   next(rest.dropFirst())
  }
 }
 func finish() {
  guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale), bitsPerSample: 8, samplesPerPixel: 4,
                                   hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { done(["error": "no image"]); return }
  rep.size = size
  NSGraphicsContext.saveGraphicsState()
  NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
  b.window.backgroundColor.setFill()
  NSRect(origin: .zero, size: size).fill()
  for (image, frame) in shots {
   let flipped = root.isFlipped ? NSRect(x: frame.minX, y: size.height - frame.maxY, width: frame.width, height: frame.height) : frame
   image.draw(in: flipped)
  }
  NSGraphicsContext.restoreGraphicsState()
  let path = support.appendingPathComponent((name as NSString).lastPathComponent.isEmpty ? "capture.png" : (name as NSString).lastPathComponent)
  do { try rep.representation(using: .png, properties: [:])?.write(to: path); done(["path": path.path]) } catch { done(["error": error.localizedDescription]) }
 }
 next(ArraySlice(views(root)))
}
#else
extension Browser {
 func startQa() {}
}
#endif
