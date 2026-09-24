(() => {
  if (window !== top || !(location.protocol === 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))) return;
  window.__stillLoginCleanup?.();
  const config = __STILL_LOGIN_CONFIG__;
  const post = window.chrome.webview.postMessage.bind(window.chrome.webview);
  let timer, lastField, lastSubmission = 0;
  const visible = e => e.getClientRects().length && !e.disabled && !e.readOnly;
  const passwordField = () => [...document.querySelectorAll('input[type=password]')].find(visible);
  function report(action, extra = {}) { post({ kind: 'still-login', token: config.token, origin: location.origin, action, ...extra }); }
  function scan() { const p = passwordField(); if (p && p !== lastField) { lastField = p; report('detected'); } }
  function schedule() { if (!document.hidden && !timer) timer = setTimeout(() => { timer = null; scan(); }, 350); }
  function submitted(e) {
    if (!config.capture || !e.isTrusted || Date.now() - lastSubmission < 1500) return;
    const p = passwordField(); if (!p || !p.value || p.value.length > 8192) return;
    const root = p.form || document;
    if (p.form && new URL(p.form.action || location.href, location.href).origin !== location.origin) return;
    if (e.type === 'submit' && e.target !== p.form) return;
    if (e.type === 'click') {
      const submitter = e.target.closest?.('button[type=submit],input[type=submit],button:not([type])');
      if (!submitter || (p.form ? submitter.form !== p.form : !root.contains(submitter))) return;
    }
    if (e.type === 'keydown' && (e.key !== 'Enter' || !root.contains(e.target))) return;
    const fields = [...root.querySelectorAll('input')].filter(visible);
    const u = fields.find(x => x !== p && ['text', 'email'].includes(x.type) && (/user|email|login/i.test(x.name + ' ' + x.id) || ['username', 'email'].includes(x.autocomplete))) || fields.find(x => x !== p && ['text', 'email'].includes(x.type));
    const next = fields.find(x => x.type === 'password' && x.autocomplete === 'new-password' && x.value);
    lastSubmission = Date.now();
    report('submitted', { username: (u?.value || '').slice(0, 1024), password: (next || p).value });
  }
  const observer = new MutationObserver(schedule);
  observer.observe(document, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', scan);
  document.addEventListener('focusin', scan);
  document.addEventListener('submit', submitted, true);
  document.addEventListener('click', submitted, true);
  document.addEventListener('keydown', submitted, true);
  window.__stillLoginCleanup = () => {
    observer.disconnect(); clearTimeout(timer);
    document.removeEventListener('DOMContentLoaded', scan);
    document.removeEventListener('focusin', scan);
    for (const type of ['submit', 'click', 'keydown']) document.removeEventListener(type, submitted, true);
  };
  scan();
})();
