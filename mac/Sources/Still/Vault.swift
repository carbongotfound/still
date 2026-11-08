// Saved logins (Windows: Vault.cs and MainWindow.Passwords.cs). They live in the Mac's Keychain, one item per profile.
// In pages, LoginObserver.js runs in Still's own script world, out of the page's reach: the key in a field, auto sign-in,
// strong passwords for new accounts, and the Save / Update prompt after signing in. Never in private tabs. AIs never get
// any of it: they can't fill while they drive a tab, what they read is redacted (redactLogins), and a sign-in page
// pauses them for the user.
import AppKit
import CommonCrypto
import CryptoKit
import LocalAuthentication
import Security
import WebKit

struct Login: Codable {
 var id = newId(), origin = "", username = "", password = ""
}

enum Vault {
 /// Test builds keep logins in a file in the test profile, so a Keychain prompt never stops a test run.
 static func file(_ folder: URL) -> URL { folder.appendingPathComponent("logins.qa.json") }
 static func query(_ folder: URL) -> [String: Any] {
  [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "Still logins", kSecAttrAccount as String: folder.standardizedFileURL.path]
 }
 static func read() -> [Login] {
  var data: Data?
  if isQa { data = try? Data(contentsOf: file(support)) } else {
   var query = query(support)
   query[kSecReturnData as String] = true
   query[kSecMatchLimit as String] = kSecMatchLimitOne
   var out: CFTypeRef?
   if SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess { data = out as? Data }
  }
  return data.flatMap { try? JSONDecoder().decode([Login].self, from: $0) } ?? []
 }
 static func write(_ entries: [Login]) {
  guard let data = try? JSONEncoder().encode(entries) else { return }
  if isQa { try? data.write(to: file(support), options: .atomic); return }
  let query = query(support)
  if SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary) == errSecItemNotFound {
   var add = query
   add[kSecValueData as String] = data
   add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
   SecItemAdd(add as CFDictionary, nil)
  }
 }
 /// A deleted or reset profile's logins.
 static func erase(_ folder: URL) {
  if isQa { try? FileManager.default.removeItem(at: file(folder)) } else { SecItemDelete(query(folder) as CFDictionary) }
 }
 /// 24 characters from the system's secure random generator, without look-alikes.
 static func generate() -> String {
  let alphabet = Array("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*-_+")
  return String((0..<24).map { _ in alphabet.randomElement()! })
 }
 static let common: Set<String> = ["password", "123456", "12345678", "123456789", "1234567890", "qwerty", "qwertyuiop", "111111", "123123", "abc123", "iloveyou", "admin",
  "welcome", "letmein", "monkey", "dragon", "football", "baseball", "sunshine", "princess", "password1", "passw0rd", "000000", "654321"]
 /// Short, made of one or two kinds of character, one of the most common, or mostly one character.
 static func weak(_ p: String) -> Bool {
  let kinds = [p.contains { $0.isLowercase }, p.contains { $0.isUppercase }, p.contains { $0.isNumber }, p.contains { !$0.isLetter && !$0.isNumber }].filter { $0 }.count
  return p.count < 8 || p.count < 12 && kinds < 3 || common.contains(p.lowercased()) || Set(p).count <= 3
 }
}

struct LoginOffer { let id: String, origin: String, username: String, password: String, existingId: String?, expires: Date }

let loginObserver = (try? String(contentsOf: resources.appendingPathComponent("LoginObserver.js"))) ?? ""

/// An http or https page: where logins are saved and offered.
func isLoginOrigin(_ url: URL) -> Bool { ["http", "https"].contains(url.scheme?.lowercased() ?? "") && url.host?.isEmpty == false }
/// https, or http on this Mac. Anywhere else, filling a login asks first and auto sign-in stays off.
func secureOrigin(_ url: URL) -> Bool { url.scheme == "https" || url.scheme == "http" && ["localhost", "127.0.0.1", "::1", "[::1]"].contains(url.host ?? "") }
/// scheme://host[:port], the way location.origin writes it.
func authority(_ url: URL) -> String? {
 guard let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased() else { return nil }
 let port = url.port.flatMap { (scheme == "https" && $0 == 443) || (scheme == "http" && $0 == 80) ? nil : $0 }
 return "\(scheme)://\(host.contains(":") ? "[\(host)]" : host)" + (port.map { ":\($0)" } ?? "")
}
func authority(_ origin: WKSecurityOrigin) -> String {
 "\(origin.protocol)://\(origin.host.contains(":") ? "[\(origin.host)]" : origin.host)" + (origin.port == 0 ? "" : ":\(origin.port)")
}
/// An AI is driving this tab right now (not paused for the user), so nothing fills a login here.
func agentDriving(_ tab: Tab) -> Bool {
 guard let key = tab.agentKey, let me = workers[key] else { return false }
 return !me.paused && Date().timeIntervalSince(me.seen) < 120
}
var passwordsVerifiedUntil = Date.distantPast
#if STILL_QA
var qaAuthAnswer = "deny", qaAuthAsks = 0, qaExportPath = ""
#endif

extension Browser {
 var offerSave: Bool { pref("OfferPasswordSave", true) }
 var offerUpdate: Bool { pref("OfferPasswordUpdate", true) }
 var autoFill: Bool { pref("AutoFillPasswords", false) }
 var neverSave: [String] { pref("NeverSavePasswords", [String]()) } // origins where you said Never

 func loginOfferData() -> [String: Any]? {
  guard let offer = loginOffer, offer.expires > Date() else { return nil }
  return ["id": offer.id, "origin": offer.origin, "username": offer.username, "password": offer.password, "update": offer.existingId != nil]
 }

 /// The login helper for a tab's pages (never in private tabs).
 func loginScript(_ tab: Tab) -> String {
  guard !tab.isPrivate, !loginObserver.isEmpty else { return "" }
  if tab.loginToken.isEmpty { tab.loginToken = newId() }
  return loginObserver.replacingOccurrences(of: "__STILL_LOGIN_CONFIG__", with: jsonText(["token": tab.loginToken, "capture": offerSave || offerUpdate]))
 }
 /// A call on the page's login helper, whose name the page reported (only Still's world can see it).
 func callLogin(_ tab: Tab, _ method: String, _ data: [String: Any], _ done: @escaping (Bool) -> Void = { _ in }) {
  guard let view = tab.view, !tab.loginApi.isEmpty else { done(false); return }
  view.evaluateJavaScript("window.\(tab.loginApi)?.\(method)(\(jsonText(data))) === true", in: nil, in: stillWorld) { done((try? $0.get()) as? Bool ?? false) }
 }

 func receiveLogin(_ tab: Tab, _ data: [String: Any], _ frame: WKFrameInfo) {
  guard !tab.isPrivate, let current = tab.view?.url, isLoginOrigin(current), let origin = authority(current),
        authority(frame.securityOrigin) == origin, data["token"] as? String == tab.loginToken, data["origin"] as? String == origin else { return }
  func text(_ key: String) -> String { data[key] as? String ?? "" }
  switch text("action") {
  case "detected":
   guard text("api").range(of: "^__stillLogin[0-9a-f]{16}$", options: .regularExpression) != nil else { return }
   tab.loginApi = text("api")
   offerLogins(tab, origin, text("form"), secureOrigin(current))
  case "fill":
   guard let entry = Vault.read().first(where: { $0.id == text("id") && $0.origin == origin }), !agentDriving(tab), secureOrigin(current) || data["confirmed"] as? Bool == true else { return }
   fillSavedLogin(entry, tab) { tab.loginFilled = $0 }
  case "accounts":
   guard !agentDriving(tab) else { return }
   callLogin(tab, "list", ["accounts": Vault.read().filter { $0.origin == origin }.sorted { $0.username < $1.username }.map { ["id": $0.id, "username": $0.username] }])
  case "covered": toast("This page is covering Still's list of logins, so nothing was filled. You can fill from Passwords instead.")
  case "auto":
   let only = Vault.read().filter { $0.origin == origin }
   guard secureOrigin(current), autoFill, only.count == 1, !tab.loginFilled, !agentDriving(tab) else { return }
   callLogin(tab, "auto", ["username": only[0].username, "password": only[0].password]) { tab.loginFilled = $0 }
  case "generated": saveGenerated(tab, origin, current.host ?? origin, text("username"), text("password"))
  case "username": if (1...1024).contains(text("username").count) { tab.loginUsername = (origin, text("username"), Date()) }
  case "manage": openPanel("passwords", "")
  case "submitted": offerToSave(tab, origin, text("username"), text("password"), text("current"))
  default: break
  }
 }

 /// Tells the page whether this site has saved logins, whether it's insecure, and whether auto sign-in may fill at the first touch.
 func offerLogins(_ tab: Tab, _ origin: String, _ form: String, _ secure: Bool) {
  let entries = Vault.read().filter { $0.origin == origin }.sorted { $0.username < $1.username }
  let auto = secure && autoFill && entries.count == 1 && ["login", "username"].contains(form) && !tab.loginFilled && !agentDriving(tab)
  callLogin(tab, "show", ["saved": !entries.isEmpty, "warn": !secure, "auto": auto])
 }

 func fillSavedLogin(_ entry: Login, _ tab: Tab, _ done: @escaping (Bool) -> Void) {
  guard let site = tab.view?.url, isLoginOrigin(site), authority(site) == entry.origin else { done(false); return }
  callLogin(tab, "fill", ["username": entry.username, "password": entry.password], done)
 }

 /// A strong password Still suggested and the user took: saved at once, so it's never lost.
 func saveGenerated(_ tab: Tab, _ origin: String, _ host: String, _ username: String, _ password: String) {
  guard (8...8192).contains(password.count), username.count <= 1024 else { return }
  var entries = Vault.read()
  var index = username.isEmpty ? entries.firstIndex { $0.id == tab.generatedLogin } : entries.firstIndex { $0.origin == origin && $0.username == username }
  if index == nil { entries.append(Login(origin: origin, username: username)); index = entries.count - 1 }
  entries[index!].password = password
  Vault.write(entries)
  tab.generatedLogin = entries[index!].id
  if panel == "passwords" { publishBrowserTools("passwords") }
  toast("Strong password saved for " + host + ".")
 }

 func offerToSave(_ tab: Tab, _ origin: String, _ username: String, _ password: String, _ current: String) {
  guard offerSave || offerUpdate, (1...8192).contains(password.count), username.count <= 1024, !neverSave.contains(origin) else { return }
  var all = Vault.read()
  let entries = all.filter { $0.origin == origin }
  var username = username
  // A suggested password is saved already: it only needs the username it went with.
  if let made = entries.first(where: { $0.id == tab.generatedLogin }), made.password == password {
   if made.username.isEmpty && !username.isEmpty && !entries.contains(where: { $0.username == username }), let i = all.firstIndex(where: { $0.id == made.id }) {
    all[i].username = username
    Vault.write(all)
   }
   return
  }
  // The second step of a two-step sign-in has no username field: use the one from the first step.
  if username.isEmpty, let first = tab.loginUsername, first.origin == origin, Date().timeIntervalSince(first.at) < 600 { username = first.username }
  let existing = entries.first { $0.username == username } ?? (current.isEmpty ? nil : entries.first { $0.password == current }) ?? (username.isEmpty && entries.count == 1 ? entries[0] : nil)
  if let existing { username = existing.username }
  if existing?.password == password || existing == nil && !offerSave || existing != nil && !offerUpdate { return }
  let offer = LoginOffer(id: newId(), origin: origin, username: username, password: password, existingId: existing?.id, expires: Date().addingTimeInterval(180))
  loginOffer = offer
  DispatchQueue.main.asyncAfter(deadline: .now() + 180) { [weak self] in
   guard let self, !self.closing, self.loginOffer?.id == offer.id else { return }
   self.loginOffer = nil
   self.schedulePublish()
   if self.panel == "passwords" { self.publishBrowserTools("passwords") }
  }
  schedulePublish()
  if panel == "passwords" { publishBrowserTools("passwords") }
 }

 func acceptLoginOffer(_ id: String, _ username: String, _ password: String) {
  guard let offer = loginOffer, offer.id == id, offer.expires > Date(), username.count <= 1024, password.count <= 8192 else { toast("This login suggestion expired. Sign in again to save it."); return }
  if offer.existingId == nil && !offerSave || offer.existingId != nil && !offerUpdate { loginOffer = nil; return }
  var entries = Vault.read()
  let match = entries.firstIndex { $0.origin == offer.origin && $0.username == username }
  // Changing the username must not silently replace a different stored login.
  if let match, offer.existingId != nil, entries[match].id != offer.existingId { toast("That username already has a saved login. Manage it in Passwords."); return }
  var index = match ?? entries.firstIndex { $0.id == offer.existingId }
  if index == nil { entries.append(Login(origin: offer.origin)); index = entries.count - 1 }
  entries[index!].username = username
  entries[index!].password = password.isEmpty ? offer.password : password
  Vault.write(entries)
  loginOffer = nil
  publishBrowserTools("passwords")
  schedulePublish()
  toast(offer.existingId != nil ? "Password updated." : "Password saved. It stays in your Mac's Keychain.")
 }

 func neverSaveLogin(_ id: String) {
  guard let offer = loginOffer, offer.id == id else { return }
  if !neverSave.contains(offer.origin) { prefs["NeverSavePasswords"] = neverSave + [offer.origin] }
  loginOffer = nil
  saveLater(); schedulePublish(); publishBrowserTools("passwords")
  toast("Still won't offer to save passwords on " + (URL(string: offer.origin)?.host ?? offer.origin) + ". You can change that in Passwords.")
 }

 // MARK: Settings → Passwords

 func passwordsData() -> [String: Any] {
  let all = Vault.read()
  let uses = Dictionary(all.map { ($0.password, 1) }, uniquingKeysWith: +)
  return ["vault": all.sorted { (hostName($0.origin), $0.username) < (hostName($1.origin), $1.username) }.map {
           ["id": $0.id, "origin": $0.origin, "username": $0.username, "weak": Vault.weak($0.password), "reused": uses[$0.password, default: 0] > 1] },
          "offer": loginOfferData() ?? NSNull(), "passwordOptions": ["save": offerSave, "fill": autoFill], "never": neverSave]
 }

 /// Touch ID or the Mac's password, at most once a minute, before a password is shown, copied, edited or exported.
 /// macOS shows why as "Still is trying to <why>."
 func verifyUser(_ why: String, _ then: @escaping () -> Void) {
  if Date() < passwordsVerifiedUntil { then(); return }
  let answer = { [weak self] (verified: Bool, unavailable: Bool) in
   if unavailable { self?.toast("To see saved passwords, give your Mac a login password in System Settings → Users & Groups.") }
   guard verified else { return }
   passwordsVerifiedUntil = Date().addingTimeInterval(60)
   then()
  }
  #if STILL_QA
  if isQa { qaAuthAsks += 1; answer(qaAuthAnswer == "allow", qaAuthAnswer == "none"); return }
  #endif
  let context = LAContext()
  var error: NSError?
  guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else { answer(false, true); return }
  context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: why) { ok, _ in DispatchQueue.main.async { answer(ok, false) } }
 }

 func handlePasswordTool(_ op: String, _ data: [String: Any]) -> Bool {
  func text(_ key: String) -> String { data[key] as? String ?? "" }
  switch op {
  case "loginAccept": acceptLoginOffer(text("id"), text("username"), text("password"))
  case "loginNever": neverSaveLogin(text("id"))
  case "loginDismiss": loginOffer = nil; schedulePublish(); publishBrowserTools("passwords")
  case "neverRemove": prefs["NeverSavePasswords"] = neverSave.filter { $0 != text("origin") }; saveLater(); publishBrowserTools("passwords")
  case "passwordPermission":
   let enabled = data["enabled"] as? Bool ?? false
   switch text("feature") {
   case "save": prefs["OfferPasswordSave"] = enabled; prefs["OfferPasswordUpdate"] = enabled; if !enabled { loginOffer = nil }
   case "fill": prefs["AutoFillPasswords"] = enabled
   default: return true
   }
   reinstallPageScripts()
   for browser in browsers { for tab in browser.tabs where !tab.isPrivate { tab.view?.evaluateJavaScript(browser.loginScript(tab), in: nil, in: stillWorld) { _ in } } }
   saveLater(); schedulePublish(); publishBrowserTools("passwords")
  case "vaultReveal", "vaultEdit", "vaultCopy":
   guard let entry = Vault.read().first(where: { $0.id == text("id") }) else { break }
   verifyUser(op == "vaultCopy" ? "copy a saved password" : op == "vaultEdit" ? "edit a saved password" : "show a saved password") { [self] in
    switch op {
    case "vaultReveal": send(["kind": "vaultRevealed", "id": entry.id, "password": entry.password])
    case "vaultEdit": send(["kind": "vaultEditing", "id": entry.id, "origin": entry.origin, "username": entry.username, "password": entry.password])
    default:
     if !isQa { // tests never touch the clipboard
      let board = NSPasteboard.general
      board.clearContents()
      board.setString(entry.password, forType: .string)
      board.setData(Data(), forType: NSPasteboard.PasteboardType("org.nspasteboard.ConcealedType")) // clipboard managers skip it
      let copied = board.changeCount
      DispatchQueue.main.asyncAfter(deadline: .now() + 30) { if board.changeCount == copied { board.clearContents() } }
     }
     toast("Password copied. Your clipboard clears in 30 seconds.")
    }
   }
  case "vaultSave":
   guard let site = URL(string: text("origin").trimmingCharacters(in: .whitespaces)), isLoginOrigin(site), let origin = authority(site) else { toast("Enter the website's full address, like https://example.com."); break }
   guard (1...8192).contains(text("password").count), text("username").count <= 1024 else { toast("Enter a password."); break }
   var entries = Vault.read()
   let same = entries.firstIndex { $0.origin == origin && $0.username == text("username") }
   let editing = text("id").isEmpty ? nil : entries.firstIndex { $0.id == text("id") }
   if let same, let editing, same != editing { toast("That website and username already have a saved password."); break }
   var index = editing ?? same
   if index == nil { entries.append(Login()); index = entries.count - 1 }
   entries[index!].origin = origin; entries[index!].username = text("username"); entries[index!].password = text("password")
   Vault.write(entries)
   publishBrowserTools("passwords"); send(["kind": "vaultSaved"]); toast("Password saved.")
  case "vaultDelete": Vault.write(Vault.read().filter { $0.id != text("id") }); publishBrowserTools("passwords")
  case "vaultFill":
   guard let entry = Vault.read().first(where: { $0.id == text("id") }), let tab = active, let url = tab.view?.url, secureOrigin(url), authority(url) == entry.origin else {
    toast("Open this login's exact secure website before filling it."); break
   }
   fillSavedLogin(entry, tab) { filled in
    if filled { self.closeSheet(); self.toast("Login filled. Check it, then sign in.") } else { self.toast("There's no sign-in form on this page to fill.") }
   }
  case "vaultExport": exportPasswords()
  default: return false
  }
  return true
 }

 /// Every saved password in a CSV file that Chrome, Edge, Firefox and most password managers can import.
 func exportPasswords() {
  let entries = Vault.read()
  guard !entries.isEmpty else { toast("There are no saved passwords to export."); return }
  verifyUser("export your saved passwords") { [self] in
   func write(_ file: URL) {
    func cell(_ v: String) -> String { v.unicodeScalars.contains { ",\"\r\n".unicodeScalars.contains($0) } ? "\"" + v.replacingOccurrences(of: "\"", with: "\"\"") + "\"" : v }
    var csv = "name,url,username,password,note\r\n"
    func text(_ v: String) -> String { v.first.map { "=+-@\t\r".contains($0) } == true ? "'" + v : v } // a spreadsheet runs a cell that starts like this, and a site can choose its username. Passwords stay exact: this file is how they move.
    for v in entries.sorted(by: { $0.origin < $1.origin }) { csv += [text(hostName(v.origin)), v.origin + "/", text(v.username), v.password].map(cell).joined(separator: ",") + ",\r\n" }
    do { try Data(csv.utf8).write(to: file, options: .atomic); toast("Exported \(entries.count) passwords. Anyone who opens that file can read them, so delete it when you're done.") }
    catch { toast("Couldn't save the file: " + error.localizedDescription) }
   }
   #if STILL_QA
   if isQa { if !qaExportPath.isEmpty { write(URL(fileURLWithPath: qaExportPath)) }; return }
   #endif
   let picker = NSSavePanel()
   picker.nameFieldStringValue = "Still passwords.csv"
   picker.message = "Export passwords"
   picker.beginSheetModal(for: window) { if $0 == .OK, let url = picker.url { write(url) } }
  }
 }
}

// MARK: What AIs read

func clip60(_ s: String) -> String {
 let s = s.split(whereSeparator: \.isWhitespace).joined(separator: " ")
 return s.utf16.count > 60 ? String(decoding: Array(s.utf16.prefix(59)), as: UTF16.self) + "…" : s
}
/// Saved logins never reach an AI: a field holding a saved username for this site reads as hidden, and any saved
/// password for it is cut out of the text.
func redactLogins(_ url: String, _ text: String) -> String {
 guard let site = URL(string: url), isLoginOrigin(site), let origin = authority(site) else { return text }
 return redact(Vault.read().filter { $0.origin == origin }, text)
}
func redact(_ logins: [Login], _ text: String) -> String {
 var text = text
 for v in logins {
  if v.password.count >= 4 { text = text.replacingOccurrences(of: v.password, with: "[hidden]").replacingOccurrences(of: clip60(v.password), with: "[hidden]") } // as saved, and as a page's line shows it
  if !v.username.isEmpty { text = text.replacingOccurrences(of: " =" + clip60(v.username), with: " =[saved login, hidden]") }
 }
 return text
}
/// All an AI gets back passes here, errors too, for the logins of every site open now: a reply can be about a page that has just moved on.
@MainActor func redactReply(_ reply: String) -> String {
 let open = Set(browsers.flatMap(\.tabs).compactMap { URL(string: $0.url).flatMap { isLoginOrigin($0) ? authority($0) : nil } })
 let logins = Vault.read().filter { open.contains($0.origin) }
 if logins.isEmpty { return reply }
 func walk(_ value: Any) -> Any {
  if let text = value as? String { return redact(logins, text) }
  if let list = value as? [Any] { return list.map(walk) }
  if let map = value as? [String: Any] { return Dictionary(uniqueKeysWithValues: map.map { ($0.key, $0.key == "image" ? $0.value : walk($0.value)) }) }
  return value
 }
 guard let data = reply.data(using: .utf8), let parsed = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return redact(logins, reply) }
 return jsonText(walk(parsed) as? [String: Any] ?? parsed)
}
/// Fingerprints of this site's saved usernames and passwords, so a screenshot can mask fields that show them (MaskJs).
func loginPrints(_ url: String) -> [Int32] {
 guard let site = URL(string: url), isLoginOrigin(site), let origin = authority(site) else { return [] }
 return Vault.read().filter { $0.origin == origin }.flatMap { [$0.username, $0.password] }.filter { !$0.isEmpty }.map { s in s.utf16.reduce(Int32(0)) { $0 &* 31 &+ Int32($1) } }
}

// MARK: Passwords from other browsers (Windows: ExternalProfileImport.cs)

enum BrowserLogins {
 typealias Found = (logins: [Login], warnings: [String], skipped: Int)
 static let firefoxLocked = "Firefox has a primary password, so Still can't read its saved passwords. In Firefox, open Passwords, choose Export passwords from the menu, and add the file with Passwords CSV."

 /// Firefox encrypts logins.json with a key kept in key4.db. Without a primary password that key opens with an empty
 /// one: PBKDF2 over SHA-1(global salt), then AES-256-CBC (PBES2), as NSS does.
 static func firefox(_ folder: URL) -> Found {
  let keys = folder.appendingPathComponent("key4.db"), file = folder.appendingPathComponent("logins.json")
  guard FileManager.default.fileExists(atPath: keys.path), FileManager.default.fileExists(atPath: file.path) else { return ([], [], 0) }
  guard let meta = try? Browser.blobs(keys, "SELECT item1, item2 FROM metaData WHERE id='password'").first, meta.count == 2,
        pbes2(meta[0], meta[1]) == Array("password-check".utf8),
        let master = (try? Browser.blobs(keys, "SELECT a11 FROM nssPrivate"))?.lazy.compactMap({ $0.first.flatMap { pbes2(meta[0], $0) } }).first else { return ([], [firefoxLocked], 0) }
  guard ((try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) <= 20 * 1024 * 1024, let data = try? Data(contentsOf: file),
        let logins = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["logins"] as? [[String: Any]] else { return ([], [], 0) }
  var found: Found = ([], [], 0)
  func text(_ login: [String: Any], _ key: String) -> String? {
   guard let value = login[key] as? String, let sealed = Data(base64Encoded: value), let plain = decrypt(master, Array(sealed)) else { return nil }
   return String(bytes: plain, encoding: .utf8)
  }
  for login in logins.prefix(5000) {
   guard let url = Browser.safeUrl(login["hostname"] as? String).flatMap(URL.init(string:)), let origin = authority(url),
         let username = text(login, "encryptedUsername"), let password = text(login, "encryptedPassword") else { found.skipped += 1; continue }
   add(&found, origin, username, password)
  }
  return found
 }

 /// Chrome, Edge, Brave, Vivaldi, Opera and Arc encrypt each password and cookie with a key they keep in your Keychain,
 /// so macOS asks you before it shares it with Still. AES-128-CBC with a key from PBKDF2 over it, as Chromium does on the Mac.
 static func chromium(_ folder: URL) -> (found: Found, cookies: [HTTPCookie]) {
  // A browser signed in to an account keeps that account's passwords in Login Data For Account.
  let rows = ["Login Data", "Login Data For Account"].map { folder.appendingPathComponent($0) }.filter { FileManager.default.fileExists(atPath: $0.path) }
   .flatMap { (try? Browser.blobs($0, "SELECT origin_url, username_value, password_value FROM logins WHERE blacklisted_by_user = 0 LIMIT 5000")) ?? [] }
  let jar = [folder.appendingPathComponent("Network/Cookies"), folder.appendingPathComponent("Cookies")].first { FileManager.default.fileExists(atPath: $0.path) }
   .flatMap { try? Browser.blobs($0, "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite, has_expires, (SELECT value FROM meta WHERE key = 'version') FROM cookies LIMIT 20000") } ?? []
  guard !rows.isEmpty || !jar.isEmpty else { return (([], [], 0), []) }
  let names = [("Google/Chrome", "Chrome"), ("Microsoft Edge", "Microsoft Edge"), ("BraveSoftware", "Brave"), ("Vivaldi", "Vivaldi"), ("com.operasoftware.Opera", "Opera"), ("Arc/", "Arc"), ("Chromium", "Chromium")]
  let browser = names.first { folder.path.contains($0.0) }?.1 ?? "Chrome"
  let (secret, status) = safeStorage(browser + " Safe Storage")
  guard let secret else {
   return (([], ["macOS didn't share \(browser)'s key with Still (macOS error \(status)), so its passwords and sign-ins can't come over. Choose \(browser) again and click Always Allow when your Mac asks for your password. Passwords can also come from a CSV file: export them from \(browser) and add the file with Passwords CSV."], 0), [])
  }
  let key = pbkdf2(Array(secret.utf8), Array("saltysalt".utf8), 1003, CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA1), 16)
  var found: Found = ([], [], 0)
  for row in rows {
   let sealed = Array(row[2])
   guard let url = Browser.safeUrl(String(decoding: row[0], as: UTF8.self)).flatMap(URL.init(string:)), let origin = authority(url), sealed.starts(with: Array("v10".utf8)),
         let plain = cbc(CCAlgorithm(kCCAlgorithmAES), key, [UInt8](repeating: 0x20, count: 16), Array(sealed.dropFirst(3))), let password = String(bytes: plain, encoding: .utf8) else { found.skipped += 1; continue }
   add(&found, origin, String(decoding: row[1], as: UTF8.self), password)
  }
  var cookies: [HTTPCookie] = []
  for row in jar { if let cookie = cookie(row, key) { cookies.append(cookie) } else { found.skipped += 1 } }
  return (found, cookies)
 }

 /// A Chromium cookie row (host, name, value, sealed value, path, expiry, secure, HttpOnly, SameSite, has expiry,
 /// database version) as a cookie WebKit can use (Windows: ReadCookies). Expired ones are left out.
 static func cookie(_ row: [Data], _ key: [UInt8]) -> HTTPCookie? {
  func text(_ i: Int) -> String { String(decoding: row[i], as: UTF8.self) }
  var value = text(2)
  if value.isEmpty {
   let sealed = Array(row[3])
   guard sealed.starts(with: Array("v10".utf8)), let plain = cbc(CCAlgorithm(kCCAlgorithmAES), key, [UInt8](repeating: 0x20, count: 16), Array(sealed.dropFirst(3))) else { return nil }
   // Since Chromium's cookie database version 24, a value starts with SHA-256 of its host. That ties it to its site: without it, it might be another site's, moved here.
   guard (Int(text(10)) ?? 0) >= 24, plain.count >= 32, Array(plain.prefix(32)) == Array(SHA256.hash(data: row[0])) else { return nil }
   value = String(decoding: plain.dropFirst(32), as: UTF8.self)
  }
  guard (1...255).contains(text(0).count), text(1).count <= 4096, value.count <= 4096 else { return nil }
  var properties: [HTTPCookiePropertyKey: Any] = [.domain: text(0), .path: text(4).isEmpty ? "/" : text(4), .name: text(1), .value: value]
  if text(9) != "0" {
   // Chromium counts microseconds from 1601.
   let expires = Date(timeIntervalSince1970: (Double(text(5)) ?? 0) / 1_000_000 - 11_644_473_600)
   guard expires > Date() else { return nil }
   properties[.expires] = expires
  }
  if text(6) != "0" { properties[.secure] = "TRUE" }
  if text(7) != "0" { properties[HTTPCookiePropertyKey("HttpOnly")] = "TRUE" }
  if #available(macOS 10.15, *) {
   if text(8) == "1" { properties[.sameSitePolicy] = HTTPCookieStringPolicy.sameSiteLax } else if text(8) == "2" { properties[.sameSitePolicy] = HTTPCookieStringPolicy.sameSiteStrict }
  }
  return HTTPCookie(properties: properties)
 }

 static func add(_ found: inout Found, _ origin: String, _ username: String, _ password: String) {
  if !(1...8192).contains(password.count) || username.count > 1024 || found.logins.contains(where: { $0.origin == origin && $0.username == username }) { found.skipped += 1; return }
  found.logins.append(Login(origin: origin, username: username, password: password))
 }

 /// The browser's key from the Keychain (macOS asks you first), or what macOS answered instead. Test builds take it
 /// from STILL_QA_SAFE_STORAGE.
 static func safeStorage(_ service: String) -> (String?, OSStatus) {
  if isQa { return (qaEnv("STILL_QA_SAFE_STORAGE"), errSecItemNotFound) }
  let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
  var out: CFTypeRef?
  let status = SecItemCopyMatching(query as CFDictionary, &out)
  return ((out as? Data).flatMap { String(data: $0, encoding: .utf8) }, status)
 }

 static let pbes2Oid: [UInt8] = [0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x05, 0x0d] // 1.2.840.113549.1.5.13
 static let desOid: [UInt8] = [0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x03, 0x07] // 1.2.840.113549.3.7, des-ede3-cbc
 static let aesOid: [UInt8] = [0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x01, 0x2a] // 2.16.840.1.101.3.4.1.42, aes256-cbc
 /// A key4.db item: SEQ { SEQ { pbes2, SEQ { SEQ { pbkdf2, SEQ { salt, iterations, ... } }, SEQ { cipher, iv } } }, data }.
 static func pbes2(_ globalSalt: Data, _ item: Data) -> [UInt8]? {
  var der = Der(Array(item))
  guard var outer = der.seq(), var algorithm = outer.seq(), algorithm.next(0x06) == pbes2Oid, var scheme = algorithm.seq(), var kdf = scheme.seq(),
        kdf.next(0x06) != nil, var p = kdf.seq(), let salt = p.next(0x04), let count = p.next(0x02), count.count <= 4,
        var cipher = scheme.seq(), cipher.next(0x06) != nil, let iv = cipher.next(0x04), let data = outer.next(0x04) else { return nil } // Firefox before 75 used 3DES here
  let iterations = count.reduce(0) { $0 << 8 | Int($1) }
  guard (1...10_000_000).contains(iterations) else { return nil }
  let key = pbkdf2(Array(Insecure.SHA1.hash(data: globalSalt)), salt, iterations, CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA256), 32)
  return cbc(CCAlgorithm(kCCAlgorithmAES), key, [0x04, UInt8(iv.count)] + iv, data) // NSS uses the DER-encoded IV
 }
 /// A logins.json value: SEQ { key id, SEQ { cipher, iv }, data }, with 3DES or AES-256.
 static func decrypt(_ master: [UInt8], _ sealed: [UInt8]) -> [UInt8]? {
  var der = Der(sealed)
  guard var outer = der.seq(), outer.next(0x04) != nil, var algorithm = outer.seq(), let oid = algorithm.next(0x06), let iv = algorithm.next(0x04), let data = outer.next(0x04) else { return nil }
  if oid == desOid && master.count >= 24 { return cbc(CCAlgorithm(kCCAlgorithm3DES), Array(master.prefix(24)), iv, data) }
  if oid == aesOid && master.count >= 32 { return cbc(CCAlgorithm(kCCAlgorithmAES), Array(master.prefix(32)), iv, data) }
  return nil
 }

 static func pbkdf2(_ password: [UInt8], _ salt: [UInt8], _ rounds: Int, _ prf: CCPseudoRandomAlgorithm, _ length: Int) -> [UInt8] {
  var out = [UInt8](repeating: 0, count: length)
  _ = CCKeyDerivationPBKDF(CCPBKDFAlgorithm(kCCPBKDF2), password.map { CChar(bitPattern: $0) }, password.count, salt, salt.count, prf, UInt32(rounds), &out, length)
  return out
 }
 static func cbc(_ algorithm: CCAlgorithm, _ key: [UInt8], _ iv: [UInt8], _ data: [UInt8]) -> [UInt8]? {
  var out = [UInt8](repeating: 0, count: data.count + 16), moved = 0
  let status = CCCrypt(CCOperation(kCCDecrypt), algorithm, CCOptions(kCCOptionPKCS7Padding), key, key.count, iv, data, data.count, &out, out.count, &moved)
  return status == kCCSuccess ? Array(out.prefix(moved)) : nil
 }
}

/// Just enough DER to read NSS's encrypted items: each call takes the next element if it has the tag.
struct Der {
 let bytes: [UInt8]
 var at = 0
 init(_ bytes: [UInt8]) { self.bytes = bytes }
 mutating func next(_ tag: UInt8) -> [UInt8]? {
  guard at + 2 <= bytes.count, bytes[at] == tag else { return nil }
  var length = Int(bytes[at + 1]), start = at + 2
  if length & 0x80 != 0 {
   let n = length & 0x7f
   guard (1...3).contains(n), start + n <= bytes.count else { return nil }
   length = bytes[start..<start + n].reduce(0) { $0 << 8 | Int($1) }
   start += n
  }
  guard start + length <= bytes.count else { return nil }
  at = start + length
  return Array(bytes[start..<at])
 }
 mutating func seq() -> Der? { next(0x30).map(Der.init) }
}
