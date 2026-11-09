# Permissions

`still/MainWindow.Agents.cs` (`Gate`, `PermissionMode`, `Approve`, `SensitiveJs`), `still/MainWindow.Ai.cs`
(`permAnswer`, `permSet`, `permSensitive`, `permReset`) and `still-ui/src/Permissions.tsx` (cards, countdown,
the log, the settings page).

## What asks

Every tool call that touches a page goes through `Gate` before it runs. It sorts the call into one of four actions:

| Action | Tools | Default |
|---|---|---|
| Read pages | `read_page`, `find`, `screenshot`, `wait_for` | Always allow |
| Open pages | `open_tab`, `navigate`, back, forward, reload, switch and close tabs | Always allow |
| Click, type and scroll | `click`, `type`, `press_key`, `scroll`, `handle_dialog` | Allow in this chat (asks once per site in each chat) |
| Sensitive steps | any of the above that looks like one of the cases below | Ask every time |

A click, typing or key press is sensitive when the page says so (`SensitiveJs` looks at the element and its form):
- a purchase ("buy", "place order", "checkout", "pay"...): "It looks like a purchase."
- send, post or reply: "It sends something in your name."
- delete, remove, unsubscribe, or cancel an order or subscription: "It deletes or cancels something."
- submitting a form that posts, by button, Enter or `submit`: "It sends a form."
- typing into a password or payment field.

On a site you mark sensitive, every click and keystroke counts as sensitive.

The rule that applies is the most specific one: this companion on this site, this companion anywhere, everyone on
this site, everyone anywhere, then the defaults above. `list_tabs`, `ask_user` and `save_file` never ask;
`upload_file` keeps its own prompt.

## In a chat

- A step that needs your OK shows a card above the message box: what it wants to do, the site, and why it's
  sensitive. The runner in the toolbar says the chat needs you, and offers Allow once and Deny there too.
- One step: Deny, Always on this site, Allow once, Allow in this chat. On a sensitive step Allow once is the main
  button. Several steps at once (the AI can run tools side by side): one card, an X per step, Deny all and
  Approve all (N).
- A sensitive step you allowed without asking (a rule, or Allow in this chat) still waits: "Going ahead in 8s",
  with Cancel and Do it now.
- Stop answers every waiting card. A card nobody answers gives up after 10 minutes and tells the AI to ask in its reply.
- Every decision goes in the chat's log, under Permissions in the chat's details (newest first, last 100):
  "You allowed it in this chat", "Allowed by your settings", "Went ahead after 8 seconds", "You cancelled it"...

## Outside AI apps

AI apps that connect to Still themselves (no chat) ask in the bar at the top of the window before a sensitive step,
every time, unless a rule for everyone says otherwise. Everything else is allowed unless you set a rule for everyone or
mark the site sensitive. Then they ask in the bar too, and Allow in this chat lasts until Still closes.

## Settings → AI permissions

The four defaults, then your rules per site and per companion, each with Always allow / Allow in this chat / Ask
every time and a remove button. Add a rule with a site, who, an action and a permission. New sites after reading the
web: Ask first, Balanced (the default) or Fewer questions (`Reach`). Sensitive sites are chips
with an add box. Reset all (asks once more) clears every rule and sensitive site.

## Tests

`python tests/desktop/permissions.py <exe>`: a fake AI app drives a local shop with an Add to cart button and a
checkout form that posts. It covers once per chat, a new chat asking again, Deny, Always on this site, another site
still asking, Ask every time, a purchase asking where clicks are allowed, Deny keeping the order from the shop, the
countdown's Cancel and running out, Approve all, a sensitive site, Stop during a card, an outside app with and
without a rule, the settings page and Reset all, and the log in the chat's details.

Screens: `docs/agentic/compare/approval-v01.png`, `sensitive-v01.png`, `countdown-v01.png`, `approve-all-v01.png`,
`permissions-v01.png`, `audit-v01.png`.
