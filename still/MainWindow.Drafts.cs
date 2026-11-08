namespace Still;

public partial class MainWindow
{
 // Keeps what the user typed when a page reloads or navigates away by surprise (a long prompt in an AI chat, a post,
 // a form). The text stays in the tab's own sessionStorage for that site, so it survives a reload or a same-tab
 // navigation but never leaves the tab. If the box comes back empty, a small chip offers to put the text back.
 // A draft is forgotten once its box is emptied (sent), and never kept for passwords, cards or one-line search boxes.
 const string DraftScript = """
 (() => {
  if (window.top !== window || !/^https?:$/.test(location.protocol)) return;
  const KEY = '__stillDraft', MIN = 25, MAX_AGE = 6 * 3600e3;
  const named = e => [e.autocomplete, e.getAttribute('name'), e.id, e.getAttribute('aria-label'), e.getAttribute('placeholder')].join(' ');
  const secretName = /cc-|card|cvc|cvv|one-time|otp|password|passwd|pwd|passphrase|secret|token|api.?key|private.?key/i;
  const editable = e => e && (e.isContentEditable || e.tagName === 'TEXTAREA'
   || (e.tagName === 'INPUT' && /^(text|)$/.test(e.type) && !/search/i.test(named(e)))) && !secretName.test(named(e));
  // A key's header, or one long run of letters and digits: never kept, whatever the box is called.
  const secretText = t => /-----BEGIN [A-Z ]+-----/.test(t) || /(?:^|\s)(?=\S*\d)(?=\S*[A-Za-z])[\w+\/=.-]{24,}(?:\s|$)/.test(t);
  const root = e => e.isContentEditable ? e.closest('[contenteditable]:not([contenteditable=false])') || e : e;
  const text = e => e.isContentEditable ? e.innerText.trim() : e.value;
  const name = e => [e.tagName, e.id, e.getAttribute('name'), e.getAttribute('aria-label'), e.getAttribute('placeholder')].join('|');
  let field = null, saved = '';
  const read = () => { try { return JSON.parse(sessionStorage.getItem(KEY) || 'null') } catch { return null } };
  const write = d => { try { d ? sessionStorage.setItem(KEY, JSON.stringify(d)) : sessionStorage.removeItem(KEY) } catch { } };
  const draft = read();
  addEventListener('input', ev => {
   const e = ev.composedPath?.()[0] || ev.target;
   if (!editable(e)) return;
   field = root(e); const t = text(field);
   if (secretText(t)) { saved = ''; write(null); }
   else if (t.length >= MIN || t.includes('\n')) { saved = t; write({ text: t, field: name(field), path: location.pathname, at: Date.now() }); }
   else if (!t.trim()) { saved = ''; write(null); } // emptied by the user: nothing to keep
  }, true);
  // Submitted: forget it, it's been sent. Still there when the page goes away without that: keep it.
  addEventListener('submit', () => { saved = ''; write(null) }, true);
  addEventListener('pagehide', () => { if (field && field.isConnected && !text(field).trim() && saved) write(null) });
  // Offered on the next two pages at most (a reload, then maybe one more step), and only within 6 hours.
  if (!draft?.text || Date.now() - draft.at > MAX_AGE || draft.offered >= 2) { if (draft) write(null); return; }
  const offer = () => {
   // The page put the text back by itself (or the user retyped it): nothing to offer.
   const all = [...document.querySelectorAll('textarea,input,[contenteditable]:not([contenteditable=false])')];
   if (all.some(e => editable(e) && text(e).includes(draft.text.slice(0, 200)))) return;
   const host = document.createElement('still-draft'), shadow = host.attachShadow({ mode: 'closed' });
   shadow.innerHTML = `<style>
    div{position:fixed;right:16px;bottom:16px;z-index:2147483647;display:flex;align-items:center;gap:8px;max-width:min(380px,calc(100vw - 32px));padding:8px 8px 8px 12px;border-radius:12px;font:13px/1.35 system-ui,sans-serif;color:#111;background:#fff;box-shadow:0 8px 28px rgba(0,0,0,.22),0 0 0 1px rgba(0,0,0,.08)}
    @media (prefers-color-scheme:dark){div{color:#eee;background:#222;box-shadow:0 8px 28px rgba(0,0,0,.5),0 0 0 1px rgba(255,255,255,.1)}}
    span{flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
    button{font:inherit;border:0;border-radius:8px;padding:5px 10px;cursor:pointer}
    .go{background:#2563eb;color:#fff;font-weight:600}.x{background:transparent;color:inherit;opacity:.6;padding:5px 7px}
   </style><div role="status"><span></span><button class="go">Restore</button><button class="x" aria-label="Dismiss">✕</button></div>`;
   shadow.querySelector('span').textContent = 'Restore your text: “' + draft.text.replace(/\s+/g, ' ').slice(0, 60) + '”';
   shadow.querySelector('.x').onclick = () => { host.remove(); write(null) };
   shadow.querySelector('.go').onclick = () => {
    const visible = e => editable(e) && e.getClientRects().length && !e.disabled && !e.readOnly;
    const fields = [...document.querySelectorAll('textarea,input,[contenteditable]:not([contenteditable=false])')].filter(visible).map(root);
    const target = fields.find(e => name(e) === draft.field && !text(e).trim()) || fields.filter(e => !text(e).trim()).sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
    host.remove();
    if (!target) return;
    target.focus();
    // insertText goes through the page's own editor (React, ProseMirror, Lexical…), unlike setting .value.
    if (!document.execCommand('insertText', false, draft.text)) {
     const proto = target.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
     Object.getOwnPropertyDescriptor(proto, 'value')?.set?.call(target, draft.text);
     target.dispatchEvent(new Event('input', { bubbles: true }));
    }
   };
   document.documentElement.appendChild(host);
   if (!saved) write({ ...draft, offered: (draft.offered || 0) + 1 });
  };
  // Chat apps build their editor after load: give them a moment.
  if (document.readyState === 'complete') setTimeout(offer, 1500); else addEventListener('load', () => setTimeout(offer, 1500), { once: true });
 })();
 """;
}
