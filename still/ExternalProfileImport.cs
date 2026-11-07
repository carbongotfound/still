using System.Formats.Asn1;
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

// Reads a Chromium-family profile (Opera GX, Opera, Chrome, Edge, Brave) or a Firefox profile for the current
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
  bool firefox=File.Exists(Path.Combine(folder,"places.sqlite"))||File.Exists(Path.Combine(folder,"key4.db"));
  if(!firefox&&!File.Exists(bookmarks)&&!File.Exists(history))throw new IOException("No browser bookmarks or history were found in that folder.");
  var result=new ExternalProfileImport();
  // Remove leftovers from an import that was interrupted by a crash or power loss.
  string snapshots=Path.Combine(App.DataRoot,"ImportSnapshot");
  if(Directory.Exists(snapshots))foreach(var stale in Directory.EnumerateDirectories(snapshots))try{Directory.Delete(stale,true);}catch(IOException){}catch(UnauthorizedAccessException){}
  string snapshot=Path.Combine(App.DataRoot,"ImportSnapshot",result.Id);
  Directory.CreateDirectory(snapshot);
  try{
   if(firefox){
    string places=Path.Combine(folder,"places.sqlite");
    if(File.Exists(places))result.Section("Bookmarks and history",()=>result.ReadFirefoxPlaces(Copy(places,snapshot)));
    if(File.Exists(Path.Combine(folder,"logins.json"))&&File.Exists(Path.Combine(folder,"key4.db")))result.Section("Passwords",()=>result.ReadFirefoxLogins(folder,snapshot));
    return result;
   }
   result.key=ReadKey(folder);
   // A browser signed in to an account keeps that account's bookmarks and passwords in separate files.
   foreach(var file in new[]{bookmarks,Path.Combine(folder,"AccountBookmarks")})if(File.Exists(file))result.Section("Bookmarks",()=>result.ReadBookmarks(file));
   if(File.Exists(history))result.Section("History",()=>result.ReadHistory(Copy(history,snapshot)));
   foreach(var logins in new[]{Path.Combine(folder,"Login Data"),Path.Combine(folder,"Login Data For Account")})
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
  using var json=JsonDocument.Parse(source,new(){MaxDepth=64});var seen=Bookmarks.Select(b=>b.Url).ToHashSet(StringComparer.Ordinal);
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
  if(locked>0)Warnings.Add((locked==1?"One password is locked to the browser that saved it, so Still can't read it.":$"{locked} passwords are locked to the browser that saved them, so Still can't read them.")+" Export your passwords to a CSV file from that browser (in Chrome: Google Password Manager, then Settings, then Export passwords) and add the file with Passwords CSV.");
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
    // That prefix ties a sealed value to its site. Without it, this might be another site's, moved here.
    bool own=version>=24&&plain.Length>=32&&CryptographicOperations.FixedTimeEquals(plain.AsSpan(0,32),SHA256.HashData(Encoding.UTF8.GetBytes(host)));
    if(own)value=Encoding.UTF8.GetString(plain,32,plain.Length-32);
    CryptographicOperations.ZeroMemory(plain);
    if(!own){Skipped++;continue;}
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
 void ReadFirefoxPlaces(string path)
 {
  using var connection=Open(path);using var command=connection.CreateCommand();
  command.CommandText="SELECT p.url, b.title FROM moz_bookmarks b JOIN moz_places p ON p.id=b.fk WHERE b.type=1 LIMIT 5000";
  var seen=new HashSet<string>(StringComparer.Ordinal);
  using(var reader=command.ExecuteReader())while(reader.Read()){
   var url=reader.IsDBNull(0)?null:SafeUrl(reader.GetString(0));
   if(url==null||!seen.Add(url)){Skipped++;continue;}
   Bookmarks.Add(new(){Url=url,Title=Title(reader.IsDBNull(1)?null:reader.GetString(1),url)});
  }
  command.CommandText="SELECT url, title, last_visit_date FROM moz_places WHERE last_visit_date IS NOT NULL AND hidden=0 ORDER BY last_visit_date DESC LIMIT 2000";
  seen.Clear();
  using(var reader=command.ExecuteReader())while(reader.Read()){
   var url=reader.IsDBNull(0)?null:SafeUrl(reader.GetString(0));
   if(url==null||!seen.Add(url)){Skipped++;continue;}
   var at=DateTimeOffset.FromUnixTimeMilliseconds(reader.GetInt64(2)/1000).LocalDateTime; // stored in microseconds
   if(at.Year<1990||at>DateTime.Now.AddDays(1)){Skipped++;continue;}
   History.Add(new(){Url=url,Title=Title(reader.IsDBNull(1)?null:reader.GetString(1),url),At=at});
  }
 }
 const string FirefoxLocked="Firefox has a primary password, so Still can't read its saved passwords. In Firefox, open Passwords, choose Export passwords from the menu, and add the file with Passwords CSV.";
 // Firefox encrypts logins.json with a key kept in key4.db. Without a primary password that key opens with an
 // empty one: PBKDF2 over SHA-1(global salt), then AES-256-CBC (PBES2), as NSS does.
 void ReadFirefoxLogins(string folder,string snapshot)
 {
  using var connection=Open(Copy(Path.Combine(folder,"key4.db"),snapshot));using var command=connection.CreateCommand();
  command.CommandText="SELECT item1, item2 FROM metaData WHERE id='password'";
  byte[] salt,check;
  using(var reader=command.ExecuteReader()){if(!reader.Read())throw new IOException("No Firefox key.");salt=(byte[])reader[0];check=(byte[])reader[1];}
  var verified=Pbes2(salt,check);
  if(verified==null||!verified.AsSpan().SequenceEqual("password-check"u8)){Warnings.Add(FirefoxLocked);return;}
  command.CommandText="SELECT a11 FROM nssPrivate";
  byte[]? master=null;
  using(var reader=command.ExecuteReader())while(master==null&&reader.Read())if(!reader.IsDBNull(0))master=Pbes2(salt,(byte[])reader[0]);
  if(master==null){Warnings.Add(FirefoxLocked);return;}
  try{
   using var source=new FileStream(Path.Combine(folder,"logins.json"),FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);
   if(source.Length>20*1024*1024)throw new IOException("logins.json exceeds 20 MB.");
   using var json=JsonDocument.Parse(source);
   string? Text(JsonElement login,string name){
    if(!login.TryGetProperty(name,out var v)||v.ValueKind!=JsonValueKind.String)return null;
    var plain=DecryptFirefox(master,Convert.FromBase64String(v.GetString()??""));if(plain==null)return null;
    try{return Encoding.UTF8.GetString(plain);}finally{CryptographicOperations.ZeroMemory(plain);}
   }
   foreach(var login in json.RootElement.GetProperty("logins").EnumerateArray().Take(5000)){
    var url=login.TryGetProperty("hostname",out var host)&&host.ValueKind==JsonValueKind.String?SafeUrl(host.GetString()):null;
    string? username=url==null?null:Text(login,"encryptedUsername"),password=username==null?null:Text(login,"encryptedPassword");
    if(url==null||username==null||password==null||password.Length is <1 or >8192||username.Length>1024){Skipped++;continue;}
    string origin=new Uri(url).GetLeftPart(UriPartial.Authority);
    if(Logins.Any(l=>l.Origin==origin&&l.Username==username)){Skipped++;continue;}
    Logins.Add(new(){Origin=origin,Username=username,Password=password});
   }
  }finally{CryptographicOperations.ZeroMemory(master);}
 }
 static byte[]? Pbes2(byte[] globalSalt,byte[] der)
 {
  try{
   var outer=new AsnReader(der,AsnEncodingRules.DER).ReadSequence();var algorithm=outer.ReadSequence();
   if(algorithm.ReadObjectIdentifier()!="1.2.840.113549.1.5.13")return null; // Firefox before 75 used 3DES here
   var scheme=algorithm.ReadSequence();var kdf=scheme.ReadSequence();kdf.ReadObjectIdentifier();
   var p=kdf.ReadSequence();byte[] entrySalt=p.ReadOctetString();int iterations=(int)p.ReadInteger();
   var cipher=scheme.ReadSequence();cipher.ReadObjectIdentifier();byte[] iv=cipher.ReadOctetString();byte[] data=outer.ReadOctetString();
   if(iterations is <1 or >10_000_000)return null;
   var key=Rfc2898DeriveBytes.Pbkdf2(SHA1.HashData(globalSalt),entrySalt,iterations,HashAlgorithmName.SHA256,32);
   try{using var aes=Aes.Create();aes.Key=key;return aes.DecryptCbc(data,(byte[])[0x04,(byte)iv.Length,..iv]);} // NSS uses the DER-encoded IV
   finally{CryptographicOperations.ZeroMemory(key);}
  }catch(Exception ex) when(ex is AsnContentException or CryptographicException or OverflowException){return null;}
 }
 static byte[]? DecryptFirefox(byte[] master,byte[] der)
 {
  try{
   var outer=new AsnReader(der,AsnEncodingRules.DER).ReadSequence();outer.ReadOctetString();
   var algorithm=outer.ReadSequence();string oid=algorithm.ReadObjectIdentifier();byte[] iv=algorithm.ReadOctetString();byte[] data=outer.ReadOctetString();
   if(oid=="1.2.840.113549.3.7"&&master.Length>=24){using var des=TripleDES.Create();des.Key=master[..24];return des.DecryptCbc(data,iv);}
   if(oid=="2.16.840.1.101.3.4.1.42"&&master.Length>=32){using var aes=Aes.Create();aes.Key=master[..32];return aes.DecryptCbc(data,iv);}
   return null;
  }catch(Exception ex) when(ex is AsnContentException or CryptographicException or FormatException){return null;}
 }
 public void Dispose(){Logins.Clear();Cookies.Clear();}
}
