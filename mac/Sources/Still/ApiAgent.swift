// API providers the user added in Settings → Models, run by Still's own agent loop with the user's own key (Windows:
// Agents/ApiAgent.cs and MainWindow.Api.cs). Labelled Compatible: Still checks these against its own fake server, never
// against real endpoints. The key lives in a file encrypted for this Mac (Sealed) and only ever goes to the provider, in its auth header.
import Foundation

struct ApiModel { var id: String, efforts: [String] }
struct ApiUse { var input: Int64 = 0, output: Int64 = 0, cost = 0.0, calls = 0 }

/// An API provider: its settings and spending, kept in prefs as on Windows. Never the key (ApiKeys).
final class ApiProvider {
 var id = "", kind = "openai", name = "", url = ""
 var models: [ApiModel] = []
 var priceIn = 0.0, priceOut = 0.0 // per million tokens; 0 = not set
 var limit = 0.0                   // a month's spending limit; 0 = none
 var context = 0                   // the models' context size in tokens; 0 = not known (Still assumes 128k and halves it if refused)
 var noTools = false               // Test connection found the model doesn't call tools: it can chat, not use tabs
 var noKey = false                 // saved without a key: a local or open server that doesn't ask for one
 var spent: [String: ApiUse] = [:] // "2026-11" → that month's use, and per job under "2026-11/titles"

 init() {}
 init(_ d: [String: Any]) {
  func num(_ k: String) -> Double { (d[k] as? NSNumber)?.doubleValue ?? 0 }
  id = d["Id"] as? String ?? ""; kind = d["Kind"] as? String == "anthropic" ? "anthropic" : "openai"
  name = d["Name"] as? String ?? ""; url = d["Url"] as? String ?? ""
  models = (d["Models"] as? [[String: Any]] ?? []).map { ApiModel(id: $0["Id"] as? String ?? "", efforts: $0["Efforts"] as? [String] ?? []) }
  priceIn = num("PriceIn"); priceOut = num("PriceOut"); limit = num("Limit"); context = Int(num("Context")); noTools = d["NoTools"] as? Bool ?? false; noKey = d["NoKey"] as? Bool ?? false
  for (k, v) in d["Spent"] as? [String: [String: Any]] ?? [:] {
   spent[k] = ApiUse(input: AgentStream.long(v["In"]), output: AgentStream.long(v["Out"]), cost: (v["Cost"] as? NSNumber)?.doubleValue ?? 0, calls: (v["Calls"] as? NSNumber)?.intValue ?? 0)
  }
 }
 var dict: [String: Any] {
  ["Id": id, "Kind": kind, "Name": name, "Url": url, "Models": models.map { ["Id": $0.id, "Efforts": $0.efforts] as [String: Any] }, "PriceIn": priceIn, "PriceOut": priceOut,
   "Limit": limit, "Context": context, "NoTools": noTools, "NoKey": noKey, "Spent": spent.mapValues { ["In": $0.input, "Out": $0.output, "Cost": $0.cost, "Calls": $0.calls] as [String: Any] }]
 }
 static var month: String {
  let f = DateFormatter(); f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM"
  return f.string(from: Date())
 }
 func costOf(_ input: Int64, _ output: Int64) -> Double { Double(input) / 1e6 * priceIn + Double(output) / 1e6 * priceOut }
 var priced: Bool { priceIn > 0 || priceOut > 0 }
 var paused: Bool { limit > 0 && (spent[ApiProvider.month]?.cost ?? 0) >= limit }
}

private var apiCache: [ApiProvider]?
/// The user's API providers, read from prefs once; saveApiProviders writes them back.
var apiProviders: [ApiProvider] {
 get {
  if let apiCache { return apiCache }
  let list = (store.prefs["ApiProviders"] as? [[String: Any]] ?? []).map(ApiProvider.init).filter { ApiKeys.idOk($0.id) }
  apiCache = list; return list
 }
 set { apiCache = newValue; saveApiProviders() }
}
func saveApiProviders() { store.prefs["ApiProviders"] = apiProviders.map(\.dict); saveAllLater() }

/// API keys: one sealed file per provider in the profile's api-keys folder, like saved logins and the Composio key. The
/// shell only ever hears whether there is a key and its last four characters.
enum ApiKeys {
 private static let lock = NSLock()
 private static var known: [String: Bool] = [:], ends: [String: String] = [:], refusedIds = Set<String>()
 static func idOk(_ id: String) -> Bool { id.count > 4 && id.count <= 20 && id.hasPrefix("api-") && id.dropFirst(4).allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber) } }
 static var folder: URL { support.appendingPathComponent("api-keys") }
 static func file(_ id: String) -> URL { folder.appendingPathComponent(id + ".sealed") }
 /// The provider answered 401 or 403 with this key.
 static func refused(_ id: String) -> Bool { lock.lock(); defer { lock.unlock() }; return refusedIds.contains(id) }
 static func setRefused(_ id: String, _ on: Bool) { lock.lock(); if on { refusedIds.insert(id) } else { refusedIds.remove(id) }; lock.unlock() }
 static func has(_ id: String) -> Bool {
  guard idOk(id) else { return false }
  lock.lock(); let cached = known[id]; lock.unlock()
  if let cached { return cached }
  let found = FileManager.default.fileExists(atPath: file(id).path)
  lock.lock(); known[id] = found; lock.unlock()
  return found
 }
 static func read(_ id: String) -> String? {
  guard idOk(id) else { return nil }
  return Sealed.read(file(id)).map { String(decoding: $0, as: UTF8.self) }
 }
 static func save(_ id: String, _ key: String) {
  guard idOk(id) else { return }
  Sealed.write(Data(key.utf8), file(id))
  lock.lock(); known[id] = true; ends[id] = key.count >= 8 ? String(key.suffix(4)) : ""; refusedIds.remove(id); lock.unlock()
 }
 static func remove(_ id: String) {
  guard idOk(id) else { return }
  try? FileManager.default.removeItem(at: file(id))
  lock.lock(); known[id] = false; ends[id] = nil; refusedIds.remove(id); lock.unlock()
 }
 /// A profile is deleted or reset: every key it kept goes with it. What an older Still kept for it in the Keychain stays.
 static func erase(_ profile: URL) {
  try? FileManager.default.removeItem(at: profile.appendingPathComponent("api-keys"))
 }
 /// The key's last four characters (none for a key under eight).
 static func end(_ id: String) -> String {
  lock.lock(); let cached = ends[id]; lock.unlock()
  if let cached { return cached }
  let end = read(id).map { $0.count >= 8 ? String($0.suffix(4)) : "" } ?? ""
  lock.lock(); ends[id] = end; lock.unlock()
  return end
 }
}

/// An API provider as one of the AIs: picked, set per mode and run like the apps, with no app to install or sign in to.
final class ApiAdapter: AgentAdapter {
 let provider: ApiProvider
 init(_ p: ApiProvider) {
  provider = p
  super.init(id: p.id, name: p.name, app: p.name, command: "")
  maker = p.kind == "anthropic" ? "Anthropic-compatible API" : "OpenAI-compatible API"
 }
 override var namesSession: Bool { true } // the chat's transcript file
 override var forgets: Bool { true } // incognito: the transcript lives in memory for the turn and is never written
 override var gaps: [String] { provider.noTools ? ["Can't use your tabs: Test connection found this model doesn't call tools."] : [] }
 override func detect(_ exe: String) async -> Bool? { ApiKeys.has(provider.id) || provider.noKey }
 override func models(_ exe: String) async -> [AgentModel] { [AgentModel(id: "", name: "Default", efforts: [])] + provider.models.map { AgentModel(id: $0.id, name: $0.id, efforts: $0.efforts) } }
 override func start(_ exe: String, _ r: RunRequest) async throws -> AgentRun { ApiRun.start(self, r) }
}

struct ApiFailure: Error { let message: String; init(_ message: String) { self.message = message } }
struct ToolsStopped: LocalizedError { var errorDescription: String? = "Still's tools stopped." }

/// Never follows a redirect: a key goes only to the address the user typed.
final class NoRedirects: NSObject, URLSessionTaskDelegate {
 static let shared = NoRedirects()
 func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}

/// Still's own agent loop for an API provider. Tools come from Still's MCP server, run as its own child exactly as the apps
/// run it (`Still --mcp`), so approvals, sensitive steps and permission modes are the same code. Replies stream; Stop ends
/// it at once; a turn takes at most maxSteps model calls and the run the same hour as an app. The transcript, tool calls
/// included, is kept in the chat's folder (api-<session>.json), except for incognito chats, whose transcript is never written.
final class ApiRun: AgentRun {
 static let maxSteps = 40
 static let session: URLSession = {
  let c = URLSessionConfiguration.ephemeral
  c.timeoutIntervalForRequest = 300; c.timeoutIntervalForResource = AgentRun.limit
  return URLSession(configuration: c, delegate: NoRedirects.shared, delegateQueue: nil)
 }()
 let p: ApiProvider, r: RunRequest
 private let stream: AsyncStream<AgentEvent>
 private let out: AsyncStream<AgentEvent>.Continuation
 private let runLock = NSLock()
 private var work: Task<Void, Never>?
 private var mcp: ApiMcp?
 var timeout: TimeInterval = 300

 private init(_ a: ApiAdapter, _ r: RunRequest) {
  p = a.provider; self.r = r
  var c: AsyncStream<AgentEvent>.Continuation?
  stream = AsyncStream { c = $0 }
  out = c!
  super.init(a)
 }
 static func start(_ a: ApiAdapter, _ r: RunRequest) -> ApiRun {
  let run = ApiRun(a, r)
  DispatchQueue.main.async { AgentRun.launched += 1 }
  let work = Task.detached { await run.loop() }
  run.runLock.lock(); run.work = work; run.runLock.unlock()
  return run
 }
 override func events() -> AsyncStream<AgentEvent> { stream }
 override func cancel() {
  super.cancel()
  runLock.lock(); let w = work, m = mcp; runLock.unlock()
  w?.cancel(); m?.end()
 }
 private var hush = false // a summary being made: its text isn't the chat's
 private func say(_ e: AgentEvent) { if hush, case .message = e { return }; out.yield(e) }
 private var helper: ApiMcp? { runLock.lock(); defer { runLock.unlock() }; return mcp }
 private func use(_ m: ApiMcp) { runLock.lock(); mcp = m; runLock.unlock() }

 /// The address Still may send a key to: https, or plain http only on this computer.
 static func address(_ text: String) -> URL? {
  var s = text.trimmingCharacters(in: .whitespaces)
  while s.hasSuffix("/") { s.removeLast() }
  guard let c = URLComponents(string: s), let u = c.url, c.user == nil, c.password == nil, c.query == nil, c.fragment == nil, let host = c.host, !host.isEmpty else { return nil }
  return c.scheme == "https" || (c.scheme == "http" && (host == "localhost" || host == "127.0.0.1")) ? u : nil
 }
 static func at(_ root: URL, _ path: String) -> URL { URL(string: root.absoluteString + "/" + path) ?? root }
 static func request(_ url: URL, _ kind: String, _ key: String, body: Data? = nil, timeout: TimeInterval = 30) -> URLRequest {
  var q = URLRequest(url: url, timeoutInterval: timeout)
  if let body { q.httpMethod = "POST"; q.httpBody = body; q.setValue("application/json", forHTTPHeaderField: "Content-Type") }
  if kind == "anthropic" { q.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version") }
  if key.isEmpty { return q } // a provider saved without a key
  if kind == "anthropic" { q.setValue(key, forHTTPHeaderField: "x-api-key") } else { q.setValue("Bearer " + key, forHTTPHeaderField: "Authorization") }
  return q
 }

 private func loop() async {
  let timer = DispatchWorkItem { [weak self] in self?.timedOut = true; self?.cancel() }
  DispatchQueue.global().asyncAfter(deadline: .now() + AgentRun.limit, execute: timer)
  do { try await turn() }
  catch {
   if cancelled {}
   else if let f = error as? ApiFailure { exitCode = 1; keep(f.message); say(.error(f.message)) }
   else { exitCode = 1; let text = plain(error.localizedDescription); keep(text); say(.error("couldn't reach it: " + text)) }
  }
  timer.cancel()
  helper?.end()
  ended()
  out.finish()
 }
 // A key never reaches an error, a log or the chat, even when a provider repeats it back.
 func plain(_ text: String) -> String { ApiKeys.read(p.id).map { $0.isEmpty ? text : text.replacingOccurrences(of: $0, with: "(key)") } ?? text }
 static func clip(_ s: String) -> String { let t = s.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespaces); return t.count > 300 ? String(t.prefix(300)) + "…" : t }
 static func dollars(_ v: Double) -> String { var s = String(format: "%.4f", v); for _ in 0..<2 where s.hasSuffix("0") { s.removeLast() }; return s } // 0.00##
 static func amount(_ v: Double) -> String { var s = String(format: "%.2f", v); while s.hasSuffix("0") { s.removeLast() }; if s.hasSuffix(".") { s.removeLast() }; return s } // 0.##
 static func clock(_ d: Date) -> String { DateFormatter.localizedString(from: d, dateStyle: .none, timeStyle: .short) }
 private func money(_ cost: Double) -> String { p.priced ? ", about $" + ApiRun.dollars(cost) : "" }

 typealias Call = (id: String, name: String, args: [String: Any])
 struct Reply { var message: [String: Any]; var calls: [Call]; var input: Int64; var output: Int64 }

 private func turn() async throws {
  guard let key = ApiKeys.read(p.id) ?? (p.noKey ? "" : nil) else { throw ApiFailure("needs a key. Add one in Settings → Models.") }
  guard let root = ApiRun.address(p.url) else { throw ApiFailure("its address must start with https:// (plain http only for localhost).") }
  var model = !r.model.isEmpty ? r.model : p.models.first?.id ?? ""
  if model.isEmpty { throw ApiFailure("has no model. Add one in Settings → Models.") }
  let file = (r.folder as NSString).appendingPathComponent("api-" + (r.session ?? "run") + ".json")
  var convo: [String: Any] = ["in": 0, "out": 0, "cost": 0.0]
  var messages: [[String: Any]] = []
  if r.resume && !r.forget {
   guard let data = FileManager.default.contents(atPath: file), let saved = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { throw ApiFailure("No conversation found") }
   convo = saved; messages = saved["messages"] as? [[String: Any]] ?? []
  }
  if let session = r.session { say(.session(session)) }
  messages.append(["role": "user", "content": r.prompt])
  var turnIn: Int64 = 0, turnOut: Int64 = 0, failure: Error?
  do {
   var tools: [[String: Any]] = []
   if !p.noTools {
    let m = try await ApiMcp.start(r.folder, r.mcp)
    use(m)
    if cancelled { throw CancellationError() }
    tools = try await m.tools()
   }
   var context = p.context > 0 ? p.context : 128_000, step = 0
   while true {
    if step == ApiRun.maxSteps { say(.note("Stopped after \(ApiRun.maxSteps) steps in one reply. Ask again to carry on.")); break }
    if p.paused { throw ApiFailure("paused: this month's spending reached your limit of $\(ApiRun.amount(p.limit)). Raise or turn off the limit in Settings → Models.") }
    let summed = try await compact(root, key, model, &messages, context)
    turnIn += summed.0; turnOut += summed.1
    let reply: Reply
    do { reply = try await call(root, key, model, messages, tools) }
    catch let f as ApiFailure where f.message == "model" {
     guard let first = p.models.first?.id, model != first else { throw ApiFailure("doesn't offer \(model). Pick another model in Settings → Models.") }
     say(.note("\(model) isn't available at \(p.name), so this ran on \(first). You can pick another in Settings → Models."))
     model = first; continue
    }
    catch let f as ApiFailure where f.message == "context" {
     if context <= 8000 { throw ApiFailure("this chat is too long for the model. Start a new chat.") }
     context /= 2; continue
    }
    step += 1
    turnIn += reply.input; turnOut += reply.output
    say(.spent(input: reply.input, output: reply.output, cost: p.costOf(reply.input, reply.output), job: r.job))
    messages.append(reply.message)
    if reply.calls.isEmpty { break }
    // Every call gets its answer, even when Stop came first, so the transcript stays one the provider accepts.
    var results: [(id: String, ok: Bool, content: [[String: Any]])] = [], stopped: Error?
    for c in reply.calls {
     if stopped == nil, let m = self.helper {
      say(.toolCall(id: c.id, name: c.name, args: c.args))
      do { let (ok, content) = try await m.call(c.name, c.args); results.append((c.id, ok, content)); say(.toolResult(id: c.id, ok: ok)); continue }
      catch { stopped = error }
     }
     results.append((c.id, false, [["type": "text", "text": "The user pressed Stop."]]))
    }
    ApiRun.addResults(&messages, results, p.kind)
    if let stopped { throw stopped }
   }
  } catch { failure = error }
  let cost = p.costOf(turnIn, turnOut)
  let allIn = AgentStream.long(convo["in"]) + turnIn, allOut = AgentStream.long(convo["out"]) + turnOut, allCost = ((convo["cost"] as? NSNumber)?.doubleValue ?? 0) + cost
  convo["in"] = allIn; convo["out"] = allOut; convo["cost"] = allCost; convo["messages"] = messages
  if turnIn + turnOut > 0 {
   say(.usage("Last reply: \(AgentStream.tokens(turnIn)) in, \(AgentStream.tokens(turnOut)) out\(money(cost)) · This chat: \(AgentStream.tokens(allIn)) in, \(AgentStream.tokens(allOut)) out\(money(allCost))"))
  }
  if !r.forget, let data = try? JSONSerialization.data(withJSONObject: convo) {
   try? FileManager.default.createDirectory(atPath: r.folder, withIntermediateDirectories: true)
   try? data.write(to: URL(fileURLWithPath: file), options: .atomic)
  }
  if let failure { throw failure }
 }

 static let trimNote = "(Earlier parts of this chat were left out to fit the model's context.)"
 static let summed = "(A summary of the earlier part of this chat, made to fit the model's context:)\n"
 static func over(_ messages: [[String: Any]], _ context: Int) -> Bool { // guessing 4 characters a token
  Double(((try? JSONSerialization.data(withJSONObject: messages)) ?? Data()).count / 4) > Double(context) * 0.7
 }
 static func starts(_ m: [String: Any]) -> Bool { m["role"] as? String == "user" && m["content"] is String } // a message of the user's, not tool results

 /// Past 70% of the model's context, the model sums up everything between the first message (Still's instructions) and
 /// the latest turn, and the summary takes their place. When it can't, or the latest turn alone is too long, trim leaves
 /// out the oldest turns. Returns the tokens the summary took.
 func compact(_ root: URL, _ key: String, _ model: String, _ messages: inout [[String: Any]], _ context: Int) async throws -> (Int64, Int64) {
  guard ApiRun.over(messages, context) else { return (0, 0) }
  var latest = messages.count - 1
  while latest > 0 && !ApiRun.starts(messages[latest]) { latest -= 1 }
  let earlier = latest > 1 ? Array(messages[1..<latest]) : []
  var used: (Int64, Int64) = (0, 0)
  if earlier.contains(where: { let s = $0["content"] as? String ?? ""; return !(s.hasPrefix(ApiRun.summed) || s == ApiRun.trimNote) }),
     let data = try? JSONSerialization.data(withJSONObject: earlier), let json = String(data: data, encoding: .utf8) {
   // Pictures and other long unbroken strings say nothing to a summary
   let said = json.replacingOccurrences(of: "\"[^\"\\s]{300,}\"", with: "\"(left out)\"", options: .regularExpression)
   hush = true
   defer { hush = false }
   do {
    let reply = try await call(root, key, model, [["role": "user", "content": "Sum up this earlier part of a conversation between a user and you, an AI working in their browser, so you can carry on without it. Keep what they asked for and why, what you did and found, the pages, tabs and files involved, decisions made, and anything left to do. Plain text, under 300 words. The conversation, as JSON:\n" + said]], [])
    used = (reply.input, reply.output)
    say(.spent(input: reply.input, output: reply.output, cost: p.costOf(reply.input, reply.output), job: r.job))
    let content = reply.message["content"]
    let summary = ((content as? String) ?? (content as? [[String: Any]])?.compactMap { $0["text"] as? String }.joined() ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    if !summary.isEmpty {
     messages.replaceSubrange(1..<latest, with: [["role": "assistant", "content": ApiRun.summed + summary]])
     say(.note("This chat got long, so its earlier part was summed up to fit the model."))
    }
   } catch is ApiFailure {} // trim instead
  }
  ApiRun.trim(&messages, context)
  return used
 }

 /// Leaves out the oldest turns (never the first, which has Still's instructions, or the latest) once the conversation
 /// would pass 70% of the model's context. A note takes their place.
 static func trim(_ messages: inout [[String: Any]], _ context: Int) {
  while over(messages, context) {
   let noted = messages.count > 1 && messages[1]["content"] as? String == trimNote
   let from = noted ? 2 : 1
   var next = from + 1
   while next < messages.count && !starts(messages[next]) { next += 1 }
   if next >= messages.count { return } // only the first turn's message and the latest turn are left
   messages.removeSubrange(from..<next)
   if !noted { messages.insert(["role": "assistant", "content": trimNote], at: 1) }
  }
 }

 func call(_ root: URL, _ key: String, _ model: String, _ messages: [[String: Any]], _ tools: [[String: Any]]) async throws -> Reply {
  p.kind == "anthropic" ? try await anthropic(root, key, model, messages, tools) : try await openAi(root, key, model, messages, tools)
 }

 private func post(_ url: URL, _ key: String, _ body: [String: Any]) async throws -> URLSession.AsyncBytes {
  let data = try JSONSerialization.data(withJSONObject: body, options: [.withoutEscapingSlashes])
  var tries = 0
  while true {
   let (bytes, response) = try await ApiRun.session.bytes(for: ApiRun.request(url, p.kind, key, body: data, timeout: timeout), delegate: NoRedirects.shared)
   let http = response as? HTTPURLResponse, status = http?.statusCode ?? 0
   if (200..<300).contains(status) { return bytes }
   var text = ""
   for try await line in bytes.lines { text += line + " "; if text.count > 4000 { break } }
   if status == 401 || status == 403 { ApiKeys.setRefused(p.id, true); throw ApiFailure("Key not accepted. Replace it in Settings → Models.") }
   if status == 429 {
    let wait = ApiRun.retryAfter(http), at = Date().addingTimeInterval(wait)
    if tries == 2 { throw ApiFailure("is still limiting requests. Try again after \(ApiRun.clock(at)).") }
    say(.note("\(p.name) is limiting requests. Trying again at \(ApiRun.clock(at))."))
    try await Task.sleep(nanoseconds: UInt64(wait * 1e9))
    tries += 1
    continue
   }
   let lower = text.lowercased()
   if status == 404 || status == 400 && lower.contains("model") && !lower.contains("context") { throw ApiFailure("model") }
   if status == 400 && (lower.contains("context") || lower.contains("too long")) { throw ApiFailure("context") }
   throw ApiFailure("answered \(status): \(plain(ApiRun.clip(text)))")
  }
 }
 static func retryAfter(_ r: HTTPURLResponse?) -> TimeInterval {
  let h = (r?.value(forHTTPHeaderField: "Retry-After") ?? "").trimmingCharacters(in: .whitespaces)
  var wait = Double(h).flatMap { $0.isFinite ? $0 : nil } ?? 20 // "nan" is a number to Double, and traps when it's turned into nanoseconds
  if Double(h) == nil, !h.isEmpty {
   let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
   if let d = f.date(from: h) { wait = d.timeIntervalSinceNow }
  }
  return min(max(wait, 1), 120)
 }
 /// Server-sent events: each data line's JSON, until [DONE] or the end.
 static func sse(_ bytes: URLSession.AsyncBytes, _ each: ([String: Any]) throws -> Void) async throws {
  for try await line in bytes.lines {
   guard line.hasPrefix("data:") else { continue }
   let data = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
   if data == "[DONE]" { break }
   if let e = jsonObject(data) { try each(e) }
  }
 }
 static func args(_ s: String) -> [String: Any] { jsonObject(s) ?? [:] }

 private func openAi(_ root: URL, _ key: String, _ model: String, _ messages: [[String: Any]], _ tools: [[String: Any]]) async throws -> Reply {
  var body: [String: Any] = ["model": model, "messages": messages, "stream": true, "stream_options": ["include_usage": true]]
  if !tools.isEmpty {
   body["tools"] = tools.map { t -> [String: Any] in ["type": "function", "function": ["name": t["name"] ?? "", "description": t["description"] ?? "", "parameters": t["inputSchema"] ?? ["type": "object"]]] }
  }
  if !r.effort.isEmpty { body["reasoning_effort"] = r.effort }
  let bytes = try await post(ApiRun.at(root, "chat/completions"), key, body)
  var text = "", calls: [Int: (id: String, name: String, args: String)] = [:], input: Int64 = 0, output: Int64 = 0
  try await ApiRun.sse(bytes) { e in
   if let error = e["error"], !(error is NSNull) { throw ApiFailure("answered: " + plain(ApiRun.clip(AgentStream.str((error as? [String: Any])?["message"]) ?? AgentStream.str(error) ?? ""))) }
   if let u = e["usage"] as? [String: Any] { input = AgentStream.long(u["prompt_tokens"]); output = AgentStream.long(u["completion_tokens"]) }
   let delta = (e["choices"] as? [[String: Any]])?.first?["delta"] as? [String: Any] // the usage chunk has none
   if let chunk = delta?["content"] as? String, !chunk.isEmpty { say(.message(chunk, join: text.isEmpty ? nil : "")); text += chunk }
   for tc in delta?["tool_calls"] as? [[String: Any]] ?? [] {
    let i = (tc["index"] as? NSNumber)?.intValue ?? 0, f = tc["function"] as? [String: Any]
    var c = calls[i] ?? ("", "", "")
    if let id = tc["id"] as? String, !id.isEmpty { c.id = id }
    c.name += f?["name"] as? String ?? ""; c.args += f?["arguments"] as? String ?? ""
    calls[i] = c
   }
  }
  var message: [String: Any] = ["role": "assistant", "content": text.isEmpty ? NSNull() : text]
  let list: [Call] = calls.keys.sorted().enumerated().map { (n, i) -> Call in let c = calls[i]!; return (c.id.isEmpty ? "call_\(n)" : c.id, c.name, ApiRun.args(c.args)) }
  if !list.isEmpty { message["tool_calls"] = list.map { ["id": $0.id, "type": "function", "function": ["name": $0.name, "arguments": jsonText($0.args)] as [String: Any]] as [String: Any] } }
  return Reply(message: message, calls: list, input: input, output: output)
 }

 private func anthropic(_ root: URL, _ key: String, _ model: String, _ messages: [[String: Any]], _ tools: [[String: Any]]) async throws -> Reply {
  let budget = ["low": 2048, "medium": 8192, "high": 24576][r.effort] ?? 0
  var body: [String: Any] = ["model": model, "max_tokens": budget + 8192, "messages": messages, "stream": true]
  if !tools.isEmpty { body["tools"] = tools.map { ["name": $0["name"] ?? "", "description": $0["description"] ?? "", "input_schema": $0["inputSchema"] ?? ["type": "object"]] as [String: Any] } }
  if budget > 0 { body["thinking"] = ["type": "enabled", "budget_tokens": budget] }
  let bytes = try await post(ApiRun.at(root, "messages"), key, body)
  var blocks: [Int: [String: Any]] = [:], json: [Int: String] = [:], input: Int64 = 0, output: Int64 = 0, said = false
  try await ApiRun.sse(bytes) { e in
   let i = (e["index"] as? NSNumber)?.intValue ?? 0
   switch e["type"] as? String {
   case "message_start":
    let u = (e["message"] as? [String: Any])?["usage"] as? [String: Any]
    input = AgentStream.long(u?["input_tokens"]) + AgentStream.long(u?["cache_read_input_tokens"])
   case "content_block_start":
    guard let b = e["content_block"] as? [String: Any] else { break }
    blocks[i] = b
    let type = b["type"] as? String
    if type == "tool_use" { json[i] = "" }
    if type == "thinking" || type == "redacted_thinking" { say(.thinking) }
   case "content_block_delta":
    guard var block = blocks[i], let d = e["delta"] as? [String: Any] else { break }
    switch d["type"] as? String {
    case "text_delta":
     let chunk = d["text"] as? String ?? ""
     block["text"] = (block["text"] as? String ?? "") + chunk
     if !chunk.isEmpty { say(.message(chunk, join: said ? "" : nil)); said = true }
    case "input_json_delta": json[i, default: ""] += d["partial_json"] as? String ?? ""
    case "thinking_delta": block["thinking"] = (block["thinking"] as? String ?? "") + (d["thinking"] as? String ?? "")
    case "signature_delta": block["signature"] = d["signature"] as? String ?? ""
    default: break
    }
    blocks[i] = block
   case "content_block_stop": if let args = json[i], blocks[i] != nil { blocks[i]?["input"] = ApiRun.args(args) }
   case "message_delta": if let o = (e["usage"] as? [String: Any])?["output_tokens"] { output = AgentStream.long(o) }
   case "error": throw ApiFailure("answered: " + plain(ApiRun.clip(AgentStream.str((e["error"] as? [String: Any])?["message"]) ?? jsonText(e))))
   default: break
   }
  }
  let ordered = blocks.keys.sorted().compactMap { blocks[$0] }
  let content = ordered.filter { $0["type"] as? String != "text" || !($0["text"] as? String ?? "").isEmpty }
  let calls: [Call] = ordered.filter { $0["type"] as? String == "tool_use" }.map { ($0["id"] as? String ?? "", $0["name"] as? String ?? "", $0["input"] as? [String: Any] ?? [:]) }
  return Reply(message: ["role": "assistant", "content": content], calls: calls, input: input, output: output)
 }

 static func addResults(_ messages: inout [[String: Any]], _ results: [(id: String, ok: Bool, content: [[String: Any]])], _ kind: String) {
  if kind == "anthropic" {
   messages.append(["role": "user", "content": results.map { x -> [String: Any] in ["type": "tool_result", "tool_use_id": x.id, "is_error": !x.ok,
    "content": x.content.map { c -> [String: Any] in c["type"] as? String == "image"
     ? ["type": "image", "source": ["type": "base64", "media_type": c["mimeType"] ?? "", "data": c["data"] ?? ""]]
     : ["type": "text", "text": c["text"] ?? ""] }] }])
  } else {
   for x in results {
    messages.append(["role": "tool", "tool_call_id": x.id, "content": x.content.map { $0["type"] as? String == "text" ? $0["text"] as? String ?? "" : "(An image: this provider gets text only.)" }.joined(separator: "\n")])
   }
  }
 }

 typealias Check = (part: String, ok: Bool, text: String)
 /// Checks an API provider for Settings, in plain words: the address, the key, the model, streaming and tool calls. It
 /// sends one tiny request (a second one without effort if the first is refused), which the provider may bill.
 static func test(_ p: ApiProvider, _ key: String, _ model: String) async -> (checks: [Check], input: Int64, output: Int64) {
  var checks: [Check] = []
  var input: Int64 = 0, output: Int64 = 0
  let accepted = key.isEmpty ? "None needed." : "Accepted.", refused = key.isEmpty ? "It asks for a key. Add one, then test again." : "Not accepted. Copy the key again from your provider and replace it."
  guard let root = address(p.url) else { return ([("Address", false, "Use an address that starts with https:// (plain http only for localhost).")], 0, 0) }
  let host = root.host ?? ""
  // The model list: reaches the address and checks the key, where the provider has one.
  var listed: [String] = []
  do {
   let (data, response) = try await session.data(for: request(at(root, "models"), p.kind, key), delegate: NoRedirects.shared)
   let status = (response as? HTTPURLResponse)?.statusCode ?? 0
   checks.append(("Address", true, "Reached \(host)."))
   if status == 401 || status == 403 { checks.append(("Key", false, refused)); return (checks, 0, 0) }
   if (200..<300).contains(status) { checks.append(("Key", true, accepted)); listed = ids(data) }
  } catch { return ([("Address", false, "Couldn't reach \(host). Check the base URL, and that the server is running.")], 0, 0) }
  if !listed.isEmpty && !listed.contains(model) { checks.append(("Model", false, "\(model) isn't in \(p.name)'s model list. Pick one it offers.")); return (checks, 0, 0) }
  let probe: [[String: Any]] = [["name": "still_test", "description": "A harmless test tool. Call it once when asked.", "inputSchema": ["type": "object", "properties": [String: Any]()]]]
  for effort in ["low", ""] {
   let run = ApiRun(ApiAdapter(p), RunRequest(prompt: "", model: model, effort: effort, folder: NSTemporaryDirectory(), mcp: [], session: nil, resume: false))
   run.timeout = 60
   defer { run.ended(); run.out.finish() }
   do {
    let reply = try await run.call(root, key, model, [["role": "user", "content": "This is a connection test. Call the still_test tool once, then say done."]], probe)
    input += reply.input; output += reply.output
    if !checks.contains(where: { $0.part == "Key" }) { checks.append(("Key", true, accepted)) }
    checks.append(("Model", true, "\(model) answered."))
    checks.append(("Streaming", true, "Replies stream in as they're written."))
    checks.append(reply.calls.contains { $0.name == "still_test" } ? ("Tools", true, "It calls tools, so it can use your tabs.") : ("Tools", false, "It didn't call the test tool, so it can chat but can't use your tabs."))
    checks.append(!effort.isEmpty ? ("Effort", true, "It takes an effort setting.") : ("Effort", false, "It refused an effort setting, so modes use Default effort."))
    return (checks, input, output)
   } catch let f as ApiFailure where !effort.isEmpty && !f.message.hasPrefix("Key not accepted") { continue } // refused with effort: once more without
   catch let f as ApiFailure {
    checks.append(f.message == "model" ? ("Model", false, "\(p.name) doesn't offer \(model). Pick one it offers.")
     : f.message.hasPrefix("Key not accepted") ? ("Key", false, refused) : ("Streaming", false, "The request failed: \(f.message)"))
    return (checks, input, output)
   } catch {
    checks.append(("Address", false, "No answer in time. Check the base URL."))
    return (checks, input, output)
   }
  }
  return (checks, input, output)
 }

 /// The models a provider lists, where it has a list (both kinds answer GET /models).
 static func list(_ p: ApiProvider, _ key: String) async throws -> [String] {
  guard let root = address(p.url) else { return [] }
  let (data, response) = try await session.data(for: request(at(root, "models"), p.kind, key), delegate: NoRedirects.shared)
  guard ((response as? HTTPURLResponse)?.statusCode ?? 0) / 100 == 2 else { return [] }
  return Array(ids(data).filter { $0.count <= 120 }.prefix(300))
 }
 static func ids(_ data: Data) -> [String] {
  ((((try? JSONSerialization.jsonObject(with: data)) as? [String: Any])?["data"] as? [[String: Any]]) ?? []).compactMap { $0["id"] as? String }.filter { !$0.isEmpty }
 }
}

/// Still's MCP server as an API run's child, spoken to over stdio like any MCP client. It asks the running Still about
/// everything that needs the user, so approvals show in the chat as they do for the apps.
final class ApiMcp {
 private let process: Spawned
 private let lock = NSLock(), writeLock = NSLock()
 private var waiting: [Int: CheckedContinuation<[String: Any], Error>] = [:]
 private var next = 0, closed = false

 private init(_ process: Spawned) { self.process = process }
 static func start(_ folder: String, _ args: [String]) async throws -> ApiMcp {
  try FileManager.default.createDirectory(atPath: folder, withIntermediateDirectories: true)
  let m = ApiMcp(try Spawned(stillExecutable, args, folder: folder, environment: AgentAdapter.environment))
  Thread.detachNewThread { m.read() }
  Thread.detachNewThread { readLines(m.process.errors) { _ in } }
  _ = try await m.request("initialize", ["protocolVersion": "2025-06-18", "capabilities": [String: Any](), "clientInfo": ["name": "Still", "version": "1"]])
  m.write(["jsonrpc": "2.0", "method": "notifications/initialized"])
  return m
 }
 private func read() {
  readLines(process.output) { line in
   guard let m = jsonObject(line) else { return }
   if let method = m["method"] as? String, let id = m["id"] { // the server asks: a ping, or something this client doesn't offer
    write(method == "ping" ? ["jsonrpc": "2.0", "id": id, "result": [String: Any]()] : ["jsonrpc": "2.0", "id": id, "error": ["code": -32601, "message": "not supported"]])
    return
   }
   if let id = (m["id"] as? NSNumber)?.intValue {
    lock.lock(); let wait = waiting.removeValue(forKey: id); lock.unlock()
    wait?.resume(returning: m)
   }
  }
  lock.lock(); closed = true; let all = waiting; waiting = [:]; lock.unlock()
  for w in all.values { w.resume(throwing: ToolsStopped()) }
  _ = process.wait()
 }
 private func write(_ message: [String: Any]) {
  guard let data = try? JSONSerialization.data(withJSONObject: message, options: [.withoutEscapingSlashes]) else { return }
  writeLock.lock(); defer { writeLock.unlock() }
  try? process.input.write(contentsOf: data + Data([10]))
 }
 private func request(_ method: String, _ params: [String: Any]) async throws -> [String: Any] {
  let id = nextId()
  let reply: [String: Any] = try await withTaskCancellationHandler {
   try await withCheckedThrowingContinuation { (c: CheckedContinuation<[String: Any], Error>) in
    lock.lock()
    if closed { lock.unlock(); c.resume(throwing: ToolsStopped()); return }
    if Task.isCancelled { lock.unlock(); c.resume(throwing: CancellationError()); return }
    waiting[id] = c
    lock.unlock()
    write(["jsonrpc": "2.0", "id": id, "method": method, "params": params])
   }
  } onCancel: {
   lock.lock(); let w = waiting.removeValue(forKey: id); lock.unlock()
   w?.resume(throwing: CancellationError())
  }
  if let error = reply["error"] as? [String: Any] { throw ApiFailure(AgentStream.str(error["message"]) ?? "Still's tools refused.") }
  return reply["result"] as? [String: Any] ?? [:]
 }
 private func nextId() -> Int { lock.lock(); defer { lock.unlock() }; next += 1; return next }
 func tools() async throws -> [[String: Any]] { try await request("tools/list", [:])["tools"] as? [[String: Any]] ?? [] }
 func call(_ name: String, _ args: [String: Any]) async throws -> (Bool, [[String: Any]]) {
  let result = try await request("tools/call", ["name": name, "arguments": args])
  return (!AgentStream.isTrue(result["isError"]), result["content"] as? [[String: Any]] ?? [])
 }
 /// Ends Still's tools for this run, and everything they started.
 func end() { process.kill() }
}

// MARK: Settings → Models → API providers

var apiTests: [String: [String: Any]] = [:] // provider id → its last Test connection, for the shell
var apiBusy = "", apiError = ""              // a provider being tested or listed; the last form error
let apiJobs: Set<String> = ["chats", "titles", "setup", "test"]

func apiPayload() -> [String: Any] {
 func use(_ u: ApiUse?) -> Any { guard let u else { return NSNull() }; return ["in": u.input, "out": u.output, "cost": u.cost, "calls": u.calls] as [String: Any] }
 let month = ApiProvider.month
 return ["busy": apiBusy, "error": apiError, "providers": apiProviders.map { p -> [String: Any] in
  let has = ApiKeys.has(p.id)
  var jobs: [String: Any] = [:]
  for j in apiJobs where p.spent[month + "/" + j] != nil { jobs[j] = use(p.spent[month + "/" + j]) }
  return ["id": p.id, "kind": p.kind, "name": p.name, "url": p.url, "models": p.models.map { ["id": $0.id, "efforts": $0.efforts] as [String: Any] }, "priceIn": p.priceIn, "priceOut": p.priceOut,
   "limit": p.limit, "context": p.context, "noTools": p.noTools, "noKey": p.noKey, "hasKey": has, "keyEnd": has ? ApiKeys.end(p.id) : "", "refused": ApiKeys.refused(p.id),
   "month": use(p.spent[month]), "jobs": jobs, "paused": p.paused, "test": apiTests[p.id].map { $0 as Any } ?? NSNull()]
 }]
}

/// An API call's tokens and cost, added to the provider's month and to the job it was for.
func spend(_ cli: AgentAdapter, _ input: Int64, _ output: Int64, _ cost: Double, _ job: String) {
 guard let api = cli as? ApiAdapter else { return }
 let p = api.provider, month = ApiProvider.month
 for key in [month, month + "/" + (apiJobs.contains(job) ? job : "chats")] {
  var u = p.spent[key] ?? ApiUse()
  u.input += input; u.output += output; u.cost += cost; u.calls += 1
  p.spent[key] = u
 }
 let f = DateFormatter(); f.calendar = Calendar(identifier: .gregorian); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM"
 let oldest = f.string(from: Calendar(identifier: .gregorian).date(byAdding: .month, value: -12, to: Date()) ?? Date())
 for k in p.spent.keys where String(k.prefix(7)) < oldest { p.spent[k] = nil }
 saveApiProviders()
}

/// Fills a provider's models from its own list, where it offers one; otherwise the user types them.
@MainActor func listApiModels(_ p: ApiProvider) async {
 guard let key = ApiKeys.read(p.id) ?? (p.noKey ? "" : nil), apiBusy.isEmpty else { return }
 apiBusy = p.id; publishAiEverywhere()
 do {
  let ids = try await ApiRun.list(p, key)
  if !ids.isEmpty { p.models = ids.map { id in p.models.first { $0.id == id } ?? ApiModel(id: id, efforts: []) }; aiModels[p.id] = nil; saveApiProviders() }
  else if p.models.isEmpty { apiError = "\(p.name) didn't list its models. Type the ones you want." }
 } catch { apiError = "Couldn't get \(p.name)'s models. Type the ones you want." }
 apiBusy = ""
}

extension Browser {
 func handleApi(_ op: String, _ data: [String: Any]) -> Bool {
  guard ["apiSave", "apiModels", "apiKeyRemove", "apiDelete", "apiTest"].contains(op) else { return false }
  func num(_ k: String) -> Double { (data[k] as? NSNumber).map { $0.doubleValue }.flatMap { $0 >= 0 && $0 < 1e7 ? $0 : nil } ?? 0 }
  let p = apiProviders.first { $0.id == argText(data, "id") }
  apiError = ""
  Task { @MainActor in
   switch op {
   case "apiSave":
    let name = argText(data, "name").trimmingCharacters(in: .whitespacesAndNewlines), key = argText(data, "key").trimmingCharacters(in: .whitespacesAndNewlines)
    var url = argText(data, "url").trimmingCharacters(in: .whitespacesAndNewlines)
    while url.hasSuffix("/") { url.removeLast() }
    if name.isEmpty || name.count > 40 { apiError = "Give it a name, up to 40 characters."; break }
    if ApiRun.address(url) == nil { apiError = "Use an address that starts with https:// (plain http only for localhost)."; break }
    if key.count > 500 || key.unicodeScalars.contains(where: { CharacterSet.whitespacesAndNewlines.contains($0) || CharacterSet.controlCharacters.contains($0) }) { apiError = "That key has spaces or line breaks in it. Copy it again."; break }
    let saved = p ?? ApiProvider()
    if p == nil { saved.id = "api-" + String(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(8)); apiProviders.append(saved) }
    saved.kind = argText(data, "kind") == "anthropic" ? "anthropic" : "openai"; saved.name = name
    if saved.url != url { saved.url = url; saved.noTools = false; apiTests[saved.id] = nil }
    saved.priceIn = num("priceIn"); saved.priceOut = num("priceOut"); saved.limit = num("limit"); saved.context = Int(min(num("context"), 10_000_000))
    if let list = data["models"] as? [Any] {
     var seen = Set<String>()
     let ids = list.compactMap { ($0 as? String)?.trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty && $0.count <= 120 && !$0.contains(where: \.isWhitespace) && !$0.contains("\"") && seen.insert($0).inserted }.prefix(300)
     saved.models = ids.map { id in saved.models.first { $0.id == id } ?? ApiModel(id: id, efforts: []) }
    }
    if !key.isEmpty { ApiKeys.save(saved.id, key); saved.noKey = false } else if !ApiKeys.has(saved.id) { saved.noKey = true } // no key, by choice: a local or open server
    aiClisCache = nil; aiModels[saved.id] = nil; saveApiProviders()
    if saved.models.isEmpty { await listApiModels(saved) }
    await checkAis(true)
    if AgentStream.isTrue(data["use"]) { useAi(saved.id) }                                  // setup: the AI it connects
    if AgentStream.isTrue(data["test"]), let first = saved.models.first { await testApi(saved, first.id) } // setup's Test connection saves first
   case "apiModels": if let p { await listApiModels(p) }
   case "apiKeyRemove":
    guard let p else { break }
    ApiKeys.remove(p.id); apiTests[p.id] = nil; await checkAis(true)
   case "apiDelete":
    guard let p, !runs.values.contains(where: { $0.chat.harness == p.id }) else { break }
    ApiKeys.remove(p.id); apiTests[p.id] = nil
    apiProviders.removeAll { $0 === p }
    if store.prefs["AiHarness"] as? String == p.id { store.prefs["AiHarness"] = "" }
    for c in companions where c.ai == p.id { c.ai = "" }
    aiClisCache = nil; aiModels[p.id] = nil; aiStatus[p.id] = nil; saveAllLater()
   case "apiTest":
    guard let p else { break }
    await testApi(p, p.models.contains { $0.id == argText(data, "model") } ? argText(data, "model") : p.models.first?.id ?? "")
   default: break
   }
   publishAiEverywhere()
  }
  return true
 }

 /// Test connection: one tiny request to the provider, then each part's result for the shell.
 @MainActor func testApi(_ p: ApiProvider, _ model: String) async {
  guard apiBusy.isEmpty else { return }
  guard let secret = ApiKeys.read(p.id) ?? (p.noKey ? "" : nil) else { apiError = "Add a key first."; return }
  if model.isEmpty { apiError = "Add a model first."; return }
  apiBusy = p.id; publishAiEverywhere()
  let (checks, input, output) = await ApiRun.test(p, secret, model)
  apiBusy = ""
  if input + output > 0 { spend(ApiAdapter(p), input, output, p.costOf(input, output), "test") }
  if let tools = checks.first(where: { $0.part == "Tools" }) { p.noTools = !tools.ok }
  if let effort = checks.first(where: { $0.part == "Effort" }), let i = p.models.firstIndex(where: { $0.id == model }) { p.models[i].efforts = effort.ok ? agentEfforts : [] }
  if checks.contains(where: { $0.part == "Key" && !$0.ok }) { ApiKeys.setRefused(p.id, true) } else if checks.contains(where: { $0.part == "Key" && $0.ok }) { ApiKeys.setRefused(p.id, false) }
  apiTests[p.id] = ["model": model, "at": isoText(Date()), "checks": checks.map { ["part": $0.part, "ok": $0.ok, "text": $0.text] as [String: Any] }]
  aiClisCache = nil; aiModels[p.id] = nil; saveApiProviders(); await checkAis(true)
 }
}
