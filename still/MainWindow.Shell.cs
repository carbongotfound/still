using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using System.Runtime.InteropServices;
using Microsoft.Web.WebView2.Wpf;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
namespace Still;
public partial class MainWindow
{
 WebView2? shellView;
 Grid? shellRoot;
 Canvas? pageCanvas;
 bool shellReady, shellQueued, overlay;
 int overlayVersion;
 int panelRequestVersion;
 readonly List<string> shellErrors=[];
 CoreWebView2DevToolsProtocolEventReceiver? shellExceptionReceiver;
 double pageX=212,pageY=44,pageWidth=1048,pageHeight=766;
 [DllImport("user32.dll")] static extern bool ReleaseCapture();
 [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h,int msg,IntPtr wp,IntPtr lp);
 [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd,IntPtr after,int x,int y,int cx,int cy,uint flags);
 void RestorePageWindow()
 {
  if(closing||overlay||active?.View is not{} view||!view.IsVisible)return;
  // HwndHost windows have native z-order, independent of WPF's visual tree.
  // Keep the live page above the full-window chrome so it receives pointer input.
  WebHost.UpdateLayout();
  view.UpdateWindowPos();
  if(view.Handle!=IntPtr.Zero)SetWindowPos(view.Handle,IntPtr.Zero,0,0,0,0,0x0001|0x0002|0x0010);
 }
 async Task InitializeShell()
 {
  shellRoot = new Grid { Background = Brushes.Black };
  shellView = new WebView2 {
   CreationProperties = new CoreWebView2CreationProperties { UserDataFolder=Path.Combine(App.DataRoot,"WebView"),ProfileName="Shell" },
   DefaultBackgroundColor = System.Drawing.Color.Black
  };
  ((Panel)WebHost.Parent).Children.Remove(WebHost);
  pageCanvas = new Canvas { Background=null };
  WebHost.Width=pageWidth;WebHost.Height=pageHeight;Canvas.SetLeft(WebHost,pageX);Canvas.SetTop(WebHost,pageY);
  pageCanvas.Children.Add(WebHost);
  shellRoot.Children.Add(shellView);shellRoot.Children.Add(pageCanvas);
  Content=shellRoot;
  var environment=await App.BrowserEnvironment;
  var shellOptions=environment.CreateCoreWebView2ControllerOptions();shellOptions.ProfileName="Shell";
  await shellView.EnsureCoreWebView2Async(environment,shellOptions);
  var core=shellView.CoreWebView2;
  core.Settings.AreDefaultContextMenusEnabled=false;core.Settings.IsStatusBarEnabled=false;
  core.Settings.IsZoomControlEnabled=false;core.Settings.AreDevToolsEnabled=App.IsQa;
  core.Settings.IsPasswordAutosaveEnabled=false;core.Settings.IsGeneralAutofillEnabled=false;
  core.Settings.AreBrowserAcceleratorKeysEnabled=false;core.Settings.AreHostObjectsAllowed=false;
  core.FrameNavigationStarting+=(_,e)=>e.Cancel=true;
  core.SetVirtualHostNameToFolderMapping("still.internal",Path.Combine(AppContext.BaseDirectory,"Shell"),CoreWebView2HostResourceAccessKind.DenyCors);
  core.NavigationStarting+=(_,e)=> { if (e.Uri!="https://still.internal/index.html")e.Cancel=true; };
  core.NewWindowRequested+=(_,e)=>e.Handled=true;
  core.PermissionRequested+=(_,e)=>e.State=CoreWebView2PermissionState.Deny;
  if(App.IsQa){await core.CallDevToolsProtocolMethodAsync("Runtime.enable","{}");shellExceptionReceiver=core.GetDevToolsProtocolEventReceiver("Runtime.exceptionThrown");shellExceptionReceiver.DevToolsProtocolEventReceived+=(_,e)=>shellErrors.Add(e.ParameterObjectAsJson);}
  core.WebMessageReceived+=async (_,e)=> {
   if(e.Source!="https://still.internal/index.html"||core.Source!="https://still.internal/index.html"||e.WebMessageAsJson.Length>65536)return;
   try {
    using var document=JsonDocument.Parse(e.WebMessageAsJson);
    var data=document.RootElement;
    string op=data.GetProperty("op").GetString()??"";
    string S(string key)=>data.TryGetProperty(key,out var v)?v.GetString()??"":"";
    BrowserTab? Target()=>tabs.FirstOrDefault(t=>t.Id==S("id"))??active;
    switch(op) {
     case "ready": shellReady=true;ShellPublish();break;
     case "bounds":
      double ratio=data.TryGetProperty("viewportWidth",out var vp)&&vp.GetDouble()>0?shellView.ActualWidth/vp.GetDouble():1;
      pageX=Math.Clamp(data.GetProperty("x").GetDouble()*ratio,0,ActualWidth);
      pageY=Math.Clamp(data.GetProperty("y").GetDouble()*ratio,0,ActualHeight);
      pageWidth=Math.Clamp(data.GetProperty("width").GetDouble()*ratio,1,ActualWidth);
      pageHeight=Math.Clamp(data.GetProperty("height").GetDouble()*ratio,1,ActualHeight);
      WebHost.Width=pageWidth;WebHost.Height=pageHeight;Canvas.SetLeft(WebHost,pageX);Canvas.SetTop(WebHost,pageY);RestorePageWindow();return;
     case "overlay": await ShellOverlay(data.GetProperty("value").GetBoolean());return;
     case "openPanel": ShellOpen(S("name"),S("value"));break;
     case "sidebarResize": if(data.TryGetProperty("width",out var width)){Prefs.SidebarWidth=Math.Clamp(width.GetDouble(),190,360);SaveLater();}break;
     case "navigate": await Navigate(S("url"));break;
     case "new": await NewTab(S("url"),data.TryGetProperty("private",out var pr)&&pr.GetBoolean(),S("url").Length==0);break;
     case "permissionAnswer": AnswerPermission(S("id"),data.TryGetProperty("allow",out var al)&&al.ValueKind==JsonValueKind.True);break;
     case "select": if(Target() is {} selected)await SelectTab(selected);break;
     case "closeTab": if(Target() is {} closed)await CloseTab(closed,data.TryGetProperty("force",out var force)&&force.GetBoolean());break;
     case "pin": if(Target() is {} pinned){pinned.Pinned=!pinned.Pinned;SaveLater();}break;
     case "duplicate": if(Target() is {} duplicate)await NewTab(duplicate.Url,duplicate.Private,false);break;
     case "sleep": if(Target() is {} sleep){DisposeView(sleep);if(sleep==active)await NewTab("",false,false);SaveLater();}break;
     case "mute": if(Target()?.View?.CoreWebView2 is {} mute)mute.IsMuted=!mute.IsMuted;break;
     case "tearOff":if(Prefs.TabTearOff&&Target() is {} torn&&data.TryGetProperty("x",out var tx)&&data.TryGetProperty("y",out var ty))await MoveTab(torn,null,new Point(tx.GetDouble(),ty.GetDouble()));break;
     case "moveTab":if(Target() is {} mv){var dest=Windows.FirstOrDefault(w=>w.WindowId==S("window")&&!w.closing);if(dest!=null||S("window")=="new")await MoveTab(mv,dest,null);}break;
     case "agentAnswer":AnswerAgent(data.TryGetProperty("allow",out var ag)&&ag.ValueKind==JsonValueKind.True);break;
     case "agentStop":StopAgent();break;
     case "reorder":
      var move=tabs.FirstOrDefault(t=>t.Id==S("id"));var before=tabs.FirstOrDefault(t=>t.Id==S("before"));
      if(move!=null&&before!=null&&move!=before){tabs.Remove(move);tabs.Insert(tabs.IndexOf(before),move);SaveLater();}break;
     case "back": BackClick(this,new());break;
     case "forward": ForwardClick(this,new());break;
     case "reload": ReloadClick(this,new());break;
     case "zoom":if(active?.View is{} zv){double amount=data.GetProperty("amount").GetDouble();zv.ZoomFactor=amount==0?1:Math.Clamp(zv.ZoomFactor+amount,.3,3);}break;
     case "bookmark": ToggleBookmark();break;
     case "reader": CloseSheet(false);await ToggleReader();break;
     case "hide": CloseSheet(false);await PickHidden();break;
     case "pip": CloseSheet(false);await PictureInPicture();break;
     case "find": FindInput.Text=S("text");await FindText();break;
     case "unhide":
      if(active!=null&&Uri.TryCreate(active.Url,UriKind.Absolute,out var page)){state.Hidden.Remove(page.Host);privateHidden.Remove(page.Host);foreach(var t in tabs.Where(t=>t.View?.CoreWebView2!=null))await InstallHiddenRules(t);SaveLater();active.View?.CoreWebView2?.Reload();}break;
     case "siteBlocking":
      if(active!=null&&Uri.TryCreate(active.Url,UriKind.Absolute,out var site)){if(!Prefs.UnblockedHosts.Remove(site.Host))Prefs.UnblockedHosts.Add(site.Host);SaveLater();active.View?.CoreWebView2?.Reload();}break;
     case "preference":
      string value=S("value");switch(S("key")){
       case "theme": if(new[]{"Light","Dark","System"}.Contains(value)){Prefs.Theme=value;ApplyTheme();}break;
       case "layout": if(new[]{"Sidebar","Top"}.Contains(value)){Prefs.Layout=value;ApplyLayout();}break;
       case "search":if(new[]{"DuckDuckGo","Google","Bing"}.Contains(value))Prefs.SearchEngine=value;break;
       case "restore":Prefs.RestoreTabs=value=="true";break;
       case "blocking":Prefs.Blocking=value=="true";break;
       case "tracking":if(new[]{"Basic","Balanced","Strict"}.Contains(value)){Prefs.Tracking=value;foreach(var t in tabs)if(t.View?.CoreWebView2 is {} tc)ApplyProtection(tc);}break;
       case "tearOff":Prefs.TabTearOff=value=="true";SaveLater();foreach(var w in Windows)w.ShellPublish();break;
       case "agents":Prefs.AgentsEnabled=value=="true";if(!Prefs.AgentsEnabled){approvedAgents.Clear();agentApproval?.TrySetResult(false);}SaveLater();foreach(var w in Windows)w.ShellPublish();break;
       case "memory":Prefs.MemorySaver=value=="true";foreach(var t in tabs)if(t.View?.CoreWebView2 is{} mc)mc.MemoryUsageTargetLevel=Prefs.MemorySaver&&t!=active?CoreWebView2MemoryUsageTargetLevel.Low:CoreWebView2MemoryUsageTargetLevel.Normal;break;
       case "autofill":Prefs.Autofill=value=="true";foreach(var t in tabs)if(t.View?.CoreWebView2 is {} ac)ac.Settings.IsGeneralAutofillEnabled=Prefs.Autofill;break;
      }SaveLater();break;
     case "bookmarkMove":{
      int i=state.Bookmarks.FindIndex(v=>v.Url==S("url"));int j=i+(data.TryGetProperty("delta",out var d)&&d.TryGetInt32(out var dv)?Math.Sign(dv):0);
      if(i>=0&&j>=0&&j<state.Bookmarks.Count&&i!=j){(state.Bookmarks[i],state.Bookmarks[j])=(state.Bookmarks[j],state.Bookmarks[i]);SaveLater();}
      break;}
     case "removeBookmark": state.Bookmarks.RemoveAll(v=>v.Url==S("url"));SaveLater();break;
     case "removeHistory":state.History.RemoveAll(v=>v.Url==S("url"));SaveLater();break;
     case "startup":StartupRegistration.Set(data.GetProperty("enabled").GetBoolean());break;
     case "defaultBrowser":BrowserRegistration.Register();BrowserRegistration.OpenDefaultAppsSettings();break;
     case "startupSettings":System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("ms-settings:startupapps"){UseShellExecute=true});break;
     case "clearHistory":state.History.Clear();Save();Toast("History cleared.");break;
     case "clearCookies":
      var regularCore=await ManagementCore();await regularCore.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.AllSite);Toast("Cookies and website data cleared.");break;
     case "chooseDownloads":
      // Native modal dialogs must start after the WebMessage callback returns.
      _=Dispatcher.BeginInvoke(()=>{
       var dialog=new OpenFolderDialog{Title="Choose download folder",InitialDirectory=Prefs.DownloadFolder};
       if(dialog.ShowDialog(this)==true){Prefs.DownloadFolder=dialog.FolderName;foreach(var t in tabs)if(t.View?.CoreWebView2 is {} dc)dc.Profile.DefaultDownloadFolderPath=Prefs.DownloadFolder;SaveLater();}
      });break;
     case "downloadsFolder":Directory.CreateDirectory(Prefs.DownloadFolder);System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe",Prefs.DownloadFolder){UseShellExecute=true});break;
     case "showDownload":
      if(int.TryParse(S("id"),out int index)&&index>=0&&index<downloads.Count)System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe","/select,\""+downloads[index].Path+"\""){UseShellExecute=true});break;
     case "openDownload":if(int.TryParse(S("id"),out int oi)&&oi>=0&&oi<downloads.Count&&downloads[oi].Operation.State==CoreWebView2DownloadState.Completed&&File.Exists(downloads[oi].Path))
       try{System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(downloads[oi].Path){UseShellExecute=true});}catch(System.ComponentModel.Win32Exception){Toast("Windows couldn't open this file.");}break;
     case "openUpdate":if(update!=null)await NewTab(update.Url,false,false);break;
     case "checkUpdate":await CheckForUpdate();if(update==null)Toast("Still is up to date.");break;
     case "cancelDownload":if(int.TryParse(S("id"),out int ci)&&ci>=0&&ci<downloads.Count)downloads[ci].Operation.Cancel();break;
     case "importBookmarks":ChooseImport("bookmarks");break;
     case "exportBookmarks":_ = Dispatcher.BeginInvoke(ExportBookmarks);break;
     case "reopen":ReopenTab();break;
     case "focus":focusMode=!focusMode;ApplyLayout();break;
     case "panel":panel=S("name");break;
     case "drag":ReleaseCapture();SendMessage(new WindowInteropHelper(this).Handle,0xA1,new IntPtr(2),IntPtr.Zero);break;
     case "copyText":{var text=S("text");if(text.Length is >0 and <=8192)try{Clipboard.SetText(text);}catch(System.Runtime.InteropServices.COMException){}break;}
     case "fullscreen":_=Dispatcher.BeginInvoke(DispatcherPriority.Input,async()=>await ToggleFullScreen());break;
     case "exitFullscreen":_=Dispatcher.BeginInvoke(DispatcherPriority.Input,async()=>{if(IsFullScreen){browserFullScreen=false;await ExitContentFullScreen();}});break;
     case "maximize":_=Dispatcher.BeginInvoke(DispatcherPriority.Input,()=>{if(IsFullScreen){browserFullScreen=false;_=ExitContentFullScreen();}else ToggleMaximize();});break;
     case "minimize":WindowState=WindowState.Minimized;break;
     case "closeWindow":Close();break;
     default:await HandleBrowserTool(op,data);break;
    }
    ShellPublish();
   }catch(Exception ex){App.Log(ex);Toast("Couldn't finish that action.");}
  };
  core.Navigate("https://still.internal/index.html");
 }
 void ShellSend(object message)
 {
  if(shellReady&&!closing&&shellView?.CoreWebView2 is {} core)try{core.PostWebMessageAsJson(JsonSerializer.Serialize(message));}catch(Exception ex){App.Log(ex);}
 }
 void ShellPublish()
 {
  if(!shellReady||shellQueued||closing)return;
  shellQueued=true;
  Dispatcher.BeginInvoke(DispatcherPriority.Background,() => {
   shellQueued=false;
   string host=active!=null&&Uri.TryCreate(active.Url,UriKind.Absolute,out var uri)?uri.Host:"";
   ShellSend(new{
    kind="state",activeId=active?.Id,dark,focusMode,fullScreen=contentFullScreen,appFullScreen=IsFullScreen,panel,profileName=ProfileCatalog.CurrentName(),loginOffer=LoginOfferData(),permission=PermissionData(),update=UpdateData(),agent=AgentData(),mcpCommand=Environment.ProcessPath,windows=WindowsData(),secondary,version=CurrentVersion.ToString(3),maximized=WindowState==WindowState.Maximized,zoom=(int)Math.Round((active?.View?.ZoomFactor??1)*100),
    preferences=new{theme=Prefs.Theme,layout=Prefs.Layout,search=Prefs.SearchEngine,restore=Prefs.RestoreTabs,blocking=Prefs.Blocking,downloads=Prefs.DownloadFolder,sidebarWidth=Prefs.SidebarWidth,tracking=Prefs.Tracking,memory=Prefs.MemorySaver,autofill=Prefs.Autofill,startup=StartupRegistration.Enabled,tearOff=Prefs.TabTearOff,agents=Prefs.AgentsEnabled,isDefaultBrowser=BrowserRegistration.IsDefault,startupDisabled=StartupRegistration.DisabledByWindows},
    tabs=tabs.Select(t=>new{id=t.Id,title=t.Title,url=t.Url,pinned=t.Pinned,isPrivate=t.Private,loading=t.Loading,sleeping=(t.View==null&&t.Url.Length>0)||t.View?.CoreWebView2?.IsSuspended==true,blocked=t.Blocked,muted=t.View?.CoreWebView2?.IsMuted==true,favicon=t.Favicon,secure=t.Secure,certificateError=t.CertificateError}),
    history=(active?.Private==true&&panel=="address"?Enumerable.Empty<Visit>():state.History).Take(panel is "history" or "address"?2000:100).Select(h=>new{title=h.Title,url=h.Url,at=h.At}),
    bookmarks=state.Bookmarks.Select(h=>new{title=h.Title,url=h.Url}),
    downloads=downloads.Select((d,i)=>new{id=i.ToString(),name=Path.GetFileName(d.Path),status=d.Operation.State.ToString(),bytes=d.Operation.BytesReceived,total=d.Operation.TotalBytesToReceive??0,isPrivate=d.Private}).Where(d=>!d.isPrivate||active?.Private==true),
    canBack=active?.View?.CoreWebView2?.CanGoBack==true,canForward=active?.View?.CoreWebView2?.CanGoForward==true,
    siteBlocking=Prefs.Blocking&&!Prefs.UnblockedHosts.Contains(host)
   });
  });
 }
 async void ShellOpen(string name,string value="")
 {
  int request=++panelRequestVersion;
  panel=name;
  if(name!="find")await ShellOverlay(true);
  if(new[]{"passwords","extensions","cookies","security","profiles","import"}.Contains(name))await PublishBrowserTools(name);
  if(request!=panelRequestVersion||closing)return;
  ShellSend(new{kind="panel",name,value});ShellPublish();shellView?.Focus();
 }
 Task<byte[]>? snapshotCapture;
 CoreWebView2? snapshotCore;
 static async Task<byte[]> CaptureSnapshot(CoreWebView2 core)
 {
  using var stream=new MemoryStream();await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Jpeg,stream);return stream.ToArray();
 }
 async Task ShellOverlay(bool value)
 {
  int version=++overlayVersion;
  overlay=value;
  if(value){
   if(active?.View?.CoreWebView2 is {} core && WebHost.Visibility==Visibility.Visible){
    try{
     if(snapshotCapture==null||snapshotCapture.IsCompleted){snapshotCore=core;snapshotCapture=CaptureSnapshot(core);}
     // A stalled website must never prevent browser controls from opening.
     if(snapshotCore==core){var bytes=await snapshotCapture.WaitAsync(TimeSpan.FromMilliseconds(180));if(version==overlayVersion)ShellSend(new{kind="snapshot",data="data:image/jpeg;base64,"+Convert.ToBase64String(bytes)});}
    }catch(Exception){}
   }
   if(version==overlayVersion)WebHost.Visibility=Visibility.Hidden;
  }else{
   WebHost.Visibility=Visibility.Visible;
   foreach(var tab in tabs)if(tab.View!=null)tab.View.Visibility=tab==active?Visibility.Visible:Visibility.Hidden;
   ShellSend(new{kind="snapshot",data=""});
   RestorePageWindow();
  }
 }
}
