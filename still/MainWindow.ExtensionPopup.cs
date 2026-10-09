using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
namespace Still;

// An extension's popup opens in a small floating panel under the toolbar, sized to its content like Chrome's,
// instead of in a tab. It closes when you click anywhere else or when the extension calls window.close().
public partial class MainWindow
{
 Window? extensionPopup;

 async Task ShowExtensionPopup(string url, double[]? anchor)
 {
  extensionPopup?.Close();
  var view = new WebView2 { DefaultBackgroundColor = System.Drawing.Color.White /* like Chrome: popups without their own background are white */ };
  var popup = new Window {
   Owner = this, WindowStyle = WindowStyle.None, ResizeMode = ResizeMode.NoResize, ShowInTaskbar = false, Title = "Extension",
   Width = 25, Height = 25, Left = -32000, Top = -32000, Background = Brush("Surface"),
   Content = new Border { BorderThickness = new Thickness(1), BorderBrush = Brush("Line"), Child = view },
  };
  extensionPopup = popup;
  bool closed = false;
  popup.Deactivated += (_, _) => { if (!closed) popup.Close(); };
  popup.Closed += (_, _) => { closed = true; view.Dispose(); if (extensionPopup == popup) extensionPopup = null; };
  popup.Show();
  try {
   var environment = await App.BrowserEnvironment; var options = environment.CreateCoreWebView2ControllerOptions(); options.ProfileName = "Default";
   await view.EnsureCoreWebView2Async(environment, options);
  } catch (Exception ex) { App.Log(ex); if (!closed) popup.Close(); Toast("Couldn't open the extension."); return; }
  if (closed || view.CoreWebView2 is not { } core) return;
  core.Settings.AreDefaultContextMenusEnabled = true;
  core.NewWindowRequested += (_, e) => { e.Handled = true; string link = e.Uri; Dispatcher.BeginInvoke(async () => { popup.Close(); await NewTab(link, false, false); }); };
  core.WindowCloseRequested += (_, _) => Dispatcher.BeginInvoke(() => { if (!closed) popup.Close(); });
  core.NavigationCompleted += async (_, _) => { foreach (int wait in new[] { 0, 150, 500, 1200 }) { await Task.Delay(wait); if (closed) return; await FitExtensionPopup(popup, core, anchor); } };
  core.Navigate(url);
 }

 // Chrome sizes popups to their content within 25-800 x 25-600 pixels: lay out narrow, grow to the width the page
 // needs, then fit the height of what's actually drawn (scrollHeight never shrinks below the window).
 async Task FitExtensionPopup(Window popup, CoreWebView2 core, double[]? anchor)
 {
  try {
   string size = await core.ExecuteScriptAsync("(() => { const d = document.documentElement, b = document.body; return [Math.max(d.scrollWidth, b ? b.scrollWidth : 0), Math.ceil(Math.max(d.getBoundingClientRect().height, b ? b.getBoundingClientRect().bottom + parseFloat(getComputedStyle(b).marginBottom) : 0))] })()");
   if (JsonSerializer.Deserialize<double[]>(size) is not { Length: 2 } s) return;
   popup.Width = Math.Clamp(s[0] + 2, 25, 800); popup.Height = Math.Clamp(s[1] + 2, 25, 600);
   if (shellView == null) return;
   // Right-align under the toolbar button (shell pixels → screen), staying on the window's monitor area.
   double z = shellView.ZoomFactor, dpi = VisualTreeHelper.GetDpi(this).DpiScaleX;
   var corner = anchor is { Length: 4 } a ? shellView.PointToScreen(new Point((a[0] + a[2]) * z, (a[1] + a[3] + 6) * z)) : shellView.PointToScreen(new Point(shellView.ActualWidth - 12, 52));
   double left = corner.X / dpi - popup.Width, top = corner.Y / dpi;
   popup.Left = Math.Max(Left + 8, left); popup.Top = top;
  } catch (Exception ex) when (ex is InvalidOperationException or System.Runtime.InteropServices.COMException or JsonException) { }
 }
}
