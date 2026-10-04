using System.IO;
using System.Threading;

namespace Still;

internal static class Program
{
 // Link launches should not initialize WPF, create a window or start another WebView environment.
 [STAThread]
 static void Main(string[] args)
 {
  StartupMetrics.Mark("entry");
  if (!args.Contains("--mcp") && args.FirstOrDefault() != "--cli")
  {
   try
   {
    App.ConfigureProfile(args);
    var name = App.InstanceName(App.DataRoot);
    if (Mutex.TryOpenExisting(name, out var running))
    {
     using (running)
      if (args.Contains("--startup") || BrowserRegistration.Forward(name, BrowserRegistration.UrlFromArgs(args))) return;
    }
   }
   catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidOperationException or ArgumentException)
   {
    // The normal startup path presents profile errors and handles an instance that is still starting.
   }
  }
  var app = new App();
  app.InitializeComponent();
  app.Run();
 }
}
