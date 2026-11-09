// Skills and plugins from GitHub or npm (Windows: MainWindow.SkillImport.cs). Still reads the SKILL.md files in a repository
// or package and shows them before adding any. A plugin (a folder with .claude-plugin/plugin.json), or a skill whose folder
// has a program in it (.py, .js, .sh), also brings that folder's files into the profile's plugins folder, and companions
// with its skills run those programs with run_plugin_program: only files inside it, through their interpreter, with the
// arguments as given and never a shell. It asks first unless the user set Plugin programs to Don't ask or allowed that
// plugin, and setup always asks. Never an MCP server or a hook. An added skill keeps where it came from (source), and a
// chat that uses one or reads a program's output counts as having read from the web, so a new site asks the way it does
// after reading a page (reach).
import Foundation

/// What the last look found, held so Add saves exactly what the user saw.
var skillImport: (source: String, skills: [(name: String, description: String, body: String, pack: SkillPack?)])?
/// The files a plugin brings: its name, its folder in the repository ("" = the top) and each file's path from the top.
final class SkillPack {
 let name: String, root: String, files: [String], address: (String) -> String
 init(_ name: String, _ root: String, _ files: [String], _ address: @escaping (String) -> String) { self.name = name; self.root = root; self.files = files; self.address = address }
}
let skillFileMax = 100_000, skillImportMax = 20, packFilesMax = 300, packFileMax = 5_000_000, packBytesMax = 25_000_000
var pluginsFolder: URL { support.appendingPathComponent("plugins") }
func isProgram(_ path: String) -> Bool { ["py", "js", "mjs", "cjs", "sh"].contains((path as NSString).pathExtension.lowercased()) }
let skillSession: URLSession = {
 let config = URLSessionConfiguration.ephemeral
 config.httpCookieStorage = nil; config.httpShouldSetCookies = false; config.urlCache = nil; config.timeoutIntervalForRequest = 30
 return URLSession(configuration: config)
}()
struct SkillImportError: Error { let message: String }
typealias FoundSkill = (name: String, description: String, body: String, notes: [String], added: Bool, pack: SkillPack?)

/// The pattern's first match in the text, as its groups ("" for one that took no part), or nil.
func regexMatch(_ pattern: String, _ text: String) -> [String]? {
 guard let re = try? NSRegularExpression(pattern: pattern), let m = re.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return nil }
 return (0..<m.numberOfRanges).map { Range(m.range(at: $0), in: text).map { String(text[$0]) } ?? "" }
}

@MainActor func skillImportFind(_ link: String) async throws -> (source: String, found: [FoundSkill]) {
 var files: [(path: String, size: Int)] = [], source = "", name = "", prefix = ""
 var address: (String) -> String = { $0 }
 func escaped(_ path: String) -> String { path.split(separator: "/", omittingEmptySubsequences: false).map { $0.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-._~"))) ?? "" }.joined(separator: "/") }
 if let gh = regexMatch(#"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})(?:/(?:tree|blob)/([A-Za-z0-9._-]{1,100})((?:/[A-Za-z0-9._-]{1,100}){0,12}))?/*$"#, link) {
  let owner = gh[1], repo = gh[2].lowercased().hasSuffix(".git") ? String(gh[2].dropLast(4)) : gh[2], at = gh[3].isEmpty ? "HEAD" : gh[3]
  prefix = gh[4].trimmingCharacters(in: CharacterSet(charactersIn: "/"))
  if prefix.split(separator: "/").contains(where: { $0 == "." || $0 == ".." }) || at == "." || at == ".." { throw SkillImportError(message: "That link doesn't look right.") }
  if (prefix as NSString).lastPathComponent.lowercased() == "skill.md" { prefix = (prefix as NSString).deletingLastPathComponent }
  guard let tree = try await skillGet("https://api.github.com/repos/\(owner)/\(repo)/git/trees/\(at)?recursive=1", 8_000_000) else {
   throw SkillImportError(message: "Couldn't find that on GitHub. It may be private, or the link may be wrong.")
  }
  files = ((jsonObject(tree)?["tree"] as? [[String: Any]]) ?? []).filter { $0["type"] as? String == "blob" }.map { ($0["path"] as? String ?? "", ($0["size"] as? NSNumber)?.intValue ?? 0) }
  source = "github.com/\(owner)/\(repo)" + (prefix.isEmpty ? "" : "/" + prefix); name = repo
  address = { "https://raw.githubusercontent.com/\(owner)/\(repo)/\(at)/\(escaped($0))" }
 } else if let npm = regexMatch(#"^(?:(?:https?://)?(?:www\.)?npmjs\.com/package/|npm:\s*|npm\s+(?:i|install)\s+)((?:@[a-z0-9][a-z0-9._~-]{0,100}/)?[a-z0-9][a-z0-9._~-]{0,100})(?:(?:/v/|@)([0-9A-Za-z.+-]{1,60}))?/*$"#, link) {
  let package = npm[1]
  var version = npm[2]
  if version.isEmpty {
   guard let resolved = try await skillGet("https://data.jsdelivr.com/v1/packages/npm/\(package)/resolved", 100_000) else { throw SkillImportError(message: "Couldn't find that package on npm.") }
   version = jsonObject(resolved)?["version"] as? String ?? ""
   if regexMatch(#"^[0-9A-Za-z.+-]{1,60}$"#, version) == nil { throw SkillImportError(message: "Couldn't find that package on npm.") }
  }
  guard let list = try await skillGet("https://data.jsdelivr.com/v1/packages/npm/\(package)@\(version)?structure=flat", 8_000_000) else { throw SkillImportError(message: "Couldn't find that version on npm.") }
  files = ((jsonObject(list)?["files"] as? [[String: Any]]) ?? []).map { (String(($0["name"] as? String ?? "").drop { $0 == "/" }), ($0["size"] as? NSNumber)?.intValue ?? 0) }
  source = "npm: \(package)@\(version)"; name = package.split(separator: "/").last.map(String.init) ?? package
  let at = version
  address = { "https://cdn.jsdelivr.net/npm/\(package)@\(at)/\(escaped($0))" }
 } else {
  throw SkillImportError(message: "Paste a GitHub link (github.com/owner/repo) or an npm package (npmjs.com/package/name, or npm:name).")
 }

 let under = prefix.isEmpty ? "" : prefix + "/"
 let skillFiles = files.filter { $0.path.hasPrefix(under) && !$0.path.contains("node_modules/") && ($0.path as NSString).lastPathComponent.lowercased() == "skill.md" }
  .sorted { ($0.path.filter { $0 == "/" }.count, $0.path) < ($1.path.filter { $0 == "/" }.count, $1.path) }.prefix(skillImportMax)
 if skillFiles.isEmpty { throw SkillImportError(message: "No skills there. Still looks for SKILL.md files, the way Claude Code and other AI apps keep skills.") }
 // A plugin brings its whole folder. Otherwise a skill brings its own folder when there's a program in it.
 let plugin = files.contains { $0.path == under + ".claude-plugin/plugin.json" }
 var pluginName = name
 if plugin, let manifest = try await skillGet(address(under + ".claude-plugin/plugin.json"), 100_000), let named = jsonObject(manifest)?["name"] as? String, !named.isEmpty { pluginName = named }
 var packs: [String: (pack: SkillPack?, note: String?)] = [:]
 func packOf(_ root: String, _ title: String) -> (pack: SkillPack?, note: String?) {
  if let known = packs[root] { return known }
  let inRoot = root.isEmpty ? "" : root + "/"
  let inside = files.filter { $0.path.hasPrefix(inRoot) && !$0.path.split(separator: "/").contains { $0 == ".git" || $0 == "node_modules" } }
  let programs = inside.filter { isProgram($0.path) }.map { ($0.path as NSString).lastPathComponent }
  let made: (pack: SkillPack?, note: String?) = programs.isEmpty ? (nil, nil)
   : inside.count > packFilesMax || inside.reduce(0, { $0 + $1.size }) > packBytesMax || inside.contains(where: { $0.size > packFileMax }) ? (nil, "Its programs are too big to bring (over 300 files or 25 MB), so only its text comes over.")
   : (SkillPack(title, root, inside.map { $0.path }, address), "It comes with \(programs.count) program\(programs.count == 1 ? "" : "s") (\(programs.prefix(3).joined(separator: ", "))\(programs.count > 3 ? "…" : "")) that companions can run on your computer. Add it only if you trust where it's from.")
  packs[root] = made
  return made
 }
 var found: [FoundSkill] = []
 for f in skillFiles where f.size <= skillFileMax {
  guard let text = try await skillGet(address(f.path), skillFileMax) else { continue }
  let (head, body) = skillHead(text)
  if body.isEmpty { continue }
  let folder = (f.path as NSString).deletingLastPathComponent
  let title = String((head["name"].flatMap { $0.isEmpty ? nil : $0 } ?? (folder.isEmpty ? name : (folder as NSString).lastPathComponent)).prefix(60))
  var notes: [String] = []
  let (pack, packNote) = packOf(plugin ? String(under.dropLast()) : folder, plugin ? pluginName : title)
  if let packNote { notes.append(packNote) }
  if pack == nil && (regexMatch(#"(?im)^\s*(?:```|~~~)\s*(?:bash|sh|shell|zsh|console|powershell|pwsh|ps1|cmd|bat)\b"#, body) != nil || regexMatch(#"(?i)\b(?:bash|shell|powershell|terminal)\b"#, head["allowed-tools"] ?? "") != nil) {
   notes.append("It runs commands on your computer, which Still's companions can't do, so parts of it may not work here.")
  }
  let more = folder.isEmpty ? 0 : files.filter { $0.path.hasPrefix(folder + "/") }.count - 1
  if pack == nil && more > 0 { notes.append("Its folder has \(more) more file\(more == 1 ? "" : "s") (notes or data) that Still doesn't bring.") }
  if body.count > 20000 { notes.append("It's long: Still keeps the first 20,000 characters.") }
  let added = Skill.all.contains { $0.source == source && $0.name.lowercased() == title.lowercased() }
  if added { notes.append("Already added from here.") }
  found.append((title, head["description"] ?? "", body, notes, added, pack))
 }
 if found.isEmpty { throw SkillImportError(message: "Couldn't read the skills there. Try again in a bit.") }
 return (source, found)
}

/// An imported SKILL.md's front matter, read the way such files write it: quoted values, and a value continued on the
/// lines under it ("description: >"). Still's own skills keep one plain line each (frontMatter).
func skillHead(_ raw: String) -> (head: [String: String], body: String) {
 let body = frontMatter(raw).body
 let text = raw.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
 var head: [String: String] = [:], key: String?
 guard text.hasPrefix("---\n"), let end = text.range(of: "\n---", range: text.index(text.startIndex, offsetBy: 4)..<text.endIndex) else { return (head, body) }
 for line in text[text.index(text.startIndex, offsetBy: 4)..<end.lowerBound].split(separator: "\n", omittingEmptySubsequences: false) {
  if let k = key, line.first?.isWhitespace == true { head[k] = tidy((head[k] ?? "") + " " + tidy(line)); continue }
  key = nil
  guard let at = line.firstIndex(of: ":"), at > line.startIndex else { continue }
  let k = tidy(line[..<at]).lowercased()
  var v = tidy(line[line.index(after: at)...])
  if v.count >= 2, let f = v.first, let l = v.last, (f == "\"" && l == "\"") || (f == "'" && l == "'") { v = String(v.dropFirst().dropLast()) }
  if [">", "|", ">-", "|-", ">+", "|+"].contains(v) { v = "" }
  head[k] = v
  if v.isEmpty { key = k } // the value is on the lines under it
 }
 return (head, body)
}

/// A GET with a size cap, https only. Test builds send it to their own server (STILL_QA_SKILL_HUB) instead of the real sites.
func skillGet(_ address: String, _ max: Int) async throws -> String? { try await skillGetData(address, max).map { String(decoding: $0, as: UTF8.self) } }
func skillGetData(_ address: String, _ max: Int) async throws -> Data? {
 var address = address
 if let hub = qaEnv("STILL_QA_SKILL_HUB"), !hub.isEmpty { address = hub.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/" + address.dropFirst("https://".count) }
 guard let url = URL(string: address) else { return nil }
 var request = URLRequest(url: url)
 request.setValue("Still", forHTTPHeaderField: "User-Agent")
 let (bytes, response) = try await skillSession.bytes(for: request)
 let status = (response as? HTTPURLResponse)?.statusCode ?? 0
 if status == 403 || status == 429 { throw SkillImportError(message: (address.contains("github") ? "GitHub" : "npm") + " is limiting requests right now. Try again in an hour.") }
 guard (200..<300).contains(status), response.expectedContentLength <= Int64(max), isQa || response.url?.scheme == "https" else { return nil }
 var data = Data()
 for try await byte in bytes { data.append(byte); if data.count > max { return nil } }
 return data
}

/// Brings a plugin's files into a new folder of its own under the profile's plugins folder (all of them or none), each
/// path checked to stay inside it, and returns the folder's name: the plugin's id.
func packPlace(_ pack: SkillPack) async throws -> String {
 let files = FileManager.default
 var slug = pack.name.lowercased().replacingOccurrences(of: "[^a-z0-9]+", with: "-", options: .regularExpression).trimmingCharacters(in: CharacterSet(charactersIn: "-"))
 if slug.count > 40 { slug = String(slug.prefix(40)).trimmingCharacters(in: CharacterSet(charactersIn: "-")) }
 if slug.isEmpty { slug = "plugin" }
 var id = slug, n = 2
 while files.fileExists(atPath: pluginsFolder.appendingPathComponent(id).path) { id = slug + "-\(n)"; n += 1 }
 let root = pluginsFolder.appendingPathComponent(id), part = pluginsFolder.appendingPathComponent(id + ".part"), inRoot = pack.root.isEmpty ? "" : pack.root + "/"
 try? files.removeItem(at: part)
 try files.createDirectory(at: part, withIntermediateDirectories: true)
 do {
  for path in pack.files {
   let rel = String(path.dropFirst(inRoot.count))
   if rel.split(separator: "/", omittingEmptySubsequences: false).contains(where: { $0.isEmpty || $0 == "." || $0 == ".." || $0.contains(":") || $0.contains("\\") }) { continue }
   let to = part.appendingPathComponent(rel).standardizedFileURL
   guard to.path.hasPrefix(part.standardizedFileURL.path + "/") else { continue } // a name that would leave the folder
   guard let data = try await skillGetData(pack.address(path), packFileMax) else { throw SkillImportError(message: "Couldn't bring the plugin's files. Try again in a bit.") }
   try files.createDirectory(at: to.deletingLastPathComponent(), withIntermediateDirectories: true)
   try data.write(to: to)
  }
  try files.moveItem(at: part, to: root)
 } catch { try? files.removeItem(at: part); throw error }
 return id
}

/// A plugin's programs as a companion names them: paths inside its folder, without the folders its setup fills.
func pluginPrograms(_ id: String) -> [String] {
 let root = pluginsFolder.appendingPathComponent(id)
 guard let walk = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey]) else { return [] }
 var list: [String] = []
 for case let url as URL in walk {
  let name = url.lastPathComponent
  if name.hasPrefix(".") || ["node_modules", "__pycache__", "venv", "site-packages"].contains(name) { walk.skipDescendants(); continue }
  if isProgram(name), (try? url.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true { list.append(url.pathComponents.dropFirst(root.pathComponents.count).joined(separator: "/")) }
 }
 return Array(list.sorted().prefix(40))
}

extension Browser {
 func skillImportLook(_ link: String) async {
  skillImport = nil
  let link = tidy(String(tidy(link).split(whereSeparator: { $0 == "?" || $0 == "#" }).first ?? ""))
  do {
   let (source, found) = try await skillImportFind(link)
   skillImport = (source, found.map { ($0.name, $0.description, $0.body, $0.pack) })
   send(["kind": "skillImport", "source": source, "skills": found.enumerated().map { ["key": $0.offset, "name": $0.element.name, "description": $0.element.description, "body": $0.element.body, "notes": $0.element.notes, "added": $0.element.added] as [String: Any] }])
  } catch let e as SkillImportError { send(["kind": "skillImport", "error": e.message]) }
  catch { NSLog("Still: skill import: \(error)"); send(["kind": "skillImport", "error": "Couldn't reach it. Check your connection and the link, then try again."]) }
 }

 func skillImportAdd(_ keys: [Any]) async {
  guard let pending = skillImport else { return }
  skillImport = nil // once: a second Add while the files come does nothing
  var added = 0, seen = Set<Int>(), placed: [ObjectIdentifier: String] = [:]
  do {
   for case let n as NSNumber in keys where pending.skills.indices.contains(n.intValue) && seen.insert(n.intValue).inserted {
    let k = pending.skills[n.intValue]
    var plugin = ""
    if let pack = k.pack {
     if let known = placed[ObjectIdentifier(pack)] { plugin = known } else { plugin = try await packPlace(pack); placed[ObjectIdentifier(pack)] = plugin }
    }
    _ = try Skill.save("", k.name, k.description, "", k.body, source: pending.source, plugin: plugin)
    added += 1
   }
  } catch let e as SkillImportError { toast(e.message) }
  catch { NSLog("Still: skill import: \(error)"); toast("Couldn't add those skills.") }
  if added > 0 { toast(added == 1 ? "Added 1 skill. Give it to a companion to use it." : "Added \(added) skills. Give them to a companion to use them.") }
  publishAiEverywhere()
 }

 /// A plugin goes with its last skill: its folder, and the user's Always for it.
 func pluginRemove(_ id: String) {
  guard regexMatch("^[a-z0-9-]{1,48}$", id) != nil else { return }
  try? FileManager.default.removeItem(at: pluginsFolder.appendingPathComponent(id))
  let allowed = pref("PluginsAllowed", [String]())
  if allowed.contains(id) { prefs["PluginsAllowed"] = allowed.filter { $0 != id }; saveLater() }
 }

 /// run_plugin_program: a program inside one of the companion's plugins, through its interpreter, with the arguments as
 /// given (never a shell), in the companion's working folder or else the plugin's. It asks first unless Plugin programs
 /// is Don't ask or the user allowed this plugin; setup and install programs always ask. Stopping the chat stops it.
 @MainActor func pluginProgram(_ who: String, _ args: [String: Any]) async -> String {
  guard let run = runs[who], let mine = companions.first(where: { $0.id == run.chat.companion }) else { return agentFail("Only a companion in Still's chat can run its plugins' programs.") }
  if run.chat.ephemeral { return agentFail("Plugin programs don't run in a private window.") }
  let id = tidy(args["plugin"] as? String ?? ""), root = pluginsFolder.appendingPathComponent(id).standardizedFileURL
  guard regexMatch("^[a-z0-9-]{1,48}$", id) != nil, let skill = Skill.all.first(where: { $0.plugin == id && mine.skills.contains($0.id) }), FileManager.default.fileExists(atPath: root.path) else {
   return agentFail("You don't have a plugin \"\(id)\". Use the plugin id load_skill gave you.")
  }
  let named = tidy(args["program"] as? String ?? "").replacingOccurrences(of: "\\", with: "/").replacingOccurrences(of: #"^(?:\$\{?CLAUDE_PLUGIN_ROOT\}?|\.)/"#, with: "", options: .regularExpression)
  let full = root.appendingPathComponent(named).standardizedFileURL
  var folder: ObjCBool = false
  guard full.path.hasPrefix(root.path + "/"), FileManager.default.fileExists(atPath: full.path, isDirectory: &folder), !folder.boolValue, isProgram(full.path) else {
   return agentFail("That isn't one of its programs. Its programs: " + pluginPrograms(id).joined(separator: ", ") + ".")
  }
  let rel = full.pathComponents.dropFirst(root.pathComponents.count).joined(separator: "/"), ext = full.pathExtension.lowercased()
  let tool = ext == "py" ? "python3" : ext == "sh" ? "/bin/bash" : "node"
  guard let exe = findCli(tool) else { return agentFail("Couldn't start \(tool): it isn't installed on this computer, or isn't on its PATH. Tell the user.") }
  let given = (args["args"] as? [Any] ?? []).map { ($0 as? String) ?? "\($0)" }
  if given.count > 40 || given.contains(where: { $0.count > 4000 }) { return agentFail("Too many or too long arguments: 40 at most, 4,000 characters each.") }
  let setup = regexMatch("(?i)setup|install", full.deletingPathExtension().lastPathComponent) != nil
  let shown = given.joined(separator: " "), what = "Run " + rel + (given.isEmpty ? "" : " " + (shown.count > 80 ? String(shown.prefix(79)) + "…" : shown))
  if setup || pref("PluginPrograms", "ask") != "auto" && !pref("PluginsAllowed", [String]()).contains(id) {
   let answer = await approve(run, what, skill.source, setup ? "plugin" : "program",
    setup ? "Setup can install other programs on your computer. It runs at your own risk." : "A program from a plugin you added. It runs on your computer with your access.", countdown: false)
   audit(run.chat, what, skill.source, answer == "always" ? "You allowed this plugin" : answer == "once" ? "You allowed it once" : answer == "stop" ? "Stopped" : answer == "timeout" ? "No answer in 10 minutes" : "You said no")
   if answer == "always" && !setup && !pref("PluginsAllowed", [String]()).contains(id) { prefs["PluginsAllowed"] = pref("PluginsAllowed", [String]()) + [id]; saveLater() }
   publishAiEverywhere()
   guard answer == "once" || answer == "always" else { return agentFail(answer == "timeout" ? "The user didn't answer within 10 minutes. Stop here and ask them in your reply." : "The user said no to this. Don't run it again unless they ask.") }
  } else { audit(run.chat, what, skill.source, "Ran without asking, as Settings allows") }
  let fromWeb = exchangeOf(run.chat).root; fromWeb.read = max(fromWeb.read, 1) // its output is someone else's text, like a page
  chatStep(run.chat, "Ran " + rel); publishAiEverywhere()
  let seconds = min(max((args["timeout"] as? NSNumber)?.doubleValue ?? 120, 5), 600)
  var env = ProcessInfo.processInfo.environment.filter { !$0.key.uppercased().hasPrefix("STILL_") }
  env["PATH"] = cliDirs().joined(separator: ":"); env["CLAUDE_PLUGIN_ROOT"] = root.path; env["PYTHONIOENCODING"] = "utf-8"
  var isFolder: ObjCBool = false
  let work = !mine.folder.isEmpty && FileManager.default.fileExists(atPath: mine.folder, isDirectory: &isFolder) && isFolder.boolValue ? mine.folder : root.path
  let p: Spawned
  do { p = try Spawned(exe, [full.path] + given, folder: work, environment: env) } catch { return agentFail("Couldn't start \(tool): \(error). Tell the user.") }
  try? p.input.close()
  final class Tail: @unchecked Sendable {
   private let lock = NSLock(); private var data = Data()
   func add(_ d: Data) { lock.lock(); data.append(d); if data.count > 120_000 { data = data.suffix(80_000) }; lock.unlock() }
   var text: String { lock.lock(); defer { lock.unlock() }; return String(decoding: data, as: UTF8.self) }
  }
  let tail = Tail(), ended = DispatchSemaphore(value: 0), code = Tail()
  for h in [p.output, p.errors] { DispatchQueue.global().async { while true { let d = h.availableData; if d.isEmpty { break }; tail.add(d) } } }
  DispatchQueue.global().async { code.add(Data(String(p.wait()).utf8)); ended.signal() }
  let until = Date().addingTimeInterval(seconds)
  var cut = false
  while ended.wait(timeout: .now()) == .timedOut {
   if Date() > until || run.stopped { cut = true; p.kill(); break }
   try? await Task.sleep(nanoseconds: 200_000_000)
  }
  try? await Task.sleep(nanoseconds: 300_000_000) // the rest of its output
  var text = tail.text.trimmingCharacters(in: .whitespacesAndNewlines)
  if text.count > 20_000 { text = "…" + text.suffix(20_000) }
  return agentOk(["exitCode": cut ? -1 : Int(code.text) ?? -1, "timedOut": cut && !run.stopped, "output": text])
 }
}
