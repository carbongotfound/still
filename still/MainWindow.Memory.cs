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
  // What the page has on (camera, mic, location) goes to Still as it changes, for the dot on the Permissions button.
  // Only the top page can tell Still; a frame's camera keeps its own counsel.
  const captures = new Set(); let geo = 0, sent = '';
  const tell = () => {
   let camera = false, mic = false;
   for (const ref of captures) {
    const stream = ref.deref();
    if (!stream) { captures.delete(ref); continue; }
    for (const t of stream.getTracks()) if (t.readyState === 'live') t.kind === 'video' ? camera = true : mic = true;
   }
   const use = [camera && 'camera', mic && 'mic', geo > 0 && 'location'].filter(Boolean).join(',');
   if (use !== sent && window.top === window && window.chrome?.webview) { sent = use; window.chrome.webview.postMessage({ kind: 'still-in-use', use }); }
  };
  for (const name of ['getUserMedia', 'getDisplayMedia']) {
   const original = devices?.[name];
   if (!original) continue;
   devices[name] = async function (...args) {
    const stream = await original.apply(this, args);
    streams.add(new WeakRef(stream));
    if (name === 'getUserMedia') { captures.add(new WeakRef(stream)); for (const t of stream.getTracks()) t.addEventListener('ended', tell); tell(); }
    return stream;
   };
  }
  const stop = window.MediaStreamTrack?.prototype.stop;
  if (stop) MediaStreamTrack.prototype.stop = function () { stop.call(this); setTimeout(tell); };
  const where = navigator.geolocation, watches = new Set();
  if (where) {
   const watch = where.watchPosition.bind(where), clear = where.clearWatch.bind(where), once = where.getCurrentPosition.bind(where);
   where.watchPosition = (...args) => { const id = watch(...args); watches.add(id); geo = watches.size; tell(); return id; };
   where.clearWatch = id => { clear(id); watches.delete(id); geo = watches.size; tell(); };
   where.getCurrentPosition = (...args) => { geo++; tell(); setTimeout(() => { geo = Math.max(watches.size, geo - 1); tell(); }, 3000); return once(...args); };
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
   // Cross-origin frames cannot be inspected safely: such tabs keep running at the low target ("frames")
   // and are only unloaded once they've been in the background a while.
   let unknown = false;
   for (const frame of document.querySelectorAll('iframe')) {
    try {
     const inner = frame.contentWindow?.__stillMemoryBusy?.();
     if (inner === true) return true;
     if (!frame.contentWindow || !frame.contentDocument || inner === 'frames') unknown = true;
    } catch { unknown = true; }
   }
   return unknown ? 'frames' : false;
  };
  // Typed text that a reload would lose (a draft, a half-filled form).
  window.__stillEdited = () => [...document.querySelectorAll('textarea,input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')].some(e => e.value && e.value !== e.defaultValue)
   || [...document.querySelectorAll('[contenteditable=""],[contenteditable=true]')].some(e => e.textContent.trim());
 })();
 """;

 void ApplyMemoryPolicy()
 {
  try { ApplyMemoryPolicyCore(); } catch (InvalidOperationException) { } // a crashed engine; Still restarts
 }
 void ApplyMemoryPolicyCore()
 {
  if (closing) return;
  foreach (var tab in tabs)
  {
   if (tab.View?.CoreWebView2 is not { } core) continue;
   if (core.IsSuspended)
   {
    if (!Prefs.MemorySaver || tab == Shown) core.Resume();
    else continue;
   }
   // Low keeps scripts and network activity running until the tab is eligible for suspension.
   core.MemoryUsageTargetLevel = Prefs.MemorySaver && !tab.Media && (tab != Shown || WindowState == WindowState.Minimized)
    ? CoreWebView2MemoryUsageTargetLevel.Low : CoreWebView2MemoryUsageTargetLevel.Normal;
  }
  if (shellView?.CoreWebView2 is { } shell)
   shell.MemoryUsageTargetLevel = Prefs.MemorySaver && WindowState == WindowState.Minimized
    ? CoreWebView2MemoryUsageTargetLevel.Low : CoreWebView2MemoryUsageTargetLevel.Normal;
  if (managementView?.CoreWebView2 is { } management)
   management.MemoryUsageTargetLevel = CoreWebView2MemoryUsageTargetLevel.Low;
 }

 // An AI's tab is busy while its run goes on or while the AI is working in it; after that it can sleep like any other.
 static bool AgentBusy(BrowserTab t) => t.AgentKey is { } k && (runs.ContainsKey(k) || agentTabs.GetValueOrDefault(k) == t.Id) || (t.InChat ?? t.RunChat) is { } c && runs.ContainsKey(c);
 // Pages an AI opened close 48 hours after their chat goes quiet. The user's own tabs never do.
 static readonly TimeSpan AgentTabLifetime = TimeSpan.FromHours(48);
 bool AgentTabExpired(BrowserTab t)
 {
  if (!(t.AgentGroup || t.RunChat != null || t.InChat != null) || t.Closed || t.Pinned || t == active || t == Shown || AgentBusy(t)) return false;
  var chat = (t.InChat ?? t.RunChat) is { } id ? AiChats.FirstOrDefault(c => c.Id == id)?.Updated : null;
  var quiet = t.InChat != null && chat is { } updated ? updated : chat is { } u && u > t.LastActive ? u : t.LastActive; // a chat page's own LastActive restarts with Still
  return DateTime.UtcNow - quiet >= AgentTabLifetime;
 }
 async Task ReduceBackgroundMemory()
 {
  foreach (var old in tabs.Where(AgentTabExpired).ToList()) if (!old.Closed) await CloseTab(old);
  if (!Prefs.MemorySaver || closing || memoryPassRunning) return;
  memoryPassRunning = true;
  bool newlySuspended = false, discarded = false, pressure = UnderMemoryPressure();
  try
  {
   foreach (var tab in tabs.ToArray())
   {
    // Only when Windows runs short of memory is a sleeping tab unloaded completely: it reloads where it was
    // scrolled to when selected. Switching tabs never unloads one. Pinned tabs and tabs with typed text only sleep.
    if (pressure && CanSuspend(tab) && !tab.Pinned && !tab.Edited && tab.View?.CoreWebView2?.IsSuspended == true)
    { DisposeView(tab); discarded = true; continue; }
    if (!CanSuspend(tab) || tab.View?.CoreWebView2 is not { } core || core.IsSuspended) continue;
    try
    {
     // A hung page must not delay memory management for the other tabs.
     tab.RestoreScroll = double.TryParse(await core.RunAsync("scrollY"), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var y) ? y : 0; // where it reloads if unloaded
     string activity = await core.RunAsync("(() => { const busy = window.__stillMemoryBusy ? window.__stillMemoryBusy() : true; if (busy === true) return 'busy'; const edited = !!window.__stillEdited?.(); return busy === 'frames' ? (edited ? 'busy' : 'frames') : edited ? 'edited' : 'idle' })()").WaitAsync(TimeSpan.FromSeconds(2));
     if (activity == "\"busy\"") continue;
     if (activity == "\"frames\"") {
      if (pressure && CanSuspend(tab) && !tab.Pinned && tab.View?.CoreWebView2 == core) { DisposeView(tab); discarded = true; }
      continue;
     }
     tab.Edited = activity == "\"edited\"";
     if (pressure && !tab.Edited && !tab.Pinned && CanSuspend(tab) && tab.View?.CoreWebView2 == core && !core.IsDocumentPlayingAudio) { DisposeView(tab); discarded = true; continue; }
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
   if (discarded) ShellPublish();
   await TrimWhileInBackground();
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
   var sleeping = Windows.Where(w => !w.closing).SelectMany(w => w.tabs.Where(t => t != w.Shown && t.ActiveDownloads == 0))
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
  catch (Exception ex) when (ex is InvalidOperationException or COMException or System.IO.IOException) { }
  // Windows can reuse these sleeping pages. Their private allocations and page state stay intact;
  // waking may incur page faults. This is a one-time trim on suspension, never a polling RAM cap.
 }

 [StructLayout(LayoutKind.Sequential)]
 struct MemoryStatus { public uint Length, Load; public ulong TotalPhys, AvailPhys, TotalPageFile, AvailPageFile, TotalVirtual, AvailVirtual, AvailExtendedVirtual; }
 [DllImport("kernel32.dll")]
 [return: MarshalAs(UnmanagedType.Bool)]
 static extern bool GlobalMemoryStatusEx(ref MemoryStatus status);
 internal static bool qaPressure;
 // Real pressure: 90% of the RAM in use, where Windows itself starts paging hard.
 static bool UnderMemoryPressure() { var s = new MemoryStatus { Length = (uint)Marshal.SizeOf<MemoryStatus>() }; return qaPressure || GlobalMemoryStatusEx(ref s) && s.Load >= 90; }
 static bool trimmedInBackground;
 // While Still is in the background, hand idle memory back to Windows once: the engine's main, GPU and helper
 // processes. Not Still.exe itself: paging its UI back in froze Still for seconds when you returned. It pages back in when you return. Renderers are handled per tab above.
 async Task TrimWhileInBackground()
 {
  if (Windows.Any(w => w.IsActive)) { trimmedInBackground = false; return; }
  if (trimmedInBackground) return;
  trimmedInBackground = true;
  try {
   var processes = await (await App.BrowserEnvironment).GetProcessExtendedInfosAsync();
   foreach (var id in processes.Where(p => p.ProcessInfo.Kind != CoreWebView2ProcessKind.Renderer).Select(p => p.ProcessInfo.ProcessId)) {
    using var handle = OpenProcess(0x0100 | 0x1000, false, id);
    if (!handle.IsInvalid) _ = EmptyWorkingSet(handle);
   }
  } catch (Exception ex) when (ex is InvalidOperationException or COMException or System.IO.IOException) { }
 }

 bool CanSuspend(BrowserTab tab) => Prefs.MemorySaver && !closing && !tab.Closed && tabs.Contains(tab)
  && tab != Shown && !AgentBusy(tab) && !tab.Media && !tab.Loading && tab.ActiveDownloads == 0 && tab.View is { IsVisible: false }
  && DateTime.UtcNow - tab.LastActive >= (qaPressure ? TimeSpan.Zero : TimeSpan.FromMinutes(1))
  && !permissions.Any(p => p.Tab == tab) && tab.View?.CoreWebView2?.IsDocumentPlayingAudio == false;
}
