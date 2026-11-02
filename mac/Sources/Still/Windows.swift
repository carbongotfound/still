// Several Still windows in one process (Windows: MainWindow.Windows.cs). They share one saved state (history,
// bookmarks, settings) and each owns its tabs. A tab moves between windows with its live page: no reload, so it keeps
// its scroll, forms, sign-ins and video. Also the profile catalog (ProfileCatalog.cs).
import AppKit
import WebKit

final class TabGroup {
 var id = newId(), name = "", color = "blue", collapsed = false
}

/// What every window shares, saved in the profile's state.json (Windows: SavedState).
final class Store {
 var prefs: [String: Any] = [:]
 var history: [[String: Any]] = []
 var bookmarks: [[String: Any]] = []
 var welcome = true
 var groups: [TabGroup] = []
 var picks: [[String: Any]] = [] // what you typed and the site you picked (never private tabs): Typed, Url, Count, At
 var hidden: [String: [String]] = [:] // elements hidden on a site, by host
}
let store = Store()
/// state.json as read at launch: the windows restore their tabs from it. saveAll keeps its Tabs and ActiveId current.
var savedState: [String: Any] = [:]
var blockingRules: WKContentRuleList?
weak var lastActiveBrowser: Browser?
/// The website data (cookies, storage, cache) of this profile: the system's store for Default, and one of its own for every
/// other profile and for test profiles (macOS 14 and later; before that every profile shares the system's store).
let pageStore: WKWebsiteDataStore = isTemp ? .nonPersistent() : Profiles.dataStore(support)
/// A throwaway profile an MCP agent opened (--temp): it never sees the real cookies or logins, and keeps nothing.
let isTemp = CommandLine.arguments.contains("--temp")

func stillError(_ text: String) -> NSError { NSError(domain: "Still", code: 1, userInfo: [NSLocalizedDescriptionKey: text]) }

func loadStore() {
 if let data = try? Data(contentsOf: support.appendingPathComponent("state.json")), let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { savedState = json }
 store.prefs = savedState["Preferences"] as? [String: Any] ?? [:]
 store.history = savedState["History"] as? [[String: Any]] ?? []
 store.bookmarks = savedState["Bookmarks"] as? [[String: Any]] ?? []
 store.welcome = savedState["Welcome"] as? Bool ?? true
 store.picks = savedState["AddressPicks"] as? [[String: Any]] ?? []
 store.hidden = savedState["Hidden"] as? [String: [String]] ?? [:]
 store.groups = (savedState["Groups"] as? [[String: Any]] ?? []).map { item in
  let group = TabGroup()
  group.id = item["Id"] as? String ?? group.id
  group.name = item["Name"] as? String ?? ""
  group.color = item["Color"] as? String ?? "blue"
  group.collapsed = item["Collapsed"] as? Bool ?? false
  return group
 }
}

/// The saved tabs by window, first window first: the main window takes the first, each other one opens its own window.
/// An older state.json without "Window" is one window.
func savedWindows() -> [[Tab]] {
 guard store.prefs["RestoreTabs"] as? Bool ?? true else { return [] }
 let rows = Dictionary(grouping: savedState["Tabs"] as? [[String: Any]] ?? []) { $0["Window"] as? Int ?? 0 }
 return rows.keys.sorted().map { key in rows[key]!.map { item in
  let tab = Tab()
  tab.id = item["Id"] as? String ?? tab.id
  tab.title = item["Title"] as? String ?? "New tab"
  tab.url = item["Url"] as? String ?? ""
  tab.pinned = item["Pinned"] as? Bool ?? false
  tab.group = item["Group"] as? String ?? ""
  tab.chatId = item["ChatId"] as? String
  tab.inChat = item["InChat"] as? String
  tab.favicon = item["Favicon"] as? String ?? ""
  return tab
 } }
}

/// The other windows from last time, each with its own tabs (the first one's are the main window's).
func restoreOtherWindows() {
 for saved in savedWindows().dropFirst() {
  let first = saved.first { $0.inChat == nil } ?? Tab()
  Browser(moving: first).tabs += saved.filter { $0 !== first }
 }
}

/// Normal windows (not temporary or incognito) closed while another stayed open, for a few seconds: closing them all, one
/// by one or with Option-click on the close button, brings every one back.
var closedWindows: [(at: Date, tabs: [Tab])] = []

/// Every open window's tabs are saved together; closing a window drops its tabs, as in Chrome.
/// The session: each normal window's tabs, numbered by window; never private tabs, a temporary window's or an incognito
/// one's. With only temporary or incognito windows left, or none as Still quits after its last window, it stays as it
/// was. Cmd+Q closes no window first, so every one is saved then.
func saveAll() {
 let normal = browsers.filter { !$0.temporary && !$0.incognito }
 var live = normal.filter { !$0.closing }
 var windows = live.map(\.tabs)
 if live.isEmpty, let last = normal.first { // the last normal window is closing
  // ponytail: "closed in the last 15 s" stands in for a quit signal; closing windows slower than that keeps only the last
  windows = closedWindows.filter { $0.at.timeIntervalSinceNow > -15 }.map(\.tabs) + [last.tabs]
  live = [last]
 }
 if !live.isEmpty {
  let kept = windows.map { $0.filter { !$0.isPrivate } }.filter { !$0.isEmpty }
  let rows: [[String: Any]] = kept.enumerated().flatMap { window, tabs in tabs.map { tab -> [String: Any] in
   var row: [String: Any] = ["Id": tab.id, "Title": tab.title, "Url": tab.url, "Pinned": tab.pinned, "Group": tab.group, "Favicon": tab.favicon, "Window": window]
   if let chat = tab.chatId { row["ChatId"] = chat }
   if let chat = tab.inChat { row["InChat"] = chat }
   return row
  } }
  savedState["Tabs"] = rows
  savedState["ActiveId"] = (live.first { !$0.secondary } ?? live.first)?.active?.id ?? ""
 }
 let rows = savedState["Tabs"] as? [[String: Any]] ?? [], open = browsers.filter { !$0.closing }.flatMap(\.tabs)
 store.groups.removeAll { group in !open.contains { $0.group == group.id } && !rows.contains { $0["Group"] as? String == group.id } }
 let state: [String: Any] = [
  "Preferences": store.prefs, "History": store.history, "Bookmarks": store.bookmarks, "Welcome": store.welcome, "ActiveId": savedState["ActiveId"] ?? "",
  "Tabs": rows,
  "Groups": store.groups.map { ["Id": $0.id, "Name": $0.name, "Color": $0.color, "Collapsed": $0.collapsed] },
  "AddressPicks": store.picks, "Hidden": store.hidden
 ]
 guard JSONSerialization.isValidJSONObject(state), let data = try? JSONSerialization.data(withJSONObject: state, options: .prettyPrinted) else { return }
 try? data.write(to: support.appendingPathComponent("state.json"), options: .atomic)
}

private var saveQueued = false
func saveAllLater() {
 if saveQueued { return }
 saveQueued = true
 DispatchQueue.main.asyncAfter(deadline: .now() + 1) { saveQueued = false; saveAll() }
}

extension Browser {
 /// A separate window where every tab is private (not saved, its own throwaway session).
 func openIncognito() { _ = Browser(incognito: true) }

 /// The other Still window under a screen point (drop target for a dragged tab). When windows overlap, the frontmost wins.
 func windowAt(_ point: NSPoint) -> Browser? {
  let candidates = browsers.filter { $0 !== self && !$0.closing && $0.incognito == incognito && $0.window.isVisible && !$0.window.isMiniaturized && $0.window.frame.contains(point) }
  return NSApp.orderedWindows.lazy.compactMap { window in candidates.first { $0.window === window } }.first ?? candidates.first
 }

 var windowsData: [[String: Any]] {
  browsers.enumerated().filter { $0.element !== self && !$0.element.closing && $0.element.incognito == incognito }.map { ["id": $0.element.windowId, "name": "Window \($0.offset + 1)", "title": $0.element.active?.title ?? ""] }
 }

 /// The interface reports screen points from the top of the main screen; AppKit counts from its bottom.
 func screenPoint(_ x: Double, _ y: Double) -> NSPoint { NSPoint(x: x, y: (NSScreen.screens.first?.frame.maxY ?? 0) - y) }

 /// Moves a tab with its live page to another window, or to a new one (target nil) at point.
 func moveTab(_ tab: Tab, to target: Browser?, at point: NSPoint?) {
  guard let index = tabs.firstIndex(where: { $0 === tab }), target !== self else { return }
  // Tabs stay with windows of their kind, and an incognito chat and its pages stay in the window that holds the chat.
  if let target, target.incognito != incognito { return }
  if incognito && (tab.chatId ?? tab.inChat ?? tab.runChat) != nil { return }
  // Leave this window (not a real close: nothing goes to "reopen closed tab").
  if tab === splitLeft || tab === splitRight { splitLeft = nil; splitRight = nil }
  dropPermissions(tab)
  if upload?.tab === tab { cancelUpload() }
  tab.group = ""
  tabs.remove(at: index)
  tab.observers = []
  tab.view?.removeFromSuperview()
  let rest = tabs.filter { $0.inChat == nil }
  if rest.isEmpty { if secondary { window.close() } else { newTab(prompt: false) } }
  else if active === tab { select(rest[min(index, rest.count - 1)]) }
  layoutPages(); saveLater(); schedulePublish()
  if let target { target.acceptTab(tab) } else { _ = Browser(moving: tab, at: point, incognito: tab.isPrivate && incognito) }
 }

 func acceptTab(_ tab: Tab, announce: Bool = true) {
  guard !closing else { return }
  if window.isMiniaturized { window.deminiaturize(nil) }
  window.makeKeyAndOrderFront(nil)
  if let view = tab.view { view.isHidden = true; root.addSubview(view); watch(tab, view) }
  tabs.append(tab)
  select(tab)
  saveLater()
  if announce { send(["kind": "tabArrived", "id": tab.id]) }
 }
}

/// Browser profiles: each keeps its own tabs, history, logins and website data (ProfileCatalog.cs).
enum Profiles {
 static var catalog: URL { profileHome.appendingPathComponent("profiles.json") }
 static var launchFile: URL { profileHome.appendingPathComponent("launch-profile.txt") }

 static func read() -> [(id: String, name: String)] {
  var list: [(id: String, name: String)] = []
  if let data = try? Data(contentsOf: catalog), let items = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
   for item in items {
    guard let id = item["Id"] as? String, id == "default" || isGuid(id), !list.contains(where: { $0.id == id }) else { continue }
    list.append((id, item["Name"] as? String ?? "Profile"))
   }
  }
  if !list.contains(where: { $0.id == "default" }) { list.insert(("default", "Default"), at: 0) }
  return list
 }
 static func write(_ list: [(id: String, name: String)]) throws {
  let data = try JSONSerialization.data(withJSONObject: list.map { ["Id": $0.id, "Name": $0.name] })
  try data.write(to: catalog, options: .atomic)
 }
 static func isGuid(_ id: String) -> Bool { id.count == 32 && id.allSatisfy { $0.isHexDigit && !$0.isUppercase } }
 static var launchId: String {
  let id = ((try? String(contentsOf: launchFile)) ?? "default").trimmingCharacters(in: .whitespacesAndNewlines)
  return read().contains { $0.id == id } ? id : "default"
 }
 static func setLaunch(_ id: String) throws {
  guard read().contains(where: { $0.id == id }) else { throw stillError("Unknown profile.") }
  try id.write(to: launchFile, atomically: true, encoding: .utf8)
 }
 static func folder(_ id: String) -> URL { id == "default" ? profileHome : profileHome.appendingPathComponent("Profiles").appendingPathComponent(id) }
 static func isCurrent(_ id: String) -> Bool { folder(id).standardizedFileURL.path == support.standardizedFileURL.path }
 static var currentName: String { isTemp ? "Temporary" : read().first { isCurrent($0.id) }?.name ?? "Default" }

 /// Each profile's website data store. Default keeps the system's, so existing sign-ins carry over.
 static func dataStore(_ folder: URL) -> WKWebsiteDataStore {
  guard folder.standardizedFileURL != defaultSupport.standardizedFileURL, #available(macOS 14.0, *) else { return .default() }
  return WKWebsiteDataStore(forIdentifier: storeId(folder))
 }
 /// A profile folder's id (its 32-hex name), or one saved in the folder for test profiles.
 static func storeId(_ folder: URL) -> UUID {
  var name = folder.lastPathComponent
  if isGuid(name) {
   for at in [8, 13, 18, 23] { name.insert("-", at: name.index(name.startIndex, offsetBy: at)) }
   if let id = UUID(uuidString: name) { return id }
  }
  let file = folder.appendingPathComponent("website-data.id")
  if let text = try? String(contentsOf: file), let id = UUID(uuidString: text.trimmingCharacters(in: .whitespacesAndNewlines)) { return id }
  let id = UUID()
  try? id.uuidString.write(to: file, atomically: true, encoding: .utf8)
  return id
 }

 /// Held while this profile is open, so other Still processes can tell (Windows: the instance mutex).
 private static var runningLock: Int32 = -1
 static func holdRunningLock() {
  runningLock = open(support.appendingPathComponent("running.lock").path, O_CREAT | O_RDWR, 0o600)
  if runningLock >= 0 { _ = flock(runningLock, LOCK_EX | LOCK_NB) }
 }
 /// Locks a closed profile so it can't open while it's deleted. nil: it's open somewhere.
 static func lockClosed(_ id: String) -> Int32? {
  let folder = folder(id)
  guard !isCurrent(id) else { return nil }
  guard FileManager.default.fileExists(atPath: folder.path) else { return -1 }
  let handle = open(folder.appendingPathComponent("running.lock").path, O_CREAT | O_RDWR, 0o600)
  guard handle >= 0 else { return -1 }
  if flock(handle, LOCK_EX | LOCK_NB) != 0 { close(handle); return nil }
  return handle
 }
 static func isRunning(_ id: String) -> Bool {
  guard let handle = lockClosed(id) else { return true }
  if handle >= 0 { close(handle) }
  return false
 }

 static func create(_ name: String) throws {
  let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
  guard (1...40).contains(name.count), !name.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { throw stillError("Use a profile name between 1 and 40 characters.") }
  var list = read()
  guard list.count < 30 else { throw stillError("This browser already has 30 profiles.") }
  let id = newId(), folder = folder(id)
  try FileManager.default.createDirectory(at: folder.deletingLastPathComponent(), withIntermediateDirectories: true)
  try checkAncestors(folder.deletingLastPathComponent())
  guard !FileManager.default.fileExists(atPath: folder.path) else { throw stillError("The new profile folder already exists.") }
  try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
  list.append((id, name))
  do { try write(list) } catch { try? FileManager.default.removeItem(at: folder); throw error }
 }

 /// Refuses symlinks anywhere in a tree, or between it and the profile home, before any deletion.
 static func checkTree(_ url: URL) throws {
  try checkAncestors(url)
  guard let items = FileManager.default.enumerator(at: url, includingPropertiesForKeys: [.isSymbolicLinkKey]) else { return }
  for case let item as URL in items where (try? item.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
   throw stillError("Remove the linked folder manually. Still will not follow links when deleting profiles.")
  }
 }
 static func checkAncestors(_ url: URL) throws {
  let home = profileHome.standardizedFileURL.path
  var current = url.standardizedFileURL
  while current.path.count >= home.count {
   if (try? current.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true { throw stillError("Still cannot delete a profile through a linked folder.") }
   if current.path == home { return }
   current.deleteLastPathComponent()
  }
  throw stillError("Invalid profile location.")
 }

 static func delete(_ id: String) throws {
  guard id != "default" else { throw stillError("Default is permanent. Its browsing data can only be reset with confirmation.") }
  var list = read()
  guard isGuid(id), list.contains(where: { $0.id == id }) else { throw stillError("Profile no longer exists.") }
  guard let lock = lockClosed(id) else { throw stillError("Close this profile's window before deleting it.") }
  defer { if lock >= 0 { close(lock) } }
  let folder = folder(id)
  if FileManager.default.fileExists(atPath: folder.path) { try checkTree(folder); try FileManager.default.removeItem(at: folder) }
  Vault.erase(folder)
  if #available(macOS 14.0, *) { WKWebsiteDataStore.remove(forIdentifier: storeId(folder)) { _ in } }
  if launchId == id { try? setLaunch("default") }
  list.removeAll { $0.id == id }
  try write(list)
 }

 static func resetDefault() throws {
  guard let lock = lockClosed("default") else { throw stillError("Open another profile, then close Default before resetting it.") }
  defer { if lock >= 0 { close(lock) } }
  let paths = ["state.json", "Clipboard"].map { profileHome.appendingPathComponent($0) }.filter { FileManager.default.fileExists(atPath: $0.path) }
  for path in paths { try checkTree(path) }
  for path in paths { try FileManager.default.removeItem(at: path) }
  Vault.erase(profileHome)
  if #available(macOS 14.0, *) { dataStore(profileHome).removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) {} }
 }
}

extension Browser {
 func profileData() -> [String: Any] {
  let launch = Profiles.launchId
  return ["current": Profiles.currentName, "profiles": Profiles.read().map { profile -> [String: Any] in
   ["id": profile.id, "name": profile.name, "current": Profiles.isCurrent(profile.id), "launch": profile.id == launch, "permanent": profile.id == "default", "running": Profiles.isRunning(profile.id)]
  }]
 }

 /// Another profile opens as its own Still process, with its own windows.
 func openBrowserProfile(_ id: String) {
  guard let profile = Profiles.read().first(where: { $0.id == id }) else { return }
  if Profiles.isCurrent(id) { closeSheet(); return }
  if Profiles.isRunning(id) { toast("\(profile.name) is already open in its own window."); return }
  let config = NSWorkspace.OpenConfiguration()
  config.createsNewApplicationInstance = true
  config.activates = !isQa
  config.arguments = ["--profile", Profiles.folder(id).path, "--profiles-root", profileHome.path] + (isQa ? ["--qa"] : [])
  NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: config) { _, error in
   DispatchQueue.main.async { self.toast(error == nil ? "Opened \(profile.name) in its own window." : "Couldn't open \(profile.name).") }
  }
 }

 /// Deleting a profile, or resetting Default, needs its name typed in.
 func confirmProfileRemoval(_ id: String, reset: Bool) {
  guard !profileConfirmation else { return }
  guard let profile = Profiles.read().first(where: { $0.id == id }) else { toast("Unknown profile."); return }
  if reset != (id == "default") { toast("Default cannot be deleted. Use Reset Default with confirmation."); return }
  if Profiles.isRunning(id) { toast(id == "default" ? "Open another profile and close Default before resetting it." : "Close this profile's window before deleting it."); return }
  profileConfirmation = true
  let alert = NSAlert()
  alert.messageText = reset ? "Reset Default?" : "Delete \(profile.name)?"
  alert.informativeText = "This permanently removes this profile's passwords, cookies, tabs, bookmarks, and history. Files saved outside its profile folder are kept.\n\nType \(profile.name) to confirm."
  let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
  input.setAccessibilityLabel("Confirm profile name")
  alert.accessoryView = input
  let approve = alert.addButton(withTitle: reset ? "Reset Default" : "Delete profile")
  alert.addButton(withTitle: "Cancel")
  approve.isEnabled = false
  let watcher = NotificationCenter.default.addObserver(forName: NSControl.textDidChangeNotification, object: input, queue: .main) { _ in approve.isEnabled = input.stringValue == profile.name }
  alert.window.initialFirstResponder = input
  alert.beginSheetModal(for: window) { response in
   NotificationCenter.default.removeObserver(watcher)
   if response == .alertFirstButtonReturn && input.stringValue == profile.name {
    do { if reset { try Profiles.resetDefault() } else { try Profiles.delete(id) }; self.toast(reset ? "Default profile reset." : "Profile deleted.") }
    catch { self.toast(error.localizedDescription) }
   }
   self.profileConfirmation = false
   self.publishBrowserTools("profiles")
  }
 }
}
