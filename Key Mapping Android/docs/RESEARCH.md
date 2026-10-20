# Keyboard + mouse control: research and what was built

Research notes behind the controls. Last updated 2026-10-19.

## 1. What other tools offer

| Tool | Control types worth copying | Source |
|---|---|---|
| BlueStacks 5 | Tap spot, **Repeated tap**, D-pad, **Aim/pan/shoot** (key toggles shooting mode, sensitivity), Free look, **Swipe**, **Zoom**, Tilt, MOBA controls, **Script** (chain actions, loops) | <https://support.bluestacks.com/hc/articles/360058928871>, <https://support.bluestacks.com/hc/articles/360060081652> |
| QtScrcpy (open source, GitHub) | `KMT_CLICK`, `KMT_CLICK_TWICE` (double tap), `KMT_CLICK_MULTI` (one key, several spots in order, with delays), `KMT_DRAG` (start/end, speed, start delay), `KMT_STEER_WHEEL` (WASD stick with per-direction offsets), `mouseMoveMap` (mouse look, per-axis speed, a "small eyes" scope trigger that moves the look origin), a switch key that toggles mapping | <https://github.com/barry-ran/QtScrcpy>, <https://github.com/barry-ran/QtScrcpy/blob/dev/docs/KeyMapDes.md> |
| Sigma-RT TCGames | Direction, Shooting mode, Fire, Normal click, View angle, ready-made keymaps. (My search tool could not retrieve its pages. This row comes from the product page the project owner referred to, not from fresh research.) | <https://www.sigma-rt.com/en/tcgames/> |
| PC shooters themselves | Separate bindings for sprint, walk, auto-run, and mouse-wheel weapon cycling are standard, so players expect them | <https://support.pubg.com/hc/en-us/articles/360002074913-What-are-the-basic-game-commands> |

## 2. Why Shift+W "goes very fast" in GameLoop

I found no source that documents how GameLoop does this, so this part is my own reasoning. On the phone, sprint is
normally "push the on-screen stick all the way up" (or into a sprint zone beyond the ring). An emulator that maps
Shift to sprint pushes the virtual stick further than a normal run. The app does the same: while the sprint key is
held, the stick target is `radius x sprint_scale` (default 1.35). If a particular game uses a separate sprint
button instead, map Shift to that button as an ordinary tap key.

## 3. Gap analysis and result

| Gap (before) | Now |
|---|---|
| Only tap / hold | Modes: hold, tap, toggle, repeat, double, swipe, drag, zoom out/in (pinch), multi-tap sequence |
| One key per action | Combinations such as `Shift+W`, `Ctrl+R` (combo beats plain key) |
| No sprint / walk / auto-run | Stick keys: sprint (push further), walk (push less), auto-run (keep forward) |
| Same mouse sensitivity scoped and unscoped | Scope button flag + "While scoped in" sensitivity |
| Wheel could only tap | Wheel can drive swipe, zoom, multi-tap, double and so on (one-shot equivalents) |
| Only a basic template | "Battle royale (PC style)" template: Shift sprint, Ctrl walk, Q/E lean, Z prone, F pick up, G grenade, Tab bag, M map, 1-3, wheel |
| Editor knew one point per control | Drag swipe ends, drag each multi-tap point, Options dialog (rate, duration, span, steps, scope) |

## 4. Deliberately not built

- **Input randomization / jitter / humanized timing**: only useful for evading detection.
- **Recoil compensation macros**: this is a gameplay advantage that games such as PUBG ban.
- **Anti-cheat bypass of any kind.**
- **Tilt / gyro, MOBA cast-at-cursor**: not requested; cast-at-cursor remains a possible later addition.
- **Gamepad**: not needed by the project owner.

## 5. Terms-of-service warning

Mobile games often treat external input tools as violations. For Call of Duty: Mobile, a 2019 anti-cheat notice
listed apps that dock a keyboard and mouse and unsafe emulators among bannable offences, as relayed by news sites.
I did not find current Activision terms text, so treat this as a risk, not a verdict. The "Repeat tap" mode
auto-clicks and may count as cheating in online games. Use it where it is allowed (single player, menus, idle games).
Sources: <https://www.gizguide.com/2019/11/cod-mobile-cheating-ban.html>,
<https://esports.gg/news/mobile/will-warzone-mobile-have-emulator-support>.
This app sends ordinary touch events over USB debugging. It does not hide itself. A ban is possible.

## 6. Test status

- 178 unit tests, `tools/advanced_ui_test.py` (24 checks on a simulated phone), `editor_test` 31, `profile_ui_test` 45,
  `intercept_test` 23, raw mouse and GL self-tests: all pass, with every touch intercepted or swallowed.
- **Not tested in a real match**: sprint push distance per game, scope sensitivity, swipe/zoom/multi-tap in a game.
  Each game places its buttons differently, so expect to adjust positions and `sprint_scale`.

## 7. Live test in a PUBG Mobile match (2026-10-19)

Run through the real pipeline (keyboard events -> app -> scrcpy touches -> phone) in a live Erangel match, with a
screenshot after each step (`tools/pubg_livetest.py`, `pubg_sprintlook_test.py`, `pubg_verify.py`).

| Key | Result |
|---|---|
| W / W+Shift | Moves. Sprint locks (orange Sprint icon) only when the stick is pushed about 274 px; 158 px did nothing. |
| Mouse look | Turns the camera (compass 175 -> 210 -> back) only from a zone right of centre (x 0.62-0.76). A zone at x 0.34-0.58 did nothing. |
| C, Z | Crouch / prone icons light up; pressing again stands up. |
| Right click (scope) | Aims down sights. |
| V | Switches first / third person. |
| Space, R, 1, 2, wheel | Touches sent and the game reacted (wheel / 1 / 2 tap the weapon slot). Tapping the weapon already in hand holsters it. |
| Not tested | Fire, grenade, heal, backpack, map, melee, shop and vehicle buttons: they would change the match or were not on screen. |

Lessons: positions must come from a screenshot of the in-match HUD (PUBG's layout-editor screen differs); sprint
needs far more push than the ring radius; hold-sprint in PUBG stays locked until the stick is touched again, so a long
Shift+W test can walk the character into water.

## 8. GameLoop / emulator key mapping: what could be found, and what was built (2026-10-19)

**Honest limits.** GameLoop's own documentation is thin. Its FAQ confirms that "Smart keymapping" is a set of per-game
keymap files that the client downloads (games installed outside GameCenter may lack them) and mentions locking the mouse
with Ctrl. It does not publish how the smart mode decides anything, which key frees the cursor, or how duplicate keys
are handled. Everything below marked (BS) comes from BlueStacks' public documentation and (patent) from a published
patent, and is used as the closest documented analogue, not as a description of GameLoop's internals.

**The GitHub repository that was named for this research** (llopez9377/gameloop-desktop) contains no key-mapping code. It is a small Python
file-copy helper for GameLoop's data folders; its "download" button goes to an opaque short link, no releases are
published, and the metadata is search-keyword heavy. Do not install from that link. The only real open-source code
found for this problem was scrcpy-based projects (QtScrcpy, scrcpy-mask), which map keys to touches like this app does.

| Emulator / tool feature | Source | In this app |
|---|---|---|
| Per-game keymaps that load by themselves | GameLoop FAQ | Already built: profiles linked to the game's package |
| Free / lock the mouse with a key | GameLoop FAQ (Ctrl), BS (F1 toggle) | F8 and the ~ key (rebindable) |
| **Hold a key to free the mouse temporarily ("Suspend")** | BS | **New: hold Alt (rebindable)** |
| **Controls only matter in the game; the cursor is free in menus ("Smart controls")** | BS, patent (scene detection from screenshots) | **New: Smart mode** |
| Only the relevant buttons shown | BS | New: markers hidden in menus; opacity keys F2/F3/F4 |
| One key touching several places | QtScrcpy multi-click, BS multi-tap | **New: "Touch both spots"** (extra spots on one key) |
| What happens when a key is already used | not documented for GameLoop | **New: choose "use it for the new spot", "touch both", or cancel; swap when changing a key** |
| Save / reset / import / export of key schemes | BS | Save / Undo / Reset exist; import / export not built |
| Per-game default keymap shipped with the client | GameLoop | Not built: needs each game's real screen; the PUBG one was made that way |

**How Smart mode works here** (`app/scene.py`): while the game's buttons are on screen you press "Learn the game screen".
The app keeps a tiny grey-scale signature of the picture around each control. While you play it compares those places
of the live phone picture four times a second (normalised correlation, so the scenery behind semi-transparent buttons
hardly matters). Most places matching = game: keys on, mouse locked for aiming, controls shown. Otherwise = menu: keys
paused (no accidental taps in a store or lobby), mouse works as a finger, controls hidden. Three agreeing readings in a row
are needed to switch, and the start state is "menu" (safe). It only reads pixels the app already shows; it does not touch
the game.

**Measured** on the author's phone: in a live PUBG match the learned screen scored 0.64-1.0 on 36 screenshots (0.36 while swimming,
when PUBG swaps its buttons, which keeps the current state); the layout-editor screen 0.29-0.36; the phone's home screen and
every Call of Duty / app screen 0.00. The video stream's brightness plane matched a same-moment screenshot with median
patch correlation 0.994 (minimum 0.625, above the 0.55 match level), so screenshot calibration carries over to the live stream.
**Not yet tested:** a full live lobby -> match -> lobby cycle in a real game with smart mode switching on its own.
Known limit: it learns one look of the HUD. A game that redraws its buttons very differently (another mode, a vehicle
HUD) may read as "menu" until you learn that screen too; you can switch smart mode off at any time.
