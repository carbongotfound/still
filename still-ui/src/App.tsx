import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { AnimatePresence, LayoutGroup, motion, MotionConfig, useReducedMotion } from "motion/react"
import { Bot, Blocks, Cpu, Palette, SlidersHorizontal, Info, Settings, FileText, Flag, Plug, Sparkles, Users, CircleHelp, PanelLeftClose, PanelRightClose, PanelRightOpen, ArrowUpRight, ChevronDown, Library, MessageSquare, SquarePen, Sun, Moon, Monitor, type LucideIcon, ArrowLeft, ArrowRight, RotateCw, Plus, X, Minus, Expand, Search, MoreHorizontal, Settings2, Bookmark, Shield, ShieldOff, BookOpen, Download, History, Pin, PinOff, VolumeX, Copy, MoonStar, EyeOff, ExternalLink, Keyboard, LockKeyhole, ChevronRight, Check, Loader2, Trash2, FolderOpen, Globe2, KeyRound, Puzzle, Cookie, ShieldCheck, Pencil, Square, UsersRound, Import, Columns2, FolderPlus, FolderMinus, ArrowLeftRight, SeparatorVertical, PanelLeft, Hand, Link2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AiPanel, ChatView, Composer, RunAnnouncer, RunningTasks, chatOf, companionOf, isRunning, type AiState } from "./AiSidebar"
import { FileIcon, FileViewer, type FileData } from "./Files"
import { AuditList, PermissionsSettings } from "./Permissions"
import { SitePermissions } from "./SitePermissions"
import { AiLogo } from "./AiLogo"
import { Buddy, CompanionContext, Face, FALLBACK, Space, agentFace, hueOf, lookOf, type Companion } from "./Buddy"
import { ProfilePanel } from "./ProfilePanel"
import { MemorySettings } from "./Memory"
import { CompanionLibrary, CompanionProfile, JoinedCard, fromPremade, premadeOf, tasksFor, type Premade } from "./crew"
import { PluginKeySetting, PluginStack } from "./Plugins"
import { ChatHistory, ChatLink, CompanionEditor, CompanionSwitch, CompanionsPage, HomeRail, LibraryPage, RenameAsk, SkillsPage, randomCompanion, type HomeView } from "./Home"
import { MascotStage } from "./Mascot"
import { IntroReplay } from "./Intro"
import { DEFAULT_LOOK } from "./look"
import { setSounds } from "./sound"
import { UploadCard, type Upload } from "./UploadCard"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from "@/components/ui/command"
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuLabel } from "@/components/ui/dropdown-menu"
import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator, ContextMenuShortcut } from "@/components/ui/context-menu"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator } from "@/components/ui/select"
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog"
import { Toaster } from "@/components/ui/sonner"
import { toast } from "sonner"
import { cn, MAC } from "@/lib/utils"
import "./app.css"
import { homeIdeas, rankSuggestions, type AddressPick, type HomeIdea } from "./suggestions"
import { BrowserTools } from "./BrowserTools"
import { SaveLoginBar } from "./Passwords"
import { Welcome } from "./Welcome"
import { Tour } from "./Tour"
import type { ToolData } from "./BrowserTools"

type Tab = { id: string; title: string; url: string; home?: HomeView; pinned: boolean; isPrivate: boolean; loading: boolean; sleeping: boolean; blocked: number; muted: boolean; favicon?: string; secure?: boolean; certificateError?: boolean; inUse?: string; agent?: string; runChat?: string; driverChat?: string; aiGroup?: boolean; chatId?: string; inChat?: string; group?: string }
type Group = { id: string; name: string; color: string; collapsed: boolean }
const splittable = (t?: Tab) => !!t?.url && !t.chatId && !t.inChat
type Visit = { title: string; url: string; favicon?: string | null; at?: string }
type DownloadItem = { id: string; name: string; status: string; bytes: number; total?: number }
type ExtensionRef = { id:string; name:string; icon?:string|null }
function ExtensionIcon({ icon }: { icon?: string | null }) { return icon ? <img className="ext-icon" src={icon} alt="" /> : <Puzzle /> }
// An extension's side panel (chrome.sidePanel). The page itself is a separate web view that Still lays over the slot.
function ExtensionPanel({ panel }: { panel: ExtensionRef }) {
 const slot = useRef<HTMLDivElement>(null)
 useLayoutEffect(() => {
  const element = slot.current
  if (!element) return
  const sync = () => { const r = element.getBoundingClientRect(); send("sidePanelBounds", { x: r.x, y: r.y, width: r.width, height: r.height, viewportWidth: innerWidth }) }
  const observer = new ResizeObserver(sync); observer.observe(element); addEventListener("resize", sync); sync()
  return () => { observer.disconnect(); removeEventListener("resize", sync) }
 }, [panel.id])
 return <aside className="ext-panel" aria-label={panel.name + " side panel"}>
  <header className="ai-head"><span className="ext-panel-icon"><ExtensionIcon icon={panel.icon} /></span><strong className="ai-title">{panel.name}</strong>
   <Button variant="ghost" size="icon-sm" aria-label="Close side panel" onClick={() => send("sidePanelClose")}><X /></Button></header>
  <div className="ext-panel-slot" ref={slot} />
 </aside>
}
type State = { welcome?:boolean; welcomeTalk?:boolean; noExtensions?:boolean; noAi?:boolean; sidePanel?:ExtensionRef|null; pinnedExtensions?:ExtensionRef[]; profileName:string; maximized:boolean; loginOffer?:{id:string;origin:string;username:string;password:string;update:boolean}; permission?:{id:string;site:string;kind:string}; update?:{version:string;current:string;ready?:boolean;progress?:number;busy?:boolean;selfUpdate?:boolean;downloading?:boolean}; version?:string; windows?:{id:string;name:string;title:string}[]; secondary?:boolean; incognito?:boolean; agent?:{client:string;pending:boolean;action:string;ask?:string;paused?:boolean;signIn?:string;tab?:string;key?:string};working?:string[]; dialog?:{id:string;kind:string;message:string;defaultText:string;site:string}; mcpCommand?:string; activeId: string; dark: boolean; focusMode: boolean; fullScreen:boolean; appFullScreen?:boolean; preferences: { theme: string; search: string; restore: boolean; blocking: boolean; downloads: string; tracking:string; memory:boolean; autofill:boolean; startup:boolean; startupDisabled:boolean; isDefaultBrowser?:boolean; tearOff?:boolean; agents?:boolean; askInChat?:boolean; tabLayout?:string; chatTitles?:string; sidebarWidth?:number; newTab?:string; interests?:string[]; sounds?:boolean; osSoundsOff?:boolean }; zoom:number; tabs: Tab[]; history: Visit[]; bookmarks: Visit[]; downloads: DownloadItem[]; canBack: boolean; canForward: boolean; siteBlocking: boolean; chatPage?: { id: string; url: string; title: string; loading: boolean; favicon?: string } | null; groups?: Group[]; split?: { left: string; right: string; ratio: number } | null; picks?: AddressPick[] }
type Bridge = { postMessage: (v: unknown) => void; addEventListener: (name: string, listener: (e: MessageEvent) => void) => void; removeEventListener: (name: string, listener: (e: MessageEvent) => void) => void }
declare global { interface Window { chrome?: { webview?: Bridge } } }
function send(op: string, payload: Record<string, unknown> = {}) { window.chrome?.webview?.postMessage({ op, ...payload }) }
// Who is driving a tab: the companion of the chat that opened it, or another AI app under its own name.
const driverOf = (ai: AiState | undefined, tab: Tab): Companion => tab.driverChat ?? tab.runChat ? companionOf(ai, chatOf(ai, tab.driverChat ?? tab.runChat)?.companion) ?? FALLBACK : { ...FALLBACK, id: "", name: tab.agent ?? "", face: agentFace(tab.agent) }
const initial: State = { profileName:"Default",maximized:false,activeId: "empty", dark: true, focusMode: false, fullScreen:false, preferences: { theme: "Dark", search: "Google", restore: true, blocking: true, downloads: "", tracking:"Balanced", memory:true, autofill:true, startup:false, startupDisabled:false }, zoom:100, tabs: [{ id: "empty", title: "New tab", url: "", pinned: false, isPrivate: false, loading: false, sleeping: false, blocked: 0, muted: false }], history: [], bookmarks: [], downloads: [], canBack: false, canForward: false, siteBlocking: true }
// One click on the new tab page hands one of these to the AI.
// "Try one of these": a look per kind of idea (suggestions.ts homeIdeas).
const IDEA_LOOKS: Record<HomeIdea["kind"], [LucideIcon, string]> = { project: [Flag, "amber"], app: [Plug, "green"], tab: [FileText, "sky"], role: [Sparkles, "rose"] }
const HELP = "https://github.com/carbongotfound/still#readme"
// Still's own pages by address, typed in the address bar: still://chats and so on. A home page, a panel, or Help.
const STILL_PAGES: [name: string, label: string, home?: HomeView][] = [["new", "New chat", "home"], ["chats", "Chat history", "chats"], ["library", "Library", "library"],
 ["companions", "Companions", "companions"], ["skills", "Skills & plugins", "skills"], ["settings", "Settings"], ["history", "History"], ["bookmarks", "Bookmarks"],
 ["downloads", "Downloads"], ["passwords", "Passwords"], ["profiles", "Profiles"], ["import", "Import"], ["extensions", "Extensions"], ["about", "About Still"], ["help", "Help"]]
const STILL_ALIASES: Record<string, string> = { "chat-history": "chats", "new-chat": "new", home: "new", plugins: "skills", "skills-and-plugins": "skills" }
/// The page a still:// address names (any case; spaces read as dashes), "" for an unknown one, undefined for any other address.
const stillPage = (url: string) => { const m = /^still:\/*(.*?)\/*$/i.exec(url.trim()); if (!m) return undefined; const name = m[1].toLowerCase().replace(/[\s_]+/g, "-"); return STILL_PAGES.find(p => p[0] === (STILL_ALIASES[name] ?? name)) ?? null }
const greeting = () => { const h = new Date().getHours(); return h < 5 ? "Hello, night owl" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening" }
const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") || url } catch { return url } }
// Shortcut hints in the native spelling: Cmd and Shift symbols on a Mac.
export const keys = (k: string) => MAC ? k.replace(/Ctrl Alt/g, "⌥⌘").replace(/Ctrl Shift/g, "⇧⌘").replace(/Ctrl/g, "⌘").replace(/Shift/g, "⇧").replace(/Alt/g, "⌥").replace(/Right/g, "→").replace(/Left/g, "←").replace(/ /g, "") : k
// Where the Mac menu bar differs from Windows: Control+Tab stays Control, and the rest follow Safari.
const MAC_KEYS: Record<string, [string, string]> = { "Private tab": ["Private window", "Ctrl Shift N"], "Recent tabs (hold Ctrl)": ["Recent tabs (hold Control)", "⌃Tab"], "Bookmarks": ["Bookmarks", "Ctrl Alt B"], "History": ["History", "Ctrl Y"], "Downloads": ["Downloads", "Ctrl Alt L"], "View page source": ["View page source", "Ctrl Alt U"], "Full screen": ["Full screen", "⌃⌘F"] }
const shortcuts = [["Go to an address", "Ctrl L"], ["Find a tab", "Ctrl K"], ["Running tasks", "Ctrl Shift K"], ["Stop the AI", "Ctrl ."], ["Approve the card in front of you", "Ctrl Enter"], ["Close a preview", "Esc"], ["New tab", "Ctrl T"], ["Private tab", "Ctrl Shift N"], ["Close tab", "Ctrl W"], ["Reopen tab", "Ctrl Shift T"], ["Recent tabs (hold Ctrl)", "Ctrl Tab"], ["Next / previous tab", "Ctrl Alt Right / Left"], ["Tabs on top / on the side", "Ctrl Shift S"], ["Pin tab", "Ctrl Shift P"], ["Bookmark page", "Ctrl D"], ["Bookmarks", "Ctrl Shift B"], ["History", "Ctrl H"], ["Downloads", "Ctrl J"], ["Find in page", "Ctrl F"], ["Chat with your AI", "Ctrl Shift A"], ["View page source", "Ctrl U"], ["Reader", "Ctrl Shift R"], ["Hide an element", "Ctrl Shift H"], ["Full screen", "F11"], ["Exit full screen", "Esc"], ["Focus mode", "Ctrl Shift F"], ["Settings", "Ctrl ,"]].map(([label, key]) => MAC ? (MAC_KEYS[label] ?? [label, key]).map((v, i) => i ? keys(v) : v) : [label, key])

// After a restart, once: the chats that were working when Still closed. Resume all picks up every one but a chat with a
// step that may not have finished, which is resumed from the chat itself (it checks first and asks again).
let offered = false
function resumeOffer(cut: { id: string; title: string; unsure: boolean }[]) {
 if (!cut.length || offered) return
 offered = true
 const unsure = cut.filter(c => c.unsure), names = (l: typeof cut) => l.map(c => `“${c.title || "New chat"}”`).join(", ")
 toast(cut.length === 1 ? `${names(cut)} stopped mid-task when Still closed.` : `${cut.length} chats stopped mid-task when Still closed: ${names(cut)}.`, { id: "resume", duration: Infinity, className: "resume-toast",
  description: unsure.length ? `Open ${names(unsure)} to resume ${unsure.length === 1 ? "it" : "them"}: a step may not have finished, so it's checked first.` : undefined,
  action: unsure.length < cut.length ? { label: unsure.length ? "Resume the others" : "Resume all", onClick: () => send("aiResumeAll") } : undefined,
  cancel: { label: "Not now", onClick: () => send("aiResumeDismiss") } })
}

// Ctrl+Enter: approve the card that has focus, or the waiting card when you aren't typing (an empty message box counts).
function approveCard() {
 const focus = document.activeElement as HTMLElement | null
 const typing = !!focus?.closest("input, textarea, [contenteditable=true]") && !(focus instanceof HTMLTextAreaElement && focus.getAttribute("aria-label") === "Message" && !focus.value.trim())
 const card = focus?.closest(".approve-card") ?? (typing ? null : document.querySelector(".approve-card"))
 const approve = card?.querySelector<HTMLButtonElement>("[data-approve]")
 approve?.click()
 return !!approve
}

const FLOW = { type: "spring" as const, stiffness: 460, damping: 34, mass: .75 }
// Settings: its pages, and every setting by its row id (set-<id>) with the words a search finds it by.
const SETTING_PAGES: [string, string, LucideIcon][] = [["general", "General", SlidersHorizontal], ["appearance", "Appearance", Palette], ["companions", "Companions", UsersRound], ["models", "Models", Cpu],
 ["skills", "Skills & plugins", Blocks], ["privacy", "Privacy & permissions", ShieldCheck], ["shortcuts", "Shortcuts", Keyboard], ["about", "About", Info]]
const AI_PAGES = ["companions", "skills"]
const OLD_PAGES: Record<string, string> = { ai: "models", memory: "companions", plugins: "skills", permissions: "privacy", extensions: "general", advanced: "general" }
type Finding = [string, string, string, string]
const SETTINGS_FIND: Finding[] = [
 ["setup", "general", "Run setup again", "welcome first steps start over"], ["talk", "general", "Set me up with your companion", "setup questions layout"],
 ["search", "general", "Search engine", "google bing duckduckgo"], ["default", "general", "Default browser", "open links"], ["startup", "general", "Open Still at sign-in", "login start boot"],
 ["restore", "general", "Pick up where you left off", "restore tabs session reopen"], ["sounds", "general", "Sounds", "audio jingle mute"], ["downloads", "general", "Download folder", "files save location"],
 ["import", "general", "Import browsing data", "chrome edge firefox brave bookmarks history passwords"], ["export", "general", "Export bookmarks", "backup file"],
 ["profiles", "general", "Profiles", "spaces accounts separate"], ["extensions", "general", "Extensions", "chrome web store add-ons"],
 ["theme", "appearance", "Theme", "dark light black system mode colors"], ["layout", "appearance", "Tab layout", "classic modern side vertical tabs"], ["tearoff", "appearance", "Drag tabs into their own window", "tear off new window"],
 ["team", "companions", "Companions", "team add edit hire look"], ["memory", "companions", "What companions remember", "memory forget facts"],
 ["ai", "models", "AI and model", "claude chatgpt grok sign in effort thinking"], ["titles", "models", "Chat titles", "name rename model first message"],
 ["mcp", "models", "Let other AI apps use Still", "mcp claude desktop code cursor agents"], ["askInChat", "models", "Ask me in the AI's chat when I'm away", "agents away"],
 ["dev", "models", "Connect an AI app by hand", "mcp config cli developer command line prompt"],
 ["skills", "skills", "Skills & plugins", "composio gmail slack apps connect"], ["composio", "skills", "Composio API key", "plugins key change delete remove"],
 ["blocking", "privacy", "Block ads & trackers", "adblock tracking"], ["passwords", "privacy", "Passwords", "logins autofill"], ["cookies", "privacy", "Cookies", "site data"],
 ["security", "privacy", "Privacy & security", "tracking protection site permissions camera location"], ["permissions", "privacy", "What companions may do", "permissions ask approve sites sensitive"],
 ["clearHistory", "privacy", "Clear browsing history", "delete"], ["clearCookies", "privacy", "Clear cookies and website data", "delete sign out"],
 ["about", "about", "About Still", "version update intro open source"]]
function SetCard({ title, children }: { title: string; children: ReactNode }) {
 return <section className="set-group" aria-label={title}><h3>{title}</h3><div className="set-card">{children}</div></section>
}
function SetRow({ id, title, help, children }: { id: string; title: string; help?: ReactNode; children?: ReactNode }) {
 return <div className="setting-row" id={"set-" + id}><div><strong>{title}</strong>{help && <p>{help}</p>}</div>{children}</div>
}
const AnimatedButton = motion.create(Button)
function FlowTabs({ tabs, top = false }: { tabs: Tab[]; top?: boolean }) {
 const reduced = useReducedMotion()
 return <AnimatePresence initial={false} mode="popLayout">{tabs.map(tab => <motion.div key={tab.id} className={cn("tab-motion", top && "top-tab-motion")} layout="position"
  initial={{ opacity: 0, x: reduced ? 0 : -8, scale: reduced ? 1 : .97 }} animate={{ opacity: 1, x: 0, scale: 1 }}
  exit={{ opacity: 0, x: reduced ? 0 : -12, scale: reduced ? 1 : .97, transition: { duration: reduced ? .01 : .16 } }} transition={FLOW}>
  <TabView tab={tab} top={top} />
 </motion.div>)}</AnimatePresence>
}
// Tabs in strip order, with each group's tabs gathered under its chip.
function TabStrip({ tabs, top }: { tabs: Tab[]; top: boolean }) {
 const { state } = useContext(UICtx)!
 const groups = state.groups ?? [], out: ReactNode[] = []
 for (let i = 0; i < tabs.length;) {
  const group = groups.find(g => g.id === tabs[i].group)
  let j = i + 1
  while (j < tabs.length && (group ? tabs[j].group === group.id : !groups.some(g => g.id === tabs[j].group))) j++
  out.push(group ? <TabGroupView key={group.id} group={group} tabs={tabs.slice(i, j)} top={top} /> : <FlowTabs key={"f" + tabs[i].id} tabs={tabs.slice(i, j)} top={top} />)
  i = j
 }
 return <>{out}</>
}
const GROUP_COLORS = ["blue", "green", "amber", "rose", "violet", "cyan", "orange", "grey"]
function TabGroupView({ group, tabs, top }: { group: Group; tabs: Tab[]; top: boolean }) {
 const { state, setContext, renaming, setRenaming } = useContext(UICtx)!
 const shown = group.collapsed ? tabs.filter(t => t.id === state.activeId) : tabs // the tab you're on stays in view
 const label = group.name || "Unnamed group"
 const save = (name: string) => { setRenaming(""); if (name.trim() !== group.name) send("groupSet", { group: group.id, name }) }
 return <div className={cn("tab-group", top && "is-top", group.collapsed && "is-collapsed")} data-color={group.color} role="group" aria-label={`${label}, ${tabs.length} ${tabs.length === 1 ? "tab" : "tabs"}`}>
  {renaming === group.id ? <input className="tab-group-name" autoFocus defaultValue={group.name} aria-label="Group name" placeholder="Name this group" maxLength={40}
   onKeyDown={e => { if (e.key === "Enter") save(e.currentTarget.value); else if (e.key === "Escape") { e.stopPropagation(); setRenaming("") } }} onBlur={e => save(e.currentTarget.value)} />
  : <ContextMenu onOpenChange={setContext}><ContextMenuTrigger asChild>
   <button className="tab-group-chip" aria-expanded={!group.collapsed} aria-label={`${label}, ${group.collapsed ? "show" : "hide"} its tabs`} title={tabs.map(t => t.title).join("\n")} onClick={() => send("groupSet", { group: group.id, collapsed: !group.collapsed })}>
    {!top && <ChevronDown className="tab-group-chevron" />}
    {group.name ? <span className="tab-group-label">{group.name}</span> : <i className="group-dot" data-color={group.color} />}
    {group.collapsed && <span className="tab-group-icons" aria-hidden>{tabs.slice(0, 3).map(t => t.favicon ? <img key={t.id} src={t.favicon} alt="" /> : <Globe2 key={t.id} />)}{tabs.length > 3 && <b>+{tabs.length - 3}</b>}</span>}
   </button></ContextMenuTrigger>
   <ContextMenuContent className="w-52">
    <ContextMenuItem onSelect={() => setTimeout(() => setRenaming(group.id), 0)}><Pencil />Rename group</ContextMenuItem>
    <div className="group-colors" role="radiogroup" aria-label="Group color">{GROUP_COLORS.map(c => <button key={c} role="radio" aria-checked={group.color === c} aria-label={c} className="group-dot" data-color={c} onClick={() => send("groupSet", { group: group.id, color: c })} />)}</div>
    <ContextMenuItem onSelect={() => send("groupSet", { group: group.id, collapsed: !group.collapsed })}>{group.collapsed ? <ChevronDown /> : <ChevronRight />}{group.collapsed ? "Show its tabs" : "Collapse"}</ContextMenuItem>
    <ContextMenuItem onSelect={() => send("groupUngroup", { group: group.id })}><FolderMinus />Ungroup</ContextMenuItem>
    <ContextMenuSeparator />
    <ContextMenuItem onSelect={() => send("groupClose", { group: group.id })}><X />Close group</ContextMenuItem>
   </ContextMenuContent></ContextMenu>}
  <FlowTabs tabs={shown} top={top} />
 </div>
}
type Ghost = { id: string; title: string; favicon?: string; x: number; y: number; tearing: boolean; side?: string }
const UICtx = createContext<{state:State;ai?:AiState;setContext:(v:boolean)=>void;open:(name:string,value?:string)=>void;arriving:string;setGhost:(g:Ghost|null)=>void;renaming:string;setRenaming:(id:string)=>void}|null>(null)
 function IconButton({ label, caption = label, children, onClick, disabled = false }: { label: string; caption?:string; children: ReactNode; onClick: (e: React.MouseEvent<HTMLButtonElement>) => void; disabled?: boolean }) {
  return <AnimatedButton variant="ghost" size="icon-sm" className="chrome-button expanding-button" aria-label={label} disabled={disabled} onClick={onClick} whileTap={{ scale: .97 }} transition={FLOW}><span className="chrome-icon">{children}</span><span className="chrome-label" aria-hidden="true"><span>{caption}</span></span></AnimatedButton>
 }
 function TabView({ tab, top = false }: { tab: Tab; top?: boolean }) {
  const {state,ai,setContext,arriving,setGhost}=useContext(UICtx)!
  const selected = tab.id === state.activeId
  const marked = state.bookmarks.some(b => b.url === tab.url)
  const chat = tab.chatId ? companionOf(ai, chatOf(ai, tab.chatId)?.companion) : undefined
  const driver = tab.agent && !state.agent?.pending && state.working?.includes(tab.id) ? driverOf(ai, tab) : undefined // only while it is at work here
  const [tearing, setTearing] = useState(false)
  // Pointer-driven drag: drop on another tab to reorder; drop outside the tab list to open a new window.
  const drag = useRef<{ sx: number; sy: number; active: boolean } | null>(null)
  const suppressClick = useRef(false)
  const outsideList = (el: Element, x: number, y: number) => {
   const list = el.closest(".top-tab-strip, .browser-sidebar")?.getBoundingClientRect()
   const out = x < 0 || y < 0 || x > innerWidth || y > innerHeight
   return out || !list || x < list.left - 40 || x > list.right + 40 || y < list.top - 40 || y > list.bottom + 40
  }
  // Over the page, a dragged tab opens beside the one you're on (left or right half).
  const pageSide = (x: number, y: number) => {
   const r = document.querySelector(".page-slot")?.getBoundingClientRect()
   if (!r || x < r.left || x > r.right || y < r.top || y > r.bottom || tab.id === state.activeId || !splittable(tab) || !splittable(state.tabs.find(t => t.id === state.activeId))) return ""
   return x < r.left + r.width / 2 ? "left" : "right"
  }
  const onPointerDown = (e: React.PointerEvent) => { if (e.button === 0) drag.current = { sx: e.clientX, sy: e.clientY, active: false } }
  const onPointerMove = (e: React.PointerEvent) => {
   const d = drag.current; if (!d) return
   // Button no longer held (the release happened elsewhere, e.g. a pop-up took the mouse): end the drag.
   if (!(e.buttons & 1)) { drag.current = null; setGhost(null); return }
   if (!d.active) { if (Math.hypot(e.clientX - d.sx, e.clientY - d.sy) < 7) return; d.active = true; try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* pointer already gone */ } }
   const side = pageSide(e.clientX, e.clientY)
   const tear = !side && !!state.preferences.tearOff && outsideList(e.currentTarget, e.clientX, e.clientY)
   setGhost({ id: tab.id, title: tab.title, favicon: tab.favicon, x: e.clientX, y: e.clientY, tearing: tear, side })
  }
  const onPointerUp = (e: React.PointerEvent) => {
   const d = drag.current; drag.current = null
   if (!d?.active) return
   suppressClick.current = true
   setGhost(null)
   try { e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* not captured */ }
   const side = pageSide(e.clientX, e.clientY)
   if (side) { send("split", { id: tab.id, side }); return }
   if (state.preferences.tearOff && outsideList(e.currentTarget, e.clientX, e.clientY)) {
    setTearing(true)
    setTimeout(() => send("tearOff", { id: tab.id, x: e.screenX, y: e.screenY }), 190)
    return
   }
   const over = document.elementFromPoint(e.clientX, e.clientY)?.closest("[data-tab-id]")?.getAttribute("data-tab-id")
   if (over && over !== tab.id) send("reorder", { id: tab.id, before: over })
  }
  const onClickCapture = (e: React.MouseEvent) => { if (suppressClick.current) { suppressClick.current = false; e.stopPropagation(); e.preventDefault() } }
  return <ContextMenu onOpenChange={setContext}>
   <ContextMenuTrigger asChild>
    <div className={cn("tab-row", tab.pinned && "pin-tab", (state.split?.left === tab.id || state.split?.right === tab.id) && "is-split", driver && "is-driven", selected && "is-selected", top && "top-tab", tearing && "is-tearing", arriving === tab.id && "is-arriving")}
     data-tab-id={tab.id} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={() => { drag.current = null; setGhost(null) }} onLostPointerCapture={() => { if (drag.current?.active) { drag.current = null; setGhost(null) } }} onClickCapture={onClickCapture}
     onAuxClick={e => { if (e.button === 1) { e.preventDefault(); send("closeTab", { id: tab.id }) } }}>
     {selected && <motion.div className="selected-tab" layoutId={tab.pinned ? "pin-selected" : "tab-selected"} transition={FLOW} />}
     <Button variant="ghost" className="tab-main" aria-current={selected ? "page" : undefined} aria-label={(tab.pinned ? "Pinned " : "Tab ") + tab.title} title={tab.url || tab.title} onClick={() => send("select", { id: tab.id })}>
      <span className={cn("tab-letter", tab.sleeping && "is-sleeping")}>{driver ? <span className="tab-agent" data-kind={agentFace(driver.face) || "claude"} style={driver.id ? { "--drive": hueOf(driver) } as CSSProperties : undefined} title={driver.name + " is using this tab"}><Face companion={driver} size={18} mood={state.agent?.tab === tab.id && state.agent.paused ? "idle" : "working"} /></span> : tab.chatId ? <Face companion={chat} size={18} mood={isRunning(ai, tab.chatId) ? "working" : "idle"} /> : tab.loading ? <Loader2 className="spin" /> : tab.isPrivate ? <LockKeyhole /> : tab.muted ? <VolumeX /> : (tab.favicon ? <img className="tab-favicon" src={tab.favicon} alt="" onError={e=>{e.currentTarget.style.visibility="hidden"}} /> : <Globe2 />)}</span>
      {!tab.pinned && <span className="tab-label">{tab.title}</span>}
     </Button>
     {!tab.pinned && <Button variant="ghost" size="icon-xs" className="close-tab" aria-label={"Close " + tab.title} onClick={() => send("closeTab", { id: tab.id })}><X /></Button>}
    </div>
   </ContextMenuTrigger>
   <ContextMenuContent className="w-60">
    <ContextMenuItem onSelect={() => send("pin", { id: tab.id })}>{tab.pinned ? <PinOff /> : <Pin />}{tab.pinned ? "Unpin tab" : "Pin tab"}<ContextMenuShortcut>{keys("Ctrl Shift P")}</ContextMenuShortcut></ContextMenuItem>
    {!tab.chatId && !!tab.url && <>
     <ContextMenuItem onSelect={() => send("bookmark", { id: tab.id })}><Bookmark />{marked ? "Remove bookmark" : "Bookmark"}<ContextMenuShortcut>{keys("Ctrl D")}</ContextMenuShortcut></ContextMenuItem>
     <ContextMenuItem onSelect={() => { send("copyText", { text: tab.url }); toast("Link copied") }}><Link2 />Copy link</ContextMenuItem>
     {!state.noAi && !!ai && !tab.isPrivate && <ContextMenuItem onSelect={() => { send("select", { id: tab.id }); if (!ai.open) send("aiToggle") }}><MessageSquare />Open in chat<ContextMenuShortcut>{keys("Ctrl Shift A")}</ContextMenuShortcut></ContextMenuItem>}
    </>}
    <ContextMenuItem onSelect={() => send("duplicate", { id: tab.id })}><Copy />Duplicate</ContextMenuItem>
    <ContextMenuItem onSelect={() => send("mute", { id: tab.id })}><VolumeX />{tab.muted ? "Unmute" : "Mute"}</ContextMenuItem>
    <ContextMenuItem onSelect={() => send("sleep", { id: tab.id })}><MoonStar />Put to sleep</ContextMenuItem>
    {state.split && (state.split.left === tab.id || state.split.right === tab.id) && <>
     <ContextMenuSeparator />
     <ContextMenuItem onSelect={() => send("splitSwap")}><ArrowLeftRight />Swap sides</ContextMenuItem>
     <ContextMenuItem disabled={Math.abs(state.split.ratio - .5) < .01} onSelect={() => send("splitRatio", { ratio: .5 })}><Columns2 />Resize to 50/50</ContextMenuItem>
     <ContextMenuItem onSelect={() => send("splitEnd")}><SeparatorVertical />Separate tabs</ContextMenuItem>
     <ContextMenuSeparator />
    </>}
    {splittable(tab) && !selected && splittable(state.tabs.find(t => t.id === state.activeId)) && <ContextMenuItem onSelect={() => send("split", { id: tab.id })}><Columns2 />Open in split view</ContextMenuItem>}
    {ai && !state.noAi && splittable(tab) && !tab.isPrivate && <ContextMenuItem onSelect={() => send("tabHand", { id: tab.id, chat: state.tabs.find(t => t.id === state.activeId)?.chatId ?? (ai.open ? ai.chatId : undefined), companion: companionOf(ai)?.id })}><Hand />Hand to {companionOf(ai)?.name ?? "your companion"}</ContextMenuItem>}
    {!tab.pinned && !tab.inChat && <>
     <ContextMenuSeparator />
     <ContextMenuItem onSelect={() => send("groupNew", { id: tab.id })}><FolderPlus />Add to new group</ContextMenuItem>
     {(state.groups ?? []).filter(g => g.id !== tab.group).map(g => <ContextMenuItem key={g.id} onSelect={() => send("groupAdd", { id: tab.id, group: g.id })}><i className="group-dot" data-color={g.color} />Add to {g.name || "group"}</ContextMenuItem>)}
     {tab.group && <ContextMenuItem onSelect={() => send("groupRemove", { id: tab.id })}><FolderMinus />Remove from group</ContextMenuItem>}
    </>}
    <ContextMenuSeparator />
    <ContextMenuItem onSelect={() => send("closeTab", { id: tab.id, force: true })}><X />Close tab<ContextMenuShortcut>{keys("Ctrl W")}</ContextMenuShortcut></ContextMenuItem>
   </ContextMenuContent>
  </ContextMenu>
 }
 function MenuPanelItem({ name, label, icon, keys }: { name: string; label: string; icon: ReactNode; keys?: string }) {
  const {open}=useContext(UICtx)!
  return <DropdownMenuItem onSelect={() => setTimeout(() => open(name), 0)}>{icon}{label}{keys && <DropdownMenuShortcut>{keys}</DropdownMenuShortcut>}</DropdownMenuItem>
 }

export default function App() {
 const [state, setState] = useState<State>(initial)
 const [pane, setPane] = useState("")
 const [displayPane, setDisplayPane] = useState("")
 const [settingsPage, setSettingsPage] = useState("general")
 const [memoryFor, setMemoryFor] = useState("") // the companion Settings > Memory opens on
 const [settingsFind, setSettingsFind] = useState("")
 const [flash, setFlash] = useState("") // the setting a search result jumped to: it lights up for a moment
 const reduced = useReducedMotion()
 const [replay, setReplay] = useState(false) // About's "Replay the intro"
 // The little sounds (sound.ts): the Sounds setting, unless the system's own sounds are off or motion is reduced
 const soundsBlocked = state.preferences.osSoundsOff ? (MAC ? "Off because your Mac's sound effects are off" : "Off because Windows sounds are off") : reduced ? "Off because reduce motion is on" : ""
 const sounds = state.preferences.sounds !== false && !soundsBlocked
 useEffect(() => {
  const row = flash ? document.getElementById("set-" + flash) : null
  if (!row) return
  row.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" }); row.classList.add("set-flash")
  const t = setTimeout(() => { row.classList.remove("set-flash"); setFlash("") }, 1600)
  return () => clearTimeout(t)
 }, [flash, reduced])
 useEffect(() => setSounds(sounds), [sounds])
 const [query, setQuery] = useState("")
 const [filter, setFilter] = useState("")
 const [menu, setMenu] = useState(false)
 const [extMenu, setExtMenu] = useState(false)
 const [ai, setAi] = useState<AiState>()
 const [aiView, setAiView] = useState<"chat" | "settings">("chat")
 const [buddy, setBuddy] = useState("") // the companion picked on the new tab page
 const [editing, setEditing] = useState<Companion | null>(null)
 const [joined, setJoined] = useState<Companion | null>(null)
 const [profile, setProfile] = useState("") // the companion whose profile is open
 const [library, setLibrary] = useState(false) // "Hire a companion" opens Still's companion library first
 const [meeting, setMeeting] = useState<Premade | null>(null) // a library companion, previewed before it's hired
 const edit = (c: Companion) => c.id ? setProfile(c.id) : setLibrary(true)
 // Adding a companion: it gets its own id here, so the joined card can start its first chat.
 const hire = (c: Companion) => { const added = { ...c, id: crypto.randomUUID().replace(/-/g, "").slice(0, 10) }; send("companionSave", added); setJoined(added) }
 const chatWith = (id: string) => { setBuddy(id); send("aiKickoff", { companion: id }) } // a new companion's first chat starts itself
 useEffect(() => { const show = (e: Event) => setProfile((e as CustomEvent<string>).detail); addEventListener("still-profile", show); return () => removeEventListener("still-profile", show) }, [])
 const [railOpen, setRailOpenState] = useState(() => { try { return localStorage.getItem("still.chatRail") !== "closed" } catch { return true } })
 const setRailOpen = (v: boolean) => { setRailOpenState(v); try { localStorage.setItem("still.chatRail", v ? "open" : "closed") } catch { /* storage unavailable */ } }
 const extButton = useRef<HTMLButtonElement>(null)
 const [context, setContext] = useState(false)
 const [snapshot, setSnapshot] = useState("")
 const [pairShot, setPairShot] = useState("") // split view: the other half, while a menu covers the pages
 const [viewing, setViewing] = useState("") // a Library file open in the viewer
 const [tasksOpen, setTasksOpen] = useState(false)
 const [fileData, setFileData] = useState<FileData | null>(null)
 const [upload, setUpload] = useState<Upload | null>(null)
 const [notice,setNotice]=useState("")
 const [toolData,setToolData]=useState<Record<string,ToolData>>({})
 const [bookmarkDraft,setBookmarkDraft]=useState<{oldUrl:string;title:string;url:string}|null>(null)
 const editBookmark=(b:{title:string;url:string})=>{open("bookmarks");setBookmarkDraft({oldUrl:b.url,title:b.title,url:b.url})}
 const [confirm, setConfirm] = useState<{ title: string; body: string; op: string } | null>(null)
 const pageRef = useRef<HTMLDivElement>(null)
 const tabsRef = useRef<HTMLDivElement>(null)
 const commandRef = useRef<HTMLInputElement>(null)
 const commandChoice = useRef(false)
 const active = state.tabs.find(t => t.id === state.activeId) ?? state.tabs[0]
 const chatTab = !!active?.chatId && !!ai
 const split = chatTab && !!state.chatPage
 const modern = state.preferences.tabLayout === "Modern" && !state.focusMode && !state.fullScreen
 const pair = !chatTab ? state.split : null // split view: this tab and another side by side
 const [renaming, setRenaming] = useState("")
 const [recent, setRecent] = useState<{ ids: string[]; index: number }>({ ids: [], index: 0 })
 const resize = useRef<{ x: number; width: number; current: number } | null>(null)
 useEffect(() => { document.documentElement.style.setProperty("--sidebar-width", (state.preferences.sidebarWidth ?? 248) + "px") }, [state.preferences.sidebarWidth])
 const chatPages = state.tabs.filter(t => (t.inChat ?? t.runChat) && (t.inChat ?? t.runChat) === active?.chatId)
 // Beside its page, the chat takes a share of the width the user can drag (kept between runs).
 const [chatShare, setChatShare] = useState(() => { try { return Number(localStorage.getItem("still.chatShare")) || .4 } catch { return .4 } })
 const shareChat = (v: number, keep = true) => { const s = Math.min(.7, Math.max(.24, v)); setChatShare(s); if (keep) try { localStorage.setItem("still.chatShare", String(s)) } catch { /* storage unavailable */ } }
 const [info, setInfoState] = useState(() => { try { return localStorage.getItem("still.chatInfo") !== "closed" } catch { return true } })
 const [splitInfo, setSplitInfo] = useState(false) // beside a page, details stay closed until asked for
 const setInfo = (v: boolean) => { setInfoState(v); try { localStorage.setItem("still.chatInfo", v ? "open" : "closed") } catch { /* storage unavailable */ } }
 const companion = ai?.companions?.find(c => c.id === buddy) ?? companionOf(ai)
 // A chat or a home page shows in the Still app tab, in place, with its own Back and Forward (the host's Go).
 const view = active?.home || "home"
 const goHome = (v: HomeView) => send("appHome", { view: v })
 const setView = goHome
 const mine = ai?.incognito ? { ...ai, chats: ai.privateChats ?? [] } : ai // an incognito window lists only its own chats
 const role = premadeOf(companion), plugins = ai?.plugins
 const ideas = !companion ? [] : homeIdeas({ name: companion.name, role: role?.role, asks: role?.asks, fits: tasksFor(state.preferences.interests), uses: role?.uses, memory: companion.memory, activeId: active?.id, tabs: state.tabs,
  apps: plugins?.key && plugins.status !== "bad" ? plugins.connected.filter(c => !companion.pluginsOff?.includes(c.slug)) : [] })
 const [typing, setTyping] = useState(false) // to the companion on the new tab: it listens
 const openAiSettings = () => { setAiView("settings"); if (!ai?.open) send("aiToggle") }
 // In a chat tab the viewer takes the page's place beside the chat; anywhere else it opens over the page.
 const openFile = (path: string) => { setViewing(path); if (split) send("chatPage", { on: false }) }
 const sideViewer = chatTab && !!viewing && !split
 useEffect(() => { setViewing("") }, [state.activeId, split])
 const suggestions = useMemo(() => rankSuggestions(query, state.history, state.bookmarks, active?.isPrivate, Date.now(), state.picks), [query, state.history, state.bookmarks, active?.isPrivate, state.picks])
 const learn = (url: string) => { if (!active?.isPrivate && query.trim()) send("addressPick", { typed: query.trim(), url }) }
 const addressRef = useRef<HTMLInputElement>(null)
 const paneRef = useRef("")
 const [pick, setPick] = useState(-1)
 const [ghost, setGhost] = useState<Ghost | null>(null)
 // A drag preview hides the page, so it must never outlive the drag: clear it on any release, focus loss or Esc.
 useEffect(() => {
  if (!ghost) return
  const clear = () => setGhost(null)
  const key = (e: KeyboardEvent) => { if (e.key === "Escape") clear() }
  addEventListener("pointerup", clear); addEventListener("blur", clear); addEventListener("keydown", key)
  return () => { removeEventListener("pointerup", clear); removeEventListener("blur", clear); removeEventListener("keydown", key) }
 }, [!!ghost])
 const [barOpen, setBarOpenState] = useState(() => { try { return localStorage.getItem("still.bookmarksBar") === "open" } catch { return false } })
 const setBarOpen = (v: boolean) => { setBarOpenState(v); try { localStorage.setItem("still.bookmarksBar", v ? "open" : "closed") } catch { /* storage unavailable */ } }
 const [arriving, setArriving] = useState("")
 const [entering, setEntering] = useState(true)
 const activeDownloads = state.downloads.filter(d => d.status === "InProgress")
 const dlProgress = (() => { const t = activeDownloads.reduce((n, d) => n + (d.total || 0), 0); return t > 0 ? activeDownloads.reduce((n, d) => n + d.bytes, 0) / t : 0.15 })()
 const [shownPermission, setShownPermission] = useState<State["permission"]>()
 const [completion, setCompletion] = useState("")
 const typedRef = useRef(false)
 useEffect(() => {
  if (pane !== "address" || !typedRef.current) { setCompletion(""); return }
  const q = query.toLowerCase()
  const hit = q.length > 0 && !/\s/.test(q) ? suggestions.find(v => v.host.toLowerCase().startsWith(q.replace(/^https?:\/\//, "").replace(/^www\./, ""))) : undefined
  const bare = query.replace(/^https?:\/\//i, "").replace(/^www\./i, "")
  setCompletion(hit ? hit.host.slice(bare.length) : "")
 }, [query, suggestions, pane])
 useLayoutEffect(() => {
  const el = addressRef.current
  if (el && pane === "address" && completion && document.activeElement === el) el.setSelectionRange(query.length, query.length + completion.length)
 }, [completion, query, pane])
 const addressItems = useMemo(() => {
  if (pane !== "address") return []
  const q = query.trim(), items: { key: string; icon: React.ReactNode; title: string; sub: string; value?: string; run: () => void }[] = []
  if (/^still:/i.test(q)) { const lower = q.toLowerCase(); STILL_PAGES.filter(p => ("still://" + p[0]).startsWith(lower) || lower.startsWith("still://" + p[0])).forEach(p => items.push({ key: "still." + p[0], icon: <Globe2 size={15} />, title: "still://" + p[0], sub: p[1], run: () => go("still://" + p[0]) })) }
  else if (q && q !== active?.url && !completion) items.push({ key: "go", icon: <Search size={15} />, title: q, sub: /^[^\s]+\.[^\s]+$/.test(q) || /^https?:/.test(q) ? "Go to address" : "Search " + state.preferences.search, run: () => go(q) })
  // Anything that isn't an address can go to the AI as a task.
  if (q && !state.noAi && !/^[^\s]+\.[^\s]+$/.test(q) && !/^[a-z]+:/i.test(q)) items.push({ key: "ai", icon: <Face size={16} />, title: q, sub: "Start a chat", run: () => { send("aiAsk", { text: q }); close() } })
  suggestions.forEach(v => items.push({ key: "s" + v.url, icon: <Globe2 size={15} />, title: v.host, sub: v.bookmark ? v.title + " · Bookmark" : "Visited", value: prettyUrl(v.url), run: () => { learn(v.url); go(v.url) } }))
  const lower = q.toLowerCase()
  state.tabs.filter(t => t.url && t.id !== state.activeId && (!q || q === active?.url || (t.title + t.url).toLowerCase().includes(lower))).slice(0, 4)
   .forEach(t => items.push({ key: "t" + t.id, icon: t.favicon ? <img className="tab-favicon" src={t.favicon} alt="" /> : <Globe2 size={15} />, title: t.title, sub: "Switch to tab", run: () => action("select", { id: t.id }) }))
  return items.slice(0, 9)
 }, [pane, query, completion, suggestions, state.tabs, state.activeId, active?.url, state.preferences.search, state.noAi])
 const pinned = state.tabs.filter(t => t.pinned)
 const ordinary = state.tabs.filter(t => !t.pinned && !t.aiGroup && !t.inChat)
 const aiTabs = state.tabs.filter(t => !t.pinned && t.aiGroup && !t.inChat)
 const aiGroup = (top: boolean) => aiTabs.length > 0 && <div className={cn("ai-tab-group", !top && "is-side")} role="group" aria-label="AI tabs"><span className="ai-tab-group-label"><Buddy size={16} />AI</span><FlowTabs tabs={aiTabs} top={top} /></div>
 useLayoutEffect(() => {
  const root = tabsRef.current
  const viewport = root?.matches('.top-tab-list') ? root : root?.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]')
  if (!root || !viewport) return
  const reveal = (start: number, size: number, scroll: number, available: number) => start < scroll ? start : start + size > scroll + available ? start + size - available : scroll
  const revealSelected = () => {
   const selected = root.querySelector<HTMLElement>('.is-selected')
   if (!selected) return
   const last = [...root.querySelectorAll('[data-tab-id]')].at(-1)
   const add = root.querySelector<HTMLElement>('[aria-label="New tab"]')
   for (const element of selected === last && add ? [selected, add] : [selected]) {
    // Layout offsets ignore entrance animations. At the end, reveal the inline button too.
    let x = 0, y = 0, node: HTMLElement | null = element
    while (node && node !== viewport) { x += node.offsetLeft; y += node.offsetTop; node = node.offsetParent as HTMLElement | null }
    if (node === viewport) viewport.scrollTo({ left: reveal(x, element.offsetWidth, viewport.scrollLeft, viewport.clientWidth), top: reveal(y, element.offsetHeight, viewport.scrollTop, viewport.clientHeight) })
   }
  }
  revealSelected()
  let frame = 0
  const observer = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(revealSelected) })
  observer.observe(viewport)
  return () => { observer.disconnect(); cancelAnimationFrame(frame) }
 }, [state.activeId, active?.pinned, state.tabs.length, state.focusMode, state.fullScreen, modern])
 useEffect(() => { paneRef.current = pane }, [pane])
 useEffect(() => { const t = setTimeout(() => setEntering(false), 700); return () => clearTimeout(t) }, [])
 useLayoutEffect(() => { if (pane !== "downloads") return; const r = document.querySelector('[aria-label="Downloads"]')?.getBoundingClientRect(); if (r) document.documentElement.style.setProperty("--dl-top", r.bottom + 8 + "px") }, [pane])
 useEffect(() => { if (state.permission) setShownPermission(state.permission) }, [state.permission])
 const working = state.agent?.pending ? undefined : state.agent
 // The page in view, beside a chat or in its own tab, and whether an AI is driving it right now.
 const shownPage = split ? state.tabs.find(t => t.id === state.chatPage?.id) : active
 const driven = working && shownPage?.agent && working.tab === shownPage.id && !shownPage.isPrivate ? shownPage : undefined
 const oldName = state.welcome || state.secondary ? undefined : ai?.companions?.find(c => c.askName) // a companion with an old stock name, asked once
 const modal = !!oldName || (!!pane && pane !== "find") || menu || context || !!confirm || !!ghost || !!state.welcome || !!upload || extMenu || !!state.dialog || !!editing || !!profile || library || !!meeting || (!!viewing && !sideViewer) || tasksOpen || replay
 const [dialogText, setDialogText] = useState("")
 useEffect(() => { setDialogText(state.dialog?.defaultText ?? "") }, [state.dialog?.id, state.dialog?.message])
 const answerDialog = (accept: boolean) => { if (state.dialog) send("dialogAnswer", { id: state.dialog.id, accept, text: dialogText }) }
 const findOpen = pane === "find"

 function open(name: string, value = "") { if (window.chrome?.webview) { send("openPanel", { name, value }); return } setQuery(value); setFilter(""); setDisplayPane(name); setPane(name) }
 function close() { setPane(""); send("panel", { name: "" }) }
 function go(url: string) {
  const page = stillPage(url)
  if (page === undefined) { close(); send("navigate", { url }) }
  else if (!page) { close(); toast("Still has no page called " + url.trim() + ". Try still://chats or still://settings.") }
  else if (page[2]) { close(); goHome(page[2]) }
  else if (page[0] === "help") { close(); send("new", { url: HELP }) }
  else open(page[0])
 }
 function action(op: string, payload: Record<string, unknown> = {}) { close(); send(op, payload) }
 function preference(key: string, value: string) { send("preference", { key, value }) }

 useEffect(() => {
  const listener = (e: MessageEvent) => {
   const data = e.data
   if (data.kind === "state") setState(data)
   if (data.kind === "ai") { setAi(data.data); resumeOffer(data.data.interrupted ?? []) }
   if (data.kind === "file") setFileData(data.data)
   if (data.kind === "attached") dispatchEvent(new CustomEvent("still-attached", { detail: data }))
   if (data.kind === "pluginCatalog" || data.kind === "pluginLogos") dispatchEvent(new CustomEvent("still-" + data.kind, { detail: data.data }))
   if (data.kind === "tools") setToolData(old=>({...old,[data.name]:data.data}))
   if (data.kind === "panel") { setPane(data.name); if (data.name) { commandChoice.current=false; setDisplayPane(data.name); setQuery(data.value ?? ""); setFilter(""); if (data.name === "settings") { setSettingsFind(""); setSettingsPage(OLD_PAGES[data.value] ?? (data.value || "general")) } } }
   if (data.kind === "toast") { toast(data.message);setNotice(data.message) }
   if (data.kind === "snapshot") { setSnapshot(data.data); setPairShot(data.partner ?? "") }
   if (data.kind === "upload") setUpload(data.data)
   if (data.kind === "recent") setRecent({ ids: data.ids, index: data.index })
   if (data.kind === "groupRename") setRenaming(data.id)
   if (data.kind === "tasks") { if (document.querySelector(".tasks-button")) window.dispatchEvent(new Event("still-tasks")); else toast("Nothing is running right now.") }
   if (data.kind === "tabArrived") { setArriving(data.id); setTimeout(() => setArriving(""), 700) }
   if (data.kind === "pointerAway") { const root = document.documentElement; root.classList.add("pointer-away"); addEventListener("pointermove", () => root.classList.remove("pointer-away"), { once: true }) }
   if (data.kind === "escape") {
    // Still's window takes Esc before the page: the top layer (an open dropdown, the settings search, a dialog) gets it first.
    const esc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })
    ;(document.activeElement ?? document).dispatchEvent(esc)
    if (!esc.defaultPrevented) { setViewing(""); setUpload(u => { if (u) send("uploadAnswer", { id: u.id }); return null }); setPane(""); setMenu(false); setContext(false); setConfirm(null); send("panel", { name: "" }) }
   }
  }
  window.chrome?.webview?.addEventListener("message", listener)
  send("ready")
  return () => window.chrome?.webview?.removeEventListener("message", listener)
 }, [])
 useEffect(() => { document.documentElement.classList.toggle("dark", state.dark) }, [state.dark])
 useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(""),6500);return()=>clearTimeout(timer)},[notice])
 useEffect(()=>setNotice(""),[state.activeId,active?.url]) // a notice is for the page it came on: another page or tab shows its own address
 useEffect(() => {
  if (modal) { send("overlay", { value: true }); return }
  const timer = setTimeout(() => send("overlay", { value: false }), reduced ? 0 : 210)
  return () => clearTimeout(timer)
 }, [modal, reduced])
 useEffect(() => {
  if (pane === "address") { const t = setTimeout(() => { if (document.activeElement !== addressRef.current) { addressRef.current?.focus(); addressRef.current?.select() } }, 30); return () => clearTimeout(t) }
  // A closed address bar must not keep focus: when the window gets focus back, it would reopen over Settings or a dialog.
  if (document.activeElement === addressRef.current) addressRef.current?.blur()
  if (pane === "tabs") {
   const t = setTimeout(() => { commandRef.current?.focus(); commandRef.current?.select() }, 90)
   return () => clearTimeout(t)
  }
 }, [pane])
 useLayoutEffect(() => {
  const element = pageRef.current
  if (!element) return
  const sync = () => { const r = element.getBoundingClientRect(); send("bounds", { x: r.x, y: r.y, width: r.width, height: r.height, viewportWidth: innerWidth }) }
  const observer = new ResizeObserver(sync); observer.observe(element); sync()
  return () => observer.disconnect()
 }, [state === initial, state.focusMode, state.fullScreen, findOpen, chatTab, split, railOpen]) // the page slot appears with the first state
 useEffect(() => {
  const handler = (e: KeyboardEvent) => {
   if (e.key === "F11") { e.preventDefault(); send("fullscreen"); return }
   if (e.key === "Escape") { if (e.defaultPrevented) return; if(!document.querySelector(":is([role=dialog],[role=alertdialog],[role=menu]):not([aria-hidden=true])")){send("exitFullscreen");setViewing("")} close(); return }
   if (!(e.ctrlKey || e.metaKey)) return
   if (e.key === "Enter" && approveCard()) { e.preventDefault(); return }
   if (e.key.toLowerCase() === "l") { e.preventDefault(); openAddress() }
   if (e.key.toLowerCase() === "k" && !e.shiftKey) { e.preventDefault(); open("tabs") }
  }
  window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler)
 }, [active?.url])

 const commandOpen = pane === "tabs"
 const openAddress = (_el?: Element | null) => { addressRef.current?.focus() }
 const dialogOpen = !!pane && !commandOpen && pane !== "find" && pane !== "address" && pane !== "downloads" && pane !== "recent"
 const title = ({ profiles:"Profiles", import:"Import browsing data", passwords:"Passwords", extensions:"Extensions", cookies:"Cookies", security:"Privacy & security", settings: "Settings", history: "History", bookmarks: "Bookmarks", downloads: "Downloads", site: host(active?.url ?? "") || "Site controls", shortcuts: "Keyboard shortcuts", about: "Still" } as Record<string, string>)[displayPane] ?? ""
 const filtered = (displayPane === "bookmarks" ? state.bookmarks : state.history).filter(v => (v.title + v.url).toLowerCase().includes(filter.toLowerCase())).slice(0, 100)
 const windowControls = (
<div className="window-controls" aria-label="Window controls">
     <AnimatedButton variant="ghost" size="icon" className="window-control" aria-label="Minimize" onClick={()=>send("minimize")} whileHover={{scale:1.06}} whileTap={{scale:.9}} transition={FLOW}><Minus /></AnimatedButton>
     <AnimatedButton variant="ghost" size="icon" className="window-control" aria-label={state.maximized ? "Restore" : "Maximize"} onClick={()=>send("maximize")} whileHover={{scale:1.06}} whileTap={{scale:.9}} transition={FLOW}>{state.maximized?<Copy/>:<Square/>}</AnimatedButton>
     <AnimatedButton variant="ghost" size="icon" className="window-control window-close" aria-label="Close Still" onClick={()=>send("closeWindow")} whileHover={{scale:1.06}} whileTap={{scale:.9}} transition={FLOW}><X /></AnimatedButton>
    </div>
 )
 // Hidden until Still sends its state, or the stand-in would flash a browser before the welcome. It still renders, so the
 // page's bounds and every other measurement are in place when it shows.
 useLayoutEffect(() => { document.documentElement.classList.toggle("is-waiting", state === initial) }, [state])
 const hasAi = !!ai && !state.noAi
 const pageName = (id: string) => SETTING_PAGES.find(p => p[0] === id)?.[1] ?? ""
 const found = settingsFind.trim() ? [...SETTINGS_FIND, ...shortcuts.map(([label], i): Finding => ["key-" + i, "shortcuts", label, "keyboard key"])].filter(([id, page, label, more]) =>
  (hasAi || !AI_PAGES.includes(page)) && !(id === "talk" && !hasAi) && !(["askInChat", "dev"].includes(id) && !state.preferences.agents) && !(id === "dev" && !state.mcpCommand) && !(["ai", "titles"].includes(id) && !hasAi) &&
  settingsFind.toLowerCase().split(/\s+/).filter(Boolean).every(w => `${label} ${more} ${pageName(page)}`.toLowerCase().includes(w))).slice(0, 12) : []
 const jumpTo = (f: Finding) => { setSettingsFind(""); setSettingsPage(f[1]); setFlash(f[0]) }
 const about = <div className="about-content"><div className="still-mark"><i /><i /></div><p>The open-source agent browser that runs on the AI you already pay for. Claude, ChatGPT or Grok, through their own apps, with no API keys. Switch AI anytime, even halfway through a task, and let your other AI apps drive it through MCP or the command line.</p><ul className="about-points"><li>Your companion works in its own background tabs and asks before anything that matters. Private tabs, passwords and cookies stay off-limits.</li><li>Every other AI app asks first, and you say yes once.</li>{MAC ? <><li>Your tabs, history and passwords stay on this Mac, with passwords in your Keychain.</li><li>Ad and tracker blocking, private windows and separate profiles built in.</li><li>Imports bookmarks, history and passwords from Chrome, Firefox, Edge, Brave and Arc, plus Safari bookmarks and any password CSV.</li></> : <><li>Your tabs, history and passwords stay on this PC, with passwords encrypted by Windows.</li><li>Ad and tracker blocking, private tabs, extensions and separate profiles built in.</li><li>Imports everything from Chrome, Edge, Brave and Opera GX, including sign-ins, and bookmarks, history and passwords from Firefox.</li></>}</ul>{state.update ? <div className="flex gap-2"><Button disabled={state.update.busy && state.update.ready} onClick={() => send("openUpdate")}>{state.update.busy ? <><Loader2 className="spin" />{state.update.ready ? "Restarting…" : `Updating… ${state.update.progress ?? 0}%`}</> : <><Download />Update to Still {state.update.version}</>}</Button><Button variant="ghost" onClick={() => send("releaseNotes")}>What's new</Button></div> : <Button variant="outline" onClick={() => send("checkUpdate")}><RotateCw />Check for updates</Button>}<Button variant="ghost" className="about-replay" onClick={() => { close(); setReplay(true) }}><Sparkles />Replay the intro</Button><p className="text-xs text-muted-foreground">{MAC ? "Still checks for new versions and shows you where to download them." : "Still updates itself automatically. New versions download in the background and install the next time you close Still."}</p><p className="text-xs text-muted-foreground">Version {state.version ?? "2.0.0"} · Powered by {MAC ? "WebKit" : "Microsoft Edge WebView2"}</p></div>
 return <UICtx.Provider value={{state,ai,setContext,open,arriving,setGhost,renaming,setRenaming}}><CompanionContext.Provider value={companionOf(ai, ai?.chatCompanion)}><MotionConfig reducedMotion="user" transition={FLOW}><TooltipProvider delayDuration={650}><MascotStage />
  <div className={cn("browser-shell", modern ? "modern-layout" : "horizontal-layout", state.fullScreen && "is-fullscreen", entering && state.secondary && "window-enter", state.incognito && "is-incognito")} data-reduced-motion={!!reduced}>
   {modern && split && <div className="top-tab-strip modern-strip" onDoubleClick={e => { if (e.target === e.currentTarget) send("maximize") }} onPointerDown={e => { if (e.button === 0 && e.target === e.currentTarget) send("drag") }}>{windowControls}</div>}
   {!modern && !state.focusMode && !state.fullScreen && <div className="top-tab-strip" onDoubleClick={e => { if (e.target === e.currentTarget || (e.target as HTMLElement).classList.contains("top-tab-list")) send("maximize") }} onPointerDown={e => { if (e.button === 0 && (e.target === e.currentTarget || (e.target as HTMLElement).classList.contains("top-tab-list"))) send("drag") }}><LayoutGroup id="top"><div className="top-tab-list" ref={tabsRef} onWheel={e => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && e.currentTarget.scrollWidth > e.currentTarget.clientWidth) e.currentTarget.scrollLeft += e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? e.currentTarget.clientWidth : 1) }}><TabStrip tabs={[...pinned, ...ordinary]} top />{aiGroup(true)}<Button variant="ghost" size="icon-sm" className="top-new-tab" aria-label="New tab" title="New tab · Ctrl+T" onClick={() => send("new")}><Plus /></Button></div></LayoutGroup>{windowControls}</div>}
   {!split && <header className="window-bar" onDoubleClick={e => { if (e.target === e.currentTarget) send("maximize") }} onPointerDown={e => { if (e.button === 0 && e.target === e.currentTarget) send("drag") }}>
    <nav className="nav-controls" aria-label="Page navigation">
     <IconButton label="Back" disabled={!state.canBack} onClick={() => send("back")}><ArrowLeft /></IconButton>
     <IconButton label="Forward" disabled={!state.canForward} onClick={() => send("forward")}><ArrowRight /></IconButton>
     <IconButton label={active?.loading ? "Stop loading" : "Reload"} caption={active?.loading?"Stop":"Reload"} onClick={() => send("reload")}>{active?.loading ? <X /> : <RotateCw />}</IconButton>
    </nav>
    {state.incognito && <span className="incognito-badge"><LockKeyhole />Incognito</span>}
    {!chatTab && /^https?:/.test(active?.url ?? "") && <SitePermissions origin={new URL(active!.url).origin} inUse={active!.inUse ?? ""} data={toolData.site ?? {}} send={send} onOpenChange={setContext} onSettings={() => open("security")} />}
    <ContextMenu onOpenChange={setContext}><ContextMenuTrigger asChild>
    <div className={cn("address-bar", pane === "address" && "is-editing", chatTab && pane !== "address" && "is-chat")} onMouseDown={e => { if (e.target === e.currentTarget) { e.preventDefault(); addressRef.current?.focus() } }}>
     {active?.isPrivate ? <LockKeyhole /> : active?.secure ? <Shield /> : <Search />}
     <input ref={addressRef} className="address-input" aria-label="Search or enter an address" spellCheck={false} autoComplete="off"
      placeholder="Search or enter an address"
      value={pane === "address" ? (pick >= 0 && addressItems[pick]?.value ? addressItems[pick].value! : query + completion) : (notice || (active?.chatId ? "Chat / " + (chatOf(ai, active.chatId)?.title ?? active.title) : active?.url ? prettyUrl(active.url) : ""))}
      onFocus={e => { if (pane !== "address") { typedRef.current = false; setQuery(active?.url ?? ""); setPick(-1); setPane("address"); setDisplayPane("address"); send("openPanel", { name: "address", value: active?.url ?? "" }) } requestAnimationFrame(() => e.target.select()) }}
      onChange={e => { const ne = e.nativeEvent as InputEvent; const del = (ne.inputType ?? "").startsWith("delete"); typedRef.current = !del; if (del) setCompletion(""); setQuery(e.target.value); setPick(-1) }}
      onKeyDown={e => {
       const count = addressItems.length
       if (e.key === "ArrowDown") { e.preventDefault(); setPick(p => Math.min(count - 1, p + 1)) }
       else if (e.key === "ArrowUp") { e.preventDefault(); setPick(p => Math.max(-1, p - 1)) }
       else if ((e.key === "Tab" && !e.shiftKey || e.key === "ArrowRight") && completion) { e.preventDefault(); typedRef.current = false; setQuery(query + completion); setCompletion("") }
       else if (e.key === "Tab" && !e.shiftKey && suggestions.length) { e.preventDefault(); typedRef.current = false; setQuery(suggestions[0].host) }
       else if (e.key === "Enter") { e.preventDefault(); const item = pick >= 0 ? addressItems[pick] : null; if (item) item.run(); else if (completion) { const hit = suggestions.find(v => v.host.toLowerCase() === (query + completion).toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "")); if (hit) learn(hit.url); go(query + completion) } else if (query.trim()) go(query); addressRef.current?.blur() }
       else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); addressRef.current?.blur() }
      }}
      onBlur={() => { setTimeout(() => { if (document.activeElement !== addressRef.current && paneRef.current === "address") close() }, 120) }} />
     {pane !== "address" && <kbd>{keys("Ctrl L")}</kbd>}
     {pane === "address" && addressItems.length > 0 && <div className="address-suggest" role="listbox" onMouseDown={e => e.preventDefault()}>
      {addressItems.map((item, i) => <button key={item.key} role="option" aria-selected={i === pick} className={cn("address-option", i === pick && "is-picked")} onMouseEnter={() => setPick(i)} onClick={() => { item.run(); addressRef.current?.blur() }}>
       <span className="address-option-icon">{item.icon}</span><span className="address-option-main">{item.title}</span><small>{item.sub}</small>
      </button>)}
     </div>}
    </div>
    </ContextMenuTrigger><ContextMenuContent className="w-48">
     <ContextMenuItem disabled={!active?.url} onSelect={() => { send("copyText", { text: active?.url ?? "" }); setNotice("Link copied") }}><Copy />Copy link</ContextMenuItem>
     <ContextMenuItem onSelect={() => openAddress(document.querySelector(".address-bar"))}><Pencil />Edit address</ContextMenuItem>
    </ContextMenuContent></ContextMenu>
    <div className="page-tools">
     {!state.noAi && ai && <><RunningTasks ai={ai} send={send} onOpen={setTasksOpen} tabs={state.tabs} /><RunAnnouncer ai={ai} /></>}
     {!state.noAi && !active?.chatId && <Button variant="outline" size="sm" className={cn("ai-pill", ai?.open && "is-open")} aria-pressed={!!ai?.open} title="Chat about this page · Ctrl+Shift+A" onClick={() => { setAiView("chat"); send("aiToggle") }}><Face companion={companionOf(ai, ai?.chatCompanion)} size={34} mood={ai?.busy ? "working" : "idle"} />Chat</Button>}
     {!chatTab && <><IconButton label="Bookmark this page" caption="Bookmark" onClick={() => send("bookmark")}><Bookmark className={state.bookmarks.some(b => b.url === active?.url) ? "bookmarked" : ""} /></IconButton>
     <IconButton label={state.siteBlocking === false && state.preferences.blocking && active?.url ? "Site controls (ad blocking is off here)" : "Site controls"} caption="Site" onClick={() => open("site")}>{state.siteBlocking === false && state.preferences.blocking && active?.url ? <ShieldOff className="text-amber-500" /> : <Shield />}</IconButton>
     <IconButton label="Reading mode" caption="Reader" onClick={() => send("reader")}><BookOpen /></IconButton></>}
     {state.update && <Button size="sm" className={cn("update-pill", state.update.busy && "is-busy")} disabled={state.update.busy && state.update.ready} onClick={() => send("openUpdate")} title={state.update.downloading ? `Downloading Still ${state.update.version} in the background. It installs when you close Still, or click to install as soon as it’s ready.` : state.update.ready ? `Still ${state.update.version} is ready. Click to install now and reopen with your tabs, or it installs when you close Still.` : `Update Still to ${state.update.version}. It installs automatically and reopens with your tabs.`}>
      {state.update.busy || state.update.downloading ? <Loader2 className="spin" /> : <Download />}
      {state.update.busy && state.update.ready ? "Restarting…" : state.update.busy || state.update.downloading ? `Updating Still… ${state.update.progress ?? 0}%` : state.update.ready ? "Restart to update" : "Update"}
     </Button>}
     <IconButton label="Downloads" onClick={() => open("downloads")}><span className="dl-icon"><Download />{activeDownloads.length > 0 && <i className="dl-mini"><b style={{ width: Math.max(8, dlProgress * 100) + "%" }} /></i>}</span></IconButton>
     <IconButton label="Passwords" onClick={()=>open("passwords")}><KeyRound />{state.loginOffer&&<i className="login-dot" aria-label="Login ready to save"/>}</IconButton>
     {!state.noExtensions && state.pinnedExtensions?.map(x => <IconButton key={x.id} label={x.name} caption={x.name} onClick={e => { const r = e.currentTarget.getBoundingClientRect(); send("extensionAction", { id: x.id, anchor: [r.x, r.y, r.width, r.height] }) }}><ExtensionIcon icon={x.icon} /></IconButton>)}
     {!state.noExtensions && <DropdownMenu open={extMenu} onOpenChange={o => { setExtMenu(o); if (o) send("extensionMenu") }}><DropdownMenuTrigger asChild><Button ref={extButton} variant="ghost" size="icon-sm" aria-label="Extensions" className="chrome-button expanding-button"><span className="chrome-icon"><Puzzle /></span><span className="chrome-label" aria-hidden="true"><span>Extensions</span></span></Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={10} className="w-60">
       {toolData.extensions?.extensions === undefined ? <DropdownMenuItem disabled><Loader2 className="animate-spin" />Loading…</DropdownMenuItem>
        : toolData.extensions.extensions.filter(e => e.enabled).length === 0 ? <DropdownMenuItem disabled>No extensions turned on</DropdownMenuItem>
        : toolData.extensions.extensions.filter(e => e.enabled).map(e => { const pinned = !!state.pinnedExtensions?.some(p => p.id === e.id); return <DropdownMenuItem key={e.id} className="ext-menu-item" onSelect={() => {
          const r = extButton.current?.getBoundingClientRect()
          send("extensionAction", { id: e.id, anchor: r ? [r.x, r.y, r.width, r.height] : null })
         }}><ExtensionIcon icon={e.icon} /><span className="truncate flex-1">{e.name}</span><Button variant="ghost" size="icon-xs" className={cn("ext-pin", pinned && "is-pinned")} aria-label={(pinned ? "Unpin " : "Pin ") + e.name} title={pinned ? "Unpin from toolbar" : "Pin to toolbar"} onClick={ev => { ev.preventDefault(); ev.stopPropagation(); send("extensionPin", { id: e.id }) }}>{pinned ? <PinOff /> : <Pin />}</Button></DropdownMenuItem> })}
       <DropdownMenuSeparator />
       <DropdownMenuItem onSelect={() => open("extensions")}><Settings2 />Manage extensions</DropdownMenuItem>
      </DropdownMenuContent></DropdownMenu>}
     <DropdownMenu open={menu} onOpenChange={setMenu}><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Menu" className="chrome-button expanding-button"><span className="chrome-icon"><MoreHorizontal /></span><span className="chrome-label" aria-hidden="true"><span>Menu</span></span></Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={10} className="w-60">
       <DropdownMenuItem onSelect={() => send("new")}><Plus />New tab<DropdownMenuShortcut>{keys("Ctrl T")}</DropdownMenuShortcut></DropdownMenuItem>
       <DropdownMenuItem onSelect={() => send("incognitoWindow")}><LockKeyhole />New incognito window<DropdownMenuShortcut>Ctrl Shift N</DropdownMenuShortcut></DropdownMenuItem>
       <DropdownMenuItem onSelect={() => send("reopen")}><RotateCw />Reopen closed tab</DropdownMenuItem>
       <DropdownMenuSeparator />
       <MenuPanelItem name="profiles" label="Profiles" icon={<UsersRound />} />
       <MenuPanelItem name="import" label="Import browsing data" icon={<Import />} />
       <MenuPanelItem name="passwords" label="Passwords" icon={<KeyRound />} />
       <MenuPanelItem name="extensions" label="Extensions" icon={<Puzzle />} />
       <MenuPanelItem name="cookies" label="Cookies" icon={<Cookie />} />
       <MenuPanelItem name="security" label="Privacy & security" icon={<ShieldCheck />} />
       <DropdownMenuSeparator />
       <div className="zoom-controls"><span>Zoom</span><Button variant="ghost" size="icon-sm" aria-label="Zoom out" onClick={()=>send("zoom",{amount:-.1})}><Minus /></Button><Button variant="ghost" size="sm" aria-label="Reset page zoom" onClick={()=>send("zoom",{amount:0})}>{state.zoom}%</Button><Button variant="ghost" size="icon-sm" aria-label="Zoom in" onClick={()=>send("zoom",{amount:.1})}><Plus /></Button></div>
       <DropdownMenuSeparator />
       <MenuPanelItem name="bookmarks" label="Bookmarks" icon={<Bookmark />} />
       <MenuPanelItem name="history" label="History" icon={<History />} keys="Ctrl H" />
       <MenuPanelItem name="downloads" label="Downloads" icon={<Download />} keys="Ctrl J" />
       <MenuPanelItem name="find" label="Find in page" icon={<Search />} keys="Ctrl F" />
       <DropdownMenuItem onSelect={()=>send("reader")}><BookOpen/>Reading mode</DropdownMenuItem>
       <DropdownMenuItem onSelect={() => send("pictureInPicture")}><ExternalLink />Picture in picture</DropdownMenuItem>
       <DropdownMenuSeparator />
       <DropdownMenuItem onSelect={() => send("fullscreen")}><Expand />Full screen<DropdownMenuShortcut>{MAC ? "⌃⌘F" : "F11"}</DropdownMenuShortcut></DropdownMenuItem>
       <DropdownMenuItem onSelect={() => send("focus")}><Expand />{state.focusMode ? "Leave focus mode" : "Focus mode"}</DropdownMenuItem>
       <DropdownMenuItem onSelect={() => preference("tabLayout", state.preferences.tabLayout === "Modern" ? "Classic" : "Modern")}><PanelLeft />{state.preferences.tabLayout === "Modern" ? "Tabs on top" : "Tabs on the side"}<DropdownMenuShortcut>Ctrl Shift S</DropdownMenuShortcut></DropdownMenuItem>
       <MenuPanelItem name="settings" label="Settings" icon={<Settings2 />} keys="Ctrl ," />
       <MenuPanelItem name="about" label="About Still" icon={<Info />} />
      </DropdownMenuContent>
     </DropdownMenu>
    </div>
    {modern && windowControls}
   </header>}
   <div className="workspace">
    {modern && <aside className="browser-sidebar" aria-label="Tabs">
     <div className="sidebar-resize" role="separator" aria-label="Resize the sidebar" aria-orientation="vertical" aria-valuenow={state.preferences.sidebarWidth ?? 248} aria-valuemin={190} aria-valuemax={360} tabIndex={0}
      onKeyDown={e => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); send("sidebarResize", { width: (state.preferences.sidebarWidth ?? 248) + (e.key === "ArrowRight" ? 10 : -10) }) } }}
      onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); resize.current = { x: e.clientX, width: e.currentTarget.parentElement!.getBoundingClientRect().width, current: state.preferences.sidebarWidth ?? 248 } }}
      onPointerMove={e => { if (resize.current) { const value = Math.max(190, Math.min(360, resize.current.width + e.clientX - resize.current.x)); resize.current.current = value; document.documentElement.style.setProperty("--sidebar-width", value + "px") } }}
      onPointerUp={() => { if (resize.current) { send("sidebarResize", { width: resize.current.current }); resize.current = null } }}
      onPointerCancel={() => { resize.current = null; document.documentElement.style.setProperty("--sidebar-width", (state.preferences.sidebarWidth ?? 248) + "px") }} />
     <ScrollArea className="tabs-scroll" ref={tabsRef}><LayoutGroup id="side">
      {pinned.length > 0 && <div className="pinned-tabs"><FlowTabs tabs={pinned} /></div>}
      <nav className="sidebar-links" aria-label="Go to">
       <Button variant="ghost" className="sidebar-link" onClick={() => send("new")}><Plus /><span>New tab</span><kbd>{keys("Ctrl T")}</kbd></Button>
       {ai && !state.noAi && <><Button variant="ghost" className="sidebar-link" onClick={() => goHome("chats")}><MessageSquare /><span>Chat history</span></Button>
       <Button variant="ghost" className="sidebar-link" onClick={() => goHome("library")}><Library /><span>Library</span></Button></>}
      </nav>
      {ordinary.some(t => t.chatId) && <><h3 className="sidebar-head">Chats</h3><div className="tab-list"><FlowTabs tabs={ordinary.filter(t => t.chatId)} /></div></>}
      <h3 className="sidebar-head">Tabs</h3>
      <div className="tab-list"><TabStrip tabs={ordinary.filter(t => !t.chatId)} top={false} /></div>
      {aiGroup(false)}
     </LayoutGroup></ScrollArea>
     <footer className="sidebar-footer">
      <Button variant="ghost" size="icon-sm" aria-label="Settings" title="Settings" onClick={() => open("settings")}><Settings2 /></Button>
      <Button variant="ghost" className="still-signature" onClick={() => open("about")}>still<span>{state.profileName}</span></Button>
     </footer>
    </aside>}
    {chatTab && ai && !state.focusMode && !state.fullScreen && <ChatSide ai={ai} state={state} activeChat={active?.chatId} open={railOpen} setOpen={setRailOpen} split={split} onEdit={edit} onSettings={openAiSettings} openPanel={open} goHome={goHome} />}
    <main className={cn("page-column", chatTab && "is-chat", split && "is-split", sideViewer && "is-viewing")}>
     {pane === "find" && <div className="find-bar"><Input autoFocus placeholder="Find on this page" aria-label="Find in page" value={filter} onChange={e => setFilter(e.target.value)} onKeyDown={e => { if (e.key === "Enter") send("find", { text: filter }) }} /><Button variant="ghost" size="sm" onClick={() => send("find", { text: filter })}>Next</Button><Button variant="ghost" size="icon-sm" aria-label="Close find" onClick={close}><X /></Button></div>}
     {!state.focusMode && !state.fullScreen && state.bookmarks.length > 0 && <nav className={cn("bookmarks-bar", barOpen && state.bookmarks.length >= 5 && "is-expanded")} aria-label="Bookmarks bar">
      <div className="bookmarks-bar-list">{state.bookmarks.slice(0, barOpen ? 200 : 40).map(b => <BookmarkMenu key={b.url} b={b} onEdit={editBookmark}><Button variant="ghost" size="sm" className="bookmark-chip" title={b.title + " · " + b.url} onClick={() => send("navigate", { url: b.url })}><span className="bookmark-letter">{b.favicon ? <img src={b.favicon} alt="" /> : (host(b.url)[0] ?? "•").toUpperCase()}</span><span className="bookmark-name">{b.title || host(b.url)}</span></Button></BookmarkMenu>)}</div>
      {state.bookmarks.length >= 5 && <Button variant="ghost" size="icon-sm" className="bookmark-toggle" aria-expanded={barOpen} aria-label={barOpen ? "Collapse bookmarks" : "Expand bookmarks"} title={barOpen ? "Show one row" : `Show all ${state.bookmarks.length} bookmarks`} onClick={() => setBarOpen(!barOpen)}><ChevronRight /></Button>}
      <Button variant="ghost" size="sm" className="bookmark-chip bookmark-all" onClick={() => open("bookmarks")}><Bookmark />All bookmarks</Button>
     </nav>}
     <div className={cn("permission-wrap", state.agent?.pending && "is-open")}><div className="permission-bar agent-bar is-asking" role="alertdialog" aria-label="AI agent" aria-hidden={!state.agent?.pending}>
      {state.agent?.client ? <AiLogo id={state.agent.client} size={20} /> : <Bot />}<span>{state.agent?.ask
       ? <><b>{state.agent.client}</b> wants to {state.agent.ask}.</>
       : <><b>{state.agent?.client}</b> wants to control Still. It can open, read and click pages, but never private tabs, passwords or cookies.</>}</span>
      <Button variant="ghost" size="sm" onClick={() => send("agentAnswer", { allow: false })}>Block</Button><Button size="sm" onClick={() => send("agentAnswer", { allow: true })}>Allow</Button>
     </div></div>
     <div className={cn("permission-wrap", state.permission && "is-open")}><div className="permission-bar" role="alertdialog" aria-label="Site permission" aria-hidden={!state.permission}>
      <ShieldCheck /><span><b>{shownPermission?.site}</b> wants to {shownPermission?.kind}.</span>
      <Button variant="ghost" size="sm" disabled={!state.permission} onClick={() => state.permission && send("permissionAnswer", { id: state.permission.id, allow: false })}>Block</Button>
      <Button size="sm" disabled={!state.permission} onClick={() => state.permission && send("permissionAnswer", { id: state.permission.id, allow: true })}>Allow</Button>
     </div></div>
     <SaveLoginBar offer={state.loginOffer} send={send} />
     <div className="page-row">
     {chatTab && ai && <section className={cn("chat-pane", (split ? splitInfo : info) && "has-info")} style={split ? { width: `${Math.round(chatShare * 100)}%` } : undefined}>
      {split && <div className="chat-divider" role="separator" aria-label="Resize the chat" aria-orientation="vertical" aria-valuenow={Math.round(chatShare * 100)} tabIndex={0}
       onKeyDown={e => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); shareChat(chatShare + (e.key === "ArrowRight" ? .04 : -.04)) } }}
       onDoubleClick={() => shareChat(.4)}
       onPointerDown={e => e.currentTarget.setPointerCapture(e.pointerId)}
       onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; const r = e.currentTarget.parentElement!.parentElement!.getBoundingClientRect(); shareChat((e.clientX - r.left) / r.width, false) }}
       onPointerUp={() => shareChat(chatShare)} />}
      <div className="chat-tools">
       {split && !state.noAi && <RunningTasks ai={ai} send={send} onOpen={setTasksOpen} tabs={state.tabs} />}
       <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Chat options" title="Chat options"><MoreHorizontal /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
         <DropdownMenuItem onSelect={() => goHome("home")}><SquarePen />New chat</DropdownMenuItem>
         <DropdownMenuItem disabled={isRunning(ai, active.chatId)} onSelect={() => send("aiDeleteChat", { id: active.chatId })}><Trash2 />Delete chat</DropdownMenuItem>
        </DropdownMenuContent></DropdownMenu>
       <Button variant="ghost" size="icon-sm" aria-label="Chat details" title="Chat details" aria-pressed={split ? splitInfo : info} className={cn((split ? splitInfo : info) && "is-on")} onClick={() => split ? setSplitInfo(!splitInfo) : setInfo(!info)}><Info /></Button>
       {chatPages.length > 0 && <Button variant="ghost" size="icon-sm" aria-label={split ? "Hide the page" : "Show the page"} title={split ? "Hide the page" : "Show the page"} onClick={() => send("chatPage", { on: !split })}>{split ? <PanelRightClose /> : <PanelRightOpen />}</Button>}
      </div>
      {/* Only once the chat's own messages are here: the tab and the chat can arrive one after the other (the Mac sends the chat first) */}
      {(!ai.chatId || ai.chatId === active.chatId) && <ChatView key={active.chatId} ai={ai} send={send} mode="tab" tabs={state.tabs} onSettings={openAiSettings} onFile={openFile} interests={state.preferences.interests} />}
      {(split ? splitInfo : info) && <ChatInfo ai={ai} pages={chatPages} onEdit={edit} onSettings={openAiSettings} onFile={openFile} />}
     </section>}
     <div className="page-pane">
     {split && chatPages.length > 1 && <div className="page-tabs" role="tablist" aria-label={`${companion?.name ?? "Your companion"}'s tabs`}>{chatPages.map(p => <button key={p.id} role="tab" aria-selected={p.url === state.chatPage?.url} title={p.url} onClick={() => send("chatPage", { on: true, id: p.id })}>{p.favicon ? <img src={p.favicon} alt="" /> : <Globe2 />}<span>{p.title || host(p.url)}</span>{p.agent && <i aria-label="Working" />}</button>)}</div>}
     {split && state.chatPage && <div className="page-nav">
      <Button variant="ghost" size="icon-sm" aria-label="Back" disabled={!state.canBack} onClick={() => send("back")}><ArrowLeft /></Button>
      <Button variant="ghost" size="icon-sm" aria-label="Forward" disabled={!state.canForward} onClick={() => send("forward")}><ArrowRight /></Button>
      <Button variant="ghost" size="icon-sm" aria-label={state.chatPage.loading ? "Stop loading" : "Reload"} onClick={() => send("reload")}>{state.chatPage.loading ? <X /> : <RotateCw />}</Button>
      <span className="page-nav-url" title={state.chatPage.url}>{state.chatPage.loading ? <Loader2 className="spin" /> : state.chatPage.favicon ? <img src={state.chatPage.favicon} alt="" /> : <Globe2 />}<b>{host(state.chatPage.url)}</b>{state.chatPage.title && <span>&nbsp;/ {state.chatPage.title}</span>}</span>
      <Button variant="ghost" size="icon-sm" aria-label="Bookmark this page" title="Bookmark this page" onClick={() => send("bookmark")}><Bookmark className={state.bookmarks.some(b => b.url === state.chatPage?.url) ? "bookmarked" : ""} /></Button>
      <Button variant="ghost" size="sm" className="page-mine" title="Move this page into your tabs" onClick={() => send("chatPopOut")}><ExternalLink />Move to my tabs</Button>
      <Button variant="ghost" size="icon-sm" aria-label="Hide the page" title="Hide the page" onClick={() => send("chatPage", { on: false })}><X /></Button>
     </div>}
     <div className="page-slot" ref={pageRef}>
      {pair && !modal && <div className="split-divider" role="separator" aria-label="Resize the split" aria-orientation="vertical" aria-valuenow={Math.round(pair.ratio * 100)} tabIndex={0} style={{ left: `calc((100% - 6px) * ${pair.ratio})` }}
       onKeyDown={e => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); send("splitRatio", { ratio: pair.ratio + (e.key === "ArrowRight" ? .05 : -.05) }) } }}
       onDoubleClick={() => send("splitRatio", { ratio: .5 })}
       onPointerDown={e => e.currentTarget.setPointerCapture(e.pointerId)}
       onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; const r = pageRef.current!.getBoundingClientRect(); send("splitRatio", { ratio: (e.clientX - r.left - 3) / (r.width - 6) }) }} />}
      {ghost?.side && <div className="split-zones" aria-hidden><div className={cn("split-zone", ghost.side === "left" && "is-on")}><span><Columns2 />Open on the left</span></div><div className={cn("split-zone", ghost.side === "right" && "is-on")}><span><Columns2 />Open on the right</span></div></div>}
      {driven && working && <PageControl key={driven.id} tab={driven} agent={working} who={driverOf(ai, driven)} chat={!split} />}
      {pair && snapshot && pairShot && <img className={cn("page-snapshot", pair.right !== active?.id && "is-right")} src={pairShot} alt="" style={{ width: `calc((100% - 6px) * ${pair.right === active?.id ? pair.ratio : 1 - pair.ratio})` }} />}
      {active?.url || active?.chatId ? (snapshot && <img className={cn("page-snapshot", pair?.right === active?.id && "is-right")} src={snapshot} alt="" style={pair ? { width: `calc((100% - 6px) * ${pair.right === active?.id ? 1 - pair.ratio : pair.ratio})` } : undefined} />) : (!active?.isPrivate || state.incognito && view !== "home") && !state.noAi && ai && companion && (state.preferences.newTab !== "sites" || view !== "home") ? <motion.div key={active?.id} className="new-tab-page is-home" style={{ "--hue": hueOf(companion) } as CSSProperties} initial={{ opacity: 0, y: reduced ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? .01 : .38, ease: [.22, 1, .36, 1] }}>
       <HomeRail view={view} setView={setView} profile={state.profileName} onSettings={() => open("settings")} />
       <div className="home-main">
        {view === "chats" ? <ChatHistory ai={mine!} send={send} onNew={() => setView("home")} />
         : view === "companions" ? <CompanionsPage ai={ai} send={send} onEdit={edit} onMake={() => setEditing(randomCompanion())} onChat={id => { setBuddy(id); send("aiKickoff", { companion: id, home: true }) }} onHire={hire} onMemory={id => { setMemoryFor(id); open("settings", "companions") }} />
         : view === "skills" ? <SkillsPage ai={ai} send={send} />
         : view === "library" ? <LibraryPage ai={ai} send={send} onOpen={openFile} />
         : <>
          <div className="home-top">
           <CompanionSwitch ai={ai} companion={companion} onPick={setBuddy} onEdit={edit} />

          </div>
          <div className="home-center">
           <Space companion={companion} team={ai.companions} mood={typing ? "listening" : "idle"} onOpen={() => setProfile(companion.id)} onPick={setBuddy} />
           <div className="home-compose"><Composer draft={state.secondary ? "window.home" : "home"} ai={ai} send={send} onTyping={setTyping} companion={companion} onCompanion={setBuddy} tabs={state.tabs}
            placeholder={`Ask ${companion.name} anything, or hand over a task…`}
            onSubmit={(text, tabs, files) => { send("aiSend", { text, home: true, companion: companion.id, ...(tabs.length && { tabs }), ...(files.length && { files }) }) }} /></div>
           <div className="home-chips">
            <button onClick={() => setView("skills")}><BookOpen />Skills & plugins</button>
            <button onClick={() => setView("companions")}><Users />Companions</button>
            <button onClick={() => setView("library")}><Library />Library</button>
            <button onClick={() => send("new", { url: HELP })}><CircleHelp />Help</button>
            <PluginStack plugins={ai?.plugins} send={send} onOpen={() => setView("skills")} />
           </div>
           {ideas.length > 0 && <div className="home-ideas"><h2>Try one of these</h2><div>{ideas.map(({ kind, label, why, prompt }) => { const [Icon, color] = IDEA_LOOKS[kind]
            return <button key={label} className="home-idea" data-kind={kind} onClick={() => send("aiSend", { text: prompt, home: true, companion: companion.id })}><Icon data-color={color} aria-hidden /><b>{label}</b><small>{why}</small></button> })}</div></div>}
           {state.bookmarks.length > 0 && <div className="speed-dial">{state.bookmarks.slice(0, 8).map(b => <BookmarkMenu key={b.url} b={b} onEdit={editBookmark}><button className="speed-dial-tile" title={b.url} onClick={() => send("navigate", { url: b.url })}><span className="speed-dial-letter">{b.favicon ? <img src={b.favicon} alt="" /> : (host(b.url)[0] ?? "•").toUpperCase()}</span><span className="speed-dial-name">{b.title || host(b.url)}</span></button></BookmarkMenu>)}</div>}
          </div>
         </>}
       </div>
      </motion.div> : <motion.div key={active?.id} className="new-tab-page" initial={{ opacity: 0, y: reduced ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? .01 : .38, ease: [.22, 1, .36, 1] }}>
       <Face size={64} mood={active?.isPrivate ? "sleep" : "idle"} className="new-tab-buddy" />
       <h1>{active?.isPrivate ? "Private tab" : greeting()}</h1>
       <p>{active?.isPrivate ? "A little privacy." : "Where to?"}</p>
       <Button variant="outline" className="start-search" onClick={e => openAddress(e.currentTarget)}><Search /><span>Search or enter an address</span><kbd>{keys("Ctrl L")}</kbd></Button>
       {!active?.isPrivate && state.bookmarks.length > 0 && <div className="speed-dial">{state.bookmarks.slice(0, 8).map(b => <BookmarkMenu key={b.url} b={b} onEdit={editBookmark}><button className="speed-dial-tile" title={b.url} onClick={() => send("navigate", { url: b.url })}><span className="speed-dial-letter">{b.favicon ? <img src={b.favicon} alt="" /> : (host(b.url)[0] ?? "•").toUpperCase()}</span><span className="speed-dial-name">{b.title || host(b.url)}</span></button></BookmarkMenu>)}</div>}
       {active?.isPrivate && <span className="private-caption"><LockKeyhole />This tab and its history won't be saved.</span>}
      </motion.div>}
     </div>
     </div>
     {sideViewer && <FileViewer path={viewing} data={fileData} send={send} onClose={() => setViewing("")} onLink={url => send("new", { url })} />}
     </div>
     {active?.loading && <div className="loading-line" aria-label="Loading page"><i /></div>}
    </main>
    {ai?.open && (!chatTab || aiView === "settings") && <AiPanel ai={ai} send={send} view={aiView} setView={setAiView} tabs={state.tabs} activeTab={active} onFile={openFile} />}
    {state.sidePanel && <ExtensionPanel panel={state.sidePanel} />}
   </div>
  </div>


  {pane === "downloads" && <><div className="dl-backdrop" onMouseDown={close} />
   <div className="dl-card" role="dialog" aria-label="Downloads">
    <div className="dl-head"><strong>Downloads</strong><Button variant="ghost" size="sm" onClick={() => send("downloadsFolder")}><FolderOpen />Open folder</Button></div>
    <div className="dl-list">{state.downloads.length ? state.downloads.slice(0, 8).map(d => {
     const pct = d.total ? Math.min(100, Math.round(d.bytes / d.total * 100)) : null
     const size = (n: number) => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"
     return <div className="dl-row" key={d.id} onDoubleClick={e => { if (d.status === "Completed" && !(e.target as HTMLElement).closest("button")) send("openDownload", { id: d.id }) }}>
      <Download className="dl-file" />
      <div className="dl-meta"><button className="dl-name" disabled={d.status !== "Completed"} onClick={e => { if (e.detail < 2) send("openDownload", { id: d.id }) }}>{d.name}</button>
       <small>{d.status === "InProgress" ? `${size(d.bytes)}${d.total ? " of " + size(d.total) : ""}${pct !== null ? " · " + pct + "%" : ""}` : d.status === "Completed" ? size(d.bytes) + " · Done" : d.status === "Interrupted" ? "Failed or cancelled" : d.status}</small>
       {d.status === "InProgress" && <div className="dl-bar"><i style={{ width: (pct ?? 30) + "%" }} className={pct === null ? "is-indeterminate" : ""} /></div>}</div>
      <Button variant="ghost" size="icon-sm" aria-label={d.status === "InProgress" ? "Cancel download" : "Show in folder"} onClick={() => send(d.status === "InProgress" ? "cancelDownload" : "showDownload", { id: d.id })}>{d.status === "InProgress" ? <X /> : <FolderOpen />}</Button>
     </div> }) : <p className="dl-empty">Files you download will show up here.</p>}</div>
   </div></>}
  {pane === "recent" && recent.ids.length > 1 && <div className="recent-switcher" onMouseDown={e => { if (e.target === e.currentTarget) send("recentPick", { id: "" }) }}>
   <div className="recent-card" role="listbox" aria-label="Recent tabs">
    {recent.ids.map((id, i) => { const t = state.tabs.find(x => x.id === id); return t && <button key={id} role="option" aria-selected={i === recent.index} className={cn("recent-item", i === recent.index && "is-picked")} onClick={() => send("recentPick", { id })}>
     <span className="recent-icon">{t.favicon ? <img src={t.favicon} alt="" /> : t.chatId ? <MessageSquare /> : <Globe2 />}</span>
     <span className="recent-title">{t.title || "New tab"}<small>{t.url ? host(t.url) : t.chatId ? "Chat" : "New tab"}</small></span></button> })}
    <p className="recent-hint">Keep holding Ctrl and press Tab to move. Let go to switch.</p>
   </div></div>}
  {ghost && <div className={cn("tab-ghost", ghost.tearing && "is-tearing")} style={{ left: ghost.x + 14, top: ghost.y + 10 }}>
   <span className="tab-ghost-icon">{ghost.favicon ? <img src={ghost.favicon} alt="" /> : <Globe2 />}</span><span className="tab-ghost-title">{ghost.title}</span>
   {ghost.tearing && <span className="tab-ghost-hint"><Copy />New window</span>}
  </div>}
  {state.welcome && <Welcome isDefault={state.preferences.isDefaultBrowser} agents={!!state.preferences.agents} layout={state.preferences.tabLayout} theme={state.preferences.theme} talk={state.welcomeTalk} ai={ai} noAi={state.noAi} hidden={pane === "import"} sounds={state.preferences.sounds !== false} soundsBlocked={soundsBlocked} send={send} onImport={() => open("import")} />}
  {!state.welcome && !state.secondary && <Tour name={companion?.name ?? "Your companion"} ready={!modal && !active?.url && !active?.chatId && !active?.isPrivate && !!ai && !state.noAi} />}
  <Dialog open={commandOpen} onOpenChange={o => { if (!o) close() }}>
   <DialogContent className={"command-dialog"} showCloseButton={false}>
    <DialogTitle className="sr-only">{displayPane === "tabs" ? "Find a tab" : "Go somewhere"}</DialogTitle>
    <DialogDescription className="sr-only">Search the web, enter an address, or switch to an open tab.</DialogDescription>
    <Command shouldFilter={displayPane === "tabs"}>
     <CommandInput ref={commandRef} placeholder={displayPane === "tabs" ? "Find an open tab…" : "Search or enter an address…"} value={query} onValueChange={v=>{commandChoice.current=false;setQuery(v)}} onKeyDown={e=>{if(e.key==="Tab"&&!e.shiftKey&&displayPane==="address"&&suggestions.length){e.preventDefault();commandChoice.current=false;setQuery(suggestions[0].url);return}if(e.key==="ArrowDown"||e.key==="ArrowUp")commandChoice.current=true;if(e.key==="Enter"&&displayPane==="address"&&query.trim()&&!commandChoice.current){e.preventDefault();e.stopPropagation();go(query)}}} aria-label="Search or enter an address" />
     <CommandList><CommandEmpty>No matching tabs.</CommandEmpty>
      {displayPane === "address" && suggestions.length > 0 && <CommandGroup heading="Suggested sites">{suggestions.map((v, i) => <CommandItem key={v.url} value={"suggestion " + v.url} onSelect={() => go(v.url)} data-suggestion={v.url}><Globe2 /><div className="command-row"><span>{v.host}</span><small>{v.bookmark ? v.title + " · Bookmark" : "Visited site"}</small></div>{i === 0 && <kbd className="ml-auto">Tab</kbd>}</CommandItem>)}</CommandGroup>}
      {displayPane === "address" && query.trim() && <CommandGroup><CommandItem value={query} onSelect={() => go(query)}><Search /><span>{query}</span><kbd className="ml-auto">Enter</kbd></CommandItem></CommandGroup>}
      <CommandGroup heading="Open tabs">{state.tabs.filter(t => displayPane === "tabs" || !query.trim() || (t.title + t.url).toLowerCase().includes(query.trim().toLowerCase())).map(t => <CommandItem key={t.id} value={"tab " + t.title + " " + t.url} onSelect={() => action("select", { id: t.id })}><span className="command-letter">{t.favicon?<img className="tab-favicon" src={t.favicon} alt=""/>:<Globe2 size={14}/>}</span><div className="command-row"><span>{t.title}</span><small>{host(t.url) || "New tab"}</small></div>{t.id === state.activeId && <Check className="ml-auto opacity-50" />}</CommandItem>)}</CommandGroup>

     </CommandList>
     <div className="command-footer"><span>{displayPane === "tabs" ? "Open tabs" : state.preferences.search}</span><span><kbd>↑</kbd><kbd>↓</kbd> to choose <kbd>Tab</kbd> to complete <kbd>Esc</kbd> to close</span></div>
    </Command>
   </DialogContent>
  </Dialog>

  <Dialog open={dialogOpen} onOpenChange={o => { if (!o) close() }}>
   <DialogContent onEscapeKeyDown={e => { if (displayPane === "settings" && settingsFind) { e.preventDefault(); setSettingsFind("") } }} className={cn("app-dialog", displayPane === "settings" && "settings-dialog", ["history", "bookmarks", "cookies", "passwords", "extensions", "downloads", "security", "import", "profiles"].includes(displayPane) && "library-dialog")}>
    <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{displayPane === "settings" ? "Changes save as you make them." : displayPane === "about" ? "The open-source agent browser." : displayPane === "profiles" ? "Separate spaces for your browsing." : displayPane === "import" ? "Import a browser profile or a saved export." : displayPane === "passwords" ? (MAC ? "Your logins, protected on this Mac." : "Your logins, protected on this PC.") : displayPane === "extensions" ? "Add tools to your browser." : displayPane === "cookies" ? "Manage website cookies." : displayPane === "security" ? "Browser protection and site permissions." : displayPane === "site" ? (active?.certificateError ? "The certificate could not be verified. Connection blocked." : active?.secure ? "Connection secured with HTTPS." : active?.loading ? "Checking this connection…" : "This page does not have a verified HTTPS connection.") : displayPane === "history" ? "Your recent visits, kept on this PC." : displayPane === "bookmarks" ? "The pages you want to come back to." : displayPane === "downloads" ? "Files from this session." : "Keep your hands on the keys."}</DialogDescription></DialogHeader>
    {["passwords","extensions","cookies","security","profiles","import"].includes(displayPane)&&<BrowserTools key={displayPane} pane={displayPane} data={toolData[displayPane]??{}} send={send} url={active?.url??""} tracking={state.preferences.tracking} memory={state.preferences.memory} autofill={state.preferences.autofill}/> }
    {displayPane === "settings" && <div className="set-shell">
     <nav className="set-nav" aria-label="Settings sections">
      <label className="set-search"><Search /><input aria-label="Search settings" placeholder="Search settings" value={settingsFind} onChange={e => setSettingsFind(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && found[0]) jumpTo(found[0]) }} /></label>
      {SETTING_PAGES.filter(([id]) => hasAi || !AI_PAGES.includes(id)).map(([id, label, Icon]) => <button key={id} className="set-nav-item" aria-current={!settingsFind && settingsPage === id ? "page" : undefined} onClick={() => { setSettingsFind(""); setSettingsPage(id) }}><Icon />{label}</button>)}
     </nav>
     <div className="set-main">
      {settingsFind ? found.length ? <SetCard title={found.length === 1 ? "1 setting" : `${found.length} settings`}>{found.map(f => { const Icon = SETTING_PAGES.find(p => p[0] === f[1])?.[2] ?? Info; return <button key={f[0]} className="set-result" onClick={() => jumpTo(f)}><strong>{f[2]}</strong><span><Icon />{pageName(f[1])}</span></button> })}</SetCard> : <p className="set-empty">Nothing matches "{settingsFind}". Try a word like theme, model or passwords.</p> : <>
      <h2 className="set-title">{pageName(settingsPage)}</h2>
      {settingsPage === "general" && <>
       <SetCard title="Start">
        <SetRow id="setup" title="Setup" help="Go through the first steps again: your companions, your AI and how Still looks."><Button variant="outline" size="sm" onClick={() => { close(); send("welcomeAgain") }}>Run setup again</Button></SetRow>
        {hasAi && ai.companions?.[0] && <SetRow id="talk" title={`Set me up with ${ai.companions[0].name}`} help={`${ai.companions[0].name} asks a few questions, then sets up your layout, theme, sites and more. You check every change.`}><Button variant="outline" size="sm" onClick={() => { close(); send("welcomeAgain", { talk: true }) }}>Set me up again</Button></SetRow>}
       </SetCard>
       <SetCard title="Browsing">
        <SetRow id="search" title="Search engine" help="Search only when you press Enter."><Select value={state.preferences.search} onValueChange={v => preference("search", v)}><SelectTrigger className="w-36" aria-label="Search engine"><SelectValue /></SelectTrigger><SelectContent>{["DuckDuckGo", "Google", "Bing"].map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent></Select></SetRow>
        <SetRow id="default" title="Default browser" help={state.preferences.isDefaultBrowser ? "Still opens your links." : `Open links from other apps in Still. ${MAC ? "macOS" : "Windows"} asks you to confirm.`}>{state.preferences.isDefaultBrowser ? <span className="tool-caption">✓ Default</span> : <Button variant="outline" size="sm" onClick={() => send("defaultBrowser")}>Make default</Button>}</SetRow>
        <SetRow id="startup" title="Open Still at sign-in" help={<>{MAC ? "Start with your launch profile when you log in to your Mac." : "Start with your launch profile when you sign in to Windows."}{state.preferences.startupDisabled && <> {MAC ? "It's switched off in Login Items. " : "Windows has disabled this startup entry. "}<Button variant="link" className="h-auto p-0 text-xs" onClick={() => send("startupSettings")}>{MAC ? "Open Login Items" : "Open Windows startup settings"}</Button></>}</>}><Switch aria-label="Open Still at sign-in" checked={state.preferences.startup} onCheckedChange={enabled => send("startup", { enabled })} /></SetRow>
        <SetRow id="restore" title="Pick up where you left off" help="Restore tabs when Still opens."><Switch aria-label="Restore tabs" checked={state.preferences.restore} onCheckedChange={v => preference("restore", String(v))} /></SetRow>
        <SetRow id="sounds" title="Sounds" help={soundsBlocked ? soundsBlocked + "." : "The intro, and a short jingle when setup is done. Browsing never makes a sound."}><Switch aria-label="Sounds" disabled={!!soundsBlocked} checked={sounds} onCheckedChange={v => preference("sounds", String(v))} /></SetRow>
       </SetCard>
       <SetCard title="Files and data">
        <SetRow id="downloads" title="Download folder" help={<span className="break-all">{state.preferences.downloads}</span>}><Button variant="outline" size="sm" onClick={() => send("chooseDownloads")}><FolderOpen />Change</Button></SetRow>
        <SetRow id="import" title="Import browsing data" help="Bookmarks, history and passwords from another browser or a saved export."><Button variant="outline" size="sm" onClick={() => open("import")}><Import />Import</Button></SetRow>
        <SetRow id="export" title="Export bookmarks" help="Save your bookmarks as a file any browser can read."><Button variant="outline" size="sm" onClick={() => send("exportBookmarks")}><ExternalLink />Export</Button></SetRow>
        <SetRow id="profiles" title="Profiles" help="Separate spaces for your browsing, each with its own tabs and sign-ins."><Button variant="outline" size="sm" onClick={() => open("profiles")}>Manage</Button></SetRow>
        <SetRow id="extensions" title="Extensions" help="Add tools from the Chrome Web Store. You check what each one can do before it installs."><Button variant="outline" size="sm" onClick={() => open("extensions")}><Puzzle />Manage</Button></SetRow>
       </SetCard>
      </>}
      {settingsPage === "appearance" && <>
       <SetCard title="Theme"><div className="set-pad" id="set-theme"><div className="theme-choices">{["Light", "Dark", "System"].map(theme => <Button key={theme} variant="outline" className={cn("theme-choice", state.preferences.theme === theme && "chosen")} onClick={() => preference("theme", theme)}>
        <div className={cn("theme-preview", theme.toLowerCase())}><i /><span /><b /></div><span>{theme === "Dark" ? "Black" : theme}{state.preferences.theme === theme && <Check />}</span>
       </Button>)}</div></div></SetCard>
       <SetCard title="Tabs">
        <SetRow id="layout" title="Tab layout" help="Classic puts tabs across the top. Modern puts them down the side, with your chats."><Select value={state.preferences.tabLayout ?? "Classic"} onValueChange={v => preference("tabLayout", v)}><SelectTrigger className="w-32" aria-label="Tab layout"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="Classic">Classic</SelectItem><SelectItem value="Modern">Modern</SelectItem></SelectContent></Select></SetRow>
        <SetRow id="tearoff" title="Drag tabs into their own window" help="Drag a tab out of the tab list to open it in a new window. Right-click a tab and choose Move to window to send it back."><Switch aria-label="Drag tabs into their own window" checked={!!state.preferences.tearOff} onCheckedChange={enabled => preference("tearOff", String(enabled))} /></SetRow>
       </SetCard>
      </>}
      {settingsPage === "companions" && hasAi && <>
       <SetCard title="Your team">
        <SetRow id="team" title="Companions" help={`${ai.companions?.length ?? 0} on your team. Add one, change how they look and what they do, or let one go.`}><Button variant="outline" size="sm" onClick={() => { close(); goHome("companions") }}><UsersRound />Open</Button></SetRow>
       </SetCard>
       <SetCard title="What they remember"><div className="set-pad" id="set-memory"><MemorySettings key={memoryFor} companions={ai.companions ?? []} first={memoryFor} send={send} /></div></SetCard>
      </>}
      {settingsPage === "models" && <>
       {hasAi && <SetCard title="Your AI">
        <SetRow id="ai" title="AI and model" help={`${ai.harnesses?.find(h => h.id === ai.harness)?.name ?? "No AI picked yet"}. Pick your AI, sign in, and choose its model and how hard it thinks.`}><Button variant="outline" size="sm" onClick={() => { close(); openAiSettings() }}><Bot />Open</Button></SetRow>
        <SetRow id="titles" title="Chat titles" help="A new chat gets a short name from its first message, written by the model you pick here."><Select value={state.preferences.chatTitles || "quick"} onValueChange={v => preference("chatTitles", v === "quick" ? "" : v)}><SelectTrigger className="w-48" aria-label="Chat titles"><SelectValue /></SelectTrigger><SelectContent className="titles-list">
         <SelectItem value="quick">Quickest model</SelectItem>
         {(ai.harnesses ?? []).filter(h => h.installed && h.status !== "signedOut").map(h => { const list = (ai.models ?? []).filter(m => m.harness === h.id && m.id); return list.length > 0 && <SelectGroup key={h.id}><SelectSeparator /><SelectLabel className="titles-label"><AiLogo id={h.id} size={14} />{h.name}</SelectLabel>{list.map(m => <SelectItem key={m.id} value={h.id + "/" + m.id}><AiLogo id={h.id} size={16} /><span className="titles-ai">{h.name} · </span>{m.name}</SelectItem>)}</SelectGroup> })}
         <SelectSeparator /><SelectItem value="off">Off (use first message)</SelectItem>
        </SelectContent></Select></SetRow>
       </SetCard>}
       <SetCard title="Other AI apps">
        <SetRow id="mcp" title="Let other AI apps use Still" help="Apps like Claude Desktop, Claude Code or Cursor can open, read and click pages for you (MCP). Each app asks you first, and you can stop it anytime. Private tabs, passwords and cookies stay off-limits."><Switch aria-label="Let other AI apps use Still" checked={!!state.preferences.agents} onCheckedChange={enabled => preference("agents", String(enabled))} /></SetRow>
        {state.preferences.agents && <SetRow id="askInChat" title="Ask me in the AI's chat when I'm away" help="If you don't answer the bar here, the AI app asks you instead, or the AI asks you in its chat and passes your answer on. Turn this off to only allow agents from this window."><Switch aria-label="Ask me in the AI's chat when I'm away" checked={state.preferences.askInChat !== false} onCheckedChange={enabled => preference("askInChat", String(enabled))} /></SetRow>}
        {state.preferences.agents && state.mcpCommand && <div className="set-pad" id="set-dev">{state.preferences.agents && state.mcpCommand && (() => { const cfg = JSON.stringify({ mcpServers: { still: { command: state.mcpCommand, args: ["--mcp"] } } }, null, 2); return <details className="mcp-config welcome-dev"><summary>For developers: connect an AI app by hand</summary><p className="tool-caption">Add this to your AI app's MCP settings:</p><pre>{cfg}</pre><Button variant="outline" size="sm" onClick={() => { send("copyText", { text: cfg }); setNotice("MCP config copied") }}><Copy />Copy config</Button>
       {(() => { const exe = `& "${state.mcpCommand}"`; const prompt = `You can control my Still web browser from the terminal (PowerShell) with:
${exe} --cli <tool> as=<your name> [key=value ...]

Always pass as=<your name> (for example as=Claude, as=ChatGPT or as=Grok) so I can see who is using Still.

Run \`${exe} --cli help\` to list tools. Common ones:
- list_tabs: open tabs and their ids
- open_tab url=<url or search>
- navigate url=<url> [tabId=<id>]
- read_page [text=false] [all=true] [offset=<n>] [tabId=<id>]: title, url, then one line per button/link/field near the visible part as [id] kind "label", then the page text (text=false = controls only, fewer tokens)
- find text=<words>: matching buttons/links/fields with ids, and matching lines of text, from the whole page
- click id=<id> (or selector=<css> | text=<visible text>)
- type id=<id> text=<text> [append=true] [submit=true] (replaces the field's text; on a dropdown, picks that option)
- press_key key=<Enter | Escape | Tab | Control+A ...>
- scroll direction=down [amount=800] | scroll id=<id>
- wait_for id=<id> | selector=<css> | text=<text> [gone=true] [timeoutMs=10000]
- handle_dialog [accept=false] [text=<answer>]: answers an alert/confirm/prompt the page opened
- upload_file paths=<full path>[;<another>]: attaches files after you click a page's upload button
- screenshot: prints the path of a PNG you can open
- switch_tab / close_tab / go_back / go_forward / reload [tabId=<id>]
- list_profiles; add profile=<name> to any tool to use another profile, or profile=temp for a separate temporary window with no cookies or logins

The first call waits for me to approve you in Still. Private tabs, passwords and cookies are never available. Ids stay valid while their element is on the page. Each action tells you where you ended up, so read the page again only when you need to. don't submit forms or buy anything without asking me.`; return <><p className="tool-caption">Or paste this prompt into Claude Code, Grok Build or another agent app:</p><pre>{prompt}</pre><Button variant="outline" size="sm" onClick={() => { send("copyText", { text: prompt }); setNotice("Agent prompt copied") }}><Copy />Copy agent prompt</Button></> })()}</details> })()}</div>}
       </SetCard>
      </>}
      {settingsPage === "skills" && hasAi && <SetCard title="Skills & plugins">
       <SetRow id="skills" title="Skills & plugins" help="Your apps, like Gmail and Slack, are with your skills: connect apps and pick which companion can use each."><Button size="sm" variant="outline" onClick={() => { close(); goHome("skills") }}>Open Skills & plugins</Button></SetRow>
       <PluginKeySetting plugins={ai?.plugins} send={send} />
      </SetCard>}
      {settingsPage === "privacy" && <>
       <p className="data-intro">Tabs, bookmarks and history stay on this {MAC ? "Mac" : "PC"}. Still has no account or cloud sync.</p>
       <SetCard title="Protection">
        <SetRow id="blocking" title="Block common ads & trackers" help="A small built-in list. Some ads may remain."><Switch aria-label="Block ads and trackers" checked={state.preferences.blocking} onCheckedChange={v => preference("blocking", String(v))} /></SetRow>
        <SetRow id="passwords" title="Passwords" help={MAC ? "Your logins, kept in your Keychain." : "Your logins, encrypted by Windows."}><Button variant="outline" size="sm" onClick={() => open("passwords")}><KeyRound />Open</Button></SetRow>
        <SetRow id="cookies" title="Cookies" help="See and remove what websites keep."><Button variant="outline" size="sm" onClick={() => open("cookies")}><Cookie />Open</Button></SetRow>
        <SetRow id="security" title="Privacy & security" help="Tracking protection and what each site may use."><Button variant="outline" size="sm" onClick={() => open("security")}><ShieldCheck />Open</Button></SetRow>
       </SetCard>
       {hasAi && <SetCard title="What companions may do"><div className="set-pad" id="set-permissions"><PermissionsSettings ai={ai} send={send} /></div></SetCard>}
       <SetCard title="Clear data">
        <SetRow id="clearHistory" title="Clear browsing history" help="Your bookmarks and open tabs stay."><Button variant="outline" size="sm" onClick={() => setConfirm({ title: "Clear your history?", body: "Your bookmarks and open tabs will stay.", op: "clearHistory" })}><History />Clear</Button></SetRow>
        <SetRow id="clearCookies" title="Clear cookies and website data" help="This signs you out of websites in Still."><Button variant="outline" size="sm" onClick={() => setConfirm({ title: "Clear website data?", body: "This signs you out of websites in Still.", op: "clearCookies" })}><Trash2 />Clear</Button></SetRow>
       </SetCard>
      </>}
      {settingsPage === "shortcuts" && <SetCard title="Keys">{shortcuts.map(([label, key], i) => <div className="shortcut-row" id={"set-key-" + i} key={label}><span>{label}</span><kbd>{key}</kbd></div>)}</SetCard>}
      {settingsPage === "about" && <SetCard title="Still"><div className="set-pad" id="set-about">{about}</div></SetCard>}
      </>}
     </div>
    </div>}
    {(displayPane === "history" || displayPane === "bookmarks") && <>{displayPane === "history" && state.history.length > 0 && <Button variant="ghost" className="settings-link" onClick={() => setConfirm({ title: "Clear your history?", body: "Your bookmarks and open tabs will stay.", op: "clearHistory" })}><History />Clear browsing history</Button>}{bookmarkDraft&&displayPane==="bookmarks"&&<form className="bookmark-edit" onSubmit={e=>{e.preventDefault();send("bookmarkEdit",bookmarkDraft);setBookmarkDraft(null)}}><Input aria-label="Bookmark name" value={bookmarkDraft.title} onChange={e=>setBookmarkDraft({...bookmarkDraft,title:e.target.value})}/><Input type="url" required aria-label="Bookmark URL" value={bookmarkDraft.url} onChange={e=>setBookmarkDraft({...bookmarkDraft,url:e.target.value})}/><div><Button type="button" variant="ghost" onClick={()=>setBookmarkDraft(null)}>Cancel</Button><Button type="submit">Save bookmark</Button></div></form>}<Input placeholder={"Search " + displayPane} aria-label={"Search " + displayPane} value={filter} onChange={e => setFilter(e.target.value)} /><ScrollArea className="library-scroll">{filtered.length ? filtered.map((v, i) => <div className="library-row" key={v.url + i}><Button variant="ghost" className="library-open" onClick={() => go(v.url)}><span className="site-initial">{[...v.title][0]}</span><span><strong>{v.title}</strong><small>{host(v.url)}{v.at && " · " + new Date(v.at).toLocaleDateString()}</small></span></Button>{displayPane==="bookmarks"&&<Button variant="ghost" size="icon-xs" aria-label={"Edit " + v.title} onClick={()=>setBookmarkDraft({oldUrl:v.url,title:v.title,url:v.url})}><Pencil/></Button>}<Button variant="ghost" size="icon-xs" aria-label={"Remove " + v.title} onClick={() => send(displayPane === "bookmarks" ? "removeBookmark" : "removeHistory", { url: v.url })}><X /></Button></div>) : <p className="empty-state">{displayPane === "bookmarks" ? "No bookmarks yet. Ctrl D saves a page." : "No visits here yet."}</p>}</ScrollArea></>}
    {displayPane === "downloads" && <><Button variant="outline" className="justify-start" onClick={() => send("downloadsFolder")}><FolderOpen />Open download folder</Button><ScrollArea className="library-scroll">{state.downloads.length ? state.downloads.map(d => <div className="download-row" key={d.id} onDoubleClick={e => { if (d.status === "Completed" && !(e.target as HTMLElement).closest("button")) send("openDownload", { id: d.id }) }}><Download /><div><strong>{d.name}</strong><small>{d.status} · {(d.bytes / 1024).toFixed(0)} KB</small></div><Button variant="ghost" size="icon-sm" aria-label={d.status === "InProgress" ? "Cancel download" : "Show in folder"} onClick={() => send(d.status === "InProgress" ? "cancelDownload" : "showDownload", { id: d.id })}>{d.status === "InProgress" ? <X /> : <FolderOpen />}</Button></div>) : <p className="empty-state">Your downloads will appear here.</p>}</ScrollArea></>}
    {displayPane === "site" && <div className="site-settings"><div className="setting-row"><div><strong>Block ads & trackers</strong><p>{active?.blocked ?? 0} requests blocked on this page.</p></div><Switch aria-label="Blocking on this site" checked={state.siteBlocking} onCheckedChange={() => send("siteBlocking")} /></div><Separator /><Button variant="ghost" className="settings-link" onClick={() => action("hide")}><EyeOff />Hide something on this page</Button><Button variant="ghost" className="settings-link" onClick={() => action("unhide")}><RotateCw />Restore hidden elements</Button><Button variant="ghost" className="settings-link" onClick={() => send("pin")}><Pin />{active?.pinned ? "Unpin this tab" : "Pin this tab"}</Button><Button variant="ghost" className="settings-link" onClick={() => send("mute")}><VolumeX />{active?.muted ? "Unmute site" : "Mute site"}</Button></div>}
    {displayPane === "shortcuts" && <ScrollArea className="shortcuts-scroll">{shortcuts.map(([label, key]) => <div className="shortcut-row" key={label}><span>{label}</span><kbd>{key}</kbd></div>)}</ScrollArea>}
    {displayPane === "about" && about}
   </DialogContent>
  </Dialog>

  <AlertDialog open={!!state.dialog}><AlertDialogContent onEscapeKeyDown={e => { e.preventDefault(); answerDialog(false) }}>
   <AlertDialogHeader><AlertDialogTitle>{state.dialog?.kind === "leave page" ? "Leave this page?" : (state.dialog?.site || "This page") + " says"}</AlertDialogTitle>
    <AlertDialogDescription className="whitespace-pre-wrap break-words max-h-[50vh] overflow-auto">{state.dialog?.kind === "leave page" ? "Changes you made may not be saved." : state.dialog?.message}</AlertDialogDescription></AlertDialogHeader>
   {state.dialog?.kind === "prompt" && <Input autoFocus aria-label="Your answer" value={dialogText} onChange={e => setDialogText(e.target.value)} onKeyDown={e => { if (e.key === "Enter") answerDialog(true) }} />}
   <AlertDialogFooter>
    {state.dialog?.kind !== "alert" && <Button variant="outline" onClick={() => answerDialog(false)}>{state.dialog?.kind === "leave page" ? "Stay" : "Cancel"}</Button>}
    <Button autoFocus={state.dialog?.kind !== "prompt"} onClick={() => answerDialog(true)}>{state.dialog?.kind === "leave page" ? "Leave" : "OK"}</Button>
   </AlertDialogFooter>
  </AlertDialogContent></AlertDialog>
  <AlertDialog open={!!confirm} onOpenChange={o => { if (!o) setConfirm(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{confirm?.title}</AlertDialogTitle><AlertDialogDescription>{confirm?.body}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => { if (confirm) send(confirm.op); setConfirm(null) }}>Clear</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  {upload && <UploadCard upload={upload} send={send} />}
  {viewing && !sideViewer && <Dialog open onOpenChange={o => { if (!o) setViewing("") }}><DialogContent className="app-dialog file-dialog" aria-describedby={undefined}><DialogTitle className="sr-only">File</DialogTitle><FileViewer path={viewing} data={fileData} send={send} onClose={() => setViewing("")} onLink={url => send("new", { url })} /></DialogContent></Dialog>}
  {oldName && !editing && <RenameAsk key={oldName.id} companion={oldName} onSave={c => send("companionSave", c)} />}
  {profile && ai && <ProfilePanel ai={ai} id={profile} send={send} onPick={setProfile} onClose={() => setProfile("")} onOpenFile={path => { setProfile(""); openFile(path) }} onSkills={() => { setProfile(""); goHome("skills") }} />}
  {library && ai && <CompanionLibrary have={ai.companions} onClose={() => setLibrary(false)} onProfile={p => { setLibrary(false); setMeeting(p) }} onAdd={p => hire(fromPremade(p))}
   onOwn={() => { setLibrary(false); setEditing(randomCompanion()) }} onPaste={c => { setLibrary(false); hire(c) }} />}
  {meeting && ai && <CompanionProfile key={meeting.id} p={meeting} hired={!!ai.companions?.some(c => premadeOf(c) === meeting)} onClose={() => { setMeeting(null); setLibrary(true) }}
   onHire={() => { hire(fromPremade(meeting)); setMeeting(null); setLibrary(true) }} />}
  {editing && ai && <CompanionEditor ai={ai} companion={editing} onClose={() => setEditing(null)} onSave={c => { if (c.id) send("companionSave", c); else hire(c); setEditing(null) }} />}
  {joined && <JoinedCard companion={joined} onLater={() => setJoined(null)} onStart={() => { setJoined(null); setLibrary(false); chatWith(joined.id) }} />}
  {replay && <IntroReplay look={ai?.companions?.[0] ? lookOf(ai.companions[0]) : DEFAULT_LOOK} sound={sounds} onSound={on => preference("sounds", String(on))} onDone={() => setReplay(false)} />}
  <Toaster theme={state.dark ? "dark" : "light"} position="top-center" offset={5} visibleToasts={1} duration={3000} toastOptions={{ className: "still-toast" }} />
 </TooltipProvider></MotionConfig></CompanionContext.Provider></UICtx.Provider>
}

import "./motion.css"

function BookmarkMenu({b,onEdit,children}:{b:{title:string;url:string};onEdit:(b:{title:string;url:string})=>void;children:React.ReactNode}){
 const {setContext}=useContext(UICtx)!
 return <ContextMenu onOpenChange={setContext}>
  <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
  <ContextMenuContent className="w-52">
   <ContextMenuItem onSelect={()=>send("navigate",{url:b.url})}><ExternalLink/>Open</ContextMenuItem>
   <ContextMenuItem onSelect={()=>send("new",{url:b.url})}><Plus/>Open in new tab</ContextMenuItem>
   <ContextMenuItem onSelect={()=>send("new",{url:b.url,private:true})}><LockKeyhole/>Open in private tab</ContextMenuItem>
   <ContextMenuSeparator/>
   <ContextMenuItem onSelect={()=>onEdit(b)}><Pencil/>Edit name or address…</ContextMenuItem>
   <ContextMenuItem onSelect={()=>{navigator.clipboard?.writeText(b.url).catch(()=>{})}}><Copy/>Copy link</ContextMenuItem>
   <ContextMenuItem onSelect={()=>send("bookmarkMove",{url:b.url,delta:-1})}><ArrowLeft/>Move left</ContextMenuItem>
   <ContextMenuItem onSelect={()=>send("bookmarkMove",{url:b.url,delta:1})}><ArrowRight/>Move right</ContextMenuItem>
   <ContextMenuSeparator/>
   <ContextMenuItem variant="destructive" onSelect={()=>send("removeBookmark",{url:b.url})}><Trash2/>Delete bookmark</ContextMenuItem>
  </ContextMenuContent>
 </ContextMenu>
}


function prettyUrl(url: string) {
 try { const u = new URL(url); if (u.protocol === "http:" || u.protocol === "https:") return u.host.replace(/^www\./, "") + (u.pathname === "/" ? "" : u.pathname) + u.search + u.hash } catch { /* not a URL */ }
 return url
}

// A chat tab's sidebar: new chat, recent chats, and the profile menu. Beside a page it shrinks to the logo.
function ChatSide({ ai, state, activeChat, open, setOpen, split, onEdit, onSettings, openPanel, goHome }: { ai: AiState; state: State; activeChat?: string; open: boolean; setOpen: (v: boolean) => void; split: boolean; onEdit: (c: Companion) => void; onSettings: () => void; openPanel: (name: string) => void; goHome: (v: HomeView) => void }) {
 const chats = (ai.incognito ? ai.privateChats ?? [] : ai.chats).filter(c => !c.archived).slice(0, 15)
 if (!open || split) return <nav className="chat-side is-closed" aria-label="Chats">
  <Button variant="ghost" size="icon-sm" aria-label="Show sidebar" title="Show sidebar" onClick={() => { setOpen(true); if (split) send("chatPage", { on: false }) }}><span className="still-mark is-small"><i /><i /></span></Button>
 </nav>
 return <nav className="chat-side" aria-label="Chats">
  <div className="chat-side-head"><span className="still-mark is-small"><i /><i /></span><b>Still</b><Button variant="ghost" size="icon-sm" aria-label="Hide sidebar" title="Hide sidebar" onClick={() => setOpen(false)}><PanelLeftClose /></Button></div>
  <div className="chat-side-nav">
   <button onClick={() => goHome("home")}><SquarePen />New Chat</button>
   <button onClick={() => goHome("chats")}><MessageSquare />Chat History</button>
   <button onClick={() => goHome("companions")}><Users />Companions</button>
   <button onClick={() => goHome("library")}><Library />Library</button>
  </div>
  <h3>Recent chats</h3>
  <ScrollArea className="chat-side-list">
   {!chats.length && <p className="chat-rail-empty">Your chats show up here.</p>}
   {chats.map(c => <div key={c.id} className={cn("chat-side-item", c.id === activeChat && "is-on")}>
    <ChatLink id={c.id} send={send} className="chat-side-open" title={c.title}><Face companion={companionOf(ai, c.companion)} size={18} /><span className="chat-side-title">{c.title}</span>{isRunning(ai, c.id) ? <Loader2 className="chat-side-busy spin" aria-label="Working" /> : c.unread && <i className="is-unread" aria-label="Unread" />}</ChatLink>
    {!isRunning(ai, c.id) && <button className="chat-side-delete" aria-label={"Delete " + c.title} title="Delete chat" onClick={() => send("aiDeleteChat", { id: c.id })}><X /></button>}
   </div>)}
  </ScrollArea>
  <DropdownMenu><DropdownMenuTrigger asChild><button className="chat-side-profile"><span className="chat-side-avatar">{state.incognito ? <LockKeyhole /> : (state.profileName[0] ?? "S").toUpperCase()}</span><span className="chat-side-title">{state.incognito ? "Incognito" : state.profileName}</span><ChevronDown /></button></DropdownMenuTrigger>
   <DropdownMenuContent side="top" align="start" sideOffset={8} className="chat-side-menu">
    <DropdownMenuLabel>Theme</DropdownMenuLabel>
    <div className="chat-side-theme">{([["Light", Sun], ["Dark", Moon], ["System", Monitor]] as const).map(([t, Icon]) => <button key={t} aria-pressed={state.preferences.theme === t} onClick={() => send("preference", { key: "theme", value: t })}><Icon />{t}</button>)}</div>
    <DropdownMenuSeparator />
    <DropdownMenuLabel>Companions</DropdownMenuLabel>
    {ai.companions?.map(c => <DropdownMenuItem key={c.id} onSelect={() => onEdit(c)}><Face companion={c} size={18} />{c.name}<Pencil className="ml-auto size-3.5 opacity-60" /></DropdownMenuItem>)}
    <DropdownMenuItem onSelect={() => onEdit(randomCompanion())}><Plus />Hire a companion</DropdownMenuItem>
    <DropdownMenuSeparator />
    <DropdownMenuItem onSelect={onSettings}><Bot />AI settings</DropdownMenuItem>
    <DropdownMenuItem onSelect={() => openPanel("settings")}><Settings2 />Settings</DropdownMenuItem>
   </DropdownMenuContent></DropdownMenu>
 </nav>
}

// The chat's details, top right: its companion, the AI it runs on, the pages it opened and usage.
/// An AI is driving the page in view: a glow runs around the page and its controls float over it. The page's window
/// leaves those spots open (pageHoles), so they show through and take the clicks.
function PageControl({ tab, agent, who, chat }: { tab: Tab; agent: NonNullable<State["agent"]>; who: Companion; chat: boolean }) {
 const ref = useRef<HTMLDivElement>(null)
 useLayoutEffect(() => {
  const pill = ref.current, slot = pill?.parentElement
  if (!pill || !slot) return
  const sync = () => { const s = slot.getBoundingClientRect(), r = pill.getBoundingClientRect(); send("pageHoles", { tab: tab.id, frame: 3, spots: [{ x: r.x - s.x, y: r.y - s.y, width: r.width, height: r.height, radius: r.height / 2 }], viewportWidth: innerWidth }) }
  const observer = new ResizeObserver(sync); observer.observe(pill); observer.observe(slot); sync()
  return () => { observer.disconnect(); send("pageHoles", { tab: tab.id, frame: 0, spots: [] }) }
 }, [tab.id])
 const kind = agentFace(who.face) || "claude"
 const hue = who.id ? { "--drive": hueOf(who) } as CSSProperties : undefined // a companion wears its hue; another AI app its maker's color
 return <>
  <div className="page-glow" data-kind={kind} style={hue} aria-hidden />
  <div ref={ref} className={cn("page-control", agent.paused && "is-paused")} data-kind={kind} style={hue} role="status" aria-label={agent.paused ? who.name + " is waiting for you" : who.name + " is working"}>
   <Face companion={who} size={28} mood={agent.paused ? "listening" : "working"} />
   <span className="page-control-text"><b>{agent.paused ? agent.signIn ? "Sign in, then hand it back" : "You're in control" : who.name + " is working…"}</b>{agent.paused && agent.signIn ? <small>{who.name} never sees your password</small> : !agent.paused && agent.action && <small>{agent.action}</small>}</span>
   <button className="page-take" onClick={() => send("agentTakeOver", { on: !agent.paused, key: agent.key })}><Hand />{agent.paused ? "Hand back" : "Take over"}</button>
   {chat && tab.runChat && <button className="page-chat" onClick={() => send("agentChat", { id: tab.id })}><ArrowUpRight />Open chat</button>}
   <button className="page-stop" aria-label="Stop" title="Stop" onClick={() => send("agentStop", { key: agent.key })}><Square /></button>
  </div>
 </>
}

function ChatInfo({ ai, pages, onEdit, onSettings, onFile }: { ai: AiState; pages: Tab[]; onEdit: (c: Companion) => void; onSettings: () => void; onFile: (path: string) => void }) {
 const files = (ai.files ?? []).filter(f => f.chat === ai.chatId)
 const companion = companionOf(ai, ai.chatCompanion)
 const harness = ai.harnesses.find(h => h.id === (ai.chatHarness || ai.harness))
 return <aside className="chat-info" aria-label="Chat details">
  <h4>In this chat</h4>
  {[companion].map(c => c && <button key={c.id} className="chat-info-row" title={"Edit " + c.name} onClick={() => onEdit(c)}><Face companion={c} size={18} /><b>{c.name}</b><Settings /></button>)}
  <button className="chat-info-row" title="AI settings" onClick={onSettings}><AiLogo id={harness?.id} size={16} /><b>{harness ? <>{harness.name}<small>{[ai.models?.find(m => m.harness === harness.id && m.id === ai.model && m.id)?.name, harness.maker && "Your " + harness.name + " plan"].filter(Boolean).join(" · ")}</small></> : "Pick your AI"}</b><ChevronRight /></button>
  {pages.length > 0 && <><Separator /><h4>Pages</h4>{pages.map(p => <button key={p.id} className="chat-info-row" title={p.url} onClick={() => send("chatPage", { on: true, id: p.id })}>{p.favicon ? <img src={p.favicon} alt="" /> : <Globe2 />}<b>{p.title || host(p.url)}</b><small>{p.agent ? "Working" : p.loading ? "Loading" : "Open"}</small></button>)}</>}
  {files.length > 0 && <><Separator /><h4>Files</h4>{files.map(f => <button key={f.path} className="chat-info-row" title={"Open " + f.name} onClick={() => onFile(f.path)}><FileIcon path={f.path} /><b>{f.name}</b></button>)}</>}
  {!!ai.audit?.length && <><Separator /><h4>Permissions</h4><AuditList list={ai.audit} /></>}
  {ai.usage && <><Separator /><p className="chat-info-usage">{ai.usage}</p></>}
 </aside>
}
