using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
namespace Still;
public sealed class LoginEntry
{
 public string Id {get;set;}=Guid.NewGuid().ToString("N");
 public string Origin {get;set;}="";
 public string Username {get;set;}="";
 public string Password {get;set;}="";
}
public static class Vault
{
 static string FilePath=>Path.Combine(App.DataRoot,"logins.dpapi");
 public static List<LoginEntry> Read()
 {
  if(!File.Exists(FilePath))return [];
  byte[] plain=ProtectedData.Unprotect(File.ReadAllBytes(FilePath),null,DataProtectionScope.CurrentUser);
  try{return JsonSerializer.Deserialize<List<LoginEntry>>(plain)??[];}finally{CryptographicOperations.ZeroMemory(plain);}
 }
 public static void Write(List<LoginEntry> entries)
 {
  byte[] plain=JsonSerializer.SerializeToUtf8Bytes(entries);
  try{File.WriteAllBytes(FilePath+".tmp",ProtectedData.Protect(plain,null,DataProtectionScope.CurrentUser));File.Move(FilePath+".tmp",FilePath,true);}finally{CryptographicOperations.ZeroMemory(plain);}
 }
 public static string Generate()
 {
  const string alphabet="ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*-_+";
  return new string(Enumerable.Range(0,24).Select(_=>alphabet[RandomNumberGenerator.GetInt32(alphabet.Length)]).ToArray());
 }
}
