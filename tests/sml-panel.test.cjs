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

test('a game without upscaler files installs from Now playing but stays out of the library list', async () => {
  const pbz = { ...game, appid: 2005010, name: 'Phantom Blade Zero', exe_name: 'PBZ-Win64-Shipping.exe', upscalers: [],
    tip: 'No upscaler files found. Many games build FSR 2 or 3 into the game itself, so the plugin tells OptiScaler to search for it.' };
  const h = panel({ appid: '2005010', display_name: 'Phantom Blade Zero' });
  const tree = await open(h, state({ games: [game, pbz] }));
  const text = strings(tree);
  assert.match(text, /No upscaler files found/);
  assert.ok(dialogButton(tree, 'Install FSR 4.1 Lite'));
  assert.ok(!/Steam Machine heroes|librarycache/.test(JSON.stringify(all(tree).map(n => n.props?.src ?? ''))), 'no artwork');
  // the one compatible game (Cyberpunk) is behind "Show 1 more", and Phantom Blade Zero isn't in the list at all
  const more = all(tree).find(n => n.type === 'Field' && /Show 1 more compatible game$/.test(String(n.props.label)));
  assert.ok(more);
  more.props.onActivate();
  const rows = all(h.render()).filter(n => (n.type === 'ToggleField' || n.type === 'Field') && /sml-gamerow/.test(JSON.stringify(n.props.label)))
    .map(n => JSON.stringify(n.props.label));
  assert.ok(rows.some(r => r.includes('Cyberpunk 2077')) && !rows.some(r => r.includes('Phantom Blade Zero')), rows.join());
});

test('nothing in the panel loads game artwork', () => {
  const src = require('node:fs').readFileSync(require('node:path').join(__dirname, '../src/panel.tsx'), 'utf8');
  assert.ok(!/heroImage|capsuleImage|<img/.test(src));
});

test('the Now playing card shows what the OptiScaler community found', async () => {
  const h = panel({ appid: '1091500', display_name: 'Cyberpunk 2077' });
  let tree = await open(h, state({ games: [{ ...game, compat: 'Works with: DLSS, FSR3, FSR3.1/4, XeSS' }] }));
  assert.match(strings(tree), /Works with: DLSS, FSR3, FSR3\.1\/4, XeSS/);
  tree = await open(panel({ appid: '1091500', display_name: 'Cyberpunk 2077' }),
    state({ games: [{ ...game, compat: 'OptiScaler community: not working in this game.' }] }));
  assert.ok(all(tree).some(n => n.type === 'div' && /sml-note bad/.test(n.props?.className ?? '') &&
    [].concat(n.props.children).join('').includes('not working')));
});

test('a refused install shows the backend\'s reason, not "Unknown error"', async () => {
  const h = panel({ appid: '1091500', display_name: 'Cyberpunk 2077' });
  let tree = await open(h);
  dialogButton(tree, 'Install FSR 4.1 Lite').props.onClick();
  await settle();
  const why = 'The game is still starting. Wait until you\'re in its menu, then press Install again.';
  h.respond('enable_game', { ok: false, error: why, state: state() });
  await settle(); await settle();
  const text = strings(h.render());
  assert.ok(text.includes(why), text.slice(-400));
  assert.ok(!/Unknown error/.test(text));
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

test('set-up games are always listed under Your games, with what their last session showed', async () => {
  const h = panel(undefined);
  const tree = await open(h, state({ games: [{ ...game, installed: true, verdict: 'lite' }, { ...game, appid: 2, name: 'B', installed: true, verdict: 'none' }] }));
  assert.ok(all(tree).some(n => n.type === 'Field' && JSON.stringify(n.props.label ?? '').includes('Your games')));
  assert.ok(!all(tree).some(n => n.type === 'Field' && /more compatible/.test(String(n.props.label))), 'nothing else to show');
  const chips = all(tree).filter(n => n.type === 'span' && /sml-badge/.test(n.props?.className ?? '')).map(n => [].concat(n.props.children).join(''));
  assert.ok(chips.includes('Active') && chips.includes('Needs fix'), chips.join(','));
});

test('Your games opens and closes from its heading', async () => {
  const h = panel(undefined);
  let tree = await open(h, state({ games: [{ ...game, installed: true, verdict: 'lite' }] }));
  const heading = t => all(t).find(n => n.type === 'Field' && n.props.className === 'sml-hdrrow');
  const listed = t => all(t).some(n => n.type === 'ToggleField' && JSON.stringify(n.props.label).includes('Cyberpunk 2077'));
  assert.match(JSON.stringify(heading(tree).props.label), /Your games.*\[1," set up"," · 1 active"\]/);
  assert.ok(listed(tree), 'open at first');
  heading(tree).props.onActivate();
  tree = h.render();
  assert.ok(!listed(tree), 'closed after pressing the heading');
  assert.match(String(heading(tree).props.description), /1 compatible game\. Press to show\./);
  heading(tree).props.onActivate();
  assert.ok(listed(h.render()), 'open again');
});

test('games are set up from Now playing only; the list can only turn a game off', async () => {
  const h = panel(undefined);
  let tree = await open(h, state({ games: [{ ...game, installed: true, verdict: 'lite' }, { ...game, appid: 2, name: 'Other Game' }] }));
  assert.ok(!dialogButton(tree, 'Install in all') && !all(tree).some(n => /Install in all/.test(String(n.props?.children ?? ''))));
  all(tree).find(n => n.type === 'Field' && /Show 1 more compatible game/.test(String(n.props.label))).props.onActivate();
  tree = h.render();
  const other = all(tree).find(n => JSON.stringify(n.props?.label ?? '').includes('Other Game'));
  assert.equal(other.type, 'Field', 'no switch for a game that is not set up');
  assert.match(JSON.stringify(other.props.description), /Start the game, then press Install on Now playing\./);
  const setUp = all(tree).find(n => n.type === 'ToggleField' && JSON.stringify(n.props.label).includes('Cyberpunk 2077'));
  setUp.props.onChange(true);  // "on" does nothing
  await settle();
  assert.ok(!h.calls.some(c => c.name === 'enable_game'));
  setUp.props.onChange(false);  // "off" uninstalls
  await settle(); await settle();
  assert.ok(h.calls.some(c => c.name === 'disable_game'));
});

test('opening the menu goes back to the top: first control focused, every scrolled container at 0', () => {
  const ts = require('typescript'), fs = require('node:fs'), vm = require('node:vm');
  const src = fs.readFileSync(require('node:path').join(__dirname, '../src/steamx.ts'), 'utf8');
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(js, { module: mod, exports: mod.exports });
  const focused = [];
  const button = { focus: o => focused.push(o) };
  const qam = { scrollTop: 640, parentElement: null };
  const panel = { scrollTop: 0, parentElement: qam };
  const root = { scrollTop: 0, parentElement: panel, querySelector: () => button };
  mod.exports.toTop(root);
  assert.equal(JSON.stringify(focused), '[{"preventScroll":true}]');
  assert.equal(qam.scrollTop, 0);
  mod.exports.toTop(null);  // nothing to do, no throw
  mod.exports.toTop({ parentElement: null, querySelector: () => { throw new Error('old engine'); } });
});

test('the panel resets to its main page when the menu opens', () => {
  const src = require('node:fs').readFileSync(require('node:path').join(__dirname, '../src/panel.tsx'), 'utf8');
  assert.match(src, /if \(!visible\) return;\s*setPage\(null\);[\s\S]{0,120}toTop\(rootRef\.current\)/);
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

test('a late start gets one note why, then a precise notification when Lite runs', async () => {
  const steam = {};
  const h = harness({
    globals: {
      appStore: { GetAppOverviewByAppID: () => null },
      SteamClient: {
        Apps: { RegisterForAppDetails(id, fn) { Promise.resolve().then(() => fn({ strLaunchOptions: '' })); return { unregister() {} }; },
          SetAppLaunchOptions() {} },
        GameSessions: { RegisterForAppLifetimeNotifications(fn) { steam.lifetime = fn; return { unregister() {} }; } },
      },
    },
  });
  h.exports.default();
  steam.lifetime({ unAppID: 870780, bRunning: true });
  await settle();
  h.respond('session_started', { ok: true, managed: true });
  await settle();
  h.respond('get_state', ok(state({ games: [{ ...game, appid: 870780, name: 'Control', installed: true }] })));
  await settle();
  const hint = 'OptiScaler loaded, but the game\'s upscaler didn\'t start. Pick an upscaler in its settings.';
  for (let i = 0; i < 2; i++) {  // the same hint twice: one notification
    h.fire(); await settle();
    h.respond('session_check', { ok: true, lite: false, done: false, hint }); await settle();
  }
  h.fire(); await settle();
  h.respond('session_check', { ok: true, lite: true, done: false, minutes: 3,
    summary: 'DLSS → FSR 4.1.2 Lite, 1280×720 → 3840×2160 (Ultra Performance)' });
  await settle();
  const notes = h.toasts.map(t => `${t.title} | ${t.body}`);
  assert.deepEqual(notes, [
    `FSR 4.1 Lite not active yet in Control | ${hint}`,
    'FSR 4.1 Lite active in Control (after 3 min) | DLSS → FSR 4.1.2 Lite, 1280×720 → 3840×2160 (Ultra Performance)',
  ]);
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
