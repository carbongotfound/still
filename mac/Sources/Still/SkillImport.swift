// Skills from GitHub or npm (Windows: MainWindow.SkillImport.cs). Still reads the SKILL.md files in a repository or package
// and shows them before adding any. Only their text comes over, as skills the user then gives to companions: never a
// script, a program, an MCP server or a package install. An added skill keeps where it came from (source), and a chat that
// uses one counts as having read from the web, so a new site asks the way it does after reading a page (reach).
import Foundation

/// What the last look found, held so Add saves exactly what the user saw.
var skillImport: (source: String, skills: [(name: String, description: String, body: String)])?
let skillFileMax = 100_000, skillImportMax = 20
let skillSession: URLSession = {
 let config = URLSessionConfiguration.ephemeral
 config.httpCookieStorage = nil; config.httpShouldSetCookies = false; config.urlCache = nil; config.timeoutIntervalForRequest = 30
 return URLSession(configuration: config)
}()
struct SkillImportError: Error { let message: String }
typealias FoundSkill = (name: String, description: String, body: String, notes: [String], added: Bool)

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
 var found: [FoundSkill] = []
 for f in skillFiles where f.size <= skillFileMax {
  guard let text = try await skillGet(address(f.path), skillFileMax) else { continue }
  let (head, body) = skillHead(text)
  if body.isEmpty { continue }
  let folder = (f.path as NSString).deletingLastPathComponent
  let title = String((head["name"].flatMap { $0.isEmpty ? nil : $0 } ?? (folder.isEmpty ? name : (folder as NSString).lastPathComponent)).prefix(60))
  var notes: [String] = []
  if regexMatch(#"(?im)^\s*(?:```|~~~)\s*(?:bash|sh|shell|zsh|console|powershell|pwsh|ps1|cmd|bat)\b"#, body) != nil || regexMatch(#"(?i)\b(?:bash|shell|powershell|terminal)\b"#, head["allowed-tools"] ?? "") != nil {
   notes.append("It runs commands on your computer, which Still's companions can't do, so parts of it may not work here.")
  }
  let more = folder.isEmpty ? 0 : files.filter { $0.path.hasPrefix(folder + "/") }.count - 1
  if more > 0 { notes.append("Its folder has \(more) more file\(more == 1 ? "" : "s") (scripts or notes) that Still doesn't bring.") }
  if body.count > 20000 { notes.append("It's long: Still keeps the first 20,000 characters.") }
  let added = Skill.all.contains { $0.source == source && $0.name.lowercased() == title.lowercased() }
  if added { notes.append("Already added from here.") }
  found.append((title, head["description"] ?? "", body, notes, added))
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
func skillGet(_ address: String, _ max: Int) async throws -> String? {
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
 return String(decoding: data, as: UTF8.self)
}

extension Browser {
 func skillImportLook(_ link: String) async {
  skillImport = nil
  let link = tidy(String(tidy(link).split(whereSeparator: { $0 == "?" || $0 == "#" }).first ?? ""))
  do {
   let (source, found) = try await skillImportFind(link)
   skillImport = (source, found.map { ($0.name, $0.description, $0.body) })
   send(["kind": "skillImport", "source": source, "skills": found.enumerated().map { ["key": $0.offset, "name": $0.element.name, "description": $0.element.description, "body": $0.element.body, "notes": $0.element.notes, "added": $0.element.added] as [String: Any] }])
  } catch let e as SkillImportError { send(["kind": "skillImport", "error": e.message]) }
  catch { NSLog("Still: skill import: \(error)"); send(["kind": "skillImport", "error": "Couldn't reach it. Check your connection and the link, then try again."]) }
 }

 func skillImportAdd(_ keys: [Any]) {
  guard let pending = skillImport else { return }
  var added = 0, seen = Set<Int>()
  do {
   for case let n as NSNumber in keys where pending.skills.indices.contains(n.intValue) && seen.insert(n.intValue).inserted {
    let k = pending.skills[n.intValue]
    _ = try Skill.save("", k.name, k.description, "", k.body, source: pending.source)
    added += 1
   }
  } catch { NSLog("Still: skill import: \(error)"); toast("Couldn't add those skills.") }
  skillImport = nil
  if added > 0 { toast(added == 1 ? "Added 1 skill. Give it to a companion to use it." : "Added \(added) skills. Give them to a companion to use them.") }
  publishAiEverywhere()
 }
}
