# Changelog

All notable changes to FSR 4.1 Lite, newest first.

## [2.2.43] - 2026-11-11

### 🐛 Fixed
- **Sharpness:** the Set sharpness switch and the slider sit in their own rows under the Now playing card, lined up
  with the switches in Settings. In 2.2.42 they were inside the card and the slider ran past its edge.
- **Notifications:** the "FSR 4.1 Lite is running" notification names what the game sent again: DLSS, FSR, FSR 2 or
  XeSS. It never named DLSS before, and left it out in FSR 2 games, because OptiScaler doesn't log those calls by
  the names the plugin looked for. I matched it to the logs from my Steam Machine.

## [2.2.42] - 2026-11-11

### ✨ Added
- **Sharpness:** each game you set up gets a Set sharpness switch on the Now playing card, with a slider from 0 to 100%.
  It works whatever you pick in the game, even in DLSS games that have no sharpness slider of their own, because
  OptiScaler's own sharpening does it. Leave it off and the game keeps its own sharpness. A change shows the next time
  the game starts. Thanks to J0TK for asking.
- **Game cards:** Baldur's Gate 3 says it's tested. On my Steam Machine DLSS ran as FSR 4.1 Lite in the DirectX 11
  version. Its own FSR 2.2 is built into the game, so pick DLSS.

### 🔧 Changed
- **Decky store:** the description says FSR 4.1 Lite works on the Steam Machine, the Steam Deck and any other SteamOS
  device.

## [2.2.41] - 2026-11-10

### 🔧 Changed
- **Games:** the GTA Definitive Edition games (GTA III, Vice City and San Andreas) are blocked, with the reason on the
  card. On my Steam Machine San Andreas closed at start every time OptiScaler loaded, on its own, next to ReShade and
  with NVIDIA spoofing off. HDR mods like RenoDX still work in them on their own.
- **Game cards:** two buttons on the card, like Uninstall and Restart now, have space between them.

### 🐛 Fixed
- **Launch options:** uninstalling FSR 4.1 Lite no longer takes out a dxgi=n,b you had before, or one ReShade needs
  once it gets dxgi.dll back. Before, uninstalling Lite could quietly turn off HDR in that game.
- **Games:** a game that crashes at start is no longer taken for a launcher. GTA San Andreas crashed with OptiScaler,
  and the plugin then avoided its real exe. Only a small exe, under 50 MB, can count as a launcher now.

## [2.2.40] - 2026-11-10

### 🔧 Changed
- **HDR:** games with Special K can get FSR 4.1 Lite again. Special K keeps its file and its settings, and FSR 4.1 Lite
  goes in under another file name next to it. I tested it in Palworld on my Steam Machine: DLSS ran as FSR 4.1 Lite,
  Special K's HDR stayed on and the controller worked.

## [2.2.39] - 2026-11-10

### ✨ Added
- **HDR:** FSR 4.1 Lite now shares a game with ReShade, the loader RenoDX's HDR mods use. Both want to load as
  dxgi.dll, so FSR 4.1 Lite takes that name and loads ReShade itself, the same way my Windows widget does. Uninstall
  FSR 4.1 Lite and ReShade gets its name back, so your HDR keeps working. I tested it in Cyberpunk 2077: Lite and
  RenoDX both ran, at normal FPS.
- **Game cards:** the 25 games I tested on my Steam Machine say so on their card, with the upscaler I picked in the
  game.

### 🔧 Changed
- **HDR:** a game with Special K can't get FSR 4.1 Lite for now, and its card says why. The two aren't tested together
  on SteamOS yet. Remove Special K to install FSR 4.1 Lite.

## [2.2.38] - 2026-11-09

### ✨ Added
- **Games:** GTA IV with the DLSS-IV mod runs FSR 4.1.2 Lite. GTA IV itself is 32-bit, but DLSS-IV does its upscaling
  in its own 64-bit helper, so the plugin sets FSR 4.1 Lite up next to that helper. DLSS-IV's DLSS and FSR both run
  Lite then: set upscaler in DLSS-IV.cfg, next to GTAIV.exe, to automatic, DLSS or FSR.

### 🔧 Changed
- **Games:** 32-bit games are blocked, with the reason on the card. OptiScaler only runs in 64-bit games, so before,
  the plugin set one up and then kept trying other file names that could never load. Blocked games now say
  "OptiScaler can't run in it".

## [2.2.37] - 2026-11-09

### 🔧 Changed
- **Performance:** the plugin does less work in the background. The check every 5 minutes reads the list of running
  programs once instead of once per game (54 ms down to 2 ms on my Steam Machine). When the plugin loads, the overlay
  check reads each game's small OptiScaler.ini instead of its 26 MB OptiScaler DLL, and a game's ini is only written
  when a setting really changed. In a game's first two minutes, the list of running Windows programs for the support
  report is taken every 30 seconds instead of every 5.

## [2.2.36] - 2026-11-09

### ✨ Added
- **Settings:** a Maximum size for the FPS overlay, like the Windows widget.

### 🐛 Fixed
- **FPS overlay:** every size came out huge. The plugin used bigger sizes than the Windows widget and set OptiScaler's
  menu font, which also made OptiScaler's own menu huge. The overlay now uses the widget's sizes (Large is 2.6% of the
  screen height) and OptiScaler's overlay font setting, and OptiScaler's menu is back to its normal size. Games you
  set up before get the fix when the plugin loads.

## [2.2.35] - 2026-11-09

### 🔧 Changed
- **Games:** the OptiPatcher tip says when you need DLSS. In a game that only offers DLSS, it tells you to pick DLSS.
  In a game that also ships FSR or XeSS, like Black Myth: Wukong, it says OptiPatcher is optional: FSR or XeSS runs
  FSR 4.1 Lite too. Before, every game said DLSS was the only option on AMD.

## [2.2.34] - 2026-11-09

### ✨ Added
- **Now playing:** a Remove old OptiScaler button for games that have OptiScaler from another install. It moves that
  install's files into the plugin's folder (`~/homebrew/data/FSR4Lite/old-optiscaler`), so nothing is deleted, and
  leaves the game's own files alone. Then FSR 4.1 Lite installs as usual.

### 🔧 Changed
- **Games:** OptiScaler from another install is found by any part of it: its loader DLL, its OptiScaler.ini or its
  folder. Before, only the ini counted, so a leftover DLL could clash with a new setup.

## [2.2.33] - 2026-11-09

### 🗑️ Removed
- **Now playing:** the resolution readout from 2.2.32, on the card and in Your games. OptiScaler writes the resolution
  down only when a game sets up its upscaler, and some games, like The Witcher 3, change FSR's quality mode without
  that, so the card could show an old mode. The card says FSR 4.1 Lite is running again. For the live resolution, turn
  on the FPS overlay in Settings: it updates every frame.

## [2.2.32] - 2026-11-09

### ✨ Added
- **Crash protection:** if a game closes right after starting two times in a row with FSR 4.1 Lite on, the plugin
  turns it off for that game, puts your launch options back and tells you why. The game's card says so too, and you
  can turn it back on any time to try again. Quitting after Lite ran never counts.
- **Now playing:** while a game runs Lite, the card shows what's running, like "FSR → FSR 4.1.2 Lite, 1920×1080 →
  3840×2160 (Performance)", the same readout as the Windows widget.
- **Your games:** after you quit, each game's card and row keep what ran in its last session.

## [2.2.31] - 2026-11-09

### ✨ Added
- **Games:** a tip on Crimson Desert's card. Changing its graphics settings while OptiScaler is loaded closes the game,
  whatever upscaler runs, so turn FSR 4.1 Lite off, change your settings, then turn it back on. Playing with FSR 4.1
  Lite on is fine.

## [2.2.30] - 2026-11-09

### 🐛 Fixed
- **Games:** 007 First Light showed "not active" while FSR 4.1 Lite was running. OptiScaler writes one line to its log
  thousands of times a second in this game, and the plugin only read the end of the log, where the proof that Lite
  ran never is. Now it reads the whole log and skips lines that repeat, so it sees Lite in 007 and any game like it.
- **Disk space:** in 007 that log grew by about 1 GB every 3 minutes. While a game runs, the plugin now empties its
  OptiScaler log once it passes 256 MB, after reading what it needs from it. The support report says when that happened.

## [2.2.29] - 2026-11-08

### 🐛 Fixed
- **Updates:** the Update card at the top of the plugin installs again. It only downloaded the update and then sat
  on "Installing…", because only the About page handed the download to Decky. Now the card does it too, and it tells
  you to close the Quick Access menu, since Decky's confirmation opens behind it. Ask Decky again shows it once more.

## [2.2.28] - 2026-11-08

### 🔧 Changed
- **Updates:** the plugin looks for a new version every hour instead of every 6 hours, so the notification reaches you
  soon after a release. Still one notification per version.

## [2.2.27] - 2026-11-08

### 🐛 Fixed
- **Games:** Ubisoft Connect games start again, like Assassin's Creed Black Flag Resynced and Mirage. OptiScaler's
  overlay closed them at launch next to Ubisoft's own overlay, so its menu and FPS overlay are now off in any game
  that runs Ubisoft Connect. Black Flag Resynced and Mirage also get NVIDIA spoofing off, as OptiScaler's
  Compatibility List recommends: pick FSR in them and they run FSR 4.1.2 Lite. Games already set up get the fix when
  the plugin loads.

## [2.2.26] - 2026-11-08

### 🐛 Fixed
- **OptiPatcher:** it now loads. 2.2.25 put it in a plugins folder next to the game, and OptiScaler only reads the
  one inside its own OptiScaler folder. DOOM Eternal and the other games the Compatibility List marks now show DLSS
  on AMD. Games set up with 2.2.25 are fixed automatically, and your own files in either plugins folder stay.

## [2.2.25] - 2026-11-08

### ✨ Added
- **OptiPatcher:** games that only offer DLSS on AMD with OptiPatcher, like DOOM Eternal, now get it next to
  OptiScaler, so DLSS isn't greyed out anymore. The plugin adds it to the games OptiScaler's Compatibility List marks
  for it (212 right now), downloads the newest release checked against GitHub's SHA-256, and looks for a newer one
  once a day. Games you set up before get it with the next update.

## [2.2.24] - 2026-11-08

### 🔧 Changed
- **Games:** DEAD OR ALIVE 6 Last Round is blocked. With OptiScaler loaded it closes itself a few seconds after it
  starts on SteamOS, whatever the setting or loader name, so the plugin says so instead of offering an install.

## [2.2.23] - 2026-11-08

### 🐛 Fixed
- **Status:** a game no longer shows Active or "FSR 4.1 Lite ran" just because OptiScaler loaded. Newer OptiScaler
  builds name the Lite model in their log as soon as they start, even when the game never upscales. Now Lite only
  counts once AMD's FSR 4 file has loaded and the game's upscaler has started.

## [2.2.22] - 2026-11-07

### ✨ Added
- **Repair:** when a game update or Steam's file check removes OptiScaler, or puts the game's own DLL back over it,
  the plugin puts it back by itself and tells you. Games that aren't running are checked every few minutes, and a
  game is checked again as it starts.
- **Now playing:** a Restart now button right after you set up a running game. It warns you to save first, then
  closes the game and starts it again so OptiScaler loads.
- **First use:** a short how-to on the main page until your first game is set up.

### 🗑️ Removed
- **GitHub:** the game report issue template.

## [2.2.21] - 2026-11-07

### 🐛 Fixed
- **Non-Steam games:** a game added as a non-Steam .exe that tells Steam it's a Steam game (God of War runs as
  Steam's app 1593500, not as your shortcut) said "Not found" on Now playing. The plugin now finds it by the .exe
  that's running, the way the Windows widget finds the game on screen, and the Install button shows. Notifications
  and the restart badge follow the same game.

## [2.2.20] - 2026-11-07

### 🐛 Fixed
- **Now playing:** a game added to Steam after the plugin loaded (like a non-Steam game you just added) said "Not
  found" with no Install button. The plugin now rescans your library by itself when the game you're playing isn't
  in it, then shows Install.

## [2.2.19] - 2026-11-07

### ✨ Added
- **Updates:** the plugin checks GitHub for a new FSR 4.1 Lite version every 6 hours, the same as the Windows
  widget, and sends one notification per version: open the plugin and press Update. You no longer have to open the
  plugin to find out.

## [2.2.18] - 2026-11-07

### 🐛 Fixed
- **OptiScaler:** "Couldn't check for a newer OptiScaler" right after an update. Two checks could run at once, and
  the first one cleaned up the second one's download. Checks now run one at a time. The update itself always worked.

## [2.2.17] - 2026-11-07

### ✨ Added
- **OptiScaler:** the newest OptiScaler nightly, always, the same as the Windows widget. The plugin looks for a new
  build every 6 hours and puts it in every game you set up that isn't running. Each game keeps its loader name and
  settings, and one notification tells you. A game that's running gets it once you close it.
- **OptiScaler:** every download is checked against the SHA-256 GitHub publishes for it, and a build that can't be
  told to run the Lite model is never used.
- **Settings:** "Update OptiScaler automatically" (on by default), with the build in use, and "Check for a newer
  OptiScaler".
- **Check setup:** which OptiScaler build the game has. The support report shows it too.

### 🔧 Changed
- **REFramework:** the newest nightly, looked for once a day, and RE Engine games set up with it get each new one.

## [2.2.16] - 2026-11-07

### 🐛 Fixed
- **Your games:** a game that's running shows its live status, like Now playing. A game set up this session said
  "Not played yet" while Lite was already running; it now says Active.

## [2.2.15] - 2026-11-07

### ✨ Added
- **About:** a row to support Steam Machine Life on Ko-fi, opened in Steam's browser.

### 🔧 Changed
- **Look:** status badges are tinted glass pills with a glowing dot: green when active, amber when the game needs
  you, red for a problem. Each game in Your games gets a smaller one in the same style.
- **Look:** "Restart the game" is now "Restart needed" with a small restart icon, on one line.

## [2.2.14] - 2026-11-07

### 🔧 Changed
- **Look:** Now playing says less before you install: one line on what to pick in the game's settings, from the
  upscalers it ships ("pick DLSS, not its own FSR").
- **Look:** updates live on the About page, now About and updates. When a new version is out, its card still shows
  at the top of the menu.

### 🐛 Fixed
- **Look:** the status line at the top sits on one line, without a box.
- **Look:** shorter rows that don't wrap: "10 more games", and one line under Uninstall from all games.

## [2.2.13] - 2026-11-07

A calmer, cleaner menu.

### 🔧 Changed
- **Look:** one quiet status line at the top instead of a second title and three boxes. Now playing is one calm card
  with the game, its status, its upscalers and one button. Headings are small and quiet, settings say less, and
  Rescan, Uninstall from all games and About are slim rows instead of big buttons.
- **Look:** the menu opens at the top of its main page every time.
- **Games:** you set games up from Now playing, with the game running, so the plugin sees which program is the game.
  Your games keeps a switch to turn a game off; Install in all compatible games is gone.

## [2.2.12] - 2026-11-07

Phantom Blade Zero, checked on my own Steam Machine while it ran.

### 🔧 Changed
- **Check setup:** the saved report also lists every Windows program running (how it was started, its memory and
  whether it draws) and every .exe in the game's folder.

### 🐛 Fixed
- **Games:** a game its launcher starts through the launcher's own folder is found. Phantom Blade Zero's launcher
  (steam/PBZ.exe) starts the game as steam\..\platform\steam\PBZ.exe, and the plugin never recognised that path, so it
  only ever saw the launcher.
- **Games:** when the game isn't running, the plugin picks a far bigger exe over an Unreal folder that only holds tools.
  Phantom Blade Zero's game is its 476 MB platform/steam/PBZ.exe, not the 5 MB tool in ProjectPBZ/Binaries/Win64.

## [2.2.11] - 2026-11-07

### 🐛 Fixed
- **Install:** when an install can't go ahead, the game shows why instead of "Unknown error".
- **Install:** pressing Install while a game is open only asks you to wait when a small program like a launcher is
  clearly what's running. Otherwise it sets the game up right away.

## [2.2.10] - 2026-11-07

Set up the way the Windows widget does it: in the game you're playing.

### 🔧 Changed
- **Games:** Install on the Now playing card sets the game up next to the program that is the game right now, like
  the widget installing into the game on screen. If only a launcher or a loading screen is running yet, it asks you
  to wait for the game's menu instead of guessing.
- **Check setup:** the saved report also shows how the plugin found the game (the programs running from its folder,
  with their memory and graphics) and every other OptiScaler log in the game's folder.

### 🐛 Fixed
- **Games:** a game set up next to its launcher moves to the game. When OptiScaler runs a whole session there and
  never sees the game draw, that program is marked as a launcher for good and the setup moves when you quit
  (Phantom Blade Zero's steam/PBZ.exe).

## [2.2.9] - 2026-11-07

### 🔧 Changed
- **Look:** Your games opens and closes from its heading, and the menu remembers which you picked.

### 🐛 Fixed
- **Games:** the plugin finds the game, not its launcher, the way the Windows widget does. Phantom Blade Zero starts a
  small launcher first, and 2.2.5 set the game up next to that. Now only a program with graphics loaded that uses a
  game's worth of memory counts as the game, and a setup next to the launcher moves to the game when you quit.
- **Games:** OptiScaler always looks for AMD's FSR 4 file in its own folder. Under Proton it could look in the folder
  Steam starts the game in instead and fall back to FSR 3. Games you already set up get this when the plugin loads.

## [2.2.8] - 2026-11-07

A cleaner menu, and notifications that say what's running.

### 🔧 Changed
- **Look:** no game artwork. Not every game has it, and the menu opens faster without it. The Now playing card has a
  header tinted by the game's status instead: green when active, amber when it needs you, red when blocked.
- **Look:** Your games is a heading you can't scroll past, with how many games are set up and active. The games you
  set up are always listed with a status dot; the rest of your compatible games sit behind one Show more row.
- **Notifications:** when FSR 4.1 Lite starts, however late in the session, the notification says what runs, for
  example "DLSS → FSR 4.1.2 Lite, 1280×720 → 3840×2160 (Ultra Performance)". A game still without Lite after 90
  seconds gets one note saying why.

## [2.2.7] - 2026-11-07

### 🐛 Fixed
- **Games:** Phantom Blade Zero fell back to FSR 3. OptiScaler loaded there but looked for AMD's FSR 4 file in the
  folder Steam starts the game in (platform/steam), not next to the exe. After a
  session like that, the plugin puts the file where OptiScaler looks and asks you to play once more. Turning the game
  off removes it again.

## [2.2.6] - 2026-11-07

### ✨ Added
- **Games:** the Now playing card shows what the OptiScaler community found for the game, as in the Windows widget:
  the upscalers that work ("Works with: DLSS, FSR3.1/4, XeSS"), or a warning when the community marks it not working
  or mixed. It comes from OptiScaler's Compatibility List, 676 games, taken with each release, so nothing is
  downloaded while you play.

## [2.2.5] - 2026-11-07

### 🔧 Changed
- **Games:** set up next to the exe the game really runs, like the Windows widget. While a game starts, the plugin
  finds its exe among the running programs and remembers it, with OptiScaler's log as the backup.

### 🐛 Fixed
- **Games:** Phantom Blade Zero runs platform/steam/PBZ.exe, not the exe in its Unreal folder, so FSR 4 never loaded
  there. A game set up next to the wrong exe moves to the right one when you quit: play once more. A game where Lite
  already runs is left as it is.
- **Status:** when OptiScaler can't load AMD's FSR 4 file, the game shows that it ran FSR 3 and why, instead of FSR 4
  loaded.

## [2.2.4] - 2026-11-07

REFramework for the Capcom games that need it, as in the Windows widget.

### ✨ Added
- **REFramework:** Monster Hunter Wilds, Onimusha: Way of the Sword, PRAGMATA, Devil May Cry 5, Dragon's Dogma 2 and
  Resident Evil 2, 3, 4, 7, Village and Requiem get REFramework next to OptiScaler, which OptiScaler needs in these
  games. It's downloaded the first time you set one up (a pinned build, checked against its SHA-256), starts with its
  menu closed, and comes out with everything it made when you turn the game off. A dinput8.dll the game already has
  is left alone.

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
