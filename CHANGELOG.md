# Changelog

All notable changes to FSR4 Injector, newest first.

## [2.2.3] - 2026-11-07

More games found and set up, with the Windows widget's game logic.

### ✨ Added
- **Games:** a game with no upscaler files can still be set up from the Now playing card. Many games build FSR 2 or
  3 into the game itself, so OptiScaler is told to search the game for it (it loads a little slower). These games stay
  out of the library list and Install in all.
- **Games:** tips on the Now playing card, as in the widget: pick DLSS or XeSS in games without FSR files, and the
  setup Red Dead Redemption 2 and Enshrouded need.

### 🔧 Changed
- **Loader:** the file name OptiScaler loaded under is remembered for each game, so setting it up again starts there.
  After a skipped name, the names the game's exe loads at startup are tried first.
- **Games:** FSR 2 games on DirectX 11 or Vulkan get OptiScaler's FSR 2 inputs for that API.

### 🐛 Fixed
- **Games:** upscalers deep inside Unreal Engine Plugins folders are found, so Phantom Blade Zero no longer says no
  upscaler was found.

## [2.2.2] - 2026-11-07

### 🔧 Changed
- **Updates:** the plugin's home is now github.com/db1522/fsr4-lite-steam-machine, so the Windows widget and this
  plugin can't be mixed up. Updates, the About page and the README all point there. On 2.2.1, install this ZIP by hand
  once from the Releases page; from here on the plugin updates itself again.

## [2.2.1] - 2026-11-07

### 🔧 Changed
- **Updates:** on the main page instead of inside About. The plugin checks GitHub once per load when the menu first
  opens, and a newer version shows as an Update available card at the top with one button; an Updates section above
  About has Check for updates at any time.

## [2.2.0] - 2026-11-07

### ✨ Added
- **Overlay:** sizes made for a TV across the room (Small to Huge) and a corner to put it in, under Show FPS and
  resolution. Each size is a share of the game's output height, read from OptiScaler's log after the first session
  (4K until then), and drawn with OptiScaler's font size so the text stays sharp. OptiScaler's in-game menu grows
  with it.

## [2.1.2] - 2026-11-07

### 🔧 Changed
- **Anti-cheat:** blocked games say so the way the Windows widget does: a red Blocked pill on the Now playing art,
  "Blocked: <anti-cheat>" in the games list, and the widget's message ("… could get your account banned, so installs
  are blocked").

### 🐛 Fixed
- **Anti-cheat:** games whose anti-cheat lives outside the game folder are recognised by their exe, as in the widget:
  Valorant and League of Legends (Riot Vanguard), Overwatch (Blizzard), Genshin Impact, Honkai: Star Rail and Zenless
  Zone Zero (HoYoverse).

## [2.1.1] - 2026-11-07

### 🔧 Changed
- **Look:** Steam's own controls in the panel match the rest: toggles switched on in Steam Machine Life's blue, the
  focused row tinted blue, and the Library and Check setup buttons in the blue button style.

## [2.1.0] - 2026-11-07

A live status for the game you're playing, and a new look.

### ✨ Added
- **Now playing:** the running game's live status on its artwork, checked every few seconds while the menu is open:
  Active, Restart the game (set up while it was running), Starting or Not active, with the reason underneath.
- **Look:** a header with the plugin mark and version, a strip with games set up, games active and setup state, a
  full-width artwork card for the game you're playing, and each game's Steam artwork in the games list.

### 🐛 Fixed
- **Games:** a session the game was set up in no longer counts as OptiScaler not loading, so it isn't moved to
  another loader name for no reason.
- **Setup:** the bundled 7-Zip runs from the plugin's data folder when the plugin folder doesn't let it run.

## [2.0.0] - 2026-11-07

One method for every game: OptiScaler with the Lite model, the way the FSR 4.1 Lite widget for Windows does it.

### ✨ Added
**Games**
- OptiScaler goes next to the game's exe with the widget's settings (FidelityFX upscaling, INT8 Lite support forced,
  the Lite model picked, frame generation off) and AMD's FSR 4.1.2 files for DirectX 12 and Vulkan. Works with games
  that ship FSR 2, FSR 3.1, native FSR 4, DLSS or XeSS, in DirectX 12, DirectX 11 and Vulkan.
- If OptiScaler doesn't load in a session, the plugin sets it up under the next loader name by itself (dxgi, winmm,
  version and so on) and asks for one more session.

**Status**
- OptiScaler's log is the proof: a notification in the game as soon as the Lite model runs, and the game's chip after
  the session (Active, Pick an upscaler, Needs fix).
- Check setup: files, launch option, Proton, the game's upscalers and the last session, a Fix setup button and a
  report saved to Downloads.

**Options**
- Show FPS and resolution (OptiScaler's overlay) and AMD's watermark, applied to every set-up game.

**Setup**
- One download of about 205 MB: OptiScaler (a pinned, tested nightly from its GitHub) and AMD's two files, each
  checked against its SHA-256 and unpacked with the bundled 7-Zip.

### 🔧 Changed
- **Games:** the list shows every game with FSR, DLSS or XeSS, with what it ships as chips. Games with anti-cheat
  stay off, as do games that already have OptiScaler from another install.
- **Version 1:** games set up by 1.x are listed in a Clean up card that removes those files first.

### 🗑️ Removed
- **Shim:** the plugin's own amdxc64.dll (both builds), game-folder and native FSR 4 modes, the model switch, Proton
  compatibility and the library test. OptiScaler does all of it.

## [1.12.1] - 2026-11-07

### 🔧 Changed
- **Check setup:** Use Proton's provider call is now Proton compatibility. Besides the plain hand-off, the native shim
  then answers only what Proton's own amdxc64 answers (FidelityFX API, Anti-Lag, empty stubs) and none of the fuller
  AMD driver extensions (device creation, shader intrinsics, WMMA), which games like Cyberpunk 2077 probe for.
- **Shim (native build):** logs every AMD driver extension a game asks for.

## [1.12.0] - 2026-11-07

### ✨ Added
- **Check setup:** Use Proton's provider call (native FSR 4 mode). The native shim then hands FSR requests to AMD's
  library exactly as Proton's own amdxc64 does (plain UpdateFfxApiProvider, no ML frame generation data), for games
  that load FSR 4.1 Lite and register it but never use it. Set per game through FSR4I_PLAIN_PROVIDER=1, kept through
  Fix setup, taken out on uninstall.
- **Shim (native build):** logs every FSR provider request (call used, result, version), so a diagnostic report
  shows the whole exchange.

## [1.11.1] - 2026-11-07

### ✨ Added
- **Check setup:** flags the plugin's own files left in a native-mode game's folder ("Old game-folder files still
  there") with a Remove leftover files button. Only files with the plugin's exact bytes count; a game's own file of
  the same name is never touched.

### 🐛 Fixed
- **Native FSR 4 mode:** switching a game to native mode removes the plugin's game-folder copies first. Left behind,
  they loaded before the native-mode files, so native mode never ran (seen in Cyberpunk 2077).

## [1.11.0] - 2026-11-07

Diagnostics for games that freeze, without a terminal.

### ✨ Added
- **Check setup:** Record a diagnostic session turns on Proton's log for one game (PROTON_LOG=1, kept through Fix
  setup and taken out on uninstall). Show report pulls the shim's steps, AMD and FidelityFX DLL loads, errors and the
  last lines before the log ended, shows them, and saves fsr4lite-diagnostic-<appid>.txt to Downloads.
- **Check setup:** in native FSR 4 mode, Test with Proton's FSR 4.1.1 library sets AMD's 4.1.2 copy aside so the
  shim loads Proton's own: it tells a library problem from a shim problem.

## [1.10.0] - 2026-11-07

### ✨ Added
- **Games:** a Model choice per game in Check setup. Lite stays the default; Standard uses AMD's regular FSR 4 model
  with the GPU's real answer, as a fallback for a game that freezes or glitches with Lite. Kept through Fix setup and
  mode switches, shown as a chip.

## [1.9.0] - 2026-11-07

Updates install from inside the plugin.

### ✨ Added
- **Updates:** About → Check for updates → Update to X downloads the release from GitHub, verifies it, and hands it
  to Decky's own installer. Decky asks to confirm, replaces the plugin and reloads it; games stay set up. No
  Developer mode needed. If this Decky build doesn't take the request, the ZIP stays in Downloads with the manual
  steps, as before.

## [1.8.0] - 2026-11-07

FSR 4.1 Lite gets its own home: github.com/db1522/fsr4-lite-steam-machine.

### ✨ Added
- **Updates:** About → Check for updates is back, now from this repository's releases.
- **Repository:** README with results and install steps, issue forms (bug report with the Check setup lines, game
  report), and a workflow that attaches the plugin ZIP to each published release.

### 🔧 Changed
- **Plugin:** author Steam Machine Life, store description and image from this repository.
- **Name:** the plugin's folder and release file are now FSR4Lite (FSR4Lite-X.Y.Z.zip). On its first start the
  plugin takes over the games, settings and AMD library the old FSR4Injector folder kept, so nothing has to be set
  up again. Remove the old copy from Decky after installing this one.

### 🗑️ Removed
- **Repository:** upstream's Legion Go 2 screenshots and icon.

## [1.7.4] - 2026-11-07

### 🐛 Fixed
- **Navigation:** a row reached by pressing up no longer hides behind Decky's fixed header. Whatever gets the focus
  is brought to the middle of the panel when it would sit under the header or off the bottom, on every page.

## [1.7.3] - 2026-11-07

### 🐛 Fixed
- **Navigation:** the Now playing, Setup and Check setup cards sit inside Steam's own rows, and their buttons bring
  themselves into view when focused. Before, focus moved onto a card button but the menu didn't scroll to it, so
  pressing up looked like a jump to the back button.

## [1.7.2] - 2026-11-07

### 🐛 Fixed
- **Games:** the list title reads "Games: 2 of 8 installed". Steam's row layout dropped the spaces around the count
  ("Games0of 8 installed").

## [1.7.1] - 2026-11-07

### 🐛 Fixed
- **Navigation:** pressing up no longer jumps out of the panel to Decky's back button. The one-column focus wrapper
  from 1.6.1 is gone; the fix that mattered there (no focus groups around single buttons) stays.
- **Scrolling:** the bottom of the panel is reachable again. The panel no longer forms its own scroll area (its
  sideways clipping did that), and the last line of text moved into the About row, so the page ends on a row the
  D-pad can reach.

## [1.7.0] - 2026-11-07

Fewer steps and a more finished look.

### ✨ Added
- **Native FSR 4 mode:** chosen automatically. When the plugin's DLL doesn't load in a game, the game moves to
  native FSR 4 mode by itself (once per game) and a notification says to play again.
- **Proton:** a Switch to Proton Experimental button on the Now playing card and in Check setup when a game runs on
  a Proton that can't load FSR 4 (GE-Proton11-1, Proton 10 or older), where this Steam build allows it.
- **Now playing:** the game's library artwork behind its name.
- **Games:** colored status chips (Active, Needs fix, Re-check, Pick AMD FSR, Not played yet, Native FSR 4, Online,
  Anti-cheat) instead of plain text.

## [1.6.1] - 2026-11-07

### 🔧 Changed
- **Games:** one list of compatible games in a fixed order, instead of Installed and Compatible lists a game moved
  between when switched, which pulled the row out from under the D-pad.

### 🐛 Fixed
- **Navigation:** the panel and its pages move as one column with the D-pad; card buttons no longer sit in focus
  groups of their own, which made up and down skip rows or stop.
- **Navigation:** controls are no longer greyed out while something runs (a disabled control drops the focus back
  to the top); presses during that time are ignored instead. Library buttons stay in place rather than appearing and
  disappearing.

## [1.6.0] - 2026-11-07

Native FSR 4 mode, take two: AMD's 4.1.2 library under its own name, out of Proton's reach.

### ✨ Added
- **Shim:** a native-mode build (bin/amdxc64_native.dll) that loads AMD's library as fsr4lite_amdxcffx64.dll first,
  and lets the known 4.1.2 build take over when Proton's own copy was loaded before it. Built from the included
  source with -DFSR4I_LITE_NAME; the game-folder build is unchanged.

### 🔧 Changed
- **Native FSR 4 mode:** Proton rewrites system32\\amdxcffx64.dll at every launch, even with PROTON_FSR4_UPGRADE=0, so
  native mode no longer replaces it (or the umu copy). AMD's 4.1.2 library goes in as fsr4lite_amdxcffx64.dll and
  only Proton's amdxc64.dll is set aside. Press Fix setup on games already in native mode.
- **Updates:** a plugin update refreshes each game's shim with the build for its mode.

### 🐛 Fixed
- **Uninstall:** a native-mode game where Proton had already written its own library back now uninstalls cleanly,
  with the stale backup removed instead of reported as kept.

## [1.5.2] - 2026-11-07

### ✨ Added
- **Check setup:** says when Proton or a game update wrote over the plugin's files, and which AMD library the game
  actually loaded when it isn't FSR 4.1.2.

### 🐛 Fixed
- **Native FSR 4 mode:** Proton Experimental's second copy of AMD's library (system32/umu) is replaced too, so a native
  FSR 4 game can't load Proton's FSR 4.1.1 from there. Put back on uninstall. Press Fix setup on games already in
  native mode.

## [1.5.1] - 2026-11-07

### ✨ Added
- **Check setup:** a Details section with what the plugin recorded last session, for troubleshooting without a terminal.

### 🐛 Fixed
- **Native FSR 4 mode:** the GPU is now passed to the shim through the launch options (FSR4I_FAMILY, FSR4I_REV), because
  native FSR 4 games call AMD's library without the request the shim normally identifies the GPU from. Fixes "GPU
  answer missing". Press Fix setup on a game already in native mode.

## [1.5.0] - 2026-11-07

Native FSR 4 mode, for games that ship FSR 4 themselves (experimental).

### ✨ Added
- **Games:** native FSR 4 mode installs FSR 4.1 Lite into the game's own Proton system folder, where native FSR 4
  games load AMD's files from, and switches Proton's own FSR 4 off for that game with PROTON_FSR4_UPGRADE=0.
  Proton's files are kept as a backup and put back on uninstall. Switch to it from Check setup.
- **Status:** when the plugin's DLL doesn't load, the notification points to native FSR 4 mode.

### 🔧 Changed
- **Install:** AMD's library is always copied, never linked, into a Proton folder, so Proton writing its own copy
  can never change the plugin's.

## [1.4.0] - 2026-11-06

Check setup: find out why a game isn't running FSR 4.1 Lite without opening a terminal.

### ✨ Added
- **Check setup:** a page for each installed game that checks file placement, the plugin's files, the launch option,
  the game's Proton version and the last session, each with a plain fix. Open it from Now playing or under
  Installed games.
- **Fix setup:** one button that reinstalls the game's files in the right folder and puts the launch option back.

 - 2026-11-06

### 🐛 Fixed
- **Games:** where FSR 3.1 lives outside the .exe folder (Unreal plugin folders), the plugin's files now go next to the
  game's .exe, where the game looks for them. Before, they could sit next to the FFX DLL and never load, leaving the
  game on "Not verified yet". Turn such a game off and on once to move its files.
- **Status:** a session where the plugin's DLL didn't load now tells you at once instead of waiting for a second one.

## [1.3.0] - 2026-11-06

FSR 4.1 Lite by Steam Machine Life: a new panel built around the game you're playing.

### ✨ Added
- **Now playing:** open the menu in a game to see if it's compatible and install or uninstall FSR 4.1 Lite with one button.
- **Status line:** shows at a glance whether the Lite model is ready, setup is needed, or the GPU isn't supported.
- **Setup card:** AMD's library download sits in its own card until it's done.

### 🔧 Changed
- **Look:** Steam Machine Life colors and Barlow Condensed, sized for reading on a TV.
- **Game lists:** Installed games and other compatible games fold away until opened.
- **Name:** the plugin is now FSR 4.1 Lite. Updates come from Steam Machine Life, not the upstream release.

## [1.2.1] - 2026-11-06

Steam Machine fork: forces the Lite model on RDNA 3 and finds more compatible games.

### ✨ Added
- **GPU:** RDNA 3 (Steam Machine) is answered as RDNA 3.5 so AMD's library picks the Lite model.

### 🔧 Changed
- **Games:** the scan goes 9 folders deep instead of 5 (Unreal keeps FSR 3.1 under Engine/Plugins), follows
  symlinked folders, prefers the DLL next to the game's .exe, and searches non-Steam games from the game root
  rather than Binaries/Win64.

## [1.2.0] - 2026-11-03

A notification during the game when FSR 4 runs, as a lighter check than AMD's watermark.

### ✨ Added
- **Status:** **Tell me when FSR4 runs** (under **All games**, off by default) shows a short notification
  during the game as soon as AMD's library runs FSR 4, with its model. Problems are still told when the
  game ends.

### 🐛 Fixed
- **Games:** A game with its own non-Steam shortcut is no longer listed under its launcher's shortcut (for
  example Ubisoft Connect, whose games sit in its folder), so FSR 4 works when you start the game's
  shortcut. A launcher shortcut that already has FSR 4 on keeps its game until you turn it off.

## [1.1.0] - 2026-10-30

Non-Steam games, a Repair button and an About page. Updating from 1.0.0 keeps your games set up: **Check
for updates** downloads the new ZIP, which you install the same way as before.

### ✨ Added
**Games**
- Windows games added to Steam with "Add a Non-Steam Game" and run with Proton are found too, from the
  folder of the shortcut's `.exe`. They have their own list, **Non-Steam games**, under **Steam games**.

**Repair**
- Re-checks AMD's library and puts the plugin's files and launch option back in every game that has
  FSR 4 on, for example after a game update or Steam's file check.
- If AMD's library itself is damaged or missing, it tells you to download it again first.

**Decky Launch Options**
- With [Decky Launch Options](https://github.com/Rayekkk/DeckyLaunchOptions) installed, **Add to Decky
  Launch Options** offers the FSR4 launch option and AMD's watermark to it, to switch per game there.

**About**
- **Use Rayek's store** makes Rayek's store Decky's store channel after you confirm, so Decky's Store
  tab lists Rayek's plugins and offers their updates.

### 🔧 Changed

**Panel**
- The About and Updates sections moved to an About page, opened from the last row of the panel; Updates
  is at the bottom of that page.
- When the plugin cannot start, the panel says "FSR4 Injector unavailable" with a Try again button, and
  you can still check for updates below it.
- When turning FSR 4 on or off, a setting or a rescan fails, the reason now also stays under that control
  until it next succeeds, not only in a message.
- An untested GPU gets its own "Beta" row; download sizes are in MB; an empty game list says what to do.

**Updates**
- A downloaded update shows its folder as `~/Downloads/…`, and the update texts match the other plugins
  (for example "Checking GitHub…").

**Launch options**
- Games that already set `WINEDLLOVERRIDES` (your own overrides, or another tool such as ReShade
  or OptiScaler) no longer refuse FSR 4; the plugin adds `amdxc64=n,b` to that variable.
- Turning FSR 4 off takes out only the plugin's own entry from `WINEDLLOVERRIDES`.

**Games**
- Games on the same drive share one copy of AMD's library instead of 82 MB each.

**Status**
- "DLL was not loaded" is shown only when it happens in two sessions in a row, so closing a game in its
  launcher no longer raises a warning.

### 🐛 Fixed

**AMD download**
- An unexpected error no longer leaves the panel stuck on "Downloading from AMD"; you can try
  again at once.
- It fetches exactly the part of AMD's package it needs (about 43 MB, which the progress now
  counts) and checks it before decoding.
- A slow connection gets up to 30 minutes, and Cancel stops the download at once.

**Launch options**
- After turning a game on, the plugin checks what Steam actually kept. If Steam did not keep the
  new launch options you are told, and turning FSR 4 off still restores your own options exactly.

**Settings**
- A switch that cannot be saved (for example on a full disk) stays as it was and says why, instead of
  looking changed until the next restart.
- Two switches changed in quick succession are both kept; before, the second could undo the first.

**Watermark**
- A game whose launch options could not be updated for the watermark is named in a message instead
  of being skipped silently.

**Game list**
- A damaged list of games set up is restored from its backup copy. If that is impossible, the panel
  says so and no game can be changed, instead of forgetting which files are the plugin's.

**Updates**
- "Check for updates" says when no release has been published yet instead of "Up to date", and a
  second download at the same time is refused.
- Updates are saved to your Downloads folder as the desktop names it in your language (for example
  `~/Pobrane`), instead of always `~/Downloads`.

**Files**
- Files written to game folders and the plugin's settings are flushed to disk, so a power loss cannot
  leave half a file.

**Errors**
- Error messages no longer show file paths.

**Status**
- The plugin's status file is written as UTF-8 whatever the system language, so a Proton folder with
  non-English letters no longer confuses the check after a Proton update.

## [1.0.0] - 2026-10-25

### ✨ Added

**Plugin**
- First release.

**Install**
- Install from the release ZIP: in Decky Settings turn on **Developer mode**, then choose
  **Developer → Install Plugin from ZIP** and select `FSR4Injector-1.0.0.zip`.

**AMD download**
- **Accept and download** fetches AMD's FSR 4 library from AMD's official driver package (about
  43 MB).

**Games**
- Turn FSR 4 on per game under **Games with FSR 3.1+**; in the game, choose **AMD FSR** as the upscaler.

**Status**
- After you quit the game, the panel shows "FSR4 active", or a notification says what went wrong.
