/* CNT Legendas — legenda ao vivo (P-05): escolher a entrada, ligar, corrigir na fila, saídas. */
"use strict";

const AV_PREF = "cnt.aovivo";
function avPrefs() {
  try { return { modelo: "small", atraso: 3, idioma: "pt-BR", modo: "bloco", fundo: "transparente", cor: "ffffff", tam: 44, pos: "baixo", caixa: false, ...JSON.parse(getPref(AV_PREF, "{}") || "{}") }; }
  catch { return { modelo: "small", atraso: 3, idioma: "pt-BR", modo: "bloco", fundo: "transparente", cor: "ffffff", tam: 44, pos: "baixo", caixa: false }; }
}
function avSalvar(p) { setPref(AV_PREF, JSON.stringify(p)); }

function avEstilo(p) {
  const q = new URLSearchParams({ modo: p.modo, fundo: p.fundo, cor: p.cor, tam: String(p.tam), pos: p.pos });
  if (p.faixa === "traducao") q.set("faixa", "traducao");
  if (p.caixa) q.set("caixa", "1");
  return q.toString();
}

async function renderAoVivo() {
  await Promise.all([loadState(), loadProjects()]);
  const r = await api("GET", "/api/aovivo/entradas");
  const p = avPrefs();
  const opts = (r.entradas || []).map((e) => `<option value="${esc(e.id)}" ${e.id === p.fonte ? "selected" : ""}>${esc(e.nome)}</option>`).join("");
  main.innerHTML = `
    <div class="page-head"><div><span class="eyebrow">Ao vivo</span><h1 style="margin-top:6px">Legenda ao vivo</h1>
      <p class="muted">Ouve uma entrada de áudio e gera a legenda na hora. Cada legenda espera alguns segundos na fila para você corrigir antes de ir para a tela.</p></div></div>
    <div class="split2 av-grid">
      <section class="panel" id="av-config">
        <h2>Entrada e reconhecimento</h2>
        <div class="stack">
          <label class="field"><span>Entrada de áudio</span>
            <select id="av-fonte">${opts}<option value="arquivo:" ${String(p.fonte || "").startsWith("arquivo:") ? "selected" : ""}>Um arquivo de vídeo ou áudio (ensaio)</option><option value="url:" ${String(p.fonte || "").startsWith("url:") ? "selected" : ""}>Endereço de uma transmissão</option></select></label>
          <p class="note" id="av-dica-sistema" hidden>Abra a live (de qualquer site) no navegador e deixe tocando com som. Tudo o que tocar no computador entra na legenda: feche outros vídeos e desligue os sons de aviso enquanto legenda.</p>
          <label class="field" id="av-extra-l" hidden><span id="av-extra-t">Arquivo</span>
            <div class="row" style="gap:6px"><input type="text" id="av-extra" style="flex:1" value="${esc(String(p.fonte || "").replace(/^(arquivo|url):/, ""))}"><button class="btn" data-a="escolher" id="av-escolher">Escolher…</button></div></label>
          <div class="row" style="gap:12px;flex-wrap:wrap">
            <label class="field"><span>Idioma falado</span><select id="av-idioma">${[["pt-BR", "Português"], ["en", "Inglês"], ["es", "Espanhol"]].map(([v, t]) => `<option value="${v}" ${v === p.idioma ? "selected" : ""}>${t}</option>`).join("")}</select></label>
            <label class="field"><span>Precisão</span><select id="av-modelo">${[["base", "Rápida (computador simples)"], ["small", "Equilibrada"], ["medium", "Alta (precisa de placa de vídeo)"]].map(([v, t]) => `<option value="${v}" ${v === p.modelo ? "selected" : ""}>${t}</option>`).join("")}</select></label>
            <label class="field"><span>Tradução ao vivo</span><select id="av-traducao">${[["", "Nenhuma"], ["es-419", "Espanhol"], ["pt-BR", "Português"], ["en", "Inglês"]].map(([v, t]) => `<option value="${v}" ${v === (p.traducao || "") ? "selected" : ""}>${t}</option>`).join("")}</select></label>
            <label class="field"><span>Espera para corrigir</span><select id="av-atraso">${[0, 2, 3, 5, 8, 12].map((v) => `<option value="${v}" ${Number(p.atraso) === v ? "selected" : ""}>${v ? `${v} segundos` : "Sem espera"}</option>`).join("")}</select></label>
          </div>
          <label class="field"><span>Cliente (nomes certos do glossário)</span><select id="av-cliente"><option value="">Nenhum</option>${(S.projects || []).map((c) => `<option value="${c.id}" ${String(c.id) === String(p.cliente || "") ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
          <label class="field"><span>Palavras para esconder <em>(separe por vírgula; aparecem como ***)</em></span><input type="text" id="av-filtro" value="${esc(p.filtro || "")}"></label>
          <div class="row" style="gap:8px"><button class="btn primary" data-a="iniciar" id="av-iniciar">${ic("play")} Começar</button>
            <button class="btn" data-a="parar" id="av-parar" hidden>Parar</button></div>
          <p class="note" id="av-msg" hidden></p>
        </div>
      </section>
      <section class="panel" id="av-saida">
        <h2>Na tela</h2>
        <div class="row" style="gap:12px;flex-wrap:wrap">
          <label class="field"><span>Jeito de mostrar</span><select id="av-modo"><option value="bloco" ${p.modo === "bloco" ? "selected" : ""}>Legenda inteira (aparece e some)</option><option value="rolando" ${p.modo === "rolando" ? "selected" : ""}>Linhas subindo (como na TV)</option></select></label>
          <label class="field"><span>Fundo</span><select id="av-fundo">${[["transparente", "Transparente"], ["00ff00", "Verde (para recorte)"], ["0000ff", "Azul (para recorte)"], ["000000", "Preto"]].map(([v, t]) => `<option value="${v}" ${v === p.fundo ? "selected" : ""}>${t}</option>`).join("")}</select></label>
          <label class="field"><span>Tamanho</span><input type="number" id="av-tam" min="14" max="160" value="${esc(p.tam)}" style="width:90px"></label>
          <label class="field"><span>Posição</span><select id="av-pos"><option value="baixo" ${p.pos === "baixo" ? "selected" : ""}>Embaixo</option><option value="cima" ${p.pos === "cima" ? "selected" : ""}>Em cima</option></select></label>
          <label class="field"><span>Faixa</span><select id="av-faixa"><option value="">Original</option><option value="traducao" ${p.faixa === "traducao" ? "selected" : ""}>Tradução ao vivo</option></select></label>
          <label class="field" style="justify-content:end"><span><input type="checkbox" id="av-caixa" ${p.caixa ? "checked" : ""}> Tarja escura atrás</span></label>
        </div>
        <label class="field"><span>Endereço para o programa de transmissão <em>(fonte de navegador)</em></span>
          <div class="row" style="gap:6px"><input type="text" id="av-url" readonly style="flex:1" class="mono"><button class="btn" data-a="copiar">Copiar</button></div></label>
        <div class="row" style="gap:8px;margin-top:8px"><button class="btn" data-a="janela">${ic("tv")} Abrir janela de legenda</button>
          <button class="btn ghost" data-a="limpar">Limpar a tela</button></div>
      </section>
    </div>
    <section class="panel" id="av-ao-vivo">
      <div class="row" style="justify-content:space-between;align-items:center"><h2 style="margin:0">Fila <span class="muted small" id="av-relogio"></span></h2>
        <div class="av-medidor" title="Volume da entrada"><i id="av-nivel"></i></div></div>
      <p class="av-parcial muted" id="av-parcial">Parado.</p>
      <div id="av-fila" class="av-fila"></div>
      <form class="row" id="av-form-texto" style="gap:6px;margin-top:10px"><input type="text" id="av-texto" style="flex:1" placeholder="Texto pronto (entra na hora). Ex.: [MÚSICA]  ou o nome de quem fala"><button class="btn">Mandar</button></form>
      <h2 style="margin-top:18px">Já foi para a tela</h2>
      <div id="av-pub" class="av-pub"></div>
      <div class="row" style="gap:8px;margin-top:10px" id="av-fim" hidden><span class="muted small" id="av-arquivo"></span><button class="btn" data-a="editor">${ic("editor")} Abrir no editor</button></div>
    </section>`;
  const $ = (id) => document.getElementById(id);
  const ler = () => ({ ...avPrefs(), fonte: fonteAtual(), idioma: $("av-idioma").value, modelo: $("av-modelo").value, atraso: Number($("av-atraso").value),
    cliente: $("av-cliente").value, filtro: $("av-filtro").value, modo: $("av-modo").value, fundo: $("av-fundo").value,
    tam: Number($("av-tam").value) || 44, pos: $("av-pos").value, caixa: $("av-caixa").checked,
    traducao: $("av-traducao").value, faixa: $("av-faixa").value });
  function fonteAtual() {
    const v = $("av-fonte").value;
    return v === "arquivo:" || v === "url:" ? v + $("av-extra").value.trim() : v;
  }
  function extra() {
    const v = $("av-fonte").value;
    $("av-extra-l").hidden = !(v === "arquivo:" || v === "url:");
    $("av-extra-t").textContent = v === "url:" ? "Endereço (rtmp, srt, http…)" : "Arquivo";
    $("av-escolher").hidden = v !== "arquivo:";
    $("av-dica-sistema").hidden = !(v === "sistema:" || v === "pulse:@DEFAULT_MONITOR@");
  }
  const url = () => { $("av-url").value = `${r.pagina}&${avEstilo(ler())}`; };
  extra(); url();
  main.onchange = () => { extra(); url(); avSalvar(ler()); };
  main.oninput = () => url();

  let ultimo = null;
  function desenhar(e) {
    ultimo = e;
    const ativo = !!e.ativo;
    $("av-iniciar").hidden = ativo; $("av-parar").hidden = !ativo;
    $("av-config").querySelectorAll("select,input").forEach((x) => { x.disabled = ativo; });
    const msg = $("av-msg");
    if (e.erro) { msg.hidden = false; msg.className = "note err"; msg.textContent = e.erro; }
    else if (ativo && !e.pronto) { msg.hidden = false; msg.className = "note"; msg.textContent = "Preparando o reconhecimento de fala… (na primeira vez pode baixar o modelo)"; }
    else msg.hidden = true;
    $("av-relogio").textContent = ativo ? `· ${fmtHMS(e.segundos || 0)} · ${e.total || 0} legendas` : "";
    const db = e.nivel == null ? -90 : e.nivel;
    $("av-nivel").style.width = `${Math.max(0, Math.min(100, (db + 60) * 1.7))}%`;
    $("av-parcial").textContent = ativo ? (e.parcial ? `Ouvindo: ${e.parcial}` : "Ouvindo…") : "Parado.";
    const fila = $("av-fila");
    const focado = document.activeElement?.closest?.(".av-item")?.dataset.id;
    if (!focado) {
      fila.innerHTML = (e.fila || []).map((l) => `<div class="av-item" data-id="${l.id}">
        <textarea rows="2" data-id="${l.id}">${esc(l.texto)}</textarea>
        <div class="av-acoes"><span class="mono small">${l.faltam.toFixed(1)} s</span>
          <button class="btn sm" data-a="ja" data-id="${l.id}" title="Mandar agora">Agora</button>
          <button class="btn sm ghost" data-a="apagar" data-id="${l.id}" title="Não mostrar">${ic("trash")}</button></div></div>`).join("")
        || `<p class="muted small">${ativo ? "Nada esperando." : ""}</p>`;
    } else {
      fila.querySelectorAll(".av-item").forEach((d) => {
        const l = (e.fila || []).find((x) => String(x.id) === d.dataset.id);
        const s = d.querySelector(".mono"); if (l && s) s.textContent = l.segurada ? "corrigindo" : `${l.faltam.toFixed(1)} s`;
      });
    }
    $("av-pub").innerHTML = (e.publicadas || []).slice().reverse().map((l) => `<div class="av-linha">${esc(l.texto).replace(/\n/g, "<br>")}${(e.traducoes || {})[l.id] ? `<div class="av-trad">${esc(e.traducoes[l.id]).replace(/\n/g, "<br>")}</div>` : ""}${l.manual ? ` <span class="muted small">(digitada)</span>` : l.editada ? ` <span class="muted small">(corrigida)</span>` : ""}</div>`).join("") || `<p class="muted small">Nada ainda.</p>`;
    $("av-fim").hidden = !(e.srt && !ativo && e.total);
    $("av-arquivo").textContent = e.srt ? `Arquivo do evento: ${e.srt}` : "";
  }
  const atualizar = async () => { try { desenhar(await api("GET", "/api/aovivo/estado")); } catch { /* tenta de novo */ } };
  desenhar(r.estado || {});
  every(400, atualizar);

  /* corrigir: enquanto o campo está com o cursor a legenda não sai (o servidor guarda a correção ao sair do campo) */
  main.addEventListener("focusin", (ev) => {
    const t = ev.target.closest(".av-item textarea"); if (!t) return;
    api("POST", `/api/aovivo/linha/${t.dataset.id}`, { acao: "editar", texto: t.value, segurar: true }).catch(() => {});
  });
  main.addEventListener("focusout", (ev) => {
    const t = ev.target.closest(".av-item textarea"); if (!t || t.dataset.feito) return;
    api("POST", `/api/aovivo/linha/${t.dataset.id}`, { acao: "editar", texto: t.value }).catch(() => {});   // já saiu: nada a fazer
  });
  main.addEventListener("keydown", (ev) => {
    const t = ev.target.closest(".av-item textarea"); if (!t) return;
    if (ev.key === "Enter" && !ev.shiftKey) {        // Enter: corrige e manda já
      ev.preventDefault();
      api("POST", `/api/aovivo/linha/${t.dataset.id}`, { acao: "editar", texto: t.value })
        .then(() => api("POST", `/api/aovivo/linha/${t.dataset.id}`, { acao: "publicar" })).then(() => { t.dataset.feito = "1"; t.blur(); }).catch((e) => toast(e.message));
    }
    if (ev.key === "Escape") { ev.preventDefault(); t.dataset.feito = "1"; api("POST", `/api/aovivo/linha/${t.dataset.id}`, { acao: "descartar" }).then(() => t.blur()); }
  });
  $("av-form-texto").onsubmit = async (ev) => {
    ev.preventDefault();
    const t = $("av-texto").value.trim(); if (!t) return;
    try { desenhar(await api("POST", "/api/aovivo/texto", { texto: t })); $("av-texto").value = ""; } catch (e) { toast(e.message); }
  };
  main.onclick = async (ev) => {
    const b = ev.target.closest("[data-a]"); if (!b) return;
    const a = b.dataset.a;
    try {
      if (a === "escolher") { const path = await pickPath("media"); if (path) { $("av-extra").value = path; avSalvar(ler()); } }
      if (a === "iniciar") {
        const p2 = ler(); avSalvar(p2);
        if (p2.fonte.endsWith(":")) { toast("Escolha o arquivo ou escreva o endereço."); return; }
        desenhar(await api("POST", "/api/aovivo/iniciar", { fonte: p2.fonte, idioma: p2.idioma, modelo: p2.modelo, atraso: p2.atraso, cliente: p2.cliente || null, filtro: p2.filtro, traducao: p2.traducao }));
      }
      if (a === "parar") desenhar(await api("POST", "/api/aovivo/parar"));
      if (a === "ja") desenhar(await api("POST", `/api/aovivo/linha/${b.dataset.id}`, { acao: "publicar" }));
      if (a === "apagar") desenhar(await api("POST", `/api/aovivo/linha/${b.dataset.id}`, { acao: "descartar" }));
      if (a === "limpar") { await api("POST", "/api/aovivo/limpar"); toast("Tela limpa."); }
      if (a === "copiar") { await navigator.clipboard.writeText($("av-url").value).catch(() => {}); toast("Endereço copiado. Cole como fonte de navegador no programa de transmissão."); }
      if (a === "janela") await api("POST", "/api/aovivo/janela", { estilo: avEstilo(ler()) });
      if (a === "editor" && ultimo?.srt) {
        const o = await api("POST", "/api/editor/open", { srt: ultimo.srt, video: "", profile_key: "" });
        location.hash = `#/editor/${o.sid}`;
      }
    } catch (e) { if (!e.licenca) toast(e.message); }
  };
}
