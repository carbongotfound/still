// Saved logins (Windows: Vault.cs and MainWindow.Passwords.cs). They live in the Mac's Keychain, one item per profile,
// and fill only on their exact secure website. The login observer runs in Still's own script world, out of the page's reach.
import AppKit
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
}

struct LoginOffer { let id: String, origin: String, username: String, password: String, existingId: String?, expires: Date }

let loginObserver = (try? String(contentsOf: resources.appendingPathComponent("LoginObserver.js"))) ?? ""

/// https, or http on this Mac (localhost).
func isLoginOrigin(_ url: URL) -> Bool { url.scheme == "https" || url.scheme == "http" && ["localhost", "127.0.0.1", "::1", "[::1]"].contains(url.host ?? "") }
/// scheme://host[:port], the way location.origin writes it.
func authority(_ url: URL) -> String? {
 guard let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased() else { return nil }
 let port = url.port.flatMap { (scheme == "https" && $0 == 443) || (scheme == "http" && $0 == 80) ? nil : $0 }
 return "\(scheme)://\(host.contains(":") ? "[\(host)]" : host)" + (port.map { ":\($0)" } ?? "")
}
func authority(_ origin: WKSecurityOrigin) -> String {
 "\(origin.protocol)://\(origin.host.contains(":") ? "[\(origin.host)]" : origin.host)" + (origin.port == 0 ? "" : ":\(origin.port)")
}

extension Browser {
 var offerSave: Bool { pref("OfferPasswordSave", true) }
 var offerUpdate: Bool { pref("OfferPasswordUpdate", true) }
 var autoFill: Bool { pref("AutoFillPasswords", false) }

 func loginOfferData() -> [String: Any]? {
  guard let offer = loginOffer, offer.expires > Date() else { return nil }
  return ["id": offer.id, "origin": offer.origin, "username": offer.username, "update": offer.existingId != nil]
 }

 /// The login observer for a tab's pages, or "" when saving and filling are both off (never in private tabs).
 func loginScript(_ tab: Tab) -> String {
  let capture = offerSave || offerUpdate
  guard !tab.isPrivate, !loginObserver.isEmpty, capture || autoFill else { return "" }
  if tab.loginToken.isEmpty { tab.loginToken = newId() }
  return loginObserver.replacingOccurrences(of: "__STILL_LOGIN_CONFIG__", with: jsonText(["token": tab.loginToken, "capture": capture]))
 }

 func receiveLogin(_ tab: Tab, _ data: [String: Any], _ frame: WKFrameInfo) {
  guard !tab.isPrivate, tab === active, let current = tab.view?.url, isLoginOrigin(current), let origin = authority(current),
        authority(frame.securityOrigin) == origin, data["token"] as? String == tab.loginToken, data["origin"] as? String == origin else { return }
  if data["action"] as? String == "detected" { inspectLogin(tab); return }
  guard data["action"] as? String == "submitted", offerSave || offerUpdate else { return }
  var username = data["username"] as? String ?? ""
  let password = data["password"] as? String ?? ""
  guard (1...8192).contains(password.count), username.count <= 1024 else { return }
  let entries = Vault.read().filter { $0.origin == origin }
  if username.isEmpty && entries.count == 1 { username = entries[0].username }
  let existing = entries.first { $0.username == username }
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

 /// Notes a visible password field, and fills the site's only saved login when automatic filling is on.
 func inspectLogin(_ tab: Tab) {
  guard !closing, !tab.isPrivate, tab === active, !tab.loading, let view = tab.view, let site = view.url, isLoginOrigin(site), let origin = authority(site) else { return }
  view.evaluateJavaScript("[...document.querySelectorAll('input[type=password]')].some(e=>e.getClientRects().length&&!e.disabled)", in: nil, in: stillWorld) { [weak self, weak tab] result in
   guard let self, let tab, case .success(let found as Bool) = result else { return }
   tab.loginDetected = found
   guard found, self.autoFill, !tab.loginFilled else { return }
   let entries = Vault.read().filter { $0.origin == origin }
   if entries.count == 1 { self.fillSavedLogin(entries[0], tab, onlyEmpty: true) { tab.loginFilled = $0 } }
  }
 }

 func fillSavedLogin(_ entry: Login, _ tab: Tab, onlyEmpty: Bool = false, _ done: @escaping (Bool) -> Void) {
  guard let view = tab.view, let site = view.url, isLoginOrigin(site), authority(site) == entry.origin else { done(false); return }
  let payload = jsonText(["origin": entry.origin, "username": entry.username, "password": entry.password, "onlyEmpty": onlyEmpty])
  let script = "((v)=>{if(location.origin!==v.origin)return false;const real=e=>{if(e.disabled||e.readOnly)return false;const r=e.getBoundingClientRect(),c=getComputedStyle(e);if(r.width<24||r.height<10||c.visibility!=='visible'||parseFloat(c.opacity)<0.5)return false;const inView=r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth;return !inView||document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.closest('input')===e};const p=[...document.querySelectorAll('input[type=password]')].find(e=>real(e)&&e.autocomplete!=='new-password');if(!p||(v.onlyEmpty&&p.value))return false;if(p.form&&new URL(p.form.action||location.href,location.href).origin!==v.origin)return false;const root=p.form||document;const inputs=[...root.querySelectorAll('input')].filter(real);const u=inputs.find(e=>e!==p&&['email','text'].includes(e.type)&&(['username','email'].includes(e.autocomplete)||/user|email|login/i.test(e.name+' '+e.id)))||inputs.find(e=>e!==p&&['email','text'].includes(e.type));if(v.onlyEmpty&&u?.value&&u.value!==v.username)return false;function set(e,value){if(!e)return;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}set(u,v.username);set(p,v.password);return true})(" + payload + ")"
  view.evaluateJavaScript(script, in: nil, in: stillWorld) { result in
   if case .success(let filled as Bool) = result { done(filled) } else { done(false) }
  }
 }

 func acceptLoginOffer(_ id: String, _ username: String) {
  guard let offer = loginOffer, offer.id == id, offer.expires > Date(), username.count <= 1024 else { toast("This login suggestion expired. Sign in again to save it."); return }
  if offer.existingId == nil && !offerSave || offer.existingId != nil && !offerUpdate { loginOffer = nil; return }
  var entries = Vault.read()
  let match = entries.firstIndex { $0.origin == offer.origin && $0.username == username }
  // Changing the username must not silently replace a different stored login.
  if let match, entries[match].id != offer.existingId { toast("That username already has a saved login. Manage it in Passwords."); return }
  if let match { entries[match].password = offer.password } else { entries.append(Login(origin: offer.origin, username: username, password: offer.password)) }
  Vault.write(entries)
  loginOffer = nil
  publishBrowserTools("passwords")
  schedulePublish()
  toast("Login saved. It stays in your Mac's Keychain.")
 }
}
