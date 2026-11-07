// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk
// Copyright (c) 2026 Steam Machine Life (changes)

// FSR 4.1 Lite's panel: one method for every game (OptiScaler with the Lite model), laid out like the FSR 4.1 Lite
// widget for Windows. Status line, a one-time setup card, the game you're playing with one button, every compatible
// game in one list, then options, library tools and About.
import { useQuickAccessVisible } from "@decky/api";
import { DialogButton, DropdownItem, Field, Focusable, PanelSection, PanelSectionRow, Router, ToggleField } from "@decky/ui";
import { FC, Fragment, ReactNode, useCallback, useEffect, useState } from "react";
import { INSTALL_HINT, UpdateController, UpdateSection } from "./about";
import { CSS, steamCss } from "./style";
import { CheckPage } from "./check";
import { canInstallUpdates, installUpdate } from "./installer";
import { capsuleImage, heroImage, keepInView, onFocusReveal } from "./steamx";
import {
  cancelDownload, checkForUpdates, cleanupLegacy, disableGame, downloadAssets, downloadProgress, enableGame, Game,
  getState, Live, liveStatus, performUpdate, readLaunchOptions, saveLaunchOptions, scanGames, setSetting, State,
  StateResult,
} from "./api";
import { errorText } from "./result";
import { ActionButton, colors, infoRow, notify, PageHeader, SectionLink, statusPlaceholder } from "./ui";

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

const failure = (text?: string): ReactNode => text ? <div style={{ color: colors.error }}>{text}</div> : null;

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
  const [heroFailed, setHeroFailed] = useState<number | null>(null);
  const [thumbFailed, setThumbFailed] = useState<Record<number, boolean>>({});
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
  const flip = (k: string) => setOpen(o => ({ ...o, [k]: !o[k] }));
  const setState = useCallback((s: State) => { lastState = s; setStateRaw(s); }, []);

  const take = <R extends StateResult>(r: R, key?: string | number): R => {
    if (r.state) setState(r.state);
    if (key !== undefined) setFailed(f => ({ ...f, [key]: r.ok ? "" : errorText(r) }));
    return r;
  };
  const refresh = useCallback(async () => {
    const r = await getState();
    if (r.ok && r.state) { setState(r.state); setError(""); } else setError(errorText(r));
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
  const applyAll = async (on: boolean) => {
    if (busy !== null || !state) return;
    const list = state.games.filter(g => on ? !g.installed && !g.anticheat && !g.manual_optiscaler : g.installed);
    setBusy(-1);
    let n = 0;
    for (const g of list) { setBulk(`${++n} of ${list.length}`); await apply(g, on); }
    setBulk("");
    setBusy(null);
    notify(NAME, on ? `Set up in ${n} game${n === 1 ? "" : "s"}.` : `Removed from ${n} game${n === 1 ? "" : "s"}.`);
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

  if (!state) return <div className="sml-root"><style>{CSS + steamCss()}</style>
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
    <PageHeader title="About" back={NAME} onBack={() => navigate(null)} focus={visible} />
    <PanelSection title={`${NAME} ${state.version}`}>
      {infoRow("Steam Machine Life", "Runs AMD's FSR 4.1.2 Lite model in your games on the Steam Machine. The same method as the FSR 4.1 Lite widget for Windows.")}
      {infoRow("OptiScaler", `${state.optiscaler}, by cdozdil and contributors (GPL-3.0). Downloaded from its own GitHub, unmodified.`)}
      {infoRow("FSR 4", "By AMD. AMD's signed FSR 4.1.2 files, unmodified, made available to the community by TheRazerMD.")}
      {infoRow("Built on", "FSR4 Injector by Rayekkk (BSD-3-Clause): the plugin's library scan, launch options and updates.")}
      {infoRow("Source", "github.com/db1522/fsr4-lite · BSD-3-Clause. 7-Zip by Igor Pavlov (LGPL). Not affiliated with AMD or Valve.")}
    </PanelSection>
  </Focusable></div>;

  const settings = state.settings;
  const dl = state.download;
  const installed = state.games.filter(g => g.installed);
  const running = Router.MainRunningApp;
  const current = running ? state.games.find(g => g.appid === Number(running.appid)) : undefined;

  const activeCount = state.games.filter(g => g.installed && g.verdict === "lite").length;

  const gameCard = () => {
    const art = (appid: number | null, title: string, pill: [string, string] | null) => {
      const hero = appid !== null && heroFailed !== appid ? heroImage(appid) : "";
      return <div className="sml-art">
        {hero && <img src={hero} alt="" onError={() => setHeroFailed(appid)} />}
        <div className="sml-artlabel">Now playing</div>
        {pill && <div className={`sml-live ${pill[0]}`}><span className={`sml-dot ${pill[0]}${pill[0] === "good" ? " live" : ""}`} />{pill[1]}</div>}
        <div className="sml-arttitle">{title}</div>
      </div>;
    };
    if (!running) return <div className="sml-now">
      {art(null, "No game running", null)}
      <div className="sml-body"><div className="sml-note" style={{ marginTop: 0 }}>Start a game, then open this menu to set up FSR 4.1 Lite in it with one button.</div></div>
    </div>;
    if (!current) return <div className="sml-now">
      {art(Number(running.appid), running.display_name, ["", "No upscaler found"])}
      <div className="sml-body"><div className="sml-note" style={{ marginTop: 0 }}>The scan didn't find FSR, DLSS or XeSS in this game, so OptiScaler has nothing to take over. If it updated recently, rescan your library below.</div></div>
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
      : "Takes effect when you restart the game. In its settings, pick FSR, DLSS or XeSS as the upscaler.";
    return <div className="sml-now">
      {art(current.appid, current.name, pill && pill[1] ? pill : null)}
      <div className="sml-body">
        <div className="sml-meta">
          {current.upscalers.map(u => <span key={u} className="sml-badge">{u}</span>)}
          {current.installed && current.proxy && <span className="sml-badge">Loads as {current.proxy}</span>}
          {current.anticheat && <span className="sml-badge bad">Blocked: {current.anticheat}</span>}
        </div>
        {!blocked && <DialogButton onGamepadFocus={keepInView} className={`sml-primary${current.installed ? " quiet" : ""}`}
          disabled={!current.installed && !state.assets_ready} onClick={() => toggle(current, !current.installed)}>
          {busy === current.appid ? "Working…" : current.installed ? "Uninstall FSR 4.1 Lite" : "Install FSR 4.1 Lite"}
        </DialogButton>}
        {current.installed && <div style={{ marginTop: 8 }}>
          <DialogButton onGamepadFocus={keepInView} className="sml-primary quiet"
            onClick={() => { setCheckId(current.appid); navigate("check"); }}>Check setup</DialogButton>
        </div>}
        <div className={`sml-note${now?.status === "inactive" ? " bad" : ""}`}>{note}</div>
        {failed[current.appid] && <div className="sml-note bad">{failed[current.appid]}</div>}
      </div>
    </div>;
  };

  const gameRow = (g: Game) => {
    const [tone, label] = chipFor(g);
    const thumb = thumbFailed[g.appid] ? "" : capsuleImage(g.appid);
    return <PanelSectionRow key={`r${g.appid}`}>
      <ToggleField label={<span className="sml-gamerow">
          {thumb ? <img className="sml-thumb" src={thumb} alt="" onError={() => setThumbFailed(f => ({ ...f, [g.appid]: true }))} />
            : <span className="sml-thumb blank" />}
          <span>{g.name}</span>
        </span>}
        description={<>
          <span className="sml-chips">
            {g.installed && <span className={`sml-badge ${tone}`}>{label}</span>}
            {g.upscalers.map(u => <span key={u} className="sml-badge">{u}</span>)}
            {g.nonsteam && <span className="sml-badge">Non-Steam</span>}
            {g.anticheat && <span className="sml-badge bad">Blocked: {g.anticheat}</span>}
          </span>
          {failure(failed[g.appid])}
        </>}
        checked={g.installed}
        disabled={!g.installed && (!state.assets_ready || !!g.anticheat || g.manual_optiscaler)}
        onChange={on => toggle(g, on)} />
    </PanelSectionRow>;
  };

  return (
    <div className="sml-root" onFocus={onFocusReveal}>
      <style>{CSS + steamCss()}</style>
      <div className="sml-top">
        <div className="sml-mark"><span>4.1</span></div>
        <div>
          <div className="sml-title">FSR 4.1 <b>Lite</b></div>
          <div className="sml-sub">by Steam Machine Life</div>
        </div>
        <div className="sml-pillver">v{state.version}</div>
      </div>
      <div className="sml-stats">
        <div className="sml-stat"><b>{installed.length}</b><span>Set up</span></div>
        <div className="sml-stat"><b className={activeCount ? "good" : ""}>{activeCount}</b><span>Active</span></div>
        <div className="sml-stat"><b style={{ color: state.assets_ready ? undefined : "var(--warn)" }}>{state.assets_ready ? "Ready" : "Setup"}</b>
          <span>{state.assets_ready ? "OptiScaler v10" : "Download needed"}</span></div>
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
          <Field focusable highlightOnFocus onActivate={() => flip("games")}
            label={`Games: ${installed.length} of ${state.games.length} set up`}
            description={!state.scanned || scanning ? "Scanning your library…"
              : state.games.length ? "Games with FSR, DLSS or XeSS. Turn one off to restore its files." : "No compatible games found."}
            childrenLayout="inline" childrenContainerWidth="min" verticalAlignment="center">
            <span style={{ display: "inline-block", transform: open.games ? "rotate(90deg)" : "none", transition: "transform .15s" }}>›</span>
          </Field>
        </PanelSectionRow>
        {open.games && state.games.map(g => <Fragment key={g.appid}>
          {gameRow(g)}
          {g.installed && <PanelSectionRow>
            <ActionButton onClick={() => { setCheckId(g.appid); navigate("check"); }}>Check setup: {g.name}</ActionButton>
          </PanelSectionRow>}
        </Fragment>)}
      </PanelSection>

      <div className="sml-sect">Options</div>
      <PanelSection>
        <PanelSectionRow>
          <ToggleField label="Notify when active" description="A notification in the game as soon as FSR 4.1 Lite is running."
            checked={settings.session_toast} onChange={async on => take(await setSetting("session_toast", on))} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label="Show FPS and resolution" description="OptiScaler's overlay: the upscaler in use and render → output resolution."
            checked={settings.overlay} onChange={async on => take(await setSetting("overlay", on))} />
        </PanelSectionRow>
        {settings.overlay && <PanelSectionRow>
          <DropdownItem label="Overlay size" description="Sized for your TV. Takes effect the next time a game starts."
            rgOptions={OVERLAY_SIZES.map(([data, label]) => ({ data, label }))} selectedOption={settings.overlay_size}
            onChange={async o => take(await setSetting("overlay_size", o.data as string))} />
        </PanelSectionRow>}
        {settings.overlay && <PanelSectionRow>
          <DropdownItem label="Overlay corner"
            rgOptions={OVERLAY_CORNERS.map(([data, label]) => ({ data, label }))} selectedOption={settings.overlay_pos}
            onChange={async o => take(await setSetting("overlay_pos", o.data as string))} />
        </PanelSectionRow>}
        <PanelSectionRow>
          <ToggleField label="Show AMD's watermark" description="AMD's label of the FSR 4 model in use. For checks and screenshots."
            checked={settings.watermark} onChange={async on => take(await setSetting("watermark", on))} />
        </PanelSectionRow>
      </PanelSection>

      <div className="sml-sect">Library</div>
      <PanelSection>
        <PanelSectionRow>
          <ActionButton onClick={rescan}>{scanning ? "Scanning…" : "Rescan library"}</ActionButton>
        </PanelSectionRow>
        {state.games.length > 0 && <PanelSectionRow>
          <ActionButton onClick={() => applyAll(true)} description="Skips games with anti-cheat, which stay blocked.">
            {busy === -1 && bulk ? `Setting up… ${bulk}` : "Install in all compatible games"}
          </ActionButton>
        </PanelSectionRow>}
        {state.games.length > 0 && <PanelSectionRow>
          <ActionButton onClick={() => applyAll(false)} description="Puts every game back as it was. Do this before removing the plugin.">
            {busy === -1 && bulk ? `Removing… ${bulk}` : "Uninstall from all games"}
          </ActionButton>
        </PanelSectionRow>}
      </PanelSection>

      <div className="sml-sect">Updates</div>
      <UpdateSection controller={upd} version={state.version} home={state.home}
        install={`${INSTALL_HINT} Your games stay set up.`}
        onInstall={canInstallUpdates() ? d => installUpdate(d.path ?? "", d.version ?? "", d.sha256 ?? "") : undefined} />

      <PanelSection>
        <SectionLink title="About" description="Credits and licenses"
          icon={<><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>} onOpen={() => navigate("about")} />
      </PanelSection>
    </div>
  );
};
