using System.IO;
using System.Text.Json;
namespace Still;
public sealed class BrowserProfile
{
 public string Id {get;set;}="default";
 public string Name {get;set;}="Default";
}
public static class ProfileCatalog
{
 static string Catalog=>Path.Combine(App.ProfileHome,"profiles.json");
 static string LaunchFile=>Path.Combine(App.ProfileHome,"launch-profile.txt");
 public static string LaunchId { get { var id=File.Exists(LaunchFile)?File.ReadAllText(LaunchFile).Trim():"default";return Read().Any(p=>p.Id==id)?id:"default"; } }
 public static void SetLaunch(string id) { if(!Read().Any(p=>p.Id==id))throw new ArgumentException("Unknown profile.");File.WriteAllText(LaunchFile+".tmp",id);File.Move(LaunchFile+".tmp",LaunchFile,true); }
 public static string Folder(BrowserProfile profile)=>profile.Id=="default"?App.ProfileHome:Path.Combine(App.ProfileHome,"Profiles",profile.Id);
 public static List<BrowserProfile> Read()
 {
  List<BrowserProfile> profiles;
  try { profiles=File.Exists(Catalog)?JsonSerializer.Deserialize<List<BrowserProfile>>(File.ReadAllText(Catalog))??[]:[]; }
  catch(JsonException){throw new InvalidDataException("The profile list is damaged. Restore profiles.json from your backup before changing profiles.");}
  profiles=profiles.Where(p=>p.Id=="default"||Guid.TryParseExact(p.Id,"N",out _)).DistinctBy(p=>p.Id).ToList();
  if(!profiles.Any(p=>p.Id=="default"))profiles.Insert(0,new());
  return profiles;
 }
 public static bool IsCurrent(BrowserProfile profile)=>string.Equals(Path.GetFullPath(Folder(profile)).TrimEnd(Path.DirectorySeparatorChar),Path.GetFullPath(App.DataRoot).TrimEnd(Path.DirectorySeparatorChar),StringComparison.OrdinalIgnoreCase);
 public static bool IsRunning(BrowserProfile profile) { if(IsCurrent(profile))return true;try{using var gate=System.Threading.Mutex.OpenExisting(App.InstanceName(Folder(profile)));return true;}catch(System.Threading.WaitHandleCannotBeOpenedException){return false;} }
 // Refuse junctions, symlinks and paths outside the catalog before any recursive deletion.
 static void CheckTree(string path)
 {
  if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)throw new IOException("Remove the linked folder manually. Still will not follow links when deleting profiles.");
  if(Directory.Exists(path))foreach(var entry in Directory.EnumerateFileSystemEntries(path))CheckTree(entry);
 }
 public static async Task DeleteClosedProfile(string id)
 {
  if(id=="default")throw new InvalidOperationException("Default is permanent. Its browsing data can only be reset with confirmation.");
  if(!Guid.TryParseExact(id,"N",out _))throw new ArgumentException("Invalid profile.");
  using var catalogGate=await Lock();
  var profiles=Read();var profile=profiles.SingleOrDefault(p=>p.Id==id)??throw new ArgumentException("Profile no longer exists.");
  using var instanceGate=new System.Threading.Mutex(true,App.InstanceName(Folder(profile)),out var exclusive);
  if(!exclusive||IsCurrent(profile))throw new InvalidOperationException("Close this profile's window before deleting it.");
  string parent=Path.GetFullPath(Path.Combine(App.ProfileHome,"Profiles"));string folder=Path.GetFullPath(Folder(profile));
  if(Path.GetDirectoryName(folder)!=parent)throw new IOException("Invalid profile location.");
  if(Directory.Exists(folder)){CheckTree(App.ProfileHome,folder);Directory.Delete(folder,true);}
  if(LaunchId==id)SetLaunch("default");profiles.Remove(profile);Write(profiles);
 }
 static void CheckTree(string root,string target)
 {
  CheckAncestors(root,target);CheckTree(target);
 }
 static void CheckAncestors(string root,string target)
 {
  for(string? current=target;current!=null;current=Path.GetDirectoryName(current)){
   if((File.GetAttributes(current)&FileAttributes.ReparsePoint)!=0)throw new IOException("Still cannot delete a profile through a linked folder.");
   if(string.Equals(Path.GetFullPath(current),Path.GetFullPath(root),StringComparison.OrdinalIgnoreCase))break;
  }
 }
 public static async Task ResetClosedDefault()
 {
  using var catalogGate=await Lock();var profile=Read().Single(p=>p.Id=="default");
  using var instanceGate=new System.Threading.Mutex(true,App.InstanceName(Folder(profile)),out var exclusive);
  if(!exclusive||IsCurrent(profile))throw new InvalidOperationException("Open another profile, then close Default before resetting it.");
  string[] names=["WebView","Extensions","ExtensionCache","state.json","state.json.bak","state.json.tmp","logins.dpapi","logins.dpapi.tmp","errors.log"];
  var paths=names.Select(n=>Path.Combine(App.ProfileHome,n)).Where(Path.Exists).ToArray();
  foreach(var path in paths)CheckTree(App.ProfileHome,path);
  foreach(var path in paths){if(Directory.Exists(path))Directory.Delete(path,true);else File.Delete(path);}
 }
 static void Write(List<BrowserProfile> profiles){File.WriteAllText(Catalog+".tmp",JsonSerializer.Serialize(profiles));File.Move(Catalog+".tmp",Catalog,true);}
 static async Task<FileStream> Lock()
 {
  Directory.CreateDirectory(App.ProfileHome);
  for(int attempt=0;attempt<40;attempt++)try{return File.Open(Path.Combine(App.ProfileHome,"profiles.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);}catch(IOException){await Task.Delay(50);}
  throw new IOException("Another profile is being changed. Try again.");
 }
 static string? displayName;
 public static string CurrentName()=>displayName??=Read().FirstOrDefault(p=>string.Equals(Path.GetFullPath(Folder(p)),App.DataRoot,StringComparison.OrdinalIgnoreCase))?.Name??"Default";
 public static async Task<BrowserProfile> Create(string name,SavedState? initial=null)
 {
  name=name.Trim();if(name.Length is <1 or >40||name.Any(char.IsControl))throw new ArgumentException("Use a profile name between 1 and 40 characters.");
  using(var gate=await Lock()){
   var profiles=Read();if(profiles.Count>=30)throw new InvalidOperationException("This browser already has 30 profiles.");
   var added=new BrowserProfile{Id=Guid.NewGuid().ToString("N"),Name=name};
   var folder=Path.GetFullPath(Folder(added));
   Directory.CreateDirectory(Path.GetDirectoryName(folder)!);
   CheckAncestors(App.ProfileHome,Path.GetDirectoryName(folder)!);
   if(Directory.Exists(folder))throw new IOException("The new profile folder already exists.");
   Directory.CreateDirectory(folder);
   try{
    if(initial!=null)File.WriteAllText(Path.Combine(folder,"state.json"),JsonSerializer.Serialize(initial));
    profiles.Add(added);Write(profiles);return added;
   }catch{
    // Only remove the newly allocated GUID directory, after checking the boundary and links.
    CheckTree(App.ProfileHome,folder);Directory.Delete(folder,true);throw;
   }
  }
 }
}
