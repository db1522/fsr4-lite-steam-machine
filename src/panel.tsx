// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk
// Copyright (c) 2026 Steam Machine Life (changes)

// FSR 4.1 Lite's panel: one method for every game (OptiScaler with the Lite model), laid out like the FSR 4.1 Lite
// widget for Windows. Status line, a one-time setup card, the game you're playing with one button, every compatible
// game in one list, then options, library tools and About.
import { useQuickAccessVisible } from "@decky/api";
import { DialogButton, DropdownItem, Field, Focusable, PanelSection, PanelSectionRow, Router, ToggleField } from "@decky/ui";
import { FC, Fragment, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { INSTALL_HINT, UpdateController, UpdateSection } from "./about";
import { CSS, steamCss } from "./style";
import { CheckPage } from "./check";
import { canInstallUpdates, installUpdate } from "./installer";
import { keepInView, onFocusReveal, toTop } from "./steamx";
import {
  cancelDownload, checkForUpdates, cleanupLegacy, disableGame, downloadAssets, downloadProgress, enableGame, Game,
  getState, Live, liveStatus, performUpdate, readLaunchOptions, saveLaunchOptions, scanGames, setSetting, State,
  StateResult,
} from "./api";
import { errorText } from "./result";
import { colors, infoRow, notify, PageHeader, statusPlaceholder } from "./ui";

const NAME = "FSR 4.1 Lite";
const OVERLAY_SIZES: Array<[string, string]> = [["small", "Small"], ["medium", "Medium"], ["large", "Large"],
  ["xlarge", "Extra large"], ["huge", "Huge"]];
const OVERLAY_CORNERS: Array<[string, string]> = [["topleft", "Top left"], ["topright", "Top right"],
  ["bottomleft", "Bottom left"], ["bottomright", "Bottom right"]];
const MB = (b: number) => `${(b / 2 ** 20).toFixed(0)} MB`;

let lastState: State | null = null;
let updates: UpdateController | null = null;
const updater = () => (updates ??= new UpdateController({ check: checkForUpdates, download: performUpdate }, "fsr4-lite"));
export const closeUpdates = () => { updates?.dispose(); updates = null; autoChecked = false; };
// Once per plugin load, the first time the menu opens: a quiet check, so a new version shows on the main page.
let autoChecked = false;

const GAMES_OPEN = "fsr4lite.gamesOpen";
/** Whether Your games is open: kept in the browser's storage, open when nothing is saved or storage isn't there. */
const readGamesOpen = (): boolean => {
  try { return window.localStorage?.getItem(GAMES_OPEN) !== "0"; } catch { return true; }
};
const writeGamesOpen = (open: boolean) => {
  try { window.localStorage?.setItem(GAMES_OPEN, open ? "1" : "0"); } catch { /* the choice just isn't kept */ }
};

/** Why a call failed, for the panel: the backend's own reason ({ok: false, error}), which errorText alone doesn't
 * read (it reads an error's message), so refusals came out as "Unknown error". */
export const reason = (r: { error?: string }): string => r.error?.trim() || errorText(r);

const failure = (text?: string): ReactNode => text ? <div style={{ color: colors.error }}>{text}</div> : null;

/** Which upscaler to pick in the game, from what it ships: "DLSS, not its own FSR" when it has no FSR files (a built-in
 *  FSR option may not switch to FSR 4.1 Lite), any of them otherwise. */
export const pickText = (upscalers: string[]): string => {
  const names = [...new Set(upscalers.map(u => u.startsWith("FSR") ? "FSR" : u))];
  if (!names.length) return "FSR";
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
  return names.includes("FSR") ? list : `${list}, not its own FSR`;
};

/** In the library list: games with upscaler files, and any game set up. Games without them (many build FSR in) are
 * offered on the Now playing card only, like the widget, which works on the game in front. */
export const listed = (g: Game) => g.upscalers.length > 0 || g.installed;

/** The chip for a game: what its last session showed. */
export const chipFor = (g: Game): [string, string] => {
  if (!g.installed) return ["", ""];
  switch (g.verdict) {
    case "lite": return ["good", "Active"];
    case "fsr4": return ["warn", "FSR 4, not Lite"];
    case "fsr3": return ["warn", "Pick an upscaler"];
    case "waiting": return ["warn", "Pick an upscaler"];
    case "unsupported": return ["bad", "Not supported"];
    case "none": return ["bad", "Needs fix"];
    default: return ["", "Not played yet"];
  }
};

/** The running game's live status as a pill: [tone, label]. */
export const livePill = (live: Live | undefined): [string, string] | null => {
  switch (live) {
    case "active": return ["good", "Active"];
    case "restart": return ["warn", "Restart the game"];
    case "starting": return ["", "Starting…"];
    case "inactive": return ["bad", "Not active"];
    case "off": return ["", "Off"];
    default: return null;
  }
};

export const Content: FC = () => {
  const visible = useQuickAccessVisible();
  const [state, setStateRaw] = useState<State | null>(lastState);
  const [busy, setBusy] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [bulk, setBulk] = useState("");
  const [error, setError] = useState("");
  const [failed, setFailed] = useState<Record<string, string>>({});
  const [page, setPage] = useState<"about" | "check" | null>(null);
  const [checkId, setCheckId] = useState<number | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [live, setLive] = useState<{ appid: number; status: Live; detail: string } | null>(null);
  const runningAppid = Number(Router.MainRunningApp?.appid ?? NaN);
  // The running game's status, every few seconds while the menu is open: Active, Restart the game, Not active.
  useEffect(() => {
    if (!visible || !Number.isFinite(runningAppid)) return;
    let stop = false;
    const tick = async () => {
      const r = await liveStatus(runningAppid);
      if (!stop && r.ok && r.status) setLive({ appid: runningAppid, status: r.status, detail: r.detail ?? "" });
    };
    tick();
    const t = window.setInterval(tick, 3000);
    return () => { stop = true; window.clearInterval(t); };
  }, [visible, runningAppid, state?.games.filter(g => g.installed).length]);
  // Every time the Quick Access Menu opens, the plugin starts at the top of its main page.
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!visible) return;
    setPage(null);
    const t = window.setTimeout(() => toTop(rootRef.current), 0);
    return () => window.clearTimeout(t);
  }, [visible]);
  const flip = (k: string) => setOpen(o => ({ ...o, [k]: !o[k] }));
  // Your games opens and closes from its heading; the choice is kept for the next time the menu opens.
  const [gamesOpen, setGamesOpen] = useState(readGamesOpen());
  const toggleGames = () => setGamesOpen(v => { writeGamesOpen(!v); return !v; });
  const setState = useCallback((s: State) => { lastState = s; setStateRaw(s); }, []);

  const take = <R extends StateResult>(r: R, key?: string | number): R => {
    if (r.state) setState(r.state);
    if (key !== undefined) setFailed(f => ({ ...f, [key]: r.ok ? "" : reason(r) }));
    return r;
  };
  const refresh = useCallback(async () => {
    const r = await getState();
    if (r.ok && r.state) { setState(r.state); setError(""); } else setError(reason(r));
  }, [setState]);
  useEffect(() => { if (visible) refresh(); }, [visible, refresh]);
  const upd = updater();
  const [updState, setUpdState] = useState(upd.getSnapshot());
  useEffect(() => upd.subscribe(() => setUpdState(upd.getSnapshot())), [upd]);
  useEffect(() => {
    if (visible && !autoChecked) { autoChecked = true; upd.run("check"); }
  }, [visible]);

  // Download progress, a few times a second while it runs.
  useEffect(() => {
    if (state?.download.state !== "running") return;
    const t = window.setInterval(async () => {
      const r = await downloadProgress();
      if (r.download && lastState) setState({ ...lastState, download: r.download, assets_ready: !!r.assets_ready });
      if (r.download?.state !== "running") refresh();
    }, 400);
    return () => window.clearInterval(t);
  }, [state?.download.state, refresh, setState]);

  /** Turns one game on or off, with its launch options read from Steam and saved back. */
  const apply = async (game: Game, on: boolean) => {
    let current: string;
    try { current = await readLaunchOptions(game.appid); }
    catch { setFailed(f => ({ ...f, [game.appid]: "Steam didn't return the launch options. Try again." })); return false; }
    const r = take(await (on ? enableGame(game.appid, current) : disableGame(game.appid, current)), game.appid);
    if (r.ok && r.launch_options !== undefined && r.launch_options !== current) {
      if (!await saveLaunchOptions(game.appid, r.launch_options))
        setFailed(f => ({ ...f, [game.appid]: "Steam didn't keep the launch options. Check them in the game's Properties." }));
    }
    return r.ok;
  };
  const toggle = async (game: Game, on: boolean) => {
    if (busy !== null) return;  // ignored rather than disabled: a disabled control loses the D-pad focus
    setBusy(game.appid);
    await apply(game, on);
    setBusy(null);
  };
  /** Every set-up game put back as it was (setting games up happens one at a time, on Now playing). */
  const uninstallAll = async () => {
    if (busy !== null || !state) return;
    const list = state.games.filter(g => g.installed);
    setBusy(-1);
    let n = 0;
    for (const g of list) { setBulk(`${++n} of ${list.length}`); await apply(g, false); }
    setBulk("");
    setBusy(null);
    notify(NAME, `Removed from ${n} game${n === 1 ? "" : "s"}.`);
  };
  const cleanLegacy = async () => {
    if (busy !== null || !state) return;
    setBusy(-1);
    for (const appid of state.legacy) {
      const current = await readLaunchOptions(appid).catch(() => "");
      const r = take(await cleanupLegacy(appid, current));
      if (r.ok && r.launch_options !== undefined && r.launch_options !== current) await saveLaunchOptions(appid, r.launch_options);
    }
    setBusy(null);
  };
  const rescan = async () => {
    if (scanning) return;
    setScanning(true);
    take(await scanGames());
    setScanning(false);
  };
  const navigate = (next: "about" | "check" | null) => setPage(next);

  if (!state) return <div className="sml-root" ref={rootRef}><style>{CSS + steamCss()}</style>
    {statusPlaceholder({ title: NAME, label: "Starting…", error, onRetry: refresh })}
    {error && <UpdateSection controller={updater()} version={__PLUGIN_VERSION__} />}
  </div>;

  if (page === "check" && checkId !== null) {
    const g = state.games.find(x => x.appid === checkId);
    return <div className="sml-root" onFocus={onFocusReveal}><style>{CSS + steamCss()}</style><Focusable onCancelActionDescription="Back"
      onCancelButton={e => { e.preventDefault(); e.stopPropagation(); navigate(null); }}>
      <PageHeader title="Check setup" back={NAME} onBack={() => navigate(null)} focus={visible} />
      <CheckPage appid={checkId} onFix={async () => {
        if (!g || busy !== null) return;
        setBusy(g.appid);
        if (g.installed) await apply(g, false);
        await apply({ ...g, installed: false }, true);
        setBusy(null);
      }} />
    </Focusable></div>;
  }

  if (page === "about") return <div className="sml-root" onFocus={onFocusReveal}><style>{CSS + steamCss()}</style><Focusable
    onCancelActionDescription="Back" onCancelButton={e => { e.preventDefault(); e.stopPropagation(); navigate(null); }}>
    <PageHeader title="About and updates" back={NAME} onBack={() => navigate(null)} focus={visible} />
    <UpdateSection controller={upd} version={state.version} home={state.home}
      install={`${INSTALL_HINT} Your games stay set up.`}
      onInstall={canInstallUpdates() ? d => installUpdate(d.path ?? "", d.version ?? "", d.sha256 ?? "") : undefined} />
    <PanelSection title={`${NAME} ${state.version}`}>
      {infoRow("Steam Machine Life", "Runs AMD's FSR 4.1.2 Lite model in your games on the Steam Machine. The same method as the FSR 4.1 Lite widget for Windows.")}
      {infoRow("OptiScaler", `${state.optiscaler}, by cdozdil and contributors (GPL-3.0). Downloaded from its own GitHub, unmodified.`)}
      {infoRow("FSR 4", "By AMD. AMD's signed FSR 4.1.2 files, unmodified, made available to the community by TheRazerMD.")}
      {infoRow("REFramework", "By praydog (MIT). Added only to the Capcom RE Engine games OptiScaler needs it in, from its own GitHub, unmodified.")}
      {infoRow("Built on", "FSR4 Injector by Rayekkk (BSD-3-Clause): the plugin's library scan, launch options and updates.")}
      {infoRow("Source", "github.com/db1522/fsr4-lite-steam-machine · BSD-3-Clause. 7-Zip by Igor Pavlov (LGPL). Not affiliated with AMD or Valve.")}
    </PanelSection>
  </Focusable></div>;

  const settings = state.settings;
  const dl = state.download;
  const installed = state.games.filter(g => g.installed);
  const library = state.games.filter(listed);
  const running = Router.MainRunningApp;
  const current = running ? state.games.find(g => g.appid === Number(running.appid)) : undefined;

  const activeCount = state.games.filter(g => g.installed && g.verdict === "lite").length;

  const gameCard = () => {
    // One calm card: what's playing, its status, one button. No artwork (not every game has it, and each image is a
    // load); the card's edge takes the status colour instead.
    const head = (title: string, pill: [string, string] | null, dim = false) => <>
      <div className="sml-nowtop">
        <span className="sml-eyebrow">Now playing</span>
        {pill && <div className={`sml-live ${pill[0]}`}><span className={`sml-dot ${pill[0]}${pill[0] === "good" ? " live" : ""}`} />{pill[1]}</div>}
      </div>
      <div className={`sml-nowtitle${dim ? " dim" : ""}`}>{title}</div>
    </>;
    if (!running) return <div className="sml-now">
      {head("No game running", null, true)}
      <div className="sml-note">Start a game, then open this menu to set it up.</div>
    </div>;
    if (!current) return <div className="sml-now">
      {head(running.display_name, ["", "Not found"])}
      <div className="sml-note">The scan didn't find this game's files. If you installed or updated it recently, rescan your library under More.</div>
    </div>;
    const now = live && live.appid === current.appid ? live : null;
    const blocked = (!!current.anticheat && !current.installed) || (current.manual_optiscaler && !current.installed);
    const pill: [string, string] | null = current.anticheat && !current.installed ? ["bad", "Blocked"]
      : current.installed ? (livePill(now?.status) ?? chipFor(current)) : null;
    const note = current.anticheat && !current.installed
      ? `${current.anticheat} found. Injecting OptiScaler could get your account banned, so installs are blocked.`
      : current.manual_optiscaler && !current.installed ? "OptiScaler from another install is already in this game. Remove it first."
      : current.installed && now?.detail ? now.detail
      : current.installed && current.detail ? current.detail
      : `Then restart the game and pick ${pickText(current.upscalers)} in its graphics settings.`;
    const meta = [
      ...(current.upscalers.length ? current.upscalers : ["No upscaler files"]),
      ...(current.installed && current.proxy ? [`loads as ${current.proxy}`] : []),
    ].join(" · ");
    return <div className={`sml-now ${pill?.[0] ?? ""}`}>
      {head(current.name, pill && pill[1] ? pill : null)}
      <div className="sml-nowmeta">{current.anticheat ? `Blocked: ${current.anticheat}` : meta}</div>
      {!blocked && <DialogButton onGamepadFocus={keepInView} className={`sml-primary${current.installed ? " quiet" : ""}`}
        disabled={!current.installed && !state.assets_ready} onClick={() => toggle(current, !current.installed)}>
        {busy === current.appid ? "Working…" : current.installed ? "Uninstall FSR 4.1 Lite" : "Install FSR 4.1 Lite"}
      </DialogButton>}
      {failed[current.appid] && <div className="sml-note bad">{failed[current.appid]}</div>}
      <div className={`sml-note${now?.status === "inactive" ? " bad" : ""}`}>{note}</div>
      {!blocked && current.tip && <div className="sml-note soft">{current.tip}</div>}
      {current.compat && <div className={`sml-note soft${current.compat.startsWith("OptiScaler community") ? " bad" : ""}`}>{current.compat}</div>}
      {current.installed && <DialogButton onGamepadFocus={keepInView} className="sml-textbtn"
        onClick={() => { setCheckId(current.appid); navigate("check"); }}>Check setup ›</DialogButton>}
    </div>;
  };

  /** A slim row with an arrow: a link or an action (no big button). */
  const linkRow = (label: string, onActivate: () => void, description?: string, tone = "") =>
    <PanelSectionRow key={label}>
      <Field focusable highlightOnFocus onActivate={onActivate} className="sml-linkrow"
        label={<span className={`sml-linklabel ${tone}`}>{label}</span>} description={description}
        childrenLayout="inline" childrenContainerWidth="min" verticalAlignment="center">
        <span className="sml-chev">›</span>
      </Field>
    </PanelSectionRow>;

  const gameRow = (g: Game) => {
    const [tone, label] = chipFor(g);
    // Setting a game up happens on Now playing, with the game running (the plugin then sees which program is the
    // game, as the widget does). In this list a game can only be turned off; the others say how to set them up.
    const extra = [...g.upscalers, ...(g.nonsteam ? ["Non-Steam"] : [])].join(" · ");
    if (!g.installed) return <PanelSectionRow key={`r${g.appid}`}>
      <Field focusable className="sml-gameoff" label={<span className="sml-gamerow"><span className="sml-dot" /><span>{g.name}</span></span>}
        description={<span className={`sml-gamesub${g.anticheat ? " bad" : ""}`}>{g.anticheat ? `Blocked: ${g.anticheat}` : extra}</span>} />
    </PanelSectionRow>;
    return <PanelSectionRow key={`r${g.appid}`}>
      <ToggleField label={<span className="sml-gamerow">
          <span className={`sml-dot ${tone || "set"}`} />
          <span>{g.name}</span>
        </span>}
        description={<>
          <span className="sml-gamesub"><span className={`sml-state ${tone}`}>{label}</span>{extra && ` · ${extra}`}</span>
          {failure(failed[g.appid])}
        </>}
        checked
        onChange={on => { if (!on) toggle(g, false); }} />
    </PanelSectionRow>;
  };

  return (
    <div className="sml-root" ref={rootRef} onFocus={onFocusReveal}>
      <style>{CSS + steamCss()}</style>
      {/* Decky's title already names the plugin: one quiet status line instead of a second header */}
      <div className="sml-status">
        <span className={`sml-dot ${state.assets_ready ? "good" : "warn"}`} />
        <span>{state.assets_ready ? "Ready" : "Setup needed"}</span>
        {activeCount > 0 && <span className="sml-statusn">· {activeCount} active</span>}
        <span className="sml-ver">v{state.version}</span>
      </div>

      {updState.check?.update_available && updState.check.latest_version && <PanelSection><PanelSectionRow><div className="sml-card">
        <div className="sml-cardlabel">Update available</div>
        <div className="sml-game">FSR 4.1 Lite {updState.check.latest_version}</div>
        <div className="sml-note" style={{ marginBottom: 12 }}>
          You have {state.version}. It downloads from GitHub and Decky installs it; your games stay set up.
        </div>
        <DialogButton onGamepadFocus={keepInView} className="sml-primary"
          onClick={() => upd.run("download", updState.check?.latest_version)}>
          {updState.busy === "download" ? "Downloading…" : updState.download?.path ? "Installing…" : `Update to ${updState.check.latest_version}`}
        </DialogButton>
        {updState.error && <div className="sml-note bad">{updState.error}</div>}
      </div></PanelSectionRow></PanelSection>}

      {state.legacy.length > 0 && <PanelSection><PanelSectionRow><div className="sml-card">
        <div className="sml-cardlabel">Before you start</div>
        <div className="sml-game">Clean up version 1</div>
        <div className="sml-note" style={{ marginBottom: 12 }}>
          {state.legacy.length} game{state.legacy.length === 1 ? " is" : "s are"} still set up the old way. This removes those files and puts the launch options back.
        </div>
        <DialogButton onGamepadFocus={keepInView} className="sml-primary" onClick={cleanLegacy}>
          {busy === -1 ? "Cleaning up…" : "Clean up"}
        </DialogButton>
      </div></PanelSectionRow></PanelSection>}

      {!state.assets_ready && <PanelSection><PanelSectionRow><div className="sml-card">
        <div className="sml-cardlabel">Setup</div>
        <div className="sml-game">{dl.state === "running" ? `Downloading… ${MB(dl.done)} / ${MB(dl.total)}` : "Get OptiScaler and FSR 4"}</div>
        <div className="sml-note" style={{ marginBottom: 12 }}>
          About {MB(dl.total)} once: OptiScaler from its GitHub and AMD's FSR 4.1.2 files. Downloading accepts AMD's license for FSR.
        </div>
        {dl.state === "running"
          ? <DialogButton onGamepadFocus={keepInView} className="sml-primary quiet" onClick={async () => take(await cancelDownload())}>Cancel</DialogButton>
          : <DialogButton onGamepadFocus={keepInView} className="sml-primary" onClick={async () => take(await downloadAssets(), "download")}>Accept and download</DialogButton>}
        {dl.state === "error" && <div className="sml-note bad">Last attempt failed: {dl.error}</div>}
      </div></PanelSectionRow></PanelSection>}

      <PanelSection><PanelSectionRow>{gameCard()}</PanelSectionRow></PanelSection>

      <PanelSection>
        <PanelSectionRow>
          <Field focusable highlightOnFocus onActivate={toggleGames} className="sml-hdrrow"
            label={<span className="sml-hdr inrow">
              <span>Your games</span>
              <span className={`sml-count ${activeCount ? "good" : ""}`}>{installed.length} set up{activeCount ? ` · ${activeCount} active` : ""}</span>
            </span>}
            description={!state.scanned || scanning ? "Scanning your library…"
              : !library.length ? "No games with FSR, DLSS or XeSS found."
              : !gamesOpen ? `${library.length} compatible game${library.length === 1 ? "" : "s"}`
              : installed.length ? undefined : "None set up yet. Start a game to set it up."}
            childrenLayout="inline" childrenContainerWidth="min" verticalAlignment="center">
            <span className="sml-chev" style={{ transform: gamesOpen ? "rotate(90deg)" : "none" }}>›</span>
          </Field>
        </PanelSectionRow>
        {gamesOpen && installed.map(g => <Fragment key={g.appid}>
          {gameRow(g)}
          <PanelSectionRow>
            <Field focusable highlightOnFocus className="sml-sublink" onActivate={() => { setCheckId(g.appid); navigate("check"); }}
              label={<span className="sml-sublabel">Check setup</span>} childrenLayout="inline" childrenContainerWidth="min" verticalAlignment="center">
              <span className="sml-chev">›</span>
            </Field>
          </PanelSectionRow>
        </Fragment>)}
        {gamesOpen && library.length > installed.length && <PanelSectionRow>
          <Field focusable highlightOnFocus onActivate={() => flip("games")} className="sml-morerow"
            label={`${open.games ? "Hide" : ""}${open.games ? " " : ""}${library.length - installed.length} more game${library.length - installed.length === 1 ? "" : "s"}`}
            description={open.games ? "Start one of them to set it up." : undefined}
            childrenLayout="inline" childrenContainerWidth="min" verticalAlignment="center">
            <span className="sml-chev" style={{ transform: open.games ? "rotate(90deg)" : "none" }}>›</span>
          </Field>
        </PanelSectionRow>}
        {gamesOpen && open.games && library.filter(g => !g.installed).map(g => gameRow(g))}
      </PanelSection>

      <div className="sml-sect">Settings</div>
      <PanelSection>
        <PanelSectionRow>
          <ToggleField label="Notify when active" description="When FSR 4.1 Lite starts in a game."
            checked={settings.session_toast} onChange={async on => take(await setSetting("session_toast", on))} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="Show FPS and resolution" description="OptiScaler's overlay in every game."
            checked={settings.overlay} onChange={async on => take(await setSetting("overlay", on))} />
        </PanelSectionRow>
        {settings.overlay && <PanelSectionRow>
          <DropdownItem label="Overlay size" description="Sized for your TV."
            rgOptions={OVERLAY_SIZES.map(([data, label]) => ({ data, label }))} selectedOption={settings.overlay_size}
            onChange={async o => take(await setSetting("overlay_size", o.data as string))} />
        </PanelSectionRow>}
        {settings.overlay && <PanelSectionRow>
          <DropdownItem label="Overlay corner"
            rgOptions={OVERLAY_CORNERS.map(([data, label]) => ({ data, label }))} selectedOption={settings.overlay_pos}
            onChange={async o => take(await setSetting("overlay_pos", o.data as string))} />
        </PanelSectionRow>}
        <PanelSectionRow>
          <ToggleField label="Show AMD's watermark" description="For checks and screenshots."
            checked={settings.watermark} onChange={async on => take(await setSetting("watermark", on))} />
        </PanelSectionRow>
      </PanelSection>

      <div className="sml-sect">More</div>
      <PanelSection>
        {linkRow(scanning ? "Scanning…" : "Rescan library", rescan)}
        {installed.length > 0 && linkRow(busy === -1 && bulk ? `Removing… ${bulk}` : "Uninstall from all games", uninstallAll,
          "Puts every game back as it was.", "danger")}
        {linkRow("About and updates", () => navigate("about"), `Version ${state.version}`)}
      </PanelSection>
    </div>
  );
};
