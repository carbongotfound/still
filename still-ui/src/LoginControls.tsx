import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import type { ToolData } from "./BrowserTools"
type Send=(op:string,payload?:Record<string,unknown>)=>void
type Ask=(title:string,body:string,run:()=>void)=>void
export function LoginControls({data,send,ask}:{data:ToolData;send:Send;ask:Ask}){
 const [expanded,setExpanded]=useState(false)
 return <>
  {data.offer&&<LoginReview key={data.offer.id} offer={data.offer} send={send}/>}
  <Button variant="ghost" className="settings-link" onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>Login detection & permissions<span>{expanded?"−":"+"}</span></Button>
  {expanded&&<div className="login-permissions">{([
   ["save","Offer to save logins","Detect submitted passwords on secure websites and show a save suggestion. Nothing is stored until you approve it."],
   ["fill","Automatically fill saved logins","Fill a single matching login on its exact secure website. Existing typed values and cross-site forms are left alone."],
   ["update","Offer to update passwords","Detect changes to a saved login and ask before replacing its password. A submitted password does not prove a successful sign-in."],
  ] as const).map(([feature,title,body])=><div className="setting-row" key={feature}><div><strong>{title}</strong><p>{body}</p></div><Switch aria-label={title} checked={!!data.passwordOptions?.[feature]} onCheckedChange={enabled=>{if(enabled)ask("Allow "+title.toLowerCase()+"?",body+" This applies to regular tabs in this profile. You can turn it off here.",()=>send("passwordPermission",{feature,enabled:true}));else send("passwordPermission",{feature,enabled:false})}}/></div>)}</div>}
 </>
}
function LoginReview({offer,send}:{offer:NonNullable<ToolData["offer"]>;send:Send}){
 const [username,setUsername]=useState(offer.username)
 return <div className="extension-review login-review"><strong>{offer.update?"Update this saved password?":"Save this login?"}</strong><p>{offer.origin}</p><Input aria-label="Username for detected login" value={username} maxLength={1024} onChange={e=>setUsername(e.target.value)}/><p>The password stays hidden. Confirm only after checking that your sign-in worked.</p><div className="tool-toolbar"><Button variant="ghost" onClick={()=>send("loginDismiss")}>Not now</Button><Button onClick={()=>send("loginAccept",{id:offer.id,username})}>{offer.update?"Update password":"Save login"}</Button></div></div>
}
