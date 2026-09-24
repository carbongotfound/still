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
 async Task<bool> AskPermission(BrowserTab tab,string site,CoreWebView2PermissionKind kind)
 {
  var pending=new PendingPermission(Guid.NewGuid().ToString("N"),tab,site,PermissionLabel(kind),new(TaskCreationOptions.RunContinuationsAsynchronously));
  permissions.Add(pending);ShellPublish();
  var done=await Task.WhenAny(pending.Answer.Task,Task.Delay(TimeSpan.FromSeconds(90)));
  permissions.Remove(pending);ShellPublish();
  return done==pending.Answer.Task&&pending.Answer.Task.Result;
 }
 void AnswerPermission(string id,bool allow){var p=permissions.FirstOrDefault(v=>v.Id==id);p?.Answer.TrySetResult(allow);}
 void DropPermissions(BrowserTab tab){foreach(var p in permissions.Where(v=>v.Tab==tab).ToArray())p.Answer.TrySetResult(false);}
 object? PermissionData()=>permissions.FirstOrDefault(p=>p.Tab==active) is{} p?new{id=p.Id,site=p.Site,kind=p.Kind}:null;
}
