import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import { AnimatePresence, LayoutGroup, motion, MotionConfig, useReducedMotion } from "motion/react"
import { Bot, ArrowLeft, ArrowRight, RotateCw, Plus, X, Minus, Expand, Search, MoreHorizontal, Settings2, Bookmark, Shield, BookOpen, Download, History, PanelLeft, Moon, Sun, Pin, VolumeX, Copy, MoonStar, EyeOff, ExternalLink, Keyboard, LockKeyhole, ChevronRight, Check, Loader2, Trash2, FolderOpen, Globe2, KeyRound, Puzzle, Cookie, ShieldCheck, Pencil, Square, UsersRound, Import } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from "@/components/ui/command"
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut } from "@/components/ui/dropdown-menu"
import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from "@/components/ui/context-menu"
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select"
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog"
import { Toaster } from "@/components/ui/sonner"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import "./app.css"
import { rankSuggestions } from "./suggestions"
import { BrowserTools } from "./BrowserTools"
import type { ToolData } from "./BrowserTools"

type Tab = { id: string; title: string; url: string; pinned: boolean; isPrivate: boolean; loading: boolean; sleeping: boolean; blocked: number; muted: boolean; favicon?: string; secure?: boolean; certificateError?: boolean }
type Visit = { title: string; url: string; at?: string }
type DownloadItem = { id: string; name: string; status: string; bytes: number; total?: number }
type State = { profileName:string; maximized:boolean; loginOffer?:{id:string;origin:string;username:string;update:boolean}; permission?:{id:string;site:string;kind:string}; update?:{version:string;current:string;ready?:boolean;progress?:number;busy?:boolean;selfUpdate?:boolean}; version?:string; windows?:{id:string;name:string;title:string}[]; secondary?:boolean; incognito?:boolean; agent?:{client:string;pending:boolean;action:string}; mcpCommand?:string; activeId: string; dark: boolean; focusMode: boolean; fullScreen:boolean; appFullScreen?:boolean; preferences: { theme: string; layout: string; search: string; restore: boolean; blocking: boolean; downloads: string; sidebarWidth:number; tracking:string; memory:boolean; autofill:boolean; startup:boolean; startupDisabled:boolean; isDefaultBrowser?:boolean; tearOff?:boolean; agents?:boolean }; zoom:number; tabs: Tab[]; history: Visit[]; bookmarks: Visit[]; downloads: DownloadItem[]; canBack: boolean; canForward: boolean; siteBlocking: boolean }
type Bridge = { postMessage: (v: unknown) => void; addEventListener: (name: string, listener: (e: MessageEvent) => void) => void; removeEventListener: (name: string, listener: (e: MessageEvent) => void) => void }
declare global { interface Window { chrome?: { webview?: Bridge } } }
function send(op: string, payload: Record<string, unknown> = {}) { window.chrome?.webview?.postMessage({ op, ...payload }) }
const initial: State = { profileName:"Default",maximized:false,activeId: "empty", dark: true, focusMode: false, fullScreen:false, preferences: { theme: "Dark", layout: "Sidebar", search: "Google", restore: true, blocking: true, downloads: "", sidebarWidth:248, tracking:"Balanced", memory:true, autofill:true, startup:false, startupDisabled:false }, zoom:100, tabs: [{ id: "empty", title: "New tab", url: "", pinned: false, isPrivate: false, loading: false, sleeping: false, blocked: 0, muted: false }], history: [], bookmarks: [], downloads: [], canBack: false, canForward: false, siteBlocking: true }
const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, "") || url } catch { return url } }
const shortcuts = [["Go to an address", "Ctrl L"], ["Find a tab", "Ctrl K"], ["New tab", "Ctrl T"], ["Private tab", "Ctrl Shift N"], ["Close tab", "Ctrl W"], ["Reopen tab", "Ctrl Shift T"], ["Next / previous tab", "Ctrl Tab / Ctrl Shift Tab"], ["Pin tab", "Ctrl Shift P"], ["Bookmark page", "Ctrl D"], ["Bookmarks", "Ctrl Shift B"], ["History", "Ctrl H"], ["Downloads", "Ctrl J"], ["Find in page", "Ctrl F"], ["Reader", "Ctrl Shift R"], ["Hide an element", "Ctrl Shift H"], ["Tab layout", "Ctrl Shift S"], ["Full screen", "F11"], ["Exit full screen", "Esc"], ["Focus mode", "Ctrl Shift F"], ["Settings", "Ctrl ,"]]

const FLOW = { type: "spring" as const, stiffness: 460, damping: 34, mass: .75 }
const AnimatedButton = motion.create(Button)
function FlowTabs({ tabs, top = false }: { tabs: Tab[]; top?: boolean }) {
 const reduced = useReducedMotion()
 return <AnimatePresence initial={false} mode="popLayout">{tabs.map(tab => <motion.div key={tab.id} className={cn("tab-motion", top && "top-tab-motion")} layout="position"
  initial={{ opacity: 0, x: reduced ? 0 : -8, scale: reduced ? 1 : .97 }} animate={{ opacity: 1, x: 0, scale: 1 }}
  exit={{ opacity: 0, x: reduced ? 0 : -12, scale: reduced ? 1 : .97, transition: { duration: reduced ? .01 : .16 } }} transition={FLOW}>
  <TabView tab={tab} top={top} />
 </motion.div>)}</AnimatePresence>
}
type Ghost = { title: string; favicon?: string; x: number; y: number; tearing: boolean }
const UICtx = createContext<{state:State;setContext:(v:boolean)=>void;open:(name:string,value?:string)=>void;arriving:string;setGhost:(g:Ghost|null)=>void}|null>(null)
 function Hint({ label, children }: { label: string; children: ReactNode }) {
  return <Tooltip><TooltipTrigger asChild>{children}</TooltipTrigger><TooltipContent side="bottom" sideOffset={8} collisionPadding={6}>{label}</TooltipContent></Tooltip>
 }
 function IconButton({ label, caption = label, children, onClick, disabled = false }: { label: string; caption?:string; children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return <AnimatedButton variant="ghost" size="icon-sm" className="chrome-button expanding-button" aria-label={label} disabled={disabled} onClick={onClick} whileTap={{ scale: .97 }} transition={FLOW}><span className="chrome-icon">{children}</span><span className="chrome-label" aria-hidden="true"><span>{caption}</span></span></AnimatedButton>
 }
 function TabView({ tab, top = false }: { tab: Tab; top?: boolean }) {
  const {state,setContext,arriving,setGhost}=useContext(UICtx)!
  const selected = tab.id === state.activeId
  const [tearing, setTearing] = useState(false)
  // Pointer-driven drag: drop on another tab to reorder; drop outside the tab list to open a new window.
  const drag = useRef<{ sx: number; sy: number; active: boolean } | null>(null)
  const suppressClick = useRef(false)
  const outsideList = (el: Element, x: number, y: number) => {
   const list = el.closest(".tabs-scroll, .top-tab-strip")?.getBoundingClientRect()
   const out = x < 0 || y < 0 || x > innerWidth || y > innerHeight
   return out || !list || x < list.left - 40 || x > list.right + 40 || y < list.top - 40 || y > list.bottom + 40
  }
  const onPointerDown = (e: React.PointerEvent) => { if (e.button === 0) drag.current = { sx: e.clientX, sy: e.clientY, active: false } }
  const onPointerMove = (e: React.PointerEvent) => {
   const d = drag.current; if (!d) return
   if (!d.active) { if (Math.hypot(e.clientX - d.sx, e.clientY - d.sy) < 7) return; d.active = true; e.currentTarget.setPointerCapture(e.pointerId) }
   const tear = !!state.preferences.tearOff && outsideList(e.currentTarget, e.clientX, e.clientY)
   setGhost({ title: tab.title, favicon: tab.favicon, x: e.clientX, y: e.clientY, tearing: tear })
  }
  const onPointerUp = (e: React.PointerEvent) => {
   const d = drag.current; drag.current = null
   if (!d?.active) return
   suppressClick.current = true
   setGhost(null)
   try { e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* not captured */ }
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
    <div className={cn("tab-row", tab.pinned && "pin-tab", selected && "is-selected", top && "top-tab", tearing && "is-tearing", arriving === tab.id && "is-arriving")}
     data-tab-id={tab.id} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={() => { drag.current = null; setGhost(null) }} onClickCapture={onClickCapture}
     onAuxClick={e => { if (e.button === 1) { e.preventDefault(); send("closeTab", { id: tab.id }) } }}>
     {selected && <motion.div className="selected-tab" layoutId={tab.pinned ? "pin-selected" : "tab-selected"} transition={FLOW} />}
     <Button variant="ghost" className="tab-main" aria-current={selected ? "page" : undefined} aria-label={(tab.pinned ? "Pinned " : "Tab ") + tab.title} title={tab.url || tab.title} onClick={() => send("select", { id: tab.id })}>
      <span className={cn("tab-letter", tab.sleeping && "is-sleeping")}>{tab.loading ? <Loader2 className="spin" /> : tab.isPrivate ? <LockKeyhole /> : tab.muted ? <VolumeX /> : (tab.favicon ? <img className="tab-favicon" src={tab.favicon} alt="" onError={e=>{e.currentTarget.style.visibility="hidden"}} /> : <Globe2 />)}</span>
      {!tab.pinned && <span className="tab-label">{tab.title}</span>}
     </Button>
     {!tab.pinned && <Button variant="ghost" size="icon-xs" className="close-tab" aria-label={"Close " + tab.title} onClick={() => send("closeTab", { id: tab.id })}><X /></Button>}
    </div>
   </ContextMenuTrigger>
   <ContextMenuContent className="w-48">
    <ContextMenuItem onSelect={() => send("pin", { id: tab.id })}><Pin />{tab.pinned ? "Unpin tab" : "Pin tab"}</ContextMenuItem>
    <ContextMenuItem onSelect={() => send("duplicate", { id: tab.id })}><Copy />Duplicate</ContextMenuItem>
    <ContextMenuItem onSelect={() => send("mute", { id: tab.id })}><VolumeX />{tab.muted ? "Unmute" : "Mute"}</ContextMenuItem>
    <ContextMenuItem onSelect={() => send("sleep", { id: tab.id })}><MoonStar />Put to sleep</ContextMenuItem>
    <ContextMenuSeparator />
    <ContextMenuItem onSelect={() => send("closeTab", { id: tab.id, force: true })}><X />Close tab</ContextMenuItem>
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
 const [settingsPage, setSettingsPage] = useState("appearance")
 const reduced = useReducedMotion()
 const [query, setQuery] = useState("")
 const [filter, setFilter] = useState("")
 const [menu, setMenu] = useState(false)
 const [context, setContext] = useState(false)
 const [snapshot, setSnapshot] = useState("")
 const [notice,setNotice]=useState("")
 const [toolData,setToolData]=useState<Record<string,ToolData>>({})
 const [bookmarkDraft,setBookmarkDraft]=useState<{oldUrl:string;title:string;url:string}|null>(null)
 const editBookmark=(b:{title:string;url:string})=>{open("bookmarks");setBookmarkDraft({oldUrl:b.url,title:b.title,url:b.url})}
 const resize=useRef<{x:number;width:number;current:number}|null>(null)
 const [confirm, setConfirm] = useState<{ title: string; body: string; op: string } | null>(null)
 const pageRef = useRef<HTMLDivElement>(null)
 const commandRef = useRef<HTMLInputElement>(null)
 const commandChoice = useRef(false)
 const active = state.tabs.find(t => t.id === state.activeId) ?? state.tabs[0]
 const suggestions = useMemo(() => rankSuggestions(query, state.history, state.bookmarks, active?.isPrivate), [query, state.history, state.bookmarks, active?.isPrivate])
 const addressRef = useRef<HTMLInputElement>(null)
 const paneRef = useRef("")
 const [pick, setPick] = useState(-1)
 const [ghost, setGhost] = useState<Ghost | null>(null)
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
  if (q && q !== active?.url && !completion) items.push({ key: "go", icon: <Search size={15} />, title: q, sub: /^[^\s]+\.[^\s]+$/.test(q) || /^https?:/.test(q) ? "Go to address" : "Search " + state.preferences.search, run: () => go(q) })
  suggestions.forEach(v => items.push({ key: "s" + v.url, icon: <Globe2 size={15} />, title: v.host, sub: v.bookmark ? v.title + " · Bookmark" : "Visited", value: prettyUrl(v.url), run: () => go(v.url) }))
  const lower = q.toLowerCase()
  state.tabs.filter(t => t.url && t.id !== state.activeId && (!q || q === active?.url || (t.title + t.url).toLowerCase().includes(lower))).slice(0, 4)
   .forEach(t => items.push({ key: "t" + t.id, icon: t.favicon ? <img className="tab-favicon" src={t.favicon} alt="" /> : <Globe2 size={15} />, title: t.title, sub: "Switch to tab", run: () => action("select", { id: t.id }) }))
  return items.slice(0, 9)
 }, [pane, query, completion, suggestions, state.tabs, state.activeId, active?.url, state.preferences.search])
 const sidebar = state.preferences.layout === "Sidebar" && !state.focusMode && !state.fullScreen
 const pinned = state.tabs.filter(t => t.pinned)
 const ordinary = state.tabs.filter(t => !t.pinned)
 useEffect(() => { paneRef.current = pane }, [pane])
 useEffect(() => { const t = setTimeout(() => setEntering(false), 700); return () => clearTimeout(t) }, [])
 useLayoutEffect(() => { if (pane !== "downloads") return; const r = document.querySelector('[aria-label="Downloads"]')?.getBoundingClientRect(); if (r) document.documentElement.style.setProperty("--dl-top", r.bottom + 8 + "px") }, [pane])
 useEffect(() => { if (state.permission) setShownPermission(state.permission) }, [state.permission])
 const modal = (!!pane && pane !== "find") || menu || context || !!confirm || !!ghost
 const findOpen = pane === "find"

 function open(name: string, value = "") { if (window.chrome?.webview) { send("openPanel", { name, value }); return } setQuery(value); setFilter(""); setDisplayPane(name); setPane(name) }
 function close() { setPane(""); send("panel", { name: "" }) }
 function go(url: string) { close(); send("navigate", { url }) }
 function action(op: string, payload: Record<string, unknown> = {}) { close(); send(op, payload) }
 function preference(key: string, value: string) { send("preference", { key, value }) }

 useEffect(() => {
  const listener = (e: MessageEvent) => {
   const data = e.data
   if (data.kind === "state") setState(data)
   if (data.kind === "tools") setToolData(old=>({...old,[data.name]:data.data}))
   if (data.kind === "panel") { setPane(data.name); if (data.name) { commandChoice.current=false; setDisplayPane(data.name); setQuery(data.value ?? ""); setFilter(""); if (data.name === "settings") setSettingsPage("appearance") } }
   if (data.kind === "toast") { toast(data.message);setNotice(data.message) }
   if (data.kind === "snapshot") setSnapshot(data.data)
   if (data.kind === "tabArrived") { setArriving(data.id); setTimeout(() => setArriving(""), 700) }
   if (data.kind === "escape") { setPane(""); setMenu(false); setContext(false); setConfirm(null); send("panel", { name: "" }); document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })) }
  }
  window.chrome?.webview?.addEventListener("message", listener)
  send("ready")
  return () => window.chrome?.webview?.removeEventListener("message", listener)
 }, [])
 useEffect(() => { document.documentElement.classList.toggle("dark", state.dark) }, [state.dark])
 useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(""),6500);return()=>clearTimeout(timer)},[notice])
 useEffect(()=>{document.documentElement.style.setProperty("--sidebar-width",state.preferences.sidebarWidth+"px")},[state.preferences.sidebarWidth])
 useEffect(() => {
  if (modal) { send("overlay", { value: true }); return }
  const timer = setTimeout(() => send("overlay", { value: false }), reduced ? 0 : 210)
  return () => clearTimeout(timer)
 }, [modal, reduced])
 useEffect(() => {
  if (pane === "address") { const t = setTimeout(() => { if (document.activeElement !== addressRef.current) { addressRef.current?.focus(); addressRef.current?.select() } }, 30); return () => clearTimeout(t) }
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
 }, [sidebar, state.focusMode, state.fullScreen, findOpen])
 useEffect(() => {
  const handler = (e: KeyboardEvent) => {
   if (e.key === "F11") { e.preventDefault(); send("fullscreen"); return }
   if (e.key === "Escape") { if(!document.querySelector("[role=dialog],[role=alertdialog],[role=menu]"))send("exitFullscreen"); close(); return }
   if (!(e.ctrlKey || e.metaKey)) return
   if (e.key.toLowerCase() === "l") { e.preventDefault(); openAddress() }
   if (e.key.toLowerCase() === "k") { e.preventDefault(); open("tabs") }
  }
  window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler)
 }, [active?.url])

 const commandOpen = pane === "tabs"
 const openAddress = (_el?: Element | null) => { addressRef.current?.focus() }
 const dialogOpen = !!pane && !commandOpen && pane !== "find" && pane !== "address" && pane !== "downloads"
 const title = ({ profiles:"Profiles", import:"Import browsing data", passwords:"Passwords", extensions:"Extensions", cookies:"Cookies", security:"Privacy & security", settings: "Settings", history: "History", bookmarks: "Bookmarks", downloads: "Downloads", site: host(active?.url ?? "") || "Site controls", shortcuts: "Keyboard shortcuts", about: "Still" } as Record<string, string>)[displayPane] ?? ""
 const filtered = (displayPane === "bookmarks" ? state.bookmarks : state.history).filter(v => (v.title + v.url).toLowerCase().includes(filter.toLowerCase())).slice(0, 100)
 const windowControls = (
<div className="window-controls" aria-label="Window controls">
     <AnimatedButton variant="ghost" size="icon" className="window-control" aria-label="Minimize" onClick={()=>send("minimize")} whileHover={{scale:1.06}} whileTap={{scale:.9}} transition={FLOW}><Minus /></AnimatedButton>
     <AnimatedButton variant="ghost" size="icon" className="window-control" aria-label={state.maximized ? "Restore" : "Maximize"} onClick={()=>send("maximize")} whileHover={{scale:1.06}} whileTap={{scale:.9}} transition={FLOW}>{state.maximized?<Copy/>:<Square/>}</AnimatedButton>
     <AnimatedButton variant="ghost" size="icon" className="window-control window-close" aria-label="Close Still" onClick={()=>send("closeWindow")} whileHover={{scale:1.06}} whileTap={{scale:.9}} transition={FLOW}><X /></AnimatedButton>
    </div>
 )
 return <UICtx.Provider value={{state,setContext,open,arriving,setGhost}}><MotionConfig reducedMotion="user" transition={FLOW}><TooltipProvider delayDuration={650}>
  <div className={cn("browser-shell", !sidebar && "horizontal-layout", state.fullScreen && "is-fullscreen", entering && state.secondary && "window-enter", state.incognito && "is-incognito")} data-reduced-motion={!!reduced}>
   {!sidebar && !state.focusMode && !state.fullScreen && <div className="top-tab-strip" onDoubleClick={e => { if (e.target === e.currentTarget || (e.target as HTMLElement).classList.contains("top-tab-list")) send("maximize") }} onPointerDown={e => { if (e.button === 0 && (e.target === e.currentTarget || (e.target as HTMLElement).classList.contains("top-tab-list"))) send("drag") }}><LayoutGroup id="top"><div className="top-tab-list"><FlowTabs tabs={[...pinned, ...ordinary]} top /><Button variant="ghost" size="icon-sm" aria-label="New tab" onClick={() => send("new")}><Plus /></Button></div></LayoutGroup>{windowControls}</div>}
   <header className="window-bar" onDoubleClick={e => { if (e.target === e.currentTarget) send("maximize") }} onPointerDown={e => { if (e.button === 0 && e.target === e.currentTarget) send("drag") }}>
    <nav className="nav-controls" aria-label="Page navigation">
     <IconButton label="Back" disabled={!state.canBack} onClick={() => send("back")}><ArrowLeft /></IconButton>
     <IconButton label="Forward" disabled={!state.canForward} onClick={() => send("forward")}><ArrowRight /></IconButton>
     <IconButton label={active?.loading ? "Stop loading" : "Reload"} caption={active?.loading?"Stop":"Reload"} onClick={() => send("reload")}>{active?.loading ? <X /> : <RotateCw />}</IconButton>
    </nav>
    {state.incognito && <span className="incognito-badge"><LockKeyhole />Incognito</span>}
    <ContextMenu onOpenChange={setContext}><ContextMenuTrigger asChild>
    <div className={cn("address-bar", pane === "address" && "is-editing")} onMouseDown={e => { if (e.target === e.currentTarget) { e.preventDefault(); addressRef.current?.focus() } }}>
     {active?.isPrivate ? <LockKeyhole /> : active?.secure ? <Shield /> : <Search />}
     <input ref={addressRef} className="address-input" aria-label="Search or enter an address" spellCheck={false} autoComplete="off"
      placeholder="Search or enter an address"
      value={pane === "address" ? (pick >= 0 && addressItems[pick]?.value ? addressItems[pick].value! : query + completion) : (notice || (active?.url ? prettyUrl(active.url) : ""))}
      onFocus={e => { if (pane !== "address") { typedRef.current = false; setQuery(active?.url ?? ""); setPick(-1); setPane("address"); setDisplayPane("address"); send("openPanel", { name: "address", value: active?.url ?? "" }) } requestAnimationFrame(() => e.target.select()) }}
      onChange={e => { const ne = e.nativeEvent as InputEvent; const del = (ne.inputType ?? "").startsWith("delete"); typedRef.current = !del; if (del) setCompletion(""); setQuery(e.target.value); setPick(-1) }}
      onKeyDown={e => {
       const count = addressItems.length
       if (e.key === "ArrowDown") { e.preventDefault(); setPick(p => Math.min(count - 1, p + 1)) }
       else if (e.key === "ArrowUp") { e.preventDefault(); setPick(p => Math.max(-1, p - 1)) }
       else if ((e.key === "Tab" && !e.shiftKey || e.key === "ArrowRight") && completion) { e.preventDefault(); typedRef.current = false; setQuery(query + completion); setCompletion("") }
       else if (e.key === "Tab" && !e.shiftKey && suggestions.length) { e.preventDefault(); typedRef.current = false; setQuery(suggestions[0].host) }
       else if (e.key === "Enter") { e.preventDefault(); const item = pick >= 0 ? addressItems[pick] : null; if (item) item.run(); else if (completion) go(query + completion); else if (query.trim()) go(query); addressRef.current?.blur() }
       else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); addressRef.current?.blur() }
      }}
      onBlur={() => { setTimeout(() => { if (document.activeElement !== addressRef.current && paneRef.current === "address") close() }, 120) }} />
     {pane !== "address" && <kbd>Ctrl L</kbd>}
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
     <IconButton label="Bookmark this page" caption="Bookmark" onClick={() => send("bookmark")}><Bookmark className={state.bookmarks.some(b => b.url === active?.url) ? "bookmarked" : ""} /></IconButton>
     <IconButton label="Site controls" caption="Site" onClick={() => open("site")}><Shield /></IconButton>
     <IconButton label="Reading mode" caption="Reader" onClick={() => send("reader")}><BookOpen /></IconButton>
     {state.update && <Button size="sm" className={cn("update-pill", state.update.busy && "is-busy")} disabled={state.update.busy && state.update.ready} onClick={() => send("openUpdate")} title={`Update Still to ${state.update.version}. It installs automatically and reopens with your tabs.`}>
      {state.update.busy ? <Loader2 className="spin" /> : <Download />}
      {state.update.busy ? (state.update.ready ? "Restarting…" : `Updating… ${state.update.progress ?? 0}%`) : "Update"}
     </Button>}
     <IconButton label="Downloads" onClick={() => open("downloads")}><span className="dl-icon"><Download />{activeDownloads.length > 0 && <i className="dl-mini"><b style={{ width: Math.max(8, dlProgress * 100) + "%" }} /></i>}</span></IconButton>
     <IconButton label="Passwords" onClick={()=>open("passwords")}><KeyRound />{state.loginOffer&&<i className="login-dot" aria-label="Login ready to save"/>}</IconButton>
     <IconButton label="Extensions" onClick={()=>open("extensions")}><Puzzle /></IconButton>
     <DropdownMenu open={menu} onOpenChange={setMenu}><DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Menu" className="chrome-button expanding-button"><span className="chrome-icon"><MoreHorizontal /></span><span className="chrome-label" aria-hidden="true"><span>Menu</span></span></Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={10} className="w-60">
       <DropdownMenuItem onSelect={() => send("new")}><Plus />New tab<DropdownMenuShortcut>Ctrl T</DropdownMenuShortcut></DropdownMenuItem>
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
       <DropdownMenuItem onSelect={() => send("pip")}><ExternalLink />Picture in picture</DropdownMenuItem>
       <DropdownMenuSeparator />
       <DropdownMenuItem onSelect={() => preference("layout", sidebar ? "Top" : "Sidebar")}><PanelLeft />Switch tab layout</DropdownMenuItem>
       <DropdownMenuItem onSelect={() => send("fullscreen")}><Expand />Full screen<DropdownMenuShortcut>F11</DropdownMenuShortcut></DropdownMenuItem>
       <DropdownMenuItem onSelect={() => send("focus")}><Expand />{state.focusMode ? "Leave focus mode" : "Focus mode"}</DropdownMenuItem>
       <MenuPanelItem name="settings" label="Settings" icon={<Settings2 />} keys="Ctrl ," />
      </DropdownMenuContent>
     </DropdownMenu>
    </div>
    {sidebar && windowControls}
   </header>
   <div className="workspace">
    {sidebar && <aside className="browser-sidebar">
     <div className="sidebar-resize" role="separator" aria-label="Resize sidebar" aria-orientation="vertical" tabIndex={0}
      onKeyDown={e=>{if(e.key==="ArrowLeft"||e.key==="ArrowRight"){e.preventDefault();send("sidebarResize",{width:state.preferences.sidebarWidth+(e.key==="ArrowRight"?10:-10)})}}}
      onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);resize.current={x:e.clientX,width:e.currentTarget.parentElement!.getBoundingClientRect().width,current:state.preferences.sidebarWidth}}}
      onPointerMove={e=>{if(resize.current){const value=Math.max(190,Math.min(360,resize.current.width+e.clientX-resize.current.x));resize.current.current=value;document.documentElement.style.setProperty("--sidebar-width",value+"px")}}}
      onPointerUp={()=>{if(resize.current){send("sidebarResize",{width:resize.current.current});resize.current=null}}}
      onPointerCancel={()=>{resize.current=null;document.documentElement.style.setProperty("--sidebar-width",state.preferences.sidebarWidth+"px")}} />
     <ScrollArea className="tabs-scroll"><LayoutGroup id="side">
      <div className="pinned-tabs"><FlowTabs tabs={pinned} /></div>
      <div className="tab-list"><FlowTabs tabs={ordinary} /></div>
     </LayoutGroup>
     <Button variant="ghost" className="new-tab" onClick={() => send("new")}><Plus /><span>New tab</span><kbd>Ctrl T</kbd></Button>
     </ScrollArea>
     <footer className="sidebar-footer">
      <Button variant="ghost" size="icon-sm" aria-label="Settings" onClick={() => open("settings")}><Settings2 /></Button>
      <Button variant="ghost" className="still-signature" onClick={() => open("about")}>still<span>{state.profileName}</span></Button>
      <Hint label={state.dark ? "Switch to light" : "Switch to black"}><Button variant="ghost" size="icon-sm" aria-label="Switch theme" onClick={() => preference("theme", state.dark ? "Light" : "Dark")}>{state.dark ? <Moon /> : <Sun />}</Button></Hint>
     </footer>
    </aside>}
    <main className="page-column">
     {pane === "find" && <div className="find-bar"><Input autoFocus placeholder="Find on this page" aria-label="Find in page" value={filter} onChange={e => setFilter(e.target.value)} onKeyDown={e => { if (e.key === "Enter") send("find", { text: filter }) }} /><Button variant="ghost" size="sm" onClick={() => send("find", { text: filter })}>Next</Button><Button variant="ghost" size="icon-sm" aria-label="Close find" onClick={close}><X /></Button></div>}
     {!state.focusMode && !state.fullScreen && state.bookmarks.length > 0 && <nav className={cn("bookmarks-bar", barOpen && state.bookmarks.length >= 5 && "is-expanded")} aria-label="Bookmarks bar">
      <div className="bookmarks-bar-list">{state.bookmarks.slice(0, barOpen ? 200 : 40).map(b => <BookmarkMenu key={b.url} b={b} onEdit={editBookmark}><Button variant="ghost" size="sm" className="bookmark-chip" title={b.title + " · " + b.url} onClick={() => send("navigate", { url: b.url })}><span className="bookmark-letter">{(host(b.url)[0] ?? "•").toUpperCase()}</span><span className="bookmark-name">{b.title || host(b.url)}</span></Button></BookmarkMenu>)}</div>
      {state.bookmarks.length >= 5 && <Button variant="ghost" size="icon-sm" className="bookmark-toggle" aria-expanded={barOpen} aria-label={barOpen ? "Collapse bookmarks" : "Expand bookmarks"} title={barOpen ? "Show one row" : `Show all ${state.bookmarks.length} bookmarks`} onClick={() => setBarOpen(!barOpen)}><ChevronRight /></Button>}
      <Button variant="ghost" size="sm" className="bookmark-chip bookmark-all" onClick={() => open("bookmarks")}><Bookmark />All bookmarks</Button>
     </nav>}
     <div className={cn("permission-wrap", state.agent && "is-open")}><div className={cn("permission-bar agent-bar", state.agent?.pending && "is-asking")} role="alertdialog" aria-label="AI agent" aria-hidden={!state.agent}>
      <Bot /><span>{state.agent?.pending
       ? <><b>{state.agent.client}</b> wants to control Still. It can open, read and click pages, but never private tabs, passwords or cookies.</>
       : <><b>{state.agent?.client}</b> is using Still{state.agent?.action ? " · " + state.agent.action : ""}</>}</span>
      {state.agent?.pending
       ? <><Button variant="ghost" size="sm" onClick={() => send("agentAnswer", { allow: false })}>Block</Button><Button size="sm" onClick={() => send("agentAnswer", { allow: true })}>Allow</Button></>
       : <Button variant="ghost" size="sm" onClick={() => send("agentStop")}><X />Stop</Button>}
     </div></div>
     <div className={cn("permission-wrap", state.permission && "is-open")}><div className="permission-bar" role="alertdialog" aria-label="Site permission" aria-hidden={!state.permission}>
      <ShieldCheck /><span><b>{shownPermission?.site}</b> wants to {shownPermission?.kind}.</span>
      <Button variant="ghost" size="sm" disabled={!state.permission} onClick={() => state.permission && send("permissionAnswer", { id: state.permission.id, allow: false })}>Block</Button>
      <Button size="sm" disabled={!state.permission} onClick={() => state.permission && send("permissionAnswer", { id: state.permission.id, allow: true })}>Allow</Button>
     </div></div>
     <div className="page-slot" ref={pageRef}>
      {active?.url ? (snapshot && <img className="page-snapshot" src={snapshot} alt="" />) : <motion.div key={active?.id} className="new-tab-page" initial={{ opacity: 0, y: reduced ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? .01 : .38, ease: [.22, 1, .36, 1] }}>
       <div className="still-mark" aria-hidden><i /><i /></div>
       <h1>still.</h1>
       <p>{active?.isPrivate ? "A little privacy." : "Where to?"}</p>
       <Button variant="outline" className="start-search" onClick={e => openAddress(e.currentTarget)}><Search /><span>Search or enter an address</span><kbd>Ctrl L</kbd></Button>
       {!active?.isPrivate && state.bookmarks.length > 0 && <div className="speed-dial">{state.bookmarks.slice(0, 8).map(b => <BookmarkMenu key={b.url} b={b} onEdit={editBookmark}><button className="speed-dial-tile" title={b.url} onClick={() => send("navigate", { url: b.url })}><span className="speed-dial-letter">{(host(b.url)[0] ?? "•").toUpperCase()}</span><span className="speed-dial-name">{b.title || host(b.url)}</span></button></BookmarkMenu>)}</div>}
       {active?.isPrivate && <span className="private-caption"><LockKeyhole />This tab and its history won't be saved.</span>}
      </motion.div>}
     </div>
     {active?.loading && <div className="loading-line" aria-label="Loading page"><i /></div>}
    </main>
   </div>
  </div>


  {pane === "downloads" && <><div className="dl-backdrop" onMouseDown={close} />
   <div className="dl-card" role="dialog" aria-label="Downloads">
    <div className="dl-head"><strong>Downloads</strong><Button variant="ghost" size="sm" onClick={() => send("downloadsFolder")}><FolderOpen />Open folder</Button></div>
    <div className="dl-list">{state.downloads.length ? state.downloads.slice(0, 8).map(d => {
     const pct = d.total ? Math.min(100, Math.round(d.bytes / d.total * 100)) : null
     const size = (n: number) => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"
     return <div className="dl-row" key={d.id}>
      <Download className="dl-file" />
      <div className="dl-meta"><button className="dl-name" disabled={d.status !== "Completed"} onClick={() => send("openDownload", { id: d.id })}>{d.name}</button>
       <small>{d.status === "InProgress" ? `${size(d.bytes)}${d.total ? " of " + size(d.total) : ""}${pct !== null ? " · " + pct + "%" : ""}` : d.status === "Completed" ? size(d.bytes) + " · Done" : d.status === "Interrupted" ? "Failed or cancelled" : d.status}</small>
       {d.status === "InProgress" && <div className="dl-bar"><i style={{ width: (pct ?? 30) + "%" }} className={pct === null ? "is-indeterminate" : ""} /></div>}</div>
      <Button variant="ghost" size="icon-sm" aria-label={d.status === "InProgress" ? "Cancel download" : "Show in folder"} onClick={() => send(d.status === "InProgress" ? "cancelDownload" : "showDownload", { id: d.id })}>{d.status === "InProgress" ? <X /> : <FolderOpen />}</Button>
     </div> }) : <p className="dl-empty">Files you download will show up here.</p>}</div>
   </div></>}
  {ghost && <div className={cn("tab-ghost", ghost.tearing && "is-tearing")} style={{ left: ghost.x + 14, top: ghost.y + 10 }}>
   <span className="tab-ghost-icon">{ghost.favicon ? <img src={ghost.favicon} alt="" /> : <Globe2 />}</span><span className="tab-ghost-title">{ghost.title}</span>
   {ghost.tearing && <span className="tab-ghost-hint"><Copy />New window</span>}
  </div>}
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
   <DialogContent className={cn("app-dialog", displayPane === "settings" && "settings-dialog", (displayPane === "history" || displayPane === "bookmarks") && "library-dialog")}>
    <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{displayPane === "settings" ? "A few things to make it yours." : displayPane === "about" ? "A quieter window onto the internet." : displayPane === "profiles" ? "Separate spaces for your browsing." : displayPane === "import" ? "Import a browser profile or a saved export." : displayPane === "passwords" ? "Your logins, protected on this PC." : displayPane === "extensions" ? "Add tools to your browser." : displayPane === "cookies" ? "Manage website cookies." : displayPane === "security" ? "Browser protection and site permissions." : displayPane === "site" ? (active?.certificateError ? "The certificate could not be verified. Connection blocked." : active?.secure ? "Connection secured with HTTPS." : active?.loading ? "Checking this connection…" : "This page does not have a verified HTTPS connection.") : displayPane === "history" ? "Your recent visits, kept on this PC." : displayPane === "bookmarks" ? "The pages you want to come back to." : displayPane === "downloads" ? "Files from this session." : "Keep your hands on the keys."}</DialogDescription></DialogHeader>
    {["passwords","extensions","cookies","security","profiles","import"].includes(displayPane)&&<BrowserTools key={displayPane} pane={displayPane} data={toolData[displayPane]??{}} send={send} url={active?.url??""} tracking={state.preferences.tracking} memory={state.preferences.memory} autofill={state.preferences.autofill}/> }
    {displayPane === "settings" && <Tabs value={settingsPage} onValueChange={setSettingsPage} className="settings-tabs">
     <LayoutGroup id="settings"><TabsList className="w-full">{[["appearance", "Appearance"], ["browsing", "Browsing"], ["data", "Your data"]].map(([value, label]) => <TabsTrigger value={value} key={value}>
      {settingsPage === value && <motion.span className="settings-selection" layoutId="settings-selection" transition={FLOW} />}<span className="settings-tab-label">{label}</span>
     </TabsTrigger>)}</TabsList></LayoutGroup>
     <TabsContent value="appearance" className="settings-content">
      <div className="setting-label">Theme</div><div className="theme-choices">{["Light", "Dark", "System"].map(theme => <Button key={theme} variant="outline" className={cn("theme-choice", state.preferences.theme === theme && "chosen")} onClick={() => preference("theme", theme)}>
       <div className={cn("theme-preview", theme.toLowerCase())}><i /><span /><b /></div><span>{theme === "Dark" ? "Black" : theme}{state.preferences.theme === theme && <Check />}</span>
      </Button>)}</div>
      <div className="setting-row"><div><strong>Tab layout</strong><p>Across the top, or down the side.</p></div><Select value={state.preferences.layout} onValueChange={v => preference("layout", v)}><SelectTrigger className="w-32"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="Sidebar">Sidebar</SelectItem><SelectItem value="Top">Top</SelectItem></SelectContent></Select></div>
      <Separator /><Button variant="ghost" className="settings-link" onClick={() => open("shortcuts")}><Keyboard />Keyboard shortcuts<ChevronRight /></Button>
     </TabsContent>
     <TabsContent value="browsing" className="settings-content">
      <div className="setting-row"><div><strong>Search engine</strong><p>Search only when you press Enter.</p></div><Select value={state.preferences.search} onValueChange={v => preference("search", v)}><SelectTrigger className="w-36"><SelectValue /></SelectTrigger><SelectContent>{["DuckDuckGo", "Google", "Bing"].map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent></Select></div>
      <Separator /><div className="setting-row"><div><strong>Let AI agents control Still (MCP)</strong><p>AI apps like Claude Desktop or Cursor can open, read and click pages for you. You approve each app first and can stop it anytime. Private tabs, passwords and cookies stay off-limits.</p></div><Switch aria-label="Let AI agents control Still" checked={!!state.preferences.agents} onCheckedChange={enabled => preference("agents", String(enabled))} /></div>
      {state.preferences.agents && state.mcpCommand && (() => { const cfg = JSON.stringify({ mcpServers: { still: { command: state.mcpCommand, args: ["--mcp"] } } }, null, 2); return <div className="mcp-config"><p className="tool-caption">Add this to your AI app's MCP settings:</p><pre>{cfg}</pre><Button variant="outline" size="sm" onClick={() => { send("copyText", { text: cfg }); setNotice("MCP config copied") }}><Copy />Copy config</Button></div> })()}
      <Separator /><div className="setting-row"><div><strong>Drag tabs into their own window</strong><p>Drag a tab out of the tab list to open it in a new window. Right-click a tab and choose Move to window to send it back.</p></div><Switch aria-label="Drag tabs into their own window" checked={!!state.preferences.tearOff} onCheckedChange={enabled => preference("tearOff", String(enabled))} /></div>
      <Separator /><div className="setting-row"><div><strong>Open Still at sign-in</strong><p>Start with your launch profile when you sign in to Windows.</p></div><Switch aria-label="Open Still at sign-in" checked={state.preferences.startup} onCheckedChange={enabled => send("startup", {enabled})} /></div>
      <Separator /><div className="setting-row"><div><strong>Default browser</strong><p>{state.preferences.isDefaultBrowser ? "Still opens your links." : "Open links from other apps in Still. Windows asks you to confirm."}</p></div>{state.preferences.isDefaultBrowser ? <span className="tool-caption">✓ Default</span> : <Button variant="outline" size="sm" onClick={() => send("defaultBrowser")}>Make default</Button>}</div>
      {state.preferences.startupDisabled && <p className="tool-caption">Windows has disabled this startup entry. <Button variant="link" onClick={() => send("startupSettings")}>Open Windows startup settings</Button></p>}
      <Separator /><div className="setting-row"><div><strong>Pick up where you left off</strong><p>Restore tabs when Still opens.</p></div><Switch aria-label="Restore tabs" checked={state.preferences.restore} onCheckedChange={v => preference("restore", String(v))} /></div>
      <Separator /><div className="setting-row"><div><strong>Block common ads & trackers</strong><p>A small built-in list. Some ads may remain.</p></div><Switch aria-label="Block ads and trackers" checked={state.preferences.blocking} onCheckedChange={v => preference("blocking", String(v))} /></div>
      <Separator /><div className="download-setting"><strong>Download folder</strong><p>{state.preferences.downloads}</p><Button variant="outline" size="sm" onClick={() => send("chooseDownloads")}><FolderOpen />Change folder</Button></div>
     </TabsContent>
     <TabsContent value="data" className="settings-content">
      <Button variant="ghost" className="settings-link" onClick={()=>open("passwords")}><KeyRound/>Passwords<ChevronRight/></Button><Button variant="ghost" className="settings-link" onClick={()=>open("cookies")}><Cookie/>Cookies<ChevronRight/></Button><Button variant="ghost" className="settings-link" onClick={()=>open("security")}><ShieldCheck/>Privacy & security<ChevronRight/></Button>
      <p className="data-intro">Tabs, bookmarks and history stay on this PC. Still has no account or cloud sync.</p>
      <Button variant="outline" className="settings-link" onClick={() => open("import")}><Import />Import browsing data<ChevronRight /></Button>
      <Button variant="ghost" className="settings-link" onClick={()=>open("profiles")}><UsersRound/>Profiles<ChevronRight/></Button>
      <Button variant="outline" className="settings-link" onClick={() => send("exportBookmarks")}><ExternalLink />Export bookmarks<ChevronRight /></Button>
      <Separator className="my-5" />
      <Button variant="ghost" className="settings-link" onClick={() => setConfirm({ title: "Clear your history?", body: "Your bookmarks and open tabs will stay.", op: "clearHistory" })}><History />Clear browsing history</Button>
      <Button variant="ghost" className="settings-link" onClick={() => setConfirm({ title: "Clear website data?", body: "This signs you out of websites in Still.", op: "clearCookies" })}><Trash2 />Clear cookies and website data</Button>
     </TabsContent>
    </Tabs>}
    {(displayPane === "history" || displayPane === "bookmarks") && <>{displayPane === "history" && state.history.length > 0 && <Button variant="ghost" className="settings-link" onClick={() => setConfirm({ title: "Clear your history?", body: "Your bookmarks and open tabs will stay.", op: "clearHistory" })}><History />Clear browsing history</Button>}{bookmarkDraft&&displayPane==="bookmarks"&&<form className="bookmark-edit" onSubmit={e=>{e.preventDefault();send("bookmarkEdit",bookmarkDraft);setBookmarkDraft(null)}}><Input aria-label="Bookmark name" value={bookmarkDraft.title} onChange={e=>setBookmarkDraft({...bookmarkDraft,title:e.target.value})}/><Input type="url" required aria-label="Bookmark URL" value={bookmarkDraft.url} onChange={e=>setBookmarkDraft({...bookmarkDraft,url:e.target.value})}/><div><Button type="button" variant="ghost" onClick={()=>setBookmarkDraft(null)}>Cancel</Button><Button type="submit">Save bookmark</Button></div></form>}<Input placeholder={"Search " + displayPane} aria-label={"Search " + displayPane} value={filter} onChange={e => setFilter(e.target.value)} /><ScrollArea className="library-scroll">{filtered.length ? filtered.map((v, i) => <div className="library-row" key={v.url + i}><Button variant="ghost" className="library-open" onClick={() => go(v.url)}><span className="site-initial">{[...v.title][0]}</span><span><strong>{v.title}</strong><small>{host(v.url)}{v.at && " · " + new Date(v.at).toLocaleDateString()}</small></span></Button>{displayPane==="bookmarks"&&<Button variant="ghost" size="icon-xs" aria-label={"Edit " + v.title} onClick={()=>setBookmarkDraft({oldUrl:v.url,title:v.title,url:v.url})}><Pencil/></Button>}<Button variant="ghost" size="icon-xs" aria-label={"Remove " + v.title} onClick={() => send(displayPane === "bookmarks" ? "removeBookmark" : "removeHistory", { url: v.url })}><X /></Button></div>) : <p className="empty-state">{displayPane === "bookmarks" ? "No bookmarks yet. Ctrl D saves a page." : "No visits here yet."}</p>}</ScrollArea></>}
    {displayPane === "downloads" && <><Button variant="outline" className="justify-start" onClick={() => send("downloadsFolder")}><FolderOpen />Open download folder</Button><ScrollArea className="library-scroll">{state.downloads.length ? state.downloads.map(d => <div className="download-row" key={d.id}><Download /><div><strong>{d.name}</strong><small>{d.status} · {(d.bytes / 1024).toFixed(0)} KB</small></div><Button variant="ghost" size="icon-sm" aria-label={d.status === "InProgress" ? "Cancel download" : "Show in folder"} onClick={() => send(d.status === "InProgress" ? "cancelDownload" : "showDownload", { id: d.id })}>{d.status === "InProgress" ? <X /> : <FolderOpen />}</Button></div>) : <p className="empty-state">Your downloads will appear here.</p>}</ScrollArea></>}
    {displayPane === "site" && <div className="site-settings"><div className="setting-row"><div><strong>Block ads & trackers</strong><p>{active?.blocked ?? 0} requests blocked on this page.</p></div><Switch aria-label="Blocking on this site" checked={state.siteBlocking} onCheckedChange={() => send("siteBlocking")} /></div><Separator /><Button variant="ghost" className="settings-link" onClick={() => action("hide")}><EyeOff />Hide something on this page</Button><Button variant="ghost" className="settings-link" onClick={() => action("unhide")}><RotateCw />Restore hidden elements</Button><Button variant="ghost" className="settings-link" onClick={() => send("pin")}><Pin />{active?.pinned ? "Unpin this tab" : "Pin this tab"}</Button><Button variant="ghost" className="settings-link" onClick={() => send("mute")}><VolumeX />{active?.muted ? "Unmute site" : "Mute site"}</Button></div>}
    {displayPane === "shortcuts" && <ScrollArea className="shortcuts-scroll">{shortcuts.map(([label, key]) => <div className="shortcut-row" key={label}><span>{label}</span><kbd>{key}</kbd></div>)}</ScrollArea>}
    {displayPane === "about" && <div className="about-content"><div className="still-mark"><i /><i /></div><p>A calm, fast browser for Windows. Black by default, quiet by design, and built to stay out of your way.</p><ul className="about-points"><li>Your tabs, history and passwords stay on this PC, with passwords encrypted by Windows.</li><li>Built-in tracker blocking, private tabs and separate profiles.</li><li>Imports everything from Opera GX, Chrome, Edge and Brave, including sign-ins.</li></ul>{state.update ? <div className="flex gap-2"><Button disabled={state.update.busy && state.update.ready} onClick={() => send("openUpdate")}>{state.update.busy ? <><Loader2 className="spin" />{state.update.ready ? "Restarting…" : `Updating… ${state.update.progress ?? 0}%`}</> : <><Download />Update to Still {state.update.version}</>}</Button><Button variant="ghost" onClick={() => send("releaseNotes")}>What's new</Button></div> : <Button variant="outline" onClick={() => send("checkUpdate")}><RotateCw />Check for updates</Button>}<p className="text-xs text-muted-foreground">Still updates itself automatically. New versions download in the background and install the next time you close Still.</p><p className="text-xs text-muted-foreground">Version {state.version ?? "1.6.6"} · Powered by Microsoft Edge WebView2 · Design inspired by Search by Office Commun</p><Button variant="outline" onClick={() => action("new", { url: "https://officecommun.com/search" })}>See the inspiration<ExternalLink /></Button></div>}
   </DialogContent>
  </Dialog>

  <AlertDialog open={!!confirm} onOpenChange={o => { if (!o) setConfirm(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{confirm?.title}</AlertDialogTitle><AlertDialogDescription>{confirm?.body}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => { if (confirm) send(confirm.op); setConfirm(null) }}>Clear</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  <Toaster theme={state.dark ? "dark" : "light"} position="top-center" offset={5} visibleToasts={1} duration={3000} toastOptions={{ className: "still-toast" }} />
 </TooltipProvider></MotionConfig></UICtx.Provider>
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
