// SPDX-License-Identifier: BSD-3-Clause
// Steam Machine Life: installs an update the plugin already downloaded and verified, through Decky's own plugin
// installer (the one behind the Store and Developer → Install Plugin from ZIP). Decky shows its usual confirmation,
// checks the ZIP's SHA-256 again, replaces the plugin and reloads it; the user's games stay set up.
// This is Decky's internal backend route, not a published plugin API: every step is guarded, and any failure leaves
// the ZIP in Downloads with the manual steps, exactly as before.

type DeckyBackend = { call?: (route: string, ...args: unknown[]) => Promise<unknown> };

const PLUGIN_NAME = "FSR 4.1 Lite";
const UPDATE = 2;  // Decky's PluginInstallType: INSTALL 0, REINSTALL 1, UPDATE 2

export const canInstallUpdates = () =>
  typeof (window as unknown as { DeckyBackend?: DeckyBackend }).DeckyBackend?.call === "function";

/** Hands the verified ZIP to Decky. Resolves true once Decky accepted the request (its dialog takes it from there). */
export async function installUpdate(path: string, version: string, sha256: string): Promise<boolean> {
  const backend = (window as unknown as { DeckyBackend?: DeckyBackend }).DeckyBackend;
  if (!backend?.call || !path || !version || !/^[0-9a-f]{64}$/.test(sha256)) return false;
  try {
    await backend.call("utilities/install_plugin", `file://${path}`, PLUGIN_NAME, version, sha256, UPDATE);
    return true;
  } catch {
    return false;
  }
}
