using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
namespace Still;
public partial class MainWindow
{
 bool extensionDownload;
 static readonly HttpClient ExtensionHttp=new(new HttpClientHandler{AllowAutoRedirect=true,MaxAutomaticRedirections=5}){Timeout=TimeSpan.FromSeconds(90)};
 // Unpacks a zipped extension into a fresh cache folder, refusing links, odd paths and oversized archives.
 static async Task<string> ExtractExtension(MemoryStream data)
 {
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
  return directory;
 }
 // Chrome Web Store: download the extension's CRX from Google's update service, strip the CRX header, then use the normal review.
 // ponytail: trusts Google's HTTPS download instead of verifying the CRX3 signature; add signature checks if extensions ever come from other hosts.
 async Task PrepareStoreExtension(string page)
 {
  var match=System.Text.RegularExpressions.Regex.Match(page,@"^https://(chromewebstore\.google\.com/detail/(?:[^/?#]+/)?|chrome\.google\.com/webstore/detail/(?:[^/?#]+/)?)([a-p]{32})(?:[/?#]|$)");
  if(!match.Success){Toast("Open an extension's page in the Chrome Web Store first.");return;}
  if(extensionDownload||extensionInstalling)return;
  string id=match.Groups[2].Value;
  extensionDownload=true;ShellOpen("extensions");await PublishBrowserTools("extensions");
  try{
   string url="https://clients2.google.com/service/update2/crx?response=redirect&prodversion=140.0&acceptformat=crx2,crx3&x=id%3D"+id+"%26uc";
   using var download=await ExtensionHttp.GetAsync(url,HttpCompletionOption.ResponseHeadersRead);download.EnsureSuccessStatusCode();
   var final=download.RequestMessage?.RequestUri;
   if(final==null||final.Scheme!="https"||!(final.Host.EndsWith(".google.com",StringComparison.Ordinal)||final.Host.EndsWith(".googleusercontent.com",StringComparison.Ordinal)||final.Host.EndsWith(".gvt1.com",StringComparison.Ordinal)))throw new IOException("Unexpected download location.");
   using var crx=new MemoryStream();using var input=await download.Content.ReadAsStreamAsync();byte[] buffer=new byte[65536];int count;
   while((count=await input.ReadAsync(buffer))>0){if(crx.Length+count>100*1024*1024)throw new IOException("Extension download is too large.");await crx.WriteAsync(buffer.AsMemory(0,count));}
   var bytes=crx.GetBuffer().AsSpan(0,(int)crx.Length);
   if(bytes.Length<16||!bytes[..4].SequenceEqual("Cr24"u8))throw new IOException("That extension isn't available to download.");
   uint version=BitConverter.ToUInt32(bytes[4..]);
   long start=version==3?12+(long)BitConverter.ToUInt32(bytes[8..]):version==2?16+(long)BitConverter.ToUInt32(bytes[8..])+BitConverter.ToUInt32(bytes[12..]):-1;
   if(start<0||start>=bytes.Length)throw new IOException("Unsupported extension package.");
   using var zip=new MemoryStream(bytes[(int)start..].ToArray());
   await StageExtension(await ExtractExtension(zip));
  }catch(Exception ex)when(ex is IOException or HttpRequestException or TaskCanceledException or InvalidDataException or JsonException or KeyNotFoundException){Toast("Couldn't add this extension: "+ex.Message);}
  finally{extensionDownload=false;await PublishBrowserTools("extensions");}
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
