# Decisões

## 2026-10-19 — Modelo de transcrição: `gpt-transcribe`
- A OpenAI lançou `gpt-transcribe` em jul/2026, recomendado no lugar de whisper-1 e gpt-4o-transcribe. US$ 0,0045/min.
- Aceita `keywords` (termos esperados — usamos o glossário) e `languages`. No SDK Python vão em `extra_body`.
- **Não devolve timestamps** (só whisper-1, que será descontinuado em 26/02/2027). Por isso os tempos vêm do alinhamento local.
- Formatos aceitos: mp3, mp4, mpeg, mpga, m4a, wav, webm (FLAC não). Enviamos WAV de blocos curtos.
- Modelo e preço são configuráveis em `Settings`.

## 2026-10-19 — Blocos curtos (~30 s) em vez de arquivos grandes
- Fica muito abaixo do limite de 25 MB, permite paralelismo, e dá um intervalo de tempo conhecido para cada trecho de texto — o alinhamento só precisa resolver dentro do bloco.
- Cortes sempre em pausas (`silencedetect`); fala contínua longa é cortada no ponto de menor energia.
- Trechos sem fala não são enviados.
- Contrapartida: cada bloco é transcrito sem ver o anterior. O `prompt` leva o contexto do projeto e `keywords` o glossário. Se a qualidade sofrer nas emendas, avaliar blocos maiores ou passar o fim do bloco anterior no prompt (perde paralelismo).

## 2026-10-19 — Alinhamento próprio em vez do pacote WhisperX
- O WhisperX instala faster-whisper, ctranslate2, pyannote etc., que não usamos (a transcrição é da OpenAI). Isso aumentaria muito o instalador.
- Usamos **os mesmos modelos wav2vec2** que o WhisperX usa para alinhar (`jonatasgrosman/wav2vec2-large-xlsr-53-portuguese` / `-spanish`, `facebook/wav2vec2-base-960h`) via `transformers`, e o mesmo algoritmo (Viterbi CTC), implementado em numpy em `align.py`.
- Dependências do alinhamento: só `torch` (CPU) + `transformers`.
- Sem modelo disponível, o app **não para**: estima os tempos pelos trechos com fala e marca no QC.

## 2026-10-19 — Formatar por programação dinâmica
- Algoritmo guloso ("enche a legenda até não caber") gera cortes ruins. A DP escolhe a sequência de cortes de menor custo total. Pesos no topo de `formatter.py` e `linebreak.py`, para ajustar com o uso real.

## 2026-10-19 — SRT em UTF-8 com BOM e CRLF
- Editores do Windows (Subtitle Edit, Aegisub, Bloco de Notas) reconhecem melhor. Leitura aceita UTF-8, UTF-16 e cp1252.

## 2026-10-19 — Chave da OpenAI no Gerenciador de Credenciais
- `keyring` no Windows usa o Credential Manager. Para desenvolvimento, a variável `OPENAI_API_KEY` tem prioridade.

## 2026-10-19 — Interface no navegador (servidor local)
- Pedido da usuária: "página no navegador". Substitui a PySide6 da especificação.
- Servidor com a biblioteca padrão do Python (`http.server`), sem FastAPI/Flask: menos dependências para empacotar.
- Segurança: escuta só em 127.0.0.1; token aleatório por sessão exigido em toda a API (outras páginas abertas no navegador não conseguem chamar); `Host` precisa ser localhost (contra DNS rebinding); CSP só permite scripts do próprio servidor.
- O navegador não revela caminhos de arquivos, então "Escolher" abre a janela nativa do Windows (tkinter) num subprocesso; arrastar e soltar envia uma cópia.
- Progresso por consulta periódica (1 s), simples e robusto.
- Página sem CDN nem fontes externas: Segoe UI do Windows, funciona offline.

## 2026-10-19 — Aviso de tempo estimado agregado
- Quando mais da metade das legendas tem tempo estimado, o QC não marca cada uma (poluía a revisão); vira um aviso geral no relatório e na tela.

## 2026-10-19 — Dois perfis do Windows
- O PC é o mesmo, com perfis diferentes (Róbson e esposa). Dados separados por perfil; modelos compartilhados em ProgramData.
- Antes, o segundo perfil a abrir o programa poderia cair no servidor do primeiro (mesma porta) e ver os dados dele. Agora: porta por perfil, sessão em arquivo do próprio perfil, cookie + token.

## 2026-10-19 — Editor no layout do Subtitle Edit
- Pedido explícito: mesmo layout do Subtitle Edit e vídeo rodando junto, no quadro exato.
- Player HTML5 com `requestVideoFrameCallback`; formatos que o navegador não toca ganham uma cópia de pré-visualização (H.264 720p) que preserva os tempos dos quadros. A legenda continua sincronizada com o original.
- Forma de onda própria (canvas + picos do servidor) em vez de biblioteca externa: sem dependências, funciona offline.

## 2026-10-20 — Tradução
- Pedido: o trabalho principal dela é legendar traduzindo (recebe SRT em PT e entrega em ES, ou o contrário). Precisa de um botão que traduza tudo.
- Modelo padrão `gpt-5.5` (US$ 5 / 30 por milhão de tokens), raciocínio "low", Chat Completions com JSON Schema estrito. Se a chave não tiver acesso, tenta `gpt-5` e `gpt-4.1` (configurável em Configurações → Avançado). Custo típico: centavos por episódio.
- 1:1 por legenda (nunca junta/divide): os tempos são preservados e o original pode ficar ao lado, na coluna "Original" do editor. Condensar para caber no CPS é tarefa do modelo; quebrar linhas é do Formatar.
- Contexto por lote: 15 anteriores já traduzidas (consistência de nomes e tratamento) + 6 seguintes (frases que continuam). Lotes em sequência, não em paralelo, por causa dessa consistência.
- Pelo editor, o que é traduzido é o que está na tela (inclusive alterações não salvas); a legenda dela não é alterada.

## 2026-10-20 — Tradução pelo ChatGPT (copiar e colar), sem automatizar o site
- Pedido: usar a assinatura do ChatGPT em vez da API, para não ter custo, sem violar os termos.
- Automatizar o site do ChatGPT (ou do Claude.ai) a partir do programa foi descartado: os termos da OpenAI proíbem extrair respostas de forma automática/programada, e a Anthropic proíbe usar a assinatura em apps de terceiros; risco de bloqueio da conta, além de quebrar com mudanças no site e verificações anti-robô.
- Solução: a usuária é quem envia as mensagens no ChatGPT. O programa prepara cada parte (instruções completas na 1ª, só os dados nas seguintes — a própria conversa guarda o contexto), copia para a área de transferência, abre/foca a aba do ChatGPT sem recarregar a conversa, lê a resposta colada (bloco ```json, JSON solto, linhas "id | texto", aspas tortas, vírgulas sobrando), confere ids, pede só os que faltaram e monta o .srt igual ao da API.
- Partes de 100 legendas: um episódio de 400 legendas = 4 idas e voltas.
- Transcrição continua pela API; sincronização roda localmente (sem chat nem API).

## 2026-10-20 — Instalador: Python embutido (não PyInstaller)
- Pedido: o instalador traz tudo; a usuária não instala Python nem nada.
- Escolha: Python 3.12 embeddable oficial + bibliotecas instaladas em `python\Lib\site-packages`. Com torch é mais previsível que PyInstaller (sem "hooks", sem detecção de importações), e o código continua igual ao de desenvolvimento.
- O embeddable não traz tkinter: o `_tkinter.pyd`, as DLLs que faltam (tcl86t, tk86t, zlib1) e as pastas `tkinter` e `tcl` são copiados do Python 3.12.10 da máquina de montagem (mesma versão).
- `python312._pth`: `python312.zip`, `.`, `Lib\site-packages`, `..` (pasta do programa) e `import site`. Isso também isola do Python que porventura exista no PC.
- O atalho chama `python\pythonw.exe -m app` (sem janela preta). As janelas "Abrir/Salvar" sobem com `python.exe` sem console.
- Inno Setup, instalação por máquina (admin) para valer nos dois perfis; `ProgramData\Legendas\modelos` com permissão de escrita para Usuários; VC++ 2015–2022 instalado em silêncio se faltar (o torch precisa).
- ffmpeg: build "essentials" do gyan.dev (alternativa: BtbN).
- Tamanho: instalador ≈ 180 MB; instalado ≈ 820 MB; + ≈ 1,2 GB por idioma de alinhamento, baixados no primeiro uso.
- O GitHub Actions monta, instala em silêncio, roda `packaging/smoke_test.py` com o Python instalado (sem o Python nem o ffmpeg da máquina no PATH, alinhamento real incluído), e desinstala. Tag `v*` publica em Releases (a cota de artefatos do GitHub é pequena).

## 2026-10-20 — Perfis de cliente (Encripta) com manual próprio
- Pedido: perfis para a Encripta a partir do manual 3.0 (PDF).
- O `Profile` ganhou campos opcionais que os perfis antigos não usam (continuam iguais): `optimal_cps`, `min_gap_ms`, `ellipsis`, `guide`, `naming`, `style_checks`. Perfis salvos antes carregam com os valores padrão.
- O manual vai como texto no pedido de tradução (seção "MANUAL DO CLIENTE", com prioridade sobre as regras gerais). Assim o mesmo mecanismo serve para qualquer cliente: basta duplicar um perfil e colar o manual no campo "Manual do cliente".
- Reticências deixaram de ser convertidas na tradução: cada perfil decide (Netflix `…`, Encripta `...`) no Formatar.
- Perfil em português da Encripta é uma adaptação nossa; confirmar com a Encripta.
- Ao trocar o idioma, o perfil automático fica na mesma família (Encripta ES ↔ Encripta PT).

## 2026-10-21 — Versão 1.0: "CNT Legendas", editor no centro, sincronização completa
- Pedido: programa mais fácil ("burocracia grande até chegar na tradução"), completo, com sincronização, e com o nome **CNT Legendas**. A usuária deixou as escolhas comigo ("você que manda").
- **Fluxo**: a tela inicial é só "abrir legenda e vídeo" + recentes + cliente. Tudo o mais é no editor: botão "Traduzir para X" de um clique (método, idiomas e cliente já lembrados; a seta ao lado abre as opções), menu Sincronizar, Verificar e Entregar. "Novo trabalho" virou "Trabalho em segundo plano" (para transcrever ou lotes), acessível pelo Início/Trabalhos.
- **Clientes** = a antiga tabela de projetos (sem migração de dados). Encripta e Netflix vêm cadastrados (uma vez, marcado em `meta`). O perfil segue o idioma da legenda dentro da família do cliente (`same_family`).
- **Sincronização** (`core/sync.py`, tudo local e sem custo, exceto texto sem tempo):
  - automática: sinal de fala por energia (100/s) × legendas; correlação por FFT com proporções comuns (25 ↔ 23,976 ↔ 24) e depois programação dinâmica por legenda com custo de mudança (≈1,5 s de fala) para trechos deslocados (comerciais, cenas cortadas) — a mesma ideia do ffsubsync/alass, sem dependências;
  - a "sobra" de 0,4 s no fim de cada legenda não conta no encaixe (senão o resultado escorrega para antes); fora do áudio conta como silêncio; empate fica com o menor deslocamento;
  - se piorar a concordância com a fala, não mexe;
  - legenda de referência usa o mesmo algoritmo, com o sinal vindo da outra legenda;
  - texto sem tempo: transcreve (API) e casa o texto dela com a transcrição palavra a palavra (`difflib`); o texto final é o dela, a transcrição só dá os tempos. Blocos separados por linha em branco viram legendas; texto corrido passa pelo Formatar;
  - cortes de cena: filtro `scene` do ffmpeg (vídeo reduzido a 256 px), guardados por vídeo; encaixe com as regras Netflix (12 quadros de janela, saída 2 quadros antes do corte).
- **Correção automática** (Verificar): só mexe no fim das legendas (sobreposição, intervalo mínimo, duração mínima, CPS quando há espaço, duração máxima) + reticências/hífen do perfil; nunca muda a quebra de linhas dela. Intervalos curtos são fechados só quando ela marca (padrão ligado no Netflix: `chain_frames = 12`).
- **Entregar**: nome no padrão do cliente, assinatura "Traducción/Tradução: Nome" depois da última legenda (nome guardado em Configurações), verificação final; pede confirmação antes de substituir um arquivo que não é o aberto e guarda cópia.
- **Renomear sem perder nada**: dados `%APPDATA%\Legendas` → `%APPDATA%\CNT Legendas` (movidos na primeira abertura), chave no Gerenciador de Credenciais lida do nome antigo e regravada no novo, modelos em `ProgramData` renomeados pelo instalador. O instalador mantém o mesmo AppId (atualiza por cima), instala na pasta nova (`UsePreviousAppDir=no`) e apaga programa e atalhos antigos. O CI instala a 0.5.0 e atualiza para conferir.
- Corretor ortográfico: o do próprio navegador (Edge/Chrome), já ativo no campo de texto com o idioma da legenda.

## 2026-10-21 — ChatGPT bloqueou uma parte ("não pode ser exibido por motivos de segurança")
- Aconteceu na primeira tradução real pela 1.0. O filtro do site do ChatGPT bloqueia respostas com cenas fortes (violência, drogas, suicídio…), mesmo em tradução. Não dá para garantir que não aconteça pelo site; a API é o caminho sem esse bloqueio de tela.
- Não tentamos "driblar" o filtro (palavras trocadas, códigos etc.). Em vez disso:
  1. o pedido passa a dizer com clareza o que é: diálogo de uma obra audiovisual, traduzido por uma profissional para o cliente; as falas são dos personagens, não um pedido de ajuda (seção "SOBRE O MATERIAL", também na API). Cada lote seguinte repete que são "falas da obra, para legendar";
  2. **Dividir a parte** em pedaços de 20: o trecho problemático fica isolado e o resto passa;
  3. **Copiar com as instruções** a parte atual, para colar numa conversa nova se a atual travar (leva as 6 legendas anteriores como contexto);
  4. **Traduzir só aquela parte pela API** (centavos), sem sair do fluxo do ChatGPT.
- O que já foi recebido nunca se perde.

## 2026-10-21 — Regras do perfil (o que pode e o que não pode) vão para a IA
- Pedido: cada perfil tem que levar para a IA exatamente as regras daquele cliente (ex.: Encripta proíbe interjeições, a Netflix aceita), e ela precisa poder criar regras novas.
- `Profile.rules`: lista de regras `{categoria, texto, ligada, verificação}` (`core/rules.py`). As ligadas entram no pedido de tradução (API e ChatGPT) na seção "REGRAS DO PERFIL", agrupadas por categoria, com prioridade sobre as regras gerais. O texto livre (`guide`) virou "Observações livres" e vai depois.
- Cada regra pode ligar uma verificação automática (interjeição, pontuação dupla, reticências, hífen, repetição, ¿/¡, texto de tela, dois-pontos, números). O Verificar só aponta o que alguma regra ligada pede — desligar a regra das interjeições desliga o aviso. Perfis salvos na 0.5 com `style_checks` continuam com todas.
- Perfis prontos agora são editáveis: a alteração fica gravada por cima (mesma chave) e "Restaurar original" apaga a alteração.
- Página do perfil (`#/perfil/<chave>`): regras por categoria (ligar/desligar, editar, categoria, verificação, remover, adicionar, procurar), limites técnicos e "Ver o que vai para a IA" (o texto exato das instruções).
- Regras Netflix escritas a partir do que sabemos dos Timed Text Style Guides (o site da Netflix não abriu daqui); conferir com o guia atual e ajustar no próprio perfil.

## 2026-10-21 — Versão 2.0: projetos em pastas, métricas e visual novo
- Pedido: logo/ícone da CNT, visual igual ao painel de referência (grafite + acento lima, menu de ferramentas à esquerda), tela inicial com Novo / Abrir / Mais recente e a lista de projetos, projetos organizados em pastas (filme / série com temporadas e episódios em qualquer ordem), status novo / em andamento / finalizado (reabrir), e relatórios completos (geral, por projeto e por episódio).
- **Logo**: `cnt-logo-(semfundo13)` (dourado com letras escuras) — é o que melhor aparece no tema escuro; o ícone do programa é o logo num quadrado grafite arredondado (`packaging/make_icon.py`, a partir de `packaging/assets/cnt-logo.png`).
- **Visual**: fontes locais (OFL) Anton (títulos), Inter (texto), JetBrains Mono (rótulos/números), em `app/static/fonts`. Tema escuro padrão, claro e automático (seletor no topo; `data-theme` no `<html>`, aplicado antes de desenhar por `theme.js`). Menu recolhível.
- **Projetos** (`core/projects.py`, `app/projects.py`): pasta raiz perguntada na primeira abertura (Configurações → trocar). Filme = `<raiz>/<nome>`; série = `<raiz>/<nome>/temporada-N/ep-M`. Nome da pasta validado pelas regras do Windows (caracteres proibidos bloqueados na digitação, nomes reservados, ponto/espaço no fim). Episódios por número, lista ou intervalo ("40-45"); a próxima sugestão é o maior + 1 da temporada. `projeto.cnt.json` em cada pasta permite reabrir (botão Abrir aceita a pasta do projeto, da temporada ou do episódio) e pastas `temporada-X/ep-Y` criadas à mão entram na lista.
- Arquivos adicionados ao projeto são **copiados** (os originais ficam onde estão), com progresso.
- Tabelas novas: `obras`, `itens`, `metricas` (instantâneos com data: abrir, salvar, traduzir, entregar), `tempo` (segundos por dia e episódio: o editor soma 1 minuto a cada minuto com atividade, no máximo 5 min por envio) e `eventos` (histórico). "Clientes" continua na tabela antiga `projects`.
- **Métricas** (`core/metrics.py`): legendas, linhas, palavras, letras, caracteres (com/sem espaço), frases, duração do vídeo, tempo com legenda na tela, legendas por minuto, médias (caracteres, palavras, duração, intervalo, palavras por frase), CPS médio/mediano/máximo e acima do perfil, 1/2/3+ linhas, diálogos, itálico, {\an8}, curtas/longas, apontamentos por tipo, tamanho da tradução vs original, e produtividade (legendas, palavras e minutos de vídeo por hora).
- Relatórios: geral (filtros de período, cliente e status; por mês, por cliente, por projeto, tempo por dia; exporta CSV), do projeto (abas Episódios/Métricas/Histórico) e do episódio (métricas, evolução, tempo por dia).
- "Abrir legenda avulsa" (fora de projeto) continua no menu Editor.

## 2026-10-21 — Tela Projetos própria; Claude e gateway personalizado
- O menu Projetos abria a mesma tela do Início. Agora: Início = boas-vindas + Novo/Abrir/Continuar + **projetos recentes** (8); Projetos = lista completa com filtros (status, filme/série, cliente), ordenação, busca, status editável na linha e episódios abertos ali mesmo (seta).
- **Tradução automática por outros serviços** (Configurações → Inteligência artificial): OpenAI (como antes), **Claude** (API da Anthropic, `output_config.format` com JSON Schema, sem dependência nova: `httpx`, que já vem com o `openai`) e **gateway personalizado** compatível com OpenAI (URL base + chave + modelo; tenta JSON Schema → json_object → texto). Chaves no Gerenciador de Credenciais (`anthropic_api_key`, `gateway_api_key`).
- Padrão do Claude: `claude-sonnet-5-5`, US$ 2 / 10 por milhão de tokens (platform.claude.com/docs/en/models/overview, conferido em 21/10/2026). Editável.
- A transcrição continua só pela OpenAI (`gpt-transcribe`).

## 2026-10-21 — Gateway no formato Anthropic (GhostCLI)
- Róbson quer usar o GhostCLI (ghostcli.cloud/docs): assinatura mensal com Claude Opus 5.5, Sonnet 5, Fable 5.1 e GPT-6 Astra por uma chave `gcli_…`; expõe `/v1/messages` (Anthropic), `/v1/chat/completions` e `/v1/responses` (OpenAI). Exige IP liberado no painel (senão 403) e o complemento de API no plano (senão 402). Não documenta `/v1/models` nem JSON Schema.
- O gateway agora tem **formato da API**: OpenAI ou Anthropic. No formato Anthropic usa o mesmo tradutor do Claude com a URL do gateway (`<base>/v1/messages`, sem duplicar `/v1`), envia a chave em `x-api-key` e `Authorization: Bearer`, e se o serviço recusar `output_config` pede o JSON no texto e lê com tolerância.
- Botão "GhostCLI" preenche: formato Anthropic, `https://ghostcli.cloud`, modelo `claude-sonnet-5`, preço 0 (assinatura). "Testar" faz um pedido mínimo de verdade (o `/models` não é garantido em gateways) e traduz 401/402/403/404 em mensagens claras.
- Alerta dado ao Róbson: os termos do GhostCLI não identificam a empresa nem dizem como acessam os modelos ou se guardam os textos; legendas de clientes (Encripta/Netflix) costumam ter confidencialidade.

## 2026-10-21 — Serviços de IA com listas de modelos (OpenAI, Claude, Gemini, GhostCLI, gateway)
- Pedido: GhostCLI já configurado no programa (host, chave, modelos), Gemini como opção, e modelos prontos para escolher, com a possibilidade de acrescentar outros (inclusive Claude futuros).
- `core/ai.py` concentra os serviços: endereço padrão, formato da API, nome da chave no Gerenciador de Credenciais, ajuda, e a lista de modelos prontos com preço (quando conhecido). Modelos acrescentados ficam em `Settings.ai_models`, o escolhido em `ai_selected`, endereços em `ai_urls`.
- GhostCLI: `https://ghostcli.cloud`, chave `gcli_…`; claude-sonnet-5, claude-opus-5-5, claude-fable-5.1 pelo formato Anthropic (`/v1/messages`) e gpt-6-astra pelo formato OpenAI (`/v1/chat/completions`). Modelo acrescentado sem formato: `claude-*` → Anthropic, o resto → OpenAI. Preço = assinatura.
- Gemini: endpoint compatível com OpenAI do Google (`https://generativelanguage.googleapis.com/v1beta/openai`), chave do AI Studio; modelos gemini-3.8-flash (recomendado para texto), gemini-3.5-flash-lite, gemini-4-argon, gemini-3.6-flash (ai.google.dev/gemini-api/docs/models, 21/10/2026). Preços não informados (conferir na página de preços do Google).
- Configurações → Inteligência artificial: "Traduzir com" (serviço ativo) + uma aba por serviço com chave, endereço (quando editável), lista de modelos (escolher/remover os seus) e "Adicionar outro modelo" (código, nome, formato, preços). O "Testar" faz um pedido mínimo real no formato do modelo escolhido.
- Configurações antigas do gateway (2.1/2.2) continuam valendo.

## 2026-10-21 — Correção: "No module named 'httpx'" no programa instalado (2.3.1)
- O `openai` atual depende de `httpx2`, não mais do `httpx`; nos testes o `httpx` vinha do requirements-dev, por isso só falhou no instalado (GhostCLI/Claude/Gemini usam `httpx`).
- `httpx` entrou no requirements.txt e o teste do programa instalado agora importa o `httpx` e monta o tradutor do GhostCLI.
