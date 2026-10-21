/* Editor de legendas no layout do Subtitle Edit:
   grade (esq.) + vídeo (dir.), painel de edição + controles do vídeo,
   painel Criar/Ajustar + forma de onda, barra de status.
   Depende de app.js (api, esc, toast, fmtTC, S, every). */
"use strict";

const ED = {
  sid: null, name: "", srt: "", video: "", fps: null, duration: 0, language: "pt-BR",
  profile: null, cues: [], sel: 0, dirty: false, savedAt: "",
  undo: [], redo: [], lastSnapTs: 0, draftTimer: null,
  peaks: null, peaksRate: 100,
  wave: { start: 0, pps: 100, drag: null, hover: null },
  follow: true, tcMode: "frames", playUntil: null,
  issues: {}, raf: 0,
};

/* ---------------------------------------------------------- tempo ---- */

function edFps() { return ED.fps || 25; }
function frameOf(t) { return Math.floor(t * edFps() + 0.01); }  // tolerância: o navegador informa o início do quadro com arredondamento
function frameStart(t) { return Math.round((frameOf(t) / edFps()) * 1000) / 1000; }
function tcFrames(t) {
  const fps = edFps(), nom = Math.round(fps);
  const f = frameOf(Math.max(0, t));
  const totalSec = Math.floor(f / fps + 1e-9);
  const ff = f - Math.round(totalSec * fps);
  const h = Math.floor(totalSec / 3600), m = Math.floor(totalSec / 60) % 60, s = totalSec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}:${String(Math.max(0, Math.min(nom - 1, ff))).padStart(2, "0")}`;
}
function parseTC(str) {
  const m = String(str).trim().match(/^(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})$/);
  if (!m) return null;
  return (Number(m[1] || 0) * 3600) + Number(m[2]) * 60 + Number(m[3]) + Number(m[4].padEnd(3, "0")) / 1000;
}
const r3 = (x) => Math.round(x * 1000) / 1000;
const fmtSec = (x) => (Math.round(x * 1000) / 1000).toFixed(3).replace(".", ",");

/* --------------------------------------------------------- regras ---- */

function visLen(s) { return s.replace(/<[^>]+>|\{[^}]*\}/g, "").length; }
function cueStats(c) {
  const lines = c.text.split("\n").filter((l) => l.trim());
  const flat = lines.join(" ");
  const dur = c.end - c.start;
  const chars = visLen(flat);
  return { lines, dur, chars, cps: dur > 0 ? chars / dur : 0, maxLine: Math.max(0, ...lines.map(visLen)) };
}
function checkCue(i) {
  const p = ED.profile, c = ED.cues[i], st = cueStats(c), out = [];
  if (!st.lines.length) out.push(["e", "sem texto"]);
  if (c.end <= c.start) out.push(["e", "fim antes do início"]);
  if (st.lines.length > p.max_lines) out.push(["e", `${st.lines.length} linhas`]);
  if (st.maxLine > p.max_chars_per_line) out.push(["e", `linha com ${st.maxLine} caracteres`]);
  if (st.cps > p.max_cps + 0.05) out.push(["w", `${st.cps.toFixed(1).replace(".", ",")} CPS`]);
  if (st.dur > 0 && st.dur < p.min_duration - 0.001) out.push(["w", "curta"]);
  if (st.dur > p.max_duration + 0.001) out.push(["w", "longa"]);
  const next = ED.cues[i + 1];
  if (next) {
    const gap = next.start - c.end;
    if (gap < -0.0005) out.push(["e", "sobrepõe a próxima"]);
    else if (gap < minGap() - 0.001) out.push(["w", "intervalo curto"]);
  }
  if (profChecks(p).size) styleChecks(c.text || "", out);
  return out;
}
function recheckAll() {
  ED.issues = {};
  ED.cues.forEach((_, i) => { const r = checkCue(i); if (r.length) ED.issues[i] = r; });
}

/* ------------------------------------------------- histórico/salvar ---- */

function snapshot(force = false) {
  const now = Date.now();
  if (!force && now - ED.lastSnapTs < 900) return;
  ED.lastSnapTs = now;
  ED.undo.push(JSON.stringify({ cues: ED.cues, sel: ED.sel }));
  if (ED.undo.length > 200) ED.undo.shift();
  ED.redo = [];
}
function restore(stackFrom, stackTo) {
  if (!stackFrom.length) return;
  stackTo.push(JSON.stringify({ cues: ED.cues, sel: ED.sel }));
  const st = JSON.parse(stackFrom.pop());
  ED.cues = st.cues; ED.sel = Math.min(st.sel, ED.cues.length - 1);
  changed(false);
  drawAll();
}
function changed(snap = true, which = null) {
  ED.dirty = true;
  if (which == null) recheckAll();
  else {
    for (const i of [which - 1, which, which + 1]) {
      if (i < 0 || i >= ED.cues.length) continue;
      const r = checkCue(i); if (r.length) ED.issues[i] = r; else delete ED.issues[i];
    }
  }
  clearTimeout(ED.draftTimer);
  ED.draftTimer = setTimeout(() => {
    if (ED.sid) api("PUT", `/api/editor/${ED.sid}/draft`, { cues: ED.cues }).catch(() => {});
  }, 2000);
  drawStatus();
}
async function save(asNew = false) {
  try {
    let path = null;
    if (asNew || !ED.srt) {
      const base = (ED.video || ED.name).split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
      const folder = (ED.srt || ED.video).replace(/[\\/][^\\/]*$/, "");
      const { paths } = await api("POST", "/api/dialog", { kind: "save_srt", initial: folder, filename: `${base}.srt` });
      if (!paths.length) return;
      path = paths[0];
    }
    const r = await api("POST", `/api/editor/${ED.sid}/save`, { cues: sortedCues(), path });
    ED.srt = r.path; ED.name = r.name; ED.dirty = false; ED.savedAt = r.saved_at;
    document.getElementById("ed-name").textContent = r.name;
    drawStatus();
    toast(`Legenda salva (${r.count} legendas).`);
  } catch (e) { toast(e.message, true); }
}
function sortedCues() {
  const selCue = ED.cues[ED.sel];
  ED.cues.sort((a, b) => a.start - b.start);
  ED.sel = Math.max(0, ED.cues.indexOf(selCue));
  return ED.cues;
}

/* ============================================================ montar */

async function renderEditor(sid) {
  document.body.classList.add("editor-mode");
  if (!sid) return renderHome();
  let data;
  try { data = await api("GET", `/api/editor/${sid}?full=1`); }
  catch (e) {
    main.innerHTML = `<div class="panel" style="margin:32px"><p class="note err">${esc(e.message)}</p><p style="margin-top:12px"><a class="btn" href="#/editor">Abrir uma legenda</a></p></div>`;
    return;
  }
  Object.assign(ED, {
    sid, name: data.name, srt: data.srt, video: data.video, fps: data.fps, duration: data.duration || 0,
    language: data.language, profile: data.profile, cues: data.cues.slice().sort((a, b) => a.start - b.start),
    sel: 0, dirty: false, undo: [], redo: [], peaks: null, savedAt: "", playUntil: null,
    hasVideo: data.has_video, hasAudio: data.has_audio,
    detected: data.detected, suggested: data.suggested_target,
    clientId: data.client_id || null, shots: data.shots || null, itemId: data.item_id || null, lastAct: Date.now(),
  });
  ED.hasOrig = ED.cues.some((c) => c.orig != null);
  ED.wave.start = 0;
  if (!ED.duration && ED.cues.length) ED.duration = ED.cues[ED.cues.length - 1].end + 5;
  recheckAll();
  await loadState();
  if (!S.projects?.length) { try { await loadProjects(); } catch {} }
  const clients = S.projects || [];

  main.innerHTML = `
  <div class="ed">
    <header class="ed-tool">
      <a class="btn ghost" href="${data.obra_id ? `#/obra/${data.obra_id}` : "#/inicio"}" id="ed-back" title="${data.obra_id ? "Voltar ao projeto" : "Voltar ao início"}">‹ ${data.obra_id ? "Projeto" : "Início"}</a>
      <span class="ed-title" id="ed-name" title="${esc(ED.srt || ED.video)}">${esc(ED.name)}</span>
      <span class="sep"></span>
      <button class="btn ghost opt" data-ed="open">Abrir</button>
      <button class="btn ghost" data-ed="save" title="Ctrl+S">Salvar</button>
      <button class="btn ghost opt" data-ed="saveas" title="Ctrl+Shift+S">Salvar como</button>
      <span class="sep"></span>
      <span class="splitbtn">
        <button class="btn primary" data-ed="translate-quick" id="ed-trq" title="Traduzir a legenda inteira">Traduzir para ${esc(shortLang(ED.suggested || "es-419"))}</button><button class="btn primary caret" data-ed="translate" title="Opções da tradução (idiomas, método)" aria-label="Opções da tradução">▾</button>
      </span>
      <span class="menuwrap">
        <button class="btn" data-ed="syncmenu" aria-haspopup="true" aria-expanded="false">Sincronizar ▾</button>
        <div class="menu" id="ed-syncmenu" role="menu" hidden>
          <button role="menuitem" data-sy="audio"><b>Automática pela fala do vídeo</b><span>Encaixa a legenda inteira no áudio. Sem custo.</span></button>
          <button role="menuitem" data-sy="ref"><b>Pela legenda de referência…</b><span>Usa outra legenda com o tempo certo (outro idioma serve).</span></button>
          <button role="menuitem" data-sy="copy"><b>Copiar os tempos de outra legenda…</b><span>Mesma quantidade de legendas, tempo a tempo.</span></button>
          <hr>
          <button role="menuitem" data-sy="shift"><b>Atrasar ou adiantar…</b><span>Tudo, ou a partir da legenda selecionada.</span></button>
          <button role="menuitem" data-sy="twopoint"><b>Por dois pontos…</b><span>Acerte a primeira e a última fala; o resto acompanha.</span></button>
          <button role="menuitem" data-sy="fps"><b>Converter quadros por segundo…</b><span>Legenda feita para 25, vídeo em 23,976 etc.</span></button>
          <hr>
          <button role="menuitem" data-sy="shots"><b>Encaixar nos cortes de cena</b><span>${ED.shots ? `${ED.shots.length} cortes já encontrados.` : "Procura os cortes no vídeo e ajusta entradas e saídas."}</span></button>
          <button role="menuitem" data-sy="script"><b>Texto sem tempo (roteiro)…</b><span>Transforma um .txt/.docx em legenda sincronizada (transcrição pela API).</span></button>
        </div>
      </span>
      <button class="btn" data-ed="verify" title="Problemas e correção automática">Verificar <span class="count" id="ed-issn" hidden></span></button>
      <button class="btn" data-ed="deliver" title="Salvar com o nome do cliente, assinatura e verificação final">Entregar</button>
      <span class="sep"></span>
      <button class="btn ghost icon" data-ed="undo" title="Desfazer (Ctrl+Z)" aria-label="Desfazer">↶</button>
      <button class="btn ghost icon" data-ed="redo" title="Refazer (Ctrl+Y)" aria-label="Refazer">↷</button>
      <button class="btn ghost icon" data-ed="find" title="Localizar e substituir (Ctrl+F)" aria-label="Localizar e substituir">🔍︎</button>
      <span class="sep"></span>
      <label class="ed-inline">Cliente
        <select id="ed-client"><option value="">Nenhum</option>${clients.map((p) => `<option value="${p.id}" ${String(p.id) === String(ED.clientId) ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>
      </label>
      <label class="ed-inline muted">Regras
        <select id="ed-profile">${S.state.profiles.map((p) => `<option value="${esc(p.key)}" ${p.key === ED.profile.key ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>
      </label>
      <button class="btn ghost ed-help" data-ed="help" title="Atalhos">?</button>
    </header>

    <section class="ed-list" id="ed-list" tabindex="0" aria-label="Legendas">
      <table class="grid"><thead><tr><th class="c-n">#</th><th class="c-t">Início</th><th class="c-t">Fim</th><th class="c-d">Duração</th><th class="c-c">CPS</th><th>Texto</th>${ED.hasOrig ? "<th>Original</th>" : ""}</tr></thead><tbody id="ed-rows"></tbody></table>
    </section>

    <section class="ed-video">
      <div class="vbox" id="vbox">
        <div class="vfit" id="vfit">
          <video id="ed-v" preload="auto" playsinline></video>
          <div class="vsub" id="ed-sub"></div>
        </div>
        <div class="vmsg" id="ed-vmsg" hidden></div>
      </div>
    </section>

    <section class="ed-edit">
      <div class="ed-times">
        <label>Início<input type="text" id="ed-start" class="tnum" spellcheck="false"></label>
        <label>Duração<input type="text" id="ed-dur" class="tnum" spellcheck="false"></label>
        <div class="row" style="gap:6px">
          <button class="btn" data-ed="prev" title="Alt+↑">‹ Anterior</button>
          <button class="btn" data-ed="next" title="Alt+↓">Próxima ›</button>
        </div>
      </div>
      <div class="ed-text">
        <div class="ed-orig" id="ed-orig" ${ED.hasOrig ? "" : "hidden"}><span class="muted small">Original</span><div id="ed-origtxt"></div></div>
        <div class="ed-text-head"><span>${ED.hasOrig ? "Tradução" : "Texto"}</span><span id="ed-cps" class="tnum"></span></div>
        <textarea id="ed-txt" spellcheck="true" lang="${esc(ED.language)}"></textarea>
        <div class="ed-text-foot"><span id="ed-linelen" class="tnum"></span><span id="ed-total" class="tnum"></span></div>
      </div>
      <div class="ed-side-btns">
        <button class="btn" data-ed="unbreak">Juntar linhas</button>
        <button class="btn" data-ed="autobr">Quebra automática</button>
        <button class="btn" data-ed="split" title="Divide na posição do vídeo">Dividir</button>
        <button class="btn" data-ed="merge">Juntar com a próxima</button>
        <button class="btn danger" data-ed="delete" title="Delete na lista">Apagar</button>
      </div>
    </section>

    <section class="ed-vctl">
      <input type="range" id="ed-seek" min="0" max="1000" value="0" step="1" aria-label="Posição do vídeo">
      <div class="row ed-trans">
        <button class="btn icon" data-ed="fback" title="Quadro anterior (←)" aria-label="Quadro anterior">⏮</button>
        <button class="btn icon primary" data-ed="play" id="ed-play" title="Tocar/pausar (Espaço)" aria-label="Tocar">▶</button>
        <button class="btn icon" data-ed="stop" title="Parar" aria-label="Parar">■</button>
        <button class="btn icon" data-ed="ffwd" title="Próximo quadro (→)" aria-label="Próximo quadro">⏭</button>
        <select id="ed-rate" title="Velocidade" aria-label="Velocidade">
          ${[0.5, 0.75, 1, 1.25, 1.5, 2].map((r) => `<option value="${r}" ${r === 1 ? "selected" : ""}>${String(r).replace(".", ",")}×</option>`).join("")}
        </select>
        <input type="range" id="ed-vol" min="0" max="1" step="0.05" value="1" aria-label="Volume" title="Volume">
        <span class="sep"></span>
        <button class="btn link tnum ed-tc" id="ed-tc" data-ed="tcmode" title="Alternar quadros/milissegundos">00:00:00:00</button>
        <span class="muted tnum" id="ed-tcdur"></span>
      </div>
      <div class="muted small tnum" id="ed-frameinfo"></div>
    </section>

    <aside class="ed-tabs">
      <div class="tabs" role="tablist">
        <button role="tab" aria-selected="true" data-tab="criar">Criar</button>
        <button role="tab" aria-selected="false" data-tab="ajustar">Ajustar</button>
      </div>
      <div class="tabpane" id="tab-criar">
        <button class="btn" data-ed="insert" title="Insert">Inserir legenda na posição do vídeo</button>
        <button class="btn" data-ed="playfrom">Tocar a partir da legenda</button>
        <button class="btn" data-ed="goto">Ir para a legenda e pausar</button>
        <button class="btn" data-ed="setstart" title="F11 ou [">Marcar início <kbd>F11</kbd></button>
        <button class="btn" data-ed="setend" title="F12 ou ]">Marcar fim <kbd>F12</kbd></button>
        <div class="jump"><button class="btn" data-ed="j-0.5">«</button><span>0,5 s</span><button class="btn" data-ed="j+0.5">»</button></div>
        <div class="jump"><button class="btn" data-ed="j-5">«</button><span>5 s</span><button class="btn" data-ed="j+5">»</button></div>
      </div>
      <div class="tabpane" id="tab-ajustar" hidden>
        <label class="small">Deslocar a partir da legenda selecionada (ms)<input type="number" id="ed-shift" value="100" step="10"></label>
        <div class="jump"><button class="btn" data-ed="shift-">Antes</button><button class="btn" data-ed="shift+">Depois</button></div>
        <button class="btn" data-ed="snap">Encaixar tudo nos quadros</button>
        <button class="btn" data-ed="nextissue" title="F8">Ir ao próximo problema <kbd>F8</kbd></button>
      </div>
    </aside>

    <section class="ed-wave">
      <div class="wave-top">
        <label class="small row" style="gap:6px"><input type="checkbox" id="ed-follow" checked> Selecionar a legenda atual durante a reprodução</label>
        <span class="muted small" id="ed-wavemsg"></span>
      </div>
      <canvas id="ed-canvas" tabindex="0" aria-label="Forma de onda"></canvas>
      <div class="wave-foot">
        <button class="btn icon" data-ed="zout" aria-label="Diminuir zoom">−</button>
        <select id="ed-zoom" aria-label="Zoom">${[25, 50, 75, 100, 150, 200, 300, 400].map((z) => `<option value="${z}" ${z === 100 ? "selected" : ""}>${z}%</option>`).join("")}</select>
        <button class="btn icon" data-ed="zin" aria-label="Aumentar zoom">+</button>
        <button class="btn icon" data-ed="playsel" title="Tocar só a legenda selecionada" aria-label="Tocar legenda">▶</button>
        <input type="range" id="ed-wscroll" min="0" max="1000" value="0" aria-label="Rolar forma de onda">
      </div>
    </section>

    <footer class="ed-status" id="ed-status"></footer>
  </div>`;

  bindEditor();
  if (ED.itemId) {   // tempo trabalhado no episódio: conta a cada minuto com atividade
    every(60000, () => {
      const v = vid();
      const active = Date.now() - ED.lastAct < 90000 || (v && !v.paused);
      if (active && ED.sid) api("POST", `/api/editor/${ED.sid}/beat`, { seconds: 60 }).catch(() => {});
    });
  }
  setupVideo(data.media);
  loadPeaks();
  drawAll();
  selectCue(0, { seek: false });
  if (typeof PENDING_TRANSLATE !== "undefined" && PENDING_TRANSLATE) {
    const o = PENDING_TRANSLATE; PENDING_TRANSLATE = null;
    setTimeout(() => openTranslate({ project_id: ED.clientId, ...o }), 50);
  }
  if (typeof PENDING_SCRIPT !== "undefined" && PENDING_SCRIPT) {
    const p = PENDING_SCRIPT; PENDING_SCRIPT = "";
    setTimeout(() => openScript(p), 50);
  }
}

/* ---------------------------------------------------- abrir arquivos */

async function renderEditorOpen() {
  document.body.classList.remove("editor-mode");
  await loadState();
  const st = { srt: "", video: "" };
  main.innerHTML = `
    <div class="page-head"><div><h1>Editor de legendas</h1><p class="muted">Abra uma legenda .srt com o vídeo para revisar e ajustar no quadro exato.</p></div></div>
    <section class="panel stack" style="max-width:760px">
      <label class="field"><span>Legenda (.srt)</span>
        <div class="row" style="flex-wrap:nowrap"><input type="text" id="o-srt" placeholder="Deixe vazio para começar uma legenda nova"><button class="btn" data-o="srt">Escolher</button></div></label>
      <label class="field"><span>Vídeo ou áudio</span>
        <div class="row" style="flex-wrap:nowrap"><input type="text" id="o-video" placeholder="C:\\Videos\\Episódio 01.mp4"><button class="btn" data-o="video">Escolher</button></div></label>
      <label class="field"><span>Perfil de regras</span>
        <select id="o-profile"><option value="">Automático (pelo idioma da legenda)</option>${S.state.profiles.map((p) => `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join("")}</select></label>
      <div><button class="btn primary" data-o="go">Abrir no editor</button></div>
    </section>`;
  main.onclick = async (e) => {
    const b = e.target.closest("[data-o]");
    if (!b) return;
    try {
      if (b.dataset.o === "srt" || b.dataset.o === "video") {
        const { paths } = await api("POST", "/api/dialog", { kind: b.dataset.o === "srt" ? "subtitle" : "media" });
        if (paths[0]) {
          document.getElementById(`o-${b.dataset.o}`).value = paths[0];
          if (b.dataset.o === "video" && !document.getElementById("o-srt").value) {
            const guess = paths[0].replace(/\.[^.\\/]+$/, ".srt");
            const { files } = await api("POST", "/api/inspect", { paths: [guess] });
            if (files[0]?.exists) document.getElementById("o-srt").value = guess;
          }
        }
      }
      if (b.dataset.o === "go") {
        const srt = document.getElementById("o-srt").value.trim().replace(/^"|"$/g, "");
        const video = document.getElementById("o-video").value.trim().replace(/^"|"$/g, "");
        const r = await api("POST", "/api/editor/open", { srt, video, profile_key: document.getElementById("o-profile").value });
        location.hash = `#/editor/${r.sid}`;
      }
    } catch (err) { toast(err.message, true); }
  };
}

/* ============================================================== vídeo */

function vid() { return document.getElementById("ed-v"); }
function curTime() { return ED.vt ?? vid()?.currentTime ?? 0; }

function setupVideo(media) {
  const v = vid(), msg = document.getElementById("ed-vmsg");
  const show = (html) => { msg.hidden = false; msg.innerHTML = html; };
  if (!ED.video) { show("Sem vídeo. Abra o vídeo junto com a legenda para ver a imagem e a forma de onda."); msg.classList.add("novideo"); return; }
  const apply = (m) => {
    if (m.status === "pronto") {
      msg.hidden = true;
      if (!v.src) v.src = m.url;
      return true;
    }
    if (m.status === "erro") { show(esc(m.error)); return true; }
    show(`Preparando o vídeo para a pré-visualização… <b class="tnum">${Math.round(m.progress * 100)}%</b><br><span class="small">Este formato não toca direto no navegador. A cópia é feita uma vez e reaproveitada.</span>`);
    return false;
  };
  if (!apply(media)) {
    const tid = every(1000, async () => {
      try { const d = await api("GET", `/api/editor/${ED.sid}`); if (apply(d.media)) clearInterval(tid); } catch {}
    });
  }
  v.addEventListener("loadedmetadata", () => {
    if (!ED.duration || Math.abs(ED.duration - v.duration) > 1) ED.duration = v.duration;
    fitVideo(); drawAll();
  });
  v.addEventListener("play", () => { document.getElementById("ed-play").textContent = "❚❚"; loop(); });
  v.addEventListener("pause", () => { document.getElementById("ed-play").textContent = "▶"; ED.playUntil = null; tick(); });
  v.addEventListener("seeked", () => tick());
  v.addEventListener("error", () => show("O navegador não conseguiu tocar este vídeo."));
  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    const cb = (_, meta) => { ED.vt = meta.mediaTime; tick(true); v.requestVideoFrameCallback(cb); };
    v.requestVideoFrameCallback(cb);
  }
  new ResizeObserver(fitVideo).observe(document.getElementById("vbox"));
}

function fitVideo() {
  const box = document.getElementById("vbox"), fit = document.getElementById("vfit"), v = vid();
  if (!box || !fit) return;
  const W = box.clientWidth, H = box.clientHeight;
  const ar = v && v.videoWidth ? v.videoWidth / v.videoHeight : 16 / 9;
  let w = W, h = W / ar;
  if (h > H) { h = H; w = H * ar; }
  fit.style.width = `${w}px`; fit.style.height = `${h}px`;
  fit.style.setProperty("--subsize", `${Math.max(12, h * 0.055)}px`);
}

function loop() {
  cancelAnimationFrame(ED.raf);
  const step = () => {
    const v = vid();
    if (!v || v.paused) return;
    if (!("requestVideoFrameCallback" in HTMLVideoElement.prototype)) { ED.vt = v.currentTime; tick(true); }
    if (ED.playUntil != null && v.currentTime >= ED.playUntil) { v.pause(); ED.playUntil = null; }
    ED.raf = requestAnimationFrame(step);
  };
  ED.raf = requestAnimationFrame(step);
}

function seek(t, opts = {}) {
  const v = vid();
  t = Math.max(0, Math.min(ED.duration || t, t));
  ED.vt = t;
  if (v && v.src && v.readyState > 0) v.currentTime = t;
  if (opts.center) centerWave(t);
  tick();
}

function stepFrame(n) {
  const v = vid();
  if (v && !v.paused) v.pause();
  const f = frameOf(curTime()) + n;
  seek((f + 0.5) / edFps());  // meio do quadro: o navegador mostra exatamente esse quadro
}

/* tick: atualiza timecode, legenda sobre o vídeo, playhead e seleção ao vivo */
function tick(fromVideo = false) {
  const t = curTime();
  const tc = document.getElementById("ed-tc");
  if (!tc) return;
  tc.textContent = ED.tcMode === "frames" ? tcFrames(t) : fmtTC(t);
  document.getElementById("ed-tcdur").textContent = `/ ${ED.tcMode === "frames" ? tcFrames(ED.duration) : fmtTC(ED.duration)}`;
  document.getElementById("ed-frameinfo").textContent = ED.fps
    ? `Quadro ${frameOf(t).toLocaleString("pt-BR")} · ${String(Math.round(ED.fps * 1000) / 1000).replace(".", ",")} fps · ${fmtTC(t)}`
    : fmtTC(t);
  const seekEl = document.getElementById("ed-seek");
  if (seekEl && document.activeElement !== seekEl && ED.duration) seekEl.value = String(Math.round((t / ED.duration) * 1000));
  // legenda sobre o vídeo
  const active = ED.cues.filter((c) => c.start <= t + 1e-4 && t < c.end);
  const sub = document.getElementById("ed-sub");
  const rendered = active.map((c) => renderSubHtml(c.text));
  const html = rendered.map((r) => `<div class="cue">${r.html}</div>`).join("");
  if (sub.innerHTML !== html) sub.innerHTML = html;
  sub.classList.toggle("top", rendered.some((r) => r.top));
  // seguir a reprodução
  const v = vid();
  if (fromVideo && v && !v.paused) {
    if (ED.follow && active.length) {
      const i = ED.cues.indexOf(active[0]);
      if (i !== ED.sel) selectCue(i, { seek: false, scrollWave: false, focusText: false });
    }
    const span = waveSpan();
    if (t > ED.wave.start + span * 0.92 || t < ED.wave.start) { ED.wave.start = Math.max(0, t - span * 0.08); }
  }
  drawWave();
}

/* ============================================================ seleção */

function selectCue(i, opts = {}) {
  if (!ED.cues.length) { ED.sel = 0; drawEdit(); drawStatus(); return; }
  ED.sel = Math.max(0, Math.min(ED.cues.length - 1, i));
  const c = ED.cues[ED.sel];
  document.querySelectorAll("#ed-rows tr.on").forEach((tr) => tr.classList.remove("on"));
  const row = document.querySelector(`#ed-rows tr[data-i="${ED.sel}"]`);
  if (row) { row.classList.add("on"); if (opts.scrollList !== false) row.scrollIntoView({ block: "nearest" }); }
  drawEdit();
  if (opts.seek !== false) { const v = vid(); if (v && !v.paused) v.pause(); seek(c.start + 0.001); }
  if (opts.scrollWave !== false) {
    const span = waveSpan();
    if (c.start < ED.wave.start || c.end > ED.wave.start + span) ED.wave.start = Math.max(0, c.start - span * 0.15);
  }
  if (opts.focusText) document.getElementById("ed-txt").focus();
  drawWave(); drawStatus();
}

/* ============================================================== grade */

function rowHtml(c, i) {
  const st = cueStats(c), iss = ED.issues[i] || [];
  const durBad = iss.some(([, m]) => m === "curta" || m === "longa");
  const cpsBad = st.cps > ED.profile.max_cps + 0.05;
  const txtBad = iss.some(([k, m]) => k === "e" && /linha|sem texto/.test(m));
  const timeBad = iss.some(([, m]) => /sobrepõe|fim antes|intervalo/.test(m));
  return `<tr data-i="${i}" class="${i === ED.sel ? "on" : ""}">
    <td class="c-n">${i + 1}</td>
    <td class="c-t tnum">${fmtTC(c.start)}</td>
    <td class="c-t tnum ${timeBad ? "bad" : ""}">${fmtTC(c.end)}</td>
    <td class="c-d tnum ${durBad ? "bad" : ""}">${fmtSec(st.dur)}</td>
    <td class="c-c tnum ${cpsBad ? "bad" : ""}">${st.cps.toFixed(1).replace(".", ",")}</td>
    <td class="c-x ${txtBad ? "bad" : ""}">${st.lines.map(esc).join('<i class="br"> | </i>') || '<i class="muted">vazia</i>'}</td>
    ${ED.hasOrig ? `<td class="c-o">${c.orig != null ? c.orig.split("\n").map(esc).join('<i class="br"> | </i>') : ""}</td>` : ""}
  </tr>`;
}
function drawRows() {
  const tb = document.getElementById("ed-rows");
  if (!tb) return;
  tb.innerHTML = ED.cues.length ? ED.cues.map(rowHtml).join("")
    : `<tr><td colspan="${ED.hasOrig ? 7 : 6}" class="muted" style="padding:16px">Nenhuma legenda. Toque o vídeo e use “Inserir legenda na posição do vídeo” (tecla Insert).</td></tr>`;
}
function updateRow(i) {
  const tr = document.querySelector(`#ed-rows tr[data-i="${i}"]`);
  if (!tr) return;
  const tmp = document.createElement("tbody");
  tmp.innerHTML = rowHtml(ED.cues[i], i);
  tr.replaceWith(tmp.firstElementChild);
}

/* =============================================================== edição */

function drawEdit() {
  const c = ED.cues[ED.sel];
  const s = document.getElementById("ed-start"), d = document.getElementById("ed-dur"), t = document.getElementById("ed-txt");
  if (!s) return;
  const dis = !c;
  [s, d, t].forEach((x) => (x.disabled = dis));
  if (!c) { s.value = d.value = t.value = ""; document.getElementById("ed-cps").textContent = ""; return; }
  if (document.activeElement !== s) s.value = fmtTC(c.start);
  if (document.activeElement !== d) d.value = fmtSec(c.end - c.start);
  if (document.activeElement !== t) t.value = c.text;
  const o = document.getElementById("ed-origtxt");
  if (o) o.innerHTML = c.orig != null ? c.orig.split("\n").map((l) => `<div>${esc(l)}</div>`).join("") : '<i class="muted small">sem original para esta legenda</i>';
  drawTextStats();
}
function drawTextStats() {
  const c = ED.cues[ED.sel];
  if (!c) return;
  const st = cueStats(c), p = ED.profile;
  const cps = document.getElementById("ed-cps");
  cps.textContent = `CPS: ${st.cps.toFixed(2).replace(".", ",")} / ${String(p.max_cps).replace(".", ",")}`;
  cps.className = "tnum " + (st.cps > p.max_cps + 0.05 ? "bad" : "");
  const ll = document.getElementById("ed-linelen");
  ll.innerHTML = "Linhas: " + (st.lines.length ? st.lines.map((l) => {
    const n = visLen(l); return `<span class="${n > p.max_chars_per_line ? "bad" : ""}">${n}</span>`;
  }).join(" / ") : "0") + ` <span class="muted">(máx. ${p.max_chars_per_line})</span>`;
  ll.className = "tnum" + (st.lines.length > p.max_lines ? " bad" : "");
  document.getElementById("ed-total").textContent = `Total: ${st.chars}`;
}

function setCue(i, patch, opts = {}) {
  snapshot(opts.force);
  Object.assign(ED.cues[i], patch);
  if (patch.start !== undefined || patch.end !== undefined) {
    ED.cues[i].start = r3(Math.max(0, ED.cues[i].start));
    ED.cues[i].end = r3(Math.max(ED.cues[i].start + 0.001, ED.cues[i].end));
  }
  changed(false, i);
  updateRow(i); if (i > 0) updateRow(i - 1); if (i + 1 < ED.cues.length) updateRow(i + 1);
  if (opts.edit !== false) drawEdit(); else drawTextStats();
  drawWave(); tick();
}

function minGap() {
  const p = ED.profile;
  return p.min_gap_ms ? p.min_gap_ms / 1000 : p.min_gap_frames / edFps();
}
/* Avisos de estilo do manual do cliente (mesmas regras de core/style.py, versão rápida). */
const INTERJ = /(^|[^\p{L}])(woo hoo|ah|ay|ey|oye|eh|ih|oh|ei|ui|uau|psiu|oba|eba|epa|opa|ufa|hey)(?![\p{L}])/iu;
/* verificações ligadas pelas regras ativas do perfil (perfis antigos: style_checks liga todas) */
const ALL_CHECKS = ["interjeicao", "pontuacao_dupla", "reticencias", "travessao", "repeticao", "abertura", "localizacao", "dois_pontos", "numero"];
function profChecks(p) {
  if (p._checks && p._checksSrc === p.rules) return p._checks;
  const set = p.rules?.length ? new Set(p.rules.filter((r) => r.active !== false && r.check).map((r) => r.check))
    : new Set(p.style_checks ? ALL_CHECKS : []);
  Object.defineProperty(p, "_checks", { value: set, writable: true, enumerable: false, configurable: true });
  Object.defineProperty(p, "_checksSrc", { value: p.rules, writable: true, enumerable: false, configurable: true });
  return set;
}
function styleChecks(text, out) {
  const p = ED.profile, on = profChecks(p), plain = text.replace(/<[^>]+>|\{\\[^}]*\}/g, "");
  const lines = plain.split("\n").filter((l) => l.trim());
  if (on.has("interjeicao") && INTERJ.test(plain)) out.push(["w", "interjeição"]);
  if (on.has("pontuacao_dupla") && /\?\?|!!|\?!|!\?|¿¡|¡¿/.test(plain)) out.push(["w", "pontuação dupla"]);
  if (on.has("reticencias") && p.ellipsis === "..." && plain.includes("…")) out.push(["w", "use ... (três pontos)"]);
  if (on.has("travessao") && p.dialogue_dash === "-" && lines.some((l) => /^\s*[-–—]\s+\S/.test(l))) out.push(["w", "hífen sem espaço"]);
  if (on.has("repeticao") && /(^|[^\p{L}])(\p{L}{2,})[,.!?]*\s+\2(?![\p{L}])/iu.test(plain)) out.push(["w", "palavra repetida"]);
}

function act(name) {
  const v = vid(), c = ED.cues[ED.sel], t = curTime(), i = ED.sel;
  switch (name) {
    case "play": if (!v?.src) return; v.paused ? v.play() : v.pause(); break;
    case "stop": if (v) { v.pause(); seek(c ? c.start : 0); } break;
    case "fback": stepFrame(-1); break;
    case "ffwd": stepFrame(1); break;
    case "prev": selectCue(i - 1); break;
    case "next": selectCue(i + 1); break;
    case "undo": restore(ED.undo, ED.redo); break;
    case "redo": restore(ED.redo, ED.undo); break;
    case "save": save(false); break;
    case "saveas": save(true); break;
    case "open":
      if (ED.dirty && !confirm("Há alterações não salvas. Abrir outro arquivo mesmo assim?")) return;
      ED.dirty = false; location.hash = "#/inicio"; break;
    case "tcmode": ED.tcMode = ED.tcMode === "frames" ? "ms" : "frames"; tick(); break;
    case "insert": {
      snapshot(true);
      const start = frameStart(t);
      let k = ED.cues.findIndex((x) => x.start > start);
      if (k < 0) k = ED.cues.length;
      const nextStart = ED.cues[k]?.start ?? Infinity;
      const end = Math.min(start + 2, nextStart - minGap());
      if (end - start < 0.2) { toast("Não há espaço livre aqui para uma nova legenda.", true); return; }
      ED.cues.splice(k, 0, { start: r3(start), end: r3(end), text: "" });
      changed(false); drawRows(); selectCue(k, { seek: false, focusText: true });
      break;
    }
    case "delete": {
      if (!c) return;
      snapshot(true); ED.cues.splice(i, 1); changed(false); drawRows(); selectCue(Math.min(i, ED.cues.length - 1), { seek: false });
      break;
    }
    case "split": {
      if (!c) return;
      const at = t > c.start + 0.1 && t < c.end - 0.1 ? frameStart(t) : r3((c.start + c.end) / 2);
      const words = c.text.replace(/\n/g, " ").split(/\s+/).filter(Boolean);
      const k = Math.max(1, Math.round(words.length * (at - c.start) / (c.end - c.start)));
      snapshot(true);
      const second = { start: r3(at + minGap()), end: c.end, text: words.slice(k).join(" ") };
      c.end = r3(at); c.text = words.slice(0, k).join(" ");
      ED.cues.splice(i + 1, 0, second);
      changed(false); drawRows(); selectCue(i, { seek: false });
      break;
    }
    case "merge": {
      const n = ED.cues[i + 1];
      if (!c || !n) return;
      snapshot(true);
      c.end = n.end; c.text = (c.text.replace(/\n/g, " ") + " " + n.text.replace(/\n/g, " ")).trim();
      ED.cues.splice(i + 1, 1);
      changed(false); drawRows(); selectCue(i, { seek: false });
      break;
    }
    case "unbreak": if (c) setCue(i, { text: c.text.replace(/\s*\n\s*/g, " ") }, { force: true }); break;
    case "autobr":
      if (!c) return;
      api("POST", "/api/editor/rewrap", { text: c.text, profile_key: ED.profile.key, language: ED.profile.language })
        .then((r) => setCue(i, { text: r.text }, { force: true })).catch((e) => toast(e.message, true));
      break;
    case "playfrom": if (c && v?.src) { seek(c.start); v.play(); } break;
    case "goto": if (c) { v?.pause(); seek(c.start, { center: true }); } break;
    case "playsel": if (c && v?.src) { seek(c.start); ED.playUntil = c.end; v.play(); } break;
    case "setstart": {
      if (!c) return;
      const ns = frameStart(t);
      const prev = ED.cues[i - 1];
      if (prev && ns < prev.end + minGap() - 1e-6 && prev.end > ns - 5) setCue(i - 1, { end: Math.max(prev.start + 0.04, ns - minGap()) }, { force: true });
      const dur = c.end - c.start;
      setCue(i, { start: ns, end: c.end > ns + 0.2 ? c.end : ns + dur }, { force: true });
      break;
    }
    case "setend": {
      if (!c) return;
      const ne = frameStart(t);
      if (ne <= c.start) { toast("O fim precisa ficar depois do início.", true); return; }
      setCue(i, { end: ne }, { force: true });
      if (v && !v.paused && ED.cues[i + 1]) selectCue(i + 1, { seek: false });
      break;
    }
    case "j-0.5": seek(t - 0.5); break;
    case "j+0.5": seek(t + 0.5); break;
    case "j-5": seek(t - 5); break;
    case "j+5": seek(t + 5); break;
    case "shift-": case "shift+": {
      const ms = Number(document.getElementById("ed-shift").value) || 0;
      const d = (name === "shift-" ? -ms : ms) / 1000;
      snapshot(true);
      for (let k = i; k < ED.cues.length; k++) { ED.cues[k].start = r3(Math.max(0, ED.cues[k].start + d)); ED.cues[k].end = r3(Math.max(ED.cues[k].start + 0.04, ED.cues[k].end + d)); }
      changed(false); drawRows(); selectCue(i, { seek: false });
      toast(`${ED.cues.length - i} legendas deslocadas ${d > 0 ? "para depois" : "para antes"}.`);
      break;
    }
    case "snap": {
      if (!ED.fps) { toast("Sem vídeo, não há quadros para encaixar.", true); return; }
      snapshot(true);
      ED.cues.forEach((x) => { x.start = r3(Math.round(x.start * ED.fps) / ED.fps); x.end = r3(Math.round(x.end * ED.fps) / ED.fps); });
      changed(false); drawRows(); drawEdit(); drawWave();
      toast("Tempos encaixados nos quadros do vídeo.");
      break;
    }
    case "nextissue": {
      const keys = Object.keys(ED.issues).map(Number).sort((a, b) => a - b);
      if (!keys.length) { toast("Nenhum problema encontrado."); return; }
      selectCue(keys.find((k) => k > i) ?? keys[0]);
      break;
    }
    case "zin": setZoom(Math.min(400, zoomPct() * 1.5)); break;
    case "zout": setZoom(Math.max(25, zoomPct() / 1.5)); break;
    case "help": showHelp(); break;
    case "translate": openTranslate({ project_id: ED.clientId }); break;
    case "translate-quick": openTranslate({ quick: true, project_id: ED.clientId }); break;
    case "syncmenu": toggleSyncMenu(); break;
    case "verify": openVerify(); break;
    case "deliver": openDeliver(); break;
    case "find": openFind(); break;
  }
}

/* ============================================================ tradução */

/* Abre (ou só traz para frente) a aba do ChatGPT, sem recarregar a conversa aberta. */
function openChatGPT() {
  let w = null;
  try { w = window.open("", "legendas-chatgpt"); } catch {}
  let blank = true;
  try { blank = !w || w.location.href === "about:blank"; } catch { blank = false; }  // outra origem: já está aberta
  if (blank) w = window.open("https://chatgpt.com/", "legendas-chatgpt");
  try { w && w.focus(); } catch {}
}

function getPref(k, d) { try { return localStorage.getItem(k) || d; } catch { return d; } }
function setPref(k, v) { try { localStorage.setItem(k, v); } catch {} }

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select();
  let ok = false; try { ok = document.execCommand("copy"); } catch {}
  ta.remove();
  return ok;
}

/* opts.method: "chat" | "api"; opts.target, opts.project_id: valores iniciais */
async function openTranslate(opts = {}) {
  if (!ED.cues.length) { toast("Não há legendas para traduzir.", true); return; }
  if (!S.projects?.length) { try { await loadProjects(); } catch {} }
  const src = opts.source || ED.detected || ED.language || "pt-BR";
  const dst = opts.target || ED.suggested || (src.startsWith("es") ? "pt-BR" : "es-419");
  const method = opts.method || getPref("legendas.metodo", S.state?.settings?.translate_method || "chat");
  /* perfil do idioma de destino, da mesma família do perfil aberto (Netflix, cliente…) */
  const profFor = (lang) => {
    const m = /^(.+?)-(pt-br|es-419)(-kids)?$/.exec(ED.profile.key || "");
    const fam = m ? m[1] : "netflix", kids = m && m[3] ? m[3] : "";
    const code = lang.startsWith("pt") ? "pt-br" : "es-419";
    const k = `${fam}-${code}${kids}`;
    const has = (x) => S.state.profiles.some((p) => p.key === x);
    return has(k) ? k : has(`${fam}-${code}`) ? `${fam}-${code}` : `netflix-${code}`;
  };
  const ov = document.createElement("div");
  ov.className = "modal-bg";
  ov.innerHTML = `
    <div class="modal wide" role="dialog" aria-modal="true" aria-labelledby="tr-title">
      <h2 id="tr-title">Traduzir esta legenda</h2>
      <div id="tr-setup" class="stack">
        <p class="muted small">${ED.cues.length} legendas. Os tempos ficam iguais e a legenda original não é alterada: a tradução vira um arquivo novo, ao lado dela.</p>
        <div class="methods" role="radiogroup" aria-label="Como traduzir">
          <label class="method"><input type="radio" name="tr-m" value="chat" ${method === "chat" ? "checked" : ""}>
            <strong>Pelo meu ChatGPT</strong><span class="muted small">Sem custo. Você cola cada parte no ChatGPT e cola a resposta aqui.</span></label>
          <label class="method"><input type="radio" name="tr-m" value="api" ${method === "api" ? "checked" : ""}>
            <strong>Automática (API)</strong><span class="muted small" id="tr-cost">Sem trabalho manual. Custo no serviço escolhido em Configurações.</span></label>
        </div>
        <div class="langs">
          <label class="field"><span>De</span><select id="tr-src">${langOptions(src)}</select></label>
          <button class="btn icon swap" data-tr="swap" title="Inverter idiomas" aria-label="Inverter idiomas">⇄</button>
          <label class="field"><span>Para</span><select id="tr-dst">${langOptions(dst)}</select></label>
        </div>
        <p class="muted small">${ED.detected ? `Idioma detectado na legenda: ${esc(shortLang(ED.detected))}.` : ""}</p>
        <div class="grid-2">
          <label class="field"><span>Cliente (regras, glossário e instruções)</span>
            <select id="tr-project"><option value="">Sem cliente</option>${(S.projects || []).map((p) => `<option value="${p.id}" ${String(p.id) === String(opts.project_id || "") ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
          <label class="field"><span>Perfil de regras</span>
            <select id="tr-profile">${S.state.profiles.map((p) => `<option value="${esc(p.key)}" ${p.key === profFor(dst) ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
        </div>
      </div>
      <div id="tr-body"></div>
      <div class="row modal-actions" id="tr-actions">
        <button class="btn" data-tr="close">Cancelar</button>
        <button class="btn primary" data-tr="go">Começar</button>
      </div>
    </div>`;
  document.body.appendChild(ov);
  const $ = (id) => ov.querySelector(id);
  const chosen = () => ov.querySelector('input[name="tr-m"]:checked').value;
  const opt = () => ({ source_lang: $("#tr-src").value, target_lang: $("#tr-dst").value,
    profile_key: $("#tr-profile").value, project_id: $("#tr-project").value ? Number($("#tr-project").value) : null, cues: ED.cues });
  let busy = false, timer = null, jobId = null;
  const close = () => { clearInterval(timer); ov.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape" && !busy) close(); };
  document.addEventListener("keydown", onKey);

  const estimate = async () => {
    const c = $("#tr-cost"); if (!c) return;
    if ($("#tr-src").value === $("#tr-dst").value) { $('[data-tr="go"]').disabled = true; return; }
    $('[data-tr="go"]').disabled = false;
    try {
      const r = await api("POST", `/api/editor/${ED.sid}/translate`, { ...opt(), estimate: true });
      c.innerHTML = `Sem trabalho manual · ${esc(r.provider || "OpenAI")}. Custo estimado: <b>${fmtUSD(r.usd)}</b>.`;
    } catch { /* sem chave, por exemplo: o texto padrão fica */ }
  };
  const syncProfile = () => { const p = profFor($("#tr-dst").value); if ([...$("#tr-profile").options].some((o) => o.value === p)) $("#tr-profile").value = p; };
  $("#tr-src").addEventListener("change", estimate);
  $("#tr-dst").addEventListener("change", () => { syncProfile(); estimate(); });
  estimate();

  const openResult = async (r) => {
    const o = await api("POST", "/api/editor/open", { srt: r.srt, video: ED.video, original: r.original, profile_key: r.profile_key, client_id: ED.clientId, item_id: ED.itemId });
    ED.dirty = false;
    close();
    toast(r.missing?.length ? `Tradução aberta. ${r.missing.length} legenda(s) ficaram no original: revise as marcadas.` : "Tradução aberta no editor. A coluna Original mostra o texto de partida.");
    location.hash = `#/editor/${o.sid}`;
  };

  /* ---------------------------------------------------------- pela API */
  const runApi = async () => {
    const job = await api("POST", `/api/editor/${ED.sid}/translate`, opt());
    jobId = job.id;
    $('[data-tr="close"]').textContent = "Cancelar tradução";
    $('[data-tr="go"]').hidden = true;
    $("#tr-body").innerHTML = `<p id="tr-msg">Na fila…</p><div class="bar" style="margin-top:8px"><i id="tr-bar" style="width:0%"></i></div><p class="muted small" id="tr-count" style="margin-top:6px"></p>`;
    timer = setInterval(async () => {
      let j; try { j = await api("GET", `/api/jobs/${jobId}`); } catch { return; }
      const v = j.live?.steps?.traduzir;
      if (j.live?.message) $("#tr-msg").textContent = j.live.message;
      if (v && v[1]) { $("#tr-bar").style.width = `${Math.round((v[0] / v[1]) * 100)}%`; $("#tr-count").textContent = `${v[0]} de ${v[1]} legendas`; }
      if (j.status === "pronto") {
        clearInterval(timer);
        await openResult({ srt: j.outputs.srt, original: j.outputs.original, profile_key: j.params.profile_key });
      } else if (["erro", "cancelado", "interrompido"].includes(j.status)) {
        clearInterval(timer); busy = false;
        $("#tr-msg").innerHTML = `<span class="note err" style="display:block">${esc(j.error || "A tradução foi interrompida.")}</span>`;
        $('[data-tr="close"]').textContent = "Fechar";
        jobId = null;
      }
    }, 1000);
  };

  /* ------------------------------------------------- pelo ChatGPT */
  let chat = null, cur = 1, chatOpened = false;
  const drawChat = (note = "") => {
    const lot = chat.lots[cur - 1];
    const doneLots = chat.lots.filter((l) => l.missing.length === 0).length;
    const pct = Math.round((chat.done / chat.total) * 100);
    $("#tr-body").innerHTML = `
      <div class="chatflow">
        <div class="row" style="justify-content:space-between">
          <strong>Parte ${cur} de ${chat.lots.length} <span class="muted small">· legendas ${lot.first} a ${lot.last}</span></strong>
          <span class="muted small tnum">${chat.done} de ${chat.total} traduzidas</span>
        </div>
        <div class="bar"><i style="width:${pct}%"></i></div>
        <ol class="chatsteps">
          <li><button class="btn primary" data-tr="copy">${cur === 1 && !chatOpened ? "Copiar parte 1 e abrir o ChatGPT" : `Copiar parte ${cur}`}</button>
            <span class="muted small">${cur === 1 ? "No ChatGPT, comece uma <b>conversa nova</b>, cole com Ctrl+V e envie." : "Cole na <b>mesma conversa</b> do ChatGPT e envie."}</span></li>
          <li><span>Quando o ChatGPT terminar, clique no botão de copiar do bloco de código da resposta e cole aqui:</span>
            <textarea id="tr-ans" class="paste" placeholder="Clique aqui e aperte Ctrl+V"></textarea></li>
        </ol>
        <p id="tr-note" class="small">${note}</p>
        <div class="lots">${chat.lots.map((l) => `<span class="lot ${l.missing.length === 0 ? "ok" : l.received ? "part" : ""} ${l.n === cur ? "cur" : ""}" title="Legendas ${l.first}–${l.last}">${l.n}</span>`).join("")}</div>
        <details class="blocked" ${chat.blockedOpen ? "open" : ""}>
          <summary>O ChatGPT não respondeu ou bloqueou (“não pode ser exibido por motivos de segurança”)?</summary>
          <p class="small muted">Acontece com cenas fortes (violência, drogas, suicídio…), mesmo sendo só tradução. Escolha um caminho; o que já foi traduzido fica guardado.</p>
          <div class="stack" style="gap:8px">
            <div><button class="btn" data-tr="split">Dividir a parte ${cur} em pedaços menores</button>
              <span class="muted small">O trecho que causa o bloqueio fica isolado num pedaço pequeno e o resto passa.</span></div>
            <div><button class="btn" data-tr="rules">Copiar a parte ${cur} com as instruções</button>
              <span class="muted small">Para colar numa <b>conversa nova</b> do ChatGPT, se a atual travou.</span></div>
            <div><button class="btn" data-tr="viaapi">Traduzir a parte ${cur} pela API</button>
              <span class="muted small">Automático, sem bloqueio de tela; custa centavos (precisa da chave da OpenAI).</span></div>
          </div>
        </details>
        <p class="muted small"><button class="btn link small" data-tr="openchat">Abrir o ChatGPT</button> · ${doneLots === chat.lots.length ? "" : `<button class="btn link small" data-tr="finish-now">Concluir assim mesmo (o que faltar fica no original)</button>`}</p>
      </div>`;
    const ta = $("#tr-ans");
    ta.addEventListener("paste", () => setTimeout(() => submitAnswer(ta.value), 0));
    ta.addEventListener("input", () => { clearTimeout(ta._t); ta._t = setTimeout(() => submitAnswer(ta.value), 900); });
  };
  const submitAnswer = async (text) => {
    if (!text.trim()) return;
    const n = $("#tr-note");
    try {
      const r = await api("POST", `/api/editor/${ED.sid}/chat/${cur}`, { text });
      chat.lots[cur - 1] = { ...chat.lots[cur - 1], received: r.received, missing: r.missing };
      chat.done = r.done;
      if (r.parsed === 0) {
        n.className = "small note warn";
        n.textContent = "Não reconheci a resposta. No ChatGPT, use o botão de copiar do bloco de código (canto do bloco) e cole aqui de novo.";
        return;
      }
      if (r.missing.length) {
        drawChat(`<span class="note warn" style="display:block">Vieram ${r.received} de ${r.count}. Faltaram ${r.missing.length} (${r.missing.slice(0, 8).join(", ")}${r.missing.length > 8 ? "…" : ""}).
          <button class="btn small" data-tr="copy-missing">Copiar pedido das que faltaram</button></span>`);
        return;
      }
      const next = chat.lots.find((l) => l.missing.length > 0);
      if (!next) { await finishChat(); return; }
      cur = next.n;
      drawChat(`<span class="note ok" style="display:block">Parte recebida. Agora copie a parte ${cur} e cole na mesma conversa.</span>`);
    } catch (e) { n.className = "small note err"; n.textContent = e.message; }
  };
  const finishChat = async () => {
    $("#tr-body").innerHTML = `<p>Montando a legenda traduzida…</p><div class="bar indet"><i></i></div>`;
    const r = await api("POST", `/api/editor/${ED.sid}/chat/finish`);
    await openResult(r);
  };
  const runChat = async () => {
    chat = await api("POST", `/api/editor/${ED.sid}/chat/start`, opt());
    cur = 1;
    $("#tr-setup").hidden = true;
    $('[data-tr="go"]').hidden = true;
    $('[data-tr="close"]').textContent = "Cancelar";
    drawChat(chat.lots.length > 1 ? `São ${chat.lots.length} partes. Mande todas na mesma conversa do ChatGPT.` : "");
  };

  if (opts.quick) {   // um clique: idiomas, cliente e método já escolhidos
    $("#tr-setup").hidden = true;
    $("#tr-title").textContent = `Traduzir para ${shortLang(dst)}`;
    setTimeout(() => $('[data-tr="go"]').click(), 0);
  }
  ov.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-tr]");
    if (e.target === ov && !busy) return close();
    if (!b) return;
    const a = b.dataset.tr;
    try {
      if (a === "close") {
        if (jobId) await api("POST", `/api/jobs/${jobId}/cancel`).catch(() => {});
        if (chat && chat.done > 0 && !confirm("Cancelar a tradução? As partes já recebidas serão descartadas.")) return;
        return close();
      }
      if (a === "swap") { const x = $("#tr-src").value; $("#tr-src").value = $("#tr-dst").value; $("#tr-dst").value = x; syncProfile(); estimate(); return; }
      if (a === "go") {
        b.disabled = true; busy = true;
        setPref("legendas.metodo", chosen());
        if (chosen() === "chat") await runChat(); else { ov.querySelectorAll("#tr-setup select, #tr-setup input, [data-tr=swap]").forEach((x) => (x.disabled = true)); await runApi(); }
        return;
      }
      if (a === "copy" || a === "copy-missing") {
        const p = await api("GET", `/api/editor/${ED.sid}/chat/${cur}${a === "copy-missing" ? "?faltam=1" : ""}`);
        const ok = await copyText(p.text);
        if (!chatOpened && a === "copy") { openChatGPT(); chatOpened = true; }
        toast(ok ? `Parte ${cur} copiada${a === "copy-missing" ? " (só as que faltaram)" : ""}. Cole no ChatGPT com Ctrl+V.` : "Não consegui copiar automaticamente. Tente de novo.", !ok);
        const ta = $("#tr-ans"); if (ta) { ta.value = ""; }
        if (a === "copy" && cur === 1) b.textContent = "Copiar parte 1 de novo";
        return;
      }
      if (a === "openchat") { openChatGPT(); chatOpened = true; return; }
      if (a === "split") {
        const r = await api("POST", `/api/editor/${ED.sid}/chat/${cur}/split`, { size: 20 });
        const parts = r.lots.length - chat.lots.length + 1;
        chat = { ...r, blockedOpen: false };
        cur = r.current;
        drawChat(`<span class="note info" style="display:block">A parte foi dividida em ${parts} pedaços. Copie a parte ${cur} e cole na mesma conversa. Se um pedaço for bloqueado de novo, divida de novo ou mande esse pela API.</span>`);
        return;
      }
      if (a === "rules") {
        const p = await api("GET", `/api/editor/${ED.sid}/chat/${cur}?regras=1`);
        const ok = await copyText(p.text);
        toast(ok ? `Parte ${cur} copiada com as instruções. No ChatGPT, abra uma conversa nova e cole.` : "Não consegui copiar. Tente de novo.", !ok);
        return;
      }
      if (a === "viaapi") {
        const lot = chat.lots[cur - 1];
        if (!confirm(`Traduzir pela API as ${lot.missing.length} legenda(s) que faltam da parte ${cur}? Custa alguns centavos na OpenAI.`)) return;
        b.disabled = true; b.textContent = "Traduzindo pela API…";
        const r = await api("POST", `/api/editor/${ED.sid}/chat/${cur}/api`);
        chat.lots[cur - 1] = { ...lot, received: r.received, missing: r.missing };
        chat.done = r.done;
        const cost = `(${fmtUSD(r.usd)})`;
        if (r.missing.length) { drawChat(`<span class="note warn" style="display:block">A API traduziu ${r.received} de ${r.count} ${cost}. Faltaram ${r.missing.length}: tente de novo ou traduza à mão depois.</span>`); return; }
        const next = chat.lots.find((l) => l.missing.length > 0);
        if (!next) { await finishChat(); return; }
        cur = next.n;
        drawChat(`<span class="note ok" style="display:block">Parte traduzida pela API ${cost}. Agora copie a parte ${cur} e cole no ChatGPT.</span>`);
        return;
      }
      if (a === "finish-now") { if (confirm("Concluir com as partes recebidas? O que faltar fica no idioma original, marcado para revisão.")) await finishChat(); return; }
    } catch (err) {
      toast(err.message, true);
      if (a === "go") { b.disabled = false; busy = false; }
    }
  });
}

function showHelp() {
  toast("Espaço: tocar/pausar · ←/→: quadro · Shift+←/→: 1 s · Alt+↑/↓: legenda anterior/próxima · F11 ou [: início · F12 ou ]: fim · Insert: nova · Ctrl+S: salvar · Ctrl+Z/Y: desfazer/refazer · F8: próximo problema · Ctrl+F: localizar e substituir");
}

/* ========================================================== forma de onda */

function zoomPct() { return Number(document.getElementById("ed-zoom")?.value || 100); }
function setZoom(z) {
  const sel = document.getElementById("ed-zoom");
  const opts = [...sel.options].map((o) => Number(o.value));
  const best = opts.reduce((a, b) => (Math.abs(b - z) < Math.abs(a - z) ? b : a));
  const center = ED.wave.start + waveSpan() / 2;
  sel.value = String(best);
  ED.wave.pps = best;
  ED.wave.start = Math.max(0, center - waveSpan() / 2);
  drawWave();
}
function canvasEl() { return document.getElementById("ed-canvas"); }
function waveSpan() { const cv = canvasEl(); return cv ? cv.clientWidth / ED.wave.pps : 10; }
function centerWave(t) { ED.wave.start = Math.max(0, t - waveSpan() / 2); drawWave(); }
function xOf(t) { return (t - ED.wave.start) * ED.wave.pps; }
function tOf(x) { return ED.wave.start + x / ED.wave.pps; }

async function loadPeaks() {
  const msg = document.getElementById("ed-wavemsg");
  if (!ED.video || ED.hasAudio === false) { msg.textContent = ED.video ? "Este arquivo não tem áudio." : ""; return; }
  msg.textContent = "Gerando a forma de onda…";
  try {
    const res = await fetch(`/api/editor/${ED.sid}/peaks`, { headers: { "X-Token": TOKEN } });
    if (!res.ok) throw new Error((await res.json()).error || "Falha ao gerar a forma de onda.");
    ED.peaksRate = Number(res.headers.get("X-Peaks-Rate") || 100);
    ED.peaks = new Uint8Array(await res.arrayBuffer());
    if (!ED.duration) ED.duration = ED.peaks.length / ED.peaksRate;
    msg.textContent = "";
    drawWave();
  } catch (e) { msg.textContent = e.message; }
}

function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

function drawWave() {
  const cv = canvasEl();
  if (!cv) return;
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const C = { bg: cssVar("--wave-bg"), grid: cssVar("--wave-grid"), wave: cssVar("--wave-fg"), waveSel: cssVar("--wave-sel"),
    cue: cssVar("--wave-cue"), cueSel: cssVar("--wave-cue-sel"), edge: cssVar("--wave-edge"), text: cssVar("--wave-text"), head: cssVar("--wave-head") };
  g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
  const t0 = ED.wave.start, t1 = t0 + W / ED.wave.pps;
  const RULER = 18, top = 2, bot = H - RULER, mid = (top + bot) / 2, amp = (bot - top) / 2 - 2;

  // régua
  const stepS = ED.wave.pps >= 150 ? 0.5 : ED.wave.pps >= 60 ? 1 : ED.wave.pps >= 30 ? 2 : 5;
  g.font = "11px Segoe UI, system-ui, sans-serif"; g.textBaseline = "middle";
  for (let s = Math.floor(t0 / stepS) * stepS; s <= t1; s += stepS) {
    const x = Math.round(xOf(s)) + 0.5;
    g.strokeStyle = C.grid; g.beginPath(); g.moveTo(x, top); g.lineTo(x, bot); g.stroke();
    if (Math.abs(s - Math.round(s)) < 1e-6) { g.fillStyle = C.text; g.globalAlpha = .7; g.fillText(String(Math.round(s)), x + 3, H - RULER / 2); g.globalAlpha = 1; }
  }

  // legendas (fundo)
  ED.cues.forEach((c, i) => {
    if (c.end < t0 || c.start > t1) return;
    const x0 = xOf(c.start), x1 = xOf(c.end);
    g.fillStyle = i === ED.sel ? C.cueSel : C.cue;
    g.fillRect(x0, top, x1 - x0, bot - top);
  });

  // cortes de cena
  if (ED.shots) {
    g.strokeStyle = cssVar("--wave-shot") || "#d97706"; g.lineWidth = 1;
    for (const sc of ED.shots) {
      if (sc < t0 || sc > t1) continue;
      const x = Math.round(xOf(sc)) + 0.5;
      g.beginPath(); g.moveTo(x, top); g.lineTo(x, bot); g.stroke();
    }
  }

  // onda
  if (ED.peaks) {
    const rate = ED.peaksRate;
    for (let x = 0; x < W; x++) {
      const a = Math.floor(tOf(x) * rate), b = Math.max(a + 1, Math.floor(tOf(x + 1) * rate));
      if (a >= ED.peaks.length) break;
      let m = 0;
      for (let k = Math.max(0, a); k < Math.min(b, ED.peaks.length); k++) if (ED.peaks[k] > m) m = ED.peaks[k];
      const h = (m / 255) * amp;
      const t = tOf(x);
      const inSel = ED.cues[ED.sel] && t >= ED.cues[ED.sel].start && t < ED.cues[ED.sel].end;
      g.fillStyle = inSel ? C.waveSel : C.wave;
      g.fillRect(x, mid - h, 1, Math.max(1, h * 2));
    }
  }

  // legendas (bordas + rótulos)
  ED.cues.forEach((c, i) => {
    if (c.end < t0 || c.start > t1) return;
    const x0 = xOf(c.start), x1 = xOf(c.end);
    g.strokeStyle = C.edge; g.lineWidth = i === ED.sel ? 2 : 1;
    g.beginPath(); g.moveTo(x0, top); g.lineTo(x0, bot); g.stroke();
    g.setLineDash([4, 3]); g.beginPath(); g.moveTo(x1, top); g.lineTo(x1, bot); g.stroke(); g.setLineDash([]);
    g.lineWidth = 1;
    g.save(); g.beginPath(); g.rect(x0 + 2, top, Math.max(0, x1 - x0 - 4), bot - top); g.clip();
    g.fillStyle = C.text; g.font = (i === ED.sel ? "600 " : "") + "12px Segoe UI, system-ui, sans-serif"; g.textBaseline = "top";
    g.fillText(c.text.replace(/\n/g, " "), x0 + 4, top + 4);
    g.textBaseline = "bottom"; g.globalAlpha = .85; g.font = "11px Segoe UI, system-ui, sans-serif";
    g.fillText(`#${i + 1}  ${fmtSec(c.end - c.start)}`, x0 + 4, bot - 3);
    g.globalAlpha = 1; g.restore();
  });

  // cursor de reprodução
  const px = xOf(curTime());
  if (px >= 0 && px <= W) { g.fillStyle = C.head; g.fillRect(Math.round(px) - 1, 0, 2, H); }

  // rolagem
  const sc = document.getElementById("ed-wscroll");
  if (sc && ED.duration && document.activeElement !== sc) sc.value = String(Math.round((t0 / Math.max(0.001, ED.duration - waveSpan())) * 1000));
}

function hitTest(x) {
  const tol = 6;
  // bordas da selecionada primeiro, depois as outras
  const order = ED.cues.map((_, i) => i).sort((a, b) => (a === ED.sel ? -1 : b === ED.sel ? 1 : 0));
  for (const i of order) {
    const c = ED.cues[i], x0 = xOf(c.start), x1 = xOf(c.end);
    if (Math.abs(x - x0) <= tol) return { i, mode: "start" };
    if (Math.abs(x - x1) <= tol) return { i, mode: "end" };
  }
  for (const i of order) {
    const c = ED.cues[i];
    if (x > xOf(c.start) && x < xOf(c.end)) return { i, mode: "move" };
  }
  return null;
}

function bindWave() {
  const cv = canvasEl();
  const pos = (e) => e.clientX - cv.getBoundingClientRect().left;
  cv.addEventListener("pointermove", (e) => {
    if (ED.wave.drag) return dragMove(e);
    const h = hitTest(pos(e));
    cv.style.cursor = !h ? "text" : h.mode === "move" ? "grab" : "ew-resize";
  });
  cv.addEventListener("pointerdown", (e) => {
    cv.setPointerCapture(e.pointerId);
    const x = pos(e), h = hitTest(x);
    if (h) {
      if (h.i !== ED.sel) selectCue(h.i, { seek: false, scrollWave: false });
      const c = ED.cues[h.i];
      ED.wave.drag = { ...h, x0: x, start: c.start, end: c.end, moved: false };
      if (h.mode === "move") cv.style.cursor = "grabbing";
    } else {
      ED.wave.drag = { mode: "seek" };
      vid()?.pause();
      seek(tOf(x));
    }
  });
  const end = () => {
    const d = ED.wave.drag; ED.wave.drag = null;
    if (d && d.mode === "move" && !d.moved) seek(tOf(d.x0));
    if (d && d.moved) { sortedCues(); drawRows(); selectCue(ED.sel, { seek: false, scrollWave: false }); }
  };
  cv.addEventListener("pointerup", end);
  cv.addEventListener("pointercancel", end);
  cv.addEventListener("dblclick", (e) => { const h = hitTest(pos(e)); if (h) { selectCue(h.i, { focusText: true }); } });
  cv.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (e.ctrlKey) { setZoom(zoomPct() * (e.deltaY < 0 ? 1.25 : 0.8)); return; }
    ED.wave.start = Math.max(0, Math.min(Math.max(0, ED.duration - waveSpan() * 0.5), ED.wave.start + (e.deltaY + e.deltaX) / ED.wave.pps));
    drawWave();
  }, { passive: false });
  new ResizeObserver(() => drawWave()).observe(cv);

  function dragMove(e) {
    const d = ED.wave.drag;
    const x = pos(e);
    if (d.mode === "seek") { seek(tOf(x)); return; }
    const dt = (x - d.x0) / ED.wave.pps;
    if (!d.moved && Math.abs(x - d.x0) < 3) return;
    if (!d.moved) { snapshot(true); d.moved = true; }
    const c = ED.cues[d.i], prev = ED.cues[d.i - 1], next = ED.cues[d.i + 1], gap = minGap();
    const lo = prev ? prev.end + gap : 0, hi = next ? next.start - gap : (ED.duration || Infinity);
    const snap = (t) => (ED.fps && !e.altKey ? Math.round(t * ED.fps) / ED.fps : t);
    if (d.mode === "start") c.start = r3(Math.min(c.end - 0.04, Math.max(lo, snap(d.start + dt))));
    if (d.mode === "end") c.end = r3(Math.max(c.start + 0.04, Math.min(hi, snap(d.end + dt))));
    if (d.mode === "move") {
      const len = d.end - d.start;
      let ns = snap(d.start + dt);
      ns = Math.max(lo, Math.min(hi - len, ns));
      c.start = r3(ns); c.end = r3(ns + len);
    }
    changed(false, d.i);
    updateRow(d.i); drawEdit(); drawWave(); tick();
    if (d.mode === "start" || d.mode === "move") seek(c.start + 0.001);
  }
}

/* ============================================================== status */

function drawStatus() {
  const el = document.getElementById("ed-status");
  if (!el) return;
  const n = Object.keys(ED.issues).length;
  const badge = document.getElementById("ed-issn");
  if (badge) { badge.textContent = n; badge.hidden = n === 0; }
  el.innerHTML = `
    <span>${ED.cues.length ? `${ED.sel + 1}/${ED.cues.length}` : "0/0"}</span>
    <button class="btn link small ${n ? "warn" : ""}" data-ed="nextissue">${n ? `${n} ${n === 1 ? "legenda precisa" : "legendas precisam"} de revisão` : "Nenhum problema"}</button>
    <span class="muted">${esc(ED.profile.name)}</span>
    <span class="grow"></span>
    <span class="${ED.dirty ? "warn" : "muted"}">${ED.dirty ? "Alterações não salvas" : ED.savedAt ? `Salvo às ${ED.savedAt}` : "Sem alterações"}</span>`;
}

function drawAll() { drawRows(); drawEdit(); drawWave(); drawStatus(); tick(); }

/* ============================================================== eventos */

function bindEditor() {
  main.onclick = (e) => {
    const b = e.target.closest("[data-ed]");
    if (b) { act(b.dataset.ed); return; }
    const tab = e.target.closest("[data-tab]");
    if (tab) {
      document.querySelectorAll("[data-tab]").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      document.getElementById("tab-criar").hidden = tab.dataset.tab !== "criar";
      document.getElementById("tab-ajustar").hidden = tab.dataset.tab !== "ajustar";
    }
  };
  const rows = document.getElementById("ed-rows");
  rows.addEventListener("click", (e) => { const tr = e.target.closest("tr[data-i]"); if (tr) selectCue(Number(tr.dataset.i), { scrollList: false }); });
  rows.addEventListener("dblclick", (e) => { const tr = e.target.closest("tr[data-i]"); if (tr) { selectCue(Number(tr.dataset.i)); vid()?.play(); } });

  const txt = document.getElementById("ed-txt");
  txt.addEventListener("input", () => { if (ED.cues[ED.sel]) setCue(ED.sel, { text: txt.value }, { edit: false }); });
  const st = document.getElementById("ed-start"), du = document.getElementById("ed-dur");
  st.addEventListener("change", () => {
    const c = ED.cues[ED.sel], t = parseTC(st.value);
    if (!c || t == null) { toast("Use o formato 00:00:00,000.", true); drawEdit(); return; }
    const dur = c.end - c.start; setCue(ED.sel, { start: t, end: t + dur }, { force: true });
  });
  du.addEventListener("change", () => {
    const c = ED.cues[ED.sel], d = Number(du.value.replace(",", "."));
    if (!c || !(d > 0)) { toast("Duração inválida.", true); drawEdit(); return; }
    setCue(ED.sel, { end: c.start + d }, { force: true });
  });
  [st, du].forEach((el) => el.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    const c = ED.cues[ED.sel]; if (!c) return;
    const d = (e.key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 0.1 : 1 / edFps());
    if (el === st) setCue(ED.sel, { start: c.start + d, end: c.end + d }, { force: true });
    else setCue(ED.sel, { end: c.end + d }, { force: true });
  }));

  document.getElementById("ed-profile").addEventListener("change", async (e) => {
    try { ED.profile = await api("PUT", `/api/editor/${ED.sid}/profile`, { key: e.target.value }); recheckAll(); drawAll(); }
    catch (err) { toast(err.message, true); }
  });
  document.getElementById("ed-client").addEventListener("change", async (e) => {
    try {
      const r = await api("PUT", `/api/editor/${ED.sid}/client`, { client_id: e.target.value ? Number(e.target.value) : null });
      ED.clientId = r.client_id; ED.profile = r.profile;
      setPref("cnt.cliente", ED.clientId ? String(ED.clientId) : "");
      document.getElementById("ed-profile").value = ED.profile.key;
      recheckAll(); drawAll();
      toast(`Regras: ${ED.profile.name}.`);
    } catch (err) { toast(err.message, true); }
  });
  document.getElementById("ed-syncmenu").addEventListener("click", (e) => {
    const b = e.target.closest("[data-sy]");
    if (b) { toggleSyncMenu(false); runSync(b.dataset.sy); }
  });
  document.getElementById("ed-follow").addEventListener("change", (e) => (ED.follow = e.target.checked));
  document.getElementById("ed-zoom").addEventListener("change", (e) => setZoom(Number(e.target.value)));
  document.getElementById("ed-rate").addEventListener("change", (e) => { const v = vid(); if (v) v.playbackRate = Number(e.target.value); });
  document.getElementById("ed-vol").addEventListener("input", (e) => { const v = vid(); if (v) v.volume = Number(e.target.value); });
  document.getElementById("ed-seek").addEventListener("input", (e) => seek((Number(e.target.value) / 1000) * ED.duration, { center: true }));
  document.getElementById("ed-wscroll").addEventListener("input", (e) => {
    ED.wave.start = (Number(e.target.value) / 1000) * Math.max(0, ED.duration - waveSpan()); drawWave();
  });
  bindWave();
  window.onresize = () => { fitVideo(); drawWave(); };
}

["keydown", "mousedown", "wheel"].forEach((ev) => document.addEventListener(ev, () => { ED.lastAct = Date.now(); }, { passive: true }));
function editorKeys(e) {
  if (!document.body.classList.contains("editor-mode") || !ED.sid || !document.getElementById("ed-txt")) return;
  const tag = (e.target.tagName || "").toLowerCase();
  const typing = tag === "textarea" || (tag === "input" && !["range", "checkbox"].includes(e.target.type)) || tag === "select";
  const k = e.key, ctrl = e.ctrlKey || e.metaKey;
  const go = (name) => { e.preventDefault(); act(name); };
  if (ctrl && k.toLowerCase() === "s") return go(e.shiftKey ? "saveas" : "save");
  if (ctrl && !e.shiftKey && k.toLowerCase() === "z" && !typing) return go("undo");
  if (ctrl && (k.toLowerCase() === "y" || (e.shiftKey && k.toLowerCase() === "z")) && !typing) return go("redo");
  if (ctrl && k === " ") return go("play");
  if (ctrl && (k.toLowerCase() === "f" || k.toLowerCase() === "h")) return go("find");
  if (k === "F11") return go("setstart");
  if (k === "F12") return go("setend");
  if (k === "F8") return go("nextissue");
  if (e.altKey && k === "ArrowUp") return go("prev");
  if (e.altKey && k === "ArrowDown") return go("next");
  if (e.altKey && k === "ArrowLeft") return go("fback");
  if (e.altKey && k === "ArrowRight") return go("ffwd");
  if (typing) return;
  if (k === " ") return go("play");
  if (k === "[") return go("setstart");
  if (k === "]") return go("setend");
  if (k === "Insert") return go("insert");
  if (k === "Delete" && document.activeElement?.id === "ed-list") return go("delete");
  if (k === "ArrowLeft") { e.preventDefault(); return e.shiftKey ? seek(curTime() - 1) : stepFrame(-1); }
  if (k === "ArrowRight") { e.preventDefault(); return e.shiftKey ? seek(curTime() + 1) : stepFrame(1); }
  if (k === "ArrowUp") return go("prev");
  if (k === "ArrowDown") return go("next");
  if (k === "Enter") { e.preventDefault(); document.getElementById("ed-txt").focus(); }
}
document.addEventListener("keydown", editorKeys);
window.addEventListener("beforeunload", (e) => { if (ED.dirty) { e.preventDefault(); e.returnValue = ""; } });
