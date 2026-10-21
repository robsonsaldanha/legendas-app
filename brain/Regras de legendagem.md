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

## Perfis de clientes com manual próprio
- Manuais de clientes podem ser confidenciais: **não ficam no código** (o repositório é público desde a 2.4.0). Cada cliente vira um arquivo `.cnt.json` guardado no computador dela, importado em Perfis de regras → "Importar perfis…" (e "Exportar" dentro do perfil faz a cópia).
- Ao importar, a chave do perfil é mantida (`cliente-es-419`, `cliente-pt-br`), então o cliente ligado a ela volta a funcionar e o perfil acompanha o idioma da legenda (mesma família: `<nome>-es-419` ↔ `<nome>-pt-br`).
- Recursos que esses perfis usam: CPS ideal além do máximo, intervalo em ms, hífen sem espaço, `...` em vez de `…`, nome `_sub_spa`/`_sub_pt`, e regras com verificação automática (interjeição, pontuação dupla, reticências, hífen, repetição, ¿/¡, texto de tela, dois-pontos, números). Os avisos são sugestões: a revisão decide.

## Regras de estilo por perfil (versão 1.1)
- Cada perfil tem a sua lista de regras (Configurações → Perfis de regras → clicar no perfil). As **ligadas** vão para a IA; as que têm **verificação automática** também aparecem no Verificar.
- Clientes com manual próprio: regras no arquivo importado (ver acima).
- Netflix (ES e PT): interjeições permitidas quando têm sentido, palavrões no mesmo nível, repetição de hesitação pode ser reduzida, itálico para fora de cena/narração/aparelhos/música, ¿¡ obrigatórios no espanhol, números de 1 a 10 por extenso. Conferir com o guia atual da Netflix.
- Para um cliente novo: Novo perfil (ou Duplicar um parecido), escrever as regras, e escolher o perfil no Cliente.
