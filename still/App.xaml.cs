using System.IO;
using System.Windows;
using System.Threading;
namespace Still;
public partial class App : Application
{
 public static string DataRoot { get; private set; } = "";
 public static bool IsQa { get; private set; }
 public static string ProfileHome { get; private set; }="";
 private static Task<Microsoft.Web.WebView2.Core.CoreWebView2Environment>? browserEnvironment;
 public static Task<Microsoft.Web.WebView2.Core.CoreWebView2Environment> BrowserEnvironment => browserEnvironment ??= Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateAsync(null,Path.Combine(DataRoot,"WebView"),new(){AreBrowserExtensionsEnabled=true,EnableTrackingPrevention=true,
  // Play audio from the engine's main process (a direct child of Still.exe) instead of a separate audio-service
  // process one level deeper, so per-app audio tools (Discord screen share, SteelSeries Sonar, OBS) can find it.
  AdditionalBrowserArguments="--disable-features=AudioServiceOutOfProcess"});
 private Mutex? instance;
 private IDisposable? linkListener;
 internal static string InstanceName(string folder)=>"Local\\Still-"+Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar).ToLowerInvariant())))[..20];
 internal static void ConfigureProfile(string[] args)
 {
  var profile = Array.IndexOf(args, "--profile");
  DataRoot = profile >= 0 && args.Length > profile + 1 ? Path.GetFullPath(args[profile + 1]) : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Still");
  int root = Array.IndexOf(args, "--profiles-root");
  ProfileHome = root >= 0 && args.Length > root + 1 ? Path.GetFullPath(args[root + 1]) : DataRoot;
  if (profile < 0) DataRoot = ProfileCatalog.Folder(ProfileCatalog.Read().Single(p => p.Id == ProfileCatalog.LaunchId));
 }
 protected override void OnStartup(StartupEventArgs e)
 {
  base.OnStartup(e);
  StartupMetrics.Mark("app-startup");
#if STILL_QA
  IsQa = e.Args.Contains("--qa");
#endif
  try { ConfigureProfile(e.Args); } catch(Exception ex) { MessageBox.Show(ex.Message,"Still");Shutdown();return; }
  var launchUrl = BrowserRegistration.UrlFromArgs(e.Args);
  // `Still.exe --mcp`: run only the MCP stdio server (launched by AI apps); no window.
  if (e.Args.FirstOrDefault() == "--cli") { var cliArgs = e.Args.Skip(1).ToArray(); new Thread(() => { int code = 1; try { code = McpServer.Cli(InstanceName(DataRoot), cliArgs); } finally { Dispatcher.Invoke(() => Shutdown(code)); } }) { IsBackground = true }.Start(); return; }
  if (e.Args.Contains("--mcp")) { new Thread(() => { try { McpServer.Run(InstanceName(DataRoot)); } finally { Dispatcher.Invoke(Shutdown); } }) { IsBackground = true }.Start(); return; }
  instance = new Mutex(true, InstanceName(DataRoot), out var first);
  if (!first) {
   // Already running: hand the link (or a plain "bring to front") to the open window.
   if (!e.Args.Contains("--startup") && !BrowserRegistration.Forward(InstanceName(DataRoot), launchUrl))
    MessageBox.Show("Still is already open. Look for it in your taskbar.", "Still");
   Shutdown(); return;
  }
  Directory.CreateDirectory(DataRoot);
  StartupMetrics.Mark("profile-ready");
  // Accept links before constructing the window. Dispatcher callbacks wait until it is ready.
  linkListener = BrowserRegistration.Listen(InstanceName(DataRoot), url => Dispatcher.BeginInvoke(() => {
   if ((Still.MainWindow.LastActive ?? MainWindow as Still.MainWindow) is { } target) target.OpenFromOutside(url);
  }));
  _ = BrowserEnvironment; // start the engine while the window is still being built
  _ = AppContent.ShellFolder;
  StartupMetrics.Mark("environment-requested");
  try{var stale=Path.Combine(DataRoot,"ImportSnapshot");if(Directory.Exists(stale))Directory.Delete(stale,true);}catch(IOException){}catch(UnauthorizedAccessException){}
  // Crashes off the UI thread and UI freezes were never recorded; log them so a "random crash" leaves a trace.
  AppDomain.CurrentDomain.UnhandledException += (_, ev) => Log(ev.ExceptionObject as Exception ?? new Exception("Unhandled: " + ev.ExceptionObject));
  TaskScheduler.UnobservedTaskException += (_, ev) => { Log(ev.Exception); ev.SetObserved(); };
  WatchForFreezes();
  DispatcherUnhandledException += (_, ev) => { Log(ev.Exception); MessageBox.Show("Still couldn't finish that action. Your saved tabs are kept.\n\n" + ev.Exception.Message, "Still"); ev.Handled = true; };
  var window = new MainWindow { ShowActivated=!IsQa, LaunchUrl = launchUrl }; MainWindow = window; window.Show();
  _ = Dispatcher.InvokeAsync(BrowserRegistration.Register, System.Windows.Threading.DispatcherPriority.ContextIdle);
  Still.MainWindow.StartAgentServer(InstanceName(DataRoot));
 }
 // What the UI thread was last asked to do; written to the log if it freezes.
 public static volatile string Breadcrumb = "startup";
 void WatchForFreezes()
 {
  var ui = Dispatcher;
  new System.Threading.Thread(() => {
   while (true) {
    System.Threading.Thread.Sleep(2000);
    var ping = ui.BeginInvoke(System.Windows.Threading.DispatcherPriority.Send, () => { });
    if (ping.Wait(TimeSpan.FromSeconds(5)) == System.Windows.Threading.DispatcherOperationStatus.Completed) continue;
    string during = Breadcrumb; var started = DateTime.Now.AddSeconds(-5);
    ping.Wait();
    Log(new TimeoutException($"Still froze for {(DateTime.Now - started).TotalSeconds:0.0}s while handling: {during}"));
   }
  }) { IsBackground = true, Name = "Freeze watchdog" }.Start();
 }
 public static void Log(Exception ex) { try { File.AppendAllText(Path.Combine(DataRoot, "errors.log"), DateTime.Now.ToString("s") + " " + ex + Environment.NewLine); } catch { } }
 protected override void OnExit(ExitEventArgs e) { linkListener?.Dispose(); instance?.Dispose(); base.OnExit(e); }
}
