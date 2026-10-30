/* CNT Legendas — lançador (2.27): abre antes do programa, numa janela pequena.
   1) procura a versão mais recente (e, se houver, baixa, instala e reinicia — o programa reabre já no lançador);
   2) confere a licença no servidor e os arquivos do programa;
   3) "Tudo pronto" → abre a janela do programa. */
"use strict";

const TOKEN = document.querySelector('meta[name="token"]').content;
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, url, body) {
  const r = await fetch(url, { method, headers: { "X-Token": TOKEN, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.error || `Erro ${r.status}`), { codigo: j.codigo });
  return j;
}

function mb(bytes) { return `${(bytes / 1048576).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`; }

/* Barra: indeterminada (vai e volta, sem reiniciar o desenho) ou com a porcentagem animada. */
let alvo = 0, mostrado = 0, animando = false;
function barra(pct) {
  const b = $("barra");
  if (pct == null) { b.classList.add("indet"); $("pct").textContent = ""; alvo = mostrado = 0; animando = false; $("fill").style.width = ""; return; }
  b.classList.remove("indet");
  alvo = Math.max(0, Math.min(100, pct));
  if (!animando) { animando = true; requestAnimationFrame(passoAnim); }
}
function passoAnim() {
  if (!animando || $("barra").classList.contains("indet")) { animando = false; return; }
  mostrado += (alvo - mostrado) * 0.18 + (alvo > mostrado ? 0.4 : 0);
  if (mostrado > alvo) mostrado = alvo;
  $("fill").style.width = `${mostrado}%`;
  $("pct").textContent = `${Math.round(mostrado)}%`;
  if (mostrado < alvo - 0.05) requestAnimationFrame(passoAnim); else { mostrado = alvo; animando = false; }
}
async function encher(pct) { barra(pct); for (let i = 0; i < 100 && Math.round(mostrado) < Math.round(pct); i++) await sleep(30); }

function tela(eyebrow, titulo, sub, passo) {
  if (eyebrow != null) $("eyebrow").textContent = eyebrow;
  if (titulo != null) $("titulo").textContent = titulo;
  if (sub != null) $("sub").innerHTML = sub;
  if (passo != null) $("passo").textContent = passo;
}

async function seguirAtualizacao() {
  const inicio = Date.now();
  tela("Seu próximo passo começa aqui", "Preparando tudo.", "Procurando a versão mais recente…", "Verificando atualizações");
  barra(null);
  let u, ultimo = "";
  for (;;) {
    try { u = await api("GET", "/api/atualizacao"); } catch { u = { estado: "sem_conexao" }; }
    const passou = Date.now() - inicio;
    if ((u.estado === "verificando" && passou < 15000) || (u.estado === "parado" && passou < 600)) { await sleep(150); continue; }
    if (u.estado === "verificando") u = { estado: "sem_conexao" };   // o servidor não respondeu em 15 s: abre na versão que tem
    if (u.estado === "disponivel" || u.estado === "baixando") {
      if (ultimo !== "baixando") { ultimo = "baixando"; tela("Atualização encontrada", `Baixando a versão ${u.versao}.`, "", "Baixando"); }
      const pct = Math.round((u.progresso || 0) * 100);
      $("sub").innerHTML = u.tamanho ? `<b>${mb((u.progresso || 0) * u.tamanho)}</b> de ${mb(u.tamanho)}` : "Baixando…";
      barra(pct);
    } else if (u.estado === "aplicando") {
      if (ultimo === "baixando") { $("sub").innerHTML = u.tamanho ? `<b>${mb(u.tamanho)}</b> de ${mb(u.tamanho)}` : ""; await encher(100); }
      if (ultimo !== "aplicando") { ultimo = "aplicando"; tela(null, "Instalando a atualização.", "Não feche o programa.", "Instalando"); barra(null); }
    } else if (u.estado === "pronto") {
      if (ultimo === "baixando") { await encher(100); }
      return reiniciar(u);
    } else if (u.estado === "reiniciando" || u.estado === "instalando") {
      tela(null, "Reiniciando o aplicativo.", "Ele abre de novo em alguns segundos.", "Reiniciando"); barra(null);
      return;
    } else if (u.estado === "erro") {
      return erroAtualizacao(u);
    } else {                                     // atualizado, sem conexão ou parado
      if (Date.now() - inicio < 500) await sleep(500 - (Date.now() - inicio));
      return validar(u.estado === "sem_conexao");
    }
    await sleep(200);
  }
}

async function reiniciar(u) {
  const instalador = u.pacote && u.pacote !== "patch";
  tela("Atualização instalada", "Tudo certo com a versão nova.", "", "Reiniciando");
  barra(100);
  for (let n = 3; n >= 1; n--) {
    $("sub").innerHTML = instalador ? `O instalador abre em <span class="cont">${n}</span>` : `Reiniciando o aplicativo em <span class="cont">${n}</span>`;
    await sleep(1000);
  }
  tela(null, "Reiniciando o aplicativo.", instalador ? "O Windows pode pedir permissão para instalar." : "Ele abre de novo em alguns segundos, já na versão nova.", "Reiniciando");
  barra(null);
  await sleep(1000);
  try { await api("POST", "/api/atualizacao/reiniciar"); } catch { /* o programa já está fechando */ }
  if (!document.querySelector("meta[name=janela]")) esperarVoltar();
}

async function esperarVoltar() {            // no navegador: quando o programa reabrir, a página recarrega
  await sleep(2500);
  for (let i = 0; i < 120; i++) {
    try { const r = await fetch("/api/atualizacao", { headers: { "X-Token": TOKEN } }); if (r.ok) { location.reload(); return; } } catch { /* ainda reiniciando */ }
    await sleep(1000);
  }
}

function erroAtualizacao(u) {
  tela("Não foi possível atualizar agora", "Continuamos na versão atual.",
    `<span class="erro">${esc(u.erro || "A atualização não terminou.")}</span> · código <b>${esc(u.codigo || "ER-RA-440")}</b>`, "Erro na atualização");
  barra(0);
  const a = $("acoes");
  a.hidden = false;
  a.innerHTML = `<button class="p" id="seguir">Continuar na versão atual</button>`;
  $("seguir").focus();
  $("seguir").onclick = () => { a.hidden = true; api("POST", "/api/atualizacao/continuar").catch(() => {}); validar(false); };
}

async function validar(semConexao) {
  tela("Seu próximo passo começa aqui", "Validando esta versão.", "Conferindo a licença e se esta cópia do CNT Legendas está inteira…", "Validando versão");
  barra(35);
  let v = null;
  try { v = await api("POST", "/api/lancador/validar"); } catch { v = null; }
  await encher(85);
  const l = v?.licenca || {};
  const integ = v?.integridade || {};
  if (integ.situacao === "alterada") {
    tela("Atenção", "Esta cópia está alterada.",
      `${integ.alterados.length + integ.faltando.length} arquivo(s) alterado(s) ou faltando · código <b>${esc(integ.codigo)}</b>. Baixe e reinstale pelo site para corrigir.`, "Validando versão");
    const a = $("acoes");
    a.hidden = false;
    a.innerHTML = `<button class="p" id="seguir">Abrir mesmo assim</button>`;
    await new Promise((ok) => { $("seguir").onclick = ok; });
    a.hidden = true;
  }
  const lic = l.modo === "licenciada" ? `Licença ativa${l.valido_ate ? ` até ${new Date(l.valido_ate).toLocaleDateString("pt-BR")}` : ""}`
    : l.modo === "avaliacao" ? "Dia de avaliação" : "Modo grátis";
  tela(null, "Tudo pronto.", `Abrindo o CNT Legendas… <span style="color:var(--mudo)">· ${esc(lic)}${semConexao ? " · sem internet agora" : ""}</span>`, "Concluído");
  await encher(100);
  await sleep(250);
  let r = {};
  try { r = await api("POST", "/api/lancador/pronto"); } catch { /* segue */ }
  if (!r.janela) location.replace("/");
}

$("versao").textContent = `v${document.querySelector('meta[name="versao"]').content}`;
$("sair").onclick = () => { api("POST", "/api/shutdown").catch(() => {}); setTimeout(() => window.close(), 300); };
seguirAtualizacao();
