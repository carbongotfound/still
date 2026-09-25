using System.Windows;
namespace Still;

// Several Still windows in one process. They share one saved state (history, bookmarks, settings)
// and each owns its tabs. A tab moves between windows by reopening its page in the target window
// (cookies and sign-ins carry over; the scroll position is restored).
public partial class MainWindow
{
 internal static readonly List<MainWindow> Windows = [];
 internal static MainWindow? LastActive;
 static readonly StateStore sharedStore = new();
 static SavedState? sharedState;
 static readonly string sharedPrivateProfile = "Private" + Guid.NewGuid().ToString("N");
 internal readonly string WindowId = Guid.NewGuid().ToString("N");
 bool secondary;

 // A secondary window, opened by dragging a tab out or "Move to → New window".
 internal MainWindow(BrowserTab moved, Point? screenPoint) : this(secondaryWindow: true)
 {
  tabs.Add(moved);
  WindowState = WindowState.Normal;
  Width = 1120; Height = 760;
  if (screenPoint is { } p) { WindowStartupLocation = WindowStartupLocation.Manual; Left = Math.Max(0, p.X - 140); Top = Math.Max(0, p.Y - 24); }
  else { WindowStartupLocation = WindowStartupLocation.CenterScreen; }
 }

 int WindowNumber => Windows.IndexOf(this) + 1;
 object WindowsData() => Windows.Where(w => w != this && !w.closing).Select(w => new { id = w.WindowId, name = "Window " + w.WindowNumber, title = w.active?.Title ?? "" });

 // Every open window's tabs are saved together; closing a window drops its tabs, as in Chrome.
 IEnumerable<BrowserTab> SavedTabs()
 {
  var live = Windows.Where(w => !w.closing).ToList();
  if (live.Count == 0) live = [this];
  return live.SelectMany(w => w.tabs).Where(t => !t.Private);
 }

 async Task MoveTab(BrowserTab tab, MainWindow? target, Point? screenPoint)
 {
  if (!tabs.Contains(tab) || target == this) return;
  double scroll = 0;
  if (tab.View?.CoreWebView2 is { } core) {
   try { double.TryParse(await core.ExecuteScriptAsync("window.scrollY"), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out scroll); } catch (Exception) { }
  }
  var moved = new BrowserTab { Url = tab.Url, Title = tab.Title, Favicon = tab.Favicon, Pinned = tab.Pinned, Private = tab.Private, RestoreScroll = scroll };
  // Leave this window (not a real close: nothing goes to "reopen closed tab").
  int index = tabs.IndexOf(tab);
  tab.Closed = true; DisposeView(tab); tabs.Remove(tab);
  if (tabs.Count == 0) {
   if (secondary) { Close(); }
   else await NewTab("", false, false);
  } else if (active == tab) await SelectTab(tabs[Math.Min(index, tabs.Count - 1)]);
  RenderTabs(); SaveLater();

  if (target == null) {
   var window = new MainWindow(moved, screenPoint);
   window.Show(); window.Activate();
  } else {
   target.AcceptTab(moved);
  }
 }

 async void AcceptTab(BrowserTab moved)
 {
  if (closing) return;
  if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal;
  Activate();
  tabs.Add(moved); await SelectTab(moved); RenderTabs(); SaveLater();
  ShellSend(new { kind = "tabArrived", id = moved.Id });
 }

}
