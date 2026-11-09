// Lets AI agents control Still, like the Windows app (MainWindow.Agents.cs, McpServer.cs): `Still --mcp` is a Model Context
// Protocol server (JSON-RPC over stdio) and `Still --cli <tool> as=<name> key=value ...` makes one call from a terminal. Both
// relay each call to the running Still over a Unix socket only this user can open. Off by default. Every agent must be
// approved by the user, a bar shows what it is doing and can stop it, and agents never see private tabs, saved passwords or
// cookies. Every call answers within a time limit, so an agent can never hang on a slow page, a dialog or a question the user
// hasn't answered yet.
import AppKit
import Darwin
import WebKit

struct AgentError: LocalizedError {
 let message: String
 init(_ message: String) { self.message = message }
 var errorDescription: String? { message }
}
/// A page script's error. missed: the element moved, vanished or is covered.
struct PageMiss: LocalizedError {
 let missed: Bool, message: String
 var errorDescription: String? { message }
}

/// Runs at most once: the first answer wins (the tool's result, a dialog, Stop or the time limit).
final class Once<T> {
 var action: ((T) -> Void)?
 func fire(_ value: T) { guard let action else { return }; self.action = nil; action(value) }
}
final class Box<T> { var value: T? }

/// An alert, confirm or prompt the page is paused on, answered from the shell's dialog or by an agent.
struct PageDialog { let kind: String, message: String, defaultText: String, site: String; let answer: (Bool, String?) -> Void }
/// A file picker an agent's click opened, waiting for upload_file.
/// What an AI may name as a file: a full path on this computer, with nothing in it the bar couldn't show.
func localFilePath(_ path: String) -> Bool {
 (path.hasPrefix("/") || path.hasPrefix("~/")) && !path.unicodeScalars.contains { [.control, .format].contains($0.properties.generalCategory) }
}
struct AgentUpload { let multiple: Bool; let host: String; let complete: ([URL]?) -> Void }

var approvedAgents = Set<String>(), blockedAgents = Set<String>() // lowercased names
/// One AI at work, by run key: a chat's id for Still's own chat (so two chats on the same AI app stay apart),
/// otherwise the outside agent's name.
final class Worker {
 var name = "", label = "", color = "", action = "" // name: the app; label and color: who the user sees (a companion)
 var seen = Date.distantPast
 var paused = false // the user took over: its calls wait until they hand it back
 var signIn = "" // paused on a sign-in page of this site: the user signs in, then hands it back
 var signedIn: (site: String, at: Date)? // when the user last handed back after signing in
 // For the pill: the tool running now and what it works on (a site, a search, a teammate; never what's typed),
 // the steps done since this stretch of work began, and the last few of them in the past tense.
 var tool = "", target = "", count = 0, since: Date? = nil, recent: [String] = []
}
var workers: [String: Worker] = [:]
func worker(_ who: String) -> Worker {
 if let known = workers[who] { return known }
 let run = runs[who], companion = run.flatMap { r in companions.first { $0.id == r.chat.companion } }
 let made = Worker()
 made.name = run?.who ?? who; made.label = companion?.name ?? run?.who ?? who; made.color = hue(companion)
 workers[who] = made
 return made
}
/// The companion's color: its look's, or for one saved before looks, the old hue as in the shell's Buddy.tsx.
func hue(_ companion: Companion?) -> String {
 if let look = companion?.look, let found = look.range(of: ##""color":"#[0-9a-fA-F]{6}""##, options: .regularExpression) { return String(look[found].dropFirst(9).dropLast()) }
 switch companion?.color {
 case "sage": return "#5c7a76"
 case "lavender": return "#8f80aa"
 case "apricot": return "#e8a76c"
 case "mint": return "#8fcbbc"
 case "blush": return "#f2a487"
 case "periwinkle": return "#bbadea"
 case "berry": return "#ed5a31"
 default: return "#4f7cf0"
 }
}
/// Who's at work now: seen in the last 2 minutes, or waiting while the user took over.
func atWork() -> [String: Worker] { workers.filter { approvedAgents.contains($0.value.name.lowercased()) && ($0.value.paused || !$0.value.tool.isEmpty || Date().timeIntervalSince($0.value.seen) < 120) } }
func did(_ who: String, _ action: String) {
 let me = worker(who)
 me.action = action.count > 90 ? String(action.prefix(90)) + "…" : action
 me.recent.append(me.action); if me.recent.count > 5 { me.recent.removeFirst() }
}
/// What a step works on, for the pill: the search, the teammate (with what it's about) or the site; never typed text.
func targetOf(_ who: String, _ tool: String, _ args: [String: Any]) -> String {
 if tool == "web_search" { return clipped(argText(args, "query").trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "\n", with: " "), 60) }
 if tool == "ask_companion" || tool == "tell_companion" {
  let name = argText(args, "name").trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "@"))
  var title = argText(args, "title").trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: ".")).replacingOccurrences(of: "\n", with: " ")
  if title.count > 1, title.dropFirst().first?.isLowercase == true { title = title.prefix(1).lowercased() + title.dropFirst() } // "Pricing research" reads as "about pricing research"; "SEO audit" stays
  return name.isEmpty ? "" : title.isEmpty ? name : name + " about " + clipped(title, 50)
 }
 if ["run_plugin_action", "get_plugin_tools", "find_plugins", "list_connected_plugins"].contains(tool) { return "" }
 var url = argText(args, "url")
 if url.isEmpty, let id = agentTabs[who] { url = findTab(id)?.tab.url ?? "" }
 guard let scheme = URL(string: url)?.scheme, scheme == "http" || scheme == "https" else { return "" }
 return hostName(url)
}

// One question in the agent bar at a time: letting a new agent in, or an action that needs the user's OK (uploads).
var approvalWaiters: [Once<Bool?>]? = nil
var askClient = "", askText = ""
var lastAnswer: (client: String, ask: String, allow: Bool, at: Date)? = nil
// Ends an agent's running call early with this reply, by run key: a dialog or file picker opened in its tab, or the user
// took over or pressed Stop.
var agentInterrupts: [String: [Answer]] = [:]
func endCalls(_ who: String, _ reply: String) { agentInterrupts.removeValue(forKey: who)?.forEach { $0.set(reply) } }
/// One tool call on its way through.
final class AgentStep {
 var intent: AiSensitive? // the sensitive step about to run
 var tabId = "", site = "", why = "", print = "" // what the gate saw: an approval is for exactly this
 var onTab = false // it's about a page in a tab, not a new one
 var again = false // the page changed since the user was asked: the next card says so
 var changed = false // ... and the tool found that out with nothing sent
 var abandoned = false // Stop, Take over or the time limit already answered the AI: nothing more of this call may reach the page
 var allowed = false // the user said yes to this one on a card
 var signedOut = false // read_url read it signed out
 var goes = "" // the site open_tab, navigate or read_url is going to
 func live() throws { if abandoned { throw AgentError("Stopped.") } }
}
// These act on a page, so they take its turn: one at a time, whoever is asking. Reads run alongside, and handle_dialog
// never waits: the step holding the turn may be stuck behind that very dialog.
let keptChanging = "The page kept changing, so Still did nothing and stopped asking. Call read_page to see it now."
struct PageChanged: LocalizedError { var errorDescription: String? { keptChanging } } // not what the user approved any more, and nothing was sent: the step asks again
let takesTurn: Set<String> = ["click", "type", "press_key", "scroll", "navigate", "go_back", "go_forward", "reload", "close_tab", "upload_file"]
/// One AI action at a time on a page, first come, first served (Windows: a SemaphoreSlim).
final class PageTurn {
 private var held = false, queue: [() -> Void] = []
 func take(_ then: @escaping () -> Void) { if held { queue.append(then) } else { held = true; then() } }
 func release() { if queue.isEmpty { held = false } else { queue.removeFirst()() } }
}
var agentTabs: [String: String] = [:] // run key -> the tab it is working in
var stoppedAgents: [String: Date] = [:] // run key -> until when its calls are refused
var agentServerStarted = false
// The user is away from Still: the agent asks them in its own chat and passes the answer on with this code.
var confirmCodes: [String: (client: String, ask: String, until: Date)] = [:]
let stopText = "The user pressed Stop. Stop what you are doing and wait for the user's next message."
let helloFirst = "Write your hello first: greet the user and say in a sentence or two what you'll do for them, then use your tools."
let tookOver = "The user took over this tab for a moment, so your last action may not have finished. Call your next tool again: Still holds it until they hand the tab back, then check the page with read_page."
func signingIn(_ site: String) -> String { "This is a sign-in page for " + site + ". AIs never type or see passwords, so Still paused you and asked the user to sign in themselves. Call your next tool again: Still holds it until they hand the tab back, then check the page with read_page." }
/// A sign-in page: AIs never type or see passwords, so this one waits, like after Take over, while the user signs in
/// (a saved login fills from the key in the field). The tab comes to the front and its pill asks them to sign in.
func askToSignIn(_ who: String, _ browser: Browser, _ tab: Tab, _ site: String) {
 let me = worker(who)
 if me.paused { return }
 me.paused = true; me.signIn = site
 taskState(runs[who], "paused", "site")
 if !tab.closed { browser.select(tab); browser.window.makeKeyAndOrderFront(nil) }
 publishEverywhere(); browser.toast(me.label + " needs you to sign in to " + site + ". It never sees your password.")
}

/// The window agent calls and links from other apps land in: the one used last, never a sign-in window.
var homeBrowser: Browser? {
 if let last = lastActiveBrowser, !last.temporary, !last.incognito, browsers.contains(where: { $0 === last }) { return last }
 return browsers.first { !$0.temporary && !$0.incognito } ?? browsers.first { !$0.temporary } ?? browsers.first
}
func findTab(_ id: String) -> (browser: Browser, tab: Tab)? {
 for browser in browsers { if let tab = browser.tabs.first(where: { $0.id == id }) { return (browser, tab) } }
 return nil
}
/// The window for a chat run's pages: one showing the chat, else one with the chat's tab, else the last used.
func chatRunner(_ who: String) -> Browser? {
 guard let run = runs[who] else { return nil }
 if run.chat.ephemeral { return ownerOf(run.chat) } // an incognito chat's pages stay in its window
 return browsers.first { $0.showing(run.chat) } ?? browsers.first { $0.tabs.contains { $0.chatId == run.chat.id } } ?? homeBrowser
}
/// No keyboard or mouse for a minute, or Still is hidden or every window minimized: nobody will see the bar.
func userAway() -> Bool {
 let idle = [CGEventType.mouseMoved, .keyDown, .leftMouseDown, .scrollWheel].map { CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: $0) }.min() ?? 0
 return idle > 60 || NSApp.isHidden || browsers.allSatisfy { $0.window.isMiniaturized || !$0.window.isVisible }
}

// ---- The permission layer ----
// Every call is read, navigate, interact or sensitive: buying, sending, deleting, a form that posts, a password or
// payment field, or anything on a site the user marked sensitive. Settings say, per site, action and companion,
// whether it runs, asks once in each chat, or asks every time. A sensitive step allowed without asking still counts
// down 8 seconds in the chat first. Outside AI apps keep today's behavior: allowed unless a rule for everyone or a
// sensitive site says to ask, and then they ask in the bar at the top. Rules: prefs["Permissions"], [{Site, Action, Companion, Mode}].
let permissionActions = ["read", "navigate", "interact", "sensitive"]
func defaultPermission(_ action: String) -> String { action == "interact" ? "chat" : action == "sensitive" ? "ask" : "always" }
func onSite(_ rule: String, _ site: String) -> Bool { !rule.isEmpty && (site == rule || site.hasSuffix("." + rule)) }
/// An address on this computer or its network, or nil if it's not an address at all.
func privateAddress(_ host: String) -> Bool? {
 var v4 = in_addr(), v6 = in6_addr()
 func ipv4(_ b: [UInt8]) -> Bool { [0, 10, 127].contains(b[0]) || b[0] == 169 && b[1] == 254 || b[0] == 172 && (16...31).contains(b[1]) || b[0] == 192 && b[1] == 168 || b[0] == 100 && (64...127).contains(b[1]) }
 if inet_pton(AF_INET6, host, &v6) == 1 {
  let b = withUnsafeBytes(of: &v6) { Array($0) }
  if b[..<10].allSatisfy({ $0 == 0 }) && b[10] == 0xff && b[11] == 0xff { return ipv4(Array(b[12...])) }
  return b[..<15].allSatisfy { $0 == 0 } && b[15] <= 1 || b[0] & 0xfe == 0xfc || b[0] == 0xfe && b[1] & 0x80 == 0x80
 }
 if inet_aton(host, &v4) != 0 { return ipv4(withUnsafeBytes(of: &v4) { Array($0) }) }
 return nil
}
/// On this computer or its network, going by the name or address alone.
func isPrivateName(_ host: String) -> Bool {
 var host = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]")).lowercased()
 while host.hasSuffix(".") { host.removeLast() }
 if let address = privateAddress(host) { return address }
 return !host.contains(".") || [".localhost", ".local", ".internal", ".intranet", ".lan", ".home", ".corp", ".home.arpa"].contains { host.hasSuffix($0) }
}
// Tests run on local pages: there, only the names a test lists count as private.
func privateName(_ host: String) -> Bool { isQa ? (ProcessInfo.processInfo.environment["STILL_QA_PRIVATE"] ?? "").split(separator: ",").contains(Substring(host)) : isPrivateName(host) }
func privateHost(_ host: String) async -> Bool {
 if privateName(host) { return true }
 if isQa { return false }
 return await withCheckedContinuation { done in
  let once = Once<Bool>()
  once.action = { done.resume(returning: $0) }
  DispatchQueue.global().async {
   var found = false, list: UnsafeMutablePointer<addrinfo>?
   if getaddrinfo(host, nil, nil, &list) == 0 {
    var at = list
    while let info = at {
     var name = [CChar](repeating: 0, count: Int(NI_MAXHOST))
     if getnameinfo(info.pointee.ai_addr, info.pointee.ai_addrlen, &name, socklen_t(name.count), nil, 0, NI_NUMERICHOST) == 0, privateAddress(String(cString: name).components(separatedBy: "%")[0]) == true { found = true }
     at = info.pointee.ai_next
    }
    freeaddrinfo(list)
   }
   let result = found
   DispatchQueue.main.async { once.fire(result) }
  }
  DispatchQueue.main.asyncAfter(deadline: .now() + 1) { once.fire(false) }
 }
}
func siteOf(_ input: String) -> String {
 let text = input.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
 return text.isEmpty ? "" : hostName(text.contains("://") ? text : "https://" + text)
}
func ruleText(_ rule: [String: Any], _ key: String) -> String { rule[key] as? String ?? "" }
var sessionGrants = Set<String>() // outside apps: "who action site" allowed until Still closes

var wentAhead: String? // the last countdown that ran out: a Cancel for it came too late, and the user hears that
/// A card in the chat's tray; for a sensitive step allowed without asking, 8 seconds to cancel it instead.
@MainActor func approve(_ run: ChatRun, _ what: String, _ site: String, _ action: String, _ why: String, countdown: Bool) async -> String {
 let card = Approval(id: String((0..<8).map { _ in "0123456789abcdef".randomElement()! }), what: what, site: site, action: action, why: why, until: countdown ? Date().addingTimeInterval(8) : nil)
 run.approvals.append(card); publishAiEverywhere()
 if !countdown { taskState(run, "waiting", "approval", what + " on " + site) }
 // The card's Cancel goes at 8 s. Half a second more, so a click already on its way still stops the step.
 await withCheckedContinuation { (done: CheckedContinuation<Void, Never>) in card.answer.wait(countdown ? 8.5 : 600) { _ in done.resume() } }
 let answer = card.answer.value ?? (countdown ? "go" : "timeout")
 if answer == "go" { wentAhead = card.id }
 run.approvals.removeAll { $0 === card }; publishAiEverywhere()
 if !countdown && !run.approvals.contains(where: { $0.until == nil }) { taskState(run, "running") }
 return answer
}

/// What came first: the work's own result, an interrupt's reply (a dialog, a file picker, Take over or Stop), or the time limit.
enum Raced { case done(String?), interrupted(String), late }
@MainActor func race(_ interrupt: Answer, _ seconds: Double, _ work: @escaping @MainActor () async -> String?) async -> Raced {
 await withCheckedContinuation { (finish: CheckedContinuation<Raced, Never>) in
  let once = Once<Raced>()
  once.action = { finish.resume(returning: $0) }
  Task { @MainActor in let result = await work(); once.fire(.done(result)) }
  interrupt.wait(seconds) { reply in once.fire(reply.map { .interrupted($0) } ?? .late) }
 }
}

// The page scripts come straight from the Windows app (mac/build.sh copies them), so both stay in step.
let agentScripts: [String: String] = {
 var scripts: [String: String] = [:]
 for name in ["Page", "Snapshot", "Find", "Click", "Watch", "Mark", "Seen", "Same", "Focus", "Scroll", "Wait", "Sensitive", "FileInput", "Cursor", "Mask"] {
  scripts[name] = (try? String(contentsOf: resources.appendingPathComponent("agent-\(name).js"), encoding: .utf8)) ?? ""
 }
 return scripts
}()

func jsonText(_ object: [String: Any]) -> String {
 guard JSONSerialization.isValidJSONObject(object), let data = try? JSONSerialization.data(withJSONObject: object, options: [.withoutEscapingSlashes]) else { return #"{"ok":false,"error":"Still couldn't encode its answer."}"# }
 return String(decoding: data, as: UTF8.self)
}
func jsonObject(_ text: String) -> [String: Any]? { (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [String: Any] }
func agentOk(_ result: Any) -> String { jsonText(["ok": true, "result": result]) }
func agentFail(_ message: String) -> String { jsonText(["ok": false, "error": message]) }
func argText(_ args: [String: Any], _ key: String) -> String { args[key] as? String ?? "" }
func argFlag(_ args: [String: Any], _ key: String) -> Bool { args[key] as? Bool == true || args[key] as? String == "true" }
func argNumber(_ args: [String: Any], _ key: String, _ fallback: Double) -> Double {
 if let number = args[key] as? NSNumber { return number.doubleValue }
 if let text = args[key] as? String, let value = Double(text.trimmingCharacters(in: .whitespaces)), value.isFinite { return value }
 return fallback
}
/// An element id from read_page or find: 12, "12" or "[12]".
func argId(_ args: [String: Any]) -> String { ((args["id"] as? NSNumber)?.stringValue ?? args["id"] as? String ?? "").trimmingCharacters(in: CharacterSet(charactersIn: "[] ")) }
func clipped(_ text: String, _ limit: Int) -> String { text.count > limit ? String(text.prefix(limit - 1)) + "…" : text }
func hostName(_ url: String) -> String {
 guard var host = URL(string: url)?.host?.lowercased() else { return ["blob:", "data:", "about:"].contains { url.lowercased().hasPrefix($0) } ? "" : url }
 while host.hasSuffix(".") { host.removeLast() }
 return host.hasPrefix("www.") ? String(host.dropFirst(4)) : host
}

func scriptError(_ code: String, _ reply: [String: Any]) -> String {
 switch code {
 case "gone": return "That element isn't on the page anymore (the page changed or it's a new page). Call read_page or find for current ids."
 case "notfound": return "Couldn't find that element on the page. Call read_page or find."
 case "hidden": return "That element is hidden right now (maybe in a closed menu). Open what contains it first, or call read_page."
 case "covered": return "Something is on top of that element: " + (reply["by"] as? String ?? "") + ". Close or click that first (often a cookie banner or pop-up)."
 case "disabled": return "\"" + (reply["label"] as? String ?? "") + "\" is disabled right now, so nothing was clicked. Do what it's waiting for first (often a required field)."
 case "offscreen": return "That element is outside the visible page and scrolling didn't bring it in, so nothing was clicked. Call read_page."
 case "noview": return "This page has no size right now, so nothing was clicked. Call read_page, or ask the user to bring its tab to the front."
 case "noscroll": return "Nothing scrolled: it's already at the end, or there's nothing to scroll here."
 case "nofocus": return "No field is focused. Pass the field's id."
 case "nooption": return "That dropdown has no matching option. Options: " + (reply["options"] as? String ?? "")
 case "empty": return "Pass the text to look for."
 default: return "The page's script failed: " + (reply["message"] as? String ?? "")
 }
}

/// Runs an agent script in the page, wrapped like the Windows app's: the shared helpers, then the tool's own code. It runs
/// in Still's own world, so the page can't see or change it (they share the DOM).
@MainActor func agentJs(_ view: WKWebView, _ body: String, _ o: [String: Any]) async throws -> Any? {
 let source = "((o)=>{try{" + (agentScripts["Page"] ?? "") + body + "}catch(err){return {error:'script',message:String(err&&err.message||err)}}})(" + jsonText(o) + ") ?? null"
 let result: Any
 do { result = try await withCheckedThrowingContinuation { done in view.evaluateJavaScript(source, in: nil, in: stillWorld) { done.resume(with: $0) } } }
 catch { throw AgentError("The page's script failed: " + error.localizedDescription) }
 if let reply = result as? [String: Any], reply["error"] as? String == "changed" { throw PageChanged() }
 if let reply = result as? [String: Any], let code = reply["error"] as? String { throw PageMiss(missed: ["gone", "notfound", "hidden", "covered", "disabled", "offscreen"].contains(code), message: scriptError(code, reply)) }
 return result is NSNull ? nil : result
}
/// Pages re-render under the AI: when the element is missing, wait for the page to settle and try once more.
/// Still missing: the error carries a fresh read of the page, so the AI picks again (and asks again if that step needs asking).
@MainActor func settled(_ tab: Tab, _ view: WKWebView, _ act: () async throws -> Any?) async throws -> Any? {
 do { return try await act() } catch let miss as PageMiss where miss.missed { await waitLoaded(tab, 3); try? await Task.sleep(nanoseconds: 500_000_000) }
 do { return try await act() } catch let miss as PageMiss where miss.missed {
  let now = (try? await agentJs(view, agentScripts["Snapshot"] ?? "", ["text": false, "all": false, "offset": 0])) as? String ?? ""
  throw AgentError(miss.message + "\n\nThe page now:\n" + now)
 }
}
@MainActor func waitLoaded(_ tab: Tab, _ seconds: Double = 15) async {
 let until = Date().addingTimeInterval(seconds)
 try? await Task.sleep(nanoseconds: 250_000_000)
 while tab.view?.isLoading == true && Date() < until { try? await Task.sleep(nanoseconds: 100_000_000) }
}
/// The AI's cursor: an arrow with its name, in its companion's color, glides to where it's about to click.
/// It's drawn inside the page, clicks pass through it, and it fades on its own.
@MainActor func pointer(_ who: String, _ tab: Tab, _ view: WKWebView, _ x: Double, _ y: Double) async {
 let me = worker(who)
 do { _ = try await agentJs(view, agentScripts["Cursor"] ?? "", ["x": x, "y": y, "name": me.label, "color": me.color]) } catch { return }
 if browsers.contains(where: { $0.shown === tab }) { try? await Task.sleep(nanoseconds: 450_000_000) } // let the user see where it's going first
}
/// What an action led to: where the agent is now, and the new tab it's in if the action opened one.
func outcome(_ who: String, _ tab: Tab, _ before: String, _ done: String) -> [String: Any] {
 let opened = agentTabs[who].flatMap { $0 != before ? findTab($0)?.tab : nil }
 let now = opened ?? tab
 var reply: [String: Any] = ["done": done, "url": now.url, "title": now.title]
 if let opened { reply["tabId"] = opened.id; reply["note"] = "This opened a new tab; you're working in it now." }
 return reply
}

// ---- Input ----
// Clicks and keys go to the page as real (trusted) events, straight to its view. A page out of view may not take them,
// so a probe in Still's world notes whether the page got them, and if not, the same input is played by script instead
// (WebKit has no DevTools input events). ponytail: a page that stops mousedown/keydown at the window before the probe
// sees it gets the input twice; read real delivery from WebKit if that shows up.
let agentProbeArm = #"""
const P = window.__stillProbe || (window.__stillProbe = { got: false, on: new WeakSet() });
for (const d of [document, ...frames()]) { const w = d.defaultView; if (w && !P.on.has(w)) { P.on.add(w); for (const t of ['mousedown', 'keydown']) w.addEventListener(t, e => { if (e.isTrusted) P.got = true; }, true); } }
P.got = false;
return true;
"""#
let agentProbeRead = "return !window.__stillProbe || window.__stillProbe.got;" // no probe: a new document, so the page took it and moved on
/// Arms the probe, sends the events, and says whether the page got them.
@MainActor func trusted(_ view: WKWebView, _ send: () -> Bool) async -> Bool {
 guard (try? await agentJs(view, agentProbeArm, [:])) != nil, send() else { return false }
 for _ in 0..<5 {
  try? await Task.sleep(nanoseconds: 100_000_000)
  if (try? await agentJs(view, agentProbeRead, [:])) as? Bool == true { return true }
 }
 return false
}
/// Mouse events at a point in the page (CSS pixels from its top left).
@MainActor func sendClick(_ view: WKWebView, _ x: Double, _ y: Double, moveOnly: Bool = false) -> Bool {
 guard let window = view.window else { return false }
 let zoom = Double(view.pageZoom)
 let at = view.convert(NSPoint(x: x * zoom, y: view.isFlipped ? y * zoom : Double(view.bounds.height) - y * zoom), to: nil)
 for type in moveOnly ? [NSEvent.EventType.mouseMoved] : [.leftMouseDown, .leftMouseUp] {
  guard let event = NSEvent.mouseEvent(with: type, location: at, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                                       context: nil, eventNumber: 0, clickCount: type == .mouseMoved ? 0 : 1, pressure: type == .leftMouseDown ? 1 : 0) else { return false }
  switch type {
  case .mouseMoved: view.mouseMoved(with: event)
  case .leftMouseDown: view.mouseDown(with: event)
  default: view.mouseUp(with: event)
  }
 }
 return true
}
/// Clicks like a real mouse; if the page didn't get it, the same click is played by script on the element.
@MainActor func mouseClick(_ view: WKWebView, _ x: Double, _ y: Double, _ o: [String: Any], _ step: AgentStep) async throws {
 try step.live()
 _ = sendClick(view, x, y, moveOnly: true)
 _ = try? await agentJs(view, agentScripts["Mark"] ?? "", [:]) // what hovering changed doesn't count as the click's doing
 try step.live()
 if await trusted(view, { sendClick(view, x, y) }) { return }
 try step.live()
 if (try? await agentJs(view, "return !!window[WATCH]?.got;", [:])) as? Bool == true { return } // it got there, or the guard stopped it: never play it twice
 var again = o; again["again"] = true // the watcher set up before stays
 _ = try await agentJs(view, "const r = (() => {\n" + (agentScripts["Click"] ?? "") + "\n})();\nif (r.error) return r;\n" + agentClickTail, again)
}
/// A step that ran but can't say it worked: how its chat row reads, in place of the tool's usual words. It ends with no tick.
@MainActor func unverified(_ who: String, _ doingWord: String, _ words: String, _ message: String) -> String {
 if let step = runs[who]?.chat.messages.last(where: { $0.role == "tool" && $0.status == "working" && says($0.text, doingWord) }) { step.text = words; step.status = "failed" }
 return jsonText(["ok": false, "error": message, "unverified": true])
}
let checkFirst = "It may still be working: call read_page to check before trying again, and don't repeat a purchase, send or delete without checking. A canvas or video can change without Still seeing it, so take a screenshot there."
/// Did the action work? Its watcher says whether the event reached the element and what changed after. Nil means it went
/// through; otherwise this is the failure to send back. key: the key pressed, "" for a click.
/// ponytail: a page that changes by itself (a clock, a carousel) reads as changed. The event still had to reach the element.
@MainActor func verdict(_ who: String, _ tab: Tab, _ view: WKWebView, _ tabBefore: String, _ urlBefore: String, _ key: String, _ name: String, _ step: AgentStep) async throws -> String? {
 let started = Date(), from = Date().addingTimeInterval(-1)
 func moved() -> Bool { tab.closed || tab.url != urlBefore || (agentTabs[who] ?? "") != tabBefore || tab.downloadAt > from }
 var seen: [String: Any]?, changed: [String] = []
 func flag(_ f: String) -> Bool { seen?[f] as? Bool == true }
 func words(_ f: String) -> String { seen?[f] as? String ?? "" }
 while true {
  let read = (try? await agentJs(view, agentScripts["Seen"] ?? "", ["key": key])) as? [String: Any]
  if step.abandoned { return nil } // its answer is already out, and the watcher may be the next step's by now
  if let now = read {
   if now["gone"] != nil { await waitLoaded(tab, 8); break } // a new document: it navigated
   seen = now; changed = now["changed"] as? [String] ?? []
   if !words("blocked").isEmpty { break }
   if !words("invalid").isEmpty && !flag("submitted") { break }
   if key.isEmpty && !words("missed").isEmpty && !flag("pressed") { break } // it landed on something else
  } else if view.isLoading || moved() { await waitLoaded(tab, 8); return nil }
  if moved() || (!changed.isEmpty && !view.isLoading) { break }
  let limit: Double = view.isLoading ? 8 : flag("submitted") ? 5 : !key.isEmpty ? (key.lowercased().contains("enter") ? 2 : 1.2) : flag("reached") || flag("pressed") ? 2 : 0.8
  if Date().timeIntervalSince(started) > limit { break }
  try? await Task.sleep(nanoseconds: 100_000_000)
 }
 if view.isLoading { await waitLoaded(tab, 8) }
 if step.abandoned { return nil }
 if !tab.closed { _ = try? await agentJs(view, agentScripts["Seen"] ?? "", ["key": key, "last": true]) }
 if words("blocked") == "before" { throw PageChanged() } // nothing reached the page: ask again
 if words("blocked") == "during" { return unverified(who, key.isEmpty ? "Clicking" : "Pressing", "Stopped: the page changed", "The page changed during the \(key.isEmpty ? "click" : "key press"), so Still stopped it partway. " + checkFirst) }
 let wentOn = moved() || changed.contains("url"), action = key.isEmpty ? "clicking “" + name + "”" : "pressing " + key, doingWord = key.isEmpty ? "Clicking" : "Pressing"
 if key.isEmpty && !words("missed").isEmpty && !flag("pressed") { return agentFail("The click didn't reach \"\(name)\": it landed on \(words("missed")). Call read_page to see the page now.") }
 if !words("invalid").isEmpty && !flag("submitted") && !wentOn { return unverified(who, doingWord, "Form not sent after " + action, "The form wasn't sent: \(words("invalid")). Fix that field first.") }
 if wentOn || seen == nil { return nil }
 if !changed.isEmpty && (!key.isEmpty || flag("reached") || flag("pressed")) { return nil }
 if flag("submitted") { return unverified(who, doingWord, "No change after " + action, "The form went out, but the page didn't change in 5 seconds, so Still can't say it worked. " + checkFirst) }
 if !key.isEmpty {
  return flag("keyed") ? unverified(who, doingWord, "No change after " + action, "Pressed \(key), but nothing on the page changed, so Still can't say it did anything. " + checkFirst)
   : agentFail("The page didn't get the \(key) key. Click the field first, or call read_page.")
 }
 return flag("reached") ? unverified(who, doingWord, "No change after " + action, "Clicked \"\(name)\", but nothing on the page changed in 2 seconds, so Still can't say it worked. " + checkFirst)
  : agentFail("The click didn't reach \"\(name)\", so nothing was clicked. Call read_page to see the page now.")
}
// The Mac's key codes and characters for named keys; letters and digits by their place on the ANSI keyboard.
let macKeys: [String: (keyCode: UInt16, text: String)] = [
 "Enter": (36, "\r"), "Tab": (48, "\t"), "Escape": (53, "\u{1b}"), "Backspace": (51, "\u{7f}"), "Delete": (117, "\u{f728}"),
 "ArrowUp": (126, "\u{f700}"), "ArrowDown": (125, "\u{f701}"), "ArrowLeft": (123, "\u{f702}"), "ArrowRight": (124, "\u{f703}"),
 "Home": (115, "\u{f729}"), "End": (119, "\u{f72b}"), "PageUp": (116, "\u{f72c}"), "PageDown": (121, "\u{f72d}"), "Space": (49, " ")
]
let macKeyOrder = Array("asdfhgzxcv§bqweryt123465=97-80]ou[ip\rlj'k;\\,/nm.\t `")
/// Key events for a key from keyInfo.
@MainActor func sendKey(_ view: WKWebView, _ info: [String: Any]) -> Bool {
 guard let window = view.window else { return false }
 let key = info["key"] as? String ?? "", named = macKeys[info["code"] as? String ?? ""]
 var flags: NSEvent.ModifierFlags = []
 if info["alt"] as? Bool == true { flags.insert(.option) }
 if info["ctrl"] as? Bool == true { flags.insert(.control) }
 if info["meta"] as? Bool == true { flags.insert(.command) }
 if info["shift"] as? Bool == true { flags.insert(.shift) }
 let text = named?.text ?? key, code = named?.keyCode ?? UInt16(key.lowercased().first.flatMap { macKeyOrder.firstIndex(of: $0) } ?? 0)
 for type in [NSEvent.EventType.keyDown, .keyUp] {
  guard let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: flags, timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                                     context: nil, characters: text, charactersIgnoringModifiers: text.lowercased(), isARepeat: false, keyCode: code) else { return false }
  if type == .keyDown { view.keyDown(with: event) } else { view.keyUp(with: event) }
 }
 if (flags.contains(.command) || flags.contains(.control)) && key.lowercased() == "a" { NSApp.sendAction(#selector(NSText.selectAll(_:)), to: view, from: nil) } // the menu's job on the Mac
 return true
}
/// Presses a key like a person would, e.g. "Enter", "Escape", "a", "Control+A", "Shift+Tab".
@MainActor func pressKey(_ view: WKWebView, _ combo: String, _ step: AgentStep) async throws {
 var info = try keyInfo(combo)
 if !step.print.isEmpty { info["expect"] = step.print }
 try step.live()
 if await trusted(view, { sendKey(view, info) }) { return }
 try step.live()
 if (try? await agentJs(view, "return !!window[WATCH]?.got;", [:])) as? Bool == true { return } // it got there, or the guard stopped it: never play it twice
 _ = try await agentJs(view, agentKeyScript, info)
}
/// Types text one key at a time; a new line is Enter where the field has lines.
@MainActor func typeKeys(_ view: WKWebView, _ text: String, _ multiline: Bool, _ me: Worker, _ step: AgentStep) async {
 for character in text.replacingOccurrences(of: "\r\n", with: "\n") {
  if me.paused || step.abandoned { return } // the user took over mid-word
  if character == "\n" { if multiline { try? await pressKey(view, "Enter", step) }; continue }
  _ = sendKey(view, ["key": String(character), "code": ""])
  try? await Task.sleep(nanoseconds: 1_000_000)
 }
}

let agentKeys: [String: (code: String, keyCode: Int, text: String)] = [
 "enter": ("Enter", 13, "\r"), "tab": ("Tab", 9, ""), "escape": ("Escape", 27, ""), "esc": ("Escape", 27, ""), "backspace": ("Backspace", 8, ""), "delete": ("Delete", 46, ""),
 "arrowup": ("ArrowUp", 38, ""), "arrowdown": ("ArrowDown", 40, ""), "arrowleft": ("ArrowLeft", 37, ""), "arrowright": ("ArrowRight", 39, ""),
 "home": ("Home", 36, ""), "end": ("End", 35, ""), "pageup": ("PageUp", 33, ""), "pagedown": ("PageDown", 34, ""), "space": ("Space", 32, " ")
]

/// A key like a person presses it, e.g. "Enter", "Escape", "a", "Control+A", "Shift+Tab", for sendKey and agentKeyScript.
func keyInfo(_ combo: String) throws -> [String: Any] {
 let parts = combo.split(separator: "+").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
 guard let key = parts.last else { throw AgentError("Pass a key, like Enter or Control+A.") }
 var alt = false, ctrl = false, meta = false, shift = false
 for modifier in parts.dropLast() {
  switch modifier.lowercased() {
  case "alt", "option": alt = true
  case "ctrl", "control": ctrl = true
  case "meta", "cmd", "command", "win": meta = true
  case "shift": shift = true
  default: throw AgentError("Unknown modifier: " + modifier)
  }
 }
 var name = key, code = "", keyCode = 0, text = key
 if let named = agentKeys[key.lowercased()] { name = named.code == "Space" ? " " : named.code; code = named.code; keyCode = named.keyCode; text = named.text }
 else if key.count == 1, let character = key.first {
  if shift { name = key.uppercased() }
  if (character.isLetter || character.isNumber) && character.isASCII {
   code = (character.isLetter ? "Key" : "Digit") + key.uppercased()
   keyCode = Int(key.uppercased().unicodeScalars.first?.value ?? 0)
  }
 } else { throw AgentError("Unknown key: " + key) }
 if alt || ctrl || meta { text = "" } // shortcuts type nothing
 return ["key": name, "code": code, "keyCode": keyCode, "text": text, "alt": alt, "ctrl": ctrl, "meta": meta, "shift": shift]
}

// The script fallbacks for clicks and keys run after the shared page helpers (agent-Page.js); evaluateJavaScript counts as
// a user gesture, so pop-ups and file pickers open.
let agentClickTail = #"""
const el = target(o), w = view(el), rect = el.getBoundingClientRect(), cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2, rootNode = el.getRootNode();
let at = typeof rootNode.elementFromPoint === 'function' ? rootNode.elementFromPoint(cx, cy) : null;
if (!at || !(inside(el, at) || inside(at, el) || at.closest('label')?.control === el)) at = el;
const base = { bubbles: true, cancelable: true, composed: true, view: w, clientX: cx, clientY: cy, screenX: cx, screenY: cy, button: 0, detail: 1 };
let halted = false;
const held = () => { if (!halted && o.expect && print(el) !== o.expect) { halted = true; if (window[WATCH]) window[WATCH].blocked = 'during'; } return halted; };
const fire = (type, buttons) => { if (held()) return; const init = Object.assign({}, base, { buttons }); at.dispatchEvent(type.startsWith('pointer') && w.PointerEvent ? new w.PointerEvent(type, Object.assign(init, { pointerId: 1, pointerType: 'mouse', isPrimary: true })) : new w.MouseEvent(type, init)); };
fire('pointerover', 0); fire('mouseover', 0); fire('pointermove', 0); fire('mousemove', 0); fire('pointerdown', 1); fire('mousedown', 1);
const f = at.closest('a[href],button,input,select,textarea,summary,[tabindex],[contenteditable]');
if (!held() && f && f !== deepActive() && typeof f.focus === 'function') f.focus({ preventScroll: true });
fire('pointerup', 0); fire('mouseup', 0); fire('click', 0);
return { label: r.label };
"""#

// type: puts the text in the focused field the way typing would (undoable, with input events), or sets it directly if the page blocks that.
let agentInsertScript = #"""
const e = deepActive();
if (!e || e.localName === 'body') return { error: 'nofocus' };
if (!o.text && o.append) return true;
const d = e.ownerDocument, w = view(e), isValue = 'value' in e && e.localName !== 'button', before = isValue ? e.value : e.textContent;
let ok = false;
try { ok = d.execCommand(o.text ? 'insertText' : 'delete', false, o.text); } catch {}
if (!ok || (isValue ? e.value : e.textContent) === before) {
 const v = o.append ? before + o.text : o.text;
 if (isValue) { const s = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), 'value'); if (s && s.set) s.set.call(e, v); else e.value = v; }
 else if (e.isContentEditable) e.textContent = v;
 else return true;
 e.dispatchEvent(new (w.InputEvent || w.Event)('input', { bubbles: true, inputType: o.text ? 'insertText' : 'deleteContentBackward', data: o.text || null }));
 if (isValue) e.dispatchEvent(new w.Event('change', { bubbles: true }));
}
return true;
"""#

// press_key: the key events, then what the browser itself would do for keys a page doesn't handle.
let agentKeyScript = #"""
const e = deepActive() || document.body, w = view(e), d = e.ownerDocument;
if (o.expect && print(e) !== o.expect) return { error: 'changed' };
const init = { key: o.key, code: o.code, keyCode: o.keyCode, which: o.keyCode, altKey: o.alt, ctrlKey: o.ctrl, metaKey: o.meta, shiftKey: o.shift, bubbles: true, cancelable: true, composed: true, view: w };
const ev = (type, extra) => { const k = new w.KeyboardEvent(type, Object.assign({}, init, extra)); if (!k.keyCode && o.keyCode) try { Object.defineProperty(k, 'keyCode', { get: () => o.keyCode }); Object.defineProperty(k, 'which', { get: () => o.keyCode }); } catch {} return k; };
const go = e.dispatchEvent(ev('keydown'));
if (o.expect && print(e) !== o.expect) { if (window[WATCH]) window[WATCH].blocked = 'during'; return true; }
if (go && o.text) e.dispatchEvent(ev('keypress', { charCode: o.text.charCodeAt(0) }));
const field = e.isContentEditable || e.localName === 'textarea' || e.localName === 'input' && !/^(button|submit|reset|checkbox|radio|file|image|range|color)$/.test(e.type);
const sc = document.scrollingElement || document.documentElement, role = e.getAttribute ? e.getAttribute('role') || '' : '';
if (go) {
 if (o.code === 'Enter') {
  if (e.isContentEditable) d.execCommand('insertParagraph');
  else if (e.localName === 'textarea') d.execCommand('insertText', false, '\n');
  else if (e.localName === 'input' && e.form) { const b = [...e.form.elements].find(x => (x.type === 'submit' || x.type === 'image') && !x.disabled); if (b) b.click(); else if (e.form.requestSubmit) e.form.requestSubmit(); else e.form.submit(); }
  else if (/^(a|button|summary)$/.test(e.localName) || /^(button|link|menuitem|tab|option)$/.test(role)) e.click();
 } else if (o.code === 'Space' && !field) {
  if (/^(button|summary)$/.test(e.localName) || /^(checkbox|radio)$/.test(e.type) || /^(button|checkbox|radio|switch|tab|menuitem|option)$/.test(role)) e.click();
  else sc.scrollBy(0, (o.shift ? -0.8 : 0.8) * innerHeight);
 } else if (o.code === 'Backspace' || o.code === 'Delete') { if (field) d.execCommand(o.code === 'Backspace' ? 'delete' : 'forwardDelete'); }
 else if (o.code === 'Tab') {
  const all = [];
  walk(document, x => { if (x.matches('a[href],button,input:not([type=hidden]),select,textarea,[tabindex],[contenteditable=""],[contenteditable=true]') && x.tabIndex >= 0 && !x.disabled && visible(x, view(x).getComputedStyle(x))) all.push(x); });
  const i = all.indexOf(e), n = all.length, next = n ? all[i < 0 ? (o.shift ? n - 1 : 0) : (i + (o.shift ? n - 1 : 1)) % n] : null;
  if (next) { next.focus(); if (/^(input|textarea)$/.test(next.localName) && typeof next.select === 'function') try { next.select(); } catch {} }
 } else if (/^(ArrowUp|ArrowDown|PageUp|PageDown|Home|End)$/.test(o.code) && !field && e.localName !== 'select') {
  if (o.code === 'Home') sc.scrollTo(0, 0);
  else if (o.code === 'End') sc.scrollTo(0, sc.scrollHeight);
  else sc.scrollBy(0, (/Up$/.test(o.code) ? -1 : 1) * (/^Page/.test(o.code) ? innerHeight * 0.8 : 40));
 } else if ((o.ctrl || o.meta) && /^a$/i.test(o.key)) { if (typeof e.select === 'function') e.select(); else d.execCommand('selectAll'); }
 else if (o.text && field) { if (!d.execCommand('insertText', false, o.text) && 'value' in e) { e.value += o.text; e.dispatchEvent(new w.Event('input', { bubbles: true })); } }
}
e.dispatchEvent(ev('keyup'));
return true;
"""#

// upload_file by element: is it a file input (click = open its picker, which Still answers with the agent's files)?
let agentPickTail = #"""
const ok = !!pick && pick.localName === 'input' && pick.type === 'file';
if (ok && o.click) pick.click();
return ok;
"""#

// Agents work in pages out of view, which never have focus; editors like Notion ignore typing without it. This tells the
// page it's in view and focused (Windows: Emulation.setFocusEmulationEnabled). It runs in the page's own world.
let agentFocusScript = #"""
(() => { const k = Symbol.for('still.focus'); if (window[k]) return true; window[k] = true;
 const no = { get: () => false, configurable: true }, shown = { get: () => 'visible', configurable: true };
 try { Document.prototype.hasFocus = () => true; Object.defineProperty(Document.prototype, 'hidden', no); Object.defineProperty(Document.prototype, 'webkitHidden', no);
  Object.defineProperty(Document.prototype, 'visibilityState', shown); Object.defineProperty(Document.prototype, 'webkitVisibilityState', shown); } catch {}
 const quiet = e => e.stopImmediatePropagation();
 document.addEventListener('visibilitychange', quiet, true); document.addEventListener('webkitvisibilitychange', quiet, true);
 window.addEventListener('blur', e => { if (e.target === window) quiet(e); }, true);
 return true; })()
"""#

let pipScript = #"""
(() => { const v = [...document.querySelectorAll('video')].find(v => v.readyState > 0); if (!v) return 'No playable video found on this page';
 if (document.pictureInPictureElement || v.webkitPresentationMode === 'picture-in-picture') { if (document.pictureInPictureElement && document.exitPictureInPicture) document.exitPictureInPicture(); else v.webkitSetPresentationMode('inline'); return 'closed'; }
 if (v.webkitSupportsPresentationMode && v.webkitSupportsPresentationMode('picture-in-picture')) { v.webkitSetPresentationMode('picture-in-picture'); return 'opened'; }
 if (v.requestPictureInPicture) { v.requestPictureInPicture().catch(() => {}); return 'opened'; }
 return "Floating video isn't available for this player."; })()
"""#

extension Browser {
 // MARK: AI agents

 /// Any number of agents at once, from every window's profile: one server per Still process.
 func startAgentServer() {
  if agentServerStarted { return }
  agentServerStarted = true
  AgentSocket.serve { line, reply in
   guard let home = homeBrowser else { reply(agentFail("Still is closing.")); return }
   home.handleAgent(line, reply)
  }
 }

 func handleAgent(_ line: String, _ reply: @escaping (String) -> Void) { Task { @MainActor in reply(redactReply(await self.agentCall(line))) } }

 @MainActor func agentCall(_ line: String) async -> String {
  guard let root = jsonObject(line), let tool = root["tool"] as? String else { return agentFail("Invalid request.") }
  let raw = root["client"] as? String ?? "An AI agent"
  let cleaned = String(raw.filter { ch in !ch.unicodeScalars.contains { $0.value < 32 || ($0.value >= 127 && $0.value < 160) } }.prefix(40))
  let client = cleaned.isEmpty ? "An AI agent" : cleaned, key = client.lowercased()
  // Still's own chat runs say which chat they are; anyone else is known by name.
  let run = root["run"] as? String ?? ""
  let who = runs[run]?.who == client ? run : client
  let args = root["args"] as? [String: Any] ?? [:]
  guard pref("AgentsEnabled", false) else { return agentFail("AI control is turned off. The user can turn it on in Still → Settings → Let other AI apps use Still.") }
  if tool == "user_confirmed" { return confirmed(client, args) }
  // Don't keep the agent waiting on a bar nobody will see: its app can ask the user (elicitation), or the user is away.
  let elicit = root["elicit"] as? Bool == true, quick = elicit || userAway()
  if blockedAgents.contains(key) { return agentFail("The user blocked this agent in Still for this session.") }
  if let until = stoppedAgents[who], Date() < until { return agentFail(stopText) }
  if pref("ApprovedAgents", [String]()).contains(where: { Mcp.agentName($0).lowercased() == key }) { approvedAgents.insert(key) } // approved once = remembered across restarts
  if !approvedAgents.contains(key) {
   switch await askUser(client, "", now: quick) {
   case .some(false): return agentFail("The user blocked this agent in Still for this session.")
   case nil: return needsConfirm(client, "", "Waiting for the user to let you in: Still shows a bar with Allow and Block at the top of its window. Tell the user to click Allow, then call the tool again.", elicit)
   default: break
   }
  }
  let me = worker(who)
  if Date().timeIntervalSince(me.seen) > 120 && !me.paused { me.since = Date(); me.count = 0; me.recent = [] } // a new stretch of work
  me.seen = Date()
  // The user took over: wait for them to hand it back, like a person would.
  let paused = Date().addingTimeInterval(40)
  while me.paused && Date() < paused { try? await Task.sleep(nanoseconds: 250_000_000); me.seen = Date() }
  if let until = stoppedAgents[who], Date() < until { return agentFail(stopText) }
  if me.paused { return agentFail(me.signIn.isEmpty ? tookOver : signingIn(me.signIn)) }
  // A new companion's first chat opens with its own words: its tools (ask_user too) wait for its hello.
  if kickoffs.contains(who), let kick = runs[who]?.chat {
   let wait = Date().addingTimeInterval(1.5)
   while !kick.messages.contains(where: { $0.role == "assistant" }) && Date() < wait { try? await Task.sleep(nanoseconds: 100_000_000) }
   if !kick.messages.contains(where: { $0.role == "assistant" }) { return agentFail(helloFirst) }
  }
  let interrupt = Answer(), step = AgentStep()
  agentInterrupts[who, default: []].append(interrupt)
  var turn: PageTurn?
  defer {
   turn?.release()
   agentInterrupts[who]?.removeAll { $0 === interrupt }
   if agentInterrupts[who]?.isEmpty == true { agentInterrupts[who] = nil }
   publishEverywhere()
   DispatchQueue.main.asyncAfter(deadline: .now() + 121) { publishEverywhere() } // the pill goes once the agent is quiet
  }
  let limit: Double = tool == "ask_user" || tool == "run_plugin_action" || tool == "ask_companion" ? 660 : tool == "wait_for" ? min(30000, max(100, argNumber(args, "timeoutMs", 10000))) / 1000 + 5 : tool == "upload_file" ? 60 : 30
  // An approval is for what the card showed. The page can change while it waits, so once it's this call's turn Still looks
  // again, and if it's not the same any more it goes back to asking. The same goes for what happens during the step itself.
  for tries in 0... {
   // The permission layer: it runs, asks in the chat, or counts down first. Take over and Stop end the wait too.
   let gate = await race(interrupt, 3600) { await self.gate(who, tool, args, quick, step, elicit) }
   var refused: String?
   switch gate {
   case .done(let reply): refused = reply
   case .interrupted(let reply): refused = reply
   case .late: refused = agentFail(stopText)
   }
   if case .done = gate {} else { for card in runs[who]?.approvals ?? [] { card.answer.set("stop") } }
   if let refused { return refused }
   // An AI may send several calls in one breath. Run side by side their clicks would mix, and each would read the other's
   // effects as its own, so they wait their turn. Stop or Take over while waiting: the call ends here and never acts.
   if takesTurn.contains(tool) {
    let wanted: PageTurn
    do { wanted = try agentTab(who, args).tab.turn } catch { return agentFail(error.localizedDescription) }
    var lost = false
    let waited = await race(interrupt, limit) { await withCheckedContinuation { (go: CheckedContinuation<Void, Never>) in wanted.take { if lost { wanted.release() }; go.resume() } }; return nil }
    switch waited {
    case .done: turn = wanted
    case .interrupted(let reply): lost = true; return reply
    case .late: lost = true; return agentFail("Another step on this page didn't finish within \(Int(limit)) s, so \(tool) wasn't done. Call read_page to see where it is.")
    }
   }
   var same = false
   switch await race(interrupt, limit, { await self.stillTheSame(who, tool, args, step) ? "same" : nil }) {
   case .done(let yes): same = yes != nil
   case .interrupted(let reply): return reply
   case .late: return agentFail("Still couldn't read the page within \(Int(limit)) s, so \(tool) wasn't done. Call read_page to see where it is.")
   }
   if same {
    // The step's intent goes on disk before it runs, its outcome after; every step is a checkpoint.
    let going = runs[who]
    if let going, let intent = step.intent { going.task.sensitive.append(intent); if going.task.sensitive.count > 40 { going.task.sensitive.removeFirst() }; saveTask(going) }
    me.tool = tool; me.target = targetOf(who, tool, args); publishEverywhere()
    defer { me.tool = ""; me.count += 1; me.seen = Date() }
    step.changed = false
    let raced = await race(interrupt, limit, { await self.runTool(who, tool, args, quick, step) }), result: String
    switch raced {
    case .done(let reply): result = reply ?? agentFail("Failed.")
    case .interrupted(let reply): step.abandoned = true; result = reply
    case .late: step.abandoned = true; result = agentFail("\(tool) didn't finish within \(Int(limit)) s, so Still stopped waiting. The page may be slow or stuck: call read_page to see where it is.")
    }
    if !(step.changed && tries < 2) {
     if let going {
      if let ran = step.intent, case .done = raced, !result.contains("\"unverified\":true") { ran.outcome = toolFailed(result) ? "failed" : "done" } // cut off, or no sign it worked: uncertain
      exposed(going, tool, step)
      checkpoint(going, tool, result)
     }
     if (tool == "ask_companion" || tool == "tell_companion") && !me.target.isEmpty && !toolFailed(result) { did(who, (tool == "ask_companion" ? "Asked " : "Handed work to ") + me.target) }
     return result
    }
   } else if tries >= 2 { return agentFail(keptChanging) }
   turn?.release(); turn = nil
   step.again = true
  }
  return agentFail(keptChanging)
 }

 /// Once it's this call's turn, right before it runs: is this still what the gate saw? The same tab on the same site, and for
 /// a click or a key the same control, doing the same thing?
 @MainActor func stillTheSame(_ who: String, _ tool: String, _ args: [String: Any], _ step: AgentStep) async -> Bool {
  if !step.onTab { return true }
  guard let tab = try? agentTab(who, args).tab, tab.id == step.tabId, tool == "navigate" || hostName(tab.url) == step.site else { return false } // navigate's site is where it's going
  if step.print.isEmpty { return true }
  guard let page = try? await agentPage(who, args), let look = (try? await agentJs(page.view, agentScripts["Sensitive"] ?? "", probe(tool, args))) as? [String: Any] else { return false }
  return look["print"] as? String == step.print && (look["why"] as? String ?? "") == step.why
 }
 func probe(_ tool: String, _ args: [String: Any]) -> [String: Any] { ["tool": tool, "id": argId(args), "selector": argText(args, "selector"), "text": argText(args, "text"), "key": argText(args, "key"), "submit": argFlag(args, "submit")] }

 /// Asks the user in the agent bar ("" = may this agent control Still). Nil: no answer yet; the question stays up.
 /// now: don't wait for the answer (the agent asks the user elsewhere, see needsConfirm).
 func askUser(_ client: String, _ ask: String, now: Bool, until: Date? = nil, _ done: @escaping (Bool?) -> Void) {
  if let said = takeAnswer(client, ask) { done(said); return } // answered after the agent stopped waiting
  let deadline = until ?? Date().addingTimeInterval(now ? 0 : 45) // shorter than MCP apps' own tool timeouts
  let wait = Once<Bool?>()
  if approvalWaiters != nil && !(askClient == client && askText == ask) {
   if now || Date() >= deadline { done(nil); return }
   wait.action = { [weak self] _ in self?.askUser(client, ask, now: false, until: deadline, done) } // another question is up: ask once it's answered
  } else {
   if approvalWaiters == nil { approvalWaiters = []; askClient = client; askText = ask; publishEverywhere() }
   wait.action = { [weak self] said in
    guard let self, said == true, !ask.isEmpty else { done(said); return }
    if self.takeAnswer(client, ask) == true { done(true) } else { self.askUser(client, ask, now: now, until: deadline, done) } // another step took that yes: this one asks for itself
   }
  }
  approvalWaiters?.append(wait)
  DispatchQueue.main.asyncAfter(deadline: .now() + max(0, deadline.timeIntervalSinceNow)) { wait.fire(nil) }
 }
 /// A yes is for one step: whichever takes it first, of those waiting on the question or calling again after it. A no stands
 /// for all of them, and so does letting an app in (ask "").
 func takeAnswer(_ client: String, _ ask: String) -> Bool? {
  guard let last = lastAnswer, last.client == client, last.ask == ask, Date().timeIntervalSince(last.at) < 120 else { return nil }
  if last.allow && !ask.isEmpty { lastAnswer = nil }
  return last.allow
 }
 /// A question's words: what follows them in ask ties a yes to the control it was about, and isn't for reading.
 func shown(_ ask: String) -> String { ask.components(separatedBy: "\0")[0] }
 @MainActor func askUser(_ client: String, _ ask: String, now: Bool) async -> Bool? {
  await withCheckedContinuation { done in askUser(client, ask, now: now) { done.resume(returning: $0) } }
 }

 func answerAgent(_ allow: Bool, remember: Bool = true) {
  guard let waiters = approvalWaiters else { return }
  settle(askClient, askText, allow, remember: remember)
  approvalWaiters = nil; askClient = ""; askText = ""
  for wait in waiters { wait.fire(allow) }
  publishEverywhere()
 }

 func settle(_ client: String, _ ask: String, _ allow: Bool, remember: Bool = true) {
  if ask.isEmpty {
   if !allow { blockedAgents.insert(client.lowercased()) }
   else {
    approvedAgents.insert(client.lowercased())
    var list = pref("ApprovedAgents", [String]())
    if remember && !list.contains(where: { $0.lowercased() == client.lowercased() }) { list.append(client); prefs["ApprovedAgents"] = list; saveLater() }
   }
  }
  lastAnswer = (client: client, ask: ask, allow: allow, at: Date())
  confirmCodes = confirmCodes.filter { !($0.value.client == client && $0.value.ask == ask) } // answered here: a code from the chat no longer counts
 }

 // The user is away from Still: the agent asks them in its own chat instead. MCP apps that support elicitation
 // ask the user themselves (the AI never sees the question); otherwise the AI passes the user's answer on.
 func needsConfirm(_ client: String, _ ask: String, _ waiting: String, _ elicit: Bool) -> String {
  guard elicit, pref("AgentsAskInChat", true) else { return agentFail(waiting) }
  confirmCodes = confirmCodes.filter { $0.value.until > Date() }
  let code = String((0..<6).map { _ in "0123456789abcdef".randomElement()! })
  confirmCodes[code] = (client: client, ask: ask, until: Date().addingTimeInterval(600))
  let question = ask.isEmpty ? "Allow \(client) to use your Still browser? It can open, read and click pages, but never private tabs, passwords or cookies." : "Allow \(client) to \(shown(ask))?"
  return jsonText(["ok": false, "confirm": ["code": code, "question": question], "error": waiting])
 }

 func confirmed(_ client: String, _ args: [String: Any]) -> String {
  guard let ask = confirmCodes.removeValue(forKey: argText(args, "code").trimmingCharacters(in: .whitespaces).lowercased()),
        ask.client.lowercased() == client.lowercased(), ask.until > Date() else {
   return agentFail("That code isn't valid anymore (the user may have answered in Still). Call the tool again.")
  }
  let allow = argFlag(args, "allow")
  if approvalWaiters != nil && askClient == ask.client && askText == ask.ask { answerAgent(allow, remember: false) } else { settle(ask.client, ask.ask, allow, remember: false) }
  toast("\(ask.client) was \(allow ? "allowed" : "turned down") \(ask.ask.isEmpty ? "to use Still" : "to " + shown(ask.ask)), answered in that app.")
  return agentOk(["done": allow ? "The user allowed it. Call the tool again now." : "The user said no. Don't try again unless they ask."])
 }

 /// The agent bar's question, or the AI at work for the pill: the one in the page on screen, else the latest.
 func agentData() -> [String: Any]? {
  if approvalWaiters != nil { return ["client": askClient, "pending": true, "action": "", "ask": shown(askText), "paused": false] }
  let shownId = shown?.id
  guard let (key, me) = atWork().max(by: { a, b in
   let x = agentTabs[a.key] == shownId, y = agentTabs[b.key] == shownId
   return x != y ? !x : a.value.seen < b.value.seen
  }) else { return nil }
  var data: [String: Any] = ["client": me.name, "pending": false, "action": me.action, "ask": "", "paused": me.paused, "signIn": me.signIn, "key": key,
   "tool": me.tool, "target": me.target, "count": me.count, "recent": me.recent]
  if let since = me.since { data["since"] = ISO8601DateFormatter().string(from: since) }
  if let tab = agentTabs[key] { data["tab"] = tab }
  return data
 }

 // Take over: the agent stops at once and waits while the user drives, and the tab it works in comes to the front.
 func takeOver(_ on: Bool, _ key: String) {
  guard let me = workers[key] else { return }
  me.paused = on
  taskState(runs[key], on ? "paused" : "running")
  if !on && !me.signIn.isEmpty { me.signedIn = (me.signIn, Date()); me.signIn = "" }
  if on { endCalls(key, agentFail(tookOver)) }
  if on, let id = agentTabs[key], let (browser, tab) = findTab(id) { browser.select(tab); browser.window.makeKeyAndOrderFront(nil) }
  publishEverywhere()
 }

 // Stop cancels what the agent is doing now and lets go of its tabs; it stays allowed, so its next task needs no new approval.
 func stopAgent(_ key: String? = nil) {
  let key = key.flatMap { $0.isEmpty ? nil : $0 } ?? agentData()?["key"] as? String ?? "" // none given: the one in the pill
  let me = workers[key]
  for browser in browsers { for tab in browser.tabs where tab.agentKey == key { if let upload = tab.agentUpload { tab.agentUpload = nil; upload.complete(nil) } } }
  releaseAgentTabs(key)
  stoppedAgents[key] = Date().addingTimeInterval(30)
  endCalls(key, agentFail(stopText))
  if let run = runs[key] { run.queue.removeAll(); stopRun(run) }
  workers[key] = nil
  publishEverywhere(); publishAiEverywhere()
  toast("Stopped " + (me?.label ?? "the AI agent") + ".")
 }

 /// A dialog or file picker opened in the tab an agent is working in: its running call returns now and says so.
 func interruptAgent(_ tab: Tab, _ reply: [String: Any]) {
  guard let who = tab.agentKey, agentTabs[who] == tab.id else { return }
  endCalls(who, agentOk(reply))
 }

 func claim(_ who: String, _ tab: Tab) {
  let before = shown
  agentTabs[who] = tab.id; tab.lastSeen = Date() // in use: memory saver leaves it awake
  if tab.agentKey != who { tab.agent = worker(who).name; tab.agentKey = who; schedulePublish() }
  if shown !== before { // a chat shows the page its AI just moved to
   if let page = shown, page.view == nil, !page.url.isEmpty, let url = URL(string: page.url) { load(url, in: createView(page)) }
   layoutPages(); schedulePublish()
  }
 }

 /// The agent's work is done: its icon leaves the user's own tabs (in every window). Tabs it opened stay in the AI group.
 /// One the user took over is done too.
 func releaseAgentTabs(_ key: String) {
  agentTabs[key] = nil
  if workers[key]?.paused == true { workers[key] = nil }
  for browser in browsers {
   var changed = false
   for tab in browser.tabs where tab.agentKey == key && !tab.aiGroup { tab.agent = nil; tab.agentKey = nil; changed = true }
   if changed { browser.schedulePublish() }
  }
 }

 // Background (the default for Still's own chat): the page belongs to the chat and shows only beside it, never in the
 // user's tab strip. Otherwise Still's chat opens it as the user's own tab, beside the chat, and other AI apps open it
 // next to the other AI tabs. An AI app's background tabs belong to it ("app:" + who) and show in the running tasks.
 // A configuration means a pop-up from an agent's click, which WebKit loads itself.
 @discardableResult
 func openAgentTab(_ who: String, _ url: String, background: Bool? = nil, configuration: WKWebViewConfiguration? = nil) -> Tab {
  var who = who, background = background ?? (runs[who] != nil)
  if configuration != nil, let opener = tabs.filter({ $0.agent == who && Date().timeIntervalSince($0.agentActedAt) < 10 }).max(by: { $0.agentActedAt < $1.agentActedAt }) {
   who = opener.agentKey ?? who; background = opener.inChat != nil // the agent that clicked, where its page is
  }
  let chat = runs[who] != nil ? who : nil
  let tab = Tab()
  tab.url = url; tab.title = url.isEmpty ? "New tab" : hostName(url)
  tab.agent = worker(who).name; tab.agentKey = who
  tab.isPrivate = incognito // an incognito chat's pages: the window's private website data
  if !incognito && onCompanion(who) { tab.engine = "Companion" }
  tab.aiGroup = chat == nil && !background
  tab.runChat = background ? nil : chat
  tab.inChat = background ? chat ?? "app:" + who : nil
  if background { tabs.append(tab) }
  else if chat != nil { tabs.insert(tab, at: tabs.firstIndex { $0 === active }.map { $0 + 1 } ?? tabs.count) }
  else { tabs.insert(tab, at: tabs.lastIndex { $0.aiGroup }.map { $0 + 1 } ?? tabs.count) }
  let view = createView(tab, configuration: configuration)
  if configuration == nil, !url.isEmpty, let address = URL(string: url) { load(address, in: view) }
  if !background && chat == nil, active == nil || active?.url.isEmpty == true && active?.chatId == nil && active?.pinned == false && tabs.count == 2 { select(tab) } // nothing to keep the user on
  claim(who, tab); schedulePublish(); saveLater()
  if background { if let chat, active?.chatId == chat { select(tab) } } // the chat in view splits to show it
  else if let run = chat.flatMap({ runs[$0] }), showing(run.chat) || active?.runChat == run.chat.id { if active?.chatId == run.chat.id { aiView.open = true }; select(tab) }
  return tab
 }

 /// Finds a tab the agent may use: never private tabs. Without a tabId the agent keeps working in the tab it used last,
 /// even after the user switches to another one.
 /// The companion profile keeps its sign-ins apart from the user's, so its chats stay out of the user's tabs, except one handed over.
 func outOfProfile(_ who: String, _ tab: Tab) -> Bool { onCompanion(who) && tab.chatId == nil && tab.engine != "Companion" && (tab.inChat ?? tab.runChat) != who }
 func agentTab(_ who: String, _ args: [String: Any]) throws -> (browser: Browser, tab: Tab) {
  var id = argText(args, "tabId")
  if id.isEmpty, let last = agentTabs[who], findTab(last) != nil { id = last }
  // With the chat in front, a new message carries on in the chat's own page: the chat tab has no page to act on.
  if id.isEmpty, active?.chatId != nil, let page = browsers.flatMap({ $0.tabs }).filter({ ($0.inChat ?? $0.runChat) == who && !$0.closed }).max(by: { $0.lastSeen < $1.lastSeen }) { id = page.id }
  for browser in browsers {
   guard let tab = id.isEmpty ? (browser === self ? browser.active : nil) : browser.tabs.first(where: { $0.id == id }) else { continue }
   // An incognito chat works only in the private tabs it opened. Every other agent never touches a private tab.
   if incognitoRun(who) ? (tab.inChat ?? tab.runChat) != who : tab.isPrivate { throw AgentError(incognitoRun(who) ? "An incognito chat only uses the tabs it opened. Open one with open_tab." : "Private tabs are off-limits to agents.") }
   if outOfProfile(who, tab) { throw AgentError("That tab is in the user's own browser profile, and you browse apart from it. Open a page with open_tab, or ask the user to hand you the tab.") }
   browser.claim(who, tab)
   return (browser, tab)
  }
  throw AgentError(id.isEmpty ? "There is no active tab." : "No tab with that id. Call list_tabs.")
 }

 /// The agent's tab, ready for page work. A page paused on a dialog can't run scripts, so that comes first.
 @MainActor func agentPage(_ who: String, _ args: [String: Any]) async throws -> (browser: Browser, tab: Tab, view: WKWebView) {
  let (browser, tab) = try agentTab(who, args)
  if tab.chatId != nil { throw AgentError("That tab is a chat, not a page. Open a page with open_tab.") }
  if let dialog = tab.dialog { throw AgentError("The page is waiting on a dialog (\(dialog.kind)): \"\(clipped(dialog.message, 200))\". Answer it with handle_dialog first.") }
  let view: WKWebView
  if let open = tab.view { view = open } else {
   view = browser.createView(tab) // a sleeping tab wakes up first
   if !tab.url.isEmpty, let url = URL(string: tab.url) { browser.load(url, in: view) }
   await waitLoaded(tab)
  }
  view.evaluateJavaScript(agentFocusScript, in: nil, in: .page) { _ in }
  return (browser, tab, view)
 }

 /// Keys and Still's own data stay on this computer whatever an AI is told: only the person can pick them. A link is judged by where it leads.
 func offLimitsFile(_ file: URL) -> Bool {
  let keys: Set<String> = [".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".claude", "keychains"]
  return [file.path, file.resolvingSymlinksInPath().path].contains { path in
   path.split(separator: "/").contains { keys.contains($0.lowercased()) } || [support.path, profileHome.path].contains { path.hasPrefix($0 + "/") }
  }
 }

 func agentWebUrl(_ input: String) throws -> String {
  let text = input.trimmingCharacters(in: .whitespacesAndNewlines), url = resolve(text)
  guard !text.isEmpty, let parsed = URL(string: url), let scheme = parsed.scheme?.lowercased(), scheme == "http" || scheme == "https", parsed.host?.isEmpty == false else { throw AgentError("Agents can only open http and https pages.") }
  return url
 }

 /// Has this chat been there, or did the user name it? A tab's title in a message is the page's words, not the user's.
 func beenTo(_ root: AiChat, _ host: String) -> Bool {
  let host = host.lowercased()
  if host == hostName(searchUrl("x")) || root.known.contains(where: { onSite($0, host) }) { return true }
  return root.messages.contains { m in
   guard m.role == "user", m.who == nil else { return false }
   let text = m.text.lowercased().replacingOccurrences(of: #"\[[^\]]*\]\("#, with: "(", options: .regularExpression)
   var from = text.startIndex
   while let hit = text.range(of: #"[a-z0-9-]+(\.[a-z0-9-]+)+|localhost"#, options: .regularExpression, range: from..<text.endIndex) {
    let word = String(text[hit])
    if onSite(word.hasPrefix("www.") ? String(word.dropFirst(4)) : word, host) { return true }
    from = hit.upperBound
   }
   return false
  }
 }
 func siteAllows(_ who: String, _ site: String, _ action: String) -> Bool {
  pref("Permissions", [[String: Any]]()).contains { ruleText($0, "Action") == action && ruleText($0, "Mode") == "always" && onSite(ruleText($0, "Site"), site) && (ruleText($0, "Companion").isEmpty || ruleText($0, "Companion") == who) }
 }
 /// Page text can steer an AI: read something signed in, then carry it off in an address. So what a chat has read decides
 /// whether going somewhere takes a yes. Nil: it doesn't.
 @MainActor func reach(_ root: AiChat, _ tool: String, _ url: String, _ host: String) async -> (why: String, data: Bool)? {
  guard let u = URLComponents(string: url), ["http", "https"].contains(u.scheme?.lowercased() ?? "") else { return nil }
  let extra = (u.percentEncodedQuery?.count ?? 0) + (u.percentEncodedFragment?.count ?? 0)
  if root.read > 0 && (extra > 200 || u.percentEncodedPath.count > 300) { return ("This address carries a lot of data: " + clipped(u.percentEncodedPath + (u.percentEncodedQuery.map { "?" + $0 } ?? "") + (u.percentEncodedFragment.map { "#" + $0 } ?? ""), 120), true) }
  if beenTo(root, host) { return nil }
  if await privateHost(host) { return ("This is on your own computer or network.", false) }
  // ponytail: a few short addresses can still carry a little, and a form on an allowed site isn't an address at all. Hosts by name, so a domain rebinding after this check gets through.
  if root.read > 0 && (tool != "read_url" || root.read > 1 || extra > 60) { return ("A new site for this chat, after it read from the web.", false) }
  return nil
 }
 /// What this step adds to what the chat has read, and where it has been.
 func exposed(_ run: ChatRun, _ tool: String, _ step: AgentStep) {
  let root = exchangeOf(run.chat).root
  let been = step.onTab ? step.site : step.signedOut ? "" : step.goes
  if !been.isEmpty && !root.known.contains(been) { root.known.append(been) }
  let signedIn = run.chat.ephemeral ? 1 : 2 // an incognito window holds nothing else
  switch tool {
  case "read_page", "find", "screenshot", "wait_for", "click", "type", "press_key", "handle_dialog", "list_tabs", "run_plugin_action": root.read = max(root.read, signedIn)
  case "read_url": root.read = max(root.read, step.signedOut ? 1 : signedIn)
  case "web_search", "read_attachment": root.read = max(root.read, 1)
  default: break
  }
 }

 /// The rule that applies, most specific first: this companion on this site, this companion anywhere, everyone on this site, everyone anywhere.
 func permissionMode(_ companion: String, _ site: String, _ action: String) -> String? {
  let rules = pref("Permissions", [[String: Any]]()).filter { ruleText($0, "Action") == action }
  let mine = companion.isEmpty ? nil : rules.first { ruleText($0, "Companion") == companion && onSite(ruleText($0, "Site"), site) } ?? rules.first { ruleText($0, "Companion") == companion && ruleText($0, "Site").isEmpty }
  let rule = mine ?? rules.first { ruleText($0, "Companion").isEmpty && onSite(ruleText($0, "Site"), site) } ?? rules.first { ruleText($0, "Companion").isEmpty && ruleText($0, "Site").isEmpty }
  return rule.map { ruleText($0, "Mode") }
 }
 func setPermission(_ site: String, _ action: String, _ companion: String, _ mode: String) {
  var list = pref("Permissions", [[String: Any]]()).filter { !(ruleText($0, "Site") == site && ruleText($0, "Action") == action && ruleText($0, "Companion") == companion) }
  if ["always", "chat", "ask"].contains(mode) { list.append(["Site": site, "Action": action, "Companion": companion, "Mode": mode]) }
  prefs["Permissions"] = list; saveLater()
 }

 /// Whether this call may go ahead: nil, or the refusal for the AI.
 @MainActor func gate(_ who: String, _ tool: String, _ args: [String: Any], _ quick: Bool, _ step: AgentStep, _ elicit: Bool) async -> String? {
  var action: String
  switch tool {
  case "read_page", "find", "screenshot", "wait_for", "web_search", "read_url": action = "read"
  case "open_tab", "navigate", "go_back", "go_forward", "reload", "switch_tab", "close_tab": action = "navigate"
  case "click", "type", "press_key", "scroll", "handle_dialog": action = "interact"
  default: return nil // list_tabs shows no page; ask_user and save_file stay in Still; upload_file asks every time on its own
  }
  var site = "", what = "", why = "", url = ""
  let again = step.again
  step.intent = nil; step.again = false; step.onTab = false; step.allowed = false; step.signedOut = false; step.print = ""; step.why = ""; step.goes = ""
  do {
   if tool == "open_tab" || tool == "navigate" { url = try agentWebUrl(argText(args, "url")); site = hostName(url); what = "Open " + site }
   else if tool == "read_url" { url = try agentWebUrl(argText(args, "url")); site = hostName(url); what = "Read " + site }
   else if tool == "web_search" { site = hostName(searchUrl("x")); what = "Search for “" + clipped(argText(args, "query"), 60) + "”" }
   else {
    site = hostName(try agentTab(who, args).tab.url)
    let named = ["scroll": "Scroll the page", "press_key": "Press " + argText(args, "key"), "handle_dialog": "Answer the page's dialog", "go_back": "Go back",
                 "go_forward": "Go forward", "reload": "Reload the page", "close_tab": "Close a tab", "switch_tab": "Switch tabs"]
    what = named[tool] ?? "Read the page"
    if tool == "click" || tool == "type" || tool == "press_key" {
     let page = try await agentPage(who, args)
     // Pages re-render under the AI: a control that isn't there yet is waited for here, so it's asked about like any other.
     let look = try await settled(page.tab, page.view) {
      guard let seen = try await agentJs(page.view, agentScripts["Sensitive"] ?? "", probe(tool, args)) as? [String: Any] else { throw PageMiss(missed: true, message: "The page is still loading, so nothing was done. Call read_page, then try again.") }
      return seen
     } as? [String: Any] ?? [:]
     let label = look["label"] as? String ?? ""
     why = look["why"] as? String ?? ""
     step.why = why; step.print = look["print"] as? String ?? ""
     // AIs never type a password: they wait while the user signs in.
     if look["password"] as? Bool == true && tool != "click" && !(tool == "press_key" && ["Tab", "Escape", "Esc"].contains(argText(args, "key"))) {
      let (browser, tab) = try agentTab(who, args)
      askToSignIn(who, browser, tab, site)
      return agentFail(signingIn(site))
     }
     if tool == "click" { what = "Click “" + label + "”" }
     else if tool == "type" { what = look["secret"] as? Bool == true || argText(args, "text").isEmpty ? "Type into “" + label + "”" : "Type “" + clipped(argText(args, "text"), 60) + "” into “" + label + "”" }
    }
   }
   if !["open_tab", "read_url", "web_search"].contains(tool) { step.tabId = try agentTab(who, args).tab.id; step.site = site; step.onTab = true }
  } catch { return agentFail(error.localizedDescription) } // no page, no such element, or the check couldn't run: without the check, nothing happens
  let marked = pref("SensitiveSites", [String]()).contains { onSite($0, site) }
  if action == "interact" && (!why.isEmpty || marked) { action = "sensitive"; if why.isEmpty { why = "You marked " + site + " as sensitive." } }
  let run = runs[who]
  if again { if let run { audit(run.chat, what, site, "The page changed, so Still asked again") }; why = why.isEmpty ? "The page changed since you were asked." : "The page changed since you were asked. " + why }
  // A child task (a teammate asked it) acts only where everyone up the chain may, with the approvals given in the
  // user's chat. Outside apps ask before a sensitive step; the rest goes unless you set a rule or marked the site sensitive.
  let up = run.map { exchangeOf($0.chat) }
  var mode = up.map { u in strictest(u.chain.map { permissionMode($0, site, action) ?? defaultPermission(action) }) } ?? permissionMode("", site, action) ?? (marked || action == "sensitive" ? "ask" : "always")
  let key = action + " " + site
  var data = false
  if let up, !url.isEmpty {
   step.goes = site
   if !up.chain.allSatisfy({ siteAllows($0, site, action) }), let asked = await reach(up.root, tool, url, site) { why = why.isEmpty ? asked.why : why + " " + asked.why; data = asked.data; if mode == "always" { mode = "chat" } }
  }
  var granted = !data && (mode == "always" || mode == "chat" && (up.map { $0.root.allowed.contains(key) } ?? sessionGrants.contains(who + " " + key)))
  if action == "sensitive" && run?.recheck == true { granted = false } // picked up after one that may not have finished: the user decides again
  guard let run else {
   if granted { return nil }
   let ask = what.prefix(1).lowercased() + what.dropFirst() + " on " + site + (step.print.isEmpty ? "" : "\0" + step.print)
   switch await askUser(who, ask, now: quick) {
   case .some(false): return agentFail("The user said no to this. Don't try it again unless they ask.")
   case nil: return needsConfirm(who, ask, "Waiting for the user to allow it: Still shows Allow and Block at the top of its window. Tell the user, then call \(tool) again.", elicit)
   default: break
   }
   if mode == "chat" { sessionGrants.insert(who + " " + key) }
   return nil
  }
  if granted && action != "sensitive" { if action == "interact" { audit(run.chat, what, site, mode == "always" ? "Allowed by your settings" : "Allowed in this chat") }; return nil }
  var answer = await approve(run, what, site, action, why, countdown: granted)
  if answer == "always" && (run.chat.ephemeral || site.isEmpty) { answer = "chat" } // an incognito chat writes no site rules, and a page with no site has none to write
  if answer == "always" { for companion in up?.chain ?? [run.chat.companion] { setPermission(site, action, companion, "always") } } // who the card named, and whoever they're helping: not everyone
  if let root = up?.root, answer == "chat" && !root.allowed.contains(key) { root.allowed.append(key) }
  step.allowed = ["always", "chat", "once"].contains(answer)
  let results = ["always": "You always allow this on " + site, "chat": "You allowed it in this chat", "once": "You allowed it once", "go": "Went ahead after 8 seconds",
                 "now": "You let it go ahead", "cancel": "You cancelled it", "stop": "Stopped", "timeout": "No answer in 10 minutes"]
  audit(run.chat, what, site, results[answer] ?? "You said no")
  publishAiEverywhere()
  if ["always", "chat", "once", "go", "now"].contains(answer) && action == "sensitive" {
   if run.recheck { run.recheck = false; for s in run.task.sensitive where s.outcome == nil { s.outcome = "rechecked" } }
   step.intent = AiSensitive(what, site)
  }
  switch answer {
  case "always", "chat", "once", "go", "now": return nil
  case "cancel": return agentFail("The user cancelled this before it ran. Don't try it again unless they ask.")
  case "stop": return agentFail(stopText)
  case "timeout": return agentFail("The user didn't answer within 10 minutes. Stop here and ask them in your reply.")
  default: return agentFail("The user said no to this. Don't try it again; if you need it, ask them in your reply.")
  }
 }

 @MainActor func runTool(_ who: String, _ tool: String, _ args: [String: Any], _ quick: Bool, _ step: AgentStep) async -> String {
  do {
   if incognitoRun(who), ["remember", "forget", "update_knowledge", "save_file", "offer_routine"].contains(tool) { return agentFail(keepsNothing) }
   switch tool {
   case "ask_user": return await withCheckedContinuation { done in askInChat(who, args) { done.resume(returning: $0) } }
   case "offer_routine": return await offerRoutine(who, args)
   case "ask_companion", "tell_companion", "list_companions": return await exchange(who, tool, args)
   case "list_connected_plugins", "find_plugins", "get_plugin_tools", "run_plugin_action": return await pluginTool(who, tool, args)
   case "remember", "recall", "forget", "update_knowledge", "read_knowledge", "open_memory_source": return memoryTool(who, tool, args)
   case "load_skill":
    // Only a skill the companion has; never matched by keyword. The step shows only when one loads.
    let id = tidy((args["id"] as? String ?? "")).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    guard let run = runs[who], let mine = companions.first(where: { $0.id == run.chat.companion }), mine.skills.contains(id), let skill = Skill.all.first(where: { $0.id == id }) else {
     return agentFail("You don't have a skill with the id \"\(id)\". Use an id from your skills listed at the start of the chat, or carry on without one.")
    }
    chatStep(run.chat, "Used skill " + skill.name); publishAiEverywhere()
    return agentOk(["skill": skill.name, "instructions": skill.body])
   case "save_file":
    let reply = saveFile(who, args)
    if let done = (jsonObject(reply)?["result"] as? [String: Any])?["done"] as? String, let space = done.firstIndex(of: " "), let end = done.range(of: " in the user's Library") {
     did(who, (done.hasPrefix("Replaced") ? "Updated" : "Saved") + done[space..<end.lowerBound]); publishAiEverywhere()
    }
    return reply
   case "list_tabs":
    var list: [[String: Any]] = []
    for (index, browser) in browsers.enumerated() {
     for tab in browser.tabs where incognitoRun(who) ? (tab.inChat ?? tab.runChat) == who : !tab.isPrivate && !outOfProfile(who, tab) {
      var item: [String: Any] = ["tabId": tab.id, "title": tab.title, "url": tab.url, "window": index + 1]
      if tab === browser.active { item["active"] = true }
      if agentTabs[who] == tab.id { item["yours"] = true }
      list.append(item)
     }
    }
    return agentOk(list)
   case "web_search": return try await webSearch(who, args)
   case "read_url": return try await readUrl(who, args, step)
   case "read_attachment": return readAttachment(who, argText(args, "id"), max(0, (args["offset"] as? NSNumber)?.intValue ?? 0))
   case "open_tab":
    let background = args["background"] as? Bool ?? (runs[who] != nil)
    let url = try agentWebUrl(argText(args, "url")), chat = runs[who] != nil ? who : nil
    let mine = browsers.flatMap(\.tabs).filter { !$0.closed && (chat != nil ? ($0.runChat ?? $0.inChat) == chat : $0.aiGroup && $0.agentKey == who || $0.inChat == "app:" + who) }
    if mine.count >= 6 { return agentFail("You already have 6 tabs open. Reuse one with navigate, or close one with close_tab first.") } // tabs one chat (or one outside AI) may have open at once
    // An incognito chat's pages open in its window; no other agent opens one in an incognito window.
    guard let host = incognitoRun(who) ? chatRunner(who) : chatRunner(who) ?? self, host.incognito == incognitoRun(who) else {
     return agentFail(incognitoRun(who) ? "The incognito window closed." : "Agents don't open tabs in an incognito window.")
    }
    let tab = host.openAgentTab(who, url, background: background)
    await waitLoaded(tab)
    did(who, "Opened " + hostName(tab.url)); return agentOk(["tabId": tab.id, "title": tab.title, "url": tab.url])
   case "navigate":
    let (_, tab, view) = try await agentPage(who, args)
    guard let address = URL(string: try agentWebUrl(argText(args, "url"))) else { return agentFail("Agents can only open http and https pages.") }
    let asked = Date()
    view.load(URLRequest(url: address)); await waitLoaded(tab)
    if tab.loadFailedAt > asked { return agentFail("That page didn't load: " + hostName(address.absoluteString) + ". Check the address, or try again.") }
    did(who, "Went to " + hostName(tab.url)); return agentOk(["tabId": tab.id, "title": tab.title, "url": tab.url])
   case "switch_tab":
    let (browser, tab) = try agentTab(who, args)
    if argFlag(args, "show") { browser.select(tab); browser.window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    did(who, "Switched to " + tab.title); return agentOk(["tabId": tab.id, "title": tab.title, "url": tab.url])
   case "close_tab":
    let (browser, tab) = try agentTab(who, args)
    browser.close(tab, force: true); agentTabs[who] = nil
    did(who, "Closed a tab"); return agentOk(["done": "Closed the tab"])
   case "go_back", "go_forward", "reload":
    let (_, tab, view) = try await agentPage(who, args)
    if tool == "go_back" { guard view.canGoBack else { return agentFail("There's no earlier page in this tab.") }; view.goBack() }
    else if tool == "go_forward" { guard view.canGoForward else { return agentFail("There's no later page in this tab.") }; view.goForward() }
    else { view.reload() }
    await waitLoaded(tab)
    did(who, tool == "reload" ? "Reloaded the page" : tool == "go_back" ? "Went back" : "Went forward"); return agentOk(["url": tab.url, "title": tab.title])
   case "read_page":
    let (browser, tab, view) = try await agentPage(who, args)
    let text = !(args["text"] as? Bool == false || args["text"] as? String == "false")
    let page = try await agentJs(view, agentScripts["Snapshot"] ?? "", ["text": text, "all": argFlag(args, "all"), "offset": Int(min(1e9, max(0, argNumber(args, "offset", 0))))])
    var seen = redactLogins(view.url?.absoluteString ?? "", page as? String ?? "")
    let site = hostName(tab.url)
    let back = worker(who).signedIn.map { $0.site == site && Date().timeIntervalSince($0.at) < 120 } ?? false
    if !back, (try? await agentJs(view, "return [...document.querySelectorAll('input[type=password]')].some(e=>e.getClientRects().length&&!e.disabled)", [:])) as? Bool == true {
     askToSignIn(who, browser, tab, site); seen += "\n\n" + signingIn(site)
    }
    did(who, "Read " + hostName(tab.url)); return agentOk(["text": seen])
   case "find":
    let (_, _, view) = try await agentPage(who, args)
    let found = try await agentJs(view, agentScripts["Find"] ?? "", ["text": argText(args, "text")])
    did(who, "Looked for \"" + argText(args, "text") + "\""); return agentOk(["text": redactLogins(view.url?.absoluteString ?? "", found as? String ?? "")])
   case "screenshot":
    let (browser, tab, view) = try await agentPage(who, args)
    // A page only paints while it's on screen: show it for a moment, then give the user their tab back.
    let previous = browser.active
    if tab !== previous { browser.select(tab); try? await Task.sleep(nanoseconds: 300_000_000) }
    let prints = loginPrints(view.url?.absoluteString ?? "") // fields showing a saved login are masked in the picture
    if !prints.isEmpty, (try? await agentJs(view, agentScripts["Mask"] ?? "", ["prints": prints, "on": true])) as? Bool != true {
     if let previous, previous !== tab, !previous.closed, browser.active !== previous { browser.select(previous) }
     return agentFail("Couldn't hide the saved login on this page, so no screenshot was taken.")
    }
    let shot: (NSImage?, Error?) = await withCheckedContinuation { done in view.takeSnapshot(with: nil) { done.resume(returning: ($0, $1)) } }
    if !prints.isEmpty { _ = try? await agentJs(view, agentScripts["Mask"] ?? "", ["prints": prints, "on": false]) }
    if let previous, previous !== tab, !previous.closed, browser.active !== previous { browser.select(previous) }
    guard let image = shot.0, let tiff = image.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else {
     return agentFail("Couldn't take the screenshot" + (shot.1.map { ": " + $0.localizedDescription } ?? "."))
    }
    did(who, "Took a screenshot"); return agentOk(["image": png.base64EncodedString(), "mimeType": "image/png"])
   case "click":
    let (_, tab, view) = try await agentPage(who, args)
    let o: [String: Any] = ["id": argId(args), "selector": argText(args, "selector"), "text": argText(args, "text"), "expect": step.print]
    let hit = try await settled(tab, view) { try await agentJs(view, agentScripts["Click"] ?? "", o) } as? [String: Any] ?? [:]
    let x = (hit["x"] as? NSNumber)?.doubleValue ?? 0, y = (hit["y"] as? NSNumber)?.doubleValue ?? 0
    let label = hit["label"] as? String ?? "", before = agentTabs[who] ?? ""
    await pointer(who, tab, view, x, y)
    tab.agentActedAt = Date() // a pop-up or file picker it opens belongs to the agent
    let urlBefore = tab.url
    try await mouseClick(view, x, y, o, step)
    // The chat's step only had the element's number from the AI's call ("Clicking element 7"): name what it was. The AI
    // may have sent more calls in the same breath, so it isn't always the last step.
    let numbered = "Clicking element " + ((args["id"] as? NSNumber)?.stringValue ?? args["id"] as? String ?? "")
    if !label.isEmpty, let step = runs[who]?.chat.messages.last(where: { $0.role == "tool" && $0.text == numbered }) { step.text = "Clicking “" + label + "”" }
    if let missed = try await verdict(who, tab, view, before, urlBefore, "", label, step) { return missed }
    did(who, "Clicked '" + label + "'"); return agentOk(outcome(who, tab, before, "Clicked \"" + label + "\""))
   case "type":
    let (_, tab, view) = try await agentPage(who, args)
    let text = argText(args, "text"), append = argFlag(args, "append"), submit = argFlag(args, "submit"), before = agentTabs[who] ?? ""
    let typed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if typed.count >= 4 { runs[who]?.typed.insert(typed) } // form data: memory never keeps it
    let q = { (clicked: Bool) -> [String: Any] in ["id": argId(args), "selector": argText(args, "selector"), "value": text, "append": append, "clicked": clicked, "expect": step.print] }
    var focus = try await settled(tab, view) { try await agentJs(view, agentScripts["Focus"] ?? "", q(false)) } as? [String: Any] ?? [:]
    tab.agentActedAt = Date()
    if let picked = focus["done"] as? String, !picked.isEmpty { did(who, picked); return agentOk(["done": picked]) }
    if let at = focus["at"] as? [String: Any], let x = (at["x"] as? NSNumber)?.doubleValue, let y = (at["y"] as? NSNumber)?.doubleValue {
     await pointer(who, tab, view, x, y)
     if !step.print.isEmpty { _ = try await agentJs(view, agentScripts["Same"] ?? "", ["expect": step.print]) }
     try? await mouseClick(view, x, y, q(false), step)
     focus = try await agentJs(view, agentScripts["Focus"] ?? "", q(true)) as? [String: Any] ?? [:] // the click moved the caret: put it back
    } else if let near = focus["near"] as? [String: Any], let x = (near["x"] as? NSNumber)?.doubleValue, let y = (near["y"] as? NSNumber)?.doubleValue {
     await pointer(who, tab, view, x, y)
    }
    let field = focus["label"] as? String ?? ""
    func unchanged() async -> Bool { ((try? await agentJs(view, "return { sig: sig(deepActive()) };", [:])) as? [String: Any])?["sig"] as? String == focus["sig"] as? String }
    try step.live()
    if !step.print.isEmpty { _ = try await agentJs(view, agentScripts["Same"] ?? "", ["expect": step.print]) } // nothing typed yet: a change asks again
    if !text.isEmpty {
     view.insertText(text)
     // Some editors ignore inserted text: put it in the way typing would, or type it key by key.
     if await unchanged() { _ = try await agentJs(view, agentScripts["Focus"] ?? "", q(true)); _ = try await agentJs(view, agentInsertScript, ["text": text, "append": append]) }
     if text.count <= 4000, await unchanged() { _ = try await agentJs(view, agentScripts["Focus"] ?? "", q(true)); await typeKeys(view, text, focus["multiline"] as? Bool == true, worker(who), step) }
     if await unchanged() { return agentFail("Typed, but \"" + field + "\" didn't change. Click it first, then type without an id, or use press_key.") }
    } else if !append { try await pressKey(view, "Backspace", step) }
    if submit {
     let urlBefore = tab.url
     // Already typed, so a change here stops with Enter unpressed instead of starting over.
     do {
      _ = try await agentJs(view, agentScripts["Watch"] ?? "", ["expect": step.print]); try await pressKey(view, "Enter", step)
      if let unsent = try await verdict(who, tab, view, before, urlBefore, "Enter", field, step) { return unsent }
     } catch is PageChanged { return agentFail("Typed into \"" + field + "\", but the page changed before Enter, so Still didn't press it. Call read_page to see it now.") }
    }
    did(who, "Typed into " + field)
    return agentOk(outcome(who, tab, before, (text.isEmpty ? "Cleared \"" : "Typed into \"") + field + "\"" + (submit ? " and pressed Enter" : "")))
   case "press_key":
    let (_, tab, view) = try await agentPage(who, args)
    let before = agentTabs[who] ?? "", urlBefore = tab.url
    tab.agentActedAt = Date()
    _ = try await agentJs(view, agentScripts["Watch"] ?? "", ["expect": step.print]); try await pressKey(view, argText(args, "key"), step)
    if let nothing = try await verdict(who, tab, view, before, urlBefore, argText(args, "key"), "", step) { return nothing }
    did(who, "Pressed " + argText(args, "key")); return agentOk(outcome(who, tab, before, "Pressed " + argText(args, "key")))
   case "scroll":
    let (_, _, view) = try await agentPage(who, args)
    try step.live()
    let o: [String: Any] = ["id": argId(args), "selector": argText(args, "selector"), "direction": argText(args, "direction"), "amount": min(20000, max(0, argNumber(args, "amount", 0)))]
    let scrolled = try await agentJs(view, agentScripts["Scroll"] ?? "", o) as? [String: Any] ?? [:], done = scrolled["done"] as? String ?? ""
    var reply: [String: Any] = ["done": done]
    if let at = scrolled["at"] as? String, !at.isEmpty { reply["at"] = at }
    did(who, done); return agentOk(reply)
   case "wait_for":
    let (_, tab, view) = try await agentPage(who, args)
    let gone = argFlag(args, "gone"), q: [String: Any] = ["id": argId(args), "selector": argText(args, "selector"), "text": argText(args, "text"), "gone": gone]
    if argId(args).isEmpty && argText(args, "selector").isEmpty && argText(args, "text").isEmpty { return agentFail("Pass an id, selector or text to wait for.") }
    let until = Date().addingTimeInterval(min(30000, max(100, argNumber(args, "timeoutMs", 10000))) / 1000)
    while true {
     if try await agentJs(view, agentScripts["Wait"] ?? "", q) as? Bool == true { did(who, "Waited for the page"); return agentOk(["found": !gone, "done": gone ? "It's gone" : "It's there", "url": tab.url]) }
     if Date() >= until { return agentOk(["found": gone, "done": gone ? "Still there after waiting" : "Didn't appear in time", "url": tab.url]) }
     try? await Task.sleep(nanoseconds: 250_000_000)
    }
   case "handle_dialog":
    let (browser, tab) = try agentTab(who, args)
    guard tab.dialog != nil else { return agentFail("No dialog is open in this tab.") }
    let accept = !(args["accept"] as? Bool == false || args["accept"] as? String == "false"), before = agentTabs[who] ?? ""
    browser.answerDialog(tab, accept, args["text"] as? String)
    await waitLoaded(tab, 8)
    did(who, accept ? "Accepted a dialog" : "Dismissed a dialog"); return agentOk(outcome(who, tab, before, accept ? "Accepted the dialog" : "Dismissed the dialog"))
   case "upload_file":
    let (_, tab, view) = try await agentPage(who, args)
    return try await uploadFiles(who, tab, view, args, quick, step)
   default: return agentFail("Unknown tool: " + tool)
   }
  } catch is PageChanged { step.changed = true; step.intent?.outcome = "failed"; return agentFail(keptChanging) } // nothing was sent
  catch { return agentFail(error.localizedDescription) }
 }

 @MainActor func uploadFiles(_ who: String, _ tab: Tab, _ view: WKWebView, _ args: [String: Any], _ quick: Bool, _ step: AgentStep) async throws -> String {
  var paths: [String] = []
  if let list = args["paths"] as? [Any] { paths = list.map { $0 as? String ?? "" } } else if let one = args["paths"] as? String { paths = [one] }
  var files: [URL] = []
  for path in paths {
   let trimmed = path.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "\""))
   if trimmed.isEmpty { continue }
   guard localFilePath(trimmed) else { return agentFail("Pass full paths of files on this computer, like /Users/you/report.pdf.") }
   let file = URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath).standardizedFileURL
   if !files.contains(file) { files.append(file) }
  }
  if files.isEmpty { return agentFail("Pass paths: the full paths of the files to attach.") }
  if files.count > 12 { return agentFail("Attach at most 12 files at a time.") }
  if files.contains(where: offLimitsFile) { return agentFail("Still doesn't let an AI attach files from that folder. The user can attach it themselves.") }
  let notInput = "That isn't a file upload field. Click the page's upload button instead, then call upload_file without an id."
  let noPicker = "No file picker is open. Click the page's upload button first (Still catches the picker for you), or pass the id of a file input."
  let query: [String: Any] = ["id": argId(args), "selector": argText(args, "selector")], byId = !argId(args).isEmpty || !argText(args, "selector").isEmpty
  let pick = "const pick = (() => {\n" + (agentScripts["FileInput"] ?? "") + "\n})();\n" + agentPickTail
  if byId {
   var check = query; check["click"] = false
   guard try await agentJs(view, pick, check) as? Bool == true else { return agentFail(notInput) }
  } else if tab.agentUpload == nil { return agentFail(noPicker) }
  else if tab.agentUpload?.multiple == false && files.count > 1 { return agentFail("This file picker takes one file.") }
  let site = hostName(tab.url), frame = byId ? "" : tab.agentUpload?.host ?? ""
  let names = files.map { $0.lastPathComponent }.joined(separator: ", ")
  let ask = "upload " + (files.count == 1 ? "this file: " : "\(files.count) files: ") + files.map(\.path).joined(separator: ", ") + " to " + (!frame.isEmpty && frame != site ? frame + " (a frame inside " + site + ")" : site)
  switch await askUser(who, ask, now: quick) {
  case .some(false): return agentFail("The user didn't allow this upload. Don't try again unless they ask.")
  case nil: return agentFail("Waiting for the user to allow the upload: Still shows Allow and Block at the top of its window. Tell the user, then call upload_file again.")
  default: break
  }
  if hostName(tab.url) != site { return agentFail("The page went to another site while the user was being asked, so nothing was attached.") }
  if let missing = files.first(where: { (try? $0.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile != true }) { return agentFail("There's no file at " + missing.path) }
  if !byId {
   guard let picker = tab.agentUpload else { return agentFail(noPicker) }
   tab.agentUpload = nil
   picker.complete(files)
  } else {
   // Click the file input: WebKit asks for files (runOpenPanel), and agentPicker answers with these.
   if let picker = tab.agentUpload { tab.agentUpload = nil; picker.complete(nil) }
   tab.uploadFiles = files; tab.agentActedAt = Date()
   var click = query; click["click"] = true
   _ = try await agentJs(view, pick, click)
   let until = Date().addingTimeInterval(3)
   while tab.uploadFiles != nil && Date() < until { try? await Task.sleep(nanoseconds: 100_000_000) }
   if tab.uploadFiles != nil { tab.uploadFiles = nil; return agentFail(notInput) }
  }
  did(who, "Attached " + names); return agentOk(["done": "Attached " + names])
 }

 /// The page wants files. An agent's upload_file answers it, or, when an agent's click opened it, upload_file will:
 /// nothing pops up, and the agent's running call says a file picker opened.
 func agentPicker(_ tab: Tab, _ multiple: Bool, _ frame: WKFrameInfo, _ complete: @escaping ([URL]?) -> Void) -> Bool {
  if let files = tab.uploadFiles {
   guard frame.isMainFrame, multiple || files.count == 1 else { complete(nil); return true } // what was approved was the page's own field
   tab.uploadFiles = nil; complete(files); return true
  }
  guard tab.agent != nil, Date().timeIntervalSince(tab.agentActedAt) < 10 else { return false }
  if let old = tab.agentUpload { tab.agentUpload = nil; old.complete(nil) }
  tab.agentUpload = AgentUpload(multiple: multiple, host: frame.securityOrigin.host.lowercased(), complete: complete)
  interruptAgent(tab, ["fileChooser": ["multiple": multiple], "url": tab.url, "note": "The page opened a file picker. Call upload_file with the full paths of the files to attach; the user is asked to allow it."])
  return true
 }

 // MARK: Page dialogs

 /// alert, confirm and prompt show in Still's own dialog (or an agent answers them); the page waits until then.
 func openDialog(_ view: WKWebView, _ kind: String, _ message: String, _ defaultText: String, _ frame: WKFrameInfo, _ answer: @escaping (Bool, String?) -> Void) {
  guard let tab = tabs.first(where: { $0.view === view }) else { answer(false, nil); return }
  if let old = tab.dialog { tab.dialog = nil; old.answer(false, nil) }
  let host = frame.securityOrigin.host
  tab.dialog = PageDialog(kind: kind, message: message, defaultText: defaultText, site: host.hasPrefix("www.") ? String(host.dropFirst(4)) : host, answer: answer)
  var info: [String: Any] = ["type": kind, "message": clipped(message, 500)]
  if kind == "prompt" { info["defaultText"] = defaultText }
  interruptAgent(tab, ["dialog": info, "url": tab.url, "note": "The page is paused on this dialog. Answer it with handle_dialog (accept=true or false)."])
  if tab === active { schedulePublish() }
 }

 func answerDialog(_ tab: Tab, _ accept: Bool, _ text: String?) {
  guard let dialog = tab.dialog else { return }
  tab.dialog = nil
  dialog.answer(accept, text)
  schedulePublish()
 }

 /// A page going away still answers its dialog and file picker: WebKit requires every one to be answered exactly once.
 func releasePage(_ tab: Tab) {
  if let dialog = tab.dialog { tab.dialog = nil; dialog.answer(false, nil) }
  if let upload = tab.agentUpload { tab.agentUpload = nil; upload.complete(nil) }
  tab.uploadFiles = nil
 }

 // MARK: Bookmarks and video

 func exportBookmarks() {
  let picker = NSSavePanel()
  picker.nameFieldStringValue = "Still bookmarks.html"
  picker.beginSheetModal(for: window) { result in
   guard result == .OK, let file = picker.url else { return }
   let escape = { (text: String) -> String in text.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;").replacingOccurrences(of: "\"", with: "&quot;") }
   let lines = self.bookmarks.map { mark -> String in "<DT><A HREF=\"" + escape(mark["Url"] as? String ?? "") + "\">" + escape(mark["Title"] as? String ?? "") + "</A>" }
   let html = "<!DOCTYPE NETSCAPE-Bookmark-file-1><META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\"><TITLE>Still bookmarks</TITLE><H1>Still bookmarks</H1><DL><p>\n" + lines.joined(separator: "\n") + "\n</DL>"
   do { try html.write(to: file, atomically: true, encoding: .utf8); self.toast("Bookmarks exported.") } catch { self.toast("Couldn't export bookmarks: " + error.localizedDescription) }
  }
 }

 func pictureInPicture() {
  guard let view = active?.view else { return }
  view.evaluateJavaScript(pipScript) { result, error in
   if error != nil { self.toast("Floating video isn't available for this player."); return }
   if let message = result as? String, message != "opened", message != "closed" { self.toast(message) }
  }
 }

 // MARK: The interface's side

 /// The interface's agent ops (agentTakeOver, agentStop, permAnswer, permSet, permSensitive, permReset); false = not one of them.
 func handleAgentOps(_ op: String, _ data: [String: Any]) -> Bool {
  switch op {
  case "agentTakeOver": takeOver(argFlag(data, "on"), argText(data, "key"))
  case "agentStop": stopAgent(argText(data, "key"))
  case "permAnswer": // a card's answer, for that card alone
   let id = argText(data, "id"), answer = argText(data, "answer")
   if answer == "cancel" && id == wentAhead { toast("Too late to cancel. That step had already gone ahead."); break }
   guard let asking = runs[argText(data, "run").isEmpty ? shownChat?.id ?? "" : argText(data, "run")] else { break }
   for card in asking.approvals where card.id == id { card.answer.set(["once", "chat", "always", "cancel", "now", "connect"].contains(answer) ? answer : "deny") }
  case "permSet":
   guard permissionActions.contains(argText(data, "action")) else { break }
   setPermission(siteOf(argText(data, "site")), argText(data, "action"), argText(data, "companion"), argText(data, "mode")); publishAiEverywhere()
  case "permSensitive":
   let marked = siteOf(argText(data, "site"))
   guard !marked.isEmpty else { break }
   prefs["SensitiveSites"] = pref("SensitiveSites", [String]()).filter { $0 != marked } + (argFlag(data, "on") ? [marked] : [])
   saveLater(); publishAiEverywhere()
  case "permReset": prefs["Permissions"] = [[String: Any]](); prefs["SensitiveSites"] = [String](); saveLater(); publishAiEverywhere()
  default: return false
  }
  return true
 }
 /// Agent fields of the `state` message: the tabs AIs are at work in (the `agent` bar itself is main.swift's agentData()).
 func agentStateFields() -> [String: Any] { ["working": atWork().compactMap { agentTabs[$0.key] }] }
 /// Agent fields of the `ai` message for the chat on screen (approvals, audit, permissions, sensitiveSites).
 func agentAiFields(_ shown: AiChat?) -> [String: Any] {
  let rules = pref("Permissions", [[String: Any]]())
  let everyone = permissionActions.map { action -> [String: Any] in
   let rule = rules.first { ruleText($0, "Action") == action && ruleText($0, "Site").isEmpty && ruleText($0, "Companion").isEmpty }
   return ["site": "", "action": action, "companion": "", "mode": rule.map { ruleText($0, "Mode") } ?? defaultPermission(action)]
  }
  let specific = rules.filter { !ruleText($0, "Site").isEmpty || !ruleText($0, "Companion").isEmpty }
   .map { ["site": ruleText($0, "Site"), "action": ruleText($0, "Action"), "companion": ruleText($0, "Companion"), "mode": ruleText($0, "Mode")] }
  // The shown chat's cards, and those of the child tasks it started (they ask in the user's chat).
  let asking = shown.map { s in runs.values.filter { $0.chat === s || $0.chat.from != nil && exchangeOf($0.chat).root === s } } ?? []
  return ["permissions": everyone + specific, "sensitiveSites": pref("SensitiveSites", [String]()),
          "approvals": asking.flatMap { r in r.approvals.map { ["id": $0.id, "run": r.chat.id, "who": r.chat.companion, "what": $0.what, "site": $0.site, "action": $0.action, "why": $0.why, "until": $0.until.map { isoText($0) as Any } ?? NSNull()] as [String: Any] } },
          "audit": shown.map { chat in chat.audit.suffix(100).map { ["at": isoText($0.at), "what": $0.what, "site": $0.site, "result": $0.result] } } as Any? ?? NSNull()]
 }
}

/// The Unix socket each running profile listens on for agent calls, in its folder. Only this user can open it.
enum AgentSocket {
 /// In the profile's folder, or, when that path is too long for a socket, in this user's own temporary folder, named after it.
 static func path(_ folder: URL = support) -> String {
  let inside = folder.appendingPathComponent("agent.sock").path
  if inside.utf8.count < 104 { return inside }
  var hash: UInt64 = 0xcbf29ce484222325 // FNV-1a
  for byte in folder.standardizedFileURL.path.utf8 { hash = (hash ^ UInt64(byte)) &* 0x100000001b3 }
  return userTemp + "still-" + String(hash, radix: 16) + ".sock"
 }
 static let userTemp: String = {
  var buffer = [CChar](repeating: 0, count: 1024)
  return confstr(_CS_DARWIN_USER_TEMP_DIR, &buffer, buffer.count) > 0 ? String(cString: buffer) : NSTemporaryDirectory()
 }()

 static func address(_ path: String) -> sockaddr_un? {
  var addr = sockaddr_un()
  let bytes = Array(path.utf8)
  guard bytes.count < MemoryLayout.size(ofValue: addr.sun_path) else { return nil }
  addr.sun_family = sa_family_t(AF_UNIX)
  addr.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
  withUnsafeMutableBytes(of: &addr.sun_path) { raw in for (index, byte) in bytes.enumerated() { raw[index] = byte } }
  return addr
 }

 /// Connects to the Still running on this profile folder, if it's this user's.
 static func dial(_ folder: URL = support) -> Int32? {
  guard var addr = address(path(folder)) else { return nil }
  let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
  if fd < 0 { return nil }
  let result = withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
  var uid = uid_t(0), gid = gid_t(0)
  if result != 0 || Darwin.getpeereid(fd, &uid, &gid) != 0 || uid != getuid() { _ = Darwin.close(fd); return nil }
  var on: Int32 = 1
  _ = Darwin.setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
  return fd
 }

 /// Any number of agents at once: each connection gets its own thread, and calls run side by side on the main thread.
 static func serve(_ handle: @escaping (String, @escaping (String) -> Void) -> Void) {
  if let other = dial() { _ = Darwin.close(other); NSLog("Still: another copy is already serving AI agents"); return }
  let path = path()
  _ = Darwin.unlink(path) // left behind by a Still that quit or crashed
  guard var addr = address(path) else { return }
  let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
  if fd < 0 { return }
  let mask = Darwin.umask(0o077) // never open to others, not even for a moment
  let bound = withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
  _ = Darwin.umask(mask)
  guard bound == 0, Darwin.listen(fd, 16) == 0 else { _ = Darwin.close(fd); NSLog("Still: couldn't open the agent socket"); return }
  _ = Darwin.chmod(path, 0o600)
  _ = signal(SIGPIPE, SIG_IGN)
  Thread.detachNewThread {
   while true {
    let client = Darwin.accept(fd, nil, nil)
    if client < 0 { if errno != EINTR { Thread.sleep(forTimeInterval: 0.2) }; continue }
    var uid = uid_t(0), gid = gid_t(0)
    guard Darwin.getpeereid(client, &uid, &gid) == 0, uid == getuid() else { _ = Darwin.close(client); continue }
    Thread.detachNewThread { AgentSocket.serveClient(client, handle) }
   }
  }
 }

 static func serveClient(_ fd: Int32, _ handle: @escaping (String, @escaping (String) -> Void) -> Void) {
  defer { _ = Darwin.close(fd) }
  var on: Int32 = 1
  _ = Darwin.setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
  var buffer = Data()
  while let line = receiveLine(fd, &buffer, keepWaiting: { true }) {
   let reply = Box<String>(), answered = DispatchSemaphore(value: 0)
   DispatchQueue.main.async { handle(line) { reply.value = $0; answered.signal() } }
   answered.wait()
   if !writeLine(fd, reply.value ?? agentFail("Failed.")) { return }
  }
 }

 /// One line (without its newline), or nil when the other side hung up or keepWaiting says to give up.
 static func receiveLine(_ fd: Int32, _ buffer: inout Data, keepWaiting: () -> Bool) -> String? {
  var chunk = [UInt8](repeating: 0, count: 65536)
  while true {
   if let end = buffer.firstIndex(of: 10) {
    let line = String(decoding: buffer[buffer.startIndex..<end], as: UTF8.self)
    buffer.removeSubrange(buffer.startIndex...end)
    return line
   }
   let count = Darwin.read(fd, &chunk, 65536)
   if count > 0 { buffer.append(contentsOf: chunk[0..<count]); continue }
   if count < 0 && (errno == EAGAIN || errno == EINTR) && keepWaiting() { continue }
   return nil
  }
 }

 static func writeLine(_ fd: Int32, _ text: String) -> Bool {
  let data = Array((text + "\n").utf8)
  var sent = 0
  while sent < data.count {
   let count = data.withUnsafeBytes { Darwin.write(fd, $0.baseAddress! + sent, $0.count - sent) }
   if count < 0 && errno == EINTR { continue }
   if count <= 0 { return false }
   sent += count
  }
  return true
 }
}

/// `Still --mcp`: a Model Context Protocol server over stdio (JSON-RPC, one message per line). AI apps launch it, and it
/// forwards tool calls to the running Still. `Still --cli <tool> as=<name> [key=value ...]`: one tool call from a terminal.
/// Flags: --as <name> (who it is, as the user sees it), --run <chat id> (Still's own chat), --this-profile (locked to its
/// profile, with the chat's own tools), --no-tools, --profile and --profiles-root (main.swift reads those), --qa.
enum Mcp {
 struct Tool { let name: String, description: String, props: [(String, [String: Any])], required: [String] }
 static func tool(_ name: String, _ description: String, _ props: [(String, [String: Any])], _ required: [String]) -> Tool { Tool(name: name, description: description, props: props, required: required) }
 static func str(_ name: String, _ description: String) -> (String, [String: Any]) { (name, ["type": "string", "description": description]) }
 static func bool(_ name: String, _ description: String) -> (String, [String: Any]) { (name, ["type": "boolean", "description": description]) }
 static func num(_ name: String, _ description: String) -> (String, [String: Any]) { (name, ["type": "number", "description": description]) }
 static let tabId = str("tabId", "Tab id (optional)")
 static let browserTools: [Tool] = [
  tool("list_tabs", "List the open tabs (never private ones) with their tabIds. `yours` marks the tab you're working in.", [], []),
  tool("web_search", "Search the web and get the results (title, URL, snippet) without opening a tab. Start here for questions and research; open a tab only to click, type, sign in or show the user something.",
       [str("query", "What to search for"), num("count", "How many results, up to 10 (default 8)")], ["query"]),
  tool("read_attachment", "Read a file the user attached to their message, by the id Still gave you: text and code come back as text (20000 characters at a time), PDFs as their text, images as the image itself.", [str("id", "The attachment's id"), num("offset", "Text position to continue from, for long files")], ["id"]),
  tool("read_url", "Read a web page's main text without opening a tab (12000 characters at a time). For pages you only need to read; use open_tab when you have to click or type there. It reads signed out (the reply says signedOut) unless the user named the site or you've used it in this chat; open_tab it to see it signed in.",
       [str("url", "The page's URL"), num("offset", "Text position to continue from, for long pages")], ["url"]),
  tool("open_tab", "Open a URL or search terms in a new tab and work there from now on, to click, type or sign in. The user keeps their own tab and can keep browsing. Start most hands-on tasks here.",
       [str("url", "URL or search terms"), bool("background", "true (the default in Still's chat): your own tab, kept out of the user's tab strip. false: open it among the user's tabs, only when they asked for it there")], ["url"]),
  tool("navigate", "Load a URL or search terms in your current tab (or tabId).", [str("url", "URL or search terms"), tabId], ["url"]),
  tool("switch_tab", "Work in another tab from now on. It stays in the background unless show is true.", [str("tabId", "Tab id from list_tabs"), bool("show", "Bring it to the front (only when the user asked to see it)")], ["tabId"]),
  tool("close_tab", "Close your current tab (or tabId).", [tabId], []),
  tool("go_back", "Go back in your tab's history.", [tabId], []),
  tool("go_forward", "Go forward in your tab's history.", [tabId], []),
  tool("reload", "Reload your tab.", [tabId], []),
  tool("read_page", "See the page: title, URL and scroll position, then one line per button, link and field near the visible part as [id] kind \"label\" (→ link, =value, {options}, ✓/☐ checked), then the page text (8000 characters at a time). An id keeps working as long as its element is on the page.",
       [bool("text", "Include the page text (default true). false = controls only, far fewer tokens"), bool("all", "List controls on the whole page, not just near the visible part"), num("offset", "Text position to continue from, for long pages"), tabId], []),
  tool("find", "Search the page for text: the buttons, links and fields that match (with ids) and the matching lines of text, from anywhere on the page. Much cheaper than read_page on a big page.", [str("text", "Text to look for"), tabId], ["text"]),
  tool("click", "Click an element like a real mouse click (it's scrolled into view first). Says where you ended up, and whether a new tab, dialog or file picker opened.",
       [str("id", "Element id from read_page or find"), str("text", "Or: visible text of the button or link"), str("selector", "Or: CSS selector"), tabId], []),
  tool("type", "Type into a field, replacing what's in it (append=true adds instead). Without an id, types into the focused field. On a dropdown, picks the option with that text. submit=true presses Enter afterwards.",
       [str("text", "Text to type, or the option to pick"), str("id", "Element id from read_page or find"), str("selector", "Or: CSS selector"), bool("submit", "Press Enter afterwards"), bool("append", "Add to the field's text instead of replacing it"), tabId], ["text"]),
  tool("save_file", "Save a file for the user: a table as CSV, notes as Markdown, data as JSON, or plain text. It goes in their Library and shows in the chat as a card they can open, so don't paste its contents into your reply. Saving again with the same name replaces the one you saved. Up to 5 MB.",
       [str("name", "File name with its ending, like laptops-under-800.csv"), str("content", "The whole file")], ["name", "content"]),
  tool("press_key", "Press a key in the page: Enter, Escape, Tab, ArrowDown, PageDown, Backspace, a letter, or a combination like Control+A or Shift+Tab.", [str("key", "Key or combination"), tabId], ["key"]),
  tool("scroll", "Scroll down or up (the page, or the scrolling panel in the middle of the view), or bring element id into view.",
       [("direction", ["type": "string", "enum": ["down", "up"]] as [String: Any]), num("amount", "Pixels (default: most of a screen)"), str("id", "Element id: scroll it into view, or with direction, scroll the panel it's in"), tabId], []),
  tool("wait_for", "Wait until an element or some text appears (or, with gone=true, disappears), for up to timeoutMs.",
       [str("text", "Text to wait for"), str("id", "Or: element id"), str("selector", "Or: CSS selector"), bool("gone", "Wait for it to disappear instead"), num("timeoutMs", "Up to 30000 (default 10000)"), tabId], []),
  tool("handle_dialog", "Answer the alert, confirm, prompt or \"leave page?\" dialog the page is paused on (other tools tell you when one opens).",
       [bool("accept", "true = OK / Leave, false = Cancel / Stay (default true)"), str("text", "For a prompt: the text to answer with"), tabId], []),
  tool("upload_file", "Attach files to the file picker the page just opened (click its upload button first), or to a file input by id. Still asks the user to allow it.",
       [("paths", ["type": "array", "items": ["type": "string"], "description": "Full paths of the files on this computer"] as [String: Any]), str("id", "Element id of a file input (optional)"), tabId], ["paths"]),
  tool("screenshot", "PNG of the visible part of a tab. Costs far more tokens than read_page or find: use it only when how the page looks matters.", [tabId], [])
 ]
 // Still's own companions keep a memory of the user, on this computer, one per companion; and Still's own chat can show
 // the user a question with options and wait for the answer.
 static let chatTools: [Tool] = [
  tool("remember", "Keep one short, lasting thing about the user in your memory, like \"Prefers aisle seats\" or \"Lives in Lisbon\": one sentence, 300 characters at most (the chat keeps the details). It's saved with today's date and the message it came from. To change something you remember, pass its id as replaces (or the same slot): the old version stays as history and stops counting. When the user corrects you, use kind correction. Never pass passwords, codes, card or account numbers, form data or anything from private tabs: Still refuses them, and it refuses what the user asked you to forget unless they say it again.",
       [str("fact", "The fact, in one short sentence"), str("kind", "profile (who they are, how to talk to them), preference, fact, person, project or correction"), str("subject", "Who it's about when it's not the user, like \"Maya (sister)\""),
        str("replaces", "The id of the memory this one updates, from recall"), str("slot", "A name for a thing that holds one value, like \"home city\" or \"browser\": a new memory in the same slot replaces the old"),
        bool("guessed", "true when you worked it out from what they did rather than they told you. It's kept apart and marked until they confirm it")], ["fact"]),
  tool("recall", "Look up what you remember about the user, and summaries of your past chats with them: what best matches the words given, with ids, dates and where each came from. Leave query empty for the most important ones. When nothing matches, it says so: don't guess.", [str("query", "A few words about what you're looking for")], []),
  tool("open_memory_source", "Show the messages a memory or a past chat came from, to check what the user actually said. Pass a memory's id or a past chat's id from recall.", [str("id", "The memory's or the past chat's id")], ["id"]),
  tool("read_knowledge", "Read one of your knowledge files (listed at the start of the chat): its full text and its version.", [str("file", "The file's id, like \"deals\"")], ["file"]),
  tool("update_knowledge", "Rewrite one of your knowledge files with what it should hold now. Read it first: pass its whole new text in short, tidy Markdown, keeping what's still true, and the version you read. If it changed since, nothing is written and you get the current text to work from. Never put passwords, codes, card or account numbers, form data or anything from private tabs in it: Still refuses them.",
       [str("file", "The file's id, like \"deals\""), str("text", "The file's full new text, in Markdown"), str("version", "The version read_knowledge gave you")], ["file", "text", "version"]),
  tool("forget", "Forget something: pass its id from recall (that forgets every version of it), or words that every memory to forget contains. If more than three match, nothing is forgotten and you get the list to check with the user. Use it when the user asks you to forget something.", [str("id", "The memory's id"), str("about", "Or: words in the memories to forget")], []),
  tool("load_skill", "Load one of your skills, listed at the start of the chat, by its id: you get its full steps to follow. Call it before you start whenever a skill's line describes the task, and skip it when none does. Only your own skills load.", [str("id", "The skill's id from your list, like \"pitch\"")], ["id"]),
  tool("ask_user", "Ask the user a question in Still's chat and wait for the answer (up to 10 minutes). Use it when you need a decision you shouldn't make yourself, and before buying, sending or deleting anything. Offer 2-4 short options when you can; the user can also write their own answer.",
       [str("question", "The question, in one short sentence"), ("options", ["type": "array", "items": ["type": "string"], "description": "2-4 short answers to pick from"] as [String: Any]),
        str("tabId", "When a page needs the user (a captcha, a code, signing in): that tab, so the card can open it for them")], ["question"]),
  tool("offer_routine", "Offer to repeat something that clearly helped on a schedule. Still asks the user in the chat, and the routine is added to your profile only if they say yes. Offer it once, after a useful result.",
       [str("text", "What to do each time, as an instruction to yourself"), str("time", "When, as HH:mm (24-hour)"),
        ("days", ["type": "array", "items": ["type": "integer"], "description": "Days of the week: 0 = Sunday to 6 = Saturday"] as [String: Any])], ["text", "time", "days"]),
  // Teammates: the user's other companions, each with its own role, memory and tools (Ai.swift, exchange).
  tool("list_companions", "List your teammates: the user's other companions, what each one does, and which one is you.", [], []),
  tool("ask_companion", "Ask a teammate something and wait for their reply (up to 10 minutes). They answer with their own role, memory and tools, and only they see your message. Say what you need and why, with what they need from you. The user sees the exchange.",
       [str("name", "The teammate's name, from list_companions"), str("message", "What you're asking them"), str("title", "What you're asking for in a few words, as in \"asked Jonah for a pitch\": a pitch. The user sees it.")], ["name", "message"]),
  tool("tell_companion", "Hand work over to a teammate without waiting: they do it in the background and their result comes back to this chat, where the user sees it. Give them everything they need to do it.",
       [str("name", "The teammate's name, from list_companions"), str("message", "What they should do, with what they need from you"), str("title", "What you're asking for in a few words, as in \"asked Jonah for a pitch\": a pitch. The user sees it.")], ["name", "message"]),
  // The user's own apps (Gmail, Calendar, Slack…) through Composio, once they connect them (Plugins.swift).
  tool("list_connected_plugins", "Names of the user's apps (plugins) connected for you, like Gmail or Slack. Names only: get_plugin_tools loads one app's actions.", [], []),
  tool("find_plugins", "Look up apps Still can connect through Composio, by name or category: each one's name, categories and whether it's connected for you.",
       [str("query", "Words in the app's name (optional)"), str("category", "A category, like Productivity, Communication or Finance (optional)")], []),
  tool("get_plugin_tools", "Load one app's actions, only when you need that app: each action's name, what it does, its inputs and whether it asks the user first.",
       [str("plugin", "The app, like Gmail or Google Calendar"), str("query", "Words to narrow a long list, like send email (optional)")], ["plugin"]),
  tool("run_plugin_action", "Run one action from get_plugin_tools. Reading goes ahead; anything that sends, posts, deletes, pays or changes data waits for the user's OK. If the app isn't connected, Still asks the user to connect it: don't guess.",
       [str("plugin", "The app, like Gmail"), str("action", "The action's name from get_plugin_tools, like GMAIL_SEND_EMAIL"), ("args", ["type": "object", "description": "The action's inputs, as get_plugin_tools describes them"] as [String: Any])], ["plugin", "action"])
 ]
 static let listProfilesTool = tool("list_profiles", "List Still's profiles (separate logins, cookies and tabs) and which are open. Pass a name as `profile` to any other tool, or \"temp\" for a clean temporary window.", [], [])
 static let profileProp = str("profile", "Still profile name from list_profiles (optional; defaults to the launch profile). A closed profile is opened. \"temp\" opens a separate temporary window with no cookies, logins or history, deleted after it closes.")
 // Every tool can target another Still profile by name, or "temp": a fresh window with no cookies, logins or history.
 // Each profile is its own Still process with its own socket. The AI sidebar's agent is locked to its own profile.
 static func toolList(_ lockProfile: Bool) -> [Tool] {
  if noTools { return [] }
  if lockProfile { return browserTools + chatTools.filter { !noPlugins || !["list_connected_plugins", "find_plugins", "get_plugin_tools", "run_plugin_action"].contains($0.name) } }
  return [listProfilesTool] + browserTools.map { Tool(name: $0.name, description: $0.description, props: $0.props + [profileProp], required: $0.required) }
 }
 static let instructions: String = "You're driving the user's own Still browser, signed in as them. "
  + "Look things up with web_search and read_url: they need no tab. For hands-on work, open_tab, so the user can keep browsing. "
  + "Use read_page to see a page (text=false when you only need its controls) and find to locate something on a big page; then click, type and press_key with the element ids. "
  + "Actions report where you ended up and any new tab, dialog or file picker, so read the page again only when you need to see what changed. "
  + "If Still says it's waiting for the user, tell the user what to click and stop until they reply. "
  + "Ask the user before buying anything, sending messages or posts, or deleting things. Private tabs, passwords and cookies are never available."

 static func schema(_ tool: Tool) -> [String: Any] {
  var properties: [String: Any] = [:]
  for (name, schema) in tool.props { properties[name] = schema }
  let input: [String: Any] = ["type": "object", "properties": properties, "required": tool.required]
  return ["name": tool.name, "description": tool.description, "inputSchema": input]
 }

 /// The name the user sees for an agent: "Claude", not "claude-code".
 static func agentName(_ client: String) -> String {
  let lowered = client.lowercased()
  for (key, name) in [("claude", "Claude"), ("codex", "ChatGPT"), ("openai", "ChatGPT"), ("chatgpt", "ChatGPT"), ("grok", "Grok"), ("gemini", "Gemini"), ("cursor", "Cursor"), ("copilot", "Copilot"), ("windsurf", "Windsurf")] where lowered.contains(key) { return name }
  return client
 }

 static var runId = "" // Still's own chat: which chat this server works for (--run)
 static var noTools = false // --no-tools: a talk with no browser at all (setup's interview)
 static var noPlugins = false // --no-plugins: an incognito chat, where connected apps are off
 static let outLock = NSLock(), stateLock = NSLock()
 static var cancelledIds = Set<String>()
 // Questions this server asks the user through their AI app (MCP elicitation), by request id.
 static var asks: [String: (wait: DispatchSemaphore, answer: Box<[String: Any]>)] = [:]
 static var asked = 0
 static func locked<T>(_ body: () -> T) -> T { stateLock.lock(); defer { stateLock.unlock() }; return body() }
 static func send(_ message: [String: Any]) {
  outLock.lock(); defer { outLock.unlock() }
  try? FileHandle.standardOutput.write(contentsOf: Data((jsonText(message) + "\n").utf8))
 }
 static func idKey(_ id: Any) -> String { (id as? String).map { "s" + $0 } ?? "n\(id)" }

 static func run() {
  _ = signal(SIGPIPE, SIG_IGN)
  let forced = argAfter("--as"), lockProfile = CommandLine.arguments.contains("--this-profile")
  runId = argAfter("--run") ?? ""
  noTools = CommandLine.arguments.contains("--no-tools")
  noPlugins = CommandLine.arguments.contains("--no-plugins")
  var client = forced ?? "An AI agent", canElicit = false
  let tools = toolList(lockProfile).map { schema($0) }
  let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1"
  while let line = Swift.readLine() {
   guard let message = jsonObject(line) else { continue }
   let method = message["method"] as? String ?? ""
   if method.isEmpty { // the app answering one of our questions
    if let rid = message["id"] as? String, let ask = locked({ asks.removeValue(forKey: rid) }) { ask.answer.value = message["result"] as? [String: Any]; ask.wait.signal() }
    continue
   }
   if method == "notifications/cancelled" {
    if let rid = (message["params"] as? [String: Any])?["requestId"] { _ = locked { cancelledIds.insert(idKey(rid)) } }
    continue
   }
   guard let id = message["id"] else { continue } // other notifications need no reply
   let params = message["params"] as? [String: Any] ?? [:]
   switch method {
   case "initialize":
    if forced == nil { client = agentName((params["clientInfo"] as? [String: Any])?["name"] as? String ?? client) }
    canElicit = (params["capabilities"] as? [String: Any])?["elicitation"] != nil
    let result: [String: Any] = ["protocolVersion": params["protocolVersion"] as? String ?? "2025-06-18", "capabilities": ["tools": [String: Any]()], "serverInfo": ["name": "still", "version": version],
                                 "instructions": instructions + (lockProfile ? "" : " Still can have several profiles (separate logins); list_profiles shows them and every tool takes an optional profile name, or \"temp\" for a clean temporary window.")]
    send(["jsonrpc": "2.0", "id": id, "result": result])
   case "ping": send(["jsonrpc": "2.0", "id": id, "result": [String: Any]()])
   case "tools/list": send(["jsonrpc": "2.0", "id": id, "result": ["tools": tools]])
   case "tools/call":
    // Calls run side by side, so one slow page never holds up the next request, and the app can cancel any of them.
    let name = params["name"] as? String ?? ""
    var args = params["arguments"] as? [String: Any] ?? [:]
    if lockProfile { args["profile"] = nil }
    let who = client, ask = canElicit, key = idKey(id)
    DispatchQueue.global().async { Mcp.callTool(id, key, who, name, args, ask, lockProfile) }
   default:
    let error: [String: Any] = ["code": -32601, "message": "Method not found: " + method]
    send(["jsonrpc": "2.0", "id": id, "error": error])
   }
  }
 }

 static func callTool(_ id: Any, _ key: String, _ who: String, _ name: String, _ args: [String: Any], _ canElicit: Bool, _ lockProfile: Bool) {
  let cancelled: () -> Bool = { Mcp.locked { Mcp.cancelledIds.contains(key) } }
  var reply = lockProfile && name == "list_profiles" || name == "user_confirmed" ? agentFail("Unknown tool: " + name) : call(who, name, args, elicit: canElicit, cancelled: cancelled)
  // The user isn't at Still: their AI app asks them (the AI never sees the question), then the call carries on.
  var tries = 0
  while tries < 2, canElicit, let confirm = jsonObject(reply)?["confirm"] as? [String: Any], let question = confirm["question"] as? String,
        let code = confirm["code"] as? String, let action = elicit(question, cancelled: cancelled) {
   tries += 1
   var answer = args
   answer["code"] = code; answer["allow"] = action == "accept"
   _ = call(who, "user_confirmed", answer, cancelled: cancelled)
   reply = action == "accept" ? call(who, name, args, elicit: canElicit, cancelled: cancelled) : agentFail("The user said no. Don't try again unless they ask.")
  }
  if !cancelled() { send(["jsonrpc": "2.0", "id": id, "result": toolResult(reply)]) }
  _ = locked { cancelledIds.remove(key) }
 }

 /// "accept" or "decline", or nil if the user closed it, didn't answer or the app couldn't ask.
 static func elicit(_ question: String, cancelled: () -> Bool) -> String? {
  let rid = locked { () -> String in asked += 1; return "still-\(asked)" }
  let wait = DispatchSemaphore(value: 0), answer = Box<[String: Any]>()
  locked { asks[rid] = (wait: wait, answer: answer) }
  let schema: [String: Any] = ["type": "object", "properties": [String: Any]()]
  let params: [String: Any] = ["message": question, "requestedSchema": schema]
  send(["jsonrpc": "2.0", "id": rid, "method": "elicitation/create", "params": params])
  let deadline = Date().addingTimeInterval(600)
  var answered = false
  while !answered && !cancelled() && Date() < deadline { answered = wait.wait(timeout: .now() + 1) == .success }
  _ = locked { asks.removeValue(forKey: rid) }
  guard answered, let action = answer.value?["action"] as? String, action == "accept" || action == "decline" else { return nil }
  return action
 }

 /// A profile is open while its Still holds the running lock in its folder.
 static func isOpen(_ folder: URL) -> Bool {
  let fd = Darwin.open(folder.appendingPathComponent("running.lock").path, O_RDONLY)
  if fd < 0 { return false }
  defer { _ = Darwin.close(fd) }
  return flock(fd, LOCK_SH | LOCK_NB) != 0 && errno == EWOULDBLOCK
 }
 static func listProfiles() -> String {
  agentOk(Profiles.read().map { profile -> [String: Any] in
   let folder = Profiles.folder(profile.id)
   return ["name": profile.name, "id": profile.id, "open": isOpen(folder), "launch": profile.id == Profiles.launchId, "defaultForAgent": folder.standardizedFileURL.path == support.standardizedFileURL.path]
  })
 }
 /// Starts Still on another profile, as its own process that doesn't share this server's stdio.
 static func launch(_ arguments: [String]) {
  let all = arguments + (isQa ? ["--qa"] : [])
  if Bundle.main.bundleURL.pathExtension == "app" {
   let config = NSWorkspace.OpenConfiguration()
   config.createsNewApplicationInstance = true
   config.activates = !isQa
   config.arguments = all
   NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: config)
  } else {
   let process = Process()
   process.executableURL = URL(fileURLWithPath: stillExecutable)
   process.arguments = all
   process.standardInput = FileHandle.nullDevice; process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
   try? process.run()
  }
 }

 static var tempFolder: URL?, tempStarted = Date.distantPast
 static let tempLock = NSLock()
 /// Opens (once per agent session) a Still window on a brand-new throwaway profile, with this agent already allowed in.
 static func openTemp(_ client: String) -> URL {
  tempLock.lock(); defer { tempLock.unlock() }
  if let tempFolder, isOpen(tempFolder) || Date().timeIntervalSince(tempStarted) < 30 { return tempFolder } // open, or still starting
  let root = FileManager.default.temporaryDirectory.appendingPathComponent("Still-temp")
  for old in (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? [] where !isOpen(old) { try? FileManager.default.removeItem(at: old) } // earlier ones, closed
  let folder = root.appendingPathComponent(newId())
  try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
  let state: [String: Any] = ["UiVersion": 4, "Welcome": false, "Preferences": ["AgentsEnabled": true, "ApprovedAgents": [client]] as [String: Any]]
  try? Data(jsonText(state).utf8).write(to: folder.appendingPathComponent("state.json"))
  tempFolder = folder; tempStarted = Date()
  launch(["--profile", folder.path, "--profiles-root", folder.path, "--temp"])
  return folder
 }

 /// Sends one tool call to the Still running on the requested profile (opening it if it's closed) and returns its JSON reply.
 /// One connection per call: calls never queue behind each other, and a cancelled call just hangs up.
 static func call(_ client: String, _ tool: String, _ args: [String: Any], elicit: Bool = false, cancelled: @escaping () -> Bool = { false }) -> String {
  if tool == "list_profiles" { return listProfiles() }
  var args = args, folder = support
  let name = args["profile"] as? String ?? "", temp = name.lowercased() == "temp"
  args["profile"] = nil
  if temp {
   // The user's own Still decides first: AI control off, a block, or a question to answer, all come back as they are.
   let answer = call(client, "list_tabs", [:], elicit: elicit, cancelled: cancelled)
   if (try? JSONSerialization.jsonObject(with: Data(answer.utf8)) as? [String: Any])?["ok"] as? Bool == false { return answer }
   folder = openTemp(client)
  }
  else if !name.isEmpty {
   guard let profile = Profiles.read().first(where: { $0.name.lowercased() == name.lowercased() || $0.id == name }) else { return agentFail("No Still profile is named \"\(name)\". Use list_profiles.") }
   folder = Profiles.folder(profile.id)
   if !isOpen(folder) { launch(["--profile", folder.path, "--profiles-root", profileHome.path]) }
  }
  let until = Date().addingTimeInterval(name.isEmpty ? 0 : 25)
  while !cancelled() {
   if let fd = AgentSocket.dial(folder) {
    defer { _ = Darwin.close(fd) }
    var timeout = timeval(tv_sec: 1, tv_usec: 0) // wake up every second to check for a cancel
    _ = Darwin.setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
    if AgentSocket.writeLine(fd, jsonText(["client": client, "tool": tool, "args": args, "elicit": elicit, "run": runId])) {
     // Still answers every call within its own time limit; this only covers a Still that froze.
     let deadline = Date().addingTimeInterval(tool == "list_tabs" || tool == "save_file" ? 120 : 720) // ask_user and permission cards wait up to 11 minutes
     var buffer = Data()
     if let line = AgentSocket.receiveLine(fd, &buffer, keepWaiting: { !cancelled() && Date() < deadline }) { return line }
     if Date() >= deadline { return agentFail("Still didn't answer in time. It may be busy; try again, or ask the user to check Still.") }
    }
   }
   if Date() >= until {
    return agentFail(temp ? "The temporary window didn't start. Try again." : (name.isEmpty ? "Still isn't running. " : "Still profile \"\(name)\" isn't reachable. ") + "Open it and turn on Settings → Let AI agents control Still (each profile has its own switch), then try again.")
   }
   Thread.sleep(forTimeInterval: 0.5)
  }
  return agentFail("Cancelled.")
 }

 /// A page read comes back as plain text (no JSON escaping, fewer tokens); other results as compact JSON.
 static func toolResult(_ reply: String) -> [String: Any] {
  let result = jsonObject(reply) ?? [:]
  guard result["ok"] as? Bool == true else { return ["content": [["type": "text", "text": result["error"] as? String ?? "Failed."]], "isError": true] }
  if let data = result["result"] as? [String: Any], let image = data["image"] as? String { return ["content": [["type": "image", "data": image, "mimeType": data["mime"] as? String ?? "image/png"]]] }
  return ["content": [["type": "text", "text": plainText(result["result"])]]]
 }

 static func plainText(_ data: Any?) -> String {
  if let object = data as? [String: Any], object.count == 1, let text = object["text"] as? String { return text }
  guard let data, JSONSerialization.isValidJSONObject(data), let json = try? JSONSerialization.data(withJSONObject: data, options: [.withoutEscapingSlashes]) else { return "{}" }
  return String(decoding: json, as: UTF8.self)
 }

 /// Prints the reply; screenshots are saved as PNG and their path printed. Exit code 0 on success.
 static func cli(_ argv: [String]) -> Int32 {
  if argv.isEmpty || ["help", "--help", "-h"].contains(argv[0]) {
   print("Usage: Still --cli <tool> as=<your name> [key=value ...]\n\nTools:")
   for tool in toolList(false) { print("  \(tool.name) " + tool.props.map { $0.0 + "=" }.joined(separator: " ") + "\n      " + tool.description) }
   return 0
  }
  var args: [String: Any] = [:]
  for argument in argv.dropFirst() {
   guard let equals = argument.firstIndex(of: "="), equals > argument.startIndex else { print("Arguments are key=value, got: \(argument)"); return 2 }
   let key = String(argument[..<equals].drop(while: { $0 == "-" })), value = String(argument[argument.index(after: equals)...])
   if value == "true" || value == "false" { args[key] = value == "true" }
   else if ["amount", "timeoutMs", "offset"].contains(key), let number = Double(value) { args[key] = number }
   else if key == "paths" { args[key] = value.split(separator: ";").map(String.init) }
   else { args[key] = value }
  }
  // Agents must say who they are, so the user sees "ChatGPT is using Still", not a generic name.
  guard let who = args["as"] as? String, !who.isEmpty else { print("Error: say who you are with as=<your name>, for example as=Claude or as=ChatGPT."); return 2 }
  args["as"] = nil
  let reply = jsonObject(call(agentName(who), argv[0], args)) ?? [:]
  guard reply["ok"] as? Bool == true else { print("Error: " + (reply["error"] as? String ?? "Failed.")); return 1 }
  if let data = reply["result"] as? [String: Any], let image = data["image"] as? String, let png = Data(base64Encoded: image) {
   let stamp = DateFormatter()
   stamp.dateFormat = "yyyyMMdd-HHmmss"
   let file = FileManager.default.temporaryDirectory.appendingPathComponent("still-screenshot-\(stamp.string(from: Date())).png")
   do { try png.write(to: file); print(file.path); return 0 } catch { print("Error: " + error.localizedDescription); return 1 }
  }
  print(plainText(reply["result"]))
  return 0
 }
}
