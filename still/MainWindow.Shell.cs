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
 [DllImport("user32.dll")] static extern int SetWindowRgn(IntPtr hwnd,IntPtr region,bool redraw);
 [DllImport("gdi32.dll")] static extern IntPtr CreateRectRgn(int left,int top,int right,int bottom);
 [DllImport("gdi32.dll")] static extern IntPtr CreateRoundRectRgn(int left,int top,int right,int bottom,int width,int height);
 [DllImport("gdi32.dll")] static extern int CombineRgn(IntPtr dest,IntPtr a,IntPtr b,int mode);
 [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr gdiObject);
 // While an AI drives the page in view, the interface draws a glow around it and its controls over it. The page's
 // window leaves those spots open, so the interface beneath shows through and takes the clicks there.
 (string Tab,double Frame,(double X,double Y,double W,double H,double R)[] Spots) holes=("",0,[]);
 IntPtr holedPage;
 void CutHoles()
 {
  IntPtr page=Shown?.View is {IsVisible:true} view?view.Handle:IntPtr.Zero;
  if(holedPage!=IntPtr.Zero&&holedPage!=page)SetWindowRgn(holedPage,IntPtr.Zero,true);
  holedPage=IntPtr.Zero;
  if(page==IntPtr.Zero)return;
  if(holes.Tab!=Shown!.Id||holes.Frame<=0&&holes.Spots.Length==0||overlay||contentFullScreen||Partner!=null){SetWindowRgn(page,IntPtr.Zero,true);return;}
  var dpi=VisualTreeHelper.GetDpi(this);
  int X(double v)=>(int)Math.Round(v*dpi.DpiScaleX);
  int Y(double v)=>(int)Math.Round(v*dpi.DpiScaleY);
  int frame=X(holes.Frame);
  var region=CreateRectRgn(frame,frame,X(pageWidth)-frame,Y(pageHeight)-frame);
  foreach(var s in holes.Spots){var spot=CreateRoundRectRgn(X(s.X),Y(s.Y),X(s.X+s.W)+1,Y(s.Y+s.H)+1,X(s.R*2),Y(s.R*2));CombineRgn(region,region,spot,4/*RGN_DIFF*/);DeleteObject(spot);}
  if(SetWindowRgn(page,region,true)==0)DeleteObject(region);else holedPage=page; // the window owns the region now
 }
 // A fullscreen video fills the window at once, without waiting for the interface to re-render and report new bounds.
 void PlacePage()
 {
  bool fill=contentFullScreen&&shellRoot!=null;
  WebHost.Width=fill?Math.Max(1,shellRoot!.ActualWidth):pageWidth;WebHost.Height=fill?Math.Max(1,shellRoot!.ActualHeight):pageHeight;
  Canvas.SetLeft(WebHost,fill?0:pageX);Canvas.SetTop(WebHost,fill?0:pageY);
  LayoutSplit();
  if(sidePanelView!=null&&!overlay)sidePanelView.Visibility=fill?Visibility.Hidden:Visibility.Visible; // a docked extension panel never covers a fullscreen video
  RestorePageWindow();
 }
 void RestorePageWindow()
 {
  if(!closing&&!overlay&&!contentFullScreen&&sidePanelView is{} panel&&panel.Handle!=IntPtr.Zero){panel.UpdateWindowPos();SetWindowPos(panel.Handle,IntPtr.Zero,0,0,0,0,0x0001|0x0002|0x0010);} // above the chrome too
  if(closing||overlay||Shown?.View is not{} view||!view.IsVisible)return;
  // HwndHost windows have native z-order, independent of WPF's visual tree.
  // Keep the live page above the full-window chrome so it receives pointer input.
  WebHost.UpdateLayout();
  view.UpdateWindowPos();
  if(view.Handle!=IntPtr.Zero)SetWindowPos(view.Handle,IntPtr.Zero,0,0,0,0,0x0001|0x0002|0x0010);
  if(Partner?.View is {IsVisible:true} side&&side.Handle!=IntPtr.Zero){side.UpdateWindowPos();SetWindowPos(side.Handle,IntPtr.Zero,0,0,0,0,0x0001|0x0002|0x0010);}
  CutHoles();
 }
 async Task InitializeShell()
 {
  shellRoot = new Grid { Background = Brushes.Black };
  shellView = new WebView2 {
   CreationProperties = new CoreWebView2CreationProperties { UserDataFolder=Path.Combine(App.DataRoot,"WebView"),ProfileName="Shell" },
   DefaultBackgroundColor = System.Drawing.Color.FromArgb(0x15, 0x15, 0x17)
  };
  ((Panel)WebHost.Parent).Children.Remove(WebHost);
  pageCanvas = new Canvas { Background=null };
  WebHost.Width=pageWidth;WebHost.Height=pageHeight;Canvas.SetLeft(WebHost,pageX);Canvas.SetTop(WebHost,pageY);
  pageCanvas.Children.Add(WebHost);
  shellRoot.Children.Add(shellView);shellRoot.Children.Add(pageCanvas);
  Content=shellRoot;
  ApplyResizeEdge();
  var environment=await App.BrowserEnvironment;
  var shellOptions=environment.CreateCoreWebView2ControllerOptions();shellOptions.ProfileName="Shell";
  await shellView.EnsureCoreWebView2Async(environment,shellOptions); ClearViewColor();
  StartupMetrics.Mark("shell-controller");
  var core=shellView.CoreWebView2;
  core.Settings.AreDefaultContextMenusEnabled=false;core.Settings.IsStatusBarEnabled=false;
  core.Settings.IsZoomControlEnabled=false;core.Settings.AreDevToolsEnabled=App.IsQa;
  core.Settings.IsPasswordAutosaveEnabled=false;core.Settings.IsGeneralAutofillEnabled=false;
  core.Settings.AreBrowserAcceleratorKeysEnabled=false;core.Settings.AreHostObjectsAllowed=false;
  core.FrameNavigationStarting+=(_,e)=>e.Cancel=true;
  core.SetVirtualHostNameToFolderMapping("still.internal",await AppContent.ShellFolder,CoreWebView2HostResourceAccessKind.DenyCors);
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
    App.Breadcrumb="shell "+op;
    string S(string key)=>data.TryGetProperty(key,out var v)?v.GetString()??"":"";
    BrowserTab? Target()=>tabs.FirstOrDefault(t=>t.Id==S("id"))??active;
    switch(op) {
     case "ready": shellReady=true;StartupMetrics.Mark("shell-ready");ShellPublish();PublishAi();break;
     case "bounds":
      if(contentFullScreen)return; // keep the normal layout bounds for when the video leaves fullscreen
      double ratio=data.TryGetProperty("viewportWidth",out var vp)&&vp.GetDouble()>0?shellView.ActualWidth/vp.GetDouble():1;
      pageX=Math.Clamp(data.GetProperty("x").GetDouble()*ratio,0,ActualWidth);
      pageY=Math.Clamp(data.GetProperty("y").GetDouble()*ratio,0,ActualHeight);
      pageWidth=Math.Clamp(data.GetProperty("width").GetDouble()*ratio,1,ActualWidth);
      pageHeight=Math.Clamp(data.GetProperty("height").GetDouble()*ratio,1,ActualHeight);
      PlacePage();return;
     case "overlay": await ShellOverlay(data.GetProperty("value").GetBoolean());return;
     case "pageHoles":{
      double scale=data.TryGetProperty("viewportWidth",out var hv)&&hv.GetDouble()>0?shellView.ActualWidth/hv.GetDouble():1;
      var spots=data.GetProperty("spots").EnumerateArray().Take(4).Select(s=>(s.GetProperty("x").GetDouble()*scale,s.GetProperty("y").GetDouble()*scale,s.GetProperty("width").GetDouble()*scale,s.GetProperty("height").GetDouble()*scale,s.GetProperty("radius").GetDouble()*scale)).ToArray();
      holes=(data.GetProperty("tab").GetString()??"",Math.Clamp(data.GetProperty("frame").GetDouble()*scale,0,12),spots);
      CutHoles();return;}
     case "openPanel": ShellOpen(S("name"),S("value"));break;
     case "navigate": await Navigate(S("url"));break;
     case "new": await NewTab(S("url"),data.TryGetProperty("private",out var pr)&&pr.GetBoolean(),S("url").Length==0);break;
     case "uploadAnswer": AnswerUpload(S("id"),data.TryGetProperty("picked",out var picked)&&picked.ValueKind==JsonValueKind.Array?picked.EnumerateArray().Where(p=>p.ValueKind==JsonValueKind.Number).Select(p=>p.GetInt32()).ToArray():[],data.TryGetProperty("browse",out var br)&&br.ValueKind==JsonValueKind.True);break;
     case "permissionAnswer": AnswerPermission(S("id"),data.TryGetProperty("allow",out var al)&&al.ValueKind==JsonValueKind.True);break;
     case "select": if(Target() is {} selected)await SelectTab(selected);break;
     case "closeTab": if(Target() is {} closed)await CloseTab(closed,data.TryGetProperty("force",out var force)&&force.GetBoolean());break;
     case "pin": if(Target() is {} pinned){pinned.Pinned=!pinned.Pinned;if(pinned.Pinned)LeaveGroup(pinned);SaveLater();}break;
     case "recent": await SwitchRecent(data.TryGetProperty("step",out var p5step)&&p5step.TryGetInt32(out var p5s)?p5s:1,data.TryGetProperty("held",out var p5held)&&p5held.ValueKind==JsonValueKind.True);break;
     case "recentPick": await PickRecent(tabs.FirstOrDefault(t=>t.Id==S("id")));break;
     case "groupNew": if(Target() is {} p5new){var made=NewGroup(p5new);ShellSend(new{kind="groupRename",id=made.Id});}break;
     case "groupAdd": if(Target() is {} p5add&&state.Groups.Any(g=>g.Id==S("group")))JoinGroup(p5add,S("group"));break;
     case "groupRemove": if(Target() is {} p5out)LeaveGroup(p5out);break;
     case "groupSet": if(state.Groups.FirstOrDefault(g=>g.Id==S("group")) is {} p5g){
       if(data.TryGetProperty("name",out var p5name)&&p5name.ValueKind==JsonValueKind.String)p5g.Name=new string((p5name.GetString()??"").Where(ch=>!char.IsControl(ch)).Take(40).ToArray()).Trim();
       if(GroupColors.Contains(S("color")))p5g.Color=S("color");
       if(data.TryGetProperty("collapsed",out var p5c)&&p5c.ValueKind is JsonValueKind.True or JsonValueKind.False)p5g.Collapsed=p5c.GetBoolean();
       foreach(var w in Windows)w.ShellPublish();SaveLater();}break;
     case "groupUngroup": foreach(var t in tabs.Where(t=>t.Group==S("group")))t.Group="";RenderTabs();SaveLater();break;
     case "groupClose": foreach(var t in tabs.Where(t=>t.Group==S("group")).ToList())await CloseTab(t,true);break;
     case "split": if(Target() is {} p5split)await StartSplit(p5split,S("side")!="left");break;
     case "splitSwap": if(Partner!=null){(splitLeft,splitRight)=(splitRight,splitLeft);LayoutSplit();ShellPublish();}break;
     case "splitRatio": splitRatio=data.TryGetProperty("ratio",out var p5r)&&p5r.TryGetDouble(out var p5rv)?Math.Clamp(p5rv,.2,.8):.5;LayoutSplit();ShellPublish();break;
     case "splitEnd": EndSplit();break;
     case "addressPick": RecordPick(S("typed"),S("url"));break;
     case "duplicate": if(Target() is {} duplicate)await NewTab(duplicate.Url,duplicate.Private,false);break;
     case "sleep": if(Target() is {} sleep){DisposeView(sleep);if(sleep==active)await NewTab("",false,false);SaveLater();}break;
     case "mute": if(Target()?.View?.CoreWebView2 is {} mute)mute.IsMuted=!mute.IsMuted;break;
     case "tearOff":if(Prefs.TabTearOff&&Target() is {} torn&&data.TryGetProperty("x",out var tx)&&data.TryGetProperty("y",out var ty)){var drop=new Point(tx.GetDouble(),ty.GetDouble());await MoveTab(torn,WindowAt(drop),drop);};break;
     case "moveTab":if(Target() is {} mv){var dest=Windows.FirstOrDefault(w=>w.WindowId==S("window")&&!w.closing);if(dest!=null||S("window")=="new")await MoveTab(mv,dest,null);}break;
     case "dialogAnswer":if(Target() is {} asked)AnswerPageDialog(asked,data.TryGetProperty("accept",out var da)&&da.ValueKind==JsonValueKind.True,data.TryGetProperty("text",out var dt)&&dt.ValueKind==JsonValueKind.String?dt.GetString():null);break;
     case "agentAnswer":AnswerAgent(data.TryGetProperty("allow",out var ag)&&ag.ValueKind==JsonValueKind.True);break;
     case "agentStop":StopAgent(data.TryGetProperty("key",out var stopKey)?stopKey.GetString()??"":"");break;
     case "agentTakeOver":await TakeOver(data.TryGetProperty("on",out var takeOn)&&takeOn.ValueKind==JsonValueKind.True,data.TryGetProperty("key",out var takeKey)?takeKey.GetString()??"":"");break;
     case "incognitoWindow":OpenIncognito();break;
     case "reorder":
      var move=tabs.FirstOrDefault(t=>t.Id==S("id"));var before=tabs.FirstOrDefault(t=>t.Id==S("before"));
      if(move!=null&&before!=null&&move!=before){tabs.Remove(move);int at=tabs.IndexOf(before);tabs.Insert(at,move);
       // Dropped between two tabs of a group, it joins; at a group's edge it stays outside, so groups stay together.
       if(move.Group!=before.Group)move.Group=!move.Pinned&&at>0&&tabs[at-1].Group==before.Group?before.Group:"";
       RenderTabs();SaveLater();}break;
     case "back": BackClick(this,new());break;
     case "forward": ForwardClick(this,new());break;
     case "reload": ReloadClick(this,new());break;
     case "zoom":if(Shown?.View is{} zv){double amount=data.GetProperty("amount").GetDouble();zv.ZoomFactor=amount==0?1:Math.Clamp(zv.ZoomFactor+amount,.3,3);}break;
     case "bookmark": ToggleBookmark(tabs.FirstOrDefault(t=>t.Id==S("id")));break;
     case "reader": CloseSheet(false);await ToggleReader();break;
     case "hide": CloseSheet(false);await PickHidden();break;
     case "pictureInPicture": CloseSheet(false);await PictureInPicture();break;
     case "find": FindInput.Text=S("text");await FindText();break;
     case "unhide":
      if(active!=null&&Uri.TryCreate(active.Url,UriKind.Absolute,out var page)){state.Hidden.Remove(page.Host);privateHidden.Remove(page.Host);foreach(var t in tabs.Where(t=>t.View?.CoreWebView2!=null))await InstallHiddenRules(t);SaveLater();active.View?.CoreWebView2?.Reload();}break;
     case "siteBlocking":
      if(active!=null&&Uri.TryCreate(active.Url,UriKind.Absolute,out var site)){if(!Prefs.UnblockedHosts.Remove(site.Host))Prefs.UnblockedHosts.Add(site.Host);SaveLater();var shown=active;await SyncYouTubeScripts();shown.View?.CoreWebView2?.Reload();}break;
     case "preference":
      string value=S("value");switch(S("key")){
       case "theme": if(new[]{"Light","Dark","System"}.Contains(value)){Prefs.Theme=value;ApplyTheme();}break;
       case "search":if(new[]{"DuckDuckGo","Google","Bing"}.Contains(value))Prefs.SearchEngine=value;break;
       case "restore":Prefs.RestoreTabs=value=="true";break;
       case "blocking":Prefs.Blocking=value=="true";_=SyncYouTubeScripts();break;
       case "tracking":if(new[]{"Basic","Balanced","Strict"}.Contains(value)){Prefs.Tracking=value;foreach(var t in tabs)if(t.View?.CoreWebView2 is {} tc)ApplyProtection(tc);}break;
       case "tearOff":Prefs.TabTearOff=value=="true";SaveLater();foreach(var w in Windows)w.ShellPublish();break;
       case "askInChat":Prefs.AgentsAskInChat=value=="true";SaveLater();break;
       case "agents":Prefs.AgentsEnabled=value=="true";if(!Prefs.AgentsEnabled){approvedAgents.Clear();Prefs.ApprovedAgents.Clear();AnswerAgent(false);}SaveLater();foreach(var w in Windows)w.ShellPublish();break;
       case "memory":Prefs.MemorySaver=value=="true";foreach(var w in Windows)w.ApplyMemoryPolicy();break;
       case "sounds":Prefs.Sounds=value=="true";foreach(var w in Windows)w.ShellPublish();break;
       case "newTab":if(value is "companion" or "sites"){Prefs.NewTab=value;foreach(var w in Windows)w.ShellPublish();}break;
       case "tabLayout":if(value is "Classic" or "Modern"){Prefs.TabLayout=value;foreach(var w in Windows)w.ShellPublish();}break;
       case "autofill":Prefs.Autofill=value=="true";foreach(var t in tabs)if(t.View?.CoreWebView2 is {} ac)ac.Settings.IsGeneralAutofillEnabled=Prefs.Autofill;break;
      }SaveLater();break;
     case "bookmarkMove":{
      int i=state.Bookmarks.FindIndex(v=>v.Url==S("url"));int j=i+(data.TryGetProperty("delta",out var d)&&d.TryGetInt32(out var dv)?Math.Sign(dv):0);
      if(i>=0&&j>=0&&j<state.Bookmarks.Count&&i!=j){(state.Bookmarks[i],state.Bookmarks[j])=(state.Bookmarks[j],state.Bookmarks[i]);SaveLater();}
      break;}
     case "removeBookmark": state.Bookmarks.RemoveAll(v=>v.Url==S("url"));SaveLater();break;
     case "removeHistory":state.History.RemoveAll(v=>v.Url==S("url"));SaveLater();break;
     case "startup":StartupRegistration.Set(data.GetProperty("enabled").GetBoolean());break;
     case "welcomeDone":state.Welcome=false;SaveLater();PublishAll();break;
     case "welcomeAgain":state.Welcome=true;welcomeTalk=data.TryGetProperty("talk",out var tk)&&tk.ValueKind==JsonValueKind.True;PublishAll();break;
     case "setupStart" or "setupAnswer" or "setupUndo" or "setupEdit" or "setupEnd":await HandleSetup(op,data);break;
     case "interests":Prefs.Interests=data.TryGetProperty("list",out var picks)&&picks.ValueKind==JsonValueKind.Array?[..picks.EnumerateArray().Where(x=>x.ValueKind==JsonValueKind.String).Select(x=>x.GetString()!.Trim()).Where(x=>x.Length is > 0 and <= 40).Distinct().Take(12)]:[];SaveLater();PublishAll();break;
     case "defaultBrowser":BrowserRegistration.Register();BrowserRegistration.OpenDefaultAppsSettings();break;
     case "startupSettings":System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("ms-settings:startupapps"){UseShellExecute=true});break;
     case "sidebarResize":if(data.TryGetProperty("width",out var p5w)&&p5w.TryGetDouble(out var p5wv)){Prefs.SidebarWidth=Math.Clamp(p5wv,190,360);SaveLater();foreach(var w in Windows)w.ShellPublish();}break;
     case "clearHistory":state.History.Clear();state.AddressPicks.Clear();Save();Toast("History cleared.");break;
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
       // Windows checks a fresh download (SmartScreen, antivirus) before it opens: seconds that must not freeze Still.
       {var file=downloads[oi].Path;_=Task.Run(()=>{try{System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(file){UseShellExecute=true});}catch(System.ComponentModel.Win32Exception){Dispatcher.BeginInvoke(()=>Toast("Windows couldn't open this file."));}});}break;
     case "openUpdate":RestartToUpdate();break;
     case "releaseNotes":if(update!=null)await NewTab(update.Url,false,false);break;
     case "checkUpdate":await CheckForUpdate();if(update==null)Toast("Still is up to date.");break;
     case "cancelDownload":if(int.TryParse(S("id"),out int ci)&&ci>=0&&ci<downloads.Count)downloads[ci].Operation.Cancel();break;
     case "importBookmarks":ChooseImport("bookmarks");break;
     case "exportBookmarks":_ = Dispatcher.BeginInvoke(ExportBookmarks);break;
     case "reopen":ReopenTab();break;
     case "focus":focusMode=!focusMode;ApplyLayout();break;
     case "panel":panel=S("name");break;
     case "drag":ReleaseCapture();SendMessage(new WindowInteropHelper(this).Handle,0xA1,new IntPtr(2),IntPtr.Zero);break;
     case "copyText":{var text=S("text");if(text.Length is >0 and <=8192&&!App.IsQa)try{Clipboard.SetText(text);}catch(System.Runtime.InteropServices.COMException){}break;}
     case "fullscreen":_=Dispatcher.BeginInvoke(DispatcherPriority.Input,async()=>await ToggleFullScreen());break;
     case "exitFullscreen":_=Dispatcher.BeginInvoke(DispatcherPriority.Input,async()=>{if(IsFullScreen){browserFullScreen=false;await ExitContentFullScreen();}});break;
     case "maximize":_=Dispatcher.BeginInvoke(DispatcherPriority.Input,()=>{if(IsFullScreen){browserFullScreen=false;_=ExitContentFullScreen();}else ToggleMaximize();});break;
     case "minimize":WindowState=WindowState.Minimized;break;
     case "closeWindow":Close();break;
     case "permAnswer" or "permSet" or "permSensitive" or "permReset" or "aiToggle" or "aiAsk" or "aiHarness" or "aiNew" or "aiOpenChat" or "aiDeleteChat" or "aiDeleteAll" or "aiSend" or "aiStop" or "aiModel" or "aiLogin" or "aiInstall" or "aiSetupCancel" or "aiCheck" or "aiAnswer" or "chatOpen" or "chatPage" or "chatPopOut" or "tabMine" or "tabHand" or "aiHelpPage" or "aiResumeAll" or "aiResumeDismiss" or "agentChat" or "companionSave" or "companionDelete" or "companionMain" or "companionMode" or "aiAdvanced" or "memoryAdd" or "memoryEdit" or "memoryForget" or "memoryClear" or "chatNoMemory" or "skillSave" or "skillDelete" or "chatArchive" or "aiNow" or "aiUnqueue" or "pickFolder" or "fileRead" or "fileShow" or "fileDelete" or "aiPickFiles" or "aiAttach":await HandleAi(op,data);break;
     case "pluginKey" or "pluginLink" or "pluginKeyRemove" or "pluginRefresh" or "pluginSearch" or "pluginConnect" or "pluginDisconnect" or "pluginToggle":await HandlePlugins(op,data);break;
     default:await HandleBrowserTool(op,data);break;
    }
    ShellPublish();
   }catch(Exception ex){App.Log(ex);Toast("Couldn't finish that action.");}
   finally{if(!App.Breadcrumb.StartsWith("idle"))App.Breadcrumb="idle, last: "+App.Breadcrumb;}
  };
  core.Navigate("https://still.internal/index.html");
 }
 void ShellSend(object message)
 {
  if(!shellReady||closing)return;try{shellView?.CoreWebView2?.PostWebMessageAsJson(JsonSerializer.Serialize(message));}catch(InvalidOperationException){}catch(Exception ex){App.Log(ex);} // a crashed engine throws; Still restarts
 }
 // Windows' "No Sounds" scheme turns Still's own sounds off too. Read once: it rarely changes while Still runs.
 static readonly bool OsSoundsOff = Registry.CurrentUser.OpenSubKey(@"AppEvents\Schemes")?.GetValue("") as string == ".None";
 void ShellPublish()
 {
  if(!shellReady||shellQueued||closing)return;
  shellQueued=true;
  Dispatcher.BeginInvoke(DispatcherPriority.Background,() => {
   shellQueued=false;
   string host=active!=null&&Uri.TryCreate(active.Url,UriKind.Absolute,out var uri)?uri.Host:"";
   ShellSend(new{
    kind="state",activeId=active?.Id,sidePanel=SidePanelData(),pinnedExtensions=PinnedExtensionsData(),dark,focusMode,fullScreen=contentFullScreen,appFullScreen=IsFullScreen,panel,profileName=ProfileCatalog.CurrentName(),loginOffer=LoginOfferData(),permission=PermissionData(),update=UpdateData(),incognito,agent=AgentData(),working=AtWork().Select(w=>agentTabs.GetValueOrDefault(w.Key)).Where(id=>id!=null),dialog=PageDialogData(),mcpCommand=Environment.ProcessPath,windows=WindowsData(),secondary,version=CurrentVersion.ToString(3),maximized=WindowState==WindowState.Maximized,zoom=(int)Math.Round((active?.View?.ZoomFactor??1)*100),
    welcome=state.Welcome&&!secondary&&!incognito,welcomeTalk,
    preferences=new{theme=Prefs.Theme,search=Prefs.SearchEngine,restore=Prefs.RestoreTabs,blocking=Prefs.Blocking,downloads=Prefs.DownloadFolder,tracking=Prefs.Tracking,memory=Prefs.MemorySaver,autofill=Prefs.Autofill,sounds=Prefs.Sounds,osSoundsOff=OsSoundsOff,startup=StartupRegistration.Enabled,tearOff=Prefs.TabTearOff,agents=Prefs.AgentsEnabled,askInChat=Prefs.AgentsAskInChat,isDefaultBrowser=BrowserRegistration.IsDefault,tabLayout=Prefs.TabLayout,newTab=Prefs.NewTab,interests=Prefs.Interests,sidebarWidth=Prefs.SidebarWidth,startupDisabled=StartupRegistration.DisabledByWindows},
    tabs=tabs.Select(t=>new{id=t.Id,group=t.Group,title=t.Title,url=t.Url,pinned=t.Pinned,agent=t.Agent,runChat=t.RunChat,driverChat=t.AgentKey is{} k&&runs.ContainsKey(k)?k:null,aiGroup=t.AgentGroup,chatId=t.ChatId,inChat=t.InChat,isPrivate=t.Private,loading=t.Loading,sleeping=(t.View==null&&t.Url.Length>0)||t.View?.CoreWebView2?.IsSuspended==true,blocked=t.Blocked,muted=t.View?.CoreWebView2?.IsMuted==true,inUse=t.InUse,favicon=t.Favicon,secure=t.Secure,certificateError=t.CertificateError}),
    history=(active?.Private==true&&panel=="address"?Enumerable.Empty<Visit>():state.History).Take(panel is "history" or "address"?2000:100).Select(h=>new{title=h.Title,url=h.Url,at=h.At}),
    groups=state.Groups.Where(g=>tabs.Any(t=>t.Group==g.Id)).Select(g=>new{id=g.Id,name=g.Name,color=g.Color,collapsed=g.Collapsed}),
    split=Partner!=null?new{left=splitLeft!.Id,right=splitRight!.Id,ratio=splitRatio}:null,
    picks=(active?.Private==true?Enumerable.Empty<AddressPick>():state.AddressPicks).Select(p=>new{typed=p.Typed,url=p.Url,count=p.Count}),
    bookmarks=state.Bookmarks.Select(h=>new{title=h.Title,url=h.Url,favicon=h.Favicon}),
    downloads=downloads.Select((d,i)=>new{id=i.ToString(),name=Path.GetFileName(d.Path),status=d.Operation.State.ToString(),bytes=d.Operation.BytesReceived,total=d.Operation.TotalBytesToReceive??0,isPrivate=d.Private}).Where(d=>!d.isPrivate||active?.Private==true),
    canBack=Shown?.View?.CoreWebView2?.CanGoBack==true,canForward=Shown?.View?.CoreWebView2?.CanGoForward==true,
    chatPage=active?.ChatId!=null&&Shown is {} sp?new{id=sp.Id,url=sp.Url,title=sp.Title,loading=sp.Loading,favicon=sp.Favicon}:null,
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
   if(Shown?.View?.CoreWebView2 is {} core && WebHost.Visibility==Visibility.Visible){
    try{
     if(snapshotCapture==null||snapshotCapture.IsCompleted){snapshotCore=core;snapshotCapture=CaptureSnapshot(core);}
     // A stalled website must never prevent browser controls from opening.
     var pairShot=Partner?.View?.CoreWebView2 is {} pairCore?CaptureSnapshot(pairCore):null; // split view: both halves
     if(snapshotCore==core){var bytes=await snapshotCapture.WaitAsync(TimeSpan.FromMilliseconds(180));
      string? partner=null;if(pairShot!=null)try{partner="data:image/jpeg;base64,"+Convert.ToBase64String(await pairShot.WaitAsync(TimeSpan.FromMilliseconds(120)));}catch(Exception){}
      if(version==overlayVersion)ShellSend(new{kind="snapshot",data="data:image/jpeg;base64,"+Convert.ToBase64String(bytes),partner});}
    }catch(Exception){}
   }
   if(version==overlayVersion){WebHost.Visibility=Visibility.Hidden;if(sidePanelView!=null)sidePanelView.Visibility=Visibility.Hidden;}
  }else{
   WebHost.Visibility=Visibility.Visible;if(sidePanelView!=null)sidePanelView.Visibility=Visibility.Visible;
   var shown=Shown;var partner=Partner;foreach(var tab in tabs)if(tab.View!=null)tab.View.Visibility=tab==shown||tab==partner?Visibility.Visible:Visibility.Hidden;
   LayoutSplit();
   ShellSend(new{kind="snapshot",data=""});
   if(snapshotCapture?.IsCompleted==true){snapshotCapture=null;snapshotCore=null;}
   RestorePageWindow();
  }
 }
}
