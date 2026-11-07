using System.IO;
using System.Text.Json;
namespace Still;

/// Each run is a task with a state and a checkpoint, kept in ai/tasks/<chat>.json (an incognito chat's only in memory):
/// running, paused (the user took over), waiting (an approval, an answer or a sign-in), interrupted (Still closed or
/// crashed mid-run), completed or failed. A sensitive step writes its intent before it runs and its outcome after, so
/// one cut off in between is known to be uncertain: it is never done again without a fresh approval.
public sealed class AiTask
{
 public string Chat { get; set; } = "";
 public string State { get; set; } = "running";
 public string Reason { get; set; } = ""; // waiting: approval, answer or signin; completed: stopped
 public string Ask { get; set; } = ""; // what the user asked for
 public DateTime Started { get; set; } = DateTime.UtcNow;
 public DateTime Updated { get; set; } = DateTime.UtcNow;
 public List<AiStep> Steps { get; set; } = []; // what it did, the last 40
 public List<string> Tabs { get; set; } = []; // its tabs at the last step
 public string Pending { get; set; } = ""; // the question or approval it was waiting on
 public string LastAudit { get; set; } = "";
 public List<AiSensitive> Sensitive { get; set; } = [];
}
public sealed class AiStep { public string What { get; set; } = ""; public bool Ok { get; set; } public DateTime At { get; set; } = DateTime.UtcNow; }
/// Outcome: null while it runs (and forever, if Still closed before it finished), then done, failed or rechecked.
public sealed class AiSensitive { public string What { get; set; } = ""; public string Site { get; set; } = ""; public DateTime At { get; set; } = DateTime.UtcNow; public string? Outcome { get; set; } }

public partial class MainWindow
{
 static readonly Dictionary<string, AiTask> aiTasks = [];
 static bool tasksLoaded, resumeAnswered; // resumeAnswered: the offer after a restart was taken or put off, once per launch
 static string TasksFolder => Path.Combine(AiFolder, "tasks");
 static string? TaskFile(string chat) => System.Text.RegularExpressions.Regex.IsMatch(chat, "^[A-Za-z0-9_-]{1,64}$") ? Path.Combine(TasksFolder, chat + ".json") : null;

 /// At start: what was going on when Still closed is interrupted now, since nothing runs before Still does.
 static void LoadTasks(List<AiChat> chats)
 {
  if (tasksLoaded) return;
  tasksLoaded = true;
  try {
   foreach (var file in Directory.GetFiles(TasksFolder, "*.json"))
    try {
     if (JsonSerializer.Deserialize<AiTask>(File.ReadAllText(file)) is not { Chat.Length: > 0 } t || TaskFile(t.Chat) != file) continue;
     if (t.State is "running" or "paused" or "waiting") { t.State = "interrupted"; t.Reason = ""; WriteTask(t); }
     aiTasks[t.Chat] = t;
    } catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException) { }
  } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
  // From before tasks: a chat still marked as running.
  foreach (var c in chats.Where(c => c.Running && !aiTasks.ContainsKey(c.Id)))
   aiTasks[c.Id] = new() { Chat = c.Id, State = "interrupted", Ask = c.Messages.LastOrDefault(m => m.Role == "user")?.Text ?? "" };
  // Approvals given in a chat end with Still; rules in Settings stay.
  foreach (var c in chats) c.Allowed.Clear();
 }
 static void WriteTask(AiTask t)
 {
  if (TaskFile(t.Chat) is not { } file) return;
  for (int tries = 1; ; tries++) // another program reading the file can hold off the swap for a moment
   try { Directory.CreateDirectory(TasksFolder); File.WriteAllText(file + ".tmp", JsonSerializer.Serialize(t)); File.Move(file + ".tmp", file, true); return; }
   catch (IOException) when (tries < 5) { Thread.Sleep(20 * tries); }
   catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { App.Log(ex); return; }
 }
 static void SaveTask(ChatRun r) { if (aiTasks.GetValueOrDefault(r.Chat.Id) != r.Task) return; r.Task.Updated = DateTime.UtcNow; if (!r.Chat.Ephemeral) WriteTask(r.Task); }
 static void ForgetTask(string chat) { aiTasks.Remove(chat); if (TaskFile(chat) is { } file) try { File.Delete(file); } catch (IOException) { } }
 static void TaskState(ChatRun? r, string state, string reason = "", string pending = "")
 {
  if (r == null || r.Task.State == state && r.Task.Reason == reason && r.Task.Pending == pending) return;
  r.Task.State = state; r.Task.Reason = reason; r.Task.Pending = pending; SaveTask(r); PublishAiEverywhere();
 }

 /// A new run's task. One that picks up an interrupted task keeps what that one did, and checks before any sensitive step.
 static void StartTask(ChatRun r, string ask)
 {
  var before = aiTasks.GetValueOrDefault(r.Chat.Id);
  r.Task = new() { Chat = r.Chat.Id, Ask = ask.Length > 2000 ? ask[..2000] : ask };
  if (before is { State: "interrupted" } || before is { State: "waiting", Reason: "signin" }) {
   r.Task.Ask = before.Ask.Length > 0 ? before.Ask : r.Task.Ask; r.Task.Steps = before.Steps; r.Task.Sensitive = before.Sensitive; r.Task.Tabs = before.Tabs; r.Task.LastAudit = before.LastAudit;
   r.Recheck = before.Sensitive.Any(s => s.Outcome == null);
  }
  aiTasks[r.Chat.Id] = r.Task; SaveTask(r);
 }

 /// After each tool: what it did, its tabs and the last audit entry, on disk before the next step.
 static void Checkpoint(ChatRun r, string tool, string result)
 {
  bool ok = !result.StartsWith("{\"ok\":false", StringComparison.Ordinal);
  string what = Me(r.Chat.Id).Action is { Length: > 0 } a ? a : tool;
  r.Task.Steps.Add(new() { What = what.Length > 160 ? what[..160] : what, Ok = ok });
  if (r.Task.Steps.Count > 40) r.Task.Steps.RemoveRange(0, r.Task.Steps.Count - 40);
  r.Task.Tabs = Windows.SelectMany(w => w.tabs).Where(t => t.AgentKey == r.Chat.Id && !t.Private && t.Url.Length > 0).Select(t => t.Url).Distinct().Take(10).ToList();
  r.Task.LastAudit = r.Chat.Audit.LastOrDefault() is { } last ? last.What + " on " + last.Site + ": " + last.Result : "";
  SaveTask(r);
 }

 /// What a companion is told when it picks a task back up: what it was asked, what it did, what may or may not have
 /// happened, and to look again before acting.
 static string ResumeBrief(AiTask t)
 {
  var lines = new List<string> { "[Still] Still closed before you finished this task, and the user asked you to pick it up again." };
  if (t.Ask.Length > 0) lines.Add("What you were asked: " + t.Ask);
  if (t.Steps.Count > 0) lines.Add("What you did before it stopped (oldest first):\n" + string.Join("\n", t.Steps.TakeLast(15).Select(s => "- " + Clip(s.What.Replace('[', '(').Replace(']', ')').ReplaceLineEndings(" "), 120) + (s.Ok ? "" : " (didn't work)"))));
  if (t.Tabs.Count > 0) lines.Add("Tabs you had open: " + string.Join(", ", t.Tabs));
  if (t.Pending.Length > 0) lines.Add("You were waiting for the user on: " + t.Pending + ". Ask again if you still need it.");
  if (t.Sensitive.Where(s => s.Outcome == null).ToList() is { Count: > 0 } unsure)
   lines.Add("These steps were under way when Still closed, so they may or may not have gone through: " + string.Join("; ", unsure.Select(s => s.What + " on " + s.Site))
    + ". Check the site first (an order, a sent message, a confirmation) and tell the user what you found. Don't do one again unless they approve it again: Still will ask them.");
  lines.Add("Pages may have changed while Still was closed: read each page again before you act on it. Start your reply with what was already done and what you checked again.");
  return string.Join("\n\n", lines);
 }

 /// Picks an interrupted task back up, or says it needs a sign-in first.
 async Task ResumeTask(AiChat c)
 {
  if (aiTasks.GetValueOrDefault(c.Id) is not { State: "interrupted" or "waiting" } t || Busy(c)) return;
  var cli = AiClis.FirstOrDefault(x => x.Id == c.Harness);
  if (cli == null || FindCli(cli.Command) == null || aiStatus.GetValueOrDefault(cli.Id) is "signedOut" or "missing") {
   t.State = "waiting"; t.Reason = "signin"; if (!c.Ephemeral) WriteTask(t); PublishAiEverywhere(); return;
  }
  c.Running = false;
  int done = t.Steps.Count, unsure = t.Sensitive.Count(s => s.Outcome == null);
  c.Messages.Add(new() { Role = "note", Text = "Picked up where it stopped" + (done > 0 ? $" after {done} step{(done == 1 ? "" : "s")}" : "")
   + (unsure > 0 ? $". {unsure} step{(unsure == 1 ? "" : "s")} may not have finished: it checks first and asks you again." : ".")
   + (c.Started && c.Session != null ? "" : $" The earlier session wasn't saved, so {cli.App} starts a new one from where the task got to.") });
  await RunAi(c, ResumeBrief(t), shown: "");
 }
 static IEnumerable<AiChat> Interrupted => AiChats.Where(c => !c.Archived && !c.Ephemeral && !runs.ContainsKey(c.Id) && aiTasks.GetValueOrDefault(c.Id)?.State == "interrupted");
 static object? TaskView(AiChat? c) => c != null && aiTasks.GetValueOrDefault(c.Id) is { } t ? new { state = runs.ContainsKey(c.Id) || t.State is "interrupted" or "completed" or "failed" || t.Reason == "signin" ? t.State : "interrupted",
  reason = t.Reason, pending = t.Pending, steps = t.Steps.Count, unsure = t.Sensitive.Count(s => s.Outcome == null) } : null;
}
