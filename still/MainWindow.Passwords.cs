using System.IO;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
namespace Still;
public partial class MainWindow
{
 sealed record LoginOffer(string Id,string Origin,string Username,string Password,string? ExistingId,DateTime Expires);
 LoginOffer? loginOffer;
 object? LoginOfferData()=>loginOffer is{} v&&v.Expires>DateTime.UtcNow?new{id=v.Id,origin=v.Origin,username=v.Username,update=v.ExistingId!=null}:null;
 static bool IsLoginOrigin(string source,out Uri uri)=>Uri.TryCreate(source,UriKind.Absolute,out uri!)&&(uri.Scheme=="https"||(uri.Scheme=="http"&&uri.IsLoopback));
 async Task InstallLoginObserver(BrowserTab tab)
 {
  if(tab.Private||tab.View?.CoreWebView2 is not{} core)return;
  if(tab.LoginScriptId!=null)core.RemoveScriptToExecuteOnDocumentCreated(tab.LoginScriptId);
  tab.LoginScriptId=null;
  if(!Prefs.OfferPasswordSave&&!Prefs.OfferPasswordUpdate&&!Prefs.AutoFillPasswords){await core.ExecuteScriptAsync("window.__stillLoginCleanup?.()");tab.LoginToken="";return;}
  tab.LoginToken=Guid.NewGuid().ToString("N");
  string js=(await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory,"Assets","LoginObserver.js"))).Replace("__STILL_LOGIN_CONFIG__",JsonSerializer.Serialize(new{token=tab.LoginToken,capture=Prefs.OfferPasswordSave||Prefs.OfferPasswordUpdate}));
  tab.LoginScriptId=await core.AddScriptToExecuteOnDocumentCreatedAsync(js);
  await core.ExecuteScriptAsync(js);
 }
 async Task ReceiveLogin(BrowserTab tab,CoreWebView2WebMessageReceivedEventArgs e)
 {
  if(tab.Private||tab!=active||tab.View?.CoreWebView2 is not{} core||tab.CertificateError||!IsLoginOrigin(e.Source,out var source)||!IsLoginOrigin(core.Source,out var current)||source.GetLeftPart(UriPartial.Authority)!=current.GetLeftPart(UriPartial.Authority))return;
  try{
   string json=e.WebMessageAsJson;if(json.Length>40000)return;
   using var message=JsonDocument.Parse(json);var m=message.RootElement;
   if(!m.TryGetProperty("kind",out var kind)||kind.GetString()!="still-login"||m.GetProperty("token").GetString()!=tab.LoginToken||m.GetProperty("origin").GetString()!=current.GetLeftPart(UriPartial.Authority))return;
   if(m.GetProperty("action").GetString()=="detected"){await InspectLogin(tab);return;}
   if(m.GetProperty("action").GetString()!="submitted"||(!Prefs.OfferPasswordSave&&!Prefs.OfferPasswordUpdate))return;
   string origin=current.GetLeftPart(UriPartial.Authority),username=m.GetProperty("username").GetString()??"",password=m.GetProperty("password").GetString()??"";
   if(password.Length is <1 or >8192||username.Length>1024)return;
   var entries=Vault.Read().Where(v=>v.Origin==origin).ToArray();
   if(username.Length==0&&entries.Length==1)username=entries[0].Username;
   var existing=entries.FirstOrDefault(v=>v.Username==username);
   if(existing?.Password==password||existing==null&&!Prefs.OfferPasswordSave||existing!=null&&!Prefs.OfferPasswordUpdate)return;
   loginOffer=new(Guid.NewGuid().ToString("N"),origin,username,password,existing?.Id,DateTime.UtcNow.AddMinutes(3));
   _=ExpireLoginOffer(loginOffer.Id);
   ShellPublish();if(panel=="passwords")await PublishBrowserTools("passwords");
  }catch(JsonException){}catch(KeyNotFoundException){}catch(InvalidOperationException){}
 }
 async Task ExpireLoginOffer(string id)
 {
  await Task.Delay(TimeSpan.FromMinutes(3));if(closing)return;
  if(loginOffer?.Id==id){loginOffer=null;ShellPublish();if(panel=="passwords")await PublishBrowserTools("passwords");}
 }
 async Task InspectLogin(BrowserTab tab)
 {
  if(closing||tab.Private||tab!=active||tab.Loading||tab.CertificateError||tab.View?.CoreWebView2 is not{} core||!IsLoginOrigin(core.Source,out var site))return;
  try{
   tab.LoginDetected=await core.ExecuteScriptAsync("[...document.querySelectorAll('input[type=password]')].some(e=>e.getClientRects().length&&!e.disabled)")=="true";
   ShellPublish();
   if(!tab.LoginDetected||!Prefs.AutoFillPasswords||tab.LoginFilled)return;
   var entries=Vault.Read().Where(v=>v.Origin==site.GetLeftPart(UriPartial.Authority)).ToArray();
   if(entries.Length==1)tab.LoginFilled=await FillSavedLogin(entries[0],tab,true);
  }catch(Exception ex){if(!closing&&!tab.Closed)App.Log(new InvalidOperationException("Login detection could not complete.",ex));}
 }
 async Task<bool> FillSavedLogin(LoginEntry entry,BrowserTab tab,bool onlyEmpty=false)
 {
  if(tab.View?.CoreWebView2 is not{} core||tab.CertificateError||!IsLoginOrigin(core.Source,out var site)||site.GetLeftPart(UriPartial.Authority)!=entry.Origin)return false;
  string payload=JsonSerializer.Serialize(new{origin=entry.Origin,username=entry.Username,password=entry.Password,onlyEmpty});
  return await core.ExecuteScriptAsync("((v)=>{if(location.origin!==v.origin)return false;const p=[...document.querySelectorAll('input[type=password]')].find(e=>e.getClientRects().length&&!e.disabled&&!e.readOnly&&e.autocomplete!=='new-password');if(!p||(v.onlyEmpty&&p.value))return false;if(p.form&&new URL(p.form.action||location.href,location.href).origin!==v.origin)return false;const root=p.form||document;const inputs=[...root.querySelectorAll('input')].filter(e=>e.getClientRects().length&&!e.disabled&&!e.readOnly);const u=inputs.find(e=>e!==p&&['email','text'].includes(e.type)&&(['username','email'].includes(e.autocomplete)||/user|email|login/i.test(e.name+' '+e.id)))||inputs.find(e=>e!==p&&['email','text'].includes(e.type));if(v.onlyEmpty&&u?.value&&u.value!==v.username)return false;function set(e,value){if(!e)return;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}set(u,v.username);set(p,v.password);return true})("+payload+")")=="true";
 }
 async Task AcceptLoginOffer(string id,string username)
 {
  var offer=loginOffer;if(offer==null||offer.Id!=id||offer.Expires<DateTime.UtcNow||username.Length>1024){Toast("This login suggestion expired. Sign in again to save it.");return;}
  if(offer.ExistingId==null&&!Prefs.OfferPasswordSave||offer.ExistingId!=null&&!Prefs.OfferPasswordUpdate){loginOffer=null;return;}
  var entries=Vault.Read();var match=entries.FirstOrDefault(v=>v.Origin==offer.Origin&&v.Username==username);
  // Changing the username must not silently replace a different stored login.
  if(match!=null&&match.Id!=offer.ExistingId){Toast("That username already has a saved login. Manage it in Passwords.");return;}
  var entry=match??new LoginEntry{Origin=offer.Origin,Username=username};
  if(match==null)entries.Add(entry);entry.Password=offer.Password;Vault.Write(entries);loginOffer=null;
  await PublishBrowserTools("passwords");ShellPublish();Toast("Login saved. It stays encrypted in this profile.");
 }
}
