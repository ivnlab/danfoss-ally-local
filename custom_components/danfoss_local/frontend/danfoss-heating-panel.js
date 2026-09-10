/* Danfoss Icon2 (Local) - "Тёплый пол" sidebar panel for Home Assistant.
 *
 * A single vanilla web component (no framework) that renders the designer's
 * high-fidelity mockup (design/handoff) on top of the live `hass` object:
 * summary of all rooms, a room page with target/quick modes/setpoints and a
 * drag-editable weekly schedule, and the home-level holiday flow. Colors of
 * the page chrome come from the HA theme; the accent/warm palette follows the
 * design tokens for light and dark.
 */

const DAY = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const DAY_LONG = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"];
const DAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
const MODE_LABEL = { home: "Дома", away: "Вне дома", pause: "Пауза", holiday: "Отпуск", holiday_sat: "Отпуск дома", manual: "Ручной" };
const SCHED_TO_PRESET = { at_home: "home", leaving_home: "away", holiday: "holiday", holiday_sat: "holiday" };
const STD_WD = [[360, 480], [960, 1350]];
const STD_WE = [[360, 1350]];

const pad2 = (n) => String(n).padStart(2, "0");
const m2t = (m) => `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}`;
const t2m = (s) => { const [h, m] = String(s).split(":").map(Number); return h * 60 + m; };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = null) => { const n = parseFloat(v); return Number.isFinite(n) ? n : d; };
const f1 = (v) => (v == null ? "–" : Number(v).toFixed(1));
const clone = (p) => p.map((d) => d.map((w) => w.slice()));
const localISO = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
const fmtDT = (v) => { if (!v) return "–"; const d = new Date(v); if (isNaN(d)) return v; const s = `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}`; return String(v).length > 10 ? `${s} ${pad2(d.getHours())}:${pad2(d.getMinutes())}` : s; };

const STYLE = `
  :host { display:block; }
  .hp{--bg:var(--primary-background-color,#f4f5f7);--card:var(--card-background-color,#fff);--ink:var(--primary-text-color,#2a2d32);--muted:var(--secondary-text-color,#73787f);--line:var(--divider-color,#d3d7dc);
       --soft:#e4e7eb;--acc:#8fa5bd;--acc-soft:#dce5ee;--acc-ink:#4c637d;--warm:#dfa075;--warm-soft:#f6e3d7;--warm-ink:#9c5f33;--ok:#3f9163;--shadow:var(--ha-card-box-shadow,0 1px 3px rgba(30,35,45,.10),0 1px 2px rgba(30,35,45,.06));
       min-height:100vh;background:var(--bg);color:var(--ink);font-family:Roboto,system-ui,sans-serif;font-size:15px;line-height:1.45}
  .hp[data-theme="dark"]{--soft:#2c3038;--acc:#8fa5bd;--acc-soft:#2e3947;--acc-ink:#b7c7da;--warm:#d9976f;--warm-soft:#3d3026;--warm-ink:#e5b491;--ok:#8ecfa4;--shadow:0 1px 3px rgba(0,0,0,.4)}
  .hp *{box-sizing:border-box}
  .hp button{font-family:inherit;cursor:pointer}
  .hp button:disabled{cursor:not-allowed}
  .hp :focus-visible{outline:2px solid var(--acc-ink);outline-offset:2px}
  .hp input,.hp select{font-family:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:15px}
  .hp input[type="checkbox"]{width:22px;height:22px;accent-color:var(--acc-ink);padding:0;margin:0}
  .wrap{max-width:1280px;margin:0 auto;padding:16px 16px 32px;display:flex;flex-direction:column;gap:14px}
  header{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:2px 4px 0}
  .title{font-size:22px;font-weight:500}.sub{color:var(--muted);font-size:13.5px}
  .banner{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:14px 18px;background:var(--acc-soft);border:1px solid var(--acc);border-radius:14px}
  .banner b{font-size:14.5px;color:var(--acc-ink)}
  .cols{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}
  .side{width:232px;flex:none}.side-list{display:flex;flex-direction:column;gap:4px}
  .nav{display:flex;align-items:center;gap:8px;padding:12px 14px;border-radius:12px;cursor:pointer;font-weight:500;min-height:20px;background:transparent}
  .nav:hover{background:var(--card)}.nav.on{background:var(--card);box-shadow:var(--shadow)}
  .nav .nm{flex:1;min-width:0;white-space:nowrap}.nav .dot{width:9px;height:9px;border-radius:50%;background:var(--warm)}.nav .t{font-size:14px;font-variant-numeric:tabular-nums;color:var(--muted)}
  .sep{height:1px;background:var(--line);margin:6px 4px}
  .main{flex:1;min-width:min(100%,340px);display:flex;flex-direction:column;gap:14px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
  .card{background:var(--card);border-radius:14px;box-shadow:var(--shadow)}
  .rc{display:flex;flex-direction:column;gap:8px;padding:14px 16px;cursor:pointer;border:2px solid transparent}
  .rc:hover{border-color:var(--acc)}
  .row{display:flex;align-items:center;gap:8px}
  .big{font-size:42px;font-weight:400;font-variant-numeric:tabular-nums;line-height:1}
  .muted{color:var(--muted)}
  .pill{display:flex;align-items:center;background:var(--soft);border-radius:24px;padding:3px}
  .rb{width:44px;height:44px;border:none;background:var(--card);color:var(--ink);font-size:20px;padding:0;border-radius:50%;line-height:44px}
  .rb:hover{background:var(--acc-soft)}
  .pill .v{min-width:56px;text-align:center;font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
  .chipbtn{border:none;font-size:12.5px;font-weight:500;background:var(--soft);color:var(--ink);padding:7px 11px;border-radius:14px}
  .chipbtn:hover{background:var(--acc-soft)}
  .menu{position:absolute;top:calc(100% + 4px);left:0;z-index:20;background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:4px;min-width:140px;display:flex;flex-direction:column}
  .menu button{border:none;background:transparent;color:var(--ink);font-size:13.5px;font-weight:500;text-align:left;padding:10px 12px;border-radius:9px}
  .menu button:hover,.menu button.on{background:var(--acc-soft)}
  .badge{font-size:11.5px;font-weight:500;padding:3px 9px;border-radius:9px}
  .badge.dev{background:var(--warm-soft);color:var(--warm-ink)}.badge.ext,.badge.vac{background:var(--acc-soft);color:var(--acc-ink)}
  .warn{font-size:11px;font-weight:500;color:var(--warm-ink);background:var(--warm-soft);padding:2px 8px;border-radius:9px}
  .lockb{border:none;background:transparent;padding:6px;margin:-6px 0;display:flex;align-items:center}
  .lockb:hover{opacity:.7}
  .obtn{border:1px solid var(--line);background:transparent;color:var(--ink);padding:10px 16px;font-size:13.5px;font-weight:500;border-radius:20px}
  .obtn:hover{background:var(--soft)}
  .obtn.acc{border-color:var(--acc-ink);color:var(--acc-ink)}.obtn.acc:hover{background:var(--card)}
  .pbtn{border:none;background:var(--acc-ink);color:var(--card);padding:10px 16px;font-size:13.5px;font-weight:500;border-radius:20px}
  .pbtn:hover{opacity:.9}.pbtn.lg{padding:12px 20px;font-size:14px;border-radius:22px}
  .tbtn{border:none;background:transparent;color:var(--acc-ink);font-size:13px;font-weight:500;text-decoration:underline;padding:8px 0}
  .seg{display:flex;background:var(--soft);border-radius:22px;padding:3px;width:fit-content}
  .seg button{border:none;padding:10px 16px;font-size:14px;font-weight:500;background:transparent;color:var(--ink);min-height:42px;border-radius:19px;white-space:nowrap}
  .seg button.on{background:var(--card)}.seg button:disabled{opacity:.45}
  .lbl{font-size:12px;color:var(--muted);font-weight:500;margin-bottom:8px}
  .sec{padding:16px 20px;border-bottom:1px solid var(--soft)}
  .stat{font-size:40px;font-weight:400;font-variant-numeric:tabular-nums;line-height:1.05}.stat-l{font-size:12px;color:var(--muted)}
  .tchip{display:flex;align-items:baseline;gap:8px;background:var(--soft);border-radius:28px;padding:3px 3px 3px 16px}
  .tchip .rb{align-self:center}
  .qk{border:1px solid var(--line);padding:11px 16px;font-size:14px;font-weight:500;background:transparent;color:var(--ink);min-height:44px;border-radius:22px}
  .qk:hover{border-color:var(--acc-ink)}.qk.on{background:var(--acc-ink);color:var(--card)}.qk:disabled{opacity:.45}
  .link{border:none;background:transparent;color:var(--acc-ink);font-size:14px;font-weight:500;text-decoration:underline;padding:11px 6px}
  .sp{display:flex;align-items:center;gap:4px;background:var(--soft);border-radius:24px;padding:3px 3px 3px 14px}
  .sp .rb{width:42px;height:42px;font-size:19px;line-height:42px}
  .bar{flex:1;position:relative;height:40px;border-radius:8px;background:var(--soft);background-image:repeating-linear-gradient(to right,var(--line) 0 1px,transparent 1px calc(100%/8))}
  .win{position:absolute;top:3px;bottom:3px;cursor:pointer;border-radius:6px;border:2px solid transparent;background:var(--acc)}
  .win.off{background:var(--line)}.win.ed{border-color:var(--acc-ink)}
  .hdl{position:absolute;top:0;bottom:0;width:16px;cursor:ew-resize;touch-action:none;display:flex;align-items:center;justify-content:center}
  .hdl.l{left:-6px}.hdl.r{right:-6px}.hdl i{width:3px;height:16px;border-radius:2px;background:var(--acc-ink);opacity:.75}
  .nowl{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--warm);pointer-events:none}
  .addb{width:40px;height:40px;border:1px dashed var(--line);background:transparent;color:var(--muted);font-size:18px;line-height:1;padding:0;border-radius:10px}
  .addb:hover{border-color:var(--acc-ink);color:var(--acc-ink)}
  .editor{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:12px;padding:14px;background:var(--soft);border-radius:12px}
  .toast{position:fixed;right:20px;bottom:20px;background:var(--acc-ink);color:var(--card);padding:10px 16px;border-radius:12px;box-shadow:var(--shadow);opacity:0;transition:opacity .2s;pointer-events:none;z-index:50;font-size:14px}
  .toast.show{opacity:1}
  @media(max-width:760px){.side{width:100%}.side-list{flex-direction:row;overflow-x:auto;padding-bottom:6px}.side-list>*{flex:none}}
`;

class DanfossHeatingPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._s = { view: -1, rare: false, edit: null, copied: false, menu: null, vacOpen: false,
      vf: { kind: "away", when: "now", start: "", end: "", rooms: {}, temp: 17 } };
    this._prog = {};      // roomId -> local program [[[s,e],...] x7] while editing
    this._dirty = {};     // roomId -> true while local edits not yet saved
    this._saveT = {};     // roomId -> debounce timer
    this._sig = "";
    this._rooms = [];
    this._dragged = false;
    this._onDocClick = (e) => { if (this._s.menu !== null && !e.composedPath().some((n) => n.classList && n.classList.contains("mode-wrap"))) { this._s.menu = null; this._render(); } };
  }

  connectedCallback() { document.addEventListener("click", this._onDocClick); this._tick = setInterval(() => this._render(), 60000); }
  disconnectedCallback() { document.removeEventListener("click", this._onDocClick); clearInterval(this._tick); }

  set hass(hass) {
    this._hass = hass;
    this._rooms = this._discover(hass);
    const sig = this._rooms.map((r) => r.ids.map((id) => { const st = hass.states[id]; return st ? st.last_updated : "?"; }).join("|")).join("#") + (hass.themes && hass.themes.darkMode ? "D" : "L");
    if (sig !== this._sig) { this._sig = sig; this._render(); }
  }
  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }

  // -- discovery -----------------------------------------------------------

  _discover(hass) {
    const ents = hass.entities || {};
    const byDev = {};
    for (const [eid, e] of Object.entries(ents)) {
      if (e.platform !== "danfoss_local" || !e.device_id) continue;
      (byDev[e.device_id] = byDev[e.device_id] || {})[eid.split(".")[0] + ":" + (e.translation_key || eid)] = eid;
    }
    const rooms = [];
    for (const [devId, m] of Object.entries(byDev)) {
      const climate = m["climate:thermostat"] || Object.values(m).find((id) => id.startsWith("climate."));
      if (!climate) continue;
      const dev = (hass.devices || {})[devId] || {};
      const area = dev.area_id && (hass.areas || {})[dev.area_id];
      const name = area ? area.name : (dev.name_by_user || dev.name || climate);
      const order = num((dev.name || "").replace(/\D+/g, ""), 99);
      const ids = Object.values(m);
      rooms.push({ devId, name, order, climate, m, ids });
    }
    rooms.sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
    return rooms;
  }

  _st(id) { return id ? this._hass.states[id] : undefined; }
  _num(room, key) { const s = this._st(room.m[key]); return s ? num(s.state) : null; }

  _model(room) {
    const h = this._hass;
    const cl = this._st(room.climate) || { state: "unavailable", attributes: {} };
    const a = cl.attributes || {};
    const sched = this._st(room.m["sensor:schedule"]) || { state: "off", attributes: {} };
    const sa = sched.attributes || {};
    const srcRaw = (this._st(room.m["sensor:setpoint_change_source"]) || {}).state;
    const source = srcRaw === "Manual" ? "device" : srcRaw === "Externally" ? "panel" : "schedule";
    const days = sa.program ? sa.program.days.map((d) => d.map((w) => [w.start, w.end])) : null;
    // A local edit stays on screen until HA echoes the same program back
    // through the schedule sensor (no flicker between save and state update).
    if (this._dirty[room.devId] && days && JSON.stringify(days) === JSON.stringify(this._prog[room.devId])) this._dirty[room.devId] = false;
    const program = this._dirty[room.devId] ? this._prog[room.devId] : (days || [[], [], [], [], [], [], []]);
    return {
      ...room, cl, available: cl.state !== "unavailable",
      air: this._num(room, "sensor:air_temperature") ?? num(a.current_temperature),
      floor: this._num(room, "sensor:floor_temperature"), hum: this._num(room, "sensor:humidity"), bat: this._num(room, "sensor:battery"),
      heating: (this._st(room.m["binary_sensor:thermal_actuator"]) || {}).state === "on",
      fault: (this._st(room.m["binary_sensor:fault"]) || {}).state === "on",
      lock: (this._st(room.m["lock:child_lock"]) || {}).state === "locked",
      preheat: (this._st(room.m["switch:pre_heat"]) || {}).state === "on",
      sp: { home: this._num(room, "number:at_home_setting"), away: this._num(room, "number:leaving_home_setting"), pause: this._num(room, "number:pause_setting"), holiday: this._num(room, "number:holiday_setting") },
      lower: this._num(room, "number:lower_temp") ?? 4, upper: this._num(room, "number:upper_temp") ?? 35,
      preset: a.preset_mode || null, hvac: cl.state, target: num(a.temperature),
      hasProgram: !!sa.program, enabled: sa.enabled !== false && !!sa.program, program,
      schedState: sched.state, nextAt: sa.next_change_at || null, nextMode: sa.next_mode || null,
      holiday: sa.holiday || null, source,
    };
  }

  _untilLabel(iso) {
    if (!iso) return "–";
    const d = new Date(iso), now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const tom = new Date(now); tom.setDate(now.getDate() + 1);
    const hm = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
    if (sameDay) return `сегодня в ${hm}`;
    if (d.toDateString() === tom.toDateString()) return `завтра в ${hm}`;
    return `${DAY_SHORT[(d.getDay() + 6) % 7]} ${hm}`;
  }

  // Effective state, mirroring the mockup's eff(): label, origin, until, target, override flag
  _eff(r) {
    const hol = r.holiday, vacNow = r.schedState === "holiday" || r.schedState === "holiday_sat";
    if (vacNow && hol) {
      const until = "до " + fmtDT(hol.end);
      return hol.kind === "away"
        ? { label: "Отпуск", origin: "vac", until, target: r.target ?? hol.temperature ?? r.sp.holiday, vac: true }
        : { label: "Отпуск дома", origin: "vac", until: "по субботней программе, " + until, target: r.target, vac: true };
    }
    const nc = r.nextAt ? this._untilLabel(r.nextAt) : null;
    const untilB = "до границы расписания (" + (nc || "–") + ")";
    const schedPreset = SCHED_TO_PRESET[r.schedState] || null;
    const manual = r.hvac === "heat" || (r.preset == null && r.hvac !== "unavailable");
    if (manual) return { label: "Ручной", origin: r.source === "device" ? "device" : "panel", until: untilB, target: r.target, ovr: true };
    if (r.enabled && schedPreset && r.preset && r.preset !== schedPreset) {
      return { label: MODE_LABEL[r.preset] || r.preset, origin: r.source === "device" ? "device" : "panel", until: untilB, target: r.target, ovr: true };
    }
    if (!r.enabled) return { label: MODE_LABEL[r.preset] || "–", origin: "schedule", until: r.hasProgram ? "расписание выключено" : "расписания нет", target: r.target };
    const nm = r.nextMode ? (MODE_LABEL[SCHED_TO_PRESET[r.nextMode]] || r.nextMode) : null;
    return { label: MODE_LABEL[r.preset] || "–", origin: "schedule", until: "по расписанию · далее " + (nm ? nm + " - " + nc : "–"), target: r.target };
  }

  // -- actions -------------------------------------------------------------

  async _call(domain, service, data, ok) {
    try { await this._hass.callService(domain, service, data); if (ok) this._toast(ok); }
    catch (e) { this._toast("Ошибка: " + (e && e.message ? e.message : e)); }
  }
  _svc(service, data, ok) { return this._call("danfoss_local", service, data, ok); }

  _bump(r, delta) {
    const e = this._eff(r); if (e.vac || e.target == null) return;
    const nt = Math.min(r.upper, Math.max(r.lower, Math.round((e.target + delta) * 2) / 2));
    this._call("climate", "set_temperature", { entity_id: r.climate, temperature: nt });
  }
  _preset(r, p) { this._call("climate", "set_preset_mode", { entity_id: r.climate, preset_mode: p }); }
  _resume(r) { this._svc("resume_schedule", { device_id: r.devId }, "Возврат к расписанию"); }
  _setpoint(r, key, delta) {
    const map = { home: "number:at_home_setting", away: "number:leaving_home_setting", pause: "number:pause_setting", holiday: "number:holiday_setting" };
    const cur = r.sp[key]; if (cur == null) return;
    const v = Math.min(r.upper, Math.max(r.lower, Math.round((cur + delta) * 2) / 2));
    this._call("number", "set_value", { entity_id: r.m[map[key]], value: v });
  }

  _progOf(r) { if (!this._dirty[r.devId]) { this._prog[r.devId] = clone(r.program); this._dirty[r.devId] = true; } return this._prog[r.devId]; }
  _queueSave(r) {
    clearTimeout(this._saveT[r.devId]);
    this._saveT[r.devId] = setTimeout(async () => {
      const days = this._prog[r.devId].map((d) => [...d].sort((a, b) => a[0] - b[0]).map((w) => ({ start: m2t(w[0]), end: m2t(w[1]) })));
      await this._svc("set_schedule", { device_id: r.devId, program: { days }, enabled: r.hasProgram ? undefined : true }, "Расписание сохранено");
      this._sig = ""; this._render();
    }, 700);
  }

  _toast(msg) { const t = this.shadowRoot.querySelector(".toast"); if (!t) return; t.textContent = msg; t.classList.add("show"); clearTimeout(this._tt); this._tt = setTimeout(() => t.classList.remove("show"), 2500); }

  // -- render --------------------------------------------------------------

  _render() {
    if (!this._hass) return;
    const S = this._s, rooms = this._rooms.map((r) => this._model(r));
    const dark = !!(this._hass.themes && this._hass.themes.darkMode);
    const now = new Date(), nowD = (now.getDay() + 6) % 7, nowMin = now.getHours() * 60 + now.getMinutes();
    const withHol = rooms.filter((r) => r.holiday);
    const activeHol = rooms.filter((r) => r.schedState === "holiday" || r.schedState === "holiday_sat");
    const isRoom = S.view >= 0 && S.view < rooms.length;

    const nav = rooms.map((r, i) => `
      <div class="nav ${S.view === i ? "on" : ""}" data-act="view" data-i="${i}" role="button" tabindex="0">
        <div class="nm">${esc(r.name)}</div>${r.heating ? `<div class="dot" title="Греет"></div>` : ""}<div class="t">${f1(r.air)}°</div>
      </div>`).join("");

    let banner = "";
    if (withHol.length) {
      const h = withHol[0].holiday, active = activeHol.length > 0;
      const what = h.kind === "away" ? `«В отсутствии»${h.temperature != null ? " · " + f1(h.temperature) + "°" : ""}` : "«Отдых дома» · по субботней программе";
      const when = active ? "до " + fmtDT(h.end) : `с ${fmtDT(h.start)} до ${fmtDT(h.end)}`;
      banner = `<div class="banner"><b>${active ? "Отпуск активен" : "Отпуск запланирован"}</b><div style="font-size:14px">${what} · ${when} · ${withHol.length} помещ.</div><div style="flex:1"></div>
        <button class="obtn acc" data-act="vac-edit">Исправить</button><button class="pbtn" data-act="vac-clear">Выйти из режима</button></div>`;
    }

    const body = isRoom ? this._renderRoom(rooms[S.view], rooms, nowD, nowMin) : this._renderSummary(rooms, withHol);

    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="hp" data-theme="${dark ? "dark" : "light"}"><div class="wrap">
        <header><div class="title">Тёплый пол</div><div class="sub">Danfoss Icon2 · ${DAY_LONG[nowD]} ${pad2(now.getHours())}:${pad2(now.getMinutes())}</div></header>
        ${banner}
        <div class="cols">
          <aside class="side"><div class="side-list">
            <div class="nav ${S.view < 0 ? "on" : ""}" data-act="view" data-i="-1" role="button" tabindex="0">Сводка</div>
            <div class="sep"></div>${nav}
          </div></aside>
          <div class="main">${body}</div>
        </div>
      </div><div class="toast"></div></div>`;
    this._bind(rooms);
  }

  _renderSummary(rooms, withHol) {
    const S = this._s;
    const cards = rooms.map((r, i) => {
      const e = this._eff(r);
      const badge = e.origin === "device" ? `<div class="badge dev">изменено на термостате</div>` : e.origin === "panel" && e.ovr ? `<div class="badge ext">изменено извне</div>` : e.origin === "vac" ? `<div class="badge vac">отпуск</div>` : "";
      const opts = [["home", "Дома"], ["away", "Вне дома"], ["pause", "Пауза"], ["holiday", "Выходные"]].map(([k, l]) => `<button data-act="mode-pick" data-i="${i}" data-m="${k}" class="${e.ovr && r.preset === k ? "on" : ""}">${l}</button>`).join("");
      return `<div class="card rc" data-act="open" data-i="${i}" role="button" tabindex="0" ${r.available ? "" : 'style="opacity:.5"'}>
        <div class="row"><div style="font-weight:500;font-size:15px;min-width:0">${esc(r.name)}</div>
          <button class="lockb" data-act="lock" data-i="${i}" title="${r.lock ? "Замок от детей включён - нажмите, чтобы выключить" : "Замок от детей выключен - нажмите, чтобы включить"}" style="color:${r.lock ? "var(--ok)" : "var(--muted)"}">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="${r.lock ? "M8 11V7a4 4 0 0 1 8 0v4" : "M8 11V7a4 4 0 0 1 7.5-2"}"></path></svg></button>
          <div style="flex:1"></div>${r.fault ? `<div class="warn">неиспр.</div>` : ""}</div>
        <div class="row" style="gap:12px;flex-wrap:wrap"><div class="big">${f1(r.air)}°</div>
          <div class="muted" style="font-size:15px">пол ${f1(r.floor)}°<br>влажн. ${r.hum == null ? "–" : Math.round(r.hum)}%</div><div style="flex:1"></div>
          <div class="pill"><button class="rb" data-act="dec" data-i="${i}" aria-label="Убавить" ${e.vac ? "disabled" : ""}>−</button><div class="v" style="color:${r.heating ? "var(--warm-ink)" : "var(--ink)"}">${f1(e.target)}°</div><button class="rb" data-act="inc" data-i="${i}" aria-label="Прибавить" ${e.vac ? "disabled" : ""}>+</button></div></div>
        <div style="display:flex;flex-direction:column;align-items:flex-start;gap:6px;min-height:22px">
          <div class="mode-wrap" style="position:relative;flex:none"><button class="chipbtn" data-act="mode-menu" data-i="${i}">${esc(e.label)} ▾</button>${S.menu === i ? `<div class="menu">${opts}</div>` : ""}</div>${badge}</div>
        <div class="row"><div class="muted" style="font-size:12.5px;flex:1">термоголовка <span style="font-weight:700;color:${r.heating ? "var(--warm-ink)" : "var(--ink)"}">${r.heating ? "открыта" : "закрыта"}</span></div>
          <div title="${r.heating ? "Запрос тепла активен - термостат греет" : "Запроса тепла нет"}" style="color:${r.heating ? "var(--warm-ink)" : "var(--line)"};display:flex"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg></div></div>
      </div>`;
    }).join("");

    const vf = S.vf;
    const satMissing = rooms.filter((r) => vf.rooms[r.devId] !== false && r.program[5].length === 0).map((r) => r.name);
    const blocked = satMissing.length > 0;
    const startDisabled = !vf.end || (vf.when === "plan" && !vf.start) || !rooms.some((r) => vf.rooms[r.devId] !== false);
    const form = S.vacOpen ? `
      <div style="display:flex;gap:28px;flex-wrap:wrap;margin-top:16px">
        <div style="flex:1 1 220px"><div class="lbl">1 · Вид отпуска</div>
          <div class="seg"><button data-act="vf-kind" data-v="away" class="${vf.kind === "away" ? "on" : ""}">В отсутствии</button><button data-act="vf-kind" data-v="at_home" class="${vf.kind === "at_home" ? "on" : ""}" ${blocked ? `disabled title="Нужна суббота в расписании: ${esc(satMissing.join(", "))}"` : ""}>Отдых дома</button></div>
          <div class="muted" style="font-size:12.5px;margin-top:8px;max-width:300px">${vf.kind === "away" ? "Все выбранные термостаты держат одну пониженную температуру." : "Каждый день отпуска - по субботней программе. Суббота обязательна и не может быть стёрта, пока отпуск запланирован."}</div></div>
        <div style="flex:1 1 240px"><div class="lbl">2 · Когда</div>
          <div class="seg" style="margin-bottom:10px"><button data-act="vf-when" data-v="now" class="${vf.when === "now" ? "on" : ""}">Сейчас</button><button data-act="vf-when" data-v="plan" class="${vf.when === "plan" ? "on" : ""}">План</button></div>
          <div style="display:flex;flex-direction:column;gap:8px;max-width:280px">
            ${vf.when === "plan" ? `<label class="muted" style="font-size:12.5px">Начало<br><input type="${vf.kind === "at_home" ? "date" : "datetime-local"}" step="1800" value="${esc(vf.start)}" data-act="vf-start" style="width:100%;margin-top:3px"></label>` : ""}
            <label class="muted" style="font-size:12.5px">Конец<br><input type="${vf.kind === "at_home" ? "date" : "datetime-local"}" step="1800" value="${esc(vf.end)}" data-act="vf-end" style="width:100%;margin-top:3px"></label></div></div>
        <div style="flex:1 1 200px"><div class="lbl">3 · Где</div><div style="display:flex;flex-direction:column;gap:2px">
          ${rooms.map((r) => `<label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:14.5px;min-height:38px"><input type="checkbox" data-act="vf-room" data-d="${r.devId}" ${vf.rooms[r.devId] !== false ? "checked" : ""}>${esc(r.name)}</label>`).join("")}</div></div>
        ${vf.kind === "away" ? `<div style="flex:0 1 200px"><div class="lbl">4 · До какой t°</div><div class="pill" style="width:fit-content"><button class="rb" data-act="vf-dec">−</button><div style="padding:6px 14px;font-size:18px;font-weight:700;font-variant-numeric:tabular-nums">${f1(vf.temp)}°</div><button class="rb" data-act="vf-inc">+</button></div></div>` : ""}
      </div>
      <div style="display:flex;gap:10px;margin-top:18px;align-items:center;flex-wrap:wrap">
        <button class="pbtn lg" data-act="vf-go" ${startDisabled ? 'disabled style="opacity:.45"' : ""}>${withHol.length ? "Сохранить изменения" : vf.when === "now" ? "Начать отпуск сейчас" : "Запланировать"}</button>
        <button data-act="vf-cancel" style="border:none;background:transparent;color:var(--muted);font-size:13.5px;font-weight:500;padding:12px 8px">Отмена</button>
        <div class="muted" style="font-size:12.5px">${startDisabled ? "Укажите даты и хотя бы одно помещение" : ""}</div></div>` : "";

    return `<section class="grid">${cards}</section>
      <section class="card" style="padding:16px 18px"><div class="row" style="gap:14px;flex-wrap:wrap"><div style="font-size:16px;font-weight:500">Отпуск</div><div class="muted" style="font-size:13px">действует на весь дом, поверх расписаний</div><div style="flex:1"></div>
        ${S.vacOpen ? "" : `<button class="obtn" data-act="vac-open">${withHol.length ? "Исправить параметры" : "Запланировать отпуск"}</button>`}</div>${form}</section>`;
  }

  _renderRoom(r, rooms, nowD, nowMin) {
    const S = this._s, e = this._eff(r);
    const originTxt = e.origin === "device" ? "изменено на самом термостате" : e.origin === "panel" && e.ovr ? "изменено извне (страница / приложение)" : e.origin === "vac" ? "отпуск" : "по расписанию";
    const vacd = !!e.vac;
    const quick = [["away", "Сейчас ухожу из дома"], ["pause", "Пауза"], ["home", "Дома сегодня днём"]].map(([m, l]) => {
      const act = e.ovr && r.preset === m;
      return `<button class="qk ${act ? "on" : ""}" data-act="quick" data-m="${m}" data-on="${act ? 1 : 0}" ${vacd ? 'disabled' : ""}>${l}</button>`;
    }).join("");
    const sps = [["home", "Дома"], ["away", "Вне дома"], ["pause", "Пауза"], ["holiday", "Отпуск"]].map(([k, l]) => `
      <div class="sp"><div style="min-width:74px"><div class="muted" style="font-size:11.5px">${l}</div><div style="font-size:16px;font-weight:700;font-variant-numeric:tabular-nums">${f1(r.sp[k])}°</div></div>
        <button class="rb" data-act="sp-dec" data-k="${k}" aria-label="Уменьшить">−</button><button class="rb" data-act="sp-inc" data-k="${k}" aria-label="Увеличить">+</button></div>`).join("");

    const days = DAY.map((label, di) => {
      const wins = r.program[di].map((w, wi) => `
        <div class="win ${r.enabled ? "" : "off"} ${S.edit && S.edit.d === di && S.edit.i === wi ? "ed" : ""}" data-act="win" data-d="${di}" data-i="${wi}" role="button" title="Дома ${m2t(w[0])} - ${m2t(w[1])}" style="left:${(w[0] / 1440 * 100).toFixed(2)}%;width:${((w[1] - w[0]) / 1440 * 100).toFixed(2)}%">
          <div class="hdl l" data-drag="s" data-d="${di}" data-i="${wi}"><i></i></div><div class="hdl r" data-drag="e" data-d="${di}" data-i="${wi}"><i></i></div></div>`).join("");
      return `<div class="row" style="margin-bottom:8px"><div style="width:32px;font-size:13px;font-weight:${di === nowD ? 700 : 400};color:${di === nowD ? "var(--ink)" : "var(--muted)"}">${label}</div>
        <div class="bar" data-bar="${di}">${wins}${di === nowD ? `<div class="nowl" style="left:${(nowMin / 1440 * 100).toFixed(2)}%"></div>` : ""}</div>
        <button class="addb" data-act="win-add" data-d="${di}" title="Добавить окно">+</button></div>`;
    }).join("");

    const ed = S.edit && r.program[S.edit.d] && r.program[S.edit.d][S.edit.i];
    const opts = (from, to, sel) => { let o = ""; for (let m = from; m <= to; m += 30) o += `<option value="${m}" ${m === sel ? "selected" : ""}>${m === 1440 ? "24:00" : m2t(m)}</option>`; return o; };
    const editor = ed ? `<div class="editor"><div style="font-weight:500;font-size:14px">${DAY[S.edit.d]} · окно «дома»</div>
      <select data-act="ed-start">${opts(0, 1410, ed[0])}</select><span class="muted">-</span><select data-act="ed-end">${opts(30, 1440, ed[1])}</select>
      <button class="obtn" data-act="ed-del" style="background:var(--card)">Удалить окно</button><button class="pbtn" data-act="ed-close" style="padding:11px 18px">Готово</button></div>` : "";

    return `<section class="card">
      <div style="padding:18px 20px;border-bottom:1px solid var(--soft)">
        <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap"><h2 style="margin:0;font-size:18px;font-weight:500">${esc(r.name)}</h2><div class="muted" style="font-size:13.5px">${esc(e.label)} · ${originTxt} · ${esc(e.until)}</div></div>
        ${r.fault ? `<div style="margin-top:10px;padding:8px 12px;background:var(--warm-soft);color:var(--warm-ink);font-weight:500;font-size:13.5px;display:inline-block;border-radius:10px">Неисправность термостата - проверьте устройство</div>` : ""}
        <div style="display:flex;align-items:baseline;gap:24px;flex-wrap:wrap;margin-top:14px">
          <div><div class="stat">${f1(r.air)}°</div><div class="stat-l">воздух</div></div>
          <div><div class="stat">${f1(r.floor)}°</div><div class="stat-l">пол</div></div>
          <div><div class="stat">${r.hum == null ? "–" : Math.round(r.hum)}%</div><div class="stat-l">влажность</div></div>
          <div style="display:flex;align-items:baseline;gap:10px"><div class="stat muted">→</div><div>
            <div class="tchip"><div class="stat" style="color:${r.heating ? "var(--warm-ink)" : "var(--ink)"}">${f1(e.target)}°</div>
              <button class="rb" data-act="sel-dec" aria-label="Убавить" ${vacd ? "disabled" : ""}>−</button><button class="rb" data-act="sel-inc" aria-label="Прибавить" ${vacd ? "disabled" : ""}>+</button></div>
            <div class="muted" style="font-size:12px;margin-top:3px;padding-left:16px">цель · ${r.heating ? "греет" : "не греет"}</div></div></div></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px">${quick}${e.ovr && !vacd ? `<button class="link" data-act="resume">Вернуться к расписанию</button>` : ""}</div>
        ${vacd ? `<div class="muted" style="margin-top:8px;font-size:12.5px">Быстрые режимы недоступны, пока действует отпуск</div>` : ""}
      </div>
      <div class="sec"><div class="muted" style="font-size:13px;font-weight:500;margin-bottom:10px">Уставки режимов</div><div style="display:flex;gap:10px;flex-wrap:wrap">${sps}</div></div>
      <div class="sec">
        <div class="row" style="gap:12px;flex-wrap:wrap;margin-bottom:6px"><div class="muted" style="font-size:13px;font-weight:500">Недельное расписание</div>
          <button class="chipbtn" data-act="sched-toggle" style="padding:8px 14px;border-radius:16px;background:${r.enabled ? "var(--acc-soft)" : "var(--soft)"};color:${r.enabled ? "var(--acc-ink)" : "var(--muted)"}">${r.enabled ? "Включено" : "Выключено"}</button>
          <div style="flex:1"></div><button class="tbtn" data-act="std">Стандартное расписание</button><button class="tbtn" data-act="copy-all">${S.copied ? "Скопировано на все ✓" : "Скопировать на все комнаты"}</button></div>
        <div class="muted" style="font-size:13px;margin-bottom:12px">${r.enabled ? `Синие окна - «Дома» (${f1(r.sp.home)}°), остальное время - «Вне дома» (${f1(r.sp.away)}°).` : r.hasProgram ? "Расписание выключено - программа сохранена, но не управляет термостатом." : "Расписания пока нет - добавьте окна или примените стандартное."}</div>
        <div style="display:flex;gap:8px;margin:0 0 4px 40px;color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums"><div style="flex:1;display:flex;justify-content:space-between"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div><div style="width:40px"></div></div>
        ${days}
        <div class="muted" style="font-size:12px;margin:4px 0 0 40px">Потяните за края окна, чтобы изменить время (сетка 30 минут), или нажмите на окно для точной правки.</div>
        ${editor}
      </div>
      <div style="padding:12px 20px 18px">
        <button data-act="rare" style="border:none;background:transparent;color:var(--muted);font-size:13px;font-weight:500;padding:10px 0;text-align:left">${S.rare ? "▴" : "▾"} Батарея, замок, преднагрев, пределы</button>
        ${S.rare ? `<div style="display:flex;gap:26px;flex-wrap:wrap;margin-top:6px;font-size:14px;align-items:center">
          <div><div class="muted" style="font-size:11.5px">Батарея</div><div style="font-weight:500;color:${r.bat != null && r.bat <= 20 ? "var(--warm-ink)" : "var(--ink)"}">${r.bat == null ? "–" : r.bat + "%"}</div></div>
          <div><div class="muted" style="font-size:11.5px">Источник уставки</div><div style="font-weight:500">${r.source === "device" ? "с самого термостата" : r.source === "panel" ? "извне (HA / приложение)" : "по расписанию"}</div></div>
          <div><div class="muted" style="font-size:11.5px">Пределы t°</div><div style="font-weight:500;font-variant-numeric:tabular-nums">${f1(r.lower)}° - ${f1(r.upper)}°</div></div>
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;min-height:44px"><input type="checkbox" data-act="lock-cb" ${r.lock ? "checked" : ""}>Замок от детей</label>
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;min-height:44px"><input type="checkbox" data-act="preheat-cb" ${r.preheat ? "checked" : ""}>Преднагрев</label></div>` : ""}
      </div></section>`;
  }

  // -- events ----------------------------------------------------------------

  _bind(rooms) {
    const S = this._s, root = this.shadowRoot;
    const cur = () => rooms[S.view];
    const rerender = () => this._render();
    root.querySelectorAll("[data-act]").forEach((el) => {
      const act = el.dataset.act, isInput = el.tagName === "INPUT" || el.tagName === "SELECT";
      el.addEventListener(isInput ? "change" : "click", (ev) => {
        const i = el.dataset.i != null ? Number(el.dataset.i) : null;
        const r = i != null && i >= 0 ? rooms[i] : null;
        switch (act) {
          case "view": S.view = i; S.edit = null; S.menu = null; return rerender();
          case "open": if (S.menu !== null) { S.menu = null; return rerender(); } S.view = i; S.edit = null; return rerender();
          case "lock": ev.stopPropagation(); return this._call("lock", r.lock ? "unlock" : "lock", { entity_id: r.m["lock:child_lock"] });
          case "inc": ev.stopPropagation(); return this._bump(r, 0.5);
          case "dec": ev.stopPropagation(); return this._bump(r, -0.5);
          case "mode-menu": ev.stopPropagation(); S.menu = S.menu === i ? null : i; return rerender();
          case "mode-pick": ev.stopPropagation(); S.menu = null; rerender(); return this._preset(r, el.dataset.m);
          case "vac-open": S.vacOpen = true; return this._prefillVac(rooms), rerender();
          case "vac-edit": S.view = -1; S.vacOpen = true; return this._prefillVac(rooms), rerender();
          case "vac-clear": return this._svc("clear_holiday", { all: true }, "Отпуск снят");
          case "vac-cancel": case "vf-cancel": S.vacOpen = false; return rerender();
          case "vf-kind": S.vf.kind = el.dataset.v; return rerender();
          case "vf-when": S.vf.when = el.dataset.v; return rerender();
          case "vf-start": S.vf.start = el.value; return rerender();
          case "vf-end": S.vf.end = el.value; return rerender();
          case "vf-room": S.vf.rooms[el.dataset.d] = el.checked; return rerender();
          case "vf-inc": S.vf.temp = Math.min(35, S.vf.temp + 0.5); return rerender();
          case "vf-dec": S.vf.temp = Math.max(4, S.vf.temp - 0.5); return rerender();
          case "vf-go": return this._submitVac(rooms);
          case "sel-inc": return this._bump(cur(), 0.5);
          case "sel-dec": return this._bump(cur(), -0.5);
          case "quick": return el.dataset.on === "1" ? this._resume(cur()) : this._preset(cur(), el.dataset.m);
          case "resume": return this._resume(cur());
          case "sp-inc": return this._setpoint(cur(), el.dataset.k, 0.5);
          case "sp-dec": return this._setpoint(cur(), el.dataset.k, -0.5);
          case "sched-toggle": return this._svc("enable_schedule", { device_id: cur().devId, enabled: !cur().enabled });
          case "std": { const r0 = cur(); const p = this._progOf(r0); for (let d = 0; d < 7; d++) p[d] = clone([d < 5 ? STD_WD : STD_WE])[0]; S.edit = null; this._queueSave(r0); return rerender(); }
          case "copy-all": { const r0 = cur(); if (this._dirty[r0.devId]) { this._toast("Сначала дождитесь сохранения"); return; } S.copied = true; rerender(); clearTimeout(this._ct); this._ct = setTimeout(() => { S.copied = false; rerender(); }, 2500); return this._svc("copy_schedule", { device_id: r0.devId }); }
          case "win": if (this._dragged) return; S.edit = { d: Number(el.dataset.d), i: Number(el.dataset.i) }; return rerender();
          case "win-add": { const r0 = cur(), di = Number(el.dataset.d), p = this._progOf(r0); const day = p[di].sort((a, b) => a[0] - b[0]); let s0 = 480;
            for (const w of day) { if (s0 + 30 <= w[0]) break; s0 = Math.max(s0, w[1]); } if (s0 >= 1440) return; day.push([s0, Math.min(s0 + 120, 1440)]); day.sort((a, b) => a[0] - b[0]);
            S.edit = { d: di, i: day.findIndex((w) => w[0] === s0) }; this._queueSave(r0); return rerender(); }
          case "ed-start": case "ed-end": { const r0 = cur(), p = this._progOf(r0), w = p[S.edit.d][S.edit.i], v = Number(el.value);
            if (act === "ed-start") w[0] = Math.min(v, w[1] - 30); else w[1] = Math.max(v, w[0] + 30);
            const day = p[S.edit.d]; day.forEach((o, j) => { if (j === S.edit.i) return; if (w[0] < o[1] && o[0] < w[1]) { if (j < S.edit.i) w[0] = Math.max(w[0], o[1]); else w[1] = Math.min(w[1], o[0]); } });
            this._queueSave(r0); return rerender(); }
          case "ed-del": { const r0 = cur(), p = this._progOf(r0); p[S.edit.d].splice(S.edit.i, 1); S.edit = null; this._queueSave(r0); return rerender(); }
          case "ed-close": S.edit = null; return rerender();
          case "rare": S.rare = !S.rare; return rerender();
          case "lock-cb": return this._call("lock", el.checked ? "lock" : "unlock", { entity_id: cur().m["lock:child_lock"] });
          case "preheat-cb": return this._call("switch", el.checked ? "turn_on" : "turn_off", { entity_id: cur().m["switch:pre_heat"] });
        }
      });
    });
    root.querySelectorAll("[data-drag]").forEach((h) => h.addEventListener("pointerdown", (ev) => this._drag(ev, h, cur())));
  }

  _drag(ev, h, r) {
    ev.stopPropagation(); ev.preventDefault();
    const bar = h.closest("[data-bar]"); if (!bar || !r) return;
    const rect = bar.getBoundingClientRect(), di = Number(h.dataset.d), wi = Number(h.dataset.i), edge = h.dataset.drag;
    const p = this._progOf(r); this._dragged = false;
    const move = (e) => {
      this._dragged = true;
      let m = Math.round(((e.clientX - rect.left) / rect.width) * 1440 / 30) * 30; m = Math.max(0, Math.min(1440, m));
      const day = p[di], w = day[wi];
      if (edge === "s") { const lo = wi > 0 ? day[wi - 1][1] : 0; w[0] = Math.max(lo, Math.min(m, w[1] - 30)); }
      else { const hi = wi < day.length - 1 ? day[wi + 1][0] : 1440; w[1] = Math.min(hi, Math.max(m, w[0] + 30)); }
      const el = this.shadowRoot.querySelector(`.win[data-d="${di}"][data-i="${wi}"]`);
      if (el) { el.style.left = (w[0] / 1440 * 100).toFixed(2) + "%"; el.style.width = ((w[1] - w[0]) / 1440 * 100).toFixed(2) + "%"; el.title = `Дома ${m2t(w[0])} - ${m2t(w[1])}`; }
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); setTimeout(() => { this._dragged = false; }, 50); this._queueSave(r); this._render(); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); window.addEventListener("pointercancel", up);
  }

  _prefillVac(rooms) {
    const vf = this._s.vf, withHol = rooms.filter((r) => r.holiday);
    if (!withHol.length) { rooms.forEach((r) => { if (!(r.devId in vf.rooms)) vf.rooms[r.devId] = true; }); return; }
    const h = withHol[0].holiday;
    vf.kind = h.kind; vf.when = "plan"; vf.temp = h.temperature ?? vf.temp;
    vf.start = h.kind === "at_home" ? String(h.start).slice(0, 10) : localISO(new Date(h.start));
    vf.end = h.kind === "at_home" ? String(h.end).slice(0, 10) : localISO(new Date(h.end));
    rooms.forEach((r) => { vf.rooms[r.devId] = !!r.holiday; });
  }

  async _submitVac(rooms) {
    const vf = this._s.vf, targets = rooms.filter((r) => vf.rooms[r.devId] !== false);
    if (!targets.length || !vf.end || (vf.when === "plan" && !vf.start)) return;
    const away = vf.kind === "away";
    let start = vf.when === "now" ? (away ? localISO(new Date()) : localISO(new Date()).slice(0, 10)) : vf.start;
    let end = vf.end;
    const fmt = (v) => (away ? v.replace("T", " ") : v.slice(0, 10));
    const payload = { kind: vf.kind, start: fmt(start), end: fmt(end) };
    if (away) payload.temperature = vf.temp;
    // rooms not selected any more lose their holiday (edit flow)
    for (const r of rooms) {
      if (targets.includes(r)) await this._svc("set_holiday", { device_id: r.devId, ...payload });
      else if (r.holiday) await this._svc("clear_holiday", { device_id: r.devId });
    }
    this._s.vacOpen = false; this._toast(vf.when === "now" ? "Отпуск начат" : "Отпуск запланирован"); this._sig = ""; this._render();
  }
}

customElements.define("danfoss-heating-panel", DanfossHeatingPanel);
