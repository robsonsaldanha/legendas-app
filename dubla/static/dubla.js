/* CNT Dubla — tela do programa: projetos, roteiro de dublagem, elenco, estúdio de gravação e mixagem. */
"use strict";

const TOKEN = document.querySelector('meta[name="cnt-token"]').content;
const main = document.getElementById("main");
const S = { proj: null, estado: null, dubladores: [], timers: [], sel: null, mic: null };

/* ------------------------------------------------------------ utilidades */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (q, el = document) => el.querySelector(q);
const tc = (t) => { t = Math.max(0, t || 0); const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = Math.floor(t % 60), ms = Math.round((t % 1) * 1000);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(Math.min(999, ms)).padStart(3, "0")}`; };
const tcCurto = (t) => tc(t).slice(3, 11);
function lerTc(v) {
  const p = String(v || "").trim().split(/[:.,]/).map(Number);
  if (p.some(isNaN)) return null;
  if (p.length === 4) return p[0] * 3600 + p[1] * 60 + p[2] + p[3] / 1000;
  if (p.length === 3) return p[0] * 60 + p[1] + p[2] / 1000;
  if (p.length === 2) return p[0] * 60 + p[1];
  return p[0];
}
async function api(method, url, body) {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json", "X-Token": TOKEN }, body: body === undefined ? undefined : JSON.stringify(body) });
  let j = {}; try { j = await r.json(); } catch { /* vazio */ }
  if (!r.ok) { const e = new Error(j.error || "Não deu certo."); e.status = r.status; throw e; }
  return j;
}
function toast(msg, erro = false) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false; t.classList.toggle("err", !!erro);
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, erro ? 7000 : 3500);
}
const every = (ms, fn) => { const id = setInterval(fn, ms); S.timers.push(id); return id; };
const escolher = async (tipo, titulo) => (await api("POST", "/api/dialogo", { tipo, titulo })).caminhos[0] || "";
function modal(titulo, corpo, botoes, aoManter = null) {
  return new Promise((ok) => {
    const bg = document.createElement("div");
    bg.className = "db-modal-bg";
    bg.innerHTML = `<div class="db-modal" role="dialog" aria-modal="true"><h2>${esc(titulo)}</h2><div class="stack">${corpo}</div>
      <div class="row" style="justify-content:flex-end;margin-top:18px">${botoes.map(([v, t, c]) => `<button class="btn ${c || ""}" data-v="${v}">${esc(t)}</button>`).join("")}</div></div>`;
    document.body.appendChild(bg);
    bg.addEventListener("click", (e) => {
      const b = e.target.closest("[data-v]"); if (!b) return;
      if (b.dataset.keep) { aoManter?.(b.dataset.v, bg); return; }        // botões que não fecham (ex.: "Escolher…")
      ok({ v: b.dataset.v, el: bg }); bg.remove();
    });
    bg.querySelector("input,textarea,select")?.focus();
  });
}
async function acompanhar(t, titulo) {
  const bg = document.createElement("div");
  bg.className = "db-modal-bg";
  bg.innerHTML = `<div class="db-modal"><h2>${esc(titulo)}</h2><p id="tk-m" class="muted">Começando…</p><div class="db-barra"><i id="tk-b" style="width:0%"></i></div></div>`;
  document.body.appendChild(bg);
  try {
    while (t.situacao === "rodando") {
      await new Promise((r) => setTimeout(r, 500));
      t = await api("GET", `/api/tarefas/${t.id}`);
      if (t.mensagem) $("#tk-m", bg).textContent = t.mensagem;
      $("#tk-b", bg).style.width = `${Math.round((t.progresso || 0) * 100)}%`;
    }
  } finally { bg.remove(); }
  if (t.situacao === "erro") throw new Error(t.mensagem || "Não deu certo.");
  return t;
}
const corDe = (id) => (S.proj?.personagens || []).find((p) => p.id === id)?.cor || "var(--muted)";
const nomeDe = (id) => (S.proj?.personagens || []).find((p) => p.id === id)?.nome || "";

/* ------------------------------------------------------------ rotas */
const ROTAS = [
  [/^#?\/?$/, telaProjetos],
  [/^#\/dubladores$/, telaDubladores],
  [/^#\/configuracoes$/, telaConfig],
  [/^#\/p\/(\d+)(?:\/(roteiro|elenco|estudio|mixagem))?$/, telaProjeto],
];
async function rotear() {
  S.timers.forEach(clearInterval); S.timers = [];
  document.querySelectorAll("video,audio").forEach((v) => { try { v.pause(); } catch { /* */ } });
  const h = location.hash || "#/";
  const sec = h.startsWith("#/dubladores") ? "dubladores" : h.startsWith("#/configuracoes") ? "configuracoes" : "projetos";
  document.querySelectorAll("[data-nav]").forEach((a) => a.toggleAttribute("aria-current", a.dataset.nav === sec));
  for (const [rx, fn] of ROTAS) {
    const m = h.match(rx);
    if (m) {
      try { await fn(...m.slice(1)); } catch (e) { main.innerHTML = `<div class="panel"><p class="note err">${esc(e.message)}</p></div>`; }
      return;
    }
  }
  location.hash = "#/";
}
window.addEventListener("hashchange", rotear);

/* ------------------------------------------------------------ projetos */
async function telaProjetos() {
  document.getElementById("crumb").textContent = "Projetos";
  const [{ projetos }, { recebidos }] = await Promise.all([api("GET", "/api/projetos"), api("GET", "/api/recebidos")]);
  main.innerHTML = `
    <div class="page-head"><div><span class="eyebrow">CNT Dubla</span><h1 style="margin-top:6px">Projetos de dublagem</h1>
      <p class="muted">Roteiro, personagens, anéis, gravação, direção e mixagem — do vídeo ao áudio dublado.</p></div>
      <button class="btn primary" id="novo">+ Novo projeto</button></div>
    ${recebidos.length ? `<section class="panel" style="margin-bottom:16px"><h2>Enviados pelo CNT Legendas</h2>
      ${recebidos.map((r) => `<div class="row" style="justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line)">
        <span><b>${esc(r.nome)}</b> <span class="small muted">${esc(r.idioma_origem)} → ${esc(r.idioma_destino)} · enviado ${esc((r.enviado_em || "").replace("T", " "))}</span></span>
        <button class="btn primary sm" data-receber="${esc(r.arquivo)}">Criar o projeto</button></div>`).join("")}</section>` : ""}
    ${projetos.length ? `<div class="db-cards">${projetos.map((p) => `<div class="db-card" data-id="${p.id}">
        <span class="mono small muted">${esc(p.idioma_origem)} → ${esc(p.idioma_destino)}${p.cliente ? ` · ${esc(p.cliente)}` : ""}</span>
        <h3 style="margin:0">${esc(p.nome)}</h3>
        <span class="small muted">${p.falas} falas · ${p.aneis} anéis · ${p.aprovados} aprovados</span>
        <div class="db-barra"><i style="width:${p.aneis ? Math.round((100 * p.aprovados) / p.aneis) : 0}%"></i></div></div>`).join("")}</div>`
      : `<div class="panel"><p>Nenhum projeto ainda. Comece com o vídeo do episódio e, se tiver, o roteiro traduzido (.srt, .docx ou .txt — inclusive o que saiu do CNT Legendas).</p></div>`}`;
  main.querySelectorAll(".db-card").forEach((c) => c.addEventListener("click", () => { location.hash = `#/p/${c.dataset.id}/roteiro`; }));
  main.querySelectorAll("[data-receber]").forEach((b) => b.addEventListener("click", async () => {
    try { const p = await api("POST", "/api/recebidos/importar", { arquivo: b.dataset.receber }); location.hash = `#/p/${p.id}/roteiro`; } catch (e) { toast(e.message, true); }
  }));
  $("#novo").onclick = novoProjeto;
}

async function novoProjeto() {
  const r = await modal("Novo projeto de dublagem", `
    <label class="field"><span>Nome</span><input type="text" id="np-nome" placeholder="Ex.: Série X — T1 E01"></label>
    <label class="field"><span>Cliente</span><input type="text" id="np-cli"></label>
    <label class="field"><span>Vídeo</span><div class="row"><input type="text" id="np-video" style="flex:1"><button class="btn" data-v="video" data-keep="1">Escolher…</button></div></label>
    <label class="field"><span>Roteiro traduzido (opcional)</span><div class="row"><input type="text" id="np-rot" style="flex:1"><button class="btn" data-v="rot" data-keep="1">Escolher…</button></div></label>
    <div class="row"><label class="field"><span>Idioma original</span><select id="np-de"><option value="en">Inglês</option><option value="es">Espanhol</option><option value="pt-BR">Português</option><option value="ja">Japonês</option><option value="ko">Coreano</option><option value="fr">Francês</option></select></label>
      <label class="field"><span>Dublar para</span><select id="np-para"><option value="pt-BR">Português (Brasil)</option><option value="es-419">Espanhol (América Latina)</option><option value="en">Inglês</option></select></label></div>`,
  [["cancelar", "Cancelar"], ["criar", "Criar", "primary"]], async (v, el) => {
    const caminho = await escolher(v === "video" ? "media" : "script", v === "video" ? "Vídeo do episódio" : "Roteiro traduzido");
    if (caminho) $(v === "video" ? "#np-video" : "#np-rot", el).value = caminho;
  });
  if (r.v !== "criar") return;
  const corpo = { nome: $("#np-nome", r.el).value, cliente: $("#np-cli", r.el).value, video: $("#np-video", r.el).value, roteiro: $("#np-rot", r.el).value,
    idioma_origem: $("#np-de", r.el).value, idioma_destino: $("#np-para", r.el).value };
  try { const p = await api("POST", "/api/projetos", corpo); location.hash = `#/p/${p.id}/roteiro`; } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------ projeto */
async function carregar(pid) { S.proj = await api("GET", `/api/projetos/${pid}`); return S.proj; }

async function telaProjeto(pid, aba = "roteiro") {
  const p = await carregar(pid);
  document.getElementById("crumb").textContent = `Projetos / ${p.nome}`;
  const aprov = p.aneis.filter((a) => a.situacao === "aprovado").length;
  main.innerHTML = `
    <div class="page-head"><div><span class="eyebrow">${esc(p.idioma_origem)} → ${esc(p.idioma_destino)}${p.cliente ? ` · ${esc(p.cliente)}` : ""}</span>
      <h1 style="margin-top:6px">${esc(p.nome)}</h1>
      <p class="muted small">${p.falas.length} falas · ${p.personagens.length} personagens · ${p.aneis.length} anéis · ${aprov} aprovados</p></div>
      <div class="row"><button class="btn" id="pj-editar">Dados do projeto…</button></div></div>
    <nav class="db-tabs">${[["roteiro", "Roteiro"], ["elenco", "Elenco"], ["estudio", "Estúdio"], ["mixagem", "Mixagem e entrega"]].map(([k, t]) =>
      `<a href="#/p/${p.id}/${k}" ${k === aba ? 'aria-current="page"' : ""}>${t}</a>`).join("")}</nav>
    <div id="aba"></div>`;
  $("#pj-editar").onclick = () => editarProjeto(p);
  await ({ roteiro: abaRoteiro, elenco: abaElenco, estudio: abaEstudio, mixagem: abaMixagem })[aba](p);
}

async function editarProjeto(p) {
  const r = await modal("Projeto", `
    <label class="field"><span>Nome</span><input type="text" id="ep-nome" value="${esc(p.nome)}"></label>
    <label class="field"><span>Cliente</span><input type="text" id="ep-cli" value="${esc(p.cliente)}"></label>
    <label class="field"><span>Vídeo</span><input type="text" id="ep-video" value="${esc(p.video)}"></label>
    <label class="field"><span>Pasta das entregas <em>(vazio = ao lado do vídeo)</em></span><input type="text" id="ep-saida" value="${esc(p.pasta_saida)}"></label>`,
  [["apagar", "Apagar projeto", "danger"], ["cancelar", "Cancelar"], ["salvar", "Salvar", "primary"]]);
  try {
    if (r.v === "salvar") { await api("PUT", `/api/projetos/${p.id}`, { nome: $("#ep-nome", r.el).value, cliente: $("#ep-cli", r.el).value, video: $("#ep-video", r.el).value, pasta_saida: $("#ep-saida", r.el).value }); rotear(); }
    if (r.v === "apagar") {
      const c = await modal("Apagar o projeto?", `<p>Os takes gravados e as cópias que o programa fez são apagados. O vídeo e o roteiro originais não mudam.</p>`, [["n", "Cancelar"], ["s", "Apagar", "primary"]]);
      if (c.v === "s") { await api("DELETE", `/api/projetos/${p.id}`); location.hash = "#/"; }
    }
  } catch (e) { toast(e.message, true); }
}

/* --- vídeo do projeto (cópia leve quando o formato não toca no navegador) */
function blocoVideo(p, id = "vid") {
  return `<div class="db-video" id="${id}-box"><video id="${id}" controls preload="auto"></video><div class="db-legenda" id="${id}-leg"></div></div>`;
}
async function ligarVideo(p, id = "vid") {
  const v = document.getElementById(id);
  if (!v) return v;
  const pronto = async () => {
    const st = await api("GET", `/api/projetos/${p.id}/video`);
    if (st.situacao === "pronto") { v.src = st.url; return true; }
    if (st.situacao === "sem_video") { $(`#${id}-box`).innerHTML = `<p class="muted" style="padding:20px">Sem vídeo. Escolha o vídeo em “Projeto…”.</p>`; return true; }
    if (st.situacao === "erro") { $(`#${id}-leg`).textContent = st.mensagem || "Não consegui preparar o vídeo."; return true; }
    $(`#${id}-leg`).textContent = "Preparando o vídeo para tocar aqui…";
    return false;
  };
  if (!(await pronto())) { const t = every(2000, async () => { if (await pronto()) { clearInterval(t); $(`#${id}-leg`).textContent = ""; } }); }
  return v;
}

/* ------------------------------------------------------------ aba: roteiro */
async function abaRoteiro(p) {
  const aba = $("#aba");
  const nomes = p.personagens.map((x) => x.nome);
  S.comOriginal = p.falas.some((f) => (f.original || "").trim());
  aba.innerHTML = `
    <div class="row" style="margin-bottom:12px">
      <button class="btn" data-a="importar">Importar roteiro…</button>
      <button class="btn" data-a="transcrever" ${S.estado?.transcricao === false ? "disabled title='A transcrição local não está instalada'" : ""}>Transcrever o original</button>
      <button class="btn" data-a="sugerir">Sugerir personagens pela voz</button>
      <button class="btn" data-a="nova">+ Fala</button>
      <span class="grow"></span>
      <button class="btn primary" data-a="aneis">Gerar anéis</button></div>
    <div class="db-split">
      <div>${blocoVideo(p)}<p class="small muted" style="margin-top:8px">Clique no tempo de uma fala para tocar o trecho. Sílabas: <span class="db-sil ok">ok</span> cabe na boca ·
        <span class="db-sil longo">+n</span> longa · <span class="db-sil curto">−n</span> curta (comparando com o original).</p></div>
      <div style="max-height:75vh;overflow:auto"><table class="db-falas"><thead><tr><th>Tempo</th><th>Personagem</th>${S.comOriginal ? "<th>Original</th>" : ""}<th>Adaptação</th><th></th></tr></thead>
        <tbody id="falas">${p.falas.map((f) => linhaFala(f, p)).join("") || `<tr><td colspan="5" class="muted">Sem falas. Importe o roteiro ou transcreva o original.</td></tr>`}</tbody></table>
        <datalist id="pers-lista">${nomes.map((n) => `<option value="${esc(n)}">`).join("")}</datalist></div>
    </div>`;
  const v = await ligarVideo(p);
  let parar = null;
  v?.addEventListener("timeupdate", () => {
    const t = v.currentTime;
    const f = p.falas.find((x) => t >= x.inicio && t <= x.fim);
    $("#vid-leg").textContent = f ? `${nomeDe(f.personagem_id) ? nomeDe(f.personagem_id) + ": " : ""}${f.texto || f.original}` : "";
    if (parar != null && t >= parar) { v.pause(); parar = null; }
  });
  const salvar = async (tr, corpo) => {
    try {
      const f = await api("PUT", `/api/projetos/${p.id}/falas/${tr.dataset.id}`, corpo);
      const i = p.falas.findIndex((x) => x.id === f.id);
      p.falas[i] = f; p.ajustes[f.id] = f.ajuste;
      tr.querySelector(".db-sil-box").innerHTML = selo(f.ajuste);
      if ("personagem" in corpo) { await carregar(p.id); Object.assign(p, S.proj); tr.querySelector(".db-pers i").style.background = corDe(f.personagem_id); }
    } catch (e) { toast(e.message, true); }
  };
  aba.addEventListener("change", (e) => {
    const tr = e.target.closest("tr[data-id]"); if (!tr) return;
    if (e.target.name === "texto") salvar(tr, { texto: e.target.value });
    if (e.target.name === "personagem") salvar(tr, { personagem: e.target.value.toUpperCase() });
    if (e.target.name === "notas") salvar(tr, { notas: e.target.value });
    if (e.target.name === "inicio" || e.target.name === "fim") { const t = lerTc(e.target.value); if (t != null) salvar(tr, { [e.target.name]: t }); }
  });
  aba.onclick = async (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    const tr = b.closest("tr[data-id]");
    const f = tr && p.falas.find((x) => x.id === Number(tr.dataset.id));
    try {
      if (b.dataset.a === "tocar" && v && f) { v.currentTime = Math.max(0, f.inicio - 0.3); parar = f.fim + 0.3; v.play(); }
      if (b.dataset.a === "apagar" && f) { await api("DELETE", `/api/projetos/${p.id}/falas/${f.id}`); tr.remove(); }
      if (b.dataset.a === "ia" && f) await sugerirAdaptacao(p, f, tr);
      if (b.dataset.a === "importar") {
        const arq = await escolher("script", "Roteiro (.srt, .docx ou .txt)"); if (!arq) return;
        const r = await modal("Importar roteiro", `<p class="small">${esc(arq)}</p>
          <label class="row small"><input type="radio" name="como" value="texto" checked> É o texto traduzido/adaptado (vai para “Adaptação”)</label>
          <label class="row small"><input type="radio" name="como" value="original"> É o texto original (vai para “Original”)</label>
          <label class="row small"><input type="checkbox" id="imp-subst"> Apagar as falas que já estão no projeto</label>`, [["n", "Cancelar"], ["s", "Importar", "primary"]]);
        if (r.v !== "s") return;
        const x = await api("POST", `/api/projetos/${p.id}/importar`, { arquivo: arq, como: r.el.querySelector("input[name=como]:checked").value, substituir: $("#imp-subst", r.el).checked });
        toast(`${x.importadas} falas importadas (${x.com_personagem} já com personagem).`); rotear();
      }
      if (b.dataset.a === "transcrever") {
        const t = await acompanhar(await api("POST", `/api/projetos/${p.id}/transcrever`, {}), "Transcrevendo o original");
        toast(`${t.resultado.falas} falas transcritas.`); rotear();
      }
      if (b.dataset.a === "sugerir") {
        const r = await modal("Sugerir personagens pela voz", `<p>O programa compara as vozes das falas <b>sem personagem</b> e agrupa as parecidas em “VOZ 1”, “VOZ 2”…
          Depois você renomeia cada uma no Elenco. É uma sugestão: confira ouvindo.</p>
          <label class="field"><span>Quantos personagens falam? <em>(vazio = o programa decide)</em></span><input type="number" id="sg-k" min="1" max="40"></label>`,
        [["n", "Cancelar"], ["s", "Sugerir", "primary"]]);
        if (r.v !== "s") return;
        const t = await acompanhar(await api("POST", `/api/projetos/${p.id}/sugerir-personagens`, { k: Number($("#sg-k", r.el).value) || null }), "Comparando as vozes");
        toast(t.mensagem); rotear();
      }
      if (b.dataset.a === "nova") {
        const t = v ? v.currentTime : 0;
        await api("POST", `/api/projetos/${p.id}/falas`, { inicio: t, fim: t + 2, texto: "" }); rotear();
      }
      if (b.dataset.a === "aneis") await gerarAneis(p);
    } catch (err) { toast(err.message, true); }
  };
}
const selo = (a) => (a ? `<span class="db-sil ${a.situacao}" title="${a.silabas} sílabas na adaptação, ${a.referencia} na referência (${a.por_segundo}/s)">${a.situacao === "ok" ? "ok" : (a.diferenca > 0 ? "+" : "") + a.diferenca} · ${a.silabas}</span>` : "");
function linhaFala(f, p) {
  return `<tr data-id="${f.id}">
    <td><span class="db-tc" data-a="tocar" title="Tocar o trecho">▶ ${tcCurto(f.inicio)}</span><br>
      <input type="text" name="inicio" value="${tc(f.inicio)}" style="width:110px" class="mono small" aria-label="Entrada">
      <input type="text" name="fim" value="${tc(f.fim)}" style="width:110px;margin-top:2px" class="mono small" aria-label="Saída"></td>
    <td><span class="db-pers"><i style="background:${corDe(f.personagem_id)}"></i><input type="text" name="personagem" list="pers-lista" value="${esc(nomeDe(f.personagem_id))}" style="width:130px"></span></td>
    ${S.comOriginal ? `<td class="orig">${esc(f.original)}</td>` : ""}
    <td><textarea name="texto" rows="2">${esc(f.texto)}</textarea><input type="text" name="notas" placeholder="Observação para o diretor" value="${esc(f.notas)}" class="small" style="margin-top:4px"></td>
    <td><div class="db-sil-box">${selo(p.ajustes[f.id])}</div>
      <button class="btn sm" data-a="ia" title="Sugestões para caber na boca (IA)" ${S.estado?.chave_ia ? "" : "disabled"}>IA</button>
      <button class="btn sm ghost" data-a="apagar" title="Apagar a fala">×</button></td></tr>`;
}
async function sugerirAdaptacao(p, f, tr) {
  const btn = tr.querySelector("[data-a=ia]"); btn.disabled = true; btn.textContent = "…";
  try {
    const r = await api("POST", `/api/projetos/${p.id}/falas/${f.id}/adaptar`, {});
    const esc2 = r.opcoes.map((o, i) => `<label class="row small" style="align-items:flex-start"><input type="radio" name="op" value="${i}" ${i ? "" : "checked"}>
      <span>${esc(o.texto)} ${selo(o)}</span></label>`).join("");
    const m = await modal("Sugestões de adaptação", `<p class="small muted">Original: ${esc(f.original)}</p>${esc2}`, [["n", "Cancelar"], ["s", "Usar esta", "primary"]]);
    if (m.v === "s") {
      const o = r.opcoes[Number(m.el.querySelector("input[name=op]:checked").value)];
      tr.querySelector("textarea[name=texto]").value = o.texto;
      tr.querySelector("textarea[name=texto]").dispatchEvent(new Event("change", { bubbles: true }));
    }
  } finally { btn.disabled = false; btn.textContent = "IA"; }
}
async function gerarAneis(p, confirmar = false) {
  const r = await modal("Gerar anéis", `<p>As falas seguidas de cada personagem viram anéis (trechos para gravar), numerados na ordem do vídeo.</p>
    <div class="row"><label class="field"><span>Duração máxima (s)</span><input type="number" id="an-max" value="20" min="5" max="60"></label>
      <label class="field"><span>Pausa máxima entre falas (s)</span><input type="number" id="an-pausa" value="4" min="0" max="20" step="0.5"></label></div>`,
  [["n", "Cancelar"], ["s", "Gerar", "primary"]]);
  if (r.v !== "s") return;
  try {
    const x = await api("POST", `/api/projetos/${p.id}/aneis`, { max_duracao: Number($("#an-max", r.el).value), max_pausa: Number($("#an-pausa", r.el).value), confirmar });
    toast(`${x.aneis} anéis criados.${x.sem_tempo ? ` ${x.sem_tempo} falas sem tempo ficaram de fora.` : ""}`);
    location.hash = `#/p/${p.id}/elenco`;
  } catch (e) {
    if (e.status === 409) {
      const c = await modal("Gerar de novo?", `<p>${esc(e.message)}</p>`, [["n", "Cancelar"], ["s", "Apagar e gerar", "primary"]]);
      if (c.v === "s") { await api("POST", `/api/projetos/${p.id}/aneis`, { confirmar: true, max_duracao: 20, max_pausa: 4 }); rotear(); }
    } else toast(e.message, true);
  }
}

/* ------------------------------------------------------------ aba: elenco */
async function abaElenco(p) {
  const [{ dubladores }, rel] = await Promise.all([api("GET", "/api/dubladores"), api("GET", `/api/projetos/${p.id}/relatorio`)]);
  S.dubladores = dubladores;
  const nFalas = (id) => p.falas.filter((f) => f.personagem_id === id).length;
  const nAneis = (id) => p.aneis.filter((a) => a.personagem_id === id).length;
  const vozTxt = (v) => (!v ? "Voz do sistema" : v.tipo === "servico" ? `Serviço: ${v.voz || "marin"}` : v.tipo === "clonada" ? "Clonada (com termo)" : "Voz do sistema");
  $("#aba").innerHTML = `<div class="db-grid2">
    <section class="panel"><h2>Personagens</h2><table class="db-tabela"><thead><tr><th></th><th>Nome</th><th>Dublador</th><th>Voz por IA</th><th>Falas</th><th>Anéis</th></tr></thead>
      <tbody>${p.personagens.map((x) => `<tr data-id="${x.id}"><td><input type="color" name="cor" value="${esc(x.cor || "#C9D94B")}" aria-label="Cor"></td>
        <td><input type="text" name="nome" value="${esc(x.nome)}" style="width:140px"></td>
        <td><select name="dublador_id"><option value="">—</option>${dubladores.map((d) => `<option value="${d.id}" ${d.id === x.dublador_id ? "selected" : ""}>${esc(d.nome)}</option>`).join("")}</select></td>
        <td><button class="btn sm" data-a="voz">${esc(vozTxt(x.voz_ia))}</button></td>
        <td class="mono">${nFalas(x.id)}</td><td class="mono">${nAneis(x.id)}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Sem personagens. Eles aparecem quando as falas ganham nome no roteiro.</td></tr>`}</tbody></table>
      <p class="small muted">Mudar o nome para o de outro personagem junta os dois.</p>
      <div class="row"><button class="btn" data-a="novo-dub">+ Dublador</button></div></section>
    <section class="panel"><h2>Anéis por dublador</h2>
      <p class="small muted">${rel.total} anéis · ${rel.situacao.aprovado} aprovados · ${rel.situacao.gravado} gravados · ${rel.situacao.refazer} para refazer · ${rel.situacao.pendente} pendentes</p>
      <table class="db-tabela"><thead><tr><th>Dublador</th><th>Personagens</th><th>Anéis</th><th>Aprovados</th><th>Minutos</th></tr></thead>
      <tbody>${rel.dubladores.map((d) => `<tr><td><b>${esc(d.dublador)}</b></td><td class="small">${d.personagens.map(esc).join(", ")}</td><td class="mono">${d.aneis}</td>
        <td class="mono">${d.aprovados}</td><td class="mono">${(d.segundos / 60).toFixed(1)}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">Gere os anéis no Roteiro.</td></tr>`}</tbody></table></section>
  </div>`;
  const aba = $("#aba");
  aba.onchange = async (e) => {
    const tr = e.target.closest("tr[data-id]"); if (!tr) return;
    try { await api("PUT", `/api/projetos/${p.id}/personagens/${tr.dataset.id}`, { [e.target.name]: e.target.value }); if (e.target.name === "nome") rotear(); }
    catch (err) { toast(err.message, true); }
  };
  aba.onclick = async (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    try {
      if (b.dataset.a === "novo-dub") { await editarDublador(); rotear(); }
      if (b.dataset.a === "voz") {
        const per = p.personagens.find((x) => x.id === Number(b.closest("tr").dataset.id));
        const v = per.voz_ia || { tipo: "sistema" };
        const r = await modal(`Voz por IA — ${per.nome}`, `<p class="small muted">Para gerar takes guia (ou finais) com IA no Estúdio.</p>
          <label class="row small"><input type="radio" name="tipo" value="sistema" ${v.tipo === "sistema" ? "checked" : ""}> Voz do sistema (no computador, sem custo)</label>
          <label class="row small"><input type="radio" name="tipo" value="servico" ${v.tipo === "servico" ? "checked" : ""} ${S.estado?.chave_ia ? "" : "disabled"}> Serviço de voz pago (sua chave de IA)</label>
          <div class="row" style="margin-left:24px"><label class="field"><span>Voz</span><select id="vz-voz">${["marin", "cedar", "coral", "nova", "shimmer", "sage", "alloy", "ash", "ballad", "echo", "fable", "onyx", "verse"].map((x) => `<option ${x === v.voz ? "selected" : ""}>${x}</option>`).join("")}</select></label>
            <label class="field" style="flex:1"><span>Como falar</span><input type="text" id="vz-instr" value="${esc(v.instrucoes || "")}" placeholder="Ex.: menino de 10 anos, animado"></label></div>
          <label class="row small"><input type="radio" name="tipo" value="clonada" ${v.tipo === "clonada" ? "checked" : ""}> Voz clonada do dublador (precisa do termo de consentimento registrado)</label>`,
        [["n", "Cancelar"], ["s", "Salvar", "primary"]]);
        if (r.v !== "s") return;
        const tipo = r.el.querySelector("input[name=tipo]:checked").value;
        await api("PUT", `/api/projetos/${p.id}/personagens/${per.id}`, { voz_ia: { tipo, voz: $("#vz-voz", r.el).value, instrucoes: $("#vz-instr", r.el).value, dublador_id: per.dublador_id } });
        rotear();
      }
    } catch (err) { toast(err.message, true); }
  };
}
async function editarDublador(d = {}) {
  const r = await modal(d.id ? "Dublador" : "Novo dublador", `
    <label class="field"><span>Nome</span><input type="text" id="dd-nome" value="${esc(d.nome || "")}"></label>
    <label class="field"><span>Contato</span><input type="text" id="dd-cont" value="${esc(d.contato || "")}"></label>
    <label class="field"><span>Observações</span><input type="text" id="dd-obs" value="${esc(d.observacoes || "")}"></label>`, [["n", "Cancelar"], ["s", "Salvar", "primary"]]);
  if (r.v !== "s") return null;
  const corpo = { nome: $("#dd-nome", r.el).value, contato: $("#dd-cont", r.el).value, observacoes: $("#dd-obs", r.el).value };
  return d.id ? api("PUT", `/api/dubladores/${d.id}`, corpo) : api("POST", "/api/dubladores", corpo);
}

/* ------------------------------------------------------------ dubladores (todos os projetos) */
async function telaDubladores() {
  document.getElementById("crumb").textContent = "Dubladores";
  const { dubladores } = await api("GET", "/api/dubladores");
  main.innerHTML = `<div class="page-head"><div><span class="eyebrow">Elenco</span><h1 style="margin-top:6px">Dubladores</h1>
      <p class="muted">Quem dubla no estúdio. O termo de consentimento é necessário para usar a voz clonada de alguém.</p></div>
      <button class="btn primary" id="nd">+ Dublador</button></div>
    <section class="panel"><table class="db-tabela"><thead><tr><th>Nome</th><th>Contato</th><th>Observações</th><th>Voz clonada</th><th></th></tr></thead>
    <tbody>${dubladores.map((d) => `<tr data-id="${d.id}"><td><b>${esc(d.nome)}</b></td><td>${esc(d.contato)}</td><td class="small">${esc(d.observacoes)}</td>
      <td>${d.consentimentos ? `<span class="db-sit aprovado">termo registrado</span>` : `<span class="db-sit">sem termo</span>`}</td>
      <td><button class="btn sm" data-a="editar">Editar</button> <button class="btn sm" data-a="termo">Termo de voz…</button></td></tr>`).join("") || `<tr><td colspan="5" class="muted">Nenhum ainda.</td></tr>`}</tbody></table></section>`;
  $("#nd").onclick = async () => { try { await editarDublador(); rotear(); } catch (e) { toast(e.message, true); } };
  main.onclick = async (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    const d = dubladores.find((x) => x.id === Number(b.closest("tr").dataset.id));
    try {
      if (b.dataset.a === "editar") { await editarDublador(d); rotear(); }
      if (b.dataset.a === "termo") await termoDeVoz(d);
    } catch (err) { toast(err.message, true); }
  };
}
async function termoDeVoz(d) {
  const { consentimentos } = await api("GET", `/api/dubladores/${d.id}/consentimentos`);
  const r = await modal(`Termo de consentimento de voz — ${d.nome}`, `
    <p class="small">A voz é dado pessoal sensível. Só registre se <b>${esc(d.nome)}</b> assinou um termo autorizando o uso da voz dele(a) por IA
      — para quê, em quais projetos e por quanto tempo. O programa guarda uma cópia do termo e da amostra de voz neste computador.</p>
    ${consentimentos.length ? `<table class="db-tabela"><tbody>${consentimentos.map((c) => `<tr><td>Assinado em ${esc(c.assinado_em)}</td><td class="small">${esc(c.escopo)}</td>
      <td>${c.revogado_em ? `<span class="db-sit refazer">revogado</span>` : `<button class="btn sm danger" data-v="rev-${c.id}">Revogar</button>`}</td></tr>`).join("")}</tbody></table>` : ""}
    <h3 style="margin:8px 0 0">Registrar termo novo</h3>
    <div class="row"><input type="text" id="tm-termo" placeholder="Termo assinado (PDF ou imagem)" style="flex:1"><button class="btn" data-v="pick-termo" data-keep="1">Escolher…</button></div>
    <div class="row"><input type="text" id="tm-amostra" placeholder="Amostra de voz (10 a 30 s, sem música)" style="flex:1"><button class="btn" data-v="pick-amostra" data-keep="1">Escolher…</button></div>
    <div class="row"><label class="field"><span>Assinado em</span><input type="date" id="tm-data"></label>
      <label class="field" style="flex:1"><span>Pode ser usada para</span><input type="text" id="tm-escopo" placeholder="Ex.: guias da série X, até 12/2027"></label></div>`,
  [["n", "Fechar"], ["s", "Registrar", "primary"]], async (v, el) => {
    const c = await escolher(v === "pick-termo" ? "any" : "media", "Escolher arquivo");
    if (c) $(v === "pick-termo" ? "#tm-termo" : "#tm-amostra", el).value = c;
  });
  if (r.v.startsWith("rev-")) { await api("DELETE", `/api/consentimentos/${r.v.slice(4)}`); toast("Termo revogado: a amostra de voz foi apagada."); return rotear(); }
  if (r.v !== "s") return;
  await api("POST", `/api/dubladores/${d.id}/consentimentos`, { termo: $("#tm-termo", r.el).value, amostra: $("#tm-amostra", r.el).value,
    assinado_em: $("#tm-data", r.el).value, escopo: $("#tm-escopo", r.el).value });
  toast("Termo registrado."); rotear();
}

/* ------------------------------------------------------------ aba: estúdio */
async function abaEstudio(p) {
  if (!p.aneis.length) { $("#aba").innerHTML = `<div class="panel"><p>Sem anéis. Gere os anéis no Roteiro.</p></div>`; return; }
  const filtro = S.filtro || { dublador: "", sit: "" };
  const dubPer = (a) => p.personagens.find((x) => x.id === a.personagem_id)?.dublador || "";
  const lista = p.aneis.filter((a) => (!filtro.dublador || dubPer(a) === filtro.dublador) && (!filtro.sit || a.situacao === filtro.sit));
  if (!S.sel || !p.aneis.some((a) => a.id === S.sel)) S.sel = (lista[0] || p.aneis[0]).id;
  const dubs = [...new Set(p.personagens.map((x) => x.dublador).filter(Boolean))];
  $("#aba").innerHTML = `<div class="db-estudio">
    <aside class="stack" style="gap:8px">
      <div class="row"><select id="f-dub"><option value="">Todos os dubladores</option>${dubs.map((d) => `<option ${d === filtro.dublador ? "selected" : ""}>${esc(d)}</option>`).join("")}</select>
        <select id="f-sit"><option value="">Todas</option>${["pendente", "gravado", "refazer", "aprovado"].map((s) => `<option value="${s}" ${s === filtro.sit ? "selected" : ""}>${s}</option>`).join("")}</select></div>
      <div class="db-aneis" id="lista-aneis">${lista.map((a) => `<button class="db-anel" data-id="${a.id}" aria-current="${a.id === S.sel}">
        <span class="n">${a.numero}</span><span><span class="db-pers"><i style="background:${corDe(a.personagem_id)}"></i>${esc(nomeDe(a.personagem_id) || "(sem personagem)")}</span><br>
        <span class="mono small muted">${tcCurto(a.inicio)} · ${(a.fim - a.inicio).toFixed(1)} s · ${a.takes.length} take(s)</span></span>
        <span class="db-sit ${a.situacao}">${a.situacao}</span></button>`).join("")}</div>
    </aside>
    <section id="anel"></section></div>`;
  $("#f-dub").onchange = (e) => { S.filtro = { ...filtro, dublador: e.target.value }; abaEstudio(p); };
  $("#f-sit").onchange = (e) => { S.filtro = { ...filtro, sit: e.target.value }; abaEstudio(p); };
  $("#lista-aneis").onclick = (e) => { const b = e.target.closest(".db-anel"); if (b) { S.sel = Number(b.dataset.id); abaEstudio(p); } };
  await painelAnel(p, p.aneis.find((a) => a.id === S.sel));
}

async function painelAnel(p, a) {
  const falas = p.falas.filter((f) => a.falas.includes(f.id));
  const pre = Number(localStorage.getItem("dubla.pre") || 3);
  const guia = localStorage.getItem("dubla.guia") !== "0";
  $("#anel").innerHTML = `
    <div class="row" style="justify-content:space-between;margin-bottom:10px"><h2 style="margin:0">Anel ${a.numero} · <span class="db-pers"><i style="background:${corDe(a.personagem_id)}"></i>${esc(nomeDe(a.personagem_id))}</span></h2>
      <span class="mono small muted">${tc(a.inicio)} → ${tc(a.fim)}</span></div>
    ${blocoVideo(p, "sv")}
    <div class="row" style="margin:10px 0">
      <button class="btn" data-a="tocar">▶ Tocar o anel</button>
      <button class="btn rec" data-a="gravar" id="b-gravar">● Gravar</button>
      <label class="row small"><input type="checkbox" id="guia" ${guia ? "checked" : ""}> Áudio original de guia <span class="muted">(use fone)</span></label>
      <label class="row small">Pré-rolagem <input type="number" id="pre" value="${pre}" min="0" max="10" step="0.5" style="width:60px"> s</label>
      <span class="db-medidor" title="Volume do microfone"><i id="medidor"></i></span>
      <span class="grow"></span>
      <button class="btn" data-a="voz-ia" title="Take com voz por IA (guia ou final), conforme a voz do personagem no Elenco">Voz por IA</button></div>
    <div class="db-texto-anel">${falas.map((f) => `<p><span class="q">${tcCurto(f.inicio)}</span> ${esc(f.texto || f.original || "")}${f.notas ? `<br><span class="small muted">↳ ${esc(f.notas)}</span>` : ""}</p>`).join("") || `<p class="muted">Sem texto.</p>`}</div>
    <h3>Takes</h3>
    <div class="db-takes">${a.takes.map((t, i) => `<div class="db-take ${t.id === a.take_aprovado_id ? "aprovado" : ""}" data-id="${t.id}">
      <b>${i + 1}</b> <span class="mono small">${t.duracao.toFixed(1)} s</span>${t.origem === "ia" ? ` <span class="db-sit">IA</span>` : ""}
      <span class="small muted">voz ${(t.voz_ini + t.deslocamento).toFixed(2)} s do início do anel</span>
      <button class="btn sm" data-a="ouvir">▶ Com o vídeo</button>
      <span class="small">Sincronia <button class="btn sm ghost" data-a="adiantar" title="Adiantar 40 ms">−</button><span class="mono">${(t.deslocamento * 1000).toFixed(0)} ms</span><button class="btn sm ghost" data-a="atrasar" title="Atrasar 40 ms">+</button></span>
      <input type="text" data-nota placeholder="Nota" value="${esc(t.nota)}" style="flex:1;min-width:120px">
      <button class="btn sm ${t.id === a.take_aprovado_id ? "primary" : ""}" data-a="aprovar">${t.id === a.take_aprovado_id ? "✓ Aprovado" : "Aprovar"}</button>
      <button class="btn sm ghost" data-a="apagar" title="Apagar o take">×</button></div>`).join("") || `<p class="muted small">Nenhum take ainda.</p>`}</div>
    <h3>Direção</h3>
    <div class="row"><select id="sit">${["pendente", "gravado", "refazer", "aprovado"].map((s) => `<option value="${s}" ${s === a.situacao ? "selected" : ""}>${s}</option>`).join("")}</select>
      <input type="text" id="nota-dir" value="${esc(a.nota_direcao)}" placeholder="Nota do diretor / revisor para este anel" style="flex:1"></div>`;
  const v = await ligarVideo(p, "sv");
  let fimEm = null, gravando = null, audioTake = null;
  const legenda = () => {
    const t = v.currentTime;
    const f = falas.find((x) => t >= x.inicio && t <= x.fim);
    $("#sv-leg").textContent = f ? (f.texto || f.original) : "";
    if (fimEm != null && t >= fimEm) { v.pause(); audioTake?.pause(); fimEm = null; if (gravando) gravando.stop(); }
  };
  v?.addEventListener("timeupdate", legenda);
  const prepararVideo = async (inicio) => {
    v.muted = !$("#guia").checked;
    v.currentTime = Math.max(0, inicio);
    await new Promise((ok) => { if (v.readyState >= 2 && Math.abs(v.currentTime - inicio) < 0.05) ok(); else v.addEventListener("seeked", ok, { once: true }); setTimeout(ok, 1500); });
  };
  $("#guia").onchange = (e) => localStorage.setItem("dubla.guia", e.target.checked ? "1" : "0");
  $("#pre").onchange = (e) => localStorage.setItem("dubla.pre", e.target.value);
  $("#sit").onchange = async (e) => { await api("PUT", `/api/projetos/${p.id}/aneis/${a.id}`, { situacao: e.target.value }); a.situacao = e.target.value; };
  $("#nota-dir").onchange = (e) => api("PUT", `/api/projetos/${p.id}/aneis/${a.id}`, { nota_direcao: e.target.value }).catch((er) => toast(er.message, true));
  $("#anel").addEventListener("change", (e) => {
    const box = e.target.closest(".db-take"); if (box && e.target.matches("[data-nota]")) api("PUT", `/api/takes/${box.dataset.id}`, { nota: e.target.value });
  });

  async function gravar() {
    if (gravando) { gravando.stop(); return; }
    if (!S.mic) {
      try { S.mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }); }
      catch { toast("Não consegui usar o microfone. Confira se ele está ligado e se o programa tem permissão.", true); return; }
      ligarMedidor(S.mic);
    }
    const preRol = Math.max(0, Number($("#pre").value) || 0);
    const inicio = Math.max(0, a.inicio - preRol);
    await prepararVideo(inicio);
    const pedacos = [];
    const rec = new MediaRecorder(S.mic);
    rec.ondataavailable = (ev) => { if (ev.data.size) pedacos.push(ev.data); };
    const caixa = $("#sv-box");
    const cont = document.createElement("div"); cont.className = "db-contagem"; caixa.appendChild(cont);
    const sel = document.createElement("div"); sel.className = "db-rec"; sel.textContent = "● GRAVANDO"; caixa.appendChild(sel);
    const tick = setInterval(() => { const falta = a.inicio - v.currentTime; cont.textContent = falta > 0.05 ? Math.ceil(falta) : ""; }, 100);
    $("#b-gravar").textContent = "■ Parar";
    rec.onstop = async () => {
      clearInterval(tick); cont.remove(); sel.remove(); v.pause(); gravando = null; $("#b-gravar").textContent = "● Gravar";
      const blob = new Blob(pedacos, { type: pedacos[0]?.type || "audio/webm" });
      const b64 = await new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(",")[1] || ""); fr.readAsDataURL(blob); });
      try {
        await api("POST", `/api/projetos/${p.id}/aneis/${a.id}/takes`, { audio: b64, pre_rolagem: a.inicio - inicio });
        await carregar(p.id); Object.assign(p, S.proj); toast("Take guardado."); abaEstudio(p);
      } catch (e) { toast(e.message, true); }
    };
    gravando = rec;
    fimEm = a.fim + 0.3;
    rec.start();
    await v.play();
  }
  function ligarMedidor(stream) {
    try {
      const ctx = new AudioContext(); const an = ctx.createAnalyser(); an.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Float32Array(an.fftSize);
      every(80, () => { an.getFloatTimeDomainData(buf); let s = 0; for (const x of buf) s += x * x; const db = 10 * Math.log10(s / buf.length + 1e-9);
        const m = document.getElementById("medidor"); if (m) m.style.width = `${Math.max(0, Math.min(100, (db + 60) * 1.8))}%`; });
    } catch { /* sem medidor */ }
  }
  $("#anel").onclick = async (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    const box = b.closest(".db-take");
    const t = box && a.takes.find((x) => x.id === Number(box.dataset.id));
    try {
      if (b.dataset.a === "tocar") { audioTake?.pause(); await prepararVideo(Math.max(0, a.inicio - 1)); fimEm = a.fim + 0.3; v.play(); }
      if (b.dataset.a === "gravar") await gravar();
      if (b.dataset.a === "ouvir" && t) {
        audioTake?.pause();
        audioTake = new Audio(`/media/take/${t.id}`);
        await prepararVideo(a.inicio + t.deslocamento);
        v.muted = true;                                   // só a dublagem (o M&E entra na mixagem)
        fimEm = a.inicio + t.deslocamento + t.duracao;
        await Promise.all([v.play(), audioTake.play()]);
      }
      if ((b.dataset.a === "adiantar" || b.dataset.a === "atrasar") && t) {
        await api("PUT", `/api/takes/${t.id}`, { deslocamento: t.deslocamento + (b.dataset.a === "adiantar" ? -0.04 : 0.04) });
        await carregar(p.id); Object.assign(p, S.proj); painelAnel(p, p.aneis.find((x) => x.id === a.id));
      }
      if (b.dataset.a === "aprovar" && t) {
        await api("PUT", `/api/projetos/${p.id}/aneis/${a.id}`, { take_aprovado_id: t.id === a.take_aprovado_id ? null : t.id });
        await carregar(p.id); Object.assign(p, S.proj); abaEstudio(p);
      }
      if (b.dataset.a === "apagar" && t) {
        const c = await modal("Apagar este take?", "<p>O áudio gravado é apagado.</p>", [["n", "Cancelar"], ["s", "Apagar", "primary"]]);
        if (c.v === "s") { await api("DELETE", `/api/takes/${t.id}`); await carregar(p.id); Object.assign(p, S.proj); abaEstudio(p); }
      }
      if (b.dataset.a === "voz-ia") {
        b.disabled = true; b.textContent = "Gerando…";
        try { await api("POST", `/api/projetos/${p.id}/aneis/${a.id}/voz-ia`, {}); await carregar(p.id); Object.assign(p, S.proj); toast("Take por IA criado."); abaEstudio(p); }
        finally { b.disabled = false; b.textContent = "Voz por IA"; }
      }
    } catch (err) { toast(err.message, true); }
  };
}

/* ------------------------------------------------------------ aba: mixagem */
async function abaMixagem(p) {
  const aprov = p.aneis.filter((a) => a.take_aprovado_id).length;
  $("#aba").innerHTML = `<div class="db-grid2">
    <section class="panel stack"><h2 style="margin:0">Música e efeitos (M&E)</h2>
      <p class="small muted">A faixa sem as vozes originais, que vai por baixo da dublagem.</p>
      <p>${p.me ? `<span class="db-sit aprovado">pronta</span> <span class="mono small">${esc(p.me)}</span>` : `<span class="db-sit">sem M&E</span>`}</p>
      <div class="row"><button class="btn" data-a="me-arq">Usar a faixa do cliente…</button>
        <button class="btn" data-a="me-sep" ${S.estado?.separador === false ? "disabled title='O separador não está instalado'" : ""}>Separar do vídeo original</button></div>
      <p class="small muted">Separar tira a voz original do áudio do vídeo no computador (com placa de vídeo é rápido). Confira o resultado: a faixa do cliente é sempre melhor.</p></section>
    <section class="panel stack"><h2 style="margin:0">Entregas</h2>
      <p class="small">${aprov} de ${p.aneis.length} anéis aprovados.${aprov < p.aneis.length ? " Os anéis sem take aprovado ficam em silêncio." : ""}</p>
      ${[["mix", "Mix final dublado (.wav)"], ["stems", "Faixas por personagem (.wav)"], ["video", "Vídeo com o áudio dublado"], ["roteiro", "Roteiro de dublagem (.docx)"], ["relatorio", "Anéis por dublador (.docx)"], ["legenda", "Legenda com o texto dublado (.srt)"]]
        .map(([k, t]) => `<label class="row small"><input type="checkbox" value="${k}" checked> ${t}</label>`).join("")}
      <div class="row"><label class="field"><span>Volume das vozes</span><input type="number" id="vol-v" value="1" min="0" max="3" step="0.1" style="width:90px"></label>
        <label class="field"><span>Volume do M&E</span><input type="number" id="vol-me" value="1" min="0" max="3" step="0.1" style="width:90px"></label></div>
      <div><button class="btn primary" data-a="exportar">Exportar</button></div>
      <div id="exp-res"></div></section></div>`;
  $("#aba").onclick = async (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    try {
      if (b.dataset.a === "me-arq") { const c = await escolher("media", "Faixa de música e efeitos"); if (c) { await api("POST", `/api/projetos/${p.id}/me`, { arquivo: c }); rotear(); } }
      if (b.dataset.a === "me-sep") { await acompanhar(await api("POST", `/api/projetos/${p.id}/me`, {}), "Separando a música e os efeitos"); toast("M&E pronto."); rotear(); }
      if (b.dataset.a === "exportar") {
        const itens = [...$("#aba").querySelectorAll("input[type=checkbox]:checked")].map((x) => x.value);
        const t = await acompanhar(await api("POST", `/api/projetos/${p.id}/exportar`, { itens, volume_vozes: Number($("#vol-v").value), volume_me: Number($("#vol-me").value) }), "Exportando");
        $("#exp-res").innerHTML = `<p class="note">${esc(t.mensagem)}</p><ul class="small">${t.resultado.arquivos.map((f) => `<li class="mono">${esc(f.split(/[\\/]/).pop())}</li>`).join("")}</ul>
          <button class="btn" data-a="pasta">Abrir a pasta</button>`;
        S.ultimaPasta = t.resultado.pasta;
      }
      if (b.dataset.a === "pasta" && S.ultimaPasta) await api("POST", "/api/abrir", { caminho: S.ultimaPasta });
    } catch (err) { toast(err.message, true); }
  };
}

/* ------------------------------------------------------------ configurações */
async function telaConfig() {
  document.getElementById("crumb").textContent = "Configurações";
  const e = S.estado || await api("GET", "/api/estado");
  main.innerHTML = `<div class="page-head"><div><span class="eyebrow">CNT Dubla ${esc(e.versao)}</span><h1 style="margin-top:6px">Configurações</h1></div></div>
    <section class="panel stack"><h2 style="margin:0">Neste computador</h2>
      <p>Transcrição do original: ${e.transcricao ? "instalada" : "não instalada"}</p>
      <p>Separador de voz (M&E): ${e.separador ? "instalado" : "não instalado"}</p>
      <p>Chave de IA (sugestões de adaptação e vozes do serviço): ${e.chave_ia ? "configurada" : "não configurada — use a mesma do CNT Legendas (Configurações → Inteligência artificial)"}</p>
      <p>Clonagem de voz local: ${e.clonagem ? "instalada" : "não instalada (motor grande; precisa de placa de vídeo para ficar rápido)"}</p></section>`;
}

/* ------------------------------------------------------------ início */
(async function iniciar() {
  const sel = document.getElementById("theme-sel");
  try { sel.value = localStorage.getItem("cnt.tema") || "dark"; } catch { /* */ }
  sel.onchange = () => { try { localStorage.setItem("cnt.tema", sel.value); } catch { /* */ } location.reload(); };
  try { S.estado = await api("GET", "/api/estado"); } catch { S.estado = null; }
  rotear();
})();
