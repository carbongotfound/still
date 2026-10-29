// "Set it up with <name>": a short interview run by the user's own AI app (a few small messages on their plan), then
// the settings it picked, each with an undo. Quick setup never comes here and never runs an AI (ported from MainWindow.Setup.cs).
import AppKit

final class SetupTalk {
 let companion: String
 var session: String?
 var started = false, busy = false, done = false
 var error = ""
 var turns: [[String: Any]] = [] // what was said, for the welcome to show: { role, text, options }
 var changes: [SetupChange] = []
 var also: [String] = [] // the other companions picked in setup: they learn the same things
 init(_ companion: String) { self.companion = companion }
}
final class SetupChange {
 let key: String, label: String, value: String
 let undo: () -> Void
 var undone = false
 init(_ key: String, _ label: String, _ value: String, _ undo: @escaping () -> Void) { self.key = key; self.label = label; self.value = value; self.undo = undo }
}
var setupTalk: SetupTalk?
var welcomeTalk = false // setup opens straight into the interview ("set me up again")

let setUpAgain = try! NSRegularExpression(pattern: #"^\s*(please\s+)?(set\s+(me|it|still)\s+up\s+again|redo\s+(my\s+)?setup|run\s+setup\s+again)\b[\s.!?]*$"#, options: .caseInsensitive)
func setUpAgainAsked(_ text: String) -> Bool { setUpAgain.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil }

func publishSetup() {
 let data: Any = setupTalk.map { s in ["busy": s.busy, "error": s.error, "done": s.done, "turns": s.turns,
  "changes": s.changes.map { ["key": $0.key, "label": $0.label, "value": $0.value, "undone": $0.undone] }] as [String: Any] } ?? NSNull()
 for browser in browsers { browser.send(["kind": "setup", "data": data]) }
}

/// The JSON object in a reply, from its first { to its last }.
func parseObject(_ text: String) -> [String: Any]? {
 guard let a = text.firstIndex(of: "{"), let b = text.lastIndex(of: "}"), a < b else { return nil }
 return jsonObject(String(text[a...b]))
}

extension Browser {
 func handleSetup(_ op: String, _ data: [String: Any]) {
  func s(_ k: String) -> String { data[k] as? String ?? "" }
  switch op {
  case "setupStart":
   setupTalk = SetupTalk(s("companion")); setupTalk?.also = (data["also"] as? [Any])?.compactMap { $0 as? String } ?? []; welcomeTalk = false
   Task { await setupAsk("Start now: say hello in one line and ask your first question.", "") }
  case "setupAnswer":
   let answer = tidy(s("text"))
   if setupTalk?.busy == false, (1...2000).contains(answer.count) { Task { await setupAsk(answer, answer) } }
  case "setupUndo":
   guard let talk = setupTalk else { break }
   for c in talk.changes where !c.undone && (s("key").isEmpty || c.key == s("key")) { c.undo(); c.undone = true }
   saveLater(); publishEverywhere(); publishAiEverywhere(); publishSetup()
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
  let prompt = (s.started ? "" : setupPrompt(who, cli) + "\n\n") + text, folder = (aiFolder as NSString).appendingPathComponent("setup")
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
    for c in s.changes where !c.undone { c.undo() } // a second round (the user asked for a change) starts from where they were
    s.changes.removeAll(); s.done = true
    setupApply(settings, who)
    s.turns.append(["role": "ai", "text": str("say").isEmpty ? "All set. Here's what I changed." : str("say")])
    saveLater(); publishEverywhere(); publishAiEverywhere()
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
 func setupPrompt(_ who: Companion?, _ cli: AgentAdapter) -> String {
  """
  You are \(who?.name ?? "the user's companion"), the companion in Still, a web browser with AI built in. \(who.map { $0.job.isEmpty ? "" : "The user picked you as: " + $0.job } ?? "")
  Talk like a sharp, friendly coworker: in the first person, short and to the point. Never call yourself by your name or in the third person, and no cutesy talk.
  You're setting Still up with the user in a short, friendly chat. Ask one short question at a time, 4 to 6 in all, and adapt to what they say. Find out:
  what they mostly use the browser for, the sites they're on every day, how hands-on they want you to be when you work in tabs for them, what they'd like your help with most, and how they'd like you to talk to them. Skip anything they've already told you. Don't use any tools and don't look anything up.

  Reply with ONLY one JSON object and nothing else:
  {"say": "a short, warm reaction to their answer (or hello)", "question": "your next question", "options": ["2 to 4 short answers they can tap"]}
  Write plainly, in second person, no em dashes. Don't call Still quiet, calm or minimal.

  When you know enough, or they ask you to finish, reply instead with:
  {"say": "one line wrapping up", "done": true, "settings": {
   "name": "what they want to be called, or empty",
   "interests": ["up to 6 short topics they care about"],
   "layout": "Classic" (tabs across the top) or "Modern" (tabs down the side) or "",
   "theme": "Light", "Dark", "System" or "",
   "search": "Google", "Bing", "DuckDuckGo" or "",
   "pinned": [{"title": "Site", "url": "https://..."}] (up to 4 sites they use all day, kept as pinned tabs),
   "sites": [{"title": "Site", "url": "https://..."}] (up to 8 sites for their new tab page),
   "newTab": "companion" (you and ideas on the new tab page) or "sites" (search and their sites) or "",
   "agent": "careful" (ask before every click), "balanced" (ask once per site in a chat) or "hands-off" (just do it) or "",
   "tone": "how they want you to talk, one or two short sentences addressed to you, like 'Keep answers short and skip the small talk.'",
   "memories": ["facts worth remembering about them, each one short sentence"]} }
  Use "" or [] for anything they didn't say: Still leaves those as they are. Buying, sending and deleting always ask, whatever they pick.

  Still right now: tabs \(pref("TabLayout", "Classic") == "Modern" ? "down the side" : "across the top"), theme \(pref("Theme", "System")), search \(pref("SearchEngine", "Google")). They're using \(cli.name).
  """
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
  func change(_ key: String, _ label: String, _ value: String, _ undo: @escaping () -> Void) { talk.changes.append(SetupChange(key, label, value, undo)) }
  func str(_ k: String, _ max: Int = 200) -> String { String(tidy(st[k] as? String ?? "").prefix(max)) }
  func sites(_ k: String, _ max: Int) -> [(title: String, url: String)] {
   var hosts = Set<String>()
   return Array((st[k] as? [Any] ?? []).compactMap { $0 as? [String: Any] }
    .map { (title: tidy($0["title"] as? String ?? ""), url: tidy($0["url"] as? String ?? "")) }
    .filter { x in URL(string: x.url).map { ["https", "http"].contains($0.scheme ?? "") && $0.host != nil } == true && x.url.count < 300 }
    .map { (title: (1...40).contains($0.title.count) ? $0.title : hostName($0.url), url: $0.url) }
    .filter { hosts.insert(hostName($0.url)).inserted }.prefix(max))
  }
  func texts(_ k: String, _ max: Int, _ len: Int) -> [String] { Array((st[k] as? [Any] ?? []).map { tidy($0 as? String ?? "") }.filter { $0.count > 1 && $0.count <= len }.prefix(max)) }
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
   let old = who.tone; who.tone = str("tone", 600); storeCompanions()
   change("tone", "How I talk", who.tone) { [self] in who.tone = old; storeCompanions() }
  }
  let interests = texts("interests", 6, 40)
  if !interests.isEmpty {
   let old = pref("Interests", [String]()); prefs["Interests"] = interests
   change("interests", "Ideas about", interests.joined(separator: ", ")) { [self] in prefs["Interests"] = old }
  }
  if let who {
   // What it learned goes into the companion's memory, like anything else it remembers.
   // Each one its own short sentence: an answer with two sentences becomes two memories.
   var facts = Array(texts("memories", 8, 200).flatMap { $0.replacingOccurrences(of: #"(?<=[.!?])\s+(?=\p{Lu})"#, with: "\n", options: .regularExpression).split(separator: "\n").map { sentence($0) } }.filter { $0.count > 2 }.prefix(8))
   let name = str("name", 40)
   if !name.isEmpty { facts.insert("Likes to be called " + name + ".", at: 0) }
   if !interests.isEmpty { facts.append("Into " + interests.joined(separator: ", ").lowercased() + ".") }
   var ids = [who.id]
   for id in setupTalk?.also ?? [] where !ids.contains(id) && companions.contains(where: { $0.id == id }) { ids.append(id) }
   let kept = ids.flatMap { id in facts.enumerated().compactMap { i, f in CompanionMemory.remember(id, f, "preference", "", i == 0 && !name.isEmpty ? "name" : f.hasPrefix("Into ") ? "interests" : "").map { (id, $0) } } }
   let mine = kept.filter { $0.0 == who.id }.map(\.1)
   if !mine.isEmpty { change("memory", "I'll remember", mine.map(\.text).joined(separator: "\n")) { for (id, f) in kept { CompanionMemory.forget(id, f.id) } } }
  }
 }
}
