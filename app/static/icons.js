/* Ícones de traço (desenho próprio, sem dependências). ic("home") → <svg>. */
"use strict";
const ICONS = {
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3M8 21h8",
  home: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  open: "M3 18V7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v1M3 18a2 2 0 0 0 2 2h12l3.5-8H7.5L4 20",
  editor: "M3 5h18v14H3zM7 13h6M7 16h10",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  chart: "M4 20V11M10 20V5M16 20v-6M2 20h20",
  users: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M22 19v-1a4 4 0 0 0-3-3.9M16 4.2a3.5 3.5 0 0 1 0 6.6",
  rules: "M10 6h11M10 12h11M10 18h11M3 6l1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17",
  settings: "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4",
  chevron: "M15 18l-6-6 6-6",
  right: "M9 6l6 6-6 6",
  plus: "M12 5v14M5 12h14",
  film: "M3 4h18v16H3zM7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4",
  tv: "M3 7h18v12H3zM8 3l4 4 4-4",
  clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  play: "M8 5l11 7-11 7z",
  check: "M5 12l5 5 9-10",
  file: "M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8zM14 3v5h5",
  text: "M4 6h16M4 12h16M4 18h10",
  words: "M4 7V5h16v2M12 5v14M9 19h6",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  refresh: "M20 11a8 8 0 0 0-14.9-3M4 5v4h4M4 13a8 8 0 0 0 14.9 3M20 19v-4h-4",
  pin: "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4",
  sync: "M3 12h4l3-8 4 16 3-8h4",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5",
  download: "M12 4v12M7 11l5 5 5-5M5 20h14",
  nota: "M5 4h14v11l-5 5H5zM14 20v-5h5M8 9h8M8 12.5h5",
  foco: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12.5a.5.5 0 1 0 0-1 .5.5 0 0 0 0 1",
};
function ic(name, cls = "") {
  return `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name] || ""}"/></svg>`;
}
