/* CNT Legendas — projetos (filmes e séries): tela inicial, novo projeto, projeto, episódio. */
"use strict";

const STATUS_TXT = { novo: "Novo", andamento: "Em andamento", finalizado: "Finalizado" };
const pill = (st) => `<span class="pill st-${esc(st)}">${esc(STATUS_TXT[st] || st)}</span>`;

function fmtHM(sec) {
  sec = Math.round(sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  if (!sec) return "—";
  return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}
function fmtHMS(sec) {
  sec = Math.round(sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const n0 = (v) => (v || v === 0 ? nf0.format(v) : "—");
function when(s) { return s ? fmtDate(s) : "—"; }
function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}
function todayLong() {
  const t = new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/* ------------------------------------------------------------ primeira vez */

async function renderWelcome() {
  await loadState();
  const sug = (S.state.home_dir ? S.state.home_dir + "\\Documents\\CNT Legendas\\Projetos" : "");
  main.innerHTML = `
    <section class="hero">
      <span class="eyebrow">Bem-vinda</span>
      <h1>Onde ficam os seus projetos?</h1>
      <p class="muted">Escolha uma pasta. Cada filme ou série que você criar aqui vira uma pasta dentro dela, com as temporadas e os episódios organizados.</p>
    </section>
    <section class="panel stack" style="max-width:780px">
      <label class="field"><span>Pasta dos projetos</span>
        <div class="row" style="flex-wrap:nowrap"><input type="text" id="w-root" class="mono" value="${esc(S.state.projects_root || sug)}" placeholder="C:\\Users\\voce\\Traducoes">
        <button class="btn" data-w="pick">${ic("open")} Escolher</button></div></label>
      <p class="muted small">Exemplo: com <span class="mono">C:\\Users\\mila\\traducoes</span>, um filme “Resgate” fica em <span class="mono">C:\\Users\\mila\\traducoes\\Resgate</span> e uma série em <span class="mono">…\\traducoes\\Série\\temporada-1\\ep-1</span>.</p>
      <div><button class="btn primary big-inline" data-w="save">${ic("check")} Usar esta pasta</button></div>
    </section>`;
  main.onclick = async (e) => {
    const b = e.target.closest("[data-w]");
    if (!b) return;
    try {
      if (b.dataset.w === "pick") {
        const { paths } = await api("POST", "/api/dialog", { kind: "folder", title: "Pasta dos projetos" });
        if (paths[0]) document.getElementById("w-root").value = paths[0];
      }
      if (b.dataset.w === "save") {
        await api("POST", "/api/obras/root", { path: document.getElementById("w-root").value.trim() });
        toast("Pronto! Os projetos vão ficar nesta pasta.");
        location.hash = "#/inicio";
      }
    } catch (err) { toast(err.message, true); }
  };
}

/* ------------------------------------------------------------ tela inicial */

let START_FILTER = { status: "", q: "" };

async function renderStart() {
  await loadState();
  if (!S.state.projects_root) { location.hash = "#/bemvindo"; return; }
  const data = await api("GET", "/api/obras");
  const who = (S.state.settings.translator_name || "").split(" ")[0];
  const rec = data.recent;
  const all = data.obras;
  const cnt = (st) => all.filter((o) => o.status === st).length;
  main.innerHTML = `
    <section class="hero">
      <div><span class="eyebrow">CNT Legendas</span>
        <h1>${greeting()}${who ? `, ${esc(who)}` : ""}</h1>
        <p class="muted">${todayLong()}</p></div>
      <div class="hero-side">
        <span class="label">Pasta dos projetos</span>
        <span class="mono small path" title="${esc(data.root)}">${esc(data.root)}</span>
        <div class="row" style="gap:6px"><button class="btn sm" data-s="openroot">${ic("open")} Abrir pasta</button><a class="btn sm ghost" href="#/bemvindo">Trocar</a></div>
      </div>
    </section>

    <section class="action-cards">
      <button class="acard" data-s="new">
        <span class="chip c-accent">${ic("plus")}</span>
        <b>Novo projeto</b><span class="muted small">Filme ou série, com a pasta organizada</span></button>
      <button class="acard" data-s="open">
        <span class="chip c-info">${ic("open")}</span>
        <b>Abrir</b><span class="muted small">Reabrir um projeto pela pasta</span></button>
      <button class="acard ${rec ? "" : "off"}" data-s="recent" ${rec ? "" : "disabled"}>
        <span class="chip c-violet">${ic("play")}</span>
        <b>${rec ? "Continuar" : "Mais recente"}</b>
        <span class="muted small">${rec ? `${esc(rec.name)}${rec.kind === "serie" ? ` · ${esc(rec.label)}` : ""}` : "Nenhum projeto ainda"}</span>
        ${rec ? `<span class="label">${esc(when(rec.updated_at))}</span>` : ""}</button>
    </section>

    <section class="kpis">
      ${kpi("Em andamento", cnt("andamento"), "projetos", "c-accent", "clock")}
      ${kpi("Novos", cnt("novo"), "ainda não começados", "c-info", "plus")}
      ${kpi("Finalizados", cnt("finalizado"), "entregues", "c-ok", "check")}
      ${kpi("Legendas", n0(all.reduce((a, o) => a + (o.legendas || 0), 0)), "em todos os projetos", "c-violet", "text")}
    </section>

    <section class="panel">
      <div class="row" style="justify-content:space-between;margin-bottom:12px">
        <h2>Projetos recentes</h2>
        <div class="row" style="gap:8px">
          <a class="btn sm ghost" href="#/projetos">Ver todos os projetos ${ic("right")}</a>
          <div class="seg" role="tablist" id="st-filter">
            ${[["", "Todos", all.length], ["novo", "Novos", cnt("novo")], ["andamento", "Em andamento", cnt("andamento")], ["finalizado", "Finalizados", cnt("finalizado")]]
              .map(([k, t, n]) => `<button role="tab" data-f="${k}" aria-selected="${START_FILTER.status === k}">${t} <span class="mono">${n}</span></button>`).join("")}
          </div>
          <label class="search">${ic("search")}<input type="search" id="st-q" placeholder="Procurar projeto ou cliente" value="${esc(START_FILTER.q)}"></label>
        </div>
      </div>
      <div class="table-wrap"><table class="table report" id="st-table"></table></div>
    </section>`;

  const draw = () => {
    const q = START_FILTER.q.toLowerCase();
    const rows = all.filter((o) => (!START_FILTER.status || o.status === START_FILTER.status)
      && (!q || `${o.name} ${o.client_name}`.toLowerCase().includes(q))).slice(0, 8);
    document.getElementById("st-table").innerHTML = `
      <thead><tr><th>Projeto</th><th>Tipo</th><th>Cliente</th><th>Status</th><th class="num">Episódios</th><th class="num">Legendas</th><th class="num">Palavras</th><th class="num">Vídeo</th><th class="num">Tempo</th><th>Atualizado</th></tr></thead>
      <tbody>${rows.length ? rows.map((o) => `<tr class="click" data-href="#/obra/${o.id}">
        <td><div class="pname">${ic(o.kind === "serie" ? "tv" : "film")}<div><strong>${esc(o.name)}</strong>${o.exists ? "" : `<div class="small" style="color:var(--err)">pasta não encontrada</div>`}</div></div></td>
        <td>${o.kind === "serie" ? "Série" : "Filme"}</td>
        <td>${esc(o.client_name || "—")}</td>
        <td>${pill(o.status)}</td>
        <td class="num mono">${o.kind === "serie" ? `${o.n_fin}/${o.n_itens}` : "—"}</td>
        <td class="num mono">${n0(o.legendas)}</td>
        <td class="num mono">${n0(o.palavras)}</td>
        <td class="num mono">${o.duracao_video_s ? fmtHMS(o.duracao_video_s) : "—"}</td>
        <td class="num mono">${fmtHM(o.seconds)}</td>
        <td class="mono small">${esc(when(o.updated_at))}</td></tr>`).join("")
        : `<tr><td colspan="10" class="muted" style="padding:24px">${all.length ? "Nenhum projeto com esse filtro." : "Nenhum projeto ainda. Clique em <b>Novo projeto</b> para começar."}</td></tr>`}</tbody>`;
    document.querySelectorAll("#st-table tr[data-href]").forEach((tr) => tr.addEventListener("click", () => (location.hash = tr.dataset.href)));
  };
  draw();
  document.getElementById("st-q").addEventListener("input", (e) => { START_FILTER.q = e.target.value; draw(); });
  main.onclick = async (e) => {
    const f = e.target.closest("[data-f]");
    if (f) {
      START_FILTER.status = f.dataset.f;
      document.querySelectorAll("#st-filter button").forEach((x) => x.setAttribute("aria-selected", String(x === f)));
      draw(); return;
    }
    const b = e.target.closest("[data-s]");
    if (!b) return;
    try {
      if (b.dataset.s === "new") location.hash = "#/obra/nova";
      if (b.dataset.s === "open") await openProjectFolder();
      if (b.dataset.s === "recent" && rec) await openItem(rec.item_id);
      if (b.dataset.s === "openroot") await api("POST", "/api/open", { path: data.root });
    } catch (err) { toast(err.message, true); }
  };
}

function kpi(label, value, sub, color, icon) {
  return `<div class="kpi"><span class="chip ${color}">${ic(icon)}</span><span class="label">${esc(label)}</span>
    <b class="kv">${value}</b><span class="muted small">${esc(sub)}</span></div>`;
}

async function openProjectFolder() {
  const { paths } = await api("POST", "/api/dialog", { kind: "folder", title: "Abrir projeto (pasta)", initial: S.state.projects_root });
  if (!paths[0]) return;
  const r = await api("POST", "/api/obras/open", { path: paths[0] });
  toast(`Projeto “${r.obra.name}” aberto.`);
  location.hash = `#/obra/${r.obra.id}`;
}

async function openItem(itemId) {
  const o = await api("POST", `/api/itens/${itemId}/open`);
  location.hash = `#/editor/${o.sid}`;
}

/* ------------------------------------------------------------ novo projeto */

async function renderNewProject() {
  await Promise.all([loadState(), loadProjects()]);
  if (!S.state.projects_root) { location.hash = "#/bemvindo"; return; }
  const W = { kind: "", name: "", client_id: getPref("cnt.cliente", ""), season: 1, episodes: "1", title: "",
    source_lang: "pt-BR", target_lang: "es-419", video: "", srt: "", nameOk: false };
  main.innerHTML = `
    <div class="page-head"><div><p class="label"><a href="#/inicio">Início</a> / Novo projeto</p><h1 style="margin-top:6px">Novo projeto</h1></div></div>
    <section class="panel">
      <span class="label">1 · O que é?</span>
      <div class="kind-cards" style="margin-top:12px">
        <button class="kcard k-film" data-k="filme">${ic("film")}<b>Filme</b><span>Um título só. A pasta guarda o vídeo e as legendas.</span></button>
        <button class="kcard k-serie" data-k="serie">${ic("tv")}<b>Série</b><span>Temporadas e episódios, em qualquer ordem.</span></button>
      </div>
    </section>
    <section class="panel" id="np-rest" hidden>
      <span class="label">2 · Nome da pasta</span>
      <div class="grid-2" style="margin-top:12px">
        <label class="field" style="grid-column:1/-1"><span>Nome</span>
          <input type="text" id="np-name" maxlength="120" placeholder="Ex.: Resgate no Oeste" autocomplete="off"></label>
      </div>
      <div class="pathbox mono" id="np-path"></div>
      <p class="small" id="np-err"></p>
      <div id="np-serie" hidden style="margin-top:18px">
        <span class="label">3 · Temporada e episódios</span>
        <div class="grid-3" style="margin-top:12px">
          <label class="field"><span>Temporada</span><input type="number" id="np-season" min="0" value="1"></label>
          <label class="field"><span>Episódio(s)</span><input type="text" id="np-eps" value="1" placeholder="1   ou   40-45   ou   1, 3, 7"></label>
          <label class="field"><span>Título do episódio <em class="muted small">(opcional)</em></span><input type="text" id="np-title"></label>
        </div>
        <p class="muted small" style="margin-top:6px">Pode começar em qualquer temporada e episódio (a temporada 2 pode começar no 40). Depois dá para acrescentar mais.</p>
      </div>
      <div class="grid-3" style="margin-top:18px">
        <label class="field"><span>Cliente</span><select id="np-client"><option value="">Nenhum</option>${(S.projects || []).map((c) => `<option value="${c.id}" ${String(c.id) === W.client_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
        <label class="field"><span>Idioma de origem</span><select id="np-src">${langOptions(W.source_lang)}</select></label>
        <label class="field"><span>Traduzir para</span><select id="np-dst">${langOptions(W.target_lang)}</select></label>
      </div>
      <div id="np-files" style="margin-top:18px">
        <span class="label">Arquivos <em class="muted">(opcional — dá para pôr depois)</em></span>
        <p class="muted small" style="margin:6px 0 10px">São <b>copiados</b> para a pasta do projeto; os originais ficam onde estão.</p>
        <div class="row">
          <button class="btn" data-a="video">${ic("film")} Escolher vídeo</button><span class="mono small" id="np-video">—</span>
        </div>
        <div class="row" style="margin-top:8px">
          <button class="btn" data-a="srt">${ic("file")} Escolher legenda</button><span class="mono small" id="np-srt">—</span>
        </div>
      </div>
      <div class="row" style="margin-top:22px;justify-content:flex-end">
        <a class="btn" href="#/inicio">Cancelar</a>
        <button class="btn primary" data-a="create" id="np-create" disabled>${ic("check")} Criar projeto</button>
      </div>
    </section>`;

  const $ = (id) => document.getElementById(id);
  let timer;
  const preview = () => {
    const root = S.state.projects_root.replace(/[\\/]+$/, "");
    const name = $("np-name").value;
    let p = `${root}\\${name || "…"}`;
    if (W.kind === "serie") {
      let eps = [];
      try { eps = parseEps($("np-eps").value); } catch {}
      const s = $("np-season").value || "?";
      const list = eps.length ? eps : ["?"];
      p = list.slice(0, 6).map((e) => `${root}\\${name || "…"}\\temporada-${s}\\ep-${e}`).join("\n") + (list.length > 6 ? `\n… e mais ${list.length - 6}` : "");
    }
    $("np-path").textContent = p;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!name) { W.nameOk = false; $("np-err").textContent = ""; upd(); return; }
      const r = await api("GET", `/api/obras/check?name=${encodeURIComponent(name)}`).catch(() => ({ problem: "" }));
      W.nameOk = !r.problem;
      $("np-err").innerHTML = r.problem ? `<span class="note err" style="display:block">${esc(r.problem)}</span>` : `<span style="color:var(--ok)">${ic("check")} Nome válido</span>`;
      upd();
    }, 180);
  };
  const upd = () => {
    let epsOk = true;
    if (W.kind === "serie") { try { epsOk = parseEps($("np-eps").value).length > 0 && $("np-season").value !== ""; } catch { epsOk = false; } }
    $("np-create").disabled = !(W.kind && W.nameOk && epsOk);
    const single = W.kind === "filme" || (epsOk && parseEpsSafe($("np-eps").value).length === 1);
    $("np-files").hidden = !single;
    $("np-title").disabled = !single;
  };
  // só deixa digitar o que o Windows aceita em nome de pasta
  $("np-name").addEventListener("beforeinput", (e) => { if (e.data && /[<>:"/\\|?*\u0000-\u001f]/.test(e.data)) { e.preventDefault(); toast("O Windows não aceita < > : \" / \\ | ? * em nomes de pasta.", true); } });
  $("np-name").addEventListener("input", (e) => {
    const clean = e.target.value.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "");
    if (clean !== e.target.value) e.target.value = clean;
    preview();
  });
  ["np-season", "np-eps"].forEach((id) => $(id).addEventListener("input", () => { preview(); upd(); }));

  main.onclick = async (e) => {
    const k = e.target.closest("[data-k]");
    if (k) {
      W.kind = k.dataset.k;
      document.querySelectorAll(".kcard").forEach((x) => x.classList.toggle("on", x === k));
      $("np-rest").hidden = false; $("np-serie").hidden = W.kind !== "serie";
      $("np-name").focus(); preview(); upd(); return;
    }
    const b = e.target.closest("[data-a]");
    if (!b) return;
    try {
      if (b.dataset.a === "video" || b.dataset.a === "srt") {
        const { paths } = await api("POST", "/api/dialog", { kind: b.dataset.a === "video" ? "media" : "subtitle" });
        if (paths[0]) { W[b.dataset.a] = paths[0]; $(`np-${b.dataset.a}`).textContent = paths[0]; }
      }
      if (b.dataset.a === "create") {
        b.disabled = true;
        const body = { kind: W.kind, name: $("np-name").value, client_id: $("np-client").value ? Number($("np-client").value) : null,
          source_lang: $("np-src").value, target_lang: $("np-dst").value };
        if (W.kind === "serie") Object.assign(body, { season: Number($("np-season").value), episodes: $("np-eps").value, title: $("np-title").value });
        setPref("cnt.cliente", $("np-client").value);
        const o = await api("POST", "/api/obras", body);
        const files = [W.video, W.srt].filter(Boolean);
        if (files.length && o.items.length === 1) await copyFiles(o.items[0].id, files);
        toast(`Projeto “${o.name}” criado.`);
        location.hash = `#/obra/${o.id}`;
      }
    } catch (err) { toast(err.message, true); b.disabled = false; }
  };
}

function parseEps(text) {
  const out = [];
  for (const part of String(text).split(/[,;\s]+/).filter(Boolean)) {
    const m = part.match(/^(\d+)-(\d+)$/);
    if (m) { let a = +m[1], b = +m[2]; if (b < a) [a, b] = [b, a]; if (b - a > 200) throw new Error("grande"); for (let i = a; i <= b; i++) out.push(i); }
    else if (/^\d+$/.test(part)) out.push(+part);
    else throw new Error("inválido");
  }
  return [...new Set(out)];
}
function parseEpsSafe(t) { try { return parseEps(t); } catch { return []; } }

/* copia arquivos para a pasta do episódio, com barra de progresso */
async function copyFiles(itemId, paths) {
  let c = await api("POST", `/api/itens/${itemId}/files`, { paths });
  if (c.status === "pronto") return c;
  const m = modal("Copiando arquivos para a pasta do projeto", `<p class="muted small">Os originais continuam onde estão.</p><div class="bar"><i id="cp-bar" style="width:0%"></i></div><p class="mono small" id="cp-txt"></p>`, "");
  m.ov.dataset.busy = "1";
  while (c.status === "copiando") {
    await new Promise((r) => setTimeout(r, 400));
    c = await api("GET", `/api/copies/${c.id}`);
    m.$("#cp-bar").style.width = `${Math.round((c.done / c.total) * 100)}%`;
    m.$("#cp-txt").textContent = `${fmtSize(c.done)} de ${fmtSize(c.total)}`;
  }
  delete m.ov.dataset.busy; m.close();
  if (c.status === "erro") throw new Error(c.error);
  return c;
}

/* ------------------------------------------------------------ projeto */

let OBRA_TAB = "eps";

async function renderObra(id) {
  await Promise.all([loadState(), loadProjects()]);
  const o = await api("GET", `/api/obras/${id}`);
  const m = o.metrics || {};
  const serie = o.kind === "serie";
  setCrumb(`Projetos <span class="muted">/ ${esc(o.name)}</span>`);
  main.innerHTML = `
    <section class="hero">
      <div><span class="eyebrow">${serie ? "Série" : "Filme"}</span>
        <h1>${esc(o.name)}</h1>
        <p class="muted">${o.client_name ? `${esc(o.client_name)} · ` : ""}${esc(shortLang(o.source_lang))} → ${esc(shortLang(o.target_lang))} · criado ${esc(when(o.created_at))}${o.finished_at && o.status === "finalizado" ? ` · finalizado ${esc(when(o.finished_at))}` : ""}</p>
        <p class="mono small path" style="margin-top:8px">${esc(o.folder)}${o.exists ? "" : ` <span style="color:var(--err)">(pasta não encontrada)</span>`}</p></div>
      <div class="hero-side">
        <span class="label">Status</span>
        <div class="seg" id="ob-status">${["novo", "andamento", "finalizado"].map((s) => `<button data-st="${s}" aria-selected="${o.status === s}">${STATUS_TXT[s]}</button>`).join("")}</div>
        <div class="row" style="gap:6px">
          <button class="btn sm" data-o="folder">${ic("open")} Abrir pasta</button>
          <select id="ob-client" class="sm" aria-label="Cliente"><option value="">Sem cliente</option>${(S.projects || []).map((c) => `<option value="${c.id}" ${c.id === o.client_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
        </div>
      </div>
    </section>

    <section class="kpis">
      ${kpi("Legendas", n0(m.legendas), `${n0(m.linhas)} linhas`, "c-accent", "text")}
      ${kpi("Palavras", n0(m.palavras), `${n0(m.caracteres)} caracteres`, "c-info", "words")}
      ${kpi("Vídeo", m.duracao_video_s ? fmtHMS(m.duracao_video_s) : "—", `${serie ? `${o.items.length} episódio(s)` : "duração"}`, "c-violet", "film")}
      ${kpi("Tempo trabalhado", fmtHM(o.seconds), o.productivity.legendas_por_hora ? `${n0(o.productivity.legendas_por_hora)} legendas/hora` : "no editor", "c-ok", "clock")}
    </section>

    <div class="tabs big" role="tablist" id="ob-tabs">
      <button role="tab" data-t="eps" aria-selected="${OBRA_TAB === "eps"}">${serie ? "Episódios" : "Arquivos"}</button>
      <button role="tab" data-t="met" aria-selected="${OBRA_TAB === "met"}">Métricas</button>
      <button role="tab" data-t="hist" aria-selected="${OBRA_TAB === "hist"}">Histórico</button>
    </div>
    <div id="ob-body"></div>`;

  const body = document.getElementById("ob-body");
  const drawEps = () => {
    if (!serie) {
      const it = o.items[0];
      body.innerHTML = `<section class="panel">${itemCard(it, true)}</section>`;
      return;
    }
    body.innerHTML = `
      <section class="panel addeps">
        <span class="label">Adicionar episódios</span>
        <div class="row" style="margin-top:10px;align-items:end">
          <label class="field" style="width:120px"><span>Temporada</span><input type="number" id="ae-s" min="0" value="${o.seasons.length ? o.seasons[o.seasons.length - 1].season : 1}"></label>
          <label class="field" style="width:220px"><span>Episódio(s)</span><input type="text" id="ae-e" placeholder="7  ou  40-45"></label>
          <label class="field" style="flex:1;min-width:180px"><span>Título <em class="muted small">(se for um só)</em></span><input type="text" id="ae-t"></label>
          <button class="btn primary" data-o="addeps">${ic("plus")} Adicionar</button>
        </div>
        <p class="muted small" id="ae-hint" style="margin-top:6px"></p>
      </section>
      ${o.seasons.map((s) => `
        <section class="panel season">
          <div class="row" style="justify-content:space-between"><h2>Temporada ${s.season}</h2><span class="label">${s.items.length} episódio(s) · ${s.items.filter((i) => i.status === "finalizado").length} finalizado(s)</span></div>
          <div class="table-wrap"><table class="table report eps">
            <thead><tr><th>Ep.</th><th>Título</th><th>Status</th><th>Arquivos</th><th class="num">Legendas</th><th class="num">Palavras</th><th class="num">Tempo</th><th>Atualizado</th><th></th></tr></thead>
            <tbody>${s.items.map((it) => `<tr data-i="${it.id}">
              <td class="mono"><b>${it.episode}</b></td>
              <td><input type="text" class="inline" data-title="${it.id}" value="${esc(it.title)}" placeholder="—" aria-label="Título do episódio ${it.episode}"></td>
              <td><select class="inline st-sel st-${it.status}" data-ist="${it.id}">${["novo", "andamento", "finalizado"].map((x) => `<option value="${x}" ${x === it.status ? "selected" : ""}>${STATUS_TXT[x]}</option>`).join("")}</select></td>
              <td class="small">${fileBadges(it)}</td>
              <td class="num mono">${n0(it.metrics?.legendas)}</td>
              <td class="num mono">${n0(it.metrics?.palavras)}</td>
              <td class="num mono">${fmtHM(it.seconds)}</td>
              <td class="mono small">${esc(when(it.updated_at))}</td>
              <td class="acts">
                <button class="btn sm primary" data-o="edit" data-i="${it.id}" title="Abrir no editor">${ic("editor")} Abrir</button>
                <button class="btn sm" data-o="files" data-i="${it.id}" title="Adicionar vídeo/legenda">${ic("file")}</button>
                <a class="btn sm" href="#/item/${it.id}" title="Métricas do episódio">${ic("chart")}</a>
                <button class="btn sm" data-o="ifolder" data-path="${esc(it.folder)}" title="Abrir pasta do episódio">${ic("open")}</button>
              </td></tr>`).join("")}</tbody></table></div>
        </section>`).join("") || `<section class="panel"><p class="muted">Nenhum episódio ainda.</p></section>`}`;
    const hint = () => {
      const s = document.getElementById("ae-s").value;
      const nx = o.next_episode[String(s)] || 1;
      document.getElementById("ae-hint").textContent = `Próximo da temporada ${s}: ${nx}. Pode ser qualquer número (ex.: a temporada começar no 40).`;
      document.getElementById("ae-e").placeholder = String(nx);
    };
    hint();
    document.getElementById("ae-s").addEventListener("input", hint);
  };
  const drawMet = () => { body.innerHTML = metricsPanels(m, o.productivity, o.seconds) + (serie ? epsMetricsTable(o.items) : ""); };
  const drawHist = async () => {
    body.innerHTML = `<section class="panel"><p class="muted">Carregando…</p></section>`;
    const r = await api("GET", `/api/obras/${id}/report`);
    body.innerHTML = `<div class="split2">
      <section class="panel"><h2>Histórico</h2><ul class="timeline">${r.events.map((e) => `<li><span class="mono small muted">${esc(when(e.at))}</span><b>${esc(EVT[e.tipo] || e.tipo)}</b><span>${esc(e.detalhe)}</span></li>`).join("") || `<li class="muted">Nada ainda.</li>`}</ul></section>
      <section class="panel"><h2>Tempo por dia</h2>${dayBars(r.days)}</section></div>`;
  };
  const drawTab = () => (OBRA_TAB === "met" ? drawMet() : OBRA_TAB === "hist" ? drawHist() : drawEps());
  drawTab();

  document.getElementById("ob-client").addEventListener("change", async (e) => {
    try { await api("PUT", `/api/obras/${id}`, { client_id: e.target.value ? Number(e.target.value) : null }); toast("Cliente do projeto atualizado."); }
    catch (err) { toast(err.message, true); }
  });
  main.onchange = async (e) => {
    const t = e.target;
    try {
      if (t.dataset.ist) { await api("PUT", `/api/itens/${t.dataset.ist}`, { status: t.value }); toast("Status do episódio atualizado."); router(); }
      if (t.dataset.title) { await api("PUT", `/api/itens/${t.dataset.title}`, { title: t.value }); toast("Título salvo."); }
    } catch (err) { toast(err.message, true); }
  };
  main.onclick = async (e) => {
    const tab = e.target.closest("[data-t]");
    if (tab) { OBRA_TAB = tab.dataset.t; document.querySelectorAll("#ob-tabs [data-t]").forEach((x) => x.setAttribute("aria-selected", String(x === tab))); drawTab(); return; }
    const st = e.target.closest("[data-st]");
    if (st) {
      if (st.dataset.st === o.status) return;
      try { await api("PUT", `/api/obras/${id}`, { status: st.dataset.st }); toast(o.status === "finalizado" ? "Projeto reaberto." : `Projeto: ${STATUS_TXT[st.dataset.st]}.`); router(); }
      catch (err) { toast(err.message, true); }
      return;
    }
    const b = e.target.closest("[data-o]");
    if (!b) return;
    try {
      const a = b.dataset.o;
      if (a === "folder") await api("POST", "/api/open", { path: o.folder });
      if (a === "ifolder") await api("POST", "/api/open", { path: b.dataset.path });
      if (a === "edit") await openItem(Number(b.dataset.i));
      if (a === "files") {
        const { paths } = await api("POST", "/api/dialog", { kind: "any", multiple: true, title: "Vídeo e/ou legenda deste episódio" });
        if (!paths.length) return;
        await copyFiles(Number(b.dataset.i), paths);
        toast("Arquivos copiados para a pasta."); router();
      }
      if (a === "addeps") {
        const r = await api("POST", `/api/obras/${id}/episodes`, { season: document.getElementById("ae-s").value,
          episodes: document.getElementById("ae-e").value || document.getElementById("ae-e").placeholder, title: document.getElementById("ae-t").value });
        toast(`Episódios adicionados. Pastas criadas em ${r.name}.`); router();
      }
      if (a === "remove") {
        if (!confirm("Tirar este projeto da lista? A pasta e os arquivos continuam no computador; dá para reabrir pelo botão Abrir.")) return;
        await api("DELETE", `/api/obras/${id}`); location.hash = "#/inicio";
      }
    } catch (err) { toast(err.message, true); }
  };
}

function fileBadges(it) {
  const v = it.video ? it.video.split(/[\\/]/).pop() : "", s = it.srt ? it.srt.split(/[\\/]/).pop() : "";
  return `<span class="fb ${v ? "on" : ""}" title="${esc(v || "sem vídeo")}">${ic("film")}${v ? "vídeo" : "sem vídeo"}</span>
    <span class="fb ${s ? "on" : ""}" title="${esc(s || "sem legenda")}">${ic("file")}${s ? `${it.files.srts.length} srt` : "sem legenda"}</span>`;
}

function itemCard(it, film) {
  return `<div class="item-card">
    <div class="ic-files">
      <div><span class="label">Vídeo</span><p class="mono small">${esc(it.video || "—")}</p></div>
      <div><span class="label">Legenda em uso</span><p class="mono small">${esc(it.srt || "—")}</p></div>
      ${it.files.srts.length > 1 ? `<div><span class="label">Outras legendas na pasta</span><p class="mono small">${it.files.srts.filter((x) => x !== it.srt).map((x) => esc(x.split(/[\\/]/).pop())).join(" · ")}</p></div>` : ""}
    </div>
    <div class="row">
      <button class="btn primary" data-o="edit" data-i="${it.id}">${ic("editor")} Abrir no editor</button>
      <button class="btn" data-o="files" data-i="${it.id}">${ic("file")} Adicionar vídeo/legenda</button>
      <a class="btn" href="#/item/${it.id}">${ic("chart")} Métricas${film ? " do filme" : ""}</a>
      <button class="btn ghost" data-o="remove">${ic("trash")} Tirar da lista</button>
    </div></div>`;
}

const EVT = { criado: "Projeto criado", episodios: "Episódios adicionados", status: "Status", status_item: "Status do episódio",
  arquivos: "Arquivos adicionados", entrega: "Entregue", traducao: "Traduzido", aberto: "Reaberto pela pasta", episodio_removido: "Episódio removido" };

/* ------------------------------------------------------------ métricas (blocos reutilizados) */

const MET_GROUPS = [
  ["Texto", [["legendas", "Legendas"], ["linhas", "Linhas"], ["palavras", "Palavras"], ["letras", "Letras"], ["caracteres", "Caracteres (com espaços)"],
    ["caracteres_sem_espaco", "Caracteres sem espaços"], ["frases", "Frases"], ["media_palavras_por_frase", "Palavras por frase (média)"]]],
  ["Tempo", [["duracao_video_s", "Duração do vídeo", "hms"], ["duracao_legendada_s", "Do primeiro ao último texto", "hms"], ["tempo_em_tela_s", "Tempo com legenda na tela", "hms"],
    ["legendas_por_minuto", "Legendas por minuto"], ["media_duracao_s", "Duração média da legenda (s)"], ["media_intervalo_s", "Intervalo médio (s)"]]],
  ["Leitura", [["media_cps", "CPS médio"], ["mediana_cps", "CPS mediano"], ["max_cps", "CPS máximo"], ["acima_do_cps", "Acima do CPS do perfil"], ["acima_do_cps_pct", "Acima do CPS (%)"],
    ["media_caracteres_por_legenda", "Caracteres por legenda (média)"], ["media_palavras_por_legenda", "Palavras por legenda (média)"]]],
  ["Formato", [["legendas_1_linha", "Legendas de 1 linha"], ["legendas_2_linhas", "Legendas de 2 linhas"], ["legendas_3_ou_mais_linhas", "3 linhas ou mais"],
    ["dialogos", "Diálogos (hífen)"], ["italico", "Com itálico"], ["posicao_alta", "No alto da tela ({\\an8})"], ["curtas", "Curtas demais"], ["longas", "Longas demais"]]],
  ["Revisão", [["apontamentos", "Apontamentos do Verificar"], ["erros", "Erros"], ["avisos", "Avisos"]]],
  ["Tradução", [["original_palavras", "Palavras do original"], ["original_caracteres", "Caracteres do original"], ["compressao_pct", "Tamanho da tradução / original (%)"]]],
];
const ISSUE_TXT = { cps: "Velocidade de leitura", caracteres: "Caracteres por linha", linhas: "Número de linhas", curta: "Curta", longa: "Longa", intervalo: "Intervalo",
  sobreposicao: "Sobreposição", interjeicao: "Interjeição", pontuacao_dupla: "Pontuação dupla", reticencias: "Reticências", travessao: "Hífen", repeticao: "Repetição",
  abertura: "¿ ¡", localizacao: "Texto de tela", dois_pontos: "Dois-pontos", numero: "Números", tempo_estimado: "Tempo estimado", vazia: "Vazia",
  tempo_invertido: "Tempo invertido", fora_de_ordem: "Fora de ordem", sem_traducao: "Sem tradução" };

function metVal(m, key, fmt) {
  const v = m[key];
  if (v == null || v === "") return "—";
  if (fmt === "hms") return v ? fmtHMS(v) : "—";
  return typeof v === "number" ? (Number.isInteger(v) ? n0(v) : nf1.format(v)) : esc(String(v));
}

function metricsPanels(m, prod, seconds) {
  if (!m || !m.legendas) return `<section class="panel"><p class="muted">Ainda não há métricas. Elas são registradas quando a legenda é aberta pelo projeto, salva, traduzida ou entregue.</p></section>`;
  const groups = MET_GROUPS.map(([title, rows]) => {
    const shown = rows.filter(([k]) => m[k] != null);
    if (!shown.length || (title === "Tradução" && !m.original_caracteres)) return "";
    return `<section class="panel mgroup"><span class="label">${esc(title)}</span><dl>${shown.map(([k, t, f]) => `<dt>${esc(t)}</dt><dd class="mono">${metVal(m, k, f)}</dd>`).join("")}</dl></section>`;
  }).join("");
  const tipos = Object.entries(m.apontamentos_por_tipo || {}).sort((a, b) => b[1] - a[1]);
  const maxT = Math.max(1, ...tipos.map(([, v]) => v));
  return `
    <section class="panel mgroup prod"><span class="label">Produtividade</span><dl>
      <dt>Tempo trabalhado no editor</dt><dd class="mono">${fmtHM(seconds)}</dd>
      <dt>Legendas por hora</dt><dd class="mono">${seconds ? n0(prod.legendas_por_hora) : "—"}</dd>
      <dt>Palavras por hora</dt><dd class="mono">${seconds ? n0(prod.palavras_por_hora) : "—"}</dd>
      <dt>Minutos de vídeo por hora</dt><dd class="mono">${prod.minutos_de_video_por_hora ? nf1.format(prod.minutos_de_video_por_hora) : "—"}</dd></dl></section>
    <div class="mgrid">${groups}</div>
    ${tipos.length ? `<section class="panel"><span class="label">Apontamentos por tipo</span><div class="hbars">${tipos.map(([k, v]) => `<div class="hb"><span>${esc(ISSUE_TXT[k] || k)}</span><i style="--w:${Math.round((v / maxT) * 100)}%"></i><b class="mono">${v}</b></div>`).join("")}</div></section>` : ""}`;
}

function epsMetricsTable(items) {
  return `<section class="panel"><h2>Por episódio</h2><div class="table-wrap"><table class="table report">
    <thead><tr><th>Episódio</th><th>Status</th><th class="num">Legendas</th><th class="num">Palavras</th><th class="num">Caracteres</th><th class="num">Vídeo</th><th class="num">CPS médio</th><th class="num">Acima CPS</th><th class="num">Apontam.</th><th class="num">Tempo</th></tr></thead>
    <tbody>${items.map((it) => { const m = it.metrics || {}; return `<tr class="click" data-href="#/item/${it.id}">
      <td><b>${esc(it.label)}</b>${it.title ? ` <span class="muted small">${esc(it.title)}</span>` : ""}</td><td>${pill(it.status)}</td>
      <td class="num mono">${n0(m.legendas)}</td><td class="num mono">${n0(m.palavras)}</td><td class="num mono">${n0(m.caracteres)}</td>
      <td class="num mono">${m.duracao_video_s ? fmtHMS(m.duracao_video_s) : "—"}</td><td class="num mono">${m.media_cps ? nf1.format(m.media_cps) : "—"}</td>
      <td class="num mono">${n0(m.acima_do_cps)}</td><td class="num mono">${n0(m.apontamentos)}</td><td class="num mono">${fmtHM(it.seconds)}</td></tr>`; }).join("")}</tbody></table></div></section>`;
}

function dayBars(days) {
  if (!days?.length) return `<p class="muted">Ainda sem tempo registrado. O tempo conta enquanto ela trabalha no editor.</p>`;
  const last = days.slice(-30), max = Math.max(1, ...last.map((d) => d.segundos));
  return `<div class="vbars">${last.map((d) => `<div class="vb" title="${esc(d.dia)}: ${fmtHM(d.segundos)}"><i style="--h:${Math.max(3, Math.round((d.segundos / max) * 100))}%"></i><span class="mono">${esc(d.dia.slice(8, 10))}/${esc(d.dia.slice(5, 7))}</span></div>`).join("")}</div>`;
}

/* ------------------------------------------------------------ episódio / filme */

async function renderItem(id) {
  const r = await api("GET", `/api/itens/${id}/report`);
  const it = r.item, m = r.metrics || {};
  setCrumb(`Projetos <span class="muted">/ ${esc(r.obra.name)}${r.obra.kind === "serie" ? ` / ${esc(it.label)}` : ""}</span>`);
  main.innerHTML = `
    <section class="hero">
      <div><span class="eyebrow">${r.obra.kind === "serie" ? `Temporada ${it.season} · Episódio ${it.episode}` : "Filme"}</span>
        <h1>${esc(r.obra.kind === "serie" ? (it.title || `${r.obra.name} — ${it.label}`) : r.obra.name)}</h1>
        <p class="muted"><a href="#/obra/${r.obra.id}">${esc(r.obra.name)}</a> · ${pill(it.status)} · métricas de ${esc(when(m.medido_em))}</p>
        <p class="mono small path" style="margin-top:8px">${esc(it.folder)}</p></div>
      <div class="hero-side"><button class="btn primary" data-x="edit">${ic("editor")} Abrir no editor</button>
        <button class="btn sm" data-x="folder">${ic("open")} Abrir pasta</button></div>
    </section>
    <section class="kpis">
      ${kpi("Legendas", n0(m.legendas), `${n0(m.linhas)} linhas`, "c-accent", "text")}
      ${kpi("Palavras", n0(m.palavras), `${n0(m.letras)} letras`, "c-info", "words")}
      ${kpi("Vídeo", m.duracao_video_s ? fmtHMS(m.duracao_video_s) : "—", `${n0(m.legendas_por_minuto)} legendas/min`, "c-violet", "film")}
      ${kpi("Tempo trabalhado", fmtHM(it.seconds), r.productivity.legendas_por_hora ? `${n0(r.productivity.legendas_por_hora)} legendas/hora` : "no editor", "c-ok", "clock")}
    </section>
    ${metricsPanels(m, r.productivity, it.seconds)}
    <div class="split2">
      <section class="panel"><h2>Evolução</h2><div class="table-wrap"><table class="table report">
        <thead><tr><th>Quando</th><th>O quê</th><th class="num">Legendas</th><th class="num">Palavras</th><th class="num">CPS médio</th><th class="num">Apontam.</th></tr></thead>
        <tbody>${r.history.slice().reverse().map((h) => `<tr><td class="mono small">${esc(when(h.at))}</td><td>${esc({ abrir: "Aberto", salvar: "Salvo", entrega: "Entregue", traducao: "Traduzido" }[h.origem] || h.origem)}</td>
          <td class="num mono">${n0(h.legendas)}</td><td class="num mono">${n0(h.palavras)}</td><td class="num mono">${h.media_cps ? nf1.format(h.media_cps) : "—"}</td><td class="num mono">${n0(h.apontamentos)}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Sem registros.</td></tr>`}</tbody></table></div></section>
      <section class="panel"><h2>Tempo por dia</h2>${dayBars(r.days)}</section>
    </div>`;
  main.onclick = async (e) => {
    const x = e.target.closest("[data-x]")?.dataset.x;
    try {
      if (x === "edit") await openItem(it.id);
      if (x === "folder") await api("POST", "/api/open", { path: it.folder });
    } catch (err) { toast(err.message, true); }
  };
}

/* ------------------------------------------------------------ todos os projetos (menu Projetos) */

let PL = { status: "", kind: "", client: "", sort: "updated", q: "", open: {} };

async function renderProjectsList() {
  await Promise.all([loadState(), loadProjects()]);
  if (!S.state.projects_root) { location.hash = "#/bemvindo"; return; }
  const data = await api("GET", "/api/obras");
  const all = data.obras;
  main.innerHTML = `
    <div class="page-head">
      <div><span class="eyebrow">Trabalho</span><h1 style="margin-top:6px">Projetos</h1>
        <p class="muted">Todos os filmes e séries, com os episódios. Clique na seta para ver os episódios sem sair da lista.</p></div>
      <div class="row"><button class="btn" data-l="open">${ic("open")} Abrir pela pasta</button><a class="btn primary" href="#/obra/nova">${ic("plus")} Novo projeto</a></div>
    </div>
    <section class="panel toolbar">
      <div class="seg" id="pl-status">${[["", "Todos"], ["novo", "Novos"], ["andamento", "Em andamento"], ["finalizado", "Finalizados"]]
        .map(([k, t]) => `<button data-st="${k}" aria-selected="${PL.status === k}">${t} <span class="mono">${k ? all.filter((o) => o.status === k).length : all.length}</span></button>`).join("")}</div>
      <div class="seg" id="pl-kind">${[["", "Filmes e séries"], ["filme", "Filmes"], ["serie", "Séries"]]
        .map(([k, t]) => `<button data-kind="${k}" aria-selected="${PL.kind === k}">${t}</button>`).join("")}</div>
      <select id="pl-client" aria-label="Cliente"><option value="">Todos os clientes</option>${(S.projects || []).map((c) => `<option value="${c.id}" ${String(c.id) === PL.client ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
      <select id="pl-sort" aria-label="Ordenar"><option value="updated">Mexidos por último</option><option value="created">Criados por último</option><option value="name">Nome (A–Z)</option><option value="subs">Mais legendas</option><option value="time">Mais tempo de trabalho</option></select>
      <label class="search">${ic("search")}<input type="search" id="pl-q" placeholder="Procurar" value="${esc(PL.q)}"></label>
    </section>
    <p class="muted small" id="pl-sum" style="margin:4px 4px 10px"></p>
    <div id="pl-list"></div>`;
  document.getElementById("pl-sort").value = PL.sort;

  const filtered = () => {
    const q = PL.q.toLowerCase();
    const rows = all.filter((o) => (!PL.status || o.status === PL.status) && (!PL.kind || o.kind === PL.kind)
      && (!PL.client || String(o.client_id) === PL.client) && (!q || `${o.name} ${o.client_name} ${o.folder}`.toLowerCase().includes(q)));
    const by = { updated: (a, b) => b.updated_at.localeCompare(a.updated_at), created: (a, b) => b.created_at.localeCompare(a.created_at),
      name: (a, b) => a.name.localeCompare(b.name, "pt-BR"), subs: (a, b) => (b.legendas || 0) - (a.legendas || 0), time: (a, b) => (b.seconds || 0) - (a.seconds || 0) };
    return rows.sort(by[PL.sort] || by.updated);
  };
  const draw = () => {
    const rows = filtered();
    document.getElementById("pl-sum").textContent = `${rows.length} projeto(s) · ${rows.reduce((a, o) => a + (o.n_itens || 0), 0)} episódio(s)/filme(s) · ${n0(rows.reduce((a, o) => a + (o.legendas || 0), 0))} legendas · ${fmtHM(rows.reduce((a, o) => a + (o.seconds || 0), 0))} de trabalho`;
    document.getElementById("pl-list").innerHTML = rows.length ? rows.map((o) => `
      <article class="prow ${PL.open[o.id] ? "open" : ""}" data-id="${o.id}">
        <div class="prow-head">
          <button class="btn icon ghost caret" data-l="toggle" aria-label="Mostrar episódios" aria-expanded="${!!PL.open[o.id]}">${ic("right")}</button>
          <span class="chip ${o.kind === "serie" ? "c-violet" : "c-info"}">${ic(o.kind === "serie" ? "tv" : "film")}</span>
          <div class="prow-name"><a href="#/obra/${o.id}"><b>${esc(o.name)}</b></a>
            <span class="muted small">${o.kind === "serie" ? "Série" : "Filme"}${o.client_name ? ` · ${esc(o.client_name)}` : ""} · criado ${esc(when(o.created_at))}${o.exists ? "" : ` · <span style="color:var(--err)">pasta não encontrada</span>`}</span></div>
          <div class="prow-stats">
            <span><span class="label">Episódios</span><b class="mono">${o.kind === "serie" ? `${o.n_fin}/${o.n_itens}` : "—"}</b></span>
            <span><span class="label">Legendas</span><b class="mono">${n0(o.legendas)}</b></span>
            <span><span class="label">Vídeo</span><b class="mono">${o.duracao_video_s ? fmtHMS(o.duracao_video_s) : "—"}</b></span>
            <span><span class="label">Tempo</span><b class="mono">${fmtHM(o.seconds)}</b></span>
            <span><span class="label">Atualizado</span><b class="mono small">${esc(when(o.updated_at))}</b></span>
          </div>
          <select class="st-sel st-${o.status}" data-ost="${o.id}" aria-label="Status">${["novo", "andamento", "finalizado"].map((x) => `<option value="${x}" ${x === o.status ? "selected" : ""}>${STATUS_TXT[x]}</option>`).join("")}</select>
          <div class="prow-acts">
            <a class="btn sm primary" href="#/obra/${o.id}">Abrir projeto</a>
            <button class="btn sm" data-l="folder" data-path="${esc(o.folder)}" title="Abrir a pasta no Windows">${ic("open")}</button>
            <button class="btn sm ghost" data-l="remove" title="Tirar da lista (a pasta fica)">${ic("trash")}</button>
          </div>
        </div>
        <div class="prow-body" id="pl-body-${o.id}">${PL.open[o.id] ? `<p class="muted small">Carregando…</p>` : ""}</div>
      </article>`).join("")
      : `<section class="panel"><p class="muted">${all.length ? "Nenhum projeto com esses filtros." : "Nenhum projeto ainda. Clique em <b>Novo projeto</b>."}</p></section>`;
    Object.keys(PL.open).forEach((id) => PL.open[id] && loadBody(Number(id)));
  };
  const loadBody = async (id) => {
    const el = document.getElementById(`pl-body-${id}`);
    if (!el) return;
    const o = await api("GET", `/api/obras/${id}`);
    el.innerHTML = `<table class="table report mini"><thead><tr><th>${o.kind === "serie" ? "Episódio" : "Filme"}</th><th>Título</th><th>Status</th><th>Arquivos</th><th class="num">Legendas</th><th class="num">Tempo</th><th>Atualizado</th><th></th></tr></thead><tbody>
      ${o.items.map((it) => `<tr><td class="mono"><b>${esc(it.label)}</b></td><td>${esc(it.title || "—")}</td><td>${pill(it.status)}</td><td class="small">${fileBadges(it)}</td>
        <td class="num mono">${n0(it.metrics?.legendas)}</td><td class="num mono">${fmtHM(it.seconds)}</td><td class="mono small">${esc(when(it.updated_at))}</td>
        <td class="acts"><button class="btn sm primary" data-l="edit" data-i="${it.id}">${ic("editor")} Abrir no editor</button> <a class="btn sm" href="#/item/${it.id}" title="Métricas">${ic("chart")}</a></td></tr>`).join("")}
      </tbody></table>`;
  };
  draw();
  document.getElementById("pl-q").addEventListener("input", (e) => { PL.q = e.target.value; draw(); });
  main.onchange = async (e) => {
    const t = e.target;
    if (t.id === "pl-client") { PL.client = t.value; draw(); }
    if (t.id === "pl-sort") { PL.sort = t.value; draw(); }
    if (t.dataset.ost) {
      try {
        await api("PUT", `/api/obras/${t.dataset.ost}`, { status: t.value });
        const o = all.find((x) => String(x.id) === t.dataset.ost);
        toast(o.status === "finalizado" && t.value !== "finalizado" ? `“${o.name}” reaberto.` : `“${o.name}”: ${STATUS_TXT[t.value]}.`);
        o.status = t.value; t.className = `st-sel st-${t.value}`;
      } catch (err) { toast(err.message, true); }
    }
  };
  main.onclick = async (e) => {
    const st = e.target.closest("[data-st]");
    if (st) { PL.status = st.dataset.st; document.querySelectorAll("#pl-status button").forEach((x) => x.setAttribute("aria-selected", String(x === st))); draw(); return; }
    const k = e.target.closest("[data-kind]");
    if (k) { PL.kind = k.dataset.kind; document.querySelectorAll("#pl-kind button").forEach((x) => x.setAttribute("aria-selected", String(x === k))); draw(); return; }
    const b = e.target.closest("[data-l]");
    if (!b) return;
    const row = b.closest(".prow");
    const id = row ? Number(row.dataset.id) : null;
    try {
      if (b.dataset.l === "toggle") {
        PL.open[id] = !PL.open[id];
        row.classList.toggle("open", PL.open[id]); b.setAttribute("aria-expanded", String(PL.open[id]));
        const body = document.getElementById(`pl-body-${id}`);
        if (PL.open[id]) { body.innerHTML = `<p class="muted small">Carregando…</p>`; await loadBody(id); } else body.innerHTML = "";
      }
      if (b.dataset.l === "edit") await openItem(Number(b.dataset.i));
      if (b.dataset.l === "folder") await api("POST", "/api/open", { path: b.dataset.path });
      if (b.dataset.l === "open") await openProjectFolder();
      if (b.dataset.l === "remove") {
        const o = all.find((x) => x.id === id);
        if (!confirm(`Tirar “${o.name}” da lista? A pasta e os arquivos continuam no computador; dá para reabrir pelo botão Abrir.`)) return;
        await api("DELETE", `/api/obras/${id}`); toast("Projeto tirado da lista."); renderProjectsList();
      }
    } catch (err) { toast(err.message, true); }
  };
}
