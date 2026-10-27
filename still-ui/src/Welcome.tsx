import { useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { ArrowRight, ArrowLeft, Bot, Check, Copy, Download, Globe2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const AIS = [{ id: "claude", name: "Claude" }, { id: "codex", name: "Codex" }, { id: "grok", name: "Grok" }]

// First run: what Still is for, bring your browser over, then connect the AI you already use.
export function Welcome({ isDefault, agents, mcpCommand, aiHarness, noAi, send, onImport }: { isDefault?: boolean; agents: boolean; mcpCommand?: string; aiHarness?: string; noAi?: boolean; send: (op: string, data?: Record<string, unknown>) => void; onImport: () => void }) {
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
      <div className="still-mark"><i /><i /></div>
      <h1>Give your AI a browser</h1>
      <p>Still is the browser you share with your AI. Claude, Codex, Grok or any MCP app can research, fill in forms and get things done in tabs next to yours, while you keep browsing. Use the AI you already have: no credits, no extra subscription.</p>
      <div className="welcome-actions"><Button variant="ghost" onClick={finish}>Skip setup</Button><Button autoFocus onClick={() => setStep(1)}>Get started<ArrowRight /></Button></div>
     </>}
     {step === 1 && <>
      <h1>Bring your stuff over</h1>
      <p>Import bookmarks, history, passwords and sign-ins from Chrome, Edge, Brave or Opera GX. Nothing leaves this PC.</p>
      <div className="welcome-options">
       <button className="welcome-option" onClick={() => { finish(); onImport() }}><Download /><span><strong>Import from another browser</strong><small>Pick a browser and review before anything is copied</small></span><ArrowRight /></button>
       <button className="welcome-option" disabled={isDefault} onClick={() => send("defaultBrowser")}><Globe2 /><span><strong>{isDefault ? "Still is your default browser" : "Make Still my default browser"}</strong><small>{isDefault ? "Links from other apps open here" : "Windows asks you to confirm"}</small></span>{isDefault ? <Check /> : <ArrowRight />}</button>
      </div>
      <div className="welcome-actions"><Button variant="ghost" onClick={() => setStep(0)}><ArrowLeft />Back</Button><Button autoFocus onClick={() => setStep(2)}>Continue<ArrowRight /></Button></div>
     </>}
     {step === 2 && <>
      <h1>Connect your AI</h1>
      <p>Your AI works in its own tabs, and you approve every app first. Private tabs, passwords and cookies stay off-limits.</p>
      {!noAi && <div className="welcome-ai">
       <strong>Chat with AI in Still</strong><small>Uses the app on this PC, signed in to your own account.</small>
       <div className="welcome-ai-picks">{AIS.map(a => <Button key={a.id} variant={aiHarness === a.id ? "default" : "outline"} size="sm" aria-pressed={aiHarness === a.id} onClick={() => send("aiHarness", { harness: a.id })}>{a.name}{aiHarness === a.id && <Check />}</Button>)}</div>
      </div>}
      <div className="welcome-options">
       <button className="welcome-option" disabled={agents} onClick={() => send("preference", { key: "agents", value: "true" })}><Bot /><span><strong>{agents ? "AI apps can use Still" : "Let AI apps use Still"}</strong><small>Claude Code, Claude Desktop, Cursor, Codex and other MCP apps</small></span>{agents ? <Check /> : <ArrowRight />}</button>
      </div>
      {agents && mcpCommand && <div className="welcome-ai-picks">
       <Button variant="outline" size="sm" onClick={() => copy("claude", `claude mcp add still -- "${mcpCommand}" --mcp`)}>{copied === "claude" ? <Check /> : <Copy />}Claude Code command</Button>
       <Button variant="outline" size="sm" onClick={() => copy("json", JSON.stringify({ mcpServers: { still: { command: mcpCommand, args: ["--mcp"] } } }, null, 2))}>{copied === "json" ? <Check /> : <Copy />}MCP config</Button>
      </div>}
      <div className="welcome-actions"><Button variant="ghost" onClick={() => setStep(1)}><ArrowLeft />Back</Button><Button autoFocus onClick={finish}>Start browsing<ArrowRight /></Button></div>
     </>}
    </motion.div>
   </AnimatePresence>
  </div>
 </div>
}
