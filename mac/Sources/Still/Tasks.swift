import Foundation

/// Each run is a task with a state and a checkpoint, kept in ai/tasks/<chat>.json (an incognito chat's only in memory):
/// running, paused (the user took over), waiting (an approval, an answer or a sign-in), interrupted (Still closed or
/// crashed mid-run), completed or failed. A sensitive step writes its intent before it runs and its outcome after, so
/// one cut off in between is known to be uncertain: it is never done again without a fresh approval. (Windows: MainWindow.Tasks.cs)
final class AiTask: Codable {
 var chat = "", state = "running", reason = "", ask = "" // reason: waiting for approval, answer or signin; completed when stopped
 var started = Date(), updated = Date()
 var steps: [AiStep] = [] // what it did, the last 40
 var tabs: [String] = [] // its tabs at the last step
 var pending = "" // the question or approval it was waiting on
 var lastAudit = ""
 var sensitive: [AiSensitive] = []
 init() {}
}
final class AiStep: Codable { var what = "", ok = true, at = Date(); init(_ what: String, _ ok: Bool) { self.what = what; self.ok = ok } }
/// outcome: nil while it runs (and forever, if Still closed before it finished), then done, failed or rechecked.
final class AiSensitive: Codable { var what = "", site = "", at = Date(), outcome: String?; init(_ what: String, _ site: String) { self.what = what; self.site = site } }

var aiTasks: [String: AiTask] = [:]
var tasksLoaded = false, quitting = false, resumeAnswered = false // resumeAnswered: the offer after a restart was taken or put off, once per launch
var tasksFolder: String { (aiFolder as NSString).appendingPathComponent("tasks") }
func taskFile(_ chat: String) -> String? { chat.range(of: #"^[A-Za-z0-9_-]{1,64}$"#, options: .regularExpression) != nil ? tasksFolder + "/" + chat + ".json" : nil }

/// At start: what was going on when Still closed is interrupted now, since nothing runs before Still does.
func loadTasks(_ chats: [AiChat]) {
 if tasksLoaded { return }
 tasksLoaded = true
 for name in (try? FileManager.default.contentsOfDirectory(atPath: tasksFolder)) ?? [] where name.hasSuffix(".json") {
  guard let data = FileManager.default.contents(atPath: tasksFolder + "/" + name), let t = try? fromPascalJSON(AiTask.self, data),
        !t.chat.isEmpty, taskFile(t.chat) == tasksFolder + "/" + name else { continue }
  if ["running", "paused", "waiting"].contains(t.state) { t.state = "interrupted"; t.reason = ""; writeTask(t) }
  aiTasks[t.chat] = t
 }
 // From before tasks: a chat still marked as running.
 for c in chats where c.running && aiTasks[c.id] == nil {
  let t = AiTask(); t.chat = c.id; t.state = "interrupted"; t.ask = c.messages.last { $0.role == "user" }?.text ?? ""; aiTasks[c.id] = t
 }
 // Approvals given in a chat end with Still; rules in Settings stay.
 for c in chats { c.allowed = [] }
}
func writeTask(_ t: AiTask) {
 guard let file = taskFile(t.chat) else { return }
 do { try FileManager.default.createDirectory(atPath: tasksFolder, withIntermediateDirectories: true); try pascalJSON(t).write(to: URL(fileURLWithPath: file), options: .atomic) }
 catch { NSLog("Still: couldn't save a task: \(error)") }
}
func saveTask(_ r: ChatRun) { guard aiTasks[r.chat.id] === r.task else { return }; r.task.updated = Date(); if !r.chat.ephemeral { writeTask(r.task) } }
func forgetTask(_ chat: String) { aiTasks[chat] = nil; if let file = taskFile(chat) { try? FileManager.default.removeItem(atPath: file) } }
func taskState(_ r: ChatRun?, _ state: String, _ reason: String = "", _ pending: String = "") {
 guard let r, r.task.state != state || r.task.reason != reason || r.task.pending != pending else { return }
 r.task.state = state; r.task.reason = reason; r.task.pending = pending; saveTask(r); publishAiEverywhere()
}

/// A new run's task. One that picks up an interrupted task keeps what that one did, and checks before any sensitive step.
func startTask(_ r: ChatRun, _ ask: String) {
 let before = aiTasks[r.chat.id], t = AiTask()
 t.chat = r.chat.id; t.ask = String(ask.prefix(2000))
 if let before, before.state == "interrupted" || before.state == "waiting" && before.reason == "signin" {
  if !before.ask.isEmpty { t.ask = before.ask }
  t.steps = before.steps; t.sensitive = before.sensitive; t.tabs = before.tabs; t.lastAudit = before.lastAudit
  r.recheck = before.sensitive.contains { $0.outcome == nil }
 }
 r.task = t; aiTasks[r.chat.id] = t; saveTask(r)
}

func toolFailed(_ result: String) -> Bool { ((try? JSONSerialization.jsonObject(with: Data(result.utf8))) as? [String: Any])?["ok"] as? Bool == false }

/// After each tool: what it did, its tabs and the last audit entry, on disk before the next step.
func checkpoint(_ r: ChatRun, _ tool: String, _ result: String) {
 let what = workers[r.chat.id].map(\.action).flatMap { $0.isEmpty ? nil : $0 } ?? tool
 r.task.steps.append(AiStep(String(what.prefix(160)), !toolFailed(result)))
 if r.task.steps.count > 40 { r.task.steps.removeFirst(r.task.steps.count - 40) }
 var seen = Set<String>()
 r.task.tabs = Array(browsers.flatMap(\.tabs).filter { $0.agentKey == r.chat.id && !$0.isPrivate && !$0.url.isEmpty }.map(\.url).filter { seen.insert($0).inserted }.prefix(10))
 r.task.lastAudit = r.chat.audit.last.map { $0.what + " on " + $0.site + ": " + $0.result } ?? ""
 saveTask(r)
}

/// What a companion is told when it picks a task back up: what it was asked, what it did, what may or may not have
/// happened, and to look again before acting.
func resumeBrief(_ t: AiTask) -> String {
 var lines = ["[Still] Still closed before you finished this task, and the user asked you to pick it up again."]
 if !t.ask.isEmpty { lines.append("What you were asked: " + t.ask) }
 if !t.steps.isEmpty { lines.append("What you did before it stopped (oldest first):\n" + t.steps.suffix(15).map { "- " + clipped($0.what.replacingOccurrences(of: "[", with: "(").replacingOccurrences(of: "]", with: ")").components(separatedBy: .newlines).joined(separator: " "), 120) + ($0.ok ? "" : " (didn't work)") }.joined(separator: "\n")) }
 if !t.tabs.isEmpty { lines.append("Tabs you had open: " + t.tabs.joined(separator: ", ")) }
 if !t.pending.isEmpty { lines.append("You were waiting for the user on: " + t.pending + ". Ask again if you still need it.") }
 let unsure = t.sensitive.filter { $0.outcome == nil }
 if !unsure.isEmpty {
  lines.append("These steps were under way when Still closed, so they may or may not have gone through: " + unsure.map { $0.what + " on " + $0.site }.joined(separator: "; ")
   + ". Check the site first (an order, a sent message, a confirmation) and tell the user what you found. Don't do one again unless they approve it again: Still will ask them.")
 }
 lines.append("Pages may have changed while Still was closed: read each page again before you act on it. Start your reply with what was already done and what you checked again.")
 return lines.joined(separator: "\n\n")
}

var interruptedChats: [AiChat] { aiChats.filter { !$0.archived && !$0.ephemeral && runs[$0.id] == nil && aiTasks[$0.id]?.state == "interrupted" } }
func taskView(_ c: AiChat?) -> Any {
 guard let c, let t = aiTasks[c.id] else { return NSNull() }
 let state = runs[c.id] != nil || ["interrupted", "completed", "failed"].contains(t.state) || t.reason == "signin" ? t.state : "interrupted"
 return ["state": state, "reason": t.reason, "pending": t.pending, "steps": t.steps.count, "unsure": t.sensitive.filter { $0.outcome == nil }.count] as [String: Any]
}

extension Browser {
 /// Picks an interrupted task back up, or says it needs a sign-in first.
 func resumeTask(_ c: AiChat) {
  guard let t = aiTasks[c.id], t.state == "interrupted" || t.state == "waiting", runs[c.id] == nil else { return }
  guard let cli = aiClis.first(where: { $0.id == c.harness }), findCli(cli.command) != nil, aiStatus[cli.id] != "signedOut", aiStatus[cli.id] != "missing" else {
   t.state = "waiting"; t.reason = "signin"; if !c.ephemeral { writeTask(t) }; publishAiEverywhere(); return
  }
  c.running = false
  let done = t.steps.count, unsure = t.sensitive.filter { $0.outcome == nil }.count
  c.messages.append(AiMessage("note", "Picked up where it stopped" + (done > 0 ? " after \(done) step\(done == 1 ? "" : "s")" : "")
   + (unsure > 0 ? ". \(unsure) step\(unsure == 1 ? "" : "s") may not have finished: it checks first and asks you again." : ".")
   + (c.started && c.session != nil ? "" : " The earlier session wasn't saved, so \(cli.app) starts a new one from where the task got to.")))
  runAi(c, resumeBrief(t), shown: "")
 }
}
