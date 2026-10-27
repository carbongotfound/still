import { useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { ArrowRight, ArrowLeft, Bot, Check, Copy, Download, Globe2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AiPicker, type AiState } from "./AiSidebar"
import { Buddy } from "./Buddy"

// First run: what Still is for, bring your browser over, then connect the AI you already use.
export function Welcome({ isDefault, agents, mcpCommand, ai, noAi, send, onImport }: { isDefault?: boolean; agents: boolean; mcpCommand?: string; ai?: AiState; noAi?: boolean; send: (op: string, data?: Record<string, unknown>) => void; onImport: () => void }) {
 const [step, setStep] = useState(0)
 const [copied, setCopied] = useState("")
 const finish = () => send("welcomeDone")
 const copy = (label: string, text: string) => { send("copyText", { text }); setCopied(label) }
 return <div className="welcome" role="dialog" aria-modal="true" aria-label="Welcome to Still">
  <div className="welcome-card">
   <div className="welcome-dots">{[0, 1, 2].map(i => <i key={i} className={cn(i === step && "is-on")} />)}</div>
   <AnimatePresence mode="wait" initial={false}>
    <motion.div key={step} className="welcome-step" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.22, ease: [0.3, 0.7, 0.2, 1] }}>
     {step === 0 && <>
      <Buddy size={56} className="welcome-buddy" />
      <h1>Give your AI a browser</h1>
      <p>Hand it the boring parts of the web: comparing prices, planning trips, filling in forms. Your AI does them in its own tabs next to yours while you keep browsing. It uses the AI you already have, so there's nothing new to pay for.</p>
      <div className="welcome-actions"><Button variant="ghost" onClick={finish}>Skip setup</Button><Button autoFocus onClick={() => setStep(1)}>Get started<ArrowRight /></Button></div>
     </>}
     {step === 1 && <>
      <h1>Bring your stuff over</h1>
      <p>Import bookmarks, history, passwords and sign-ins from Chrome, Edge, Brave or Opera GX. Nothing leaves this PC.</p>
      <div className="welcome-options">
       <button className="welcome-option" onClick={() => { finish(); onImport() }}><Download /><span><strong>Import from another browser</strong><small>Pick a browser and review before anything is copied</small></span><ArrowRight /></button>
       <button className="welcome-option" disabled={isDefault} onClick={() => send("defaultBrowser")}><Globe2 /><span><strong>{isDefault ? "Still is your default browser" : "Make Still my default browser"}</strong><small>{isDefault ? "Links from other apps open here" : "Windows asks you to confirm"}</small></span>{isDefault ? <Check /> : <ArrowRight />}</button>
      </div>
      <div className="welcome-actions"><Button variant="ghost" onClick={() => setStep(0)}><ArrowLeft />Back</Button><Button autoFocus onClick={() => { setStep(2); send("aiCheck") }}>Continue<ArrowRight /></Button></div>
     </>}
     {step === 2 && <>
      <h1>{noAi ? "Connect your AI" : "Pick your AI"}</h1>
      <p>{noAi ? "Let AI apps on this computer use Still." : "Claude, Codex or Grok, signed in to your own account. You'll find it under Ask AI in the toolbar."} Private tabs, passwords and cookies stay off-limits.</p>
      {!noAi && ai && <AiPicker ai={ai} onPick={id => { send("aiHarness", { harness: id }); finish(); if (!ai.open) send("aiToggle") }} />}
      <details className="welcome-dev" open={noAi}>
       <summary>For developers: Claude Code, Cursor and other MCP apps</summary>
       <div className="welcome-options">
        <button className="welcome-option" disabled={agents} onClick={() => send("preference", { key: "agents", value: "true" })}><Bot /><span><strong>{agents ? "AI apps can use Still" : "Let AI apps use Still"}</strong><small>Each app asks you before it starts</small></span>{agents ? <Check /> : <ArrowRight />}</button>
       </div>
       {agents && mcpCommand && <div className="welcome-ai-picks">
        <Button variant="outline" size="sm" onClick={() => copy("claude", `claude mcp add still -- "${mcpCommand}" --mcp`)}>{copied === "claude" ? <Check /> : <Copy />}Claude Code command</Button>
        <Button variant="outline" size="sm" onClick={() => copy("json", JSON.stringify({ mcpServers: { still: { command: mcpCommand, args: ["--mcp"] } } }, null, 2))}>{copied === "json" ? <Check /> : <Copy />}MCP config</Button>
       </div>}
      </details>
      <div className="welcome-actions"><Button variant="ghost" onClick={() => setStep(1)}><ArrowLeft />Back</Button><Button autoFocus onClick={finish}>{ai?.harness || noAi ? "Start browsing" : "Skip for now"}<ArrowRight /></Button></div>
     </>}
    </motion.div>
   </AnimatePresence>
  </div>
 </div>
}
