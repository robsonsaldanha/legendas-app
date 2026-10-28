# Materiais comerciais do CNT Legendas (versão 2.24)

Arquivos prontos para enviar a clientes:

| Arquivo | Para quê |
|---|---|
| `CNT-Legendas-Apresentacao-Comercial.pdf` | PDF comercial (12 páginas, paisagem): benefícios, planos, "em constante atualização" |
| `CNT-Legendas-Ficha-Tecnica.pdf` | PDF técnico (17 páginas): tour pelas telas reais, funções, padrões, licença |
| `CNT-Legendas-Guia-do-Usuario.pdf` | Tutorial passo a passo (22 páginas): instalar, ativar, usar |
| `CNT-Legendas-Apresentacao.pptx` | Apresentação para PowerPoint (13 slides, com notas do apresentador) |

## Como refazer quando o programa mudar
- `img/`: capturas das telas reais (dados de exemplo fictícios; sem marcas de terceiros).
- `_fonte/*.py`: geram `_fonte/*.html` (PDFs) e o `.pptx`. Os PDFs saem de `node _fonte/topdf.js <html> <pdf>` (Chromium/Playwright).
- Ao mudar versão, preço ou plano, confira o texto em `_fonte/comercial.py`, `tecnico.py`, `tutorial.py` e `gerar_pptx.py` (valores vêm de `brain/Licenciamento.md`).
