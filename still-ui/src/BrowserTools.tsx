import { useEffect, useState } from "react"
import { KeyRound, Plus, Copy, ArrowDownToLine, Trash2, Puzzle, FolderOpen, ExternalLink, RotateCw, ShieldCheck, Cookie, Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog"
import { DataTools } from "./DataTools"
import { LoginControls } from "./LoginControls"
type Send = (op:string,payload?:Record<string,unknown>)=>void
export type ToolData={external?:{busy:boolean;error:string;done:string;profile:string;sources:{id:string;name:string}[];preview?:{id:string;name:string;bookmarks:number;history:number;passwords:number;cookies:number;cookiesLocked:boolean;skipped:number;warnings:string[]}};error?:string;vault?:{id:string;origin:string;username:string}[];cookies?:{id:string;name:string;domain:string;path:string;secure:boolean;httpOnly:boolean;session:boolean}[];extensions?:{id:string;name:string;enabled:boolean;hasPage:boolean;}[];candidate?:{name:string;permissions:string[]};permissions?:{origin:string;kind:string;state:string}[];engine?:string;isPrivate?:boolean;profiles?:{id:string;name:string;current:boolean;launch:boolean;permanent:boolean;running:boolean}[];preview?:{id:string;file:string;kind:string;logins:number;bookmarks:number;history:number;tabs:number;skipped:number};offer?:{id:string;origin:string;username:string;update:boolean};passwordOptions?:{save:boolean;fill:boolean;update:boolean};downloading?:boolean}
export function BrowserTools({pane,data,send,url,tracking,memory,autofill}:{pane:string;data:ToolData;send:Send;url:string;tracking:string;memory:boolean;autofill:boolean}){
 const [filter,setFilter]=useState("")
 const [adding,setAdding]=useState(false)
 const [origin,setOrigin]=useState("")
 const [username,setUsername]=useState("")
 const [password,setPassword]=useState("")
 const [visible,setVisible]=useState(false)
 const [confirmation,setConfirmation]=useState<{title:string;body:string;run:()=>void}|null>(null)
 useEffect(()=>{
  const listener=(e:MessageEvent)=>{if(e.data.kind==="vaultGenerated")setPassword(e.data.password);if(e.data.kind==="vaultSaved"){setAdding(false);setPassword("");setUsername("");setVisible(false)}}
  window.chrome?.webview?.addEventListener("message",listener)
  return()=>window.chrome?.webview?.removeEventListener("message",listener)
 },[])
 const pref=(key:string,value:string)=>send("preference",{key,value})
 const refresh=()=>send("refreshTools",{name:pane})
 const currentOrigin=(()=>{try{return new URL(url).origin}catch{return ""}})()
 const ask=(title:string,body:string,run:()=>void)=>setConfirmation({title,body,run})
 return <div className="browser-tools">
  {data.error&&<p className="tool-error" role="alert">{data.error}</p>}
  {(pane==="profiles"||pane==="import")&&<DataTools pane={pane} data={data} send={send}/>}
  {pane==="passwords"&&<>
   <div className="tool-intro"><KeyRound/><p>Encrypted by Windows for your account. Logins fill only on the exact website you saved.</p></div>
   <LoginControls data={data} send={send} ask={ask}/>
   {!adding?<div className="tool-toolbar"><Input aria-label="Search saved logins" placeholder="Find a login" value={filter} onChange={e=>setFilter(e.target.value)}/><Button variant="outline" onClick={()=>{setOrigin(currentOrigin);setAdding(true)}}><Plus/>Add login</Button></div>:<form className="vault-form" onSubmit={e=>{e.preventDefault();send("vaultSave",{origin,username,password})}}>
    <label htmlFor="login-site">Website</label><Input id="login-site" type="url" required placeholder="https://example.com" value={origin} onChange={e=>setOrigin(e.target.value)}/>
    <label htmlFor="login-user">Username or email</label><Input id="login-user" autoComplete="off" value={username} onChange={e=>setUsername(e.target.value)}/>
    <label htmlFor="login-password">Password</label><div className="password-input"><Input id="login-password" type={visible?"text":"password"} autoComplete="new-password" required value={password} onChange={e=>setPassword(e.target.value)}/><Button type="button" variant="ghost" size="icon" aria-label={visible?"Hide password":"Show password"} onClick={()=>setVisible(!visible)}>{visible?<EyeOff/>:<Eye/>}</Button></div>
    <div className="tool-toolbar"><Button type="button" variant="ghost" onClick={()=>send("vaultGenerate")}><RotateCw/>Generate strong password</Button><span/><Button type="button" variant="ghost" onClick={()=>{setAdding(false);setPassword("")}}>Cancel</Button><Button type="submit">Save login</Button></div>
   </form>}
   {!adding&&<ScrollArea className="tools-list">{data.vault?.filter(v=>(v.origin+v.username).toLowerCase().includes(filter.toLowerCase())).map(v=><div className="tool-row" key={v.id}><KeyRound/><div className="tool-copy"><strong>{new URL(v.origin).host}</strong><small>{v.username||"No username"}</small></div><Button variant="ghost" size="icon-sm" aria-label={"Fill login for "+v.username} disabled={currentOrigin!==v.origin} onClick={()=>send("vaultFill",{id:v.id})}><ArrowDownToLine/></Button><Button variant="ghost" size="icon-sm" aria-label={"Copy password for "+v.username} onClick={()=>send("vaultCopy",{id:v.id})}><Copy/></Button><Button variant="ghost" size="icon-sm" aria-label={"Delete login for "+v.username} onClick={()=>ask("Delete this login?",v.username+" at "+v.origin,()=>send("vaultDelete",{id:v.id}))}><Trash2/></Button></div>)}{data.vault?.length===0&&<p className="empty-state">Your saved logins will appear here.</p>}</ScrollArea>}
  </>}
  {pane==="extensions"&&<>
   <div className="tool-intro"><Puzzle/><p>Open any extension in the Chrome Web Store and press <strong>Add to Still</strong> next to the address bar. You review its permissions before it installs.</p></div>
   <div className="tool-toolbar"><Button disabled={data.downloading} onClick={()=>send("openStore")}>{data.downloading?"Downloading…":<><ExternalLink/>Chrome Web Store</>}</Button><Button variant="ghost" onClick={()=>send("extensionChoose")}><FolderOpen/>Load folder</Button><Button variant="ghost" size="icon-sm" aria-label="Refresh extensions" onClick={refresh}><RotateCw/></Button></div>
   {data.candidate&&<div className="extension-review"><strong>Add {data.candidate.name}?</strong><p>Declared permissions and website access:</p><ScrollArea className="permission-list">{data.candidate.permissions.length?data.candidate.permissions.map(p=><code key={p}>{p}</code>):<span>No permissions requested.</span>}</ScrollArea><div className="tool-toolbar"><Button variant="ghost" onClick={()=>send("extensionCancel")}>Cancel</Button><Button onClick={()=>send("extensionInstall")}>Add extension</Button></div></div>}
   <ScrollArea className="tools-list">{data.extensions?.map(e=><div className="tool-row" key={e.id}><Puzzle/><div className="tool-copy"><strong>{e.name}</strong><small>{e.enabled?"Enabled":"Disabled"}</small></div>{e.hasPage&&<Button variant="ghost" size="icon-sm" aria-label={"Open "+e.name+" page"} onClick={()=>send("extensionPage",{id:e.id})}><ExternalLink/></Button>}<Switch aria-label={"Enable "+e.name} checked={e.enabled} onCheckedChange={()=>send("extensionToggle",{id:e.id})}/><Button variant="ghost" size="icon-sm" aria-label={"Remove "+e.name} onClick={()=>ask("Remove this extension?",e.name+" will be removed from your regular profile.",()=>send("extensionRemove",{id:e.id}))}><Trash2/></Button></div>)}{data.extensions?.length===0&&<p className="empty-state">No extensions installed.</p>}</ScrollArea>
  </>}
  {pane==="cookies"&&<>
   <div className="tool-intro"><Cookie/><p>{data.isPrivate?"Cookies in your private session.":"Cookies saved by websites in your regular profile."} Cookie values stay inside the browser engine.</p></div>
   <div className="tool-toolbar"><Input aria-label="Search cookies" placeholder="Find a website or cookie" value={filter} onChange={e=>setFilter(e.target.value)}/><Button variant="ghost" size="icon-sm" aria-label="Refresh cookies" onClick={refresh}><RotateCw/></Button></div>
   <ScrollArea className="tools-list">{data.cookies?.filter(c=>(c.domain+c.name).toLowerCase().includes(filter.toLowerCase())).map(c=><div className="tool-row" key={c.id}><Cookie/><div className="tool-copy"><strong>{c.domain}</strong><small>{c.name} · {c.httpOnly?"HTTP only · ":""}{c.secure?"Secure":"HTTP"}{c.session?" · Session":""}</small></div><Button variant="ghost" size="icon-sm" aria-label={"Delete cookie "+c.name} onClick={()=>ask("Delete this cookie?",`${c.name} from ${c.domain} will be removed. You may be signed out of that site.`,()=>send("cookieDelete",{id:c.id}))}><Trash2/></Button></div>)}{data.cookies?.length===0&&<p className="empty-state">No cookies in this profile.</p>}</ScrollArea>
  </>}
  {pane==="security"&&<>
   <div className="tool-intro"><ShieldCheck/><p>Invalid certificates are blocked. Microsoft reputation checks are requested; Windows policy can override them.</p></div>
   <div className="setting-row"><div><strong>Tracking prevention</strong><p>Strict protection can affect some websites.</p></div><Select value={tracking} onValueChange={v=>pref("tracking",v)}><SelectTrigger className="w-32"><SelectValue/></SelectTrigger><SelectContent>{["Basic","Balanced","Strict"].map(v=><SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent></Select></div>
   <Separator/><div className="setting-row"><div><strong>Reduce background memory use</strong><p>Keep page state while asking inactive tabs to use less memory.</p></div><Switch aria-label="Memory saver" checked={memory} onCheckedChange={v=>pref("memory",String(v))}/></div>
   <Separator/><div className="setting-row"><div><strong>Form autofill</strong><p>Names, addresses, and other non-password fields.</p></div><Switch aria-label="Form autofill" checked={autofill} onCheckedChange={v=>pref("autofill",String(v))}/></div>
   <Separator/><div className="tool-section-label">Website permissions</div><ScrollArea className="permissions-scroll">{data.permissions?.map(p=><div className="tool-row" key={p.origin+p.kind}><div className="tool-copy"><strong>{p.origin}</strong><small>{p.kind} · {p.state}</small></div><Button variant="outline" size="sm" onClick={()=>send("permissionReset",{origin:p.origin,kind:p.kind})}>Reset</Button></div>)}{data.permissions?.length===0&&<p className="tool-caption">No saved permission decisions.</p>}</ScrollArea><p className="tool-caption">WebView2 {data.engine}</p>
  </>}
  <AlertDialog open={!!confirmation} onOpenChange={v=>{if(!v)setConfirmation(null)}}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{confirmation?.title}</AlertDialogTitle><AlertDialogDescription>{confirmation?.body}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={()=>{confirmation?.run();setConfirmation(null)}}>Confirm</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
 </div>
}
