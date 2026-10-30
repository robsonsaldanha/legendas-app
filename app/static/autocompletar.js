/* CNT Legendas — autocompletar no texto da legenda e glossário do projeto aprendido (2.26).

   Autocompletar: como nos editores de código. Enquanto ela digita, a partir da 2ª letra, aparecem os termos do
   glossário (projeto, cliente e geral), os nomes próprios e as palavras já usadas nesta legenda.
   Tab ou Enter aceita · ↑ ↓ escolhem · Esc fecha.

   Glossário aprendido: quando ela troca a mesma palavra pela mesma outra 3 vezes no projeto, o programa
   pergunta se quer pôr no glossário do projeto. Nada entra sem ela confirmar. */
"use strict";

const AC = { termos: [], aberto: false, itens: [], sel: 0, inicio: 0, fim: 0, box: null, sid: null };
const PALAVRA_RE = /[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu;

async function carregarSugestoes() {
  AC.termos = []; AC.sid = ED.sid;
  if (!ED.sid) return;
  try { AC.termos = (await api("GET", `/api/editor/${ED.sid}/sugestoes`)).termos || []; } catch { AC.termos = []; }
}

/* Palavras desta legenda: nomes próprios (com maiúscula no meio da frase) e palavras de 4+ letras, por frequência. */
function palavrasDaLegenda() {
  const freq = new Map(), nomes = new Set();
  for (const c of ED.cues) {
    const txt = c.text.replace(/<[^>]+>|\{\\an\d\}/g, " ");
    const ws = txt.match(PALAVRA_RE) || [];
    ws.forEach((w, k) => {
      if (w.length < 4 && !/^\p{Lu}/u.test(w)) return;
      freq.set(w, (freq.get(w) || 0) + 1);
      const antes = txt.slice(0, txt.indexOf(w)).trimEnd();
      if (k > 0 && /^\p{Lu}/u.test(w) && !/[.!?…:\-–—]$/.test(antes)) nomes.add(w);
    });
  }
  return { freq, nomes };
}

function candidatos(prefixo, atual) {
  const p = prefixo.toLocaleLowerCase("pt-BR");
  const out = [], visto = new Set();
  const add = (texto, fonte, nota = "") => {
    const k = texto.toLocaleLowerCase("pt-BR");
    if (visto.has(k) || k === p || !k.startsWith(p) || texto === atual) return;
    visto.add(k); out.push({ texto, fonte, nota });
  };
  for (const t of AC.termos) add(t.texto, "glossário", t.nota);
  const { freq, nomes } = palavrasDaLegenda();
  [...nomes].sort((a, b) => (freq.get(b) || 0) - (freq.get(a) || 0)).forEach((w) => add(w, "nome"));
  [...freq.entries()].filter(([w, n]) => n >= 1 && w.length >= 4).sort((a, b) => b[1] - a[1]).forEach(([w]) => add(w, "nesta legenda"));
  return out.slice(0, 8);
}

/* Posição do cursor dentro do textarea (espelho com o mesmo estilo). */
function posCursor(ta, pos) {
  const st = getComputedStyle(ta);
  const div = document.createElement("div");
  for (const k of ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing", "padding", "border", "boxSizing", "whiteSpace", "wordWrap", "textAlign"]) div.style[k] = st[k];
  Object.assign(div.style, { position: "absolute", visibility: "hidden", whiteSpace: "pre-wrap", wordWrap: "break-word", width: `${ta.clientWidth}px`, left: "-9999px", top: "0" });
  div.textContent = ta.value.slice(0, pos);
  const span = document.createElement("span"); span.textContent = "​"; div.appendChild(span);
  document.body.appendChild(div);
  const r = { x: span.offsetLeft, y: span.offsetTop + parseFloat(st.lineHeight || "18") };
  div.remove();
  const b = ta.getBoundingClientRect();
  return { left: b.left + r.x - ta.scrollLeft, top: b.top + r.y - ta.scrollTop };
}

function fecharAC() {
  AC.aberto = false; AC.itens = [];
  AC.box?.remove(); AC.box = null;
}

function desenharAC(ta) {
  if (!AC.box) {
    AC.box = document.createElement("div");
    AC.box.className = "ac-box"; AC.box.setAttribute("role", "listbox"); AC.box.setAttribute("aria-label", "Sugestões");
    AC.box.addEventListener("mousedown", (e) => {
      const li = e.target.closest("[data-k]");
      if (li) { e.preventDefault(); AC.sel = Number(li.dataset.k); aceitarAC(ta); }
    });
    document.body.appendChild(AC.box);
  }
  AC.box.innerHTML = AC.itens.map((it, k) => `<div class="ac-item ${k === AC.sel ? "on" : ""}" role="option" aria-selected="${k === AC.sel}" data-k="${k}">
      <span class="ac-txt">${esc(it.texto)}</span><span class="ac-fonte">${esc(it.fonte)}</span></div>`).join("")
    + `<div class="ac-dica">Tab ou Enter aceita · Esc fecha</div>`;
  const p = posCursor(ta, AC.fim);
  const h = AC.box.offsetHeight, w = AC.box.offsetWidth;
  AC.box.style.left = `${Math.max(8, Math.min(p.left, window.innerWidth - w - 8))}px`;
  AC.box.style.top = `${p.top + 4 + h > window.innerHeight ? p.top - h - 22 : p.top + 4}px`;
}

function atualizarAC(ta) {
  if (AC.sid !== ED.sid) carregarSugestoes();
  const pos = ta.selectionStart;
  if (pos !== ta.selectionEnd) return fecharAC();
  const antes = ta.value.slice(0, pos);
  const m = antes.match(/[\p{L}\p{N}][\p{L}\p{N}'’-]*$/u);
  if (!m || m[0].length < 2) return fecharAC();
  const depois = ta.value.slice(pos).match(/^[\p{L}\p{N}'’-]*/u)[0];
  const itens = candidatos(m[0], m[0] + depois);
  if (!itens.length) return fecharAC();
  Object.assign(AC, { aberto: true, itens, sel: 0, inicio: pos - m[0].length, fim: pos + depois.length });
  desenharAC(ta);
}

function aceitarAC(ta) {
  const it = AC.itens[AC.sel];
  if (!it) return fecharAC();
  const v = ta.value;
  ta.value = v.slice(0, AC.inicio) + it.texto + v.slice(AC.fim);
  const cur = AC.inicio + it.texto.length;
  ta.setSelectionRange(cur, cur);
  fecharAC();
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  ta.focus();
}

function ligarAutocompletar() {
  const ta = document.getElementById("ed-txt");
  if (!ta || ta.dataset.ac) return;
  ta.dataset.ac = "1";
  ta.addEventListener("input", (e) => { if (e.isTrusted) { ED.digitouIdx = ED.sel; atualizarAC(ta); } });
  ta.addEventListener("keydown", (e) => {
    if (!AC.aberto) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); e.stopPropagation();
      AC.sel = (AC.sel + (e.key === "ArrowDown" ? 1 : AC.itens.length - 1)) % AC.itens.length; desenharAC(ta);
    } else if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey && !e.ctrlKey)) {
      e.preventDefault(); e.stopPropagation(); aceitarAC(ta);
    } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fecharAC(); }
  }, true);
  ta.addEventListener("blur", () => setTimeout(fecharAC, 120));
  ta.addEventListener("click", () => fecharAC());
}

/* ------------------------------------------------------------ glossário aprendido */

/* Pares (palavra antiga → nova) de uma edição: só trocas de uma palavra por uma palavra. */
function trocasDePalavras(antes, depois) {
  const a = antes.replace(/<[^>]+>|\{\\an\d\}/g, " ").match(PALAVRA_RE) || [];
  const b = depois.replace(/<[^>]+>|\{\\an\d\}/g, " ").match(PALAVRA_RE) || [];
  if (!a.length || !b.length || Math.abs(a.length - b.length) > 3) return [];
  // alinha pelo começo e pelo fim; o meio diferente de mesmo tamanho vira pares
  let i = 0; while (i < a.length && i < b.length && a[i] === b[i]) i++;
  let ja = a.length - 1, jb = b.length - 1; while (ja >= i && jb >= i && a[ja] === b[jb]) { ja--; jb--; }
  const ma = a.slice(i, ja + 1), mb = b.slice(i, jb + 1);
  if (!ma.length || ma.length !== mb.length || ma.length > 3) return [];
  return ma.map((w, k) => [w, mb[k]]).filter(([x, y]) => x !== y && x.toLowerCase() !== y.toLowerCase() && x.length >= 2 && y.length >= 2);
}

async function registrarCorrecoes(i, antes) {
  const c = ED.cues[i];
  if (!c || antes == null || c.text === antes || !ED.itemId) return;
  for (const [de, para] of trocasDePalavras(antes, c.text)) {
    let r;
    try { r = await api("POST", `/api/editor/${ED.sid}/correcao`, { de, para }); } catch { continue; }
    if (r.perguntar) perguntarGlossario(r.de, r.para, r.vezes);
  }
}

function perguntarGlossario(de, para, vezes) {
  if (document.querySelector(".modal-bg")) return;   // não interrompe outra janela: pergunta na próxima troca
  const m = modal("Pôr no glossário do projeto?", `
    <p>Você trocou <b>“${esc(de)}”</b> por <b>“${esc(para)}”</b> ${vezes} vezes neste projeto.</p>
    <p>Quer adicionar ao <b>glossário do projeto</b>? Assim a tradução por IA e o autocompletar já usam “${esc(para)}”.</p>
    <p class="muted small">Só entra neste projeto. Dá para mudar ou tirar depois, no glossário do projeto.</p>`,
    `<button class="btn" data-g="nao">Não, obrigado</button><button class="btn primary" data-g="sim">Adicionar</button>`);
  m.ov.addEventListener("click", async (e) => {
    const g = e.target.closest("[data-g]")?.dataset.g;
    if (!g) return;
    m.close();
    try {
      await api("POST", `/api/editor/${ED.sid}/correcao/decidir`, { de, para, adicionar: g === "sim" });
      if (g === "sim") { toast(`“${para}” entrou no glossário do projeto.`); carregarSugestoes(); }
    } catch (err) { toast(err.message, true); }
  });
}

/* Ao sair de uma legenda que ela digitou, compara o antes e o depois. */
(function () {
  const original = window.selectCue;
  window.selectCue = function (i, opts) {
    const anterior = ED.acIdx, textoAntes = ED.acTexto;
    const r = original(i, opts);
    if (anterior != null && anterior !== ED.sel && ED.digitouIdx === anterior) registrarCorrecoes(anterior, textoAntes);
    if (anterior !== ED.sel) { ED.acIdx = ED.sel; ED.acTexto = ED.cues[ED.sel]?.text; ED.digitouIdx = null; fecharAC(); }
    ligarAutocompletar();
    return r;
  };
})();
