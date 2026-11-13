// The AI agent apps Still drives headless (ported from Agents/AgentAdapter.cs and
// Agents/AgentStream.cs). Still never reads their login; it only asks each app whether it is signed in. Every run goes
// through Still's MCP server and nothing else.
import Darwin
import Foundation
import PDFKit

struct AgentModel { let id: String, name: String, efforts: [String] }

/// One run: the prompt (sent on stdin, or in a prompt file, never on the command line), the model and effort picked from
/// the adapter's own list, the folder it runs in, the arguments that start Still's MCP server, and the chat's session.
struct RunRequest {
 var prompt: String, model: String, effort: String, folder: String, mcp: [String], session: String?, resume: Bool
 var forget = false // an incognito chat: the app saves no session (only where it has a documented option)
 var job = "chats" // what the run is for (chats, titles, setup or test): an API provider's spending is split by it
 var promptFile: String { (folder as NSString).appendingPathComponent("prompt-" + (session ?? "run") + ".txt") }
}

/// One step of an agent run, the same whichever CLI produced it. Questions, approvals and files reach Still through its
/// own MCP tools (ask_user, the approval cards), so they never come through here.
enum AgentEvent {
 /// join: when set, this continues the reply just before it (joined with join) instead of starting a new one.
 case message(String, join: String?)
 case thinking
 case toolCall(id: String, name: String, args: Any?)
 case toolResult(id: String, ok: Bool)
 case session(String)
 case usage(String)
 case error(String)
 /// A line in the chat from Still about the run (a rate limit pause, a model swapped for the default, the step cap).
 case note(String)
 /// One API call's tokens and estimated cost (0 without prices), for the provider's monthly total.
 case spent(input: Int64, output: Int64, cost: Double, job: String)
}

let agentEfforts = ["low", "medium", "high"]
var aiFolder: String { support.appendingPathComponent("ai").path }
// Attachments: any number, of any kind, up to 500 MB each. An image goes to the AI as a picture only up to 5 MB (what the AI apps take).
let maxAttach: Int64 = 500 << 20, maxImage: Int64 = 5 << 20, partName = ".stillpart" // a file still coming in, in its attachment's folder
func attachName(_ raw: String) -> String {
 let clean = String((raw as NSString).lastPathComponent.map { "/:\\".contains($0) ? "_" : $0 }.prefix(120)).trimmingCharacters(in: .whitespaces)
 return clean.isEmpty || clean.hasPrefix(".") ? "file" + clean : clean
}
func tooBig(_ name: String, _ size: Int64) -> String { "\(name) is \(sizeText(size)). Files can be up to 500 MB." }
func newAttachId() -> String { String(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(16)) }
var attachmentsFolder: String { aiFolder + "/attachments" }
func imageMime(_ name: String) -> String? { ["png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"][(name as NSString).pathExtension.lowercased()] }
func sizeText(_ b: Int64) -> String { b < 1024 ? "\(b) B" : b < 1 << 20 ? String(format: "%.1f KB", Double(b) / 1024) : String(format: "%.1f MB", Double(b) / 1048576) }
func attachment(_ id: String, in folder: String = attachmentsFolder) -> AiFile? {
 guard id.range(of: "^[a-f0-9]{16}$", options: .regularExpression) != nil, let name = try? FileManager.default.contentsOfDirectory(atPath: folder + "/" + id).first(where: { $0 != partName }) else { return nil }
 let size = (try? FileManager.default.attributesOfItem(atPath: folder + "/" + id + "/" + name)[.size] as? Int) ?? 0
 return AiFile(id: id, name: name, size: size)
}
func filesNote(_ files: [AiFile]) -> String {
 "\n\n[Still] The user attached \(files.count == 1 ? "a file" : "\(files.count) files"): " + files.map { "\"\($0.name)\" (\(sizeText(Int64($0.size))), id \($0.id))" }.joined(separator: "; ") + ". Read each with read_attachment before you answer."
}
/// read_attachment: text and code as text, a PDF's text, an image as itself.
func readAttachment(_ who: String, _ id: String, _ offset: Int) -> String {
 let folder = runs[who].map { $0.chat.ephemeral ? ownerOf($0.chat)?.attachmentsHere ?? "" : attachmentsFolder } ?? attachmentsFolder // an incognito chat's are in its window's folder
 guard let file = attachment(id, in: folder) else { return agentFail("No attachment has that id. Use the id from the [Still] note in the user's message.") }
 let url = URL(fileURLWithPath: folder + "/" + id + "/" + file.name)
 did(who, "Read " + file.name)
 return readPage(url, file.name, offset, "Tell the user what you can read.")
}
/// A file for the AI (name is what it knows it as): text and code a page at a time from the file itself (it can be 500 MB),
/// 20000 bytes from offset cut back to a whole character; a PDF's text; a picture up to 5 MB as itself.
func readPage(_ url: URL, _ name: String, _ offset: Int, _ otherwise: String) -> String {
 if imageMime(name) != nil, Int64((try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0) > maxImage { return agentFail("\(name) is a picture over 5 MB, too big to show you. Ask the user for a smaller copy.") }
 if let mime = imageMime(name), let data = try? Data(contentsOf: url) { return agentOk(["image": data.base64EncodedString(), "mime": mime]) }
 if url.pathExtension.lowercased() != "pdf" {
  guard let f = try? FileHandle(forReadingFrom: url), !((try? f.read(upToCount: 8000)) ?? Data()).contains(0) else {
   return agentFail("\(name) isn't text, a PDF or an image Still can show you. \(otherwise)")
  }
  defer { try? f.close() }
  let length = Int((try? f.seekToEnd()) ?? 0), at = min(offset, length)
  try? f.seek(toOffset: UInt64(at))
  let page = [UInt8]((try? f.read(upToCount: 20000)) ?? Data())
  var end = page.count
  if at + end < length { var i = end - 1; while i > 0, page[i] & 0xC0 == 0x80 { i -= 1 }; if page[i] >= 0x80 { end = i } }
  let words = String(decoding: page[..<end], as: UTF8.self)
  if end == length, words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return agentOk(["name": name, "text": "(No text in this file.)"]) }
  return agentOk(["name": name, "text": words, "offset": at, "next": at + end < length ? at + end as Any : NSNull(), "length": length])
 }
 guard let pdf = PDFDocument(url: url) else { return agentFail("Couldn't read \(name) as a PDF. Ask the user for another copy.") }
 let text = pdf.string ?? ""
 if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return agentOk(["name": name, "text": "(No text in this file. If it's a scanned PDF, ask the user for the text or a picture of the pages.)"]) }
 let chars = Array(text), at = min(offset, chars.count), end = min(chars.count, at + 20000)
 return agentOk(["name": name, "text": String(chars[at..<end]), "offset": at, "next": end < chars.count ? end as Any : NSNull(), "length": chars.count])
}
/// This app's own binary: what the AI apps start as Still's MCP server.
let stillExecutable = Bundle.main.executablePath ?? CommandLine.arguments[0]

/// An AI agent app on the user's Mac that Still drives headless.
class AgentAdapter {
 let id: String      // "claude", "grok", "chatgpt" or a manifest's id
 let name: String    // what the user sees: "Claude", "Grok", "ChatGPT"
 let app: String     // the app, for messages: "Claude Code", "Grok Build"
 let command: String
 var maker = ""
 var installer = ""       // the maker's install script; "" = Still never installs it
 var installCommand = ""  // shown for the user to copy
 var site = ""
 var secondary = false      // a manifest agent: listed under "More agents"
 var terminalSignIn = ""    // the user runs this in a terminal to sign in; Still never runs it
 var compatible = false     // built from the app's docs and package, not yet run live: labelled Compatible

 init(id: String, name: String, app: String, command: String) { self.id = id; self.name = name; self.app = app; self.command = command }
 func with(_ setup: (AgentAdapter) -> Void) -> Self { setup(self); return self }

 var promptOnStdin: Bool { true }
 /// Still picks the session id up front (so a stopped first run can still be resumed); otherwise the app reports it.
 var namesSession: Bool { false }
 /// It can run without saving the session on this computer (incognito chats): each turn is then a new session that carries the chat so far.
 var forgets: Bool { false }
 /// Extra environment for its runs (never a key).
 var env: [String: String] { [:] }
 /// What it can't do that the others can, said plainly in AI settings.
 var gaps: [String] { [] }
 /// Login settings from the user's environment that this app keeps. Every other app loses them (apiKeys).
 var kept: [String] { [] }
 /// Set when its runs bill something other than the app's own sign-in: what its card says about that.
 var billing: String { "" }

 /// Signed in? nil when the app can't say. Uses none of the user's AI usage.
 func detect(_ exe: String) async -> Bool? { nil }
 func models(_ exe: String) async -> [AgentModel] { [AgentModel(id: "", name: "Default", efforts: [])] }
 /// The command line for one run. It may write config files into the run's folder.
 func args(_ exe: String, _ r: RunRequest) async throws -> [String] { [] }
 func parse(_ e: [String: Any]) -> [AgentEvent] { [] }
 /// A line that isn't JSON. Agents with plain output speak in lines.
 func plain(_ line: String) -> [AgentEvent] { [] }

 func start(_ exe: String, _ r: RunRequest) async throws -> AgentRun { try await CliRun.start(self, exe, r) }

 // Keys that would bill an API account instead of the app's own sign-in. Removed from every app except what it keeps (kept), and Still never sets one.
 static let apiKeys = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
  "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_BASE_URL", "GOOGLE_GENAI_USE_VERTEXAI"]

 /// What Still's helpers run with: the user's own PATH (a GUI app starts with a bare one) and no API keys.
 static var environment: [String: String] {
  var env = ProcessInfo.processInfo.environment
  for key in apiKeys { env[key] = nil }
  env["PATH"] = cliDirs().joined(separator: ":")
  return env
 }
 static func environment(keeping kept: [String]) -> [String: String] {
  var env = environment
  for key in kept { env[key] = ProcessInfo.processInfo.environment[key] }
  return env
 }

 /// Runs the app briefly and returns what it printed (stdout, then stderr), or nil if it didn't finish in time.
 static func output(_ exe: String, _ folder: String, _ args: [String]) async -> String? {
  await printed(exe, folder, args).map { $0[0] + "\n" + $0[1] }
 }
 static func printed(_ exe: String, _ folder: String, _ args: [String], seconds: Double = 20, keep: [String] = []) async -> [String]? {
  try? FileManager.default.createDirectory(atPath: folder, withIntermediateDirectories: true)
  guard let p = try? Spawned(exe, args, folder: folder, environment: environment(keeping: keep)) else { return nil }
  try? p.input.close()
  return await withCheckedContinuation { done in
   DispatchQueue.global().async {
    let late = Box<Bool>()
    let timer = DispatchWorkItem { late.value = true; p.kill() }
    DispatchQueue.global().asyncAfter(deadline: .now() + seconds, execute: timer)
    let errors = Box<Data>(), read = DispatchGroup()
    read.enter()
    DispatchQueue.global().async { errors.value = p.errors.readDataToEndOfFile(); read.leave() }
    let out = p.output.readDataToEndOfFile()
    read.wait()
    timer.cancel()
    _ = p.wait()
    done.resume(returning: late.value == true ? nil : [String(decoding: out, as: UTF8.self), String(decoding: errors.value ?? Data(), as: UTF8.self)])
   }
  }
 }

 /// Still's MCP server for one run, as a standard mcp.json.
 static func writeMcpConfig(_ r: RunRequest) throws -> String {
  let config = (r.folder as NSString).appendingPathComponent("mcp.json")
  let json: [String: Any] = ["mcpServers": ["still": ["command": stillExecutable, "args": r.mcp]]]
  try JSONSerialization.data(withJSONObject: json, options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: config))
  return config
 }

 // Installer: the maker's own install script, at a fixed address shown to the user before they press Install.
 // terminalSignIn: what the user runs in a terminal to sign in. Still never runs a sign-in or auth command itself.
 static let builtIn: [AgentAdapter] = [
  ClaudeAdapter(id: "claude", name: "Claude", app: "Claude Code", command: "claude").with {
   $0.maker = "Anthropic"; $0.installer = "https://claude.ai/install.sh"; $0.installCommand = "curl -fsSL https://claude.ai/install.sh | bash"
   $0.site = "https://claude.com/product/claude-code"; $0.terminalSignIn = "claude auth login"
  },
  // Never installed by Still: the user installs it themselves if they want it.
  ChatGptAdapter(id: "chatgpt", name: "ChatGPT", app: "ChatGPT", command: "codex").with {
   $0.maker = "OpenAI"; $0.installCommand = "npm install -g @openai/codex"; $0.site = "https://chatgpt.com"; $0.terminalSignIn = "codex login"
  },
  GrokAdapter(id: "grok", name: "Grok", app: "Grok Build", command: "grok").with {
   $0.maker = "xAI"; $0.installer = "https://x.ai/cli/install.sh"; $0.installCommand = "curl -fsSL https://x.ai/cli/install.sh | bash"
   $0.site = "https://x.ai/cli"; $0.terminalSignIn = "grok login --device-auth"
  },
  // Signed in from a terminal: Gemini CLI has no sign-in command of its own.
  GeminiAdapter(id: "gemini", name: "Gemini", app: "Gemini CLI", command: "gemini").with {
   $0.maker = "Google"; $0.installCommand = "npm install -g @google/gemini-cli"; $0.site = "https://github.com/google-gemini/gemini-cli"; $0.terminalSignIn = "gemini"
  },
  OpenCodeAdapter(id: "opencode", name: "OpenCode", app: "OpenCode", command: "opencode").with {
   $0.maker = "OpenCode"; $0.installCommand = "npm install -g opencode-ai"; $0.site = "https://opencode.ai"; $0.secondary = true
  },
  // Compatible: built from their docs and packages, tested with fake apps only. Signed in from a terminal.
  QwenAdapter(id: "qwen", name: "Qwen Code", app: "Qwen Code", command: "qwen").with {
   $0.maker = "Qwen"; $0.installCommand = "npm install -g @qwen-code/qwen-code"; $0.site = "https://github.com/QwenLM/qwen-code"; $0.terminalSignIn = "qwen"; $0.secondary = true; $0.compatible = true
  },
  CopilotAdapter(id: "copilot", name: "GitHub Copilot", app: "Copilot CLI", command: "copilot").with {
   $0.maker = "GitHub"; $0.installCommand = "npm install -g @github/copilot"; $0.site = "https://github.com/github/copilot-cli"; $0.terminalSignIn = "copilot login"; $0.secondary = true; $0.compatible = true
  },
  DshAdapter(id: "dsh", name: "DeepSeek Harness", app: "DeepSeek Harness", command: "dsh").with {
   $0.maker = "DeepSeek"; $0.installCommand = "npm install -g @deepseek-ai/dsh"; $0.site = "https://github.com/deepseek-ai/deepseek-harness"; $0.terminalSignIn = "dsh web"; $0.secondary = true; $0.compatible = true
  },
  // Mac only: Amp's docs run it on Windows through WSL, which Still doesn't drive.
  AmpAdapter(id: "amp", name: "Amp", app: "Amp", command: "amp").with {
   $0.maker = "Amp"; $0.installCommand = "curl -fsSL https://ampcode.com/install.sh | bash"; $0.site = "https://ampcode.com"; $0.terminalSignIn = "amp login"; $0.secondary = true; $0.compatible = true
  },
 ]
}

/// Gemini CLI, signed in with Google. Still's MCP server in the run folder's settings and a policy that denies every tool
/// but Still's, so no shell, file, web, skill or sub-agent tool runs and nothing waits on a terminal prompt.
final class GeminiAdapter: AgentAdapter {
 override var namesSession: Bool { true }
 // It reads the run folder's settings (Still's MCP server) only in a folder it trusts: this one, for the run.
 override var env: [String: String] { ["GEMINI_CLI_TRUST_WORKSPACE": "true"] }
 override var gaps: [String] { ["To sign in, run gemini in a terminal and pick Sign in with Google.", "No effort setting, so modes pick a model only.",
  "Gemini keeps its own record of incognito chats on this computer. It has no option to turn that off."] }
 static var home: String { (ProcessInfo.processInfo.environment["GEMINI_CLI_HOME"].flatMap { $0.isEmpty ? nil : $0 } ?? NSHomeDirectory()) + "/.gemini" }
 /// Signed in with Google: its settings pick that sign-in and it has saved one. Still reads which sign-in, never the login.
 override func detect(_ exe: String) async -> Bool? {
  let settings = (try? Data(contentsOf: URL(fileURLWithPath: Self.home + "/settings.json"))).flatMap { try? JSONSerialization.jsonObject(with: $0, options: [.json5Allowed]) } as? [String: Any]
  let auth = ((settings?["security"] as? [String: Any])?["auth"] as? [String: Any])?["selectedType"] as? String ?? settings?["selectedAuthType"] as? String
  return auth == "oauth-personal" && FileManager.default.fileExists(atPath: Self.home + "/oauth_creds.json")
 }
 // Its own model names (checked with 0.66.0); auto lets Gemini pick.
 override func models(_ exe: String) async -> [AgentModel] {
  [("", "Default"), ("auto", "Auto"), ("pro", "Pro"), ("flash", "Flash"), ("flash-lite", "Flash Lite")].map { AgentModel(id: $0.0, name: $0.1, efforts: []) }
 }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  let dir = r.folder + "/.gemini", policy = dir + "/still-policy.toml"
  try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
  let settings: [String: Any] = ["mcpServers": ["still": ["command": stillExecutable, "args": r.mcp, "trust": true, "timeout": 660000]]] // ask_user waits for the user
  try JSONSerialization.data(withJSONObject: settings, options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: dir + "/settings.json"))
  try "[[rule]]\ntoolName = \"*\"\ndecision = \"deny\"\npriority = 100\n\n[[rule]]\ntoolName = \"mcp_still_*\"\ndecision = \"allow\"\npriority = 900\n".write(toFile: policy, atomically: true, encoding: .utf8)
  var args = ["--output-format", "stream-json", "--allowed-mcp-server-names", "still", "-e", "none", "--policy", policy, r.resume ? "--resume" : "--session-id", r.session ?? ""]
  if !r.model.isEmpty { args += ["-m", r.model] }
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.gemini(e) }
}

/// Qwen Code (`qwen`), built from its docs and its 0.26.6 package, not run live: the prompt on stdin (it reads a piped
/// prompt), Claude-style stream-json, Still's MCP server in the run folder's settings, and every built-in tool off.
final class QwenAdapter: AgentAdapter {
 // Its built-in tools in 0.26.6, all hidden from the model. tools.core (an allowlist of none) also turns off file, shell and
 // search tools a later version adds.
 static let builtInTools = ["exec", "edit", "write_file", "read_file", "zoom_image", "grep_search", "glob", "run_shell_command", "todo_write",
  "save_memory", "manage_memory", "search_memory", "agent", "skill", "exit_plan_mode", "enter_plan_mode", "web_fetch", "web_search", "image_gen",
  "list_directory", "lsp", "ask_user_question", "cron_create", "cron_list", "cron_delete", "autofix_pr", "loop_wakeup", "create_sub_session", "list_agents",
  "task_stop", "task_create", "task_update", "task_list", "team_create", "team_delete", "team_plan_approval", "request_shutdown", "send_message",
  "structured_output", "monitor", "notebook_edit", "tool_call", "tool_search", "read_mcp_resource", "advisor", "enter_worktree", "exit_worktree", "workflow",
  "artifact", "record_artifact", "record_source", "report_findings", "get_goal", "update_goal", "propose_goal", "display_image",
  "omni_downsample_image", "omni_downscale_video", "omni_downsample_audio", "omni_extract_keyframes", "omni_extract_audio", "omni_clip_video",
  "omni_convert_image", "omni_transcribe_audio", "omni_clip_image", "omni_clip_audio", "omni_caption_image", "omni_caption_audio", "omni_ocr_image",
  "omni_understand_video_segments", "omni_recall_media_memory"]
 override var forgets: Bool { true } // general.chatRecording off: an incognito chat saves nothing
 override var gaps: [String] { ["To sign in, run qwen in a terminal and pick a sign-in.", "No model or effort settings in Still yet, so every mode uses the model you set in Qwen Code."] }
 static var home: String { ProcessInfo.processInfo.environment["QWEN_HOME"].flatMap { $0.isEmpty ? nil : $0 } ?? NSHomeDirectory() + "/.qwen" }
 // Folder trust (off unless the user turned it on): Still's own list, trusting its AI folder (incognito runs are in it
 // too), so the run folder's settings load.
 override var env: [String: String] {
  let trust = aiFolder + "/qwen-trusted-folders.json"
  try? FileManager.default.createDirectory(atPath: aiFolder, withIntermediateDirectories: true)
  try? JSONSerialization.data(withJSONObject: [aiFolder: "TRUST_FOLDER"], options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: trust))
  return ["QWEN_CODE_TRUSTED_FOLDERS_PATH": trust]
 }
 /// Signed in with Qwen OAuth: its settings pick that sign-in and it has saved one. Another sign-in (an API key): it can't say.
 override func detect(_ exe: String) async -> Bool? {
  let settings = (try? Data(contentsOf: URL(fileURLWithPath: Self.home + "/settings.json"))).flatMap { try? JSONSerialization.jsonObject(with: $0, options: [.json5Allowed]) } as? [String: Any]
  let type = ((settings?["security"] as? [String: Any])?["auth"] as? [String: Any])?["selectedType"] as? String ?? ""
  return type.isEmpty ? false : type == "qwen-oauth" ? FileManager.default.fileExists(atPath: Self.home + "/oauth_creds.json") : nil
 }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  let dir = r.folder + "/.qwen"
  try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
  let settings: [String: Any] = [
   "mcpServers": ["still": ["command": stillExecutable, "args": r.mcp, "trust": true, "timeout": 660000]], // ask_user waits for the user
   "permissions": ["allow": ["mcp__still"]],
   "tools": ["core": ["mcp__still"], "disabled": Self.builtInTools],
   "general": ["chatRecording": !r.forget]]
  try JSONSerialization.data(withJSONObject: settings, options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: dir + "/settings.json"))
  var args = ["--output-format", "stream-json", "--allowed-mcp-server-names", "still", "-e", "none", "--approval-mode", "default"]
  if r.resume, let session = r.session { args += ["--resume", session] }
  if !r.model.isEmpty { args += ["-m", r.model] }
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.messages(e, tokenUsage: true) }
}

/// GitHub Copilot CLI (`copilot`), built from its docs, not run live: the prompt on stdin, only its reply printed (-s),
/// Still's MCP server added for the run, every built-in tool kind denied (deny wins over any allow).
final class CopilotAdapter: AgentAdapter {
 // A UUID that names no session yet starts one with that id; the same id resumes it.
 override var namesSession: Bool { true }
 override var gaps: [String] { ["To sign in, run copilot login in a terminal.", "Shows its reply once it's done, not each step.",
  "Copilot keeps its own record of incognito chats on this computer.", "Effort applies on the models Copilot offers it for."] }
 override func models(_ exe: String) async -> [AgentModel] { [AgentModel(id: "", name: "Default", efforts: agentEfforts), AgentModel(id: "auto", name: "Auto", efforts: [])] }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  let config = r.folder + "/copilot-mcp.json"
  let json: [String: Any] = ["mcpServers": ["still": ["type": "local", "command": stillExecutable, "args": r.mcp, "tools": ["*"], "timeout": 660000]]]
  try JSONSerialization.data(withJSONObject: json, options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: config))
  var args = ["-s", "--additional-mcp-config", "@" + config, "--allow-tool", "still", "--deny-tool", "shell,write,read,url,memory",
   "--disable-builtin-mcps", "--no-ask-user", "--no-custom-instructions", "--session-id", r.session ?? ""]
  if !r.model.isEmpty { args += ["--model", r.model] }
  if !r.effort.isEmpty { args += ["--effort", r.effort] }
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { plain(jsonText(e)) }
 override func plain(_ line: String) -> [AgentEvent] { line.trimmingCharacters(in: .whitespaces).isEmpty ? [] : [.message(line, join: "\n")] }
}

/// DeepSeek Harness (`dsh`, DeepSeek's own agent), built from its docs and source (github.com/deepseek-ai/deepseek-harness),
/// not run live: the headless profile with its JSON event stream, the prompt on stdin, and a --patch overlay in the run
/// folder that adds Still's MCP server, turns its own tools off, turns its session-log upload off and lets it use the
/// sign-in or key saved in its own app. Still never reads that sign-in.
final class DshAdapter: AgentAdapter {
 // Its own tools: shell, files, jobs, skills, sub-agents, workflows, web and MCP resources.
 static let tools = ["tool-bash", "tool-pwsh", "tool-jobs", "tool-fs", "tool-fs-search", "tool-working-directory", "tool-skill",
  "tool-agent-team", "tool-subagent-control", "tool-subagent", "tool-subagent-fork", "tool-workflow", "tool-web", "mcp-resources"]
 override var gaps: [String] { ["To sign in or add your DeepSeek key, run dsh web in a terminal.", "It is a developer preview, so it may change or break.",
  "No model or effort settings in Still yet, so every mode uses the model you set in DeepSeek Harness.", "DeepSeek Harness keeps its own record of incognito chats on this computer."] }
 override var env: [String: String] { ["DSH_TELEMETRY_MODE": "DISABLED"] }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  // A patch replaces a row's whole config, so the session-log row gets one of its own. JSON is YAML, so no escaping to get wrong.
  let patch = r.folder + "/still-dsh.yml"
  let rows: [[String: Any]] = [
   ["insert": [["id": "still-mcp", "name": "@deepseek-ai/dsh-mcp-client", "config": ["serverName": "still", "transport": "stdio",
    "command": stillExecutable, "args": r.mcp, "cwd": r.folder, "toolCallTimeoutMs": 660000]]]], // ask_user waits for the user
   ["id": "session-log-deepseek", "config": ["enabled": false]]]
   + ["credentials", "authorization", "deepseek-account"].map { ["id": $0, "disabled": false] }
   + Self.tools.map { ["id": $0, "disabled": true] }
  try JSONSerialization.data(withJSONObject: rows, options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: patch))
  var args = ["--profile", "headless", "--patch", patch, "--json"]
  if r.resume, let session = r.session { args += ["--session-id", session] }
  return args + ["-"]
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.dsh(e) }
}

/// Amp (`amp`), built from its docs, not run live: execute mode with the prompt on stdin, Claude-style stream-json, a
/// settings file of Still's own for the run (Still's MCP server, every built-in tool off), and its mode as the effort.
/// Still can't continue an Amp thread by id from its docs, so each message brings the chat so far.
final class AmpAdapter: AgentAdapter {
 override var gaps: [String] { ["To sign in, run amp login in a terminal.", "Amp saves each thread to your Amp account, incognito chats too.",
  "Each message starts a new Amp thread with the chat so far.", "Effort is Amp's mode: low, medium, high or ultra."] }
 override func models(_ exe: String) async -> [AgentModel] { [AgentModel(id: "", name: "Default", efforts: ["low", "medium", "high", "ultra"])] }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  let settings = r.folder + "/amp-settings.json"
  // builtin:* turns off Amp's own tools only; its documented tool names are listed too, for an Amp that doesn't take the glob.
  let json: [String: Any] = ["amp.mcpServers": ["still": ["command": stillExecutable, "args": r.mcp]],
   "amp.tools.disable": ["builtin:*", "builtin:Bash", "builtin:create_file", "builtin:edit_file", "builtin:glob", "builtin:Grep", "builtin:Read",
    "builtin:read_web_page", "builtin:Task", "builtin:todo_read", "builtin:todo_write", "builtin:undo_edit", "builtin:web_search"]]
  try JSONSerialization.data(withJSONObject: json, options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: settings))
  var args = ["-x", "--stream-json", "--settings-file", settings]
  if !r.effort.isEmpty { args += ["--mode", r.effort] }
  return args
 }
 // Its thread id isn't kept: a next message can't continue the thread, so it starts a new one with the chat so far.
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.messages(e, tokenUsage: true).filter { if case .session = $0 { return false } else { return true } } }
}

/// OpenCode, on whichever provider the user set up inside it: a plan sign-in, that provider's key kept by OpenCode, or
/// OpenCode's free models. Still never sees which. Its own tools, skills and sub-agents stay off.
final class OpenCodeAdapter: AgentAdapter {
 var version = ""
 override var gaps: [String] { ["Runs on the provider you set up in OpenCode (opencode providers login, in a terminal).",
  "OpenCode keeps its own record of incognito chats on this computer. It has no option to turn that off."]
  + (!version.isEmpty && !version.hasPrefix("1.") ? ["Still was checked with OpenCode 1. This is \(version), so it may not work."] : []) }
 static func modelLine(_ line: String) -> Bool { line.range(of: #"^[A-Za-z0-9][\w.@-]*/\S+$"#, options: .regularExpression) != nil }
 // Ready once it lists a model: its free ones need no sign-in.
 override func detect(_ exe: String) async -> Bool? {
  if let v = await AgentAdapter.printed(exe, aiFolder, ["--version"]) { version = v[0].trimmingCharacters(in: .whitespacesAndNewlines) }
  guard let p = await AgentAdapter.printed(exe, aiFolder, ["models"]) else { return nil }
  return p[0].components(separatedBy: "\n").contains { Self.modelLine($0.trimmingCharacters(in: .whitespaces)) }
 }
 /// Its catalog: each model's line, then its details, whose variants are its effort levels. Models without tool calls are left out.
 override func models(_ exe: String) async -> [AgentModel] {
  var list = [AgentModel(id: "", name: "Default", efforts: [])]
  guard let p = await AgentAdapter.printed(exe, aiFolder, ["models", "--verbose"]) else { return list }
  let order = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
  var id = "", details = ""
  func add() {
   guard !id.isEmpty else { return }
   guard let m = jsonObject(details) else { list.append(AgentModel(id: id, name: id, efforts: [])); return }
   if (m["capabilities"] as? [String: Any])?["toolcall"] as? Bool == false { return }
   let name = (m["name"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? id
   let variants = ((m["variants"] as? [String: Any])?.keys).map(Array.init) ?? []
   list.append(AgentModel(id: id, name: name + " · " + (id.split(separator: "/").first.map(String.init) ?? ""),
    efforts: variants.sorted { (order.firstIndex(of: $0) ?? 99, $0) < (order.firstIndex(of: $1) ?? 99, $1) }))
  }
  for raw in p[0].components(separatedBy: "\n") {
   let line = raw.trimmingCharacters(in: CharacterSet(charactersIn: "\r"))
   if Self.modelLine(line) { add(); id = line; details = "" } else { details += line + "\n" }
  }
  add()
  return list
 }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  // Still's MCP server in the run folder's config (v1 shape) and every tool off but Still's. Its MCP calls time out after
  // 5 seconds unless told otherwise; ask_user waits for the user.
  let config: [String: Any] = ["$schema": "https://opencode.ai/config.json", "mcp": ["still": ["type": "local", "command": [stillExecutable] + r.mcp, "enabled": true, "timeout": 660000]],
   "tools": ["*": false, "still_*": true]]
  try FileManager.default.createDirectory(atPath: r.folder, withIntermediateDirectories: true)
  try JSONSerialization.data(withJSONObject: config, options: [.withoutEscapingSlashes]).write(to: URL(fileURLWithPath: r.folder + "/opencode.json"))
  var args = ["run", "--format", "json", "--dir", r.folder, "--title", "Still"] // a title of its own would cost a model call
  if r.resume, let session = r.session { args += ["--session", session] }
  if !r.model.isEmpty { args += ["-m", r.model] }
  if !r.effort.isEmpty { args += ["--variant", r.effort] }
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.openCode(e) }
}

final class ClaudeAdapter: AgentAdapter {
 override var forgets: Bool { true } // --no-session-persistence
 override var namesSession: Bool { true }
 static let levels = ["low", "medium", "high", "xhigh", "max"]
 // Claude Code's own login methods stay available: products that run it may not remove or restrict them.
 override var kept: [String] { ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"] }
 private var bills = ""
 override var billing: String { bills }
 override func detect(_ exe: String) async -> Bool? {
  // The setting sources a run uses: with its default ones, a login in the user's settings file reads as signed in and the run then says it isn't.
  guard let printed = await AgentAdapter.printed(exe, aiFolder, ["--setting-sources", "project,local", "auth", "status"], keep: kept) else { bills = ""; return nil }
  let status = jsonObject(printed[0].trimmingCharacters(in: .whitespacesAndNewlines))
  bills = Self.whoBills(status?["apiProvider"] as? String, status?["authMethod"] as? String, status?["apiKeySource"] as? String)
  return (status?["loggedIn"] as? Bool) ?? false
 }
 /// From what `claude auth status` says. "" = Claude's own sign-in. An auth token reads the same there as a subscription
 /// token, so this also looks whether that variable is set, never at its value.
 static func whoBills(_ provider: String?, _ method: String?, _ keySource: String?) -> String {
  switch (provider, method) {
  case ("bedrock", _): return "Using Amazon Bedrock from your environment. Your AWS account is billed."
  case ("vertex", _): return "Using Google Cloud from your environment. Your Google Cloud account is billed."
  case ("foundry", _): return "Using Microsoft Foundry from your environment. Your Azure account is billed."
  case (_, "third_party"): return "Using a cloud provider from your environment. Your account there is billed."
  case (_, "api_key"): return keySource == "ANTHROPIC_API_KEY" ? "Using an API key from your environment. Your API account is billed." : "Using an API key. Your API account is billed."
  case (_, "api_key_helper"): return "Using an API key. Your API account is billed."
  case (_, "oauth_token"): return ProcessInfo.processInfo.environment["ANTHROPIC_AUTH_TOKEN"]?.isEmpty == false ? "Using an auth token from your environment. The account it belongs to is billed." : ""
  default: return ""
  }
 }
 override func models(_ exe: String) async -> [AgentModel] {
  [("", "Default"), ("fable", "Fable"), ("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")].map { AgentModel(id: $0.0, name: $0.1, efforts: Self.levels) }
 }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  let config = try AgentAdapter.writeMcpConfig(r)
  var args = ["-p", "--output-format", "stream-json", "--verbose", "--mcp-config", config, "--strict-mcp-config", "--allowedTools", "mcp__still", r.resume ? "--resume" : "--session-id", r.session ?? "",
   "--disable-slash-commands", "--setting-sources", "project,local"] // none of the user's own skills, commands, plugins or settings
  if r.forget { args.append("--no-session-persistence") }
  args += ["--tools", ""] // none of its own: files go through Still's tools, in the working folder only (Folder.swift)
  if !r.model.isEmpty { args += ["--model", r.model] }
  if !r.effort.isEmpty { args += ["--effort", r.effort] }
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.messages(e, tokenUsage: false) }
}

final class GrokAdapter: AgentAdapter {
 override var promptOnStdin: Bool { false }
 override var namesSession: Bool { true }
 // Grok has no status command; listing models needs a sign-in and says so.
 override func detect(_ exe: String) async -> Bool? {
  await AgentAdapter.output(exe, aiFolder, ["models"]).map { !$0.lowercased().contains("not authenticated") }
 }
 override func models(_ exe: String) async -> [AgentModel] {
  var list = [AgentModel(id: "", name: "Default", efforts: agentEfforts)]
  let text = await AgentAdapter.output(exe, aiFolder, ["models"]) ?? ""
  let pattern = try! NSRegularExpression(pattern: #"^\s*[*-]\s+(\S+)"#, options: .anchorsMatchLines)
  for match in pattern.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
   if let range = Range(match.range(at: 1), in: text) { list.append(AgentModel(id: String(text[range]), name: String(text[range]), efforts: [])) } // its effort levels per model aren't listed: default effort only
  }
  return list
 }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  // Grok reads MCP servers from the folder's .grok/config.toml, and only starts them with --trust. Its own approval
  // prompts would stall a headless run; Still decides inside its MCP server, and Grok's own tools are off (--tools).
  _ = await AgentAdapter.output(exe, r.folder, ["mcp", "add", "-s", "project", "still", stillExecutable, "--"] + r.mcp)
  try r.prompt.write(toFile: r.promptFile, atomically: true, encoding: .utf8)
  var args = ["--prompt-file", r.promptFile, "--output-format", "streaming-messages-json", "--trust", "--tools", "search_tool,use_tool", "--no-subagents", "--always-approve", r.resume ? "-r" : "-s", r.session ?? ""]
  if !r.model.isEmpty { args += ["-m", r.model] }
  if !r.effort.isEmpty { args += ["--reasoning-effort", r.effort] }
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.messages(e, tokenUsage: true) }
}

/// ChatGPT, through OpenAI's agent CLI signed in with the user's ChatGPT plan. The UI only ever calls it ChatGPT.
final class ChatGptAdapter: AgentAdapter {
 override var forgets: Bool { true } // exec --ephemeral
 override func detect(_ exe: String) async -> Bool? {
  guard let text = await AgentAdapter.output(exe, aiFolder, ["login", "status"]) else { return nil }
  // An API key login would bill an API account: only a ChatGPT sign-in counts.
  return text.contains("Logged in") && !text.contains("Not logged in") && !text.lowercased().contains("api key")
 }
 override func models(_ exe: String) async -> [AgentModel] {
  var list = [AgentModel(id: "", name: "Default", efforts: ["low", "medium", "high", "xhigh"])]
  let text = await AgentAdapter.output(exe, aiFolder, ["debug", "models"]) ?? ""
  for case let model as [String: Any] in jsonObject(text.trimmingCharacters(in: .whitespacesAndNewlines))?["models"] as? [Any] ?? [] {
   guard model["visibility"] as? String == "list", let slug = model["slug"] as? String else { continue }
   let efforts = (model["supported_reasoning_levels"] as? [Any] ?? []).compactMap { ($0 as? [String: Any])?["effort"] as? String }.filter { !$0.isEmpty }
   list.append(AgentModel(id: slug, name: model["display_name"] as? String ?? slug, efforts: efforts))
  }
  return list
 }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  // TOML literal strings ('...') need no escaping but can't hold an apostrophe.
  if (r.mcp + [stillExecutable]).contains(where: { $0.contains("'") }) { throw AgentError("ChatGPT can't run Still from a folder whose name has an apostrophe.") }
  func quoted(_ value: String) -> String { "'" + value + "'" }
  // In steps: as one expression, older Swift compilers time out type-checking it.
  var args: [String] = ["exec"]
  if r.resume { args.append("resume") }
  if r.forget { args.append("--ephemeral") }
  args += ["--json", "--skip-git-repo-check", "-c", "sandbox_mode='read-only'", "-c", "mcp_servers.still.tool_timeout_sec=660"] // ask_user waits for the user
  // Its own approval for Still's tools can't show in a run (it turns them down: "user cancelled MCP tool call"); Still asks the user itself.
  args += ["-c", "mcp_servers.still.default_tools_approval_mode='approve'"]
  let servers: String = r.mcp.map(quoted).joined(separator: ",")
  args += ["-c", "mcp_servers.still.command=" + quoted(stillExecutable), "-c", "mcp_servers.still.args=[" + servers + "]"]
  for own in ["shell_tool", "unified_exec", "apps", "plugins", "browser_use", "computer_use", "in_app_browser", "multi_agent", "image_generation"] { args += ["-c", "features.\(own)=false"] } // like the other apps: Still's tools and nothing else
  if !r.model.isEmpty { args += ["-c", "model=" + quoted(r.model)] }
  if !r.effort.isEmpty { args += ["-c", "model_reasoning_effort=" + quoted(r.effort)] }
  if r.resume, let session = r.session { args.append(session) }
  args.append("-")
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] { AgentStream.codex(e) }
}

/// Any other agent CLI, described by a JSON file in Still's agents folder (see docs/agentic/agents.md). Placeholders in
/// its args: {prompt}, {promptFile}, {model}, {effort}, {cwd}, {mcpConfig} (a standard mcp.json for Still) and {session}.
/// Without {prompt} or {promptFile} the prompt goes to stdin.
final class ManifestAdapter: AgentAdapter {
 struct Spec {
  var id = "", name = "", command = "", site = "", install = "", expect = ".", mcpFile = "", output = "plain"
  var enabled = false
  var detect: [String] = [], signin: [String] = [], run: [String] = [], resume: [String] = [], model: [String] = [], effort: [String] = [], models: [String] = []
  var fields: [String: String] = [:]
  init(_ json: [String: Any]) {
   var keyed: [String: Any] = [:]
   for (key, value) in json { keyed[key.lowercased()] = value } // property names match case-insensitively, as on Windows
   func text(_ key: String, _ fallback: String) -> String { keyed[key.lowercased()] as? String ?? fallback }
   func list(_ key: String) -> [String] { (keyed[key.lowercased()] as? [Any] ?? []).compactMap { $0 as? String } }
   id = text("id", ""); name = text("name", ""); command = text("command", ""); site = text("site", ""); install = text("install", "")
   expect = text("expect", "."); mcpFile = text("mcpFile", ""); output = text("output", "plain"); enabled = keyed["enabled"] as? Bool ?? false
   detect = list("detect"); signin = list("signin"); run = list("run"); resume = list("resume")
   model = list("model"); effort = list("effort"); models = list("models")
   fields = (keyed["fields"] as? [String: Any] ?? [:]).compactMapValues { $0 as? String }
  }
 }
 var spec = Spec([:])

 // Written once, turned off, for the user to adapt. Not tested by Still: none of these apps is on the build Mac.
 static let examples: [(String, String)] = [
  ("gemini", #"""
   {
    "id": "gemini", "name": "Gemini", "enabled": false,
    "note": "Example, not tested by Still. Sign in by running gemini once in a terminal. Set enabled to true to use it.",
    "command": "gemini", "site": "https://github.com/google-gemini/gemini-cli", "install": "npm install -g @google/gemini-cli",
    "detect": ["--version"], "expect": "\\d+\\.\\d+",
    "mcpFile": ".gemini/settings.json",
    "run": ["--output-format", "stream-json", "--allowed-mcp-server-names", "still", "--yolo"],
    "model": ["-m", "{model}"], "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "output": "jsonl",
    "resume": ["--resume", "{session}"],
    "fields": { "session": "session_id when type=init", "text": "content when type=message,role=assistant", "delta": "delta",
     "tool": "tool_name when type=tool_use", "toolId": "tool_id", "toolArgs": "parameters", "error": "message when type=error,severity=error" }
   }
   """#),
  ("cursor-agent", #"""
   {
    "id": "cursor-agent", "name": "Cursor Agent", "enabled": false,
    "note": "Example, not tested by Still. Sign in with: cursor-agent login. Set enabled to true to use it.",
    "command": "cursor-agent", "site": "https://cursor.com/cli", "install": "See cursor.com/cli",
    "detect": ["status"], "expect": "(?i)logged in", "signin": ["login"],
    "mcpFile": ".cursor/mcp.json",
    "run": ["-p", "--output-format", "stream-json", "--approve-mcps", "--force"],
    "resume": ["--resume", "{session}"], "model": ["--model", "{model}"],
    "output": "stream-json"
   }
   """#),
  ("opencode", #"""
   {
    "id": "opencode", "name": "OpenCode", "enabled": false,
    "note": "Example, not tested by Still. Add Still to OpenCode's MCP servers yourself (command: /Applications/Still.app/Contents/MacOS/Still --mcp --as OpenCode). Set enabled to true to use it.",
    "command": "opencode", "site": "https://opencode.ai", "install": "npm install -g opencode-ai",
    "detect": ["--version"], "expect": "\\d+\\.\\d+",
    "run": ["run", "--file", "{promptFile}", "Do what the attached file asks."], "model": ["--model", "{model}"],
    "output": "plain"
   }
   """#),
  ("aider", #"""
   {
    "id": "aider", "name": "Aider", "enabled": false,
    "note": "Example, not tested by Still. Aider has no MCP support, so it can chat but can't use your tabs.",
    "command": "aider", "site": "https://aider.chat", "install": "python3 -m pip install aider-install",
    "detect": ["--version"], "expect": "\\d+\\.\\d+",
    "run": ["--no-git", "--yes-always", "--no-pretty", "--message-file", "{promptFile}"], "model": ["--model", "{model}"],
    "output": "plain"
   }
   """#)
 ]

 static var folder: URL { profileHome.appendingPathComponent("agents") }
 /// The enabled manifests. A broken file is skipped and logged; it never stops Still.
 static func load() -> [AgentAdapter] {
  let files = FileManager.default
  if !files.fileExists(atPath: folder.path) {
   try? files.createDirectory(at: folder, withIntermediateDirectories: true)
   for (name, json) in examples { try? json.write(to: folder.appendingPathComponent(name + ".json"), atomically: true, encoding: .utf8) }
  }
  let names = ((try? files.contentsOfDirectory(atPath: folder.path)) ?? []).filter { $0.hasSuffix(".json") }.sorted()
  var found: [AgentAdapter] = []
  for name in names {
   guard let data = try? Data(contentsOf: folder.appendingPathComponent(name)),
         let json = (try? JSONSerialization.jsonObject(with: data, options: [.json5Allowed])) as? [String: Any] else { NSLog("Still: skipped agents/\(name)"); continue }
   let s = Spec(json)
   guard s.enabled, s.id.range(of: "^[a-z0-9-]{1,30}$", options: .regularExpression) != nil, !["claude", "grok", "chatgpt", "codex", "gemini", "opencode", "qwen", "copilot", "amp", "dsh"].contains(s.id),
         !s.command.isEmpty, !s.run.isEmpty else { continue }
   let adapter = ManifestAdapter(id: s.id, name: s.name.isEmpty ? s.id : s.name, app: s.name.isEmpty ? s.command : s.name, command: s.command)
   adapter.spec = s; adapter.site = s.site; adapter.installCommand = s.install; adapter.secondary = true
   if !s.signin.isEmpty { adapter.terminalSignIn = ([s.command.contains(" ") ? "'\(s.command)'" : s.command] + s.signin).joined(separator: " ") } // shown to run in a terminal
   found.append(adapter)
  }
  return found
 }

 override var promptOnStdin: Bool { !(spec.run + spec.resume).contains { $0.contains("{prompt}") || $0.contains("{promptFile}") } }
 override func detect(_ exe: String) async -> Bool? {
  if spec.detect.isEmpty { return nil }
  guard let text = await AgentAdapter.output(exe, aiFolder, spec.detect) else { return nil }
  return text.range(of: spec.expect, options: .regularExpression) != nil
 }
 override func models(_ exe: String) async -> [AgentModel] {
  let efforts = spec.effort.isEmpty ? [] : agentEfforts
  return [AgentModel(id: "", name: "Default", efforts: efforts)] + spec.models.map { AgentModel(id: $0, name: $0, efforts: efforts) }
 }
 override func args(_ exe: String, _ r: RunRequest) async throws -> [String] {
  let config = try AgentAdapter.writeMcpConfig(r)
  let root = URL(fileURLWithPath: r.folder).standardizedFileURL.path + "/"
  if !spec.mcpFile.isEmpty {
   let extra = URL(fileURLWithPath: r.folder).appendingPathComponent(spec.mcpFile).standardizedFileURL
   if extra.path.hasPrefix(root) {
    try FileManager.default.createDirectory(at: extra.deletingLastPathComponent(), withIntermediateDirectories: true)
    try? FileManager.default.removeItem(at: extra)
    try FileManager.default.copyItem(atPath: config, toPath: extra.path)
   }
  }
  try r.prompt.write(toFile: r.promptFile, atomically: true, encoding: .utf8)
  let values = ["{prompt}": r.prompt, "{promptFile}": r.promptFile, "{model}": r.model, "{effort}": r.effort, "{cwd}": r.folder, "{mcpConfig}": config, "{session}": r.session ?? ""]
  func fill(_ arg: String) -> String { values.reduce(arg) { $0.replacingOccurrences(of: $1.key, with: $1.value) } }
  var args = spec.run.map(fill)
  if r.resume && r.session != nil { args += spec.resume.map(fill) }
  if !r.model.isEmpty { args += spec.model.map(fill) }
  if !r.effort.isEmpty { args += spec.effort.map(fill) }
  return args
 }
 override func parse(_ e: [String: Any]) -> [AgentEvent] {
  switch spec.output {
  case "stream-json": return AgentStream.messages(e, tokenUsage: true)
  case "jsonl": return AgentStream.fields(e, spec.fields)
  default: return plain(jsonText(e))
  }
 }
 override func plain(_ line: String) -> [AgentEvent] {
  spec.output == "plain" && !line.trimmingCharacters(in: .whitespaces).isEmpty ? [.message(line, join: "\n")] : []
 }
}

/// A child process in its own process group, so ending it ends everything it started at once (Windows: a Job Object).
final class Spawned {
 let pid: pid_t
 let input: FileHandle, output: FileHandle, errors: FileHandle
 private var reaped: Int32?
 private let lock = NSLock()

 init(_ exe: String, _ args: [String], folder: String, environment: [String: String]) throws {
  var inPipe: [Int32] = [0, 0], outPipe: [Int32] = [0, 0], errPipe: [Int32] = [0, 0]
  guard pipe(&inPipe) == 0, pipe(&outPipe) == 0, pipe(&errPipe) == 0 else { throw AgentError("couldn't start it.") }
  var actions: posix_spawn_file_actions_t? = nil
  posix_spawn_file_actions_init(&actions)
  defer { posix_spawn_file_actions_destroy(&actions) }
  posix_spawn_file_actions_adddup2(&actions, inPipe[0], 0)
  posix_spawn_file_actions_adddup2(&actions, outPipe[1], 1)
  posix_spawn_file_actions_adddup2(&actions, errPipe[1], 2)
  posix_spawn_file_actions_addchdir_np(&actions, folder)
  var attributes: posix_spawnattr_t? = nil
  posix_spawnattr_init(&attributes)
  defer { posix_spawnattr_destroy(&attributes) }
  // Its own process group; none of Still's other files; signals back to normal (Still ignores SIGPIPE).
  posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETSIGMASK))
  posix_spawnattr_setpgroup(&attributes, 0)
  var defaults = sigset_t(), none = sigset_t()
  sigemptyset(&defaults); sigaddset(&defaults, SIGPIPE); sigemptyset(&none)
  posix_spawnattr_setsigdefault(&attributes, &defaults)
  posix_spawnattr_setsigmask(&attributes, &none)
  let argv = ([exe] + args).map { strdup($0) } + [nil]
  let envp = environment.map { strdup($0.key + "=" + $0.value) } + [nil]
  defer { argv.forEach { free($0) }; envp.forEach { free($0) } }
  var child = pid_t()
  let result = posix_spawn(&child, exe, &actions, &attributes, argv, envp)
  for fd in [inPipe[0], outPipe[1], errPipe[1]] { close(fd) }
  guard result == 0 else {
   for fd in [inPipe[1], outPipe[0], errPipe[0]] { close(fd) }
   throw AgentError("couldn't start it: " + String(cString: strerror(result)))
  }
  pid = child
  Children.started(child)
  input = FileHandle(fileDescriptor: inPipe[1], closeOnDealloc: true)
  output = FileHandle(fileDescriptor: outPipe[0], closeOnDealloc: true)
  errors = FileHandle(fileDescriptor: errPipe[0], closeOnDealloc: true)
 }

 /// Ends it and everything it started (Still's MCP server, shells, helpers) right away.
 func kill() {
  if Darwin.killpg(pid, SIGKILL) != 0 { _ = Darwin.kill(pid, SIGKILL) }
 }

 /// Waits for it to exit and returns its exit code (128 + the signal when a signal ended it).
 func wait() -> Int32 {
  lock.lock(); defer { lock.unlock() }
  if let reaped { return reaped }
  var status: Int32 = 0
  while waitpid(pid, &status, 0) < 0 && errno == EINTR {}
  let code = status & 0x7f == 0 ? (status >> 8) & 0xff : 128 + (status & 0x7f)
  reaped = code
  Children.ended(pid)
  return code
 }
}

/// What Still has running (AI apps, sign-ins), listed under the profile so a start after a crash ends what's left:
/// on the Mac nothing ends a child when its parent dies (Windows: the Job Object does). A listed pid counts only while
/// its start time still matches, so a number the system gave to something else since is never touched.
enum Children {
 private static let lock = NSLock()
 private static var running: [pid_t: UInt64] = [:]
 private static var file: URL { support.appendingPathComponent("running-ai.txt") }

 static func started(_ pid: pid_t) {
  guard let at = startTime(pid) else { return }
  lock.lock(); defer { lock.unlock() }
  running[pid] = at; save()
 }
 static func ended(_ pid: pid_t) {
  lock.lock(); defer { lock.unlock() }
  if running.removeValue(forKey: pid) != nil { save() }
 }
 private static func save() {
  if running.isEmpty { try? FileManager.default.removeItem(at: file); return }
  try? running.map { "\($0.key) \($0.value)" }.joined(separator: "\n").write(to: file, atomically: true, encoding: .utf8)
 }
 static func startTime(_ pid: pid_t) -> UInt64? {
  var info = proc_bsdinfo(), size = Int32(MemoryLayout<proc_bsdinfo>.size)
  guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, size) == size else { return nil }
  return info.pbi_start_tvsec * 1_000_000 + info.pbi_start_tvusec
 }
 /// At start, holding the profile's lock (no other copy runs on it): ends each listed run still going, and its group.
 static func sweep() {
  guard let text = try? String(contentsOf: file, encoding: .utf8) else { return }
  for line in text.split(separator: "\n") {
   let field = line.split(separator: " ")
   guard field.count == 2, let pid = pid_t(field[0]), let at = UInt64(field[1]), pid > 1, startTime(pid) == at else { continue }
   if Darwin.killpg(pid, SIGKILL) != 0 { _ = Darwin.kill(pid, SIGKILL) }
   NSLog("Still: ended AI app \(pid), left running by a Still that didn't quit")
  }
  try? FileManager.default.removeItem(at: file)
 }
}

/// Calls each line of a pipe until it closes. Lines that end in \r\n lose the \r.
func readLines(_ handle: FileHandle, _ each: (String) -> Void) {
 var buffer = Data()
 while true {
  let chunk = handle.availableData
  if chunk.isEmpty { break }
  buffer.append(chunk)
  while let end = buffer.firstIndex(of: 10) {
   var line = buffer[buffer.startIndex..<end]
   if line.last == 13 { line = line.dropLast() }
   each(String(decoding: line, as: UTF8.self))
   buffer.removeSubrange(buffer.startIndex...end)
  }
 }
 if !buffer.isEmpty { each(String(decoding: buffer, as: UTF8.self)) }
}

/// A running agent: an app (CliRun) or Still's own loop for an API provider (ApiRun), with the same events. Still quitting ends every one.
class AgentRun {
 static let limit: TimeInterval = 3600
 static var launched = 0 // runs started since Still opened: each one uses the user's plan (tests check Quick setup uses none)
 private static var live: [ObjectIdentifier: AgentRun] = [:]
 private static let liveLock = NSLock()
 let adapter: AgentAdapter
 let started = Date()
 private let lock = NSLock()
 private var errorLines: [String] = []
 var cancelled = false, timedOut = false
 var exitCode: Int32 = 0

 init(_ adapter: AgentAdapter) {
  self.adapter = adapter
  AgentRun.liveLock.lock(); AgentRun.live[ObjectIdentifier(self)] = self; AgentRun.liveLock.unlock()
 }
 /// It's over: Still quitting no longer needs to end it.
 func ended() { AgentRun.liveLock.lock(); AgentRun.live[ObjectIdentifier(self)] = nil; AgentRun.liveLock.unlock() }

 func keep(_ line: String) {
  lock.lock(); defer { lock.unlock() }
  errorLines.append(line)
  if errorLines.count > 40 { errorLines.removeFirst() }
 }
 var errors: [String] { lock.lock(); defer { lock.unlock() }; return errorLines }

 /// The run's events, in order, until it ends.
 func events() -> AsyncStream<AgentEvent> { AsyncStream { $0.finish() } }

 /// Ends it right away.
 func cancel() { cancelled = true }

 /// Still is quitting: every run ends with it.
 static func endAll() {
  liveLock.lock(); let all = Array(live.values); liveLock.unlock()
  for run in all { run.cancel() }
 }

 /// Keeps what the app printed when it failed, so a crash can be looked into later. Prompts are never written.
 func saveLog(_ folder: String, _ chatId: String) {
  let logs = URL(fileURLWithPath: folder).appendingPathComponent("logs")
  try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
  let stamp = DateFormatter()
  stamp.dateFormat = "yyyyMMdd-HHmmss"
  let seconds = Int(Date().timeIntervalSince(started))
  let lines = ["agent: \(adapter.app)", "chat: \(chatId)", "exit code: \(exitCode)", String(format: "ran for: %02d:%02d:%02d", seconds / 3600, seconds / 60 % 60, seconds % 60), ""] + errors
  try? lines.joined(separator: "\n").write(to: logs.appendingPathComponent("\(stamp.string(from: Date()))-\(adapter.id).log"), atomically: true, encoding: .utf8)
  let old = ((try? FileManager.default.contentsOfDirectory(atPath: logs.path)) ?? []).filter { $0.hasSuffix(".log") }.sorted(by: >).dropFirst(20)
  for name in old { try? FileManager.default.removeItem(at: logs.appendingPathComponent(name)) }
 }
}

/// An app's run. Its processes share a process group, so cancel ends every child at once.
final class CliRun: AgentRun {
 private let process: Spawned
 private let stderrDone = DispatchGroup()

 private init(_ adapter: AgentAdapter, _ process: Spawned) {
  self.process = process
  super.init(adapter)
  stderrDone.enter()
  Thread.detachNewThread { [self] in readLines(process.errors) { self.keep($0) }; stderrDone.leave() }
 }

 static func start(_ adapter: AgentAdapter, _ exe: String, _ r: RunRequest) async throws -> AgentRun {
  try FileManager.default.createDirectory(atPath: r.folder, withIntermediateDirectories: true)
  let args = try await adapter.args(exe, r)
  let run = CliRun(adapter, try Spawned(exe, args, folder: r.folder, environment: AgentAdapter.environment(keeping: adapter.kept).merging(adapter.env) { $1 }))
  DispatchQueue.main.async { launched += 1 }
  // Written from the side, so a big prompt never blocks Still while the app is slow to read it.
  let prompt = adapter.promptOnStdin ? Data(r.prompt.utf8) : Data(), input = run.process.input
  DispatchQueue.global().async { try? input.write(contentsOf: prompt); try? input.close() }
  return run
 }

 /// The run's events, in order, until the app exits. Lines that aren't JSON go to plain (and are kept for errors).
 override func events() -> AsyncStream<AgentEvent> {
  AsyncStream { continuation in
   Thread.detachNewThread { [self] in
    let timer = DispatchWorkItem { [weak self] in self?.timedOut = true; self?.cancel() }
    DispatchQueue.global().asyncAfter(deadline: .now() + AgentRun.limit, execute: timer)
    readLines(process.output) { line in
     if line.hasPrefix("{"), let e = jsonObject(line) { for event in adapter.parse(e) { continuation.yield(event) } }
     else { keep(line); for event in adapter.plain(line) { continuation.yield(event) } }
    }
    stderrDone.wait()
    exitCode = process.wait()
    timer.cancel()
    ended()
    continuation.finish()
   }
  }
 }

 /// Ends the app and everything it started right away.
 override func cancel() { super.cancel(); process.kill() }
}

/// Turns each CLI's JSON lines into AgentEvents. Pure functions, so tests can feed them recorded output.
enum AgentStream {
 static func str(_ value: Any?) -> String? {
  switch value {
  case nil, is NSNull: return nil
  case let text as String: return text
  case let number as NSNumber: return CFGetTypeID(number) == CFBooleanGetTypeID() ? (number.boolValue ? "true" : "false") : number.stringValue
  case let object?: return JSONSerialization.isValidJSONObject(object) ? (try? JSONSerialization.data(withJSONObject: object)).map { String(decoding: $0, as: UTF8.self) } : "\(object)"
  }
 }
 static func isTrue(_ value: Any?) -> Bool { (value as? NSNumber).map { CFGetTypeID($0) == CFBooleanGetTypeID() && $0.boolValue } ?? false }
 static func long(_ value: Any?) -> Int64 { min(max((value as? NSNumber)?.int64Value ?? 0, 0), 1 << 40) } // token counts: adding them up can't overflow
 static func percent(_ window: Any?) -> String {
  guard let used = ((window as? [String: Any])?["utilization"] as? NSNumber)?.doubleValue else { return "?" }
  return "\(Int((used * 100).rounded(.toNearestOrEven)))%"
 }
 static func tokens(_ n: Int64) -> String {
  if n < 1000 { return "\(n)" }
  if n >= 10000 { return "\(Int((Double(n) / 1000).rounded(.toNearestOrEven)))k" }
  let value = (Double(n) / 100).rounded(.toNearestOrEven) / 10
  return value == value.rounded() ? "\(Int(value))k" : String(format: "%.1fk", value)
 }

 /// Claude Code (stream-json) and Grok Build (streaming-messages-json) both stream Anthropic Messages events.
 /// Grok wraps Still's tools in search_tool/use_tool; tokens are reported only where no usage window is.
 static func messages(_ e: [String: Any], tokenUsage: Bool) -> [AgentEvent] {
  var events: [AgentEvent] = []
  let type = str(e["type"])
  if let session = str(e["session_id"]), !session.isEmpty, type == "system" || type == "result" { events.append(.session(session)) }
  if type == "result", isTrue(e["is_error"]), e["result"] != nil { events.append(.error(str(e["result"]) ?? "")) }
  if type == "rate_limit_event", let windows = (e["rate_limit_info"] as? [String: Any])?["unifiedWindows"] as? [String: Any] {
   events.append(.usage("5-hour limit \(percent(windows["five_hour"])) used · weekly \(percent(windows["seven_day"]))"))
  } else if type == "result", tokenUsage, let usage = e["usage"] as? [String: Any] {
   events.append(.usage("Last reply: \(tokens(long(usage["input_tokens"]) + long(usage["cache_read_input_tokens"]))) in, \(tokens(long(usage["output_tokens"]))) out"))
  }
  guard type == "assistant" || type == "user" else { return events }
  for case let block as [String: Any] in (e["message"] as? [String: Any])?["content"] as? [Any] ?? [] {
   switch str(block["type"]) {
   case "text" where type == "assistant": if let text = str(block["text"]), !text.isEmpty { events.append(.message(text, join: nil)) }
   case "thinking" where type == "assistant", "redacted_thinking" where type == "assistant": events.append(.thinking)
   case "tool_use" where type == "assistant":
    let id = str(block["id"]) ?? "", name = str(block["name"]) ?? "", input = block["input"] as? [String: Any]
    if name == "use_tool" { events.append(.toolCall(id: id, name: str(input?["tool_name"]) ?? "", args: input?["tool_input"])) }
    else if name != "search_tool" { events.append(.toolCall(id: id, name: name, args: block["input"])) }
   case "tool_result" where type == "user": events.append(.toolResult(id: str(block["tool_use_id"]) ?? "", ok: !isTrue(block["is_error"])))
   default: break
   }
  }
  return events
 }

 /// The ChatGPT app's CLI (`exec --json`): thread, item and turn events.
 static func codex(_ e: [String: Any]) -> [AgentEvent] {
  let item = e["item"] as? [String: Any], kind = str(item?["type"]) ?? ""
  switch str(e["type"]) {
  case "thread.started": if let thread = str(e["thread_id"]), !thread.isEmpty { return [.session(thread)] }
  case "item.started" where kind == "mcp_tool_call": return [.toolCall(id: str(item?["id"]) ?? "", name: str(item?["tool"]) ?? "", args: item?["arguments"])]
  case "item.completed" where kind == "mcp_tool_call":
   let failed = str(item?["status"]) == "failed" || (item?["error"] != nil && !(item?["error"] is NSNull))
   let blocked = codexBlocked(str(item?["tool"]) ?? "a", str((item?["error"] as? [String: Any])?["message"]) ?? str(item?["error"]))
   return [.toolResult(id: str(item?["id"]) ?? "", ok: !failed)] + (blocked.map { [.error($0)] } ?? [])
  case "item.completed" where kind == "reasoning": return [.thinking]
  case "item.completed" where kind == "agent_message": if let text = str(item?["text"]), !text.isEmpty { return [.message(text, join: nil)] }
  case "turn.completed":
   if let usage = e["usage"] as? [String: Any] {
    return [.usage("Last reply: \(tokens(long(usage["input_tokens"]))) in (\(tokens(long(usage["cached_input_tokens"]))) cached), \(tokens(long(usage["output_tokens"]))) out")]
   }
  case "turn.failed", "error":
   let message = str((e["error"] as? [String: Any])?["message"]) ?? str(e["message"]) ?? "failed"
   return [.error(message.contains("401") ? "not signed in. Sign in, then try again." : message)]
  default: break
  }
  return []
 }

 /// The ChatGPT app turning down one of Still's tools by itself (Windows: CodexBlocked): its approval step, which can't show in
 /// a run Still started. Its run has Still's tools pre-approved; this is for an older app or a config that overrides it.
 static func codexBlocked(_ tool: String, _ why: String?) -> String? {
  guard let why, why.range(of: "cancel|approv|reject", options: [.regularExpression, .caseInsensitive]) != nil else { return nil }
  return "it stopped Still's \(tool) tool before it ran, waiting for its own approval, which it can't ask for inside Still (\(why)). Still asks you itself before anything sensitive, so the ChatGPT app's approval should be off for Still: update the app (npm install -g @openai/codex) and make sure ~/.codex/config.toml doesn't set approval_mode for the still server or its tools."
 }

 /// Gemini CLI (`--output-format stream-json`, checked with 0.66.0): init, the reply in message deltas, tool_use,
 /// tool_result, error and a closing result. Still's tools come as mcp_still_<tool>.
 static func gemini(_ e: [String: Any]) -> [AgentEvent] {
  switch str(e["type"]) {
  case "init": if let session = str(e["session_id"]), !session.isEmpty { return [.session(session)] }
  case "message" where str(e["role"]) == "assistant": if let text = str(e["content"]), !text.isEmpty { return [.message(text, join: isTrue(e["delta"]) ? "" : nil)] }
  case "tool_use": return [.toolCall(id: str(e["tool_id"]) ?? "", name: bare(str(e["tool_name"]), "mcp_still_"), args: e["parameters"])]
  case "tool_result": return [.toolResult(id: str(e["tool_id"]) ?? "", ok: str(e["status"]) == "success")]
  case "error" where str(e["severity"]) == "error": return [.error(str(e["message"]) ?? "failed")]
  case "result":
   var events: [AgentEvent] = []
   if let u = e["stats"] as? [String: Any], long(u["input_tokens"]) + long(u["output_tokens"]) > 0 {
    events.append(.usage("Last reply: \(tokens(long(u["input_tokens"]))) in (\(tokens(long(u["cached"]))) cached), \(tokens(long(u["output_tokens"]))) out"))
   }
   if str(e["status"]) == "error" { events.append(.error(str((e["error"] as? [String: Any])?["message"]) ?? "failed")) }
   return events
  default: break
  }
  return []
 }

 /// OpenCode (`run --format json`, checked with 1.19.5): step_start, text (a whole part), tool_use (once it's done),
 /// step_finish with tokens, and error. Every event has the sessionID. Still's tools come as still_<tool>.
 static func openCode(_ e: [String: Any]) -> [AgentEvent] {
  let part = e["part"] as? [String: Any]
  switch str(e["type"]) {
  case "step_start": if let session = str(e["sessionID"]), !session.isEmpty { return [.session(session)] }
  case "text": if let text = str(part?["text"]), !text.isEmpty { return [.message(text, join: nil)] }
  case "reasoning": return [.thinking]
  case "tool_use":
   let id = str(part?["callID"]) ?? "", state = part?["state"] as? [String: Any]
   var events: [AgentEvent] = [.toolCall(id: id, name: bare(str(part?["tool"]), "still_"), args: state?["input"])]
   if let status = str(state?["status"]), status == "completed" || status == "error" { events.append(.toolResult(id: id, ok: status == "completed")) }
   return events
  case "step_finish":
   if let t = part?["tokens"] as? [String: Any], long(t["input"]) + long(t["output"]) > 0 {
    let cached = long((t["cache"] as? [String: Any])?["read"])
    return [.usage("Last reply: \(tokens(long(t["input"]) + cached)) in (\(tokens(cached)) cached), \(tokens(long(t["output"]))) out")]
   }
  case "error":
   let error = e["error"] as? [String: Any]
   return [.error(str((error?["data"] as? [String: Any])?["message"]) ?? str(error?["name"]) ?? "failed")]
  default: break
  }
  return []
 }
 /// DeepSeek Harness (`--profile headless --json`, built from its docs and source, not run live): session first, then text
 /// and thinking once each step commits, tool_call and tool_result, a final event repeating the answer (skipped), and
 /// error for a failure outside a turn. Still's tools come as mcp__still__<tool>.
 static func dsh(_ e: [String: Any]) -> [AgentEvent] {
  switch str(e["type"]) {
  case "session": if let session = str(e["sessionId"]), !session.isEmpty { return [.session(session)] }
  case "text": if let text = str(e["text"]), !text.isEmpty { return [.message(text, join: nil)] }
  case "thinking": return [.thinking]
  case "tool_call": return [.toolCall(id: str(e["callId"]) ?? "", name: bare(str(e["tool"]), "mcp__still__"), args: e["input"])]
  case "tool_result": return [.toolResult(id: str(e["callId"]) ?? "", ok: str(e["status"]) == "completed")]
  case "error": return [.error(str(e["message"]) ?? "failed")]
  default: break
  }
  return []
 }
 static func bare(_ tool: String?, _ prefix: String) -> String { guard let tool else { return "" }; return tool.hasPrefix(prefix) ? String(tool.dropFirst(prefix.count)) : tool }

 /// A manifest agent's JSON lines, read through its field map. Each map entry is "path" or "path when key=value[,key=value]".
 static func fields(_ e: [String: Any], _ map: [String: String]) -> [AgentEvent] {
  func pick(_ key: String) -> String? {
   guard let rule = map[key] else { return nil }
   let parts = rule.components(separatedBy: " when ")
   let path = parts[0].trimmingCharacters(in: .whitespaces)
   if parts.count > 1 {
    let conditions = parts.dropFirst().joined(separator: " when ").split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
    for condition in conditions {
     let pair = condition.split(separator: "=", maxSplits: 1).map(String.init)
     guard pair.count == 2, str(at(e, pair[0])) == pair[1] else { return nil }
    }
   }
   guard let value = str(at(e, path)), !value.isEmpty else { return nil }
   return value
  }
  var events: [AgentEvent] = []
  if let session = pick("session") { events.append(.session(session)) }
  if let tool = pick("tool") { events.append(.toolCall(id: pick("toolId") ?? "", name: tool, args: map["toolArgs"].flatMap { at(e, $0) })) }
  if let text = pick("text") { events.append(.message(text, join: pick("delta") == "true" ? "" : nil)) }
  if let error = pick("error") { events.append(.error(error)) }
  return events
 }

 static func at(_ node: Any?, _ path: String) -> Any? {
  var node = node
  for key in path.split(separator: ".").map(String.init) {
   if let object = node as? [String: Any] { node = object[key] }
   else if let array = node as? [Any], let index = Int(key), index >= 0, index < array.count { node = array[index] }
   else { return nil }
  }
  return node
 }
}

// MARK: Finding the apps

/// The user's PATH from their login shell. A GUI app starts with a bare PATH, which misses Homebrew, npm and nvm.
let loginPath: String = {
 let shell = ProcessInfo.processInfo.environment["SHELL"].flatMap { $0.isEmpty ? nil : $0 } ?? "/bin/zsh"
 let marker = "__STILL_PATH__"
 guard let p = try? Spawned(shell, ["-ilc", "printf '\\n\(marker)%s\\n' \"$PATH\""], folder: NSHomeDirectory(), environment: ProcessInfo.processInfo.environment) else { return "" }
 try? p.input.close()
 let timer = DispatchWorkItem { p.kill() }
 DispatchQueue.global().asyncAfter(deadline: .now() + 4, execute: timer)
 DispatchQueue.global().async { _ = p.errors.readDataToEndOfFile() }
 let out = String(decoding: p.output.readDataToEndOfFile(), as: UTF8.self)
 timer.cancel()
 _ = p.wait()
 return out.components(separatedBy: "\n").last { $0.hasPrefix(marker) }.map { String($0.dropFirst(marker.count)) } ?? ""
}()

/// Where AI apps get installed, re-read each time so a fresh install is found without restarting Still.
func cliDirs() -> [String] {
 let home = NSHomeDirectory()
 var dirs = (qaEnv("STILL_QA_CLIS").map { [$0] } ?? []) + loginPath.split(separator: ":").map(String.init) + (ProcessInfo.processInfo.environment["PATH"] ?? "").split(separator: ":").map(String.init)
 dirs += ["\(home)/.local/bin", "\(home)/.grok/bin", "\(home)/.claude/local", "\(home)/.npm-global/bin", "\(home)/.bun/bin", "\(home)/.volta/bin",
          "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
 let nvm = "\(home)/.nvm/versions/node"
 if let versions = try? FileManager.default.contentsOfDirectory(atPath: nvm) {
  dirs += versions.sorted { $0.compare($1, options: .numeric) == .orderedDescending }.map { "\(nvm)/\($0)/bin" }
 }
 var seen = Set<String>()
 return dirs.filter { !$0.isEmpty && seen.insert($0).inserted }
}

/// An installed CLI's full path, or nil. A command with a slash is a path already (a manifest may name one).
func findCli(_ name: String) -> String? {
 if name.isEmpty { return "" } // an API provider: Still runs it itself
 let files = FileManager.default
 func runnable(_ path: String) -> Bool {
  var folder: ObjCBool = false
  return files.fileExists(atPath: path, isDirectory: &folder) && !folder.boolValue && files.isExecutableFile(atPath: path)
 }
 if name.contains("/") { let path = (name as NSString).expandingTildeInPath; return runnable(path) ? path : nil }
 return cliDirs().lazy.map { $0 + "/" + name }.first(where: runnable)
}
