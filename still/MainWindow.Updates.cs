using System.Net.Http;
using System.Reflection;
using System.Text.Json;
using System.Windows.Threading;
namespace Still;
public partial class MainWindow
{
 const string LatestRelease = "https://api.github.com/repos/carbongotfound/still/releases/latest";
 const string ReleasePage = "https://github.com/carbongotfound/still/releases/";
 record UpdateInfo(string Version, string Url);
 UpdateInfo? update;
 static Version CurrentVersion => Assembly.GetEntryAssembly()?.GetName().Version ?? new Version(0, 0);

 // Checks the public "latest release" (drafts and pre-releases are never returned), shortly after
 // startup and every 6 hours. It only reads the version; nothing about you is sent.
 void StartUpdateChecks()
 {
  if (App.IsQa) return;
  var timer = new DispatcherTimer { Interval = TimeSpan.FromHours(6) };
  timer.Tick += async (_, _) => await CheckForUpdate();
  timer.Start();
  _ = Dispatcher.InvokeAsync(async () => { await Task.Delay(TimeSpan.FromSeconds(15)); await CheckForUpdate(); });
 }

 async Task CheckForUpdate()
 {
  try {
   using var request = new HttpRequestMessage(HttpMethod.Get, LatestRelease);
   request.Headers.UserAgent.ParseAdd("Still/" + CurrentVersion.ToString(3));
   using var response = await ExtensionHttp.SendAsync(request);
   if (!response.IsSuccessStatusCode) return;
   using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
   string tag = json.RootElement.GetProperty("tag_name").GetString() ?? "";
   if (!Version.TryParse(tag.TrimStart('v', 'V'), out var latest)) return;
   // Only link to this repository's own release page.
   var found = latest > CurrentVersion ? new UpdateInfo(latest.ToString(3), ReleasePage + "tag/" + Uri.EscapeDataString(tag)) : null;
   if (found?.Version != update?.Version) { update = found; ShellPublish(); }
  } catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException or InvalidOperationException) { }
 }

 object? UpdateData() => update == null ? null : new { version = update.Version, current = CurrentVersion.ToString(3) };
}
