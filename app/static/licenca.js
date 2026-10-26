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

/* ------------------------------------------------------------ atualização ao abrir (2.24)
   Ao abrir, a tela mostra cada passo — procurando, baixando (com %), instalando — e, com a versão nova
   instalada, conta 3, 2, 1 antes de fechar e reabrir. Assim o fechar-e-abrir não parece defeito.
   Na abertura seguinte, mostra se deu certo (com o que mudou) ou o erro com o código. */

const UPD_BUSY = ["verificando", "disponivel", "baixando", "aplicando", "pronto", "reiniciando", "instalando"];
const UPD_MIN_MS = 900;                       // cada passo fica na tela pelo menos isso (para dar para ler)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function updOverlay() {
  let ov = document.querySelector(".upd-ov");
  if (!ov) {
    ov = document.createElement("div");
    ov.className = "upd-ov";
    ov.setAttribute("role", "alertdialog");
    ov.setAttribute("aria-live", "polite");
    ov.setAttribute("aria-label", "Atualização do CNT Legendas");
    document.body.appendChild(ov);
  }
  return ov;
}

const UPD_PASSOS = ["Procurar", "Baixar", "Instalar", "Reiniciar"];
function updDraw(ov, { passo, titulo, texto = "", pct = null, versaoAtual = "", extra = "" }) {
  ov.innerHTML = `<div class="upd-box">
    <ol class="upd-passos" aria-label="Etapas da atualização">${UPD_PASSOS.map((n, i) =>
      `<li class="${i < passo ? "feito" : i === passo ? "atual" : ""}" ${i === passo ? 'aria-current="step"' : ""}>${esc(n)}</li>`).join("")}</ol>
    <h2>${esc(titulo)}</h2>${texto ? `<p class="muted">${texto}</p>` : ""}
    ${pct != null ? `<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div>
      <p class="upd-pct tnum">${pct}%</p>` : extra ? "" : `<div class="upd-spin" aria-hidden="true"></div>`}
    ${extra}
    ${versaoAtual ? `<p class="muted small">Versão atual: ${esc(versaoAtual)}</p>` : ""}</div>`;
}

async function updateGate() {
  let u = S.state?.atualizacao;
  if (!u || !UPD_BUSY.includes(u.estado) && u.estado !== "erro") { refreshLicenseSoon(); await mostrarResultadoDaAtualizacao(); return; }
  const ov = updOverlay();
  let ultimo = "", desde = 0;
  const passo = async (estado) => {           // tempo mínimo de cada passo antes de trocar
    if (estado !== ultimo) {
      const falta = UPD_MIN_MS - (Date.now() - desde);
      if (ultimo && falta > 0) await sleep(falta);
      ultimo = estado; desde = Date.now();
    }
  };
  while (true) {
    const novo = u.versao ? `a versão ${u.versao}` : "a versão nova";
    if (u.estado === "verificando") {
      await passo("verificando");
      updDraw(ov, { passo: 0, titulo: "Procurando atualizações…", versaoAtual: u.versao_atual });
    } else if (u.estado === "disponivel" || u.estado === "baixando") {
      await passo("baixando");
      const pct = Math.round((u.progresso || 0) * 100);
      updDraw(ov, { passo: 1, titulo: `Baixando ${novo}`, pct,
        texto: u.tamanho ? `${fmtSize(Math.round((u.progresso || 0) * u.tamanho))} de ${fmtSize(u.tamanho)}` : "", versaoAtual: u.versao_atual });
    } else if (u.estado === "aplicando") {
      await passo("aplicando");
      updDraw(ov, { passo: 2, titulo: "Instalando a atualização…", texto: "Não feche o programa.", versaoAtual: u.versao_atual });
    } else if (u.estado === "pronto") {
      await passo("pronto");
      await contagemEReinicio(ov, u);
      return;
    } else if (u.estado === "reiniciando" || u.estado === "instalando") {
      updDraw(ov, { passo: 3, titulo: "Reiniciando o aplicativo…", texto: u.estado === "instalando"
        ? "O instalador está rodando (o Windows pode pedir permissão). O programa reabre sozinho quando terminar." : "Ele abre de novo em alguns segundos." });
      if (u.estado === "reiniciando") await waitRestartAndReload();
      return;
    } else if (u.estado === "erro") {
      await passo("erro");
      await erroNaAtualizacao(ov, u);
      break;
    } else {                                   // atualizado, sem conexão ou parado: segue para o programa
      await passo("fim");
      break;
    }
    await sleep(400);
    try { u = await api("GET", "/api/atualizacao"); } catch { u = { ...u, estado: "reiniciando" }; }
  }
  ov.remove();
  refreshLicenseSoon();
  await mostrarResultadoDaAtualizacao();
}

/* Versão nova instalada: 3, 2, 1 → "Reiniciando o aplicativo…" (1 s) → fecha e reabre. */
async function contagemEReinicio(ov, u) {
  const instalador = u.pacote && u.pacote !== "patch";
  for (let n = 3; n >= 1; n--) {
    updDraw(ov, { passo: 3, titulo: "Atualização instalada", texto: instalador
      ? `O instalador da versão ${esc(u.versao || "")} abre em <b class="tnum">${n}</b>…`
      : `Reiniciando o aplicativo em <b class="tnum">${n}</b>…`, extra: `<div class="upd-contagem tnum" aria-hidden="true">${n}</div>` });
    await sleep(1000);
  }
  updDraw(ov, { passo: 3, titulo: "Reiniciando o aplicativo…", texto: "Ele abre de novo em alguns segundos, já na versão nova." });
  await sleep(1000);
  try { await api("POST", "/api/atualizacao/reiniciar"); } catch { /* o servidor já pode estar fechando */ }
  if (!instalador) await waitRestartAndReload();
}

async function erroNaAtualizacao(ov, u) {
  await new Promise((ok) => {
    updDraw(ov, { passo: 1, titulo: "Não foi possível atualizar agora",
      texto: `${esc(u.erro || "A atualização não terminou.")}<br><span class="small">O programa continua na versão atual e tenta de novo na próxima vez que abrir.</span>`,
      extra: `<p class="upd-codigo">Código do erro: <b class="mono">${esc(u.codigo || "ER-RA-440")}</b></p>
        <div class="row" style="justify-content:center"><button class="btn primary" id="upd-seguir">Continuar na versão atual</button></div>`,
      versaoAtual: u.versao_atual });
    const b = document.getElementById("upd-seguir");
    b.focus();
    b.addEventListener("click", ok, { once: true });
  });
  try { await api("POST", "/api/atualizacao/continuar"); } catch { /* segue */ }
}

/* Depois de reabrir: "atualizado com sucesso" (com o que mudou) ou o erro com o código. */
async function mostrarResultadoDaAtualizacao() {
  let r;
  try { r = await api("GET", "/api/atualizacao/resultado"); } catch { return; }
  const res = r.resultado;
  if (!res) return;
  if (res.situacao === "sucesso" && !r.mostrar_novidades) { api("POST", "/api/atualizacao/resultado/visto", {}).catch(() => {}); return; }
  const ok = res.situacao === "sucesso";
  const lista = (res.novidades || []).length
    ? `<ul class="upd-novidades">${res.novidades.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`
    : `<p class="muted">Correções e melhorias internas.</p>`;
  const corpo = ok
    ? `<p><b>O CNT Legendas foi atualizado com sucesso</b> para a versão ${esc(res.versao)}${res.de ? ` (antes: ${esc(res.de)})` : ""}.</p>
       <h3 class="upd-sub">O que mudou</h3>${lista}
       <label class="check" style="margin-top:14px"><input type="checkbox" id="upd-nao-mostrar"> Não mostrar esta tela nas próximas atualizações</label>
       <p class="muted small">Dá para ligar de novo em Configurações › Novidades da versão.</p>`
    : `<p><b>A atualização não foi concluída.</b></p><p>${esc(res.mensagem || "")}</p>
       <p class="upd-codigo">Código do erro: <b class="mono">${esc(res.codigo || "ER-RA-441")}</b></p>
       <p class="muted small">Se acontecer de novo, use “Relatar um problema” e informe esse código.</p>`;
  let nao = false;
  await new Promise((fim) => {
    const m = modal(ok ? "Atualização concluída" : "Erro na atualização", corpo,
      `<button class="btn primary" data-k="ok" autofocus>${ok ? "Começar a usar" : "Entendi"}</button>`, { onClose: fim });
    m.ov.addEventListener("change", (e) => { if (e.target.id === "upd-nao-mostrar") nao = e.target.checked; });
    m.ov.querySelector('[data-k="ok"]').addEventListener("click", () => m.close());
  });
  try {
    const v = await api("POST", "/api/atualizacao/resultado/visto", { nao_mostrar: nao });
    if (S.state?.settings) S.state.settings.mostrar_novidades = v.mostrar_novidades;
  } catch { /* tenta de novo na próxima abertura */ }
}

async function waitRestartAndReload() {
  await sleep(2500);
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch("/api/atualizacao", { headers: { "X-Token": TOKEN } });
      if (r.ok) { const u = await r.json(); if (!["reiniciando", "pronto"].includes(u.estado)) { location.reload(); return; } }
    } catch { /* ainda reiniciando */ }
    await sleep(1000);
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
