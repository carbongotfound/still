import { useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { ArrowRight, ArrowLeft, Check, Download, Globe2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// First-run welcome: pick where tabs live, optionally import from another browser, then start browsing.
export function Welcome({ layout, isDefault, send, onImport }: { layout: string; isDefault?: boolean; send: (op: string, data?: Record<string, unknown>) => void; onImport: () => void }) {
 const [step, setStep] = useState(0)
 const pickLayout = (value: string) => send("preference", { key: "layout", value })
 const finish = () => send("welcomeDone")
 return <div className="welcome" role="dialog" aria-modal="true" aria-label="Welcome to Still">
  <div className="welcome-card">
   <div className="welcome-dots">{[0, 1, 2].map(i => <i key={i} className={cn(i === step && "is-on")} />)}</div>
   <AnimatePresence mode="wait" initial={false}>
    <motion.div key={step} className="welcome-step" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.22, ease: [0.3, 0.7, 0.2, 1] }}>
     {step === 0 && <>
      <div className="still-mark"><i /><i /></div>
      <h1>Welcome to Still</h1>
      <p>A calm, fast browser that stays out of your way. Let's set up a couple of things. It takes ten seconds.</p>
      <div className="welcome-actions"><Button variant="ghost" onClick={finish}>Skip setup</Button><Button autoFocus onClick={() => setStep(1)}>Get started<ArrowRight /></Button></div>
     </>}
     {step === 1 && <>
      <h1>Where should your tabs go?</h1>
      <p>You can change this any time in Settings.</p>
      <div className="welcome-layouts">
       {[{ value: "Sidebar", label: "On the side", note: "Room for lots of tabs" }, { value: "Top", label: "On top", note: "Classic, like most browsers" }].map(o =>
        <button key={o.value} className={cn("welcome-layout", layout === o.value && "is-picked")} onClick={() => pickLayout(o.value)} aria-pressed={layout === o.value}>
         <span className={cn("mini-browser", o.value === "Top" ? "is-top" : "is-side")}>
          <span className="mini-tabs">{[0, 1, 2].map(i => <i key={i} className={cn(i === 0 && "is-active")} />)}</span>
          <span className="mini-main"><span className="mini-address" /><span className="mini-page"><i /><i /><i /></span></span>
         </span>
         <strong>{o.label}{layout === o.value && <Check />}</strong><small>{o.note}</small>
        </button>)}
      </div>
      <div className="welcome-actions"><Button variant="ghost" onClick={() => setStep(0)}><ArrowLeft />Back</Button><Button autoFocus onClick={() => setStep(2)}>Continue<ArrowRight /></Button></div>
     </>}
     {step === 2 && <>
      <h1>Bring your stuff over</h1>
      <p>Import bookmarks, history, passwords and sign-ins from Opera GX, Chrome, Edge or Brave. Nothing leaves this PC.</p>
      <div className="welcome-options">
       <button className="welcome-option" onClick={() => { finish(); onImport() }}><Download /><span><strong>Import from another browser</strong><small>Pick a browser and review before anything is copied</small></span><ArrowRight /></button>
       <button className="welcome-option" disabled={isDefault} onClick={() => send("defaultBrowser")}><Globe2 /><span><strong>{isDefault ? "Still is your default browser" : "Make Still my default browser"}</strong><small>{isDefault ? "Links from other apps open here" : "Windows asks you to confirm"}</small></span>{isDefault ? <Check /> : <ArrowRight />}</button>
      </div>
      <div className="welcome-actions"><Button variant="ghost" onClick={() => setStep(1)}><ArrowLeft />Back</Button><Button autoFocus onClick={finish}>Start browsing<ArrowRight /></Button></div>
     </>}
    </motion.div>
   </AnimatePresence>
  </div>
 </div>
}
