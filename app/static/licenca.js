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

/* ------------------------------------------------------------ atualizar, reiniciar e bandeja (programa aberto) */

/* Pergunta com botões; devolve a chave do botão escolhido (ou null se fechou). */
function ask(title, body, buttons) {
  return new Promise((resolve) => {
    let done = false;
    const m = modal(title, body, buttons.map(([k, t, cls]) => `<button class="btn ${cls || ""}" data-k="${k}">${esc(t)}</button>`).join(""),
      { onClose: () => { if (!done) resolve(null); } });
    m.ov.addEventListener("click", (e) => {
      const k = e.target.closest("[data-k]")?.dataset.k;
      if (k) { done = true; m.close(); resolve(k); }
    });
  });
}

/* Antes de atualizar ou reiniciar: salvar o editor e avisar dos trabalhos em segundo plano. */
async function prepararSaida(acao) {
  if (location.hash.startsWith("#/editor/") && ED.dirty) {
    const k = await ask("Há alterações não salvas",
      `<p>A legenda aberta no editor tem alterações que ainda não foram salvas. O que fazer antes de ${esc(acao)}?</p>`,
      [["cancelar", "Cancelar"], ["como", "Salvar como…"], ["salvar", "Salvar", "primary"]]);
    if (!k || k === "cancelar") return false;
    if (!(await save(k === "como"))) return false;
  }
  try {
    const { jobs } = await api("GET", "/api/jobs");
    const n = jobs.filter((j) => j.status === "rodando" || j.status === "fila").length;
    if (n) {
      const k = await ask("Trabalhos em andamento",
        `<p>${n === 1 ? "Há 1 trabalho" : `Há ${n} trabalhos`} em segundo plano (transcrição, tradução…). Eles param agora e dá para retomar depois, em “Trabalhos em segundo plano”.</p>`,
        [["cancelar", "Cancelar"], ["ok", `Continuar e ${acao}`, "primary"]]);
    if (k !== "ok") return false;
    }
  } catch { /* sem lista: segue */ }
  return true;
}

async function aplicarAtualizacao() {
  if (!(await prepararSaida("atualizar"))) return;
  try {
    S.state.atualizacao = await api("POST", "/api/atualizacao/aplicar", { hash: location.hash });
  } catch (e) { toast(e.message, true); return; }
  if (S.state.atualizacao.estado === "atualizado") { toast("Você já está na versão mais nova."); return; }
  updateGate();
}

let UPD_DISPENSADA = "";
/* manual = pelo menu (sempre responde); senão, só avisa se houver versão nova ainda não dispensada. */
async function checkUpdate(manual = false) {
  let u;
  try { u = await api("POST", "/api/atualizacao/verificar"); } catch (e) { if (manual) toast(e.message, true); return; }
  if (u.estado === "disponivel") {
    // 2.16: sozinho, não abre nada na frente do trabalho — o ⚠ ao lado do status avisa; ela clica quando quiser
    if (!manual) { if (typeof atualizarStatus === "function") atualizarStatus(); return; }
    const k = await ask(`Nova versão ${u.versao}`,
      `<p>Há uma versão nova do CNT Legendas. Atualizar agora leva alguns segundos: o programa salva o que precisar, fecha e reabre onde você está.</p>
       ${u.notas ? `<details><summary>O que muda</summary><p class="small">${esc(u.notas)}</p></details>` : ""}
       <p class="muted small">Versão atual: ${esc(u.versao_atual)}. Se escolher “Depois”, ela entra na próxima vez que abrir o programa.</p>`,
      [["depois", "Depois"], ["agora", "Atualizar agora", "primary"]]);
    if (k === "agora") return aplicarAtualizacao();
    UPD_DISPENSADA = u.versao;
  } else if (manual) {
    toast(u.estado === "sem_conexao" ? "Não consegui falar com o servidor agora. Tente de novo mais tarde."
      : u.estado === "erro" ? `A atualização não deu certo: ${u.erro}` : `Você já está na versão mais nova (${u.versao_atual}).`, u.estado !== "atualizado");
  }
}

async function reiniciarPrograma() {
  if (!(await prepararSaida("reiniciar"))) return;
  try { await api("POST", "/api/reiniciar", { hash: location.hash }); } catch (e) { toast(e.message, true); return; }
  S.state.atualizacao = { ...(S.state.atualizacao || {}), estado: "reiniciando" };
  updateGate();
}

async function reabrirUltimo() {
  try {
    const d = await api("GET", `/api/obras?mes=${thisMonth()}`);
    if (!d.recent) { toast("Nenhum episódio foi aberto ainda."); return; }
    await openItem(d.recent.item_id);
  } catch (e) { toast(e.message, true); }
}

/* Chamado pelo menu do ícone da bandeja (janela própria). */
window.cntTray = (acao) => {
  if (acao === "reabrir") return reabrirUltimo();
  if (acao === "novo") { location.hash = "#/obra/nova"; return; }
  if (acao === "atualizar") return checkUpdate(true);
  if (acao === "reiniciar") return reiniciarPrograma();
  if (acao === "relatar") return relatarProblema();
};

/* "Relatar um problema": descrição + e-mail para resposta + (se ela deixar) o fim do registro técnico. */
async function relatarProblema() {
  const email0 = getPref("cnt.email-suporte") || "";
  const m = modal("Relatar um problema", `
    <label class="field"><span>O que aconteceu?</span>
      <textarea id="rp-desc" rows="6" placeholder="Ex.: cliquei em Entregar e apareceu um erro vermelho; o arquivo não foi criado." autofocus></textarea></label>
    <label class="field"><span>E-mail para a resposta <em class="muted small">(opcional)</em></span>
      <input type="text" inputmode="email" autocomplete="email" id="rp-email" value="${esc(email0)}" placeholder="voce@exemplo.com"></label>
    <label class="check"><input type="checkbox" id="rp-reg" checked>
      <span>Enviar junto o registro técnico do programa (ajuda a achar o problema).
      <button type="button" class="btn link small" data-r="ver">Ver o que vai</button></span></label>
    <pre id="rp-prev" class="mono small" hidden style="max-height:180px;overflow:auto;white-space:pre-wrap"></pre>
    <p class="muted small">Vão: o que você escreveu, o e-mail, a versão do programa e do Windows e, se marcado, o registro (pode ter nomes de arquivos e pastas).
      Não vão: legendas, vídeos nem as chaves de IA. Detalhes na <a href="${esc((S.state?.licenca?.site || "https://legendas.cntoficial.com.br").replace(/\/$/, ""))}/privacidade" target="_blank" rel="noopener">Política de privacidade</a>.</p>`,
    `<button class="btn" data-r="x">Cancelar</button><button class="btn primary" data-r="ok">Enviar</button>`, { wide: true });
  m.ov.addEventListener("click", async (e) => {
    const r = e.target.closest("[data-r]")?.dataset.r;
    if (!r) return;
    e.preventDefault();
    if (r === "x") return m.close();
    if (r === "ver") {
      const pre = m.$("#rp-prev");
      if (!pre.hidden) { pre.hidden = true; return; }
      try { const g = await api("GET", "/api/suporte/registros"); pre.textContent = g.tamanho ? `(últimos trechos de ${Math.round(g.tamanho / 1024)} KB)\n…${g.fim}` : "O registro está vazio."; pre.hidden = false; }
      catch (err) { toast(err.message, true); }
      return;
    }
    if (r === "ok") {
      const btn = e.target.closest("button"); btn.disabled = true; m.ov.dataset.busy = "1";
      try {
        const email = m.$("#rp-email").value.trim();
        const res = await api("POST", "/api/suporte", { descricao: m.$("#rp-desc").value, email, registros: m.$("#rp-reg").checked });
        if (email) setPref("cnt.email-suporte", email);
        delete m.ov.dataset.busy; m.close();
        toast(`Enviado. Protocolo nº ${res.protocolo}.${email ? " A resposta vai para o seu e-mail." : ""}`);
      } catch (err) { toast(err.message, true); btn.disabled = false; delete m.ov.dataset.busy; }
    }
  });
}

/* Depois de atualizar/reiniciar: volta para onde estava (o editor reabre o mesmo arquivo). */
async function retomarOndeEstava(r) {
  if (!r) return false;
  try {
    if (r.editor) {
      const o = await api("POST", "/api/editor/open", r.editor);
      location.hash = `#/editor/${o.sid}`;
      return true;
    }
    if (r.hash) { location.hash = r.hash; return true; }
  } catch (e) { toast(`Não consegui reabrir onde você estava: ${e.message}`, true); }
  return false;
}

/* Com o programa aberto, procura versão nova a cada 30 minutos. */
setInterval(() => { if (!document.querySelector(".upd-ov")) checkUpdate(false); }, 30 * 60 * 1000);
