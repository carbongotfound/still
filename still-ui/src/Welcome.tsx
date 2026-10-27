import { useState, type ReactNode } from "react"
import { AnimatePresence, motion } from "motion/react"
import { Bot, Check, Copy, CornerDownLeft, Dices, Download, Globe2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AiPicker, type AiState } from "./AiSidebar"
import { COLORS, FACE_NAMES, FALLBACK, Face, NAMES, type Companion } from "./Buddy"

const TASKS = [
 ["Plan a weekend away", "Help me plan a weekend away. Ask me where I'm starting from and what I like, then find a few options."],
 ["Find the best price for something", "Help me find the best price for something. Ask me what I'm shopping for first."],
 ["Catch me up on the news", "Catch me up on today's top news in a few bullet points, with links."],
 ["Find an easy dinner for tonight", "Find me an easy, well-reviewed dinner recipe for tonight."],
]
const Bubble = ({ children }: { children: ReactNode }) => <p className="welcome-bubble">{children}</p>

// First run, as a chat with your companion: meet them, name them and pick their look, connect your AI, then hand them a first task.
export function Welcome({ isDefault, agents, mcpCommand, ai, noAi, send, onImport }: { isDefault?: boolean; agents: boolean; mcpCommand?: string; ai?: AiState; noAi?: boolean; send: (op: string, data?: Record<string, unknown>) => void; onImport: () => void }) {
 const flow = noAi || !ai ? ["hello", "import", "agents"] : ["hello", "name", "ai", "import", "task"]
 const [step, setStep] = useState(0)
 const [c, setC] = useState<Companion>(ai?.companions?.[0] ?? FALLBACK)
 const [look, setLook] = useState(false)
 const [task, setTask] = useState("")
 const [own, setOwn] = useState("")
 const [copied, setCopied] = useState("")
 const at = flow[step]
 const finish = () => send("welcomeDone")
 const copy = (label: string, text: string) => { send("copyText", { text }); setCopied(label) }
 const save = () => { if (c.name.trim()) send("companionSave", { ...c, name: c.name.trim() }) }
 const next = () => {
  if (look) { setLook(false); return }
  if (at === "name") save()
  if (at === "task") { const text = own.trim() || task; if (text) send("aiSend", { text, home: true, companion: c.id }); finish(); return }
  if (step === flow.length - 1) { finish(); return }
  setStep(step + 1); if (flow[step + 1] === "ai") send("aiCheck")
 }
 const names = NAMES.filter(n => n !== c.name).slice(0, 4)
 const name = c.name.trim() || "your companion"
 return <div className="welcome" role="dialog" aria-modal="true" aria-label="Welcome to Still">
  <div className="welcome-card" onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !(e.target as HTMLElement).closest("button,textarea")) { e.preventDefault(); next() } }}>
   <div className="welcome-top"><div className="welcome-progress"><i style={{ width: (step + 1) / flow.length * 100 + "%" }} /></div><button className="welcome-skip" onClick={finish}>Skip all</button></div>
   <div className="welcome-body">
    <Face companion={c} size={210} mood={at === "hello" ? "happy" : "idle"} className="welcome-face" key={c.face + c.color} />
    <AnimatePresence mode="wait" initial={false}>
     <motion.div key={at + look} className="welcome-talk" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: .22, ease: [.3, .7, .2, 1] }}>
      {at === "hello" && <>
       <Bubble>Hi! I'm {noAi || !ai ? "Still" : name}.</Bubble>
       <Bubble>{noAi || !ai ? "A calm browser that AI apps on this PC can work in, next to your own tabs." : "I work on the web for you in my own tabs: comparing, researching and doing the boring bits, while you keep browsing."}</Bubble>
       {!noAi && ai && <Bubble>Let's get me set up. It takes a minute.</Bubble>}
      </>}
      {at === "name" && !look && <>
       <Bubble>What would you like to name me?</Bubble>
       <div className="welcome-box">
        <input autoFocus aria-label="Name your companion" placeholder="Name your companion" maxLength={24} value={c.name} onChange={e => setC({ ...c, name: e.target.value })} />
        <div className="welcome-chips">{names.map(n => <button key={n} onClick={() => setC({ ...c, name: n })}>{n}</button>)}<button aria-label="Other names" title="Other names" onClick={() => setC({ ...c, name: NAMES[Math.floor(Math.random() * NAMES.length)] })}><Dices /></button></div>
       </div>
       <div className="welcome-box is-row"><button className="welcome-look" onClick={() => setLook(true)}>Change my look</button>
        <div className="welcome-faces">{FACE_NAMES.slice(0, 7).map(f => <button key={f} aria-label={f} className={cn(c.face === f && "is-picked")} onClick={() => setC({ ...c, face: f })}><Face companion={{ ...c, face: f }} size={22} /></button>)}</div></div>
      </>}
      {at === "name" && look && <div className="welcome-lookbook">
       <h4>Face</h4>
       <div className="companion-faces" role="radiogroup" aria-label="Face">{FACE_NAMES.map(f => <button key={f} role="radio" aria-checked={c.face === f} aria-label={f} className={cn(c.face === f && "is-picked")} onClick={() => setC({ ...c, face: f })}><Face companion={{ ...c, face: f }} size={34} /></button>)}</div>
       <h4>Color</h4>
       <div className="companion-colors" role="radiogroup" aria-label="Color">{COLORS.map(k => <button key={k} role="radio" aria-checked={c.color === k} aria-label={k} data-color={k} className={cn("face", c.color === k && "is-picked")} onClick={() => setC({ ...c, color: k })} />)}</div>
      </div>}
      {at === "ai" && ai && <>
       <Bubble>Which AI should I think with?</Bubble>
       <Bubble>I use the AI app you already have, signed in with your own account, so there's nothing new to pay for. Private tabs, passwords and cookies stay off-limits to me.</Bubble>
       <AiPicker ai={ai} onPick={id => send("aiHarness", { harness: id })} />
      </>}
      {at === "import" && <>
       <Bubble>Want to bring your stuff over?</Bubble>
       <Bubble>Bookmarks, history, passwords and sign-ins from Chrome, Edge, Brave or Opera GX. Nothing leaves this PC.</Bubble>
       <div className="welcome-options">
        <button className="welcome-option" onClick={() => { finish(); onImport() }}><Download /><span><strong>Import from another browser</strong><small>Pick a browser and review before anything is copied</small></span></button>
        <button className="welcome-option" disabled={isDefault} onClick={() => send("defaultBrowser")}><Globe2 /><span><strong>{isDefault ? "Still is your default browser" : "Make Still my default browser"}</strong><small>{isDefault ? "Links from other apps open here" : "Windows asks you to confirm"}</small></span>{isDefault && <Check />}</button>
       </div>
      </>}
      {at === "agents" && <>
       <Bubble>Want AI apps on this PC to use Still?</Bubble>
       <Bubble>Claude Code, Cursor and other MCP apps can open, read and click pages here. Each app asks you before it starts.</Bubble>
       <div className="welcome-options"><button className="welcome-option" disabled={agents} onClick={() => send("preference", { key: "agents", value: "true" })}><Bot /><span><strong>{agents ? "AI apps can use Still" : "Let AI apps use Still"}</strong><small>Never private tabs, passwords or cookies</small></span>{agents && <Check />}</button></div>
       {agents && mcpCommand && <div className="welcome-ai-picks">
        <Button variant="outline" size="sm" onClick={() => copy("claude", `claude mcp add still -- "${mcpCommand}" --mcp`)}>{copied === "claude" ? <Check /> : <Copy />}Claude Code command</Button>
        <Button variant="outline" size="sm" onClick={() => copy("json", JSON.stringify({ mcpServers: { still: { command: mcpCommand, args: ["--mcp"] } } }, null, 2))}>{copied === "json" ? <Check /> : <Copy />}MCP config</Button>
       </div>}
      </>}
      {at === "task" && <>
       <Bubble>All set. Which task should I tackle first?</Bubble>
       <div className="welcome-box"><textarea aria-label="Your own task" rows={2} placeholder="Or tell me in your own words" value={own} onChange={e => setOwn(e.target.value)} /></div>
       <div className="welcome-answers" role="radiogroup" aria-label="First task">{TASKS.map(([label, prompt]) => <button key={label} role="radio" aria-checked={task === prompt} onClick={() => setTask(task === prompt ? "" : prompt)}><i />{label}</button>)}</div>
      </>}
     </motion.div>
    </AnimatePresence>
   </div>
   <div className="welcome-foot">
    {step > 0 && <Button variant="ghost" onClick={() => look ? setLook(false) : setStep(step - 1)}>Back</Button>}
    <span className="flex-1" />
    {at === "task" && !task && !own.trim() && <Button variant="ghost" onClick={finish}>Skip</Button>}
    <Button className="welcome-next" disabled={at === "name" && !c.name.trim()} onClick={next}>{look ? "Save look" : at === "task" ? (task || own.trim() ? "Start" : "Done") : "Continue"}<CornerDownLeft /></Button>
   </div>
  </div>
 </div>
}
