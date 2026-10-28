// Tab niceties (Windows: MainWindow.Tabs.cs and parts of Actions.cs): chat tabs, the recent tabs switcher, tab groups,
// split view, the address bar's learned picks, reading mode, hidden elements, page source and favicons.
import AppKit
import WebKit

extension Browser {
 /// The tab whose page is on screen: the active tab, or for a chat tab whose page is open, the page its AI works in (beside the chat).
 var shown: Tab? {
  guard let tab = active, let chat = tab.chatId else { return active }
  guard tab.pageOpen else { return nil }
  return tabs.filter { ($0.inChat ?? $0.runChat) == chat && !$0.closed }.max { $0.lastSeen < $1.lastSeen }
 }
 /// The other half of a split, while the active tab is in one.
 var partner: Tab? {
  guard let left = splitLeft, let right = splitRight, !contentFullScreen else { return nil }
  return active === left ? right : active === right ? left : nil
 }
 /// A page's video (or other element) is full screen.
 var contentFullScreen: Bool {
  if #available(macOS 13.0, *) { return shown?.view.map { $0.fullscreenState != .notInFullscreen } ?? false }
  return false
 }

 /// The tab that shows this chat, opened next to the others if it isn't.
 func chatTab(_ chatId: String) -> Tab {
  if let open = tabs.first(where: { $0.chatId == chatId }) { return open }
  let tab = Tab()
  tab.chatId = chatId
  let title = aiChats.first { $0.id == chatId }?.title ?? ""
  tab.title = title.isEmpty ? "Chat" : title
  tabs.append(tab)
  saveLater()
  return tab
 }
 @discardableResult func openChatTab(_ chatId: String) -> Tab? {
  guard !chatId.isEmpty else { return nil }
  let tab = chatTab(chatId)
  select(tab)
  return tab
 }

 // MARK: Recent tabs

 // Ctrl+Tab goes back through the tabs you used most recently. A quick press flips to the last one;
 // holding Control shows the list, Tab and Shift+Tab move through it, and letting go of Control switches.
 func switchRecent(_ step: Int, held: Bool = false) {
  if recent == nil {
   guard let active else { return }
   var list = tabs.filter { $0.inChat == nil && !$0.closed && $0 !== active }.sorted { $0.lastSeen > $1.lastSeen }
   guard !list.isEmpty else { return }
   list.insert(active, at: 0)
   recent = list; recentIndex = 0; recentAt = Date(); recentHeld = false
   recentTimer?.invalidate()
   recentTimer = Timer.scheduledTimer(withTimeInterval: 0.03, repeats: true) { [weak self] _ in self?.recentTick() }
  }
  recentHeld = recentHeld || held // tests hold it open without a keyboard
  let count = recent?.count ?? 1
  recentIndex = ((recentIndex + step) % count + count) % count
  publishRecent()
 }
 func recentTick() {
  guard let recent else { recentTimer?.invalidate(); return }
  if recentHeld || NSEvent.modifierFlags.contains(.control) {
   // Still held: show the list after a moment, so a quick press never flashes it.
   if panel != "recent" && Date().timeIntervalSince(recentAt) > 0.18 { openPanel("recent", ""); publishRecent() }
   return
  }
  pickRecent(recent[recentIndex])
 }
 func pickRecent(_ pick: Tab?) {
  recentTimer?.invalidate(); recentTimer = nil
  let listed = panel == "recent"
  recent = nil
  if listed { closeSheet() }
  if let pick, !pick.closed, tabs.contains(where: { $0 === pick }) { select(pick) }
  else if listed, let view = shown?.view { window.makeFirstResponder(view) }
 }
 func publishRecent() { if let recent { send(["kind": "recent", "ids": recent.map(\.id), "index": recentIndex]) } }

 /// Option+Command+Left/Right: the next or previous tab, in strip order.
 func cycleTabs(_ step: Int) {
  let list = tabs.filter { $0.inChat == nil }
  guard list.count > 1, let active, let index = list.firstIndex(where: { $0 === active }) else { return }
  select(list[((index + step) % list.count + list.count) % list.count])
 }

 // MARK: Tab groups: named, colored and collapsible. A group's tabs stay side by side in the strip.

 static let groupColors = ["blue", "green", "amber", "rose", "violet", "cyan", "orange", "grey"]
 @discardableResult func newGroup(_ tab: Tab) -> TabGroup {
  let used = Set(store.groups.map(\.color))
  let group = TabGroup()
  group.color = Browser.groupColors.first { !used.contains($0) } ?? Browser.groupColors[store.groups.count % Browser.groupColors.count]
  store.groups.append(group)
  joinGroup(tab, group.id)
  return group
 }
 func joinGroup(_ tab: Tab, _ group: String) {
  guard !tab.pinned, tab.inChat == nil else { return }
  tab.group = ""
  let last = tabs.last { $0.group == group }
  tab.group = group
  if let last, last !== tab { tabs.removeAll { $0 === tab }; tabs.insert(tab, at: tabs.firstIndex { $0 === last }! + 1) }
  saveLater()
 }
 func leaveGroup(_ tab: Tab) {
  guard !tab.group.isEmpty else { return }
  let last = tabs.last { $0 !== tab && $0.group == tab.group }
  tab.group = ""
  if let last, let at = tabs.firstIndex(where: { $0 === tab }), at < tabs.firstIndex(where: { $0 === last })! {
   tabs.remove(at: at); tabs.insert(tab, at: tabs.firstIndex { $0 === last }! + 1)
  }
  saveLater()
 }

 // MARK: Split view: two tabs side by side in one window. Selecting either shows both; one pair per window.

 func splittable(_ tab: Tab) -> Bool { tab.chatId == nil && tab.inChat == nil && !tab.url.isEmpty && !tab.closed }
 func startSplit(_ other: Tab, right: Bool) {
  let pick = other !== active ? other : tabs.filter { $0 !== active && splittable($0) }.max { $0.lastSeen < $1.lastSeen }
  guard let here = active, let pick, splittable(here), splittable(pick) else { toast("Split view needs two open pages."); return }
  (splitLeft, splitRight) = right ? (here, pick) : (pick, here)
  splitRatio = 0.5
  // The pair sits together in the tab strip.
  tabs.removeAll { $0 === pick }
  tabs.insert(pick, at: tabs.firstIndex { $0 === here }! + (right ? 1 : 0))
  pick.group = here.group
  select(here)
 }
 func endSplit() { splitLeft = nil; splitRight = nil; layoutPages() }
 /// Clicking into the other half makes it the current tab: the address bar and buttons follow it.
 func focusSplitSide(_ tab: Tab) {
  guard tab !== active, partner === tab, !closing else { return }
  active?.lastSeen = Date()
  active = tab
  tab.lastSeen = Date()
  saveLater()
  schedulePublish()
 }

 /// Learned ranking: what you typed and the site you picked, so the address bar puts it first next time.
 func recordPick(_ typed: String, _ url: String) {
  let typed = typed.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
  guard active?.isPrivate == false, (1...60).contains(typed.count), let scheme = URL(string: url)?.scheme?.lowercased(), scheme == "http" || scheme == "https" else { return }
  let index = store.picks.firstIndex { $0["Typed"] as? String == typed && $0["Url"] as? String == url }
  var pick = index.map { store.picks.remove(at: $0) } ?? ["Typed": typed, "Url": url, "Count": 0]
  pick["Count"] = (pick["Count"] as? Int ?? 0) + 1
  pick["At"] = Browser.stamp.string(from: Date())
  store.picks.insert(pick, at: 0) // newest first, so the cap keeps the most recent
  if store.picks.count > 300 { store.picks.removeLast(store.picks.count - 300) }
  saveLater()
 }

 // MARK: Page holes

 /// The interface's AI glow and controls show through the shown page (not while a panel, a split or a full screen video is up).
 func cutHoles() {
  let shown = self.shown
  for tab in tabs {
   guard let view = tab.view as? PageView else { continue }
   let on = tab === shown && holes.tab == tab.id && (holes.frame > 0 || !holes.spots.isEmpty) && !view.isHidden && !overlay && partner == nil && !contentFullScreen
   if on { view.cut((holes.frame, holes.spots)) } else if view.holes != nil { view.cut(nil) }
  }
 }

 // MARK: Reading mode, hidden elements and page source

 func toggleReader() {
  guard let tab = active, tab === shown, let view = tab.view else { return }
  if tab.reader { tab.reader = false; view.reload(); return }
  let readability = (try? String(contentsOf: resources.appendingPathComponent("Readability.js"))) ?? ""
  guard !readability.isEmpty else { toast("Reading mode isn't available on this page."); return }
  let dark = self.dark
  let script = """
  (() => {
   const copy = document.cloneNode(true);
   copy.querySelectorAll('nav,aside,[role="navigation"],[role="banner"]').forEach(el=>el.remove());
   const article = new Readability(copy).parse();
   if (!article || article.textContent.trim().length < 120) return false;
   const doc = new DOMParser().parseFromString(article.content,'text/html');
   doc.querySelectorAll('script,iframe,object,embed,form,input,button,style,link,meta,base,nav,aside,[role="navigation"]').forEach(el=>el.remove());
   doc.querySelectorAll('*').forEach(el=>Array.from(el.attributes).forEach(a=>{
     if(a.name.startsWith('on') || a.name==='style' || a.name==='srcdoc' || ((a.name==='href'||a.name==='src') && /^\\s*(javascript|data):/i.test(a.value))) el.removeAttribute(a.name);
   }));
   const root = document.createElement('main');
   root.style.cssText='max-width:700px;margin:0 auto;padding:65px 32px 100px';
   const source=document.createElement('p');source.textContent=location.hostname+' · STILL READER';source.style.cssText='font:12px system-ui;letter-spacing:1px;opacity:.55';
   const title=document.createElement('h1');title.textContent=article.title;title.style.cssText='font:600 38px/1.2 system-ui;letter-spacing:-1px;margin:28px 0';
   const byline=document.createElement('p');byline.textContent=article.byline||'';byline.style.cssText='font:14px system-ui;opacity:.65;margin-bottom:32px';
   const hint=document.createElement('p');hint.textContent='⇧⌘R to return to the page';hint.style.cssText='font:12px system-ui;opacity:.55;margin-top:48px';
   root.append(source,title,byline,...doc.body.childNodes,hint);
   document.body.replaceChildren(root);
   document.body.removeAttribute('class');document.body.removeAttribute('style');
   const style=document.createElement('style');
   style.textContent='html,body{background:\(dark ? "#1C1C1E" : "#FAFAF7")!important;color:\(dark ? "#EAECE4" : "#30312D")!important;margin:0!important;font:19px/1.85 Georgia,serif!important} body main img{max-width:100%;height:auto} body main a{color:inherit;text-decoration:underline;text-underline-offset:3px} body main pre{overflow:auto} body main p{margin:1.25em 0}';
   document.head.querySelectorAll('style,link[rel="stylesheet"]').forEach(el=>el.remove());
   document.head.appendChild(style);
   return true;
  })();
  """
  view.evaluateJavaScript(readability + "\n;" + script, in: nil, in: stillWorld) { [weak self, weak tab] result in
   guard let self, let tab else { return }
   if case .success(let value) = result, value as? Bool == true { tab.reader = true; self.toast("Reading mode. ⇧⌘R returns to the page.") }
   else if case .success = result { self.toast("This page doesn't have an article to simplify.") }
   else { self.toast("Reading mode isn't available on this page.") }
  }
 }

 /// Click an element to hide it on this site from now on (private tabs: for this session).
 func pickHidden() {
  guard let tab = active, tab === shown, let view = tab.view, !tab.url.isEmpty else { return }
  tab.hideToken = newId(); tab.hideExpires = Date().addingTimeInterval(120)
  let script = """
  (() => {
    if (window.__stillCancelPicker) window.__stillCancelPicker();
    let last, oldOutline;
    const toast = document.createElement('div');
    toast.textContent = 'Click an element to hide it. Esc to cancel.';
    toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:2147483647;padding:14px 20px;background:#252624;color:white;border-radius:10px;font:14px system-ui;pointer-events:none';
    document.documentElement.appendChild(toast);
    function move(e) {
      if(last) last.style.outline = oldOutline;
      last = e.target; oldOutline = last.style.outline;
      last.style.outline = '2px solid #8c9a7d';
    }
    function cleanup() {
      if(last) last.style.outline = oldOutline;
      document.removeEventListener('mousemove',move,true);
      document.removeEventListener('click',pick,true);
      document.removeEventListener('keydown',key,true);
      toast.remove(); delete window.__stillCancelPicker;
    }
    function key(e) { if(e.key === 'Escape') { e.preventDefault(); cleanup(); } }
    function pick(e) {
      e.preventDefault(); e.stopImmediatePropagation();
      const el = e.target;
      if(el === document.body || el === document.documentElement) { cleanup(); return; }
      const parts = []; let n = el;
      while(n && n !== document.body) {
        if(n.id) { parts.unshift('#'+CSS.escape(n.id)); break; }
        let part = n.tagName.toLowerCase();
        const siblings = n.parentElement ? Array.from(n.parentElement.children).filter(x => x.tagName === n.tagName) : [];
        if(siblings.length > 1) part += ':nth-of-type(' + (siblings.indexOf(n)+1) + ')';
        parts.unshift(part); n=n.parentElement;
      }
      const selector=parts.join(' > ');
      cleanup();
      if(selector && selector.length < 500) {
        const style=document.createElement('style'); style.textContent=selector+'{display:none!important}';
        document.documentElement.appendChild(style);
        window.chrome.webview.postMessage({kind:'still-hide',token:'\(tab.hideToken ?? "")',selector,host:location.hostname});
      }
    }
    window.__stillCancelPicker=cleanup;
    document.addEventListener('mousemove',move,true);
    document.addEventListener('click',pick,true);
    document.addEventListener('keydown',key,true);
    setTimeout(cleanup,120000);
  })();
  """
  view.evaluateJavaScript(pageShim + script, in: nil, in: stillWorld) { _ in }
 }

 func receiveHidden(_ tab: Tab, _ data: [String: Any], _ frame: WKFrameInfo) {
  guard let token = tab.hideToken, Date() < tab.hideExpires, data["token"] as? String == token, let page = URL(string: tab.url), let host = page.host,
        frame.securityOrigin.host == host, frame.securityOrigin.protocol == page.scheme else { return }
  let selector = data["selector"] as? String ?? ""
  guard data["host"] as? String == host, (1...500).contains(selector.count), selector.rangeOfCharacter(from: CharacterSet(charactersIn: "{}\r\n")) == nil else { return }
  tab.hideToken = nil
  var list = (tab.isPrivate ? privateHidden[host] : store.hidden[host]) ?? []
  if !list.contains(selector) && list.count < 100 { list.append(selector) }
  if tab.isPrivate { privateHidden[host] = list } else { store.hidden[host] = list }
  saveLater()
  reinstallPageScripts()
  toast(tab.isPrivate ? "Hidden for this private session." : "Hidden on this site. Restore it in site controls.")
 }

 func unhide() {
  guard let tab = active, let host = URL(string: tab.url)?.host else { return }
  store.hidden[host] = nil
  privateHidden[host] = nil
  reinstallPageScripts()
  saveLater()
  tab.view?.reload()
 }

 /// The CSS that keeps a site's hidden elements hidden, from the start of every page.
 func hiddenScript(_ tab: Tab) -> String {
  var map = store.hidden
  if tab.isPrivate { map.merge(privateHidden) { _, session in session } }
  guard !map.isEmpty else { return "" }
  return """
  (() => {
    if (window !== top) return;
    const rules = \(jsonText(map));
    const selectors = rules[location.hostname] || [];
    if (!selectors.length) return;
    const install = () => {
      const style = document.createElement('style');
      style.id = 'still-hidden-rules';
      style.textContent = selectors.map(s => s + '{display:none!important}').join('\\n');
      (document.head || document.documentElement).appendChild(style);
    };
    if (document.documentElement) install(); else document.addEventListener('DOMContentLoaded', install, {once:true});
  })();
  """
 }

 /// The page's source in a new tab (WebKit has no view-source: pages). The shown page's own document, or a fresh copy.
 func viewSource(_ address: String) {
  func open(_ html: String) {
   let escaped = html.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
   let title = ("view-source:" + address).replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
   let tab = newTab(isPrivate: active?.isPrivate ?? false, prompt: false)
   let page = "<!doctype html><meta charset=utf-8><meta name=color-scheme content='light dark'><title>\(title)</title><pre style='white-space:pre-wrap;word-break:break-all;font:12px/1.5 ui-monospace,Menlo,monospace;margin:16px'>\(escaped)</pre>"
   (tab.view ?? createView(tab)).loadHTMLString(page, baseURL: nil)
  }
  if let view = shown?.view, shown?.url == address {
   view.evaluateJavaScript("document.documentElement.outerHTML", in: nil, in: stillWorld) { result in if case .success(let html as String) = result { open(html) } }
  } else if let url = URL(string: address), ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
   URLSession(configuration: .ephemeral).dataTask(with: url) { data, _, _ in
    let html = data.flatMap { String(data: $0, encoding: .utf8) ?? String(data: $0, encoding: .isoLatin1) } ?? ""
    DispatchQueue.main.async { if html.isEmpty { self.toast("Couldn't open that page's source.") } else { open(html) } }
   }.resume()
  }
 }

 // MARK: Favicons

 /// The site's icon as a small PNG data URL (the interface shows only data: images). Bookmarks for the site pick it up too.
 func updateFavicon(_ tab: Tab) {
  guard let view = tab.view, let page = view.url?.absoluteString, page.hasPrefix("http") else { return }
  let find = "(()=>{const l=[...document.querySelectorAll('link[rel~=\"icon\" i],link[rel=\"shortcut icon\" i],link[rel=\"apple-touch-icon\" i]')].find(e=>e.href&&!/\\.svg(\\?|$)/i.test(e.href));return l?l.href:location.origin+'/favicon.ico'})()"
  view.evaluateJavaScript(find, in: nil, in: stillWorld) { [weak self, weak tab] result in
   guard case .success(let href as String) = result, let url = URL(string: href), ["http", "https"].contains(url.scheme ?? "") else { return }
   URLSession(configuration: .ephemeral).dataTask(with: url) { data, _, _ in
    guard let data, data.count < 1_000_000, let image = NSImage(data: data), image.size.width > 0 else { return }
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 32, pixelsHigh: 32, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)
    guard let rep else { return }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    image.draw(in: NSRect(x: 0, y: 0, width: 32, height: 32))
    NSGraphicsContext.restoreGraphicsState()
    guard let png = rep.representation(using: .png, properties: [:]), png.count < 131072 else { return }
    DispatchQueue.main.async {
     guard let self, let tab, !tab.closed, tab.view?.url?.absoluteString == page else { return }
     tab.favicon = "data:image/png;base64," + png.base64EncodedString()
     if !tab.isPrivate {
      for i in self.bookmarks.indices where hostName(self.bookmarks[i]["Url"] as? String ?? "") == hostName(page) { self.bookmarks[i]["Favicon"] = tab.favicon }
     }
     self.saveLater()
     publishEverywhere()
    }
   }.resume()
  }
 }

 /// Esc: closes the recent list or a panel, else cancels the element picker and leaves a page's full screen.
 func escape() {
  if recent != nil { pickRecent(nil); return }
  send(["kind": "escape"])
  if !panel.isEmpty { closeSheet() }
  else { shown?.view?.evaluateJavaScript("if(window.__stillCancelPicker)window.__stillCancelPicker();if(document.fullscreenElement)document.exitFullscreen();", in: nil, in: stillWorld) { _ in } }
 }

 // MARK: Still's page scripts

 /// Still's scripts in pages: the draft keeper, the login observer and hidden elements, in their own world.
 func addPageScripts(_ tab: Tab, _ controller: WKUserContentController) {
  func add(_ source: String) { if !source.isEmpty { controller.addUserScript(WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true, in: stillWorld)) } }
  add(pageShim)
  if !tab.isPrivate { add(draftScript) }
  add(loginScript(tab))
  add(hiddenScript(tab))
 }
 /// After hidden elements or login settings change: every page gets the new scripts from its next load.
 func reinstallPageScripts() {
  for browser in browsers { for tab in browser.tabs { if let view = tab.view { browser.applyBlocking(view) } } }
 }

 func receivePage(_ tab: Tab, _ data: [String: Any], _ frame: WKFrameInfo) {
  guard frame.isMainFrame else { return }
  switch data["kind"] as? String {
  case "still-login": receiveLogin(tab, data, frame)
  case "still-hide": receiveHidden(tab, data, frame)
  default: break
  }
 }
}

/// Still's page scripts post here (only scripts in Still's own world can reach it).
final class PageMessages: NSObject, WKScriptMessageHandler {
 func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
  guard let view = message.webView, let text = message.body as? String, text.utf8.count <= 40000, let data = jsonObject(text) else { return }
  for browser in browsers { if let tab = browser.tabs.first(where: { $0.view === view }) { browser.receivePage(tab, data, message.frameInfo); return } }
 }
}
let pageMessages = PageMessages()
/// The scripts written for WebView2 post with window.chrome.webview, which in Still's world goes to PageMessages.
let pageShim = "window.chrome={webview:{postMessage:m=>webkit.messageHandlers.stillPage.postMessage(JSON.stringify(m))}};"
let draftScript = (try? String(contentsOf: resources.appendingPathComponent("draft.js"))) ?? ""
