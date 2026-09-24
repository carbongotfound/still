using System.IO;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
namespace Still;
public partial class MainWindow
{
 ExternalProfileImport? externalImport;
 string externalImportName="",externalImportError="",externalImportDone="";
 bool externalImportBusy;
 string externalImportPath="";
 int externalImportGeneration;
 readonly Dictionary<string,(string Name,string Path)> externalSources=[];
 object ExternalImportData()=>new{
  busy=externalImportBusy,error=externalImportError,done=externalImportDone,profile=ProfileCatalog.CurrentName(),
  sources=externalSources.Select(s=>new{id=s.Key,name=s.Value.Name}),
  preview=externalImport==null?null:new{id=externalImport.Id,name=externalImportName,bookmarks=externalImport.Bookmarks.Count,history=externalImport.History.Count,
   passwords=externalImport.Logins.Count,cookies=externalImport.Cookies.Count,cookiesLocked=externalImport.CookiesLocked,skipped=externalImport.Skipped,warnings=externalImport.Warnings}
 };
 void DiscoverExternalProfiles()
 {
  if(externalSources.Count>0)return;
  var roaming=Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
  var local=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
  void Add(string name,string path){if(Directory.Exists(path))externalSources[Guid.NewGuid().ToString("N")]=(name,path);}
  foreach(var opera in new[]{("Opera GX","Opera GX Stable"),("Opera","Opera Stable")}){
   string root=Path.Combine(roaming,"Opera Software",opera.Item2);if(!Directory.Exists(root))continue;
   Add(opera.Item1,root);
   // Opera keeps additional profiles under _side_profiles.
   string side=Path.Combine(root,"_side_profiles");
   if(Directory.Exists(side))foreach(var dir in Directory.EnumerateDirectories(side).Take(30))Add(opera.Item1+" · "+Path.GetFileName(dir),dir);
  }
  foreach(var browser in new[]{("Chrome","Google\\Chrome\\User Data"),("Edge","Microsoft\\Edge\\User Data"),("Brave","BraveSoftware\\Brave-Browser\\User Data"),("Vivaldi","Vivaldi\\User Data")}){
   string root=Path.Combine(local,browser.Item2);if(!Directory.Exists(root))continue;
   Add(browser.Item1,Path.Combine(root,"Default"));
   foreach(var dir in Directory.EnumerateDirectories(root,"Profile *").Take(30))Add(browser.Item1+" · "+Path.GetFileName(dir),dir);
  }
 }
 void ChooseExternalProfile()
 {
  if(externalImportBusy)return;
  _=Dispatcher.BeginInvoke(async()=>{
   var picker=new OpenFolderDialog{Title="Choose an Opera GX or Chromium profile folder"};
   if(picker.ShowDialog(this)==true)await PrepareExternalProfile(picker.FolderName,Path.GetFileName(picker.FolderName));
  });
 }
 async Task PrepareExternalProfile(string path,string name)
 {
  if(externalImportBusy)return;
  int generation=++externalImportGeneration;
  externalImport?.Dispose();externalImport=null;importBatch=null;externalImportError="";externalImportDone="";externalImportBusy=true;
  await PublishBrowserTools("import");
  try{
   var snapshot=await Task.Run(()=>ExternalProfileImport.Read(path));
   if(generation==externalImportGeneration){externalImport=snapshot;externalImportName=name;externalImportPath=path;}else snapshot.Dispose();
  }catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException){
   // Never expose source paths or stored data in errors/logs.
   App.Log(new IOException("Profile import: "+ex.GetType().Name));
   if(generation==externalImportGeneration)externalImportError="Couldn't read this profile. "+(ex is IOException?ex.Message:"Windows denied access to the profile folder.");
  }finally{externalImportBusy=false;if(!closing)await PublishBrowserTools("import");}
 }
 async Task CompleteExternalProfile(string id,bool bookmarks,bool history,bool passwords,bool cookies,bool autofill)
 {
  if(externalImportBusy||externalImport?.Id!=id)return;
  if(!bookmarks&&!history&&!passwords&&!cookies){Toast("Choose something to import.");return;}
  var snapshot=externalImport;
  externalImportBusy=true;await PublishBrowserTools("import");
  var parts=new List<string>();
  try{
   // Commit exactly the reviewed snapshot into the current profile; never re-read source files.
   if(bookmarks){int n=0;var known=state.Bookmarks.Select(b=>b.Url).ToHashSet();foreach(var b in snapshot.Bookmarks)if(known.Add(b.Url)){state.Bookmarks.Add(b);n++;}parts.Add($"{n} bookmarks");}
   if(history){
    var known=state.History.Select(h=>h.Url).ToHashSet();int n=0;
    foreach(var h in snapshot.History)if(known.Add(h.Url)){state.History.Add(h);n++;}
    state.History=state.History.OrderByDescending(v=>v.At).Take(2000).ToList();parts.Add($"{n} history entries");
   }
   if(passwords){
    var entries=Vault.Read();int n=0;
    foreach(var login in snapshot.Logins)if(!entries.Any(v=>v.Origin==login.Origin&&v.Username==login.Username)){entries.Add(login);n++;}
    Vault.Write(entries);parts.Add($"{n} passwords");
    if(autofill){Prefs.AutoFillPasswords=true;Prefs.OfferPasswordSave=true;Prefs.OfferPasswordUpdate=true;}
   }
   if(cookies){
    var manager=(await ManagementCore()).CookieManager;int n=0;
    foreach(var c in snapshot.Cookies){
     try{
      var cookie=manager.CreateCookie(c.Name,c.Value,c.Domain,c.Path);
      cookie.IsSecure=c.Secure;cookie.IsHttpOnly=c.HttpOnly;
      cookie.SameSite=c.SameSite switch{0 when c.Secure=>CoreWebView2CookieSameSiteKind.None,2=>CoreWebView2CookieSameSiteKind.Strict,_=>CoreWebView2CookieSameSiteKind.Lax};
      if(!c.Session)cookie.Expires=c.Expires.ToLocalTime();
      manager.AddOrUpdateCookie(cookie);n++;
     }catch(ArgumentException){}
    }
    parts.Add($"{n} cookies");
   }
   SaveLater();RenderTabs();
   externalImportDone="Imported "+string.Join(", ",parts)+" from "+externalImportName+".";
   Toast(externalImportDone+(cookies?" Reload open sites to use your signed-in sessions.":""));
  }catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or System.Security.Cryptography.CryptographicException){
   App.Log(ex);externalImportError="The import couldn't be saved. Nothing sensitive was written outside Still's encrypted vault.";
  }finally{snapshot.Dispose();externalImport=null;externalImportBusy=false;await PublishBrowserTools("import");}
 }

 // Chromium browsers hold their cookie database exclusively while running. With the user's
 // explicit request, close the source browser's windows gracefully, then read again.
 async Task CloseSourceAndRetry()
 {
  if(externalImportBusy||externalImport==null)return;
  string path=externalImportPath,name=externalImportName;
  string exe=name.StartsWith("Opera")?"opera":name.StartsWith("Chrome")?"chrome":name.StartsWith("Edge")?"msedge":name.StartsWith("Brave")?"brave":name.StartsWith("Vivaldi")?"vivaldi":"";
  if(exe==""){Toast("Close the source browser, then review again.");return;}
  bool gx=name.StartsWith("Opera GX");
  externalImportBusy=true;await PublishBrowserTools("import");
  await Task.Run(()=>{
   System.Diagnostics.Process[] Matching()=>System.Diagnostics.Process.GetProcessesByName(exe).Where(p=>{
    if(exe!="opera")return true;
    try{return (p.MainModule?.FileName?.Contains("Opera GX",StringComparison.OrdinalIgnoreCase)??false)==gx;}catch{return false;}
   }).ToArray();
   foreach(var p in Matching())try{if(p.MainWindowHandle!=IntPtr.Zero)p.CloseMainWindow();}catch(InvalidOperationException){}
   for(int i=0;i<40&&Matching().Any(p=>{try{return p.MainWindowHandle!=IntPtr.Zero;}catch{return false;}});i++)Thread.Sleep(250);
   Thread.Sleep(1500);
   // Background/tray processes keep the lock after windows close; end only those.
   foreach(var p in Matching())try{if(p.MainWindowHandle==IntPtr.Zero){p.Kill(true);p.WaitForExit(3000);}}catch(Exception){}
  });
  externalImportBusy=false;
  await PrepareExternalProfile(path,name);
 }
}
