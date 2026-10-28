using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
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
 bool secondary, incognito;

 // A separate window where every tab is private (not saved, isolated InPrivate session).
 internal static void OpenIncognito()
 {
  var w = new MainWindow(new BrowserTab { Private = true, Title = "New tab" }, null) { incognito = true };
  w.WindowState = WindowState.Maximized; w.Show(); w.Activate();
 }

 // A secondary window, opened by dragging a tab out or "Move to → New window".
 internal MainWindow(BrowserTab moved, Point? screenPoint) : this(secondaryWindow: true)
 {
  tabs.Add(moved);
  if (moved.View is { CoreWebView2: { } core } live) { WebHost.Children.Add(live); WireView(moved, live, core); }
  WindowState = WindowState.Normal;
  Width = 1120; Height = 760;
  // Where the tab was dropped, on any screen (one left of or above the main screen has negative coordinates).
  if (screenPoint is { } p) { WindowStartupLocation = WindowStartupLocation.Manual; Left = Math.Max(SystemParameters.VirtualScreenLeft, p.X - 140); Top = Math.Max(SystemParameters.VirtualScreenTop, p.Y - 24); }
  else if (!(App.IsQa && Environment.GetEnvironmentVariable("STILL_QA_POS") != null)) { WindowStartupLocation = WindowStartupLocation.CenterScreen; } // test windows stay on the test screen
 }

 [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out NativeRect rect);
 [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
 [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr hwnd, uint cmd);
 [DllImport("user32.dll")] static extern IntPtr GetTopWindow(IntPtr hwnd);

 // The other Still window whose frame contains a screen point (drop target for a dragged tab).
 // When windows overlap, the one highest in the z-order wins.
 MainWindow? WindowAt(Point dip)
 {
  var dpi = VisualTreeHelper.GetDpi(this);
  int x = (int)Math.Round(dip.X * dpi.DpiScaleX), y = (int)Math.Round(dip.Y * dpi.DpiScaleY);
  var candidates = Windows.Where(w => w != this && !w.closing).Select(w => (w, h: new WindowInteropHelper(w).Handle))
   .Where(c => c.h != IntPtr.Zero && !IsIconic(c.h) && GetWindowRect(c.h, out var r) && x >= r.Left && x < r.Right && y >= r.Top && y < r.Bottom).ToList();
  if (candidates.Count <= 1) return candidates.FirstOrDefault().w;
  for (var h = GetTopWindow(IntPtr.Zero); h != IntPtr.Zero; h = GetWindow(h, 2)) // GW_HWNDNEXT, top to bottom
   foreach (var c in candidates) if (c.h == h) return c.w;
  return candidates[0].w;
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
  if (tab.LoadingTask is { } loading) await loading;
  if (!tabs.Contains(tab)) return;
  // The live page goes with the tab: no reload, so it keeps its scroll, forms, sign-ins and video.
  // Leave this window (not a real close: nothing goes to "reopen closed tab").
  var moved = tab;
  int index = tabs.IndexOf(tab);
  if (tab == splitLeft || tab == splitRight) { splitLeft = splitRight = null; LayoutSplit(); }
  DropPermissions(tab); tab.Group = "";
  tabs.Remove(tab);
  if (tab.View is { } view) { view.Visibility = Visibility.Hidden; WebHost.Children.Remove(view); if (view.CoreWebView2 == null) { view.Dispose(); tab.View = null; } }
  if (tabs.Count == 0) {
   if (secondary) { Close(); }
   else await NewTab("", false, false);
  } else if (active == tab) await SelectTab(tabs[Math.Min(index, tabs.Count - 1)]);
  RenderTabs(); SaveLater();

  if (target == null) {
   var window = new MainWindow(moved, screenPoint) { incognito = moved.Private && incognito };
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
  if (moved.View is { CoreWebView2: { } core } live) { WebHost.Children.Add(live); WireView(moved, live, core); }
  tabs.Add(moved); await SelectTab(moved); RenderTabs(); SaveLater();
  ShellSend(new { kind = "tabArrived", id = moved.Id });
 }

}
