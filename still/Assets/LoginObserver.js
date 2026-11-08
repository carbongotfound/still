// Still's password helper in a page: finds sign-in, sign-up, change-password and email-first forms, offers saved
// logins from a key in the field, suggests a strong password for new ones, and reports a submitted login so Still can
// offer to save it. Usernames and passwords come from Still only for this exact site, and only a person's click fills.
(() => {
  if (window !== top || !/^https?:$/.test(location.protocol)) return;
  window.__stillLoginCleanup?.();
  const config = __STILL_LOGIN_CONFIG__;
  const post = window.chrome.webview.postMessage.bind(window.chrome.webview);
  // The page's own scripts run later and could replace these; keep the originals.
  const make = Document.prototype.createElement.bind(document), shadow = Element.prototype.attachShadow;
  const setText = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent').set;
  const value = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  const formAction = Object.getOwnPropertyDescriptor(HTMLFormElement.prototype, 'action').get;
  const random = crypto.getRandomValues.bind(crypto);
  const api = '__stillLogin' + [...random(new Uint8Array(8))].map(b => b.toString(16).padStart(2, '0')).join('');
  let timer, signature = '', lastSubmission = 0, accounts = [], warn = false, auto = false, host, root, open = null, armed = '', suggestion = '';
  const visible = e => e.getClientRects().length && !e.disabled && !e.readOnly;
  const fields = scope => [...scope.querySelectorAll('input')].filter(visible);
  const text = e => ['text', 'email', 'tel', ''].includes(e.type);
  const userish = e => text(e) && (/\b(username|email|webauthn)\b/.test(e.autocomplete) || /user|e-?mail|login|account|identifier/i.test(e.name + ' ' + e.id + ' ' + (e.getAttribute('aria-label') || '') + ' ' + e.placeholder));
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  const searchy = e => /search|query|^q$/i.test(e.type + ' ' + e.name + ' ' + e.id) || !!e.closest('[role=search]');
  // What kind of form is on screen: login, signup, change, or username (the first step of a two-step sign-in).
  function scan() {
    const pw = [...document.querySelectorAll('input[type=password]')].filter(visible);
    if (pw.length) {
      const scope = pw[0].form || document, all = fields(scope);
      const user = all.find(x => userish(x) && before(x, pw[0])) || all.filter(x => text(x) && before(x, pw[0]) && !searchy(x)).pop() || all.find(userish);
      const fresh = pw.filter(x => /new-password/.test(x.autocomplete)), current = pw.filter(x => /current-password/.test(x.autocomplete));
      const kind = fresh.length ? (current.length || pw.length >= 3 ? 'change' : 'signup') : pw.length >= 3 ? 'change' : pw.length === 2 ? 'signup' : 'login';
      return { kind, user, pw, fresh: kind === 'login' ? [] : fresh.length ? fresh : kind === 'change' ? pw.slice(1) : pw, scope };
    }
    const user = fields(document).find(x => userish(x) && !searchy(x));
    return user ? { kind: 'username', user, pw: [], fresh: [], scope: user.form || document } : null;
  }
  // toJSON: a page's Object.prototype.toJSON would be handed this message, token and all, when it's sent.
  function report(action, extra = {}) { post({ kind: 'still-login', token: config.token, origin: location.origin, action, ...extra, toJSON: undefined }); }
  function check() {
    const form = scan(), now = form ? form.kind + form.pw.length : '';
    if (now !== signature) { signature = now; if (form) report('detected', { form: form.kind, api }); }
  }
  function schedule() { if (!document.hidden && !timer) timer = setTimeout(() => { timer = null; check(); }, 350); }
  function set(e, v) { if (!e) return; value.set.call(e, v); e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); }
  // A field a person can see and means to use: big enough, solid enough, and the thing at its centre.
  function real(e) {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (r.width < 24 || r.height < 10 || s.visibility !== 'visible') return false;
    for (let a = e; a; a = a.parentElement) if (+getComputedStyle(a).opacity < .5) return false;
    const top = e.getRootNode().elementFromPoint?.(r.left + r.width / 2, r.top + r.height / 2);
    return !!top && (top === e || e.contains(top));
  }
  // Auto sign-in waits for this, so a page can't collect a login with nobody there, or into a field nobody can see.
  function touched(e) {
    if (!auto || !e.isTrusted || e.type === 'keyup' && e.key !== 'Tab') return;
    const form = scan();
    if (!form || !['login', 'username'].includes(form.kind) || !(e.target === form.user || form.pw.includes(e.target)) || !real(e.target)) return;
    auto = false;
    report('auto');
  }
  const foreign = address => { try { return new URL(address, location.href).origin !== location.origin; } catch { return true; } };
  // Where this form would send what's in it: its own address (a field named "action" can't stand in for it) or one of its buttons'.
  const leaves = scope => scope instanceof HTMLFormElement && (foreign(formAction.call(scope)) || [...document.querySelectorAll('[formaction]')].some(b => b.form === scope && foreign(b.getAttribute('formaction'))));
  // Fills the username, and the password unless this is a username-only step. onlyEmpty: never overwrite what's typed.
  function fill(login, onlyEmpty) {
    const form = scan(); if (!form || form.kind === 'signup') return false;
    const p = form.pw.find(x => !form.fresh.includes(x));
    if (onlyEmpty && (p && value.get.call(p) || form.user && value.get.call(form.user) && value.get.call(form.user) !== login.username)) return false;
    if (leaves(form.scope)) return false;
    if (login.username) set(form.user, login.username);
    if (p) set(p, login.password);
    close();
    return true;
  }
  // A strong password: 20 characters (fewer if the field says so), with upper and lower case, digits and symbols.
  function strong(length) {
    const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*-_+';
    for (;;) {
      let out = '';
      while (out.length < length) for (const b of random(new Uint8Array(64))) if (b < 201 && out.length < length) out += letters[b % letters.length];
      if (/[A-Z]/.test(out) && /[a-z]/.test(out) && /\d/.test(out) && /[^A-Za-z\d]/.test(out)) return out;
    }
  }
  function ui() {
    if (host?.isConnected) return;
    host = make('still-passwords');
    host.style.cssText = 'all:initial;position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647';
    root = shadow.call(host, { mode: 'closed' });
    // A constructed sheet and DOM calls only, so pages with a strict CSP or Trusted Types still show it.
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(`
      :host{color-scheme:light dark}
      *{box-sizing:border-box;font:13px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:0}
      .key,.menu{position:fixed;--bg:#fbfaf7;--fg:#24211d;--muted:#6e675e;--line:#e4dfd6;--hover:#f0ece4;--accent:#3d6f5f;--warn:#9a5a12}
      @media (prefers-color-scheme:dark){.key,.menu{--bg:#22211f;--fg:#efebe4;--muted:#a59d92;--line:#3a3733;--hover:#2e2c29;--accent:#86c2ad;--warn:#e5ac5c}}
      .key{display:grid;place-items:center;width:24px;height:24px;border:0;border-radius:7px;background:var(--hover);color:var(--accent);cursor:pointer;padding:0;box-shadow:0 0 0 1px var(--line)}
      .key:hover{background:var(--line)} svg{width:15px;height:15px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
      .menu{min-width:260px;max-width:360px;padding:6px;border-radius:14px;background:var(--bg);color:var(--fg);border:1px solid var(--line);box-shadow:0 18px 40px -18px #0007,0 2px 8px -4px #0003}
      .item{display:flex;align-items:center;gap:10px;width:100%;padding:8px 10px;border:0;border-radius:9px;background:none;color:inherit;text-align:left;cursor:pointer}
      .item:hover,.item:focus-visible{background:var(--hover);outline:none} .item svg{color:var(--accent)}
      .item span{display:flex;flex-direction:column;min-width:0} b{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      small{font-size:11.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap} .mono{font-family:ui-monospace,Consolas,Menlo,monospace;color:var(--fg)}
      .item.armed b{color:var(--warn)} .warn{display:flex;gap:8px;margin:2px 4px 6px;padding:8px 10px;border-radius:9px;background:color-mix(in oklab,var(--warn) 14%,transparent);color:var(--warn);font-size:12px}
      .warn svg{margin-top:1px} .foot{display:block;width:100%;margin-top:4px;padding:8px 10px;border:0;border-top:1px solid var(--line);border-radius:0 0 9px 9px;background:none;color:var(--muted);text-align:left;cursor:pointer}
      .foot:hover{color:var(--fg)}`);
    root.adoptedStyleSheets = [sheet];
    for (const type of ['pointerdown', 'mousedown']) root.addEventListener(type, e => e.preventDefault()); // keep the caret in the field
    root.addEventListener('click', picked);
    (document.body || document.documentElement).append(host);
  }
  const KEY = 'M12.4 11.6 21 3M15.5 7.5l3 3L22 7l-3-3M13 15.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z';
  const SPARK = 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6';
  const ALERT = 'M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z';
  function el(tag, cls, icon) {
    const e = make(tag); if (cls) e.className = cls;
    if (icon) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'), path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      svg.setAttribute('viewBox', '0 0 24 24'); path.setAttribute('d', icon); svg.append(path); e.append(svg);
    }
    return e;
  }
  function line(icon, title, detail, data, mono) {
    const b = el('button', 'item', icon), s = make('span'), t = make('b'), d = make('small');
    setText.call(t, title); setText.call(d, detail); if (mono) d.className = 'mono';
    s.append(t, d); b.append(s); Object.assign(b.dataset, data); return b;
  }
  // The key sits inside the right end of the field; the menu opens under it.
  function place() {
    if (!open || !open.field.isConnected || !visible(open.field)) { close(); return; }
    const r = open.field.getBoundingClientRect();
    open.key.style.left = Math.max(0, r.right - 30) + 'px'; open.key.style.top = (r.top + (r.height - 24) / 2) + 'px';
    if (open.menu) { open.menu.style.left = Math.max(4, Math.min(r.left, innerWidth - open.menu.offsetWidth - 4)) + 'px'; open.menu.style.top = (r.bottom + 6) + 'px'; }
  }
  function menu() {
    if (!open || open.menu) return;
    const m = open.menu = el('div', 'menu');
    m.setAttribute('role', 'listbox');
    if (warn && accounts.length && !open.fresh) { const w = el('div', 'warn', ALERT), t = make('span'); setText.call(t, "This page isn't secure, so others on the network could see what's filled in."); w.append(t); m.append(w); }
    if (open.fresh) {
      suggestion ||= strong(open.field.maxLength > 0 ? Math.min(20, open.field.maxLength) : 20);
      m.append(line(SPARK, 'Use a strong password', suggestion, { generate: '1' }, true));
    } else for (const a of accounts) {
      const b = line(KEY, a.username || 'No username', armed === a.id ? 'Click again to fill it anyway' : location.host, { id: a.id });
      if (armed === a.id) b.classList.add('armed');
      m.append(b);
    }
    const foot = el('button', 'foot'); setText.call(foot, open.fresh ? 'Still saves it for you. Manage passwords' : 'Manage passwords'); foot.dataset.manage = '1'; m.append(foot);
    root.append(m); place();
  }
  function show(field, fresh) {
    if (!accounts.length && !fresh || fresh && field.maxLength > 0 && field.maxLength < 8) return;
    if (open?.field === field) return;
    close(); ui();
    const key = el('button', 'key', KEY); key.dataset.toggle = '1'; key.setAttribute('aria-label', 'Saved passwords');
    root.append(key); open = { field, fresh, key, menu: null }; place();
    if (!value.get.call(field)) menu();
  }
  function close() { if (!open) return; open.key.remove(); open.menu?.remove(); open = null; armed = ''; }
  function picked(e) {
    const b = e.target.closest?.('button'); if (!b || !e.isTrusted || !open) return;
    if (b.dataset.toggle) { if (open.menu) { open.menu.remove(); open.menu = null; } else menu(); return; }
    if (b.dataset.manage) { report('manage'); close(); return; }
    if (b.dataset.generate) {
      const form = scan(); if (!form) return;
      for (const f of form.fresh) set(f, suggestion);
      report('generated', { username: form.user ? value.get.call(form.user).slice(0, 1024) : '', password: suggestion });
      close(); return;
    }
    if (b.dataset.id) {
      if (warn && armed !== b.dataset.id) { armed = b.dataset.id; open.menu?.remove(); open.menu = null; menu(); return; }
      report('fill', { id: b.dataset.id, confirmed: warn }); close();
    }
  }
  function focused(t) {
    const form = scan(); if (!form || !(t instanceof HTMLInputElement)) return;
    if (form.fresh.includes(t)) show(t, true);
    else if (t === form.user || form.pw.includes(t)) show(t, false);
  }
  function submitted(e) {
    if (!e.isTrusted || Date.now() - lastSubmission < 1500) return;
    const form = scan(); if (!form) return;
    const { scope } = form;
    if (leaves(scope)) return;
    if (e.type === 'submit' && e.target !== scope) return;
    if (e.type === 'click') {
      const b = e.target.closest?.('button,input[type=submit],input[type=image],[role=button]');
      if (!b || !scope.contains(b) || b.type !== 'submit' && b.type !== 'image' && !/sign|log|continue|next|submit|register|create|join|save|change|update/i.test(b.innerText || b.value || b.getAttribute('aria-label') || '')) return;
    }
    if (e.type === 'keydown' && (e.key !== 'Enter' || !scope.contains(e.target))) return;
    const username = form.user ? value.get.call(form.user).slice(0, 1024) : '';
    if (form.kind === 'username') { if (username) { lastSubmission = Date.now(); report('username', { username }); } return; }
    if (!config.capture) return;
    const fresh = form.fresh.find(x => value.get.call(x)), current = form.pw.find(x => !form.fresh.includes(x));
    const password = value.get.call(fresh || current || form.pw[0]);
    if (!password || password.length > 8192) return;
    lastSubmission = Date.now();
    report('submitted', { username, password, current: fresh && current ? value.get.call(current) : '', form: form.kind });
  }
  Object.defineProperty(window, api, { value: Object.freeze({
    // From Still: the logins saved for this site, whether the page is insecure, and whether auto sign-in is on here.
    show(data) {
      accounts = data.accounts || []; warn = !!data.warn; auto = !!data.auto;
      if (document.activeElement && !open) focused(document.activeElement); // a field focused before Still answered
    },
    fill(login) { return fill(login, false); },
    auto(login) { return fill(login, true); },
  }) });
  const observer = new MutationObserver(schedule);
  observer.observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ['type'] });
  const listen = [['DOMContentLoaded', check], ['focusin', check], ['focusin', e => focused(e.target)], ['pointerdown', touched], ['keyup', touched], ['submit', submitted], ['click', submitted], ['keydown', submitted],
    ['keydown', e => { if (e.key === 'Escape') close(); }], ['scroll', () => place()],
    ['input', e => { if (open?.menu && e.target === open.field && e.isTrusted) { open.menu.remove(); open.menu = null; } }], // typing hides the list; the key brings it back
    ['focusout', e => { if (open && e.target === open.field) setTimeout(() => { if (open && document.activeElement !== open.field) close(); }, 150); }]];
  for (const [type, fn] of listen) document.addEventListener(type, fn, true);
  addEventListener('resize', place);
  window.__stillLoginCleanup = () => {
    observer.disconnect(); clearTimeout(timer); close(); host?.remove();
    for (const [type, fn] of listen) document.removeEventListener(type, fn, true);
    removeEventListener('resize', place);
  };
  check();
})();
