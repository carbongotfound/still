using System.IO;
using System.Windows;
using System.Threading;
namespace Still;
public partial class App : Application
{
 public static string DataRoot { get; private set; } = "";
 public static bool IsQa { get; private set; }
 public static bool IsTemp { get; private set; } // a throwaway profile an MCP agent opened: no cookies, logins or history
 public static string ProfileHome { get; private set; }="";
 private static Task<Microsoft.Web.WebView2.Core.CoreWebView2Environment>? browserEnvironment;
 public static Task<Microsoft.Web.WebView2.Core.CoreWebView2Environment> BrowserEnvironment => browserEnvironment ??= Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateAsync(null,Path.Combine(DataRoot,"WebView"),new(){AreBrowserExtensionsEnabled=true,EnableTrackingPrevention=true,
  // Play audio from the engine's main process (a direct child of Still.exe) instead of a separate audio-service
  // process one level deeper, so per-app audio tools (Discord screen share, SteelSeries Sonar, OBS) can find it.
  // GPU and network keep their own processes. Merged into the main one they saved ~190 MB, but then a GPU crash
  // (an extension capturing the page, a driver hiccup) took down the whole engine and every window with it.
  // Video is drawn by the engine, not handed to the graphics card as an overlay: NVIDIA overlays could freeze a
  // fullscreen YouTube picture (looking paused) while the sound played on.
  AdditionalBrowserArguments="--disable-features=AudioServiceOutOfProcess --disable-direct-composition-video-overlays"+(IsQa?(Environment.GetEnvironmentVariable("STILL_QA_SOUND")==null?" --mute-audio ":" ")+Environment.GetEnvironmentVariable("STILL_QA_BROWSER_ARGS"):"")});
 private Mutex? instance;
 private IDisposable? linkListener, launcherListener;
 internal static string InstanceName(string folder)=>"Local\\Still-"+Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar).ToLowerInvariant())))[..20];
 static string? ArgAfter(string[] args, string flag) { int i = Array.IndexOf(args, flag); return i >= 0 && i + 1 < args.Length ? args[i + 1] : null; }
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
  IsTemp = e.Args.Contains("--temp"); launchArgs = e.Args;
  try { ConfigureProfile(e.Args); } catch(Exception ex) { MessageBox.Show(ex.Message,"Still");Shutdown();return; }
  var launchUrl = BrowserRegistration.UrlFromArgs(e.Args);
  // `Still.exe --mcp`: run only the MCP stdio server (launched by AI apps); no window.
  if (e.Args.FirstOrDefault() == "--cli") { var cliArgs = e.Args.Skip(1).ToArray(); new Thread(() => { int code = 1; try { code = McpServer.Cli(InstanceName(DataRoot), cliArgs); } finally { Dispatcher.Invoke(() => Shutdown(code)); } }) { IsBackground = true }.Start(); return; }
  if (e.Args.Contains("--mcp")) { new Thread(() => { try { McpServer.RunId = ArgAfter(e.Args, "--run") ?? ""; McpServer.NoTools = e.Args.Contains("--no-tools"); McpServer.Run(InstanceName(DataRoot), ArgAfter(e.Args, "--as"), e.Args.Contains("--this-profile")); } finally { Dispatcher.Invoke(Shutdown); } }) { IsBackground = true }.Start(); return; }
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
  Action<string> open = url => Dispatcher.BeginInvoke(() => {
   if ((Still.MainWindow.LastActive ?? MainWindow as Still.MainWindow) is { } target) target.OpenFromOutside(url);
  });
  linkListener = BrowserRegistration.Listen(InstanceName(DataRoot), open);
  if (!e.Args.Contains("--profile") && !IsQa) launcherListener = BrowserRegistration.ListenForLauncher(open);
  _ = BrowserEnvironment.ContinueWith(t => t.Result.BrowserProcessExited += (_, ev) => {
   if (ev.BrowserProcessExitKind == Microsoft.Web.WebView2.Core.CoreWebView2BrowserProcessExitKind.Failed) Dispatcher.BeginInvoke(RestartAfterEngineCrash);
  }, CancellationToken.None, TaskContinuationOptions.OnlyOnRanToCompletion, TaskScheduler.FromCurrentSynchronizationContext()); // start the engine while the window is still being built
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
    if (ui.HasShutdownStarted) return; // quitting stops the UI thread on purpose; that isn't a freeze
    var ping = ui.BeginInvoke(System.Windows.Threading.DispatcherPriority.Send, () => { });
    if (ping.Wait(TimeSpan.FromSeconds(5)) == System.Windows.Threading.DispatcherOperationStatus.Completed) continue;
    string during = Breadcrumb; var started = DateTime.Now.AddSeconds(-5);
    ping.Wait();
    if (ui.HasShutdownStarted) return;
    Log(new TimeoutException($"Still froze for {(DateTime.Now - started).TotalSeconds:0.0}s while handling: {during}"));
   }
  }) { IsBackground = true, Name = "Freeze watchdog" }.Start();
 }
 public static void Log(Exception ex) { try { File.AppendAllText(Path.Combine(DataRoot, "errors.log"), DateTime.Now.ToString("s") + " " + ex + Environment.NewLine); } catch { } }
 static string[] launchArgs = [];
 bool restarting;
 // The engine's main process died: every page and Still's own UI died with it, and each click would only show an
 // error. Save the tabs and start Still again. If it already crashed right after such a restart, stop instead.
 void RestartAfterEngineCrash()
 {
  if (restarting || Dispatcher.HasShutdownStarted) return;
  restarting = true;
  Log(new Exception("The browser engine crashed; restarting Still."));
  try { (Still.MainWindow.Windows.FirstOrDefault() ?? MainWindow as Still.MainWindow)?.Save(); } catch (Exception ex) { Log(ex); }
  if (launchArgs.Contains("--recovered") && DateTime.Now - System.Diagnostics.Process.GetCurrentProcess().StartTime < TimeSpan.FromSeconds(90)) {
   MessageBox.Show("Still's browser engine keeps crashing, so Still closed. Your tabs are saved; open Still again to continue.", "Still");
   Environment.Exit(1);
  }
  linkListener?.Dispose(); launcherListener?.Dispose();
  try { instance?.ReleaseMutex(); } catch (ApplicationException) { }
  instance?.Dispose();
  var start = new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false };
  foreach (var arg in launchArgs.Where(a => a != "--recovered" && !a.Contains("://"))) start.ArgumentList.Add(arg);
  start.ArgumentList.Add("--recovered");
  System.Diagnostics.Process.Start(start);
  Environment.Exit(0);
 }
 protected override void OnExit(ExitEventArgs e)
 {
  linkListener?.Dispose(); launcherListener?.Dispose(); instance?.Dispose();
  // A temporary profile is deleted once its browser processes have let go of the files (the next temp window sweeps leftovers).
  if (IsTemp && DataRoot.StartsWith(Path.Combine(Path.GetTempPath(), "Still-temp"), StringComparison.OrdinalIgnoreCase))
   System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "cmd.exe"), $"/d /c for /l %i in (1,1,15) do @if exist \"{DataRoot}\" (ping -n 3 127.0.0.1 >nul & rmdir /s /q \"{DataRoot}\" 2>nul)") { CreateNoWindow = true, UseShellExecute = false });
  base.OnExit(e);
 }
}
