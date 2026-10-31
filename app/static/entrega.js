/* CNT Legendas — formato de entrega e prazos (2.15). */
"use strict";

const FORMATOS = [
  ["srt", "SubRip (.srt)"], ["vtt", "WebVTT (.vtt)"], ["ttml", "TTML / DFXP — IMSC (.ttml)"], ["ass", "Advanced SubStation (.ass)"],
];
const ORIGEM_FORMATO = { projeto: "do projeto", cliente: "do cliente", equipe: "da equipe", global: "das Configurações", padrao: "padrão" };

/* <option>s do formato. `herda` = texto da primeira opção (vazio = herda do nível de cima); sem herda, só os formatos. */
function formatoOptions(valor, herda) {
  const v = valor || "";
  return (herda ? `<option value="" ${v ? "" : "selected"}>${esc(herda)}</option>` : "")
    + FORMATOS.map(([id, nome]) => `<option value="${id}" ${id === v ? "selected" : ""}>${esc(nome)}</option>`).join("");
}

/* ------------------------------------------------------------ prazos */

function prazoData(iso) {
  const [a, m, d] = String(iso || "").split("-").map(Number);
  return a ? new Date(a, m - 1, d) : null;
}

/* "hoje", "amanhã", "em 3 dias", "atrasado 2 dias" — e se é urgente (até amanhã). */
function prazoTexto(iso) {
  const dt = prazoData(iso);
  if (!dt) return { texto: "", nivel: "" };
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  const dias = Math.round((dt - hoje) / 86400000);
  const data = dt.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  if (dias < 0) return { texto: `${data} · atrasado ${-dias} dia${dias === -1 ? "" : "s"}`, nivel: "atrasado" };
  if (dias === 0) return { texto: `${data} · hoje`, nivel: "urgente" };
  if (dias === 1) return { texto: `${data} · amanhã`, nivel: "urgente" };
  return { texto: `${data} · em ${dias} dias`, nivel: dias <= 3 ? "perto" : "" };
}

/* Mostra no topo a próxima entrega. Discreto: um texto pequeno; clicar abre o projeto. */
async function atualizarPrazoTopo() {
  const el = document.getElementById("prazo-topo");
  if (!el) return;
  let r;
  try { r = await api("GET", "/api/prazos"); } catch { return; }
  const p = (r.prazos || [])[0];
  if (!p) { el.hidden = true; el.innerHTML = ""; return; }
  const t = prazoTexto(p.prazo);
  el.hidden = false;
  el.className = `prazo-topo ${t.nivel}`;
  el.href = `#/obra/${p.obra_id}`;
  el.title = (r.prazos || []).slice(0, 6).map((x) => `${x.obra} — ${x.label}: ${prazoTexto(x.prazo).texto}`).join("\n");
  el.innerHTML = `<span class="muted">Próxima entrega</span> <b>${esc(p.obra)}${p.kind === "serie" ? ` · ${esc(p.label)}` : ""}</b> <span>${esc(t.texto)}</span>`;
}

/* ------------------------------------------------------------ antes de entregar (2.26)
   Nota de qualidade e comparação com a entrega anterior (ou, na primeira, com o original), com as mudanças
   destacadas. Depois, a tela de entrega de sempre (com os relatórios). */

function difPalavras(a, b) {
  const ta = String(a || "").split(/(\s+)/), tb = String(b || "").split(/(\s+)/);
  const n = ta.length, m = tb.length;
  if (n * m > 40000) return [`<del>${esc(a)}</del>`, `<ins>${esc(b)}</ins>`];
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = ta[i] === tb[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0, ra = "", rb = "";
  while (i < n && j < m) {
    if (ta[i] === tb[j]) { ra += esc(ta[i]); rb += esc(tb[j]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) { ra += /\S/.test(ta[i]) ? `<del>${esc(ta[i])}</del>` : esc(ta[i]); i++; }
    else { rb += /\S/.test(tb[j]) ? `<ins>${esc(tb[j])}</ins>` : esc(tb[j]); j++; }
  }
  while (i < n) { ra += /\S/.test(ta[i]) ? `<del>${esc(ta[i])}</del>` : esc(ta[i]); i++; }
  while (j < m) { rb += /\S/.test(tb[j]) ? `<ins>${esc(tb[j])}</ins>` : esc(tb[j]); j++; }
  return [ra, rb].map((x) => x.replace(/\n/g, "<br>"));
}

function notaHtml(nota) {
  const cls = nota.valor >= 90 ? "otima" : nota.valor >= 75 ? "boa" : nota.valor >= 60 ? "media" : "baixa";
  return `<div class="nq ${cls}"><div class="nq-num"><b class="tnum">${nota.valor}</b><span>/100</span></div>
    <div class="nq-txt"><b>Nota de qualidade: ${esc(nota.faixa)}</b>
      ${nota.motivos.length ? `<ul>${nota.motivos.map((m) => `<li>${esc(m.texto)}: ${m.legendas} ${m.tipo === "ortografia" ? "palavra(s)" : "legenda(s)"} <span class="muted">(−${m.pontos} pontos)</span></li>`).join("")}</ul>`
        : `<p class="muted small">Nenhum problema pelas regras do cliente.</p>`}</div></div>`;
}

async function openEntregaPrevia() {
  if (!ED.cues.length) { toast("Não há legendas para entregar.", true); return; }
  let p;
  try { p = await api("POST", `/api/editor/${ED.sid}/entrega/previa`, { cues: sortedCues() }); } catch (e) { toast(e.message, true); return; }
  const base = p.base.tipo === "entrega" ? `a entrega anterior${p.base.quando ? ` (${esc(new Date(p.base.quando.replace(" ", "T")).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }))})` : ""}`
    : p.base.tipo === "original" ? `o arquivo original${p.base.nome ? ` (${esc(p.base.nome)})` : ""}` : "";
  const r = p.resumo;
  const chips = p.modo === "sem_base" ? "" : `<div class="row cmp-chips">
      ${p.modo !== "traducao" ? `<button class="ds-chip" data-f="texto"><b>${r.texto}</b> texto alterado</button>` : ""}
      <button class="ds-chip" data-f="tempo"><b>${r.so_tempo}</b> só tempo</button>
      <button class="ds-chip" data-f="entrou"><b>${r.novas}</b> nova(s)</button>
      <button class="ds-chip" data-f="saiu"><b>${r.apagadas}</b> apagada(s)</button>
      <button class="ds-chip on" data-f="todas">Todas</button><span class="muted small">${r.iguais} sem alteração</span></div>`;
  const linha = (d, k) => {
    const tipo = d.tipo === "mudou" ? (d.so_tempo ? "tempo" : "texto") : d.tipo;
    const [a, b] = d.tipo === "mudou" && !d.so_tempo ? difPalavras(d.antes.text, d.depois.text)
      : [d.antes ? esc(d.antes.text).replace(/\n/g, "<br>") : "", d.depois ? esc(d.depois.text).replace(/\n/g, "<br>") : ""];
    const tempo = (c) => c ? `<span class="tnum muted small">${esc(fmtTC(c.start))} → ${esc(fmtTC(c.end))}</span>` : "";
    const tempoMudou = d.antes && d.depois && (Math.abs(d.antes.start - d.depois.start) > 0.0005 || Math.abs(d.antes.end - d.depois.end) > 0.0005);
    return `<tr class="cmp-${tipo}" data-t="${tipo}" data-k="${k}" ${d.n ? `data-n="${d.n}"` : ""}>
      <td class="tnum">${d.n ?? "—"}</td>
      <td>${d.antes ? `${tempo(d.antes)}<div>${a}</div>` : '<i class="muted">não tinha</i>'}</td>
      <td>${d.depois ? `<span class="${tempoMudou ? "cmp-tempo-mudou" : ""}">${tempo(d.depois)}</span><div>${b}</div>` : '<i class="muted">apagada</i>'}</td></tr>`;
  };
  const m = modal("Antes de entregar", `
    ${notaHtml(p.nota)}
    <h3 class="upd-sub">${p.modo === "sem_base" ? "Comparação" : `O que mudou em relação a ${base}`}</h3>
    ${p.texto_resumo.map((t) => `<p class="small" style="margin:2px 0">${esc(t)}</p>`).join("")}
    ${chips}
    ${p.diferencas.length ? `<div class="ver-wrap cmp-wrap"><table class="table ver-dif cmp"><thead><tr><th>#</th><th>Antes</th><th>Agora</th></tr></thead>
      <tbody>${p.diferencas.map(linha).join("")}</tbody></table></div>
      ${p.total_diferencas > p.diferencas.length ? `<p class="muted small">Mostrando ${p.diferencas.length} de ${p.total_diferencas}. O relatório de alterações tem todas.</p>` : ""}
      <p class="muted small">Clique numa linha para ver a legenda no editor. <ins>Verde</ins> entrou, <del>vermelho</del> saiu.</p>`
      : p.modo === "sem_base" ? "" : `<p class="note ok">Nenhuma diferença.</p>`}`,
    `<button class="btn" data-x="cancelar">Cancelar</button><button class="btn primary" data-x="seguir">Continuar para a entrega</button>`, { wide: true });
  m.ov.addEventListener("click", (e) => {
    const f = e.target.closest("[data-f]")?.dataset.f;
    if (f) {
      m.ov.querySelectorAll("[data-f]").forEach((b) => b.classList.toggle("on", b.dataset.f === f));
      m.ov.querySelectorAll("tr[data-t]").forEach((tr) => { tr.hidden = f !== "todas" && tr.dataset.t !== f; });
      return;
    }
    const tr = e.target.closest("tr[data-n]");
    if (tr) { m.close(); selectCue(Number(tr.dataset.n) - 1); return; }
    const x = e.target.closest("[data-x]")?.dataset.x;
    if (x === "cancelar") m.close();
    if (x === "seguir") { m.close(); openDeliver({ temBase: p.modo !== "sem_base", nota: p.nota }); }
  });
}
