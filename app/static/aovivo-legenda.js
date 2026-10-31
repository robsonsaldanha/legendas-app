/* Página de legenda ao vivo (fonte de navegador / janela para capturar).
   Opções no endereço: faixa=traducao, modo=bloco|rolando, fundo=00ff00|transparente, cor=ffffff, tam=44, linhas=3,
   pos=baixo|cima, fonte=padrao|larga|estreita|serifa|forte|maquina, peso=400|600|800, contorno=0..10 (px),
   ccor=000000, sombra=0|1, caixa=1 (tarja), tcor=000000, topac=0..100, demo=1 (texto de exemplo, sem ligar),
   escala=0.3 (tamanho proporcional numa área menor que 1920 px, como a prévia da tela) */
"use strict";
(() => {
  const q = new URLSearchParams(location.search);
  const hex = (v, d) => (/^[0-9a-f]{3,8}$/i.test(v || "") ? "#" + v : d);
  const modo = q.get("modo") === "rolando" ? "rolando" : "bloco";
  const fundo = q.get("fundo") || "transparente";
  document.body.style.background = fundo === "transparente" ? "transparent" : hex(fundo, "transparent");
  if (q.get("pos") === "cima") document.body.classList.add("cima");
  if (q.get("caixa") === "1") document.body.classList.add("caixa");
  const area = document.getElementById("area");
  const num = (k, d, a, b) => Math.max(a, Math.min(b, Number.isFinite(parseFloat(q.get(k))) ? parseFloat(q.get(k)) : d));
  const FONTES = { padrao: '"Inter", "Segoe UI", Arial, sans-serif', larga: 'Verdana, "DejaVu Sans", sans-serif',
    estreita: '"Arial Narrow", "Roboto Condensed", Tahoma, sans-serif', serifa: 'Georgia, "Times New Roman", serif',
    forte: 'Impact, "Arial Black", sans-serif', maquina: '"Courier New", "Liberation Mono", monospace' };
  area.style.color = hex(q.get("cor"), "#ffffff");
  const escala = num("escala", 1, 0.05, 4);          // prévia/player da tela: proporção de um vídeo de 1920 px de largura
  area.style.fontSize = num("tam", 44, 14, 160) * escala + "px";
  area.style.fontFamily = FONTES[q.get("fonte")] || FONTES.padrao;
  area.style.fontWeight = String(num("peso", 600, 300, 900));
  // contorno: um anel de sombras (funciona em qualquer fonte); sombra suave opcional embaixo
  const w = num("contorno", 2, 0, 10) * Math.max(escala, 0.35), cc = hex(q.get("ccor"), "#000000"), sombras = [];
  for (let i = 0; w > 0 && i < 16; i++) {
    const a = (i / 16) * 2 * Math.PI;
    sombras.push(`${(Math.cos(a) * w).toFixed(2)}px ${(Math.sin(a) * w).toFixed(2)}px 0 ${cc}`);
  }
  if (q.get("sombra") !== "0") sombras.push("0 3px 8px rgba(0,0,0,.75)");
  const css = document.createElement("style");
  const tc = hex(q.get("tcor"), "#000000").slice(1), op = num("topac", 78, 0, 100) / 100;
  const rgb = tc.length === 3 ? tc.split("").map((c) => parseInt(c + c, 16)) : [0, 2, 4].map((i) => parseInt(tc.slice(i, i + 2), 16));
  css.textContent = `.leg { text-shadow: ${sombras.join(", ") || "none"} }
    body.caixa .leg { background: rgba(${rgb.join(",")},${op}); text-shadow: ${w > 0 ? sombras.slice(0, 16).join(", ") : "none"} }`;
  document.head.appendChild(css);
  const faixa = q.get("faixa") === "traducao" ? "traducao" : "";   // segunda faixa: a tradução ao vivo
  const maxLinhas = Math.max(1, Math.min(8, parseInt(q.get("linhas") || "3", 10) || 3));
  let timer = null;

  function mostrar(texto) {
    if (modo === "bloco") {
      area.innerHTML = "";
      const d = document.createElement("div");
      d.className = "leg"; d.textContent = texto; area.appendChild(d);
      clearTimeout(timer);
      const dur = Math.max(2500, Math.min(7000, texto.length * 70));
      timer = setTimeout(() => { d.classList.add("saindo"); setTimeout(() => d.remove(), 300); }, dur);
    } else {
      for (const linha of texto.split("\n")) {
        const d = document.createElement("div");
        d.className = "leg"; d.textContent = linha; area.appendChild(d);
      }
      while (area.children.length > maxLinhas) area.firstElementChild.remove();
      clearTimeout(timer);
      timer = setTimeout(() => { area.innerHTML = ""; }, 12000);   // silêncio longo: limpa a tela
    }
  }

  function ligar() {
    const es = new EventSource("/aovivo/fluxo?k=" + encodeURIComponent(q.get("k") || ""));
    const aviso = document.getElementById("aviso");
    es.onopen = () => { aviso.style.display = "none"; };
    es.onerror = () => { aviso.style.display = q.get("avisos") === "0" ? "none" : "block"; };
    es.onmessage = (m) => {
      let ev; try { ev = JSON.parse(m.data); } catch { return; }
      if (ev.tipo === "legenda" && (ev.faixa || "") === faixa) mostrar(ev.texto || "");
      else if (ev.tipo === "limpar") { clearTimeout(timer); area.innerHTML = ""; }
    };
  }
  if (q.get("demo") === "1") {
    mostrar(q.get("texto") || "Assim fica a legenda ao vivo\ncom duas linhas na tela.");
    clearTimeout(timer);
  } else ligar();
})();
