/* The NeverSink tab: NeverSink's own tiers (no prices): filter name, strictness, the quest (Q) style, the six numbered
 * sound files (sound 1 <- NeverSink's number 6, 2 <- 1, 3 <- 2, 4 <- 3, 5 <- 4, 6 <- 5), the NeverSink version in use,
 * Generate / Refresh NeverSink Base. */
"use strict";
(() => {
const P = window.PFG;
const { h } = P;

const isEmptyStyle = (s) => !s || (!s.text && !s.border && !s.bg && !s.icon && !s.effect && (s.size === null || s.size === undefined)
  && (!s.sound || s.sound.kind === "none"));

P.tabNs = {
  mount(pane, ctx) {
    this.ctx = ctx;
    const K = P.K;
    this.name = h("input", { type: "text", class: "grow", "aria-label": "ชื่อ filter", oninput: () => ctx.changed() });
    this.strict = h("select", { "aria-label": "NeverSink Strictness", onchange: () => ctx.changed() },
      K.levels.map((l, i) => h("option", { value: i }, `${i} - ${l}`)));
    this.qLbl = h("span", { class: "hint" });
    this.qBtn = h("button", { type: "button", class: "secondary", onclick: () => this.editQ() }, "ตั้งสไตล์…");
    this.soundRows = {};
    const soundRow = (n) => {
      const label = h("span", { class: "hint" });
      const file = h("input", { type: "file", accept: "audio/*,.mp3,.wav,.ogg", "aria-label": `ไฟล์เสียง ${n}`,
        onchange: async (e) => { const f = e.target.files[0]; if (f) { ctx.cfg[`sound_${n}`] = await P.sounds.setFile(n, f); this.refreshSounds(); ctx.changed(); } } });
      const clear = h("button", { type: "button", class: "secondary", "aria-label": `ล้างเสียง ${n}`, onclick: async () => {
        await P.sounds.clear(n); ctx.cfg[`sound_${n}`] = ""; file.value = ""; this.refreshSounds(); ctx.changed(); } }, "Clear");
      this.soundRows[n] = { label };
      return h("div", { class: "row" }, h("label", { class: "l" }, `เสียง ${n}`), label, file, clear);
    };
    this.tag = h("div", { class: "hint", id: "ns-tag" });
    this.btnGen = h("button", { type: "button", id: "btn-generate-tier", onclick: () => ctx.generate("tier", false) }, "Generate Now");
    this.btnRefresh = h("button", { type: "button", id: "btn-refresh", class: "secondary", onclick: () => ctx.generate("tier", true) }, "Refresh NeverSink Base");
    pane.replaceChildren(
      h("div", { class: "row" }, h("label", { class: "l" }, "ชื่อ filter:"), this.name, h("span", { class: "hint" }, ".filter")),
      h("div", { class: "row" }, h("label", { class: "l" }, "NeverSink Strictness:"), this.strict),
      h("div", { class: "row" }, h("label", { class: "l" }, "ของเควส (Q):"), this.qBtn, this.qLbl),
      h("div", { class: "section" }, "Alert sounds:"),
      ...["1", "2", "3", "4", "5", "6"].map(soundRow),
      this.tag,
      h("div", { class: "actions" }, this.btnGen, this.btnRefresh));
  },
  load(cfg, game) {
    this.name.value = cfg.filter_name_tier || P.K.default_names.tier;
    const s = cfg[`strictness_${game}`];
    this.strict.value = String(Number.isInteger(s) ? s : 2);
    this.refreshQ(cfg);
    this.refreshSounds();
    this.showTag(game);
  },
  collect(cfg, game) {
    cfg[`strictness_${game}`] = parseInt(this.strict.value, 10);
    cfg.filter_name_tier = this.name.value.trim() || P.K.default_names.tier;
    return cfg;
  },
  refreshQ(cfg) {
    const set = cfg.style_q && !isEmptyStyle(cfg.style_q);
    this.qLbl.textContent = set ? "ตั้งสไตล์เองแล้ว" : "ใช้ของ NeverSink";
    this.qLbl.style.color = set ? "var(--accent)" : "";
  },
  refreshSounds() {
    for (const n of ["1", "2", "3", "4", "5", "6"]) {
      const name = this.ctx.cfg[`sound_${n}`] || "";
      this.soundRows[n].label.textContent = name || "(ไม่ตั้ง — ใช้เสียงของ NeverSink)";
    }
  },
  showTag(game) {
    const last = P.nsLast(game);
    this.tag.textContent = last.tag ? `NeverSink ที่ใช้: ${last.tag} (เช็คล่าสุด ${String(last.checked_at || "").slice(0, 16).replace("T", " ")}) — กด Refresh เพื่อดึงใหม่` : "NeverSink: ยังไม่เคยดึง — จะดึงตอนกด Generate";
  },
  editQ() {
    const ctx = this.ctx;
    P.openStyleDialog({
      title: "สไตล์ของเควส (Q)", style: ctx.cfg.style_q || P.K.style.default_quest, showSound: true, soundLabel: "Q",
      sample: "Quest Item", clearText: "ล้าง (ใช้ของ NeverSink)", hint: "ใช้ทั้ง 2 แท็บ · ของเควสโชว์เสมอ",
      onSave: async (style) => {
        ctx.cfg.style_q = style;                     // null = not set (NeverSink's own look); an emptied style is kept as is
        if (style === null) await P.sounds.clear("Q");
        this.refreshQ(ctx.cfg); ctx.changed();
      },
    });
  },
};
})();
