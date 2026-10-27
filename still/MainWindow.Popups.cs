using System.Windows;
using System.Windows.Interop;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
namespace Still;
// Pop-ups work like in Edge: window.open with a size (sign-in, payment and share windows) gets its own small window,
// and a pop-up nobody clicked for is blocked, with the permission bar offering to allow them on that site.
public partial class MainWindow
{
 async Task OpenPageWindow(BrowserTab opener, CoreWebView2NewWindowRequestedEventArgs e)
 {
  var f = e.WindowFeatures; var area = SystemParameters.WorkArea;
  var view = new WebView2 { DefaultBackgroundColor = System.Drawing.Color.White, Width = Math.Clamp((double)f.Width, 200, area.Width - 40), Height = Math.Clamp((double)f.Height, 150, area.Height - 80) };
  var popup = new Window { Owner = this, Content = view, SizeToContent = SizeToContent.WidthAndHeight, Title = Host(e.Uri), ShowActivated = !App.IsQa,
   WindowStartupLocation = f.HasPosition ? WindowStartupLocation.Manual : WindowStartupLocation.CenterOwner };
  if (f.HasPosition) { popup.Left = f.Left; popup.Top = f.Top; }
  popup.SourceInitialized += (_, _) => { int on = dark ? 1 : 0; DwmSetWindowAttribute(new WindowInteropHelper(popup).Handle, 20, ref on, 4); };
  popup.Closed += (_, _) => view.Dispose();
  popup.Show();
  var environment = await App.BrowserEnvironment; var options = environment.CreateCoreWebView2ControllerOptions();
  options.ProfileName = opener.Private ? privateProfile : "Default"; options.IsInPrivateModeEnabled = opener.Private;
  await view.EnsureCoreWebView2Async(environment, options);
  var core = view.CoreWebView2;
  e.NewWindow = core;
  // The title always starts with the site, so a pop-up can't pass itself off as another one.
  void Name() => popup.Title = Host(core.Source) + (string.IsNullOrWhiteSpace(core.DocumentTitle) ? "" : " · " + core.DocumentTitle);
  core.SourceChanged += (_, _) => Name(); core.DocumentTitleChanged += (_, _) => Name();
  core.WindowCloseRequested += (_, _) => Dispatcher.BeginInvoke(popup.Close);
  core.NewWindowRequested += (_, e2) => { e2.Handled = true; string link = e2.Uri; Dispatcher.BeginInvoke(async () => await NewTab(link, opener.Private, false)); };
 }

 async void PopupBlocked(BrowserTab tab, string uri)
 {
  try {
   string site = Host(tab.Url);
   if (string.IsNullOrWhiteSpace(site) || permissions.Any(p => p.Tab == tab && p.Kind == "open pop-ups")) return;
   if (!await AskPermission(tab, site, "open pop-ups")) return;
   if (!tab.Private) { Prefs.AllowedPopups.Add(site); SaveLater(); }
   if (uri.StartsWith("http")) await NewTab(uri, tab.Private, false);
  } catch (Exception ex) { App.Log(ex); }
 }
}
