/* CNT Legendas — ferramentas do editor: sincronizar, verificar, entregar, localizar.
   Usa o estado ED do editor.js. Toda mudança passa por snapshot() (dá para desfazer). */
"use strict";

/* ------------------------------------------------------------ utilidades */

function modal(title, body, actions, opts = {}) {
  const ov = document.createElement("div");
  ov.className = "modal-bg";
  ov.innerHTML = `<div class="modal ${opts.wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <h2>${esc(title)}</h2><div class="stack mbody">${body}</div>
      <div class="row modal-actions">${actions}</div></div>`;
  document.body.appendChild(ov);
  const close = () => { ov.remove(); document.removeEventListener("keydown", onKey); opts.onClose?.(); };
  const onKey = (e) => { if (e.key === "Escape" && !ov.dataset.busy) close(); };
  document.addEventListener("keydown", onKey);
  ov.addEventListener("click", (e) => { if (e.target === ov && !ov.dataset.busy) close(); });
  ov.querySelector("[autofocus]")?.focus();
  return { ov, close, $: (q) => ov.querySelector(q) };
}

/* aplica legendas novas (do servidor) mantendo a seleção; pode desfazer */
function applyCues(cues, msg) {
  snapshot(true);
  const selStart = ED.cues[ED.sel]?.start;
  ED.cues = cues.slice().sort((a, b) => a.start - b.start);
  if (selStart != null) {
    let k = ED.cues.findIndex((c) => c.start >= selStart - 1e-6);
    ED.sel = Math.max(0, Math.min(k < 0 ? ED.cues.length - 1 : k, ED.cues.length - 1));
  }
  ED.hasOrig = ED.hasOrig || ED.cues.some((c) => c.orig != null);
  changed(false); drawAll(); selectCue(ED.sel, { seek: false });
  if (msg) toast(`${msg} (Ctrl+Z desfaz)`);
  carregarMemoria();
}

async function syncOp(op, params = {}) {
  const r = await api("POST", `/api/editor/${ED.sid}/sync`, { op, ...params, cues: sortedCues() });
  applyCues(r.cues, r.message);
  return r;
}

const fmtTCms = (t) => fmtTC(t);

async function pickPath(kind) {
  const { paths } = await api("POST", "/api/dialog", { kind });
  return paths[0] || "";
}

/* tarefa demorada (sincronia automática, cortes) com janela de progresso */
async function runTask(kind, params, title) {
  const m = modal(title, `<p id="tk-msg">Começando…</p><div class="bar"><i id="tk-bar" style="width:0%"></i></div>`,
    `<button class="btn" data-x="cancel">Cancelar</button>`);
  m.ov.dataset.busy = "1";
  let t;
  try { t = await api("POST", `/api/editor/${ED.sid}/task`, { kind, ...params, cues: kind === "shots" ? [] : sortedCues() }); }
  catch (e) { m.close(); throw e; }
  let stop = false;
  m.$("[data-x=cancel]").onclick = () => { stop = true; api("POST", `/api/editor/${ED.sid}/task/${t.id}/cancel`).catch(() => {}); m.close(); };
  while (!stop) {
    await new Promise((r) => setTimeout(r, 400));
    try { t = await api("GET", `/api/editor/${ED.sid}/task/${t.id}`); } catch { continue; }
    if (t.message) m.$("#tk-msg").textContent = t.message;
    m.$("#tk-bar").style.width = `${Math.round((t.progress || 0) * 100)}%`;
    if (t.status !== "rodando") break;
  }
  if (stop) return null;
  m.close();
  if (t.status === "erro") throw new Error(t.message || "Não deu certo.");
  return t;
}

/* ------------------------------------------------------------ sincronizar */

function toggleSyncMenu(force) {
  const menu = document.getElementById("ed-syncmenu");
  const btn = document.querySelector('[data-ed="syncmenu"]');
  if (!menu) return;
  const open = force ?? menu.hidden;
  menu.hidden = !open;
  btn?.setAttribute("aria-expanded", String(open));
  if (open && btn) {   // a barra corta o que passa dela: o menu fica "solto" na tela
    const r = btn.getBoundingClientRect();
    menu.style.top = `${r.bottom + 4}px`;
    menu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 400))}px`;
  }
  if (open) setTimeout(() => document.addEventListener("click", function off(e) {
    if (!e.target.closest(".menuwrap")) { menu.hidden = true; btn?.setAttribute("aria-expanded", "false"); }
    document.removeEventListener("click", off);
  }), 0);
}

async function runSync(kind) {
  try {
    if (!ED.cues.length && kind !== "script") { toast("Não há legendas para sincronizar.", true); return; }
    if (kind === "audio") {
      if (!ED.video || !ED.hasAudio) { toast("Abra o vídeo (com áudio) junto da legenda para sincronizar pela fala.", true); return; }
      const t = await runTask("audio", {}, "Sincronizando pela fala do vídeo");
      if (!t) return;
      if (t.result.changed) applyCues(t.result.cues, `Sincronizada. ${t.message}`);
      else toast(t.message || "A legenda já estava sincronizada.");
    }
    if (kind === "fit") {
      if (!ED.video || !ED.hasAudio) { toast("Abra o vídeo (com áudio) junto da legenda para acertar na voz.", true); return; }
      const t = await runTask("fit", {}, "Acertando início e fim na fala");
      if (!t) return;
      if (t.result.changed) applyCues(t.result.cues, t.message);
      else toast(t.message);
    }
    if (kind === "precise") {
      if (!ED.video || !ED.hasAudio) { toast("Abra o vídeo (com áudio) junto da legenda para sincronizar pela fala.", true); return; }
      openPrecise();
    }
    if (kind === "ref") {
      const path = await pickPath("subtitle");
      if (!path) return;
      const t = await runTask("ref", { path }, "Sincronizando pela legenda de referência");
      if (!t) return;
      if (t.result.changed) applyCues(t.result.cues, `Sincronizada. ${t.message}`);
      else toast(t.message || "A legenda já estava sincronizada.");
    }
    if (kind === "copy") {
      const path = await pickPath("subtitle");
      if (path) await syncOp("copy", { path });
    }
    if (kind === "shift") openShift();
    if (kind === "twopoint") openTwoPoint();
    if (kind === "fps") openFps();
    if (kind === "shots") {
      if (!ED.video || ED.hasVideo === false) { toast("Abra o vídeo para encontrar os cortes de cena.", true); return; }
      if (!ED.shots) {
        const t = await runTask("shots", {}, "Procurando os cortes de cena");
        if (!t) return;
        ED.shots = t.result.shots; drawWave();
        toast(t.message);
      }
      await syncOp("snap");
    }
    if (kind === "script") openScript();
  } catch (e) { toast(e.message, true); }
}

function openPrecise() {
  const m = modal("Sincronia precisa pela fala", `
    <p class="muted small">Cada legenda passa a começar quando a fala começa e a terminar quando a fala termina. Música, chiado e respiração não contam. A legenda não é esticada para dar tempo de ler: se o CPS passar do limite, ele fica em vermelho para você revisar. Tudo encaixado no quadro do vídeo.</p>
    <ol class="muted small" style="margin:8px 0 8px 18px">
      <li>Separa a voz do resto do áudio (na placa de vídeo, se houver; uma vez por vídeo).</li>
      <li>Acha o começo e o fim de cada fala.</li>
      <li>Quando a fala é emendada (sem pausa entre duas legendas), corta entre as palavras.</li>
    </ol>
    <label class="check"><input type="checkbox" id="pr-words" ${getPref("cnt.precisa.palavras", "1") === "1" ? "checked" : ""}>
      <span>Transcrever a fala para cortar falas emendadas entre as palavras <em class="muted small">(no computador, sem custo; na primeira vez baixa o modelo, ~3 GB)</em></span></label>
    <p class="muted small" style="margin-top:8px">Legendas em que o programa não teve certeza ficam com ⚑ e aparecem no F8 (próximo problema). Ctrl+Z desfaz tudo.</p>`,
    `<button class="btn" data-x="close">Cancelar</button><button class="btn primary" data-x="go">Sincronizar</button>`);
  m.ov.addEventListener("click", async (e) => {
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (!x) return;
    if (x === "close") return m.close();
    const words = m.$("#pr-words").checked;
    setPref("cnt.precisa.palavras", words ? "1" : "0");
    m.close();
    try {
      const t = await runTask("precise", { words }, "Sincronia precisa pela fala");
      if (!t) return;
      if (t.result.changed) applyCues(t.result.cues, t.message);
      else toast(t.message);
    } catch (err) { toast(err.message, true); }
  });
}

function openShift() {
  const n = ED.sel + 1;
  const m = modal("Atrasar ou adiantar", `
    <label class="field"><span>Quanto (milissegundos)</span><input type="number" id="sh-ms" value="${getPref("cnt.desloc", "500")}" step="10" min="0" autofocus></label>
    <div class="methods" role="radiogroup">
      <label class="method"><input type="radio" name="sh-w" value="all" checked><strong>Todas as legendas</strong></label>
      <label class="method"><input type="radio" name="sh-w" value="from"><strong>A partir da legenda ${n}</strong><span class="muted small">(a selecionada) até o fim</span></label>
    </div>`,
    `<button class="btn" data-x="close">Cancelar</button><button class="btn" data-x="-">Adiantar</button><button class="btn primary" data-x="+">Atrasar</button>`);
  m.ov.addEventListener("click", async (e) => {
    const a = e.target.closest("[data-x]")?.dataset.x;
    if (!a) return;
    if (a === "close") return m.close();
    const ms = Math.abs(Number(m.$("#sh-ms").value) || 0);
    if (!ms) { toast("Informe quantos milissegundos.", true); return; }
    setPref("cnt.desloc", String(ms));
    const from = m.ov.querySelector('input[name="sh-w"]:checked').value === "from" ? ED.sel : 0;
    try { await syncOp("shift", { ms: a === "-" ? -ms : ms, from }); m.close(); } catch (err) { toast(err.message, true); }
  });
}

function openTwoPoint() {
  const a = Math.min(ED.sel, ED.cues.length - 1), b = ED.cues.length - 1;
  const row = (id, i) => `
    <div class="tp">
      <label class="field"><span>Legenda nº</span><input type="number" id="${id}-n" value="${i + 1}" min="1" max="${ED.cues.length}"></label>
      <div class="field"><span>Está em</span><span class="tnum" id="${id}-old">${fmtTCms(ED.cues[i].start)}</span></div>
      <label class="field"><span>Deve começar em</span><input type="text" class="tnum" id="${id}-new" value="${fmtTCms(ED.cues[i].start)}"></label>
      <button class="btn" data-x="${id}-now" title="Usa a posição atual do vídeo">Posição do vídeo</button>
    </div>`;
  const m = modal("Sincronia por dois pontos", `
    <p class="muted small">Escolha duas falas bem separadas (por exemplo, a primeira e a última), diga onde cada uma deve começar, e as legendas entre elas acompanham. Dica: pause o vídeo no começo da fala e use “Posição do vídeo”.</p>
    ${row("p1", a === b ? 0 : a)}${row("p2", b)}`,
    `<button class="btn" data-x="close">Cancelar</button><button class="btn primary" data-x="go">Sincronizar</button>`, { wide: true });
  const upd = (id) => {
    const i = Math.max(1, Math.min(ED.cues.length, Number(m.$(`#${id}-n`).value) || 1)) - 1;
    m.$(`#${id}-old`).textContent = fmtTCms(ED.cues[i].start);
    m.$(`#${id}-new`).value = fmtTCms(ED.cues[i].start);
  };
  ["p1", "p2"].forEach((id) => m.$(`#${id}-n`).addEventListener("change", () => upd(id)));
  m.ov.addEventListener("click", async (e) => {
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (!x) return;
    if (x === "close") return m.close();
    if (x.endsWith("-now")) { m.$(`#${x.slice(0, 2)}-new`).value = fmtTCms(frameStart(curTime())); return; }
    const get = (id) => {
      const i = Number(m.$(`#${id}-n`).value) - 1, t = parseTC(m.$(`#${id}-new`).value);
      if (!(i >= 0 && i < ED.cues.length) || t == null) throw new Error("Confira os números das legendas e os tempos (00:00:00,000).");
      return [ED.cues[i].start, t];
    };
    try {
      const [ao, an] = get("p1"), [bo, bn] = get("p2");
      await syncOp("twopoint", { a_old: ao, a_new: an, b_old: bo, b_new: bn });
      m.close();
    } catch (err) { toast(err.message, true); }
  });
}

function openFps() {
  const rates = [["23.976", "23,976"], ["24", "24"], ["25", "25"], ["29.97", "29,97"], ["30", "30"]];
  const opt = (sel) => rates.map(([v, t]) => `<option value="${v}" ${v === sel ? "selected" : ""}>${t}</option>`).join("");
  const vf = ED.fps ? (Math.abs(ED.fps - 23.976) < 0.01 ? "23.976" : Math.abs(ED.fps - 29.97) < 0.01 ? "29.97" : String(Math.round(ED.fps))) : "23.976";
  const m = modal("Converter quadros por segundo", `
    <p class="muted small">Use quando a legenda foi feita para outra versão do vídeo (por exemplo, 25 quadros por segundo na Europa e 23,976 aqui) e vai ficando cada vez mais atrasada ou adiantada.</p>
    <div class="grid-2">
      <label class="field"><span>A legenda foi feita para</span><select id="fp-from">${opt(vf === "25" ? "23.976" : "25")}</select></label>
      <label class="field"><span>O vídeo tem${ED.fps ? " (detectado)" : ""}</span><select id="fp-to">${opt(vf)}</select></label>
    </div>`,
    `<button class="btn" data-x="close">Cancelar</button><button class="btn primary" data-x="go">Converter</button>`);
  m.ov.addEventListener("click", async (e) => {
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (x === "close") return m.close();
    if (x !== "go") return;
    const from = m.$("#fp-from").value, to = m.$("#fp-to").value;
    if (from === to) { toast("Escolha valores diferentes.", true); return; }
    const exact = (v) => ({ "23.976": 24000 / 1001, "29.97": 30000 / 1001 }[v] || Number(v));
    try { await syncOp("fps", { from_fps: exact(from), to_fps: exact(to) }); m.close(); } catch (err) { toast(err.message, true); }
  });
}

async function openScript(given = "") {
  if (!ED.video) { toast("Abra o vídeo primeiro: o texto é encaixado na fala dele.", true); return; }
  const path = given || await pickPath("script");
  if (!path) return;
  const m = modal("Texto sem tempo → legenda", `
    <p>O programa transcreve o vídeo (OpenAI), casa o seu texto com a fala e monta a legenda com os tempos certos. <b>O texto é o seu</b>: a transcrição só serve para achar o tempo.</p>
    <p class="muted small">Texto separado por linhas em branco: cada bloco vira uma legenda. Texto corrido: o programa divide nas regras do cliente.</p>
    <p id="sc-cost" class="small">Calculando o custo…</p>`,
    `<button class="btn" data-x="close">Cancelar</button><button class="btn primary" data-x="go" disabled>Começar</button>`);
  try {
    const est = await api("POST", `/api/editor/${ED.sid}/script`, { path, estimate: true });
    m.$("#sc-cost").innerHTML = `${fmtMin(est.minutes)} de fala · custo estimado <b>${fmtUSD(est.usd)}</b>.`;
    m.$("[data-x=go]").disabled = false;
  } catch (e) { m.$("#sc-cost").innerHTML = `<span class="note err" style="display:block">${esc(e.message)}</span>`; }
  m.ov.addEventListener("click", async (e) => {
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (x === "close") return m.close();
    if (x !== "go") return;
    try {
      const job = await api("POST", `/api/editor/${ED.sid}/script`, { path });
      m.close();
      await followJob(job.id, "Sincronizando o texto", "sincronizar");
    } catch (err) { toast(err.message, true); }
  });
}

/* acompanha um trabalho da fila e abre o resultado no editor */
async function followJob(jid, title, step) {
  const m = modal(title, `<p id="fj-msg">Na fila…</p><div class="bar"><i id="fj-bar" style="width:0%"></i></div>`,
    `<button class="btn" data-x="cancel">Cancelar</button>`);
  m.ov.dataset.busy = "1";
  let stop = false;
  m.$("[data-x=cancel]").onclick = async () => { stop = true; await api("POST", `/api/jobs/${jid}/cancel`).catch(() => {}); delete m.ov.dataset.busy; m.close(); };
  while (!stop) {
    await new Promise((r) => setTimeout(r, 1000));
    let j; try { j = await api("GET", `/api/jobs/${jid}`); } catch { continue; }
    if (j.live?.message) m.$("#fj-msg").textContent = j.live.message;
    const steps = j.live?.steps || {};
    const v = steps[step] || steps.transcrever;
    if (v && v[1]) m.$("#fj-bar").style.width = `${Math.round((v[0] / v[1]) * 100)}%`;
    if (j.status === "pronto") {
      m.close();
      const o = await api("POST", "/api/editor/open", { srt: j.outputs.srt, video: ED.video, profile_key: j.params.profile_key, client_id: ED.clientId, item_id: ED.itemId });
      ED.dirty = false;
      toast("Legenda sincronizada aberta no editor.");
      location.hash = `#/editor/${o.sid}`;
      return;
    }
    if (["erro", "cancelado", "interrompido"].includes(j.status)) {
      delete m.ov.dataset.busy;
      m.$("#fj-msg").innerHTML = `<span class="note err" style="display:block">${esc(j.error || "Interrompido.")}</span>`;
      m.$("[data-x=cancel]").textContent = "Fechar";
      m.$("[data-x=cancel]").onclick = () => m.close();
      return;
    }
  }
}

/* ------------------------------------------------------------ verificar */

async function openVerify() {
  document.getElementById("ed-drawer")?.remove();
  const dr = document.createElement("aside");
  dr.className = "drawer"; dr.id = "ed-drawer";
  dr.setAttribute("aria-label", "Verificação");
  document.body.appendChild(dr);
  const draw = async () => {
    dr.innerHTML = `<div class="drawer-head"><h2>Verificar</h2><button class="btn icon" data-v="close" aria-label="Fechar">×</button></div><p class="muted">Conferindo…</p>`;
    let issues = [];
    try { issues = (await api("POST", `/api/editor/${ED.sid}/qc`, { cues: sortedCues() })).issues; }
    catch (e) { dr.querySelector("p").textContent = e.message; return; }
    const errs = issues.filter((x) => x.severity === "erro").length;
    const byIdx = new Map();
    issues.forEach((x) => { if (!byIdx.has(x.index)) byIdx.set(x.index, []); byIdx.get(x.index).push(x); });
    dr.innerHTML = `
      <div class="drawer-head"><h2>Verificar</h2><button class="btn icon" data-v="close" aria-label="Fechar">×</button></div>
      <p class="small">${issues.length ? `<b>${byIdx.size}</b> legenda(s) com apontamentos · ${errs} erro(s), ${issues.length - errs} aviso(s).` : "Nenhum problema encontrado. Pode entregar."}
        <span class="muted">Regras: ${esc(ED.profile.name)}.</span></p>
      <div class="row">
        <button class="btn primary" data-v="fix" title="Sobreposição, intervalo mínimo, duração mínima, velocidade de leitura (quando há espaço), reticências e hífen">Corrigir tempos e estilo</button>
        <button class="btn" data-v="refresh">Conferir de novo</button>
      </div>
      <label class="small row" style="gap:6px"><input type="checkbox" id="v-chain" ${(ED.profile.chain_frames || 0) > 0 ? "checked" : ""}> Fechar intervalos curtos (menos de 12 quadros)</label>
      <ul class="issues">${[...byIdx.entries()].map(([i, xs]) => `<li><button data-v="go" data-i="${i - 1}">
          <span class="tnum muted">#${i} · ${esc(xs[0].timecode)}</span>
          ${xs.map((x) => `<span class="${x.severity === "erro" ? "err" : "warn"}">${esc(x.message)}</span>`).join("")}</button></li>`).join("")}</ul>`;
  };
  dr.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-v]");
    if (!b) return;
    const a = b.dataset.v;
    try {
      if (a === "close") dr.remove();
      if (a === "refresh") await draw();
      if (a === "go") { const i = Number(b.dataset.i); const idx = Math.min(i, ED.cues.length - 1); selectCue(idx); document.getElementById("ed-txt")?.focus(); }
      if (a === "fix") { await syncOp("fix", { chain: dr.querySelector("#v-chain").checked }); await draw(); }
    } catch (err) { toast(err.message, true); }
  });
  await draw();
}

/* ------------------------------------------------------------ entregar */

async function openDeliver(previa = {}) {
  if (!ED.cues.length) { toast("Não há legendas para entregar.", true); return; }
  let info;
  try { info = await api("GET", `/api/editor/${ED.sid}/deliver`); } catch (e) { toast(e.message, true); return; }
  recheckAll();
  const n = Object.keys(ED.issues).length;
  const who = S.state?.settings?.translator_name || "";
  const hasSig = ED.cues.slice(-3).some((c) => /^(Traducción|Tradução|Translation|Legendas?|Subtítulos?)\s*:/i.test(c.text));
  const m = modal("Entregar a legenda", `
    <label class="field"><span>Nome do arquivo ${info.naming ? `<em class="muted small">· padrão ${esc(info.profile)}</em>` : ""}</span>
      <input type="text" id="dl-name" value="${esc(info.name)}"></label>
    <label class="field"><span>Formato <em class="muted small">· ${esc(ORIGEM_FORMATO[info.formato_origem] || "padrão")}</em> ${helpBtn("formato")}</span>
      <select id="dl-fmt">${formatoOptions(info.formato || "srt")}</select></label>
    <label class="field"><span>Pasta</span>
      <div class="row" style="flex-wrap:nowrap"><input type="text" id="dl-folder" value="${esc(info.folder)}"><button class="btn" data-x="folder">Escolher</button></div></label>
    <label class="row small" style="gap:6px"><input type="checkbox" id="dl-sig" ${hasSig ? "disabled" : who ? "checked" : ""}>
      Assinatura no fim ${hasSig ? "<span class='muted'>(já tem)</span>" : ""}</label>
    <div class="row" id="dl-sigrow" style="flex-wrap:nowrap" ${hasSig ? "hidden" : ""}>
      <span class="small">${esc(info.signature_label)}:</span><input type="text" id="dl-who" value="${esc(who)}" placeholder="Seu nome" style="flex:1">
    </div>
    <p class="muted small" ${hasSig ? "hidden" : ""}>A assinatura entra depois da última legenda (antes dos créditos). Se os créditos começarem antes, ajuste o tempo dela depois.</p>
    <label class="row small" style="gap:6px"><input type="checkbox" id="dl-rep"> Salvar também o relatório de verificação (.qc.txt)</label>
    <label class="row small" style="gap:6px"><input type="checkbox" id="dl-alt" ${previa.temBase ? (getPref("cnt.dl.alt", "1") === "1" ? "checked" : "") : "disabled"}>
      Salvar o relatório das alterações (.alteracoes.txt) ${previa.temBase ? "" : '<span class="muted">(primeira entrega)</span>'}</label>
    <label class="row small" style="gap:6px"><input type="checkbox" id="dl-pdf" ${getPref("cnt.dl.pdf", "0") === "1" ? "checked" : ""}>
      Relatório em PDF para o cliente${previa.nota ? ` <span class="muted">(nota ${previa.nota.valor}/100)</span>` : ""} ${helpBtn("relatorio-cliente")}</label>
    ${n ? `<p class="note warn">${n} legenda(s) com apontamentos. <button class="btn link small" data-x="verify">Ver antes de entregar</button></p>` : `<p class="note ok">Nenhum problema encontrado.</p>`}`,
    `<button class="btn" data-x="close">Cancelar</button><button class="btn primary" data-x="go">Entregar</button>`, { wide: true });
  m.$("#dl-fmt").addEventListener("change", (e) => {   // troca só desta vez: acompanha a extensão do nome
    const ext = "." + e.target.value;
    m.$("#dl-name").value = m.$("#dl-name").value.replace(/\.(srt|vtt|ttml|dfxp|xml|ass|ssa)$/i, "") + ext;
  });
  m.$("#dl-who").addEventListener("input", (e) => { if (!hasSig) m.$("#dl-sig").checked = !!e.target.value.trim(); });
  m.ov.addEventListener("click", async (e) => {
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (!x) return;
    if (x === "close") return m.close();
    if (x === "verify") { m.close(); return openVerify(); }
    if (x === "folder") {
      const { paths } = await api("POST", "/api/dialog", { kind: "folder", initial: m.$("#dl-folder").value });
      if (paths[0]) m.$("#dl-folder").value = paths[0];
      return;
    }
    if (x !== "go") return;
    const who2 = m.$("#dl-who").value.trim();
    const body = { cues: sortedCues(), name: m.$("#dl-name").value.trim(), folder: m.$("#dl-folder").value.trim(),
      signature: m.$("#dl-sig").checked && who2 ? `${info.signature_label}: ${who2}` : "", report: m.$("#dl-rep").checked,
      formato: m.$("#dl-fmt").value, relatorio_alteracoes: m.$("#dl-alt").checked, relatorio_cliente: m.$("#dl-pdf").checked };
    if (previa.temBase) setPref("cnt.dl.alt", body.relatorio_alteracoes ? "1" : "0");
    setPref("cnt.dl.pdf", body.relatorio_cliente ? "1" : "0");
    try {
      if (who2 && who2 !== who) {
        S.state.settings = await api("PUT", "/api/settings", { translator_name: who2 }).catch(() => S.state.settings);
      }
      let r;
      try { r = await api("POST", `/api/editor/${ED.sid}/deliver`, body); }
      catch (err) {
        if (!/Já existe/.test(err.message) || !confirm(`${err.message}\n\nSubstituir? (uma cópia do arquivo antigo fica guardada)`)) throw err;
        r = await api("POST", `/api/editor/${ED.sid}/deliver`, { ...body, overwrite: true });
      }
      m.close();
      const sameFile = ED.srt && r.path.toLowerCase() === ED.srt.toLowerCase();
      if (r.signature_added) {   // mostra a assinatura no editor também
        const last = ED.cues[ED.cues.length - 1];
        snapshot(true);
        ED.cues.push({ start: r3(last.end + 0.5), end: r3(last.end + 0.5 + Math.max(ED.profile.min_duration, 2)), text: body.signature });
        changed(false); drawAll();
      }
      if (sameFile) { ED.dirty = r.signature_added ? ED.dirty : false; ED.savedAt = new Date().toLocaleTimeString("pt-BR").slice(0, 8); drawStatus(); }
      const extra = r.errors ? ` Atenção: ${r.errors} erro(s) de regra.` : r.warnings ? ` ${r.warnings} aviso(s) para conferir.` : "";
      const rels = [r.alteracoes && "relatório das alterações", r.pdf && "relatório em PDF"].filter(Boolean);
      toast(`Entregue: ${r.name} (${r.count} legendas).${extra}${rels.length ? ` Também: ${rels.join(" e ")}.` : ""}`);
      api("POST", "/api/open", { path: r.path, select: true }).catch(() => {});
    } catch (err) { toast(err.message, true); }
  });
}

/* ------------------------------------------------------- localizar/substituir */

function openFind() {
  document.getElementById("ed-find")?.remove();
  const box = document.createElement("div");
  box.className = "findbox"; box.id = "ed-find";
  box.innerHTML = `
    <input type="text" id="fd-q" placeholder="Localizar" aria-label="Localizar">
    <input type="text" id="fd-r" placeholder="Substituir por" aria-label="Substituir por">
    <label class="small"><input type="checkbox" id="fd-case"> Aa</label>
    <button class="btn" data-f="next" title="Enter">Próxima</button>
    <button class="btn" data-f="one">Substituir</button>
    <button class="btn" data-f="all">Substituir todas</button>
    <span class="small muted" id="fd-info"></span>
    <button class="btn icon" data-f="close" aria-label="Fechar">×</button>`;
  document.body.appendChild(box);
  const q = box.querySelector("#fd-q"), rr = box.querySelector("#fd-r");
  const sel = window.getSelection()?.toString();
  if (sel && sel.length < 60) q.value = sel;
  q.focus(); q.select();
  const rx = (g = false) => {
    const s = q.value; if (!s) return null;
    return new RegExp(s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), (box.querySelector("#fd-case").checked ? "" : "i") + (g ? "g" : ""));
  };
  const info = (t) => (box.querySelector("#fd-info").textContent = t);
  const next = () => {
    const r = rx(); if (!r) return;
    const n = ED.cues.length;
    for (let k = 1; k <= n; k++) {
      const i = (ED.sel + k) % n;
      const m = r.exec(ED.cues[i].text);
      if (m) {
        selectCue(i);
        const ta = document.getElementById("ed-txt");
        if (ta) { ta.focus(); ta.setSelectionRange(m.index, m.index + m[0].length); q.focus(); }
        info(`legenda ${i + 1}`);
        return true;
      }
    }
    info("não encontrado");
    return false;
  };
  box.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); next(); }
    if (e.key === "Escape") box.remove();
    e.stopPropagation();
  });
  box.addEventListener("click", (e) => {
    const a = e.target.closest("[data-f]")?.dataset.f;
    if (!a) return;
    if (a === "close") return box.remove();
    if (a === "next") return next();
    const r = rx(a === "all");
    if (!r) return;
    if (a === "one") {
      const c = ED.cues[ED.sel];
      if (c && r.test(c.text)) { setCue(ED.sel, { text: c.text.replace(rx(), rr.value) }, { force: true }); }
      next();
    }
    if (a === "all") {
      let count = 0;
      const nc = ED.cues.map((c) => { const t = c.text.replace(r, () => { count++; return rr.value; }); return t === c.text ? c : { ...c, text: t }; });
      if (!count) { info("não encontrado"); return; }
      snapshot(true); ED.cues = nc; changed(false); drawAll();
      info(`${count} substituição(ões)`);
      toast(`${count} substituição(ões). Ctrl+Z desfaz.`);
    }
  });
}
