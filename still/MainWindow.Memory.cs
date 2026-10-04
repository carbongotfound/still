using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;

namespace Still;

public partial class MainWindow
{
 readonly DispatcherTimer memoryTimer = new() { Interval = TimeSpan.FromSeconds(15) };
 bool memoryPassRunning;
 [DllImport("kernel32.dll", SetLastError = true)]
 static extern SafeProcessHandle OpenProcess(uint access, bool inherit, int processId);
 [DllImport("psapi.dll", SetLastError = true)]
 [return: MarshalAs(UnmanagedType.Bool)]
 static extern bool EmptyWorkingSet(SafeProcessHandle process);

 // Keep live media/capture and calls running, including muted videos. Weak references do not retain
 // finished streams or peer connections. This script is installed in every document/frame.
 const string MemoryActivityScript = """
 (() => {
  const streams = new Set(), peers = new Set();
  const devices = navigator.mediaDevices;
  for (const name of ['getUserMedia', 'getDisplayMedia']) {
   const original = devices?.[name];
   if (!original) continue;
   devices[name] = async function (...args) {
    const stream = await original.apply(this, args);
    streams.add(new WeakRef(stream)); return stream;
   };
  }
  const Peer = window.RTCPeerConnection;
  if (Peer) window.RTCPeerConnection = class extends Peer {
   constructor(...args) { super(...args); peers.add(new WeakRef(this)); }
  };
  window.__stillMemoryBusy = () => {
   if ([...document.querySelectorAll('audio,video')].some(m => !m.paused && !m.ended)) return true;
   for (const ref of streams) {
    const stream = ref.deref();
    if (!stream) streams.delete(ref);
    else if (stream.getTracks().some(t => t.readyState === 'live')) return true;
   }
   for (const ref of peers) {
    const peer = ref.deref();
    if (!peer) peers.delete(ref);
    else if (!['closed','failed','disconnected'].includes(peer.connectionState)) return true;
   }
   // Cross-origin frames cannot be inspected safely. Leave these tabs running at the low target.
   for (const frame of document.querySelectorAll('iframe')) {
    try { if (!frame.contentWindow || frame.contentWindow.__stillMemoryBusy?.()) return true;
     if (!frame.contentDocument) return true;
    } catch { return true; }
   }
   return false;
  };
 })();
 """;

 void ApplyMemoryPolicy()
 {
  if (closing) return;
  foreach (var tab in tabs)
  {
   if (tab.View?.CoreWebView2 is not { } core) continue;
   if (core.IsSuspended)
   {
    if (!Prefs.MemorySaver || tab == active) core.Resume();
    else continue;
   }
   // Low keeps scripts and network activity running until the tab is eligible for suspension.
   core.MemoryUsageTargetLevel = Prefs.MemorySaver && (tab != active || WindowState == WindowState.Minimized)
    ? CoreWebView2MemoryUsageTargetLevel.Low : CoreWebView2MemoryUsageTargetLevel.Normal;
  }
  if (shellView?.CoreWebView2 is { } shell)
   shell.MemoryUsageTargetLevel = Prefs.MemorySaver && WindowState == WindowState.Minimized
    ? CoreWebView2MemoryUsageTargetLevel.Low : CoreWebView2MemoryUsageTargetLevel.Normal;
  if (managementView?.CoreWebView2 is { } management)
   management.MemoryUsageTargetLevel = CoreWebView2MemoryUsageTargetLevel.Low;
 }

 async Task ReduceBackgroundMemory()
 {
  if (!Prefs.MemorySaver || closing || memoryPassRunning) return;
  memoryPassRunning = true;
  bool newlySuspended = false;
  try
  {
   foreach (var tab in tabs.ToArray())
   {
    if (!CanSuspend(tab) || tab.View?.CoreWebView2 is not { } core || core.IsSuspended) continue;
    try
    {
     // A hung page must not delay memory management for the other tabs.
     if (await core.ExecuteScriptAsync("window.__stillMemoryBusy ? window.__stillMemoryBusy() : true").WaitAsync(TimeSpan.FromSeconds(2)) != "false") continue;
     // Selecting/closing the tab, starting media or toggling memory saver can happen while awaiting.
     if (!CanSuspend(tab) || tab.View?.CoreWebView2 != core || core.IsDocumentPlayingAudio) continue;
     if (await core.TrySuspendAsync())
     {
      if (closing || tab.Closed) continue;
      if (!CanSuspend(tab)) { core.Resume(); ApplyMemoryPolicy(); }
      else newlySuspended = true;
      ShellPublish();
     }
    }
    catch (Exception ex) when (ex is InvalidOperationException or COMException or TimeoutException) { }
   }
   if (newlySuspended) await ReleaseSleepingWorkingSets();
  }
  finally { memoryPassRunning = false; }
 }

 async Task ReleaseSleepingWorkingSets()
 {
  try
  {
   var environment = await App.BrowserEnvironment;
   var processes = await environment.GetProcessExtendedInfosAsync();
   if (!Prefs.MemorySaver || closing) return;
   // Decide after the await: a tab may have been resumed, moved or closed meanwhile.
   var sleeping = Windows.Where(w => !w.closing).SelectMany(w => w.tabs.Where(t => t != w.active && t.ActiveDownloads == 0))
    .Select(t => t.View?.CoreWebView2).Where(c => c?.IsSuspended == true).Select(c => c!.FrameId).ToHashSet();
   foreach (var process in processes)
   {
    if (process.ProcessInfo.Kind != CoreWebView2ProcessKind.Renderer || process.AssociatedFrameInfos.Count == 0) continue;
    // Never trim a renderer shared with an active page, a shell, an extension or an unknown frame.
    bool sleepingOnly = process.AssociatedFrameInfos.All(frame => {
     int depth = 0;
     while (frame.ParentFrameInfo is { } parent && depth++ < 64) frame = parent;
     return depth < 64 && frame.FrameId != 0 && sleeping.Contains(frame.FrameId);
    });
    if (!sleepingOnly) continue;
    using var handle = OpenProcess(0x0100 | 0x1000 /* SET_QUOTA | QUERY_LIMITED_INFORMATION */, false, process.ProcessInfo.ProcessId);
    if (!handle.IsInvalid) _ = EmptyWorkingSet(handle);
   }
  }
  catch (Exception ex) when (ex is InvalidOperationException or COMException) { }
  // Windows can reuse these sleeping pages. Their private allocations and page state stay intact;
  // waking may incur page faults. This is a one-time trim on suspension, never a polling RAM cap.
 }

 bool CanSuspend(BrowserTab tab) => Prefs.MemorySaver && !closing && !tab.Closed && tabs.Contains(tab)
  && tab != active && !tab.Loading && tab.ActiveDownloads == 0 && tab.View is { IsVisible: false }
  && DateTime.UtcNow - tab.LastActive >= TimeSpan.FromMinutes(1)
  && !permissions.Any(p => p.Tab == tab) && tab.View?.CoreWebView2?.IsDocumentPlayingAudio == false;
}
