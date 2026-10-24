/* CNT Legendas — página local. Sem dependências externas. */
"use strict";

const TOKEN = document.querySelector('meta[name="token"]').content;
const main = document.getElementById("main");

const S = {
  state: null,
  projects: [],
  draft: freshDraft(),
  timers: [],
};

function freshDraft() {
  return {
    files: [],              // {path, name, kind, duration, size, uploading, progress, error}
    steps: { transcrever: false, sincronizar: false, traduzir: true },
    project_id: "",
    source_lang: "pt-BR",
    target_lang: "es-419",
    detected: null,          // idioma detectado na legenda escolhida
    method: null,            // "chat" (ChatGPT, sem custo) | "api"
    profile_key: "netflix-es-419",
    out_dir: "",
    context: "",
    estimate: null,          // {minutes, usd} | "loading" | null
  };
}

/* ================================================================ util */

async function api(method, path, body) {
  const opts = { method, headers: { "X-Token": TOKEN } };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new Error("O CNT Legendas não está respondendo. Ele foi fechado? Abra de novo pelo atalho.");
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 402 && data.licenca) {       // recurso pago sem licença: explica e oferece ativar
    showLicenseBlocked(data.error, data.recurso);
    const e = new Error(""); e.licenca = true; throw e;
  }
  if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Legenda como o espectador vê: aplica <i>, <b>, <u> e <font color>, remove outras
   marcações; {\an8} (e outras posições do alto) sobe a legenda. O texto é escapado
   antes, então só as tags conhecidas viram HTML. */
function renderSubHtml(text) {
  let s = esc(String(text).replace(/\r/g, ""));
  const m = /^\s*\{\\an([1-9])\}/.exec(String(text));
  const pos = m ? Number(m[1]) : 2, top = pos >= 7;
  s = s.replace(/\{\\[^}]*\}/g, "");
  s = s.replace(/&lt;(\/?)(i|b|u)&gt;/gi, (m, slash, tag) => `<${slash}${tag.toLowerCase()}>`);
  s = s.replace(/&lt;font\s+color=(?:&quot;|&#39;)?(#[0-9a-f]{3,8}|[a-z]+)(?:&quot;|&#39;)?\s*&gt;/gi, (m, c) => `<span style="color:${c}">`);
  s = s.replace(/&lt;\/font&gt;/gi, "</span>");
  s = s.replace(/&lt;\/?[a-z][^&]*?&gt;/gi, "");
  const tmp = document.createElement("div");
  tmp.innerHTML = s;  // o navegador fecha tags que ficaram abertas
  return { html: tmp.innerHTML, top, pos };
}

let toastTimer;
function toast(msg, isErr = false) {
  if (!msg) return;                                 // (erro de licença já mostrado na janela própria)
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast" + (isErr ? " err" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), isErr ? 7000 : 3500);
}

const nf1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const usd = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

function fmtUSD(v) {
  if (v == null) return "—";
  if (v > 0 && v < 0.01) return "menos de US$ 0,01";
  return usd.format(v).replace(/\u00a0/g, " ");
}
function fmtDur(sec) {
  if (sec == null) return "";
  const m = Math.round(sec / 60);
  if (sec < 60) return `${Math.round(sec)} s`;
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}
function fmtMin(min) {
  if (min == null) return "—";
  return min < 1 ? `${Math.round(min * 60)} s` : `${nf1.format(min)} min`;
}
function fmtTC(sec) {
  const ms = Math.round(sec * 1000);
  const h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, s = Math.floor(ms / 1000) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`;
}
function fmtSize(b) {
  if (!b) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${nf1.format(b)} ${u[i]}`;
}
function fmtDate(s) {
  if (!s) return "";
  const [d, t] = s.split(" ");
  const [y, mo, da] = d.split("-");
  const today = new Date().toISOString().slice(0, 10);
  return (d === today ? "Hoje" : `${da}/${mo}/${y}`) + " " + t.slice(0, 5);
}
const KIND = { media: "Vídeo/áudio", subtitle: "Legenda", text: "Texto", other: "Outro" };
const STATUS = { fila: "Na fila", rodando: "Em andamento", pronto: "Pronto", erro: "Erro", cancelado: "Cancelado", interrompido: "Interrompido" };
const STEP_NAMES = { transcrever: "Transcrever", sincronizar: "Sincronizar", traduzir: "Traduzir", formatar: "Formatar", alinhar: "Tempo das palavras" };

function langName(code) {
  if (!code || code === "auto") return "Detectar automaticamente";
  const l = (S.state?.languages || []).find((x) => x.code === code);
  return l ? l.name : code;
}
function profileName(key) {
  const p = (S.state?.profiles || []).find((x) => x.key === key);
  return p ? p.name : key;
}

function every(ms, fn) {
  const id = setInterval(fn, ms);
  S.timers.push(id);
  return id;
}
function clearTimers() {
  S.timers.forEach(clearInterval);
  S.timers = [];
}

async function loadState() {
  S.state = await api("GET", "/api/state");
  return S.state;
}
async function loadProjects() {
  S.projects = (await api("GET", "/api/projects")).projects;
  return S.projects;
}

/* ============================================================== router */

const routes = [
  [/^#\/inicio$/, renderStart],
  [/^#\/bemvindo$/, renderWelcome],
  [/^#\/projetos$/, renderProjectsList],
  [/^#\/obra\/nova$/, renderNewProject],
  [/^#\/obra\/(\d+)$/, renderObra],
  [/^#\/item\/(\d+)$/, renderItem],
  [/^#\/relatorios$/, renderReports],
  [/^#\/novo$/, renderNew],
  [/^#\/clientes$/, renderProjects],
  [/^#\/cliente\/(novo|\d+)$/, renderProject],
  [/^#\/trabalhos$/, renderJobs],
  [/^#\/trabalho\/(\d+)$/, renderJob],
  [/^#\/configuracoes$/, renderSettings],
  [/^#\/perfis$/, renderProfilesPage],
  [/^#\/perfil\/(novo|[\w\-]+)$/, renderProfile],
  [/^#\/editor(?:\/(\w+))?$/, renderEditor],
];

/* barra de ferramentas (menu da esquerda) */
/* 2.9: quatro itens (o resto continua, aberto por Configurações e pelo Novo trabalho) */
const NAV = [
  [null, [["inicio", "home", "Início"], ["editor", "editor", "Editor"], ["relatorios", "chart", "Relatórios"],
    ["configuracoes", "settings", "Configurações"]]],
];
const CRUMB = { inicio: "Início", bemvindo: "Início", projetos: "Início", obra: "Início", item: "Início", relatorios: "Relatórios",
  novo: "Configurações / Em segundo plano", clientes: "Configurações / Clientes", cliente: "Configurações / Clientes",
  trabalhos: "Configurações / Em segundo plano", trabalho: "Configurações / Em segundo plano",
  configuracoes: "Configurações", perfis: "Configurações / Perfis de regras", perfil: "Configurações / Perfis de regras", editor: "Editor" };
function drawNav() {
  document.getElementById("nav").innerHTML = NAV.map(([sec, items]) =>
    (sec ? `<div class="nav-sec">${esc(sec)}</div>` : "") + items.map(([k, icon, t]) =>
      `<a href="#/${k}" data-nav="${k}" title="${esc(t)}">${ic(icon)}<span>${esc(t)}</span>${k === "configuracoes" ? `<span class="count" id="running-count" hidden title="Trabalhos rodando em segundo plano"></span>` : ""}</a>`).join("")).join("");
  const shell = document.getElementById("shell"), btn = document.getElementById("collapse");
  const apply = (c) => { shell.classList.toggle("collapsed", c); btn.innerHTML = `${ic("chevron")}<span>${c ? "Expandir menu" : "Recolher menu"}</span>`; btn.title = c ? "Expandir menu" : "Recolher menu"; };
  apply(getPref("cnt.menu", "") === "recolhido");
  btn.onclick = () => { const c = !shell.classList.contains("collapsed"); setPref("cnt.menu", c ? "recolhido" : ""); apply(c); };
  const sel = document.getElementById("theme-sel");
  sel.value = getPref("cnt.tema", "dark");
  sel.onchange = () => {
    setPref("cnt.tema", sel.value);
    const t = sel.value === "auto" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : sel.value;
    document.documentElement.setAttribute("data-theme", t);
    if (ED.sid) drawWave();
  };
}
function setCrumb(html) { const el = document.getElementById("crumb"); if (el) el.innerHTML = html; }

async function renderProfilesPage() {
  await loadState();
  main.innerHTML = `
    <div class="page-head"><div><span class="eyebrow">Cadastros</span><h1 style="margin-top:6px">Perfis de regras</h1>
      <p class="muted">Limites técnicos e a lista do que pode e do que não pode em cada cliente. As regras ligadas vão para a IA na tradução.</p></div>
      <div class="row"><button class="btn" id="pf-import">Importar perfis…</button>
        <a class="btn primary" href="#/perfil/novo">${ic("plus")} Novo perfil</a></div></div>
    <section class="panel"><div class="table-wrap"><table class="table report" id="profiles"></table></div>
      <p class="muted small" style="margin-top:10px">Perfis de clientes com manual próprio ficam num arquivo <b>.cnt.json</b> guardado no seu computador: use “Importar perfis…” para trazê-los, e “Exportar” dentro do perfil para fazer uma cópia.</p></section>
    <input type="file" id="pf-file" accept=".json,application/json" hidden>`;
  drawProfiles(S.state.profiles);
  const file = document.getElementById("pf-file");
  document.getElementById("pf-import").onclick = () => file.click();
  file.onchange = async () => {
    const f = file.files[0];
    if (!f) return;
    try {
      let data;
      try { data = JSON.parse(await f.text()); } catch { throw new Error("Este arquivo não é um perfil do CNT Legendas."); }
      const r = await api("POST", "/api/profiles/import", { data });
      S.state.profiles = r.profiles;
      drawProfiles(r.profiles);
      toast(r.keys.length === 1 ? "1 perfil importado." : `${r.keys.length} perfis importados.`);
    } catch (e) { toast(e.message, true); }
    file.value = "";
  };
}

function downloadJson(name, data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

let lastHash = location.hash;
function leavingEditorOk() {
  if (!lastHash.startsWith("#/editor/") || !ED.dirty) return true;
  return confirm("Há alterações não salvas na legenda. Sair mesmo assim? (Elas continuam guardadas enquanto o programa estiver aberto.)");
}

async function router() {
  if (location.hash !== lastHash && !leavingEditorOk()) {
    history.replaceState(null, "", lastHash);
    return;
  }
  lastHash = location.hash;
  clearTimers();
  main.onclick = null; main.onchange = null; main.onsubmit = null; main.oninput = null;
  cancelAnimationFrame(ED.raf);
  document.querySelectorAll("video").forEach((v) => { v.pause(); v.removeAttribute("src"); v.load(); });
  const hash = location.hash || "#/inicio";
  if (!hash.startsWith("#/editor/")) { document.body.classList.remove("editor-mode"); ED.sid = null; ED.dirty = false; }
  ["ed-find", "ed-drawer", "ed-syncmenu-float"].forEach((id) => document.getElementById(id)?.remove());
  const section = hash.split("/")[1] || "inicio";
  const navKey = { trabalho: "configuracoes", trabalhos: "configuracoes", cliente: "configuracoes", clientes: "configuracoes",
    novo: "configuracoes", perfil: "configuracoes", perfis: "configuracoes", obra: "inicio", item: "inicio", projetos: "inicio",
    bemvindo: "inicio" }[section] || section;
  setCrumb(esc(CRUMB[section] || ""));
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === navKey) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  for (const [rx, fn] of routes) {
    const m = hash.match(rx);
    if (m) {
      try {
        await fn(...m.slice(1));
      } catch (e) {
        main.innerHTML = `<div class="panel"><p class="note err">${esc(e.message)}</p></div>`;
      }
      main.focus({ preventScroll: true });
      return;
    }
  }
  location.hash = "#/inicio";
}

async function refreshRunningCount() {
  try {
    const { jobs } = await api("GET", "/api/jobs");
    const n = jobs.filter((j) => j.status === "rodando" || j.status === "fila").length;
    const el = document.getElementById("running-count");
    el.textContent = n;
    el.hidden = n === 0;
    return jobs;
  } catch { return null; }
}

/* ========================================================= novo trabalho */

async function renderNew() {
  await Promise.all([loadState(), loadProjects()]);
  const d = S.draft;
  const st = S.state;
  const noKey = !st.api_key && !st.local_transcribe;

  main.innerHTML = `
    <div class="page-head">
      <div>
        <h1>Trabalho em segundo plano</h1>
        <p class="muted">Para transcrever um vídeo, sincronizar ou traduzir sem abrir o editor. O .srt sai ao lado do original. Para o dia a dia, use o <a href="#/inicio">Início</a>.</p>
      </div>
    </div>
    ${noKey ? `<p class="note warn" style="margin-bottom:16px">Sem chave da OpenAI: dá para traduzir pelo seu ChatGPT e sincronizar legendas. Para transcrever ou usar a API, <a href="#/configuracoes">configure a chave</a>.</p>` : ""}
    <div class="split">
      <div>
        <section class="panel">
          <h2>Arquivos</h2>
          <div class="drop" id="drop">
            <p><strong>Arraste a legenda, o vídeo ou o roteiro para cá</strong></p>
            <p class="muted small">Traduzir: basta a legenda (.srt). Transcrever: o vídeo. Sincronizar: o vídeo + a legenda fora do tempo, ou + o texto sem tempo (.txt/.docx).</p>
            <div class="row">
              <button class="btn primary" data-action="pick-sub">Escolher legenda (.srt)</button>
              <button class="btn" data-action="pick-media">Escolher vídeo ou áudio</button>
              <button class="btn" data-action="pick-text">Escolher texto sem tempo</button>
            </div>
          </div>
          <ul class="files" id="files"></ul>
          <details style="margin-top:10px">
            <summary class="muted small">Colar o caminho do arquivo</summary>
            <div class="path-input">
              <input type="text" id="path-in" placeholder="C:\\Videos\\Episódio 01.mp4" aria-label="Caminho do arquivo">
              <button class="btn" data-action="add-path">Adicionar</button>
            </div>
          </details>
        </section>

        <section class="panel">
          <h2>O que fazer</h2>
          <div class="steps">
            ${stepTile("traduzir", "Traduzir", "Traduz a legenda inteira mantendo os tempos, nas regras do cliente.")}
            ${stepTile("transcrever", "Transcrever", "Gera a legenda a partir do áudio do vídeo.")}
            ${stepTile("sincronizar", "Sincronizar", "Encaixa uma legenda fora do tempo, ou um texto sem tempo, na fala do vídeo.")}
          </div>
          <p class="muted small" style="margin-top:10px">A formatação (linhas, velocidade de leitura e duração) é feita sempre, no final.</p>
          <div class="methods" id="f-method" style="margin-top:14px" ${d.steps.traduzir ? "" : "hidden"} role="radiogroup" aria-label="Como traduzir">
            <label class="method"><input type="radio" name="f-m" value="chat" ${curMethod() === "chat" ? "checked" : ""}>
              <strong>Traduzir pelo meu ChatGPT</strong><span class="muted small">Sem custo. Você cola as partes no ChatGPT e a resposta aqui.</span></label>
            <label class="method"><input type="radio" name="f-m" value="api" ${curMethod() === "api" ? "checked" : ""}>
              <strong>Traduzir pela API</strong><span class="muted small">Automática, com custo na OpenAI.</span></label>
          </div>
        </section>

        <section class="panel">
          <h2>Detalhes</h2>
          <div class="grid-2">
            <label class="field"><span>Cliente</span>
              <select id="f-project">
                <option value="">Sem cliente</option>
                ${S.projects.map((p) => `<option value="${p.id}" ${String(p.id) === String(d.project_id) ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
              </select>
              ${S.projects.length ? "" : `<a href="#/cliente/novo" class="small">Cadastrar cliente</a>`}
            </label>
            <label class="field"><span>Perfil de regras</span>
              <select id="f-profile">${st.profiles.map((p) => `<option value="${esc(p.key)}" ${p.key === d.profile_key ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>
            </label>
            <div class="langs" style="grid-column:1/-1">
              <label class="field"><span>Idioma de origem <em class="muted small" id="f-detected">${d.detected ? "· detectado na legenda" : ""}</em></span>
                <select id="f-src">${langOptions(d.source_lang, true)}</select>
              </label>
              <button class="btn icon swap" data-action="swap" title="Inverter idiomas" aria-label="Inverter idiomas" ${d.steps.traduzir ? "" : "disabled"}>⇄</button>
              <label class="field"><span>Traduzir para</span>
                <select id="f-dst" ${d.steps.traduzir ? "" : "disabled"}>${langOptions(d.target_lang)}</select>
              </label>
            </div>
            <label class="field" style="grid-column:1/-1"><span>Pasta de saída</span>
              <div class="row" style="flex-wrap:nowrap">
                <input type="text" id="f-out" value="${esc(d.out_dir)}" placeholder="Mesma pasta do arquivo original">
                <button class="btn" data-action="pick-out">Escolher</button>
              </div>
            </label>
            <label class="field" style="grid-column:1/-1"><span>Contexto deste episódio (opcional)</span>
              <textarea id="f-ctx" placeholder="Assunto do episódio, quem fala com quem, nomes de pessoas e lugares… Ajuda a tradução e a transcrição.">${esc(d.context)}</textarea>
            </label>
          </div>
        </section>
      </div>

      <aside class="sticky">
        <section class="panel summary" id="summary"></section>
      </aside>
    </div>`;

  renderFiles();
  syncNewForm();
  renderSummary();
  bindNew();
}

function stepTile(key, title, desc) {
  const enabled = S.state.phase[key];
  const checked = S.draft.steps[key] && enabled;
  const soon = "";
  return `<label class="step ${enabled ? "" : "off"}">
      <input type="checkbox" data-step="${key}" ${checked ? "checked" : ""} ${enabled ? "" : "disabled"}>
      <strong>${title}</strong>
      <span class="muted">${enabled ? desc : soon}</span>
    </label>`;
}

function langOptions(sel, auto = false) {
  return (auto ? `<option value="auto" ${sel === "auto" ? "selected" : ""}>Detectar automaticamente</option>` : "") + S.state.languages.map((l) => `<option value="${l.code}" ${l.code === sel ? "selected" : ""}>${esc(l.name)}</option>`).join("");
}

function renderFiles() {
  const ul = document.getElementById("files");
  if (!ul) return;
  ul.innerHTML = S.draft.files.map((f, i) => `
    <li>
      <span class="tag">${KIND[f.kind] || "Arquivo"}</span>
      <div style="min-width:0">
        <div class="name" title="${esc(f.path || f.name)}">${esc(f.name)}</div>
        ${f.uploading ? `<div class="bar" style="margin-top:6px"><i style="width:${f.progress || 0}%"></i></div>` : ""}
        ${f.error ? `<div class="small" style="color:var(--err)">${esc(f.error)}</div>` : ""}
        ${f.kind === "media" && f.has_audio === false ? `<div class="small" style="color:var(--err)">Este arquivo não tem áudio.</div>` : ""}
      </div>
      <span class="meta muted small tnum">${f.duration ? fmtDur(f.duration) : f.cues ? `${f.cues} legendas` : fmtSize(f.size)}</span>
      <button class="btn link" data-action="remove-file" data-i="${i}" aria-label="Remover ${esc(f.name)}">Remover</button>
    </li>`).join("");
}

function currentSteps() {
  return Object.entries(S.draft.steps).filter(([k, v]) => v && S.state.phase[k]).map(([k]) => k);
}

function validateDraft() {
  const d = S.draft;
  const ready = d.files.filter((f) => !f.uploading && !f.error);
  const has = (k) => ready.some((f) => f.kind === k);
  const steps = currentSteps();
  if (d.files.some((f) => f.uploading)) return "Aguarde o envio do arquivo terminar.";
  if (!ready.length) return steps.includes("traduzir") && !steps.includes("transcrever")
    ? "Escolha a legenda (.srt) que vai ser traduzida." : "Escolha o vídeo ou a legenda.";
  if (!steps.length) return "Marque pelo menos uma etapa.";
  if (steps.includes("traduzir") && !steps.includes("transcrever") && !has("subtitle"))
    return "Para traduzir, escolha a legenda (.srt). Ou marque Transcrever para começar pelo vídeo.";
  if (ready.filter((f) => f.kind === "subtitle").length > 1) return "Uma legenda por trabalho. Remova as outras.";
  if ((steps.includes("transcrever") || steps.includes("sincronizar")) && !has("media")) return "Para transcrever ou sincronizar é preciso o vídeo ou o áudio.";
  if (ready.some((f) => f.kind === "media" && f.has_audio === false)) return "O vídeo escolhido não tem áudio.";
  if (steps.includes("transcrever") && !steps.includes("sincronizar") && (has("subtitle") || has("text")))
    return "Você adicionou uma legenda ou texto. Para transcrever do zero, remova esse arquivo.";
  if (ready.filter((f) => f.kind === "media").length > 1) return "Um vídeo por trabalho. Remova os outros.";
  if (steps.includes("sincronizar") && has("subtitle") && has("text")) return "Para sincronizar use a legenda OU o texto, não os dois.";
  if (steps.includes("sincronizar") && !has("subtitle") && !has("text") && !steps.includes("transcrever"))
    return "Para sincronizar, junte ao vídeo a legenda fora do tempo (.srt) ou o texto sem tempo (.txt/.docx).";
  const needsOpenAI = !S.state.local_transcribe && (steps.includes("transcrever") || (steps.includes("sincronizar") && has("text")));
  if (needsOpenAI && !S.state.api_key) return "Configure a chave da OpenAI primeiro (Configurações).";
  const prov = (S.state.ai?.providers || []).find((x) => x.id === S.state.ai?.provider);
  if (steps.includes("traduzir") && curMethod() === "api" && prov && !prov.ready)
    return `Configure o ${prov.name} em Configurações → Inteligência artificial.`;
  return "";
}

function renderSummary() {
  const box = document.getElementById("summary");
  if (!box) return;
  const d = S.draft;
  const steps = currentSteps();
  const problem = validateDraft();
  const media = d.files.find((f) => f.kind === "media");
  const sub = d.files.find((f) => f.kind === "subtitle");
  const est = d.estimate;
  box.innerHTML = `
    <h2>Resumo</h2>
    <div class="stack">
      <div class="flow">${[...steps.map((s) => STEP_NAMES[s]), "Formatar"].map(esc).join(" <i>›</i> ")}</div>
      <dl>
        ${sub ? `<dt>Legenda</dt><dd class="tnum">${sub.cues ?? "—"} legendas</dd>` : ""}
        ${media ? `<dt>Vídeo</dt><dd class="tnum">${fmtDur(media.duration) || "—"}</dd>` : ""}
        <dt>Idioma</dt><dd>${steps.includes("traduzir") ? `${esc(shortLang(d.source_lang))} › ${esc(shortLang(d.target_lang))}` : esc(langName(d.source_lang))}</dd>
        <dt>Perfil</dt><dd>${esc(profileName(d.profile_key))}</dd>
        <dt>Saída</dt><dd>${d.out_dir ? "Pasta escolhida" : "Junto do original"}</dd>
      </dl>
      <div>
        <p class="muted small">Custo estimado na OpenAI</p>
        ${est === "loading" ? `<div class="bar indet" style="margin:10px 0"><i></i></div><p class="muted small">Calculando…</p>`
          : steps.includes("traduzir") && curMethod() === "chat" && !steps.includes("transcrever") ? `<p class="cost">US$ 0,00</p><p class="muted small">Tradução pelo seu ChatGPT</p>`
          : est ? `<p class="cost">${fmtUSD(curMethod() === "chat" && steps.includes("traduzir") ? Math.max(0, est.usd - (est.translate_usd || 0)) : est.usd)}</p><p class="muted small">${[est.minutes ? `${fmtMin(est.minutes)} de fala` : "", est.cues && steps.includes("traduzir") ? `${est.cues} legendas para traduzir` : ""].filter(Boolean).join(" · ")}</p>`
          : `<button class="btn" data-action="estimate" ${problem ? "disabled" : ""}>Calcular custo</button>`}
      </div>
      ${problem ? `<p class="note warn small">${esc(problem)}</p>` : ""}
      <button class="btn primary big" data-action="start" ${problem ? "disabled" : ""}>${esc(startLabel(steps))}</button>
    </div>`;
}

function curMethod() {
  return S.draft.method || getPref("legendas.metodo", S.state?.settings?.translate_method || "chat");
}
let PENDING_TRANSLATE = null;  // o editor abre a janela de tradução assim que carregar

function shortLang(code) {
  if (!code || code === "auto") return "idioma detectado";
  return { "pt-BR": "Português", "es-419": "Espanhol (LatAm)", "es-ES": "Espanhol (Espanha)" }[code] || langName(code);
}
function startLabel(steps) {
  const t = steps.includes("transcrever"), tr = steps.includes("traduzir");
  if (t && tr) return "Transcrever e traduzir";
  if (tr && curMethod() === "chat") return t ? "Transcrever (depois traduzir pelo ChatGPT)" : `Traduzir para ${shortLang(S.draft.target_lang)} pelo ChatGPT`;
  if (tr) return `Traduzir para ${shortLang(S.draft.target_lang)}`;
  if (t) return "Transcrever";
  return "Começar";
}
function oppositeLang(code) { return code && code.startsWith("es") ? "pt-BR" : "es-419"; }
/* Perfil acompanha o idioma da legenda final (mantém o infantil, se escolhido). */
function autoProfile() {
  const d = S.draft;
  const m = /^(.+?)-(pt-br|es-419)(-kids)?$/.exec(d.profile_key);
  if (!m) return;
  const lang = d.steps.traduzir ? d.target_lang : d.source_lang;
  if (!lang || lang === "auto") return;
  const code = lang.startsWith("pt") ? "pt-br" : lang === "es-419" ? "es-419" : null;
  if (!code) return;
  const key = `${m[1]}-${code}${m[3] || ""}`;
  if (!S.state?.profiles || S.state.profiles.some((p) => p.key === key)) d.profile_key = key;
}
function syncNewForm() {
  const d = S.draft;
  autoProfile();
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  set("f-src", d.source_lang); set("f-dst", d.target_lang); set("f-profile", d.profile_key);
  document.querySelectorAll("[data-step]").forEach((cb) => { cb.checked = !!d.steps[cb.dataset.step] && !cb.disabled; });
  const dst = document.getElementById("f-dst"); if (dst) dst.disabled = !d.steps.traduzir;
  const sw = document.querySelector('[data-action="swap"]'); if (sw) sw.disabled = !d.steps.traduzir;
  const fm = document.getElementById("f-method"); if (fm) fm.hidden = !d.steps.traduzir;
  const det = document.getElementById("f-detected"); if (det) det.textContent = d.detected ? "· detectado na legenda" : "";
}

function draftPayload() {
  const d = S.draft;
  return {
    inputs: d.files.filter((f) => !f.uploading && !f.error).map((f) => f.path),
    params: {
      steps: currentSteps(), project_id: d.project_id ? Number(d.project_id) : null,
      source_lang: d.source_lang, target_lang: d.target_lang, profile_key: d.profile_key,
      out_dir: d.out_dir.trim(), context: d.context.trim(),
    },
  };
}

function invalidateEstimate() {
  if (S.draft.estimate !== "loading") S.draft.estimate = null;
}

async function addPaths(paths) {
  if (!paths.length) return;
  const { files } = await api("POST", "/api/inspect", { paths });
  for (const f of files) {
    if (!f.exists) { toast(`Arquivo não encontrado: ${f.path}`, true); continue; }
    if (f.kind === "other") { toast(`Tipo de arquivo não suportado: ${f.name}`, true); continue; }
    if (f.kind === "media") S.draft.files = S.draft.files.filter((x) => x.kind !== "media");
    if (f.kind === "subtitle") S.draft.files = S.draft.files.filter((x) => x.kind !== "subtitle");
    S.draft.files.push(f);
    const d = S.draft;
    if (f.kind === "subtitle") {
      // recebeu uma legenda: o trabalho é traduzir
      d.steps.traduzir = true; d.steps.transcrever = false;
      if (f.language) {
        d.detected = f.language; d.source_lang = f.language; d.target_lang = oppositeLang(f.language);
        toast(`Legenda em ${shortLang(f.language)}: vai ser traduzida para ${shortLang(d.target_lang)}. Dá para trocar em Detalhes.`);
      }
    } else if (f.kind === "text") {
      S.draft.files = S.draft.files.filter((x) => x === f || x.kind !== "subtitle");
      d.steps.sincronizar = true; d.steps.transcrever = false; d.steps.traduzir = false;
      toast("Texto sem tempo: vai ser encaixado na fala do vídeo (usa a transcrição pela API).");
    } else if (f.kind === "media" && !d.files.some((x) => x.kind === "subtitle" || x.kind === "text")) {
      d.steps.transcrever = true;
      if (!d.detected) d.source_lang = "auto";   // o idioma sai da fala do vídeo
    }
  }
  syncNewForm();
  invalidateEstimate();
  renderFiles();
  renderSummary();
}

function uploadFile(file) {
  const entry = { name: file.name, kind: guessKind(file.name), size: file.size, uploading: true, progress: 0 };
  S.draft.files.push(entry);
  renderFiles(); renderSummary();
  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/api/upload?name=${encodeURIComponent(file.name)}`);
  xhr.setRequestHeader("X-Token", TOKEN);
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) { entry.progress = Math.round((e.loaded / e.total) * 100); renderFiles(); }
  };
  xhr.onload = async () => {
    S.draft.files = S.draft.files.filter((x) => x !== entry);
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status !== 200) { toast(data.error || "Falha ao enviar o arquivo.", true); renderFiles(); renderSummary(); return; }
    try { await addPaths([data.path]); } catch (e) { toast(e.message, true); }
  };
  xhr.onerror = () => { entry.uploading = false; entry.error = "Falha ao enviar o arquivo."; renderFiles(); renderSummary(); };
  xhr.send(file);
}

function guessKind(name) {
  const ext = name.toLowerCase().split(".").pop();
  if (ext === "srt") return "subtitle";
  if (ext === "txt" || ext === "docx") return "text";
  return "media";
}

async function pickFiles(kind, multiple) {
  try {
    const { paths } = await api("POST", "/api/dialog", { kind, multiple });
    return paths;
  } catch (e) {
    toast(e.message, true);
    document.querySelector("details")?.setAttribute("open", "");
    return [];
  }
}

function bindNew() {
  const d = S.draft;
  const drop = document.getElementById("drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { [...(e.dataTransfer?.files || [])].forEach(uploadFile); });

  main.onclick = async (e) => {
    const b = e.target.closest("[data-action]");
    if (!b) return;
    const a = b.dataset.action;
    if (a === "pick-media") await addPaths(await pickFiles("media", false));
    if (a === "pick-sub") await addPaths(await pickFiles("subtitle", false));
    if (a === "pick-text") await addPaths(await pickFiles("text", false));
    if (a === "swap") {
      [d.source_lang, d.target_lang] = [d.target_lang, d.source_lang];
      d.detected = null; syncNewForm(); invalidateEstimate(); renderSummary();
    }
    if (a === "pick-other") await addPaths(await pickFiles("any", true));
    if (a === "add-path") {
      const inp = document.getElementById("path-in");
      const v = inp.value.trim().replace(/^"|"$/g, "");
      if (v) { try { await addPaths([v]); inp.value = ""; } catch (err) { toast(err.message, true); } }
    }
    if (a === "remove-file") {
      const [gone] = d.files.splice(Number(b.dataset.i), 1);
      if (gone?.kind === "subtitle") d.detected = null;
      syncNewForm(); invalidateEstimate(); renderFiles(); renderSummary();
    }
    if (a === "pick-out") {
      const [p] = await pickFiles("folder", false);
      if (p) { d.out_dir = p; document.getElementById("f-out").value = p; renderSummary(); }
    }
    if (a === "estimate") {
      d.estimate = "loading"; renderSummary();
      try { d.estimate = await api("POST", "/api/estimate", draftPayload()); }
      catch (err) { d.estimate = null; toast(err.message, true); }
      renderSummary();
    }
    if (a === "start") {
      b.disabled = true;
      const steps = currentSteps();
      const viaChat = steps.includes("traduzir") && curMethod() === "chat";
      try {
        if (viaChat && !steps.includes("transcrever")) {
          // tradução pelo ChatGPT: abre a legenda no editor com a janela de tradução
          const sub = d.files.find((f) => f.kind === "subtitle"), media = d.files.find((f) => f.kind === "media");
          const r = await api("POST", "/api/editor/open", { srt: sub.path, video: media?.path || "", profile_key: "" });
          PENDING_TRANSLATE = { method: "chat", source: d.source_lang, target: d.target_lang, project_id: d.project_id };
          location.hash = `#/editor/${r.sid}`;
          return;
        }
        const payload = draftPayload();
        if (viaChat) {  // transcreve pela API; a tradução vem depois, pelo ChatGPT, no editor
          payload.params.steps = steps.filter((x) => x !== "traduzir");
          payload.params.chat_target = d.target_lang;
        }
        const job = await api("POST", "/api/jobs", payload);
        S.draft = { ...freshDraft(), project_id: d.project_id, profile_key: d.profile_key, source_lang: d.source_lang, target_lang: d.target_lang, steps: { ...d.steps }, out_dir: d.out_dir };
        location.hash = `#/trabalho/${job.id}`;
      } catch (err) { toast(err.message, true); b.disabled = false; }
    }
  };

  main.querySelectorAll('input[name="f-m"]').forEach((r) => r.addEventListener("change", () => {
    d.method = r.value; setPref("legendas.metodo", r.value); renderSummary();
  }));
  main.querySelectorAll("[data-step]").forEach((cb) => cb.addEventListener("change", () => {
    d.steps[cb.dataset.step] = cb.checked;
    syncNewForm(); invalidateEstimate(); renderSummary();
  }));
  document.getElementById("f-project").addEventListener("change", (e) => {
    d.project_id = e.target.value;
    const p = S.projects.find((x) => String(x.id) === d.project_id);
    if (p) {
      if (!d.detected) { d.source_lang = p.source_lang; d.target_lang = p.target_lang; }
      d.profile_key = p.profile_key;
      syncNewForm();
    }
    invalidateEstimate(); renderSummary();
  });
  const bindVal = (id, key) => document.getElementById(id).addEventListener("change", (e) => { d[key] = e.target.value; invalidateEstimate(); renderSummary(); });
  bindVal("f-profile", "profile_key");
  ["f-src", "f-dst"].forEach((id) => document.getElementById(id).addEventListener("change", (e) => {
    d[id === "f-src" ? "source_lang" : "target_lang"] = e.target.value;
    if (id === "f-src") d.detected = null;
    syncNewForm(); invalidateEstimate(); renderSummary();
  }));
  bindVal("f-out", "out_dir");
  document.getElementById("f-ctx").addEventListener("input", (e) => { d.context = e.target.value; });
  document.getElementById("path-in").addEventListener("keydown", (e) => { if (e.key === "Enter") main.querySelector('[data-action="add-path"]').click(); });
}

/* ============================================================ trabalhos */

async function renderJobs() {
  const draw = async () => {
    const jobs = await refreshRunningCount();
    if (!jobs) return;
    if (!jobs.length) {
      main.innerHTML = `<div class="page-head"><h1>Trabalhos</h1></div>
        <div class="panel empty"><p>Nenhum trabalho ainda.</p><a class="btn primary" href="#/novo">Começar um trabalho</a></div>`;
      return;
    }
    const active = jobs.filter((j) => j.status === "rodando" || j.status === "fila");
    const rows = jobs.map((j) => {
      const prog = j.live ? progressOf(j.live.steps) : null;
      return `<tr class="click" data-href="#/trabalho/${j.id}">
        <td><strong>${esc(j.name)}</strong><div class="muted small">${esc(j.project_name || "Sem cliente")} · ${j.steps.filter((s) => s !== "formatar").map((s) => STEP_NAMES[s]).join(", ")}</div></td>
        <td><span class="pill ${j.status}">${STATUS[j.status]}</span>
          ${j.status === "rodando" && j.live ? `<div class="muted small" style="margin-top:4px">${esc(j.live.message)}</div>${prog != null ? `<div class="bar" style="margin-top:6px;max-width:220px"><i style="width:${prog}%"></i></div>` : ""}` : ""}
          ${j.status === "pronto" && j.issues ? `<div class="muted small" style="margin-top:4px">${j.issues} apontamentos</div>` : ""}
        </td>
        <td class="muted small tnum">${fmtDate(j.created_at)}</td>
        <td class="num">${j.usd != null ? fmtUSD(j.usd) : "—"}</td>
      </tr>`;
    }).join("");
    main.innerHTML = `
      <div class="page-head">
        <div><h1>Trabalhos</h1><p class="muted">${active.length ? `${active.length} em andamento ou na fila. Um trabalho roda por vez.` : "Todos os trabalhos, do mais recente ao mais antigo."}</p></div>
        <a class="btn primary" href="#/novo">Novo trabalho</a>
      </div>
      <div class="panel" style="padding:6px 10px">
        <table class="table">
          <thead><tr><th>Vídeo</th><th>Situação</th><th>Quando</th><th class="num">Custo</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
    main.querySelectorAll("tr[data-href]").forEach((tr) => tr.addEventListener("click", () => (location.hash = tr.dataset.href)));
    return active.length;
  };
  const n = await draw();
  every(2000, async () => { if (document.hidden) return; await draw(); });
  return n;
}

function progressOf(steps) {
  const t = steps?.transcrever, a = steps?.alinhar, tr = steps?.traduzir;
  if (tr && tr[1]) return Math.round((tr[0] / tr[1]) * 100);
  if (a && a[1]) return 60 + Math.round((a[0] / a[1]) * 38);
  if (t && t[1]) return Math.round((t[0] / t[1]) * 60);
  return null;
}

/* ===================================================== um trabalho */

async function renderJob(id) {
  await loadState();
  let job = await api("GET", `/api/jobs/${id}`);
  const active = () => job.status === "rodando" || job.status === "fila";

  if (!active() && job.status === "pronto") return renderResult(job);
  drawProgress(job);
  if (active()) {
    const tid = every(1000, async () => {
      if (document.hidden) return;
      try { job = await api("GET", `/api/jobs/${id}`); } catch { return; }
      refreshRunningCount();
      if (job.status === "pronto") { clearInterval(tid); renderResult(job); return; }
      drawProgress(job);
      if (!active()) clearInterval(tid);
    });
  }
}

function jobLangs(job) {
  const src = job.params.source_lang_detected || (job.params.source_lang === "auto" ? "" : job.params.source_lang);
  if (job.steps.includes("traduzir")) return `${src ? shortLang(src) : "Detectar idioma"} › ${shortLang(job.params.target_lang)}`;
  return langName(src || "pt-BR");
}

function jobHead(job, actions = "") {
  return `<div class="page-head">
      <div>
        <p class="muted small"><a href="#/trabalhos">Trabalhos</a> / ${esc(job.project_name || "Sem cliente")}</p>
        <h1 style="margin-top:6px">${esc(job.name)}</h1>
        <p class="muted"><span class="pill ${job.status}">${STATUS[job.status]}</span>
          &nbsp;${job.steps.map((s) => STEP_NAMES[s]).join(" › ")} · ${esc(jobLangs(job))} · ${esc(profileName(job.params.profile_key))}</p>
      </div>
      <div class="row">${actions}</div>
    </div>`;
}

function drawProgress(job) {
  const live = job.live || { message: "", steps: {}, log: [] };
  const step = (key, label, unit) => {
    const v = live.steps[key];
    if (!v) return `<div><div class="row" style="justify-content:space-between"><span>${label}</span><span class="muted small">aguardando</span></div><div class="bar"><i></i></div></div>`;
    const pct = v[1] ? Math.round((v[0] / v[1]) * 100) : 0;
    return `<div><div class="row" style="justify-content:space-between"><span>${label}</span><span class="muted small tnum">${v[0]} de ${v[1]} ${unit}</span></div><div class="bar"><i style="width:${pct}%"></i></div></div>`;
  };
  let body;
  if (job.status === "rodando" || job.status === "fila") {
    body = `<section class="panel stack">
        <p><strong>${esc(live.message || "Preparando…")}</strong></p>
        ${job.status === "rodando" && !live.steps.transcrever && !live.steps.traduzir ? `<div class="bar indet"><i></i></div>` : ""}
        ${job.steps.includes("transcrever") ? step("transcrever", "Transcrição na OpenAI", "trechos") : ""}
        ${job.steps.includes("transcrever") ? step("alinhar", "Tempo de cada palavra", "trechos") : ""}
        ${job.steps.includes("traduzir") ? step("traduzir", "Tradução na OpenAI", "legendas") : ""}
        <p class="muted small">Pode fechar esta página: o trabalho continua enquanto o programa estiver aberto.</p>
      </section>`;
  } else {
    const msg = job.status === "erro" ? (job.error || "O trabalho falhou.")
      : job.status === "interrompido" ? "O programa foi fechado durante este trabalho."
      : "Trabalho cancelado.";
    body = `<section class="panel stack">
        <p class="note ${job.status === "erro" ? "err" : "warn"}">${esc(msg)}</p>
        <p class="muted">Ao tentar de novo, o que já foi feito é aproveitado e não é cobrado outra vez.</p>
        <div class="row"><button class="btn primary" data-action="retry">Tentar de novo</button>
        <button class="btn" data-action="delete">Tirar do histórico</button></div>
      </section>`;
  }
  const logHtml = (live.log || []).slice().reverse().map(([t, m]) => `<li><time>${esc(t)}</time><span>${esc(m)}</span></li>`).join("");
  main.innerHTML = jobHead(job, job.status === "rodando" || job.status === "fila" ? `<button class="btn danger" data-action="cancel">Cancelar</button>` : "")
    + body
    + (logHtml ? `<section class="panel"><h2>Registro</h2><ul class="log">${logHtml}</ul></section>` : "");
  main.onclick = (e) => jobActions(e, job);
}

async function jobActions(e, job) {
  const b = e.target.closest("[data-action]");
  if (!b) return;
  const a = b.dataset.action;
  try {
    if (a === "cancel") { await api("POST", `/api/jobs/${job.id}/cancel`); toast("Cancelando…"); }
    if (a === "retry") { await api("POST", `/api/jobs/${job.id}/retry`); router(); }
    if (a === "delete") {
      if (!confirm("Tirar este trabalho do histórico? Os arquivos .srt gerados não são apagados.")) return;
      await api("DELETE", `/api/jobs/${job.id}`); location.hash = "#/trabalhos";
    }
    if (a === "open") await api("POST", "/api/open", { path: b.dataset.path });
    if (a === "editor-chat") {
      const r = await api("POST", "/api/editor/open", { job_id: job.id });
      PENDING_TRANSLATE = { method: "chat", target: job.params.chat_target, project_id: job.project_id || "" };
      location.hash = `#/editor/${r.sid}`;
    }
    if (a === "editor") {
      const r = await api("POST", "/api/editor/open", { job_id: job.id });
      location.hash = `#/editor/${r.sid}`;
    }
    if (a === "show") await api("POST", "/api/open", { path: b.dataset.path, select: true });
    if (a === "again") {
      S.draft = freshDraft();
      Object.assign(S.draft, { project_id: job.project_id || "", source_lang: job.params.source_lang, target_lang: job.params.target_lang, profile_key: job.params.profile_key, out_dir: job.params.out_dir || "" });
      location.hash = "#/novo";
    }
  } catch (err) { toast(err.message, true); }
}

/* ---- resultado: a tela de revisão ---- */

const ISSUE_SHORT = { cps: "CPS", caracteres: "caracteres", linhas: "linhas", curta: "curta", longa: "longa", intervalo: "intervalo", tempo_estimado: "tempo estimado", sobreposicao: "sobreposição", vazia: "vazia", tempo_invertido: "tempo", fora_de_ordem: "ordem" };

async function renderResult(job) {
  refreshRunningCount();
  const res = await api("GET", `/api/jobs/${job.id}/result`);
  const byCue = {};
  for (const i of res.issues) (byCue[i.index] ||= []).push(i);
  const errCount = res.issues.filter((i) => i.severity === "erro").length;
  const flagged = Object.keys(byCue).length;
  let onlyFlagged = false;
  let sel = res.cues.length ? (Number(Object.keys(byCue)[0]) || 1) : 0;

  const srt = res.srt;
  const qc = job.outputs.qc;
  main.innerHTML = jobHead(job, `
      ${job.params.chat_target ? `<button class="btn primary" data-action="editor-chat" ${res.exists ? "" : "disabled"}>Traduzir pelo ChatGPT</button>` : ""}
      <button class="btn ${job.params.chat_target ? "" : "primary"}" data-action="editor" ${res.exists ? "" : "disabled"}>Abrir no editor</button>
      <button class="btn" data-action="open" data-path="${esc(srt)}" ${res.exists ? "" : "disabled"}>Abrir em outro programa</button>
      <button class="btn" data-action="show" data-path="${esc(srt)}" ${res.exists ? "" : "disabled"}>Mostrar na pasta</button>`)
    + `
    ${!res.exists ? `<p class="note err" style="margin-bottom:16px">O arquivo da legenda não está mais em ${esc(srt)}.</p>` : ""}
    ${job.estimated_timing ? `<p class="note warn" style="margin-bottom:16px">Parte dos tempos foi estimada, porque o alinhamento preciso não estava disponível. Confira a sincronia dos trechos marcados. <a href="#/configuracoes">Ver alinhamento</a></p>` : ""}
    <section class="panel" style="margin-bottom:16px">
      <div class="stats">
        <div><strong>${res.cues.length}</strong><span>legendas</span></div>
        <div><strong>${flagged}</strong><span>para revisar${errCount ? ` (${errCount} erros)` : ""}</span></div>
        ${job.minutes ? `<div><strong>${fmtMin(job.minutes)}</strong><span>de fala</span></div>` : ""}
        <div><strong>${fmtUSD(job.usd)}</strong><span>na OpenAI</span></div>
      </div>
      <p class="muted small" style="margin-top:12px">Salvo em <span class="tnum">${esc(srt)}</span>${qc ? ` · <button class="btn link small" data-action="open" data-path="${esc(qc)}">relatório de QC</button>` : ""} · <button class="btn link small" data-action="again">novo trabalho com as mesmas opções</button></p>
    </section>
    <div class="review">
      <div>
        <div class="screen" id="screen" aria-live="polite"></div>
        <div class="screen-meta" id="screen-meta"></div>
      </div>
      <div>
        <div class="row" style="justify-content:space-between;margin-bottom:8px">
          <h2>Legendas</h2>
          <label class="small row" style="gap:6px"><input type="checkbox" id="only-flagged" ${flagged ? "" : "disabled"}> Só as que precisam de revisão</label>
        </div>
        <ul class="cues" id="cues" role="listbox" tabindex="0" aria-label="Legendas"></ul>
        ${res.cues.length >= 400 ? `<p class="muted small" style="margin-top:6px">Mostrando as 400 primeiras. O arquivo completo abre no seu editor.</p>` : ""}
      </div>
    </div>`;

  const list = document.getElementById("cues");
  const drawList = () => {
    const cues = onlyFlagged ? res.cues.filter((c) => byCue[c.n]) : res.cues;
    list.innerHTML = cues.map((c) => {
      const iss = byCue[c.n] || [];
      const hasErr = iss.some((i) => i.severity === "erro");
      return `<li role="option" data-n="${c.n}" aria-selected="${c.n === sel}" class="${iss.length ? "flagged" : ""} ${hasErr ? "has-err" : ""}">
        <span class="n">${c.n}</span>
        <div>
          <div class="t">${fmtTC(c.start)} → ${fmtTC(c.end)}</div>
          <div class="lines">${c.lines.map((l) => `<div>${esc(l)}</div>`).join("")}</div>
          ${iss.length ? `<div class="cue-issues">${iss.map((i) => esc(i.message)).join(" ")}</div>` : ""}
        </div>
      </li>`;
    }).join("") || `<li class="muted">Nenhuma legenda.</li>`;
  };
  const drawScreen = () => {
    const c = res.cues.find((x) => x.n === sel);
    const scr = document.getElementById("screen");
    const meta = document.getElementById("screen-meta");
    if (!c) { scr.innerHTML = ""; meta.textContent = ""; return; }
    const iss = byCue[c.n] || [];
    const dur = c.end - c.start;
    const chars = c.lines.join(" ").length;
    scr.innerHTML = `<div class="safe"></div><span class="tc">${fmtTC(c.start)}</span>
      <div class="flags">${iss.map((i) => `<span class="${i.severity === "erro" ? "e" : ""}">${esc(ISSUE_SHORT[i.code] || i.code)}</span>`).join("")}</div>
      ${(() => { const r = renderSubHtml(c.lines.join("\n")); return `<div class="sub${r.top ? " top" : ""}"><div class="cue">${r.html}</div></div>`; })()}`;
    meta.innerHTML = `<span>Legenda ${c.n} de ${res.cues.length}</span><span class="tnum">${nf1.format(dur)} s · ${chars} caracteres · ${nf1.format(dur > 0 ? chars / dur : 0)} CPS</span>`;
  };
  const select = (n, scroll = true) => {
    sel = n;
    list.querySelectorAll("li[data-n]").forEach((li) => li.setAttribute("aria-selected", String(Number(li.dataset.n) === n)));
    drawScreen();
    if (scroll) list.querySelector(`li[data-n="${n}"]`)?.scrollIntoView({ block: "nearest" });
  };
  drawList(); drawScreen();
  list.addEventListener("click", (e) => { const li = e.target.closest("li[data-n]"); if (li) select(Number(li.dataset.n), false); });
  list.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = [...list.querySelectorAll("li[data-n]")].map((li) => Number(li.dataset.n));
    const i = items.indexOf(sel);
    const next = items[Math.max(0, Math.min(items.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) select(next);
  });
  document.getElementById("only-flagged").addEventListener("change", (e) => {
    onlyFlagged = e.target.checked; drawList();
    if (onlyFlagged && !byCue[sel]) { const first = Number(Object.keys(byCue)[0]); if (first) select(first); }
  });
  main.onclick = (e) => jobActions(e, job);
}

/* ============================================================== projetos */

async function renderProjects() {
  await Promise.all([loadState(), loadProjects()]);
  if (!S.projects.length) {
    main.innerHTML = `<div class="page-head"><div><h1>Clientes</h1><p class="muted">Cada cliente guarda as regras (perfil), o glossário e as instruções. Escolha o cliente ao abrir a legenda e o resto vem junto.</p></div></div>
      <div class="panel empty"><p>Nenhum cliente ainda.</p><a class="btn primary" href="#/cliente/novo">Cadastrar cliente</a></div>`;
    return;
  }
  main.innerHTML = `
    <div class="page-head">
      <div><h1>Clientes</h1><p class="muted">Regras, glossário e instruções de cada cliente (ou de uma série específica).</p></div>
      <a class="btn primary" href="#/cliente/novo">Novo cliente</a>
    </div>
    <div class="panel" style="padding:6px 10px">
      <table class="table">
        <thead><tr><th>Cliente</th><th>Idiomas</th><th>Regras</th><th class="num">Glossário</th></tr></thead>
        <tbody>${S.projects.map((p) => `<tr class="click" data-href="#/cliente/${p.id}">
          <td><strong>${esc(p.name)}</strong>${p.client ? `<div class="muted small">${esc(p.client)}</div>` : ""}</td>
          <td class="small">${esc(langName(p.source_lang))} › ${esc(langName(p.target_lang))}</td>
          <td class="small">${esc(profileName(p.profile_key))}</td>
          <td class="num">${p.glossary_count} termos</td></tr>`).join("")}</tbody>
      </table>
    </div>`;
  main.querySelectorAll("tr[data-href]").forEach((tr) => tr.addEventListener("click", () => (location.hash = tr.dataset.href)));
}

async function renderProject(id) {
  await loadState();
  const isNew = id === "novo";
  const p = isNew ? { name: "", client: "", context: "", instructions: "", profile_key: "netflix-pt-br", source_lang: "pt-BR", target_lang: "es-419", glossary: [] }
    : await api("GET", `/api/projects/${id}`);
  let gloss = p.glossary.map((g) => ({ ...g }));

  main.innerHTML = `
    <div class="page-head">
      <div><p class="muted small"><a href="#/clientes">Clientes</a></p><h1 style="margin-top:6px">${isNew ? "Novo cliente" : esc(p.name)}</h1></div>
      <div class="row">
        ${isNew ? "" : `<button class="btn danger" data-action="delete">Apagar cliente</button>`}
        <button class="btn primary" data-action="save">Salvar</button>
      </div>
    </div>
    <section class="panel">
      <div class="grid-2">
        <label class="field"><span>Nome</span><input type="text" id="p-name" value="${esc(p.name)}" placeholder="Ex.: nome do cliente, ou Cliente — Série X"></label>
        <label class="field"><span>Empresa (opcional)</span><input type="text" id="p-client" value="${esc(p.client)}"></label>
        <label class="field"><span>Idioma de origem</span><select id="p-src">${langOptions(p.source_lang)}</select></label>
        <label class="field"><span>Idioma da tradução</span><select id="p-dst">${langOptions(p.target_lang)}</select></label>
        <label class="field"><span>Regras (perfil) · <a href="#/perfil/${esc(p.profile_key)}" id="p-rules-link">ver e editar as regras</a></span><select id="p-profile">${S.state.profiles.map((x) => `<option value="${esc(x.key)}" ${x.key === p.profile_key ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>
        <p class="muted small" style="align-self:end">As regras acompanham o idioma da legenda quando o cliente tem um perfil para cada idioma (ex.: Netflix ES ↔ PT).</p>
        <label class="field" style="grid-column:1/-1"><span>Sobre o material</span>
          <textarea id="p-context" placeholder="Assunto, época, personagens principais. Vai como contexto para a transcrição.">${esc(p.context)}</textarea></label>
        <label class="field" style="grid-column:1/-1"><span>Instruções do cliente</span>
          <textarea id="p-instr" placeholder="Ex.: tratar por “usted”; manter palavrões; nomes de marcas sem tradução.">${esc(p.instructions)}</textarea></label>
      </div>
    </section>
    <section class="panel">
      <div class="row" style="justify-content:space-between;margin-bottom:12px">
        <div><h2>Glossário</h2><p class="muted small">Nomes e termos com a tradução certa. Valem na tradução (API e ChatGPT) e ajudam a transcrição.</p></div>
        <div class="row">
          <button class="btn" data-action="import">Importar CSV</button>
          <button class="btn" data-action="export" ${gloss.length ? "" : "disabled"}>Exportar CSV</button>
        </div>
      </div>
      <table class="table" id="gloss"></table>
      <button class="btn" data-action="add" style="margin-top:10px">Adicionar termo</button>
    </section>`;

  const drawGloss = () => {
    document.getElementById("gloss").innerHTML = `<thead><tr><th style="width:34%">Termo</th><th style="width:34%">Tradução</th><th>Observação</th><th></th></tr></thead><tbody>`
      + (gloss.length ? gloss.map((g, i) => `<tr>
        <td><input type="text" data-i="${i}" data-k="term" value="${esc(g.term)}" aria-label="Termo"></td>
        <td><input type="text" data-i="${i}" data-k="translation" value="${esc(g.translation)}" aria-label="Tradução"></td>
        <td><input type="text" data-i="${i}" data-k="note" value="${esc(g.note)}" aria-label="Observação"></td>
        <td><button class="btn link" data-action="del-term" data-i="${i}">Remover</button></td></tr>`).join("")
        : `<tr><td colspan="4" class="muted">Nenhum termo. Adicione um por um ou importe um CSV com as colunas termo, tradução e observação.</td></tr>`) + "</tbody>";
  };
  drawGloss();
  document.getElementById("gloss").addEventListener("input", (e) => {
    const t = e.target;
    if (t.dataset.i != null) gloss[Number(t.dataset.i)][t.dataset.k] = t.value;
  });

  document.getElementById("p-profile").addEventListener("change", (e) => { document.getElementById("p-rules-link").href = `#/perfil/${e.target.value}`; });
  const collect = () => ({
    name: document.getElementById("p-name").value, client: document.getElementById("p-client").value,
    source_lang: document.getElementById("p-src").value, target_lang: document.getElementById("p-dst").value,
    profile_key: document.getElementById("p-profile").value, context: document.getElementById("p-context").value,
    instructions: document.getElementById("p-instr").value, glossary: gloss.filter((g) => g.term.trim()),
  });

  main.onclick = async (e) => {
    const b = e.target.closest("[data-action]");
    if (!b) return;
    const a = b.dataset.action;
    try {
      if (a === "add") { gloss.push({ term: "", translation: "", note: "" }); drawGloss(); document.querySelector(`#gloss input[data-i="${gloss.length - 1}"]`).focus(); }
      if (a === "del-term") { gloss.splice(Number(b.dataset.i), 1); drawGloss(); }
      if (a === "import") {
        const { paths } = await api("POST", "/api/dialog", { kind: "csv" });
        if (!paths.length) return;
        const { glossary } = await api("POST", "/api/glossary/import", { path: paths[0] });
        const known = new Set(gloss.map((g) => g.term.toLowerCase()));
        const added = glossary.filter((g) => !known.has(g.term.toLowerCase()));
        gloss = gloss.concat(added); drawGloss();
        main.querySelector('[data-action="export"]').disabled = !gloss.length;
        toast(`${added.length} termos importados. Clique em Salvar para guardar.`);
      }
      if (a === "export") {
        const { paths } = await api("POST", "/api/dialog", { kind: "folder", title: "Onde salvar o glossário" });
        if (!paths.length) return;
        const r = await api("POST", "/api/glossary/export", { folder: paths[0], name: collect().name || "glossario", glossary: gloss });
        toast(`Glossário salvo em ${r.path}`);
      }
      if (a === "save") {
        const saved = isNew ? await api("POST", "/api/projects", collect()) : await api("PUT", `/api/projects/${id}`, collect());
        toast("Cliente salvo.");
        if (isNew) location.hash = `#/cliente/${saved.id}`; else router();
      }
      if (a === "delete") {
        if (!confirm(`Apagar o cliente “${p.name}” e o glossário dele? Os trabalhos já feitos continuam no histórico.`)) return;
        await api("DELETE", `/api/projects/${id}`); toast("Cliente apagado."); location.hash = "#/clientes";
      }
    } catch (err) { toast(err.message, true); }
  };
}

/* ========================================================= configurações */

async function renderSettings() {
  const [st] = await Promise.all([loadState(), loadProjects()]);
  const s = st.settings;
  const al = st.align;
  const modelRow = (lang, label) => {
    const v = al.models[lang];
    const status = v === "pronto" ? `<span class="pill pronto">Baixado</span>`
      : v === "baixando" ? `<span class="pill rodando">Baixando…</span>`
      : String(v).startsWith("erro") ? `<span class="pill erro">Falhou</span>`
      : `<button class="btn" data-action="download" data-lang="${lang}" ${al.installed ? "" : "disabled"}>Baixar (≈1,2 GB)</button>`;
    return `<tr><td>${label}</td><td class="num">${status}</td></tr>`;
  };

  const setRow = (help, title, value, action) => `<div class="ds-set-row"><div class="ds-set-line">
      <div class="ds-set-text"><div class="ds-set-title">${esc(title)} ${helpBtn(help)}</div><div class="ds-set-value">${value}</div></div>
      ${action}</div></div>`;
  const nClients = (S.projects || []).length;
  const prov = (st.ai?.providers || []).find((x) => x.id === st.ai?.provider);
  main.innerHTML = `
  <div class="ds-page">
    <header class="ds-head"><div class="ds-head-main"><h1 class="ds-title">Configurações</h1>
      <p class="ds-sub">O dia a dia fica aqui em cima. O técnico fica em “Avançado”, lá embaixo.</p></div></header>

    <section class="ds-set" aria-label="Configurações principais">
      ${setRow("cfg-licenca", "Licença", (() => { const l = st.licenca || {}; return l.modo === "licenciada"
        ? `${esc(l.licenca)} · plano ${esc(l.plano)} · ${l.valido_ate ? `válida até ${esc(new Date(l.valido_ate).toLocaleDateString("pt-BR"))}` : "sem vencimento"}`
        : l.modo === "avaliacao" ? `Avaliação até ${esc(new Date(l.valido_ate).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }))}`
        : "Modo grátis: projetos e tradução manual. IA, sincronia pela fala, regras e relatórios precisam de licença."; })(),
        `<button class="ds-btn sm ${(st.licenca || {}).modo === "licenciada" ? "" : "primary"}" data-action="licenca">${(st.licenca || {}).modo === "licenciada" ? "Ver" : "Ativar"}</button>`)}
      ${setRow("cfg-versao", "Versão do programa", `${esc(st.versao_completa || st.version || "")} · o programa se atualiza sozinho ao abrir e avisa quando houver versão nova`,
        `<button class="ds-btn sm" data-action="check-update">Procurar atualização</button>`)}
      ${st.janela ? setRow("cfg-bandeja", "Bandeja do sistema", `<label class="check"><input type="checkbox" id="s-bandeja" ${s.bandeja !== false ? "checked" : ""}>
          Manter o ícone ao lado do relógio; o X esconde a janela em vez de fechar</label>`, "") : ""}
      ${setRow("cfg-perfil", "Perfil na nuvem", `<span id="pf-resumo">${esc(perfilResumo(S.perfil))}</span>`,
        `<button class="ds-btn sm" data-action="perfil">Abrir</button>`)}
      ${setRow("cfg-nome", "Seu nome na legenda", `<input type="text" id="s-who" value="${esc(s.translator_name || "")}" placeholder="Como você assina as legendas" aria-label="Seu nome na legenda">`,
        `<button class="ds-btn sm" data-action="save-who">Salvar</button>`)}
      ${setRow("cfg-pasta", "Pasta dos trabalhos", `<span class="mono small">${esc(st.projects_root || "não escolhida")}</span> — um mês por pasta (${esc(monthFolder(thisMonth()))}…)`,
        `<a class="ds-btn sm" href="#/bemvindo">Trocar</a>`)}
      ${setRow("cfg-clientes", "Clientes", nClients ? `${nClients} cadastrado${nClients === 1 ? "" : "s"}: ${esc((S.projects || []).slice(0, 4).map((c) => c.name).join(", "))}${nClients > 4 ? "…" : ""}` : "Nenhum ainda",
        `<a class="ds-btn sm" href="#/clientes">Abrir</a>`)}
      ${setRow("cfg-perfis", "Perfis de regras", `${(st.profiles || []).length} perfis (limites e manual de cada cliente)`,
        `<a class="ds-btn sm" href="#/perfis">Abrir</a>`)}
      ${setRow("cfg-ia", "Tradução automática", `Pelo seu ChatGPT (sem custo) ou pela API${prov ? ` · serviço: ${esc(prov.name || prov.id)}${prov.ready ? " (pronto)" : " (falta a chave)"}` : ""}`,
        `<button class="ds-btn sm" data-action="open-ai">Configurar</button>`)}
      ${setRow("cfg-fila", "Trabalhos em segundo plano", "Transcrições e traduções que rodam sozinhas",
        `<a class="ds-btn sm" href="#/trabalhos">Ver</a>`)}
      ${setRow("cfg-editor", "Preferências do editor", "Cores, fontes, forma de onda e tamanho das áreas",
        `<button class="ds-btn sm" data-action="edprefs">Abrir</button>`)}
    </section>

    <details class="ds-adv" id="ai-wrap" ${AI_TAB ? "open" : ""}>
      <summary><div class="ds-set-text"><div class="ds-set-title">Tradução automática pela API</div>
        <div class="ds-set-value">Serviço, modelo e chaves (ficam no Gerenciador de Credenciais do Windows).</div></div></summary>
      <div class="ds-adv-body">${aiSection(st)}</div>
    </details>

    <details class="ds-adv" id="adv-wrap">
      <summary><div class="ds-set-text"><div class="ds-set-title">Avançado ${helpBtn("cfg-avancado")}</div>
        <div class="ds-set-value">Modelos de IA, preços, placa de vídeo, transcrição, tempo das palavras e arquivos temporários. Não precisa mexer no dia a dia.</div></div></summary>
      <div class="ds-adv-body">
    <section class="panel stack">
      <h2>Tempo das palavras</h2>
      <p class="muted">Para a legenda entrar e sair no momento exato da fala, o programa usa um modelo de alinhamento que roda no próprio computador. Sem ele, os tempos são estimados.</p>
      ${al.installed ? "" : `<p class="note warn">O alinhamento preciso não está instalado nesta versão. Os tempos serão estimados até a versão com instalador completo.</p>`}
      <table class="table"><tbody>${modelRow("pt", "Português")}${modelRow("es", "Espanhol")}</tbody></table>
      <p class="muted small">Se não baixar antes, o modelo é baixado automaticamente no primeiro trabalho daquele idioma.</p>
    </section>

    <section class="panel stack">
      <h2>Avançado</h2>
      <div class="grid-2">
        <label class="field"><span>Modelo de transcrição</span><input type="text" id="s-model" value="${esc(s.transcribe_model)}"></label>
        <label class="field"><span>Preço por minuto de áudio (US$)</span><input type="number" step="0.0001" min="0" id="s-price" value="${s.transcribe_usd_per_min}"></label>
        <label class="field"><span>Modelo de tradução</span><input type="text" id="s-tmodel" value="${esc(s.translate_model)}"></label>
        <label class="field"><span>Preço da tradução (US$ por milhão de tokens: entrada / saída)</span>
          <div class="row" style="flex-wrap:nowrap"><input type="number" step="0.01" min="0" id="s-tin" value="${s.translate_usd_per_mtok_in}" aria-label="Entrada"><input type="number" step="0.01" min="0" id="s-tout" value="${s.translate_usd_per_mtok_out}" aria-label="Saída"></div></label>
        <label class="field"><span>Trechos enviados ao mesmo tempo</span><input type="number" min="1" max="8" id="s-par" value="${s.parallel_requests}"></label>
        <label class="field"><span>Tempo das palavras</span>
          <select id="s-align">
            <option value="auto" ${s.align === "auto" ? "selected" : ""}>Preciso quando disponível</option>
            <option value="model" ${s.align === "model" ? "selected" : ""}>Sempre preciso (para se faltar o modelo)</option>
            <option value="estimate" ${s.align === "estimate" ? "selected" : ""}>Sempre estimado (mais rápido)</option>
          </select></label>
        <label class="field"><span>Placa de vídeo (separar a voz e transcrever)</span>
          <select id="s-gpu">
            <option value="auto" ${s.use_gpu !== "nao" ? "selected" : ""}>Usar quando houver (recomendado)</option>
            <option value="nao" ${s.use_gpu === "nao" ? "selected" : ""}>Não usar (só o processador)</option>
          </select></label>
        <label class="field"><span>Quem transcreve a fala (legenda nova)</span>
          <select id="s-engine">
            <option value="local" ${s.transcribe_engine !== "openai" ? "selected" : ""}>Este computador (Whisper, sem custo)</option>
            <option value="openai" ${s.transcribe_engine === "openai" ? "selected" : ""}>API da OpenAI (pago, pela internet)</option>
          </select></label>
        <label class="check"><input type="checkbox" id="s-multi" ${s.transcribe_multilang !== false ? "checked" : ""}> Conferir falas em outros idiomas (personagem estrangeiro): transcreve no idioma da fala e marca ⚑</label>
        <label class="field"><span>Modelo de transcrição no computador</span>
          <select id="s-whisper">
            <option value="large-v3" ${s.whisper_model === "large-v3" || !s.whisper_model ? "selected" : ""}>O melhor (~3 GB, recomendado)</option>
            <option value="medium" ${s.whisper_model === "medium" ? "selected" : ""}>Médio (~1,5 GB)</option>
            <option value="small" ${s.whisper_model === "small" ? "selected" : ""}>Rápido (~480 MB, menos preciso)</option>
          </select></label>
        <label class="field"><span>Apagar arquivos temporários após (dias)</span><input type="number" min="1" max="365" id="s-days" value="${s.keep_job_days}"></label>
      </div>
      <div class="row"><button class="btn primary" data-action="save-settings">Salvar</button></div>
    </section>
      </div>
    </details>

    <section class="panel stack">
      <h2>Programa</h2>
      <p class="muted small">Versão ${esc(st.version)}. Dados e arquivos temporários em <span class="tnum">${esc(st.data_dir)}</span>.</p>
      <div class="row"><button class="btn" data-action="open-data">Abrir pasta de dados</button>
      <button class="btn danger" data-action="quit">Fechar o programa</button></div>
    </section>
  </div>`;



  api("GET", "/api/perfil").then((p) => { S.perfil = p; const el = document.getElementById("pf-resumo"); if (el) el.textContent = perfilResumo(p); }).catch(() => {});
  document.getElementById("s-bandeja")?.addEventListener("change", async (e) => {
    try {
      S.state.settings = await api("PUT", "/api/settings", { bandeja: e.target.checked });
      toast(e.target.checked ? "O ícone fica na bandeja; o X esconde a janela." : "Sem bandeja: o X pergunta e fecha o programa.");
    } catch (err) { toast(err.message, true); e.target.checked = !e.target.checked; }
  });
  main.onclick = async (e) => {
    const b = e.target.closest("[data-action]");
    if (!b) return;
    const a = b.dataset.action;
    const msg = document.getElementById("key-msg");
    const showKeyMsg = (r) => { msg.hidden = false; msg.className = "note " + (r.ok ? "ok" : "err"); msg.textContent = r.message; };
    try {
      if (a.startsWith("ai-")) { await aiAction(a, b); return; }
      if (a === "edprefs") { openEdPrefs(); return; }
      if (a === "licenca") { openLicenseModal(); return; }
      if (a === "open-ai") { const d = document.getElementById("ai-wrap"); d.open = true; d.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
      if (a === "save-key") {
        const v = document.getElementById("key-in").value.trim();
        if (!v) { toast("Cole a chave no campo.", true); return; }
        b.disabled = true; b.textContent = "Testando…";
        const r = await api("POST", "/api/key", { key: v });
        document.getElementById("key-in").value = "";
        await renderSettings();
        const m2 = document.getElementById("key-msg");
        m2.hidden = false; m2.className = "note " + (r.ok ? "ok" : "err"); m2.textContent = r.ok ? "Chave salva. " + r.message : r.message;
      }
      if (a === "test-key") { b.disabled = true; showKeyMsg(await api("POST", "/api/key/test")); b.disabled = false; }
      if (a === "remove-key") {
        if (!confirm("Remover a chave da OpenAI deste computador?")) return;
        await api("DELETE", "/api/key"); toast("Chave removida."); renderSettings();
      }
      if (a === "download") {
        await api("POST", `/api/models/${b.dataset.lang}`); toast("Baixando o modelo. Pode continuar usando o programa.");
        renderSettings();
        const tid = every(3000, async () => {
          const s2 = await api("GET", "/api/state");
          if (s2.align.models[b.dataset.lang] !== "baixando") { clearInterval(tid); renderSettings(); }
        });
      }
      if (a === "save-who") {
        S.state.settings = await api("PUT", "/api/settings", { translator_name: document.getElementById("s-who").value.trim() });
        toast("Nome salvo.");
      }
      if (a === "save-settings") {
        await api("PUT", "/api/settings", {
          transcribe_model: document.getElementById("s-model").value.trim(),
          transcribe_usd_per_min: Number(document.getElementById("s-price").value),
          translate_model: document.getElementById("s-tmodel").value.trim() || "gpt-5.5",
          translate_usd_per_mtok_in: Number(document.getElementById("s-tin").value),
          translate_usd_per_mtok_out: Number(document.getElementById("s-tout").value),
          parallel_requests: Number(document.getElementById("s-par").value),
          align: document.getElementById("s-align").value,
          use_gpu: document.getElementById("s-gpu").value,
          whisper_model: document.getElementById("s-whisper").value,
          transcribe_engine: document.getElementById("s-engine").value,
          transcribe_multilang: document.getElementById("s-multi").checked,
          keep_job_days: Number(document.getElementById("s-days").value),
        });
        await loadState();
        toast("Configurações salvas.");
      }
      if (a === "check-update") await checkUpdate(true);
      if (a === "perfil") await perfilModal();
      if (a === "open-data") await api("POST", "/api/open", { path: st.data_dir });
      if (a === "quit") {
        if (!confirm("Fechar o programa? Trabalhos em andamento serão interrompidos (dá para retomar depois).")) return;
        await api("POST", "/api/shutdown");     // na janela própria, ela fecha sozinha
        main.innerHTML = `<div class="panel empty"><p>O programa foi fechado. Pode fechar esta aba.</p></div>`;
      }
    } catch (err) { toast(err.message, true); }
  };
}

function drawProfiles(list) {
  document.getElementById("profiles").innerHTML = `<thead><tr><th>Perfil</th><th class="num">Regras</th><th class="num">Caracteres</th><th class="num">CPS</th><th class="num">Duração</th></tr></thead><tbody>`
    + list.map((p) => `<tr class="click" data-href="#/perfil/${esc(p.key)}">
      <td><strong>${esc(p.name)}</strong>${p.builtin ? ` <span class="muted small">${p.modified ? "pronto · alterado" : "pronto"}</span>` : ""}</td>
      <td class="num">${(p.rules || []).filter((r) => r.active).length}</td>
      <td class="num">${p.max_chars_per_line} × ${p.max_lines}</td><td class="num">${nf1.format(p.max_cps)}</td>
      <td class="num">${nf1.format(p.min_duration)}–${nf1.format(p.max_duration)} s</td>
    </tr>`).join("") + "</tbody>";
  document.querySelectorAll("#profiles tr[data-href]").forEach((tr) => tr.addEventListener("click", () => (location.hash = tr.dataset.href)));
}

/* ---------------------------------------------- inteligência artificial */

let AI_TAB = null;

function aiSection(st) {
  const ai = st.ai;
  if (!ai?.providers) return "";
  AI_TAB = AI_TAB || ai.provider;
  const p = ai.providers.find((x) => x.id === AI_TAB) || ai.providers[0];
  const price = (m) => m.usd_in != null || m.usd_out != null
    ? `US$ ${nf1.format(m.usd_in ?? 0)} / ${nf1.format(m.usd_out ?? 0)}` : (p.subscription ? "assinatura" : "preço não informado");
  const showFmt = p.id === "ghostcli" || p.id === "gateway";
  return `
    <section class="panel stack" id="ai">
      <div class="row" style="justify-content:space-between"><h2>Inteligência artificial</h2><span class="label">tradução automática</span></div>
      <p class="muted small">A <b>tradução automática</b> (pela API) usa o serviço marcado abaixo. A transcrição é feita neste computador (ou pela OpenAI, se escolhido em Avançado). As chaves ficam no Gerenciador de Credenciais do Windows, nunca em arquivo.</p>
      <div class="ai-use">
        <span class="label">Traduzir com</span>
        ${ai.providers.map((x) => `<label class="ai-chip ${x.ready ? "" : "off"}" title="${x.ready ? "" : "Falta configurar"}">
          <input type="radio" name="ai-prov" value="${x.id}" ${ai.provider === x.id ? "checked" : ""} ${x.ready ? "" : "disabled"}>
          <b>${esc(x.name)}</b><span class="mono small">${esc(x.selected || "—")}</span></label>`).join("")}
      </div>
      <div class="seg ai-tabs" role="tablist">${ai.providers.map((x) => `<button data-action="ai-tab" data-p="${x.id}" aria-selected="${x.id === p.id}">${esc(x.name)}${x.key ? " ✓" : ""}</button>`).join("")}</div>
      <div class="ai-card" id="ai-card" data-p="${p.id}">
        <div class="row" style="justify-content:space-between"><h3>${esc(p.name)}</h3>
          ${p.key ? `<span class="pill st-finalizado">chave ${esc(p.key)}</span>` : `<span class="pill">sem chave</span>`}</div>
        <p class="muted small">${esc(p.help)}</p>
        <div class="grid-2">
          ${p.id === "gateway" ? `<label class="field"><span>Nome (aparece na tela)</span><input type="text" id="ai-name" value="${esc(p.name === "Gateway personalizado" ? "" : p.name)}" placeholder="Ex.: OpenRouter"></label>` : ""}
          <label class="field" ${p.id === "gateway" ? "" : `style="grid-column:1/-1"`}><span>Chave ${p.id === "gateway" ? `<em class="muted small">(se o serviço pedir)</em>` : ""}</span>
            <input type="password" id="ai-key" autocomplete="off" placeholder="${p.key ? "Já configurada — cole outra para trocar" : esc(p.key_prefix ? p.key_prefix + "…" : "chave")}"></label>
          ${p.url_editable ? `<label class="field" style="grid-column:1/-1"><span>Endereço (host) ${p.default_url ? `<em class="muted small">· padrão ${esc(p.default_url)}</em>` : ""}</span>
            <input type="text" id="ai-url" class="mono" value="${esc(p.url)}" placeholder="${esc(p.default_url || "https://…/v1")}"></label>` : ""}
          ${p.id !== "openai" ? `<label class="check" style="grid-column:1/-1"><input type="checkbox" id="ai-ipv4" ${p.ipv4 ? "checked" : ""}>
            <span>Conectar só por IPv4 <em class="muted small">— use quando o serviço libera o acesso pelo seu IP (o painel do GhostCLI mostra IPv4). Sem isso, o Windows pode sair por IPv6 e o serviço ver outro endereço.</em></span></label>` : ""}
        </div>
        <div class="row"><button class="btn primary" data-action="ai-save">Salvar e testar</button>
          ${p.key || p.id === "gateway" ? `<button class="btn" data-action="ai-test">Testar</button>` : ""}
          ${p.ready && ai.provider !== p.id ? `<button class="btn" data-action="ai-use">Usar para traduzir</button>` : ""}
          ${p.key ? `<button class="btn danger" data-action="ai-del">Remover chave</button>` : ""}</div>
        <p class="note" id="ai-msg" hidden></p>

        <div class="ai-models">
          <span class="label">Modelo</span>
          ${p.models.length ? p.models.map((m) => `<label class="ai-model ${m.id === p.selected ? "on" : ""}">
            <input type="radio" name="ai-model" value="${esc(m.id)}" ${m.id === p.selected ? "checked" : ""}>
            <div><b>${esc(m.label)}</b> <span class="mono small muted">${esc(m.id)}</span>
              ${showFmt ? `<span class="pill fmt">${m.api_format === "anthropic" ? "Anthropic" : "OpenAI"}</span>` : ""}
              ${m.custom ? `<span class="pill">seu</span>` : ""}
              <div class="muted small">${esc(price(m))}${m.note ? ` · ${esc(m.note)}` : ""}</div></div>
            ${m.custom ? `<button class="btn link small" data-action="ai-rm" data-m="${esc(m.id)}">Remover</button>` : ""}
          </label>`).join("") : `<p class="muted small">Nenhum modelo ainda. Acrescente abaixo.</p>`}
        </div>
        <details class="ai-add" ${p.models.length ? "" : "open"}>
          <summary>${ic("plus")} Adicionar outro modelo</summary>
          <div class="grid-3" style="margin-top:10px">
            <label class="field"><span>Código do modelo</span><input type="text" id="am-id" class="mono" placeholder="${p.id === "claude" ? "claude-…" : p.id === "gemini" ? "gemini-…" : p.id === "openai" ? "gpt-…" : "nome-do-modelo"}"></label>
            <label class="field"><span>Nome <em class="muted small">(opcional)</em></span><input type="text" id="am-label"></label>
            ${showFmt ? `<label class="field"><span>Formato da API</span><select id="am-fmt"><option value="">Automático${p.id === "ghostcli" ? " (claude-* = Anthropic)" : ""}</option>${Object.entries(ai.formats).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select></label>` : `<span></span>`}
            <label class="field"><span>US$/milhão entrada <em class="muted small">(opcional)</em></span><input type="text" id="am-in" inputmode="decimal"></label>
            <label class="field"><span>US$/milhão saída <em class="muted small">(opcional)</em></span><input type="text" id="am-out" inputmode="decimal"></label>
            <div style="align-self:end"><button class="btn primary" data-action="ai-add">${ic("plus")} Adicionar e usar</button></div>
          </div>
          <p class="muted small" style="margin-top:6px">Use o código exato do modelo, como aparece na documentação ou no painel do serviço.</p>
        </details>
      </div>
    </section>`;
}

async function aiAction(a, b) {
  const prov = document.getElementById("ai-card")?.dataset.p;
  const v = (id) => (document.getElementById(id)?.value || "").trim();
  const show = (r) => {
    const m = document.getElementById("ai-msg");
    if (!m || !r) return;
    m.hidden = false; m.className = "note " + (r.ok ? "ok" : "err"); m.textContent = r.message;
  };
  const redraw = async (test) => { await renderSettings(); document.getElementById("ai")?.scrollIntoView({ block: "start" }); show(test); };
  if (a === "ai-tab") { AI_TAB = b.dataset.p; await redraw(); return; }
  if (a === "ai-save") {
    b.disabled = true;
    const body = { key: v("ai-key"), test: true };
    if (document.getElementById("ai-url")) body.url = v("ai-url");
    if (document.getElementById("ai-name")) body.name = v("ai-name");
    const v4 = document.getElementById("ai-ipv4");
    if (v4) body.ipv4 = v4.checked;
    const r = await api("PUT", `/api/ai/${prov}`, body);
    await redraw(r.test);
  }
  if (a === "ai-test") { b.disabled = true; show(await api("POST", `/api/ai/${prov}/test`)); b.disabled = false; }
  if (a === "ai-use") { await api("PUT", `/api/ai/${prov}`, { use: true }); toast("Tradução automática por este serviço."); await redraw(); }
  if (a === "ai-del") {
    if (!confirm("Remover a chave deste serviço deste computador?")) return;
    await api("DELETE", `/api/ai/${prov}`); toast("Chave removida."); await redraw();
  }
  if (a === "ai-add") {
    if (!v("am-id")) { toast("Digite o código do modelo.", true); return; }
    await api("PUT", `/api/ai/${prov}`, { add_model: { id: v("am-id"), label: v("am-label"), format: v("am-fmt"), usd_in: v("am-in"), usd_out: v("am-out") } });
    toast("Modelo adicionado e selecionado."); await redraw();
  }
  if (a === "ai-rm") {
    await api("PUT", `/api/ai/${prov}`, { remove_model: b.dataset.m }); toast("Modelo removido."); await redraw();
  }
}

document.addEventListener("change", async (e) => {
  try {
    if (e.target.name === "ai-prov") {
      await api("PUT", `/api/ai/${e.target.value}`, { use: true });
      await loadState();
      toast(`Tradução automática: ${e.target.closest("label").querySelector("b").textContent}.`);
    }
    if (e.target.id === "ai-ipv4") {
      const prov = document.getElementById("ai-card").dataset.p;
      await api("PUT", `/api/ai/${prov}`, { ipv4: e.target.checked });
      toast(e.target.checked ? "Conexão só por IPv4 ligada." : "Conexão só por IPv4 desligada.");
    }
    if (e.target.name === "ai-model") {
      const prov = document.getElementById("ai-card").dataset.p;
      await api("PUT", `/api/ai/${prov}`, { model: e.target.value });
      document.querySelectorAll(".ai-model").forEach((l) => l.classList.toggle("on", l.contains(e.target)));
      await loadState();
      toast(`Modelo: ${e.target.value}.`);
    }
  } catch (err) { toast(err.message, true); }
});

/* ================================================================ início */

window.addEventListener("hashchange", router);
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => e.preventDefault());
(async () => {
  drawNav();
  try {
    await loadState();
    const retomar = S.state.retomar;   // depois de atualizar/reiniciar
    await updateGate();          // atualização obrigatória antes de trabalhar
    drawLicenseBadge();
    if (await retomarOndeEstava(retomar)) { /* já navegou */ }
    else if (!location.hash) { location.hash = S.state.projects_root ? "#/inicio" : "#/bemvindo"; }
    else router();
  } catch (e) { router(); }
  refreshRunningCount();
  setInterval(() => { if (!document.hidden) refreshRunningCount(); }, 5000);
  perfilAoAbrir();
})();
