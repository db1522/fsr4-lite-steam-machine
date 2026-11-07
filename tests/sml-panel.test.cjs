// SPDX-License-Identifier: BSD-3-Clause
// FSR 4.1 Lite 2.0 panel: setup card, the Now playing card, the one game list, Check setup and session handling.
const test = require('node:test');
const assert = require('node:assert/strict');
const { harness, all, settle } = require('./frontend_harness.cjs');

const OVERRIDE = 'WINEDLLOVERRIDES=dxgi=n,b';
const game = { appid: 1091500, name: 'Cyberpunk 2077', exe_name: 'Cyberpunk2077.exe', upscalers: ['DLSS', 'FSR 3.1'],
  anticheat: '', nonsteam: false, manual_optiscaler: false, installed: false, verdict: '', detail: '' };
const state = (over = {}) => ({
  version: '2.0.0', home: '/home/deck', assets_ready: true, download: { state: 'idle', done: 0, total: 1, error: '' },
  settings: { session_toast: true, watermark: false, overlay: false }, scanned: true, games: [game], legacy: [],
  optiscaler: 'OptiScaler v10', ...over,
});
const ok = (s, extra = {}) => ({ ok: true, state: s, ...extra });

function panel(running) {
  const options = {}, applied = [];
  const h = harness({
    ui: { Router: { MainRunningApp: running } },
    globals: {
      appStore: { GetAppOverviewByAppID: () => null },
      SteamClient: {
        Apps: {
          RegisterForAppDetails(appid, fn) { Promise.resolve().then(() => fn({ strLaunchOptions: options[appid] ?? '' })); return { unregister() {} }; },
          SetAppLaunchOptions(appid, value) { applied.push([appid, value]); options[appid] = value; },
        },
        GameSessions: { RegisterForAppLifetimeNotifications() { return { unregister() {} }; } },
      },
    },
  });
  return Object.assign(h, { applied, options });
}
const strings = tree => all(tree).flatMap(n => [n.props?.label, typeof n.props?.description === 'string' ? n.props.description : null,
  ...[].concat(n.props?.children ?? []).filter(c => typeof c === 'string' || typeof c === 'number')]).filter(v => v !== undefined && v !== null).join(' | ');
const dialogButton = (tree, label) => all(tree).find(n => n.type === 'DialogButton' && [].concat(n.props.children).join('').includes(label));
async function open(h, s = state()) { h.render(); h.respond('get_state', ok(s)); await settle(); return h.render(); }

test('without OptiScaler and FSR 4 the setup card downloads them', async () => {
  const h = panel(undefined);
  const tree = await open(h, state({ assets_ready: false }));
  assert.match(strings(tree), /Get OptiScaler and FSR 4/);
  dialogButton(tree, 'Accept and download').props.onClick();
  await settle();
  assert.ok(h.calls.some(c => c.name === 'download_assets'));
});

test('with no game running the card says so', async () => {
  const tree = await open(panel(undefined));
  assert.match(strings(tree), /No game running/);
  assert.ok(!dialogButton(tree, 'Install FSR 4.1 Lite'));
});

test('a running game installs with one button and its launch option is saved', async () => {
  const h = panel({ appid: '1091500', display_name: 'Cyberpunk 2077' });
  let tree = await open(h);
  assert.match(strings(tree), /DLSS/);
  dialogButton(tree, 'Install FSR 4.1 Lite').props.onClick();
  await settle();
  h.respond('enable_game', ok(state({ games: [{ ...game, installed: true, verdict: 'unplayed', proxy: 'dxgi.dll' }] }),
    { launch_options: `${OVERRIDE} %command%` }));
  await settle(); await settle();
  assert.deepEqual(h.calls.find(c => c.name === 'enable_game').args, [1091500, '']);
  assert.deepEqual(h.applied.at(-1), [1091500, `${OVERRIDE} %command%`]);
  tree = h.render();
  assert.ok(dialogButton(tree, 'Uninstall FSR 4.1 Lite'));
  assert.ok(dialogButton(tree, 'Check setup'));
});

test('the running game shows its live status: Restart the game, then Active', async () => {
  const h = panel({ appid: '1091500', display_name: 'Cyberpunk 2077' });
  await open(h, state({ games: [{ ...game, installed: true, verdict: 'unplayed', proxy: 'dxgi.dll' }] }));
  // the first check (before the games arrived) is superseded by the one made with them: answer both
  for (const c of h.calls.filter(c => c.name === 'live_status' && !c.settled))
    h.respond('live_status', { ok: true, status: 'restart', detail: 'Set up while the game was running. Restart the game.' });
  await settle();
  let tree = h.render();
  const pill = t => all(t).filter(n => n.type === 'div' && /sml-live/.test(n.props?.className ?? '')).map(n => [].concat(n.props.children).filter(c => typeof c === 'string').join(''));
  assert.deepEqual(pill(tree), ['Restart the game']);
  assert.match(strings(tree), /Restart the game\./);
});

test('a newer version on GitHub shows on the main page, not only in About', async () => {
  const h = panel(undefined);
  await open(h);
  assert.ok(h.calls.some(c => c.name === 'check_for_updates'), 'checked once when the menu opened');
  h.respond('check_for_updates', { ok: true, current_version: '2.2.0', latest_version: '2.3.0', update_available: true, download_available: true });
  await settle();
  const tree = h.render();
  assert.ok(dialogButton(tree, 'Update to 2.3.0'), strings(tree));
});

test('a game with anti-cheat gets no install button', async () => {
  const tree = await open(panel({ appid: '1091500', display_name: 'x' }), state({ games: [{ ...game, anticheat: 'BattlEye' }] }));
  assert.ok(!dialogButton(tree, 'Install FSR 4.1 Lite'));
  assert.match(strings(tree), /BattlEye found\. Injecting OptiScaler could get your account banned, so installs are blocked\./);
  const pills = all(tree).filter(n => n.type === 'div' && /sml-live/.test(n.props?.className ?? '')).map(n => [].concat(n.props.children).filter(c => typeof c === 'string').join(''));
  assert.deepEqual(pills, ['Blocked']);
});

test('games show what their last session showed', async () => {
  const h = panel(undefined);
  let tree = await open(h, state({ games: [{ ...game, installed: true, verdict: 'lite' }, { ...game, appid: 2, name: 'B', installed: true, verdict: 'none' }] }));
  all(tree).filter(n => n.type === 'Field' && n.props.onActivate)[0].props.onActivate();
  tree = h.render();
  const chips = all(tree).filter(n => n.type === 'span' && /sml-badge/.test(n.props?.className ?? '')).map(n => [].concat(n.props.children).join(''));
  assert.ok(chips.includes('Active') && chips.includes('Needs fix'), chips.join(','));
});

test('Check setup explains the setup in plain words', () => {
  const ts = require('typescript'), fs = require('node:fs'), vm = require('node:vm');
  const src = fs.readFileSync(require('node:path').join(__dirname, '../src/check.tsx'), 'utf8');
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(js, { module: mod, exports: mod.exports, require: () => ({}) });
  const { checks } = mod.exports;
  const d = { name: 'X', installed: true, exe_dir: '/g', exe_name: 'x.exe', proxy: 'dxgi.dll', files_ok: true, missing: [],
    upscalers: ['DLSS'], anticheat: '', proton: 'Proton Experimental', verdict: 'lite', detail: '', log_lines: [] };
  const titles = (c) => c.map(x => x.title);
  assert.ok(titles(checks(d, `${OVERRIDE} %command%`)).includes('FSR 4.1 Lite ran'));
  assert.ok(titles(checks(d, '%command%')).includes('Launch option missing'));
  assert.ok(titles(checks({ ...d, files_ok: false }, OVERRIDE)).includes('Files missing'));
  assert.ok(titles(checks({ ...d, verdict: 'none' }, OVERRIDE)).includes("OptiScaler didn't load"));
});

test('when OptiScaler did not load, the next loader name is saved and the player is told', async () => {
  const steam = {}, applied = [];
  const h = harness({
    globals: {
      appStore: { GetAppOverviewByAppID: () => null },
      SteamClient: {
        Apps: { RegisterForAppDetails(id, fn) { Promise.resolve().then(() => fn({ strLaunchOptions: applied.at(-1)?.[1] ?? `${OVERRIDE} %command%` })); return { unregister() {} }; },
          SetAppLaunchOptions(id, v) { applied.push([id, v]); } },
        GameSessions: { RegisterForAppLifetimeNotifications(fn) { steam.lifetime = fn; return { unregister() {} }; } },
      },
    },
  });
  h.exports.default();
  steam.lifetime({ unAppID: 9, bRunning: false });
  await settle(); await settle();
  h.respond('session_ended', { ok: true, managed: true, verdict: 'none', retry: 'winmm.dll', detail: 'Now set up as winmm.dll: play once more.',
    launch_options: 'WINEDLLOVERRIDES=winmm=n,b %command%' });
  for (let i = 0; i < 4; i++) await settle();
  assert.deepEqual(applied.at(-1), [9, 'WINEDLLOVERRIDES=winmm=n,b %command%']);
  assert.ok(h.toasts.some(t => /one more try/.test(t.title)));
});

test('an update is handed to Decky\'s own installer with its checksum, and refused without one', async () => {
  const ts = require('typescript'), fs = require('node:fs'), vm = require('node:vm');
  const src = fs.readFileSync(require('node:path').join(__dirname, '../src/installer.ts'), 'utf8');
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const calls = [];
  const window = { DeckyBackend: { call: async (...a) => { calls.push(a); } } };
  const mod = { exports: {} };
  vm.runInNewContext(js, { module: mod, exports: mod.exports, window });
  const { installUpdate, canInstallUpdates } = mod.exports;
  assert.equal(canInstallUpdates(), true);
  const sha = 'a'.repeat(64);
  assert.equal(await installUpdate('/home/deck/Downloads/FSR4Lite-1.8.1.zip', '1.8.1', sha), true);
  assert.deepEqual(calls[0], ['utilities/install_plugin', 'file:///home/deck/Downloads/FSR4Lite-1.8.1.zip', 'FSR 4.1 Lite', '1.8.1', sha, 2]);
  assert.equal(await installUpdate('/x.zip', '1.8.1', 'not-a-hash'), false);
  window.DeckyBackend.call = async () => { throw new Error('no route'); };
  assert.equal(await installUpdate('/x.zip', '1.8.1', sha), false, 'a refusal falls back to the manual steps');
});
