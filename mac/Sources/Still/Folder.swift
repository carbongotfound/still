import AppKit

// Work in a folder (Windows: MainWindow.Folder.cs): a companion's folder on the user's Mac, where its AI app (whichever it
// is) lists, reads, creates and edits files with Still's tools. Nothing outside it: no "..", no path out of it, and no
// symbolic link on the way (inside). Replacing a whole file of the user's asks unless the companion is on Keep going;
// deleting one always asks and sends it to the Trash. A file it made in this chat it may replace or delete, and Allow in
// this chat stops the asking.

/// The folder a chat works in: its own, or else its companion's; "" for none, one that's gone, or a private window.
func folderOf(_ chat: AiChat) -> String {
 var isFolder: ObjCBool = false
 guard !chat.ephemeral, let f = chat.folder ?? companions.first(where: { $0.id == chat.companion })?.folder, f.hasPrefix("/"),
       FileManager.default.fileExists(atPath: f, isDirectory: &isFolder), isFolder.boolValue else { return "" }
 return URL(fileURLWithPath: f).standardizedFileURL.path
}
/// What the AI hears when its folder changed since it was last told (a new session's instructions name it).
func folderNote(_ chat: AiChat, _ work: String) -> String {
 let told = chat.folderTold ?? work
 chat.folderTold = work
 return !chat.started || told == work ? "" : "[Still] " + (work.isEmpty ? "The user took away your working folder, so you can't reach their files now." : "The user changed your working folder to \(work): list_files, read_file, write_file, edit_file and delete_file reach the files there and nothing outside it.") + "\n\n"
}
/// Everyone in the chain (the companion, and whoever it's helping) is on Keep going.
func keepGoing(_ chat: AiChat) -> Bool { exchangeOf(chat).chain.allSatisfy { c in levelOf(companions.first { $0.id == c }).programs == "auto" } }

struct OutOfFolder: Error { let why: String }
/// A path the AI gave (relative, or full and inside), as a full path inside root.
/// aiPicture (Windows: StepPicture): a picture a companion read in a chat, whose step says Read <path>: from the chat's folder,
/// else a file attached in it, as a data: address. Nil for anything else, or a picture that's gone or over 5 MB.
func stepPicture(_ chat: AiChat, _ step: String, attachments: String) -> String? {
 guard step.hasPrefix("Read "), let mime = imageMime(step), chat.messages.contains(where: { $0.role == "tool" && $0.status == nil && $0.text == step }) else { return nil }
 let name = String(step.dropFirst(5)), root = folderOf(chat)
 var path = root.isEmpty ? "" : (try? inside(root, name)) ?? ""
 if !FileManager.default.fileExists(atPath: path), let sent = chat.messages.flatMap({ $0.files ?? [] }).last(where: { $0.name == name }), let file = attachment(sent.id, in: attachments) {
  path = attachments + "/" + file.id + "/" + file.name
 }
 guard let size = (try? FileManager.default.attributesOfItem(atPath: path))?[.size] as? Int, Int64(size) <= maxImage, let bytes = FileManager.default.contents(atPath: path) else { return nil }
 return "data:\(mime);base64," + bytes.base64EncodedString()
}
func inside(_ root: String, _ given: String) throws -> String {
 let g = given.trimmingCharacters(in: .whitespacesAndNewlines)
 if g.isEmpty || g == "." || g == "/" { return root }
 if g.split(separator: "/").contains("..") || g.hasPrefix("~") { throw OutOfFolder(why: "Give a path inside the working folder, like notes/todo.md, with no \"..\".") }
 let full = (g.hasPrefix("/") ? URL(fileURLWithPath: g) : URL(fileURLWithPath: root).appendingPathComponent(g)).standardizedFileURL.path
 if full == root { return root }
 guard full.hasPrefix(root + "/") else { throw OutOfFolder(why: "That's outside the working folder. To look at files elsewhere, ask the user with request_folder.") }
 var at = full
 while at.count > root.count {
  if (try? FileManager.default.destinationOfSymbolicLink(atPath: at)) != nil { throw OutOfFolder(why: String(at.dropFirst(root.count + 1)) + " is a link to somewhere else, so Still keeps you out of it.") }
  at = (at as NSString).deletingLastPathComponent
 }
 return full
}

@MainActor func folderTool(_ who: String, _ tool: String, _ args: [String: Any]) async -> String {
 guard let run = runs[who] else { return agentFail("Only a companion in Still's chat has a working folder.") }
 var root = folderOf(run.chat), path = "", why: String?
 let fm = FileManager.default, given = argText(args, "path")
 if !root.isEmpty { do { path = try inside(root, given) } catch { why = (error as? OutOfFolder)?.why ?? "That isn't a path Still can use." } }
 // A folder the user let it see, by its full path: list_files and read_file there, nothing else.
 var look = false
 if path.isEmpty, let seen = seenFolder(run, given) {
  root = seen; look = true
  do { path = try inside(root, given) } catch { return agentFail((error as? OutOfFolder)?.why ?? "That isn't a path Still can use.") }
 }
 if path.isEmpty { return agentFail(why ?? (run.chat.ephemeral ? "Chats in a private window don't work in folders." : "This chat has no working folder. If the task needs files on the user's computer, ask for the folder with request_folder.")) }
 if look && tool != "list_files" && tool != "read_file" { return agentFail("You can only look in \(root): the user let you see it, not change it. To change files there, ask with request_folder and write: true.") }
 let rel = look ? path : path == root ? "." : String(path.dropFirst(root.count + 1))
 var isFolder: ObjCBool = false
 let exists = fm.fileExists(atPath: path, isDirectory: &isFolder), folder = exists && isFolder.boolValue
 if tool != "list_files" && path == root { return agentFail("Give the path of a file in the working folder, like notes/todo.md.") }
 switch tool {
 case "list_files":
  guard folder, let names = try? fm.contentsOfDirectory(atPath: path) else { return agentFail(rel + " isn't a folder. list_files with no path shows what's in the working folder.") }
  var folders: [String] = [], files: [String] = []
  for name in names.sorted(by: { $0.caseInsensitiveCompare($1) == .orderedAscending }) {
   var d: ObjCBool = false
   _ = fm.fileExists(atPath: path + "/" + name, isDirectory: &d)
   if d.boolValue { folders.append(name + "/"); continue }
   let size = (try? fm.attributesOfItem(atPath: path + "/" + name)[.size] as? Int) ?? 0
   files.append(name + " (" + sizeText(Int64(size)) + ")")
  }
  let all = folders + files
  return agentOk(["folder": rel, "items": Array(all.prefix(500)), "more": all.count > 500 ? all.count - 500 as Any : NSNull()])
 case "read_file":
  guard exists, !folder else { return agentFail(rel + " isn't a file in the working folder. Use list_files to see what's there.") }
  return readPage(URL(fileURLWithPath: path), rel, max(0, (args["offset"] as? NSNumber)?.intValue ?? 0), "Tell the user what you can read.")
 case "write_file":
  let content = argText(args, "content")
  if content.utf8.count > 5_000_000 { return agentFail("That's too big: keep a file under 5 MB.") }
  if folder { return agentFail(rel + " is a folder.") }
  if exists, let no = await mayChange(run, root, path, "Replace " + rel, "It replaces the whole file in your folder " + (root as NSString).lastPathComponent + ".", delete: false) { return no }
  do {
   try fm.createDirectory(atPath: (path as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
   try Data(content.utf8).write(to: URL(fileURLWithPath: path))
  } catch { return agentFail("Couldn't write \(rel): \(error.localizedDescription)") }
  if !exists { run.chat.made.insert(path) }
  return agentOk(["done": (exists ? "Replaced " : "Created ") + rel])
 case "edit_file":
  guard exists, !folder else { return agentFail(rel + " isn't a file in the working folder. Create it with write_file.") }
  guard let data = fm.contents(atPath: path), data.count <= 5_000_000 else { return agentFail(rel + " is over 5 MB, too big to edit here.") }
  if data.contains(0) { return agentFail(rel + " isn't text.") }
  let bom = data.starts(with: [0xEF, 0xBB, 0xBF])
  let text = String(decoding: bom ? data.dropFirst(3) : data, as: UTF8.self)
  var old = argText(args, "old"), put = argText(args, "new")
  if old.isEmpty { return agentFail("Pass old: the exact text to change, as read_file shows it.") }
  if text.range(of: old) == nil, text.range(of: "\r\n") != nil {
   old = old.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\n", with: "\r\n"); put = put.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\n", with: "\r\n")
  }
  let count = text.components(separatedBy: old).count - 1
  if count == 0 { return agentFail("That text isn't in \(rel). Read it again and copy the text exactly.") }
  if count > 1 && args["all"] as? Bool != true { return agentFail("That text is in \(rel) \(count) times. Pass more of the text around it, or all=true to change every one.") }
  do { try ((bom ? Data([0xEF, 0xBB, 0xBF]) : Data()) + Data(text.replacingOccurrences(of: old, with: put).utf8)).write(to: URL(fileURLWithPath: path)) }
  catch { return agentFail("Couldn't write \(rel): \(error.localizedDescription)") }
  return agentOk(["done": "Edited \(rel)" + (count > 1 ? " in \(count) places" : "")])
 case "delete_file":
  if folder { return agentFail(rel + " is a folder. Still deletes files one at a time.") }
  guard exists else { return agentFail(rel + " isn't a file in the working folder.") }
  if let no = await mayChange(run, root, path, "Delete " + rel, "It goes to the Trash.", delete: true) { return no }
  do { try fm.trashItem(at: URL(fileURLWithPath: path), resultingItemURL: nil) } catch { return agentFail("Couldn't delete \(rel). It may be open in another app.") }
  run.chat.made.remove(path)
  return agentOk(["done": "Moved \(rel) to the Trash"])
 default: return agentFail("Still has no tool by that name.")
 }
}

/// The folder the user let this run see (until the reply ends, or for the chat) that holds this full path, if any.
func seenFolder(_ run: ChatRun, _ given: String) -> String? {
 let g = given.trimmingCharacters(in: .whitespacesAndNewlines)
 guard g.hasPrefix("/") else { return nil }
 let full = URL(fileURLWithPath: g).standardizedFileURL.path
 var isFolder: ObjCBool = false
 return (Array(run.seen) + run.chat.allowed.filter { $0.hasPrefix("see ") }.map { String($0.dropFirst(4)) })
  .first { (full == $0 || full.hasPrefix($0 + "/")) && FileManager.default.fileExists(atPath: $0, isDirectory: &isFolder) && isFolder.boolValue }
}
/// request_folder (Windows: RequestFolder): a companion asks to see a folder, or (write) to work in one. A card asks every
/// time, at every level. To see: Allow once (until the reply ends), Allow for this chat, or Not now; list_files and read_file
/// then reach it by full path, read-only. To work in: Allow makes it the chat's folder, Choose another folder lets the user
/// pick one, Not now refuses. Never a folder that holds Still's data or apps' settings and keys (guarded), which the user
/// can still pick themselves.
@MainActor func requestFolder(_ who: String, _ args: [String: Any]) async -> String {
 guard let run = runs[who] else { return agentFail("Only a companion in Still's chat can ask for a working folder.") }
 if run.chat.ephemeral { return agentFail("Chats in a private window don't work in folders.") }
 let given = argText(args, "path").trimmingCharacters(in: .whitespacesAndNewlines), why = clipped(argText(args, "why").trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "\n", with: " "), 200)
 var isFolder: ObjCBool = false
 var path = given.hasPrefix("/") ? URL(fileURLWithPath: given).standardizedFileURL.path : ""
 guard !path.isEmpty, FileManager.default.fileExists(atPath: path, isDirectory: &isFolder), isFolder.boolValue else {
  return agentFail("There's no folder at \(clipped(given, 200)). Pass the full path of a folder that exists, like /Users/you/Photos/frames, or ask the user where it is.")
 }
 if guarded(path) { return agentFail("That folder holds Still's data or apps' settings and keys, so Still won't offer it. Ask for the folder with the user's own files.") }
 let name = (path as NSString).lastPathComponent, work = folderOf(run.chat)
 if !argFlag(args, "write") {
  if !work.isEmpty && (path == work || path.hasPrefix(work + "/")) { return agentOk(["done": path + " is in your working folder: list_files and read_file reach it already."]) }
  if seenFolder(run, path) != nil { return agentOk(["done": "You can look in " + path + " already: list_files and read_file with full paths there."]) }
  let seen = await approve(run, "See " + name, path, "see", why, countdown: false)
  audit(run.chat, "See " + path, name, seen == "once" ? "You allowed it until this reply ends" : seen == "chat" ? "You allowed it for this chat" : seen == "stop" ? "Stopped" : seen == "timeout" ? "No answer in 10 minutes" : "Not now")
  if seen == "chat" { run.chat.allowed.append("see " + path) } else if seen == "once" { run.seen.insert(path) }
  publishAiEverywhere()
  guard seen == "once" || seen == "chat" else {
   return agentFail(seen == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said not now. Carry on without it, or ask them in your reply.")
  }
  return agentOk(["done": "You can look in \(path) \(seen == "chat" ? "for the rest of this chat" : "until you finish this reply"): list_files and read_file with full paths there, like \(path)/notes.txt. It's read-only: to change files there, ask with request_folder and write: true."])
 }
 if path == work { return agentOk(["done": "You already work in " + path]) }
 var answer = await approve(run, "Work in " + name, path, "folder", why, countdown: false)
 if answer == "pick" {
  let picker = NSOpenPanel()
  picker.canChooseDirectories = true; picker.canChooseFiles = false; picker.allowsMultipleSelection = false
  picker.message = "Pick a folder for this chat"; picker.directoryURL = URL(fileURLWithPath: path)
  let picked: URL? = await withCheckedContinuation { done in
   if let window = chatRunner(who)?.window { picker.beginSheetModal(for: window) { done.resume(returning: $0 == .OK ? picker.url : nil) } }
   else { done.resume(returning: picker.runModal() == .OK ? picker.url : nil) }
  }
  if let picked { path = picked.standardizedFileURL.path; answer = "picked" } else { answer = "deny" }
 }
 audit(run.chat, "Work in " + path, name, answer == "once" ? "You allowed it" : answer == "picked" ? "You picked this folder" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "Not now")
 guard answer == "once" || answer == "picked" else {
  publishAiEverywhere()
  return agentFail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said not now. Carry on without the folder, or ask them in your reply.")
 }
 run.chat.folder = path; run.chat.folderTold = path
 saveAiChats(run.chat); publishAiEverywhere()
 return agentOk(["done": "You work in \(path) now" + (answer == "picked" ? ", the folder the user picked" : "") + ": list_files, read_file, write_file, edit_file and delete_file reach the files there and nothing outside it."])
}
/// Still's own data, a folder of apps' settings and keys in the user's folder (Library, .claude, .ssh…), or one holding any.
func guarded(_ path: String) -> Bool {
 func under(_ a: String, _ b: String) -> Bool { a == b || a.hasPrefix(b.hasSuffix("/") ? b : b + "/") }
 let home = URL(fileURLWithPath: NSHomeDirectory()).standardizedFileURL.path, own = [support.path, profileHome.path]
 if (own + [home]).contains(where: { under($0, path) }) || own.contains(where: { under(path, $0) }) { return true } // the folder itself, one it's in, or one in it
 guard under(path, home) else { return false }
 let first = String(path.dropFirst(home.count + 1)).split(separator: "/").first.map(String.init) ?? ""
 return first.hasPrefix(".") || first == "Library"
}

/// Whether a replace or delete goes ahead: a file it made in this chat, Allow in this chat, or (replacing) Keep going say
/// yes; otherwise the user answers in the chat. nil: go ahead; otherwise the refusal for the AI.
@MainActor func mayChange(_ run: ChatRun, _ root: String, _ path: String, _ what: String, _ why: String, delete: Bool) async -> String? {
 let key = "files " + root, site = (root as NSString).lastPathComponent
 if run.chat.made.contains(path) || run.chat.allowed.contains(key) { return nil }
 if !delete && keepGoing(run.chat) { audit(run.chat, what, site, "Done without asking, as Keep going allows"); return nil }
 let answer = await approve(run, what, site, "files", why, countdown: false)
 audit(run.chat, what, site, answer == "chat" ? "You allowed changes in this folder for this chat" : answer == "once" ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no")
 if answer == "chat" { run.chat.allowed.append(key) }
 publishAiEverywhere()
 return answer == "once" || answer == "chat" ? nil : agentFail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't try it again unless they ask.")
}

extension Browser {
 /// chatFolder: a chat's own folder, picked or given ("" with remove: none in it); with no chat, the next new chat's.
 func chatFolder(_ data: [String: Any]) {
  let id = argText(data, "chat"), given = argText(data, "path")
  let chat = id.isEmpty ? nil : myChats.first { $0.id == id }
  if !id.isEmpty && (chat == nil || chat!.ephemeral) { return }
  let set = { [self] (path: String) in
   if let chat { chat.folder = path; saveAiChats() } else { nextFolder = path }
   publishAiEverywhere()
  }
  var isFolder: ObjCBool = false
  if data["remove"] as? Bool == true { set(""); return }
  if given.hasPrefix("/"), FileManager.default.fileExists(atPath: given, isDirectory: &isFolder), isFolder.boolValue { set(given); return }
  let picker = NSOpenPanel()
  picker.canChooseDirectories = true; picker.canChooseFiles = false; picker.allowsMultipleSelection = false
  picker.message = chat == nil ? "Pick a folder for the new chat" : "Pick a folder for this chat"
  picker.beginSheetModal(for: window) { result in if result == .OK, let url = picker.url { set(url.path) } }
 }
}
