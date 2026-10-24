/* CNT Legendas — dicas discretas debaixo do texto (2.15): memória de tradução e ortografia.
   Nada pula na tela: é uma linha pequena; só muda se ela clicar. Histórico de versões também fica aqui. */
"use strict";

const DICAS = { tm: new Map(), orto: new Map(), ortoOk: true, timer: 0, pedindo: "" };

/* ------------------------------------------------------- memória de tradução */

async function carregarMemoria() {
  DICAS.tm = new Map();
  if (!ED.sid || !ED.hasOrig) return;
  const origs = [...new Set(ED.cues.map((c) => c.orig).filter((o) => o && o.trim()))];
  if (!origs.length) return;
  try {
    const r = await api("POST", `/api/editor/${ED.sid}/memoria`, { origs });
    origs.forEach((o, i) => { if (r.sugestoes[i]) DICAS.tm.set(o, r.sugestoes[i]); });
    desenharDicas();
  } catch { /* sem memória: nada a mostrar */ }
}

function sugestaoMemoria(c) {
  const s = c?.orig ? DICAS.tm.get(c.orig) : null;
  if (!s) return null;
  const norm = (t) => String(t || "").replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim().toLowerCase();
  return norm(s.trad) === norm(c.text) ? null : s;
}

/* ------------------------------------------------------------- ortografia */

function ortografiaLigada() { return DICAS.ortoOk && EDP.dicas?.ortografia !== false; }
function memoriaLigada() { return EDP.dicas?.memoria !== false; }

function agendarOrtografia() {
  clearTimeout(DICAS.timer);
  if (!ortografiaLigada()) return;
  DICAS.timer = setTimeout(conferirOrtografia, 450);
}

async function conferirOrtografia() {
  const c = ED.cues[ED.sel];
  if (!c || !ortografiaLigada()) return;
  const texto = c.text;
  if (DICAS.orto.has(texto) || DICAS.pedindo === texto) { desenharDicas(); return; }
  DICAS.pedindo = texto;
  try {
    const r = await api("POST", "/api/ortografia", { sid: ED.sid, texto, lang: ED.language });
    if (!r.disponivel) { DICAS.ortoOk = false; return; }
    if (DICAS.orto.size > 400) DICAS.orto.clear();
    DICAS.orto.set(texto, r.erros);
  } catch { return; } finally { DICAS.pedindo = ""; }
  if (ED.cues[ED.sel]?.text === texto) desenharDicas();
}

/* ------------------------------------------------------------------ linha */

function desenharDicas() {
  const el = document.getElementById("ed-dicas");
  if (!el) return;
  const c = ED.cues[ED.sel];
  const partes = [];
  const tm = memoriaLigada() ? sugestaoMemoria(c) : null;
  if (tm) {
    partes.push(`<span class="dica-tm" title="${esc(tm.igual ? "Você já traduziu este mesmo original" : `Original parecido: ${tm.orig}`)}">
      <span class="muted">${tm.igual ? "Já traduzido" : "Parecido"}:</span> <span class="dica-txt">${esc(tm.trad.replace(/\n/g, " / "))}</span>
      <button class="btn link small" data-dica="tm">Usar</button></span>`);
  }
  const erros = c && ortografiaLigada() ? (DICAS.orto.get(c.text) || []) : [];
  erros.slice(0, 3).forEach((e, k) => {
    partes.push(`<span class="dica-orto"><span class="dica-erro" title="Pode estar escrita errada">${esc(e.palavra)}</span>${e.sugestoes.length
      ? " → " + e.sugestoes.map((s, j) => `<button class="btn link small" data-orto="${k}" data-s="${j}">${esc(s)}</button>`).join(" ")
      : ' <span class="muted">sem sugestão</span>'}
      <button class="btn link small muted" data-orto-add="${k}" title="Não apontar mais esta palavra">ignorar</button></span>`);
  });
  if (erros.length > 3) partes.push(`<span class="muted">+${erros.length - 3}</span>`);
  el.innerHTML = partes.join('<span class="dica-sep">·</span>');
  el.hidden = !partes.length;
}

function cliqueDica(e) {
  const b = e.target.closest("[data-dica], [data-orto], [data-orto-add]");
  if (!b) return false;
  const c = ED.cues[ED.sel];
  if (!c) return true;
  if (b.dataset.dica === "tm") {
    const s = sugestaoMemoria(c);
    if (s) { setCue(ED.sel, { text: s.trad }, { force: true }); toast("Tradução da memória aplicada (Ctrl+Z desfaz)."); }
    return true;
  }
  const erros = DICAS.orto.get(c.text) || [];
  if (b.dataset.orto != null) {
    const er = erros[Number(b.dataset.orto)];
    if (er && c.text.slice(er.inicio, er.fim) === er.palavra) {
      setCue(ED.sel, { text: c.text.slice(0, er.inicio) + er.sugestoes[Number(b.dataset.s)] + c.text.slice(er.fim) }, { force: true });
      conferirOrtografia();
    }
    return true;
  }
  if (b.dataset.ortoAdd != null) {
    const er = erros[Number(b.dataset.ortoAdd)];
    if (er) {
      api("POST", "/api/ortografia/dicionario", { palavra: er.palavra }).then((r) => {
        if (S.state?.settings) S.state.settings.dicionario = r.dicionario;
        DICAS.orto.clear(); conferirOrtografia();
        toast(`“${er.palavra}” entrou no seu dicionário.`);
      }).catch((err) => toast(err.message, true));
    }
    return true;
  }
  return false;
}

/* --------------------------------------------------------------- versões */

const ORIGEM_VERSAO = { salvar: "Salvo", entrega: "Entregue" };

async function abrirVersoes() {
  let r;
  try { r = await api("GET", `/api/editor/${ED.sid}/versoes`); } catch (e) { toast(e.message, true); return; }
  if (!r.versoes.length) { toast(ED.srt ? "Ainda não há versões: cada vez que você salva, uma fica guardada." : "Salve a legenda primeiro: cada vez que você salva, uma versão fica guardada.", true); return; }
  const m = modal(`Versões de ${r.arquivo}`, `
    <p class="muted small">Cada “Salvar” e “Entregar” guarda uma cópia (as 50 mais recentes), na pasta do programa. Voltar para uma versão
      não apaga nada: ela entra como alteração não salva e o Ctrl+Z desfaz.</p>
    <div class="ver-wrap"><table class="table ver-lista"><thead><tr><th>Quando</th><th></th><th class="num">Legendas</th><th></th></tr></thead><tbody>
      ${r.versoes.map((v) => `<tr data-v="${esc(v.id)}"><td class="tnum">${esc(new Date(v.quando.replace(" ", "T")).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" }))}</td>
        <td>${esc(ORIGEM_VERSAO[v.origem] || v.origem)}</td><td class="num">${v.legendas}</td>
        <td><button class="btn small" data-vc="${esc(v.id)}">Comparar</button></td></tr>`).join("")}
    </tbody></table></div>
    <div id="ver-dif"></div>`,
    `<button class="btn" data-vx="close">Fechar</button><button class="btn primary" data-vx="usar" disabled>Voltar para esta versão</button>`, { wide: true });
  let escolhida = null;
  m.ov.addEventListener("click", async (e) => {
    const vc = e.target.closest("[data-vc]")?.dataset.vc;
    const x = e.target.closest("[data-vx]")?.dataset.vx;
    if (x === "close") return m.close();
    if (vc) {
      let d;
      try { d = await api("POST", `/api/editor/${ED.sid}/versoes/${vc}`, { cues: sortedCues() }); } catch (err) { toast(err.message, true); return; }
      escolhida = d;
      m.ov.querySelectorAll("tr[data-v]").forEach((tr) => tr.classList.toggle("sel", tr.dataset.v === vc));
      m.$("[data-vx=usar]").disabled = false;
      const lado = (c) => c ? `<span class="tnum muted small">${esc(fmtTC(c.start))}</span><div>${esc(c.text).replace(/\n/g, "<br>")}</div>` : "";
      m.$("#ver-dif").innerHTML = d.diferencas.length ? `<h3 class="small">${d.diferencas.length} diferença(s) entre esta versão e o que está na tela</h3>
        <div class="ver-wrap"><table class="table ver-dif"><thead><tr><th>#</th><th>Nesta versão</th><th>Agora</th></tr></thead><tbody>
        ${d.diferencas.slice(0, 300).map((x) => `<tr class="${x.tipo}"><td class="tnum">${x.n ?? "—"}</td><td>${x.antes ? lado(x.antes) : '<i class="muted">não tinha</i>'}</td>
          <td>${x.depois ? lado(x.depois) : '<i class="muted">apagada</i>'}${x.so_tempo ? ' <span class="muted small">(só o tempo)</span>' : ""}</td></tr>`).join("")}
        </tbody></table></div>` : `<p class="note ok">Igual ao que está na tela.</p>`;
      return;
    }
    if (x === "usar" && escolhida) {
      const atuais = sortedCues();
      const cues = escolhida.cues.map((c, i) => {   // mantém o original ao lado, quando dá para achar
        const par = atuais.length === escolhida.cues.length ? atuais[i] : atuais.find((a) => Math.abs(a.start - c.start) < 0.05);
        return par && par.orig != null ? { ...c, orig: par.orig } : c;
      });
      m.close();
      applyCues(cues, "Versão antiga na tela, ainda não salva");
    }
  });
}
