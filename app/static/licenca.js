/* CNT Legendas — licença (avaliação, ativação, recursos pagos) e atualização obrigatória. */
"use strict";

const LIC_MOTIVO = {
  nunca: "Ainda não foi possível começar a avaliação (o programa precisa de internet na primeira vez).",
  avaliacao_encerrada: "O dia de avaliação terminou.",
  vencida: "A licença venceu. Renove para voltar a usar as funções pagas.",
  revogada: "A licença foi cancelada.",
  sem_conexao: "Faz mais de 30 dias que o programa não confere a licença. Conecte à internet e reabra.",
  computador_removido: "Este computador foi tirado da licença.",
  outro_computador: "A licença guardada é de outro computador.",
  invalida: "A licença guardada não é válida.",
  nao_encontrada: "A licença não foi encontrada no servidor.",
};

function licInfo() { return (S.state && S.state.licenca) || { modo: "gratis", recursos: [] }; }
function siteUrl() { return licInfo().site || "https://legendas.cntoficial.com.br"; }

function horasRestantes(iso) {
  if (!iso) return null;
  return Math.max(0, (new Date(iso) - Date.now()) / 3600e3);
}

/* Etiqueta na barra de cima: avaliação (quanto falta) ou modo grátis. Licenciada não mostra nada. */
function drawLicenseBadge() {
  const el = document.getElementById("lic-badge");
  if (!el) return;
  const l = licInfo();
  if (l.modo === "licenciada") { el.innerHTML = ""; return; }
  const h = horasRestantes(l.valido_ate);
  const txt = l.modo === "avaliacao"
    ? `Avaliação: ${h >= 1 ? `${Math.floor(h)} h` : `${Math.max(1, Math.round(h * 60))} min`} restantes`
    : "Modo grátis";
  el.innerHTML = `<button type="button" class="lic-pill ${l.modo}" data-lic="open" title="Licença">${esc(txt)}</button>`;
  el.querySelector("button").onclick = () => openLicenseModal();
}

function showLicenseBlocked(msg, recurso) {
  const m = modal("Recurso da licença paga", `<p>${esc(msg)}</p>
    <p class="muted small">No modo grátis você continua criando projetos e traduzindo à mão no editor.</p>`,
    `<a class="btn" href="${esc(siteUrl())}/#planos" target="_blank" rel="noopener">Ver os planos</a>
     <button class="btn primary" data-l="ativar">Tenho um código</button>`);
  m.ov.onclick = (e) => {
    if (e.target === m.ov) return m.close();
    if (e.target.closest("[data-l=ativar]")) { m.close(); openLicenseModal(); }
  };
}

function openLicenseModal() {
  const l = licInfo();
  const fim = l.valido_ate ? new Date(l.valido_ate).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : null;
  const estado = l.modo === "licenciada"
    ? `<p><b>Licença ${esc(l.licenca)}</b> · ${esc(l.titular)}<br>Plano ${esc(l.plano)} · ${fim ? `válida até ${esc(fim)}` : "sem vencimento"}</p>`
    : l.modo === "avaliacao"
      ? `<p><b>Avaliação</b>: tudo liberado até ${esc(fim || "—")}.</p>`
      : `<p><b>Modo grátis.</b> ${esc(LIC_MOTIVO[l.motivo] || "")}</p>`;
  const m = modal("Licença", `${estado}
    <label class="field"><span>Código de ativação (chega por e-mail depois da compra)</span>
      <input type="text" id="lic-code" placeholder="CNTL-XXXX-XXXX-XXXX-XXXX" autocomplete="off" spellcheck="false" autofocus></label>
    <p class="muted small">Cada código ativa um computador, uma vez. O computador precisa estar na internet.
      Para comprar: <a href="${esc(siteUrl())}/comprar" target="_blank" rel="noopener">${esc(siteUrl().replace("https://", ""))}</a></p>
    <p class="note err" id="lic-err" hidden></p>`,
    `<button class="btn" data-l="x">Fechar</button><button class="btn" data-l="conferir">Conferir de novo</button><button class="btn primary" data-l="ok">Ativar</button>`);
  m.ov.onclick = async (e) => {
    const k = e.target.closest("[data-l]")?.dataset.l;
    if (e.target === m.ov || k === "x") return m.close();
    const err = m.$("#lic-err");
    try {
      if (k === "ok") {
        S.state.licenca = await api("POST", "/api/licenca/ativar", { codigo: m.$("#lic-code").value });
        m.close(); drawLicenseBadge(); toast("Licença ativada neste computador. Obrigado!");
        router();
      }
      if (k === "conferir") {
        S.state.licenca = await api("POST", "/api/licenca/conferir");
        m.close(); drawLicenseBadge(); toast(S.state.licenca.modo === "gratis" ? (LIC_MOTIVO[S.state.licenca.motivo] || "Modo grátis.") : "Licença conferida.");
      }
    } catch (ex) { if (ex.message) { err.textContent = ex.message; err.hidden = false; } }
  };
}

/* A licença é conferida em segundo plano ao abrir: atualiza a etiqueta quando terminar. */
async function refreshLicenseSoon() {
  for (const wait of [2500, 6000, 15000]) {
    await new Promise((r) => setTimeout(r, wait));
    try { S.state.licenca = await api("GET", "/api/licenca"); drawLicenseBadge(); } catch { /* fechado */ }
  }
}

/* ------------------------------------------------------------ atualização obrigatória */

const UPD_BUSY = ["verificando", "disponivel", "baixando", "aplicando", "reiniciando", "instalando"];

async function updateGate() {
  let u = S.state?.atualizacao;
  if (!u || u.estado === "parado") { refreshLicenseSoon(); return; }
  let ov = null;
  const draw = () => {
    const pct = Math.round((u.progresso || 0) * 100);
    const t = {
      verificando: ["Procurando atualizações…", ""],
      disponivel: [`Nova versão ${u.versao}`, "Preparando o download…"],
      baixando: [`Baixando a versão ${u.versao}`, `${pct}%${u.tamanho ? ` de ${fmtSize(u.tamanho)}` : ""}`],
      aplicando: [`Instalando a versão ${u.versao}`, "Quase lá…"],
      reiniciando: ["Reiniciando o CNT Legendas", "A página recarrega sozinha."],
      instalando: [`Instalando a versão ${u.versao}`, "O instalador está rodando. O programa reabre sozinho quando terminar; pode fechar esta página."],
    }[u.estado] || ["", ""];
    if (!ov) {
      ov = document.createElement("div");
      ov.className = "upd-ov";
      ov.setAttribute("role", "alertdialog");
      ov.setAttribute("aria-live", "polite");
      document.body.appendChild(ov);
    }
    ov.innerHTML = `<div class="upd-box"><h2>${esc(t[0])}</h2><p class="muted">${esc(t[1])}</p>
      ${u.estado === "baixando" ? `<div class="bar"><i style="width:${pct}%"></i></div>` : `<div class="upd-spin" aria-hidden="true"></div>`}
      ${u.notas && u.estado !== "verificando" ? `<details><summary>O que muda</summary><p class="small">${esc(u.notas)}</p></details>` : ""}
      <p class="muted small">Versão atual: ${esc(u.versao_atual)}</p></div>`;
  };
  while (UPD_BUSY.includes(u.estado)) {
    draw();
    if (u.estado === "reiniciando") { await waitRestartAndReload(); return; }
    if (u.estado === "instalando") return;           // o instalador fecha e reabre o programa
    await new Promise((r) => setTimeout(r, 600));
    try { u = await api("GET", "/api/atualizacao"); } catch { u = { ...u, estado: "reiniciando" }; }
  }
  if (u.estado === "erro") toast(`A atualização não deu certo: ${u.erro}. O programa segue na versão atual; ela será tentada de novo na próxima abertura.`, true);
  ov?.remove();
  refreshLicenseSoon();
}

async function waitRestartAndReload() {
  await new Promise((r) => setTimeout(r, 2500));
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch("/api/atualizacao", { headers: { "X-Token": TOKEN } });
      if (r.ok) { const u = await r.json(); if (u.estado !== "reiniciando") { location.reload(); return; } }
    } catch { /* ainda reiniciando */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  location.reload();
}
