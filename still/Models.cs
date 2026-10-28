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
 [JsonIgnore] public string? Agent { get; set; } // the AI working in this tab right now (bot icon)
 [JsonIgnore] public bool AgentGroup { get; set; } // opened by an AI: shown together in the AI group
 public bool Pinned { get; set; }
 public string? ChatId { get; set; } // a chat tab: shows this AI chat instead of a page
 [JsonIgnore] public bool PageOpen { get; set; } // a chat tab showing its AI's page beside the conversation
 public string? InChat { get; set; } // a page the AI opened for this chat: it lives in the chat, beside the conversation, not in the tab strip
 [JsonIgnore] public string? RunChat { get; set; } // an ordinary tab Still's chat AI opened: "Go to chat" opens that chat, and it can show beside the chat
 public string Favicon { get; set; } = "";
 [JsonIgnore] public bool Private { get; set; }
 [JsonIgnore] public WebView2? View { get; set; }
 // Held so the page's file-picker events keep arriving; an unreferenced receiver gets collected.
 [JsonIgnore] public object? FileChooserEvents { get; set; }
 [JsonIgnore] public Task? LoadingTask { get; set; }
 [JsonIgnore] public bool Loading { get; set; }
 [JsonIgnore] public bool Closed { get; set; }
 [JsonIgnore] public bool Edited { get; set; } // has typed text: memory saver never unloads it, so nothing is lost
 [JsonIgnore] public bool Media { get; set; } // played sound: memory saver leaves it alone so video/music never breaks
 [JsonIgnore] public bool Reader { get; set; }
 [JsonIgnore] public int Blocked { get; set; }
 [JsonIgnore] public string? HideScriptId { get; set; }
 [JsonIgnore] public string? HideToken { get; set; }
 [JsonIgnore] public DateTime HideExpires { get; set; }
 [JsonIgnore] public DateTime LastActive { get; set; } = DateTime.UtcNow;
 [JsonIgnore] public bool CertificateError { get; set; }
 [JsonIgnore] public bool ShowingError { get; set; }
 [JsonIgnore] public DateTime DownloadStartedAt { get; set; }
 [JsonIgnore] public int ActiveDownloads { get; set; }
 [JsonIgnore] public double RestoreScroll { get; set; }
 [JsonIgnore] public bool Secure { get; set; }
 [JsonIgnore] public ulong NavigationId { get; set; }
 [JsonIgnore] public string? LoginScriptId { get; set; }
 [JsonIgnore] public string LoginToken { get; set; }="";
 [JsonIgnore] public bool LoginDetected { get; set; }
 [JsonIgnore] public bool LoginFilled { get; set; }
 [JsonIgnore] public PageDialog? Dialog { get; set; } // an alert/confirm/prompt the page is paused on
 [JsonIgnore] public object? AgentUpload { get; set; } // a file picker an AI's click opened, waiting for upload_file
 [JsonIgnore] public DateTime AgentActedAt { get; set; }
}
public sealed record PageDialog(CoreWebView2ScriptDialogOpeningEventArgs Args, CoreWebView2Deferral Deferral, string Site);
public sealed class Visit
{
 public string Title { get; set; } = "";
 public string Url { get; set; } = "";
 public string? Favicon { get; set; }
 public DateTime At { get; set; } = DateTime.Now;
}
public sealed class Preferences
{
 public string Theme { get; set; } = "Dark";
 public string SearchEngine { get; set; } = "Google";
 public bool OfferPasswordSave { get; set; } = true;
 public bool AutoFillPasswords { get; set; }
 public bool OfferPasswordUpdate { get; set; } = true;
 public bool Blocking { get; set; } = true;
 public string Tracking { get; set; } = "Balanced";
 public bool MemorySaver { get; set; } = true;
 public List<string> PinnedExtensions { get; set; } = []; // extension ids shown in the toolbar
 public bool TabTearOff { get; set; }
 public bool AgentsEnabled { get; set; }
 public bool AgentsAskInChat { get; set; } = true; // away from Still: agents may ask the user in their own chat
 public Dictionary<string, string> AiModels { get; set; } = []; // per AI: model id, "" = the CLI's default
 public Dictionary<string, string> AiEfforts { get; set; } = []; // per AI: reasoning effort, "" = default
 public List<Companion> Companions { get; set; } = []; // empty = the default crew
 public bool AiAdvanced { get; set; } // pick the model and effort by hand instead of a mode
 public string AiHarness { get; set; } = ""; // the AI sidebar's agent: "claude", "chatgpt", "grok", a manifest id, or "" until chosen
 public bool Autofill { get; set; } = true;
 public bool RestoreTabs { get; set; } = true;
 public string DownloadFolder { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
 public List<string> UnblockedHosts { get; set; } = [];
 public List<string> AllowedAppLinks { get; set; } = [];
 public List<string> AllowedPopups { get; set; } = [];
 public List<string> ApprovedAgents { get; set; } = [];
 public double Width { get; set; } = 1260;
 public double Height { get; set; } = 810;
}
public sealed class SavedState
{
 public int UiVersion { get; set; }
 public bool Welcome { get; set; }
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
