/* CNT Legendas — status da conexão, alerta de atualização e depuração (2.16).
   O programa faz os pings (servidor :00/:30, Google :15/:45); a página só pergunta o resultado a cada 5 s. */
"use strict";

const NET = { info: null, html: "", updVisto: "", recuperadoVisto: false };

function netHtml(c) {
  if (!c) return "";
  const cls = { online: "ok", lenta: "warn", verificando: "neutro", reconectando: "warn", manutencao: "warn" }[c.estado] || "err";
  const sub = c.estado === "online" || c.estado === "lenta" ? `${c.ms} ms`
    : c.estado === "sem_internet" ? "sem internet" : c.estado === "servidor_fora" ? "servidor não responde"
    : c.estado === "manutencao" ? "em manutenção" : "";
  const off = c.licenca_offline_ate ? `\nTrabalhando sem servidor: a licença vale até ${new Date(c.licenca_offline_ate).toLocaleDateString("pt-BR")}.` : "";
  const dica = `${c.motivo}${c.codigo ? ` (código ${c.codigo})` : ""}${off}\n\n${(c.detalhe || []).join("\n")}`;
  const dep = c.depuracao?.ativo ? `<button type="button" class="net-dep" data-net="dep" title="Modo de depuração ligado: registrando tudo. Clique para ver.">● Depuração ${fmtMinSeg(c.depuracao.restante_s)}</button>` : "";
  const rec = c.depuracao?.recuperados?.length && !NET.recuperadoVisto
    ? `<button type="button" class="net-dep" data-net="rec" title="O programa fechou inesperadamente enquanto a depuração estava ligada. O relatório foi guardado; clique para abrir a pasta.">Relatório de depuração pronto</button>` : "";
  const upd = c.atualizacao?.disponivel
    ? `<button type="button" class="net-upd" data-net="upd" title="Versão nova ${esc(c.atualizacao.versao)} disponível. Clique quando quiser atualizar." aria-label="Atualização disponível">⚠</button>` : "";
  return `${rec}${dep}${upd}<span class="net ${cls}" tabindex="0" title="${esc(dica)}" aria-label="${esc(c.texto)}: ${esc(c.motivo)}">
    <i class="net-dot" aria-hidden="true"></i>${esc(c.texto)}${sub ? ` <span class="net-sub">· ${esc(sub)}</span>` : ""}</span>`;
}

function fmtMinSeg(s) { return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }

async function atualizarStatus() {
  let c;
  try { c = await api("GET", "/api/conexao"); } catch { c = { estado: "app", texto: "Programa sem resposta", motivo: "O CNT Legendas não respondeu. Ele foi fechado?", codigo: "ER-RA-500", detalhe: [] }; }
  NET.info = c;
  NET.html = netHtml(c);
  document.querySelectorAll(".net-slot").forEach((el) => { el.innerHTML = NET.html; });
  DEPUR.ativo = !!c.depuracao?.ativo;
  if (DEPUR.ativo && !DEPUR.timer) DEPUR.timer = setInterval(enviarEventos, 1000);
  if (!DEPUR.ativo && DEPUR.timer) { clearInterval(DEPUR.timer); DEPUR.timer = 0; DEPUR.fila = []; }
  const cfg = document.getElementById("dep-estado");
  if (cfg) cfg.textContent = depTexto(c.depuracao);
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-net]");
  if (!b) return;
  const k = b.dataset.net;
  if (k === "upd") return checkUpdate(true);
  if (k === "dep") { location.hash = "#/configuracoes"; return; }
  if (k === "rec") { NET.recuperadoVisto = true; api("POST", "/api/depuracao/abrir").catch((err) => toast(err.message, true)); atualizarStatus(); }
});

/* ------------------------------------------------------------ depuração: o que acontece na tela */

const DEPUR = { ativo: false, timer: 0, fila: [] };

function depTexto(d) {
  if (!d) return "";
  if (d.ativo) return `Ligado: registrando tudo por mais ${fmtMinSeg(d.restante_s)} (${d.acoes} ações). Pasta: ${d.pasta}`;
  if (d.ultimo_zip) return `Último relatório: ${d.ultimo_zip}`;
  return `Desligado. Os relatórios ficam em ${d.logs}`;
}

function depEvento(tipo, acao, dados) {
  if (!DEPUR.ativo) return;
  DEPUR.fila.push({ tipo, acao, dados: dados || {}, hora: new Date().toLocaleTimeString("pt-BR") + "." + String(Date.now() % 1000).padStart(3, "0") });
  if (DEPUR.fila.length > 300) DEPUR.fila.shift();
}

async function enviarEventos() {
  if (!DEPUR.fila.length) return;
  const eventos = DEPUR.fila.splice(0, 200);
  try { await fetch("/api/depuracao/eventos", { method: "POST", headers: { "X-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify({ eventos }) }); }
  catch { /* programa fechando */ }
}

function descreverAlvo(el) {
  const d = {};
  for (const [k, v] of Object.entries(el.dataset || {})) if (k.length < 20) d[k] = String(v).slice(0, 80);
  const txt = (el.getAttribute("aria-label") || el.title || el.textContent || el.value || "").replace(/\s+/g, " ").trim().slice(0, 80);
  return { elemento: el.tagName.toLowerCase(), id: el.id || undefined, texto: txt, ...d, tela: location.hash || "#/inicio" };
}

document.addEventListener("click", (e) => {
  if (!DEPUR.ativo) return;
  const el = e.target.closest("button, a, [data-action], [data-ed], [data-o], [data-x], [role=menuitem], tr[data-i], input[type=checkbox], label");
  if (el) depEvento("clique", `clicou em “${descreverAlvo(el).texto || el.tagName}”`, descreverAlvo(el));
}, true);
document.addEventListener("change", (e) => {
  if (!DEPUR.ativo) return;
  const el = e.target;
  if (!el || !el.tagName) return;
  const sensivel = el.type === "password" || /chave|key|senha|token/i.test(el.id + el.name);
  const valor = sensivel ? "***" : el.type === "checkbox" ? el.checked : el.tagName === "TEXTAREA" ? `(${el.value.length} caracteres)` : String(el.value).slice(0, 120);
  depEvento("campo", `mudou ${el.id || el.name || el.tagName.toLowerCase()}`, { valor, tela: location.hash });
}, true);
document.addEventListener("keydown", (e) => {
  if (!DEPUR.ativo || !(e.ctrlKey || e.metaKey || e.altKey || /^F\d+$/.test(e.key))) return;
  depEvento("atalho", `tecla ${[e.ctrlKey && "Ctrl", e.altKey && "Alt", e.shiftKey && "Shift", e.key].filter(Boolean).join("+")}`, { tela: location.hash });
}, true);
window.addEventListener("hashchange", () => depEvento("navegacao", `foi para ${location.hash}`));
window.addEventListener("error", (e) => depEvento("erro-tela", e.message, { arquivo: e.filename, linha: e.lineno, coluna: e.colno }));
window.addEventListener("unhandledrejection", (e) => depEvento("erro-tela", String(e.reason?.message || e.reason), {}));

async function alternarDepuracao(ligar) {
  try {
    const r = await api("POST", "/api/depuracao", { ligar });
    if (ligar) toast("Modo de depuração ligado por 5 minutos. Faça o que deu problema; tudo fica registrado.");
    else toast(r.zip ? `Relatório salvo: ${r.zip}` : "Depuração desligada.");
    await atualizarStatus();
    if (!ligar && r.zip) api("POST", "/api/depuracao/abrir").catch(() => {});
  } catch (e) { toast(e.message, true); }
}

setInterval(atualizarStatus, 5000);
atualizarStatus();
