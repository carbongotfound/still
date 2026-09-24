using Microsoft.Win32;
using System.IO;
namespace Still;

// Per-user registration. No elevation and no command assembled from web content.
internal static class StartupRegistration
{
 const string Run = @"Software\Microsoft\Windows\CurrentVersion\Run";
 static string Name => App.IsQa ? "Still-QA-" + Path.GetFileName(App.DataRoot) : "Still";
 static string Command => "\"" + Environment.ProcessPath! + "\" --startup";
 public static bool Enabled { get { using var key=Registry.CurrentUser.OpenSubKey(Run); return key?.GetValue(Name) is string value && value==Command; } }
 public static bool DisabledByWindows { get { using var key=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"); return key?.GetValue(Name) is byte[] { Length: > 0 } value && value[0]==3; } }
 public static void Set(bool enabled)
 {
  using var key=Registry.CurrentUser.CreateSubKey(Run);
  if(enabled)key.SetValue(Name,Command,RegistryValueKind.String);
  else if(key.GetValue(Name) is string value && value==Command)key.DeleteValue(Name,false);
 }
}
