/* CNT Legendas — revisão no editor (2.26): anotações por legenda, modo foco e tela de cinema.
   As anotações não vão para o .srt: ficam no banco do programa (por episódio ou por arquivo). */
"use strict";

/* ------------------------------------------------------------ anotações */

async function carregarNotas() {
  ED.notas = [];
  if (!ED.sid) return;
  try { ED.notas = (await api("GET", `/api/editor/${ED.sid}/notas`)).notas || []; } catch { ED.notas = []; }
  if (typeof drawRows === "function") drawRows();
}

/* Anotação de uma legenda: a que começa no mesmo tempo (folga de 0,3 s) ou dentro dela. */
function notaDe(c) {
  if (!c || !ED.notas?.length) return null;
  return ED.notas.find((n) => Math.abs(n.inicio - c.start) < 0.3)
    || ED.notas.find((n) => n.inicio >= c.start && n.inicio < c.end) || null;
}

function notaCell(c, i) {
  const n = notaDe(c);
  return `<td class="c-nota">${n ? `<button type="button" class="nota-btn" data-nota="${i}" title="${esc(n.texto)}" aria-label="Anotação: ${esc(n.texto.slice(0, 80))}">${ic("nota")}</button>` : ""}</td>`;
}

async function abrirNota(i) {
  const c = ED.cues[i];
  if (!c) return;
  const n = notaDe(c);
  const m = modal(`Anotação — legenda ${i + 1}`, `
    <p class="muted small"><span class="tnum">${esc(fmtTC(c.start))}</span> · ${esc(c.text.replace(/\{\\an\d\}/g, "")).replace(/\n/g, " / ")}</p>
    <textarea id="nota-txt" rows="5" placeholder="Escreva a sua anotação (não vai para a legenda nem para o arquivo)" autofocus>${esc(n?.texto || "")}</textarea>
    <p class="muted small">Fica guardada no programa. Ctrl+Enter salva.</p>`,
    `${n ? '<button class="btn danger" data-n="apagar">Apagar</button><span class="grow"></span>' : ""}
     <button class="btn" data-n="cancelar">Cancelar</button><button class="btn primary" data-n="salvar">Salvar</button>`);
  const ta = m.$("#nota-txt");
  ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
  const salvar = async () => {
    const texto = ta.value.trim();
    try {
      if (n) await api(texto ? "PUT" : "DELETE", `/api/editor/${ED.sid}/notas/${n.id}`, texto ? { texto, inicio: c.start, fim: c.end } : undefined);
      else if (texto) await api("POST", `/api/editor/${ED.sid}/notas`, { texto, inicio: c.start, fim: c.end });
      m.close(); await carregarNotas();
      toast(texto ? "Anotação guardada." : "Anotação apagada.");
    } catch (e) { toast(e.message, true); }
  };
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); salvar(); } });
  m.ov.addEventListener("click", async (e) => {
    const a = e.target.closest("[data-n]")?.dataset.n;
    if (a === "cancelar") m.close();
    else if (a === "salvar") salvar();
    else if (a === "apagar") {
      try { await api("DELETE", `/api/editor/${ED.sid}/notas/${n.id}`); m.close(); await carregarNotas(); toast("Anotação apagada."); }
      catch (err) { toast(err.message, true); }
    }
  });
}

document.addEventListener("click", (e) => {
  const b = e.target.closest(".nota-btn[data-nota]");
  if (b) { e.stopPropagation(); abrirNota(Number(b.dataset.nota)); }
}, true);

/* ------------------------------------------------------------ modo foco */

function focoLigado() { try { return localStorage.getItem("cnt.foco") === "1"; } catch { return false; } }
function aplicarFoco() {
  const on = focoLigado();
  document.body.classList.toggle("ed-foco", on);
  const b = document.querySelector('[data-ed="foco"]');
  if (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); b.classList.toggle("on", on); }
}
function alternarFoco() {
  try { localStorage.setItem("cnt.foco", focoLigado() ? "0" : "1"); } catch { /* sem armazenamento: vale só agora */ document.body.classList.toggle("ed-foco"); }
  aplicarFoco();
  toast(document.body.classList.contains("ed-foco") ? "Modo foco: a legenda atual em destaque." : "Modo foco desligado.");
}

/* ------------------------------------------------------------ tela de cinema */

function cueEm(t) {
  return ED.cues.findIndex((c) => t >= c.start && t < c.end);
}

function abrirCinema() {
  const orig = vid();
  if (!ED.video || !orig?.src) { toast("Abra o vídeo junto com a legenda para usar a tela de cinema.", true); return; }
  orig.pause();
  const ov = document.createElement("div");
  ov.className = "cine"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.setAttribute("aria-label", "Tela de cinema");
  ov.innerHTML = `
    <div class="cine-palco"><video id="cine-v" preload="auto"></video><div class="cine-leg" id="cine-leg" aria-live="off"></div></div>
    <div class="cine-barra">
      <button class="btn" id="cine-play">▶ Assistir</button>
      <span class="tnum" id="cine-tc">00:00:00</span>
      <input type="range" id="cine-pos" min="0" max="1000" value="0" aria-label="Posição do vídeo">
      <span class="muted small">Espaço: pausar/continuar · ← →: legenda anterior/próxima · N: anotar · Esc: sair</span>
      <button class="btn" id="cine-anotar" title="Anotar a legenda deste momento (N)">${ic("nota")} Anotar</button>
      <button class="btn ghost" id="cine-sair">Sair</button>
    </div>
    <div class="cine-nota" id="cine-nota" hidden>
      <div class="small muted" id="cine-nota-tit"></div>
      <textarea id="cine-nota-txt" rows="3" placeholder="Anotação desta legenda (não vai para o arquivo)"></textarea>
      <div class="row" style="justify-content:flex-end;gap:8px"><span class="muted small">Ctrl+Enter salva</span>
        <button class="btn" id="cine-nota-x">Fechar</button><button class="btn primary" id="cine-nota-ok">Salvar anotação</button></div>
    </div>`;
  document.body.appendChild(ov);
  const v = ov.querySelector("#cine-v"), leg = ov.querySelector("#cine-leg"), tc = ov.querySelector("#cine-tc"), pos = ov.querySelector("#cine-pos");
  const play = ov.querySelector("#cine-play"), box = ov.querySelector("#cine-nota"), ta = ov.querySelector("#cine-nota-txt");
  v.src = orig.currentSrc || orig.src;
  v.currentTime = orig.currentTime || (ED.cues[ED.sel]?.start ?? 0);
  let atual = -1;
  const desenhar = () => {
    const t = v.currentTime;
    const i = cueEm(t);
    if (i !== atual) {
      atual = i;
      const c = ED.cues[i];
      leg.innerHTML = c ? esc(c.text.replace(/\{\\an\d\}/g, "")).replace(/&lt;(\/?)i&gt;/gi, "<$1i>").replace(/\n/g, "<br>")
        + (notaDe(c) ? `<span class="cine-tem-nota" title="Esta legenda tem anotação">${ic("nota")}</span>` : "") : "";
      leg.classList.toggle("tem-nota", !!(c && notaDe(c)));
    }
    tc.textContent = fmtTC(t).slice(0, 8);
    if (v.duration) pos.value = Math.round((t / v.duration) * 1000);
  };
  v.addEventListener("timeupdate", desenhar);
  v.addEventListener("seeked", desenhar);
  v.addEventListener("play", () => { play.textContent = "❚❚ Pausar"; box.hidden = true; });
  v.addEventListener("pause", () => { play.textContent = "▶ Continuar"; });
  pos.addEventListener("input", () => { if (v.duration) v.currentTime = (pos.value / 1000) * v.duration; });
  const alternar = () => { if (v.paused) v.play().catch(() => {}); else v.pause(); };
  play.addEventListener("click", alternar);
  const anotar = () => {
    v.pause();
    let i = cueEm(v.currentTime);
    if (i < 0) i = ED.cues.findIndex((c) => c.start > v.currentTime) - 1;
    if (i < 0) i = 0;
    const c = ED.cues[i];
    if (!c) return;
    const n = notaDe(c);
    box.dataset.i = i;
    ov.querySelector("#cine-nota-tit").textContent = `Legenda ${i + 1} · ${fmtTC(c.start).slice(0, 8)} — ${c.text.replace(/\{\\an\d\}/g, "").replace(/\n/g, " / ")}`;
    ta.value = n?.texto || "";
    box.hidden = false; ta.focus();
  };
  const salvarNota = async () => {
    const i = Number(box.dataset.i), c = ED.cues[i], n = notaDe(c), texto = ta.value.trim();
    try {
      if (n) await api(texto ? "PUT" : "DELETE", `/api/editor/${ED.sid}/notas/${n.id}`, texto ? { texto, inicio: c.start, fim: c.end } : undefined);
      else if (texto) await api("POST", `/api/editor/${ED.sid}/notas`, { texto, inicio: c.start, fim: c.end });
      await carregarNotas(); atual = -2; desenhar();
      box.hidden = true; toast(texto ? "Anotação guardada." : "Anotação apagada.");
    } catch (e) { toast(e.message, true); }
  };
  ov.querySelector("#cine-nota-ok").addEventListener("click", salvarNota);
  ov.querySelector("#cine-anotar").addEventListener("click", anotar);
  ov.querySelector("#cine-nota-x").addEventListener("click", () => { box.hidden = true; });
  ta.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); salvarNota(); }
    if (e.key === "Escape") { e.preventDefault(); box.hidden = true; }
  });
  const pular = (dir) => {
    const t = v.currentTime;
    const alvo = dir > 0 ? ED.cues.find((c) => c.start > t + 0.05) : [...ED.cues].reverse().find((c) => c.start < t - 0.3);
    if (alvo) v.currentTime = alvo.start;
  };
  const sair = () => {
    const t = v.currentTime;
    v.pause(); v.removeAttribute("src"); v.load();
    ov.remove(); document.removeEventListener("keydown", teclas, true);
    if (orig) orig.currentTime = t;
    const i = cueEm(t);
    if (i >= 0) selectCue(i);
    try { if (document.fullscreenElement) document.exitFullscreen(); } catch { /* */ }
  };
  ov.querySelector("#cine-sair").addEventListener("click", sair);
  const teclas = (e) => {
    if (e.target === ta) return;
    if (e.key === " " || e.code === "Space") { e.preventDefault(); e.stopPropagation(); alternar(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); sair(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); pular(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); pular(-1); }
    else if (e.key.toLowerCase() === "n" && !e.ctrlKey && !e.metaKey) { e.preventDefault(); e.stopPropagation(); anotar(); }
  };
  document.addEventListener("keydown", teclas, true);
  try { ov.requestFullscreen?.().catch(() => {}); } catch { /* sem tela cheia: ocupa a janela */ }
  desenhar();
  play.focus();
}
