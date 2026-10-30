/* CNT Legendas — relatório geral de métricas (todos os projetos). */
"use strict";

let REP_F = { from: "", to: "", client: "", status: "" };

async function renderReports() {
  await Promise.all([loadState(), loadProjects()]);
  const qs = new URLSearchParams(Object.entries(REP_F).filter(([, v]) => v)).toString();
  const [r, rit] = await Promise.all([api("GET", `/api/report${qs ? `?${qs}` : ""}`), api("GET", "/api/ritmo").catch(() => null)]);
  const m = r.metrics || {};
  const maxMonth = Math.max(1, ...r.months.map((x) => x.legendas));
  main.innerHTML = `
    <div class="page-head"><div><span class="eyebrow">Relatórios</span><h1 style="margin-top:6px">Métricas</h1>
      <p class="muted">Tudo o que foi legendado nos projetos: textos, tempo de vídeo, velocidade de leitura, revisão e produtividade.</p></div>
      <button class="btn" data-r="csv">${ic("download")} Exportar planilha (CSV)</button></div>
    <section class="panel filters">
      <label class="field"><span>De</span><input type="date" id="rf-from" value="${esc(REP_F.from)}"></label>
      <label class="field"><span>Até</span><input type="date" id="rf-to" value="${esc(REP_F.to)}"></label>
      <label class="field"><span>Cliente</span><select id="rf-client"><option value="">Todos</option>${(S.projects || []).map((c) => `<option value="${c.id}" ${String(c.id) === REP_F.client ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
      <label class="field"><span>Status</span><select id="rf-status"><option value="">Todos</option>${["novo", "andamento", "finalizado"].map((s) => `<option value="${s}" ${s === REP_F.status ? "selected" : ""}>${STATUS_TXT[s]}</option>`).join("")}</select></label>
      <div class="row" style="align-self:end;gap:6px"><button class="btn primary" data-r="apply">Aplicar</button><button class="btn ghost" data-r="clear">Limpar</button></div>
    </section>
    <section class="kpis">
      ${kpi("Projetos", n0(r.projects.length), `${r.counts.finalizado} finalizados · ${r.counts.andamento} em andamento`, "c-accent", "folder")}
      ${kpi("Episódios / filmes", n0(r.episodes), `${n0(m.legendas)} legendas`, "c-info", "tv")}
      ${kpi("Vídeo legendado", m.duracao_video_s ? fmtHMS(m.duracao_video_s) : "—", `${n0(m.palavras)} palavras`, "c-violet", "film")}
      ${kpi("Tempo trabalhado", fmtHM(r.seconds), r.productivity.legendas_por_hora ? `${n0(r.productivity.legendas_por_hora)} legendas/hora` : "no editor", "c-ok", "clock")}
    </section>
    ${rit ? ritmoPainel(rit) : ""}
    ${metricsPanels(m, r.productivity, r.seconds)}
    <div class="split2">
      <section class="panel"><h2>Por mês</h2>${r.months.length ? `<div class="table-wrap"><table class="table report">
        <thead><tr><th>Mês</th><th>Legendas</th><th class="num">Palavras</th><th class="num">Episódios</th><th class="num">Tempo</th></tr></thead>
        <tbody>${r.months.map((x) => `<tr><td class="mono">${esc(monthName(x.mes))}</td>
          <td><div class="inbar"><i style="--w:${Math.round((x.legendas / maxMonth) * 100)}%"></i><b class="mono">${n0(x.legendas)}</b></div></td>
          <td class="num mono">${n0(x.palavras)}</td><td class="num mono">${n0(x.itens)}</td><td class="num mono">${fmtHM(x.segundos)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">Sem dados no período.</p>`}</section>
      <section class="panel"><h2>Por cliente</h2>${r.clients.length ? `<div class="table-wrap"><table class="table report">
        <thead><tr><th>Cliente</th><th class="num">Projetos</th><th class="num">Episódios</th><th class="num">Legendas</th><th class="num">Vídeo</th><th class="num">Tempo</th></tr></thead>
        <tbody>${r.clients.map((c) => `<tr><td><b>${esc(c.cliente)}</b></td><td class="num mono">${c.projetos}</td><td class="num mono">${c.itens}</td>
          <td class="num mono">${n0(c.legendas)}</td><td class="num mono">${c.duracao_video_s ? fmtHMS(c.duracao_video_s) : "—"}</td><td class="num mono">${fmtHM(c.segundos)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">Sem dados no período.</p>`}</section>
    </div>
    <section class="panel"><h2>Projetos</h2><div class="table-wrap"><table class="table report">
      <thead><tr><th>Projeto</th><th>Tipo</th><th>Cliente</th><th>Status</th><th class="num">Legendas</th><th class="num">Palavras</th><th class="num">Vídeo</th><th class="num">Tempo</th><th>Criado</th><th>Atualizado</th></tr></thead>
      <tbody>${r.projects.map((o) => `<tr class="click" data-href="#/obra/${o.id}"><td><b>${esc(o.name)}</b></td><td>${o.kind === "serie" ? "Série" : "Filme"}</td>
        <td>${esc(o.client_name || "—")}</td><td>${pill(o.status)}</td><td class="num mono">${n0(o.legendas)}</td><td class="num mono">${n0(o.palavras)}</td>
        <td class="num mono">${o.duracao_video_s ? fmtHMS(o.duracao_video_s) : "—"}</td><td class="num mono">${fmtHM(o.seconds)}</td>
        <td class="mono small">${esc(when(o.created_at))}</td><td class="mono small">${esc(when(o.updated_at))}</td></tr>`).join("") || `<tr><td colspan="10" class="muted">Nenhum projeto.</td></tr>`}</tbody></table></div></section>
    <section class="panel"><h2>Tempo por dia</h2>${dayBars(r.days)}</section>`;
  main.querySelectorAll("tr[data-href]").forEach((tr) => tr.addEventListener("click", () => (location.hash = tr.dataset.href)));
  main.onclick = (e) => {
    const a = e.target.closest("[data-r]")?.dataset.r;
    if (a === "apply") {
      REP_F = { from: document.getElementById("rf-from").value, to: document.getElementById("rf-to").value,
        client: document.getElementById("rf-client").value, status: document.getElementById("rf-status").value };
      renderReports();
    }
    if (a === "clear") { REP_F = { from: "", to: "", client: "", status: "" }; renderReports(); }
    if (a === "csv") exportCsv(r);
  };
}

function monthName(ym) {
  const [y, mo] = ym.split("-").map(Number);
  const t = new Date(y, mo - 1, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function exportCsv(r) {
  const cols = [["name", "Projeto"], ["kind", "Tipo"], ["client_name", "Cliente"], ["status_label", "Status"], ["legendas", "Legendas"],
    ["palavras", "Palavras"], ["duracao_video_s", "Vídeo (s)"], ["seconds", "Tempo trabalhado (s)"], ["created_at", "Criado"], ["updated_at", "Atualizado"], ["finished_at", "Finalizado"], ["folder", "Pasta"]];
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [cols.map(([, t]) => q(t)).join(";")]
    .concat(r.projects.map((o) => cols.map(([k]) => q(k === "kind" ? (o.kind === "serie" ? "Série" : "Filme") : typeof o[k] === "number" ? String(Math.round(o[k] * 100) / 100).replace(".", ",") : o[k])).join(";")));
  lines.push("", q("Totais"));
  for (const [grp, rows] of MET_GROUPS) for (const [k, t] of rows) if (r.metrics[k] != null) lines.push(`${q(`${grp}: ${t}`)};${q(String(r.metrics[k]).replace(".", ","))}`);
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `CNT Legendas - relatorio ${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/* ================================================================ ritmo e previsão (2.26)
   Só a partir do 3º trabalho feito e entregue no programa: os 2 primeiros são a base. */

async function carregarPrevisao() {
  ED.previsao = null;
  if (!ED.itemId) return;
  try { ED.previsao = await api("GET", `/api/itens/${ED.itemId}/previsao`); } catch { ED.previsao = null; }
  if (typeof drawStatus === "function") drawStatus();
}

function fmtDuracao(seg) {
  seg = Math.round(seg || 0);
  const h = Math.floor(seg / 3600), m = Math.round((seg % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}` : `${m} min`;
}

function diaSemana(iso) {
  const [a, mm, d] = iso.split("-").map(Number);
  const dt = new Date(a, mm - 1, d), hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  const dias = Math.round((dt - hoje) / 86400000);
  if (dias <= 0) return "hoje";
  if (dias === 1) return "amanhã";
  return dt.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
}

function previsaoTexto() {
  const p = ED.previsao?.previsao;
  if (!p) return "";
  const cls = p.situacao === "atrasado" ? "atrasado" : p.situacao === "apertado" ? "urgente" : "";
  const txt = p.falta_s ? `No seu ritmo: falta ~${fmtDuracao(p.falta_s)} · termina ${diaSemana(p.termina)}` : "No seu ritmo: quase pronto";
  return `<span class="ds-prazo ${cls}" title="Previsão pelo seu ritmo nos trabalhos entregues (${esc(String(ED.previsao.trabalhos))}). Já foram ${p.pct}% do tempo esperado.">${esc(txt)}</span>`;
}

function ritmoPainel(r) {
  if (!r.pronto) {
    return `<section class="panel"><h2>Seu ritmo</h2>
      <p class="muted">O ritmo e a previsão de entrega aparecem a partir do 3º trabalho feito no programa: os 2 primeiros servem de base.
      ${r.trabalhos ? `Já ${r.trabalhos === 1 ? "foi 1 trabalho entregue" : `foram ${r.trabalhos} trabalhos entregues`}; falta ${r.faltam}.` : `Falta${r.faltam === 1 ? "" : "m"} ${r.faltam} trabalho${r.faltam === 1 ? "" : "s"} entregue${r.faltam === 1 ? "" : "s"}.`}</p>
      <p class="muted small">Conta o tempo com o editor aberto: ativo (digitando, clicando ou com o vídeo tocando) e parado; e o tempo fora do programa entre começar e entregar.</p></section>`;
  }
  const tot = (r.ativo_s || 0) + (r.parado_s || 0) + (r.fora_s || 0) || 1;
  const pc = (x) => Math.round((100 * (x || 0)) / tot);
  return `<section class="panel"><h2>Seu ritmo <span class="muted small">· ${r.trabalhos} trabalhos entregues no programa</span></h2>
    <section class="kpis">
      ${kpi("Vídeo por hora", `${String(r.video_min_por_hora).replace(".", ",")} min`, "minutos de vídeo por hora ativa", "c-accent", "film")}
      ${kpi("Legendas por hora", n0(r.legendas_por_hora), `${n0(r.palavras_por_hora)} palavras · ${n0(r.caracteres_por_hora)} caracteres`, "c-info", "tv")}
      ${kpi("Por minuto de vídeo", fmtDuracao(r.ativo_por_minuto_de_video_s), "de trabalho ativo", "c-violet", "clock")}
      ${kpi("Horas por dia", r.horas_ativas_por_dia ? fmtDuracao(r.horas_ativas_por_dia * 3600) : "—", "ativas, nos dias em que trabalhou", "c-ok", "clock")}
    </section>
    <h3 class="small" style="margin:14px 0 6px">Onde o tempo foi (do começo à entrega)</h3>
    <div class="ritmo-barra" role="img" aria-label="Ativo ${pc(r.ativo_s)}%, parado ${pc(r.parado_s)}%, fora do programa ${pc(r.fora_s)}%">
      <i class="r-ativo" style="width:${pc(r.ativo_s)}%"></i><i class="r-parado" style="width:${pc(r.parado_s)}%"></i><i class="r-fora" style="width:${pc(r.fora_s)}%"></i></div>
    <p class="small"><span class="r-leg r-ativo"></span> Ativo ${fmtDuracao(r.ativo_s)} · <span class="r-leg r-parado"></span> Aberto parado ${fmtDuracao(r.parado_s)} (${String(r.parado_pct).replace(".", ",")}% do tempo aberto)
      · <span class="r-leg r-fora"></span> Fora do programa ${fmtDuracao(r.fora_s)}</p>
    <div class="table-wrap"><table class="table report"><thead><tr><th>Trabalho</th><th class="num">Vídeo</th><th class="num">Legendas</th><th class="num">Palavras</th>
      <th class="num">Ativo</th><th class="num">Parado</th><th class="num">Fora</th><th class="num">Vídeo/hora</th><th class="num">Legendas/hora</th></tr></thead>
      <tbody>${r.amostras.map((a) => `<tr><td>${esc(a.nome)}</td><td class="num mono">${a.video_s ? fmtHMS(a.video_s) : "—"}</td><td class="num mono">${n0(a.legendas)}</td>
        <td class="num mono">${n0(a.palavras)}</td><td class="num mono">${fmtDuracao(a.ativo_s)}</td><td class="num mono">${fmtDuracao(a.parado_s)}</td>
        <td class="num mono">${fmtDuracao(a.fora_s)}</td><td class="num mono">${a.video_min_por_hora ? `${String(a.video_min_por_hora).replace(".", ",")} min` : "—"}</td>
        <td class="num mono">${n0(a.legendas_por_hora)}</td></tr>`).join("")}</tbody></table></div></section>`;
}
