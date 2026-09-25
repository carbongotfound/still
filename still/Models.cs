using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Web.WebView2.Wpf;
using Microsoft.Web.WebView2.Core;
namespace Still;
public sealed class BrowserTab
{
 public string Id { get; set; } = Guid.NewGuid().ToString("N");
 public string Title { get; set; } = "New tab";
 public string Url { get; set; } = "";
 public bool Pinned { get; set; }
 public string Favicon { get; set; } = "";
 [JsonIgnore] public bool Private { get; set; }
 [JsonIgnore] public WebView2? View { get; set; }
 [JsonIgnore] public Task? LoadingTask { get; set; }
 [JsonIgnore] public bool Loading { get; set; }
 [JsonIgnore] public bool Closed { get; set; }
 [JsonIgnore] public bool Reader { get; set; }
 [JsonIgnore] public int Blocked { get; set; }
 [JsonIgnore] public string? HideScriptId { get; set; }
 [JsonIgnore] public string? HideToken { get; set; }
 [JsonIgnore] public DateTime HideExpires { get; set; }
 [JsonIgnore] public DateTime LastActive { get; set; } = DateTime.UtcNow;
 [JsonIgnore] public bool CertificateError { get; set; }
 [JsonIgnore] public bool ShowingError { get; set; }
 [JsonIgnore] public bool Secure { get; set; }
 [JsonIgnore] public ulong NavigationId { get; set; }
 [JsonIgnore] public string? LoginScriptId { get; set; }
 [JsonIgnore] public string LoginToken { get; set; }="";
 [JsonIgnore] public bool LoginDetected { get; set; }
 [JsonIgnore] public bool LoginFilled { get; set; }
}
public sealed class Visit
{
 public string Title { get; set; } = "";
 public string Url { get; set; } = "";
 public DateTime At { get; set; } = DateTime.Now;
}
public sealed class Preferences
{
 public string Theme { get; set; } = "Dark";
 public string Layout { get; set; } = "Sidebar";
 public string SearchEngine { get; set; } = "Google";
 public bool OfferPasswordSave { get; set; }
 public bool AutoFillPasswords { get; set; }
 public bool OfferPasswordUpdate { get; set; }
 public bool Blocking { get; set; } = true;
 public double SidebarWidth { get; set; } = 248;
 public string Tracking { get; set; } = "Balanced";
 public bool MemorySaver { get; set; } = true;
 public bool Autofill { get; set; } = true;
 public bool RestoreTabs { get; set; } = true;
 public string DownloadFolder { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
 public List<string> UnblockedHosts { get; set; } = [];
 public double Width { get; set; } = 1260;
 public double Height { get; set; } = 810;
}
public sealed class SavedState
{
 public int UiVersion { get; set; }
 public Preferences Preferences { get; set; } = new();
 public List<BrowserTab> Tabs { get; set; } = [];
 public string? ActiveId { get; set; }
 public List<Visit> History { get; set; } = [];
 public List<Visit> Bookmarks { get; set; } = [];
 public Dictionary<string, List<string>> Hidden { get; set; } = [];
}
public sealed class DownloadItem
{
 public string Path { get; set; } = "";
 public CoreWebView2DownloadOperation Operation { get; set; } = null!;
 public bool Private { get; set; }
}
public sealed class StateStore
{
 private readonly string file = Path.Combine(App.DataRoot, "state.json");
 public bool Recovered { get; private set; }
 public SavedState Load()
 {
  foreach (var candidate in new[] { file, file + ".bak" })
  {
   if (!File.Exists(candidate)) continue;
   try { var data = JsonSerializer.Deserialize<SavedState>(File.ReadAllText(candidate)); if (data is not null) return data; }
   catch (Exception ex) { Recovered = true; App.Log(ex); }
  }
  return new();
 }
 public void Save(SavedState state)
 {
  try {
   File.WriteAllText(file + ".tmp", JsonSerializer.Serialize(state, new JsonSerializerOptions { WriteIndented = true }));
   if (File.Exists(file)) File.Replace(file + ".tmp", file, file + ".bak");
   else File.Move(file + ".tmp", file);
  } catch (Exception ex) { App.Log(ex); }
 }
}
