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
  const sug = (S.state.home_dir ? S.state.home_dir + "\\Documents\\Legendas" : "");
  const mf = monthFolder(thisMonth());
  main.innerHTML = `
  <div class="ds-page" style="max-width:860px">
    <header class="ds-head"><div class="ds-head-main"><h1 class="ds-title">Onde ficam os seus trabalhos?</h1>
      <p class="ds-sub">Escolha a pasta onde você guarda as legendas. Dentro dela o programa usa uma pasta por mês (<b>${esc(mf)}</b>) e, dentro do mês, uma por projeto. Se a pasta já tem os seus meses, os trabalhos que estão lá aparecem no programa — nada é movido nem apagado.</p></div></header>
    <section class="ds-set"><div class="ds-set-row"><div class="ds-set-line">
      <div class="ds-set-text"><div class="ds-set-title">Pasta dos trabalhos ${helpBtn("cfg-pasta")}</div>
        <input type="text" id="w-root" class="mono" style="width:100%;margin-top:8px" value="${esc(S.state.projects_root || sug)}" placeholder="C:\\Users\\voce\\Documents\\Legendas"></div>
      <button type="button" class="ds-btn sm" data-w="pick">${ic("open")} Escolher</button></div></div></section>
    <p class="ds-meta">Exemplo: <span class="mono small">…\\Legendas\\${esc(mf)}\\Endless Love\\temporada-2\\ep-90</span></p>
    <div><button type="button" class="ds-btn primary" data-w="save">${ic("check")} Usar esta pasta</button></div>
  </div>`;
  main.onclick = async (e) => {
    const b = e.target.closest("[data-w]");
    if (!b) return;
    try {
      if (b.dataset.w === "pick") {
        const { paths } = await api("POST", "/api/dialog", { kind: "folder", title: "Pasta dos trabalhos" });
        if (paths[0]) document.getElementById("w-root").value = paths[0];
      }
      if (b.dataset.w === "save") {
        b.disabled = true;
        const r = await api("POST", "/api/obras/root", { path: document.getElementById("w-root").value.trim() });
        const n = r.scan?.adicionados || 0;
        toast(n ? `Pronto! ${n} trabalho(s) encontrado(s) nas pastas de mês.` : "Pronto! Os trabalhos vão ficar nesta pasta.");
        START_MES = null;
        location.hash = "#/inicio";
      }
    } catch (err) { toast(err.message, true); b.disabled = false; }
  };
}

/* ------------------------------------------------------------ tela inicial (mês a mês) */

let START_MES = null;

async function renderStart() {
  await Promise.all([loadState(), loadProjects()]);
  if (!S.state.projects_root) { location.hash = "#/bemvindo"; return; }
  const mes = START_MES || thisMonth();
  const [data, mm] = await Promise.all([api("GET", `/api/obras?mes=${mes}`), api("GET", "/api/obras/months")]);
  const rows = data.obras;
  const rec = data.recent;
  const root = data.root.replace(/[\\/]+$/, "");
  const going = rows.filter((o) => o.done < o.total).length;
  const toDeliver = rows.filter((o) => /^Entregar/.test(o.next || "")).length;
  const delivered = rows.reduce((a, o) => a + (o.done || 0), 0);
  const others = mm.months.filter((m) => m.mes !== mes);
  const isNow = mes === thisMonth();
  main.innerHTML = `
  <div class="ds-page">
    <header class="ds-head">
      <div class="ds-head-main">
        <div class="ds-head-line">
          <button type="button" class="ds-iconbtn" data-s="prev" aria-label="Mês anterior">‹</button>
          <h1 class="ds-title">${esc(monthLabel(mes))}</h1>
          <button type="button" class="ds-iconbtn" data-s="next" aria-label="Próximo mês">›</button>
          ${helpBtn("inicio")}
        </div>
        <p class="ds-sub">Pasta: <span class="mono small">${esc(root)}</span> › <b>${esc(monthFolder(mes))}</b>
          <button type="button" class="ds-link" data-s="openmonth">Abrir no Windows</button></p>
      </div>
      <div class="ds-actions">
        <a class="ds-btn" href="#/editor">Abrir uma legenda solta</a>
        <a class="ds-btn primary" href="#/obra/nova">${ic("plus")} Novo trabalho</a>
      </div>
    </header>

    ${rows.length ? `<div class="ds-chips">
      <span class="ds-chip"><b>${going}</b> em andamento</span>
      ${toDeliver ? `<span class="ds-chip"><b>${toDeliver}</b> para entregar</span>` : ""}
      <span class="ds-chip"><b>${delivered}</b> entregue${delivered === 1 ? "" : "s"} no mês</span>
      ${rec && isNow ? `<button type="button" class="ds-chip" data-s="recent" style="cursor:pointer">Continuar de onde parou: <b>${esc(rec.name)}${rec.kind === "serie" ? ` · ${esc(rec.label)}` : ""}</b> ›</button>` : ""}
    </div>` : ""}

    <section class="ds-list" aria-label="Trabalhos de ${esc(monthLabel(mes))}">
      ${rows.length ? rows.map((o) => `
        <article class="ds-row ${o.total && o.done === o.total ? "done" : ""}">
          <div class="ds-row-name"><a href="#/obra/${o.id}">${esc(o.name)}</a>
            <span class="ds-meta">${o.kind === "serie" ? "Série" : "Filme"}${o.client_name ? ` · ${esc(o.client_name)}` : ""} · ${esc(shortLang(o.source_lang))} → ${esc(shortLang(o.target_lang))}${o.exists ? "" : ` · <span class="ds-err">pasta não encontrada</span>`}</span></div>
          <div class="ds-prog"><div class="ds-bar" aria-hidden="true"><i style="width:${o.pct || 0}%"></i></div><span class="ds-meta">${esc(o.progress || "")}</span></div>
          <div class="ds-next"><small>Próximo passo</small><span>${esc(o.next || "")}</span></div>
          <a class="ds-btn sm" href="#/obra/${o.id}">Abrir</a>
        </article>`).join("")
        : `<div class="ds-empty"><b>Nenhum trabalho em ${esc(monthLabel(mes).toLowerCase().replace(/^./, (c) => c.toUpperCase()))} ainda</b>
            <span>${isNow ? "Quando chegar um trabalho, clique em Novo trabalho." : "Use as setas para ir a outro mês."}</span>
            ${isNow ? `<a class="ds-btn primary" href="#/obra/nova">${ic("plus")} Novo trabalho</a>` : ""}</div>`}
    </section>

    ${others.length ? `<section style="display:flex;flex-direction:column;gap:12px" aria-label="Outros meses">
      <h2 class="ds-h2">Outros meses</h2>
      <div class="ds-months">${others.slice(0, 12).map((m) => `<button type="button" class="ds-month" data-mes="${m.mes}">
        <strong>${esc(m.label)}</strong><span>${m.total ? `${m.total} trabalho${m.total === 1 ? "" : "s"}${m.total && m.finalizado === m.total ? " · todos entregues" : m.andamento ? ` · ${m.andamento} em andamento` : ""}` : "Nenhum trabalho"}</span></button>`).join("")}</div>
      <p class="ds-meta">Procurando um trabalho antigo? <a href="#/projetos">Ver a lista de todos os projetos</a> · <button type="button" class="ds-link" data-s="scan">Procurar trabalhos novos nas pastas</button></p>
    </section>` : ""}
  </div>`;
  main.onclick = async (e) => {
    const m = e.target.closest("[data-mes]");
    if (m) { START_MES = m.dataset.mes; renderStart(); return; }
    const b = e.target.closest("[data-s]");
    if (!b) return;
    try {
      if (b.dataset.s === "prev") { START_MES = shiftMonth(mes, -1); renderStart(); }
      if (b.dataset.s === "next") { START_MES = shiftMonth(mes, 1); renderStart(); }
      if (b.dataset.s === "recent" && rec) await openItem(rec.item_id);
      if (b.dataset.s === "openmonth") await api("POST", "/api/open", { path: `${root}\\${monthFolder(mes)}` }).catch(() => api("POST", "/api/open", { path: root }));
      if (b.dataset.s === "scan") {
        const r = await api("POST", "/api/obras/scan");
        toast(r.adicionados ? `${r.adicionados} trabalho(s) encontrado(s) nas pastas.` : "Nenhum trabalho novo nas pastas de mês.");
        renderStart();
      }
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

/* ------------------------------------------------------------ novo trabalho (3 perguntas) */

const NT_KINDS = [
  { id: "traduzir", title: "Traduzir uma legenda", text: "O cliente mandou a legenda pronta (.srt). É o mais comum.",
    a: ["subtitle", "Legenda do cliente (.srt)"], b: ["media", "Vídeo — opcional, para conferir"], cta: "Criar e abrir no editor" },
  { id: "transcrever", title: "Legendar um vídeo", text: "Só tem o vídeo. O programa escreve a legenda a partir da fala, no seu computador.",
    a: ["media", "Vídeo"], b: null, cta: "Criar e começar a legendar" },
  { id: "sincronizar", title: "Acertar o tempo", text: "A legenda existe, mas está fora do tempo do vídeo.",
    a: ["subtitle", "Legenda fora do tempo (.srt)"], b: ["media", "Vídeo"], cta: "Criar e abrir no editor" },
];

async function renderNewProject() {
  await Promise.all([loadState(), loadProjects()]);
  if (!S.state.projects_root) { location.hash = "#/bemvindo"; return; }
  const all = (await api("GET", "/api/obras")).obras;
  // um projeto por nome+cliente (o mês mais recente)
  const seen = new Set();
  const projs = all.slice().sort((x, y) => (y.mes || "").localeCompare(x.mes || "") || y.updated_at.localeCompare(x.updated_at))
    .filter((o) => { const k = `${o.name.toLowerCase()}|${o.client_id || 0}`; if (seen.has(k)) return false; seen.add(k); return true; });
  const mes = thisMonth();
  const clientId = getPref("cnt.cliente", "");
  const cli = (S.projects || []).find((c) => String(c.id) === clientId);
  const W = { kind: "traduzir", client: clientId, proj: projs.length ? String(projs[0].id) : "new", newKind: "serie", name: "",
    season: 1, episode: "", src: cli?.source_lang || "auto", dst: cli?.target_lang || "es-419", files: { a: "", b: "" }, nameErr: "" };
  const cur = () => NT_KINDS.find((k) => k.id === W.kind);
  const obra = () => projs.find((o) => String(o.id) === W.proj);
  const pickProj = () => {
    const o = obra();
    if (o) { W.src = o.source_lang || W.src; W.dst = o.target_lang || W.dst; W.client = o.client_id ? String(o.client_id) : W.client; }
  };
  pickProj();

  const draw = () => {
    const k = cur(), o = obra(), isNew = W.proj === "new";
    const serie = isNew ? W.newKind === "serie" : o?.kind === "serie";
    const root = S.state.projects_root.replace(/[\\/]+$/, "");
    const pname = isNew ? (W.name || "…") : (o?.folder.split(/[\\/]/).pop() || "");
    const dest = `${root}\\${monthFolder(mes)}\\${pname}${serie ? `\\temporada-${W.season || "?"}\\ep-${W.episode || "?"}` : ""}`;
    main.innerHTML = `
    <div class="ds-page">
      <a class="ds-back" href="#/inicio">‹ Voltar ao Início</a>
      <header class="ds-head"><div class="ds-head-main"><div class="ds-head-line"><h1 class="ds-title">Novo trabalho</h1>${helpBtn("novo")}</div>
        <p class="ds-sub">Vai para a pasta de <b>${esc(monthLabel(mes))}</b>.</p></div></header>
      <form class="ds-form" id="nt" novalidate>
        <section class="ds-q" aria-labelledby="q1">
          <h2 id="q1"><em>1.</em> O que você vai fazer? ${helpBtn("o-que")}</h2>
          <div class="ds-choices">${NT_KINDS.map((x) => `<button type="button" class="ds-choice" data-kind="${x.id}" aria-pressed="${x.id === W.kind}">
            <strong>${esc(x.title)}</strong><span>${esc(x.text)}</span></button>`).join("")}</div>
        </section>

        <section class="ds-q" aria-labelledby="q2">
          <h2 id="q2"><em>2.</em> Para quem e qual ${serie ? "episódio" : "trabalho"}? ${helpBtn("quem")}</h2>
          <div class="ds-fields">
            <label class="ds-field"><span>Cliente</span><select id="nt-client"><option value="">Sem cliente</option>${(S.projects || []).map((c) => `<option value="${c.id}" ${String(c.id) === W.client ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
            <label class="ds-field"><span>Projeto</span><select id="nt-proj">
              ${projs.map((p) => `<option value="${p.id}" ${String(p.id) === W.proj ? "selected" : ""}>${esc(p.name)}${p.mes_label ? ` (${esc(p.mes_label)})` : ""}</option>`).join("")}
              <option value="new" ${isNew ? "selected" : ""}>+ Projeto novo…</option></select></label>
            ${serie ? `<label class="ds-field"><span>Temporada</span><input type="number" id="nt-season" min="0" value="${esc(W.season)}"></label>
              <label class="ds-field"><span>Episódio</span><input type="number" id="nt-ep" min="0" value="${esc(W.episode)}" placeholder="ex.: 93"></label>` : ""}
          </div>
          ${isNew ? `<div class="ds-fields">
            <label class="ds-field" style="grid-column:span 2"><span>Nome do projeto (vira o nome da pasta)</span><input type="text" id="nt-name" maxlength="120" value="${esc(W.name)}" placeholder="Ex.: Endless Love — T2" autocomplete="off"></label>
            <label class="ds-field"><span>É…</span><select id="nt-newkind"><option value="serie" ${W.newKind === "serie" ? "selected" : ""}>Série (com episódios)</option><option value="filme" ${W.newKind === "filme" ? "selected" : ""}>Filme</option></select></label>
          </div>${W.nameErr ? `<p class="ds-err">${esc(W.nameErr)}</p>` : ""}` : ""}
          <div class="ds-fields">
            <label class="ds-field"><span>Idioma do original ${helpBtn("idiomas")}</span><select id="nt-src">${langOptions(W.src, true)}</select></label>
            ${W.kind !== "sincronizar" ? `<label class="ds-field"><span>${W.kind === "transcrever" ? "Depois traduzir para" : "Traduzir para"}</span><select id="nt-dst">${W.kind === "transcrever" ? `<option value="">Não traduzir</option>` : ""}${langOptions(W.dst)}</select></label>` : ""}
            <label class="ds-field"><span>Entregar até <em class="muted small">(opcional)</em></span><input type="date" id="nt-prazo" value="${esc(W.prazo || "")}"></label>
          </div>
        </section>

        <section class="ds-q" aria-labelledby="q3">
          <h2 id="q3"><em>3.</em> Arquivos ${helpBtn("arquivos")}</h2>
          <div class="ds-drops">
            ${[["a", k.a], ["b", k.b]].filter(([, v]) => v).map(([slot, [kind, label]]) => `<div class="ds-drop ${W.files[slot] ? "on" : ""}">
              <strong>${esc(label)}</strong>
              <small>${W.files[slot] ? esc(W.files[slot]) : "Ainda não escolhido"}</small>
              <button type="button" class="ds-btn sm" data-pick="${slot}" data-kind="${kind}">${W.files[slot] ? "Trocar" : "Escolher arquivo"}</button></div>`).join("")}
          </div>
          <p class="ds-meta">Os arquivos são copiados para a pasta do ${serie ? "episódio" : "projeto"}; os seus originais ficam onde estão.</p>
        </section>

        <footer class="ds-foot"><small>Vai para: ${esc(dest)}</small>
          <button type="submit" class="ds-btn primary" id="nt-go">${esc(k.cta)}</button></footer>
      </form>
    </div>`;
  };
  draw();

  const val = (id) => document.getElementById(id)?.value;
  const grab = () => {
    W.client = val("nt-client") ?? W.client;
    W.season = val("nt-season") ?? W.season;
    W.episode = val("nt-ep") ?? W.episode;
    W.name = val("nt-name") ?? W.name;
    W.newKind = val("nt-newkind") ?? W.newKind;
    W.src = val("nt-src") ?? W.src;
    W.prazo = val("nt-prazo") ?? W.prazo;
    if (document.getElementById("nt-dst")) W.dst = val("nt-dst");
  };
  main.onchange = (e) => {
    grab();
    if (e.target.id === "nt-proj") { W.proj = e.target.value; pickProj(); draw(); }
    else if (e.target.id === "nt-client" && W.proj === "new") {
      const c = (S.projects || []).find((x) => String(x.id) === W.client);
      if (c) { W.src = c.source_lang || W.src; W.dst = c.target_lang || W.dst; }
      draw();
    } else if (["nt-newkind", "nt-season", "nt-ep", "nt-name"].includes(e.target.id)) draw();
  };
  main.oninput = (e) => {
    if (e.target.id !== "nt-name") return;
    const clean = e.target.value.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "");
    if (clean !== e.target.value) { e.target.value = clean; toast("O Windows não aceita < > : \" / \\ | ? * em nomes de pasta.", true); }
  };
  main.onclick = async (e) => {
    const c = e.target.closest("[data-kind]:not([data-pick])");
    if (c) {
      grab(); W.kind = c.dataset.kind; W.files = { a: "", b: "" };
      if (W.kind === "transcrever") W.dst = "";          // legendar: traduzir depois é opcional
      else if (!W.dst) W.dst = obra()?.target_lang || (S.projects || []).find((x) => String(x.id) === W.client)?.target_lang || "es-419";
      draw(); return;
    }
    const p = e.target.closest("[data-pick]");
    if (p) {
      grab();
      try {
        const { paths } = await api("POST", "/api/dialog", { kind: p.dataset.kind });
        if (paths[0]) { W.files[p.dataset.pick] = paths[0]; draw(); }
      } catch (err) { toast(err.message, true); }
    }
  };
  main.onsubmit = async (e) => {
    e.preventDefault();
    grab();
    const k = cur();
    const go = document.getElementById("nt-go");
    const isNew = W.proj === "new";
    const serie = isNew ? W.newKind === "serie" : obra()?.kind === "serie";
    if (k.a && !W.files.a && W.kind !== "traduzir") return toast(`Escolha: ${k.a[1]}.`, true);
    if (serie && (W.episode === "" || W.season === "")) return toast("Informe a temporada e o episódio.", true);
    if (isNew && !W.name.trim()) return toast("Dê um nome ao projeto.", true);
    go.disabled = true;
    try {
      setPref("cnt.cliente", W.client);
      const clientId = W.client ? Number(W.client) : null;
      const langs = { source_lang: W.src || "auto", target_lang: W.dst || "es-419" };
      let o, item;
      if (isNew) {
        const body = { kind: serie ? "serie" : "filme", name: W.name.trim(), client_id: clientId, mes, ...langs };
        if (serie) Object.assign(body, { season: Number(W.season), episodes: String(W.episode) });
        o = await api("POST", "/api/obras", body);
        item = o.items[0];
      } else {
        o = obra();
        if (o.mes !== mes) o = await api("POST", `/api/obras/${o.id}/continue`, { mes });
        await api("PUT", `/api/obras/${o.id}`, { client_id: clientId, ...langs });
        if (serie) {
          try { o = await api("POST", `/api/obras/${o.id}/episodes`, { season: Number(W.season), episodes: String(W.episode) }); }
          catch (err) { o = await api("GET", `/api/obras/${o.id}`); }   // o episódio já existia: usa ele
          item = o.items.find((it) => it.season === Number(W.season) && it.episode === Number(W.episode));
        } else item = (await api("GET", `/api/obras/${o.id}`)).items[0];
      }
      if (W.prazo && item) await api("PUT", `/api/itens/${item.id}`, { prazo: W.prazo });
      const files = [W.files.a, W.files.b].filter(Boolean);
      if (files.length) await copyFiles(item.id, files);
      if (W.kind === "transcrever") {
        const fresh = (await api("GET", `/api/obras/${o.id}`)).items.find((it) => it.id === item.id);
        const steps = W.dst ? ["transcrever", "traduzir"] : ["transcrever"];
        const j = await api("POST", "/api/jobs", { inputs: [fresh.video], params: { steps, source_lang: W.src || "auto",
          target_lang: W.dst || "es-419", profile_key: (S.projects || []).find((x) => x.id === clientId)?.profile_key || "",
          project_id: clientId, obra_id: o.id, out_dir: fresh.folder } });
        toast("Legendando o vídeo em segundo plano. Você pode fazer outra coisa enquanto isso.");
        location.hash = `#/trabalho/${j.id}`;
        return;
      }
      if (!files.length) { toast("Trabalho criado. Ponha os arquivos quando chegarem."); location.hash = `#/obra/${o.id}`; return; }
      toast(W.kind === "sincronizar" ? "No editor, use Sincronizar › Sincronia precisa pela fala."
        : `Pronto: ${o.name}${serie ? `, episódio ${W.episode}` : ""}.`);
      await openItem(item.id);
    } catch (err) { toast(err.message, true); go.disabled = false; }
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

/* ------------------------------------------------------------ projeto (passo a passo) */

let OBRA_TAB = "eps";
const STEP_KEYS = ["arquivos", "traduzir", "revisar", "entregar"];
const STEP_NOTE = ["Falta o vídeo e a legenda", "Pronto para traduzir", "Traduzido — falta revisar", "Revisado — falta entregar"];

function epNote(it) {
  const d = (it.finished_at || "").match(/^\d{4}-(\d{2})-(\d{2})/);
  if (it.step >= 4) return ["Pronto", `Entregue${d ? ` em ${d[2]}/${d[1]}` : ""}`];
  return ["Agora", STEP_NOTE[it.step]];
}

function epCard(it, serie, isNow) {
  const [lab, note] = epNote(it);
  const track = (window.OBRA_STEPS || ["Arquivos", "Traduzir", "Revisar", "Entregar"]).map((t, k) =>
    `<li class="${k < it.step ? "done" : ""}" ${k === it.step ? 'aria-current="step"' : ""}>${esc(t)}</li>`).join("");
  return `<article class="ds-ep ${isNow ? "now" : ""}" data-i="${it.id}">
    <div class="ds-ep-num">${serie ? `<small>Episódio</small><b>${esc(it.episode)}</b>
      <input type="text" data-title="${it.id}" value="${esc(it.title || "")}" placeholder="título (opcional)" aria-label="Título do episódio ${esc(it.episode)}">`
      : `<small>Filme</small><b style="font-size:20px">${ic("film")}</b>`}</div>
    <ol class="ds-track" aria-label="Passos">${track}</ol>
    <div class="ds-ep-note"><small>${esc(lab)}</small><span>${esc(note)}</span>${it.prazo && it.step < 4 ? (() => { const t = prazoTexto(it.prazo); return `<span class="ds-prazo ${t.nivel}" title="Prazo de entrega">Entrega ${esc(t.texto)}</span>`; })() : ""}${it.exists ? "" : `<span class="ds-err">pasta não encontrada</span>`}</div>
    <div class="ds-ep-acts">
      <button type="button" class="ds-btn sm ${isNow ? "primary" : ""}" data-o="${it.step === 0 ? "files" : "edit"}" data-i="${it.id}">${esc(it.action)}</button>
      <div class="ds-more"><button type="button" class="ds-iconbtn" data-o="more" data-i="${it.id}" aria-haspopup="menu" aria-expanded="false" aria-label="Mais opções">⋯</button></div>
    </div>
  </article>`;
}

function epMenu(it) {
  return `<div class="ds-menu" role="menu">
    <button role="menuitem" data-o="edit" data-i="${it.id}">Abrir no editor</button>
    <button role="menuitem" data-o="files" data-i="${it.id}">Pôr vídeo ou legenda…</button>
    <button role="menuitem" data-o="ifolder" data-path="${esc(it.folder)}">Abrir a pasta no Windows</button>
    <a role="menuitem" href="#/item/${it.id}">Números do episódio</a>
    <button role="menuitem" data-o="prazo" data-i="${it.id}">${it.prazo ? "Mudar o prazo de entrega…" : "Prazo de entrega…"}</button>
    <hr>
    ${it.status === "finalizado" ? `<button role="menuitem" data-o="istatus" data-st="andamento" data-i="${it.id}">Reabrir (não está entregue)</button>`
      : `<button role="menuitem" data-o="istatus" data-st="finalizado" data-i="${it.id}">Marcar como entregue</button>`}
    <button role="menuitem" data-o="iremove" data-i="${it.id}">Tirar da lista (a pasta fica)</button>
  </div>`;
}

let OBRA_LAST = null;
async function renderObra(id) {
  if (OBRA_LAST !== id) { OBRA_TAB = "eps"; OBRA_LAST = id; }
  await Promise.all([loadState(), loadProjects()]);
  const o = await api("GET", `/api/obras/${id}`);
  window.OBRA_STEPS = o.steps;
  const serie = o.kind === "serie";
  const m = o.metrics || {};
  setCrumb(`Início <span class="muted">/ ${esc(o.name)}</span>`);
  const now = o.items.find((it) => it.step < 4);
  const prof = (S.projects || []).find((c) => c.id === o.client_id);
  const lastSeason = o.seasons.length ? o.seasons[o.seasons.length - 1].season : 1;
  main.innerHTML = `
  <div class="ds-page">
    <a class="ds-back" href="#/inicio" data-o="back">‹ ${esc(o.mes_label || "Início")}</a>
    <header class="ds-head">
      <div class="ds-head-main">
        <h1 class="ds-title">${esc(o.name)}</h1>
        <p class="ds-sub">${serie ? "Série" : "Filme"}${o.client_name ? ` · <b>${esc(o.client_name)}</b>` : " · sem cliente"} · ${esc(shortLang(o.source_lang))} → ${esc(shortLang(o.target_lang))}${prof?.profile_key ? ` · regras: ${esc(profileName(prof.profile_key))}` : ""}${o.formato ? ` · entrega em .${esc(o.formato)}` : ""}${o.status === "finalizado" ? " · <b>entregue</b>" : ""}</p>
      </div>
      <div class="ds-actions">
        <button type="button" class="ds-btn" data-o="folder">${ic("open")} Abrir a pasta</button>
        ${serie ? `<button type="button" class="ds-btn" data-o="addeps">${ic("plus")} Episódios</button>` : ""}
        <div class="ds-more"><button type="button" class="ds-btn quiet" data-o="omore" aria-haspopup="menu" aria-expanded="false">Mais ▾</button></div>
      </div>
    </header>

    ${OBRA_TAB === "eps" ? `
    <section class="ds-how" aria-label="Como funciona">
      <span>Cada ${serie ? "episódio" : "trabalho"} passa por</span>
      ${o.steps.map((t, k) => `<span class="ds-how-step">${esc(t)} ${helpBtn("passo-" + STEP_KEYS[k], `O que é ${t}?`)}${k < 3 ? `<span class="ds-how-arrow" aria-hidden="true">→</span>` : ""}</span>`).join("")}
    </section>
    ${o.items.length ? (serie ? o.seasons.map((sz) => `
      <section class="ds-season" aria-label="Temporada ${sz.season}">
        ${o.seasons.length > 1 || sz.season !== 1 ? `<h2 class="ds-h2">Temporada ${sz.season}</h2>` : ""}
        ${sz.items.map((it) => epCard(it, true, now && it.id === now.id)).join("")}
      </section>`).join("") : epCard(o.items[0], false, !!now))
      : `<div class="ds-empty"><b>Nenhum episódio ainda</b><span>Clique em “Episódios” para pôr o primeiro.</span>
         <button type="button" class="ds-btn primary" data-o="addeps">${ic("plus")} Episódios</button></div>`}
    <p class="ds-meta">Números do projeto (legendas, palavras, tempo trabalhado) e o histórico ficam em <button type="button" class="ds-link" data-o="tab-met">Números e histórico</button>.</p>`
    : `<div class="tabs big" role="tablist" id="ob-tabs">
        <button role="tab" data-t="eps" aria-selected="false">‹ Episódios</button>
        <button role="tab" data-t="met" aria-selected="${OBRA_TAB === "met"}">Números</button>
        <button role="tab" data-t="hist" aria-selected="${OBRA_TAB === "hist"}">Histórico</button>
      </div><div id="ob-body"></div>`}
  </div>`;

  if (OBRA_TAB === "met") document.getElementById("ob-body").innerHTML = metricsPanels(m, o.productivity, o.seconds) + (serie ? epsMetricsTable(o.items) : "");
  if (OBRA_TAB === "hist") {
    const r = await api("GET", `/api/obras/${id}/report`);
    document.getElementById("ob-body").innerHTML = `<div class="split2">
      <section class="panel"><h2>Histórico</h2><ul class="timeline">${r.events.map((e) => `<li><span class="mono small muted">${esc(when(e.at))}</span><b>${esc(EVT[e.tipo] || e.tipo)}</b><span>${esc(e.detalhe)}</span></li>`).join("") || `<li class="muted">Nada ainda.</li>`}</ul></section>
      <section class="panel"><h2>Tempo por dia</h2>${dayBars(r.days)}</section></div>`;
  }

  const closeMenus = () => document.querySelectorAll(".ds-menu").forEach((x) => { x.previousElementSibling?.setAttribute("aria-expanded", "false"); x.remove(); });
  const toggleMenu = (btn, html) => {
    const open = btn.getAttribute("aria-expanded") === "true";
    closeMenus();
    if (open) return;
    btn.insertAdjacentHTML("afterend", html);
    btn.setAttribute("aria-expanded", "true");
    btn.nextElementSibling.querySelector("button, a")?.focus();
  };
  main.onchange = async (e) => {
    const t = e.target;
    try {
      if (t.dataset.title) { await api("PUT", `/api/itens/${t.dataset.title}`, { title: t.value }); toast("Título salvo."); }
    } catch (err) { toast(err.message, true); }
  };
  main.onclick = async (e) => {
    const tab = e.target.closest("[data-t]");
    if (tab) { OBRA_TAB = tab.dataset.t; renderObra(id); return; }
    const b = e.target.closest("[data-o]");
    if (!b) { if (!e.target.closest(".ds-menu")) closeMenus(); return; }
    const a = b.dataset.o;
    const itemId = Number(b.dataset.i);
    try {
      if (a === "back") { START_MES = o.mes || null; return; }
      if (a === "more") { toggleMenu(b, epMenu(o.items.find((x) => x.id === itemId))); return; }
      if (a === "omore") {
        toggleMenu(b, `<div class="ds-menu" role="menu">
          <button role="menuitem" data-o="glossario">Glossário do projeto…</button>
          <button role="menuitem" data-o="client">Mudar o cliente…</button>
          <button role="menuitem" data-o="formato">Formato de entrega…</button>
          <button role="menuitem" data-o="tab-met">Números e histórico</button>
          ${o.status === "finalizado" ? `<button role="menuitem" data-o="status" data-st="andamento">Reabrir o projeto</button>`
            : `<button role="menuitem" data-o="status" data-st="finalizado">Marcar o projeto todo como entregue</button>`}
          <hr><button role="menuitem" data-o="remove">Tirar da lista (a pasta fica)</button></div>`);
        return;
      }
      closeMenus();
      if (a === "glossario") { await glossarioProjeto(id, o.name); return; }
      if (a === "tab-met") { OBRA_TAB = "met"; renderObra(id); }
      if (a === "folder") await api("POST", "/api/open", { path: o.folder });
      if (a === "ifolder") await api("POST", "/api/open", { path: b.dataset.path });
      if (a === "edit") await openItem(itemId);
      if (a === "files") {
        const { paths } = await api("POST", "/api/dialog", { kind: "any", multiple: true, title: "Vídeo e/ou legenda deste episódio" });
        if (!paths.length) return;
        await copyFiles(itemId, paths);
        toast("Arquivos copiados para a pasta do episódio."); renderObra(id);
      }
      if (a === "istatus") { await api("PUT", `/api/itens/${itemId}`, { status: b.dataset.st }); toast(b.dataset.st === "finalizado" ? "Marcado como entregue." : "Episódio reaberto."); renderObra(id); }
      if (a === "iremove") {
        if (!confirm("Tirar este episódio da lista? A pasta e os arquivos continuam no computador.")) return;
        await api("DELETE", `/api/itens/${itemId}`); renderObra(id);
      }
      if (a === "status") { await api("PUT", `/api/obras/${id}`, { status: b.dataset.st }); toast(b.dataset.st === "finalizado" ? "Projeto marcado como entregue." : "Projeto reaberto."); renderObra(id); }
      if (a === "remove") {
        if (!confirm("Tirar este projeto da lista? A pasta e os arquivos continuam no computador; dá para encontrá-lo de novo pela pasta.")) return;
        await api("DELETE", `/api/obras/${id}`); location.hash = "#/inicio";
      }
      if (a === "prazo") {
        const it = o.items.find((x) => x.id === itemId);
        const md = modal(serie ? `Prazo de entrega — ${it.label}` : "Prazo de entrega", `
          <label class="ds-field"><span>Entregar até</span><input type="date" id="pz-d" value="${esc(it.prazo || "")}"></label>
          <p class="ds-meta">Não é obrigatório. A próxima entrega aparece no topo da tela.</p>`,
          `${it.prazo ? `<button class="btn" data-m="limpar">Tirar o prazo</button>` : ""}<span style="flex:1"></span><button class="btn" data-m="x">Cancelar</button><button class="btn primary" data-m="ok">Salvar</button>`);
        md.ov.onclick = async (ev) => {
          const k = ev.target.closest("[data-m]")?.dataset.m;
          if (k === "x") md.close();
          if (k === "ok" || k === "limpar") {
            try {
              await api("PUT", `/api/itens/${itemId}`, { prazo: k === "limpar" ? "" : md.$("#pz-d").value });
              md.close(); toast(k === "limpar" ? "Prazo tirado." : "Prazo salvo."); renderObra(id); atualizarPrazoTopo();
            } catch (err) { toast(err.message, true); }
          }
        };
      }
      if (a === "formato") {
        const cli = (S.projects || []).find((c) => c.id === o.client_id);
        const herda = cli?.formato ? `Igual ao cliente (${FORMATOS.find((f) => f[0] === cli.formato)?.[1] || cli.formato})` : "Igual ao cliente / Configurações (padrão .srt)";
        const md = modal("Formato de entrega do projeto", `<label class="ds-field"><span>Formato</span><select id="of-sel">${formatoOptions(o.formato, herda)}</select></label>
          <p class="ds-meta">Só para este projeto. Na hora de entregar ainda dá para trocar só daquela vez.</p>`,
          `<button class="btn" data-m="x">Cancelar</button><button class="btn primary" data-m="ok">Salvar</button>`);
        md.ov.onclick = async (ev) => {
          const k = ev.target.closest("[data-m]")?.dataset.m;
          if (k === "x") md.close();
          if (k === "ok") { await api("PUT", `/api/obras/${id}`, { formato: md.$("#of-sel").value }); md.close(); toast("Formato do projeto salvo."); renderObra(id); }
        };
      }
      if (a === "client") {
        const md = modal("Cliente do projeto", `<label class="ds-field"><span>Cliente</span><select id="oc-sel"><option value="">Sem cliente</option>${(S.projects || []).map((c) => `<option value="${c.id}" ${c.id === o.client_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>`,
          `<button class="btn" data-m="x">Cancelar</button><button class="btn primary" data-m="ok">Salvar</button>`);
        md.ov.onclick = async (ev) => {
          const k = ev.target.closest("[data-m]")?.dataset.m;
          if (k === "x") md.close();
          if (k === "ok") { const v = md.$("#oc-sel").value; await api("PUT", `/api/obras/${id}`, { client_id: v ? Number(v) : null }); md.close(); toast("Cliente atualizado."); renderObra(id); }
        };
      }
      if (a === "addeps") {
        const nx = o.next_episode[String(lastSeason)] || 1;
        const md = modal("Pôr episódios", `
          <div class="ds-fields"><label class="ds-field"><span>Temporada</span><input type="number" id="ae-s" min="0" value="${lastSeason}"></label>
          <label class="ds-field"><span>Episódio(s)</span><input type="text" id="ae-e" value="${nx}" autofocus></label></div>
          <p class="ds-meta">Um número (${nx}), vários (${nx}, ${nx + 2}) ou um intervalo (${nx}-${nx + 4}). Cada episódio ganha a sua pasta.</p>`,
          `<button class="btn" data-m="x">Cancelar</button><button class="btn primary" data-m="ok">Pôr</button>`);
        md.ov.onclick = async (ev) => {
          const k = ev.target.closest("[data-m]")?.dataset.m;
          if (k === "x") md.close();
          if (k === "ok") {
            try { await api("POST", `/api/obras/${id}/episodes`, { season: md.$("#ae-s").value, episodes: md.$("#ae-e").value }); md.close(); toast("Episódios criados."); renderObra(id); }
            catch (err) { toast(err.message, true); }
          }
        };
      }
    } catch (err) { toast(err.message, true); }
  };
}
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape") return;
  document.querySelectorAll(".ds-menu").forEach((x) => { x.previousElementSibling?.setAttribute("aria-expanded", "false"); x.remove(); });
});

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
