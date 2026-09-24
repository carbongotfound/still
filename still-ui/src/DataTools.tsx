import { useState } from "react"
import { UsersRound, Plus, ExternalLink, Bookmark, KeyRound, Import, Download, Check, Trash2, RotateCcw, FolderOpen, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import type { ToolData } from "./BrowserTools"
type Send=(op:string,payload?:Record<string,unknown>)=>void
export function DataTools({pane,data,send}:{pane:string;data:ToolData;send:Send}){
 const [name,setName]=useState("")
 const [replace,setReplace]=useState(false)
 if(pane==="profiles")return <>
  <div className="tool-intro"><UsersRound/><p>Each profile has its own tabs, cookies, history, extensions, and encrypted logins. Profiles open in separate windows.</p></div>
  <form className="tool-toolbar" onSubmit={e=>{e.preventDefault();if(name.trim()){send("profileCreate",{name:name.trim()});setName("")}}}><Input aria-label="New profile name" placeholder="Work, personal, study…" maxLength={40} value={name} onChange={e=>setName(e.target.value)} required/><Button type="submit" variant="outline"><Plus/>Create profile</Button></form>
  <div className="profile-list">{data.profiles?.map(p=><div className="tool-row" key={p.id}><span className="profile-avatar">{p.name.slice(0,1).toUpperCase()}</span><div className="tool-copy"><strong>{p.name}</strong><small>{[p.current && "Current", p.launch && "Launch profile", p.permanent && "Protected Default"].filter(Boolean).join(" · ") || "Separate browsing data"}</small></div><Button variant="ghost" size="sm" disabled={p.current} onClick={()=>send("profileOpen",{id:p.id})}>{p.current?<><Check/>Active</>:<>Open<ExternalLink/></>}</Button>{!p.launch&&<Button variant="ghost" size="sm" aria-label={"Launch with "+p.name} onClick={()=>send("profileLaunch",{id:p.id})}>Use at launch</Button>}<Button variant="ghost" size="icon-sm" disabled={p.running} aria-label={p.permanent?"Reset Default profile":"Delete profile "+p.name} title={p.running?"Close this profile before removing its data":p.permanent?"Reset browsing data with confirmation":"Delete with confirmation"} onClick={()=>send(p.permanent?"profileResetDefault":"profileDelete",{id:p.id})}>{p.permanent?<RotateCcw/>:<Trash2/>}</Button></div>)}</div><p className="tool-caption">Default stays available. Close a profile before deleting or resetting its data. A Windows confirmation asks you to type its name.</p>
 </>
 if(pane!=="import")return null
 return <>
  <div className="tool-intro"><Import/><p>Bring your browsing with you. Review every import before saving.</p></div>
  <ExternalImport data={data} send={send}/>
  <h3 className="import-section-title">Import a file into this profile</h3>
  <div className="import-actions">
   <Button variant="outline" onClick={()=>send("importChoose",{kind:"bookmarks"})}><Bookmark/><span>Bookmarks<small>HTML export or Chromium bookmarks JSON</small></span><Plus/></Button>
   <Button variant="outline" onClick={()=>send("importChoose",{kind:"passwords"})}><KeyRound/><span>Passwords<small>Opera, Chrome, Edge, Firefox, or Bitwarden CSV</small></span><Plus/></Button>
   <Button variant="outline" onClick={()=>send("importChoose",{kind:"session"})}><Import/><span>Still browsing data<small>Tabs, bookmarks, and history from a JSON export</small></span><Plus/></Button>
  </div>
  {data.preview&&<div className="extension-review"><strong>{data.preview.file}</strong><p>{data.preview.logins} logins · {data.preview.bookmarks} bookmarks · {data.preview.history} history entries · {data.preview.tabs} tabs</p>{data.preview.skipped>0&&<p>{data.preview.skipped} unsupported or duplicate entries will be skipped.</p>}{data.preview.kind==="passwords"&&<div className="setting-row"><div><strong>Replace matching logins</strong><p>Otherwise, your existing passwords are kept.</p></div><Switch aria-label="Replace matching logins" checked={replace} onCheckedChange={setReplace}/></div>}<div className="tool-toolbar"><Button variant="ghost" onClick={()=>send("importCancel")}>Cancel</Button><Button onClick={()=>send("importConfirm",{id:data.preview!.id,replace})}>Import into this profile</Button></div></div>}
  <p className="tool-caption">Password CSV exports contain readable passwords. Still encrypts imported logins immediately; the original export remains where you saved it. </p>
  <Button variant="ghost" className="settings-link" onClick={()=>send("exportData")}><Download/>Export Still browsing data</Button>
 </>
}

function ExternalImport({data,send}:{data:ToolData;send:Send}){
 const external=data.external
 const preview=external?.preview
 return <section className="external-import" aria-label="Import from another browser">
  <div className="tool-copy"><strong>From another browser</strong><p>Opera GX, Opera, Chrome, Edge, Brave, or Vivaldi. Brings bookmarks, history, saved passwords, and signed-in sessions into {external?.profile??"this profile"}. The source browser can stay open.</p></div>
  <div className="external-sources">{external?.sources?.map(source=><Button key={source.id} variant="outline" size="sm" disabled={external.busy} onClick={()=>send("externalReview",{id:source.id})}><Import/>{source.name}</Button>)}<Button variant="outline" size="sm" disabled={external?.busy} onClick={()=>send("externalChoose")}><FolderOpen/>Choose profile folder</Button></div>
  {external?.busy&&<p role="status" className="import-progress"><Loader2 className="animate-spin"/>Reading your browser data…</p>}
  {external?.error&&<p role="alert" className="import-error">{external.error}</p>}
  {preview&&<ExternalReview key={preview.id} preview={preview} busy={!!external?.busy} send={send}/>}
  {external?.done&&!preview&&<div className="extension-review" role="status"><strong><Check/> {external.done}</strong><p>Reload open websites to use imported sign-ins. The source browser was not changed.</p></div>}
  <p className="tool-caption">Passwords are decrypted with your Windows account and immediately re-encrypted in Still's vault. Nothing leaves this PC. Extensions and browser settings are not transferred.</p>
 </section>
}
function ExternalReview({preview,busy,send}:{preview:NonNullable<NonNullable<ToolData["external"]>["preview"]>;busy:boolean;send:Send}){
 const [bookmarks,setBookmarks]=useState(preview.bookmarks>0)
 const [history,setHistory]=useState(preview.history>0)
 const [passwords,setPasswords]=useState(preview.passwords>0)
 const [cookies,setCookies]=useState(preview.cookies>0)
 const [autofill,setAutofill]=useState(true)
 const rows:[string,string,number,boolean,(v:boolean)=>void][]=[
  ["Bookmarks","including Speed Dial; folders are flattened",preview.bookmarks,bookmarks,setBookmarks],
  ["History","recent pages, used for address suggestions",preview.history,history,setHistory],
  ["Passwords","saved logins, stored encrypted",preview.passwords,passwords,setPasswords],
  ["Cookies & sign-ins","keeps you signed in to your sites",preview.cookies,cookies,setCookies]]
 return <form className="extension-review" onSubmit={e=>{e.preventDefault();send("externalConfirm",{id:preview.id,bookmarks,history,passwords,cookies,autofill})}}>
  <strong>Review import from {preview.name}</strong>
  {rows.map(([label,note,count,value,set])=><div className="setting-row" key={label}><div><strong>{label}</strong><p>{count.toLocaleString()} · {note}</p></div><Switch aria-label={"Import "+label} checked={value} onCheckedChange={set} disabled={busy||!count}/></div>)}
  {passwords&&<div className="setting-row"><div><strong>Fill passwords automatically</strong><p>Sign-in forms fill themselves on matching sites, and new logins are offered for saving.</p></div><Switch aria-label="Fill imported passwords automatically" checked={autofill} onCheckedChange={setAutofill} disabled={busy}/></div>}
  {preview.cookiesLocked&&<div className="import-locked"><p><strong>Sign-ins are locked.</strong> {preview.name} keeps its cookies locked while it's open. Close it to bring your signed-in sessions (Google, YouTube, Discord…) with you.</p><Button type="button" variant="outline" size="sm" disabled={busy} onClick={()=>send("externalCloseSource")}>Close {preview.name.split(" · ")[0]} and include sign-ins</Button></div>}
  {preview.skipped>0&&<p>{preview.skipped} duplicate or unsupported entries skipped.</p>}
  {preview.warnings.map(w=><p key={w} className="tool-caption">{w}</p>)}
  <div className="tool-toolbar"><Button type="button" variant="ghost" disabled={busy} onClick={()=>send("externalCancel")}>Cancel</Button><Button type="submit" disabled={busy||(!bookmarks&&!history&&!passwords&&!cookies)}>Import</Button></div>
 </form>
}
