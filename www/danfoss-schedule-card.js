/* Danfoss Icon2 (Local) - weekly schedule card (functional prototype).
 * Mirrors the Danfoss Ally model one-to-one: a day is a list of "at home"
 * windows on a 30-minute grid, everything else is "away"; holiday is either
 * "away" (datetime range) or "at home" (date range, replays Saturday).
 * Reads sensor.<rt>_schedule attributes, edits locally, writes back through
 * the danfoss_local.* services.
 * Config: { type: "custom:danfoss-schedule-card", entity: "sensor.icon2_rt_6_schedule" }
 */

const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const SAT = 5;
const STATE_LABEL = { at_home: "Дома", leaving_home: "Вне дома", holiday: "Отпуск", off: "Выкл" };

const pad = (n) => String(n).padStart(2, "0");
const minToHHMM = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
const hhmmToMin = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
const onGrid = (m) => m % 30 === 0;

class DanfossScheduleCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("entity is required");
    this._config = config;
    this._dirty = false;
    this._days = null;
  }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states[this._config.entity];
    if (!st) { this._renderError(`Нет сущности ${this._config.entity}`); return; }
    this._state = st;
    if (!this._dirty) this._loadFromState(st);
    this._render();
  }

  getCardSize() { return 12; }

  _deviceId() {
    if (this._config.device_id) return this._config.device_id;
    const ent = this._hass.entities && this._hass.entities[this._config.entity];
    return ent ? ent.device_id : null;
  }

  _loadFromState(st) {
    const a = st.attributes || {};
    const p = a.program;
    this._days = p ? p.days.map((d) => d.map((w) => ({ ...w }))) : [[], [], [], [], [], [], []];
    this._hasProgram = !!p;
    this._enabled = a.enabled !== false && !!p;
    this._holiday = a.holiday || null;
  }

  async _call(service, data, okMsg) {
    const device_id = this._deviceId();
    if (!device_id && !data.all) { this._toast("Не удалось определить device_id термостата"); return; }
    try {
      await this._hass.callService("danfoss_local", service, { ...(data.all ? {} : { device_id }), ...data });
      this._dirty = false;
      this._toast(okMsg || "Сохранено");
    } catch (e) {
      this._toast("Ошибка: " + (e && e.message ? e.message : e));
    }
  }

  _programForService() {
    return { days: this._days.map((d) => [...d].sort((x, y) => x.start - y.start).map((w) => ({ start: minToHHMM(w.start), end: minToHHMM(w.end) }))) };
  }

  _toast(msg) {
    const t = this.shadowRoot && this.shadowRoot.querySelector(".toast");
    if (!t) return;
    t.textContent = msg; t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2500);
  }

  _renderError(msg) {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px;color:var(--error-color)">${msg}</div></ha-card>`;
  }

  _fmtHoliday() {
    const h = this._holiday;
    if (!h) return "нет";
    const d = (s) => new Date(s).toLocaleDateString("ru-RU");
    const dt = (s) => new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    return h.kind === "away" ? `вне дома ${dt(h.start)} - ${dt(h.end)}` : `дома ${d(h.start)} - ${d(h.end)} (по субботе)`;
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const a = this._state.attributes || {};
    const name = (a.friendly_name || this._config.entity).replace(/\s*(Расписание|Schedule)$/i, "");
    const next = a.next_change_at
      ? `${new Date(a.next_change_at).toLocaleString("ru-RU", { weekday: "short", hour: "2-digit", minute: "2-digit" })} → ${STATE_LABEL[a.next_mode] || a.next_mode}`
      : "нет";
    const satEmpty = this._days[SAT].length === 0;

    const dayRows = this._days.map((wins, di) => {
      const items = [...wins].sort((x, y) => x.start - y.start).map((w) => `
        <span class="win">${minToHHMM(w.start)} - ${minToHHMM(w.end)}
          <button class="icon" data-act="del" data-d="${di}" data-i="${wins.indexOf(w)}" title="Удалить">✕</button>
        </span>`).join("");
      return `
        <div class="day">
          <div class="dayname">${DAYS[di]}</div>
          <div class="wins">${items || `<span class="muted">весь день вне дома</span>`}</div>
          <div class="add">
            <input type="time" step="1800" value="06:00" data-role="start" data-d="${di}">
            <span>-</span>
            <input type="time" step="1800" value="08:00" data-role="end" data-d="${di}">
            <button data-act="add" data-d="${di}">+ дома</button>
            ${di === 0 ? `<button class="ghost" data-act="copyday" title="Скопировать понедельник на Вт-Пт">Пн → будни</button>` : ""}
          </div>
        </div>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 16px 16px; position:relative; }
        .hdr { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
        .title { font-size:1.1em; font-weight:600; }
        .now { font-size:.9em; color:var(--secondary-text-color); }
        .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:6px 0; }
        .day { display:grid; grid-template-columns: 34px 1fr; gap:4px 10px; padding:6px 0; border-top:1px solid var(--divider-color); }
        .dayname { font-weight:600; padding-top:4px; }
        .wins { display:flex; flex-wrap:wrap; gap:6px; align-items:center; min-height:26px; }
        .win { display:inline-flex; align-items:center; gap:4px; background:#2e7d32; color:#fff; border-radius:14px; padding:2px 6px 2px 10px; font-variant-numeric: tabular-nums; }
        .add { grid-column: 2; display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
        .muted { color:var(--secondary-text-color); font-size:.9em; }
        input, select { font: inherit; padding:2px 4px; background:var(--card-background-color); color:var(--primary-text-color); border:1px solid var(--divider-color); border-radius:6px; }
        button { font: inherit; padding:4px 10px; border-radius:8px; border:1px solid var(--divider-color); background:var(--secondary-background-color); color:var(--primary-text-color); cursor:pointer; }
        button.primary { background:var(--primary-color); color:#fff; border-color:var(--primary-color); }
        button.icon { padding:0 4px; border:none; background:transparent; color:#fff; }
        button.ghost { background:transparent; }
        button[disabled] { opacity:.5; cursor:not-allowed; }
        .section { border-top:1px solid var(--divider-color); padding-top:8px; margin-top:6px; }
        .footer { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; align-items:center; }
        .dirty { color:var(--warning-color); font-size:.85em; }
        .toast { position:absolute; right:16px; bottom:8px; background:var(--primary-color); color:#fff; padding:4px 10px; border-radius:8px; opacity:0; transition:opacity .2s; pointer-events:none; }
        .toast.show { opacity:1; }
      </style>
      <ha-card>
        <div class="hdr">
          <div>
            <div class="title">${name}</div>
            <div class="now">сейчас по графику: <b>${STATE_LABEL[this._state.state] || this._state.state}</b> · следующий: ${next}</div>
            <div class="now">отпуск: ${this._fmtHoliday()}</div>
          </div>
          <label class="row"><input type="checkbox" data-role="enabled" ${this._enabled ? "checked" : ""} ${this._hasProgram ? "" : "disabled"}> включено</label>
        </div>
        ${dayRows}
        <div class="section">
          <div class="row">
            <b>Отпуск</b>
            <select data-role="hkind">
              <option value="away">вне дома</option>
              <option value="at_home" ${satEmpty ? "disabled" : ""}>дома (по субботе)</option>
            </select>
            <label class="row" style="margin:0"><input type="checkbox" data-role="hall"> на все термостаты</label>
          </div>
          <div class="row" data-role="hrow-away">
            <input type="datetime-local" step="1800" data-role="hstart">
            <span>-</span>
            <input type="datetime-local" step="1800" data-role="hend">
          </div>
          <div class="row" data-role="hrow-athome" hidden>
            <input type="date" data-role="hdstart">
            <span>-</span>
            <input type="date" data-role="hdend">
            ${satEmpty ? `<span class="muted">сначала задайте субботу</span>` : ""}
          </div>
          <div class="row">
            <button data-act="setholiday">Задать отпуск</button>
            <button class="ghost" data-act="clearholiday">Снять отпуск</button>
          </div>
        </div>
        <div class="footer">
          <button class="primary" data-act="save">Сохранить</button>
          <button data-act="copyall" ${this._hasProgram ? "" : "disabled"}>Скопировать на все</button>
          <button class="ghost" data-act="clear">Очистить расписание</button>
          ${this._dirty ? `<span class="dirty">есть несохранённые изменения</span>` : ""}
        </div>
        <div class="toast"></div>
      </ha-card>`;

    const q = (sel) => this.shadowRoot.querySelector(sel);
    this.shadowRoot.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", (e) => this._onAction(e.currentTarget)));
    q('[data-role="enabled"]').addEventListener("change", (e) => this._call("enable_schedule", { enabled: e.target.checked }));
    q('[data-role="hkind"]').addEventListener("change", (e) => {
      const away = e.target.value === "away";
      q('[data-role="hrow-away"]').hidden = !away; q('[data-role="hrow-athome"]').hidden = away;
    });
  }

  _onAction(btn) {
    const act = btn.dataset.act, d = Number(btn.dataset.d);
    const q = (sel) => this.shadowRoot.querySelector(sel);
    if (act === "add") {
      const start = hhmmToMin(q(`[data-role="start"][data-d="${d}"]`).value);
      const end = hhmmToMin(q(`[data-role="end"][data-d="${d}"]`).value);
      if (!onGrid(start) || !onGrid(end)) { this._toast("Время только с шагом 30 минут"); return; }
      if (!(start < end)) { this._toast("Начало должно быть раньше конца"); return; }
      if (this._days[d].some((w) => start < w.end && w.start < end)) { this._toast("Пересекается с существующим окном"); return; }
      this._days[d].push({ start, end }); this._dirty = true; this._render();
    } else if (act === "del") {
      if (d === SAT && this._holiday && this._holiday.kind === "at_home" && this._days[SAT].length === 1) {
        this._toast("Субботу нельзя очистить, пока запланирован отпуск дома"); return;
      }
      this._days[d].splice(Number(btn.dataset.i), 1); this._dirty = true; this._render();
    } else if (act === "copyday") {
      for (let i = 1; i <= 4; i++) this._days[i] = this._days[0].map((w) => ({ ...w }));
      this._dirty = true; this._render();
    } else if (act === "save") {
      this._call("set_schedule", { program: this._programForService(), enabled: this._enabled || !this._hasProgram });
    } else if (act === "copyall") {
      if (this._dirty) { this._toast("Сначала сохраните"); return; }
      this._call("copy_schedule", {}, "Скопировано на все термостаты");
    } else if (act === "clear") {
      if (!confirm("Удалить расписание этого термостата?")) return;
      this._call("clear_schedule", {});
    } else if (act === "setholiday") {
      const kind = q('[data-role="hkind"]').value, all = q('[data-role="hall"]').checked;
      let start, end;
      if (kind === "away") {
        start = q('[data-role="hstart"]').value; end = q('[data-role="hend"]').value;
        if (!start || !end || start >= end) { this._toast("Укажите корректные дату и время"); return; }
        start = start.replace("T", " "); end = end.replace("T", " ");
      } else {
        start = q('[data-role="hdstart"]').value; end = q('[data-role="hdend"]').value;
        if (!start || !end || start > end) { this._toast("Укажите корректные даты"); return; }
      }
      this._call("set_holiday", { kind, start, end, ...(all ? { all: true } : {}) }, all ? "Отпуск задан на все термостаты" : "Отпуск задан");
    } else if (act === "clearholiday") {
      const all = q('[data-role="hall"]').checked;
      this._call("clear_holiday", all ? { all: true } : {}, "Отпуск снят");
    }
  }
}

customElements.define("danfoss-schedule-card", DanfossScheduleCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "danfoss-schedule-card", name: "Danfoss Icon2 schedule", description: "Weekly schedule editor for danfoss_local thermostats (Ally model)" });
