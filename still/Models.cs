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
 public int Window { get; set; } // which window it was saved in (0 is the first): every window comes back
 public string Group { get; set; } = ""; // a TabGroup id, "" = none
 [JsonIgnore] public object? Wire { get; set; } // which window's page handlers are live (see MainWindow.WireView)
 public string? ChatId { get; set; } // a chat tab: shows this AI chat instead of a page
 [JsonIgnore] public bool PageOpen { get; set; } // a chat tab showing its AI's page beside the conversation
 [JsonIgnore] public string Home { get; set; } = ""; // an app tab without a chat: the home page it shows ("" home, chats, companions, library, skills)
 [JsonIgnore] public List<string> Back { get; } = []; // an app tab's own back and forward: "chat:<id>" or "home:<page>" (see MainWindow.Go)
 [JsonIgnore] public List<string> Forward { get; } = [];
 public string? InChat { get; set; } // a page the AI opened for this chat: it lives in the chat, beside the conversation, not in the tab strip
 [JsonIgnore] public string? AgentKey { get; set; } // which AI run is at work here (see MainWindow.Worker)
 [JsonIgnore] public string? RunChat { get; set; } // an ordinary tab Still's chat AI opened: "Open chat" opens that chat, and it can show beside the chat
 [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Engine { get; set; } // "Companion": the page is in the companion profile (Where companions browse); null: the user's own
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
 [JsonIgnore] public string? UsbScriptId { get; set; } // hides USB, HID and serial from sites where they're blocked
 [JsonIgnore] public string InUse { get; set; } = ""; // what the page has on now: camera, mic, location (the Permissions button's dot)
 [JsonIgnore] public bool RuleMuted { get; set; } // muted because its site's sound is blocked, not by the user
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
 [JsonIgnore] public string LoginApi { get; set; }=""; // the page's login helper (LoginObserver.js), named at random per page
 [JsonIgnore] public string GeneratedLogin { get; set; }=""; // the login saved with a strong password suggested on this page
 [JsonIgnore] public (string Origin,string Username,DateTime At) LoginUsername { get; set; } // a two-step sign-in's first step
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
/// What AIs may do without asking. Site "" = any site, Companion "" = everyone. Action: read, navigate, interact or
/// sensitive. Mode: always (never asks), chat (asks once per site in each chat), ask (asks every time).
public sealed class SitePermission
{
 public string Site { get; set; } = "";
 public string Action { get; set; } = "";
 public string Companion { get; set; } = "";
 public string Mode { get; set; } = "";
}
public sealed class Preferences
{
 public string Theme { get; set; } = "System"; // Light, Dark, or System: follows Windows
 public string SearchEngine { get; set; } = "Google";
 public bool OfferPasswordSave { get; set; } = true;
 public bool AutoFillPasswords { get; set; }
 public bool OfferPasswordUpdate { get; set; } = true;
 public List<string> NeverSavePasswords { get; set; } = []; // origins where you said Never
 public bool Blocking { get; set; } = true;
 public string Tracking { get; set; } = "Balanced";
 public bool MemorySaver { get; set; } = true;
 public List<string> PinnedExtensions { get; set; } = []; // extension ids shown in the toolbar
 public bool TabTearOff { get; set; }
 public bool AgentsEnabled { get; set; }
 public bool AgentsAskInChat { get; set; } = true; // away from Still: agents may ask the user in their own chat
 public string AgentProfile { get; set; } = "regular"; // Where companions browse, for new chats: "regular" (the user's own profile) or "companion" (a separate one)
 public Dictionary<string, string> AiModels { get; set; } = []; // per AI: model id, "" = the CLI's default
 public Dictionary<string, string> AiEfforts { get; set; } = []; // per AI: reasoning effort, "" = default
 public string ChatTitles { get; set; } = ""; // what names new chats: "" = the quickest model, "off" = their first message, or "ai/model"
 public string PluginUser { get; set; } = ""; // who this profile is to Composio (plugins): a random id, not a secret
 public List<Companion> Companions { get; set; } = []; // empty until setup, which always leaves at least one; the first is the main one
 public bool NamesChecked { get; set; } // companions with an old stock name were flagged to ask about it (FlagOldNames)
 public bool AiAdvanced { get; set; } // pick the model and effort by hand instead of a mode
 public Dictionary<string, string[]> AiTiers { get; set; } = []; // per "ai:mode": [model, effort] picked in Settings; none = the defaults
 public string ChatSummaries { get; set; } = ""; // "off": companions don't summarize finished chats into their memory
 public string AiHarness { get; set; } = ""; // the AI sidebar's agent: "claude", "chatgpt", "grok", "gemini", "opencode", an API provider's or a manifest's id, or "" until chosen
 public List<ApiProvider> ApiProviders { get; set; } = []; // API providers the user added: settings and spending only, never the key (ApiKeyStore)
 public bool Autofill { get; set; } = true;
 public bool SaveDrafts { get; set; } = true; // Settings > Save drafts: message boxes keep what's typed until it's sent
 public bool AutoUpdate { get; set; } = true; // Settings > About > Update automatically: off, a new version downloads and installs only when you click Update
 public bool Sounds { get; set; } = true; // setup, the intro and the look editor; browsing never makes a sound
 public bool RestoreTabs { get; set; } = true;
 public string DownloadFolder { get; set; } = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
 public List<string> UnblockedHosts { get; set; } = [];
 public List<string> AllowedAppLinks { get; set; } = [];
 public List<string> AllowedPopups { get; set; } = []; // hosts, from before SitePermissions: an Allow for pop-ups
 public Dictionary<string, Dictionary<string, string>> SitePermissions { get; set; } = []; // origin → Popups, Autoplay, ScreenShare or Usb → Allow or Deny
 public List<string> ApprovedAgents { get; set; } = [];
 public List<SitePermission> Permissions { get; set; } = []; // on top of the defaults: read and navigate always, interact once per chat, sensitive every time
 public List<string> SensitiveSites { get; set; } = []; // every click or keystroke there counts as sensitive
 public string NewTab { get; set; } = "companion"; // the new tab page: "companion" (your companion and ideas) or "sites" (search and your sites)
 public List<string> Interests { get; set; } = []; // what the user said they're into: ideas and chat starters come from these
 public string TabLayout { get; set; } = "Classic"; // Classic: tabs across the top. Modern: a sidebar down the left.
 public double SidebarWidth { get; set; } = 248;
 public double Width { get; set; } = 1260;
 public double Height { get; set; } = 810;
}
public sealed class TabGroup
{
 public string Id { get; set; } = Guid.NewGuid().ToString("N");
 public string Name { get; set; } = "";
 public string Color { get; set; } = "blue";
 public bool Collapsed { get; set; }
}
public sealed class AddressPick
{
 public string Typed { get; set; } = "";
 public string Url { get; set; } = "";
 public int Count { get; set; }
 public DateTime At { get; set; } = DateTime.UtcNow;
}
public sealed class SavedState
{
 public int UiVersion { get; set; }
 public bool Welcome { get; set; }
 public string SeenVersion { get; set; } = ""; // the release (2.10) whose What's New was shown
 public Preferences Preferences { get; set; } = new();
 public List<BrowserTab> Tabs { get; set; } = [];
 public string? ActiveId { get; set; }
 public List<Visit> History { get; set; } = [];
 public List<Visit> Bookmarks { get; set; } = [];
 public List<TabGroup> Groups { get; set; } = [];
 public List<AddressPick> AddressPicks { get; set; } = []; // what you typed and the site you picked (never private tabs)
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
   for (int tries = 0; ; tries++) {
    try { if (File.Exists(file)) File.Replace(file + ".tmp", file, file + ".bak"); else File.Move(file + ".tmp", file); return; }
    catch (IOException) when (tries < 5) { Thread.Sleep(40); } // another program (a backup, a virus scan) has it open for a moment
   }
  } catch (Exception ex) { App.Log(ex); }
 }
}
