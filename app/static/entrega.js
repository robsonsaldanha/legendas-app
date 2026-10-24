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
