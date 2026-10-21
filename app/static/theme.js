/* aplica o tema antes de desenhar a página (sem "piscar" claro/escuro) */
(function () {
  var t = "dark";
  try { t = localStorage.getItem("cnt.tema") || "dark"; } catch (e) {}
  if (t === "auto") t = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);
})();
