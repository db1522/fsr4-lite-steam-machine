// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Rayekkk
// Copyright (c) 2026 Steam Machine Life (changes)

import { definePlugin } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { getState, off, readLaunchOptions, saveLaunchOptions, sessionCheck, sessionEnded, sessionStarted } from "./api";
import { closeUpdates, Content } from "./panel";
import { notify } from "./ui";

// A "4" badge for FSR 4.
const Fsr4Icon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
    strokeLinecap="round" strokeLinejoin="round" style={{ width: "1em", height: "1em" }}>
    <rect x="2.5" y="2.5" width="19" height="19" rx="4.5" />
    <path d="M14.5 6.5 8 14.5h9" />
    <path d="M14.5 6.5v11" />
  </svg>
);

const NAME = "FSR 4.1 Lite";

export default definePlugin(() => {
  // While a game we set up runs, OptiScaler's log is read every few seconds until it shows the Lite model.
  const watching = new Map<number, number | undefined>();
  const unwatch = (appid: number) => { window.clearTimeout(watching.get(appid)); watching.delete(appid); };
  const check = (appid: number, name: string) => watching.set(appid, window.setTimeout(async () => {
    const res = await sessionCheck(appid);
    if (!watching.has(appid) || res.done) return void unwatch(appid);
    if (res.lite) { unwatch(appid); notify(`${NAME} active`, `${name} is running FSR 4.1 Lite.`); return; }
    check(appid, name);
  }, 5000));

  const lifetime = SteamClient.GameSessions.RegisterForAppLifetimeNotifications(async n => {
    if (n?.bRunning) {
      const res = await sessionStarted(n.unAppID);
      if (!res.managed) return;
      const r = await getState();
      if (!r.state?.settings.session_toast) return;
      const name = r.state.games.find(g => g.appid === n.unAppID)?.name ?? "The game";
      check(n.unAppID, name);
      return;
    }
    unwatch(n.unAppID);
    const options = await readLaunchOptions(n.unAppID).catch(() => "");
    const res = await sessionEnded(n.unAppID, options);
    if (!res.managed) return;
    if (res.retry && res.launch_options !== undefined) {
      await saveLaunchOptions(n.unAppID, res.launch_options);
      notify(`${NAME}: one more try`, res.detail ?? "Play once more.");
    } else if (res.verdict && !["lite", "unplayed"].includes(res.verdict)) {
      notify(`${NAME} not active`, res.detail ?? "Open Check setup to see why.");
    }
  });

  return {
    name: NAME,
    titleView: <div className={staticClasses.Title}>{NAME}</div>,
    content: <Content />,
    icon: <Fsr4Icon />,
    onDismount() {
      off(lifetime);
      [...watching.keys()].forEach(unwatch);
      closeUpdates();
    },
  };
});
