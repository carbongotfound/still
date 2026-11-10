import Foundation

// Work in a folder (Windows: MainWindow.Folder.cs): a companion's folder on the user's Mac, where its AI app (whichever it
// is) lists, reads, creates and edits files with Still's tools. Nothing outside it: no "..", no path out of it, and no
// symbolic link on the way (inside). Replacing a whole file of the user's asks unless the companion is on Keep going;
// deleting one always asks and sends it to the Trash. A file it made in this chat it may replace or delete, and Allow in
// this chat stops the asking.

/// The folder a chat works in, or "" (none, gone, or a private window).
func folderOf(_ chat: AiChat) -> String {
 var isFolder: ObjCBool = false
 guard !chat.ephemeral, let f = companions.first(where: { $0.id == chat.companion })?.folder, f.hasPrefix("/"),
       FileManager.default.fileExists(atPath: f, isDirectory: &isFolder), isFolder.boolValue else { return "" }
 return URL(fileURLWithPath: f).standardizedFileURL.path
}
/// Everyone in the chain (the companion, and whoever it's helping) is on Keep going.
func keepGoing(_ chat: AiChat) -> Bool { exchangeOf(chat).chain.allSatisfy { c in levelOf(companions.first { $0.id == c }).programs == "auto" } }

struct OutOfFolder: Error { let why: String }
/// A path the AI gave (relative, or full and inside), as a full path inside root.
func inside(_ root: String, _ given: String) throws -> String {
 let g = given.trimmingCharacters(in: .whitespacesAndNewlines)
 if g.isEmpty || g == "." || g == "/" { return root }
 if g.split(separator: "/").contains("..") || g.hasPrefix("~") { throw OutOfFolder(why: "Give a path inside the working folder, like notes/todo.md, with no \"..\".") }
 let full = (g.hasPrefix("/") ? URL(fileURLWithPath: g) : URL(fileURLWithPath: root).appendingPathComponent(g)).standardizedFileURL.path
 if full == root { return root }
 guard full.hasPrefix(root + "/") else { throw OutOfFolder(why: "That's outside the working folder.") }
 var at = full
 while at.count > root.count {
  if (try? FileManager.default.destinationOfSymbolicLink(atPath: at)) != nil { throw OutOfFolder(why: String(at.dropFirst(root.count + 1)) + " is a link to somewhere else, so Still keeps you out of it.") }
  at = (at as NSString).deletingLastPathComponent
 }
 return full
}

@MainActor func folderTool(_ who: String, _ tool: String, _ args: [String: Any]) async -> String {
 guard let run = runs[who] else { return agentFail("Only a companion in Still's chat has a working folder.") }
 let root = folderOf(run.chat), fm = FileManager.default
 if root.isEmpty { return agentFail(run.chat.ephemeral ? "Chats in a private window don't work in folders." : "This chat has no working folder. If you need one, ask the user to pick a folder for you.") }
 let path: String
 do { path = try inside(root, argText(args, "path")) } catch { return agentFail((error as? OutOfFolder)?.why ?? "That isn't a path Still can use.") }
 let rel = path == root ? "." : String(path.dropFirst(root.count + 1))
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
