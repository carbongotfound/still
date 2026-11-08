using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Microsoft.Win32;
namespace Still;
// Saved logins in pages (LoginObserver.js): the key in a field, auto sign-in at the first touch, strong passwords for new accounts, and
// the Save / Update prompt after signing in. Never in private tabs. AIs never get any of it: they can't fill while
// they drive a tab, what they read is redacted (RedactLogins), and a sign-in page pauses them for the user.
public partial class MainWindow
{
 sealed record LoginOffer(string Id,string Origin,string Username,string Password,string? ExistingId,DateTime Expires);
 LoginOffer? loginOffer;
 object? LoginOfferData()=>loginOffer is{} v&&v.Expires>DateTime.UtcNow?new{id=v.Id,origin=v.Origin,username=v.Username,password=v.Password,update=v.ExistingId!=null}:null;
 static string Origin(Uri uri)=>uri.GetLeftPart(UriPartial.Authority);
 static bool IsLoginOrigin(string source,out Uri uri)=>Uri.TryCreate(source,UriKind.Absolute,out uri!)&&uri.Scheme is "https" or "http";
 /// https, or http on this computer. Anywhere else, filling a login asks first and auto sign-in stays off.
 static bool SecureOrigin(Uri uri)=>uri.Scheme=="https"||uri.IsLoopback;
 [GeneratedRegex("^__stillLogin[0-9a-f]{16}$")] private static partial Regex LoginApi();
 /// An AI is driving this tab right now (not paused for the user), so nothing fills a login here.
 static bool AgentDriving(BrowserTab tab)=>tab.AgentKey is{} who&&workers.GetValueOrDefault(who) is{Paused:false} w&&DateTime.UtcNow-w.Seen<TimeSpan.FromMinutes(2);

 async Task InstallLoginObserver(BrowserTab tab)
 {
  if(tab.Private||tab.View?.CoreWebView2 is not{} core)return;
  if(tab.LoginScriptId!=null)core.RemoveScriptToExecuteOnDocumentCreated(tab.LoginScriptId);
  // Before each new document's own scripts only: anything run in a page already going could hand them the token. So the
  // token lasts as long as the tab, for the helper already in the page. A changed setting reaches that page at its next load.
  if(tab.LoginToken.Length==0)tab.LoginToken=Guid.NewGuid().ToString("N");
  string js=(await AppContent.ReadAsset("LoginObserver.js")).Replace("__STILL_LOGIN_CONFIG__",JsonSerializer.Serialize(new{token=tab.LoginToken,capture=Prefs.OfferPasswordSave||Prefs.OfferPasswordUpdate}));
  tab.LoginScriptId=await core.AddScriptToExecuteOnDocumentCreatedAsync(js);
 }
 async Task ReceiveLogin(BrowserTab tab,CoreWebView2WebMessageReceivedEventArgs e)
 {
  if(tab.Private||tab.View?.CoreWebView2 is not{} core||tab.CertificateError||!IsLoginOrigin(e.Source,out var source)||!IsLoginOrigin(core.Source,out var current)||Origin(source)!=Origin(current))return;
  try{
   string json=e.WebMessageAsJson;if(json.Length>40000)return;
   using var message=JsonDocument.Parse(json);var m=message.RootElement;
   string S(string k)=>m.TryGetProperty(k,out var v)&&v.ValueKind==JsonValueKind.String?v.GetString()??"":"";
   string origin=Origin(current);
   if(S("kind")!="still-login"||S("token")!=tab.LoginToken||S("origin")!=origin)return;
   switch(S("action")){
    case "detected":
     if(!LoginApi().IsMatch(S("api")))return;
     tab.LoginApi=S("api");tab.LoginDetected=S("form") is "login" or "username";ShellPublish();
     await OfferLogins(tab,core,origin,S("form"),SecureOrigin(current));break;
    case "fill":{
     var entry=Vault.Read().FirstOrDefault(v=>v.Id==S("id")&&v.Origin==origin);
     bool confirmed=m.TryGetProperty("confirmed",out var c)&&c.ValueKind==JsonValueKind.True;
     if(entry==null||AgentDriving(tab)||!SecureOrigin(current)&&!confirmed)return;
     tab.LoginFilled=await FillSavedLogin(entry,tab);break;
    }
    case "auto":{
     var only=Vault.Read().Where(v=>v.Origin==origin).ToArray();
     if(SecureOrigin(current)&&Prefs.AutoFillPasswords&&only.Length==1&&!tab.LoginFilled&&!AgentDriving(tab)&&!tab.CertificateError&&tab.LoginApi.Length>0)
      tab.LoginFilled=await core.RunAsync("window["+JsonSerializer.Serialize(tab.LoginApi)+"]?.auto("+JsonSerializer.Serialize(new{username=only[0].Username,password=only[0].Password})+")??false")=="true";
     break;
    }
    case "generated":await SaveGenerated(tab,origin,current.Host,S("username"),S("password"));break;
    case "username":if(S("username").Length is >0 and <=1024)tab.LoginUsername=(origin,S("username"),DateTime.UtcNow);break;
    case "manage":ShellOpen("passwords");break;
    case "submitted":await OfferToSave(tab,origin,S("username"),S("password"),S("current"));break;
   }
  }catch(JsonException){}catch(InvalidOperationException){}
 }
 /// Tells the page which logins this site has (usernames only), whether it's insecure, and whether auto sign-in may fill at the first touch.
 async Task OfferLogins(BrowserTab tab,CoreWebView2 core,string origin,string form,bool secure)
 {
  try{
   var entries=Vault.Read().Where(v=>v.Origin==origin).OrderBy(v=>v.Username).ToArray();
   bool auto=secure&&Prefs.AutoFillPasswords&&entries.Length==1&&form is "login" or "username"&&!tab.LoginFilled&&!AgentDriving(tab);
   await core.RunAsync("window["+JsonSerializer.Serialize(tab.LoginApi)+"]?.show("+JsonSerializer.Serialize(new{accounts=entries.Select(v=>new{id=v.Id,username=v.Username}),warn=!secure,auto})+")");
  }catch(Exception ex){if(!closing&&!tab.Closed)App.Log(new InvalidOperationException("Login detection could not complete.",ex));}
 }
 async Task<bool> FillSavedLogin(LoginEntry entry,BrowserTab tab)
 {
  if(tab.View?.CoreWebView2 is not{} core||tab.CertificateError||tab.LoginApi.Length==0||!IsLoginOrigin(core.Source,out var site)||Origin(site)!=entry.Origin)return false;
  return await core.RunAsync("window["+JsonSerializer.Serialize(tab.LoginApi)+"]?.fill("+JsonSerializer.Serialize(new{username=entry.Username,password=entry.Password})+")??false")=="true";
 }
 /// A strong password Still suggested and the user took: saved at once, so it's never lost.
 async Task SaveGenerated(BrowserTab tab,string origin,string host,string username,string password)
 {
  if(password.Length is <8 or >8192||username.Length>1024)return;
  var entries=Vault.Read();
  var entry=username.Length>0?entries.FirstOrDefault(v=>v.Origin==origin&&v.Username==username):entries.FirstOrDefault(v=>v.Id==tab.GeneratedLogin);
  if(entry==null){entry=new LoginEntry{Origin=origin,Username=username};entries.Add(entry);}
  entry.Password=password;Vault.Write(entries);tab.GeneratedLogin=entry.Id;
  if(panel=="passwords")await PublishBrowserTools("passwords");
  Toast("Strong password saved for "+host+".");
 }
 async Task OfferToSave(BrowserTab tab,string origin,string username,string password,string current)
 {
  if(!Prefs.OfferPasswordSave&&!Prefs.OfferPasswordUpdate||password.Length is <1 or >8192||username.Length>1024||Prefs.NeverSavePasswords.Contains(origin))return;
  var all=Vault.Read();var entries=all.Where(v=>v.Origin==origin).ToList();
  // A suggested password is saved already: it only needs the username it went with.
  if(entries.FirstOrDefault(v=>v.Id==tab.GeneratedLogin) is{} made&&made.Password==password){
   if(made.Username.Length==0&&username.Length>0&&!entries.Any(v=>v.Username==username)){made.Username=username;Vault.Write(all);}
   return;
  }
  // The second step of a two-step sign-in has no username field: use the one from the first step.
  if(username.Length==0&&tab.LoginUsername is var (o,u,at)&&o==origin&&DateTime.UtcNow-at<TimeSpan.FromMinutes(10))username=u;
  var existing=entries.FirstOrDefault(v=>v.Username==username)??(current.Length>0?entries.FirstOrDefault(v=>v.Password==current):null)??(username.Length==0&&entries.Count==1?entries[0]:null);
  if(existing!=null)username=existing.Username;
  if(existing?.Password==password||existing==null&&!Prefs.OfferPasswordSave||existing!=null&&!Prefs.OfferPasswordUpdate)return;
  loginOffer=new(Guid.NewGuid().ToString("N"),origin,username,password,existing?.Id,DateTime.UtcNow.AddMinutes(3));
  _=ExpireLoginOffer(loginOffer.Id);
  ShellPublish();if(panel=="passwords")await PublishBrowserTools("passwords");
 }
 async Task ExpireLoginOffer(string id)
 {
  await Task.Delay(TimeSpan.FromMinutes(3));if(closing)return;
  if(loginOffer?.Id==id){loginOffer=null;ShellPublish();if(panel=="passwords")await PublishBrowserTools("passwords");}
 }
 async Task AcceptLoginOffer(string id,string username,string password)
 {
  var offer=loginOffer;if(offer==null||offer.Id!=id||offer.Expires<DateTime.UtcNow||username.Length>1024||password.Length>8192){Toast("This login suggestion expired. Sign in again to save it.");return;}
  if(offer.ExistingId==null&&!Prefs.OfferPasswordSave||offer.ExistingId!=null&&!Prefs.OfferPasswordUpdate){loginOffer=null;return;}
  var entries=Vault.Read();var match=entries.FirstOrDefault(v=>v.Origin==offer.Origin&&v.Username==username);
  // Changing the username must not silently replace a different stored login.
  if(match!=null&&offer.ExistingId!=null&&match.Id!=offer.ExistingId){Toast("That username already has a saved login. Manage it in Passwords.");return;}
  var entry=match??entries.FirstOrDefault(v=>v.Id==offer.ExistingId)??new LoginEntry{Origin=offer.Origin};
  if(!entries.Contains(entry))entries.Add(entry);
  entry.Username=username;entry.Password=password.Length>0?password:offer.Password;Vault.Write(entries);loginOffer=null;
  await PublishBrowserTools("passwords");ShellPublish();Toast(offer.ExistingId!=null?"Password updated.":"Password saved. It stays encrypted on this computer.");
 }
 async Task NeverSaveLogin(string id)
 {
  if(loginOffer is not{} offer||offer.Id!=id)return;
  if(!Prefs.NeverSavePasswords.Contains(offer.Origin))Prefs.NeverSavePasswords.Add(offer.Origin);
  loginOffer=null;SaveLater();ShellPublish();await PublishBrowserTools("passwords");
  Toast("Still won't offer to save passwords on "+new Uri(offer.Origin).Host+". You can change that in Passwords.");
 }

 // ---- Settings → Passwords ----
 object PasswordsData()
 {
  var all=Vault.Read();var uses=all.GroupBy(v=>v.Password).ToDictionary(g=>g.Key,g=>g.Count());
  return new{
   vault=all.OrderBy(v=>Host(v.Origin)).ThenBy(v=>v.Username).Select(v=>new{id=v.Id,origin=v.Origin,username=v.Username,weak=Weak(v.Password),reused=uses[v.Password]>1}),
   offer=LoginOfferData(),passwordOptions=new{save=Prefs.OfferPasswordSave,fill=Prefs.AutoFillPasswords},never=Prefs.NeverSavePasswords};
 }
 static readonly string[] CommonPasswords=["password","123456","12345678","123456789","1234567890","qwerty","qwertyuiop","111111","123123","abc123","iloveyou","admin","welcome","letmein","monkey","dragon","football","baseball","sunshine","princess","password1","passw0rd","000000","654321"];
 /// Short, made of one or two kinds of character, one of the most common, or mostly one character.
 internal static bool Weak(string p)=>p.Length<8||p.Length<12&&new[]{p.Any(char.IsLower),p.Any(char.IsUpper),p.Any(char.IsDigit),p.Any(c=>!char.IsLetterOrDigit(c))}.Count(x=>x)<3
  ||CommonPasswords.Contains(p.ToLowerInvariant())||p.Distinct().Count()<=3;
 DateTime verifiedUntil;
#if STILL_QA
 internal static string qaAuthAnswer="deny";internal static int qaAuthAsks;internal static string qaExportPath="";
#endif
 /// Windows Hello or the PIN, at most once a minute, before a password is shown, copied, edited or exported.
 async Task<bool> VerifyUser(string why)
 {
  if(DateTime.UtcNow<verifiedUntil)return true;
#if STILL_QA
  qaAuthAsks++;var answer=qaAuthAnswer=="allow"?OsAuth.Answer.Verified:qaAuthAnswer=="none"?OsAuth.Answer.Unavailable:OsAuth.Answer.Declined;
#else
  var answer=await OsAuth.Verify(new System.Windows.Interop.WindowInteropHelper(this).Handle,why);
#endif
  if(answer==OsAuth.Answer.Unavailable)Toast("To see saved passwords, turn on Windows Hello or a PIN in Windows Settings → Accounts → Sign-in options.");
  if(answer!=OsAuth.Answer.Verified)return false;
  verifiedUntil=DateTime.UtcNow.AddMinutes(1);return true;
 }
 async Task HandlePasswordTool(string op,JsonElement data)
 {
  string S(string key)=>data.TryGetProperty(key,out var v)&&v.ValueKind==JsonValueKind.String?v.GetString()??"":"";
  switch(op){
   case "loginAccept":await AcceptLoginOffer(S("id"),S("username"),S("password"));break;
   case "loginNever":await NeverSaveLogin(S("id"));break;
   case "loginDismiss":loginOffer=null;ShellPublish();await PublishBrowserTools("passwords");break;
   case "neverRemove":Prefs.NeverSavePasswords.Remove(S("origin"));SaveLater();await PublishBrowserTools("passwords");break;
   case "passwordPermission":{
    bool enabled=data.TryGetProperty("enabled",out var allowed)&&allowed.ValueKind==JsonValueKind.True;
    switch(S("feature")){case "save":Prefs.OfferPasswordSave=Prefs.OfferPasswordUpdate=enabled;break;case "fill":Prefs.AutoFillPasswords=enabled;break;default:return;}
    if(!enabled&&S("feature")=="save")loginOffer=null;
    foreach(var tab in tabs.Where(t=>t.View?.CoreWebView2!=null&&!t.Private))await InstallLoginObserver(tab);
    SaveLater();ShellPublish();await PublishBrowserTools("passwords");break;
   }
   case "vaultReveal":case "vaultEdit":case "vaultCopy":{
    var entry=Vault.Read().FirstOrDefault(v=>v.Id==S("id"));if(entry==null)break;
    if(!await VerifyUser(op=="vaultCopy"?"Copy a saved password":op=="vaultEdit"?"Edit a saved password":"Show a saved password"))break;
    if(op=="vaultReveal")ShellSend(new{kind="vaultRevealed",id=entry.Id,password=entry.Password});
    else if(op=="vaultEdit")ShellSend(new{kind="vaultEditing",id=entry.Id,origin=entry.Origin,username=entry.Username,password=entry.Password});
    else{
#if !STILL_QA
     Clipboard.SetText(entry.Password);copiedPassword=entry.Password;_=ClearPasswordClipboard(entry.Password,++clipboardVersion); // test builds never touch the clipboard
#endif
     Toast("Password copied. Your clipboard clears in 30 seconds.");
    }
    break;
   }
   case "vaultSave":{
    if(!Uri.TryCreate(S("origin").Trim(),UriKind.Absolute,out var site)||site.Scheme is not("https" or "http")){Toast("Enter the website's full address, like https://example.com.");break;}
    if(S("password").Length is <1 or >8192||S("username").Length>1024){Toast("Enter a password.");break;}
    var entries=Vault.Read();string origin=Origin(site);
    var same=entries.FirstOrDefault(v=>v.Origin==origin&&v.Username==S("username"));
    var entry=entries.FirstOrDefault(v=>v.Id==S("id")&&S("id").Length>0);
    if(same!=null&&entry!=null&&same!=entry){Toast("That website and username already have a saved password.");break;}
    entry??=same;if(entry==null){entry=new LoginEntry();entries.Add(entry);}
    entry.Origin=origin;entry.Username=S("username");entry.Password=S("password");Vault.Write(entries);
    await PublishBrowserTools("passwords");ShellSend(new{kind="vaultSaved"});Toast("Password saved.");break;
   }
   case "vaultDelete":{var entries=Vault.Read();entries.RemoveAll(v=>v.Id==S("id"));Vault.Write(entries);await PublishBrowserTools("passwords");break;}
   case "vaultFill":{
    var entry=Vault.Read().FirstOrDefault(v=>v.Id==S("id"));var tab=active;
    if(entry==null||tab==null||!Uri.TryCreate(tab.Url,UriKind.Absolute,out var url)||Origin(url)!=entry.Origin||!SecureOrigin(url)||tab.CertificateError){Toast("Open this login's exact secure website before filling it.");break;}
    if(await FillSavedLogin(entry,tab)){CloseSheet();Toast("Login filled. Check it, then sign in.");}else Toast("There's no sign-in form on this page to fill.");break;
   }
   case "vaultExport":await ExportPasswords();break;
  }
 }
 /// Every saved password in a CSV file that Chrome, Edge, Firefox and most password managers can import.
 async Task ExportPasswords()
 {
  var entries=Vault.Read();if(entries.Count==0){Toast("There are no saved passwords to export.");return;}
  if(!await VerifyUser("Export your saved passwords"))return;
  string? file=null;
#if STILL_QA
  file=qaExportPath;
#else
  var dialog=new SaveFileDialog{Title="Export passwords",FileName="Still passwords.csv",Filter="CSV file|*.csv"};
  if(dialog.ShowDialog(this)==true)file=dialog.FileName;
#endif
  if(string.IsNullOrEmpty(file))return;
  static string Cell(string v)=>v.IndexOfAny([',','"','\r','\n'])>=0?"\""+v.Replace("\"","\"\"")+"\"":v;
  var csv=new StringBuilder("name,url,username,password,note\r\n");
  static string Text(string v)=>v.Length>0&&"=+-@\t\r".Contains(v[0])?"'"+v:v; // a spreadsheet runs a cell that starts like this, and a site can choose its username. Passwords stay exact: this file is how they move.
  foreach(var v in entries.OrderBy(v=>v.Origin))csv.Append(Cell(Text(Host(v.Origin)))).Append(',').Append(Cell(v.Origin+"/")).Append(',').Append(Cell(Text(v.Username))).Append(',').Append(Cell(v.Password)).Append(",\r\n");
  try{await File.WriteAllTextAsync(file,csv.ToString(),new UTF8Encoding(false));Toast($"Exported {entries.Count} passwords. Anyone who opens that file can read them, so delete it when you're done.");}
  catch(Exception ex) when(ex is IOException or UnauthorizedAccessException){Toast("Couldn't save the file: "+ex.Message);}
 }

 // ---- What AIs read ----
 static string Clip60(string s){s=Regex.Replace(s,@"\s+"," ").Trim();return s.Length>60?s[..59]+"…":s;}
 /// Saved logins never reach an AI: a field holding a saved username for this site reads as hidden, and any saved
 /// password for it is cut out of the text.
 static string RedactLogins(string url,string text)
 {
  if(!Uri.TryCreate(url,UriKind.Absolute,out var uri)||uri.Scheme is not("https" or "http"))return text;
  return Redact(Vault.Read().Where(v=>v.Origin==Origin(uri)),text);
 }
 static string Redact(IEnumerable<LoginEntry> logins,string text)
 {
  foreach(var v in logins){
   if(v.Password.Length>=4)text=text.Replace(v.Password,"[hidden]").Replace(Clip60(v.Password),"[hidden]"); // as saved, and as a page's line shows it
   if(v.Username.Length>0)text=text.Replace(" ="+Clip60(v.Username)," =[saved login, hidden]");
  }
  return text;
 }
 /// All an AI gets back passes here, errors too, for the logins of every site open now: a reply can be about a page that has just moved on.
 string RedactReply(string reply)
 {
  var open=Windows.SelectMany(w=>w.tabs).Select(t=>Uri.TryCreate(t.Url,UriKind.Absolute,out var u)&&u.Scheme is "https" or "http"?Origin(u):"").ToHashSet();
  var logins=Vault.Read().Where(v=>open.Contains(v.Origin)).ToList();
  if(logins.Count==0)return reply;
  try{
   if(JsonNode.Parse(reply) is not{}root)return Redact(logins,reply);
   Walk(root);
   return root.ToJsonString(ReplyJson);
  }catch(JsonException){return Redact(logins,reply);}
  void Walk(JsonNode? node)
  {
   if(node is JsonObject o)foreach(var k in o.Select(p=>p.Key).ToList()){
    if(k=="image")continue;
    if(o[k] is JsonValue v&&v.TryGetValue<string>(out var s))o[k]=Redact(logins,s);else Walk(o[k]);
   }
   else if(node is JsonArray a)for(int i=0;i<a.Count;i++){
    if(a[i] is JsonValue v&&v.TryGetValue<string>(out var s))a[i]=Redact(logins,s);else Walk(a[i]);
   }
  }
 }
 /// Fingerprints of this site's saved usernames and passwords, so a screenshot can mask fields that show them.
 static int[] LoginPrints(string url)
 {
  if(!Uri.TryCreate(url,UriKind.Absolute,out var uri)||uri.Scheme is not("https" or "http"))return [];
  static int Print(string s){int h=0;unchecked{foreach(char c in s)h=h*31+c;}return h;}
  return Vault.Read().Where(v=>v.Origin==Origin(uri)).SelectMany(v=>new[]{v.Username,v.Password}).Where(s=>s.Length>0).Select(Print).ToArray();
 }
}
