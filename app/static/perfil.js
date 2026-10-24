/* CNT Legendas — perfil na nuvem (2.13): situação, sincronizar, restaurar de outro computador, exportar/importar. */
"use strict";

const fmtQuando = (iso) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");

function perfilResumo(p) {
  if (!p) return "Carregando…";
  if (!p.disponivel) return "Com uma licença ativada, configurações, clientes, glossários e regras ficam guardados no servidor. Enquanto isso, use exportar/importar arquivo.";
  if (p.estado === "erro") return `Não sincronizou: ${p.erro}`;
  if (p.estado === "sincronizando") return "Sincronizando…";
  const emp = p.workspace ? ` · Workspace ${p.workspace.nome ? `“${p.workspace.nome}”` : "da empresa"}` : "";
  return p.ultima ? `Guardado no servidor · última sincronização ${fmtQuando(p.ultima)}${emp}` : `Ainda não sincronizado${emp}`;
}

function resumoAplicado(r) {
  const partes = [];
  if (r.clientes_novos) partes.push(`${r.clientes_novos} cliente${r.clientes_novos > 1 ? "s" : ""} novo${r.clientes_novos > 1 ? "s" : ""}`);
  if (r.clientes_atualizados) partes.push(`${r.clientes_atualizados} atualizado${r.clientes_atualizados > 1 ? "s" : ""}`);
  if (r.perfis) partes.push(`${r.perfis} perfil${r.perfis > 1 ? "s" : ""} de regras`);
  if (r.configuracoes) partes.push("configurações");
  return partes.length ? `Perfil aplicado: ${partes.join(", ")}.` : "Perfil aplicado (nada novo).";
}

/* Computador recém-ativado: oferece trazer o perfil de outro computador da mesma conta. */
async function ofertaRestaurar(p) {
  const outros = p.outros || [];
  if (!outros.length) return;
  const k = await ask("Trazer o seu perfil?",
    `<p>Encontramos ${outros.length === 1 ? "um perfil guardado" : "perfis guardados"} da sua conta. Restaurar traz para este computador as
      configurações, os clientes com glossários e os perfis de regras. Nada daqui é apagado. As chaves de IA não vêm: digite de novo em Configurações.</p>
     <div class="stack">${outros.map((o) => `<label class="check"><input type="radio" name="pf-origem" value="${o.id}" ${o === outros[0] ? "checked" : ""}>
       <span><b>${esc(o.nome)}</b> · última alteração ${esc(fmtQuando(o.atualizado_em))}${o.computador_ativo ? "" : " · computador liberado"}</span></label>`).join("")}</div>`,
    [["zero", "Começar do zero"], ["depois", "Depois"], ["ok", "Restaurar", "primary"]]);
  if (k === "zero") { await api("POST", "/api/perfil/comecar-do-zero"); toast("Tudo bem: este computador começa com um perfil novo."); }
  if (k === "ok") {
    const id = document.querySelector("input[name=pf-origem]:checked")?.value || outros[0].id;
    try {
      const r = await api("POST", "/api/perfil/restaurar", { id: Number(id) });
      toast(resumoAplicado(r.resumo));
      await loadState(); router();
    } catch (e) { toast(e.message, true); }
  }
}

async function perfilModal() {
  let p = await api("GET", "/api/perfil");
  const m = modal("Perfil na nuvem", `<p>${esc(perfilResumo(p))}</p>
    <p class="muted small">Vai para o servidor: configurações (menos as chaves de IA e as pastas deste computador), clientes com glossários e perfis de regras.
      Um perfil por licença ativada (por computador). O texto das legendas e os vídeos nunca saem do computador.</p>
    ${p.disponivel && (p.outros || []).length ? `<h3>Outros computadores da sua conta</h3><div class="stack">${p.outros.map((o) => `<div class="row" style="justify-content:space-between">
      <span><b>${esc(o.nome)}</b> <span class="muted small">· ${esc(fmtQuando(o.atualizado_em))}</span></span>
      <button class="btn" data-p="restaurar" data-id="${o.id}">Trazer para cá</button></div>`).join("")}</div>` : ""}
    <h3>Arquivo</h3><p class="muted small">Para guardar uma cópia ou levar a outro computador sem internet.</p>`,
    `<button class="btn" data-p="exportar">Exportar arquivo</button><button class="btn" data-p="importar">Importar arquivo</button>
     ${p.disponivel ? `<button class="btn primary" data-p="sync">Sincronizar agora</button>` : ""}<button class="btn" data-p="x">Fechar</button>`);
  m.ov.onclick = async (e) => {
    const b = e.target.closest("[data-p]");
    if (e.target === m.ov || b?.dataset.p === "x") return m.close();
    if (!b) return;
    try {
      if (b.dataset.p === "sync") { b.disabled = true; p = await api("POST", "/api/perfil/sincronizar"); toast(p.estado === "erro" ? p.erro : "Perfil sincronizado.", p.estado === "erro"); m.close(); renderSettings(); }
      if (b.dataset.p === "exportar") { const r = await api("POST", "/api/perfil/exportar"); if (r.ok) toast(`Perfil exportado em ${r.path}.`); }
      if (b.dataset.p === "importar") { const r = await api("POST", "/api/perfil/importar"); if (r.ok) { toast(resumoAplicado(r.resumo)); m.close(); await loadState(); renderSettings(); } }
      if (b.dataset.p === "restaurar") {
        const ok = await ask("Trazer este perfil?", "<p>As configurações, clientes e perfis de regras dele são juntados aos deste computador (o que vier substitui o que tiver o mesmo nome). Nada é apagado.</p>",
          [["n", "Cancelar"], ["s", "Trazer", "primary"]]);
        if (ok !== "s") return;
        const r = await api("POST", "/api/perfil/restaurar", { id: Number(b.dataset.id) });
        toast(resumoAplicado(r.resumo)); m.close(); await loadState(); renderSettings();
      }
    } catch (ex) { toast(ex.message, true); b.disabled = false; }
  };
}

/* Ao abrir: espera a primeira sincronização e, num computador recém-ativado, oferece restaurar. */
async function perfilAoAbrir() {
  for (const wait of [25000, 20000, 30000]) {
    await new Promise((r) => setTimeout(r, wait));
    try {
      const p = await api("GET", "/api/perfil");
      if (p.sugerir_restaurar) return ofertaRestaurar(p);
      if (p.estado === "ok" || !p.disponivel) return;
    } catch { return; }
  }
}
