// Plugins (Windows: MainWindow.Plugins.cs): the user's apps (Gmail, Calendar, Slack…) through Composio, a third-party
// service, with the user's own project API key (ak_…, from Composio's Platform: Settings → Project Settings → API Keys).
// Off until they paste one. For You's Connect key (ck_…) is for Composio's MCP endpoint and the API refuses it: Still says
// so and doesn't keep it. The key is kept like saved logins (sealed for this Mac) and only ever goes to Composio in the x-api-key
// header: never to a file in the clear, a log, memory, the shell, an agent, MCP or a CLI. The shell only hears that there
// is one, and its last four characters. Every app comes from Composio's own catalog, kept in plugin-catalog.json with each
// logo in Cache/PluginLogos. Companions get four small lookups (list_connected_plugins, find_plugins, get_plugin_tools,
// run_plugin_action), so no app's actions sit in their context until they need that app: reads go ahead, anything else
// asks the user first.
import AppKit
import Security

struct PluginAccount { let id: String, slug: String, name: String }
/// One app in Composio's catalog. auth: managed (Composio signs in to it), none (nothing to sign in to) or custom (needs the user's own app at Composio).
struct PluginApp: Codable { let slug: String, name: String, logo: String, cats: [String], auth: String }
struct PluginCatalogSaved: Codable { let at: Date, apps: [PluginApp] } // plugin-catalog.json

var pluginStatus = "off" // off (no key), ok, bad (Composio refused the key), down (no answer)
var pluginKeyProblem = "" // the last key pasted wasn't kept: kind (not a project key), bad (refused) or down (no answer)
var pluginChecking = false
var pluginAccounts: [PluginAccount] = []
var pluginCatalog: [PluginApp]? // nil until read from the cache or Composio
var pluginBySlug: [String: PluginApp] = [:]
var pluginCatalogAt = Date.distantPast
var pluginCatalogLoad: Task<Void, Never>? // the load in progress, which every caller meanwhile waits for
var pluginLogoTried = Set<String>() // logos fetched this session, loaded or not
var pluginConnecting = "", pluginFailed = "", pluginError = "" // the app that didn't connect, and Composio's own words for the last failure
// Keys Composio's API refuses in x-api-key: For You's Connect key (ck_) and the personal one its CLI uses (uak_).
func notProjectKey(_ key: String) -> Bool { key.hasPrefix("ck_") || key.hasPrefix("uak_") }
let composioApi = qaEnv("STILL_QA_COMPOSIO") ?? "https://backend.composio.dev/api/v3.1"
let composioSession: URLSession = { let config = URLSessionConfiguration.ephemeral; config.timeoutIntervalForRequest = 30; config.urlCache = nil; return URLSession(configuration: config) }()
var pluginCatalogFile: URL { support.appendingPathComponent("plugin-catalog.json") }
var pluginLogoFolder: URL { support.appendingPathComponent("Cache/PluginLogos") }
func pluginCap(_ s: String) -> String { s.first?.isLowercase == true ? s.prefix(1).uppercased() + s.dropFirst() : s }
func pluginSlugOk(_ s: String) -> Bool { (1...80).contains(s.utf8.count) && s.unicodeScalars.allSatisfy { "abcdefghijklmnopqrstuvwxyz0123456789_-".unicodeScalars.contains($0) } }
func pluginName(_ slug: String, _ fallback: String = "") -> String { pluginApps()[slug]?.name ?? (fallback.isEmpty ? pluginCap(slug) : fallback) }
func pluginStr(_ node: Any?, _ key: String) -> String { (node as? [String: Any])?[key] as? String ?? "" }
func pluginEscape(_ text: String) -> String { text.addingPercentEncoding(withAllowedCharacters: CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")) ?? "" }
func composioError(_ node: [String: Any]) -> String {
 let message = pluginStr(node["error"], "message")
 return !message.isEmpty ? message : (node["error"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Composio couldn't do that."
}

/// The Composio key, sealed for this Mac like saved logins.
enum PluginKey {
 static var file: URL { support.appendingPathComponent("composio.sealed") }
 static var exists: Bool = FileManager.default.fileExists(atPath: file.path)
 static var savedEnd: String?
 /// The saved key's last four characters, all the shell ever sees of it.
 static var end: String {
  guard exists else { return "" }
  if savedEnd == nil { savedEnd = read().map { $0.count >= 4 ? String($0.suffix(4)) : "" } ?? "" }
  return savedEnd ?? ""
 }
 static func read() -> String? {
  Sealed.read(file).map { String(decoding: $0, as: UTF8.self) }
 }
 static func save(_ key: String) {
  let data = Data(key.utf8)
  exists = true
  savedEnd = String(key.suffix(4))
  Sealed.write(data, file)
 }
 static func erase() {
  exists = false
  savedEnd = nil
  try? FileManager.default.removeItem(at: file)
 }
}
/// Off, cleanly: the key is gone, nothing is connected as far as Still knows, and a sign-in in progress stops. The apps stay
/// connected in the user's Composio account, for when a key comes back.
func forgetPluginKey() { PluginKey.erase(); pluginStatus = "off"; pluginAccounts = []; pluginFailed = ""; pluginError = ""; pluginKeyProblem = "" }

/// One call to Composio, with the saved key or one being tried. Nil when there's no key, or Composio refused it or didn't
/// answer (pluginStatus says which). Other errors come back as Composio's own { error: { message } }.
@MainActor func composio(_ method: String, _ path: String, _ body: [String: Any]? = nil, trying: String? = nil) async -> [String: Any]? {
 guard let key = trying ?? PluginKey.read(), let url = URL(string: composioApi + path) else { pluginStatus = "off"; return nil }
 var request = URLRequest(url: url)
 request.httpMethod = method
 request.setValue(key, forHTTPHeaderField: "x-api-key")
 if let body {
  request.httpBody = try? JSONSerialization.data(withJSONObject: body)
  request.setValue("application/json", forHTTPHeaderField: "Content-Type")
 }
 guard let reply = try? await composioSession.data(for: request), let http = reply.1 as? HTTPURLResponse else { pluginStatus = "down"; return nil }
 if http.statusCode == 401 || http.statusCode == 403 { pluginStatus = "bad"; return nil }
 if http.statusCode >= 500 { pluginStatus = "down"; return nil }
 pluginStatus = "ok"
 if reply.0.isEmpty { return [:] }
 guard let object = (try? JSONSerialization.jsonObject(with: reply.0)) as? [String: Any] else { pluginStatus = "down"; return nil }
 return object
}

/// The catalog by slug: what's cached on disk until Composio's own list comes in.
func pluginApps() -> [String: PluginApp] {
 if pluginCatalog == nil {
  let decoder = JSONDecoder()
  decoder.dateDecodingStrategy = .iso8601
  let saved = (try? Data(contentsOf: pluginCatalogFile)).flatMap { try? decoder.decode(PluginCatalogSaved.self, from: $0) }
  pluginCatalogAt = saved?.at ?? .distantPast
  setPluginCatalog(saved?.apps ?? [])
 }
 return pluginBySlug
}
func setPluginCatalog(_ apps: [PluginApp]) {
 var seen = Set<String>()
 let unique = apps.filter { pluginSlugOk($0.slug) && seen.insert($0.slug).inserted }
 pluginCatalog = unique
 pluginBySlug = Dictionary(uniqueKeysWithValues: unique.map { ($0.slug, $0) })
}
/// One app from Composio's toolkit list. Nil when its slug isn't one Still can use.
func pluginCatalogApp(_ i: [String: Any]) -> PluginApp? {
 let slug = pluginStr(i, "slug").lowercased(), meta = i["meta"] as? [String: Any], name = pluginStr(i, "name")
 var cats: [String] = []
 for c in meta?["categories"] as? [Any] ?? [] {
  let cat = pluginCap((c as? String ?? (pluginStr(c, "name").isEmpty ? pluginStr(c, "id") : pluginStr(c, "name"))).trimmingCharacters(in: .whitespacesAndNewlines))
  if (1..<60).contains(cat.count), !cats.contains(cat), cats.count < 4 { cats.append(cat) }
 }
 let auth = i["no_auth"] as? Bool == true ? "none" : (i["composio_managed_auth_schemes"] as? [Any])?.isEmpty == false ? "managed" : "custom"
 return pluginSlugOk(slug) ? PluginApp(slug: slug, name: name.isEmpty ? pluginCap(slug) : name, logo: pluginStr(meta, "logo"), cats: cats, auth: auth) : nil
}

/// Composio's whole catalog, most used first, page by page. Once a day, or when asked; a list Composio can't give says why.
@MainActor func loadPluginCatalog(force: Bool = false) async {
 if let running = pluginCatalogLoad { return await running.value }
 guard PluginKey.exists, force || pluginApps().isEmpty || Date().timeIntervalSince(pluginCatalogAt) >= 24 * 3600 else { return }
 let load = Task { @MainActor in await fetchPluginCatalog(); pluginCatalogLoad = nil }
 pluginCatalogLoad = load
 await load.value
}
@MainActor func fetchPluginCatalog() async {
 var apps: [PluginApp] = [], cursor = ""
 for _ in 0..<40 {
  let list = await composio("GET", "/toolkits?limit=500&sort_by=usage" + (cursor.isEmpty ? "" : "&cursor=" + pluginEscape(cursor)))
  guard let items = list?["items"] as? [Any] else { pluginError = list.map { "Composio couldn't list its apps: " + composioError($0) } ?? ""; publishAiEverywhere(); return }
  apps += items.compactMap { ($0 as? [String: Any]).flatMap(pluginCatalogApp) }
  cursor = pluginStr(list, "next_cursor")
  if cursor.isEmpty || items.isEmpty { break }
 }
 setPluginCatalog(apps); pluginCatalogAt = Date(); pluginError = ""
 let encoder = JSONEncoder()
 encoder.dateEncodingStrategy = .iso8601
 try? encoder.encode(PluginCatalogSaved(at: pluginCatalogAt, apps: pluginCatalog ?? [])).write(to: pluginCatalogFile, options: .atomic)
 for browser in browsers { browser.sendPluginCatalog() }
 publishAiEverywhere()
}

/// One app's logo as a data: image, from Composio's catalog without the key, kept in Cache/PluginLogos. Nil when it doesn't load.
func fetchPluginLogo(_ app: PluginApp) async -> String? {
 guard app.logo.hasPrefix("https://") || isQa && app.logo.hasPrefix("http://127.0.0.1:"), let url = URL(string: app.logo),
  let reply = try? await composioSession.data(from: url), let http = reply.1 as? HTTPURLResponse, (200..<300).contains(http.statusCode),
  (1...300_000).contains(reply.0.count) else { return nil }
 let bytes = reply.0, head = String(decoding: bytes.prefix(300), as: UTF8.self)
 let type = http.mimeType.flatMap { $0.hasPrefix("image/") ? $0 : nil }
  ?? (head.range(of: "<svg", options: .caseInsensitive) != nil ? "image/svg+xml" : bytes.starts(with: [0x89, 0x50, 0x4E, 0x47]) ? "image/png" : "")
 let uri = "data:\(type);base64,\(bytes.base64EncodedString())"
 guard !type.isEmpty, (try? FileManager.default.createDirectory(at: pluginLogoFolder, withIntermediateDirectories: true)) != nil,
  (try? Data(uri.utf8).write(to: pluginLogoFolder.appendingPathComponent(app.slug), options: .atomic)) != nil else { return nil }
 return uri
}

/// What a companion is told about its plugins: how to look, not what's there.
func pluginInstructions(_ who: Companion?) -> String {
 guard who != nil, PluginKey.exists else { return "" }
 return "\nPlugins: you can work in the user's own apps (email, calendars, chat, docs and hundreds more) through Composio. "
  + "list_connected_plugins names the apps connected for you; find_plugins looks one up by name or category; get_plugin_tools loads one app's actions when you need them; run_plugin_action runs one. "
  + "Reading goes ahead; anything that sends, posts, deletes, pays or changes data waits for the user's OK, and Still asks them for you. "
  + "If you need an app that isn't connected, don't guess or work around it: run_plugin_action asks the user to connect it.\n"
}

// Reads go ahead. Anything else might send, post, delete, pay or change data, so it waits for the user. When in doubt, it asks.
let pluginReadVerbs: Set<String> = ["GET", "LIST", "FETCH", "SEARCH", "FIND", "READ", "RETRIEVE", "QUERY", "VIEW", "DESCRIBE", "LOOKUP", "COUNT"]
func pluginReads(_ tool: [String: Any], _ slug: String, _ toolkit: String) -> Bool {
 let tags = (tool["tags"] as? [Any] ?? []).map { "\($0)".lowercased() }
 if tags.contains(where: { $0.contains("destructive") || ["create", "update", "delete", "write", "send"].contains($0) }) { return false }
 let prefix = toolkit.uppercased() + "_"
 return slug.hasPrefix(prefix) && pluginReadVerbs.contains(String(slug.dropFirst(prefix.count).split(separator: "_").first ?? ""))
}

/// A tool's inputs, small enough for the AI: its own schema, or only names, types and short descriptions when that's long.
func pluginInputs(_ schema: Any?) -> Any {
 guard let schema = schema as? [String: Any] else { return NSNull() }
 if let data = try? JSONSerialization.data(withJSONObject: schema), data.count <= 3000 { return schema }
 var props: [String: Any] = [:]
 for (name, p) in (schema["properties"] as? [String: Any] ?? [:]).prefix(40) { props[name] = ["type": pluginStr(p, "type"), "description": clipped(pluginStr(p, "description"), 140)] }
 return ["type": "object", "properties": props, "required": schema["required"] ?? [String]()]
}

/// An app the companion named: its slug, or its name as the catalog or a connected account has it.
func pluginSlug(_ named: String) -> String? {
 let n = named.trimmingCharacters(in: .whitespacesAndNewlines), lower = n.lowercased(), squashed = lower.replacingOccurrences(of: " ", with: "")
 guard (1...80).contains(n.count) else { return nil }
 let apps = pluginApps()
 if apps[lower] != nil || pluginAccounts.contains(where: { $0.slug == lower }) { return lower }
 return pluginCatalog?.first(where: { $0.name.caseInsensitiveCompare(n) == .orderedSame })?.slug
  ?? pluginAccounts.first(where: { $0.name.caseInsensitiveCompare(n) == .orderedSame })?.slug ?? (apps[squashed] != nil ? squashed : nil)
}

extension Browser {
 /// Who the user is to Composio: a random id for this profile, so its connections stay its own.
 var pluginUser: String {
  if let id = prefs["PluginUser"] as? String, !id.isEmpty { return id }
  let id = "still-" + String((0..<16).map { _ in "0123456789abcdef".randomElement()! })
  prefs["PluginUser"] = id; saveLater()
  return id
 }

 @MainActor func refreshPlugins() async {
  guard PluginKey.exists else { pluginStatus = "off"; publishAiEverywhere(); return }
  let list = await composio("GET", "/connected_accounts?user_ids=\(pluginEscape(pluginUser))&statuses=ACTIVE&limit=200")
  if let items = list?["items"] as? [[String: Any]] {
   pluginAccounts = items.map { PluginAccount(id: pluginStr($0, "id"), slug: pluginStr($0["toolkit"], "slug"), name: pluginName(pluginStr($0["toolkit"], "slug"), pluginStr($0["toolkit"], "name"))) }
    .filter { !$0.id.isEmpty && !$0.slug.isEmpty }
  } else if pluginStatus == "bad" { pluginAccounts = [] }
  publishAiEverywhere()
 }

 // Sent on its own, not with every state update: it's hundreds of apps. No logo addresses: the shell only shows images it's handed.
 func sendPluginCatalog() {
  _ = pluginApps() // the one saved on disk until Composio's comes in
  send(["kind": "pluginCatalog", "data": (pluginCatalog ?? []).map { app -> [String: Any] in ["slug": app.slug, "name": app.name, "cats": app.cats, "auth": app.auth] }])
 }

 /// Logos for the apps the page shows, as data: images (the shell loads nothing from the web). Each comes from Composio's
 /// catalog once, without the key, and stays in Cache/PluginLogos. One that doesn't load keeps its initial.
 @MainActor func sendPluginLogos(_ slugs: [String]) async {
  let apps = pluginApps()
  var ready: [String: String] = [:], fetch: [PluginApp] = [], seen = Set<String>()
  for slug in slugs.filter({ seen.insert($0).inserted }).prefix(400) {
   guard let app = apps[slug], !app.logo.isEmpty else { continue }
   let file = pluginLogoFolder.appendingPathComponent(slug)
   if FileManager.default.fileExists(atPath: file.path) { ready[slug] = try? String(contentsOf: file, encoding: .utf8) }
   else if PluginKey.exists && pluginLogoTried.insert(slug).inserted { fetch.append(app) } // nothing new from the web while plugins are off
  }
  if !ready.isEmpty { send(["kind": "pluginLogos", "data": ready]) }
  for start in stride(from: 0, to: fetch.count, by: 8) { // 8 at a time, each batch sent as it lands
   let batch = fetch[start..<min(start + 8, fetch.count)]
   let loads = batch.map { app in Task { await fetchPluginLogo(app) } }
   var done: [String: String] = [:]
   for (app, load) in zip(batch, loads) { done[app.slug] = await load.value }
   if !done.isEmpty { send(["kind": "pluginLogos", "data": done]) }
  }
 }

 /// Composio's own sign-in for one app, in a Still window. True once the account is connected.
 @MainActor func connectPlugin(_ slug: String) async -> Bool {
  guard pluginConnecting.isEmpty, !slug.isEmpty else { return false }
  pluginConnecting = slug; pluginFailed = ""; pluginError = ""; publishAiEverywhere()
  func failed(_ why: [String: Any]?) -> Bool {
   if PluginKey.exists { pluginFailed = slug; pluginError = why.map { pluginName(slug) + " didn't connect: " + composioError($0) } ?? "" }
   return false
  }
  var signIn: Browser?
  defer {
   if let signIn, !signIn.closing, browsers.contains(where: { $0 === signIn }) { signIn.window.close() }
   pluginConnecting = ""; publishAiEverywhere()
  }
  // An app the user set up at Composio themselves first, then Composio's own sign-in.
  let configs = await composio("GET", "/auth_configs?toolkit_slug=" + pluginEscape(slug))
  guard let all = configs?["items"] as? [[String: Any]] else { return failed(configs) }
  let usable = all.filter { pluginStr($0, "status") != "DISABLED" }
  var config = pluginStr(usable.first(where: { $0["is_composio_managed"] as? Bool != true }) ?? usable.first, "id")
  var made: [String: Any]?
  if config.isEmpty { made = await composio("POST", "/auth_configs", ["toolkit": ["slug": slug], "auth_config": ["type": "use_composio_managed_auth"]]); config = pluginStr(made?["auth_config"], "id") }
  guard !config.isEmpty else { return failed(made) }
  let link = await composio("POST", "/connected_accounts/link", ["auth_config_id": config, "user_id": pluginUser])
  let url = pluginStr(link, "redirect_url"), id = pluginStr(link, "connected_account_id")
  guard !id.isEmpty, url.hasPrefix("https://") || isQa && url.hasPrefix("http://127.0.0.1:") else { return failed(link) }
  let tab = Tab()
  tab.url = url; tab.title = "Connect " + pluginName(slug)
  let opened = Browser(moving: tab, temporary: true)
  signIn = opened
  let end = Date().addingTimeInterval(600)
  while Date() < end {
   let closed = opened.closing || !browsers.contains { $0 === opened } // closed by the user: one last look, then stop
   if !closed { try? await Task.sleep(nanoseconds: 1_500_000_000) }
   if !PluginKey.exists { return false } // the key was removed meanwhile
   let account = await composio("GET", "/connected_accounts/" + pluginEscape(id))
   let status = pluginStr(account, "status")
   if status == "ACTIVE" { await refreshPlugins(); return true }
   if closed { return false } // the user closed it: not an error
   if ["FAILED", "EXPIRED", "INACTIVE"].contains(status) || account == nil { return failed(account == nil ? nil : ["error": "the sign-in didn't finish."]) }
  }
  return failed(["error": "the sign-in took too long."])
 }

 func handlePlugins(_ op: String, _ data: [String: Any]) -> Bool {
  switch op {
  // A new key, or one replacing the saved key: checked with Composio first, and only kept if Composio takes it.
  case "pluginKey":
   let key = argText(data, "key").trimmingCharacters(in: .whitespacesAndNewlines)
   guard (8...400).contains(key.count), !key.contains(where: \.isWhitespace) else { break }
   if notProjectKey(key) { pluginKeyProblem = "kind"; publishAiEverywhere(); break } // never sent, never kept
   pluginChecking = true; pluginKeyProblem = ""; publishAiEverywhere()
   let before = pluginStatus
   Task { @MainActor in
    let tried = await composio("GET", "/connected_accounts?user_ids=\(pluginEscape(self.pluginUser))&statuses=ACTIVE&limit=1", trying: key)
    pluginChecking = false
    guard tried != nil else { pluginKeyProblem = pluginStatus == "bad" ? "bad" : "down"; pluginStatus = PluginKey.exists ? before : "off"; publishAiEverywhere(); return }
    PluginKey.save(key)
    await self.refreshPlugins()
    await loadPluginCatalog(force: true)
   }
  case "pluginLink":
   guard argText(data, "to") == "key" else { break }
   let tab = Tab()
   tab.url = (isQa ? ProcessInfo.processInfo.environment["STILL_QA_COMPOSIO_PAGE"] : nil) ?? "https://platform.composio.dev/"
   _ = Browser(moving: tab, temporary: true)
  case "pluginKeyRemove": forgetPluginKey(); publishAiEverywhere()
  case "pluginRefresh":
   sendPluginCatalog()
   let force = data["force"] as? Bool == true
   Task { @MainActor in
    await self.refreshPlugins()
    if pluginStatus == "ok" { await loadPluginCatalog(force: force) }
   }
  case "pluginLogos":
   guard let slugs = data["slugs"] as? [Any] else { break }
   let named = slugs.map { $0 as? String ?? "" }
   Task { @MainActor in await self.sendPluginLogos(named) }
  case "pluginConnect": // can take minutes: the shell doesn't wait
   let slug = argText(data, "slug")
   Task { @MainActor in _ = await self.connectPlugin(slug) }
  case "pluginDisconnect":
   guard let gone = pluginAccounts.first(where: { $0.id == argText(data, "id") }) else { break }
   Task { @MainActor in
    if await composio("DELETE", "/connected_accounts/" + pluginEscape(gone.id)) != nil { pluginAccounts.removeAll { $0.id == gone.id } }
    await self.refreshPlugins()
   }
  case "pluginToggle":
   let slug = argText(data, "slug")
   guard let mate = companions.first(where: { $0.id == argText(data, "companion") }), !slug.isEmpty else { break }
   mate.pluginsOff.removeAll { $0 == slug }
   if data["on"] as? Bool == false { mate.pluginsOff.append(slug) }
   storeCompanions(); publishAiEverywhere()
  default: return false
  }
  return true
 }

 func pluginsPayload() -> [String: Any] {
  ["key": PluginKey.exists, "keyEnd": PluginKey.end, "status": pluginStatus, "checking": pluginChecking, "problem": pluginKeyProblem,
   "connecting": pluginConnecting, "failed": pluginFailed, "error": pluginError, "connected": pluginAccounts.map { ["id": $0.id, "slug": $0.slug, "name": $0.name] }]
 }

 /// All an action will carry, for its card. Past what fits, the card says how much it isn't showing.
 func pluginWhy(_ arguments: [String: Any]) -> String {
  let all = arguments.sorted { $0.key < $1.key }.compactMap { k, v -> String? in
   let shown = v as? String ?? (try? JSONSerialization.data(withJSONObject: v, options: [.fragmentsAllowed, .sortedKeys])).flatMap { String(data: $0, encoding: .utf8) } ?? ""
   return shown.isEmpty ? nil : k + ": " + shown
  }.sorted { $0.count < $1.count }.joined(separator: " · ") // shortest first: a long body can't push the recipient off the card
  return all.count <= 1200 ? all : String(all.prefix(1200)) + " … and \(all.count - 1200) more characters not shown"
 }

 @MainActor func pluginTool(_ who: String, _ tool: String, _ args: [String: Any]) async -> String {
  guard let run = runs[who] else { return agentFail("Plugins are only for Still's own companions.") }
  if run.chat.ephemeral { return agentFail("Connected apps are off in incognito windows. Tell the user if it matters, and do it another way.") }
  guard PluginKey.exists else { return agentFail("Plugins are off: the user hasn't added a Composio API key. Tell them they can turn plugins on in Skills & plugins.") }
  // A helper works for whoever asked: an app any of them has off stays off.
  let team = exchangeOf(run.chat).chain.map { id in companions.first { $0.id == id } }
  func mine(_ slug: String) -> Bool { team.allSatisfy { $0?.pluginsOff.contains(slug) != true } }
  func unavailable() -> String { pluginStatus == "bad" ? "Composio refused the user's key. Tell them to check it in Skills & plugins." : "Composio isn't answering, so plugins are unavailable right now. Do it another way or try later." }

  if tool == "list_connected_plugins" {
   if pluginStatus != "ok" { await refreshPlugins() }
   if pluginStatus == "bad" || pluginStatus == "down" { return agentFail(unavailable()) }
   var names: [String] = []
   for account in pluginAccounts where mine(account.slug) && !names.contains(account.name) { names.append(account.name) }
   return agentOk(names)
  }
  if tool == "find_plugins" {
   await loadPluginCatalog()
   guard !pluginApps().isEmpty else { return agentFail(unavailable()) }
   let query = argText(args, "query").trimmingCharacters(in: .whitespacesAndNewlines), category = argText(args, "category").trimmingCharacters(in: .whitespacesAndNewlines)
   let squashed = query.replacingOccurrences(of: " ", with: "")
   let found = (pluginCatalog ?? []).filter { app in
    (query.isEmpty || app.name.range(of: query, options: .caseInsensitive) != nil || app.slug.range(of: squashed, options: .caseInsensitive) != nil)
     && (category.isEmpty || app.cats.contains { $0.range(of: category, options: .caseInsensitive) != nil })
   }
   return agentOk(["apps": found.prefix(25).map { app -> [String: Any] in ["name": app.name, "categories": app.cats, "connected": pluginAccounts.contains { $0.slug == app.slug } && mine(app.slug)] },
    "more": max(0, found.count - 25)] as [String: Any])
  }

  let named = argText(args, "plugin")
  guard let slug = pluginSlug(named) else { return agentFail("There's no app called “\(clipped(named, 60))”. Call find_plugins to look it up.") }
  let app = pluginName(slug)
  guard mine(slug) else { return agentFail("The user turned \(app) off for you. They can turn it on in Skills & plugins.") }
  if tool == "get_plugin_tools" {
   let query = argText(args, "query").trimmingCharacters(in: .whitespacesAndNewlines)
   guard let list = await composio("GET", "/tools?toolkit_slug=\(pluginEscape(slug))&limit=25" + (query.isEmpty ? "" : "&query=" + pluginEscape(query))) else { return agentFail(unavailable()) }
   let items = (list["items"] as? [Any] ?? []).map { $0 as? [String: Any] ?? [:] }
   let total = list["total_items"] as? Int ?? items.count
   return agentOk(["plugin": app, "connected": pluginAccounts.contains { $0.slug == slug },
    "actions": items.map { t -> [String: Any] in ["action": pluginStr(t, "slug"), "what": clipped(pluginStr(t, "description"), 300), "asksFirst": !pluginReads(t, pluginStr(t, "slug"), slug), "input": pluginInputs(t["input_parameters"])] },
    "more": total > items.count ? "\(total - items.count) more: pass query to narrow it down." as Any : NSNull()] as [String: Any])
  }

  // run_plugin_action
  let action = argText(args, "action").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
  guard (1...120).contains(action.count) else { return agentFail("Pass the action's name from get_plugin_tools, like \(slug.uppercased())_….") }
  guard let info = await composio("GET", "/tools/" + pluginEscape(action)) else { return agentFail(unavailable()) }
  guard pluginStr(info["toolkit"], "slug") == slug else { return agentFail("\(app) has no action called \(action). Call get_plugin_tools to see its actions.") }
  var account = pluginAccounts.first { $0.slug == slug }
  if account == nil {
   // Not connected: a card with a button that connects it, then the work goes on.
   guard await approve(run, "Connect " + app, app, "connect", "You sign in through Composio, in a Still window.", countdown: false) == "connect" else {
    return agentFail("The user didn't connect \(app). Don't ask again unless they bring it up.")
   }
   guard await connectPlugin(slug), let now = pluginAccounts.first(where: { $0.slug == slug }) else { return agentFail(app + " didn't get connected. Tell the user they can connect it in Skills & plugins.") }
   account = now
  }
  let arguments = args["args"] as? [String: Any] ?? [:]
  if !pluginReads(info, action, slug) {
   let name = pluginStr(info, "name"), what = (name.isEmpty ? action : name) + " in " + app
   let answer = await approve(run, what, app, "plugin", pluginWhy(arguments), countdown: false)
   let allowed = ["once", "chat", "always"].contains(answer)
   audit(run.chat, what, app, allowed ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no")
   publishAiEverywhere()
   guard allowed else { return agentFail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't try it again unless they ask.") }
  }
  guard let account, let done = await composio("POST", "/tools/execute/" + pluginEscape(action), ["user_id": pluginUser, "connected_account_id": account.id, "arguments": arguments]) else {
   return agentFail("Composio isn't answering, so it didn't run. Tell the user.")
  }
  guard done["successful"] as? Bool == true else { return agentFail(app + ": " + composioError(done)) }
  let output = done["data"] ?? [String: Any]()
  let text = (try? JSONSerialization.data(withJSONObject: output, options: [.fragmentsAllowed])).map { String(decoding: $0, as: UTF8.self) } ?? ""
  return agentOk(text.count > 40000 ? String(text.prefix(40000)) + "…" : output)
 }
}
