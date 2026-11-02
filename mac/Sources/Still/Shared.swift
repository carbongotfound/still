// What the AI side (Ai.swift), the agent tools (Agents.swift), the shell (main.swift) and the QA channel (Qa.swift) share
// (ported from MainWindow.Ai.cs). Everything here is used on the main thread only.
import AppKit

/// A file the user attached to a message: kept in ai/attachments/<id>, read with read_attachment.
struct AiFile: Codable { var id = "", name = "", size = 0 }
final class AiMessage: Codable {
 var role = "", text = ""
 var files: [AiFile]?
 // A companion's own line in a chat that isn't its own (old team chats), or the companion who asked (a "user" message).
 // An ask/tell card: who messaged whom, how it's going (working, replied, failed, stopped), the reply and the chat it's in.
 var who: String?, to: String?, status: String?, reply: String?, chat: String?
 init(_ role: String, _ text: String, who: String? = nil) { self.role = role; self.text = text; self.who = who }
}
final class AiAudit: Codable {
 var at = Date(), what = "", site = "", result = ""
 init(_ what: String, _ site: String, _ result: String) { self.what = what; self.site = site; self.result = result }
}
final class AiChat: Codable {
 var id = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
 var title = "", harness = ""
 var session: String? // the CLI's conversation, resumed by the next message
 var started = false
 var companion = "" // who the user is working with in this chat
 var from: String? // a teammate's chat that asked this companion something: this chat answers it
 var team: [String]?, sessions: [String: String]? // only read to split up a team chat from before companions messaged each other (untangle)
 var unread = false, archived = false
 var noMemory = false // "Don't remember this chat": nothing from it goes into the companion's memory
 var ephemeral = false // an incognito window's chat: never saved, and gone with its window (so not in CodingKeys)
 var worked = 0 // how long its last run took, in seconds
 var running = false // saved while a run goes on: still set at startup means Still closed mid-run
 var error = "" // why its last run failed, until the next one (not saved)
 var updated = Date()
 var messages: [AiMessage] = []
 var allowed: [String] = [] // "action site" the user allowed for the rest of this chat
 var audit: [AiAudit] = [] // what the AI asked to do on sites, and what happened
 enum CodingKeys: String, CodingKey { case team, sessions, from, id, title, harness, session, started, companion, unread, archived, noMemory, worked, running, updated, messages, allowed, audit }
 init() {}
}

/// One answer, set once: the first one wins (Windows: TaskCompletionSource<string>).
final class Answer {
 private(set) var value: String?
 private var waiters: [(String?) -> Void] = []
 func set(_ value: String) {
  guard self.value == nil else { return }
  self.value = value
  let all = waiters; waiters = []
  all.forEach { $0(value) }
 }
 /// Calls then with the answer, or with nil after seconds.
 func wait(_ seconds: Double, _ then: @escaping (String?) -> Void) {
  if let value { then(value); return }
  let once = Once<String?>(); once.action = then
  waiters.append { once.fire($0) }
  DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { once.fire(nil) }
 }
}

/// A question the AI asked with ask_user, waiting for the user's answer in the chat. page: a tab that needs the user's hands.
struct AiQuestion { let text: String, options: [String], page: String?, answer: Answer }
/// A step waiting for the user's OK in the chat; with until, a sensitive step counting down to go ahead on its own.
final class Approval {
 let id: String, what: String, site: String, action: String, why: String, until: Date?
 let answer = Answer()
 init(id: String, what: String, site: String, action: String, why: String, until: Date?) {
  self.id = id; self.what = what; self.site = site; self.action = action; self.why = why; self.until = until
 }
}
/// A chat at work. Any number run at once, each its own AI app process with its own question and follow-ups.
final class ChatRun {
 let chat: AiChat
 let who: String // the AI app's name, as its MCP client
 let started = Date()
 var run: AgentRun?
 var stopped = false
 var question: AiQuestion?
 var queue: [String] = [] // typed while it worked: sent together when it finishes
 var approvals: [Approval] = []
 var typed = Set<String>() // what it typed into pages: form data, which memory never keeps
 init(_ chat: AiChat, _ who: String) { self.chat = chat; self.who = who }
}

var runs: [String: ChatRun] = [:] // by chat id
var kickoffs = Set<String>() // chats a new companion started itself: its first question's answer goes to its memory
// A new companion's first turn, sent for it (aiKickoff): it opens the chat with a task for its role and one question.
let kickoffAsk = "[Still] You were just hired and this is your first chat, so start it yourself now. The user never sees this note. Never open with a generic \"how can I help\", a tool call or a question: your first words are your own message. Greet the user by name if you know it, then say in one or two sentences what you'll do for them first for your role, built on what you know about them: what you remember, what they told Still in setup, the open tabs below and the apps connected for you. Then start that work right away with your real tools. Only after that, and only if you genuinely need something to go further, call ask_user once with one focused question and 2 or 3 short options. When they answer, remember what it tells you about how they want you to work, then carry on. If they skip, go on with your best guess and say what you assumed."
var aiChats: [AiChat] = [] // newest first; Ai.swift loads and saves them
var browsers: [Browser] = [] // every open window, kept by main.swift
/// The Mac's appearance as QA sets it ("Light" or "Dark"); nil = the real one. Only the QA channel sets it.
var qaSystemTheme: String?

func publishAiEverywhere() { for browser in browsers { browser.publishAi() } }
func publishEverywhere() { for browser in browsers { browser.schedulePublish() } }

/// Notes what the AI asked to do on a site and what happened, for the chat's activity list.
func audit(_ chat: AiChat, _ what: String, _ site: String, _ result: String) {
 chat.audit.append(AiAudit(what, site, result))
 if chat.audit.count > 300 { chat.audit.removeFirst(chat.audit.count - 300) }
}
