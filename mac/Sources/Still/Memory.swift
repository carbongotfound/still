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
 var guessed = false // worked out from what the user did, not something they said: kept apart until they confirm it
 enum CodingKeys: String, CodingKey { case id, text, kind, at, chat, key, guessed }
 init(_ text: String, _ kind: String, _ chat: String, _ key: String) { self.text = text; self.kind = kind; self.chat = chat; self.key = key }
 init(from decoder: Decoder) throws {
  let c = try decoder.container(keyedBy: CodingKeys.self)
  id = try c.decodeIfPresent(String.self, forKey: .id) ?? id
  text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
  kind = try c.decodeIfPresent(String.self, forKey: .kind) ?? "fact"
  at = try c.decodeIfPresent(Date.self, forKey: .at) ?? Date()
  chat = try c.decodeIfPresent(String.self, forKey: .chat) ?? ""
  key = try c.decodeIfPresent(String.self, forKey: .key) ?? ""
  guessed = try c.decodeIfPresent(Bool.self, forKey: .guessed) ?? false
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

 static func drop(_ id: String) { cache[id] = nil; notesCache[id] = nil } // the companion is gone, folder and all

 // Knowledge files: the working notes of a companion's job, Markdown it keeps up as it works (its role's kit seeds them
 // empty). Each has a name and what it holds in its front matter. They're in its folder, so they go when it does.
 struct Note { let id: String, name: String, about: String, body: String }
 static var notesCache: [String: [Note]] = [:]
 static func notesFolder(_ id: String) -> URL { folder(id).appendingPathComponent("knowledge") }
 static func equipped(_ id: String) -> Bool { FileManager.default.fileExists(atPath: notesFolder(id).path) }
 static func seed(_ id: String, _ file: String, _ text: String) {
  notesCache[id] = nil
  let url = notesFolder(id).appendingPathComponent(file + ".md")
  do {
   try FileManager.default.createDirectory(at: notesFolder(id), withIntermediateDirectories: true)
   if !FileManager.default.fileExists(atPath: url.path) { try text.write(to: url, atomically: true, encoding: .utf8) }
  } catch { NSLog("Still: couldn't start \(file) for \(id): \(error)") }
 }
 static func notes(_ id: String) -> [Note] {
  if id.isEmpty { return [] }
  if let list = notesCache[id] { return list }
  let names = ((try? FileManager.default.contentsOfDirectory(atPath: notesFolder(id).path)) ?? []).filter { $0.hasSuffix(".md") }.sorted().prefix(20)
  let list = names.compactMap { file -> Note? in
   guard let raw = try? String(contentsOf: notesFolder(id).appendingPathComponent(file), encoding: .utf8) else { return nil }
   let (head, body) = frontMatter(raw), fid = (file as NSString).deletingPathExtension
   return Note(id: fid, name: head["name"].flatMap { $0.isEmpty ? nil : $0 } ?? fid, about: head["about"] ?? "", body: body)
  }
  notesCache[id] = list
  return list
 }
 /// Rewrites a knowledge file's notes, keeping its name and what it holds.
 static func write(_ id: String, _ file: String, _ text: String) -> Note? {
  guard let note = notes(id).first(where: { $0.id == file }) else { return nil }
  let body = String(text.replacingOccurrences(of: "\r\n", with: "\n").trimmingCharacters(in: .whitespacesAndNewlines).prefix(12000))
  do { try "---\nname: \(note.name)\nabout: \(note.about)\n---\n\n\(body)\n".write(to: notesFolder(id).appendingPathComponent(file + ".md"), atomically: true, encoding: .utf8) }
  catch { NSLog("Still: couldn't write \(file) for \(id): \(error)"); return nil }
  notesCache[id] = nil
  return Note(id: note.id, name: note.name, about: note.about, body: body)
 }
 /// The knowledge files as the companion's prompt has them, each with what it holds so far.
 static func notesBrief(_ id: String) -> String {
  let list = notes(id)
  if list.isEmpty { return "" }
  return "Your knowledge files, kept on the user's computer. Use what's in them. When you learn something one of them should hold, rewrite that file with update_knowledge: short and tidy, keeping what's still true.\n"
   + list.map { n in "\n## \(n.name) (file \"\(n.id)\"): \(n.about)\n" + (n.body.isEmpty ? "(Empty so far.)" : n.body.count > 4000 ? String(n.body.prefix(4000)) + "\n(…)" : n.body) + "\n" }.joined() + "\n"
 }

 static func squash(_ text: String) -> String { text.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression).trimmingCharacters(in: .whitespaces) }

 /// Keeps a fact, or freshens the one it repeats. Nil when it's refused: it looks like a secret, or it's empty.
 @discardableResult static func remember(_ id: String, _ text: String, _ kind: String = "fact", _ chat: String = "", _ key: String = "", guessed: Bool = false) -> Fact? {
  let text = squash(text)
  if id.isEmpty || text.count < 3 || secret(text) { return nil }
  var list = of(id)
  let fact = add(&list, text.count > 300 ? String(text.prefix(300)) + "…" : text, kind, chat, key, guessed: guessed)
  // A long memory keeps everything the user told it and the 60 latest chats.
  let old = list.filter { $0.kind == "chat" }.sorted { $0.at > $1.at }.dropFirst(60)
  list.removeAll { f in old.contains { $0 === f } }
  cache[id] = list
  save(id)
  return fact
 }

 static func add(_ list: inout [Fact], _ text: String, _ kind: String, _ chat: String, _ key: String, guessed: Bool = false) -> Fact? {
  if text.count < 3 { return nil }
  let kind = kinds.contains(kind) ? kind : "fact"
  let w = words(text)
  let same = !key.isEmpty ? list.first { $0.key == key } : list.first { $0.key.isEmpty && ($0.kind == "chat") == (kind == "chat") && similar(words($0.text), w) }
  if let same {
   same.text = text; same.kind = kind; same.at = Date(); same.guessed = same.guessed && guessed // once confirmed, it stays confirmed
   if !chat.isEmpty { same.chat = chat }
   return same
  }
  let fact = Fact(text, kind, chat, key)
  fact.guessed = guessed
  list.append(fact)
  return fact
 }

 static func edit(_ id: String, _ factId: String, _ text: String) -> Bool {
  let text = squash(text)
  guard let f = of(id).first(where: { $0.id == factId }), text.count >= 3, !secret(text) else { return false }
  f.text = String(text.prefix(300)); f.at = Date(); f.guessed = false; save(id) // the user wrote it: confirmed
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
 /// they like), then the newest. Only facts that share a word with it or are core make it (and everything the user wrote
 /// in setup or on the memory page); past chats only when related.
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
  func related(_ f: Fact) -> Bool { !f.key.isEmpty || f.kind == "preference" || f.kind == "person" || f.chat.isEmpty && !f.guessed || !words(f.text).isDisjoint(with: q) }
  let facts: [(Int, Fact, Double)] = list.filter { $0.element.kind != "chat" && related($0.element) }.map { ($0.offset, $0.element, score($0.element)) }
  let chats: [(Int, Fact, Int)] = list.filter { $0.element.kind == "chat" }.map { ($0.offset, $0.element, words($0.element.text).intersection(q).count) }.filter { $0.2 > 0 }
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
  let facts = relevant(id, query)
  func line(_ f: Fact) -> String { "- \(f.kind == "chat" ? "A past chat: " : "")\(f.text) (\(day.string(from: f.at)), id \(f.id))" }
  let told = facts.filter { !$0.guessed }.map(line), guessed = facts.filter { $0.guessed }.map(line)
  return told.joined(separator: "\n") + (guessed.isEmpty ? "" : (told.isEmpty ? "" : "\n") + "Guessed from what they did, not confirmed (check before relying on them):\n" + guessed.joined(separator: "\n"))
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

/// A companion hired from the crew comes with its role's kit (Assets/roles/<role>/, in the app's resources), once: its
/// skills, added to the user's skills unless there's one by that id already, and turned on for it; and its knowledge
/// files, empty to start. True when it got them.
@discardableResult func equip(_ c: Companion) -> Bool {
 guard !c.crew.isEmpty, !CompanionMemory.equipped(c.id) else { return false }
 let kit = resources.appendingPathComponent("roles").appendingPathComponent(c.crew)
 func files(_ kind: String) -> [URL] {
  let dir = kit.appendingPathComponent(kind)
  return ((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []).filter { $0.hasSuffix(".md") }.sorted().map { dir.appendingPathComponent($0) }
 }
 for file in files("skills") {
  let id = file.deletingPathExtension().lastPathComponent
  guard let text = try? String(contentsOf: file, encoding: .utf8) else { continue }
  do { try Skill.add(id, text); if !c.skills.contains(id) { c.skills.append(id) } } catch { NSLog("Still: couldn't add skill \(id): \(error)") }
 }
 for file in files("knowledge") {
  if let text = try? String(contentsOf: file, encoding: .utf8) { CompanionMemory.seed(c.id, file.deletingPathExtension().lastPathComponent, text) }
 }
 return CompanionMemory.equipped(c.id)
}

/// The remember, recall and forget tools: Still's own chat only, on the memory of the companion it's with.
func memoryTool(_ who: String, _ tool: String, _ args: [String: Any]) -> String {
 guard let run = runs[who], let me = companions.first(where: { $0.id == run.chat.companion }) else { return agentFail("Memory belongs to Still's own companions, in their chats.") }
 if run.chat.from != nil && tool != "recall" { let chain = exchangeOf(run.chat).chain; return agentFail("You're helping \(nameOf(chain[max(0, chain.count - 2)])), who decides what's kept: put what's worth remembering in your reply.") }
 switch tool {
 case "remember":
  if run.chat.noMemory { return agentFail("This chat is off the record: the user asked you not to remember it.") }
  let fact = argText(args, "fact").trimmingCharacters(in: .whitespacesAndNewlines)
  if let why = memoryRefuses(run, fact) { return agentFail(why) }
  guard let kept = CompanionMemory.remember(me.id, fact, argText(args, "kind"), run.chat.id, guessed: argFlag(args, "guessed")) else { return agentFail("Pass one short fact.") }
  publishAiEverywhere()
  return agentOk(["remembered": kept.text, "id": kept.id])
 case "update_knowledge":
  if run.chat.noMemory { return agentFail("This chat is off the record: the user asked you not to keep anything from it.") }
  let text = argText(args, "text")
  if let why = memoryRefuses(run, text) { return agentFail(why) }
  guard let note = CompanionMemory.write(me.id, tidy(argText(args, "file")), text) else { return agentFail("There's no knowledge file by that id. Yours are listed at the start of the chat.") }
  publishAiEverywhere()
  return agentOk(["updated": note.name])
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
