// Each companion's memory of the user (ported from CompanionMemory.cs): companions/<id>/memory.json in the profile, plain
// JSON on this Mac, and only ever put into that companion's own chats. Passwords, codes, card numbers and private tabs never go in.
import Foundation

/// One thing a companion remembers about the user.
final class Fact: Codable {
 var id = String(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(8))
 var text = ""
 var kind = "fact" // fact, preference, habit, person, project, or chat (a past chat)
 var at = Date()
 var chat = "" // the chat it came from; "" = setup, or the user typed it
 var key = "" // a slot that holds one fact ("name", "interests", "chat:<id>"): a new one replaces it
 enum CodingKeys: String, CodingKey { case id, text, kind, at, chat, key }
 init(_ text: String, _ kind: String, _ chat: String, _ key: String) { self.text = text; self.kind = kind; self.chat = chat; self.key = key }
 init(from decoder: Decoder) throws {
  let c = try decoder.container(keyedBy: CodingKeys.self)
  id = try c.decodeIfPresent(String.self, forKey: .id) ?? id
  text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
  kind = try c.decodeIfPresent(String.self, forKey: .kind) ?? "fact"
  at = try c.decodeIfPresent(Date.self, forKey: .at) ?? Date()
  chat = try c.decodeIfPresent(String.self, forKey: .chat) ?? ""
  key = try c.decodeIfPresent(String.self, forKey: .key) ?? ""
 }
}

// Files on disk use the Windows app's names (Id, Text, At...), so the same tests and profiles read on both.
struct PascalKey: CodingKey {
 var stringValue: String
 var intValue: Int? { nil }
 init(stringValue: String) { self.stringValue = stringValue }
 init?(intValue: Int) { nil }
}
func isoText(_ date: Date) -> String {
 let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
 return f.string(from: date)
}
func isoDate(_ text: String) -> Date? {
 let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
 if let date = f.date(from: text) { return date }
 f.formatOptions = [.withInternetDateTime]
 return f.date(from: text.replacingOccurrences(of: #"\.\d+"#, with: "", options: .regularExpression))
}
func pascalJSON<T: Encodable>(_ value: T, pretty: Bool = false) throws -> Data {
 let e = JSONEncoder()
 e.keyEncodingStrategy = .custom { path in PascalKey(stringValue: path.last!.stringValue.prefix(1).uppercased() + path.last!.stringValue.dropFirst()) }
 e.dateEncodingStrategy = .custom { date, encoder in var c = encoder.singleValueContainer(); try c.encode(isoText(date)) }
 if pretty { e.outputFormatting = [.prettyPrinted] }
 return try e.encode(value)
}
func fromPascalJSON<T: Decodable>(_ type: T.Type, _ data: Data) throws -> T {
 let d = JSONDecoder()
 d.keyDecodingStrategy = .custom { path in PascalKey(stringValue: path.last!.stringValue.prefix(1).lowercased() + path.last!.stringValue.dropFirst()) }
 d.dateDecodingStrategy = .custom { decoder in isoDate(try decoder.singleValueContainer().decode(String.self)) ?? Date() }
 return try d.decode(type, from: data)
}

enum CompanionMemory {
 static let kinds = ["fact", "preference", "habit", "person", "project", "chat"]
 static var cache: [String: [Fact]] = [:]
 static func folder(_ id: String) -> URL { support.appendingPathComponent("companions").appendingPathComponent(id) }
 static func fileOf(_ id: String) -> URL { folder(id).appendingPathComponent("memory.json") }

 static func of(_ id: String) -> [Fact] {
  if id.isEmpty { return [] }
  if let list = cache[id] { return list }
  var list: [Fact]
  if FileManager.default.fileExists(atPath: fileOf(id).path) {
   do { list = try fromPascalJSON([Fact].self, try Data(contentsOf: fileOf(id))) } catch { NSLog("Still: memory of \(id): \(error)"); list = [] }
  } else { list = migrate(id) }
  cache[id] = list
  return list
 }

 // Before 1.9 memory was free text, one thing per line: notes every companion shared, and each one's own.
 static func migrate(_ id: String) -> [Fact] {
  var list: [Fact] = []
  for old in [support.appendingPathComponent("companions/memory.md"), folder(id).appendingPathComponent("memory.md")] {
   guard let text = try? String(contentsOf: old, encoding: .utf8) else { continue }
   for line in text.components(separatedBy: .newlines) {
    let clean = line.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "-* "))
    _ = add(&list, clean, "fact", "", "")
   }
  }
  return list
 }

 static func save(_ id: String) {
  do {
   try FileManager.default.createDirectory(at: folder(id), withIntermediateDirectories: true)
   try pascalJSON(of(id), pretty: true).write(to: fileOf(id), options: .atomic)
  } catch { NSLog("Still: couldn't save memory of \(id): \(error)") }
 }

 static func drop(_ id: String) { cache[id] = nil } // the companion is gone, folder and all

 static func squash(_ text: String) -> String { text.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression).trimmingCharacters(in: .whitespaces) }

 /// Keeps a fact, or freshens the one it repeats. Nil when it's refused: it looks like a secret, or it's empty.
 @discardableResult static func remember(_ id: String, _ text: String, _ kind: String = "fact", _ chat: String = "", _ key: String = "") -> Fact? {
  let text = squash(text)
  if id.isEmpty || text.count < 3 || secret(text) { return nil }
  var list = of(id)
  let fact = add(&list, text.count > 300 ? String(text.prefix(300)) + "…" : text, kind, chat, key)
  // A long memory keeps everything the user told it and the 60 latest chats.
  let old = list.filter { $0.kind == "chat" }.sorted { $0.at > $1.at }.dropFirst(60)
  list.removeAll { f in old.contains { $0 === f } }
  cache[id] = list
  save(id)
  return fact
 }

 static func add(_ list: inout [Fact], _ text: String, _ kind: String, _ chat: String, _ key: String) -> Fact? {
  if text.count < 3 { return nil }
  let kind = kinds.contains(kind) ? kind : "fact"
  let w = words(text)
  let same = !key.isEmpty ? list.first { $0.key == key } : list.first { $0.key.isEmpty && ($0.kind == "chat") == (kind == "chat") && similar(words($0.text), w) }
  if let same {
   same.text = text; same.kind = kind; same.at = Date()
   if !chat.isEmpty { same.chat = chat }
   return same
  }
  let fact = Fact(text, kind, chat, key)
  list.append(fact)
  return fact
 }

 static func edit(_ id: String, _ factId: String, _ text: String) -> Bool {
  let text = squash(text)
  guard let f = of(id).first(where: { $0.id == factId }), text.count >= 3, !secret(text) else { return false }
  f.text = String(text.prefix(300)); f.at = Date(); save(id)
  return true
 }

 /// Forgets facts by id, or every fact that matches the words given. Returns what it forgot.
 @discardableResult static func forget(_ id: String, _ factIdOrWords: String) -> [Fact] {
  if factIdOrWords.isEmpty { return [] } // "" would match every unkeyed fact
  var list = of(id)
  let q = words(factIdOrWords)
  let gone = list.filter { $0.id == factIdOrWords || $0.key == factIdOrWords || !q.isEmpty && q.isSubset(of: words($0.text)) }
  if !gone.isEmpty { list.removeAll { f in gone.contains { $0 === f } }; cache[id] = list; save(id) }
  return gone
 }

 static func clear(_ id: String) { _ = of(id); cache[id] = []; save(id) }
 static func forgetChat(_ id: String, _ chat: String) {
  var list = of(id)
  let count = list.count
  list.removeAll { $0.chat == chat || $0.key == "chat:" + chat }
  if list.count != count { cache[id] = list; save(id) }
 }

 /// The facts that fit what the user just asked, best first: shared words, then the core things (who they are, what
 /// they like), then the newest. Past chats come last, the related ones first.
 static func relevant(_ id: String, _ query: String, _ count: Int = 14) -> [Fact] {
  let q = words(query), now = Date()
  func score(_ f: Fact) -> Double {
   let shared = Double(words(f.text).intersection(q).count * 2)
   let core: Double = !f.key.isEmpty ? 3 : f.kind == "preference" || f.kind == "person" ? 1 : 0
   let days: Double = now.timeIntervalSince(f.at) / 86400
   return shared + core + 1 / (1 + days / 30)
  }
  // Stable sorts, like LINQ's OrderBy: ties keep the file's order.
  let list = Array(of(id).enumerated())
  let facts: [(Int, Fact, Double)] = list.filter { $0.element.kind != "chat" }.map { ($0.offset, $0.element, score($0.element)) }
  let chats: [(Int, Fact, Int)] = list.filter { $0.element.kind == "chat" }.map { ($0.offset, $0.element, words($0.element.text).intersection(q).count) }
  let best = facts.sorted { (a: (Int, Fact, Double), b: (Int, Fact, Double)) -> Bool in a.2 != b.2 ? a.2 > b.2 : a.0 < b.0 }
  let past = chats.sorted { (a: (Int, Fact, Int), b: (Int, Fact, Int)) -> Bool in
   if a.2 != b.2 { return a.2 > b.2 }
   if a.1.at != b.1.at { return a.1.at > b.1.at }
   return a.0 < b.0
  }
  return best.prefix(count).map { $0.1 } + past.prefix(4).map { $0.1 }
 }

 static func brief(_ id: String, _ query: String) -> String {
  let day = DateFormatter()
  day.locale = Locale(identifier: "en_US_POSIX"); day.dateFormat = "yyyy-MM-dd"
  return relevant(id, query).map { "- \($0.kind == "chat" ? "A past chat: " : "")\($0.text) (\(day.string(from: $0.at)), id \($0.id))" }.joined(separator: "\n")
 }

 /// Never kept: passwords, codes, keys, card and account numbers.
 static func secret(_ text: String) -> Bool { [secretWords, cardNumber, tokenLike].contains { $0.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil } }

 static func similar(_ a: Set<String>, _ b: Set<String>) -> Bool { !a.isEmpty && !b.isEmpty && Double(a.intersection(b).count) / Double(a.union(b).count) >= 0.75 }
 static let stop: Set<String> = ["the", "and", "for", "are", "with", "that", "this", "you", "your", "they", "them", "their", "has", "have", "was", "who", "what", "when", "where", "how", "likes", "user", "user's"]
 static func words(_ text: String) -> Set<String> {
  let lower = text.lowercased()
  return Set(wordRx.matches(in: lower, range: NSRange(lower.startIndex..., in: lower)).compactMap { Range($0.range, in: lower).map { String(lower[$0]) } }.filter { $0.count > 2 && !stop.contains($0) })
 }

 static let wordRx = try! NSRegularExpression(pattern: #"[\p{L}\p{N}']+"#)
 static let secretWords = try! NSRegularExpression(pattern: #"\b(pass ?words?|passcodes?|passwd|pass ?phrases?|pin (codes?|numbers?)|one[- ]time codes?|otp|2fa codes?|verification codes?|security codes?|cvv|cvc|cookie (values?|data|strings?)|session (cookies?|ids?|tokens?)|api ?keys?|secret keys?|private keys?|access tokens?|bearer|social security|ssn|card numbers?|account numbers?|routing numbers?|iban)\b"#, options: .caseInsensitive)
 static let cardNumber = try! NSRegularExpression(pattern: #"\b(?:\d[ -]?){12,19}\b"#)
 static let tokenLike = try! NSRegularExpression(pattern: #"\b(sk|pk|ghp|gho|xox[bap]|AKIA)[-_]?[A-Za-z0-9]{12,}|\b[A-Za-z0-9_\-]{32,}\b"#)
}

/// Why something can't go into memory, or nil if it can: secrets, what the AI typed into a form, anything from a private tab.
func memoryRefuses(_ run: ChatRun?, _ text: String) -> String? {
 if CompanionMemory.secret(text) { return "That looks like a password, a code or an account number. Still never keeps those." }
 if Vault.read().contains(where: { $0.password.count >= 4 && text.contains($0.password) }) { return "That's one of your saved passwords. Still never keeps those." }
 if run?.typed.contains(where: { text.range(of: $0, options: .caseInsensitive) != nil }) == true { return "That's something typed into a form on a page. Still doesn't keep form data." }
 for t in browsers.flatMap(\.tabs) where t.isPrivate {
  let host = hostName(t.url)
  if t.title.count >= 4 && t.title != "Private tab" && text.range(of: t.title, options: .caseInsensitive) != nil
   || host.count > 3 && text.range(of: host, options: .caseInsensitive) != nil { return "That comes from a private tab. Still never keeps those." }
 }
 return nil
}

/// The remember, recall and forget tools: Still's own chat only, on the memory of the companion it's with.
func memoryTool(_ who: String, _ tool: String, _ args: [String: Any]) -> String {
 guard let run = runs[who], let me = companions.first(where: { $0.id == run.chat.companion }) else { return agentFail("Memory belongs to Still's own companions, in their chats.") }
 switch tool {
 case "remember":
  if run.chat.noMemory { return agentFail("This chat is off the record: the user asked you not to remember it.") }
  let fact = argText(args, "fact").trimmingCharacters(in: .whitespacesAndNewlines)
  if let why = memoryRefuses(run, fact) { return agentFail(why) }
  guard let kept = CompanionMemory.remember(me.id, fact, argText(args, "kind"), run.chat.id) else { return agentFail("Pass one short fact.") }
  publishAiEverywhere()
  return agentOk(["remembered": kept.text, "id": kept.id])
 case "recall":
  let day = DateFormatter()
  day.locale = Locale(identifier: "en_US_POSIX"); day.dateFormat = "yyyy-MM-dd"
  return agentOk(["facts": CompanionMemory.relevant(me.id, argText(args, "query"), 12).map { ["id": $0.id, "text": $0.text, "kind": $0.kind, "date": day.string(from: $0.at)] }])
 default:
  let id = argText(args, "id")
  let gone = CompanionMemory.forget(me.id, id.isEmpty ? argText(args, "about") : id)
  publishAiEverywhere()
  return agentOk(["forgot": gone.map(\.text)])
 }
}
