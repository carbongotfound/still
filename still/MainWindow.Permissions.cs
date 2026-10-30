using System.Text.Json;
using Microsoft.Web.WebView2.Core;
namespace Still;
public partial class MainWindow
{
 sealed record PendingPermission(string Id,BrowserTab Tab,string Site,string Kind,TaskCompletionSource<bool> Answer);
 readonly List<PendingPermission> permissions=[];

 static string PermissionLabel(CoreWebView2PermissionKind kind)=>kind switch{
  CoreWebView2PermissionKind.Microphone=>"use your microphone",
  CoreWebView2PermissionKind.Camera=>"use your camera",
  CoreWebView2PermissionKind.Geolocation=>"know your location",
  CoreWebView2PermissionKind.Notifications=>"show notifications",
  CoreWebView2PermissionKind.ClipboardRead=>"see your clipboard",
  CoreWebView2PermissionKind.OtherSensors=>"use motion sensors",
  CoreWebView2PermissionKind.MultipleAutomaticDownloads=>"download multiple files",
  CoreWebView2PermissionKind.FileReadWrite=>"edit files on this PC",
  CoreWebView2PermissionKind.Autoplay=>"play media automatically",
  CoreWebView2PermissionKind.LocalFonts=>"use your installed fonts",
  CoreWebView2PermissionKind.MidiSystemExclusiveMessages=>"control MIDI devices",
  CoreWebView2PermissionKind.WindowManagement=>"manage windows on your displays",
  _=>"use a device feature"};

 // Shows the request in Still's own permission bar; unanswered requests are denied after 90s or when the tab closes.
 Task<bool> AskPermission(BrowserTab tab,string site,CoreWebView2PermissionKind kind)=>AskPermission(tab,site,PermissionLabel(kind));
 async Task<bool> AskPermission(BrowserTab tab,string site,string what)
 {
  var pending=new PendingPermission(Guid.NewGuid().ToString("N"),tab,site,what,new(TaskCreationOptions.RunContinuationsAsynchronously));
  permissions.Add(pending);ShellPublish();
  var done=await Task.WhenAny(pending.Answer.Task,Task.Delay(TimeSpan.FromSeconds(90)));
  permissions.Remove(pending);ShellPublish();
  return done==pending.Answer.Task&&pending.Answer.Task.Result;
 }
 void AnswerPermission(string id,bool allow){var p=permissions.FirstOrDefault(v=>v.Id==id);p?.Answer.TrySetResult(allow);}
 void DropPermissions(BrowserTab tab){foreach(var p in permissions.Where(v=>v.Tab==tab).ToArray())p.Answer.TrySetResult(false);}
 object? PermissionData()=>permissions.FirstOrDefault(p=>p.Tab==active) is{} p?new{id=p.Id,site=p.Site,kind=p.Kind}:null;

 // The Permissions button: each permission for the active tab's site, Allow, Ask or Block. Most are the engine's own
 // per-site settings, saved in the profile like an answer in the permission bar. Pop-ups, sound, screen sharing and USB
 // are Still's (Prefs.SitePermissions); Autoplay is both (the engine's autoplay, and Still mutes the site). A private
 // window's choices last until it closes.
 static readonly string[] SiteKinds=["Camera","Microphone","Geolocation","Notifications","ClipboardRead","Popups","MultipleAutomaticDownloads","Autoplay","ScreenShare","MidiSystemExclusiveMessages","Usb"];
 readonly Dictionary<string,Dictionary<string,string>> privateSiteRules=[];
 Dictionary<string,Dictionary<string,string>> SiteRules(bool isPrivate)=>isPrivate?privateSiteRules:Prefs.SitePermissions;
 static string SiteOrigin(string url)=>Uri.TryCreate(url,UriKind.Absolute,out var u)&&u.Scheme is "http" or "https"?Origin(u):"";
 string SiteRule(BrowserTab tab,string kind)=>SiteRules(tab.Private).GetValueOrDefault(SiteOrigin(tab.Url))?.GetValueOrDefault(kind)
  ??(kind=="Popups"&&!tab.Private&&Prefs.AllowedPopups.Contains(Host(tab.Url))?"Allow":"");

 async Task<object> SitePermissionData()
 {
  var tab=active;string origin=tab==null?"":SiteOrigin(tab.Url);
  if(tab?.View?.CoreWebView2 is not{} core||origin=="")return new{origin=""};
  var states=new Dictionary<string,string>();
  foreach(var p in await core.Profile.GetNonDefaultPermissionSettingsAsync())
   if(p.PermissionOrigin.TrimEnd('/')==origin&&p.PermissionState!=CoreWebView2PermissionState.Default)states[p.PermissionKind.ToString()]=p.PermissionState==CoreWebView2PermissionState.Allow?"Allow":"Deny";
  foreach(var kind in new[]{"Popups","Autoplay","ScreenShare","Usb"})if(SiteRule(tab,kind) is{Length:>0} rule)states[kind]=rule;
  return new{origin,site=Host(tab.Url),isPrivate=tab.Private,states=SiteKinds.ToDictionary(k=>k,k=>states.GetValueOrDefault(k,"Ask")),inUse=tab.InUse};
 }

 /// state: Allow, Ask or Deny. It applies at once: the engine's next request, the site's sound, its pop-ups.
 async Task SetSitePermission(BrowserTab tab,string kind,string state)
 {
  string origin=SiteOrigin(tab.Url);
  if(origin==""||!SiteKinds.Contains(kind)||state is not ("Allow" or "Ask" or "Deny")||tab.View?.CoreWebView2 is not{} core)return;
  if(kind is "Popups" or "Autoplay" or "ScreenShare" or "Usb"){
   var rules=SiteRules(tab.Private);
   if(!rules.TryGetValue(origin,out var mine))rules[origin]=mine=[];
   if(state=="Ask")mine.Remove(kind);else mine[kind]=state;
   if(mine.Count==0)rules.Remove(origin);
   if(kind=="Popups"&&!tab.Private)Prefs.AllowedPopups.Remove(Host(tab.Url));
  }
  if(kind!="Popups"&&Enum.TryParse<CoreWebView2PermissionKind>(kind,out var engine))
   await core.Profile.SetPermissionStateAsync(engine,origin,state=="Allow"?CoreWebView2PermissionState.Allow:state=="Deny"?CoreWebView2PermissionState.Deny:CoreWebView2PermissionState.Default);
  if(!tab.Private)SaveLater();
  await ApplySiteRules(tab.Private);
 }

 async Task ResetSitePermissions(BrowserTab tab)
 {
  if(SiteOrigin(tab.Url) is not{Length:>0} origin||tab.View?.CoreWebView2 is not{} core)return;
  foreach(var kind in SiteKinds)if(kind!="Popups"&&Enum.TryParse<CoreWebView2PermissionKind>(kind,out var engine))await core.Profile.SetPermissionStateAsync(engine,origin,CoreWebView2PermissionState.Default);
  SiteRules(tab.Private).Remove(origin);
  if(!tab.Private){Prefs.AllowedPopups.Remove(Host(tab.Url));SaveLater();}
  await ApplySiteRules(tab.Private);
 }

 /// Sound and USB follow the rules in every tab of that kind (private or not).
 async Task ApplySiteRules(bool isPrivate){foreach(var t in tabs.Where(t=>t.Private==isPrivate).ToArray()){ApplySound(t);await ApplyUsbRule(t);}ShellPublish();}
 void ApplySound(BrowserTab tab)
 {
  if(tab.View?.CoreWebView2 is not{} core)return;
  bool off=SiteRule(tab,"Autoplay")=="Deny";
  if(off)core.IsMuted=true;else if(tab.RuleMuted)core.IsMuted=false;
  tab.RuleMuted=off;
 }
 async Task ApplyUsbRule(BrowserTab tab)
 {
  if(tab.View?.CoreWebView2 is not{} core)return;
  if(tab.UsbScriptId!=null){core.RemoveScriptToExecuteOnDocumentCreated(tab.UsbScriptId);tab.UsbScriptId=null;}
  var off=SiteRules(tab.Private).Where(r=>r.Value.GetValueOrDefault("Usb")=="Deny").Select(r=>r.Key).ToArray();
  if(off.Length>0)tab.UsbScriptId=await core.AddScriptToExecuteOnDocumentCreatedAsync("if("+JsonSerializer.Serialize(off)+".includes(location.origin))for(const k of['usb','hid','serial'])try{Object.defineProperty(Navigator.prototype,k,{get:()=>undefined})}catch{}");
 }
}
