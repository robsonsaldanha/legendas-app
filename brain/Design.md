# Design system — CNT Legendas (2.9)

Telas aprovadas pelo Róbson em 2026-10-22 (proposta "CNT Legendas — proposta de telas mais simples": Início por mês, Projeto passo a passo, Novo trabalho em 3 perguntas, Configurações em linhas, dicas "?"). Pedido da usuária: "não ficou fácil de mexer, ficou algo muito poluído"; o editor está bom (só espaçamento); quer "?" com dicas.

## Auditoria antes da 2.9 (app.css + telas)

| Ponto | Encontrado | Decisão |
|---|---|---|
| Tamanhos de fonte | 15 valores (9,5 a 44 px; 12,5, 13,5, 14,5…) | Escala fixa: 13 / 14 / 15 / 17 / 20 / 28 / 44 |
| Espaçamentos | ~20 combinações de padding soltas | Escala de 4 px: 4, 8, 12, 16, 20, 24, 32, 40, 56 |
| Raios | 8 valores | 3 tokens: 10 (controles), 14 (cartões), 999 (pílulas) |
| Hex fora do `:root` | 25 | Usar só tokens nas telas novas |
| Fonte "de máquina" (JetBrains Mono) | rótulos em maiúsculas (`.label`, `.eyebrow`) e números em quase toda tela | Mono só para caminho de arquivo, tempo (00:00:00,000) e CPS. Rótulos em Inter normal |
| Estilo inline nos JS | 136 `style=` | Telas novas usam classes (`.ds-*`) |
| Densidade | cartões de números + tabela de 10 colunas no Início | Uma linha por projeto, só o que leva à próxima ação |

## Tokens

Cores: as do `:root` (grafite + lima) continuam. Novos: `--tip-bg` (dica), `--tip-line`, `--ink-2` (texto secundário com contraste ≥ 4,5:1 sobre `--panel`).

Tipografia: Inter para tudo; Anton só no título da página (`.ds-title`, 44 px). Corpo 15 px / 1,5.

Espaço: `--s1`…`--s9` = 4, 8, 12, 16, 20, 24, 32, 40, 56 px. Página: margem 48/56 px; entre blocos 32 px; dentro de cartão 20–24 px.

Alvos de clique ≥ 40 px (botões 44 px; "?" 24 px com área de 32 px).

## Componentes novos (prefixo `ds-`)

- **`.ds-page`**: coluna da página (máx. 1180 px), blocos com 32 px entre si.
- **`.ds-head`**: título (Anton) + subtítulo + ações à direita; quebra em telas estreitas.
- **`.ds-help`** — botão "?": `<button class="ds-help" aria-expanded aria-controls>`. Abre a **`.ds-tip`** (fundo `--tip-bg`, borda lima, título em negrito + texto + ×). Teclado: Enter/Espaço abre e fecha; Esc fecha. Uma dica aberta por vez. A função `helpBtn(id)` usa o texto de `HELP[id]`; a escrita das dicas: o que é, quando usar e o que acontece com os arquivos.
- **`.ds-row`**: linha de projeto (nome + meta | progresso | próximo passo | botão). Quebra em 2 linhas abaixo de 900 px.
- **`.ds-track`**: trilha de 4 passos (Arquivos → Traduzir → Revisar → Entregar). Feito = lima; atual = lima 45% + rótulo lima; a fazer = cinza. É uma `<ol>`, com o passo atual marcado com `aria-current="step"`.
- **`.ds-choice`**: cartão de escolha (botão com `aria-pressed`), borda lima quando escolhido.
- **`.ds-set`**: lista de configurações (título + valor atual + "?" + botão de ação), uma linha por item; o técnico fica em "Avançado" recolhido.
- **`.ds-chip`**: pílula de resumo ("3 em andamento").

## Navegação

Menu com 4 itens: Início, Editor, Relatórios, Configurações. Clientes, Perfis de regras e "Em segundo plano" continuam existindo e são abertos por Configurações e pelo Novo trabalho (nenhuma função saiu).
