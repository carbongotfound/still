// The shell's browser tools (Windows: MainWindow.BrowserTools.cs, Permissions.cs, FilePaste.cs, Import.cs, Updates.cs and
// parts of Shell.cs): the interface ops main.swift doesn't handle, and the state fields that go with them.
import AppKit
import ImageIO
import ServiceManagement
import Sparkle
import WebKit

extension Browser {
 func toolStateFields() -> [String: Any] {
  var fields: [String: Any] = [
   "groups": store.groups.filter { group in tabs.contains { $0.group == group.id } }.map { ["id": $0.id, "name": $0.name, "color": $0.color, "collapsed": $0.collapsed] },
   "picks": active?.isPrivate == true ? [] : store.picks.map { ["typed": $0["Typed"] ?? "", "url": $0["Url"] ?? "", "count": $0["Count"] ?? 0] },
   "loginOffer": loginOfferData() ?? NSNull(), "permission": permissionData() ?? NSNull(), "update": updateData() ?? NSNull(),
   "sidePanel": NSNull(), "pinnedExtensions": [Any](), "windows": windowsData, "split": NSNull(), "chatPage": NSNull()
  ]
  if let left = splitLeft, let right = splitRight, partner != nil { fields["split"] = ["left": left.id, "right": right.id, "ratio": splitRatio] }
  if active?.chatId != nil, let page = shown { fields["chatPage"] = ["id": page.id, "url": page.url, "title": page.title, "loading": page.loading, "favicon": page.favicon] }
  return fields
 }

 func handleTools(_ op: String, _ data: [String: Any]) -> Bool {
  func text(_ key: String) -> String { data[key] as? String ?? "" }
  func number(_ key: String) -> Double? { (data[key] as? NSNumber)?.doubleValue }
  func flag(_ key: String) -> Bool { data[key] as? Bool ?? false }
  let target = tabs.first { $0.id == text("id") } ?? active
  switch op {
  case "pageHoles":
   let scale = (number("viewportWidth") ?? 0) > 0 ? shell.bounds.width / number("viewportWidth")! : 1
   let spots = (data["spots"] as? [[String: Any]] ?? []).prefix(4).map { spot -> (rect: NSRect, radius: CGFloat) in
    func v(_ key: String) -> CGFloat { CGFloat((spot[key] as? NSNumber)?.doubleValue ?? 0) * scale }
    return (NSRect(x: v("x"), y: v("y"), width: v("width"), height: v("height")), v("radius"))
   }
   holes = (text("tab"), min(12, max(0, CGFloat(number("frame") ?? 0) * scale)), Array(spots))
   cutHoles()
  case "uploadAnswer": answerUpload(text("id"), (data["picked"] as? [NSNumber] ?? []).map(\.intValue), flag("browse"))
  case "permissionAnswer": answerPermission(text("id"), flag("allow"))
  case "recent": switchRecent((data["step"] as? NSNumber)?.intValue ?? 1, held: flag("held"))
  case "recentPick": pickRecent(tabs.first { $0.id == text("id") })
  case "groupNew": if let target { send(["kind": "groupRename", "id": newGroup(target).id]) }
  case "groupAdd": if let target, store.groups.contains(where: { $0.id == text("group") }) { joinGroup(target, text("group")) }
  case "groupRemove": if let target { leaveGroup(target) }
  case "groupSet":
   guard let group = store.groups.first(where: { $0.id == text("group") }) else { break }
   if let name = data["name"] as? String { group.name = String(String(name.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }).prefix(40)).trimmingCharacters(in: .whitespaces) }
   if Browser.groupColors.contains(text("color")) { group.color = text("color") }
   if let collapsed = data["collapsed"] as? Bool { group.collapsed = collapsed }
   saveLater(); publishEverywhere()
  case "groupUngroup": for tab in tabs where tab.group == text("group") { tab.group = "" }; saveLater()
  case "groupClose": for tab in tabs.filter({ $0.group == text("group") }) { close(tab, force: true) }
  case "split": if let target { startSplit(target, right: text("side") != "left") }
  case "splitSwap": if partner != nil { (splitLeft, splitRight) = (splitRight, splitLeft); layoutPages() }
  case "splitRatio": splitRatio = number("ratio").map { min(0.8, max(0.2, $0)) } ?? 0.5; layoutPages()
  case "splitEnd": endSplit()
  case "addressPick": recordPick(text("typed"), text("url"))
  case "tearOff":
   if pref("TabTearOff", false), let target, let x = number("x"), let y = number("y") { let drop = screenPoint(x, y); moveTab(target, to: windowAt(drop), at: drop) }
  case "moveTab": // the tab menu's Move to new window / Move to another window
   let dest = browsers.first { $0.windowId == text("window") && !$0.closing }
   if let target, dest != nil || text("window") == "new" { moveTab(target, to: dest, at: nil) }
  case "reader": closeSheet(); toggleReader()
  case "hide": closeSheet(); pickHidden()
  case "unhide": unhide()
  case "sidebarResize": if let width = number("width") { prefs["SidebarWidth"] = min(360, max(190, width)); saveLater(); publishEverywhere() }
  case "startup": setStartup(flag("enabled"))
  case "startupSettings": if #available(macOS 13.0, *) { SMAppService.openSystemSettingsLoginItems() }
  case "checkUpdate": checkForUpdate(manual: true)
  case "openUpdate":
   if let install = Updater.shared.installNow { install() } // installs it and reopens Still
   else if Updater.shared.started { Updater.shared.controller.updater.checkForUpdates() } // Sparkle's window: what's new, and Install
   else if let url = availableUpdate?.url { newTab(url, prompt: false) } // QA builds don't run Sparkle
  case "releaseNotes": if let url = availableUpdate?.url { newTab(url, prompt: false) }
  case "refreshTools": publishBrowserTools(text("name"))
  case "sitePermission", "sitePermissionsReset":
   guard let tab = active, let origin = URL(string: tab.url).flatMap(authority) else { break }
   var rules = siteRules(tab.isPrivate)
   if op == "sitePermissionsReset" { rules[origin] = nil }
   else if ["Allow", "Ask", "Deny"].contains(text("state")) {
    rules[origin, default: [:]][text("kind")] = text("state") == "Ask" ? nil : text("state")
    if rules[origin]?.isEmpty == true { rules[origin] = nil }
   }
   setSiteRules(tab.isPrivate, rules)
   for each in tabs where each.isPrivate == tab.isPrivate { applySound(each) }
   publishBrowserTools("site")
  case "profileCreate":
   do { try Profiles.create(text("name")) } catch { toast(error.localizedDescription) }
   publishBrowserTools("profiles")
  case "profileOpen": openBrowserProfile(text("id"))
  case "profileLaunch": do { try Profiles.setLaunch(text("id")) } catch { toast(error.localizedDescription) }; publishBrowserTools("profiles")
  case "profileDelete": confirmProfileRemoval(text("id"), reset: false)
  case "profileResetDefault": confirmProfileRemoval("default", reset: true)
  case "importChoose": chooseImport(text("kind"))
  case "importBookmarks": chooseImport("bookmarks")
  case "importConfirm": completeImport(text("id"), replace: flag("replace"))
  case "importCancel": importBatch = nil; publishBrowserTools("import")
  case "exportData": exportBrowserData()
  case "vaultGenerate": send(["kind": "vaultGenerated", "password": Vault.generate()])
  case "cookieDelete":
   if let item = cookieInventory[text("id")] { item.store.delete(item.cookie) { self.publishBrowserTools("cookies") } }
  case "cookieDeleteDomain":
   let doomed = cookieInventory.values.filter { $0.cookie.domain == text("domain") }
   let group = DispatchGroup()
   for item in doomed { group.enter(); item.store.delete(item.cookie) { group.leave() } }
   group.notify(queue: .main) { self.publishBrowserTools("cookies") }
  case "permissionReset":
   var saved = sitePermissions
   saved[text("origin")]?[text("kind")] = nil
   if saved[text("origin")]?.isEmpty == true { saved[text("origin")] = nil }
   prefs["SitePermissions"] = saved; saveLater(); publishBrowserTools("security")
  default: return handlePasswordTool(op, data)
  }
  return true
 }

 /// A browser tools panel's data (Windows: PublishBrowserTools).
 func publishBrowserTools(_ name: String) {
  func reply(_ data: [String: Any]) { send(["kind": "tools", "name": name, "data": data]) }
  switch name {
  case "passwords":
   reply(passwordsData())
  case "profiles": reply(profileData())
  case "import": reply(importData())
  case "extensions": reply(["extensions": [Any](), "downloading": false])
  case "site":
   guard let tab = active, let origin = URL(string: tab.url).flatMap(authority) else { reply([:]); break }
   reply(["origin": origin, "site": hostName(origin), "isPrivate": tab.isPrivate, "states": siteRules(tab.isPrivate)[origin] ?? [:], "inUse": tab.inUse, "off": Browser.siteKindsOff])
  case "security":
   let engine = Bundle(for: WKWebView.self).infoDictionary?["CFBundleShortVersionString"] as? String ?? ""
   reply(["tracking": pref("Tracking", "Balanced"), "reputationRequested": true, "engine": engine,
          "permissions": sitePermissions.sorted { $0.key < $1.key }.flatMap { site in site.value.sorted { $0.key < $1.key }.map { ["origin": site.key, "kind": $0.key, "state": $0.value] } }])
  case "cookies":
   let isPrivate = active?.isPrivate == true
   let cookies = (isPrivate ? privateStore : active?.engine == "Companion" ? companionStore : pageStore).httpCookieStore // the site's cookies in this tab's profile
   cookies.getAllCookies { found in
    self.cookieInventory = [:]
    var rows: [[String: Any]] = []
    for cookie in found.sorted(by: { ($0.domain, $0.name) < ($1.domain, $1.name) }).prefix(2000) {
     let id = newId()
     self.cookieInventory[id] = (cookie, cookies)
     rows.append(["id": id, "name": cookie.name, "domain": cookie.domain, "path": cookie.path, "secure": cookie.isSecure, "httpOnly": cookie.isHTTPOnly, "session": cookie.isSessionOnly])
    }
    reply(["isPrivate": isPrivate, "cookies": rows])
   }
  default: reply([:])
  }
 }

 // MARK: Site permissions

 /// The Permissions button's choices kept per site: origin → kind (Camera, Microphone, Popups, MultipleAutomaticDownloads,
 /// Autoplay) → "Allow" or "Deny"; no entry is Ask.
 var sitePermissions: [String: [String: String]] { pref("SitePermissions", [String: [String: String]]()) }
 /// What WebKit gives no way to allow or refuse: the Permissions button shows these as not available.
 static let siteKindsOff = ["Geolocation", "Notifications", "ClipboardRead", "ScreenShare", "MidiSystemExclusiveMessages", "Usb"]
 /// A private window's rules live only as long as Still runs.
 func siteRules(_ isPrivate: Bool) -> [String: [String: String]] { isPrivate ? privateSitePermissions : sitePermissions }
 func setSiteRules(_ isPrivate: Bool, _ rules: [String: [String: String]]) {
  if isPrivate { privateSitePermissions = rules } else { prefs["SitePermissions"] = rules; saveLater() }
 }
 func siteRule(_ tab: Tab, _ kind: String) -> String? { URL(string: tab.url).flatMap(authority).flatMap { siteRules(tab.isPrivate)[$0]?[kind] } }

 /// Sound on Block mutes the site's tabs; unblocking unmutes only what the rule muted, never the user's own mute.
 /// page: a page just loaded, so its media need muting again.
 func applySound(_ tab: Tab, page: Bool = false) {
  let blocked = siteRule(tab, "Autoplay") == "Deny"
  var changed = false
  if blocked && !tab.muted { tab.muted = true; tab.ruleMuted = true; changed = true }
  else if !blocked && tab.ruleMuted { tab.muted = false; tab.ruleMuted = false; changed = true }
  if changed || page && tab.muted { tab.view?.evaluateJavaScript(muteScript(tab.muted)) }
  if changed { schedulePublish() }
 }

 /// Mutes or unmutes the page's media, and keeps muting any that start later while the tab is muted.
 func muteScript(_ muted: Bool) -> String {
  "window.__stillMuted=\(muted);document.querySelectorAll('video,audio').forEach(m=>m.muted=\(muted));" +
  "if(!window.__stillMuteHook){window.__stillMuteHook=1;addEventListener('play',e=>{if(window.__stillMuted)e.target.muted=true},true)}"
 }

 /// Camera or microphone on: the Permissions button's dot.
 func captureChanged(_ tab: Tab?, _ view: WKWebView) {
  tab?.inUse = [view.cameraCaptureState != .none ? "camera" : nil, view.microphoneCaptureState != .none ? "mic" : nil].compactMap { $0 }.joined(separator: ",")
  schedulePublish()
 }

 /// Shows the request in Still's own permission bar; unanswered requests are denied after 90 seconds or when the tab closes.
 func askPermission(_ tab: Tab, _ origin: WKSecurityOrigin, _ kind: String, _ done: @escaping (Bool) -> Void) {
  let site = authority(origin), kinds = kind == "CameraAndMicrophone" ? ["Camera", "Microphone"] : [kind]
  let saved = kinds.map { siteRules(tab.isPrivate)[site]?[$0] }
  if saved.allSatisfy({ $0 == "Allow" }) { done(true); return }
  if saved.contains("Deny") { done(false); return }
  let label = kind == "Camera" ? "use your camera" : kind == "Microphone" ? "use your microphone" : "use your camera and microphone"
  let pending = PendingPermission(tab: tab, site: origin.host.isEmpty ? "This page" : hostName(site), kind: label)
  pending.answer = { [weak self] allow in
   guard let self else { return }
   self.permissions.removeAll { $0 === pending }
   if !tab.closed {
    var all = self.siteRules(tab.isPrivate)
    for kind in kinds { all[site, default: [:]][kind] = allow ? "Allow" : "Deny" }
    self.setSiteRules(tab.isPrivate, all)
   }
   self.schedulePublish()
   done(allow)
  }
  permissions.append(pending)
  schedulePublish()
  DispatchQueue.main.asyncAfter(deadline: .now() + 90) { [weak pending] in pending?.finish(false) }
 }
 /// A link to another app: Still asks in its permission bar, and remembers yes per site and app. Who asked: a frame answers for
 /// itself. Only a real click by the page itself can be remembered, or use what's remembered.
 func openAppLink(_ tab: Tab, _ url: URL, _ scheme: String, _ action: WKNavigationAction) {
  guard let app = NSWorkspace.shared.urlForApplication(toOpen: url) else { toast("No app on this Mac opens \(scheme): links."); return }
  let origin = action.sourceFrame.securityOrigin, site = origin.host.isEmpty ? "This page" : hostName(authority(origin))
  let own = action.sourceFrame.isMainFrame && action.buttonNumber != 0, key = site + "|" + scheme
  let open = { [weak self] in if isQa { self?.qaAppLinks.append(url.absoluteString) } else { NSWorkspace.shared.open(url) } }
  if own && pref("AllowedAppLinks", [String]()).contains(key) { open(); return }
  let pending = PendingPermission(tab: tab, site: site, kind: "open " + FileManager.default.displayName(atPath: app.path).replacingOccurrences(of: ".app", with: ""))
  pending.answer = { [weak self] allow in
   guard let self else { return }
   self.permissions.removeAll { $0 === pending }
   self.schedulePublish()
   guard allow, !tab.closed else { return }
   if own && !tab.isPrivate { var list = pref("AllowedAppLinks", [String]()); list.append(key); self.prefs["AllowedAppLinks"] = list; self.saveLater() }
   open()
  }
  permissions.append(pending)
  schedulePublish()
  DispatchQueue.main.asyncAfter(deadline: .now() + 90) { [weak pending] in pending?.finish(false) }
 }
 func answerPermission(_ id: String, _ allow: Bool) { permissions.first { $0.id == id }?.finish(allow) }
 func dropPermissions(_ tab: Tab) { for pending in permissions where pending.tab === tab { pending.finish(false) } }
 func permissionData() -> [String: Any]? {
  guard let pending = permissions.first(where: { $0.tab === active }) else { return nil }
  return ["id": pending.id, "site": pending.site, "kind": pending.kind]
 }

 // MARK: Upload card

 // When a site asks for a file, Still opens a card under the button: your recent files that the site accepts, led by the
 // copied image, and "Open a file". The card lives in Still's own interface, so the site only sees the file you pick.
 func offerFiles(_ tab: Tab, _ parameters: WKOpenPanelParameters, _ complete: @escaping ([URL]?) -> Void) {
  cancelUpload()
  let request = UploadRequest(tab: tab, multiple: parameters.allowsMultipleSelection, complete: complete)
  guard tab === shown, ready, !closing, let view = tab.view else { browse(request); return }
  upload = request
  // The button under the mouse anchors the card; the file input it opens says which files the site takes.
  let mouse = view.convert(window.mouseLocationOutsideOfEventStream, from: nil)
  let zoom = view.pageZoom, x = mouse.x / zoom, y = (view.isFlipped ? mouse.y : view.bounds.height - mouse.y) / zoom
  let inside = view.bounds.contains(mouse)
  let find = "((x,y,inside)=>{const e=inside&&document.elementFromPoint(x,y);const b=e&&e.closest('button,label,a,input,[role=button]');const a=document.activeElement;const f=a&&a.type==='file'?a:b&&(b.type==='file'?b:b.control||b.querySelector('input[type=file]'));const r=b?b.getBoundingClientRect():{left:x-1,top:y-1,width:2,height:2};return [r.left,r.top,r.width,r.height,inside?1:0,(f&&f.accept)||'']})(\(x),\(y),\(inside))"
  view.evaluateJavaScript(find, in: nil, in: stillWorld) { [weak self] result in
   guard let self, self.upload === request else { return }
   var anchor: Any = NSNull()
   if case .success(let value as [Any]) = result, value.count == 6 {
    let box = value.prefix(4).map { CGFloat(($0 as? NSNumber)?.doubleValue ?? 0) * zoom }
    request.accept = value[5] as? String ?? ""
    if (value[4] as? NSNumber)?.boolValue == true {
     let origin = view.frame.origin
     anchor = [(origin.x + box[0]) / self.shellRatio, (origin.y + box[1]) / self.shellRatio, box[2] / self.shellRatio, box[3] / self.shellRatio]
    }
   }
   let types = Browser.acceptedTypes(request.accept)
   let copied = (types == nil || types!.contains("png")) ? self.saveClipboardImage() : nil
   DispatchQueue.global(qos: .userInitiated).async {
    let files = Browser.recentFiles(types)
    DispatchQueue.main.async {
     guard self.upload === request else { return }
     request.files = (copied.map { [$0] } ?? []) + files
     func card(_ thumbs: Bool) -> [String: Any] {
      ["kind": "upload", "data": ["id": request.id, "site": hostName(tab.url), "multiple": request.multiple, "anchor": anchor, "files": request.files.enumerated().map { index, file -> [String: Any] in
       let image = Browser.imageTypes.contains(file.pathExtension.lowercased())
       return ["id": index, "name": index == 0 && copied != nil ? "Copied image" : file.lastPathComponent, "copied": index == 0 && copied != nil,
               "type": file.pathExtension.uppercased(), "thumb": thumbs && image ? Browser.thumbnail(file) ?? NSNull() as Any : NSNull()]
      }] as [String: Any]]
     }
     self.send(card(false))
     DispatchQueue.global(qos: .userInitiated).async {
      let withThumbs = card(true)
      DispatchQueue.main.async { if self.upload === request { self.send(withThumbs) } }
     }
    }
   }
  }
 }

 static let imageTypes = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "heic", "avif", "tiff"]
 static let mimeTypes: [String: [String]] = [
  "image/*": imageTypes + ["svg"], "video/*": ["mp4", "webm", "mov", "mkv", "avi", "m4v"], "audio/*": ["mp3", "wav", "m4a", "ogg", "flac", "aac"],
  "image/png": ["png"], "image/jpeg": ["jpg", "jpeg"], "image/jpg": ["jpg", "jpeg"], "image/gif": ["gif"], "image/webp": ["webp"], "image/svg+xml": ["svg"],
  "application/pdf": ["pdf"], "text/plain": ["txt"], "text/csv": ["csv"], "application/json": ["json"], "application/zip": ["zip"]
 ]
 /// The extensions a picker's accept="" allows, or nil when it takes any file (or a type Still doesn't know).
 static func acceptedTypes(_ accept: String) -> Set<String>? {
  var types = Set<String>()
  for token in accept.split(separator: ",").map({ $0.trimmingCharacters(in: .whitespaces).lowercased() }) where !token.isEmpty {
   if token.hasPrefix(".") { types.insert(String(token.dropFirst())) } else if let known = mimeTypes[token] { types.formUnion(known) } else { return nil }
  }
  return types.isEmpty ? nil : types
 }
 /// The newest accepted files at the top of Desktop, Downloads, Documents and Pictures (test builds: the profile's QaFiles folder).
 static func recentFiles(_ types: Set<String>?) -> [URL] {
  let home = FileManager.default.homeDirectoryForCurrentUser
  let folders = isQa ? [support.appendingPathComponent("QaFiles")] : ["Desktop", "Downloads", "Documents", "Pictures", "Pictures/Screenshots"].map { home.appendingPathComponent($0) }
  let keys: [URLResourceKey] = [.contentModificationDateKey, .isRegularFileKey]
  let files = folders.flatMap { folder in
   ((try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: keys, options: [.skipsHiddenFiles])) ?? []).filter { file in
    (try? file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true && (types?.contains(file.pathExtension.lowercased()) ?? true)
   }
  }
  func date(_ file: URL) -> Date { (try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast }
  return Array(files.sorted { date($0) > date($1) }.prefix(12))
 }
 private static var thumbnails: [String: String] = [:]
 private static let thumbnailLock = NSLock()
 /// A small JPEG preview, cached by path and date so the card opens instantly next time.
 static func thumbnail(_ file: URL) -> String? {
  let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate)?.timeIntervalSince1970 ?? 0
  let key = file.path + "|\(modified)"
  thumbnailLock.lock(); defer { thumbnailLock.unlock() }
  if let cached = thumbnails[key] { return cached }
  guard let source = CGImageSourceCreateWithURL(file as CFURL, nil),
        let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 320, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary),
        let jpeg = NSBitmapImageRep(cgImage: image).representation(using: .jpeg, properties: [.compressionFactor: 0.82]) else { return nil }
  let url = "data:image/jpeg;base64," + jpeg.base64EncodedString()
  thumbnails[key] = url
  return url
 }
 /// The copied image as a PNG the site can upload. Old pastes are cleaned up after a day.
 func saveClipboardImage() -> URL? {
  let board = NSPasteboard.general
  guard board.availableType(from: [.png, .tiff]) != nil, let image = NSImage(pasteboard: board), let tiff = image.tiffRepresentation,
        let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { return nil }
  let folder = support.appendingPathComponent("Clipboard")
  try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
  for old in (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.creationDateKey])) ?? []
  where ((try? old.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? Date()) < Date().addingTimeInterval(-86400) { try? FileManager.default.removeItem(at: old) }
  let stamp = DateFormatter()
  stamp.dateFormat = "yyyy-MM-dd HHmmss"
  let file = folder.appendingPathComponent("Pasted image \(stamp.string(from: Date())).png")
  return (try? png.write(to: file)) == nil ? nil : file
 }

 /// The card's answer: the picked files, "Open a file", or nothing (closed).
 func answerUpload(_ id: String, _ picked: [Int], _ browse: Bool) {
  guard let request = upload, request.id == id else { return }
  upload = nil
  send(["kind": "upload", "data": NSNull()])
  if browse { self.browse(request); return }
  var seen = Set<Int>()
  let files = picked.filter { $0 >= 0 && $0 < request.files.count && seen.insert($0).inserted }.prefix(request.multiple ? 12 : 1).map { request.files[$0] }
  request.finish(files.isEmpty ? nil : files)
 }
 func cancelUpload() {
  guard let request = upload else { return }
  upload = nil
  request.finish(nil)
  send(["kind": "upload", "data": NSNull()])
 }
 func browse(_ request: UploadRequest) {
  let picker = NSOpenPanel()
  picker.allowsMultipleSelection = request.multiple
  picker.canChooseDirectories = false
  picker.beginSheetModal(for: window) { result in request.finish(result == .OK ? picker.urls : nil) }
 }

 // MARK: Updates: GitHub's latest public release, at startup and every 2 hours. Sparkle installs it (see Updater below).

 func startUpdateChecks() {
  guard !isQa else { return }
  Updater.shared.start()
  Timer.scheduledTimer(withTimeInterval: 7200, repeats: true) { [weak self] _ in self?.checkForUpdate() }
  DispatchQueue.main.asyncAfter(deadline: .now() + 15) { [weak self] in self?.checkForUpdate() }
 }
 func checkForUpdate(manual: Bool = false) {
  var request = URLRequest(url: URL(string: "https://api.github.com/repos/carbongotfound/still/releases/latest")!)
  request.setValue("Still/" + currentVersion, forHTTPHeaderField: "User-Agent")
  URLSession(configuration: .ephemeral).dataTask(with: request) { data, response, _ in
   let tag = data.flatMap { jsonObject(String(decoding: $0, as: UTF8.self)) }?["tag_name"] as? String
   DispatchQueue.main.async {
    if let tag, (response as? HTTPURLResponse)?.statusCode == 200, let latest = versionParts(tag) {
     if latest.lexicographicallyPrecedes(versionParts(currentVersion) ?? []) || latest == versionParts(currentVersion) { availableUpdate = nil }
     else if availableUpdate?.version != latest.map(String.init).joined(separator: ".") {
      availableUpdate = (latest.map(String.init).joined(separator: "."), "https://github.com/carbongotfound/still/releases/tag/" + (tag.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? tag))
     }
     if availableUpdate != nil && self.pref("AutoUpdate", true) { Updater.shared.fetch() }
     publishEverywhere()
    }
    if manual && availableUpdate == nil { self.toast("Still is up to date.") }
   }
  }.resume()
 }
 func updateData() -> [String: Any]? {
  guard let update = availableUpdate, !Updater.shared.fetching else { return nil } // the pill waits until Sparkle has it ready
  return ["version": update.version, "current": currentVersion, "ready": Updater.shared.installNow != nil, "progress": 0, "busy": false, "selfUpdate": Updater.shared.started, "downloading": false]
 }

 // MARK: Open at login (macOS 13 and later)

 func setStartup(_ enabled: Bool) {
  if isQa { prefs["QaStartup"] = enabled; saveLater(); return } // tests never change the Mac's login items
  guard #available(macOS 13.0, *) else { toast("Opening at login needs macOS 13 or later."); return }
  do {
   if enabled { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
   if SMAppService.mainApp.status == .requiresApproval { toast("Allow Still in System Settings → General → Login Items."); SMAppService.openSystemSettingsLoginItems() }
  } catch { toast("Couldn't change that: \(error.localizedDescription)") }
 }

 // MARK: Import and export (Windows: MainWindow.Import.cs)

 func chooseImport(_ kind: String) {
  guard ["passwords", "session", "bookmarks"].contains(kind) else { return }
  let picker = NSOpenPanel()
  picker.message = "Import into \(Profiles.currentName)"
  picker.canChooseDirectories = false
  picker.beginSheetModal(for: window) { result in
   guard result == .OK, let url = picker.url else { return }
   do { try self.prepareImport(kind, url); self.openPanel("import", "") } catch { self.toast("Couldn't read this import: \(error.localizedDescription)") }
  }
 }

 static func safeUrl(_ value: String?) -> String? {
  guard let value, value.count <= 8192, let url = URL(string: value.trimmingCharacters(in: .whitespaces)), ["http", "https"].contains(url.scheme?.lowercased() ?? ""),
        url.host?.isEmpty == false, url.user == nil, url.password == nil else { return nil }
  return url.absoluteString
 }

 func prepareImport(_ kind: String, _ file: URL) throws {
  if ((try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) > 10 * 1024 * 1024 { throw stillError("Choose a file smaller than 10 MB.") }
  let data = try Data(contentsOf: file)
  let contents = String(data: data, encoding: .utf8) ?? String(decoding: data, as: UTF8.self)
  let batch = ImportBatch(kind: kind, file: file.lastPathComponent)
  switch kind {
  case "passwords":
   var rows = Browser.csv(contents)
   let header = rows.isEmpty ? [] : rows.removeFirst().map { $0.trimmingCharacters(in: CharacterSet.whitespaces.union(["\u{FEFF}"])).lowercased() }
   func column(_ names: String...) -> Int { header.firstIndex { names.contains($0) } ?? -1 }
   let site = column("url", "origin", "hostname", "login_uri"), user = column("username", "login_username"), secret = column("password", "login_password")
   guard site >= 0, secret >= 0 else { throw stillError("The CSV needs URL and password columns, such as a Chrome, Edge, Firefox, or Bitwarden password export.") }
   for row in rows where row.count > 1 || row.first?.isEmpty == false {
    if batch.logins.count + batch.skipped >= 5000 { throw stillError("Import at most 5,000 logins at a time.") }
    func value(_ i: Int) -> String { i >= 0 && i < row.count ? row[i] : "" }
    let password = value(secret), username = value(user)
    guard let url = Browser.safeUrl(value(site)).flatMap(URL.init(string:)), let origin = authority(url), (1...8192).contains(password.count), username.count <= 1024,
          !batch.logins.contains(where: { $0.origin == origin && $0.username == username }) else { batch.skipped += 1; continue }
    batch.logins.append(Login(origin: origin, username: username, password: password))
   }
  case "session":
   guard let state = jsonObject(contents) else { throw stillError("This is not a Still data file.") }
   func visits(_ key: String, _ limit: Int) -> [[String: Any]] {
    (state[key] as? [[String: Any]] ?? []).compactMap { item in Browser.safeUrl(item["Url"] as? String).map { ["Title": item["Title"] as? String ?? $0, "Url": $0, "At": item["At"] as? String ?? ""] } }.prefix(limit).map { $0 }
   }
   batch.bookmarks = visits("Bookmarks", 5000)
   batch.history = visits("History", 2000)
   batch.tabs = (state["Tabs"] as? [[String: Any]] ?? []).compactMap { item in
    Browser.safeUrl(item["Url"] as? String).map { url in let tab = Tab(); tab.url = url; tab.title = item["Title"] as? String ?? url; tab.pinned = item["Pinned"] as? Bool ?? false; return tab }
   }.prefix(50).map { $0 }
  case "bookmarks":
   func bookmark(_ url: String, _ title: String) throws {
    guard let valid = Browser.safeUrl(url), !batch.bookmarks.contains(where: { $0["Url"] as? String == valid }) else { batch.skipped += 1; return }
    if batch.bookmarks.count >= 5000 { throw stillError("Import at most 5,000 bookmarks at a time.") }
    batch.bookmarks.append(["Url": valid, "Title": String(title.prefix(500))])
   }
   if contents.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("{") {
    func walk(_ node: Any, _ depth: Int) throws {
     guard depth < 64 else { return }
     if let object = node as? [String: Any] {
      if let url = object["url"] as? String { try bookmark(url, object["name"] as? String ?? url) } else { for child in object.values { try walk(child, depth + 1) } }
     } else if let list = node as? [Any] { for child in list { try walk(child, depth + 1) } }
    }
    try walk(try JSONSerialization.jsonObject(with: Data(contents.utf8)), 0)
   } else {
    let pattern = try NSRegularExpression(pattern: "<a\\s+[^>]*href\\s*=\\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", options: [.caseInsensitive, .dotMatchesLineSeparators])
    let source = contents as NSString
    for match in pattern.matches(in: contents, range: NSRange(location: 0, length: source.length)) {
     let title = source.substring(with: match.range(at: 2)).replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
     try bookmark(Browser.htmlDecode(source.substring(with: match.range(at: 1))), Browser.htmlDecode(title))
    }
   }
  default: throw stillError("Unknown import type.")
  }
  importBatch = batch
  publishBrowserTools("import")
 }

 func completeImport(_ id: String, replace: Bool) {
  guard let batch = importBatch, batch.id == id else { return }
  var added = 0, kept = 0
  if batch.kind == "passwords" {
   var entries = Vault.read()
   for login in batch.logins {
    if let index = entries.firstIndex(where: { $0.origin == login.origin && $0.username == login.username }) {
     if replace { entries[index].password = login.password; added += 1 } else { kept += 1 }
    } else { entries.append(login); added += 1 }
   }
   Vault.write(entries)
  } else {
   for item in batch.bookmarks where !bookmarks.contains(where: { $0["Url"] as? String == item["Url"] as? String }) { bookmarks.append(item); added += 1 }
   for item in batch.history where !history.contains(where: { $0["Url"] as? String == item["Url"] as? String && $0["At"] as? String == item["At"] as? String }) { history.append(item) }
   history = Array(history.sorted { ($0["At"] as? String ?? "") > ($1["At"] as? String ?? "") }.prefix(2000))
   for tab in batch.tabs where !tabs.contains(where: { $0.url == tab.url }) { tab.isPrivate = incognito; tabs.append(tab); added += 1 }
   saveLater()
  }
  importBatch = nil
  publishBrowserTools("import")
  toast("Imported \(added) items." + (kept > 0 ? " Kept \(kept) existing logins." : ""))
 }

 func exportBrowserData() {
  let picker = NSSavePanel()
  picker.nameFieldStringValue = "Still data.json"
  picker.message = "Export tabs, bookmarks, and history"
  picker.beginSheetModal(for: window) { result in
   guard result == .OK, let url = picker.url else { return }
   saveAll()
   do {
    if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    try FileManager.default.copyItem(at: support.appendingPathComponent("state.json"), to: url)
    self.toast("Browsing data exported. Passwords and cookies are not included.")
   } catch { self.toast(error.localizedDescription) }
  }
 }

 /// Rows of a CSV file: quoted fields may hold commas, doubled quotes and line breaks.
 static func csv(_ text: String) -> [[String]] {
  var rows: [[String]] = [], row: [String] = [], field = "", quoted = false
  let chars = Array(text)
  var i = 0
  while i < chars.count {
   let c = chars[i]; i += 1
   if quoted {
    if c != "\"" { field.append(c) } else if i < chars.count && chars[i] == "\"" { field.append(c); i += 1 } else { quoted = false }
   } else if c == "\"" { quoted = true }
   else if c == "," { row.append(field); field = "" }
   else if c == "\n" || c == "\r\n" || c == "\r" { row.append(field); rows.append(row); row = []; field = "" }
   else { field.append(c) }
  }
  if !field.isEmpty || !row.isEmpty { row.append(field); rows.append(row) }
  return rows
 }
 static func htmlDecode(_ text: String) -> String {
  var out = text
  for (entity, value) in [("&lt;", "<"), ("&gt;", ">"), ("&quot;", "\""), ("&#39;", "'"), ("&#x27;", "'"), ("&nbsp;", " "), ("&amp;", "&")] { out = out.replacingOccurrences(of: entity, with: value) }
  return out
 }
}

final class PendingPermission {
 let id = newId(), tab: Tab, site: String, kind: String
 var answer: ((Bool) -> Void)?
 init(tab: Tab, site: String, kind: String) { self.tab = tab; self.site = site; self.kind = kind }
 func finish(_ allow: Bool) { let done = answer; answer = nil; done?(allow) }
}

/// A page's file picker, waiting on the upload card. WebKit needs its answer exactly once.
final class UploadRequest {
 let id = newId(), tab: Tab, multiple: Bool
 var files: [URL] = []
 var accept = ""
 private var complete: (([URL]?) -> Void)?
 init(tab: Tab, multiple: Bool, complete: @escaping ([URL]?) -> Void) { self.tab = tab; self.multiple = multiple; self.complete = complete }
 func finish(_ files: [URL]?) { let done = complete; complete = nil; done?(files) }
 deinit { complete?(nil) }
}

final class ImportBatch {
 let id = newId(), kind: String, file: String
 var logins: [Login] = []
 var bookmarks: [[String: Any]] = [], history: [[String: Any]] = []
 var tabs: [Tab] = []
 var skipped = 0
 init(kind: String, file: String) { self.kind = kind; self.file = file }
}

var availableUpdate: (version: String, url: String)?

/// Sparkle (sparkle-project.org) installs updates: it reads the latest release's appcast.xml, downloads Still-mac.zip, checks
/// its EdDSA signature against SUPublicEDKey in Info.plist and swaps the app. Still's GitHub check above says when to look.
/// With Update automatically on it fetches in the background and installs when Still quits, or now from the Update pill;
/// with it off the pill opens Sparkle's own window.
final class Updater: NSObject, SPUUpdaterDelegate {
 static let shared = Updater()
 private(set) lazy var controller = SPUStandardUpdaterController(startingUpdater: false, updaterDelegate: self, userDriverDelegate: nil)
 private(set) var started = false
 private(set) var fetching = false
 private(set) var installNow: (() -> Void)?
 func start() { if !started { controller.startUpdater(); started = true } }
 func fetch() {
  guard started, installNow == nil, !fetching, controller.updater.canCheckForUpdates else { return }
  fetching = true
  controller.updater.checkForUpdatesInBackground()
 }
 func updater(_ updater: SPUUpdater, willInstallUpdateOnQuit item: SUAppcastItem, immediateInstallationBlock immediateInstallHandler: @escaping () -> Void) -> Bool {
  installNow = immediateInstallHandler; fetching = false; publishEverywhere()
  return true // Still offers it on the Update pill; Sparkle installs it anyway when Still quits
 }
 func updater(_ updater: SPUUpdater, didFinishUpdateCycleFor updateCheck: SPUUpdateCheck, error: Error?) {
  if fetching { fetching = false; publishEverywhere() } // nothing to fetch, or it failed: the pill shows, and opens Sparkle's window
 }
 /// Started on another profile folder (tests): reopening would open the Default profile instead, so it doesn't.
 func updaterShouldRelaunchApplication(_ updater: SPUUpdater) -> Bool { argAfter("--profile") == nil && argAfter("--profiles-root") == nil }
}
var currentVersion: String {
 #if STILL_QA
 if let fake = ProcessInfo.processInfo.environment["STILL_QA_VERSION"] { return fake }
 #endif
 return Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
}
/// The release line, "2.10" for 2.10.3: What's New is per release.
var releaseLine: String { currentVersion.split(separator: ".").prefix(2).joined(separator: ".") }
/// "v1.2.3" → [1, 2, 3], padded to three parts.
func versionParts(_ text: String) -> [Int]? {
 let parts = text.trimmingCharacters(in: CharacterSet(charactersIn: "vV")).split(separator: ".").map { Int($0) }
 guard !parts.isEmpty, !parts.contains(where: { $0 == nil }) else { return nil }
 return (parts.compactMap { $0 } + [0, 0, 0]).prefix(3).map { $0 }
}

var startupEnabled: Bool {
 if isQa { return store.prefs["QaStartup"] as? Bool ?? false }
 if #available(macOS 13.0, *) { return SMAppService.mainApp.status == .enabled }
 return false
}
/// Still is in Login Items but switched off there (System Settings → General → Login Items).
var startupDisabled: Bool {
 if !isQa, #available(macOS 13.0, *) { return SMAppService.mainApp.status == .requiresApproval }
 return false
}

var defaultBrowserChecked = Date.distantPast
private var defaultBrowserCached = false
/// Whether Still opens web links, checked at most every few seconds.
var isDefaultBrowser: Bool {
 if Date().timeIntervalSince(defaultBrowserChecked) > 5 {
  let app = NSWorkspace.shared.urlForApplication(toOpen: URL(string: "https://example.com")!)
  defaultBrowserCached = app.flatMap { Bundle(url: $0)?.bundleIdentifier } == Bundle.main.bundleIdentifier
  defaultBrowserChecked = Date()
 }
 return defaultBrowserCached
}
