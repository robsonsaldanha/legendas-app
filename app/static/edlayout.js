/* CNT Legendas — editor: tamanhos das áreas (divisórias arrastáveis), preferências do editor
   (no layout clássico de editor de legendas) e menu do botão direito (posição {\anN}, itálico…). */
"use strict";

/* --------------------------------------------------------- preferências */

const EDP_DEFAULT = {
  layout: { video: 0, edit: 180, wave: 236, tabs: 236 },   // video 0 = 44% da largura
  color: { short: true, long: true, cps: true, len: true, lines: true, overlap: true, gap: true },
  errColor: "",                     // vazio = cor do tema
  sub: { size: 100, bold: false },  // legenda sobre o vídeo (% do tamanho padrão)
  wave: { sel: "", fg: "", bg: "", head: "", grid: true, invertWheel: false, snapShots: true, cps: false },
  font: { listSize: 13, listBold: false, textSize: 18, textBold: true, textCenter: true },
  dicas: { ortografia: true, memoria: true },   // linha discreta debaixo do texto (2.15)
};
let EDP = structuredClone(EDP_DEFAULT);

function loadEdPrefs() {
  const saved = S.state?.settings?.editor || {};
  EDP = structuredClone(EDP_DEFAULT);
  for (const k of Object.keys(EDP)) {
    if (saved[k] == null) continue;
    EDP[k] = typeof EDP[k] === "object" ? { ...EDP[k], ...saved[k] } : saved[k];
  }
  return EDP;
}
let edPrefsTimer;
function saveEdPrefs() {
  clearTimeout(edPrefsTimer);
  edPrefsTimer = setTimeout(async () => {
    try {
      const r = await api("PUT", "/api/settings", { editor: EDP });
      if (S.state?.settings) S.state.settings.editor = r.editor;
    } catch (e) { toast(e.message, true); }
  }, 400);
}

/* aplica cores, fontes e tamanhos no editor aberto */
function applyEdPrefs() {
  const ed = document.querySelector(".ed");
  if (!ed) return;
  const L = EDP.layout;
  ed.style.setProperty("--ed-tabs", `${L.tabs}px`);
  ed.style.setProperty("--ed-edit", `${L.edit}px`);
  ed.style.setProperty("--ed-wave", `${L.wave}px`);
  ed.style.setProperty("--ed-video", L.video ? `${L.video}px` : "44%");
  ed.style.setProperty("--grid-font", `${EDP.font.listSize}px`);
  ed.style.setProperty("--grid-weight", EDP.font.listBold ? "600" : "400");
  ed.style.setProperty("--txt-font", `${EDP.font.textSize}px`);
  ed.style.setProperty("--txt-weight", EDP.font.textBold ? "600" : "400");
  ed.style.setProperty("--txt-align", EDP.font.textCenter ? "center" : "left");
  ed.style.setProperty("--sub-scale", String((EDP.sub.size || 100) / 100));
  ed.style.setProperty("--sub-weight", EDP.sub.bold ? "700" : "500");
  ed.style.setProperty("--bad-bg", EDP.errColor || "");
  if (!EDP.errColor) ed.style.removeProperty("--bad-bg");
  const root = document.documentElement.style;
  [["--wave-sel", EDP.wave.sel], ["--wave-fg", EDP.wave.fg], ["--wave-bg", EDP.wave.bg], ["--wave-head", EDP.wave.head]]
    .forEach(([k, v]) => (v ? root.setProperty(k, v) : root.removeProperty(k)));
}

/* --------------------------------------------------------- divisórias */

function initSplitters() {
  const ed = document.querySelector(".ed");
  if (!ed) return;
  ed.querySelectorAll(".ed-split").forEach((x) => x.remove());
  const mk = (id, dir, title) => {
    const h = document.createElement("div");
    h.className = `ed-split ${dir}`; h.dataset.s = id; h.title = title;
    h.setAttribute("role", "separator"); h.setAttribute("aria-orientation", dir === "v" ? "vertical" : "horizontal");
    ed.appendChild(h);
    return h;
  };
  const hs = {
    video: mk("video", "v", "Arraste para mudar a largura do vídeo"),
    edit: mk("edit", "h", "Arraste para mudar a altura da área de edição"),
    wave: mk("wave", "h", "Arraste para mudar a altura da forma de onda"),
    tabs: mk("tabs", "v", "Arraste para mudar a largura do painel Criar/Ajustar"),
  };
  Object.values(hs).forEach((h) => h.addEventListener("pointerdown", (e) => startSplit(e, h.dataset.s)));
  Object.values(hs).forEach((h) => h.addEventListener("dblclick", () => {
    EDP.layout[h.dataset.s] = EDP_DEFAULT.layout[h.dataset.s]; applyEdPrefs(); relayout(); saveEdPrefs();
  }));
  placeSplitters();
}

function placeSplitters() {
  const ed = document.querySelector(".ed");
  if (!ed) return;
  const R = ed.getBoundingClientRect();
  const r = (sel) => ed.querySelector(sel)?.getBoundingClientRect();
  const video = r(".ed-video"), vctl = r(".ed-vctl"), edit = r(".ed-edit"), wave = r(".ed-wave");
  const set = (s, css) => { const h = ed.querySelector(`.ed-split[data-s="${s}"]`); if (h) Object.assign(h.style, css); };
  if (video && vctl) set("video", { left: `${video.left - R.left - 3}px`, top: `${video.top - R.top}px`, height: `${vctl.bottom - video.top}px` });
  if (edit) set("edit", { top: `${edit.top - R.top - 3}px`, left: "0px", width: `${R.width}px` });
  if (wave) set("wave", { top: `${wave.top - R.top - 3}px`, left: "0px", width: `${R.width}px` });
  if (wave) set("tabs", { left: `${wave.left - R.left - 3}px`, top: `${wave.top - R.top}px`, height: `${wave.height}px` });
}

function relayout() {
  placeSplitters();
  if (typeof fitVideo === "function") fitVideo();
  if (typeof drawWave === "function") drawWave();
}

function startSplit(e, which) {
  e.preventDefault();
  const ed = document.querySelector(".ed"), R = ed.getBoundingClientRect();
  const h = e.currentTarget;
  h.setPointerCapture(e.pointerId);
  h.classList.add("on");
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const move = (ev) => {
    const L = EDP.layout;
    if (which === "video") L.video = Math.round(clamp(R.right - ev.clientX, 240, R.width - 420));
    if (which === "tabs") L.tabs = Math.round(clamp(ev.clientX - R.left, 150, R.width * 0.45));
    if (which === "edit") {
      const waveTop = ed.querySelector(".ed-wave").getBoundingClientRect().top;
      L.edit = Math.round(clamp(waveTop - ev.clientY, 90, R.height - L.wave - 44 - 26 - 120));
    }
    if (which === "wave") {
      const bottom = ed.querySelector(".ed-status").getBoundingClientRect().top;
      L.wave = Math.round(clamp(bottom - ev.clientY, 110, R.height - L.edit - 44 - 26 - 120));
    }
    applyEdPrefs(); relayout();
  };
  const up = () => {
    h.removeEventListener("pointermove", move); h.removeEventListener("pointerup", up);
    h.classList.remove("on"); saveEdPrefs();
  };
  h.addEventListener("pointermove", move);
  h.addEventListener("pointerup", up);
}

/* ------------------------------------------- posição na tela ({\anN}) */

const AN_RE = /^\{\\an([1-9])\}/;
function cuePos(text) { const m = AN_RE.exec(text || ""); return m ? Number(m[1]) : 2; }
function withPos(text, n) {
  const body = String(text || "").replace(AN_RE, "");
  return n === 2 ? body : `{\\an${n}}${body}`;
}
function setCuePos(i, n) {
  const c = ED.cues[i];
  if (!c) return;
  setCue(i, { text: withPos(c.text, n) }, { force: true });
  drawEdit(); tick();
}
function toggleItalic(i) {
  const c = ED.cues[i];
  if (!c) return;
  const pos = c.text.match(AN_RE)?.[0] || "", body = c.text.replace(AN_RE, "");
  const lines = body.split("\n");
  const all = lines.every((l) => /^<i>.*<\/i>$/.test(l.trim()) || !l.trim());
  const out = lines.map((l) => (all ? l.replace(/^<i>/, "").replace(/<\/i>$/, "") : l.trim() ? `<i>${l.replace(/<\/?i>/g, "")}</i>` : l));
  setCue(i, { text: pos + out.join("\n") }, { force: true });
  drawEdit(); tick();
}

function openAlign(i) {
  const cur = cuePos(ED.cues[i]?.text);
  const cell = (n) => `<button class="btn ${n === cur ? "primary" : ""}" data-an="${n}" title="{\\an${n}}">${["↙", "↓", "↘", "←", "•", "→", "↖", "↑", "↗"][n - 1]}<span class="small">${n === 2 ? "padrão" : `{\\an${n}}`}</span></button>`;
  const m = modal("Alinhamento da legenda", `
    <p class="muted small">Posição da legenda na tela, com a marca padrão do SRT ({\\an1} a {\\an9}, a mesma usada pelos editores de legenda e dos players). Embaixo no centro ({\\an2}) é o normal e não leva marca; para subir a legenda quando há texto na parte de baixo do vídeo, use em cima no centro ({\\an8}).</p>
    <div class="an-grid">${[7, 8, 9, 4, 5, 6, 1, 2, 3].map(cell).join("")}</div>`,
    `<button class="btn" data-x="close">Fechar</button>`);
  m.ov.addEventListener("click", (e) => {
    const b = e.target.closest("[data-an]");
    if (b) { setCuePos(i, Number(b.dataset.an)); m.close(); return; }
    if (e.target.closest("[data-x=close]")) m.close();
  });
}

/* --------------------------------------------------- menu do botão direito */

function edContextMenu(e) {
  const row = e.target.closest("#ed-rows tr[data-i]");
  const inText = e.target.id === "ed-txt";
  if (!row && !inText) return;
  e.preventDefault();
  const i = row ? Number(row.dataset.i) : ED.sel;
  if (row && i !== ED.sel) selectCue(i, { scrollList: false });
  const c = ED.cues[i];
  if (!c) return;
  const top = cuePos(c.text) === 8;
  closeEdMenu();
  const m = document.createElement("div");
  m.className = "menu ctx"; m.id = "ed-ctx"; m.setAttribute("role", "menu");
  m.innerHTML = `
    <button role="menuitem" data-c="top">${top ? "Voltar a legenda para baixo (tirar {\\an8})" : "Subir legenda para o topo ({\\an8})"}</button>
    <button role="menuitem" data-c="align">Alinhamento… <span class="muted small">{\\an1}–{\\an9}</span></button>
    <hr>
    <button role="menuitem" data-c="italic">Itálico <kbd>Ctrl+I</kbd></button>
    <button role="menuitem" data-c="autobr">Quebra automática</button>
    <button role="menuitem" data-c="unbreak">Juntar linhas</button>
    <hr>
    <button role="menuitem" data-c="insert">Inserir legenda na posição do vídeo</button>
    <button role="menuitem" data-c="split">Dividir</button>
    <button role="menuitem" data-c="merge">Juntar com a próxima</button>
    <button role="menuitem" data-c="copy">Copiar o texto</button>
    <hr>
    <button role="menuitem" data-c="nota">${notaDe(c) ? "Ver ou editar a anotação…" : "Anotação…"} <span class="muted small">não vai para o arquivo</span></button>
    <hr>
    <button role="menuitem" data-c="delete" class="danger">Apagar</button>`;
  document.body.appendChild(m);
  const W = window.innerWidth, H = window.innerHeight, w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = `${Math.min(e.clientX, W - w - 8)}px`; m.style.top = `${Math.min(e.clientY, H - h - 8)}px`;
  m.addEventListener("click", (ev) => {
    const a = ev.target.closest("[data-c]")?.dataset.c;
    if (!a) return;
    closeEdMenu();
    if (a === "top") setCuePos(i, top ? 2 : 8);
    else if (a === "align") openAlign(i);
    else if (a === "italic") toggleItalic(i);
    else if (a === "nota") abrirNota(i);
    else if (a === "copy") copyText(ED.cues[i].text.replace(AN_RE, "")).then((ok) => toast(ok ? "Texto copiado." : "Não consegui copiar."));
    else act(a);
  });
  setTimeout(() => document.addEventListener("pointerdown", function off(ev) {
    if (!ev.target.closest("#ed-ctx")) { closeEdMenu(); document.removeEventListener("pointerdown", off); }
  }), 0);
}
function closeEdMenu() { document.getElementById("ed-ctx")?.remove(); }
document.addEventListener("contextmenu", (e) => { if (document.body.classList.contains("editor-mode")) edContextMenu(e); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeEdMenu(); });

/* -------------------------------------------- configurações do editor */

function edPrefsHtml() {
  const P = EDP;
  const ck = (path, label) => {
    const [a, b] = path.split(".");
    return `<label class="check"><input type="checkbox" data-p="${path}" ${P[a][b] ? "checked" : ""}><span>${label}</span></label>`;
  };
  const col = (path, label, def) => {
    const [a, b] = path.split(".");
    const v = b ? P[a][b] : P[a];
    return `<label class="field colorf"><span>${label}</span><span class="row" style="gap:6px"><input type="color" data-p="${path}" value="${v || def}"><button class="btn link small" data-reset="${path}">padrão</button></span></label>`;
  };
  const num = (path, label, min, max, step = 1) => {
    const [a, b] = path.split(".");
    return `<label class="field"><span>${label}</span><input type="number" data-p="${path}" value="${P[a][b]}" min="${min}" max="${max}" step="${step}"></label>`;
  };
  return `
    <div class="prefs">
      <section><h3>Colorir problemas na lista</h3>
        ${ck("color.short", "Duração curta demais")}${ck("color.long", "Duração longa demais")}
        ${ck("color.cps", "Velocidade de leitura (CPS) acima do máximo")}${ck("color.len", "Linha longa demais")}
        ${ck("color.lines", "Mais linhas que o permitido")}${ck("color.overlap", "Sobreposição de tempos")}
        ${ck("color.gap", "Intervalo curto entre legendas")}
        ${col("errColor", "Cor dos problemas", "#f8d7d3")}
      </section>
      <section><h3>Dicas debaixo do texto</h3>
        <p class="muted small">Uma linha pequena, sem janela: só muda alguma coisa se você clicar.</p>
        ${ck("dicas.ortografia", "Corretor ortográfico (aponta e sugere; “ignorar” põe a palavra no seu dicionário)")}
        ${ck("dicas.memoria", "Memória de tradução (mostra como você já traduziu o mesmo original)")}
      </section>
      <section><h3>Legenda sobre o vídeo</h3>
        ${num("sub.size", "Tamanho (%)", 50, 200, 5)}${ck("sub.bold", "Negrito")}
      </section>
      <section><h3>Forma de onda</h3>
        <div class="grid-2">${col("wave.sel", "Onda da legenda selecionada", "#ffffff")}${col("wave.fg", "Onda", "#cfa463")}
        ${col("wave.bg", "Fundo", "#101418")}${col("wave.head", "Cursor (posição do vídeo)", "#e5484d")}</div>
        ${ck("wave.grid", "Mostrar linhas de grade")}${ck("wave.invertWheel", "Inverter a direção da roda do mouse")}
        ${ck("wave.snapShots", "Encaixar nos cortes de cena ao arrastar (segure Shift para não encaixar)")}
        ${ck("wave.cps", "Mostrar caracteres por segundo na forma de onda")}
      </section>
      <section><h3>Fonte</h3>
        <div class="grid-2">${num("font.listSize", "Lista: tamanho", 10, 20)}${num("font.textSize", "Caixa de texto: tamanho", 12, 32)}</div>
        ${ck("font.listBold", "Lista em negrito")}${ck("font.textBold", "Caixa de texto em negrito")}${ck("font.textCenter", "Centralizar o texto na caixa")}
      </section>
      <section><h3>Tamanhos das áreas</h3>
        <p class="muted small">Arraste as divisórias entre as áreas do editor (vídeo, lista, edição, forma de onda). Clique duas vezes numa divisória para voltar ao tamanho padrão.</p>
        <button class="btn" data-reset="layout">Voltar todas as áreas ao tamanho padrão</button>
      </section>
    </div>`;
}

function openEdPrefs() {
  loadEdPrefs();
  const m = modal("Configurações do editor", edPrefsHtml(), `<button class="btn" data-x="all">Restaurar tudo</button><button class="btn primary" data-x="close">Fechar</button>`, { wide: true });
  const setPath = (path, v) => { const [a, b] = path.split("."); if (b) EDP[a][b] = v; else EDP[a] = v; };
  const refresh = () => {
    applyEdPrefs(); relayout();
    if (ED.sid && document.getElementById("ed-rows")) { recheckAll(); drawRows(); drawEdit(); fitVideo(); tick(); }
    saveEdPrefs();
  };
  m.ov.addEventListener("input", (e) => {
    const p = e.target.dataset.p;
    if (!p) return;
    const v = e.target.type === "checkbox" ? e.target.checked : e.target.type === "number" ? Number(e.target.value) : e.target.value;
    setPath(p, v); refresh();
  });
  m.ov.addEventListener("click", (e) => {
    const r = e.target.closest("[data-reset]")?.dataset.reset;
    if (r === "layout") { EDP.layout = structuredClone(EDP_DEFAULT.layout); refresh(); toast("Áreas no tamanho padrão."); return; }
    if (r) { setPath(r, ""); refresh(); m.close(); openEdPrefs(); return; }
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (x === "close") m.close();
    if (x === "all" && confirm("Voltar todas as configurações do editor ao padrão?")) { EDP = structuredClone(EDP_DEFAULT); refresh(); m.close(); openEdPrefs(); }
  });
}
