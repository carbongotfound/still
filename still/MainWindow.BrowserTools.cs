using System.IO;
using System.Text.Json;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using Microsoft.Win32;
namespace Still;
public partial class MainWindow
{
 WebView2? managementView;
 readonly Dictionary<string,(CoreWebView2Cookie Cookie,CoreWebView2CookieManager Manager)> cookieInventory=[];
 readonly Dictionary<string,CoreWebView2BrowserExtension> extensionInventory=[];
 string? extensionCandidatePath;
 string? extensionManifestHash;
 string? extensionContentHash;
 int extensionReviewVersion;
 bool extensionInstalling;
 string? copiedPassword;
 long clipboardVersion;
 object? extensionCandidate;
 readonly Dictionary<string,string> extensionPages=[];
 void ApplyProtection(CoreWebView2 core)
 {
  core.Settings.AreHostObjectsAllowed=false;
  core.Settings.IsReputationCheckingRequired=true;
  core.Profile.PreferredTrackingPreventionLevel=Enum.Parse<CoreWebView2TrackingPreventionLevel>(Prefs.Tracking);
  core.Settings.IsGeneralAutofillEnabled=Prefs.Autofill;
  // Saved logins use Still's Windows-protected vault, with explicit per-origin filling.
  core.Settings.IsPasswordAutosaveEnabled=false;
 }
 async Task UpdateFavicon(BrowserTab tab,CoreWebView2 core)
 {
  try{string page=core.Source;using var source=await core.GetFaviconAsync(CoreWebView2FaviconImageFormat.Png);if(source==null||tab.Closed)return;using var data=new MemoryStream();await source.CopyToAsync(data);if(core.Source==page&&tab.View?.CoreWebView2==core&&data.Length is >0 and <131072){tab.Favicon="data:image/png;base64,"+Convert.ToBase64String(data.ToArray());SaveLater();}}catch(Exception){/* A missing or cancelled favicon uses the globe fallback. */}
 }
 async Task<CoreWebView2> ManagementCore()
 {
  if(tabs.FirstOrDefault(t=>!t.Private&&t.View?.CoreWebView2!=null)?.View?.CoreWebView2 is {} ready)return ready;
  if(managementView?.CoreWebView2 is {} existing)return existing;
  managementView=new WebView2{Visibility=Visibility.Hidden};WebHost.Children.Add(managementView);
  var env=await App.BrowserEnvironment;var options=env.CreateCoreWebView2ControllerOptions();options.ProfileName="Default";
  await managementView.EnsureCoreWebView2Async(env,options);ApplyProtection(managementView.CoreWebView2);return managementView.CoreWebView2;
 }
 async Task PublishBrowserTools(string name)
 {
  try{
   object data=new{};
   if(name=="passwords")data=new{vault=Vault.Read().Select(v=>new{id=v.Id,origin=v.Origin,username=v.Username}),offer=LoginOfferData(),passwordOptions=new{save=Prefs.OfferPasswordSave,fill=Prefs.AutoFillPasswords,update=Prefs.OfferPasswordUpdate}};
   if(name=="profiles")data=ProfileData();
   if(name=="import"){DiscoverExternalProfiles();data=ImportData();}
   if(name=="cookies"){
    var core=active?.View?.CoreWebView2??await ManagementCore();var manager=core.CookieManager;
    var cookies=await manager.GetCookiesAsync("");cookieInventory.Clear();
    foreach(var cookie in cookies.OrderBy(c=>c.Domain).ThenBy(c=>c.Name).Take(2000))cookieInventory[Guid.NewGuid().ToString("N")]=(cookie,manager);
    data=new{isPrivate=active?.Private==true,cookies=cookieInventory.Select(k=>new{id=k.Key,name=k.Value.Cookie.Name,domain=k.Value.Cookie.Domain,path=k.Value.Cookie.Path,secure=k.Value.Cookie.IsSecure,httpOnly=k.Value.Cookie.IsHttpOnly,session=k.Value.Cookie.IsSession})};
   }
   if(name=="extensions"){
    var core=await ManagementCore();extensionInventory.Clear();foreach(var extension in await core.Profile.GetBrowserExtensionsAsync())
     // The runtime also returns internal PDF/clipboard extensions. Only expose
     // user-installed extensions here, not engine components.
     if(File.Exists(Path.Combine(App.DataRoot,"Extensions",extension.Id+".path")))extensionInventory[extension.Id]=extension;
    data=new{extensions=extensionInventory.Values.Select(e=>new{id=e.Id,name=e.Name,enabled=e.IsEnabled,hasPage=GetExtensionPage(e.Id)!=null,officialVersion=OfficialVersion(e.Id)}),candidate=extensionCandidate,official=officialCandidate==null?null:new{version=officialCandidate.Version,sha256=officialCandidate.Sha256},downloading=extensionDownload};
   }
   if(name=="security"){
    var core=active?.View?.CoreWebView2??await ManagementCore();var permissions=await core.Profile.GetNonDefaultPermissionSettingsAsync();
    data=new{tracking=core.Profile.PreferredTrackingPreventionLevel.ToString(),reputationRequested=core.Settings.IsReputationCheckingRequired,permissions=permissions.Select(p=>new{origin=p.PermissionOrigin,kind=p.PermissionKind.ToString(),state=p.PermissionState.ToString()}),engine=core.Environment.BrowserVersionString};
   }
   ShellSend(new{kind="tools",name,data});
  }catch(Exception ex){ShellSend(new{kind="tools",name,data=new{error=ex.Message}});}
 }
 async Task HandleBrowserTool(string op,JsonElement data)
 {
  string S(string key)=>data.TryGetProperty(key,out var v)?v.GetString()??"":"";
  switch(op){
   case "profileCreate":await ProfileCatalog.Create(S("name"));await PublishBrowserTools("profiles");break;
   case "profileOpen":OpenBrowserProfile(S("id"));break;
   case "profileLaunch":ProfileCatalog.SetLaunch(S("id"));await PublishBrowserTools("profiles");break;
   case "profileDelete":{string id=S("id");_ = Dispatcher.BeginInvoke(()=>ConfirmProfileRemoval(id,false));break;}
   case "profileResetDefault":_ = Dispatcher.BeginInvoke(()=>ConfirmProfileRemoval("default",true));break;
   case "importChoose":ChooseImport(S("kind"));break;
   case "externalChoose":ChooseExternalProfile();break;
   case "externalReview":if(externalSources.TryGetValue(S("id"),out var source))await PrepareExternalProfile(source.Path,source.Name);break;
   case "externalCancel":if(!externalImportBusy){externalImport?.Dispose();externalImport=null;externalImportError="";await PublishBrowserTools("import");}break;
   case "externalCloseSource":await CloseSourceAndRetry();break;
   case "externalConfirm":{bool B(string k)=>data.TryGetProperty(k,out var v)&&v.ValueKind==JsonValueKind.True;await CompleteExternalProfile(S("id"),B("bookmarks"),B("history"),B("passwords"),B("cookies"),B("autofill"));break;}
   case "importConfirm":await CompleteImport(S("id"),data.TryGetProperty("replace",out var replace)&&replace.GetBoolean());break;
   case "importCancel":importBatch=null;await PublishBrowserTools("import");break;
   case "exportData":ExportBrowserData();break;
   case "officialBlocker":await PrepareOfficialBlocker();break;
   case "officialSource":await NewTab("https://github.com/uBlockOrigin/uBOL-home",false,false);break;
   case "loginAccept":await AcceptLoginOffer(S("id"),S("username"));break;
   case "loginDismiss":loginOffer=null;ShellPublish();await PublishBrowserTools("passwords");break;
   case "passwordPermission":{
    bool enabled=data.TryGetProperty("enabled",out var allowed)&&allowed.GetBoolean();
    switch(S("feature")){case "save":Prefs.OfferPasswordSave=enabled;break;case "fill":Prefs.AutoFillPasswords=enabled;break;case "update":Prefs.OfferPasswordUpdate=enabled;break;default:return;}
    if(!Prefs.OfferPasswordSave&&!Prefs.OfferPasswordUpdate)loginOffer=null;
    foreach(var tab in tabs.Where(t=>t.View?.CoreWebView2!=null&&!t.Private)){await InstallLoginObserver(tab);if(tab==active)await InspectLogin(tab);}
    SaveLater();await PublishBrowserTools("passwords");break;
   }
   case "refreshTools":await PublishBrowserTools(S("name"));break;
   case "vaultGenerate":ShellSend(new{kind="vaultGenerated",password=Vault.Generate()});break;
   case "vaultSave":{
    if(!Uri.TryCreate(S("origin"),UriKind.Absolute,out var origin)||origin.Scheme is not("https" or "http")){Toast("Enter a complete website address.");break;}
    if(S("password").Length is <1 or >8192||S("username").Length>1024){Toast("Enter a password.");break;}
    var entries=Vault.Read();var normalized=origin.GetLeftPart(UriPartial.Authority);
    var entry=entries.FirstOrDefault(v=>v.Origin==normalized&&v.Username==S("username"));if(entry==null){entry=new LoginEntry();entries.Add(entry);}
    entry.Origin=normalized;entry.Username=S("username");entry.Password=S("password");Vault.Write(entries);
    await PublishBrowserTools("passwords");ShellSend(new{kind="vaultSaved"});Toast("Login saved for this Windows account.");break;
   }
   case "vaultDelete":{var entries=Vault.Read();entries.RemoveAll(v=>v.Id==S("id"));Vault.Write(entries);await PublishBrowserTools("passwords");break;}
   case "vaultCopy":{
    var entry=Vault.Read().FirstOrDefault(v=>v.Id==S("id"));if(entry==null)break;Clipboard.SetText(entry.Password);copiedPassword=entry.Password;Toast("Password copied. Clipboard clears in 30 seconds.");_ = ClearPasswordClipboard(entry.Password,++clipboardVersion);break;
   }
   case "vaultFill":{
    var entry=Vault.Read().FirstOrDefault(v=>v.Id==S("id"));var tab=active;
    if(entry==null||tab?.View?.CoreWebView2 is not{} core||!Uri.TryCreate(tab.Url,UriKind.Absolute,out var url)||url.GetLeftPart(UriPartial.Authority)!=entry.Origin||!(url.Scheme=="https"||url.IsLoopback)||tab.CertificateError){Toast("Open this login's exact secure website before filling it.");break;}
    if(await FillSavedLogin(entry,tab)){CloseSheet();Toast("Login filled. Review it, then sign in.");}else Toast("No matching visible login form was found.");break;
   }
   case "cookieDelete":if(cookieInventory.TryGetValue(S("id"),out var cookie)){await DeleteStoredCookie(cookie.Cookie,cookie.Manager);await PublishBrowserTools("cookies");}break;
   case "cookieDeleteDomain":foreach(var item in cookieInventory.Values.Where(v=>v.Cookie.Domain==S("domain")).ToArray())await DeleteStoredCookie(item.Cookie,item.Manager);await PublishBrowserTools("cookies");break;
   case "permissionReset":{
    var core=active?.View?.CoreWebView2??await ManagementCore();if(Enum.TryParse<CoreWebView2PermissionKind>(S("kind"),out var kind))await core.Profile.SetPermissionStateAsync(kind,S("origin"),CoreWebView2PermissionState.Default);await PublishBrowserTools("security");break;
   }
   case "extensionChoose":_ = Dispatcher.BeginInvoke(async()=>{var folder=new OpenFolderDialog{Title="Choose an unpacked extension folder"};if(folder.ShowDialog(this)==true)try{await StageExtension(folder.FolderName);}catch(Exception ex){Toast(ex.Message);}});break;
   case "extensionCancel":extensionCandidate=null;extensionCandidatePath=null;officialCandidate=null;await PublishBrowserTools("extensions");break;
   case "extensionInstall":if(!extensionInstalling){extensionInstalling=true;try{await InstallExtension();}catch(IOException ex){Toast(ex.Message);}finally{extensionInstalling=false;}}break;
   case "extensionToggle":if(extensionInventory.TryGetValue(S("id"),out var toggle)){await toggle.EnableAsync(!toggle.IsEnabled);await PublishBrowserTools("extensions");}break;
   case "extensionRemove":if(extensionInventory.TryGetValue(S("id"),out var remove)){await remove.RemoveAsync();await PublishBrowserTools("extensions");}break;
   case "extensionPage":if(extensionInventory.ContainsKey(S("id"))&&GetExtensionPage(S("id")) is{} entryPage)await NewTab(entryPage,false,false);break;
   case "bookmarkEdit":{
    var bookmark=state.Bookmarks.FirstOrDefault(b=>b.Url==S("oldUrl"));if(bookmark!=null&&Uri.TryCreate(S("url"),UriKind.Absolute,out var u)&&u.Scheme is "http" or "https"){bookmark.Title=S("title").Trim();bookmark.Url=u.AbsoluteUri;SaveLater();}break;
   }
  }
 }
 async Task DeleteStoredCookie(CoreWebView2Cookie cookie,CoreWebView2CookieManager manager)
 {
  manager.DeleteCookie(cookie);
  // DeleteCookie queues work in the browser process. Wait for the store to
  // acknowledge it before republishing the list, otherwise a deleted row reappears.
  for(int attempt=0;attempt<10;attempt++){
   await Task.Delay(40);
   var remaining=await manager.GetCookiesAsync("");
   if(!remaining.Any(c=>c.Name==cookie.Name&&c.Domain==cookie.Domain&&c.Path==cookie.Path))return;
  }
 }
 async Task ClearPasswordClipboard(string password,long version)
 {
  await Task.Delay(30000);if(closing||version!=clipboardVersion)return;
  try{if(Clipboard.ContainsText()&&Clipboard.GetText()==password)Clipboard.Clear();}catch(Exception){}finally{copiedPassword=null;}
 }
 void ClearOwnedPasswordClipboard()
 {
  try{if(copiedPassword!=null&&Clipboard.ContainsText()&&Clipboard.GetText()==copiedPassword)Clipboard.Clear();}catch(Exception){}finally{copiedPassword=null;}
 }
 async Task StageExtension(string folder)
 {
  if(extensionInstalling)throw new InvalidOperationException("Wait for the current extension installation to finish.");
  int review=++extensionReviewVersion;
  var path=Path.GetFullPath(folder);string manifestPath=Path.Combine(path,"manifest.json");if(new FileInfo(manifestPath).Length>1024*1024)throw new IOException("The extension manifest is too large.");
  byte[] manifestBytes=await File.ReadAllBytesAsync(manifestPath);using var manifest=JsonDocument.Parse(manifestBytes);
  var root=manifest.RootElement;string name=ExtensionName(root,path);var permissions=new List<string>();officialCandidate=null;
  foreach(string key in new[]{"permissions","host_permissions","optional_permissions","optional_host_permissions"})if(root.TryGetProperty(key,out var list))permissions.AddRange(list.EnumerateArray().Select(v=>v.GetString()??""));
  if(root.TryGetProperty("content_scripts",out var scripts))foreach(var script in scripts.EnumerateArray())if(script.TryGetProperty("matches",out var matches))permissions.AddRange(matches.EnumerateArray().Select(v=>v.GetString()??""));
  string contentHash=await Task.Run(()=>ExtensionTreeHash(path));
  if(review!=extensionReviewVersion)return;
  extensionCandidatePath=path;extensionContentHash=contentHash;extensionManifestHash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(manifestBytes));extensionCandidate=new{name,permissions=permissions.Distinct().ToArray()};await PublishBrowserTools("extensions");
 }
 static string ExtensionTreeHash(string folder)
 {
  using var digest=System.Security.Cryptography.IncrementalHash.CreateHash(System.Security.Cryptography.HashAlgorithmName.SHA256);
  var dirs=new Queue<string>();dirs.Enqueue(folder);var files=new List<string>();long total=0;
  while(dirs.Count>0){string directory=dirs.Dequeue();if((File.GetAttributes(directory)&FileAttributes.ReparsePoint)!=0)throw new IOException("Extension folders cannot contain links.");foreach(var file in Directory.EnumerateFileSystemEntries(directory)){
   var attributes=File.GetAttributes(file);if((attributes&FileAttributes.ReparsePoint)!=0)throw new IOException("Extension folders cannot contain links.");
   if((attributes&FileAttributes.Directory)!=0)dirs.Enqueue(file);else{files.Add(file);total+=new FileInfo(file).Length;if(files.Count>20000||total>200*1024*1024)throw new IOException("Extension is too large.");}
  }}
  foreach(var file in files.OrderBy(f=>Path.GetRelativePath(folder,f),StringComparer.Ordinal)){
   digest.AppendData(System.Text.Encoding.UTF8.GetBytes(Path.GetRelativePath(folder,file)));digest.AppendData([0]);
   using var stream=File.OpenRead(file);digest.AppendData(System.Security.Cryptography.SHA256.HashData(stream));
  }
  return Convert.ToHexString(digest.GetHashAndReset());
 }
 async Task InstallExtension()
 {
  if(extensionCandidatePath==null)return;
  string source=extensionCandidatePath,destination=Path.Combine(App.DataRoot,"Extensions",Guid.NewGuid().ToString("N"));
  string? expectedManifest=extensionManifestHash;
  string? expectedContent=extensionContentHash;var reviewedOfficial=officialCandidate;
  await Task.Run(()=>{
   var dirs=new Queue<string>();dirs.Enqueue(source);long total=0;int count=0;var files=new List<(string Source,string Relative)>();
   while(dirs.Count>0){string current=dirs.Dequeue();if((File.GetAttributes(current)&FileAttributes.ReparsePoint)!=0)throw new IOException("Extension folders cannot contain links.");foreach(var path in Directory.EnumerateFileSystemEntries(current)){var attr=File.GetAttributes(path);if((attr&FileAttributes.ReparsePoint)!=0)throw new IOException("Extension folders cannot contain links.");if((attr&FileAttributes.Directory)!=0)dirs.Enqueue(path);else{total+=new FileInfo(path).Length;if(++count>20000||total>200*1024*1024)throw new IOException("Extension folder exceeds 200 MB or 20,000 files.");files.Add((path,Path.GetRelativePath(source,path)));}}}
   foreach(var file in files){string target=Path.GetFullPath(Path.Combine(destination,file.Relative));if(!target.StartsWith(destination+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Invalid extension path.");Directory.CreateDirectory(Path.GetDirectoryName(target)!);File.Copy(file.Source,target);}
  });
  if(expectedManifest==null||Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(await File.ReadAllBytesAsync(Path.Combine(destination,"manifest.json"))))!=expectedManifest)throw new IOException("The extension permissions changed. Choose the folder again to review them.");
  if(expectedContent==null||await Task.Run(()=>ExtensionTreeHash(destination))!=expectedContent)throw new IOException("The extension files changed after review. Review the extension again.");
  var core=await ManagementCore();var previousOfficial=reviewedOfficial==null?[]:(await core.Profile.GetBrowserExtensionsAsync()).Where(e=>OfficialVersion(e.Id)!=null).ToArray();
  var installed=await core.Profile.AddBrowserExtensionAsync(destination);
  File.WriteAllText(Path.Combine(destination,"..",installed.Id+".path"),destination);
  if(reviewedOfficial!=null){File.WriteAllText(Path.Combine(App.DataRoot,"Extensions",installed.Id+".official.json"),JsonSerializer.Serialize(reviewedOfficial));foreach(var prior in previousOfficial)if(prior.Id!=installed.Id)await prior.RemoveAsync();}
  extensionCandidate=null;extensionCandidatePath=null;officialCandidate=null;await PublishBrowserTools("extensions");Toast("Extension added. Reload open pages to use it.");
 }
 string? GetExtensionPage(string id)
 {
  try{
   if(extensionPages.TryGetValue(id,out var cached))return cached;
   var folder=File.ReadAllText(Path.Combine(App.DataRoot,"Extensions",id+".path"));using var json=JsonDocument.Parse(File.ReadAllText(Path.Combine(folder,"manifest.json")));var m=json.RootElement;string? page=null;
   if(m.TryGetProperty("options_page",out var option))page=option.GetString();
   else if(m.TryGetProperty("options_ui",out var options)&&options.TryGetProperty("page",out var op))page=op.GetString();
   else if(m.TryGetProperty("action",out var action)&&action.TryGetProperty("default_popup",out var popup))page=popup.GetString();
   if(page!=null&&!page.Contains("..")&&!page.Contains(':'))return extensionPages[id]="chrome-extension://"+id+"/"+page.TrimStart('/');
  }catch(Exception){}
  return null;
 }
}
