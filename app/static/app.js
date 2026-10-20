/* Legendas — página local. Sem dependências externas. */
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
    throw new Error("O programa Legendas não está respondendo. Ele foi fechado? Abra de novo pelo atalho.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let toastTimer;
function toast(msg, isErr = false) {
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
  [/^#\/novo$/, renderNew],
  [/^#\/trabalhos$/, renderJobs],
  [/^#\/trabalho\/(\d+)$/, renderJob],
  [/^#\/projetos$/, renderProjects],
  [/^#\/projeto\/(novo|\d+)$/, renderProject],
  [/^#\/configuracoes$/, renderSettings],
  [/^#\/editor(?:\/(\w+))?$/, renderEditor],
];

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
  main.onclick = null;
  cancelAnimationFrame(ED.raf);
  document.querySelectorAll("video").forEach((v) => { v.pause(); v.removeAttribute("src"); v.load(); });
  const hash = location.hash || "#/novo";
  if (!hash.startsWith("#/editor/")) { document.body.classList.remove("editor-mode"); ED.sid = null; ED.dirty = false; }
  const section = hash.split("/")[1] || "novo";
  const navKey = { trabalho: "trabalhos", projeto: "projetos" }[section] || section;
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
  location.hash = "#/novo";
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
  const noKey = !st.api_key;

  main.innerHTML = `
    <div class="page-head">
      <div>
        <h1>Novo trabalho</h1>
        <p class="muted">Traduza uma legenda ou transcreva um vídeo. O arquivo .srt sai ao lado do original.</p>
      </div>
    </div>
    ${noKey ? `<p class="note warn" style="margin-bottom:16px">Falta a chave da OpenAI. <a href="#/configuracoes">Configure aqui</a> antes de começar.</p>` : ""}
    <div class="split">
      <div>
        <section class="panel">
          <h2>Arquivos</h2>
          <div class="drop" id="drop">
            <p><strong>Arraste a legenda ou o vídeo para cá</strong></p>
            <p class="muted small">Para traduzir, basta a legenda (.srt). Junte o vídeo se quiser revisar com a imagem depois.</p>
            <div class="row">
              <button class="btn primary" data-action="pick-sub">Escolher legenda (.srt)</button>
              <button class="btn" data-action="pick-media">Escolher vídeo ou áudio</button>
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
            ${stepTile("traduzir", "Traduzir", "Traduz a legenda inteira mantendo os tempos, no padrão Netflix.")}
            ${stepTile("transcrever", "Transcrever", "Gera a legenda a partir do áudio do vídeo.")}
            ${stepTile("sincronizar", "Sincronizar", "Ajusta os tempos de uma legenda ou texto ao áudio.")}
          </div>
          <p class="muted small" style="margin-top:10px">A formatação (linhas, velocidade de leitura e duração) é feita sempre, no final.</p>
        </section>

        <section class="panel">
          <h2>Detalhes</h2>
          <div class="grid-2">
            <label class="field"><span>Projeto</span>
              <select id="f-project">
                <option value="">Sem projeto</option>
                ${S.projects.map((p) => `<option value="${p.id}" ${String(p.id) === String(d.project_id) ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
              </select>
              ${S.projects.length ? "" : `<a href="#/projeto/novo" class="small">Criar projeto com glossário</a>`}
            </label>
            <label class="field"><span>Perfil de regras</span>
              <select id="f-profile">${st.profiles.map((p) => `<option value="${esc(p.key)}" ${p.key === d.profile_key ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>
            </label>
            <div class="langs" style="grid-column:1/-1">
              <label class="field"><span>Idioma de origem <em class="muted small" id="f-detected">${d.detected ? "· detectado na legenda" : ""}</em></span>
                <select id="f-src">${langOptions(d.source_lang)}</select>
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
  const soon = { sincronizar: "Chega na próxima etapa do projeto (fase 3).", traduzir: "Chega na próxima etapa do projeto (fase 2)." }[key];
  return `<label class="step ${enabled ? "" : "off"}">
      <input type="checkbox" data-step="${key}" ${checked ? "checked" : ""} ${enabled ? "" : "disabled"}>
      <strong>${title}</strong>
      <span class="muted">${enabled ? desc : soon}</span>
    </label>`;
}

function langOptions(sel) {
  return S.state.languages.map((l) => `<option value="${l.code}" ${l.code === sel ? "selected" : ""}>${esc(l.name)}</option>`).join("");
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
  if (steps.includes("traduzir") && d.source_lang === d.target_lang) return "O idioma de origem e o de destino são iguais.";
  if (ready.filter((f) => f.kind === "subtitle").length > 1) return "Uma legenda por trabalho. Remova as outras.";
  if ((steps.includes("transcrever") || steps.includes("sincronizar")) && !has("media")) return "Para transcrever é preciso o vídeo ou o áudio.";
  if (ready.some((f) => f.kind === "media" && f.has_audio === false)) return "O vídeo escolhido não tem áudio.";
  if (steps.includes("transcrever") && !steps.includes("sincronizar") && (has("subtitle") || has("text")))
    return "Você adicionou uma legenda ou texto. Para transcrever do zero, remova esse arquivo.";
  if (ready.filter((f) => f.kind === "media").length > 1) return "Um vídeo por trabalho. Remova os outros.";
  if (!S.state.api_key) return "Configure a chave da OpenAI primeiro.";
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
          : est ? `<p class="cost">${fmtUSD(est.usd)}</p><p class="muted small">${[est.minutes ? `${fmtMin(est.minutes)} de fala` : "", est.cues && steps.includes("traduzir") ? `${est.cues} legendas para traduzir` : ""].filter(Boolean).join(" · ")}</p>`
          : `<button class="btn" data-action="estimate" ${problem ? "disabled" : ""}>Calcular custo</button>`}
      </div>
      ${problem ? `<p class="note warn small">${esc(problem)}</p>` : ""}
      <button class="btn primary big" data-action="start" ${problem ? "disabled" : ""}>${esc(startLabel(steps))}</button>
    </div>`;
}

function shortLang(code) {
  return { "pt-BR": "Português", "es-419": "Espanhol (LatAm)", "es-ES": "Espanhol (Espanha)", "en-US": "Inglês" }[code] || code;
}
function startLabel(steps) {
  const t = steps.includes("transcrever"), tr = steps.includes("traduzir");
  if (t && tr) return "Transcrever e traduzir";
  if (tr) return `Traduzir para ${shortLang(S.draft.target_lang)}`;
  if (t) return "Transcrever";
  return "Começar";
}
function oppositeLang(code) { return code && code.startsWith("es") ? "pt-BR" : "es-419"; }
/* Perfil acompanha o idioma da legenda final (mantém o infantil, se escolhido). */
function autoProfile() {
  const d = S.draft;
  if (!/^netflix-(pt-br|es-419)(-kids)?$/.test(d.profile_key)) return;
  const lang = d.steps.traduzir ? d.target_lang : d.source_lang;
  const fam = lang.startsWith("pt") ? "netflix-pt-br" : lang === "es-419" ? "netflix-es-419" : null;
  if (!fam) return;
  d.profile_key = fam + (d.profile_key.endsWith("-kids") ? "-kids" : "");
}
function syncNewForm() {
  const d = S.draft;
  autoProfile();
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  set("f-src", d.source_lang); set("f-dst", d.target_lang); set("f-profile", d.profile_key);
  document.querySelectorAll("[data-step]").forEach((cb) => { cb.checked = !!d.steps[cb.dataset.step] && !cb.disabled; });
  const dst = document.getElementById("f-dst"); if (dst) dst.disabled = !d.steps.traduzir;
  const sw = document.querySelector('[data-action="swap"]'); if (sw) sw.disabled = !d.steps.traduzir;
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
    } else if (f.kind === "media" && !d.files.some((x) => x.kind === "subtitle")) {
      d.steps.transcrever = true;
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
      try {
        const job = await api("POST", "/api/jobs", draftPayload());
        S.draft = { ...freshDraft(), project_id: d.project_id, profile_key: d.profile_key, source_lang: d.source_lang, target_lang: d.target_lang, steps: { ...d.steps }, out_dir: d.out_dir };
        location.hash = `#/trabalho/${job.id}`;
      } catch (err) { toast(err.message, true); b.disabled = false; }
    }
  };

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
        <td><strong>${esc(j.name)}</strong><div class="muted small">${esc(j.project_name || "Sem projeto")} · ${j.steps.filter((s) => s !== "formatar").map((s) => STEP_NAMES[s]).join(", ")}</div></td>
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
        <p class="muted small"><a href="#/trabalhos">Trabalhos</a> / ${esc(job.project_name || "Sem projeto")}</p>
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
      <button class="btn primary" data-action="editor" ${res.exists ? "" : "disabled"}>Abrir no editor</button>
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
      <div class="sub">${c.lines.map((l) => `<div>${esc(l)}</div>`).join("")}</div>`;
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
    main.innerHTML = `<div class="page-head"><div><h1>Projetos</h1><p class="muted">Um projeto guarda o glossário, as instruções do cliente e as preferências de uma série ou cliente.</p></div></div>
      <div class="panel empty"><p>Nenhum projeto ainda.</p><a class="btn primary" href="#/projeto/novo">Criar projeto</a></div>`;
    return;
  }
  main.innerHTML = `
    <div class="page-head">
      <div><h1>Projetos</h1><p class="muted">Glossário, instruções e preferências por série ou cliente.</p></div>
      <a class="btn primary" href="#/projeto/novo">Novo projeto</a>
    </div>
    <div class="panel" style="padding:6px 10px">
      <table class="table">
        <thead><tr><th>Projeto</th><th>Idiomas</th><th>Perfil</th><th class="num">Glossário</th></tr></thead>
        <tbody>${S.projects.map((p) => `<tr class="click" data-href="#/projeto/${p.id}">
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
      <div><p class="muted small"><a href="#/projetos">Projetos</a></p><h1 style="margin-top:6px">${isNew ? "Novo projeto" : esc(p.name)}</h1></div>
      <div class="row">
        ${isNew ? "" : `<button class="btn danger" data-action="delete">Apagar projeto</button>`}
        <button class="btn primary" data-action="save">Salvar</button>
      </div>
    </div>
    <section class="panel">
      <div class="grid-2">
        <label class="field"><span>Nome</span><input type="text" id="p-name" value="${esc(p.name)}" placeholder="Ex.: Série O Sítio — 2ª temporada"></label>
        <label class="field"><span>Cliente</span><input type="text" id="p-client" value="${esc(p.client)}"></label>
        <label class="field"><span>Idioma de origem</span><select id="p-src">${langOptions(p.source_lang)}</select></label>
        <label class="field"><span>Idioma da tradução</span><select id="p-dst">${langOptions(p.target_lang)}</select></label>
        <label class="field"><span>Perfil de regras</span><select id="p-profile">${S.state.profiles.map((x) => `<option value="${esc(x.key)}" ${x.key === p.profile_key ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>
        <span></span>
        <label class="field" style="grid-column:1/-1"><span>Sobre a série</span>
          <textarea id="p-context" placeholder="Assunto, época, personagens principais. Vai como contexto para a transcrição.">${esc(p.context)}</textarea></label>
        <label class="field" style="grid-column:1/-1"><span>Instruções do cliente</span>
          <textarea id="p-instr" placeholder="Ex.: tratar por “usted”; manter palavrões; nomes de marcas sem tradução.">${esc(p.instructions)}</textarea></label>
      </div>
    </section>
    <section class="panel">
      <div class="row" style="justify-content:space-between;margin-bottom:12px">
        <div><h2>Glossário</h2><p class="muted small">Nomes e termos que a transcrição deve acertar. A coluna de tradução será usada quando a tradução chegar.</p></div>
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
        toast("Projeto salvo.");
        if (isNew) location.hash = `#/projeto/${saved.id}`; else router();
      }
      if (a === "delete") {
        if (!confirm(`Apagar o projeto “${p.name}” e o glossário dele? Os trabalhos já feitos continuam no histórico.`)) return;
        await api("DELETE", `/api/projects/${id}`); toast("Projeto apagado."); location.hash = "#/projetos";
      }
    } catch (err) { toast(err.message, true); }
  };
}

/* ========================================================= configurações */

async function renderSettings() {
  const st = await loadState();
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

  main.innerHTML = `
    <div class="page-head"><div><h1>Configurações</h1></div></div>

    <section class="panel stack">
      <h2>Chave da OpenAI</h2>
      ${st.api_key
        ? `<p>Chave configurada, terminando em <strong class="tnum">${esc(st.api_key)}</strong>. Fica guardada no Gerenciador de Credenciais do Windows.</p>
           <div class="row"><button class="btn" data-action="test-key">Testar chave</button><button class="btn danger" data-action="remove-key">Remover chave</button></div>`
        : `<p class="muted">Crie uma chave em platform.openai.com, em API keys, e cole aqui. Ela fica guardada no Gerenciador de Credenciais do Windows, nunca em arquivo.</p>`}
      <div class="row" style="flex-wrap:nowrap">
        <input type="password" id="key-in" placeholder="sk-…" autocomplete="off" aria-label="Chave da OpenAI">
        <button class="btn primary" data-action="save-key">${st.api_key ? "Trocar chave" : "Salvar e testar"}</button>
      </div>
      <p id="key-msg" hidden></p>
    </section>

    <section class="panel stack">
      <h2>Tempo das palavras</h2>
      <p class="muted">Para a legenda entrar e sair no momento exato da fala, o programa usa um modelo de alinhamento que roda no próprio computador. Sem ele, os tempos são estimados.</p>
      ${al.installed ? "" : `<p class="note warn">O alinhamento preciso não está instalado nesta versão. Os tempos serão estimados até a versão com instalador completo.</p>`}
      <table class="table"><tbody>${modelRow("pt", "Português")}${modelRow("es", "Espanhol")}</tbody></table>
      <p class="muted small">Se não baixar antes, o modelo é baixado automaticamente no primeiro trabalho daquele idioma.</p>
    </section>

    <section class="panel">
      <h2>Perfis de regras</h2>
      <table class="table" id="profiles"></table>
      <div id="profile-form"></div>
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
        <label class="field"><span>Apagar arquivos temporários após (dias)</span><input type="number" min="1" max="365" id="s-days" value="${s.keep_job_days}"></label>
      </div>
      <div class="row"><button class="btn primary" data-action="save-settings">Salvar</button></div>
    </section>

    <section class="panel stack">
      <h2>Programa</h2>
      <p class="muted small">Versão ${esc(st.version)}. Dados e arquivos temporários em <span class="tnum">${esc(st.data_dir)}</span>.</p>
      <div class="row"><button class="btn" data-action="open-data">Abrir pasta de dados</button>
      <button class="btn danger" data-action="quit">Fechar o programa</button></div>
    </section>`;

  drawProfiles(st.profiles);

  main.onclick = async (e) => {
    const b = e.target.closest("[data-action]");
    if (!b) return;
    const a = b.dataset.action;
    const msg = document.getElementById("key-msg");
    const showKeyMsg = (r) => { msg.hidden = false; msg.className = "note " + (r.ok ? "ok" : "err"); msg.textContent = r.message; };
    try {
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
      if (a === "save-settings") {
        await api("PUT", "/api/settings", {
          transcribe_model: document.getElementById("s-model").value.trim(),
          transcribe_usd_per_min: Number(document.getElementById("s-price").value),
          translate_model: document.getElementById("s-tmodel").value.trim() || "gpt-5.5",
          translate_usd_per_mtok_in: Number(document.getElementById("s-tin").value),
          translate_usd_per_mtok_out: Number(document.getElementById("s-tout").value),
          parallel_requests: Number(document.getElementById("s-par").value),
          align: document.getElementById("s-align").value,
          keep_job_days: Number(document.getElementById("s-days").value),
        });
        toast("Configurações salvas.");
      }
      if (a === "open-data") await api("POST", "/api/open", { path: st.data_dir });
      if (a === "quit") {
        if (!confirm("Fechar o programa? Trabalhos em andamento serão interrompidos (dá para retomar depois).")) return;
        await api("POST", "/api/shutdown");
        main.innerHTML = `<div class="panel empty"><p>O programa foi fechado. Pode fechar esta aba.</p></div>`;
      }
      if (a === "dup-profile" || a === "edit-profile") {
        const p = S.state.profiles.find((x) => x.key === b.dataset.key);
        profileForm(a === "dup-profile" ? { ...p, key: null, builtin: false, name: p.name + " (cópia)" } : p);
      }
      if (a === "del-profile") {
        if (!confirm("Apagar este perfil?")) return;
        const r = await api("DELETE", `/api/profiles/${b.dataset.key}`);
        S.state.profiles = r.profiles; drawProfiles(r.profiles); document.getElementById("profile-form").innerHTML = "";
      }
      if (a === "save-profile") {
        const f = (id) => document.getElementById(id).value;
        const data = {
          name: f("pf-name"), language: f("pf-lang"), max_chars_per_line: Number(f("pf-cpl")), max_lines: Number(f("pf-lines")),
          max_cps: Number(f("pf-cps")), min_duration: Number(f("pf-min")), max_duration: Number(f("pf-max")), min_gap_frames: Number(f("pf-gap")),
        };
        const key = b.dataset.key;
        const r = key ? await api("PUT", `/api/profiles/${key}`, data) : await api("POST", "/api/profiles", data);
        S.state.profiles = r.profiles; drawProfiles(r.profiles); document.getElementById("profile-form").innerHTML = "";
        toast("Perfil salvo.");
      }
      if (a === "cancel-profile") document.getElementById("profile-form").innerHTML = "";
    } catch (err) { toast(err.message, true); }
  };
}

function drawProfiles(list) {
  document.getElementById("profiles").innerHTML = `<thead><tr><th>Perfil</th><th class="num">Caracteres</th><th class="num">Linhas</th><th class="num">CPS</th><th class="num">Duração</th><th></th></tr></thead><tbody>`
    + list.map((p) => `<tr>
      <td>${esc(p.name)}${p.builtin ? ` <span class="muted small">pronto</span>` : ""}</td>
      <td class="num">${p.max_chars_per_line}</td><td class="num">${p.max_lines}</td><td class="num">${nf1.format(p.max_cps)}</td>
      <td class="num">${nf1.format(p.min_duration)}–${nf1.format(p.max_duration)} s</td>
      <td class="num"><button class="btn link" data-action="dup-profile" data-key="${esc(p.key)}">Duplicar</button>
        ${p.builtin ? "" : `<button class="btn link" data-action="edit-profile" data-key="${esc(p.key)}">Editar</button><button class="btn link" data-action="del-profile" data-key="${esc(p.key)}">Apagar</button>`}</td>
    </tr>`).join("") + "</tbody>";
}

function profileForm(p) {
  const num = (id, label, v, step = "1", min = "0") => `<label class="field"><span>${label}</span><input type="number" id="${id}" value="${v}" step="${step}" min="${min}"></label>`;
  document.getElementById("profile-form").innerHTML = `
    <div class="stack" style="margin-top:16px;border-top:1px solid var(--line);padding-top:16px">
      <h3>${p.key ? "Editar perfil" : "Novo perfil"}</h3>
      <div class="grid-2">
        <label class="field"><span>Nome</span><input type="text" id="pf-name" value="${esc(p.name)}"></label>
        <label class="field"><span>Idioma</span><select id="pf-lang">${langOptions(p.language)}</select></label>
        ${num("pf-cpl", "Caracteres por linha", p.max_chars_per_line, "1", "10")}
        ${num("pf-lines", "Linhas", p.max_lines, "1", "1")}
        ${num("pf-cps", "Velocidade máxima (CPS)", p.max_cps, "0.5", "1")}
        ${num("pf-gap", "Intervalo entre legendas (quadros)", p.min_gap_frames)}
        ${num("pf-min", "Duração mínima (s)", Math.round(p.min_duration * 1000) / 1000, "0.001", "0.1")}
        ${num("pf-max", "Duração máxima (s)", p.max_duration, "0.5", "1")}
      </div>
      <div class="row"><button class="btn primary" data-action="save-profile" data-key="${p.key || ""}">Salvar perfil</button>
      <button class="btn" data-action="cancel-profile">Cancelar</button></div>
    </div>`;
  document.getElementById("pf-name").focus();
}

/* ================================================================ início */

window.addEventListener("hashchange", router);
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => e.preventDefault());
(async () => {
  try {
    await loadState();
    if (!location.hash) { location.hash = S.state.api_key ? "#/novo" : "#/configuracoes"; }
    else router();
  } catch (e) { router(); }
  refreshRunningCount();
  setInterval(() => { if (!document.hidden) refreshRunningCount(); }, 5000);
})();
