/* CNT Legendas — glossário geral e do projeto (o do cliente fica na tela do cliente).
   Na tradução entram os três; o mesmo termo em mais de um: vale o mais específico (projeto > cliente > geral). */
"use strict";

async function editarGlossario({ titulo, explica, url, nomeArquivo }) {
  let lista = (await api("GET", url)).glossario.map((g) => ({ ...g }));
  const m = modal(titulo, `<p class="muted small">${esc(explica)}</p>
      <div class="gl-wrap"><table class="table" id="gl-tab"></table></div>
      <div class="row"><button class="btn" data-g="add">Adicionar termo</button><button class="btn" data-g="imp">Importar CSV</button>
        <button class="btn" data-g="exp">Exportar CSV</button></div>`,
    `<button class="btn" data-g="x">Cancelar</button><button class="btn primary" data-g="ok">Salvar</button>`, { wide: true });
  const desenhar = () => {
    m.$("#gl-tab").innerHTML = `<thead><tr><th style="width:34%">Termo</th><th style="width:34%">Tradução</th><th>Observação</th><th></th></tr></thead><tbody>`
      + (lista.length ? lista.map((g, i) => `<tr>
        <td><input type="text" data-i="${i}" data-k="term" value="${esc(g.term)}" aria-label="Termo"></td>
        <td><input type="text" data-i="${i}" data-k="translation" value="${esc(g.translation)}" aria-label="Tradução"></td>
        <td><input type="text" data-i="${i}" data-k="note" value="${esc(g.note)}" aria-label="Observação"></td>
        <td><button class="btn link" data-g="del" data-i="${i}">Remover</button></td></tr>`).join("")
        : `<tr><td colspan="4" class="muted">Nenhum termo ainda.</td></tr>`) + "</tbody>";
  };
  desenhar();
  m.$("#gl-tab").addEventListener("input", (e) => { const t = e.target; if (t.dataset.i != null) lista[+t.dataset.i][t.dataset.k] = t.value; });
  m.ov.onclick = async (e) => {
    const b = e.target.closest("[data-g]");
    if (e.target === m.ov || b?.dataset.g === "x") return m.close();
    if (!b) return;
    try {
      const g = b.dataset.g;
      if (g === "add") { lista.push({ term: "", translation: "", note: "" }); desenhar(); m.$(`#gl-tab input[data-i="${lista.length - 1}"]`).focus(); }
      if (g === "del") { lista.splice(+b.dataset.i, 1); desenhar(); }
      if (g === "imp") {
        const { paths } = await api("POST", "/api/dialog", { kind: "csv" });
        if (!paths.length) return;
        const { glossary } = await api("POST", "/api/glossary/import", { path: paths[0] });
        const conhecidos = new Set(lista.map((x) => x.term.toLowerCase()));
        const novos = glossary.filter((x) => !conhecidos.has(x.term.toLowerCase()));
        lista = lista.concat(novos); desenhar();
        toast(`${novos.length} termos importados. Clique em Salvar para guardar.`);
      }
      if (g === "exp") {
        const { paths } = await api("POST", "/api/dialog", { kind: "folder", title: "Onde salvar o glossário" });
        if (!paths.length) return;
        const r = await api("POST", "/api/glossary/export", { folder: paths[0], name: nomeArquivo, glossary: lista });
        toast(`Glossário salvo em ${r.path}`);
      }
      if (g === "ok") {
        const r = await api("PUT", url, { glossario: lista.filter((x) => x.term.trim()) });
        m.close(); toast(`Glossário salvo (${r.termos} termo${r.termos === 1 ? "" : "s"}).`);
      }
    } catch (err) { toast(err.message, true); }
  };
}

function glossarioGeral() {
  return editarGlossario({ titulo: "Glossário geral", url: "/api/glossario/geral", nomeArquivo: "glossario geral",
    explica: "Vale em todos os trabalhos, de qualquer cliente e projeto. Use para termos que você sempre traduz igual. Se o mesmo termo estiver no glossário do cliente ou do projeto, vale o deles." });
}

function glossarioProjeto(obraId, nome) {
  return editarGlossario({ titulo: `Glossário do projeto · ${nome}`, url: `/api/obras/${obraId}/glossario`, nomeArquivo: `glossario ${nome}`,
    explica: "Só para este projeto (personagens, lugares, nomes próprios da série ou do filme). Não se mistura com os outros projetos do mesmo cliente. Na tradução, vale mais que o do cliente e o geral." });
}

/* Linha curta para mostrar quais glossários entram na tradução. */
async function textoGlossarioEfetivo({ cliente, sid }) {
  try {
    const r = await api("GET", `/api/glossario/efetivo?${new URLSearchParams({ ...(cliente ? { cliente } : {}), ...(sid ? { sid } : {}) })}`);
    if (!r.total) return "Sem glossário nesta tradução.";
    const partes = [["geral", "geral"], ["cliente", "do cliente"], ["projeto", "do projeto"]].filter(([k]) => r.niveis[k]).map(([k, t]) => `${r.niveis[k]} ${t}`);
    return `Glossário: ${r.total} termo${r.total === 1 ? "" : "s"} (${partes.join(" · ")}).`;
  } catch { return ""; }
}
