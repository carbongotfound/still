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
        activeId = active?.Id, panel, dark, fullScreen=IsFullScreen,browserFullScreen,contentFullScreen,windowState=WindowState.ToString(),focusMode, layout = Prefs.Layout, shellErrors,
        viewport = new{pageX,pageY,pageWidth,pageHeight,visible=WebHost.Visibility.ToString(),viewWidth=active?.View?.ActualWidth,viewHeight=active?.View?.ActualHeight,hostWidth=WebHost.ActualWidth,hostHeight=WebHost.ActualHeight,zoom=active?.View?.ZoomFactor},
        protection = new{reputation=active?.View?.CoreWebView2?.Settings.IsReputationCheckingRequired,tracking=active?.View?.CoreWebView2?.Profile.PreferredTrackingPreventionLevel.ToString(),blocking=Prefs.Blocking},
        windows = Windows.Select(w => new { id = w.WindowId, tabs = w.tabs.Select(t => t.Url), privateTabs = w.tabs.Count(t => t.Private), w.secondary, w.incognito, left = w.Left, top = w.Top }),
        title = Title, width = ActualWidth, height = ActualHeight, left = Left, top = Top,
        tabs = tabs.Select(t => new { t.Id, t.Title, t.Url, t.Pinned, t.Private, t.Loading, ready = t.View?.CoreWebView2 != null, t.Reader, t.Blocked, favicon=t.Favicon.Length>0,t.Secure,t.CertificateError,memory=t.View?.CoreWebView2?.MemoryUsageTargetLevel.ToString(),visible = t.View?.Visibility.ToString() }),
        history = state.History, bookmarks = state.Bookmarks, hidden = state.Hidden,
        downloads = downloads.Select(d => new { d.Path, status = d.Operation.State.ToString(), bytes = d.Operation.BytesReceived }),
        profilePrivate = active?.View?.CoreWebView2?.Profile.IsInPrivateModeEnabled,
        back = active?.View?.CoreWebView2?.CanGoBack, forward = active?.View?.CoreWebView2?.CanGoForward,
        processMemory = System.Diagnostics.Process.GetCurrentProcess().WorkingSet64
       });
       if (op == "checkUpdate") { await CheckForUpdate(); return JsonSerializer.Serialize(new { update = UpdateData(), installer = update?.Installer, exists = update?.Installer != null && File.Exists(update.Installer) }); }
       if (op == "eval" && active?.View?.CoreWebView2 is { } core) return await core.ExecuteScriptAsync(doc.RootElement.GetProperty("script").GetString() ?? "");
       if (op == "stageExtension") { await StageExtension(doc.RootElement.GetProperty("path").GetString()!);return "{\"ok\":true}"; }
       if (op == "stageImport") { await PrepareImport(doc.RootElement.GetProperty("kind").GetString()!,doc.RootElement.GetProperty("path").GetString()!);return "{\"ok\":true}"; }
       if (op == "stageExternalProfile") { await PrepareExternalProfile(doc.RootElement.GetProperty("path").GetString()!,"Opera GX");return "{\"ok\":true}"; }
       if (op == "shellEval" && shellView?.CoreWebView2 is { } ui) return await ui.ExecuteScriptAsync(doc.RootElement.GetProperty("script").GetString() ?? "");
       if (op == "shellCdp" && shellView?.CoreWebView2 is { } dev) return await dev.CallDevToolsProtocolMethodAsync(doc.RootElement.GetProperty("method").GetString()!,doc.RootElement.GetProperty("parameters").GetRawText());
       if (op == "pageCdp" && active?.View?.CoreWebView2 is { } pageDev) return await pageDev.CallDevToolsProtocolMethodAsync(doc.RootElement.GetProperty("method").GetString()!,doc.RootElement.GetProperty("parameters").GetRawText());
       if (op == "key") { var key = Enum.Parse<System.Windows.Input.Key>(doc.RootElement.GetProperty("key").GetString()!); var mods = Enum.Parse<System.Windows.Input.ModifierKeys>(doc.RootElement.GetProperty("mods").GetString()!); HandleShortcut(key, mods); return "{\"ok\":true}"; }
       if (op == "capture") {
        shellRoot!.UpdateLayout();
        int width=(int)shellRoot.ActualWidth, height=(int)shellRoot.ActualHeight;
        using var chromeStream=new MemoryStream();
        await shellView!.CoreWebView2.CapturePreviewAsync(Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat.Png,chromeStream).WaitAsync(TimeSpan.FromSeconds(3));
        chromeStream.Position=0;
        var native=new System.Windows.Media.Imaging.BitmapImage();native.BeginInit();native.CacheOption=System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;native.StreamSource=chromeStream;native.EndInit();native.Freeze();
        System.Windows.Media.Imaging.BitmapImage? page=null;
        System.Windows.Rect pageRect=default;
        if(WebHost.Visibility==System.Windows.Visibility.Visible && active?.View?.CoreWebView2 is {} browser && active.View.Visibility==System.Windows.Visibility.Visible){
         using var stream=new MemoryStream();await browser.CapturePreviewAsync(Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat.Png,stream).WaitAsync(TimeSpan.FromSeconds(3));stream.Position=0;
         page=new();page.BeginInit();page.CacheOption=System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;page.StreamSource=stream;page.EndInit();page.Freeze();
         var point=active.View.TransformToAncestor(shellRoot).Transform(new System.Windows.Point(0,0));pageRect=new(point.X,point.Y,active.View.ActualWidth,active.View.ActualHeight);
        }
        var visual=new System.Windows.Media.DrawingVisual();
        using(var dc=visual.RenderOpen()) {dc.DrawImage(native,new System.Windows.Rect(0,0,width,height));if(page!=null)dc.DrawImage(page,pageRect);}
        var rendered=new System.Windows.Media.Imaging.RenderTargetBitmap(width,height,96,96,System.Windows.Media.PixelFormats.Pbgra32);rendered.Render(visual);
        var encoder=new System.Windows.Media.Imaging.PngBitmapEncoder();encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(rendered));
        string path=Path.Combine(App.DataRoot,Path.GetFileName(doc.RootElement.GetProperty("name").GetString() ?? "capture.png"));
        using(var file=File.Create(path))encoder.Save(file);
        return JsonSerializer.Serialize(new {path});
       }
       if (op == "quit") { Close(); return "{\"ok\":true}"; }
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
