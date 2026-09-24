using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Shell;
using System.Windows.Threading;

namespace Still;
public partial class MainWindow
{
 bool browserFullScreen, contentFullScreen, fullScreenApplied;
 bool IsFullScreen => browserFullScreen || contentFullScreen;
 WindowChrome? restoreChrome;
 ResizeMode restoreResizeMode;
 WindowState restoreWindowState;
 Rect fullScreenRestoreBounds;
 WindowPlacement restorePlacement;
 ITaskbarList2? taskbar;

 [StructLayout(LayoutKind.Sequential)] struct NativeRect { public int Left, Top, Right, Bottom; }
 [StructLayout(LayoutKind.Sequential)] struct NativePoint { public int X, Y; }
 [StructLayout(LayoutKind.Sequential)] struct MonitorInfo { public int Size; public NativeRect Monitor, Work; public uint Flags; }
 [StructLayout(LayoutKind.Sequential)] struct WindowPlacement { public int Length; public uint Flags, ShowCmd; public NativePoint Min, Max; public NativeRect Normal; }
 [DllImport("user32.dll")] static extern IntPtr MonitorFromWindow(IntPtr hwnd, uint flags);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);
 [DllImport("user32.dll")] static extern bool GetWindowPlacement(IntPtr hwnd, ref WindowPlacement placement);
 [DllImport("user32.dll")] static extern bool SetWindowPlacement(IntPtr hwnd, in WindowPlacement placement);
 [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW")] static extern IntPtr GetWindowLongPtr(IntPtr hwnd, int index);
 [DllImport("user32.dll", EntryPoint="SetWindowLongPtrW")] static extern IntPtr SetWindowLongPtr(IntPtr hwnd, int index, IntPtr value);
 [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
 const long FrameStyles=0x00C00000L|0x00040000L; // WS_CAPTION | WS_THICKFRAME
 const long FrameExStyles=0x00000001L|0x00000100L|0x00000200L|0x00020000L; // DLGMODALFRAME | WINDOWEDGE | CLIENTEDGE | STATICEDGE
 long restoreStyle,restoreExStyle;
 [ComImport, Guid("602D4995-B13A-429B-A66E-1935E44F4317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface ITaskbarList2
 {
  void HrInit(); void AddTab(IntPtr hwnd); void DeleteTab(IntPtr hwnd); void ActivateTab(IntPtr hwnd); void SetActiveAlt(IntPtr hwnd);
  void MarkFullscreenWindow(IntPtr hwnd, [MarshalAs(UnmanagedType.Bool)] bool fullscreen);
 }

 void InitializeFullScreen()
 {
  var hwnd=new WindowInteropHelper(this).Handle;
  HwndSource.FromHwnd(hwnd)?.AddHook((IntPtr window,int message,IntPtr wParam,IntPtr lParam,ref bool handled)=>{
   // Refit after Windows applies a display-layout or DPI change, without taking focus.
   if(message is 0x007E or 0x02E0 && IsFullScreen)
    Dispatcher.BeginInvoke(DispatcherPriority.Loaded,()=>{if(IsFullScreen&&!closing)FitFullScreen(MonitorFromWindow(hwnd,2));});
   return IntPtr.Zero;
  });
  // Stay above the taskbar only while focused, so Alt+Tab and other windows still work.
  Activated+=(_,_)=>{if(IsFullScreen){Topmost=true;MarkFullScreen(true);FitFullScreen(MonitorFromWindow(hwnd,2));}};
  Deactivated+=(_,_)=>{if(IsFullScreen)Topmost=false;};
  Closed+=(_,_)=>{MarkFullScreen(false);if(taskbar!=null){Marshal.FinalReleaseComObject(taskbar);taskbar=null;}};
 }
 void MarkFullScreen(bool value)
 {
  try{
   if(taskbar==null){taskbar=(ITaskbarList2)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("56FDF344-FD6D-11D0-958A-006097C9A090"))!)!;taskbar.HrInit();}
   taskbar.MarkFullscreenWindow(new WindowInteropHelper(this).Handle,value);
  }catch(COMException){/* Full-monitor geometry also supports the shell's automatic detection. */}
 }
 void FitFullScreen(IntPtr monitor)
 {
  var info=new MonitorInfo{Size=Marshal.SizeOf<MonitorInfo>()};
  if(!GetMonitorInfo(monitor,ref info))return;
  var r=info.Monitor;
  // Cover the physical monitor, including the taskbar area. HWND_TOP | SWP_FRAMECHANGED | SWP_SHOWWINDOW.
  var hwnd=new WindowInteropHelper(this).Handle;
  SetWindowPos(hwnd,IsActive?new IntPtr(-1):IntPtr.Zero,r.Left,r.Top,r.Right-r.Left,r.Bottom-r.Top,0x0010|0x0020|0x0040);
  RestorePageWindow();
 }
 void ApplyFullScreen()
 {
  if(closing||IsFullScreen==fullScreenApplied)return;
  var hwnd=new WindowInteropHelper(this).Handle;
  if(IsFullScreen){
   var monitor=MonitorFromWindow(hwnd,2);
   restoreWindowState=WindowState;fullScreenRestoreBounds=WindowState==WindowState.Normal?new Rect(Left,Top,Width,Height):RestoreBounds;
   restorePlacement=new(){Length=Marshal.SizeOf<WindowPlacement>()};GetWindowPlacement(hwnd,ref restorePlacement);
   restoreChrome=WindowChrome.GetWindowChrome(this);restoreResizeMode=ResizeMode;
   fullScreenApplied=true;WindowState=WindowState.Normal;ResizeMode=ResizeMode.NoResize;WindowChrome.SetWindowChrome(this,null);
   restoreStyle=(long)GetWindowLongPtr(hwnd,-16);restoreExStyle=(long)GetWindowLongPtr(hwnd,-20);
   SetWindowLongPtr(hwnd,-16,new IntPtr(restoreStyle&~FrameStyles));SetWindowLongPtr(hwnd,-20,new IntPtr(restoreExStyle&~FrameExStyles));
   int square=1;DwmSetWindowAttribute(hwnd,33,ref square,4);
   Activate();SetForegroundWindow(hwnd);Topmost=true;
   FitFullScreen(monitor);MarkFullScreen(true);
  }else{
   fullScreenApplied=false;MarkFullScreen(false);Topmost=false;
   SetWindowLongPtr(hwnd,-16,new IntPtr(restoreStyle));SetWindowLongPtr(hwnd,-20,new IntPtr(restoreExStyle));
   WindowChrome.SetWindowChrome(this,restoreChrome);ResizeMode=restoreResizeMode;
   SetWindowPlacement(hwnd,in restorePlacement);WindowState=restoreWindowState;
   int round=2;DwmSetWindowAttribute(hwnd,33,ref round,4);RestorePageWindow();
  }
  ShellPublish();
 }
 async Task ExitContentFullScreen()
 {
  contentFullScreen=false;ApplyFullScreen();
  if(active?.View?.CoreWebView2 is{} core)try{if(core.ContainsFullScreenElement)await core.ExecuteScriptAsync("if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});");}catch(COMException){}catch(InvalidOperationException){}
 }
 async Task ToggleFullScreen()
 {
  if(IsFullScreen){browserFullScreen=false;await ExitContentFullScreen();}
  else{browserFullScreen=true;ApplyFullScreen();}
 }
}
