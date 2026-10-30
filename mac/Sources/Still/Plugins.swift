// Plugins (Windows: MainWindow.Plugins.cs): the user's apps (Gmail, Calendar, Slack…) through Composio, a third-party
// service, with the user's own project API key (ak_…, from Composio's Platform: Settings → Project Settings → API Keys).
// Off until they paste one. For You's Connect key (ck_…) is for Composio's MCP endpoint and the API refuses it: Still says
// so and doesn't keep it. The key is kept like saved logins (the Keychain) and
// only ever goes to Composio in the x-api-key header: never to a file in the clear, a log, memory, the shell, an agent,
// MCP or a CLI. Companions get two tools, plugin_tools and use_plugin: reads go ahead, anything else asks the user first.
import AppKit
import Security

struct PluginAccount { let id: String, slug: String, name: String }

var pluginStatus = "off" // off (no key), checking, ok, bad (Composio refused the key), kind (not a project key), down (no answer)
var pluginAccounts: [PluginAccount] = []
var pluginFound: [[String: Any]]? // nil until Composio answers a search
var pluginConnecting = "", pluginFailed = "", pluginError = "" // the app that didn't connect, and Composio's own words for the last failure
// Keys Composio's API refuses in x-api-key: For You's Connect key (ck_) and the personal one its CLI uses (uak_).
func notProjectKey(_ key: String) -> Bool { key.hasPrefix("ck_") || key.hasPrefix("uak_") }
let composioApi = qaEnv("STILL_QA_COMPOSIO") ?? "https://backend.composio.dev/api/v3.1"
let composioSession: URLSession = { let config = URLSessionConfiguration.ephemeral; config.timeoutIntervalForRequest = 30; config.urlCache = nil; return URLSession(configuration: config) }()
// Names for the apps people connect most; Composio's own name for the rest.
let pluginNames = ["gmail": "Gmail", "googlecalendar": "Google Calendar", "slack": "Slack", "notion": "Notion", "github": "GitHub", "googledrive": "Google Drive",
 "linear": "Linear", "hubspot": "HubSpot", "googlesheets": "Google Sheets", "googledocs": "Google Docs", "outlook": "Outlook", "jira": "Jira",
 "asana": "Asana", "trello": "Trello", "airtable": "Airtable", "salesforce": "Salesforce", "zoom": "Zoom", "figma": "Figma", "dropbox": "Dropbox",
 "calendly": "Calendly", "zendesk": "Zendesk", "intercom": "Intercom", "linkedin": "LinkedIn", "stripe": "Stripe"]
func pluginName(_ slug: String, _ fallback: String = "") -> String { pluginNames[slug] ?? (fallback.isEmpty ? slug.prefix(1).uppercased() + slug.dropFirst() : fallback) }
func pluginStr(_ node: Any?, _ key: String) -> String { (node as? [String: Any])?[key] as? String ?? "" }
func pluginEscape(_ text: String) -> String { text.addingPercentEncoding(withAllowedCharacters: CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")) ?? "" }
func composioError(_ node: [String: Any]) -> String {
 let message = pluginStr(node["error"], "message")
 return !message.isEmpty ? message : (node["error"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Composio couldn't do that."
}

/// The Composio key, in the Keychain like saved logins. Test builds keep it in a file in the test profile, so a
/// Keychain prompt never stops a test run.
enum PluginKey {
 static var file: URL { support.appendingPathComponent("composio.qa") }
 static var query: [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "Still Composio key", kSecAttrAccount as String: support.standardizedFileURL.path] }
 static var exists: Bool = isQa ? FileManager.default.fileExists(atPath: file.path) : SecItemCopyMatching(query as CFDictionary, nil) == errSecSuccess
 static func read() -> String? {
  if isQa { return (try? Data(contentsOf: file)).map { String(decoding: $0, as: UTF8.self) } }
  var query = query
  query[kSecReturnData as String] = true
  query[kSecMatchLimit as String] = kSecMatchLimitOne
  var out: CFTypeRef?
  guard SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
  return String(decoding: data, as: UTF8.self)
 }
 static func save(_ key: String) {
  let data = Data(key.utf8)
  exists = true
  if isQa { try? data.write(to: file, options: .atomic); return }
  if SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary) == errSecItemNotFound {
   var add = query
   add[kSecValueData as String] = data
   add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
   SecItemAdd(add as CFDictionary, nil)
  }
 }
 static func erase() {
  exists = false
  if isQa { try? FileManager.default.removeItem(at: file) } else { SecItemDelete(query as CFDictionary) }
 }
}
func forgetPluginKey() { PluginKey.erase(); pluginStatus = "off"; pluginAccounts = []; pluginFound = nil; pluginFailed = ""; pluginError = "" }

/// One call to Composio. Nil when there's no key, or Composio refused it or didn't answer (pluginStatus says which).
/// Other errors come back as Composio's own { error: { message } }.
@MainActor func composio(_ method: String, _ path: String, _ body: [String: Any]? = nil) async -> [String: Any]? {
 guard let key = PluginKey.read(), let url = URL(string: composioApi + path) else { pluginStatus = "off"; return nil }
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

/// What a companion is told about its plugins.
func pluginInstructions(_ who: Companion?) -> String {
 guard let who, PluginKey.exists else { return "" }
 var mine: [String] = []
 for account in pluginAccounts where !who.pluginsOff.contains(account.slug) && !mine.contains(account.name) { mine.append(account.name) }
 return "\nPlugins: you can work in the user's own apps through Composio. " + (mine.isEmpty ? "None are connected for you yet. " : "Connected for you: " + mine.joined(separator: ", ") + ". ")
  + "Call plugin_tools to find a tool, then use_plugin to run it. Reading goes ahead; anything that sends, posts, deletes, pays or changes data waits for the user's OK, and Still asks them for you. "
  + "If you need an app that isn't connected, call use_plugin anyway: Still offers the user a button to connect it.\n"
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
 for (name, p) in (schema["properties"] as? [String: Any] ?? [:]).prefix(40) { props[name] = ["type": pluginStr(p, "type"), "description": String(pluginStr(p, "description").prefix(140))] }
 return ["type": "object", "properties": props, "required": schema["required"] ?? [String]()]
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

 @MainActor func searchPlugins(_ query: String) async {
  let list = await composio("GET", "/toolkits?limit=40&sort_by=usage" + (query.isEmpty ? "" : "&search=" + pluginEscape(query)))
  // Only apps Composio signs in to itself: one click, no developer app of the user's own.
  pluginFound = (list?["items"] as? [[String: Any]] ?? []).filter { ($0["composio_managed_auth_schemes"] as? [Any])?.isEmpty != true }
   .map { ["slug": pluginStr($0, "slug"), "name": pluginName(pluginStr($0, "slug"), pluginStr($0, "name")), "about": pluginStr($0["meta"], "description")] }
  pluginError = list == nil || list?["items"] is [Any] ? "" : composioError(list!) // said, not an empty list
  publishAiEverywhere()
 }

 /// Composio's own sign-in for one app, in a Still window. True once the account is connected.
 @MainActor func connectPlugin(_ slug: String) async -> Bool {
  guard pluginConnecting.isEmpty, !slug.isEmpty else { return false }
  pluginConnecting = slug; pluginFailed = ""; pluginError = ""; publishAiEverywhere()
  func failed(_ why: [String: Any]?) -> Bool { pluginFailed = slug; pluginError = why.map { pluginName(slug) + " didn't connect: " + composioError($0) } ?? ""; return false }
  var signIn: Browser?
  defer {
   if let signIn, !signIn.closing, browsers.contains(where: { $0 === signIn }) { signIn.window.close() }
   pluginConnecting = ""; publishAiEverywhere()
  }
  let configs = await composio("GET", "/auth_configs?is_composio_managed=true&toolkit_slug=" + pluginEscape(slug))
  guard let all = configs?["items"] as? [[String: Any]] else { return failed(configs) }
  var config = pluginStr(all.first { pluginStr($0, "status") != "DISABLED" }, "id")
  var made: [String: Any]?
  if config.isEmpty { made = await composio("POST", "/auth_configs", ["toolkit": ["slug": slug], "auth_config": ["type": "use_composio_managed_auth"]]); config = pluginStr(made?["auth_config"], "id") }
  guard !config.isEmpty else { return failed(made) }
  let link = await composio("POST", "/connected_accounts/link", ["auth_config_id": config, "user_id": pluginUser])
  let url = pluginStr(link, "redirect_url"), id = pluginStr(link, "connected_account_id")
  guard !id.isEmpty, url.hasPrefix("https://") || isQa && url.hasPrefix("http://127.0.0.1:") else { return failed(link) }
  let tab = Tab()
  tab.url = url; tab.title = "Connect " + pluginName(slug)
  let opened = Browser(moving: tab)
  signIn = opened
  let end = Date().addingTimeInterval(600)
  while Date() < end {
   let closed = opened.closing || !browsers.contains { $0 === opened } // closed by the user: one last look, then stop
   if !closed { try? await Task.sleep(nanoseconds: 1_500_000_000) }
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
  case "pluginKey":
   let key = argText(data, "key").trimmingCharacters(in: .whitespacesAndNewlines)
   guard (8...400).contains(key.count), !key.contains(where: \.isWhitespace) else { break }
   if notProjectKey(key) { pluginStatus = "kind"; publishAiEverywhere(); break } // never sent, never kept
   PluginKey.save(key); pluginStatus = "checking"; publishAiEverywhere()
   Task { @MainActor in
    await self.refreshPlugins()
    if pluginStatus == "bad" { forgetPluginKey(); pluginStatus = "bad"; publishAiEverywhere() } // a key Composio refuses isn't kept
   }
  case "pluginLink":
   guard argText(data, "to") == "key" else { break }
   let tab = Tab()
   tab.url = "https://platform.composio.dev/"
   _ = Browser(moving: tab)
  case "pluginKeyRemove": forgetPluginKey(); publishAiEverywhere()
  case "pluginRefresh": Task { @MainActor in await self.refreshPlugins() }
  case "pluginSearch":
   let query = String(argText(data, "query").trimmingCharacters(in: .whitespaces).prefix(100))
   Task { @MainActor in await self.searchPlugins(query) }
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
  ["key": PluginKey.exists, "status": pluginStatus, "connecting": pluginConnecting, "found": pluginFound.map { $0 as Any } ?? NSNull(), "failed": pluginFailed, "error": pluginError,
   "connected": pluginAccounts.map { ["id": $0.id, "slug": $0.slug, "name": $0.name] }]
 }

 @MainActor func pluginTool(_ who: String, _ tool: String, _ args: [String: Any]) async -> String {
  guard let run = runs[who] else { return agentFail("Plugins are only for Still's own companions.") }
  guard PluginKey.exists else { return agentFail("Plugins are off: the user hasn't added a Composio API key. Tell them they can turn plugins on in Skills & plugins.") }
  let mate = companions.first { $0.id == run.chat.companion }
  let unavailable = { pluginStatus == "bad" ? "Composio refused the user's key. Tell them to check it in Skills & plugins." : "Composio isn't answering, so plugins are unavailable right now. Do it another way or try later." }
  if tool == "plugin_tools" {
   let plugin = argText(args, "plugin").trimmingCharacters(in: .whitespaces).lowercased(), query = argText(args, "query").trimmingCharacters(in: .whitespaces)
   var slugs: [String] = []
   for slug in plugin.isEmpty ? pluginAccounts.map(\.slug).filter({ mate?.pluginsOff.contains($0) != true }) : [plugin] where !slugs.contains(slug) { slugs.append(slug) }
   guard !slugs.isEmpty else { return agentFail("No plugins are connected for you. Pass the app's name as plugin (like gmail or googlecalendar) to see its tools.") }
   var result: [[String: Any]] = []
   for slug in slugs.prefix(8) {
    guard let list = await composio("GET", "/tools?toolkit_slug=\(pluginEscape(slug))&limit=\(slugs.count > 1 ? 8 : 25)" + (query.isEmpty ? "" : "&query=" + pluginEscape(query))) else { return agentFail(unavailable()) }
    result.append(["plugin": slug, "name": pluginName(slug), "connected": pluginAccounts.contains { $0.slug == slug }, "offForYou": mate?.pluginsOff.contains(slug) == true,
     "tools": (list["items"] as? [[String: Any]] ?? []).map { t -> [String: Any] in
      ["tool": pluginStr(t, "slug"), "what": String(pluginStr(t, "description").prefix(300)), "asksFirst": !pluginReads(t, pluginStr(t, "slug"), slug), "input": pluginInputs(t["input_parameters"])] }])
   }
   return agentOk(result)
  }

  // use_plugin
  let slug = argText(args, "tool").trimmingCharacters(in: .whitespaces).uppercased()
  guard (1...120).contains(slug.count) else { return agentFail("Pass the tool's name from plugin_tools, like GMAIL_FETCH_EMAILS.") }
  guard let info = await composio("GET", "/tools/" + pluginEscape(slug)) else { return agentFail(unavailable()) }
  let toolkit = pluginStr(info["toolkit"], "slug"), app = pluginName(toolkit, pluginStr(info["toolkit"], "name"))
  guard !toolkit.isEmpty else { return agentFail("There's no tool called \(slug). Call plugin_tools to find one.") }
  if mate?.pluginsOff.contains(toolkit) == true { return agentFail("The user turned \(app) off for you. They can turn it on in Skills & plugins.") }
  var account = pluginAccounts.first { $0.slug == toolkit }
  if account == nil {
   // Not connected: a card with a button that connects it, then the work goes on.
   guard await approve(run, "Connect " + app, app, "connect", "You sign in through Composio, in a Still window.", countdown: false) == "connect" else {
    return agentFail("The user didn't connect \(app). Don't ask again unless they bring it up.")
   }
   guard await connectPlugin(toolkit), let now = pluginAccounts.first(where: { $0.slug == toolkit }) else { return agentFail(app + " didn't get connected. Tell the user they can connect it in Skills & plugins.") }
   account = now
  }
  let arguments = args["arguments"] as? [String: Any] ?? [:]
  if !pluginReads(info, slug, toolkit) {
   let name = pluginStr(info, "name")
   let what = (name.isEmpty ? slug : name) + " in " + app
   let why = arguments.sorted { $0.key < $1.key }.compactMap { k, v in (v as? String).flatMap { $0.isEmpty ? nil : k + ": " + String($0.prefix(60)) } }.prefix(3).joined(separator: " · ")
   let answer = await approve(run, what, app, "plugin", why, countdown: false)
   let allowed = ["once", "chat", "always"].contains(answer)
   audit(run.chat, what, app, allowed ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no")
   publishAiEverywhere()
   guard allowed else { return agentFail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't try it again unless they ask.") }
  }
  guard let account, let done = await composio("POST", "/tools/execute/" + pluginEscape(slug), ["user_id": pluginUser, "connected_account_id": account.id, "arguments": arguments]) else {
   return agentFail("Composio isn't answering, so it didn't run. Tell the user.")
  }
  guard done["successful"] as? Bool == true else { return agentFail(app + ": " + composioError(done)) }
  let output = done["data"] ?? [String: Any]()
  let text = (try? JSONSerialization.data(withJSONObject: output, options: [.fragmentsAllowed])).map { String(decoding: $0, as: UTF8.self) } ?? ""
  return agentOk(text.count > 40000 ? String(text.prefix(40000)) + "…" : output)
 }
}
