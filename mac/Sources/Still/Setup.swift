// "Set it up with <name>": an interview run by the user's own AI app (small messages on their plan) that follows up on
// what they say until it knows them, then sets Still up around them (setup.md): settings, companions from Still's
// library, what each companion focuses on and remembers, and starter routines, off. Every change keeps an undo, and the
// text ones can be reworded in the summary. Quick setup never comes here and never runs an AI (ported from MainWindow.Setup.cs).
import AppKit

final class SetupTalk {
 let companion: String
 let library: [[String: Any]] // Still's companions as the welcome hires them, with their role and area
 var session: String?
 var started = false, busy = false, done = false
 var error = ""
 var turns: [[String: Any]] = [] // what was said, for the welcome to show: { role, text, options }
 var changes: [SetupChange] = []
 init(_ companion: String, _ library: [[String: Any]]) { self.companion = companion; self.library = library }
}
final class SetupChange {
 let key: String, label: String
 let owner: String // the companion it's for: a companion setup hired takes what it gave it along when it goes
 var value: String
 let undo: () -> Void
 let edit: ((String) -> String?)? // puts the user's own wording in: what's shown after, or nil if none of it is kept
 var undone = false
 init(_ key: String, _ label: String, _ value: String, owner: String, edit: ((String) -> String?)?, _ undo: @escaping () -> Void) {
  self.key = key; self.label = label; self.value = value; self.owner = owner; self.edit = edit; self.undo = undo
 }
}
var setupTalk: SetupTalk?
var welcomeTalk = false // setup opens straight into the interview ("set me up again")

let setUpAgain = try! NSRegularExpression(pattern: #"^\s*(please\s+)?(set\s+(me|it|still)\s+up\s+again|redo\s+(my\s+)?setup|run\s+setup\s+again)\b[\s.!?]*$"#, options: .caseInsensitive)
func setUpAgainAsked(_ text: String) -> Bool { setUpAgain.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil }

func publishSetup() {
 let data: Any = setupTalk.map { s in ["busy": s.busy, "error": s.error, "done": s.done, "turns": s.turns,
  "changes": s.changes.map { ["key": $0.key, "label": $0.label, "value": $0.value, "undone": $0.undone, "editable": $0.edit != nil] }] as [String: Any] } ?? NSNull()
 for browser in browsers { browser.send(["kind": "setup", "data": data]) }
}

/// Takes a change back. A companion setup hired goes with everything setup gave it.
func undoSetup(_ s: SetupTalk, _ c: SetupChange) {
 c.undo(); c.undone = true
 if c.key.hasPrefix("hire:") { for x in s.changes where x.owner == c.owner { x.undone = true } }
}

/// The JSON object in a reply, from its first { to its last }.
func parseObject(_ text: String) -> [String: Any]? {
 guard let a = text.firstIndex(of: "{"), let b = text.lastIndex(of: "}"), a < b else { return nil }
 return jsonObject(String(text[a...b]))
}

/// Routine days as the profile panel shows them.
func routineDays(_ d: [Int]) -> String {
 d.count == 7 ? "Every day" : d == [1, 2, 3, 4, 5] ? "Weekdays" : d == [0, 6] ? "Weekends" : d.map { ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][$0] }.joined(separator: ", ")
}

extension Browser {
 func handleSetup(_ op: String, _ data: [String: Any]) {
  func s(_ k: String) -> String { data[k] as? String ?? "" }
  switch op {
  case "setupStart":
   setupTalk = SetupTalk(s("companion"), (data["library"] as? [Any])?.compactMap { $0 as? [String: Any] } ?? []); welcomeTalk = false
   Task { await setupAsk("Start now: say hello in one line and ask your first question.", "") }
  case "setupAnswer":
   let answer = tidy(s("text"))
   if setupTalk?.busy == false, (1...2000).contains(answer.count) { Task { await setupAsk(answer, answer) } }
  case "setupUndo":
   guard let talk = setupTalk else { break }
   for c in talk.changes where !c.undone && (s("key").isEmpty || c.key == s("key")) { undoSetup(talk, c) }
   storeCompanions(); publishEverywhere(); publishAiEverywhere(); publishSetup()
  case "setupEdit":
   let value = tidy(s("value"))
   guard let c = setupTalk?.changes.first(where: { $0.key == s("key") && !$0.undone && $0.edit != nil }), (1...1000).contains(value.count) else { break }
   if let shown = c.edit?(value) { c.value = shown } else { c.undone = true; toast("That looks like a password or a code, so it isn't kept.") }
   storeCompanions(); publishEverywhere(); publishAiEverywhere(); publishSetup()
  default: setupTalk = nil; publishSetup() // setupEnd
  }
 }

 @MainActor func setupAsk(_ text: String, _ shown: String) async {
  guard let s = setupTalk else { return }
  let who = companions.first { $0.id == s.companion } ?? companions.first
  let harness = who.map { $0.ai.isEmpty ? pref("AiHarness", "") : $0.ai } ?? pref("AiHarness", "")
  let cli = aiClis.first { $0.id == harness }
  if !shown.isEmpty { s.turns.append(["role": "user", "text": shown]) }
  guard let cli, let exe = findCli(cli.command) else { s.error = "No AI app is set up yet."; publishSetup(); return }
  s.busy = true; s.error = ""; publishSetup()
  let prompt = (s.started ? "" : setupPrompt(who, cli, s) + "\n\n") + text, folder = (aiFolder as NSString).appendingPathComponent("setup")
  var mcp = ["--mcp", "--no-tools", "--as", cli.name, "--this-profile", "--profile", support.path, "--profiles-root", profileHome.path]
  if isQa { mcp.insert("--qa", at: 1) }
  var (model, effort) = forMode(cli.id, "efficient") // the quickest model: setup is small talk
  if !(aiModels[cli.id] ?? []).contains(where: { $0.id == model }) { model = ""; effort = "" }
  var said = "", request: RunRequest?
  do {
   if cli.namesSession && s.session == nil { s.session = UUID().uuidString.lowercased() }
   let r = RunRequest(prompt: prompt, model: model, effort: effort, folder: folder, mcp: mcp, session: s.session, resume: s.started && s.session != nil)
   request = r
   let run = try await cli.start(exe, r)
   let limit = DispatchWorkItem { run.cancel() }
   DispatchQueue.main.asyncAfter(deadline: .now() + 120, execute: limit)
   for await e in run.events() {
    switch e {
    case .message(let m, let join): said += join.map { $0 + m } ?? (said.isEmpty ? "" : "\n") + m
    case .session(let id): if s.session == nil { s.session = id }
    default: break
    }
   }
   limit.cancel()
   s.started = s.session != nil
   if run.cancelled { s.error = "\(cli.app) didn't answer." }
   else if said.isEmpty { s.error = run.errors.last(where: { !tidy($0).isEmpty }).map(signedOut) == true ? "\(cli.name) isn't signed in." : "\(cli.app) didn't answer." }
  } catch { s.error = "\(cli.app) didn't answer."; NSLog("Still: setup: \(error)") }
  if let r = request { try? FileManager.default.removeItem(atPath: r.promptFile) }
  if setupTalk !== s { return } // the user left setup meanwhile
  s.busy = false
  if !said.isEmpty {
   let reply = parseObject(said)
   func str(_ k: String) -> String { tidy(reply?[k] as? String ?? "") }
   if AgentStream.isTrue(reply?["done"]), let settings = reply?["settings"] as? [String: Any] {
    for c in s.changes where !c.undone { undoSetup(s, c) } // a second round (the user asked for a change) starts from where they were
    s.changes.removeAll(); s.done = true
    setupApply(settings, who)
    s.turns.append(["role": "ai", "text": str("say").isEmpty ? "All set. Here's what I set up for you." : str("say")])
    storeCompanions(); publishEverywhere(); publishAiEverywhere()
   } else {
    let options = (reply?["options"] as? [Any] ?? []).map { tidy($0 as? String ?? "") }.filter { (1...80).contains($0.count) }.prefix(4)
    let line = reply == nil ? tidy(said) : [str("say"), str("question")].filter { !$0.isEmpty }.joined(separator: "\n")
    s.done = false // asked to change something, it asks back: the summary waits for the next "done"
    s.turns.append(["role": "ai", "text": String(line.prefix(1200)), "options": Array(options)])
   }
  }
  publishSetup()
 }

 /// One clean sentence: single spaces, a capital first letter and a full stop.
 func sentence<S: StringProtocol>(_ s: S) -> String {
  let t = tidy(s.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)).trimmingCharacters(in: CharacterSet(charactersIn: ",;: "))
  guard let first = t.first else { return t }
  return first.uppercased() + String(t.dropFirst()) + (".!?".contains(t.last!) ? "" : ".")
 }
 func setupPrompt(_ who: Companion?, _ cli: AgentAdapter, _ talk: SetupTalk) -> String {
  func field(_ x: [String: Any], _ k: String) -> String { x[k] as? String ?? "" }
  func role(_ c: Companion) -> String {
   if !c.crew.isEmpty, let x = talk.library.first(where: { field($0, "crew") == c.crew }) { return field(x, "role") }
   return c.job.count > 100 ? String(c.job.prefix(100)) + "..." : c.job.isEmpty ? "their own companion" : c.job
  }
  let free = talk.library.filter { x in !companions.contains { $0.crew == field(x, "crew") } }.map { "- \(field($0, "crew")): \(field($0, "name")), \(field($0, "role")), \(field($0, "area"))" }
  return ((try? String(contentsOf: resources.appendingPathComponent("setup.md"), encoding: .utf8)) ?? "")
   .replacingOccurrences(of: "{{name}}", with: who?.name ?? "the user's companion")
   .replacingOccurrences(of: "{{picked}}", with: who.map { $0.job.isEmpty ? "" : "The user picked you as: " + $0.job } ?? "")
   .replacingOccurrences(of: "{{team}}", with: companions.map { "- \($0.id): \($0.name), \(role($0))" }.joined(separator: "\n"))
   .replacingOccurrences(of: "{{library}}", with: free.isEmpty ? "(none, they have them all)" : free.joined(separator: "\n"))
   .replacingOccurrences(of: "{{now}}", with: "tabs \(pref("TabLayout", "Classic") == "Modern" ? "down the side" : "across the top"), theme \(pref("Theme", "System")), search \(pref("SearchEngine", "Google"))")
   .replacingOccurrences(of: "{{cli}}", with: cli.name)
 }

 /// How often the AI asks before clicking and typing, for every site and companion (Windows: SetPermission("", "interact", "", mode)).
 func setInteractPermission(_ mode: String?) {
  var list = pref("Permissions", [[String: Any]]()).filter { !isInteractDefault($0) }
  if let mode, ["always", "chat", "ask"].contains(mode) { list.append(["Site": "", "Action": "interact", "Companion": "", "Mode": mode]) }
  prefs["Permissions"] = list; saveLater()
 }
 func isInteractDefault(_ p: [String: Any]) -> Bool { (p["Site"] as? String ?? "").isEmpty && (p["Companion"] as? String ?? "").isEmpty && p["Action"] as? String == "interact" }

 /// Applies what the interview settled on. Each change keeps its own undo; anything invalid is left out.
 func setupApply(_ st: [String: Any], _ who: Companion?) {
  guard let talk = setupTalk else { return }
  func change(_ key: String, _ label: String, _ value: String, owner: String = "", edit: ((String) -> String?)? = nil, _ undo: @escaping () -> Void) {
   talk.changes.append(SetupChange(key, label, value, owner: owner, edit: edit, undo))
  }
  func str(_ k: String, _ max: Int = 200, _ o: [String: Any]? = nil) -> String { String(tidy((o ?? st)[k] as? String ?? "").prefix(max)) }
  func sites(_ k: String, _ max: Int) -> [(title: String, url: String)] {
   var hosts = Set<String>()
   return Array((st[k] as? [Any] ?? []).compactMap { $0 as? [String: Any] }
    .map { (title: tidy($0["title"] as? String ?? ""), url: tidy($0["url"] as? String ?? "")) }
    .filter { x in URL(string: x.url).map { ["https", "http"].contains($0.scheme ?? "") && $0.host != nil } == true && x.url.count < 300 }
    .map { (title: (1...40).contains($0.title.count) ? $0.title : hostName($0.url), url: $0.url) }
    .filter { hosts.insert(hostName($0.url)).inserted }.prefix(max))
  }
  func texts(_ k: String, _ max: Int, _ len: Int, _ o: [String: Any]? = nil) -> [String] { Array(((o ?? st)[k] as? [Any] ?? []).map { tidy($0 as? String ?? "") }.filter { $0.count > 1 && $0.count <= len }.prefix(max)) }
  // Each one its own short sentence: an answer with two sentences becomes two memories.
  func sentences(_ lines: [String]) -> [String] {
   Array(lines.flatMap { $0.replacingOccurrences(of: #"\n+|(?<=[.!?])\s+(?=\p{Lu})"#, with: "\n", options: .regularExpression).split(separator: "\n").map { sentence($0) } }.filter { $0.count > 2 }.prefix(8))
  }
  // What it learned goes into memory, like anything else a companion remembers: undo forgets it, and an edit swaps the
  // user's lines in. The summary shows what the first companion keeps.
  func remember(_ key: String, _ label: String, _ to: [Companion], _ lines: [String], owner: String = "") {
   func keep(_ lines: [String]) -> [(String, Fact)] {
    to.filter { c in companions.contains { $0 === c } }.flatMap { c in lines.compactMap { f in
     CompanionMemory.remember(c.id, f, "preference", "", f.hasPrefix("Likes to be called ") ? "name" : f.hasPrefix("Works on ") ? "interests" : "").map { (c.id, $0) } } }
   }
   var kept = keep(lines)
   func shown() -> String { kept.filter { $0.0 == to[0].id }.map(\.1.text).joined(separator: "\n") }
   func forget() { for (id, f) in kept { CompanionMemory.forget(id, f.id) } }
   if kept.contains(where: { $0.0 == to[0].id }) {
    change(key, label, shown(), owner: owner, edit: { text in forget(); kept = keep(sentences([text])); return kept.isEmpty ? nil : shown() }) { forget() }
   }
  }
  let theme = { [self] (t: String) in prefs["Theme"] = t; for browser in browsers { browser.applyTheme() } }

  if ["Classic", "Modern"].contains(str("layout")) && str("layout") != pref("TabLayout", "Classic") {
   let old = pref("TabLayout", "Classic"); prefs["TabLayout"] = str("layout")
   change("layout", "Tabs", str("layout") == "Modern" ? "Down the side" : "Across the top") { [self] in prefs["TabLayout"] = old }
  }
  if ["Light", "Dark", "System"].contains(str("theme")) && str("theme") != pref("Theme", "System") {
   let old = pref("Theme", "System"); theme(str("theme"))
   change("theme", "Theme", str("theme") == "System" ? "Matches your system" : str("theme")) { theme(old) }
  }
  if ["Google", "Bing", "DuckDuckGo"].contains(str("search")) && str("search") != pref("SearchEngine", "Google") {
   let old = pref("SearchEngine", "Google"); prefs["SearchEngine"] = str("search")
   change("search", "Search", str("search")) { [self] in prefs["SearchEngine"] = old }
  }
  let pins = sites("pinned", 4).filter { x in !tabs.contains { $0.pinned && hostName($0.url) == hostName(x.url) } }
  if !pins.isEmpty {
   // Pinned tabs wait unloaded until they're first opened, like pinned tabs after a restart.
   let added = pins.map { x -> Tab in let t = Tab(); t.title = x.title; t.url = x.url; t.pinned = true; return t }
   tabs.insert(contentsOf: added, at: 0)
   change("pinned", "Pinned", added.map(\.title).joined(separator: ", ")) { [self] in for t in added { if t.view == nil { tabs.removeAll { $0 === t } } else { close(t) } } }
  }
  let marks = sites("sites", 8).filter { x in !bookmarks.contains { hostName($0["Url"] as? String ?? "") == hostName(x.url) } }
  if !marks.isEmpty {
   bookmarks.insert(contentsOf: marks.map { ["Title": $0.title, "Url": $0.url] }, at: 0)
   let urls = Set(marks.map(\.url))
   change("sites", "Your sites", marks.map(\.title).joined(separator: ", ")) { [self] in bookmarks.removeAll { urls.contains($0["Url"] as? String ?? "") } }
  }
  if ["companion", "sites"].contains(str("newTab")) && str("newTab") != pref("NewTab", "companion") {
   let old = pref("NewTab", "companion"); prefs["NewTab"] = str("newTab")
   change("newTab", "New tab page", str("newTab") == "sites" ? "Search and your sites" : "\(who?.name ?? "Your companion") and ideas") { [self] in prefs["NewTab"] = old }
  }
  let level = str("agent")
  if ["careful", "balanced", "hands-off"].contains(level) {
   // How often the AI asks before clicking and typing. Buying, sending and deleting ("sensitive") always ask.
   let old = pref("Permissions", [[String: Any]]()).first(where: isInteractDefault)?["Mode"] as? String
   setInteractPermission(level == "careful" ? "ask" : level == "hands-off" ? "always" : "chat")
   change("agent", "When I work in tabs", level == "careful" ? "I ask before every click" : level == "hands-off" ? "I just do it, but always ask before buying, sending or deleting" : "I ask once per site in each chat") { [self] in setInteractPermission(old) }
  }
  if let who, str("tone", 600).count > 3, str("tone", 600) != who.tone {
   let old = who.tone; who.tone = str("tone", 600)
   change("tone", "How I talk", who.tone, edit: { t in who.tone = String(t.prefix(600)); return who.tone }) { who.tone = old }
  }
  let interests = texts("interests", 6, 40)
  if !interests.isEmpty {
   let old = pref("Interests", [String]()); prefs["Interests"] = interests
   change("interests", "Ideas about", interests.joined(separator: ", ")) { [self] in prefs["Interests"] = old }
  }

  // Companions from Still's library whose work matches theirs, hired as the library hires them: routine off.
  var hired: [String: Companion] = [:]
  for crew in texts("hire", 3, 24) where !companions.contains(where: { $0.crew == crew }) {
   guard let entry = talk.library.first(where: { $0["crew"] as? String == crew }) else { continue }
   let c = saveCompanion(entry); hired[crew] = c
   change("hire:" + crew, "New on your team", "\(entry["role"] as? String ?? "") \(c.name) · \(entry["area"] as? String ?? "")", owner: c.id) { [self] in dropCompanion(c) }
  }
  func find(_ id: String) -> Companion? { hired[id] ?? companions.first { $0.id == id } ?? companions.first { !id.isEmpty && $0.crew == id } }
  func whose(_ c: Companion, _ mine: String, _ theirs: String) -> String { c === who ? mine : theirs.replacingOccurrences(of: "{0}", with: c.name) }

  if let who {
   var facts = sentences(texts("memories", 8, 200))
   let name = str("name", 40)
   if !name.isEmpty { facts.insert("Likes to be called " + name + ".", at: 0) }
   if !interests.isEmpty { facts.append("Works on " + interests.joined(separator: ", ").lowercased() + ".") }
   remember("memory", companions.count > 1 ? "Your team will remember" : "I'll remember", [who] + companions.filter { $0 !== who }, facts)
  }
  // What each companion focuses on for them goes under its own instructions, after "For me:", so setting up again
  // replaces it.
  for o in (st["companions"] as? [Any] ?? []).compactMap({ $0 as? [String: Any] }).prefix(10) {
   guard let c = find(str("id", 24, o)) else { continue }
   let focus = str("instructions", 600, o), before = c.job.components(separatedBy: "\n\nFor me: ")[0]
   if focus.count > 10 && before.count < 900 {
    let old = c.job
    func focusOn(_ t: String) -> String { let t = String(t.prefix(990 - before.count)); c.job = (before + "\n\nFor me: " + t).trimmingCharacters(in: .whitespacesAndNewlines); return t }
    change("focus:" + c.id, whose(c, "What I'll focus on", "What {0} will focus on"), focusOn(focus), owner: c.id, edit: focusOn) { c.job = old }
   }
   remember("memory:" + c.id, whose(c, "I'll also remember", "{0} will also remember"), [c], sentences(texts("memories", 6, 200, o)), owner: c.id)
  }
  for o in (st["routines"] as? [Any] ?? []).compactMap({ $0 as? [String: Any] }).prefix(3) {
   guard let c = find(str("id", 24, o)) else { continue }
   var r = o; r["id"] = nil; r["on"] = false
   guard let routine = Routine.read([r], old: []).first else { continue }
   c.routines.append(routine)
   change("routine:" + routine.id, whose(c, "My routine, off for now", "{0}'s routine, off for now"), "\(routineDays(routine.days)) at \(routine.time): \(routine.text)", owner: c.id) { c.routines.removeAll { $0.id == routine.id } }
  }
  // What they want help with first: the welcome offers it as their first task.
  let first = str("first", 300)
  if first.count > 3 { change("first", "First, I'll help with", first, edit: { $0 }) {} }
 }
}
