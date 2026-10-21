/* CNT Legendas — Início: abrir legenda/vídeo direto no editor, recentes e atalhos. */
"use strict";

const HOME = { srt: "", video: "", text: "", uploading: 0 };

function homeClient() { return getPref("cnt.cliente", ""); }

async function renderHome() {
  document.body.classList.remove("editor-mode");
  await Promise.all([loadState(), loadProjects()]);
  setCrumb("Editor <span class=\"muted\">/ abrir legenda avulsa</span>");
  const st = S.state;
  const client = homeClient();
  const clients = S.projects || [];
  main.innerHTML = `
    <div class="home">
      <div class="page-head"><div><span class="eyebrow">Editor</span><h1 style="margin-top:6px">Abrir legenda avulsa</h1>
        <p class="muted">Para revisar uma legenda rápida, fora de um projeto. Para o trabalho do dia a dia, use <a href="#/inicio">Projetos</a>: assim tudo fica organizado e entra nos relatórios.</p></div></div>
      <section class="panel home-open">
        <div class="drop big" id="home-drop">
          <p><strong>Arraste aqui a legenda (.srt) e o vídeo</strong></p>
          <p class="muted small">Ou escolha os arquivos:</p>
          <div class="row" style="justify-content:center">
            <button class="btn primary" data-h="pick-srt">Escolher legenda</button>
            <button class="btn" data-h="pick-video">Escolher vídeo</button>
            <button class="btn ghost" data-h="pick-text" title="Roteiro ou transcrição sem tempos">Texto sem tempo…</button>
          </div>
        </div>
        <ul class="files" id="home-files"></ul>
        <div class="home-go">
          <label class="field"><span>Cliente</span>
            <select id="home-client"><option value="">Nenhum (regras Netflix)</option>${clients.map((p) => `<option value="${p.id}" ${String(p.id) === client ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
          <button class="btn primary big" data-h="open" id="home-open" disabled>Abrir no editor</button>
        </div>
        <p class="muted small" id="home-hint"></p>
      </section>

      <section class="panel">
        <h2>Recentes</h2>
        <ul class="recent" id="home-recent">${recentHtml(st.recent || [])}</ul>
      </section>


      ${st.api_key ? "" : `<p class="muted small">A tradução pelo seu ChatGPT e a sincronização funcionam sem chave. Para transcrever ou traduzir pela API, <a href="#/configuracoes">cadastre a chave da OpenAI</a>.</p>`}
    </div>`;
  drawHomeFiles();
  bindHome();
}

function recentHtml(list) {
  if (!list.length) return `<li class="muted small">As legendas que você abrir aparecem aqui.</li>`;
  const cname = (id) => (S.projects || []).find((p) => p.id === id)?.name;
  return list.map((r) => `<li>
      <button class="rec" data-h="recent" data-srt="${esc(r.srt)}" data-video="${esc(r.video)}" data-client="${r.client_id || ""}">
        <b>${esc(r.name)}</b>
        <span class="muted small">${r.video && r.srt ? "com vídeo · " : ""}${cname(r.client_id) ? esc(cname(r.client_id)) + " · " : ""}${esc(r.folder)}</span>
        <span class="muted small tnum">${esc(fmtDate(r.opened_at))}</span>
      </button>
      <button class="btn link small" data-h="forget" data-id="${r.id}" aria-label="Tirar da lista">×</button></li>`).join("");
}

function drawHomeFiles() {
  const el = document.getElementById("home-files");
  if (!el) return;
  const row = (kind, label, path) => path ? `<li><span class="kind">${label}</span><div class="name"><strong>${esc(path.split(/[\\/]/).pop())}</strong><div class="muted small">${esc(path.replace(/[\\/][^\\/]*$/, ""))}</div></div>
      <button class="btn link" data-h="clear" data-k="${kind}">Remover</button></li>` : "";
  el.innerHTML = row("srt", "Legenda", HOME.srt) + row("video", "Vídeo", HOME.video) + row("text", "Texto", HOME.text)
    + (HOME.uploading ? `<li class="muted small">Copiando arquivo arrastado…</li>` : "");
  const btn = document.getElementById("home-open");
  btn.disabled = HOME.uploading > 0 || !(HOME.srt || HOME.video);
  btn.textContent = HOME.text ? "Abrir e sincronizar o texto" : HOME.srt ? "Abrir no editor" : HOME.video ? "Abrir o vídeo (legenda nova)" : "Abrir no editor";
  document.getElementById("home-hint").textContent = HOME.text && !HOME.video ? "Para sincronizar o texto, escolha também o vídeo."
    : HOME.srt && !HOME.video ? "Dica: junte o vídeo para revisar no quadro exato e sincronizar pela fala." : "";
}

async function homeAdd(paths) {
  if (!paths.length) return;
  const { files } = await api("POST", "/api/inspect", { paths });
  for (const f of files) {
    if (!f.exists) { toast(`Arquivo não encontrado: ${f.path}`, true); continue; }
    if (f.kind === "subtitle") { HOME.srt = f.path; HOME.text = ""; }
    else if (f.kind === "media") HOME.video = f.path;
    else if (f.kind === "text") { HOME.text = f.path; HOME.srt = ""; }
    else toast(`Tipo de arquivo não suportado: ${f.name}`, true);
  }
  // escolheu só o vídeo: procura a legenda com o mesmo nome na pasta
  if (HOME.video && !HOME.srt && !HOME.text) {
    const stem = HOME.video.replace(/\.[^.\\/]+$/, "");
    const guesses = ["", "_sub_pt", "_sub_spa", ".pt-BR", ".es-419", ".pt", ".es"].map((x) => `${stem}${x}.srt`);
    try {
      const { files: g } = await api("POST", "/api/inspect", { paths: guesses });
      const hit = g.find((x) => x.exists);
      if (hit) { HOME.srt = hit.path; toast(`Legenda encontrada junto do vídeo: ${hit.name}`); }
    } catch {}
  }
  drawHomeFiles();
}

function homeUpload(file) {
  HOME.uploading++; drawHomeFiles();
  const xhr = new XMLHttpRequest();
  xhr.open("POST", `/api/upload?name=${encodeURIComponent(file.name)}`);
  xhr.setRequestHeader("X-Token", TOKEN);
  xhr.onload = async () => {
    HOME.uploading--;
    let data = {}; try { data = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status !== 200) { toast(data.error || "Falha ao receber o arquivo.", true); drawHomeFiles(); return; }
    try { await homeAdd([data.path]); } catch (e) { toast(e.message, true); }
  };
  xhr.onerror = () => { HOME.uploading--; toast("Falha ao receber o arquivo.", true); drawHomeFiles(); };
  xhr.send(file);
}

async function homeOpen(srt, video, clientId, text = "") {
  const o = await api("POST", "/api/editor/open", { srt, video, client_id: clientId ? Number(clientId) : null });
  location.hash = `#/editor/${o.sid}`;
  if (text) PENDING_SCRIPT = text;
}
let PENDING_SCRIPT = "";

function bindHome() {
  const drop = document.getElementById("home-drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => {
    const files = [...(e.dataTransfer?.files || [])];
    const big = files.find((f) => f.size > 2e9);
    if (big) toast(`${big.name} é grande: copiar demora. É mais rápido usar “Escolher vídeo”.`);
    files.forEach(homeUpload);
  });
  document.getElementById("home-client").addEventListener("change", (e) => setPref("cnt.cliente", e.target.value));
  main.onclick = async (e) => {
    const b = e.target.closest("[data-h]");
    if (!b) return;
    const a = b.dataset.h;
    try {
      if (a === "pick-srt") await homeAdd(await pickFiles("subtitle", false));
      if (a === "pick-video") await homeAdd(await pickFiles("media", false));
      if (a === "pick-text") await homeAdd(await pickFiles("text", false));
      if (a === "clear") { HOME[b.dataset.k] = ""; drawHomeFiles(); }
      if (a === "open") {
        if (HOME.text && !HOME.video) { toast("Para sincronizar o texto, escolha também o vídeo.", true); return; }
        const client = document.getElementById("home-client").value;
        setPref("cnt.cliente", client);
        const { srt, video, text } = HOME;
        await homeOpen(text ? "" : srt, video, client, text);
        Object.assign(HOME, { srt: "", video: "", text: "" });
      }
      if (a === "recent") await homeOpen(b.dataset.srt, b.dataset.video, b.dataset.client || homeClient());
      if (a === "forget") {
        const r = await api("DELETE", `/api/recent/${b.dataset.id}`);
        document.getElementById("home-recent").innerHTML = recentHtml(r.recent);
      }
    } catch (err) { toast(err.message, true); }
  };
}
