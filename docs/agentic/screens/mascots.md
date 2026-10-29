# Mascots

Original 3D characters, one per AI, built in code (`still-ui/src/mascot3d.tsx`): no model files, no stock assets.
Soft toon material with a rim light, ink outlines and a contact shadow. Each has its own silhouette and motion.

- Clay (Claude): a terracotta gumdrop with a clay curl, cheeks and stubby arms. Snappy springs.
- Mo (ChatGPT): a round teal buddy with a pale belly and a leaf sprout. Slow, floaty springs.
- Vex (Grok): a graphite capsule with a dark visor, lime eyes, an antenna and floating hands. Quick, hovering.

States: idle (breathing, blinking, glancing around), listening, thinking (head tilt, orbiting dots), working (busy loop),
needs (bounce and wave), done (a small celebration), error (droop and frown).
Runs drive them (`useRunMood`): thinking until the first step, working through steps, needs on a question, done for a
moment after, error on a failure, listening while you type to them.

Rendering: one hidden WebGL canvas draws every visible mascot in turn into its own small 2D canvas, at most 30 fps,
and stops when the window is hidden or no mascot is on screen. three.js loads lazily the first time a mascot shows.
Without WebGL, or with reduced motion on, still pictures rendered from the same models show instead
(`src/assets/mascots`, 21 WebP files, 52 KB). Regenerate them with `python tests/desktop/mascots.py <exe> --pictures`.

Where they show: the new tab hero (follows the cursor), the companion row and picker, the sidebar header and chat
turns, the takeover pill, and the marker on a tab an AI is working in.

Shots: `compare/mascots-v01-{light,dark}.png` (every mascot in every state), `compare/newtab-mascot-v02-*.png`,
`compare/sidebar-mascot-v02-*.png`, `compare/picker-mascot-v02-*.png`.
