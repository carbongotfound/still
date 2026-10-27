// Lets AI agents control Still, like the Windows app: `Still --mcp` is a Model Context Protocol server (JSON-RPC over stdio)
// and `Still --cli <tool> as=<name> key=value ...` makes one call from a terminal. Both relay each call to the running Still
// over a Unix socket only this user can open. Off by default. Every agent must be approved by the user, a bar shows what it
// is doing and can stop it, and agents never see private tabs, saved passwords or cookies. Every call answers within a time
// limit, so an agent can never hang on a slow page, a dialog or a question the user hasn't answered yet.
import AppKit
import Darwin
import WebKit

struct AgentError: LocalizedError {
 let message: String
 init(_ message: String) { self.message = message }
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
struct AgentUpload { let multiple: Bool; let complete: ([URL]?) -> Void }

var approvedAgents = Set<String>(), blockedAgents = Set<String>() // lowercased names
var stoppedAgents: [String: Date] = [:]
var agentName = "", agentAction = "", agentSeen = Date.distantPast
// One question in the agent bar at a time: letting a new agent in, or an upload that needs the user's OK.
var approvalWaiters: [Once<Bool?>]? = nil
var askClient = "", askText = ""
var lastAnswer: (client: String, ask: String, allow: Bool, at: Date)? = nil
// Ends an agent's running call early with this reply: a dialog or file picker opened in its tab, or the user pressed Stop.
var agentInterrupts: [String: Once<String>] = [:]
var agentTabs: [String: String] = [:] // agent name -> the tab it is working in
// The user is away from Still: the agent asks them in its own chat and passes the answer on with this code.
var confirmCodes: [String: (client: String, ask: String, until: Date)] = [:]

// The page scripts come straight from the Windows app (mac/build.sh copies them), so both stay in step.
let agentScripts: [String: String] = {
 var scripts: [String: String] = [:]
 for name in ["Page", "Snapshot", "Find", "Click", "Focus", "Scroll", "Wait", "FileInput"] {
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
func hostName(_ url: String) -> String { URL(string: url)?.host.map { $0.hasPrefix("www.") ? String($0.dropFirst(4)) : $0 } ?? url }

func scriptError(_ code: String, _ reply: [String: Any]) -> String {
 switch code {
 case "gone": return "That element isn't on the page anymore (the page changed or it's a new page). Call read_page or find for current ids."
 case "notfound": return "Couldn't find that element on the page. Call read_page or find."
 case "hidden": return "That element is hidden right now (maybe in a closed menu). Open what contains it first, or call read_page."
 case "covered": return "Something is on top of that element: " + (reply["by"] as? String ?? "") + ". Close or click that first (often a cookie banner or pop-up)."
 case "nofocus": return "No field is focused. Pass the field's id."
 case "nooption": return "That dropdown has no matching option. Options: " + (reply["options"] as? String ?? "")
 case "empty": return "Pass the text to look for."
 default: return "The page's script failed: " + (reply["message"] as? String ?? "")
 }
}

let agentKeys: [String: (code: String, keyCode: Int, text: String)] = [
 "enter": ("Enter", 13, "\r"), "tab": ("Tab", 9, ""), "escape": ("Escape", 27, ""), "esc": ("Escape", 27, ""), "backspace": ("Backspace", 8, ""), "delete": ("Delete", 46, ""),
 "arrowup": ("ArrowUp", 38, ""), "arrowdown": ("ArrowDown", 40, ""), "arrowleft": ("ArrowLeft", 37, ""), "arrowright": ("ArrowRight", 39, ""),
 "home": ("Home", 36, ""), "end": ("End", 35, ""), "pageup": ("PageUp", 33, ""), "pagedown": ("PageDown", 34, ""), "space": ("Space", 32, " ")
]

/// A key like a person presses it, e.g. "Enter", "Escape", "a", "Control+A", "Shift+Tab", for agentKeyScript.
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

// WebKit has no DevTools input events, so the Mac app clicks, types and presses keys with DOM events from the page itself.
// These run after the shared page helpers (agent-Page.js); evaluateJavaScript counts as a user gesture, so pop-ups and file pickers open.
let agentClickTail = #"""
const el = target(o), w = view(el), rect = el.getBoundingClientRect(), cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2, rootNode = el.getRootNode();
let at = typeof rootNode.elementFromPoint === 'function' ? rootNode.elementFromPoint(cx, cy) : null;
if (!at || !(inside(el, at) || inside(at, el) || at.closest('label')?.control === el)) at = el;
const base = { bubbles: true, cancelable: true, composed: true, view: w, clientX: cx, clientY: cy, screenX: cx, screenY: cy, button: 0, detail: 1 };
const fire = (type, buttons) => { const init = Object.assign({}, base, { buttons }); at.dispatchEvent(type.startsWith('pointer') && w.PointerEvent ? new w.PointerEvent(type, Object.assign(init, { pointerId: 1, pointerType: 'mouse', isPrimary: true })) : new w.MouseEvent(type, init)); };
fire('pointerover', 0); fire('mouseover', 0); fire('pointermove', 0); fire('mousemove', 0); fire('pointerdown', 1); fire('mousedown', 1);
const f = at.closest('a[href],button,input,select,textarea,summary,[tabindex],[contenteditable]');
if (f && f !== deepActive() && typeof f.focus === 'function') f.focus({ preventScroll: true });
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
const init = { key: o.key, code: o.code, keyCode: o.keyCode, which: o.keyCode, altKey: o.alt, ctrlKey: o.ctrl, metaKey: o.meta, shiftKey: o.shift, bubbles: true, cancelable: true, composed: true, view: w };
const ev = (type, extra) => { const k = new w.KeyboardEvent(type, Object.assign({}, init, extra)); if (!k.keyCode && o.keyCode) try { Object.defineProperty(k, 'keyCode', { get: () => o.keyCode }); Object.defineProperty(k, 'which', { get: () => o.keyCode }); } catch {} return k; };
const go = e.dispatchEvent(ev('keydown'));
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

let pipScript = #"""
(() => { const v = [...document.querySelectorAll('video')].find(v => v.readyState > 0); if (!v) return 'No playable video found on this page';
 if (document.pictureInPictureElement || v.webkitPresentationMode === 'picture-in-picture') { if (document.pictureInPictureElement && document.exitPictureInPicture) document.exitPictureInPicture(); else v.webkitSetPresentationMode('inline'); return 'closed'; }
 if (v.webkitSupportsPresentationMode && v.webkitSupportsPresentationMode('picture-in-picture')) { v.webkitSetPresentationMode('picture-in-picture'); return 'opened'; }
 if (v.requestPictureInPicture) { v.requestPictureInPicture().catch(() => {}); return 'opened'; }
 return "Floating video isn't available for this player."; })()
"""#

extension Browser {
 // MARK: AI agents

 func startAgentServer() {
  AgentSocket.serve { [weak self] line, reply in
   guard let self else { reply(agentFail("Still is closing.")); return }
   self.handleAgent(line, reply)
  }
 }

 func handleAgent(_ line: String, _ reply: @escaping (String) -> Void) {
  guard let root = jsonObject(line), let tool = root["tool"] as? String else { reply(agentFail("Invalid request.")); return }
  let raw = root["client"] as? String ?? "An AI agent"
  let cleaned = String(raw.filter { ch in !ch.unicodeScalars.contains { $0.value < 32 || ($0.value >= 127 && $0.value < 160) } }.prefix(40))
  let client = cleaned.isEmpty ? "An AI agent" : cleaned, key = client.lowercased()
  let args = root["args"] as? [String: Any] ?? [:]
  guard pref("AgentsEnabled", false) else { reply(agentFail("AI control is turned off. The user can turn it on in Still → Settings → Let other AI apps use Still.")); return }
  if tool == "user_confirmed" { reply(confirmed(client, args)); return }
  // Don't keep the agent waiting on a bar nobody will see: its app can ask the user (elicitation), or the user is away.
  let quick = root["elicit"] as? Bool == true || userAway()
  if blockedAgents.contains(key) { reply(agentFail("The user blocked this agent in Still for this session.")); return }
  if let until = stoppedAgents[key], Date() < until { reply(agentFail("The user pressed Stop. Stop what you are doing and wait for the user's next message.")); return }
  if pref("ApprovedAgents", [String]()).contains(where: { Mcp.agentName($0).lowercased() == key }) { approvedAgents.insert(key) } // approved once = remembered across restarts
  if approvedAgents.contains(key) { startTool(client, tool, args, quick, reply); return }
  askUser(client, "", now: quick) { answer in
   switch answer {
   case .some(true): self.startTool(client, tool, args, quick, reply)
   case .some(false): reply(agentFail("The user blocked this agent in Still for this session."))
   default: reply(self.needsConfirm(client, "", "Waiting for the user to let you in: Still shows a bar with Allow and Block at the top of its window. Tell the user to click Allow, then call the tool again."))
   }
  }
 }

 func startTool(_ client: String, _ tool: String, _ args: [String: Any], _ quick: Bool, _ reply: @escaping (String) -> Void) {
  agentName = client; agentSeen = Date()
  let key = client.lowercased(), call = Once<String>()
  call.action = { [weak self] result in
   if agentInterrupts[key] === call { agentInterrupts[key] = nil }
   reply(result)
   self?.schedulePublish()
   DispatchQueue.main.asyncAfter(deadline: .now() + 121) { self?.schedulePublish() } // the bar goes once the agent is quiet
  }
  agentInterrupts[key] = call
  let limit = tool == "wait_for" ? Int(min(30000, max(100, argNumber(args, "timeoutMs", 10000)))) + 5000 : tool == "upload_file" ? 60000 : 30000
  DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(limit)) {
   call.fire(agentFail("\(tool) didn't finish within \(limit / 1000) s, so Still stopped waiting. The page may be slow or stuck: call read_page to see where it is."))
  }
  runTool(client, tool, args, quick) { call.fire($0) }
 }

 /// Asks the user in the agent bar ("" = may this agent control Still). Nil: no answer yet; the question stays up.
 /// now: don't wait for the answer (the agent asks the user elsewhere, see needsConfirm).
 func askUser(_ client: String, _ ask: String, now: Bool, until: Date? = nil, _ done: @escaping (Bool?) -> Void) {
  if let last = lastAnswer, last.client == client, last.ask == ask, Date().timeIntervalSince(last.at) < 120 { done(last.allow); return } // answered after the agent stopped waiting
  let deadline = until ?? Date().addingTimeInterval(now ? 0 : 45) // shorter than MCP apps' own tool timeouts
  let wait = Once<Bool?>()
  if approvalWaiters != nil && !(askClient == client && askText == ask) {
   if now || Date() >= deadline { done(nil); return }
   wait.action = { [weak self] _ in self?.askUser(client, ask, now: false, until: deadline, done) } // another question is up: ask once it's answered
  } else {
   if approvalWaiters == nil { approvalWaiters = []; askClient = client; askText = ask; schedulePublish() }
   wait.action = done
  }
  approvalWaiters?.append(wait)
  DispatchQueue.main.asyncAfter(deadline: .now() + max(0, deadline.timeIntervalSinceNow)) { wait.fire(nil) }
 }

 func answerAgent(_ allow: Bool) {
  guard let waiters = approvalWaiters else { return }
  settle(askClient, askText, allow)
  approvalWaiters = nil; askClient = ""; askText = ""
  for wait in waiters { wait.fire(allow) }
  schedulePublish()
 }

 func settle(_ client: String, _ ask: String, _ allow: Bool) {
  if ask.isEmpty {
   if !allow { blockedAgents.insert(client.lowercased()) }
   else {
    approvedAgents.insert(client.lowercased())
    var list = pref("ApprovedAgents", [String]())
    if !list.contains(where: { $0.lowercased() == client.lowercased() }) { list.append(client); prefs["ApprovedAgents"] = list; saveLater() }
   }
  }
  lastAnswer = (client: client, ask: ask, allow: allow, at: Date())
  confirmCodes = confirmCodes.filter { !($0.value.client == client && $0.value.ask == ask) } // answered here: a code from the chat no longer counts
 }

 // The user is away from Still: the agent asks them in its own chat instead. MCP apps that support elicitation
 // ask the user themselves (the AI never sees the question); otherwise the AI passes the user's answer on.
 func needsConfirm(_ client: String, _ ask: String, _ waiting: String) -> String {
  guard pref("AgentsAskInChat", true) else { return agentFail(waiting) }
  confirmCodes = confirmCodes.filter { $0.value.until > Date() }
  let code = String((0..<6).map { _ in "0123456789abcdef".randomElement()! })
  confirmCodes[code] = (client: client, ask: ask, until: Date().addingTimeInterval(600))
  let question = ask.isEmpty ? "Allow \(client) to use your Still browser? It can open, read and click pages, but never private tabs, passwords or cookies." : "Allow \(client) to \(ask)?"
  return jsonText(["ok": false, "confirm": ["code": code, "question": question],
                   "error": waiting + " If the user isn't at Still, ask them in your chat instead: \"\(question)\" Then call user_confirmed with code \"\(code)\" and allow true or false, as they answer. Never answer for the user."])
 }

 func confirmed(_ client: String, _ args: [String: Any]) -> String {
  guard let ask = confirmCodes.removeValue(forKey: argText(args, "code").trimmingCharacters(in: .whitespaces).lowercased()),
        ask.client.lowercased() == client.lowercased(), ask.until > Date() else {
   return agentFail("That code isn't valid anymore (the user may have answered in Still). Call the tool again.")
  }
  let allow = argFlag(args, "allow")
  if approvalWaiters != nil && askClient == ask.client && askText == ask.ask { answerAgent(allow) } else { settle(ask.client, ask.ask, allow) }
  toast("\(ask.client) was \(allow ? "allowed" : "turned down") \(ask.ask.isEmpty ? "to use Still" : "to " + ask.ask), answered through its chat.")
  return agentOk(["done": allow ? "The user allowed it. Call the tool again now." : "The user said no. Don't try again unless they ask."])
 }

 /// No keyboard or mouse for a minute, or Still is minimized or hidden: nobody will see the bar.
 func userAway() -> Bool {
  let idle = [CGEventType.mouseMoved, .keyDown, .leftMouseDown, .scrollWheel].map { CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: $0) }.min() ?? 0
  return idle > 60 || window.isMiniaturized || !window.isVisible || NSApp.isHidden
 }

 func agentData() -> [String: Any]? {
  if approvalWaiters != nil { return ["client": askClient, "pending": true, "action": "", "ask": askText] }
  if approvedAgents.contains(agentName.lowercased()) && Date().timeIntervalSince(agentSeen) < 120 { return ["client": agentName, "pending": false, "action": agentAction, "ask": ""] }
  return nil
 }

 // Stop cancels what the agent is doing now; it stays allowed, so its next task needs no new approval.
 func stopAgent() {
  if !agentName.isEmpty {
   releaseAgentTabs(agentName)
   stoppedAgents[agentName.lowercased()] = Date().addingTimeInterval(30)
   agentInterrupts.removeValue(forKey: agentName.lowercased())?.fire(agentFail("The user pressed Stop. Stop what you are doing and wait for the user's next message."))
  }
  for tab in tabs { if let upload = tab.agentUpload { tab.agentUpload = nil; upload.complete(nil) } }
  agentAction = ""; agentSeen = .distantPast
  schedulePublish()
  toast("Stopped " + (agentName.isEmpty ? "the AI agent" : agentName) + ".")
 }

 /// A dialog or file picker opened in the tab an agent is working in: its running call returns now and says so.
 func interruptAgent(_ tab: Tab, _ reply: [String: Any]) {
  guard let who = tab.agent, agentTabs[who] == tab.id, let running = agentInterrupts.removeValue(forKey: who.lowercased()) else { return }
  running.fire(agentOk(reply))
 }

 func claim(_ who: String, _ tab: Tab) {
  agentTabs[who] = tab.id; tab.lastSeen = Date() // in use: memory saver leaves it awake
  if tab.agent != who { tab.agent = who; schedulePublish() }
 }

 /// The agent's work is done: its icon leaves the user's own tabs. Tabs it opened stay in the AI group.
 func releaseAgentTabs(_ name: String) {
  agentTabs[name] = nil
  for tab in tabs where tab.agent == name && !tab.aiGroup { tab.agent = nil }
  schedulePublish()
 }

 /// Opens in the background, next to the other AI tabs, so the user can keep browsing. A configuration means a pop-up WebKit loads itself.
 @discardableResult
 func openAgentTab(_ who: String, _ url: String, configuration: WKWebViewConfiguration? = nil) -> Tab {
  let tab = Tab()
  tab.url = url; tab.title = url.isEmpty ? "New tab" : hostName(url); tab.agent = who; tab.aiGroup = true
  tabs.insert(tab, at: tabs.lastIndex(where: { $0.aiGroup }).map { $0 + 1 } ?? tabs.count)
  let view = createView(tab, configuration: configuration)
  if active == nil || active?.url.isEmpty == true && active?.pinned == false && tabs.count == 2 { select(tab) } // nothing to keep the user on
  claim(who, tab); saveLater(); schedulePublish()
  if configuration == nil, let address = URL(string: url) { load(address, in: view) }
  return tab
 }

 /// A tab the agent may use: never private tabs. Without a tabId it keeps working in the tab it used last.
 func agentTab(_ who: String, _ args: [String: Any]) throws -> Tab {
  var id = argText(args, "tabId")
  if id.isEmpty, let last = agentTabs[who], tabs.contains(where: { $0.id == last }) { id = last }
  guard let tab = id.isEmpty ? active : tabs.first(where: { $0.id == id }) else { throw AgentError(id.isEmpty ? "There is no active tab." : "No tab with that id. Call list_tabs.") }
  if tab.isPrivate { throw AgentError("Private tabs are off-limits to agents.") }
  claim(who, tab)
  return tab
 }

 /// The agent's tab, ready for page work. A page paused on a dialog can't run scripts, so that comes first.
 func agentPage(_ who: String, _ args: [String: Any], _ work: @escaping (Tab, WKWebView) -> Void) throws {
  let tab = try agentTab(who, args)
  if let dialog = tab.dialog { throw AgentError("The page is waiting on a dialog (\(dialog.kind)): \"\(clipped(dialog.message, 200))\". Answer it with handle_dialog first.") }
  if let view = tab.view { work(tab, view); return }
  let view = createView(tab) // a sleeping tab wakes up first
  if !tab.url.isEmpty, let url = URL(string: tab.url) { load(url, in: view) }
  waitLoaded(tab, 15) { work(tab, view) }
 }

 func waitLoaded(_ tab: Tab, _ seconds: Double, _ then: @escaping () -> Void) {
  let until = Date().addingTimeInterval(seconds)
  DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.pollLoaded(tab, until, then) }
 }
 func pollLoaded(_ tab: Tab, _ until: Date, _ then: @escaping () -> Void) {
  if tab.view?.isLoading != true || Date() >= until { then(); return }
  DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { self.pollLoaded(tab, until, then) }
 }

 func webUrl(_ input: String) -> String? {
  let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
  guard !text.isEmpty, let url = URL(string: resolve(text)), let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" else { return nil }
  return url.absoluteString
 }

 /// Runs an agent script in the page, wrapped like the Windows app's: the shared helpers, then the tool's own code.
 func js(_ view: WKWebView, _ body: String, _ o: [String: Any], _ fail: @escaping (String) -> Void, _ ok: @escaping (Any?) -> Void) {
  let source = "((o)=>{try{" + (agentScripts["Page"] ?? "") + body + "}catch(err){return {error:'script',message:String(err&&err.message||err)}}})(" + jsonText(o) + ")"
  view.evaluateJavaScript(source) { result, error in
   if let error { fail(agentFail("The page's script failed: " + error.localizedDescription)); return }
   if let reply = result as? [String: Any], let code = reply["error"] as? String { fail(agentFail(scriptError(code, reply))); return }
   ok(result)
  }
 }

 func did(_ action: String) { agentAction = action.count > 90 ? String(action.prefix(90)) + "…" : action }

 /// What an action led to: where the agent is now, and the new tab it's in if the action opened one.
 func outcome(_ who: String, _ tab: Tab, _ before: String, _ done: String) -> [String: Any] {
  let opened = agentTabs[who].flatMap { id in id != before ? tabs.first(where: { $0.id == id }) : nil }
  let now = opened ?? tab
  var reply: [String: Any] = ["done": done, "url": now.url, "title": now.title]
  if let opened { reply["tabId"] = opened.id; reply["note"] = "This opened a new tab; you're working in it now." }
  return reply
 }

 func runTool(_ who: String, _ tool: String, _ args: [String: Any], _ quick: Bool, _ done: @escaping (String) -> Void) {
  do {
   switch tool {
   case "list_tabs":
    done(agentOk(tabs.filter { !$0.isPrivate }.map { tab -> [String: Any] in
     var item: [String: Any] = ["tabId": tab.id, "title": tab.title, "url": tab.url, "window": 1]
     if tab === active { item["active"] = true }
     if agentTabs[who] == tab.id { item["yours"] = true }
     return item
    }))
   case "open_tab":
    guard let url = webUrl(argText(args, "url")) else { done(agentFail("Agents can only open http and https pages.")); return }
    let tab = openAgentTab(who, url)
    waitLoaded(tab, 15) { self.did("Opened " + hostName(tab.url)); done(agentOk(["tabId": tab.id, "title": tab.title, "url": tab.url])) }
   case "navigate":
    try agentPage(who, args) { tab, view in
     guard let url = self.webUrl(argText(args, "url")), let address = URL(string: url) else { done(agentFail("Agents can only open http and https pages.")); return }
     self.load(address, in: view)
     self.waitLoaded(tab, 15) { self.did("Went to " + hostName(tab.url)); done(agentOk(["tabId": tab.id, "title": tab.title, "url": tab.url])) }
    }
   case "switch_tab":
    let tab = try agentTab(who, args)
    if argFlag(args, "show") { select(tab); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    did("Switched to " + tab.title); done(agentOk(["tabId": tab.id, "title": tab.title, "url": tab.url]))
   case "close_tab":
    let tab = try agentTab(who, args)
    close(tab); agentTabs[who] = nil; did("Closed a tab"); done(agentOk(["done": "Closed the tab"]))
   case "go_back", "go_forward", "reload":
    try agentPage(who, args) { tab, view in
     if tool == "go_back" { guard view.canGoBack else { done(agentFail("There's no earlier page in this tab.")); return }; view.goBack() }
     else if tool == "go_forward" { guard view.canGoForward else { done(agentFail("There's no later page in this tab.")); return }; view.goForward() }
     else { view.reload() }
     self.waitLoaded(tab, 15) { self.did(tool == "reload" ? "Reloaded the page" : tool == "go_back" ? "Went back" : "Went forward"); done(agentOk(["url": tab.url, "title": tab.title])) }
    }
   case "read_page":
    try agentPage(who, args) { tab, view in
     let text = !(args["text"] as? Bool == false || args["text"] as? String == "false")
     self.js(view, agentScripts["Snapshot"] ?? "", ["text": text, "all": argFlag(args, "all"), "offset": Int(min(1e9, max(0, argNumber(args, "offset", 0))))], done) { page in
      self.did("Read " + hostName(tab.url)); done(agentOk(["text": page as? String ?? ""]))
     }
    }
   case "find":
    try agentPage(who, args) { _, view in
     self.js(view, agentScripts["Find"] ?? "", ["text": argText(args, "text")], done) { found in
      self.did("Looked for \"" + argText(args, "text") + "\""); done(agentOk(["text": found as? String ?? ""]))
     }
    }
   case "screenshot":
    try agentPage(who, args) { tab, view in
     // A page only paints while it's on screen: show it for a moment, then give the user their tab back.
     let previous = self.active
     if tab !== previous { self.select(tab) }
     DispatchQueue.main.asyncAfter(deadline: .now() + (tab !== previous ? 0.3 : 0)) {
      view.takeSnapshot(with: nil) { image, error in
       if let previous, previous !== tab, self.active === tab, self.tabs.contains(where: { $0 === previous }) { self.select(previous) }
       guard let image, let tiff = image.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else {
        done(agentFail("Couldn't take the screenshot" + (error.map { ": " + $0.localizedDescription } ?? ".")))
        return
       }
       self.did("Took a screenshot"); done(agentOk(["image": png.base64EncodedString(), "mimeType": "image/png"]))
      }
     }
    }
   case "click":
    try agentPage(who, args) { tab, view in
     let before = agentTabs[who] ?? ""
     tab.agentActedAt = Date() // a pop-up or file picker it opens belongs to the agent
     let script = "const r = (() => {\n" + (agentScripts["Click"] ?? "") + "\n})();\nif (r.error) return r;\n" + agentClickTail
     self.js(view, script, ["id": argId(args), "selector": argText(args, "selector"), "text": argText(args, "text")], done) { hit in
      let label = (hit as? [String: Any])?["label"] as? String ?? ""
      self.waitLoaded(tab, 8) { self.did("Clicked '" + label + "'"); done(agentOk(self.outcome(who, tab, before, "Clicked \"" + label + "\""))) }
     }
    }
   case "type":
    try agentPage(who, args) { tab, view in
     let text = argText(args, "text"), append = argFlag(args, "append"), submit = argFlag(args, "submit"), before = agentTabs[who] ?? ""
     self.js(view, agentScripts["Focus"] ?? "", ["id": argId(args), "selector": argText(args, "selector"), "value": text, "append": append], done) { focused in
      tab.agentActedAt = Date()
      let focus = focused as? [String: Any] ?? [:]
      if let picked = focus["done"] as? String, !picked.isEmpty { self.did(picked); done(agentOk(["done": picked])); return }
      let field = focus["label"] as? String ?? ""
      let verb: String = text.isEmpty ? "Cleared \"" : "Typed into \"", enter: String = submit ? " and pressed Enter" : ""
      let finish: () -> Void = {
       self.waitLoaded(tab, submit ? 8 : 0) {
        self.did("Typed into " + field)
        done(agentOk(self.outcome(who, tab, before, verb + field + "\"" + enter)))
       }
      }
      self.js(view, agentInsertScript, ["text": text, "append": append], done) { _ in
       if submit, let enter = try? keyInfo("Enter") { self.js(view, agentKeyScript, enter, done) { _ in finish() } } else { finish() }
      }
     }
    }
   case "press_key":
    let key = try keyInfo(argText(args, "key"))
    try agentPage(who, args) { tab, view in
     let before = agentTabs[who] ?? ""
     tab.agentActedAt = Date()
     self.js(view, agentKeyScript, key, done) { _ in
      self.waitLoaded(tab, 8) { self.did("Pressed " + argText(args, "key")); done(agentOk(self.outcome(who, tab, before, "Pressed " + argText(args, "key")))) }
     }
    }
   case "scroll":
    try agentPage(who, args) { _, view in
     let o: [String: Any] = ["id": argId(args), "selector": argText(args, "selector"), "direction": argText(args, "direction"), "amount": min(20000, max(0, argNumber(args, "amount", 0)))]
     self.js(view, agentScripts["Scroll"] ?? "", o, done) { scrolled in
      let result = scrolled as? [String: Any] ?? [:], text = result["done"] as? String ?? ""
      var reply: [String: Any] = ["done": text]
      if let at = result["at"] as? String, !at.isEmpty { reply["at"] = at }
      self.did(text); done(agentOk(reply))
     }
    }
   case "wait_for":
    let query: [String: Any] = ["id": argId(args), "selector": argText(args, "selector"), "text": argText(args, "text"), "gone": argFlag(args, "gone")]
    if argId(args).isEmpty && argText(args, "selector").isEmpty && argText(args, "text").isEmpty { done(agentFail("Pass an id, selector or text to wait for.")); return }
    let until = Date().addingTimeInterval(min(30000, max(100, argNumber(args, "timeoutMs", 10000))) / 1000)
    try agentPage(who, args) { tab, view in self.waitFor(tab, view, query, until, done) }
   case "handle_dialog":
    let tab = try agentTab(who, args)
    guard tab.dialog != nil else { done(agentFail("No dialog is open in this tab.")); return }
    let accept = !(args["accept"] as? Bool == false || args["accept"] as? String == "false"), before = agentTabs[who] ?? ""
    answerDialog(tab, accept, args["text"] as? String)
    waitLoaded(tab, 8) { self.did(accept ? "Accepted a dialog" : "Dismissed a dialog"); done(agentOk(self.outcome(who, tab, before, accept ? "Accepted the dialog" : "Dismissed the dialog"))) }
   case "upload_file":
    try agentPage(who, args) { tab, view in self.uploadFiles(who, tab, view, args, quick, done) }
   default: done(agentFail("Unknown tool: " + tool))
   }
  } catch { done(agentFail(error.localizedDescription)) }
 }

 func waitFor(_ tab: Tab, _ view: WKWebView, _ query: [String: Any], _ until: Date, _ done: @escaping (String) -> Void) {
  let gone = query["gone"] as? Bool ?? false
  js(view, agentScripts["Wait"] ?? "", query, done) { found in
   if found as? Bool == true { self.did("Waited for the page"); done(agentOk(["found": !gone, "done": gone ? "It's gone" : "It's there", "url": tab.url] as [String: Any])); return }
   if Date() >= until { done(agentOk(["found": gone, "done": gone ? "Still there after waiting" : "Didn't appear in time", "url": tab.url] as [String: Any])); return }
   DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.waitFor(tab, view, query, until, done) }
  }
 }

 func uploadFiles(_ who: String, _ tab: Tab, _ view: WKWebView, _ args: [String: Any], _ quick: Bool, _ done: @escaping (String) -> Void) {
  var paths: [String] = []
  if let list = args["paths"] as? [Any] { paths = list.map { $0 as? String ?? "" } } else if let one = args["paths"] as? String { paths = [one] }
  var files: [URL] = []
  for path in paths {
   let trimmed = path.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "\""))
   if trimmed.isEmpty { continue }
   let file = URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath).standardizedFileURL
   if !files.contains(file) && files.count < 12 { files.append(file) }
  }
  if files.isEmpty { done(agentFail("Pass paths: the full paths of the files to attach.")); return }
  if let missing = files.first(where: { (try? $0.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile != true }) { done(agentFail("There's no file at " + missing.path)); return }
  let names = files.map { $0.lastPathComponent }.joined(separator: ", "), ask = "upload " + clipped(names, 120) + " to " + hostName(tab.url)
  let query: [String: Any] = ["id": argId(args), "selector": argText(args, "selector")]
  let byId = !argId(args).isEmpty || !argText(args, "selector").isEmpty
  let allowed: () -> Void = {
   self.askUser(who, ask, now: quick) { answer in
    switch answer {
    case .some(true): self.attachFiles(tab, view, files, query, byId, names, done)
    case .some(false): done(agentFail("The user didn't allow this upload. Don't try again unless they ask."))
    default: done(self.needsConfirm(who, ask, "Waiting for the user to allow the upload: Still shows Allow and Block at the top of its window. Tell the user, then call upload_file again."))
    }
   }
  }
  if byId {
   var check = query; check["click"] = false
   js(view, "const pick = (() => {\n" + (agentScripts["FileInput"] ?? "") + "\n})();\n" + agentPickTail, check, done) { found in
    if found as? Bool == true { allowed() } else { done(agentFail("That isn't a file upload field. Click the page's upload button instead, then call upload_file without an id.")) }
   }
  } else if tab.agentUpload != nil { allowed() }
  else { done(agentFail("No file picker is open. Click the page's upload button first (Still catches the picker for you), or pass the id of a file input.")) }
 }

 func attachFiles(_ tab: Tab, _ view: WKWebView, _ files: [URL], _ query: [String: Any], _ byId: Bool, _ names: String, _ done: @escaping (String) -> Void) {
  let finish: () -> Void = { self.did("Attached " + names); done(agentOk(["done": "Attached " + names])) }
  if !byId {
   guard let picker = tab.agentUpload else { done(agentFail("No file picker is open. Click the page's upload button first (Still catches the picker for you), or pass the id of a file input.")); return }
   tab.agentUpload = nil
   picker.complete(picker.multiple ? files : Array(files.prefix(1)))
   finish(); return
  }
  // Click the file input: WebKit asks for files (runOpenPanel), and agentPicker answers with these.
  if let picker = tab.agentUpload { tab.agentUpload = nil; picker.complete(nil) }
  tab.uploadFiles = files; tab.agentActedAt = Date()
  var pick = query; pick["click"] = true
  js(view, "const pick = (() => {\n" + (agentScripts["FileInput"] ?? "") + "\n})();\n" + agentPickTail, pick, done) { _ in self.awaitPicker(tab, Date().addingTimeInterval(3), finish, done) }
 }

 func awaitPicker(_ tab: Tab, _ until: Date, _ finish: @escaping () -> Void, _ done: @escaping (String) -> Void) {
  if tab.uploadFiles == nil { finish(); return }
  if Date() >= until { tab.uploadFiles = nil; done(agentFail("That isn't a file upload field. Click the page's upload button instead, then call upload_file without an id.")); return }
  DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { self.awaitPicker(tab, until, finish, done) }
 }

 /// The page wants files. An agent's upload_file answers it, or, when an agent's click opened it, upload_file will:
 /// nothing pops up, and the agent's running call says a file picker opened.
 func agentPicker(_ tab: Tab, _ multiple: Bool, _ complete: @escaping ([URL]?) -> Void) -> Bool {
  if let files = tab.uploadFiles { tab.uploadFiles = nil; complete(multiple ? files : Array(files.prefix(1))); return true }
  guard tab.agent != nil, Date().timeIntervalSince(tab.agentActedAt) < 10 else { return false }
  if let old = tab.agentUpload { tab.agentUpload = nil; old.complete(nil) }
  tab.agentUpload = AgentUpload(multiple: multiple, complete: complete)
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
}

/// The Unix socket the running Still listens on for agent calls. Only this user can open it.
enum AgentSocket {
 static var path: String { support.appendingPathComponent("agent.sock").path }

 static func address() -> sockaddr_un? {
  var addr = sockaddr_un()
  let bytes = Array(path.utf8)
  guard bytes.count < MemoryLayout.size(ofValue: addr.sun_path) else { return nil }
  addr.sun_family = sa_family_t(AF_UNIX)
  addr.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
  withUnsafeMutableBytes(of: &addr.sun_path) { raw in for (index, byte) in bytes.enumerated() { raw[index] = byte } }
  return addr
 }

 static func dial() -> Int32? {
  guard var addr = address() else { return nil }
  let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
  if fd < 0 { return nil }
  let result = withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
  if result != 0 { _ = Darwin.close(fd); return nil }
  var on: Int32 = 1
  _ = Darwin.setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
  return fd
 }

 /// Any number of agents at once: each connection gets its own thread, and calls run side by side on the main thread.
 static func serve(_ handle: @escaping (String, @escaping (String) -> Void) -> Void) {
  if let other = dial() { _ = Darwin.close(other); NSLog("Still: another copy is already serving AI agents"); return }
  _ = Darwin.unlink(path) // left behind by a Still that quit or crashed
  guard var addr = address() else { return }
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
enum Mcp {
 struct Tool { let name: String, description: String, props: [(String, [String: Any])], required: [String] }
 static func tool(_ name: String, _ description: String, _ props: [(String, [String: Any])], _ required: [String]) -> Tool { Tool(name: name, description: description, props: props, required: required) }
 static func str(_ name: String, _ description: String) -> (String, [String: Any]) { (name, ["type": "string", "description": description]) }
 static func bool(_ name: String, _ description: String) -> (String, [String: Any]) { (name, ["type": "boolean", "description": description]) }
 static func num(_ name: String, _ description: String) -> (String, [String: Any]) { (name, ["type": "number", "description": description]) }
 static let tabId = str("tabId", "Tab id (optional)")
 static let tools: [Tool] = [
  tool("list_tabs", "List the open tabs (never private ones) with their tabIds. `yours` marks the tab you're working in.", [], []),
  tool("open_tab", "Open a URL or search terms in a new background tab and work there from now on. The user keeps their own tab and can keep browsing. Start most tasks here.", [str("url", "URL or search terms")], ["url"]),
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
  tool("press_key", "Press a key in the page: Enter, Escape, Tab, ArrowDown, PageDown, Backspace, a letter, or a combination like Control+A or Shift+Tab.", [str("key", "Key or combination"), tabId], ["key"]),
  tool("scroll", "Scroll down or up (the page, or the scrolling panel in the middle of the view), or bring element id into view.",
       [("direction", ["type": "string", "enum": ["down", "up"]] as [String: Any]), num("amount", "Pixels (default: most of a screen)"), str("id", "Element id: scroll it into view, or with direction, scroll the panel it's in"), tabId], []),
  tool("wait_for", "Wait until an element or some text appears (or, with gone=true, disappears), for up to timeoutMs.",
       [str("text", "Text to wait for"), str("id", "Or: element id"), str("selector", "Or: CSS selector"), bool("gone", "Wait for it to disappear instead"), num("timeoutMs", "Up to 30000 (default 10000)"), tabId], []),
  tool("handle_dialog", "Answer the alert, confirm, prompt or \"leave page?\" dialog the page is paused on (other tools tell you when one opens).",
       [bool("accept", "true = OK / Leave, false = Cancel / Stay (default true)"), str("text", "For a prompt: the text to answer with"), tabId], []),
  tool("upload_file", "Attach files to the file picker the page just opened (click its upload button first), or to a file input by id. Still asks the user to allow it.",
       [("paths", ["type": "array", "items": ["type": "string"], "description": "Full paths of the files on this computer"] as [String: Any]), str("id", "Element id of a file input (optional)"), tabId], ["paths"]),
  tool("user_confirmed", "Only when Still told you to check with the user: after asking them in your chat, pass the code and their answer. Never answer for the user.", [str("code", "The code Still gave you"), bool("allow", "true if the user said yes")], ["code"]),
  tool("screenshot", "PNG of the visible part of a tab. Costs far more tokens than read_page or find: use it only when how the page looks matters.", [tabId], [])
 ]
 static let instructions: String = "You're driving the user's own Still browser, signed in as them. "
  + "Work in background tabs: open_tab for new work, so the user can keep browsing. "
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
  for (key, name) in [("claude", "Claude"), ("codex", "Codex"), ("openai", "Codex"), ("grok", "Grok"), ("gemini", "Gemini"), ("cursor", "Cursor"), ("copilot", "Copilot"), ("windsurf", "Windsurf")] where lowered.contains(key) { return name }
  return client
 }

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
  var client = "An AI agent", canElicit = false
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
    client = agentName((params["clientInfo"] as? [String: Any])?["name"] as? String ?? client)
    canElicit = (params["capabilities"] as? [String: Any])?["elicitation"] != nil
    let result: [String: Any] = ["protocolVersion": params["protocolVersion"] as? String ?? "2025-06-18", "capabilities": ["tools": [String: Any]()],
                                 "serverInfo": ["name": "still", "version": version], "instructions": instructions]
    send(["jsonrpc": "2.0", "id": id, "result": result])
   case "ping": send(["jsonrpc": "2.0", "id": id, "result": [String: Any]()])
   case "tools/list":
    let list = tools.map { schema($0) }
    send(["jsonrpc": "2.0", "id": id, "result": ["tools": list]])
   case "tools/call":
    // Calls run side by side, so one slow page never holds up the next request, and the app can cancel any of them.
    let name = params["name"] as? String ?? "", args = params["arguments"] as? [String: Any] ?? [:]
    let who = client, ask = canElicit, key = idKey(id)
    DispatchQueue.global().async { Mcp.callTool(id, key, who, name, args, ask) }
   default:
    let error: [String: Any] = ["code": -32601, "message": "Method not found: " + method]
    send(["jsonrpc": "2.0", "id": id, "error": error])
   }
  }
 }

 static func callTool(_ id: Any, _ key: String, _ who: String, _ name: String, _ args: [String: Any], _ canElicit: Bool) {
  let cancelled: () -> Bool = { Mcp.locked { Mcp.cancelledIds.contains(key) } }
  var reply = call(who, name, args, elicit: canElicit, cancelled: cancelled)
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

 /// Sends one tool call to the running Still and returns its JSON reply. One connection per call: calls never queue
 /// behind each other, and a cancelled call just hangs up.
 static func call(_ client: String, _ tool: String, _ args: [String: Any], elicit: Bool = false, cancelled: @escaping () -> Bool = { false }) -> String {
  let notRunning = "Still isn't running. Open it and turn on Settings → Let AI agents control Still, then try again."
  guard let fd = AgentSocket.dial() else { return agentFail(notRunning) }
  defer { _ = Darwin.close(fd) }
  var timeout = timeval(tv_sec: 1, tv_usec: 0) // wake up every second to check for a cancel
  _ = Darwin.setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
  guard AgentSocket.writeLine(fd, jsonText(["client": client, "tool": tool, "args": args, "elicit": elicit])) else { return agentFail(notRunning) }
  // Still answers every call within its own time limit; this only covers a Still that froze.
  let deadline = Date().addingTimeInterval(120)
  var buffer = Data()
  if let line = AgentSocket.receiveLine(fd, &buffer, keepWaiting: { !cancelled() && Date() < deadline }) { return line }
  return Date() >= deadline ? agentFail("Still didn't answer in time. It may be busy; try again, or ask the user to check Still.") : agentFail(notRunning)
 }

 /// A page read comes back as plain text (no JSON escaping, fewer tokens); other results as compact JSON.
 static func toolResult(_ reply: String) -> [String: Any] {
  let result = jsonObject(reply) ?? [:]
  guard result["ok"] as? Bool == true else { return ["content": [["type": "text", "text": result["error"] as? String ?? "Failed."]], "isError": true] }
  if let data = result["result"] as? [String: Any], let image = data["image"] as? String { return ["content": [["type": "image", "data": image, "mimeType": "image/png"]]] }
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
   for tool in tools { print("  \(tool.name) " + tool.props.map { $0.0 + "=" }.joined(separator: " ") + "\n      " + tool.description) }
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
  // Agents must say who they are, so the user sees "Codex is using Still", not a generic name.
  guard let who = args["as"] as? String, !who.isEmpty else { print("Error: say who you are with as=<your name>, for example as=Claude or as=Codex."); return 2 }
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
