// What the AI side (Ai.swift), the agent tools (Agents.swift), the shell (main.swift) and the QA channel (Qa.swift) share
// (ported from MainWindow.Ai.cs). Everything here is used on the main thread only.
import AppKit

// chats.json can come from an older or newer Still (or from Windows): a field it doesn't have keeps its default,
// and one that doesn't read does too, so a chat is never lost over one field. (Swift's own decoding fails the whole file.)
extension KeyedDecodingContainer {
 func value<T: Decodable>(_ key: Key, _ fallback: T) -> T { ((try? decodeIfPresent(T.self, forKey: key)) ?? nil) ?? fallback }
}

/// A file the user attached to a message: kept in ai/attachments/<id>, read with read_attachment.
struct AiFile: Codable { var id = "", name = "", size = 0 }
/// A message typed while the chat worked: what the user typed (Up next shows it, with its files), what the chat shows
/// (with its tab links) and what the AI is told (with Still's notes on the tabs and files).
struct Queued { let typed: String, shown: String, asked: String, files: [AiFile] }
extension AiFile {
 init(from decoder: Decoder) throws {
  let c = try decoder.container(keyedBy: CodingKeys.self)
  id = c.value(.id, id); name = c.value(.name, name); size = c.value(.size, size)
 }
}
final class AiMessage: Codable {
 var role = "", text = ""
 var files: [AiFile]?
 var answer: Bool? // the user's answer to the AI's question, not a prompt of their own
 // A companion's own line in a chat that isn't its own (old team chats), or the companion who asked (a "user" message).
 // An ask/tell card: who messaged whom, how it's going (working, replied, failed, stopped), the reply and the chat it's in.
 // A step's status: working or failed, and none once it worked.
 var who: String?, to: String?, status: String?, reply: String?, chat: String?
 var title: String? // an ask/tell card: what was asked for, in a few words
 var took: Int? // a run's last step: how long the run took, in seconds ("Worked for…")
 var model: String?, effort: String? // a run's last reply: the model it ran on, by name, and its effort ("" for the model's own)
 init(_ role: String, _ text: String, who: String? = nil) { self.role = role; self.text = text; self.who = who }
 required init(from decoder: Decoder) throws {
  let c = try decoder.container(keyedBy: CodingKeys.self)
  role = c.value(.role, role); text = c.value(.text, text); files = c.value(.files, files); answer = c.value(.answer, answer)
  who = c.value(.who, who); to = c.value(.to, to); status = c.value(.status, status); reply = c.value(.reply, reply); chat = c.value(.chat, chat); title = c.value(.title, title); took = c.value(.took, took); model = c.value(.model, model); effort = c.value(.effort, effort)
 }
}
final class AiAudit: Codable {
 var at = Date(), what = "", site = "", result = ""
 init(_ what: String, _ site: String, _ result: String) { self.what = what; self.site = site; self.result = result }
 required init(from decoder: Decoder) throws {
  let c = try decoder.container(keyedBy: CodingKeys.self)
  at = c.value(.at, at); what = c.value(.what, what); site = c.value(.site, site); result = c.value(.result, result)
 }
}
final class AiChat: Codable {
 var id = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
 var title = "", harness = ""
 var session: String? // the CLI's conversation, resumed by the next message
 var started = false
 var companion = "" // who the user is working with in this chat
 var from: String? // a teammate's chat that asked this companion something: this chat answers it
 var profile: String? // "companion": its pages open in the companion profile (Where companions browse); nil: the user's own
 var team: [String]?, sessions: [String: String]? // only read to split up a team chat from before companions messaged each other (untangle)
 var unread = false, archived = false
 var noMemory = false // "Don't remember this chat": nothing from it goes into the companion's memory
 var routine = false // started by a routine, not by the user: never counts as the companion's first chat
 var seenChange = 0 // the last memory change its session has heard about (not saved)
 var ephemeral = false // an incognito window's chat: never saved, and gone with its window (so not in CodingKeys)
 var worked = 0 // how long its last run took, in seconds
 var running = false // saved while a run goes on: still set at startup means Still closed mid-run
 var error = "" // why its last run failed, until the next one (not saved)
 var updated = Date()
 var messages: [AiMessage] = []
 var allowed: [String] = [] // "action site" the user allowed for the rest of this chat ("files <folder>": replacing and deleting there)
 var made = Set<String>() // files it made in its working folder since Still started: it may replace or delete them (not saved)
 var folder: String? // its own working folder over its companion's ("": none in this chat); nil: the companion's
 var folderTold: String? // the folder its AI was last told about
 var known: [String] = [] // the sites this chat has been to
 var read = 0 // what it has read: 0 nothing, 1 the public web, 2 pages, apps or files of the user's
 var web = 0 // what of that others wrote (pages, search results, apps), the same way: Ask more's new-site check
 var audit: [AiAudit] = [] // what the AI asked to do on sites, and what happened
 enum CodingKeys: String, CodingKey { case team, sessions, from, profile, id, title, harness, session, started, companion, unread, archived, noMemory, routine, worked, running, updated, messages, allowed, known, read, web, audit, folder, folderTold }
 init() {}
 required init(from decoder: Decoder) throws {
  let c = try decoder.container(keyedBy: CodingKeys.self)
  team = c.value(.team, team); sessions = c.value(.sessions, sessions); from = c.value(.from, from); profile = c.value(.profile, profile); id = c.value(.id, id)
  title = c.value(.title, title); harness = c.value(.harness, harness); session = c.value(.session, session); started = c.value(.started, started)
  companion = c.value(.companion, companion); unread = c.value(.unread, unread); archived = c.value(.archived, archived); noMemory = c.value(.noMemory, noMemory); routine = c.value(.routine, routine)
  worked = c.value(.worked, worked); running = c.value(.running, running); updated = c.value(.updated, updated)
  messages = c.value(.messages, messages); allowed = c.value(.allowed, allowed); known = c.value(.known, known); read = c.value(.read, read); web = c.value(.web, web); audit = c.value(.audit, audit)
  folder = c.value(.folder, folder); folderTold = c.value(.folderTold, folderTold)
 }
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
 var seen: Set<String> = [] // folders the user let it see until this reply ends
 var run: AgentRun?
 var stopped = false
 var question: AiQuestion?
 var queue: [Queued] = [] // typed while it worked: sent together when it finishes
 var approvals: [Approval] = []
 var typed = Set<String>() // what it typed into pages: form data, which memory never keeps
 var task = AiTask() // its state and checkpoint (Tasks.swift)
 var recheck = false // picked up after a sensitive step that may not have finished: the next one asks again
 init(_ chat: AiChat, _ who: String) { self.chat = chat; self.who = who }
}

var runs: [String: ChatRun] = [:] // by chat id
var kickoffs = Set<String>() // chats a new companion started itself, until its first question is answered
var aiChats: [AiChat] = [] // newest first; Ai.swift loads and saves them
var browsers: [Browser] = [] // every open window, kept by main.swift
/// The Mac's appearance as QA sets it ("Light" or "Dark"); nil = the real one. Only the QA channel sets it.
var qaSystemTheme: String?

func publishAiEverywhere() { for browser in browsers { browser.publishAi() } }
var aiPublishQueued = false
/// A reply streams in a few characters at a time: the chat redraws at most ten times a second instead of for every piece
func publishAiSoon() {
 if aiPublishQueued { return }
 aiPublishQueued = true
 DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { aiPublishQueued = false; publishAiEverywhere() }
}
func publishEverywhere() { for browser in browsers { browser.schedulePublish() } }

/// Notes what the AI asked to do on a site and what happened, for the chat's activity list.
func audit(_ chat: AiChat, _ what: String, _ site: String, _ result: String) {
 chat.audit.append(AiAudit(what, site, result))
 if chat.audit.count > 300 { chat.audit.removeFirst(chat.audit.count - 300) }
}
