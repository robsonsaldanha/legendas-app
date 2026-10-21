/* CNT Legendas — perfil de regras: limites técnicos + regras do que pode e do que não pode.
   As regras ativas vão para a IA (API e ChatGPT) e, quando têm verificação ligada, para o Verificar. */
"use strict";

let PROFILE_DRAFT = null;   // usado por "Duplicar" (abre a página já preenchida)

async function renderProfile(key) {
  await loadState();
  let p;
  if (key === "novo") {
    p = PROFILE_DRAFT || { name: "", language: "es-419", max_chars_per_line: 42, max_lines: 2, max_cps: 17, min_duration: 0.833,
      max_duration: 7, min_gap_frames: 2, dialogue_dash: "- ", ellipsis: "…", rules: [], guide: "" };
    const meta = await api("GET", "/api/profiles/netflix-es-419");
    p = { ...p, key: null, builtin: false, modified: false, categories: meta.categories, checks: meta.checks };
    PROFILE_DRAFT = null;
  } else {
    p = await api("GET", `/api/profiles/${key}`);
  }
  let rules = (p.rules || []).map((r) => ({ ...r }));
  const cats = p.categories, checks = p.checks;
  const num = (id, label, v, step = "1", min = "0", hint = "") => `<label class="field"><span>${label}${hint ? ` <em class="muted small">${hint}</em>` : ""}</span><input type="number" id="${id}" value="${v ?? ""}" step="${step}" min="${min}"></label>`;
  const sel = (id, label, v, opts) => `<label class="field"><span>${label}</span><select id="${id}">${opts.map(([val, t]) => `<option value="${esc(val)}" ${val === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>`;

  main.innerHTML = `
    <div class="page-head">
      <div><p class="muted small"><a href="#/configuracoes">Configurações</a> · Perfis de regras</p>
        <h1 style="margin-top:6px">${p.key ? esc(p.name) : "Novo perfil"}</h1>
        ${p.builtin ? `<p class="muted small">Perfil que vem com o programa${p.modified ? " — <b>alterado por você</b>" : ""}. Pode editar à vontade; “Restaurar original” desfaz.</p>` : ""}</div>
      <div class="row">
        <button class="btn" data-p="preview">Ver o que vai para a IA</button>
        ${p.key ? `<button class="btn" data-p="dup">Duplicar</button>` : ""}
        ${p.builtin && p.modified ? `<button class="btn" data-p="restore">Restaurar original</button>` : ""}
        ${p.key && !p.builtin ? `<button class="btn danger" data-p="delete">Apagar</button>` : ""}
        <button class="btn primary" data-p="save">Salvar</button>
      </div>
    </div>

    <section class="panel">
      <h2>Regras de tradução e estilo</h2>
      <p class="muted small">Tudo o que pode e o que não pode neste perfil. As regras <b>ligadas</b> vão no pedido de tradução (API e ChatGPT). Quando a regra tem uma <b>verificação automática</b>, o Verificar também aponta onde ela não foi seguida.</p>
      <div class="row" style="margin:10px 0">
        <input type="search" id="r-filter" placeholder="Procurar nas regras" style="max-width:280px" aria-label="Procurar nas regras">
        <button class="btn" data-p="add">Adicionar regra</button>
        <span class="muted small" id="r-count"></span>
      </div>
      <div id="rules"></div>
      <button class="btn" data-p="add" style="margin-top:10px">Adicionar regra</button>
    </section>

    <section class="panel">
      <h2>Limites técnicos</h2>
      <div class="grid-3">
        <label class="field"><span>Nome</span><input type="text" id="pf-name" value="${esc(p.name)}"></label>
        <label class="field"><span>Idioma</span><select id="pf-lang">${langOptions(p.language)}</select></label>
        ${sel("pf-naming", "Nome do arquivo traduzido", p.naming || "", [["", "Nome.es-419.srt"], ["encripta", "Nome_sub_spa.srt / _sub_pt"]])}
        ${num("pf-cpl", "Caracteres por linha", p.max_chars_per_line, "1", "10")}
        ${num("pf-lines", "Linhas", p.max_lines, "1", "1")}
        ${num("pf-cps", "Velocidade máxima (CPS)", p.max_cps, "0.5", "1")}
        ${num("pf-opt", "CPS ideal", p.optimal_cps, "0.5", "0", "(vazio = igual ao máximo)")}
        ${num("pf-min", "Duração mínima (s)", Math.round(p.min_duration * 1000) / 1000, "0.001", "0.1")}
        ${num("pf-max", "Duração máxima (s)", p.max_duration, "0.001", "1")}
        ${num("pf-gap", "Intervalo mínimo (quadros)", p.min_gap_frames)}
        ${num("pf-gapms", "…ou em milissegundos", p.min_gap_ms, "1", "0", "(tem prioridade)")}
        ${num("pf-chain", "Fechar intervalos menores que (quadros)", p.chain_frames || 0, "1", "0", "(0 = não)")}
        ${sel("pf-dash", "Hífen de diálogo", p.dialogue_dash ?? "- ", [["- ", "Com espaço (- Texto)"], ["-", "Sem espaço (-Texto)"]])}
        ${sel("pf-ell", "Reticências", p.ellipsis ?? "…", [["…", "Caractere único (…)"], ["...", "Três pontos (...)"]])}
      </div>
    </section>

    <section class="panel">
      <h2>Observações livres</h2>
      <label class="field"><span class="muted small">Texto que também vai para a IA, depois das regras (por exemplo, um trecho do manual do cliente).</span>
        <textarea id="pf-guide" rows="5">${esc(p.guide || "")}</textarea></label>
    </section>`;

  const drawRules = () => {
    const q = (document.getElementById("r-filter")?.value || "").toLowerCase();
    const order = new Map(cats.map((c, i) => [c, i]));
    const idx = rules.map((r, i) => i).sort((a, b) => (order.get(rules[a].category) ?? 99) - (order.get(rules[b].category) ?? 99) || a - b);
    let last = null, html = "";
    for (const i of idx) {
      const r = rules[i];
      if (q && !(`${r.text} ${r.category}`.toLowerCase().includes(q))) continue;
      if (r.category !== last) { html += `<h3 class="rule-cat">${esc(r.category)}</h3>`; last = r.category; }
      html += `<div class="rule ${r.active ? "" : "off"}" data-i="${i}">
        <label class="rule-on" title="Ligada: vai para a IA"><input type="checkbox" data-k="active" ${r.active ? "checked" : ""}> <span class="small">${r.active ? "Ligada" : "Desligada"}</span></label>
        <textarea data-k="text" rows="${Math.min(6, Math.max(1, Math.ceil(r.text.length / 95)))}" aria-label="Regra">${esc(r.text)}</textarea>
        <div class="rule-meta">
          <select data-k="category" aria-label="Categoria">${cats.map((c) => `<option ${c === r.category ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
          <select data-k="check" aria-label="Verificação automática"><option value="">Sem verificação automática</option>${Object.entries(checks).map(([k, t]) => `<option value="${k}" ${k === r.check ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
          <button class="btn link small" data-p="del" data-i="${i}">Remover</button>
        </div></div>`;
    }
    document.getElementById("rules").innerHTML = html || `<p class="muted">${q ? "Nenhuma regra com esse texto." : "Nenhuma regra ainda. Adicione as regras do cliente."}</p>`;
    const on = rules.filter((r) => r.active).length;
    document.getElementById("r-count").textContent = `${rules.length} regras · ${on} ligadas`;
  };
  drawRules();
  document.getElementById("r-filter").addEventListener("input", drawRules);
  const box = document.getElementById("rules");
  box.addEventListener("input", (e) => {
    const row = e.target.closest(".rule"); if (!row) return;
    const r = rules[Number(row.dataset.i)], k = e.target.dataset.k;
    if (k === "text") r.text = e.target.value;
  });
  box.addEventListener("change", (e) => {
    const row = e.target.closest(".rule"); if (!row) return;
    const r = rules[Number(row.dataset.i)], k = e.target.dataset.k;
    if (k === "active") { r.active = e.target.checked; row.classList.toggle("off", !r.active); row.querySelector(".rule-on span").textContent = r.active ? "Ligada" : "Desligada"; drawRulesCount(); }
    if (k === "category") { r.category = e.target.value; drawRules(); }
    if (k === "check") r.check = e.target.value;
  });
  const drawRulesCount = () => { document.getElementById("r-count").textContent = `${rules.length} regras · ${rules.filter((r) => r.active).length} ligadas`; };

  const collect = () => {
    const f = (id) => document.getElementById(id).value;
    const n = (id) => { const v = f(id); return v === "" ? null : Number(v); };
    const base = { ...p };
    ["key", "builtin", "modified", "categories", "checks"].forEach((k) => delete base[k]);
    return { ...base, name: f("pf-name"), language: f("pf-lang"), naming: f("pf-naming"),
      max_chars_per_line: n("pf-cpl"), max_lines: n("pf-lines"), max_cps: n("pf-cps"), optimal_cps: n("pf-opt") || null,
      min_duration: n("pf-min"), max_duration: n("pf-max"), min_gap_frames: n("pf-gap") ?? 2, min_gap_ms: n("pf-gapms") || null,
      chain_frames: n("pf-chain") || 0, dialogue_dash: f("pf-dash"), ellipsis: f("pf-ell"), guide: f("pf-guide"),
      rules: rules.filter((r) => r.text.trim()) };
  };

  main.onclick = async (e) => {
    const b = e.target.closest("[data-p]");
    if (!b) return;
    const a = b.dataset.p;
    try {
      if (a === "add") {
        const cat = rules.length ? rules[rules.length - 1].category : "Outros";
        rules.push({ id: "", category: cat === "Outros" ? "Outros" : cat, text: "", active: true, check: "" });
        document.getElementById("r-filter").value = "";
        drawRules();
        const ta = box.querySelector(`.rule[data-i="${rules.length - 1}"] textarea`);
        ta?.focus(); ta?.scrollIntoView({ block: "center" });
      }
      if (a === "del") { rules.splice(Number(b.dataset.i), 1); drawRules(); }
      if (a === "save") {
        const data = collect();
        const r = p.key ? await api("PUT", `/api/profiles/${p.key}`, data) : await api("POST", "/api/profiles", data);
        S.state.profiles = r.profiles;
        toast("Perfil salvo. As próximas traduções e verificações já usam estas regras.");
        if (!p.key) location.hash = `#/perfil/${r.key}`; else router();
      }
      if (a === "dup") {
        PROFILE_DRAFT = { ...collect(), name: `${p.name} (cópia)` };
        location.hash = "#/perfil/novo";
      }
      if (a === "restore") {
        if (!confirm("Voltar este perfil ao original do programa? Suas alterações nele serão perdidas.")) return;
        await api("DELETE", `/api/profiles/${p.key}`); toast("Perfil restaurado."); router();
      }
      if (a === "delete") {
        if (!confirm(`Apagar o perfil “${p.name}”?`)) return;
        await api("DELETE", `/api/profiles/${p.key}`); toast("Perfil apagado."); location.hash = "#/configuracoes";
      }
      if (a === "preview") {
        if (!p.key) { toast("Salve o perfil primeiro para ver o texto.", true); return; }
        const r = await api("GET", `/api/profiles/${p.key}/prompt`);
        const m = modal("O que vai para a IA", `<p class="muted small">Instruções enviadas com este perfil (versão salva), traduzindo de ${esc(shortLang(r.source))} para ${esc(shortLang(r.target))}. O glossário e as instruções do cliente entram junto quando houver.</p>
          <textarea class="prompt-view" readonly>${esc(r.text)}</textarea>`,
          `<button class="btn" data-x="copy">Copiar</button><button class="btn primary" data-x="close">Fechar</button>`, { wide: true });
        m.ov.addEventListener("click", async (ev) => {
          const x = ev.target.closest("[data-x]")?.dataset.x;
          if (x === "close") m.close();
          if (x === "copy") toast((await copyText(r.text)) ? "Texto copiado." : "Não consegui copiar.");
        });
      }
    } catch (err) { toast(err.message, true); }
  };
}
