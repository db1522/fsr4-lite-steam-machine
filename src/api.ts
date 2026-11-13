// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk
// Copyright (c) 2026 Steam Machine Life (changes)

// The backend's methods, typed, and Steam's launch options. Every call goes through settle(): it never rejects, a
// dead backend is { ok: false, error } like any refusal (DeckyKit D2).
import { callable } from "@decky/api";
import { UpdateCheck, UpdateDownload } from "./about";
import { Result, settle } from "./result";

export type Verdict = "" | "unplayed" | "lite" | "fsr4" | "fsr3" | "waiting" | "unsupported" | "none";

export interface Game {
  appid: number;
  name: string;
  exe_name: string;
  upscalers: string[];  // what the game ships: FSR 3.1, FSR 2, DLSS, XeSS
  anticheat: string;  // its name, "" when none
  broken?: string;  // why OptiScaler can't run in it on SteamOS (installs blocked), "" when it can
  nonsteam: boolean;
  manual_optiscaler: boolean;  // OptiScaler from another install is already there
  installed: boolean;
  compat: string;  // OptiScaler's community Compatibility List: "Works with: …" or a warning ("" when not listed)
  tip: string;  // the widget's card line: no upscaler files, DLSS/XeSS only, or the game's own rule ("" when none)
  verdict: Verdict;
  detail: string;
  proxy?: string;  // the name OptiScaler loads under
  turned_off?: string;  // why crash protection turned FSR 4.1 Lite off for this game ("" when it didn't)
  sharpness?: number | null;  // 0 to 1, set in the plugin for this game; null: the game's own
}

export interface Download { state: "idle" | "running" | "done" | "error"; done: number; total: number; error: string }

export interface State {
  version: string;
  home: string;
  assets_ready: boolean;
  download: Download;
  settings: { session_toast: boolean; watermark: boolean; overlay: boolean; auto_update: boolean;
    overlay_size: "small" | "medium" | "large" | "xlarge" | "huge"; overlay_pos: "topleft" | "topright" | "bottomleft" | "bottomright" };
  scanned: boolean;
  games: Game[];
  legacy: number[];  // games still set up by FSR 4.1 Lite 1.x
  linux?: number[];  // Steam games installed as their native Linux version: they need Proton forced first
  linux_note?: string;  // what the card says for them
  optiscaler: string;  // the OptiScaler build new setups get, "OptiScaler v10.0.0-pre1 (Nov 7, 2026)"
  opti_note: string;   // why the last check for a newer build failed, if it did
}

export interface Diagnosis {
  name: string; installed: boolean; exe_dir: string; exe_name: string; proxy: string;
  files_ok: boolean; missing: string[]; upscalers: string[]; anticheat: string; proton: string;
  verdict: Verdict; detail: string; log_lines: string[];
  opti_build: string; opti_current: string;  // the game's OptiScaler build and the newest one here
}

export type StateResult = Result<State>;
export type ToggleResult = StateResult & { launch_options?: string };

const rpc = <A extends unknown[], R extends Result<unknown>>(name: string) => {
  const call = callable<A, R>(name);
  return (...args: A) => settle(call(...args));
};

export const getState = rpc<[], StateResult>("get_state");
export const scanGames = rpc<[], StateResult>("scan_games");
export const downloadAssets = rpc<[], StateResult>("download_assets");
export const downloadProgress = rpc<[], Result<never> & { download?: Download; assets_ready?: boolean }>("download_progress");
export const cancelDownload = rpc<[], StateResult>("cancel_download");
export const enableGame = rpc<[number, string], ToggleResult>("enable_game");
export const disableGame = rpc<[number, string], ToggleResult>("disable_game");
export const cleanupLegacy = rpc<[number, string], ToggleResult>("cleanup_legacy");
/** OptiScaler from another install moved out of the game's folder (into the plugin's data, nothing deleted). */
export const removeManual = rpc<[number], StateResult & { moved?: string[]; backup?: string }>("remove_manual");
export const setSetting = rpc<[string, boolean | string], StateResult>("set_setting");
export const setSharpness = rpc<[number, number | null], StateResult>("set_sharpness");
// A line in the backend's timeline for freeze reports (what the panel asked Steam to do, and when)
export const note = rpc<[string], Result<never>>("note");
// The game in the library list a running app id is: a non-Steam shortcut can run under its game's own Steam id.
export const resolveRunning = rpc<[number], Result<never> & { appid?: number }>("resolve_running");
export const checkOptiscaler = rpc<[], StateResult & { message?: string }>("check_optiscaler");
export const diagnose = rpc<[number], Result<never> & { report?: Diagnosis }>("diagnose");
export const saveReport = rpc<[number], Result<never> & { saved?: string }>("save_report");
export const sessionStarted = rpc<[number], Result<never> & { managed?: boolean; appid?: number }>("session_started");
export type Live = "idle" | "off" | "restart" | "starting" | "active" | "inactive";
export const liveStatus = rpc<[number], Result<never> & { status?: Live; detail?: string }>("live_status");
export const sessionCheck = rpc<[number], Result<never> & {
  lite?: boolean; done?: boolean; summary?: string; minutes?: number; hint?: string;
}>("session_check");
export const sessionEnded = rpc<[number, string], Result<never> & {
  managed?: boolean; verdict?: Verdict; detail?: string; retry?: string; launch_options?: string;
  turned_off?: boolean }>("session_ended");
export const checkForUpdates = rpc<[], UpdateCheck>("check_for_updates");
export const performUpdate = rpc<[string], UpdateDownload>("perform_update");

export const off = (u: SteamUnregister | undefined) => (typeof u === "function" ? u() : u?.unregister());

// Current launch options straight from Steam. Rejects instead of guessing, so the user's own options are never lost.
// Right after a write a non-Steam shortcut first reports its old options and the new ones a moment later, so a
// read-back that expects a value waits up to a second for it, then takes what Steam said last.
export const readLaunchOptions = (appid: number, expected?: string) =>
  new Promise<string>((resolve, reject) => {
    let done = false, last: string | undefined;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      setTimeout(() => off(reg), 0);
      if (last === undefined) reject(new Error("Steam did not return the launch options"));
      else resolve(last);
    };
    const timer = setTimeout(finish, 3000);
    const reg = SteamClient.Apps.RegisterForAppDetails(appid, details => {
      if (done) return;
      last = details?.strLaunchOptions ?? "";
      if (expected === undefined || last === expected) finish();
      else setTimeout(finish, 1000);
    });
  });

// Writes launch options to Steam and reads back what Steam kept. Resolves true when Steam kept exactly them.
export const saveLaunchOptions = async (appid: number, options: string) => {
  note(`saving launch options for ${appid}`);
  SteamClient.Apps.SetAppLaunchOptions(appid, options);
  return (await readLaunchOptions(appid, options).catch(() => "")) === options;
};
