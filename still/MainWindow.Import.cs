using System.IO;
using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.VisualBasic.FileIO;
using Microsoft.Win32;
namespace Still;
public partial class MainWindow
{
 sealed class ImportBatch
 {
  public string Id=Guid.NewGuid().ToString("N"),Kind="",FileName="";
  public List<LoginEntry> Logins=[];
  public List<Visit> Bookmarks=[],History=[];
  public List<BrowserTab> Tabs=[];
  public int Skipped;
 }
 ImportBatch? importBatch;
 object ImportData()=>new{external=ExternalImportData(),preview=importBatch==null?null:new{id=importBatch.Id,kind=importBatch.Kind,file=importBatch.FileName,logins=importBatch.Logins.Count,bookmarks=importBatch.Bookmarks.Count,history=importBatch.History.Count,tabs=importBatch.Tabs.Count,skipped=importBatch.Skipped}};
 void ChooseImport(string kind)
 {
  _=Dispatcher.BeginInvoke(async()=>{
   var picker=new OpenFileDialog{Title="Import into "+ProfileCatalog.CurrentName(),Filter=kind=="passwords"?"Passwords CSV|*.csv":kind=="session"?"Still data JSON|*.json":"Bookmarks HTML or JSON|*.html;*.htm;*.json|All files|*.*"};
   if(picker.ShowDialog(this)!=true)return;
   try{await PrepareImport(kind,picker.FileName);ShellOpen("import");}catch(Exception ex){Toast("Couldn't read this import: "+ex.Message);}
  });
 }
 static string? ImportUrl(string value)=>ExternalProfileImport.SafeUrl(value);
 async Task PrepareImport(string kind,string path)
 {
  if(new FileInfo(path).Length>10*1024*1024)throw new IOException("Choose a file smaller than 10 MB.");
  string contents=await File.ReadAllTextAsync(path);var batch=new ImportBatch{Kind=kind,FileName=Path.GetFileName(path)};
  if(kind=="passwords"){
   using var csv=new TextFieldParser(new StringReader(contents)){TextFieldType=FieldType.Delimited,HasFieldsEnclosedInQuotes=true};csv.SetDelimiters(",");
   var header=csv.ReadFields()?.Select(v=>v.Trim().ToLowerInvariant()).ToArray()??[];
   int Column(params string[] names)=>Array.FindIndex(header,h=>names.Contains(h));
   int site=Column("url","origin","hostname","login_uri"),user=Column("username","login_username"),secret=Column("password","login_password");
   if(site<0||secret<0)throw new IOException("The CSV needs URL and password columns, such as a Chrome, Edge, Firefox, or Bitwarden password export.");
   while(!csv.EndOfData){
    if(batch.Logins.Count+batch.Skipped>=5000)throw new IOException("Import at most 5,000 logins at a time.");
    var row=csv.ReadFields()??[];string Value(int i)=>i>=0&&i<row.Length?row[i]:"";
    var url=ImportUrl(Value(site));string password=Value(secret),username=Value(user);
    if(url==null||password.Length is <1 or >8192||username.Length>1024){batch.Skipped++;continue;}
    string origin=new Uri(url).GetLeftPart(UriPartial.Authority);
    if(batch.Logins.Any(v=>v.Origin==origin&&v.Username==username)){batch.Skipped++;continue;}
    batch.Logins.Add(new(){Origin=origin,Username=username,Password=password});
   }
  }else if(kind=="session"){
   var imported=JsonSerializer.Deserialize<SavedState>(contents)??throw new IOException("This is not a Still data file.");
   batch.Bookmarks=imported.Bookmarks.Where(v=>ImportUrl(v.Url)!=null).Take(5000).Select(v=>new Visit{Title=v.Title,Url=ImportUrl(v.Url)!,At=v.At}).ToList();
   batch.History=imported.History.Where(v=>ImportUrl(v.Url)!=null).Take(2000).Select(v=>new Visit{Title=v.Title,Url=ImportUrl(v.Url)!,At=v.At}).ToList();
   batch.Tabs=imported.Tabs.Where(v=>ImportUrl(v.Url)!=null).Take(50).Select(v=>new BrowserTab{Title=v.Title,Url=ImportUrl(v.Url)!,Pinned=v.Pinned}).ToList();
  }else if(kind=="bookmarks"){
   void Bookmark(string url,string title){var valid=ImportUrl(url);if(valid==null||batch.Bookmarks.Any(b=>b.Url==valid)){batch.Skipped++;return;}if(batch.Bookmarks.Count>=5000)throw new IOException("Import at most 5,000 bookmarks at a time.");batch.Bookmarks.Add(new(){Url=valid,Title=title.Length>500?title[..500]:title});}
   if(contents.TrimStart().StartsWith('{')){
    using var json=JsonDocument.Parse(contents,new(){MaxDepth=64});
    void Walk(JsonElement node){if(node.ValueKind==JsonValueKind.Object){if(node.TryGetProperty("url",out var url)&&url.ValueKind==JsonValueKind.String)Bookmark(url.GetString()!,node.TryGetProperty("name",out var title)?title.GetString()??url.GetString()!:url.GetString()!);else foreach(var property in node.EnumerateObject())Walk(property.Value);}else if(node.ValueKind==JsonValueKind.Array)foreach(var child in node.EnumerateArray())Walk(child);}
    Walk(json.RootElement);
   }else{
    var anchors=Regex.Matches(contents,"<a\\s+[^>]*href\\s*=\\s*[\"'](?<url>[^\"']+)[\"'][^>]*>(?<title>.*?)</a>",RegexOptions.IgnoreCase|RegexOptions.Singleline,TimeSpan.FromSeconds(2));
    foreach(Match match in anchors)Bookmark(WebUtility.HtmlDecode(match.Groups["url"].Value),WebUtility.HtmlDecode(Regex.Replace(match.Groups["title"].Value,"<[^>]+>","",RegexOptions.None,TimeSpan.FromSeconds(1))));
   }
  }else throw new IOException("Unknown import type.");
  importBatch=batch;await PublishBrowserTools("import");
 }
 async Task CompleteImport(string id,bool replaceLogins)
 {
  var batch=importBatch;if(batch==null||batch.Id!=id)return;
  int added=0,kept=0;
  if(batch.Kind=="passwords"){
   var entries=Vault.Read();
   foreach(var login in batch.Logins){var existing=entries.FirstOrDefault(v=>v.Origin==login.Origin&&v.Username==login.Username);if(existing!=null){if(replaceLogins){existing.Password=login.Password;added++;}else kept++;}else{entries.Add(login);added++;}}
   Vault.Write(entries);
  }else{
   foreach(var item in batch.Bookmarks)if(!state.Bookmarks.Any(v=>v.Url==item.Url)){state.Bookmarks.Add(item);added++;}
   foreach(var item in batch.History)if(!state.History.Any(v=>v.Url==item.Url&&v.At==item.At))state.History.Add(item);
   state.History=state.History.OrderByDescending(v=>v.At).Take(2000).ToList();
   foreach(var item in batch.Tabs)if(!tabs.Any(v=>v.Url==item.Url)){tabs.Add(item);added++;}
   SaveLater();RenderTabs();
  }
  importBatch=null;await PublishBrowserTools("import");Toast($"Imported {added} items."+(kept>0?$" Kept {kept} existing logins.":""));
 }
 void ExportBrowserData()
 {
  _=Dispatcher.BeginInvoke(()=>{
   var dialog=new SaveFileDialog{Title="Export tabs, bookmarks, and history",FileName="Still data.json",Filter="Still data JSON|*.json"};
   if(dialog.ShowDialog(this)!=true)return;
   try{Save();File.WriteAllText(dialog.FileName,JsonSerializer.Serialize(state,new JsonSerializerOptions{WriteIndented=true}));Toast("Browsing data exported. Passwords and cookies are not included.");}catch(Exception ex){Toast(ex.Message);}
  });
 }
}
