/* Página de legenda ao vivo (fonte de navegador / janela para capturar).
   Opções no endereço: modo=bloco|rolando, fundo=00ff00|transparente, cor=ffffff, tam=44, linhas=3, pos=baixo|cima, caixa=1 */
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
  area.style.color = hex(q.get("cor"), "#ffffff");
  area.style.fontSize = Math.max(14, Math.min(160, parseInt(q.get("tam") || "44", 10) || 44)) + "px";
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
      if (ev.tipo === "legenda") mostrar(ev.texto || "");
      else if (ev.tipo === "limpar") { clearTimeout(timer); area.innerHTML = ""; }
    };
  }
  ligar();
})();
