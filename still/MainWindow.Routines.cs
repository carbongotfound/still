using System.Text.Json;
using System.Windows.Threading;

namespace Still;

/// Something a companion does on a schedule: at Time (HH:MM, this PC's clock) on Days (0 = Sunday), Still starts a new
/// chat with it and sends Text, while Still is open. Approvals work as in any chat: nothing sends, posts or changes data
/// without asking.
public sealed class Routine
{
 public string Id { get; set; } = "";
 public string Text { get; set; } = "";
 public string Time { get; set; } = "09:00";
 public List<int> Days { get; set; } = [];
 public bool On { get; set; } = true;
 public string Last { get; set; } = ""; // the day it last ran (yyyy-MM-dd), so it runs once a day
}

public partial class MainWindow
{
 static DispatcherTimer? routineClock;
 // A routine runs if Still is open within this long after its time (asleep or closed longer: it waits for its next day).
 static readonly TimeSpan RoutineGrace = TimeSpan.FromMinutes(15);

 static void WatchRoutines()
 {
  if (routineClock != null) return;
  routineClock = new DispatcherTimer { Interval = TimeSpan.FromSeconds(30) };
  routineClock.Tick += (_, _) => Windows.FirstOrDefault(w => !w.closing && !w.incognito)?.RunRoutines(DateTime.Now);
  routineClock.Start();
 }

 internal static bool Due(Routine r, DateTime now) =>
  r.On && r.Days.Contains((int)now.DayOfWeek) && TimeSpan.TryParse(r.Time, out var at) && now.TimeOfDay >= at && now.TimeOfDay < at + RoutineGrace
  && r.Last != now.ToString("yyyy-MM-dd");

 void RunRoutines(DateTime now)
 {
  var ran = false;
  foreach (var c in Companions.ToList()) foreach (var r in c.Routines.Where(r => Due(r, now))) {
   r.Last = now.ToString("yyyy-MM-dd"); SaveLater(); ran = true;
   var shown = aiChat; // the chat in the sidebar stays; the routine's chat shows in the list and the running tasks
   _ = RunAi(null, r.Text, companion: c.Id);
   aiChat = shown;
  }
  if (ran) PublishAiEverywhere();
 }

 /// The routines the shell saved, checked: at most 20, each with text, a time and days. Keeps when each last ran.
 static List<Routine> ReadRoutines(JsonElement list, List<Routine> old) =>
  list.EnumerateArray().Where(e => e.ValueKind == JsonValueKind.Object).Take(20).Select(e => {
   string Str(string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";
   var id = Str("id") is { Length: > 0 and <= 24 } i && i.All(char.IsAsciiLetterOrDigit) ? i : Guid.NewGuid().ToString("N")[..10];
   var days = e.TryGetProperty("days", out var d) && d.ValueKind == JsonValueKind.Array ? d.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.Number && x.TryGetInt32(out var n) && n is >= 0 and <= 6).Select(x => x.GetInt32()).Distinct().Order().ToList() : [];
   return new Routine { Id = id, Text = Str("text").Trim() is var t && t.Length > 2000 ? t[..2000] : t, Time = TimeSpan.TryParse(Str("time"), out var at) && at < TimeSpan.FromDays(1) ? $"{at.Hours:00}:{at.Minutes:00}" : "",
    Days = days, On = !e.TryGetProperty("on", out var on) || on.ValueKind != JsonValueKind.False, Last = old.FirstOrDefault(o => o.Id == id)?.Last ?? "" };
  }).Where(r => r.Text.Length > 0 && r.Time.Length > 0 && r.Days.Count > 0).ToList();
}
