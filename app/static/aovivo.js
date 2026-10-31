/* CNT Legendas — legenda ao vivo (P-05): escolher a entrada, ligar, corrigir na fila, saídas. */
"use strict";

const AV_PREF = "cnt.aovivo";
const AV_PADRAO = { fonte: "url:", motor: "auto", modelo: "small", atraso: 3, idioma: "pt-BR", modo: "bloco", fundo: "transparente", cor: "ffffff", tam: 44,
  pos: "baixo", caixa: false, letra: "padrao", peso: 600, contorno: 2, ccor: "000000", sombra: true, tcor: "000000", topac: 78, linhas: 3 };
function avPrefs() {
  try { return { ...AV_PADRAO, ...JSON.parse(getPref(AV_PREF, "{}") || "{}") }; }
  catch { return { ...AV_PADRAO }; }
}
function avSalvar(p) { setPref(AV_PREF, JSON.stringify(p)); }

function avEstilo(p) {
  const q = new URLSearchParams({ modo: p.modo, fundo: p.fundo, cor: p.cor, tam: String(p.tam), pos: p.pos, fonte: p.letra,
    peso: String(p.peso), contorno: String(p.contorno), ccor: p.ccor, sombra: p.sombra ? "1" : "0", linhas: String(p.linhas) });
  if (p.faixa === "traducao") q.set("faixa", "traducao");
  if (p.caixa) { q.set("caixa", "1"); q.set("tcor", p.tcor); q.set("topac", String(p.topac)); }
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
            <select id="av-fonte"><option value="url:" ${String(p.fonte || "").startsWith("url:") ? "selected" : ""}>Link de uma live ou de um vídeo</option>${opts}<option value="arquivo:" ${String(p.fonte || "").startsWith("arquivo:") ? "selected" : ""}>Um arquivo de vídeo ou áudio (ensaio)</option></select></label>
          <p class="note" id="av-dica-sistema" hidden>Abra a live (de qualquer site) no navegador e deixe tocando com som. Tudo o que tocar no computador entra na legenda: feche outros vídeos e desligue os sons de aviso enquanto legenda.</p>
          <label class="field" id="av-extra-l" hidden><span id="av-extra-t">Arquivo</span>
            <div class="row" style="gap:6px"><input type="text" id="av-extra" style="flex:1" value="${esc(String(p.fonte || "").replace(/^(arquivo|url):/, ""))}"><button class="btn" data-a="escolher" id="av-escolher">Escolher…</button></div></label>
          <div class="row" style="gap:12px;flex-wrap:wrap">
            <label class="field"><span>Idioma falado</span><select id="av-idioma">${[["pt-BR", "Português"], ["en", "Inglês"], ["es", "Espanhol"]].map(([v, t]) => `<option value="${v}" ${v === p.idioma ? "selected" : ""}>${t}</option>`).join("")}</select></label>
            <label class="field"><span>Reconhecimento</span><select id="av-motor">${[["auto", "Automático (placa de vídeo, se houver)"], ["gpu", "Placa de vídeo (rápido, no computador)"], ["cpu", "Processador do computador (mais lento)"], ["nuvem", "IA na nuvem (mais precisa; usa a sua chave de IA, com custo)"]].map(([v, t]) => `<option value="${v}" ${v === p.motor ? "selected" : ""}>${t}</option>`).join("")}</select></label>
            <label class="field" id="av-modelo-l"><span>Precisão</span><select id="av-modelo">${[["base", "Rápida (computador simples)"], ["small", "Equilibrada"], ["medium", "Alta (precisa de placa de vídeo)"]].map(([v, t]) => `<option value="${v}" ${v === p.modelo ? "selected" : ""}>${t}</option>`).join("")}</select></label>
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
          <label class="field"><span>Letra</span><select id="av-letra">${[["padrao", "Padrão"], ["larga", "Larga"], ["estreita", "Estreita"], ["serifa", "Com serifa"], ["forte", "Forte (cartaz)"], ["maquina", "Máquina de escrever"]].map(([v, t]) => `<option value="${v}" ${v === p.letra ? "selected" : ""}>${t}</option>`).join("")}</select></label>
          <label class="field"><span>Peso</span><select id="av-peso">${[[400, "Normal"], [600, "Seminegrito"], [800, "Negrito"]].map(([v, t]) => `<option value="${v}" ${Number(p.peso) === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
          <label class="field"><span>Cor do texto</span><input type="color" id="av-cor" value="#${esc(p.cor)}"></label>
          <label class="field"><span>Contorno</span><select id="av-contorno">${[0, 1, 2, 3, 4, 6, 8].map((v) => `<option value="${v}" ${Number(p.contorno) === v ? "selected" : ""}>${v ? `${v} px` : "Sem contorno"}</option>`).join("")}</select></label>
          <label class="field"><span>Cor do contorno</span><input type="color" id="av-ccor" value="#${esc(p.ccor)}"></label>
          <label class="field" style="justify-content:end"><span><input type="checkbox" id="av-sombra" ${p.sombra ? "checked" : ""}> Sombra</span></label>
          <label class="field"><span>Posição</span><select id="av-pos"><option value="baixo" ${p.pos === "baixo" ? "selected" : ""}>Embaixo</option><option value="cima" ${p.pos === "cima" ? "selected" : ""}>Em cima</option></select></label>
          <label class="field"><span>Faixa</span><select id="av-faixa"><option value="">Original</option><option value="traducao" ${p.faixa === "traducao" ? "selected" : ""}>Tradução ao vivo</option></select></label>
          <label class="field" style="justify-content:end"><span><input type="checkbox" id="av-caixa" ${p.caixa ? "checked" : ""}> Tarja atrás do texto</span></label>
          <label class="field" id="av-tarja-cor-l"><span>Cor da tarja</span><input type="color" id="av-tcor" value="#${esc(p.tcor)}"></label>
          <label class="field" id="av-tarja-op-l"><span>Transparência da tarja</span><select id="av-topac">${[[100, "Sólida"], [78, "Pouca"], [55, "Média"], [35, "Muita"]].map(([v, t]) => `<option value="${v}" ${Number(p.topac) === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
          <label class="field" id="av-linhas-l"><span>Linhas na tela</span><select id="av-linhas">${[1, 2, 3, 4].map((v) => `<option value="${v}" ${Number(p.linhas) === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        </div>
        <div class="av-previa" title="Prévia da legenda com o visual escolhido"><iframe id="av-previa" tabindex="-1" aria-label="Prévia da legenda"></iframe></div>
        <label class="field"><span>Link da legenda <em>(no programa de transmissão: fonte de navegador; funciona neste computador)</em></span>
          <div class="row" style="gap:6px"><input type="text" id="av-url" readonly style="flex:1" class="mono"><button class="btn" data-a="copiar">Copiar</button></div></label>
        <div class="row" style="gap:8px;margin-top:8px"><button class="btn" data-a="janela">${ic("tv")} Abrir janela de legenda</button>
          <button class="btn ghost" data-a="limpar">Limpar a tela</button></div>
      </section>
    </div>
    <section class="panel" id="av-player-box" hidden>
      <div class="row" style="justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><h2 style="margin:0">Player <span class="muted small" id="av-midia"></span></h2>
        <button class="btn sm ghost" data-a="navegador">Abrir no navegador</button></div>
      <div class="av-player"><div id="av-player"></div><iframe class="av-sobre" id="av-sobre" tabindex="-1" aria-hidden="true"></iframe></div>
      <p class="muted small" style="margin-top:8px">O vídeo começa sem som (o programa ouve a transmissão por conta própria); ative o som no player se quiser ouvir. A legenda aparece por cima com o visual escolhido, com alguns segundos de atraso.</p>
    </section>
    <section class="panel" id="av-ao-vivo">
      <div class="row" style="justify-content:space-between;align-items:center"><h2 style="margin:0">Fila <span class="muted small" id="av-relogio"></span></h2>
        <div class="av-medidor" title="Volume da entrada"><i id="av-nivel"></i></div></div>
      <p class="av-status" id="av-status" aria-live="polite"><span class="av-luz"></span><span id="av-status-t">Parado.</span></p>
      <p class="muted small" id="av-srt"></p>
      <p class="av-parcial muted" id="av-parcial">Parado.</p>
      <div id="av-fila" class="av-fila"></div>
      <form class="row" id="av-form-texto" style="gap:6px;margin-top:10px"><input type="text" id="av-texto" style="flex:1" placeholder="Texto pronto (entra na hora). Ex.: [MÚSICA]  ou o nome de quem fala"><button class="btn">Mandar</button></form>
      <h2 style="margin-top:18px">Já foi para a tela</h2>
      <div id="av-pub" class="av-pub"></div>
      <div class="row" style="gap:8px;margin-top:10px" id="av-fim" hidden><span class="muted small" id="av-arquivo"></span><button class="btn" data-a="editor">${ic("editor")} Abrir no editor</button></div>
    </section>`;
  const $ = (id) => document.getElementById(id);
  const ler = () => ({ ...avPrefs(), fonte: fonteAtual(), idioma: $("av-idioma").value, modelo: $("av-modelo").value, motor: $("av-motor").value, atraso: Number($("av-atraso").value),
    cliente: $("av-cliente").value, filtro: $("av-filtro").value, modo: $("av-modo").value, fundo: $("av-fundo").value,
    tam: Number($("av-tam").value) || 44, pos: $("av-pos").value, caixa: $("av-caixa").checked,
    cor: $("av-cor").value.slice(1), letra: $("av-letra").value, peso: Number($("av-peso").value), contorno: Number($("av-contorno").value),
    ccor: $("av-ccor").value.slice(1), sombra: $("av-sombra").checked, tcor: $("av-tcor").value.slice(1), topac: Number($("av-topac").value),
    linhas: Number($("av-linhas").value),
    traducao: $("av-traducao").value, faixa: $("av-faixa").value });
  function fonteAtual() {
    const v = $("av-fonte").value;
    return v === "arquivo:" || v === "url:" ? v + $("av-extra").value.trim() : v;
  }
  function extra() {
    const v = $("av-fonte").value;
    $("av-extra-l").hidden = !(v === "arquivo:" || v === "url:");
    $("av-extra-t").textContent = v === "url:" ? "Link (copie da barra de endereço do navegador: página da live ou do vídeo, ou endereço da transmissão)" : "Arquivo";
    $("av-extra").placeholder = v === "url:" ? "https://…" : "";
    $("av-escolher").hidden = v !== "arquivo:";
    $("av-modelo-l").hidden = $("av-motor").value === "nuvem";      // na nuvem não há "precisão" a escolher
    $("av-dica-sistema").hidden = !(v === "sistema:" || v === "pulse:@DEFAULT_MONITOR@");
  }
  let previaT = null;
  const url = () => {
    const p2 = ler();
    $("av-url").value = `${r.pagina}&${avEstilo(p2)}`;
    $("av-tarja-cor-l").hidden = $("av-tarja-op-l").hidden = !p2.caixa;
    $("av-linhas-l").hidden = p2.modo !== "rolando";
    clearTimeout(previaT);           // prévia: a mesma página da legenda, com texto de exemplo
    const esc = (el) => ((el.getBoundingClientRect().width || 960) / 1920).toFixed(3);
    previaT = setTimeout(() => { $("av-previa").src = `${r.pagina}&${avEstilo(p2)}&demo=1&avisos=0&escala=${esc($("av-previa"))}`; }, 150);
    const sobre = `${r.pagina}&${avEstilo({ ...p2, fundo: "transparente" })}&avisos=0&escala=${esc($("av-player-box").hidden ? main : $("av-player"))}`;
    if ($("av-sobre").dataset.src !== sobre) { $("av-sobre").dataset.src = sobre; $("av-sobre").src = sobre; }
  };
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
    else if (ativo && e.aviso) { msg.hidden = false; msg.className = "note warn"; msg.textContent = e.aviso; }
    else if (ativo && !e.pronto) { msg.hidden = false; msg.className = "note"; msg.textContent = e.etapa || "Iniciando o reconhecimento de fala…"; }
    else msg.hidden = true;
    // status: o que está acontecendo agora, em palavras
    const atraso = Math.round(e.atraso_rec || 0);
    const [cls, txt] = !ativo ? ["", e.erro ? "Parou." : "Parado."]
      : !e.pronto ? ["prep", e.etapa || "Iniciando o reconhecimento de fala…"]
      : (e.nivel ?? -90) < -55 ? ["ok", `Ouvindo, mas a entrada está em silêncio${e.motor_nome ? ` · ${e.motor_nome}` : ""}. Confira se a live está tocando.`]
      : atraso >= 6 ? ["lento", `Ouvindo · ${e.motor_nome || "reconhecimento"} com ${atraso} s de fala esperando (a legenda sai atrasada)`]
      : ["ok", `Ouvindo e reconhecendo em dia · ${e.motor_nome || ""}`.replace(/ · $/, "")];
    $("av-status").className = `av-status ${cls}`; $("av-status-t").textContent = txt;
    $("av-relogio").textContent = ativo ? `· ${fmtHMS(e.segundos || 0)} · ${e.total || 0} legendas${e.motor_nome ? ` · ${e.motor_nome}` : ""}` : "";
    // player: monta uma vez por mídia (refazer o iframe a cada atualização recomeçaria o vídeo)
    const pl = (e.midia || {}).player || {};
    $("av-player-box").hidden = !(ativo && pl.src);
    if (pl.src && $("av-player").dataset.src !== pl.src && ativo) {
      $("av-player").dataset.src = pl.src;
      $("av-player").innerHTML = pl.tipo === "iframe"
        ? `<iframe src="${esc(pl.src)}" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`
        : pl.tipo === "video" ? `<video src="${esc(pl.src)}" autoplay muted controls playsinline></video>`
        : `<div class="av-sem-player"><p>Este site não deixa mostrar o vídeo aqui. A legenda continua normalmente; use “Abrir no navegador” para assistir.</p></div>`;
      $("av-midia").textContent = [e.midia.titulo, e.midia.ao_vivo ? "ao vivo" : "gravado"].filter(Boolean).join(" · ");
      requestAnimationFrame(url);       // a legenda por cima do player na proporção do player
    }
    if (!ativo) { $("av-player").dataset.src = ""; $("av-player").innerHTML = ""; }
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
    $("av-srt").textContent = ativo && e.srt ? `Gravando a legenda em: ${e.srt}` : "";
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
        desenhar(await api("POST", "/api/aovivo/iniciar", { fonte: p2.fonte, idioma: p2.idioma, modelo: p2.modelo, motor: p2.motor, atraso: p2.atraso, cliente: p2.cliente || null, filtro: p2.filtro, traducao: p2.traducao }));
      }
      if (a === "parar") desenhar(await api("POST", "/api/aovivo/parar"));
      if (a === "ja") desenhar(await api("POST", `/api/aovivo/linha/${b.dataset.id}`, { acao: "publicar" }));
      if (a === "apagar") desenhar(await api("POST", `/api/aovivo/linha/${b.dataset.id}`, { acao: "descartar" }));
      if (a === "limpar") { await api("POST", "/api/aovivo/limpar"); toast("Tela limpa."); }
      if (a === "copiar") { await navigator.clipboard.writeText($("av-url").value).catch(() => {}); toast("Endereço copiado. Cole como fonte de navegador no programa de transmissão."); }
      if (a === "janela") await api("POST", "/api/aovivo/janela", { estilo: avEstilo(ler()) });
      if (a === "navegador") {
        const link = ultimo?.fonte?.startsWith("url:") ? ultimo.fonte.slice(4) : ((ultimo?.midia || {}).player || {}).src;
        if (link) await api("POST", "/api/abrir-link", { url: link });
      }
      if (a === "editor" && ultimo?.srt) {
        const o = await api("POST", "/api/editor/open", { srt: ultimo.srt, video: "", profile_key: "" });
        location.hash = `#/editor/${o.sid}`;
      }
    } catch (e) { if (!e.licenca) toast(e.message); }
  };
}
