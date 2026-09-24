using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
namespace Still;
public partial class MainWindow
{
 sealed record OfficialExtension(string Version,string Url,string Sha256);
 OfficialExtension? officialCandidate;
 bool extensionDownload;
 static readonly HttpClient ExtensionHttp=new(new HttpClientHandler{AllowAutoRedirect=true,MaxAutomaticRedirections=5}){Timeout=TimeSpan.FromSeconds(90)};
 const string OfficialReleases="https://api.github.com/repos/uBlockOrigin/uBOL-home/releases/latest";
 async Task PrepareOfficialBlocker()
 {
  if(extensionDownload||extensionInstalling)return;
  extensionDownload=true;await PublishBrowserTools("extensions");
  try{
   using var request=new HttpRequestMessage(HttpMethod.Get,OfficialReleases);request.Headers.UserAgent.ParseAdd("Still/1.3");
   using var response=await ExtensionHttp.SendAsync(request);response.EnsureSuccessStatusCode();
   using var release=JsonDocument.Parse(await response.Content.ReadAsStringAsync());
   var root=release.RootElement;string version=root.GetProperty("tag_name").GetString()!;
   var core=await ManagementCore();if((await core.Profile.GetBrowserExtensionsAsync()).Any(e=>OfficialVersion(e.Id)==version)){Toast("uBlock Origin Lite is up to date.");return;}
   var asset=root.GetProperty("assets").EnumerateArray().First(a=>a.GetProperty("name").GetString()!.EndsWith(".chromium.zip",StringComparison.Ordinal));
   string url=asset.GetProperty("browser_download_url").GetString()!,digest=asset.GetProperty("digest").GetString()??"";
   if(!url.StartsWith("https://github.com/uBlockOrigin/uBOL-home/releases/download/",StringComparison.Ordinal)||!digest.StartsWith("sha256:")||digest.Length!=71||!digest[7..].All(Uri.IsHexDigit)||asset.GetProperty("size").GetInt64()>30*1024*1024)throw new IOException("The official release could not be verified.");
   using var download=await ExtensionHttp.GetAsync(url,HttpCompletionOption.ResponseHeadersRead);download.EnsureSuccessStatusCode();
   var final=download.RequestMessage?.RequestUri;
   if(final==null||final.Scheme!="https"||!(final.Host=="github.com"||final.Host.EndsWith(".githubusercontent.com",StringComparison.Ordinal)))throw new IOException("Unexpected download location.");
   using var data=new MemoryStream();using var input=await download.Content.ReadAsStreamAsync();byte[] buffer=new byte[65536];int count;
   while((count=await input.ReadAsync(buffer))>0){if(data.Length+count>30*1024*1024)throw new IOException("Extension download is larger than expected.");await data.WriteAsync(buffer.AsMemory(0,count));}
   string actual=Convert.ToHexString(SHA256.HashData(data.GetBuffer().AsSpan(0,(int)data.Length))).ToLowerInvariant();
   if(actual!=digest[7..].ToLowerInvariant())throw new IOException("The extension download did not match the publisher's SHA-256 digest.");
   string directory=Path.Combine(App.DataRoot,"ExtensionCache",Guid.NewGuid().ToString("N"));Directory.CreateDirectory(directory);data.Position=0;
   await Task.Run(()=>{
    using var zip=new ZipArchive(data,ZipArchiveMode.Read,true);long total=0;if(zip.Entries.Count>20000)throw new IOException("Too many extension files.");
    foreach(var entry in zip.Entries){
     total+=entry.Length;if(total>200*1024*1024)throw new IOException("The unpacked extension is too large.");
     if(((entry.ExternalAttributes>>16)&0xf000)==0xa000||entry.FullName.Contains(':'))throw new IOException("Unsafe extension archive entry.");
     string target=Path.GetFullPath(Path.Combine(directory,entry.FullName));
     if(!target.StartsWith(directory+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Unsafe extension archive path.");
     if(entry.FullName.EndsWith('/')){Directory.CreateDirectory(target);continue;}
     Directory.CreateDirectory(Path.GetDirectoryName(target)!);entry.ExtractToFile(target);
    }
   });
   await StageExtension(directory);officialCandidate=new(version,url,actual);await PublishBrowserTools("extensions");
  }catch(Exception ex){Toast("Couldn't prepare uBlock Origin Lite: "+ex.Message);}
  finally{extensionDownload=false;await PublishBrowserTools("extensions");}
 }
 string? OfficialVersion(string id)
 {
  try{return JsonSerializer.Deserialize<OfficialExtension>(File.ReadAllText(Path.Combine(App.DataRoot,"Extensions",id+".official.json")))?.Version;}catch{return null;}
 }
 static string ExtensionName(JsonElement manifest,string folder)
 {
  string name=manifest.GetProperty("name").GetString()??"Extension";
  if(name.StartsWith("__MSG_")&&name.EndsWith("__"))try{
   string locale=manifest.TryGetProperty("default_locale",out var lang)?lang.GetString()??"en":"en";
   if(locale.All(c=>char.IsAsciiLetterOrDigit(c)||c is '_' or '-')){
    using var messages=JsonDocument.Parse(File.ReadAllText(Path.Combine(folder,"_locales",locale,"messages.json")));
    if(messages.RootElement.TryGetProperty(name[6..^2],out var entry))name=entry.GetProperty("message").GetString()??name;
   }
  }catch{}
  return name;
 }
}
