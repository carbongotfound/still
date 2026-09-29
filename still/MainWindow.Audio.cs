using System.Runtime.InteropServices;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;
namespace Still;

// The engine picks an audio output when sound starts and never moves it, so switching speakers/headphones in
// Windows (or Sonar) left Still playing on the old device. When the Windows default output changes, every page
// re-opens its playing media and Web Audio on the new default (setSinkId toggles force the stream to be re-created).
public partial class MainWindow
{
 const string AudioRerouteScript = """
 (() => {
  if (window.__stillAudioReroute) return;
  const contexts = new Set(), media = new Set();
  const Ctx = window.AudioContext;
  if (Ctx) window.AudioContext = class extends Ctx { constructor(...a) { super(...a); contexts.add(new WeakRef(this)); } };
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function (...a) { media.add(new WeakRef(this)); return play.apply(this, a); };
  // Detach from the output, then back to the system default: the stream re-opens on whatever the default is now.
  const flip = async el => { try { if (el instanceof Ctx) { const was = el.state; await el.setSinkId({ type: "none" }); await el.setSinkId(""); if (was === "running") await el.resume(); }
   else if (typeof el.setSinkId === "function") await el.setSinkId(el.sinkId === "default" ? "" : "default"); } catch {} };
  window.__stillAudioReroute = () => {
   document.querySelectorAll("audio,video").forEach(flip);
   for (const set of [media, contexts]) for (const ref of set) { const el = ref.deref(); if (el) flip(el); else set.delete(ref); }
  };
  // Also react on our own when the page is told the device list changed (covers embedded frames).
  navigator.mediaDevices?.addEventListener?.("devicechange", () => window.__stillAudioReroute());
 })();
 """;

 static string? defaultOutput;
 static DispatcherTimer? outputWatch;

 // Polls the Windows default output (cheap COM call) and re-routes every tab in every window when it changes.
 // ponytail: 1.5 s poll instead of an IMMNotificationClient callback; switch if the delay ever matters.
 static void WatchDefaultOutput()
 {
  if (outputWatch != null) return;
  defaultOutput = DefaultOutputId();
  outputWatch = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
  outputWatch.Tick += (_, _) => {
   var now = DefaultOutputId();
   if (now == null || now == defaultOutput) return;
   defaultOutput = now;
   foreach (var w in Windows) foreach (var t in w.tabs)
    if (t.View?.CoreWebView2 is { } core) _ = core.ExecuteScriptAsync("window.__stillAudioReroute?.()");
  };
  outputWatch.Start();
 }

 static Task InstallAudioReroute(CoreWebView2 core) => core.AddScriptToExecuteOnDocumentCreatedAsync(AudioRerouteScript);

 static string? DefaultOutputId()
 {
  try {
   var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
   try {
    if (enumerator.GetDefaultAudioEndpoint(0 /*eRender*/, 1 /*eMultimedia*/, out var device) != 0 || device == null) return null;
    try { return device.GetId(out var id) == 0 ? id : null; } finally { Marshal.ReleaseComObject(device); }
   } finally { Marshal.ReleaseComObject(enumerator); }
  } catch (COMException) { return null; }
 }

 [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorCom { }
 [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IMMDeviceEnumerator
 {
  [PreserveSig] int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
  [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
 }
 [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IMMDevice
 {
  [PreserveSig] int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, out IntPtr instance);
  [PreserveSig] int OpenPropertyStore(int access, out IntPtr properties);
  [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
 }
}
