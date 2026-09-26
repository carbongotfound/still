using System.IO;
using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using Microsoft.Win32;
using Microsoft.Web.WebView2.Core;

namespace Still;
public partial class MainWindow
{
 void OpenSheet(string name, string title)
 {
  panel = name; SheetTitle.Text = title; SheetContent.Children.Clear(); SheetBackdrop.Visibility = Visibility.Visible;
  foreach (var t in tabs) if (t.View != null) t.View.Visibility = Visibility.Hidden;
  LoadProgress.Visibility = Visibility.Collapsed;
 }
 void CloseSheet(bool focus = true)
 {
  if(shellReady){++panelRequestVersion;panel="";ShellSend(new{kind="panel",name="",value=""});if(focus)active?.View?.Focus();return;}
  panel = ""; SheetBackdrop.Visibility = Visibility.Collapsed;
  if (active?.View is { } view) { view.Visibility = Visibility.Visible; if (focus) view.Focus(); }
  UpdateChrome();
 }
 void CloseSheetClick(object s, RoutedEventArgs e) => CloseSheet();
 void BackdropClick(object s, MouseButtonEventArgs e) => CloseSheet();
 void SheetClick(object s, MouseButtonEventArgs e) => e.Handled = true;
 TextBlock Note(string text, double size = 13) => new() { Text = text, FontSize = size, Foreground = Brush("Muted"), TextWrapping = TextWrapping.Wrap, LineHeight = size * 1.6, Margin = new Thickness(0, 0, 0, 16) };
 Button ActionButton(string text, Action action, bool filled = false)
 {
  var button = new Button { Content = text, HorizontalContentAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 0, 0, 6), Padding = new Thickness(12, 10, 12, 10) };
  if (filled) button.SetResourceReference(BackgroundProperty, "Sidebar");
  button.Click += (_, _) => action();
  return button;
 }
 void Heading(string text) => SheetContent.Children.Add(new TextBlock { Text = text, FontSize = 12, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 12, 0, 10), Foreground = Brush("Muted") });
 void Choices(string caption, string[] choices, string current, Action<string> choose)
 {
  Heading(caption);
  var row = new System.Windows.Controls.Primitives.UniformGrid { Columns = choices.Length, Margin = new Thickness(0, 0, 0, 10) };
  foreach (string choice in choices) {
   var b = new Button { Content = choice, Margin = new Thickness(0, 0, 5, 0), Padding = new Thickness(8, 9, 8, 9), BorderThickness = new Thickness(1), BorderBrush = Brush("Line") };
   b.SetResourceReference(BackgroundProperty, current == choice ? "Wash" : "Surface");
   b.Click += (_, _) => { choose(choice); SaveLater(); ShowSettings(); };
   row.Children.Add(b);
  }
  SheetContent.Children.Add(row);
 }
 void ShowAddress(string initial, bool tabsOnly = false)
 {
  if(shellReady){ShellOpen(tabsOnly?"tabs":"address",initial);return;}
  OpenSheet(tabsOnly ? "tabs" : "address", tabsOnly ? "Find a tab" : "Go somewhere");
  var input = new TextBox { Text = initial, FontSize = 18, Height = 48, Padding = new Thickness(10, 0, 10, 0), VerticalContentAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 0, 10) };
  System.Windows.Automation.AutomationProperties.SetName(input, tabsOnly ? "Find a tab" : "Search or enter an address");
  var entry = new DockPanel();
  var go = new Button { Content = "→", FontSize = 22, Width = 44, Margin = new Thickness(6,0,0,10), ToolTip = "Go" };
  System.Windows.Automation.AutomationProperties.SetName(go, "Go");
  DockPanel.SetDock(go, Dock.Right); entry.Children.Add(go); entry.Children.Add(input); SheetContent.Children.Add(entry);
  var results = new StackPanel();
  SheetContent.Children.Add(results);
  SheetContent.Children.Add(new Border { Height = 1, Background = Brush("Line"), Margin = new Thickness(0, 15, 0, 12) });
  SheetContent.Children.Add(Note(tabsOnly ? "Type to filter your open tabs. ↑ ↓ to choose. Enter to switch." : Prefs.SearchEngine + " · Enter to go. ↑ ↓ to choose. Esc to close.", 11));
  var actions = new List<Action>();
  var buttons = new List<Button>();
  int selected = -1;
  void Highlight() { for (int i = 0; i < buttons.Count; i++) buttons[i].SetResourceReference(BackgroundProperty, i == selected ? "Wash" : "Surface"); }
  void Fill()
  {
   results.Children.Clear(); actions.Clear(); buttons.Clear(); selected = -1;
   var text = input.Text.Trim();
   void Result(string title, string detail, Action action) {
    var stack = new StackPanel();
    stack.Children.Add(new TextBlock { Text = title, TextTrimming = TextTrimming.CharacterEllipsis, MaxWidth = 435 });
    stack.Children.Add(new TextBlock { Text = detail, FontSize = 11, Foreground = Brush("Muted"), TextTrimming = TextTrimming.CharacterEllipsis, MaxWidth = 435, Margin = new Thickness(0, 3, 0, 0) });
    var b = new Button { Content = stack, HorizontalContentAlignment = HorizontalAlignment.Left, Padding = new Thickness(10, 9, 10, 9), Margin = new Thickness(0, 2, 0, 0) };
    b.Click += (_, _) => action(); buttons.Add(b); actions.Add(action); results.Children.Add(b);
   }
   foreach (var tab in tabs.Where(t => text.Length == 0 || t.Title.Contains(text, StringComparison.OrdinalIgnoreCase) || t.Url.Contains(text, StringComparison.OrdinalIgnoreCase)).Take(tabsOnly ? 12 : 4))
    Result(tab.Title, (tab.Private ? "Private tab" : "Switch to tab") + (tab.Url.Length > 0 ? " · " + Host(tab.Url) : ""), async () => await SelectTab(tab));
   if (!tabsOnly && text.Length > 0) {
    var seen = new HashSet<string>();
    foreach (var item in state.Bookmarks.Concat(state.History).Where(h => h.Title.Contains(text, StringComparison.OrdinalIgnoreCase) || h.Url.Contains(text, StringComparison.OrdinalIgnoreCase)).Where(h => seen.Add(h.Url)).Take(Math.Max(0, 7 - actions.Count)))
     Result(item.Title, item.Url, async () => await Navigate(item.Url));
   }
   if (tabsOnly && actions.Count == 0) results.Children.Add(Note("No matching tabs."));
   if (!tabsOnly && text.Length == 0 && actions.Count == 0) results.Children.Add(Note("An address, a question, anything."));
  }
  go.Click += async (_, _) => { if (tabsOnly && actions.Count > 0) actions[Math.Max(0, selected)](); else if (!tabsOnly) await Navigate(input.Text); };
  input.TextChanged += (_, _) => Fill();
  input.PreviewKeyDown += async (_, e) => {
   if (e.Key is Key.Down or Key.Up) { e.Handled = true; if (actions.Count > 0) selected = (selected + (e.Key == Key.Down ? 1 : -1) + actions.Count) % actions.Count; Highlight(); }
   if (e.Key == Key.Enter) {
    e.Handled = true;
    if (selected >= 0 && selected < actions.Count) actions[selected]();
    else if (tabsOnly && actions.Count > 0) actions[0]();
    else if (!tabsOnly) await Navigate(input.Text);
   }
  };
  Fill(); Dispatcher.BeginInvoke(() => { input.Focus(); input.SelectAll(); });
 }
 void ShowSettings()
 {
  if(shellReady){ShellOpen("settings");return;}
  OpenSheet("settings", "Make yourself at home.");
  SheetContent.Children.Add(Note("Still. A quiet browser."));
  Choices("Appearance", ["Light", "Dark", "System"], Prefs.Theme, s => { Prefs.Theme = s; ApplyTheme(); });
  Choices("Tabs", ["Sidebar", "Top"], Prefs.Layout, s => { Prefs.Layout = s; ApplyLayout(); });
  Choices("Search with", ["DuckDuckGo", "Google", "Bing"], Prefs.SearchEngine, s => Prefs.SearchEngine = s);
  Choices("Restore tabs when Still opens", ["On", "Off"], Prefs.RestoreTabs ? "On" : "Off", s => Prefs.RestoreTabs = s == "On");
  Choices("Block common ads and trackers", ["On", "Off"], Prefs.Blocking ? "On" : "Off", s => { Prefs.Blocking = s == "On"; Toast("Applies to new requests. Reload an open page to see the change."); });
  Heading("Downloads");
  SheetContent.Children.Add(Note(Prefs.DownloadFolder, 12));
  SheetContent.Children.Add(ActionButton("Choose download folder", () => {
   var dialog = new OpenFolderDialog { Title = "Choose your download folder", InitialDirectory = Prefs.DownloadFolder };
   if (dialog.ShowDialog(this) == true) { Prefs.DownloadFolder = dialog.FolderName; foreach (var tab in tabs) if (tab.View?.CoreWebView2 is { } c) c.Profile.DefaultDownloadFolderPath = Prefs.DownloadFolder; SaveLater(); ShowSettings(); }
  }, true));
  Heading("Your browser");
  SheetContent.Children.Add(ActionButton("Keyboard shortcuts", ShowShortcuts));
  SheetContent.Children.Add(ActionButton("Import bookmarks from an HTML file", ImportBookmarks));
  SheetContent.Children.Add(ActionButton("Export bookmarks", ExportBookmarks));
  SheetContent.Children.Add(ActionButton("Clear browsing history", () => {
   if (MessageBox.Show(this, "Clear Still's browsing history? Your bookmarks and open tabs stay.", "Clear history", MessageBoxButton.YesNo) == MessageBoxResult.Yes) { state.History.Clear(); Save(); Toast("Browsing history cleared."); }
  }));
  SheetContent.Children.Add(ActionButton("Clear cookies and website data", async () => {
   if (MessageBox.Show(this, "This signs you out of websites in Still. Continue?", "Clear website data", MessageBoxButton.YesNo) != MessageBoxResult.Yes) return;
   var normal = tabs.FirstOrDefault(t => !t.Private && t.View?.CoreWebView2 != null);
   if (normal?.View?.CoreWebView2 is { } c) { await c.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.AllSite); Toast("Cookies and website data cleared."); }
   else Toast("Open a regular web page first, then clear its profile.");
  }));
  SheetContent.Children.Add(ActionButton("About Still", ShowAbout));
 }
 void ShowAbout()
 {
  if(shellReady){ShellOpen("about");return;}
  OpenSheet("about", "still.");
  SheetContent.Children.Add(Note("Version 1.0\nA native Windows browser with room to breathe.", 15));
  Heading("Inspired by Search");
  SheetContent.Children.Add(Note("The quiet interface of Search by Office Commun inspired Still. This is an independent Windows implementation with its own identity."));
  SheetContent.Children.Add(ActionButton("Visit the original Search", async () => await NewTab("https://officecommun.com/search", false, false), true));
  Heading("Built here");
  SheetContent.Children.Add(Note("Your tabs, history and bookmarks stay in your Windows user profile. Still has no account, telemetry, or cloud sync. Websites have their own privacy policies. Microsoft's WebView2 runtime is maintained and updated separately."));
  SheetContent.Children.Add(Note("Still uses Microsoft WebView2 and Mozilla Readability. This first release does not include extension installation, browser-data migration, or a Still updater."));
  SheetContent.Children.Add(ActionButton("Open Still's data folder", () => Process.Start(new ProcessStartInfo("explorer.exe", App.DataRoot) { UseShellExecute = true })));
 }
 void ShowShortcuts()
 {
  if(shellReady){ShellOpen("shortcuts");return;}
  OpenSheet("shortcuts", "A few good shortcuts.");
  string[][] rows = [
   ["Go to an address", "Ctrl L"], ["Find an open tab", "Ctrl K"], ["New tab", "Ctrl T"], ["Private tab", "Ctrl Shift N"],
   ["Close / sleep pinned tab", "Ctrl W"], ["Reopen closed tab", "Ctrl Shift T"], ["Next / previous tab", "Ctrl Tab / Ctrl Shift Tab"],
   ["Jump to a tab", "Ctrl 1 … 9"], ["Pin / unpin", "Ctrl Shift P"], ["Bookmark page", "Ctrl D"],
   ["Bookmarks", "Ctrl Shift B"], ["History", "Ctrl H"], ["Downloads", "Ctrl J"], ["Find in page", "Ctrl F"],
   ["Reading mode", "Ctrl Shift R"], ["Hide an element", "Ctrl Shift H"], ["Sidebar / top tabs", "Ctrl Shift S"],
   ["Focus mode", "Ctrl Shift F"], ["Settings", "Ctrl ,"], ["Back / forward", "Alt ← / →"], ["Zoom", "Ctrl + / − / 0"]
  ];
  foreach (var row in rows) {
   var g = new Grid { Margin = new Thickness(0, 0, 0, 13) };
   g.Children.Add(new TextBlock { Text = row[0] });
   g.Children.Add(new TextBlock { Text = row[1], HorizontalAlignment = HorizontalAlignment.Right, Foreground = Brush("Muted"), FontSize = 12 });
   SheetContent.Children.Add(g);
  }
 }
 void ToggleBookmark()
 {
  if (active == null || active.Url.Length == 0) return;
  if (state.Bookmarks.Any(b => b.Url == active.Url)) { state.Bookmarks.RemoveAll(b => b.Url == active.Url); Toast("Bookmark removed."); }
  else { state.Bookmarks.Add(new Visit { Title = active.Title, Url = active.Url, Favicon = active.Private || active.Favicon.Length == 0 ? null : active.Favicon }); Toast("Page bookmarked."); }
  SaveLater(); UpdateChrome();
 }
 void ShowLibrary(bool bookmarks)
 {
  if(shellReady){ShellOpen(bookmarks?"bookmarks":"history");return;}
  OpenSheet(bookmarks ? "bookmarks" : "history", bookmarks ? "Saved for later." : "Where you've been.");
  var input = new TextBox { Margin = new Thickness(0,0,0,16) };
  System.Windows.Automation.AutomationProperties.SetName(input, bookmarks ? "Search bookmarks" : "Search history");
  SheetContent.Children.Add(input);
  SheetContent.Children.Add(Note(bookmarks ? "Your bookmarks. Type above to filter." : "Your most recent visits. Type above to filter.", 12));
  var list = new StackPanel(); SheetContent.Children.Add(list);
  void Fill() {
   list.Children.Clear();
   var source = bookmarks ? state.Bookmarks : state.History;
   var found = source.Where(v => (v.Title + v.Url).Contains(input.Text, StringComparison.OrdinalIgnoreCase)).Take(100).ToList();
   if (found.Count == 0) { list.Children.Add(Note(bookmarks ? "No bookmarks yet. Press Ctrl D on a page to save it." : "No visits here yet.")); return; }
   foreach (var visit in found) {
    var row = new DockPanel { Margin = new Thickness(0,0,0,3) };
    var del = ActionButton("×", () => { source.Remove(visit); SaveLater(); Fill(); UpdateChrome(); });
    del.ToolTip = "Remove"; DockPanel.SetDock(del, Dock.Right); row.Children.Add(del);
    var content = new StackPanel();
    content.Children.Add(new TextBlock { Text = visit.Title, TextTrimming = TextTrimming.CharacterEllipsis, MaxWidth = 400 });
    content.Children.Add(new TextBlock { Text = Host(visit.Url) + (bookmarks ? "" : " · " + visit.At.ToString("MMM d, HH:mm")), FontSize = 11, Foreground = Brush("Muted"), Margin = new Thickness(0,3,0,0) });
    var b = new Button { Content = content, HorizontalContentAlignment = HorizontalAlignment.Left, Padding = new Thickness(8, 9, 8, 9) };
    b.Click += async (_, _) => await Navigate(visit.Url); row.Children.Add(b); list.Children.Add(row);
   }
  }
  input.TextChanged += (_, _) => Fill(); Fill(); Dispatcher.BeginInvoke(() => input.Focus());
 }
 void ShowDownloads()
 {
  if(shellReady){ShellOpen("downloads");return;}
  OpenSheet("downloads", "Downloads");
  SheetContent.Children.Add(ActionButton("Open download folder", () => { Directory.CreateDirectory(Prefs.DownloadFolder); Process.Start(new ProcessStartInfo("explorer.exe", Prefs.DownloadFolder) { UseShellExecute = true }); }, true));
  SheetContent.Children.Add(ActionButton("Refresh", ShowDownloads));
  if (downloads.Count == 0) SheetContent.Children.Add(Note("Downloads from this session will appear here."));
  foreach (var item in downloads.Where(d => !d.Private || active?.Private == true)) {
   var operation = item.Operation;
   string status = operation.State == CoreWebView2DownloadState.Completed ? "Complete" : operation.State == CoreWebView2DownloadState.Interrupted ? "Interrupted · " + operation.InterruptReason : $"{operation.BytesReceived / 1024:N0} KB received";
   Heading(Path.GetFileName(item.Path)); SheetContent.Children.Add(Note(status, 12));
   if (operation.State == CoreWebView2DownloadState.InProgress) SheetContent.Children.Add(ActionButton("Cancel download", () => { operation.Cancel(); ShowDownloads(); }));
   else if (operation.State == CoreWebView2DownloadState.Completed) SheetContent.Children.Add(ActionButton("Show in folder", () => Process.Start(new ProcessStartInfo("explorer.exe", "/select,\"" + item.Path + "\"") { UseShellExecute = true })));
   else if (operation.CanResume) SheetContent.Children.Add(ActionButton("Resume", () => { operation.Resume(); ShowDownloads(); }));
  }
 }
 void ShowSiteControls()
 {
  if(shellReady){ShellOpen("site");return;}
  if (active == null || active.Url.Length == 0) { Toast("Open a website to see its controls."); return; }
  var tab = active; string host = new Uri(tab.Url).Host;
  OpenSheet("site", Host(tab.Url));
  SheetContent.Children.Add(Note(tab.Url.StartsWith("https://") ? "The connection to this site uses HTTPS." : "This page does not use an HTTPS connection."));
  Heading("Less noise");
  SheetContent.Children.Add(Note($"{tab.Blocked} common ad or tracker requests blocked on this page.\nThe built-in list is small; it does not block every ad.", 12));
  bool exempt = Prefs.UnblockedHosts.Contains(host);
  SheetContent.Children.Add(ActionButton(exempt ? "Turn blocking on for this site" : "Turn blocking off for this site", () => {
   if (exempt) Prefs.UnblockedHosts.Remove(host); else Prefs.UnblockedHosts.Add(host);
   SaveLater(); CloseSheet(); tab.View?.CoreWebView2?.Reload();
  }, true));
  SheetContent.Children.Add(ActionButton("Hide something on this page", async () => { CloseSheet(); await PickHidden(); }));
  SheetContent.Children.Add(ActionButton("Restore hidden elements on this site", async () => {
   state.Hidden.Remove(host); SaveLater(); foreach (var t in tabs.Where(t => t.View?.CoreWebView2 != null)) await InstallHiddenRules(t);
   CloseSheet(); tab.View?.CoreWebView2?.Reload(); Toast("Hidden elements restored.");
  }));
  SheetContent.Children.Add(ActionButton(tab.View?.CoreWebView2?.IsMuted == true ? "Unmute site" : "Mute site", () => {
   if (tab.View?.CoreWebView2 is { } c) { c.IsMuted = !c.IsMuted; ShowSiteControls(); }
  }));
  SheetContent.Children.Add(ActionButton("Pin / unpin this tab", () => { tab.Pinned = !tab.Pinned; RenderTabs(); SaveLater(); Toast(tab.Pinned ? "Tab pinned." : "Tab unpinned."); }));
 }
 void ShowError(string title, string detail)
 {
  if(shellReady){ShellSend(new{kind="toast",message=title+" "+detail});return;}
  OpenSheet("error", title); SheetContent.Children.Add(Note(detail));
  SheetContent.Children.Add(ActionButton("Get Microsoft's WebView2 Runtime", () => Process.Start(new ProcessStartInfo("https://developer.microsoft.com/en-us/microsoft-edge/webview2/") { UseShellExecute = true }), true));
 }
 void AddMenu(ContextMenu menu, string label, Action action, string shortcut = "")
 {
  var item = new MenuItem { Header = label, InputGestureText = shortcut };
  item.Click += (_, _) => action(); menu.Items.Add(item);
 }
 void ShowMenu(Button button)
 {
  var m = new ContextMenu();
  AddMenu(m, "New tab", async () => await NewTab(), "Ctrl T");
  AddMenu(m, "New private tab", async () => await NewTab("", true), "Ctrl Shift N");
  AddMenu(m, "Reopen closed tab", ReopenTab, "Ctrl Shift T");
  m.Items.Add(new Separator());
  AddMenu(m, "Bookmarks", () => ShowLibrary(true), "Ctrl Shift B");
  AddMenu(m, "History", () => ShowLibrary(false), "Ctrl H");
  AddMenu(m, "Downloads", ShowDownloads, "Ctrl J");
  AddMenu(m, "Find in page", ShowFind, "Ctrl F");
  AddMenu(m, "Reading mode", async () => await ToggleReader(), "Ctrl Shift R");
  AddMenu(m, "Picture in picture", async () => await PictureInPicture());
  m.Items.Add(new Separator());
  AddMenu(m, "Pin / unpin tab", () => { if (active != null) { active.Pinned = !active.Pinned; RenderTabs(); SaveLater(); } }, "Ctrl Shift P");
  AddMenu(m, "Switch tab layout", () => { Prefs.Layout = Prefs.Layout == "Sidebar" ? "Top" : "Sidebar"; ApplyLayout(); }, "Ctrl Shift S");
  AddMenu(m, "Focus mode", () => { focusMode = !focusMode; ApplyLayout(); }, "Ctrl Shift F");
  AddMenu(m, "Settings", ShowSettings, "Ctrl ,");
  m.PlacementTarget = button; m.IsOpen = true;
 }
 async void ReopenTab()
 {
  if (closedTabs.Count == 0) { Toast("No closed tabs to reopen."); return; }
  var tab = closedTabs.Pop(); tabs.Add(tab); await SelectTab(tab);
 }
 async void ImportBookmarks()
 {
  var dialog = new OpenFileDialog { Title = "Import bookmarks", Filter = "Bookmarks HTML|*.html;*.htm" };
  if (dialog.ShowDialog(this) != true) return;
  try {
   var html = await File.ReadAllTextAsync(dialog.FileName);
   int count = 0;
   foreach (System.Text.RegularExpressions.Match match in System.Text.RegularExpressions.Regex.Matches(html, "<a\\s+[^>]*href\\s*=\\s*[\"'](?<url>[^\"']+)[\"'][^>]*>(?<title>.*?)</a>", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.Singleline)) {
    string url = System.Net.WebUtility.HtmlDecode(match.Groups["url"].Value);
    string title = System.Net.WebUtility.HtmlDecode(System.Text.RegularExpressions.Regex.Replace(match.Groups["title"].Value, "<[^>]+>", ""));
    if (Uri.TryCreate(url, UriKind.Absolute, out var u) && u.Scheme is "https" or "http" && !state.Bookmarks.Any(b => b.Url == url)) { state.Bookmarks.Add(new Visit { Url = url, Title = title }); count++; }
   }
   SaveLater(); Toast($"Imported {count} bookmarks."); ShowLibrary(true);
  } catch (Exception ex) { Toast("Couldn't import bookmarks: " + ex.Message); }
 }
 void ExportBookmarks()
 {
  var dialog = new SaveFileDialog { Title = "Export bookmarks", FileName = "Still bookmarks.html", Filter = "HTML|*.html" };
  if (dialog.ShowDialog(this) != true) return;
  try {
   var lines = state.Bookmarks.Select(b => $"<DT><A HREF=\"{System.Net.WebUtility.HtmlEncode(b.Url)}\">{System.Net.WebUtility.HtmlEncode(b.Title)}</A>");
   File.WriteAllText(dialog.FileName, "<!DOCTYPE NETSCAPE-Bookmark-file-1><META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\"><TITLE>Still bookmarks</TITLE><H1>Still bookmarks</H1><DL><p>\n" + string.Join("\n", lines) + "\n</DL>");
   Toast("Bookmarks exported.");
  } catch (Exception ex) { Toast("Couldn't export bookmarks: " + ex.Message); }
 }
}

