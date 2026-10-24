/* CNT Legendas — audiodescrição no editor (P-06). O roteiro é a própria legenda: cada legenda é uma descrição.
   Usa ED (editor.js) e runTask/modal/pickPath (tools.js). */
"use strict";

const AD_PPM = "cnt.ad.ppm";
function adPpm() { return Math.max(80, Math.min(260, Number(getPref(AD_PPM, "150")) || 150)); }
function adPalavras(t) { return ((t || "").match(/[\wÀ-ÿ]+(?:[-'][\wÀ-ÿ]+)*/g) || []).length; }
function adCabem(dur) { return Math.max(0, Math.floor(dur * adPpm() / 60 + 1e-6)); }

async function abrirAD() {
  document.getElementById("ed-drawer")?.remove();
  const dr = document.createElement("aside");
  dr.className = "drawer ad-drawer"; dr.id = "ed-drawer";
  dr.setAttribute("aria-label", "Audiodescrição");
  document.body.appendChild(dr);
  let issues = null, ultimaSel = -1, audio = null, sugestao = null, gravs = [], gravador = null;
  const gravDe = (c) => c && gravs.find((g) => Math.abs(g.inicio - c.start) <= 0.5);
  const carregarGravs = async () => { try { gravs = (await api("GET", `/api/editor/${ED.sid}/ad/gravacoes`)).gravacoes; } catch { gravs = []; } };
  const perfilAD = ED.profile?.key === "audiodescricao-pt-br";

  const desenhar = () => {
    const c = ED.cues[ED.sel];
    const dur = c ? c.end - c.start : 0;
    const pal = c ? adPalavras(c.text) : 0, cabe = adCabem(dur);
    dr.innerHTML = `
      <div class="drawer-head"><h2>Audiodescrição</h2><button class="btn icon" data-ad="fechar" aria-label="Fechar">×</button></div>
      <p class="small muted">Cada legenda é uma descrição. Escreva nos espaços sem fala, confira e exporte o roteiro e o áudio.</p>
      ${perfilAD ? "" : `<p class="note small">As regras desta legenda são de legendagem. <button class="btn sm" data-ad="perfil">Usar as regras de audiodescrição</button></p>`}
      <label class="field"><span>Velocidade da voz <em>(palavras por minuto)</em></span>
        <input type="number" id="ad-ppm" min="80" max="260" step="5" value="${adPpm()}" style="width:100px"></label>
      <div class="row" style="gap:6px;flex-wrap:wrap">
        <button class="btn" data-ad="espacos" title="Procura no vídeo os trechos sem fala">Achar espaços sem fala</button>
        <button class="btn" data-ad="verificar">Verificar</button>
        <button class="btn primary" data-ad="exportar">Exportar…</button>
      </div>
      ${ED.adEspacos ? `<div class="ad-sec"><div class="row" style="justify-content:space-between"><b class="small">${ED.adEspacos.length} espaços sem fala</b>
          <button class="btn sm" data-ad="criar-todos" title="Uma descrição vazia em cada espaço que ainda não tem">Criar nos vazios</button></div>
        <ul class="issues ad-esp">${ED.adEspacos.map((e, k) => `<li><button data-ad="ir" data-k="${k}">
          <span class="tnum">${fmtTC(e.inicio)} · ${e.duracao.toFixed(1)} s · cabem ${adCabem(e.duracao)} palavras</span>
          ${e.ocupado ? `<span class="muted">já tem descrição</span>` : `<span class="ok">livre</span>`}</button></li>`).join("")}</ul></div>` : ""}
      <div class="ad-sec" id="ad-sel">
        ${c ? `<b class="small">Descrição nº ${ED.sel + 1}</b> <span class="tnum small muted">${fmtTC(c.start)} → ${fmtTC(c.end)} (${dur.toFixed(1)} s)</span>
          <p class="small ${pal > cabe ? "err" : "muted"}">${pal} de ${cabe} palavras${pal > cabe ? " — não cabe nesse tempo" : ""}</p>
          <div class="row" style="gap:6px;flex-wrap:wrap"><button class="btn sm" data-ad="ouvir" ${c.text?.trim() ? "" : "disabled"} title="Voz do sistema">▶ Ouvir</button>
            <button class="btn sm" data-ad="sugerir" title="A IA olha alguns quadros do trecho e sugere um rascunho (você revisa)">Sugerir com IA</button>
            <button class="btn sm ${gravador ? "danger" : ""}" data-ad="gravar" title="Gravar esta descrição com a sua voz (microfone)">${gravador ? "■ Parar a gravação" : "● Gravar com a minha voz"}</button></div>
          ${gravDe(c) ? `<p class="small">Sua voz gravada (${gravDe(c).duracao.toFixed(1)} s)${gravDe(c).duracao > dur + 0.3 ? ` <span class="err">— passa do trecho</span>` : ""}
            · <a href="#" data-ad="ouvir-grav">ouvir</a> · <a href="#" data-ad="apagar-grav">apagar</a> <span class="muted">(vale na exportação no lugar da voz do sistema)</span></p>` : ""}
          ${sugestao && sugestao.i === ED.sel ? `<div class="ad-sug"><p>${esc(sugestao.texto)}</p>
            <div class="row" style="gap:6px"><button class="btn sm primary" data-ad="usar">Usar</button><button class="btn sm ghost" data-ad="descartar">Descartar</button></div></div>` : ""}`
        : `<p class="small muted">Selecione uma descrição para ouvir ou pedir sugestão.</p>`}
      </div>
      ${issues ? `<div class="ad-sec"><b class="small">${issues.length ? `${issues.length} apontamento(s)` : "Nenhum problema encontrado."}</b>
        <ul class="issues">${issues.map((x) => `<li><button data-ad="ir-n" data-n="${x.n}"><span class="tnum muted">#${x.n}</span>
          <span class="${x.nivel === "erro" ? "err" : "warn"}">${esc(x.mensagem)}</span></button></li>`).join("")}</ul></div>` : ""}`;
    ultimaSel = ED.sel;
  };

  const verificar = async () => {
    const r = await api("POST", `/api/editor/${ED.sid}/ad/verificar`, { cues: sortedCues(), ppm: adPpm(), idioma: ED.profile?.language || ED.language });
    issues = r.issues; desenhar();
  };

  const vigia = setInterval(() => {
    if (!document.body.contains(dr)) { clearInterval(vigia); audio?.pause(); gravador?.stop(); return; }
    if (ED.sel !== ultimaSel && !dr.contains(document.activeElement)) desenhar();
  }, 400);

  dr.addEventListener("change", (e) => {
    if (e.target.id === "ad-ppm") { setPref(AD_PPM, String(Math.max(80, Math.min(260, Number(e.target.value) || 150)))); desenhar(); drawStatus(); }
  });
  dr.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-ad]");
    if (!b) return;
    const a = b.dataset.ad;
    try {
      if (a === "fechar") { dr.remove(); audio?.pause(); }
      if (a === "perfil") {
        const sel = document.getElementById("ed-profile");
        if (sel) { sel.value = "audiodescricao-pt-br"; sel.dispatchEvent(new Event("change", { bubbles: true })); }
        setTimeout(abrirAD, 600);
      }
      if (a === "espacos") {
        const t = await runTask("ad_espacos", { ppm: adPpm() }, "Achando os espaços sem fala");
        if (t) { ED.adEspacos = t.result.espacos; toast(t.message); drawWave(); desenhar(); }
      }
      if (a === "criar-todos") {
        const livres = (ED.adEspacos || []).filter((x) => !x.ocupado);
        if (!livres.length) { toast("Todos os espaços já têm descrição."); return; }
        snapshot(true);
        for (const x of livres) { ED.cues.push({ start: x.inicio, end: x.fim, text: "" }); x.ocupado = true; }
        sortedCues(); changed(false); drawAll();
        selectCue(ED.cues.findIndex((c) => c.start === livres[0].inicio));
        toast(`${livres.length} descrições vazias criadas. Escreva em cada uma.`);
        desenhar();
      }
      if (a === "ir") {
        const x = ED.adEspacos[Number(b.dataset.k)];
        const i = ED.cues.findIndex((c) => c.end > x.inicio && c.start < x.fim);
        if (i >= 0) selectCue(i); else seek(x.inicio);
      }
      if (a === "ir-n") { selectCue(Math.min(Number(b.dataset.n) - 1, ED.cues.length - 1)); document.getElementById("ed-txt")?.focus(); }
      if (a === "verificar") await verificar();
      if (a === "ouvir") {
        const c = ED.cues[ED.sel];
        b.disabled = true;
        const r = await api("POST", `/api/editor/${ED.sid}/ad/voz`, { texto: c.text, ppm: adPpm() });
        b.disabled = false;
        audio?.pause();
        audio = new Audio(r.url); audio.play().catch(() => {});
        const dur = c.end - c.start;
        if (r.duracao > dur + 0.3) toast(`A voz leva ${r.duracao.toFixed(1)} s e o trecho tem ${dur.toFixed(1)} s.`, true);
      }
      if (a === "gravar") {
        if (gravador) { gravador.stop(); return; }
        const c = ED.cues[ED.sel];
        let stream;
        try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
        catch { throw new Error("Não consegui usar o microfone. Confira se ele está ligado e se o programa tem permissão."); }
        const pedacos = [];
        gravador = new MediaRecorder(stream);
        gravador.ondataavailable = (ev) => { if (ev.data.size) pedacos.push(ev.data); };
        gravador.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          gravador = null; desenhar();
          const blob = new Blob(pedacos, { type: pedacos[0]?.type || "audio/webm" });
          const b64 = await new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(",")[1] || ""); fr.readAsDataURL(blob); });
          try {
            const r = await api("POST", `/api/editor/${ED.sid}/ad/gravacao`, { inicio: c.start, audio: b64 });
            await carregarGravs(); desenhar();
            toast(`Gravação guardada (${r.duracao.toFixed(1)} s).`);
          } catch (e2) { toast(e2.message, true); }
        };
        gravador.start(); desenhar();
        return;
      }
      if (a === "ouvir-grav") { e.preventDefault(); const g = gravDe(ED.cues[ED.sel]); if (g) { audio?.pause(); audio = new Audio(g.url + "?t=" + Date.now()); audio.play().catch(() => {}); } }
      if (a === "apagar-grav") { e.preventDefault(); await api("POST", `/api/editor/${ED.sid}/ad/gravacao/apagar`, { inicio: ED.cues[ED.sel].start }); await carregarGravs(); desenhar(); }
      if (a === "sugerir") {
        const c = ED.cues[ED.sel];
        b.disabled = true; b.textContent = "Olhando o vídeo…";
        const ant = ED.cues[ED.sel - 1]?.text || "";
        const r = await api("POST", `/api/editor/${ED.sid}/ad/sugerir`, { inicio: c.start, fim: c.end, contexto: ant, ppm: adPpm() });
        sugestao = { i: ED.sel, texto: r.texto }; desenhar();
      }
      if (a === "usar" && sugestao) {
        snapshot(true); ED.cues[sugestao.i].text = sugestao.texto; sugestao = null;
        changed(false); drawAll(); selectCue(ED.sel); desenhar();
      }
      if (a === "descartar") { sugestao = null; desenhar(); }
      if (a === "exportar") exportarAD();
    } catch (err) {
      b.disabled = false;
      if (a === "sugerir") desenhar();
      toast(err.message, true);
    }
  });
  await carregarGravs();
  desenhar();
}

function exportarAD() {
  const m = modal("Exportar a audiodescrição", `
    <p class="small muted">Os arquivos vão para a pasta do vídeo, com “- audiodescricao” no nome. O vídeo e a legenda originais não mudam.</p>
    <label class="row small" style="gap:6px"><input type="checkbox" value="docx" checked> Roteiro para revisão (.docx, com tempos)</label>
    <label class="row small" style="gap:6px"><input type="checkbox" value="txt" checked> Roteiro em texto (.txt, com tempos)</label>
    <label class="row small" style="gap:6px"><input type="checkbox" value="ttml" checked> Texto com tempos para plataformas (.ttml)</label>
    <label class="row small" style="gap:6px"><input type="checkbox" value="faixa" checked> Faixa só da audiodescrição, com voz sintética (.wav)</label>
    <label class="row small" style="gap:6px"><input type="checkbox" value="mixada" checked> Áudio mixado: original + descrições (.wav)</label>
    <label class="field"><span>Volume do áudio original durante as descrições</span>
      <select id="ad-abaixar"><option value="0.2">20%</option><option value="0.3" selected>30%</option><option value="0.5">50%</option><option value="0.7">70%</option></select></label>`,
    `<button class="btn ghost" data-x="cancel">Cancelar</button><button class="btn primary" data-x="ok">Exportar</button>`);
  m.$("[data-x=cancel]").onclick = m.close;
  m.$("[data-x=ok]").onclick = async () => {
    const formatos = [...m.ov.querySelectorAll("input[type=checkbox]:checked")].map((x) => x.value);
    const abaixar = Number(m.$("#ad-abaixar").value);
    if (!formatos.length) { toast("Marque pelo menos um arquivo.", true); return; }
    m.close();
    try {
      const t = await runTask("ad_exportar", { formatos, abaixar, ppm: adPpm() }, "Exportando a audiodescrição");
      if (!t) return;
      const arqs = t.result.arquivos || [];
      const r = modal("Audiodescrição exportada", `<p>${esc(t.message)}</p><ul class="small">${arqs.map((f) => `<li class="mono">${esc(f.split(/[\\/]/).pop())}</li>`).join("")}</ul>`,
        `<button class="btn" data-x="pasta">Abrir a pasta</button><button class="btn primary" data-x="ok">Fechar</button>`);
      r.$("[data-x=ok]").onclick = r.close;
      r.$("[data-x=pasta]").onclick = () => { api("POST", "/api/open", { path: arqs[0], select: true }).catch((e) => toast(e.message, true)); r.close(); };
    } catch (e) { toast(e.message, true); }
  };
}


/* ------------------------------------------------------------ enviar para a CNT Dubla (T-058) */
function enviarParaDubla() {
  const base = (ED.video || ED.name || "").split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
  const m = modal("Enviar para a dublagem", `
    <p class="small muted">O vídeo e esta legenda vão para a CNT Dubla como roteiro de dublagem (em “Projetos → Enviados pelo CNT Legendas”).
      ${ED.hasOrig ? "O texto original também vai, para a comparação de sílabas." : ""}</p>
    <label class="field"><span>Nome do projeto de dublagem</span><input type="text" id="dub-nome" value="${esc(base)}"></label>`,
  `<button class="btn ghost" data-x="cancel">Cancelar</button><button class="btn primary" data-x="ok">Enviar</button>`);
  m.$("[data-x=cancel]").onclick = m.close;
  m.$("[data-x=ok]").onclick = async () => {
    try {
      await api("POST", `/api/editor/${ED.sid}/enviar-dubla`, { nome: m.$("#dub-nome").value, cues: sortedCues() });
      m.close(); toast("Enviado. Abra a CNT Dubla: o projeto aparece em “Enviados pelo CNT Legendas”.");
    } catch (e) { toast(e.message, true); }
  };
}
