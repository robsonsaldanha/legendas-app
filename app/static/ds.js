/* CNT Legendas — peças da interface simplificada (2.9): dicas "?" e meses.
   Ver brain/Design.md. */
"use strict";

/* Textos das dicas: o que é, quando usar e o que acontece com os arquivos. */
const HELP = {
  inicio: ["Seus trabalhos, mês a mês",
    "Cada mês é uma pasta dentro da sua pasta de trabalhos (ex.: OUTUBRO 2026). Um trabalho novo entra no mês em que você o recebe. Use as setas para ver outros meses. Os trabalhos que já estavam nas pastas de mês aparecem aqui sozinhos."],
  novo: ["Novo trabalho",
    "Você responde três perguntas: o que vai fazer, para quem e quais arquivos. O programa cria a pasta do episódio no mês atual, copia os arquivos para lá (os seus originais ficam onde estão) e já abre o próximo passo."],
  avulsa: ["Abrir uma legenda solta",
    "Para mexer numa legenda que não faz parte de um projeto: abre direto no editor. Nada é criado na pasta de trabalhos."],
  passos: ["Os 4 passos de cada episódio",
    "Arquivos: o vídeo e a legenda do cliente. Traduzir: no editor, pelo seu ChatGPT ou pela API. Revisar: conferir no editor as legendas marcadas. Entregar: gera o arquivo final com o nome que o cliente pede. O botão de cada episódio mostra o próximo passo."],
  "passo-arquivos": ["Arquivos",
    "Coloque o vídeo e a legenda que o cliente mandou. Eles são copiados para a pasta do episódio; os seus arquivos originais não são mexidos."],
  "passo-traduzir": ["Traduzir",
    "Abre o editor com a legenda do cliente. Você traduz pelo seu ChatGPT (sem custo) ou pela API. A tradução vira um arquivo novo: a legenda do cliente nunca é alterada."],
  "passo-revisar": ["Revisar",
    "No editor, as legendas com problema aparecem marcadas (CPS em vermelho, ⚑). F8 vai para a próxima. Se precisar, acerte o tempo pela fala em Sincronizar."],
  "passo-entregar": ["Entregar",
    "No editor, o botão Entregar confere as regras do cliente e gera o arquivo final, com o nome certo, na subpasta Entrega. O episódio fica como entregue."],
  "o-que": ["O que você vai fazer?",
    "Traduzir: o cliente mandou a legenda pronta. Legendar um vídeo: só tem o vídeo, e o programa escreve a legenda a partir da fala (no seu computador, sem custo). Acertar o tempo: a legenda existe, mas está fora do tempo do vídeo."],
  quem: ["Para quem e qual episódio",
    "O cliente decide as regras (caracteres por linha, velocidade de leitura, manual). Escolha um projeto que já existe para continuar a série, ou crie um novo. Se a série é de um mês anterior, ela ganha uma pasta no mês atual."],
  idiomas: ["Idiomas",
    "Vêm do projeto ou do cliente. Se o idioma de origem ficar em “Detectar automaticamente”, o programa descobre pela legenda ou pela fala do vídeo."],
  arquivos: ["Arquivos",
    "São copiados para a pasta do episódio. Os seus originais continuam onde estão. Dá para pôr depois também."],
  "cfg-licenca": ["Licença",
    "Todo computador tem 1 dia de avaliação com tudo liberado. Depois, criar projetos e traduzir à mão continuam grátis; o resto precisa de licença. O código de ativação chega por e-mail depois da compra e ativa um computador, uma vez. O programa confere a licença ao abrir e funciona até 30 dias sem internet."],
  "cfg-versao": ["Versão do programa",
    "Ao abrir, o programa procura versão nova e atualiza sozinho. Com ele aberto, confere a cada 30 minutos e pergunta se quer atualizar agora: antes, oferece salvar a legenda aberta, e depois reabre onde você estava."],
  "cfg-bandeja": ["Bandeja do sistema",
    "Ligado: o ícone do CNT Legendas fica ao lado do relógio enquanto o programa está aberto, e o X só esconde a janela (os trabalhos continuam). Para fechar de vez, clique com o botão direito no ícone e escolha Sair. Desligado: o X pergunta e fecha o programa."],
  "cfg-perfil": ["Perfil na nuvem",
    "Com a licença ativada, as suas configurações, clientes (com glossários e instruções) e perfis de regras ficam guardados no servidor, ligados à sua conta. Num computador novo ou formatado, ao ativar a licença, o programa oferece trazer tudo de volta. As chaves de IA e as pastas deste computador não vão. Também dá para exportar e importar um arquivo."],
  "cfg-nome": ["Seu nome na legenda",
    "Algumas entregas pedem o nome de quem traduziu no fim da legenda (“Traducción: …”). É este nome que o programa usa."],
  "cfg-pasta": ["Pasta dos trabalhos",
    "Dentro dela o programa cria uma pasta por mês (OUTUBRO 2026) e, dentro do mês, uma por projeto. Ao escolher a pasta, os trabalhos que já estão nas pastas de mês entram na lista. Nada é movido nem apagado."],
  "cfg-clientes": ["Clientes",
    "Cada cliente tem o seu perfil de regras e os idiomas de costume. Escolher o cliente no trabalho já aplica tudo isso."],
  "cfg-perfis": ["Perfis de regras",
    "O “manual” de cada cliente: caracteres por linha, linhas, velocidade de leitura (CPS) e o que pode e o que não pode. O editor confere a legenda por ele. Perfis de clientes com manual próprio são importados de um arquivo .cnt.json."],
  "cfg-ia": ["Tradução automática",
    "Você pode traduzir colando as partes no seu ChatGPT (sem custo) ou deixar a tradução automática pela API de um serviço (pago por uso). Aqui ficam o serviço escolhido e as chaves."],
  "cfg-fila": ["Trabalhos em segundo plano",
    "Transcrições, sincronizações e traduções longas rodam sozinhas enquanto você faz outra coisa. Aqui aparecem as que estão rodando e as já feitas."],
  "cfg-editor": ["Preferências do editor",
    "Cores dos problemas na lista, tamanho da legenda sobre o vídeo, forma de onda, fontes e tamanhos das áreas. Também pelo botão ⚙ dentro do editor."],
  "cfg-tema": ["Aparência", "Escuro, claro ou o mesmo do Windows."],
  editor: ["Os botões do editor",
    "Traduzir: a legenda inteira, pelo seu ChatGPT ou pela API (▾ escolhe idiomas e jeito). Revisar: a IA corrige no mesmo idioma e gera um arquivo novo. Sincronizar: acerta os tempos pela fala do vídeo. Verificar: lista o que está fora das regras (F8 vai ao próximo). Entregar: gera o arquivo final com o nome do cliente. A legenda que você abriu nunca é alterada: salvar cria a cópia “(editada)”."],
  "cfg-avancado": ["Avançado",
    "Modelos de IA, preços, placa de vídeo, transcrição e arquivos temporários. Já vem tudo configurado; só mexa se precisar."],
};

function helpBtn(id, label) {
  const h = HELP[id];
  if (!h) return "";
  return `<button type="button" class="ds-help" data-help="${esc(id)}" aria-expanded="false" aria-label="${esc(label || `O que é: ${h[0]}`)}">?</button>`;
}

/* Uma dica aberta por vez, logo abaixo do "?". Esc ou × fecham. */
let TIP_OPEN = null;
function closeTip() {
  if (!TIP_OPEN) return;
  TIP_OPEN.el.remove();
  TIP_OPEN.btn.setAttribute("aria-expanded", "false");
  TIP_OPEN = null;
}
function openTip(btn) {
  const id = btn.dataset.help;
  const same = TIP_OPEN && TIP_OPEN.btn === btn;
  closeTip();
  if (same) return;
  const [title, text] = HELP[id] || ["", ""];
  const el = document.createElement("div");
  el.className = "ds-tip float";
  el.id = "ds-tip";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", title);
  el.innerHTML = `<div class="ds-tip-badge" aria-hidden="true">?</div><div class="ds-tip-body"><strong>${esc(title)}</strong><span>${esc(text)}</span></div>
    <button type="button" class="ds-tip-x" aria-label="Fechar dica">×</button>`;
  document.body.appendChild(el);
  const r = btn.getBoundingClientRect();
  const w = el.offsetWidth;
  el.style.left = `${Math.max(16, Math.min(window.scrollX + r.left - 20, window.scrollX + document.documentElement.clientWidth - w - 16))}px`;
  el.style.top = `${window.scrollY + r.bottom + 10}px`;
  btn.setAttribute("aria-expanded", "true");
  btn.setAttribute("aria-controls", "ds-tip");
  TIP_OPEN = { btn, el };
  el.querySelector(".ds-tip-x").focus({ preventScroll: true });
}
document.addEventListener("click", (e) => {
  const b = e.target.closest(".ds-help");
  if (b) { e.preventDefault(); e.stopPropagation(); openTip(b); return; }
  if (e.target.closest(".ds-tip-x")) { const btn = TIP_OPEN?.btn; closeTip(); btn?.focus(); return; }
  if (TIP_OPEN && !e.target.closest("#ds-tip")) closeTip();
}, true);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && TIP_OPEN) { const btn = TIP_OPEN.btn; closeTip(); btn.focus(); e.stopPropagation(); }
}, true);
window.addEventListener("hashchange", closeTip);

/* ------------------------------------------------------------ meses */

const MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function monthLabel(mes) {
  const [y, m] = mes.split("-").map(Number);
  return `${MESES[m - 1]} ${y}`;
}
function monthFolder(mes) { return monthLabel(mes).toUpperCase(); }
function shiftMonth(mes, delta) {
  const [y, m] = mes.split("-").map(Number);
  const k = y * 12 + (m - 1) + delta;
  return `${Math.floor(k / 12)}-${String((k % 12) + 1).padStart(2, "0")}`;
}
