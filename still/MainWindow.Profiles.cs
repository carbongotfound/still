using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
namespace Still;
public partial class MainWindow
{
 void OpenBrowserProfile(string id)
 {
  var profile=ProfileCatalog.Read().FirstOrDefault(p=>p.Id==id);if(profile==null)return;
  string folder=Path.GetFullPath(ProfileCatalog.Folder(profile));
  if(string.Equals(folder,App.DataRoot,StringComparison.OrdinalIgnoreCase)){CloseSheet();return;}
  var start=new ProcessStartInfo(Environment.ProcessPath!){UseShellExecute=false};
  start.ArgumentList.Add("--profile");start.ArgumentList.Add(folder);
  start.ArgumentList.Add("--profiles-root");start.ArgumentList.Add(App.ProfileHome);
  if(App.IsQa)start.ArgumentList.Add("--qa");
  Process.Start(start);Toast("Opened "+profile.Name+" in its own window.");
 }
 bool profileConfirmation;
 async void ConfirmProfileRemoval(string id,bool reset)
 {
  if(profileConfirmation)return;
  profileConfirmation=true;
  try{
   var profile=ProfileCatalog.Read().SingleOrDefault(p=>p.Id==id)??throw new ArgumentException("Unknown profile.");
   if(reset!=(id=="default"))throw new InvalidOperationException("Default cannot be deleted. Use Reset Default with confirmation.");
   if(ProfileCatalog.IsRunning(profile))throw new InvalidOperationException(id=="default"?"Open another profile and close Default before resetting it.":"Close this profile's window before deleting it.");
   var dialog=new Window{Owner=this,Title=reset?"Reset Default profile":"Delete browser profile",Width=460,SizeToContent=SizeToContent.Height,ResizeMode=ResizeMode.NoResize,WindowStartupLocation=WindowStartupLocation.CenterOwner,Background=new SolidColorBrush(Color.FromRgb(12,12,12)),Foreground=Brushes.White,ShowInTaskbar=false};
   var body=new StackPanel{Margin=new Thickness(24)};
   body.Children.Add(new TextBlock{Text=reset?"Reset Default?":"Delete "+profile.Name+"?",FontSize=20,FontWeight=FontWeights.SemiBold,TextWrapping=TextWrapping.Wrap});
   body.Children.Add(new TextBlock{Text="This permanently removes this profile's passwords, cookies, extensions, tabs, bookmarks, and history. Files saved outside its profile folder are kept.\n\nType "+profile.Name+" to confirm.",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(0,14,0,18)});
   var input=new TextBox{FontSize=16,Padding=new Thickness(10),Background=new SolidColorBrush(Color.FromRgb(24,24,24)),Foreground=Brushes.White};System.Windows.Automation.AutomationProperties.SetName(input,"Confirm profile name");body.Children.Add(input);
   var row=new StackPanel{Orientation=Orientation.Horizontal,HorizontalAlignment=HorizontalAlignment.Right,Margin=new Thickness(0,20,0,0)};
   var cancel=new Button{Content="Cancel",IsCancel=true,Padding=new Thickness(18,8,18,8)};
   var approve=new Button{Content=reset?"Reset Default":"Delete profile",IsEnabled=false,Padding=new Thickness(18,8,18,8),Margin=new Thickness(10,0,0,0)};
   input.TextChanged+=(_,_)=>approve.IsEnabled=input.Text==profile.Name;
   approve.Click+=(_,_)=>{if(input.Text==profile.Name)dialog.DialogResult=true;};row.Children.Add(cancel);row.Children.Add(approve);body.Children.Add(row);dialog.Content=body;
   dialog.Loaded+=(_,_)=>input.Focus();
   if(dialog.ShowDialog()!=true)return;
   if(reset)await ProfileCatalog.ResetClosedDefault();else await ProfileCatalog.DeleteClosedProfile(id);
   Toast(reset?"Default profile reset.":"Profile deleted.");
  }catch(Exception ex){Toast(ex.Message);}
  finally{profileConfirmation=false;await PublishBrowserTools("profiles");}
 }
 object ProfileData()=>new{current=ProfileCatalog.CurrentName(),profiles=ProfileCatalog.Read().Select(p=>new{id=p.Id,name=p.Name,current=ProfileCatalog.IsCurrent(p),launch=p.Id==ProfileCatalog.LaunchId,permanent=p.Id=="default",running=ProfileCatalog.IsRunning(p)})};
}
