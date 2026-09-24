using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;

namespace Still;

public sealed class ImportedCookie
{
 public string Name="",Value="",Domain="",Path="/";
 public bool Secure,HttpOnly,Session;
 public int SameSite; // Chromium: -1 unspecified, 0 none, 1 lax, 2 strict
 public DateTime Expires;
}

// Reads a Chromium-family profile (Opera GX, Opera, Chrome, Edge, Brave) for the current
// Windows account. Works while the source browser is running: every database is copied
// into a private, per-import snapshot folder inside Still's profile and deleted afterwards.
// Encrypted values are decrypted only with the source browser's own DPAPI-protected key,
// which Windows releases only to this same Windows account.
public sealed class ExternalProfileImport : IDisposable
{
 public string Id { get; } = Guid.NewGuid().ToString("N");
 public List<Visit> Bookmarks { get; } = [];
 public List<Visit> History { get; } = [];
 public List<LoginEntry> Logins { get; } = [];
 public List<ImportedCookie> Cookies { get; } = [];
 public List<string> Warnings { get; } = [];
 public int Skipped { get; private set; }
 public bool CookiesLocked { get; private set; }
 byte[]? key;

 public static string? SafeUrl(string? value) => value?.Length <= 8192 && Uri.TryCreate(value,UriKind.Absolute,out var uri)
  && uri.Scheme is "https" or "http" && uri.UserInfo.Length==0 ? uri.AbsoluteUri : null;
 static string Title(string? title,string url) => string.IsNullOrWhiteSpace(title)?new Uri(url).Host:new string(title.Where(c=>!char.IsControl(c)).Take(500).ToArray());

 public static ExternalProfileImport Read(string folder)
 {
  folder=Path.GetFullPath(folder);
  if(folder.StartsWith(@"\\",StringComparison.Ordinal))throw new IOException("Choose a local profile folder, not a network share.");
  if(!Directory.Exists(folder))throw new IOException("That profile folder no longer exists.");
  if(!File.Exists(Path.Combine(folder,"Bookmarks"))&&!File.Exists(Path.Combine(folder,"History"))&&Directory.Exists(Path.Combine(folder,"Default")))folder=Path.Combine(folder,"Default");
  string bookmarks=Path.Combine(folder,"Bookmarks"),history=Path.Combine(folder,"History");
  if(!File.Exists(bookmarks)&&!File.Exists(history))throw new IOException("No Chromium bookmarks or history were found in that folder.");
  var result=new ExternalProfileImport();
  string snapshot=Path.Combine(App.DataRoot,"ImportSnapshot",result.Id);
  Directory.CreateDirectory(snapshot);
  try{
   result.key=ReadKey(folder);
   if(File.Exists(bookmarks))result.Section("Bookmarks",()=>result.ReadBookmarks(bookmarks));
   if(File.Exists(history))result.Section("History",()=>result.ReadHistory(Copy(history,snapshot)));
   string logins=Path.Combine(folder,"Login Data");
   if(File.Exists(logins))result.Section("Passwords",()=>result.ReadLogins(Copy(logins,snapshot)));
   string cookies=Path.Combine(folder,"Network","Cookies");if(!File.Exists(cookies))cookies=Path.Combine(folder,"Cookies");
   if(File.Exists(cookies))result.Section("Cookies",()=>result.ReadCookies(Copy(cookies,snapshot)));
  }finally{
   SqliteConnection.ClearAllPools();
   try{Directory.Delete(snapshot,true);}catch(IOException){}catch(UnauthorizedAccessException){}
   if(result.key!=null)CryptographicOperations.ZeroMemory(result.key);
  }
  return result;
 }
 void Section(string name,Action read)
 {
  try{read();}
  catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException or SqliteException or CryptographicException or FormatException)
  {if((ex.HResult&0xFFFF)==32&&name=="Cookies"){CookiesLocked=true;return;}
   Warnings.Add((ex.HResult&0xFFFF)==32
    ? name+" are locked while the source browser is open. Close it completely (including its tray icon), then review again to include them."
    : name+" couldn't be read and will be skipped.");App.Log(new IOException(name+" import: "+ex.GetType().Name));}
 }

 // Copy a live database plus its journal/WAL while the source browser keeps writing.
 static string Copy(string path,string snapshot)
 {
  string target=Path.Combine(snapshot,Guid.NewGuid().ToString("N")+".db");
  CopyShared(path,target,256L*1024*1024);
  foreach(var suffix in new[]{"-wal","-journal"})if(File.Exists(path+suffix))CopyShared(path+suffix,target+suffix,128L*1024*1024);
  return target;
 }
 static void CopyShared(string from,string to,long max)
 {
  if((File.GetAttributes(from)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked database files are refused.");
  using var source=new FileStream(from,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);
  if(source.Length>max)throw new IOException("This file exceeds the import size limit.");
  using var target=new FileStream(to,FileMode.CreateNew,FileAccess.Write,FileShare.None);
  source.CopyTo(target);
 }
 static SqliteConnection Open(string path)
 {
  // Opened read-write only so SQLite can replay the copied WAL/rollback journal into the private copy.
  var connection=new SqliteConnection(new SqliteConnectionStringBuilder{DataSource=path,Mode=SqliteOpenMode.ReadWrite,Pooling=false}.ToString());
  connection.Open();
  using var command=connection.CreateCommand();command.CommandText="PRAGMA trusted_schema=OFF;";command.ExecuteNonQuery();
  return connection;
 }

 static byte[]? ReadKey(string profile)
 {
  foreach(var dir in new[]{profile,Path.GetDirectoryName(profile)}){
   if(dir==null)continue;string file=Path.Combine(dir,"Local State");
   if(!File.Exists(file))continue;
   using var stream=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);
   using var json=JsonDocument.Parse(stream);
   if(!json.RootElement.TryGetProperty("os_crypt",out var crypt)||!crypt.TryGetProperty("encrypted_key",out var encoded))return null;
   var raw=Convert.FromBase64String(encoded.GetString()??"");
   if(raw.Length<6||!raw.AsSpan(0,5).SequenceEqual("DPAPI"u8))return null;
   try{return ProtectedData.Unprotect(raw[5..],null,DataProtectionScope.CurrentUser);}
   finally{CryptographicOperations.ZeroMemory(raw);}
  }
  return null;
 }
 // Returns null for values this account can't decrypt, including Chrome's app-bound (v20) values.
 byte[]? Decrypt(byte[] data)
 {
  if(data.Length==0)return [];
  if(data.Length>3+12+16&&data[0]=='v'&&data[1]=='1'&&data[2]=='0'){
   if(key==null)return null;
   var nonce=data.AsSpan(3,12);var cipher=data.AsSpan(15,data.Length-15-16);var tag=data.AsSpan(data.Length-16);
   var plain=new byte[cipher.Length];
   using var gcm=new AesGcm(key,16);gcm.Decrypt(nonce,cipher,tag,plain);return plain;
  }
  if(data[0]=='v')return null;
  try{return ProtectedData.Unprotect(data,null,DataProtectionScope.CurrentUser);}catch(CryptographicException){return null;}
 }

 void ReadBookmarks(string path)
 {
  using var source=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);
  if(source.Length>10*1024*1024)throw new IOException("Bookmarks exceed 10 MB.");
  using var json=JsonDocument.Parse(source,new(){MaxDepth=64});var seen=new HashSet<string>(StringComparer.Ordinal);
  void Walk(JsonElement item)
  {
   if(Bookmarks.Count>=5000)return;
   if(item.ValueKind==JsonValueKind.Object){
    if(item.TryGetProperty("url",out var raw)){
     var url=raw.ValueKind==JsonValueKind.String?SafeUrl(raw.GetString()):null;
     if(url==null||!seen.Add(url)){Skipped++;return;}
     string? name=item.TryGetProperty("name",out var label)&&label.ValueKind==JsonValueKind.String?label.GetString():null;
     Bookmarks.Add(new(){Url=url,Title=Title(name,url)});
    }else foreach(var property in item.EnumerateObject())Walk(property.Value);
   }else if(item.ValueKind==JsonValueKind.Array)foreach(var child in item.EnumerateArray())Walk(child);
  }
  Walk(json.RootElement);
  if(Bookmarks.Count==5000)Warnings.Add("Bookmarks are limited to the first 5,000 entries; folders are flattened.");
 }
 void ReadHistory(string path)
 {
  using var connection=Open(path);using var command=connection.CreateCommand();
  command.CommandText="SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 2000";
  using var reader=command.ExecuteReader();var seen=new HashSet<string>(StringComparer.Ordinal);
  while(reader.Read()){
   var url=reader.IsDBNull(0)?null:SafeUrl(reader.GetString(0));
   if(url==null||!seen.Add(url)){Skipped++;continue;}
   DateTime at;
   try{at=DateTime.FromFileTimeUtc(checked(reader.GetInt64(2)*10)).ToLocalTime();if(at.Year<1990||at>DateTime.Now.AddDays(1)){Skipped++;continue;}}
   catch(Exception ex) when(ex is OverflowException or ArgumentException or InvalidCastException){Skipped++;continue;}
   History.Add(new(){Url=url,Title=Title(reader.IsDBNull(1)?null:reader.GetString(1),url),At=at});
  }
 }
 void ReadLogins(string path)
 {
  using var connection=Open(path);using var command=connection.CreateCommand();
  command.CommandText="SELECT origin_url, username_value, password_value FROM logins WHERE blacklisted_by_user=0 LIMIT 5000";
  using var reader=command.ExecuteReader();int locked=0;
  while(reader.Read()){
   var url=reader.IsDBNull(0)?null:SafeUrl(reader.GetString(0));
   if(url==null||reader.IsDBNull(2)){Skipped++;continue;}
   var plain=Decrypt((byte[])reader[2]);
   if(plain==null){locked++;continue;}
   string password=Encoding.UTF8.GetString(plain);CryptographicOperations.ZeroMemory(plain);
   string username=reader.IsDBNull(1)?"":reader.GetString(1);
   string origin=new Uri(url).GetLeftPart(UriPartial.Authority);
   if(password.Length is <1 or >8192||username.Length>1024||Logins.Any(l=>l.Origin==origin&&l.Username==username)){Skipped++;continue;}
   Logins.Add(new(){Origin=origin,Username=username,Password=password});
  }
  if(locked>0)Warnings.Add($"{locked} passwords use the source browser's app-bound encryption and can't be read. Export them to CSV from that browser to import them.");
 }
 void ReadCookies(string path)
 {
  using var connection=Open(path);using var command=connection.CreateCommand();
  // Since Chromium DB version 24, decrypted values are prefixed with SHA-256(host_key).
  command.CommandText="SELECT value FROM meta WHERE key='version'";
  int version=int.TryParse(command.ExecuteScalar() as string,out var v)?v:0;
  command.CommandText="SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite, has_expires FROM cookies LIMIT 20000";
  using var reader=command.ExecuteReader();int locked=0;var now=DateTime.UtcNow;
  while(reader.Read()){
   string host=reader.GetString(0),name=reader.GetString(1),value=reader.IsDBNull(2)?"":reader.GetString(2);
   if(value.Length==0&&!reader.IsDBNull(3)){
    var plain=Decrypt((byte[])reader[3]);
    if(plain==null){locked++;continue;}
    int skip=version>=24&&plain.Length>=32?32:0;
    value=Encoding.UTF8.GetString(plain,skip,plain.Length-skip);CryptographicOperations.ZeroMemory(plain);
   }
   bool session=reader.GetInt64(9)==0;DateTime expires=now;
   if(!session){
    try{expires=DateTime.FromFileTimeUtc(checked(reader.GetInt64(5)*10));}catch(Exception ex) when(ex is OverflowException or ArgumentException){Skipped++;continue;}
    if(expires<=now){Skipped++;continue;}
   }
   if(host.Length is 0 or >255||name.Length>4096||value.Length>4096){Skipped++;continue;}
   Cookies.Add(new(){Domain=host,Name=name,Value=value,Path=reader.IsDBNull(4)?"/":reader.GetString(4),Secure=reader.GetInt64(6)!=0,HttpOnly=reader.GetInt64(7)!=0,SameSite=(int)reader.GetInt64(8),Session=session,Expires=expires});
  }
  if(locked>0)Warnings.Add($"{locked} cookies use app-bound encryption and can't be transferred; sign in to those sites again.");
 }
 public void Dispose(){Logins.Clear();Cookies.Clear();}
}
