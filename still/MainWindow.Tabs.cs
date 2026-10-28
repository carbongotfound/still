using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Threading;
namespace Still;
// Tab niceties: the recent tabs switcher, tab groups, split view and the address bar's learned picks.
public partial class MainWindow
{
 // Ctrl+Tab goes back through the tabs you used most recently. A quick press flips to the last one;
 // holding Ctrl shows the list, Tab and Shift+Tab move through it, and letting go of Ctrl switches.
 List<BrowserTab>? recent; int recentIndex; bool recentHeld; DateTime recentAt; DispatcherTimer? recentTimer;
 [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
 async Task SwitchRecent(int step, bool held = false)
 {
  if (recent == null) {
   if (active == null) return;
   var list = tabs.Where(t => t.InChat == null && !t.Closed && t != active).OrderByDescending(t => t.LastActive).ToList();
   if (list.Count == 0) return;
   list.Insert(0, active);
   recent = list; recentIndex = 0; recentAt = DateTime.UtcNow; recentHeld = false;
   recentTimer ??= new DispatcherTimer(TimeSpan.FromMilliseconds(30), DispatcherPriority.Input, async (_, _) => await RecentTick(), Dispatcher);
   recentTimer.Start();
  }
  recentHeld |= held; // tests hold it open without a keyboard
  recentIndex = ((recentIndex + step) % recent.Count + recent.Count) % recent.Count;
  PublishRecent();
  await Task.CompletedTask;
 }
 async Task RecentTick()
 {
  if (recent == null) { recentTimer?.Stop(); return; }
  if (recentHeld || (GetAsyncKeyState(0x11) & 0x8000) != 0) {
   // Still held: show the list after a moment, so a quick press never flashes it.
   if (panel != "recent" && DateTime.UtcNow - recentAt > TimeSpan.FromMilliseconds(180)) { ShellOpen("recent"); PublishRecent(); }
   return;
  }
  await PickRecent(recent[recentIndex]);
 }
 async Task PickRecent(BrowserTab? pick)
 {
  recentTimer?.Stop();
  bool shown = panel == "recent"; recent = null;
  if (shown) CloseSheet(false);
  if (pick != null && !pick.Closed && tabs.Contains(pick)) await SelectTab(pick);
  else if (shown) active?.View?.Focus();
 }
 void PublishRecent() { if (recent != null) ShellSend(new { kind = "recent", ids = recent.Select(t => t.Id), index = recentIndex }); }

 // Ctrl+Alt+Left/Right: the next or previous tab, in strip order.
 async Task CycleTabs(int step)
 {
  var list = tabs.Where(t => t.InChat == null).ToList();
  if (list.Count < 2 || active == null) return;
  await SelectTab(list[((list.IndexOf(active) + step) % list.Count + list.Count) % list.Count]);
 }

 // Tab groups: named, colored and collapsible. A group's tabs stay side by side in the strip.
 internal static readonly string[] GroupColors = ["blue", "green", "amber", "rose", "violet", "cyan", "orange", "grey"];
 TabGroup NewGroup(BrowserTab tab)
 {
  var used = state.Groups.Select(g => g.Color).ToHashSet();
  var group = new TabGroup { Color = GroupColors.FirstOrDefault(c => !used.Contains(c)) ?? GroupColors[state.Groups.Count % GroupColors.Length] };
  state.Groups.Add(group);
  JoinGroup(tab, group.Id);
  return group;
 }
 void JoinGroup(BrowserTab tab, string group)
 {
  if (tab.Pinned || tab.InChat != null) return;
  tab.Group = "";
  var last = tabs.LastOrDefault(t => t.Group == group);
  tab.Group = group;
  if (last != null) { tabs.Remove(tab); tabs.Insert(tabs.IndexOf(last) + 1, tab); }
  RenderTabs(); SaveLater();
 }
 void LeaveGroup(BrowserTab tab)
 {
  if (tab.Group.Length == 0) return;
  var last = tabs.LastOrDefault(t => t != tab && t.Group == tab.Group);
  tab.Group = "";
  if (last != null && tabs.IndexOf(tab) < tabs.IndexOf(last)) { tabs.Remove(tab); tabs.Insert(tabs.IndexOf(last) + 1, tab); }
  RenderTabs(); SaveLater();
 }

 // Split view: two tabs side by side in one window. Selecting either shows both; one pair per window.
 BrowserTab? splitLeft, splitRight; double splitRatio = .5;
 const double SplitGap = 6;
 BrowserTab? Partner => splitLeft == null || splitRight == null || contentFullScreen ? null : active == splitLeft ? splitRight : active == splitRight ? splitLeft : null;
 static bool Splittable(BrowserTab t) => t.ChatId == null && t.InChat == null && t.Url.Length > 0 && !t.Closed;
 async Task StartSplit(BrowserTab other, bool right)
 {
  var here = active;
  BrowserTab? pick = other != here ? other : tabs.Where(t => t != here && Splittable(t)).MaxBy(t => t.LastActive);
  if (here == null || pick == null || !Splittable(here) || !Splittable(pick)) { Toast("Split view needs two open pages."); return; }
  if (Partner?.View is { } old && old != pick.View) old.Visibility = Visibility.Hidden;
  (splitLeft, splitRight) = right ? (here, pick) : (pick, here); splitRatio = .5;
  // The pair sits together in the tab strip.
  tabs.Remove(pick); tabs.Insert(tabs.IndexOf(here) + (right ? 1 : 0), pick); pick.Group = here.Group;
  await SelectTab(here);
 }
 void EndSplit()
 {
  splitLeft = splitRight = null;
  LayoutSplit(); RestorePageWindow(); RenderTabs();
 }
 void LayoutSplit()
 {
  var partner = Partner;
  foreach (var t in tabs) if (t.View is { } v && (partner == null || t != splitLeft && t != splitRight)) {
   v.HorizontalAlignment = HorizontalAlignment.Stretch; v.Width = double.NaN;
   if (t != Shown && v.Visibility == Visibility.Visible) v.Visibility = Visibility.Hidden; // the other half of a pair no longer showing
  }
  if (partner == null) return;
  double left = Math.Round((pageWidth - SplitGap) * splitRatio);
  if (splitLeft!.View is { } l) { l.HorizontalAlignment = HorizontalAlignment.Left; l.Width = Math.Max(1, left); }
  if (splitRight!.View is { } r) { r.HorizontalAlignment = HorizontalAlignment.Right; r.Width = Math.Max(1, pageWidth - SplitGap - left); }
  if (partner.View is { } pv && panel == "") pv.Visibility = Visibility.Visible;
 }
 // Clicking into the other half makes it the current tab: the address bar and buttons follow it.
 void FocusSplitSide(BrowserTab tab)
 {
  if (tab == active || Partner != tab || closing) return;
  if (active != null) active.LastActive = DateTime.UtcNow;
  active = tab; tab.LastActive = DateTime.UtcNow;
  RenderTabs(); UpdateChrome(); SaveLater();
 }

 // Learned ranking: what you typed and the site you picked, so the address bar puts it first next time.
 void RecordPick(string typed, string url)
 {
  typed = typed.Trim().ToLowerInvariant();
  if (active?.Private != false || typed.Length is 0 or > 60 || !Uri.TryCreate(url, UriKind.Absolute, out var u) || u.Scheme is not ("http" or "https")) return;
  var pick = state.AddressPicks.FirstOrDefault(p => p.Typed == typed && p.Url == url);
  if (pick == null) state.AddressPicks.Insert(0, pick = new AddressPick { Typed = typed, Url = url });
  pick.Count++; pick.At = DateTime.UtcNow;
  if (state.AddressPicks.Count > 300) state.AddressPicks = state.AddressPicks.OrderByDescending(p => p.At).Take(300).ToList();
  SaveLater(); ShellPublish();
 }
}
