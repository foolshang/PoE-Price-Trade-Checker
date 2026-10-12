/* The style editor (colours with opacity, size, icon, effect, sound) - same fields as the desktop editor. One builder,
 * two uses: P.buildStyleEditor() makes the editor itself (the sub tabs of the Whitelist tab show it inline, every edit
 * goes to onChange(style) at once) and P.openStyleDialog() wraps it in the modal dialog (the quest (Q) style of the
 * NeverSink tab). The editor works on a copy of the style dict; the Python side decides what it stores. */
"use strict";
(() => {
const P = window.PFG;
const { h } = P;

const COLOR_PARTS = [["text", "ตัวอักษร"], ["border", "กรอบ"], ["bg", "พื้นหลัง"]];

/** opts: style, showSound, soundLabel (the sound slot a picked file is kept in), sample, onChange(style) -> {el, get, set}. */
P.buildStyleEditor = (opts) => {
  const K = P.K.style;
  let st = P.clone(opts.style);
  const prevAlpha = {};                                   // part -> last non-zero opacity (restored by un-ticking "โปร่งใส")
  let on = {};
  const preview = h("div", { class: "style-preview" }, opts.sample || "ตัวอย่าง");
  const grid = h("div", { class: "style-grid" });
  let muted = false;                                      // set() redraws the controls: no onChange while it runs

  const out = () => {
    const o = P.clone(st);
    for (const part of ["text", "border", "bg"]) o[part] = on[part] ? st[part] : null;
    o.size = on.size ? st.size : null;
    o.icon = on.icon ? st.icon : null;
    o.effect = on.effect ? st.effect : null;
    if (!opts.showSound) o.sound = { kind: "none", id: 1, file: "", volume: K.default_volume };
    return o;
  };
  const refresh = () => {
    const bg = on.bg && st.bg ? P.rgba(st.bg, "#101010") : "#101010";
    preview.style.background = bg;
    preview.style.color = on.text && st.text ? P.rgba(st.text, "#c8c8c8") : "#c8c8c8";
    preview.style.borderColor = on.border && st.border ? P.rgba(st.border, bg) : "#555";
    preview.style.fontSize = (on.size && st.size ? Math.max(11, Math.min(26, st.size / 1.8)) : 15) + "px";
  };
  const touch = () => { refresh(); if (!muted && opts.onChange) opts.onChange(out()); };

  const build = () => {
    on = {
      text: !!st.text, border: !!st.border, bg: !!st.bg, size: st.size !== null && st.size !== undefined,
      icon: !!st.icon, effect: !!st.effect,
    };
    const rows = [];
    const row = (label, ...ctl) => { rows.push(h("label", { class: "l" }, label), h("div", { class: "ctl" }, ...ctl)); };
    const tick = (part) => h("input", { type: "checkbox", checked: on[part], "aria-label": "ใช้ส่วนนี้",
      onchange: (e) => { on[part] = e.target.checked; touch(); } });

    // colours + opacity
    for (const [part, label] of COLOR_PARTS) {
      if (!st[part]) st[part] = [255, 255, 255, 255];
      if (st[part].length < 4) st[part] = [...st[part].slice(0, 3), 255];
      prevAlpha[part] = st[part][3] > 0 ? st[part][3] : 255;
      const color = h("input", { type: "color", value: P.hex(st[part]), "aria-label": `สี${label}`,
        oninput: (e) => { st[part] = [...P.unhex(e.target.value), st[part][3]]; touch(); } });
      const num = h("input", { type: "number", min: 0, max: 255, value: st[part][3], "aria-label": `ความทึบ ${label}` });
      const rng = h("input", { type: "range", min: 0, max: 255, value: st[part][3], "aria-label": `แถบความทึบ ${label}` });
      const clear = h("input", { type: "checkbox", checked: st[part][3] === 0, "aria-label": `โปร่งใส ${label}` });
      const setAlpha = (v) => {
        v = Math.max(0, Math.min(255, parseInt(v, 10) || 0));
        st[part][3] = v; num.value = v; rng.value = v; clear.checked = v === 0;
        if (v > 0) prevAlpha[part] = v;
        touch();
      };
      num.addEventListener("input", () => setAlpha(num.value));
      rng.addEventListener("input", () => setAlpha(rng.value));
      clear.addEventListener("change", () => setAlpha(clear.checked ? 0 : prevAlpha[part]));
      row(label, tick(part), color,
        h("div", { class: "alpha" }, h("span", { class: "hint" }, "ความทึบ (255 = ทึบ, 0 = โปร่งใส)"), num, rng, h("label", {}, clear, " โปร่งใส")));
    }

    // size
    if (st.size === null || st.size === undefined) st.size = 40;
    const size = h("input", { type: "number", min: K.font_min, max: K.font_max, value: st.size, "aria-label": "ขนาดตัวอักษร",
      oninput: (e) => { st.size = Math.max(K.font_min, Math.min(K.font_max, parseInt(e.target.value, 10) || K.font_min)); touch(); } });
    row("ขนาด", tick("size"), size, h("span", { class: "hint" }, `${K.font_min}–${K.font_max}`));

    // icon
    if (!st.icon) st.icon = { size: 0, color: "White", shape: "Circle" };
    const sel = (values, cur, cb, label) => h("select", { "aria-label": label, onchange: (e) => { cb(e.target.value); touch(); } },
      values.map((v) => h("option", { value: v, selected: String(v) === String(cur) }, v)));
    row("ไอคอน", tick("icon"), sel([0, 1, 2], st.icon.size, (v) => { st.icon.size = +v; }, "ขนาดไอคอน"),
      sel(K.colors, st.icon.color, (v) => { st.icon.color = v; }, "สีไอคอน"),
      sel(K.shapes, st.icon.shape, (v) => { st.icon.shape = v; }, "รูปทรงไอคอน"), h("span", { class: "hint" }, "ขนาด · สี · รูปทรง"));

    // effect (beam)
    if (!st.effect) st.effect = { color: "White", temp: false };
    row("ลำแสง", tick("effect"), sel(K.colors, st.effect.color, (v) => { st.effect.color = v; }, "สีลำแสง"),
      h("label", {}, h("input", { type: "checkbox", checked: st.effect.temp, "aria-label": "ลำแสงชั่วคราว",
        onchange: (e) => { st.effect.temp = e.target.checked; touch(); } }), " ชั่วคราว (Temp)"));

    // sound
    if (opts.showSound) {
      const snd = st.sound || (st.sound = { kind: "none", id: 1, file: "", volume: K.default_volume });
      const gameBox = h("span", { class: "ctl" });
      const fileBox = h("span", { class: "ctl" });
      const fileName = h("span", { class: "hint" }, snd.kind === "file" && snd.file ? snd.file : "ยังไม่ได้เลือกไฟล์");
      const vol = h("input", { type: "number", min: 0, max: K.volume_max, value: snd.volume, "aria-label": "ระดับเสียง",
        oninput: (e) => { snd.volume = Math.max(0, Math.min(K.volume_max, parseInt(e.target.value, 10) || 0)); touch(); } });
      const file = h("input", { type: "file", accept: "audio/*,.mp3,.wav,.ogg", "aria-label": "เลือกไฟล์เสียง", onchange: async (e) => {
        const f = e.target.files[0];
        if (!f) return;
        snd.file = await P.sounds.setFile(opts.soundLabel, f);
        snd.kind = "file"; kindSel.value = "file"; fileName.textContent = snd.file; show(); touch();
      } });
      gameBox.append(sel(K.sound_ids, snd.id, (v) => { snd.id = +v; }, "เสียงของเกม"), h("span", { class: "hint" }, "เสียงเกม"));
      fileBox.append(file, fileName);
      const show = () => { gameBox.hidden = snd.kind !== "game"; fileBox.hidden = snd.kind !== "file"; vol.hidden = snd.kind === "none"; };
      const kindSel = h("select", { "aria-label": "ชนิดเสียง", onchange: (e) => { snd.kind = e.target.value; show(); touch(); } },
        [["none", "ไม่ตั้ง (ใช้ของ NeverSink)"], ["game", "เสียงของเกม"], ["file", "ไฟล์ของฉัน (mp3/wav/ogg)"]]
          .map(([v, t]) => h("option", { value: v, selected: v === snd.kind }, t)));
      show();
      row("เสียง", kindSel, gameBox, fileBox, vol);
    }
    grid.replaceChildren(...rows, preview);
    refresh();
  };

  build();
  return {
    el: grid,
    get: out,
    /** show another style (no onChange fired) */
    set(style) { st = P.clone(style); muted = true; try { build(); } finally { muted = false; } },
  };
};

P.openStyleDialog = (opts) => {
  const dlg = P.$("#dlg-style");
  const ed = P.buildStyleEditor(opts);
  const finish = async (clear) => {
    dlg.close();
    await opts.onSave(clear ? null : ed.get());
  };
  const save = h("button", { type: "button", onclick: () => finish(false) }, "บันทึก");
  const cancel = h("button", { type: "button", class: "secondary", onclick: () => dlg.close() }, "ยกเลิก");
  const reset = h("button", { type: "button", class: "secondary", onclick: () => finish(true) }, opts.clearText || "รีเซ็ตเป็นค่า NeverSink");
  dlg.replaceChildren(
    h("h3", {}, opts.title),
    opts.hint ? h("p", { class: "hint" }, opts.hint) : null,
    ed.el,
    h("div", { class: "actions" }, save, cancel, reset));
  dlg.showModal();
};
})();
