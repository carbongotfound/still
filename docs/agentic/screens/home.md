# The chat home (new tab)

`still-ui/src/Home.tsx` and the home block in `App.tsx`. Every new tab opens on it.

- Rail on the left (`HomeRail`): New chat, Chats, Library, Companions, Skills, then settings and the profile.
  Each opens a page in place of the home; a chat tab's sidebar links open them in a new tab.
- Switcher at the top (`CompanionSwitch`): the active companion as a pill, the others as faces, a menu for the rest
  and a + for a new one. Running chats live in the toolbar's runner (see `agent.md`).
- The companion's face at 96 px, then the message box: `/` lists skills, + adds a skill or a link to an open tab,
  the mode chip picks the companion and Quick / Everyday / Thorough. The send button wears the companion's hue.
- Chips: Skills, Companions, Library, Help. "Try one of these": three cards, the first sums up an open tab.

## Modes

The chip's menu: find and pick a companion, then Quick, Everyday or Thorough, each with a line on what it does,
then an Advanced switch.

| Mode | Claude | Other AI apps |
|---|---|---|
| Quick (`efficient`) | `--model haiku --effort low` | effort low |
| Everyday (`default`) | the app's own defaults | the app's own defaults |
| Thorough (`expert`) | `--model opus --effort high` | effort high |

Advanced swaps the chip for the model and effort pickers (`Prefs.AiAdvanced`).

## Companions

Kept in `Prefs.Companions` (state.json): name, job, face, color, AI app, mode, skills. The crew to pick from is in
`crew.tsx` (Glint, Noon, Zest, Bloom, Fizz, Rivet and Mallow); others wear the mascot of the AI they run on. Eight hues: sage, lavender, apricot, mint, blush,
periwinkle, berry, ocean. The editor sets the look, name, job, the AI app ("Not installed" and "Sign in first"
show in the list), the mode, the skills they always use and what they remember.

## Memory

Markdown files in the profile: `companions/memory.md` (shared, on the Companions page) and
`companions/<id>/memory.md` (each companion, in the editor). 20,000 characters each. Both go into the first
message of a chat, under "What the user asked you to remember".

## Skills

One library per profile, `skills/<id>.md`: front matter (`name`, `description`, `when`) and the steps.
`/id` in a message, or a skill the companion always uses, adds the steps to the prompt and a "Read skill" row to the chat.

## Chat History

Search by title, filters for Unread (blue dot), Needs input (amber), Archived and Companion, newest or oldest first,
grouped Today / Yesterday / This week / Earlier. Hover a row to archive or delete it. A reply that lands while
you're on another tab or chat marks it unread.

Not built: the notification bell (there are no notifications yet); searching inside messages.

Tests: `python tests/desktop/companions.py <exe>` (31 checks, fake AI app, no plan used); `--shots` for the
screenshots below.

Shots: `compare/newtab-v03-*.png`, `compare/modes-v01-*.png`, `compare/companions-v01-*.png`, `compare/companion-editor-v02-*.png`,
`compare/skills-v01-*.png`, `compare/skill-chip-v01.png`, `compare/chats-v01.png`.
