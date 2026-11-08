// SPDX-License-Identifier: BSD-3-Clause
// Steam Machine Life: Steam client helpers the panel uses for artwork and Proton. Every call is guarded: Steam builds
// differ, and a missing call falls back to the plain behaviour instead of breaking the panel.
import { Navigation } from "@decky/ui";

/** The game's wide library hero image, or "" when there is none. Steam serves its own cache at steamloopback.host. */
export const heroImage = (appid: number): string => {
  try {
    const overview = appStore?.GetAppOverviewByAppID(appid);
    const custom = overview && appStore.GetCustomHeroImageURLs?.(overview);
    if (custom?.length) return custom[0];
  } catch { /* fall through to Steam's cache */ }
  return appid < 2 ** 31 ? `https://steamloopback.host/assets/${appid}/library_hero.jpg` : "";
};

/** The game's small library header image for list rows, or "" for non-Steam games (no Steam artwork cache). */
export const capsuleImage = (appid: number): string =>
  appid < 2 ** 31 ? `https://steamloopback.host/assets/${appid}/header.jpg` : "";

/** Opens a web page in Steam's browser (Gaming Mode's own overlay browser). False when this Steam can't. */
export const openWeb = (url: string): boolean => {
  try {
    Navigation.NavigateToExternalWeb(url);
    return true;
  } catch {
    return false;
  }
};

/** Whether this Steam can switch a game's compatibility tool from a plugin. */
export const canSetProton = () => typeof SteamClient?.Apps?.SpecifyCompatTool === "function";

/** Sets the game to Proton Experimental. Returns false when this Steam build has no way to do it. */
export const setProtonExperimental = (appid: number): boolean => {
  try {
    if (!canSetProton()) return false;
    SteamClient.Apps.SpecifyCompatTool!(appid, "proton_experimental");
    return true;
  } catch {
    return false;
  }
};

/** Decky's panel header stays put while the content scrolls under it, and Steam scrolls a row only to the top edge,
 *  so a row reached by pressing up can end up hidden behind the header. Whatever gets the focus inside the panel is
 *  moved to the middle when it sits under the header (or off the bottom); rows already in view are left alone. */
const HEADER = 110;  // px: Decky's title bar plus the QAM tabs above it, with a margin
export const revealIfHidden = (el: Element | null | undefined) => {
  try {
    if (!el?.getBoundingClientRect) return;
    const r = el.getBoundingClientRect();
    if (r.top < HEADER || r.bottom > window.innerHeight - 16) el.scrollIntoView({ block: "center" });
  } catch { /* older engines: Steam's own scroll applies */ }
};
export const keepInView = (e: Event) => revealIfHidden((e.currentTarget ?? e.target) as Element | null);

/** Back to the top of the panel when the Quick Access Menu opens: the focus moves to the panel's first control (Steam
 *  would put it back where it was left, scrolling down again), then every scrolled container around the panel goes
 *  back to the top. */
export const toTop = (root: HTMLElement | null | undefined) => {
  try {
    if (!root) return;
    root.querySelector<HTMLElement>("button, [tabindex]:not([tabindex='-1'])")?.focus({ preventScroll: true });
    for (let el: HTMLElement | null = root; el; el = el.parentElement) {
      if (el.scrollTop) el.scrollTop = 0;
    }
  } catch { /* older engines: Steam's own scroll applies */ }
};
/** For a page's root: every focus inside it, whichever control it lands on. */
export const onFocusReveal = (e: { target: EventTarget }) => revealIfHidden(e.target as Element);


/** A game's id for starting and closing it: a Steam game's app id, or a non-Steam shortcut's 64-bit m_gameid. */
export const gameId = (appid: number): string => {
  const o = appStore.GetAppOverviewByAppID(appid) as (SteamAppOverview & { m_gameid?: string }) | null | undefined;
  return o?.m_gameid || String(appid);
};

/**
 * Closes the running game and starts it again, so OptiScaler loads (Restart now). Waits up to a minute for it to
 * close; false when Steam can't close or start games here, or it didn't close in time.
 */
export const restartGame = async (appid: number, running: () => boolean, wait = (ms: number) =>
  new Promise<void>(r => window.setTimeout(r, ms))): Promise<boolean> => {
  const apps = SteamClient.Apps;
  if (!apps.TerminateApp || !apps.RunGame) return false;
  const id = gameId(appid);
  apps.TerminateApp(id, false);
  for (let i = 0; i < 120 && running(); i++) await wait(500);
  if (running()) return false;
  await wait(2000);  // Steam finishes the session (cloud sync, the plugin's session end) before the next start
  apps.RunGame(id, "", -1, 100);
  return true;
};
