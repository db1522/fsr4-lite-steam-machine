// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026 Steam Machine Life
// Check setup: every condition FSR 4.1 Lite needs in one game, in plain words, with one fix button and a report
// that can be saved to Downloads and sent, the same report the Windows widget makes.
import { DialogButton, Field, PanelSection, PanelSectionRow, Spinner } from "@decky/ui";
import { FC, ReactNode, useCallback, useEffect, useState } from "react";
import { diagnose, Diagnosis, readLaunchOptions, saveReport } from "./api";
import { keepInView } from "./steamx";

type Tone = "good" | "warn" | "bad";
export interface Check { tone: Tone; title: string; detail: string }

const ICON: Record<Tone, string> = { good: "✓", warn: "!", bad: "✕" };
const COLOR: Record<Tone, string> = { good: "#3fd68f", warn: "#f5c96b", bad: "#ff8a95" };

export function protonCheck(proton: string): Check {
  const p = proton.toLowerCase();
  if (!p) return { tone: "warn", title: "Proton: not launched yet", detail: "Start the game once so Steam sets up its Proton." };
  if (p.includes("experimental")) return { tone: "good", title: `Proton: ${proton}`, detail: "Supported." };
  const m = p.match(/(?:ge-)?proton[ -]?(\d+)/);
  if (m && Number(m[1]) < 10) return { tone: "warn", title: `Proton: ${proton}`,
    detail: "Older than Proton 10. If FSR 4.1 Lite doesn't start, pick Proton Experimental in the game's Properties → Compatibility." };
  return { tone: "good", title: `Proton: ${proton}`, detail: "Supported." };
}

export function checks(d: Diagnosis, options: string): Check[] {
  if (!d.installed) return [{ tone: "bad", title: "Not set up", detail: "Install FSR 4.1 Lite in this game first." }];
  const out: Check[] = [];
  out.push(d.files_ok
    ? { tone: "good", title: "OptiScaler in place", detail: `Next to ${d.exe_name}, loading as ${d.proxy}.` }
    : { tone: "bad", title: "Files missing", detail: "A game update or Steam's file check removed them. Press Fix setup." });
  if (d.opti_build) out.push(d.opti_build === d.opti_current
    ? { tone: "good", title: d.opti_build, detail: "The newest OptiScaler build here." }
    : { tone: "good", title: d.opti_build, detail: `Gets ${d.opti_current} once the game is closed.` });
  const name = d.proxy.replace(/\.dll$/i, "");
  out.push(new RegExp(`WINEDLLOVERRIDES=\\S*\\b${name}=n,b`).test(options)
    ? { tone: "good", title: "Launch option set", detail: "Proton loads OptiScaler." }
    : { tone: "bad", title: "Launch option missing", detail: "Without it Proton ignores OptiScaler. Press Fix setup." });
  out.push(protonCheck(d.proton));
  if (d.upscalers.length) out.push({ tone: "good", title: `Game ships ${d.upscalers.join(", ")}`,
    detail: "Pick one of these as the upscaler in the game's graphics settings. OptiScaler swaps it for FSR 4.1 Lite." });
  const last: Record<string, Check> = {
    lite: { tone: "good", title: "FSR 4.1 Lite ran", detail: "OptiScaler's log shows the Lite model last session." },
    fsr4: { tone: "warn", title: "FSR 4 ran, Lite not confirmed", detail: "Press Fix setup and play again. If it stays, save a report." },
    fsr3: { tone: "warn", title: "The game used FSR 3", detail: d.detail },
    waiting: { tone: "warn", title: "The upscaler didn't start", detail: d.detail },
    unsupported: { tone: "bad", title: "FSR 4 can't run here", detail: d.detail },
    none: { tone: "bad", title: "OptiScaler didn't load", detail: d.detail || "Play once more: the plugin tries the next loader name by itself." },
  };
  out.push(last[d.verdict] ?? { tone: "warn", title: "Not played yet", detail: "Play the game for a minute with an upscaler picked, then check again." });
  return out;
}

export const CheckPage: FC<{ appid: number; onFix(): Promise<void> }> = ({ appid, onFix }) => {
  const [report, setReport] = useState<Diagnosis | null>(null);
  const [options, setOptions] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [saved, setSaved] = useState("");
  const [details, setDetails] = useState(false);
  const load = useCallback(async () => {
    setError("");
    const [r, o] = await Promise.all([diagnose(appid), readLaunchOptions(appid).catch(() => "")]);
    if (r.ok && r.report) { setReport(r.report); setOptions(o); } else setError(r.error ?? "Couldn't read this game's setup.");
  }, [appid]);
  useEffect(() => { load(); }, [load]);

  if (error) return <PanelSection><PanelSectionRow><Field focusable label="Check failed" description={error} /></PanelSectionRow></PanelSection>;
  if (!report) return <PanelSection><PanelSectionRow><Spinner /></PanelSectionRow></PanelSection>;
  const list = checks(report, options);
  const fixable = report.installed && list.some(c => c.tone !== "good" && /Fix setup/.test(c.detail));
  const row = (c: Check, i: number): ReactNode => <PanelSectionRow key={i}>
    <Field focusable label={<span><span style={{ color: COLOR[c.tone], fontWeight: 700, marginRight: 8 }}>{ICON[c.tone]}</span>{c.title}</span>}
      description={c.detail} />
  </PanelSectionRow>;
  return <>
    <PanelSection><PanelSectionRow><div className="sml-card" style={{ marginTop: 4 }}>
      <div className="sml-cardlabel">Check setup</div>
      <div className="sml-game">{report.name}</div>
      <div className="sml-note" style={{ marginBottom: 12 }}>
        {list.every(c => c.tone === "good") ? "Everything is in place." : `${list.filter(c => c.tone !== "good").length} thing(s) to look at below.`}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {fixable && <DialogButton onGamepadFocus={keepInView} className="sml-primary"
          onClick={async () => { if (working) return; setWorking(true); await onFix(); setWorking(false); load(); }}>
          {working ? "Fixing…" : "Fix setup"}
        </DialogButton>}
        <DialogButton onGamepadFocus={keepInView} className="sml-primary quiet"
          onClick={async () => { const r = await saveReport(appid); setSaved(r.ok ? (r.saved ?? "") : (r.error ?? "")); }}>
          Save report to Downloads
        </DialogButton>
        <DialogButton onGamepadFocus={keepInView} className="sml-primary quiet" onClick={load}>Check again</DialogButton>
      </div>
      {saved && <div className="sml-note">{saved.replace(/^\/home\/[^/]+/, "~")}. Upload it from Desktop Mode when asking for help.</div>}
    </div></PanelSectionRow></PanelSection>
    <PanelSection>{list.map(row)}</PanelSection>
    {report.log_lines.length > 0 && <PanelSection>
      <PanelSectionRow>
        <Field focusable highlightOnFocus onActivate={() => setDetails(!details)} label="OptiScaler log"
          description="The lines about FSR 4 from the last session." childrenLayout="inline" childrenContainerWidth="min"
          verticalAlignment="center">{details ? "▾" : "›"}</Field>
      </PanelSectionRow>
      {details && <PanelSectionRow><Field focusable label="" description={
        <div style={{ fontFamily: "monospace", fontSize: 11, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{report.log_lines.join("\n")}</div>} /></PanelSectionRow>}
    </PanelSection>}
  </>;
};
