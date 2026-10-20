# Regras de legendagem

## Perfis embutidos (`core/profiles.py`)

| Chave | Idioma | CPL | Linhas | CPS | Duração | Intervalo |
|---|---|---|---|---|---|---|
| `netflix-es-419` | Espanhol (LatAm) | 42 | 2 | 17 | 5/6 s – 7 s | 2 quadros |
| `netflix-es-419-kids` | Espanhol infantil | 42 | 2 | 13 | idem | idem |
| `netflix-pt-br` | Português (Brasil) | 42 | 2 | 17 | idem | idem |
| `netflix-pt-br-kids` | Português infantil | 42 | 2 | 13 | idem | idem |

Fontes: Netflix Timed Text Style Guide de cada idioma (42 CPL; 17 CPS adulto, 13 infantil) e diretrizes gerais de timing da Netflix (mínimo 5/6 s, máximo 7 s, 2 quadros entre legendas). CPS conta espaços.

Outras regras do guia de espanhol a considerar nas Fases 2/6: diálogo com hífen + espaço (uma fala por linha); reticências como caractere único `…`; ¿ ¡ de abertura; números de 1 a 10 por extenso; itálico para títulos de obras, palavras estrangeiras, vozes de aparelhos e narração fora de cena.

## Como o Formatar decide (resumo)

**Onde cortar entre legendas** — custo de cada legenda possível:
- custo fixo por legenda (evita picotar);
- não cabe em 2×42 → custo enorme;
- CPS acima do limite → custo proporcional;
- fala mais longa que 7 s → custo alto;
- terminar no meio da oração → custo; em vírgula → custo menor; em fim de frase → zero;
- terminar em palavra fraca ("de", "o", "que"...) → custo alto;
- cortar logo antes de "e/mas/porque" → bônus; antes de "de/da/do" → custo;
- fechar uma frase e cortar a seguinte no meio → custo;
- terminar numa pausa da fala → bônus; pausa longa (≥1,5 s) dentro da legenda → custo.

**Tempos**: início = primeira palavra. Fim = última palavra + até 0,5 s, estendido para cumprir duração mínima e CPS **se houver espaço** antes da próxima; nunca invade o intervalo de 2 quadros. Intervalos menores que 0,5 s são encadeados (fecham em 2 quadros).

**Linhas**: uma linha se couber. Senão, a melhor divisão em 2: preferir após pontuação; nunca deixar palavra fraca no fim da linha de cima; preferir linha de baixo maior (pirâmide) sem forçar; evitar uma linha com menos de 40% da outra.

## Relatório de QC
`<vídeo>.<idioma>.qc.txt`: lista as legendas com erro (linhas/caracteres, sobreposição, ordem) e avisos (CPS, duração, intervalo, tempo estimado). Começar a revisão por ele.

## Limitações conhecidas (Fase 1)
- Sem identificação de falantes: duas pessoas falando em sequência rápida podem cair na mesma legenda sem hífen de diálogo. Avaliar `gpt-4o-transcribe-diarize` ou heurística na Fase 6.
- Sem detecção de cortes de cena (shot changes).

## Perfis da Encripta (cliente)
Fonte: *Manual de traducción y subtítulos en español 3.0* da Encripta (PDF enviado pela usuária em 20/10/2026).

| | Encripta |
|---|---|
| Caracteres por linha / linhas | 42 / 2 |
| CPS | máximo 28, ideal 15 (o Formatar mira em 15; o QC só avisa acima de 28) |
| Duração | 1,001 s a 6,999 s |
| Intervalo mínimo | 84 ms (não em quadros) |
| Quadros por segundo padrão | 23,976 |
| Diálogo | hífen **sem** espaço: `-Texto`, só quando os dois personagens estão na tela; texto de tela + fala: só a fala leva hífen |
| Reticências | três pontos `...` (o Subtitle Edit trata `…` como símbolo a corrigir) |
| Nome do arquivo | `Nome_da_Obra_sub_spa.srt` / `Nome_da_Obra_sub_pt.srt` |

- `encripta-es-419` — **Encripta — Español (neutro)**: fiel ao manual. O manual inteiro (interjeições, reticências, localização, canções, números, itálico, `{\an8}`...) vai resumido em `profile.guide` e entra no pedido de tradução (API e ChatGPT) como "MANUAL DO CLIENTE".
- `encripta-pt-br` — **Encripta — Português (Brasil)**: mesmos critérios técnicos; regras de estilo adaptadas do manual em espanhol (a Encripta não mandou manual em português — confirmar com ela).
- QC de estilo (`core/style.py`, só perfis com `style_checks`): interjeição proibida, pontuação dupla, `…` em vez de `...`, hífen com espaço, palavra repetida, pergunta/exclamação sem `¿`/`¡` (espanhol), texto de tela em maiúsculas com ponto final, maiúscula depois de dois-pontos, número de 0 a 10 em algarismo. São **avisos**: a revisão decide.
- Normalização automática ao formatar/traduzir: reticências e hífen de diálogo no formato do perfil.
- Fora do alcance da máquina (fica no manual para o modelo e na revisão): itálico por contexto, legendas de localização, nacionalização de títulos, assinatura "Traducción: Nombre" depois da última cena.
