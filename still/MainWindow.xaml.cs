using System.IO;
using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using Microsoft.Win32;

namespace Still;
public partial class MainWindow : Window
{
 readonly StateStore store = new();
 readonly SavedState state;
 readonly List<BrowserTab> tabs = [];
 readonly Stack<BrowserTab> closedTabs = [];
 readonly List<DownloadItem> downloads = [];
 readonly DispatcherTimer saveTimer = new() { Interval = TimeSpan.FromMilliseconds(450) };
 readonly DispatcherTimer toastTimer = new() { Interval = TimeSpan.FromSeconds(5) };
 readonly string privateProfile = "Private" + Guid.NewGuid().ToString("N");
 BrowserTab? active;
 bool dark, closing, focusMode;
 string panel = "";
 Preferences Prefs => state.Preferences;
 [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
 public MainWindow()
 {
  InitializeComponent();
  Frame.Visibility=Visibility.Collapsed;Background=Brushes.Black;
  state = store.Load();
  if(state.UiVersion<2){state.Preferences.Theme="Dark";state.UiVersion=2;}
  if(state.UiVersion<3){state.Preferences.SearchEngine="Google";state.UiVersion=3;}
  Width = Math.Clamp(Prefs.Width, MinWidth, Math.Max(MinWidth, SystemParameters.WorkArea.Width - 60));
  Height = Math.Clamp(Prefs.Height, MinHeight, Math.Max(MinHeight, SystemParameters.WorkArea.Height - 60));
  if (App.IsQa) Prefs.DownloadFolder = Path.Combine(App.DataRoot, "Downloads");
  tabs.AddRange(state.Tabs.Where(t => !string.IsNullOrEmpty(t.Id) && (Prefs.RestoreTabs || t.Pinned)));
  saveTimer.Tick += (_, _) => { saveTimer.Stop(); Save(); };
  // Memory saver: background tabs idle for 5+ minutes are suspended (scripts frozen, page kept intact, no reload).
  var suspendTimer = new DispatcherTimer { Interval = TimeSpan.FromMinutes(1) };
  suspendTimer.Tick += async (_, _) => {
   if (!Prefs.MemorySaver || closing) return;
   foreach (var t in tabs.ToArray()) {
    if (t == active || t.Loading || t.View?.CoreWebView2 is not { } c || c.IsSuspended || c.IsDocumentPlayingAudio) continue;
    if (DateTime.UtcNow - t.LastActive < TimeSpan.FromMinutes(5) || permissions.Any(p => p.Tab == t)) continue;
    try { if (await c.TrySuspendAsync()) ShellPublish(); } catch (Exception ex) when (ex is InvalidOperationException or System.Runtime.InteropServices.COMException) { }
   }
  };
  suspendTimer.Start();
  toastTimer.Tick += (_, _) => { toastTimer.Stop(); ToastBar.Visibility = Visibility.Collapsed; };
  WindowState = WindowState.Maximized; // open maximized by default (above the taskbar)
  SourceInitialized += (_, _) => { var h = new WindowInteropHelper(this).Handle; InitializeFullScreen(); int round = 2; DwmSetWindowAttribute(h, 33, ref round, 4); ApplyTheme(); };
  Loaded += async (_, _) => {
   try { await InitializeShell(); }
   catch(Exception ex) { if(closing)return;App.Log(ex);MessageBox.Show(this,"Still couldn't start its interface.\n\n"+(ex is WebView2RuntimeNotFoundException ? "Install Microsoft's WebView2 Evergreen Runtime, then reopen Still." : ex.Message),"Still");Close();return; }
   if(closing)return;
   ApplyTheme(); ApplyLayout();
   if (tabs.Count == 0) tabs.Add(new BrowserTab());
   await SelectTab(tabs.FirstOrDefault(t => t.Id == state.ActiveId) ?? tabs.First());
   StartUpdateChecks();
   if (LaunchUrl != null) await NewTab(LaunchUrl, false, false);
   if (store.Recovered) Toast("Recovered your saved session. A backup is kept in your profile.");
#if STILL_QA
   if (App.IsQa) StartQa();
#endif
  };
  Closing += (_, _) => {
   closing = true; saveTimer.Stop();
   if(IsFullScreen){Prefs.Width=fullScreenRestoreBounds.Width;Prefs.Height=fullScreenRestoreBounds.Height;}
   else if (WindowState == WindowState.Normal) { Prefs.Width = ActualWidth; Prefs.Height = ActualHeight; }
   Save(); foreach (var tab in tabs) { tab.Closed = true; tab.View?.Dispose(); }
   managementView?.Dispose();shellView?.Dispose();loginOffer=null;importBatch=null;ClearOwnedPasswordClipboard();
  };
  SizeChanged += (_, _) => { Sheet.Width = Math.Max(320, Math.Min(550, ContentArea.ActualWidth - 40)); Sheet.MaxHeight = Math.Max(250, PageArea.ActualHeight - 60); };
  StateChanged+=(_,_)=>{RestorePageWindow();ShellPublish();};
  SystemEvents.UserPreferenceChanged += SystemPreferenceChanged;
  Closed += (_, _) => SystemEvents.UserPreferenceChanged -= SystemPreferenceChanged;
 }
 public string? LaunchUrl { get; init; }
 DateTime lastDownloadPublish;
 // A link opened from another app while Still is running.
 public async void OpenFromOutside(string url)
 {
  if (closing) return;
  if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal;
  Activate(); Topmost = !Topmost; Topmost = !Topmost;
  if (url.Length > 0 && shellReady) await NewTab(url, false, false);
 }
 void SystemPreferenceChanged(object sender, UserPreferenceChangedEventArgs e) { if (Prefs.Theme == "System") Dispatcher.BeginInvoke(ApplyTheme); }
 void SaveLater() { if (!closing) { saveTimer.Stop(); saveTimer.Start(); ShellPublish(); } }
 void Save()
 {
  state.Tabs = tabs.Where(t => !t.Private).ToList();
  state.ActiveId = active?.Private == false ? active.Id : tabs.FirstOrDefault(t => !t.Private)?.Id;
  store.Save(state);
 }
 void Toast(string message) { if(shellReady){ShellSend(new{kind="toast",message});return;} ToastText.Text = message; ToastBar.Visibility = Visibility.Visible; toastTimer.Stop(); toastTimer.Start(); }
 SolidColorBrush Brush(string name) => (SolidColorBrush)FindResource(name);
 void ApplyTheme()
 {
  dark = Prefs.Theme == "Dark" || (Prefs.Theme == "System" && (int?)Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 1) == 0);
  var colors = dark
   ? new[] { "#080808", "#000000", "#080808", "#EFEFEA", "#A5A6A0", "#292929", "#222222", "#191919" }
   : new[] { "#FAFAF9", "#FFFFFF", "#F2F2F0", "#272826", "#71726E", "#E3E3DF", "#E0E2DB", "#ECEDE8" };
  string[] keys = ["Ground", "Surface", "Sidebar", "Ink", "Muted", "Line", "Wash", "Hover"];
  for (int i = 0; i < keys.Length; i++) Application.Current.Resources[keys[i]] = new SolidColorBrush((Color)ColorConverter.ConvertFromString(colors[i]));
  int theme = dark ? 1 : 0;
  DwmSetWindowAttribute(new WindowInteropHelper(this).Handle, 20, ref theme, 4);
  foreach (var tab in tabs) if (tab.View?.CoreWebView2 is { } core) core.Profile.PreferredColorScheme = dark ? CoreWebView2PreferredColorScheme.Dark : CoreWebView2PreferredColorScheme.Light;
  RenderTabs(); UpdateChrome(); SaveLater();
 }
 void ApplyLayout()
 {
  bool side = Prefs.Layout == "Sidebar" && !focusMode;
  SideColumn.Width = new GridLength(side ? 220 : 0);
  SidebarPanel.Visibility = side ? Visibility.Visible : Visibility.Collapsed;
  StripRow.Height = new GridLength(!side && !focusMode ? 42 : 0);
  RenderTabs(); SaveLater();
 }
 void RenderTabs()
 {
  if(shellView!=null){ShellPublish();return;}
  TabPanel.Children.Clear(); PinPanel.Children.Clear(); TopTabs.Children.Clear();
  foreach (var tab in tabs.OrderByDescending(t => t.Pinned))
  {
   if (tab.Pinned) PinPanel.Children.Add(TabButton(tab, true, false));
   else TabPanel.Children.Add(TabButton(tab, false, false));
   TopTabs.Children.Add(TabButton(tab, tab.Pinned, true));
  }
  PinPanel.Visibility = tabs.Any(t => t.Pinned) ? Visibility.Visible : Visibility.Collapsed;
  var add = new Button { Content = "+", FontSize = 20, Width = 34, Padding = new Thickness(0), ToolTip = "New tab · Ctrl + T" };
  add.Click += async (_, _) => await NewTab();
  TopTabs.Children.Add(add);
 }
 Button TabButton(BrowserTab tab, bool pin, bool horizontal)
 {
  var b = new Button { Margin = new Thickness(0, 0, 4, 4), Height = pin && !horizontal ? 42 : 34, Padding = new Thickness(pin ? 0 : 9, 0, pin ? 0 : 5, 0), HorizontalContentAlignment = HorizontalAlignment.Stretch, ToolTip = tab.Title + (tab.Url.Length > 0 ? "\n" + tab.Url : ""), AllowDrop = true };
  b.SetResourceReference(BackgroundProperty, tab == active ? "Wash" : pin ? "Hover" : "Sidebar");
  if (pin) { b.Width = horizontal ? 38 : 42; b.Content = new TextBlock { Text = Initial(tab), FontWeight = FontWeights.SemiBold, FontSize = 15, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center }; }
  else {
   if (horizontal) b.Width = 185;
   var g = new Grid(); g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(24) }); g.ColumnDefinitions.Add(new ColumnDefinition()); g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(23) });
   var letter = new TextBlock { Text = tab.Private ? "\uE72E" : Initial(tab), FontSize = 11, FontWeight = FontWeights.SemiBold, VerticalAlignment = VerticalAlignment.Center, Foreground = Brush("Muted") };
   if (tab.Private) letter.FontFamily = new FontFamily("Segoe MDL2 Assets");
   var label = new TextBlock { Text = tab.Title, TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center, Foreground = tab == active ? Brush("Ink") : Brush("Muted") };
   Grid.SetColumn(label, 1);
   var close = new Button { Content = "×", FontSize = 16, Padding = new Thickness(0), Width = 21, Height = 24, Opacity = tab == active ? 0.7 : 0, ToolTip = "Close tab" };
   System.Windows.Automation.AutomationProperties.SetName(close, "Close " + tab.Title);
   Grid.SetColumn(close, 2); close.Click += async (_, e) => { e.Handled = true; await CloseTab(tab); };
   b.MouseEnter += (_, _) => close.Opacity = 0.85; b.MouseLeave += (_, _) => close.Opacity = tab == active ? 0.7 : 0;
   g.Children.Add(letter); g.Children.Add(label); g.Children.Add(close); b.Content = g;
  }
  System.Windows.Automation.AutomationProperties.SetName(b, (pin ? "Pinned " : "Tab ") + tab.Title);
  b.Click += async (_, _) => await SelectTab(tab);
  b.PreviewMouseDown += async (_, e) => { if (e.ChangedButton == MouseButton.Middle) { e.Handled = true; await CloseTab(tab); } };
  b.ContextMenu = TabMenu(tab);
  Point start = new();
  b.PreviewMouseLeftButtonDown += (_, e) => start = e.GetPosition(b);
  b.MouseMove += (_, e) => { if (e.LeftButton == MouseButtonState.Pressed && (e.GetPosition(b) - start).Length > 10) DragDrop.DoDragDrop(b, new DataObject("StillTab", tab.Id), DragDropEffects.Move); };
  b.Drop += (_, e) => { if (e.Data.GetData("StillTab") is string id && tabs.FirstOrDefault(t => t.Id == id) is { } moved && moved != tab) { tabs.Remove(moved); tabs.Insert(tabs.IndexOf(tab), moved); RenderTabs(); SaveLater(); } };
  return b;
 }
 static string Initial(BrowserTab tab) { var title = tab.Title.Trim(); return title.Length == 0 || title == "New tab" ? "·" : System.Globalization.StringInfo.GetNextTextElement(title).ToUpperInvariant(); }
 ContextMenu TabMenu(BrowserTab tab)
 {
  var menu = new ContextMenu();
  AddMenu(menu, tab.Pinned ? "Unpin tab" : "Pin tab", () => { tab.Pinned = !tab.Pinned; RenderTabs(); SaveLater(); });
  AddMenu(menu, "Duplicate", async () => await NewTab(tab.Url, tab.Private, false));
  AddMenu(menu, tab.View?.CoreWebView2?.IsMuted == true ? "Unmute" : "Mute", () => { if (tab.View?.CoreWebView2 is { } c) c.IsMuted = !c.IsMuted; });
  AddMenu(menu, "Put tab to sleep", async () => { DisposeView(tab); if (tab == active) await NewTab("", false, false); RenderTabs(); Toast("Tab is asleep. Select it to load it again."); });
  menu.Items.Add(new Separator());
  AddMenu(menu, "Close tab", async () => await CloseTab(tab, true));
  AddMenu(menu, "Close other unpinned tabs", async () => { foreach (var other in tabs.Where(t => t != tab && !t.Pinned).ToList()) await CloseTab(other, true); });
  return menu;
 }
 async Task<BrowserTab> NewTab(string url = "", bool isPrivate = false, bool prompt = true)
 {
  var tab = new BrowserTab { Url = url, Private = isPrivate, Title = isPrivate ? "Private tab" : "New tab" };
  tabs.Add(tab); await SelectTab(tab);
  if (prompt && url.Length == 0) ShowAddress("");
  SaveLater(); return tab;
 }
 async Task SelectTab(BrowserTab tab)
 {
  if (tab.Closed || !tabs.Contains(tab)) return;
  if(active!=tab&&contentFullScreen)await ExitContentFullScreen();
  CloseSheet(false);
  foreach (var t in tabs) if (t.View != null) t.View.Visibility = Visibility.Hidden;
  var leaving=active; if(leaving!=null)leaving.LastActive=DateTime.UtcNow;
  active = tab;tab.LastActive=DateTime.UtcNow;
  if(tab.View?.CoreWebView2 is {IsSuspended:true} sleeping)sleeping.Resume(); // instant: page state was kept
  foreach(var t in tabs)if(t.View?.CoreWebView2 is {} memory)memory.MemoryUsageTargetLevel=Prefs.MemorySaver&&t!=tab?CoreWebView2MemoryUsageTargetLevel.Low:CoreWebView2MemoryUsageTargetLevel.Normal;
  StartPage.Visibility = tab.Url.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
  PrivateNote.Visibility = tab.Private ? Visibility.Visible : Visibility.Collapsed;
  Greeting.Text = tab.Private ? "A little privacy." : "Where to?";
  RenderTabs(); UpdateChrome(); SaveLater();
  if (tab.Url.Length > 0) await EnsureView(tab);
  if (active == tab && tab.View != null && panel == "") { tab.View.Visibility = Visibility.Visible;RestorePageWindow(); tab.View.Focus(); }
  if(active==tab)await InspectLogin(tab);
 }
 async Task CloseTab(BrowserTab tab, bool removePin = false)
 {
  if (tab.Pinned && !removePin) {
   DisposeView(tab);
   if (tab == active) { var next = tabs.FirstOrDefault(t => t != tab && !t.Pinned); if (next != null) await SelectTab(next); else await NewTab("", false, false); }
   Toast("Pinned tab put to sleep."); RenderTabs(); SaveLater(); return;
  }
  var index = tabs.IndexOf(tab);
  if (index < 0) return;
  if (!tab.Private) { closedTabs.Push(new BrowserTab { Url = tab.Url, Title = tab.Title, Pinned = tab.Pinned }); while (closedTabs.Count > 25) { var keep = closedTabs.Take(25).Reverse().ToArray(); closedTabs.Clear(); foreach (var t in keep) closedTabs.Push(t); } }
  tab.Closed = true; DisposeView(tab); tabs.Remove(tab);
  if (tabs.Count == 0) await NewTab("", false, false);
  else if (active == tab) await SelectTab(tabs[Math.Min(index, tabs.Count - 1)]);
  RenderTabs(); SaveLater();
 }
 void DisposeView(BrowserTab tab)
 {
  DropPermissions(tab);
  if(tab==active&&contentFullScreen){contentFullScreen=false;ApplyFullScreen();}
  if (tab.View is { } view) { WebHost.Children.Remove(view); view.Dispose(); tab.View = null; }
  tab.LoadingTask = null; tab.Loading = false; tab.Reader = false; tab.HideScriptId = null;tab.LoginScriptId=null;tab.LoginDetected=false;tab.LoginFilled=false;
 }
 async Task EnsureView(BrowserTab tab)
 {
  if (tab.View?.CoreWebView2 != null) return;
  if (tab.LoadingTask != null) { await tab.LoadingTask; return; }
  tab.LoadingTask = CreateView(tab);
  await tab.LoadingTask;
 }
 async Task CreateView(BrowserTab tab)
 {
  var view = new WebView2 {
   CreationProperties = new CoreWebView2CreationProperties { UserDataFolder = Path.Combine(App.DataRoot, "WebView"), ProfileName = tab.Private ? privateProfile : "Default", IsInPrivateModeEnabled = tab.Private },
   DefaultBackgroundColor = dark ? System.Drawing.Color.Black : System.Drawing.Color.White,
   Visibility = active == tab && panel == "" ? Visibility.Visible : Visibility.Hidden
  };
  tab.View = view; WebHost.Children.Add(view); tab.Loading = true; UpdateChrome();
  view.Loaded+=(_,_)=>RestorePageWindow();
  view.IsVisibleChanged+=(_,_)=>{if(view.IsVisible)Dispatcher.BeginInvoke(DispatcherPriority.Loaded,RestorePageWindow);};
  WebHost.UpdateLayout();
  try {
   var environment=await App.BrowserEnvironment;var options=environment.CreateCoreWebView2ControllerOptions();options.ProfileName=tab.Private?privateProfile:"Default";options.IsInPrivateModeEnabled=tab.Private;
   await view.EnsureCoreWebView2Async(environment,options);
   if (tab.Closed || tab.View != view || closing) return;
   view.UpdateWindowPos();RestorePageWindow();
   var core = view.CoreWebView2;
   core.Settings.IsStatusBarEnabled = false;
   core.Settings.IsZoomControlEnabled = true;
   core.Settings.AreBrowserAcceleratorKeysEnabled = true;
   ApplyProtection(core);
   core.FaviconChanged+=async(_,_)=>await UpdateFavicon(tab,core);
   core.ServerCertificateErrorDetected+=(_,e)=>{e.Action=CoreWebView2ServerCertificateErrorAction.Cancel;tab.CertificateError=true;tab.Secure=false;ShellPublish();};
   core.Profile.PreferredColorScheme = dark ? CoreWebView2PreferredColorScheme.Dark : CoreWebView2PreferredColorScheme.Light;
   if (Directory.Exists(Prefs.DownloadFolder)) core.Profile.DefaultDownloadFolderPath = Prefs.DownloadFolder;
   core.NavigationStarting += (_, e) => {
    tab.NavigationId=e.NavigationId;
    tab.LoginFilled=false;tab.LoginDetected=false;
    if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri)) { e.Cancel = true; return; }
    if (uri.Scheme is not ("http" or "https" or "about" or "data" or "blob" or "file" or "chrome-extension")) {
     e.Cancel = true;
     Dispatcher.BeginInvoke(() => ConfirmExternal(e.Uri));
     return;
    }
    if(Uri.TryCreate(tab.Url,UriKind.Absolute,out var previous)&&previous.Host!=uri.Host)tab.Favicon="";
    tab.Loading = true; tab.Reader = false; tab.HideToken = null; tab.Blocked = 0;tab.Secure=false;tab.CertificateError=false;
    if (uri.Scheme is "http" or "https" or "file") { tab.Url = e.Uri; tab.ShowingError = false; }
    if (tab == active) UpdateChrome();
   };
   core.SourceChanged += (_, _) => { if (!tab.Reader && !tab.ShowingError && core.Source != "about:blank") tab.Url = core.Source; if (tab == active) UpdateChrome(); SaveLater(); };
   core.DocumentTitleChanged += (_, _) => {
    if (!tab.Reader) tab.Title = string.IsNullOrWhiteSpace(core.DocumentTitle) ? Host(tab.Url) : core.DocumentTitle;
    RenderTabs(); if (tab == active) UpdateChrome(); SaveLater();
   };
   core.HistoryChanged += (_, _) => { if (tab == active) UpdateChrome(); };
   core.NavigationCompleted += (_, e) => {
    // A replaced navigation can finish with ConnectionAborted after a new page starts.
    if(e.NavigationId!=tab.NavigationId)return;
    // Cancelling a certificate error can leave the previous document displayed.
    // Keep the address tied to that document, not to the failed destination.
    var failedUrl=tab.Url;
    bool showError=!e.IsSuccess&&e.WebErrorStatus!=CoreWebView2WebErrorStatus.OperationCanceled;
    if(!e.IsSuccess&&!showError&&!string.IsNullOrEmpty(core.Source)&&core.Source!="about:blank")tab.Url=core.Source;
    tab.Secure=e.IsSuccess&&!tab.CertificateError&&Uri.TryCreate(tab.Url,UriKind.Absolute,out var secured)&&secured.Scheme=="https";
    tab.Loading = false; if (tab == active) UpdateChrome();
    if(e.IsSuccess)_=InspectLogin(tab);
    if (e.IsSuccess && !tab.ShowingError && !tab.Private && !tab.Reader && Uri.TryCreate(tab.Url, UriKind.Absolute, out var u) && u.Scheme is "https" or "http") {
     state.History.RemoveAll(v => v.Url == tab.Url && (DateTime.Now - v.At).TotalMinutes < 5);
     state.History.Insert(0, new Visit { Title = tab.Title, Url = tab.Url });
     if (state.History.Count > 2000) state.History.RemoveRange(2000, state.History.Count - 2000);
     SaveLater();
    }
    if(showError){
     // Show a full-page error for this cause; keep the address on the page that failed.
     tab.ShowingError=true;tab.Url=failedUrl;
     core.NavigateToString(ErrorPages.Html(e.WebErrorStatus,tab.CertificateError,failedUrl,dark,Prefs.SearchEngine));
     if(tab==active)UpdateChrome();
    }
   };
   core.NewWindowRequested += async (_, e) => {
    var deferral = e.GetDeferral(); e.Handled = true;
    try {
     if (!e.IsUserInitiated) { Toast("A pop-up was blocked."); return; }
     var child = await NewTab("about:blank", tab.Private, false);
     if (child.View?.CoreWebView2 is { } childCore) e.NewWindow = childCore;
    } catch (Exception ex) { App.Log(ex); Toast("Couldn't open this pop-up."); }
    finally { deferral.Complete(); }
   };
   core.DownloadStarting += (_, e) => {
    var operation = e.DownloadOperation;
    Directory.CreateDirectory(Prefs.DownloadFolder);
    string name = Path.GetFileName(e.ResultFilePath);
    if (string.IsNullOrEmpty(name)) name = "download";
    string path = Path.Combine(Prefs.DownloadFolder, name);
    for (int i = 1; File.Exists(path); i++) path = Path.Combine(Prefs.DownloadFolder, Path.GetFileNameWithoutExtension(name) + $" ({i})" + Path.GetExtension(name));
    e.ResultFilePath = path;
    downloads.Insert(0, new DownloadItem { Path = path, Operation = operation, Private = tab.Private });
    operation.StateChanged += (_, _) => {
     if (operation.State == CoreWebView2DownloadState.Completed) Toast("Downloaded " + Path.GetFileName(path));
     if (operation.State == CoreWebView2DownloadState.Interrupted) Toast("Download interrupted: " + operation.InterruptReason);
     ShellPublish();
    };
    // Keep the toolbar progress ring moving, at most ~4 updates a second.
    operation.BytesReceivedChanged += (_, _) => { if((DateTime.UtcNow-lastDownloadPublish).TotalMilliseconds>250){lastDownloadPublish=DateTime.UtcNow;ShellPublish();} };
    e.Handled=true;
    // Show the downloads card as soon as a download starts, like Chrome/Opera.
    if (shellReady) Dispatcher.BeginInvoke(() => ShellOpen("downloads")); else Toast("Downloading " + name);
    ShellPublish();
   };
   core.PermissionRequested += async (_, e) => {
    using var deferral=e.GetDeferral();
    // Ask inside Still (a bar above the page), never with a separate Windows dialog.
    var site=Host(e.Uri);var allow=await AskPermission(tab,string.IsNullOrWhiteSpace(site)?"This page":site,e.PermissionKind);
    e.State = allow ? CoreWebView2PermissionState.Allow : CoreWebView2PermissionState.Deny;
    e.SavesInProfile = !tab.Private; // remember the choice per site, like Chrome (reset in Privacy & security)
    // Dispose completes this deferral. Completing it explicitly as well causes
    // WebView2's E_ILLEGAL_METHOD_CALL after the prompt closes.
   };
   core.ProcessFailed += (_, e) => Dispatcher.BeginInvoke(() => { if (!tab.Closed) { DisposeView(tab); Toast("This page stopped responding. Reload it to continue."); UpdateChrome(); } });
   core.ContainsFullScreenElementChanged += (_, _) => { if(tab!=active||tab.Closed||closing)return;contentFullScreen=core.ContainsFullScreenElement;ApplyFullScreen(); };
   SetupBlocking(tab, core);
   await InstallHiddenRules(tab);
   await InstallLoginObserver(tab);
   core.WebMessageReceived += async (_, e) => await ReceiveHidden(tab, e);
   core.WebMessageReceived += async (_, e) => await ReceiveLogin(tab, e);
   core.Navigate(tab.Url);
  } catch (Exception ex) {
   if (closing || tab.Closed || tab.View != view) return;
   App.Log(ex); DisposeView(tab);
   if (tab == active) ShowError("The browser engine couldn't start.", ex is WebView2RuntimeNotFoundException ? "Install Microsoft's WebView2 Evergreen Runtime, then reopen Still." : ex.Message);
  } finally { if (tab.View == view) tab.LoadingTask = null; }
 }
 public static string Host(string url) => Uri.TryCreate(url, UriKind.Absolute, out var u) ? (u.IsFile ? Path.GetFileName(u.LocalPath) : u.Host.Replace("www.", "")) : url;
 public static string ResolveAddress(string input, string engine)
 {
  input = input.Trim();
  if (string.IsNullOrEmpty(input)) return "";
  if (Uri.TryCreate(input, UriKind.Absolute, out var explicitUri) && explicitUri.Scheme is "http" or "https" or "file") return explicitUri.AbsoluteUri;
  if (File.Exists(input)) return new Uri(Path.GetFullPath(input)).AbsoluteUri;
  if (!input.Any(char.IsWhiteSpace) && (input.Contains('.') || input.StartsWith("localhost", StringComparison.OrdinalIgnoreCase) || input.StartsWith("[::1]"))) {
   var scheme = input.StartsWith("localhost", StringComparison.OrdinalIgnoreCase) || input.StartsWith("127.") || input.StartsWith("[::1]") ? "http://" : "https://";
   if (Uri.TryCreate(scheme + input, UriKind.Absolute, out var domain) && domain.Host.Length > 0) return domain.AbsoluteUri;
  }
  return (engine == "Google" ? "https://www.google.com/search?q=" : engine == "Bing" ? "https://www.bing.com/search?q=" : "https://duckduckgo.com/?q=") + Uri.EscapeDataString(input);
 }
 async Task Navigate(string input)
 {
  string url = ResolveAddress(input, Prefs.SearchEngine);
  if (url.Length == 0) return;
  CloseSheet(false);
  if (active == null) await NewTab("", false, false);
  var tab = active!;
  if(Host(tab.Url)!=Host(url))tab.Favicon="";
  tab.Url = url; tab.Reader = false; StartPage.Visibility = Visibility.Collapsed;
  if (tab.View?.CoreWebView2 is { } core) core.Navigate(url); else await EnsureView(tab);
  if (tab.View != null && active == tab) { tab.View.Visibility = Visibility.Visible;RestorePageWindow(); tab.View.Focus(); }
  UpdateChrome(); SaveLater();
 }
 void UpdateChrome()
 {
  var core = active?.View?.CoreWebView2;
  BackButton.IsEnabled = core?.CanGoBack == true; ForwardButton.IsEnabled = core?.CanGoForward == true;
  ReloadButton.Content = active?.Loading == true ? "\uE711" : "\uE72C";
  LoadProgress.Visibility = active?.Loading == true && panel == "" ? Visibility.Visible : Visibility.Collapsed;
  var url = active?.Url ?? "";
  AddressLabel.Text = url.Length == 0 ? "Search or enter an address" : (active?.Private == true ? "Private · " : "") + Host(url);
  AddressButton.ToolTip = url.Length == 0 ? "Search or enter an address · Ctrl + L" : url + "\nCtrl + L to edit";
  SecurityGlyph.Text = url.StartsWith("https://") ? "\uE72E" : "\uE721";
  BookmarkButton.Content = state.Bookmarks.Any(b => b.Url == url) ? "\uE735" : "\uE734";
  Title = active == null || active.Url.Length == 0 ? "Still" : active.Title + " · Still";
  if(App.IsQa)Title+=" · Test";
  Title+=" · "+ProfileCatalog.CurrentName();
  ShellPublish();
 }
 void ConfirmExternal(string uri)
 {
  if (!Uri.TryCreate(uri, UriKind.Absolute, out var u) || u.Scheme is not ("mailto" or "tel")) { Toast("This link uses an unsupported application protocol."); return; }
  if (MessageBox.Show(this, "Open this link in the associated Windows app?\n\n" + uri, "Open external app", MessageBoxButton.YesNo) == MessageBoxResult.Yes) Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
 }
 void DragWindow(object s, MouseButtonEventArgs e) { if (e.ChangedButton != MouseButton.Left) return; if (e.ClickCount == 2) ToggleMaximize(); else try { DragMove(); } catch (InvalidOperationException) { } }
 void ToggleMaximize() => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
 void CloseWindow(object s, RoutedEventArgs e) => Close();
 void MinimizeWindow(object s, RoutedEventArgs e) => WindowState = WindowState.Minimized;
 void MaximizeWindow(object s, RoutedEventArgs e) => ToggleMaximize();
 void BackClick(object s, RoutedEventArgs e) { if (active?.View?.CoreWebView2 is { CanGoBack: true } c) c.GoBack(); }
 void ForwardClick(object s, RoutedEventArgs e) { if (active?.View?.CoreWebView2 is { CanGoForward: true } c) c.GoForward(); }
 async void ReloadClick(object s, RoutedEventArgs e) { if (active is not { } tab || tab.Url.Length == 0) return; if (tab.View?.CoreWebView2 is { } c) { if (tab.Loading) c.Stop(); else if (tab.ShowingError) c.Navigate(tab.Url); else { tab.Reader = false; c.Reload(); } } else await EnsureView(tab); }
 void AddressClick(object s, RoutedEventArgs e) => ShowAddress(active?.Url ?? "");
 async void NewTabClick(object s, RoutedEventArgs e) => await NewTab();
 void ThemeClick(object s, RoutedEventArgs e) { Prefs.Theme = dark ? "Light" : "Dark"; ApplyTheme(); }
 void SettingsClick(object s, RoutedEventArgs e) => ShowSettings();
 void BookmarkClick(object s, RoutedEventArgs e) => ToggleBookmark();
 void ShieldClick(object s, RoutedEventArgs e) => ShowSiteControls();
 async void ReaderClick(object s, RoutedEventArgs e) => await ToggleReader();
 void MenuClick(object s, RoutedEventArgs e) => ShowMenu((Button)s);
}
