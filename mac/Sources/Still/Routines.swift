// Routines: what a companion does on a schedule (ported from MainWindow.Routines.cs).
import Foundation

/// At time (HH:MM, this Mac's clock) on days (0 = Sunday), Still starts a new chat with the companion and sends text,
/// while Still is open. Approvals work as in any chat: nothing sends, posts or changes data without asking.
struct Routine {
 var id = "", text = "", time = "", days: [Int] = [], on = true
 var last = "" // the day it last ran (yyyy-MM-dd), so it runs once a day
 init() {}
 init(_ d: [String: Any]) { id = d["Id"] as? String ?? ""; text = d["Text"] as? String ?? ""; time = d["Time"] as? String ?? ""; days = d["Days"] as? [Int] ?? []; on = d["On"] as? Bool ?? true; last = d["Last"] as? String ?? "" }
 var dict: [String: Any] { ["Id": id, "Text": text, "Time": time, "Days": days, "On": on, "Last": last] }
 var shell: [String: Any] { ["id": id, "text": text, "time": time, "days": days, "on": on] }

 static let grace = 15 // minutes: it runs if Still is open within this long after its time, else it waits for its next day
 static func minutes(_ t: String) -> Int? { let p = t.split(separator: ":").compactMap { Int($0) }; return p.count == 2 && (0..<24).contains(p[0]) && (0..<60).contains(p[1]) ? p[0] * 60 + p[1] : nil }
 static func day(_ d: Date) -> String { let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM-dd"; return f.string(from: d) }

 func due(_ now: Date) -> Bool {
  let c = Calendar.current.dateComponents([.weekday, .hour, .minute], from: now)
  guard on, let at = Routine.minutes(time), days.contains(c.weekday! - 1) else { return false }
  return (0..<Routine.grace).contains(c.hour! * 60 + c.minute! - at) && last != Routine.day(now)
 }

 /// The routines the shell saved, checked: at most 20, each with text, a time and days. Keeps when each last ran.
 static func read(_ list: [Any], old: [Routine]) -> [Routine] {
  list.compactMap { $0 as? [String: Any] }.prefix(20).compactMap { e in
   var r = Routine(), id = e["id"] as? String ?? ""
   r.id = (1...24).contains(id.count) && id.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber) }) ? id : String(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(10))
   r.text = String((e["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines).prefix(2000))
   r.days = Set((e["days"] as? [Any] ?? []).compactMap { ($0 as? NSNumber)?.intValue }.filter { (0...6).contains($0) }).sorted()
   guard !r.text.isEmpty, !r.days.isEmpty, let at = minutes(e["time"] as? String ?? "") else { return nil }
   r.time = String(format: "%02d:%02d", at / 60, at % 60); r.on = e["on"] as? Bool ?? true; r.last = old.first { $0.id == r.id }?.last ?? ""
   return r
  }
 }
}

var routineClock: Timer?

extension Browser {
 static func watchRoutines() {
  guard routineClock == nil else { return }
  routineClock = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in browsers.first { !$0.incognito }?.runRoutines(Date()) }
 }

 func runRoutines(_ now: Date) {
  var ran = false
  for c in companions { for i in c.routines.indices where c.routines[i].due(now) {
   c.routines[i].last = Routine.day(now); storeCompanions(); ran = true
   let v = aiView, shown = v.chat // the chat in the sidebar stays; the routine's chat shows in the list and the running tasks
   runAi(nil, c.routines[i].text, companion: c.id)
   v.chat = shown
  } }
  if ran { publishAiEverywhere() }
 }
}
