#if STILL_QA
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
namespace Still;
// Compiled only into explicit test builds. Never included in release binaries.
public partial class MainWindow
{
 void StartQa()
 {
  string name = "StillQa-" + Environment.ProcessId;
  File.WriteAllText(Path.Combine(App.DataRoot, "qa-pipe.txt"), name);
  _ = Task.Run(async () => {
   while (!closing) {
    try {
     using var pipe = new NamedPipeServerStream(name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
     await pipe.WaitForConnectionAsync();
     using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, true);
     using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true };
     string? line = await reader.ReadLineAsync();
     if (line == null) continue;
     string reply = await (await Dispatcher.InvokeAsync(async () => {
      try {
       using var doc = JsonDocument.Parse(line);
       string op = doc.RootElement.GetProperty("op").GetString() ?? "";
       if (op == "state") return JsonSerializer.Serialize(new {
        activeId = active?.Id, panel, dark, theme = Prefs.Theme, aiCalls = AgentRun.Launched, startup=StartupMetrics.Timings, fullScreen=IsFullScreen,browserFullScreen,contentFullScreen,windowState=WindowState.ToString(),focusMode, shellErrors, sidePanelUrl = sidePanelView?.Source?.ToString(), sidePanelWidth = sidePanelView?.ActualWidth, extensionPopup = extensionPopup != null,
        viewport = new{pageX,pageY,pageWidth,pageHeight,visible=WebHost.Visibility.ToString(),viewWidth=active?.View?.ActualWidth,viewHeight=active?.View?.ActualHeight,hostWidth=WebHost.ActualWidth,hostHeight=WebHost.ActualHeight,zoom=active?.View?.ZoomFactor},
        protection = new{reputation=active?.View?.CoreWebView2?.Settings.IsReputationCheckingRequired,tracking=active?.View?.CoreWebView2?.Profile.PreferredTrackingPreventionLevel.ToString(),blocking=Prefs.Blocking},
        windows = Windows.Select(w => new { id = w.WindowId, tabs = w.tabs.Select(t => t.Url), privateTabs = w.tabs.Count(t => t.Private), w.secondary, w.incognito, w.temporary, left = w.Left, top = w.Top }),
        title = Title, width = ActualWidth, height = ActualHeight, left = Left, top = Top,
        tabs = tabs.Select(t => new { t.Id, t.Title, t.Url, t.Pinned, t.Private, t.InChat, t.RunChat, t.ChatId, t.Loading, ready = t.View?.CoreWebView2 != null, t.Reader, t.Blocked, muted=t.View?.CoreWebView2?.IsMuted==true, t.InUse, favicon=t.Favicon.Length>0,t.Secure,t.CertificateError,suspended=t.View?.CoreWebView2?.IsSuspended,activeDownloads=t.ActiveDownloads,memory=t.View?.CoreWebView2?.MemoryUsageTargetLevel.ToString(),visible = t.View?.Visibility.ToString() }),
        history = state.History, bookmarks = state.Bookmarks, hidden = state.Hidden,
        downloads = downloads.Select(d => new { d.Path, status = d.Operation.State.ToString(), bytes = d.Operation.BytesReceived }),
        profilePrivate = active?.View?.CoreWebView2?.Profile.IsInPrivateModeEnabled,
        back = active?.View?.CoreWebView2?.CanGoBack, forward = active?.View?.CoreWebView2?.CanGoForward,
        processMemory = System.Diagnostics.Process.GetCurrentProcess().WorkingSet64
       });
       if (op == "windowAt") { double x = doc.RootElement.GetProperty("x").GetDouble(), y = doc.RootElement.GetProperty("y").GetDouble(); return JsonSerializer.Serialize(new { found = WindowAt(new System.Windows.Point(x, y))?.WindowId }); }
       if (op == "checkUpdate") { await CheckForUpdate(); return JsonSerializer.Serialize(new { update = UpdateData(), installer = update?.Installer, exists = update?.Installer != null && File.Exists(update.Installer) }); }
       if (op == "evalTab") { var id = doc.RootElement.GetProperty("id").GetString(); return Windows.SelectMany(w => w.tabs).FirstOrDefault(t => t.Id == id)?.View?.CoreWebView2 is { } any ? await any.RunAsync(doc.RootElement.GetProperty("script").GetString() ?? "") : "{\"error\":\"no page\"}"; }
       if (op == "tabs") return JsonSerializer.Serialize(new { layout = Prefs.TabLayout, groups = state.Groups, picks = state.AddressPicks, recent = recent?.Select(t => t.Id), recentIndex,
        split = new { left = splitLeft?.Id, right = splitRight?.Id, ratio = splitRatio, partner = Partner?.Id, leftWidth = splitLeft?.View?.ActualWidth, rightWidth = splitRight?.View?.ActualWidth, rightVisible = splitRight?.View?.IsVisible, leftVisible = splitLeft?.View?.IsVisible },
        windows = Windows.Select(w => new { id = w.WindowId, active = w.active?.Id, tabs = w.tabs.Select(t => new { t.Id, t.Url, t.Group, wired = t.Wire != null, visible = t.View?.IsVisible }) }),
        order = tabs.Select(t => t.Id) });
       if (op == "eval" && (doc.RootElement.TryGetProperty("tab", out var evalTab) ? tabs.FirstOrDefault(t => t.Id == evalTab.GetString()) : Shown ?? active)?.View?.CoreWebView2 is { } core) return await core.RunAsync(doc.RootElement.GetProperty("script").GetString() ?? ""); // the page in view, or a given tab
       if (op == "stageExtension") { await StageExtension(doc.RootElement.GetProperty("path").GetString()!);return "{\"ok\":true}"; }
       if (op == "stageStorePackage") { await StageStorePackage(await File.ReadAllBytesAsync(doc.RootElement.GetProperty("path").GetString()!),doc.RootElement.GetProperty("id").GetString()!);return "{\"ok\":true}"; }
       if (op == "stageImport") { await PrepareImport(doc.RootElement.GetProperty("kind").GetString()!,doc.RootElement.GetProperty("path").GetString()!);return "{\"ok\":true}"; }
       if (op == "stageExternalProfile") { await PrepareExternalProfile(doc.RootElement.GetProperty("path").GetString()!,doc.RootElement.TryGetProperty("name", out var source) ? source.GetString()! : "Opera GX");return "{\"ok\":true}"; }
       if (op == "shellEval" && shellView?.CoreWebView2 is { } ui) return await ui.ExecuteScriptAsync(doc.RootElement.GetProperty("script").GetString() ?? "");
       if (op == "shellCdp" && shellView?.CoreWebView2 is { } dev) return await dev.CallDevToolsProtocolMethodAsync(doc.RootElement.GetProperty("method").GetString()!,doc.RootElement.GetProperty("parameters").GetRawText());
       if (op == "pageCdp" && active?.View?.CoreWebView2 is { } pageDev) return await pageDev.CallDevToolsProtocolMethodAsync(doc.RootElement.GetProperty("method").GetString()!,doc.RootElement.GetProperty("parameters").GetRawText());
       if (op == "key") { var key = Enum.Parse<System.Windows.Input.Key>(doc.RootElement.GetProperty("key").GetString()!); var mods = Enum.Parse<System.Windows.Input.ModifierKeys>(doc.RootElement.GetProperty("mods").GetString()!); if (!IsShortcut(key, mods)) return "{\"ok\":false}"; HandleShortcut(key, mods); return "{\"ok\":true}"; }
       if (op == "capture") {
        shellRoot!.UpdateLayout();
        int width=(int)shellRoot.ActualWidth, height=(int)shellRoot.ActualHeight;
        using var chromeStream=new MemoryStream();
        await shellView!.CoreWebView2.CapturePreviewAsync(Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat.Png,chromeStream).WaitAsync(TimeSpan.FromSeconds(3));
        chromeStream.Position=0;
        var native=new System.Windows.Media.Imaging.BitmapImage();native.BeginInit();native.CacheOption=System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;native.StreamSource=chromeStream;native.EndInit();native.Freeze();
        System.Windows.Media.Imaging.BitmapImage? page=null;
        System.Windows.Rect pageRect=default;
        if(WebHost.Visibility==System.Windows.Visibility.Visible && Shown?.View?.CoreWebView2 is {} browser && Shown.View.Visibility==System.Windows.Visibility.Visible){
         using var stream=new MemoryStream();await browser.CapturePreviewAsync(Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat.Png,stream).WaitAsync(TimeSpan.FromSeconds(3));stream.Position=0;
         page=new();page.BeginInit();page.CacheOption=System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;page.StreamSource=stream;page.EndInit();page.Freeze();
         var point=Shown.View.TransformToAncestor(shellRoot).Transform(new System.Windows.Point(0,0));pageRect=new(point.X,point.Y,Shown.View.ActualWidth,Shown.View.ActualHeight);
        }
        System.Windows.Media.Imaging.BitmapImage? side=null;System.Windows.Rect sideRect=default;
        if(WebHost.Visibility==System.Windows.Visibility.Visible&&Partner?.View is {IsVisible:true} pv&&pv.CoreWebView2 is {} pc){
         using var ps=new MemoryStream();await pc.CapturePreviewAsync(Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat.Png,ps).WaitAsync(TimeSpan.FromSeconds(3));ps.Position=0;
         side=new();side.BeginInit();side.CacheOption=System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;side.StreamSource=ps;side.EndInit();side.Freeze();
         var sp=pv.TransformToAncestor(shellRoot).Transform(new System.Windows.Point(0,0));sideRect=new(sp.X,sp.Y,pv.ActualWidth,pv.ActualHeight);
        }
        var visual=new System.Windows.Media.DrawingVisual();
        using(var dc=visual.RenderOpen()) {
         dc.DrawImage(native,new System.Windows.Rect(0,0,width,height));
         if(side!=null)dc.DrawImage(side,sideRect);
         if(page!=null){
          // The page window leaves the AI's glow and controls open (CutHoles): show the picture the same way.
          bool holed=holedPage!=IntPtr.Zero&&holes.Tab==Shown!.Id;
          System.Windows.Media.Geometry clip=new System.Windows.Media.RectangleGeometry(holed?new System.Windows.Rect(pageRect.X+holes.Frame,pageRect.Y+holes.Frame,Math.Max(0,pageRect.Width-2*holes.Frame),Math.Max(0,pageRect.Height-2*holes.Frame)):pageRect);
          if(holed)foreach(var s in holes.Spots)clip=new System.Windows.Media.CombinedGeometry(System.Windows.Media.GeometryCombineMode.Exclude,clip,new System.Windows.Media.RectangleGeometry(new System.Windows.Rect(pageRect.X+s.X,pageRect.Y+s.Y,s.W,s.H),s.R,s.R));
          dc.PushClip(clip);dc.DrawImage(page,pageRect);dc.Pop();
         }
        }
        var rendered=new System.Windows.Media.Imaging.RenderTargetBitmap(width,height,96,96,System.Windows.Media.PixelFormats.Pbgra32);rendered.Render(visual);
        var encoder=new System.Windows.Media.Imaging.PngBitmapEncoder();encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(rendered));
        string path=Path.Combine(App.DataRoot,Path.GetFileName(doc.RootElement.GetProperty("name").GetString() ?? "capture.png"));
        using(var file=File.Create(path))encoder.Save(file);
        return JsonSerializer.Serialize(new {path});
       }
       if (op == "systemTheme") { qaSystemTheme = doc.RootElement.GetProperty("value").GetString() == "Light" ? "Light" : "Dark"; foreach (var w in Windows) if (Prefs.Theme == "System") w.ApplyTheme(); return "{\"ok\":true}"; }
       // Answers the Windows Hello prompt for tests (allow, deny or none: not set up), and where an export is written.
       if (op == "osAuth") { if (doc.RootElement.TryGetProperty("answer", out var a)) { qaAuthAnswer = a.GetString() ?? "deny"; verifiedUntil = default; } if (doc.RootElement.TryGetProperty("exportPath", out var x)) qaExportPath = x.GetString() ?? ""; return JsonSerializer.Serialize(new { asks = qaAuthAsks, answer = qaAuthAnswer }); }
       if (op == "quit") { Close(); return "{\"ok\":true}"; }
       if (op == "closeWindow") { Windows.FirstOrDefault(w => w.WindowId == doc.RootElement.GetProperty("id").GetString())?.Close(); return "{\"ok\":true}"; }
       if (op == "closeAll") { foreach (var w in Windows.ToList()) w.Close(); return "{\"ok\":true}"; } // like the taskbar's Close all windows: this one first
       if (op == "memoryPressure") { qaPressure = true; try { await ReduceBackgroundMemory(); } finally { qaPressure = false; } return "{\"ok\":true}"; }
       return "{\"error\":\"unknown operation or no page\"}";
      } catch (Exception ex) { return JsonSerializer.Serialize(new { error = ex.Message }); }
     }));
     await writer.WriteLineAsync(reply);
    } catch (Exception ex) { if (!closing) App.Log(ex); }
   }
  });
 }
}
#endif
