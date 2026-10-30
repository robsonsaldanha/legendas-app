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
- Os editores de legenda e de texto do Windows reconhecem melhor. Leitura aceita UTF-8, UTF-16 e cp1252.

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

## 2026-10-19 — Editor no layout clássico de editor de legendas
- Pedido explícito: o layout clássico que ela já usa (lista, vídeo, edição, forma de onda) e vídeo rodando junto, no quadro exato.
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

## 2026-10-20 — Perfis de cliente com manual próprio
- Pedido: perfis de um cliente a partir do manual dele (PDF). Desde a 2.4.0 o conteúdo do manual não fica no código (ver abaixo).
- O `Profile` ganhou campos opcionais que os perfis antigos não usam (continuam iguais): `optimal_cps`, `min_gap_ms`, `ellipsis`, `guide`, `naming`, `style_checks`. Perfis salvos antes carregam com os valores padrão.
- O manual vai como texto no pedido de tradução (seção "MANUAL DO CLIENTE", com prioridade sobre as regras gerais). Assim o mesmo mecanismo serve para qualquer cliente: basta duplicar um perfil e colar o manual no campo "Manual do cliente".
- Reticências deixaram de ser convertidas na tradução: cada perfil decide (`…` ou `...`) no Formatar.
- Perfil em português do cliente é uma adaptação nossa; confirmar com o cliente.
- Ao trocar o idioma, o perfil automático fica na mesma família (cliente ES ↔ cliente PT).

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
- Pedido: cada perfil tem que levar para a IA exatamente as regras daquele cliente (ex.: um cliente proíbe interjeições, a Netflix aceita), e ela precisa poder criar regras novas.
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

## 2026-10-21 — GhostCLI recusando por IP mesmo com o IP liberado (2.3.2)
- O painel do GhostCLI libera IPs **por chave** (cada chave tem sua lista "IPs autorizados") e mostra só o IPv4. Duas causas prováveis do 403: a chave colada no programa é outra (sem o IP liberado) ou o Windows sai por IPv6 e o serviço vê outro endereço.
- `core/http.py`: cliente HTTP com User-Agent do programa e opção de **forçar IPv4** (`local_address="0.0.0.0"`). Ligado por padrão no GhostCLI (`Settings.ai_ipv4`, caixa "Conectar só por IPv4" em cada serviço).
- O tradutor de gateway (formato OpenAI) passou a chamar o serviço direto com `httpx`, sem o SDK da OpenAI, para poder forçar IPv4 e ler a mensagem real do erro.
- Erros 403 agora mostram o texto que o serviço devolveu (e reconhecem bloqueio do Cloudflare). O "Testar", em 401/403, mostra os IPs públicos de saída deste computador (consulta ao api.ipify.org) para comparar com o painel.

## 2026-10-21 — Repositório público; manuais de clientes fora do código (2.4.0)
- Motivo: o limite de gastos do GitHub Actions acabou (repositório privado, máquinas Windows). Em repositório público o Actions é gratuito. O Róbson autorizou tornar público e pediu para **retirar o manual do cliente** (o nome dele pode aparecer).
- Os perfis de cliente saíram de `core/profiles.py`/`core/rules.py` e o cliente de fábrica com manual saiu do `_seed_clients` (instalações novas começam só com a Netflix). Quem já tinha o cliente continua com ele; o perfil volta ao importar o arquivo.
- Importar/exportar perfis: `POST /api/profiles/import` (pacote `{"cnt_legendas_perfis": 1, "perfis": {chave: perfil}}` ou um perfil solto); "Exportar" no perfil baixa o `.cnt.json`. A chave é mantida, para os clientes ligados a ela. `same_family` passou a considerar os perfis importados.
- Cliente com perfil que não existe mais cai no perfil Netflix do idioma (como antes, sem erro).
- O histórico do git foi reescrito num único commit e as versões antigas (com o manual dentro) foram apagadas do GitHub antes de abrir o repositório. Os testes usam um perfil fictício (`tests/perfil_exemplo.py`).

## 2026-10-21 — Sincronia pela voz, editor com áreas fixas, <br />, {\an8}, revisão e origem intocada (2.5.0)
- **Sincronia (prioridade)**: a legenda 17 do teste dela continuava na tela com música depois da fala. Causa: o "automática pela fala" só deslocava a legenda inteira e media "fala" pela energia do áudio (música e ruído contavam como fala).
  - Detector de voz **Silero VAD** (ONNX, ~2 MB, MIT, v6.2.3) via `onnxruntime`, em `core/vad.py`; o modelo vai no instalador (`models/silero_vad.onnx`). Processa o áudio em trechos paralelos (≈10 s para 45 min). Sem modelo ou sem voz detectada (< 1 s) → reserva por energia, avisando.
  - `fit_to_voice` (core/sync.py): acerta início e fim de cada legenda na voz — entra quando a voz começa (até 0,8 s), sai `linger` (0,5 s) depois que a voz acaba, estica um pouco se a voz continua; nunca menor do que a leitura exige (CPS máximo, duração mínima), nem maior que a duração máxima; sem voz por perto (letreiro, música) não mexe.
  - "Automática pela fala do vídeo" = encaixe geral + `fit_to_voice`. Novo item "Acertar início e fim na voz" (só o ajuste, sem deslocar). O lote (pipeline) também usa.
- **Editor**: tamanhos fixos das áreas (variáveis CSS na grade), divisórias arrastáveis (vídeo, edição, forma de onda, painel Criar/Ajustar), duplo clique volta ao padrão; guardados em `Settings.editor`. Antes a linha de edição era `auto` e mudava de altura conforme o texto, mexendo no vídeo.
- **Quebra de linha** mostrada como `<br />` na lista (como nos editores de legenda). Enter na caixa de texto = nova linha; fora dela, Enter só leva à caixa de texto.
- **Posição**: `{\an1}`–`{\an9}` no começo da legenda (padrão SRT/ASS). Botão direito → "Subir legenda para o topo ({\an8})" e "Alinhamento…"; Ctrl+I itálico. A prévia mostra a posição. Na tradução/revisão a marca não vai para a IA e volta no mesmo lugar.
- **Configurações do editor** (⚙ no editor e em Configurações), no padrão dos editores de legenda: o que colorir na lista e a cor; tamanho/negrito da legenda sobre o vídeo; cores da forma de onda, grade, inverter roda, encaixar nos cortes de cena ao arrastar (Shift desliga), CPS na onda; fonte da lista e da caixa de texto.
- **Revisão no mesmo idioma**: ES→ES (ou PT→PT) deixou de ser bloqueado; vira revisão (prompt de revisor: corrige, aplica as regras, condensa pelo CPS, não traduz). Botão "Revisar". Saída "… (revisada).srt".
- **A legenda de origem nunca é alterada**: o programa registra os arquivos que ele cria (`gerados` no banco). Legenda aberta que não é do programa = origem: o primeiro "Salvar" cria "Nome (editada).srt" ao lado e os seguintes vão para essa cópia; "Salvar como" e "Entregar" recusam o nome da origem (a entrega com o mesmo nome do cliente vai para a subpasta "Entrega"). Tradução, revisão e entrega são sempre arquivos novos.

## 2026-10-22 — Sincronia precisa pela fala (2.6.0)
- Pedido: "a sincronia precisa ser perfeita, por fala, mesmo que ultrapasse o CPS" — a legenda entra quando a fala começa e sai quando a fala termina; CPS acima do limite fica vermelho para revisão. Caso real (Endless Love T02E90, áudio turco, legenda espanhola do cliente): a legenda 17 seguia ~1,5 s no chiado depois da fala.
- Medição no trecho real (02:00–07:20, 72 legendas): os inícios do cliente já estavam a ~2 quadros da fala; a 2.5.0 deslocava tudo 0,1 s (aceitava mudança sem melhora clara) e puxava inícios para respiração/ruído. Corrigido: `auto_sync` só desloca com melhora clara (≥ 2 pontos e ≥ 0,25 s).
- **Separação da voz** (`core/separate.py`): modelo UVR-MDX-NET-Voc_FT (ONNX, projeto Ultimate Vocal Remover; baixado do repositório público de modelos do UVR no build — conferir a licença dos pesos), STFT em numpy (igual ao torch.stft, testado), pedaços de ~6 s montados na hora (cabe um episódio inteiro na memória). Roda **em processo separado** (libera a placa ao terminar/cancelar/falhar), no DirectML (`onnxruntime-directml`, placa NVIDIA/AMD/Intel) quando há placa dedicada, senão no processador. ~3 min para 5,5 min de áudio num processador fraco de 2 núcleos; resultado guardado por vídeo (`voz16.wav`).
- **Tempos pela fala** (`core/precise.py`): Silero (32 ms) + energia da voz (10 ms); trechos de fala separados por pausas de 80 ms; começo de fala "nítido" (sobe forte; suspiro/som fraco antes da frase não conta); fim = onde a fala acaba (efeito sonoro que sobra na voz separada, sem sinal do detector, não conta); encaixe no quadro (início para trás, fim para frente); nada de esticar pelo CPS. No trecho real: 57 de 72 inícios a até 2 quadros do cliente, nenhum erro grande nos inícios conferidos, 13 fins encurtados (chiado/música), a 17 passou de 02:56,699 para 02:55,480.
- **Falas emendadas** (sem pausa entre duas legendas): corte entre palavras pela **transcrição local** (`core/whisper_local.py`, faster-whisper "small" por padrão, modelo baixado na 1ª vez para a pasta comum de modelos; CUDA na placa NVIDIA com cuBLAS/cuDNN dos pacotes pip, senão processador; processo separado, e se a placa falhar repete no processador). O texto transcrito não é usado, só os tempos das palavras. Sem transcrição, o corte fica onde estava e a legenda é marcada.
- Legendas sem certeza ganham ⚑ (motivo no `rev`), entram no F8 e somem quando ela mexe no tempo.
- Menu Sincronizar: "Sincronia precisa pela fala" (separa a voz), "Automática pela fala (rápida)" (desloca se claro + tempos pela fala sem separar) e "Só acertar início e fim na fala". Configurações: placa de vídeo (auto/não usar) e tamanho do modelo de transcrição.
- Instalador maior (bibliotecas da NVIDIA para a transcrição): o Róbson autorizou ("não me importo com o peso do instalador").
- 2.6.1: a sincronia precisa falhava no programa instalado com "name 'Settings' is not defined" (import faltando em app/editor.py). Os testes cobriam as partes, não a ligação; entrou um teste do caminho completo (separação e detector simulados) e uma checagem de nomes indefinidos (pyflakes) antes de lançar.

## 2026-10-22 — Sincronia precisa: ajustes com o episódio inteiro do PC dela (2.6.2)
- O Róbson mandou pelo OneDrive o log e o cache do editor do PC dela (voz separada, probabilidades do detector, palavras da transcrição). Confirmado: separação e transcrição rodaram **na placa de vídeo** (DirectML e CUDA); a voz separada lá é idêntica à daqui (correlação 0,999+).
- **Bug no detector de voz**: processar o áudio em 64 trechos paralelos (lote) mudava o resultado do Silero em vários pontos — falas inteiras sumiam (ex.: "Asu ya no está aquí", prob. ~0 com lote, ~0,9 sem). Agora um fluxo só (~13 s para 45 min).
- **Transcrição com idioma errado**: o Whisper detectou "en" (só olha os primeiros 30 s) e devolveu uma *tradução* em inglês, com 38% das palavras de duração zero — tempos inúteis, que geraram cortes errados no meio da fala. Agora: idioma votado em até 8 trechos com som espalhados pelo episódio, `task="transcribe"`, e as palavras só são usadas se < 15% tiverem duração zero (senão a fala emendada fica marcada para conferir, sem corte inventado).
- **Fim da fala pela energia relativa**: o fim é onde a voz cai mais de 12 dB abaixo do nível da fala forte ao redor (ou 22 dB, se o detector ainda tem certeza de que é fala — finais de frase mais baixos). Espectrograma conferido: na 17 a fala (harmônicos) termina em 174,8 s; depois vem chiado (−14 dB) e um sopro (175,9 s). Resultado: 02:51,680 → 02:54,880 (cliente: 02:56,699).
- Som curto depois da fala com o detector em dúvida (prob. < 0,85, a ≥ 0,25 s da fala) = sopro/respiração, não conta. Grito que o detector não reconhece (ex.: "¡Maldición!", prob. 0,23) conta se for alto na voz separada.
- Episódio inteiro (537 legendas): 477 inícios a até 2 quadros do cliente, só 3 mudaram mais de 0,3 s; 201 fins encurtados mais de 0,5 s (chiado/música no fim); nenhum esticado. 43 marcadas para conferir (quase todas falas emendadas, onde só a transcrição boa resolve). Conferido visualmente em 40 legendas (forma de onda + espectrograma).

## 2026-10-22 — Transcrição de vídeo sem legenda no computador (2.7.0)
- Pedido do Róbson: usar a transcrição local também quando não há legenda para se basear, "mas o modelo eu quero que seja sempre o melhor, não importa se é mais pesado".
- Novo padrão `transcribe_engine = "local"`: o passo "Transcrever" usa o Whisper no computador (`whisper_local.transcribe_words(..., full=True)`: ignora trechos sem fala, usa o contexto e os termos do glossário como dica, devolve trechos de texto e tempos das palavras). Sem custo; o orçamento mostra US$ 0. A API da OpenAI continua como opção em Configurações ("Quem transcreve a fala").
- Modelo **sempre large-v3** por padrão (o melhor do Whisper; ~3 GB, baixado uma vez, na placa NVIDIA quando houver). Quem vinha da 2.6 com "small" é migrado para large-v3 (uma vez, ao carregar as configurações sem `transcribe_engine`). Ainda dá para escolher médio/rápido.
- Idioma: se a tarefa está em "detectar", vale o idioma votado pelo Whisper em vários trechos (pt → pt-BR, es → es-419); senão, o escolhido.
- Tempos das palavras: para pt/es usa o alinhador preciso (como antes) sobre os trechos do Whisper; para outros idiomas (ex.: turco) ou com "estimado", usa as palavras do próprio Whisper.
- Sem a chave da OpenAI dá para transcrever (a tela só exige a chave quando a OpenAI foi escolhida). Se o Whisper não estiver instalado, volta para a OpenAI. Testes com API falsa continuam usando a falsa (injetada tem prioridade).

## 2026-10-22 — 20 idiomas, idioma detectado pela fala e falas estrangeiras no mesmo episódio (2.8.0)
- Pedido: português, espanhol, inglês, italiano, francês, alemão, russo, turco, persa, japonês, mandarim, grego, latim "e mais 7, os mais utilizados". Escolhidos: coreano (doramas), árabe, hindi, indonésio, holandês, polonês, hebraico. Tailandês ficou de fora de propósito: não separa palavras por espaço e a quebra de linha precisaria de um dicionário de palavras.
- Lista central em `core/languages.py` (código do arquivo, nome, código do Whisper, limites da Netflix). Limites conferidos nos guias da Netflix em 2026-10-22: japonês 13 caracteres/4 CPS; chinês simplificado 16/9 (infantil 7); coreano 16/12 (infantil 9); árabe 42/20 (17); hindi 42/22 (18); os demais 42/17 (13) — russo, grego e indonésio conferidos. Contagem de "meia largura" (japonês/coreano contam letras latinas e espaços como 0,5) não foi implementada: conta tudo como 1 (mais rígido).
- `for_language(perfil, idioma)`: o perfil do cliente é de pt/es; para japonês, chinês, coreano, árabe e hindi valem os limites da Netflix do idioma (mantém infantil se o perfil for infantil). Sem perfil: "Netflix — <idioma>" sem regras de estilo do espanhol.
- "Detectar automaticamente" é a opção padrão do idioma de origem ao colocar um vídeo. Com idioma a detectar, a transcrição local não recebe a frase-modelo em português (puxaria para o português); só o contexto e os termos do glossário. Legenda recebida: detecção por alfabeto (japonês, coreano, chinês, russo, grego, árabe/persa, hebraico, hindi) e por palavras comuns (pt, es, en, it, fr, de, tr, nl, pl, id).
- **Falas em outro idioma** (pedido: "às vezes vai ter mais de uma linguagem no mesmo EP"): depois da transcrição no idioma principal, cada trecho de fala com ≥ 1 s tem o idioma conferido pelo Whisper; trechos de outro idioma com certeza ≥ 0,8 são retranscritos no idioma deles (trechos seguidos juntos). Só troca se a nova transcrição for mais provável (log-prob média +0,15) ou, com certeza ≥ 0,92, se não for pior (forçado no idioma principal, o Whisper às vezes *traduz* a fala estrangeira). Falas muito curtas ("okay") ficam como estão. Opção em Configurações (ligada por padrão).
- Essas legendas entram no relatório ("Fala em inglês (transcrita no idioma original). Confira.") e aparecem com ⚑ no editor: as marcas ficam fora do SRT (`core/flags.py`, pasta "marcas" dos dados, ligadas ao caminho e à data do arquivo), no campo `chk` (some quando ela mexe no texto; o `rev` da sincronia some quando mexe no tempo). A tradução avisa a IA de que pode haver falas em outros idiomas (traduz tudo; se já estiver no idioma de destino, mantém).
- O alinhador preciso (pt/es) recebe só os trechos do idioma principal; os estrangeiros ficam com os tempos de palavra do Whisper.
- Japonês e chinês (sem espaço entre palavras): as palavras são juntadas sem espaço quando os dois lados são dessa escrita (vale pelo texto, então uma fala japonesa no meio de um episódio turco também), e a quebra de linha escolhe entre caracteres, preferindo depois de pontuação/espaço e sem começar linha com 、。」？！ nem terminar com 「（.
- Teste real no CI (Windows): áudio português + inglês + português (gTTS) com o Whisper "small": o inglês tem de sair em inglês e marcado.
- 2.8.1: o teste real do CI (português + inglês) mostrou que conferir o idioma por *trecho do Whisper* não basta: o Whisper junta falas de idiomas diferentes no mesmo trecho. Agora o idioma é conferido por **frase** (palavras cortadas em pausas ≥ 0,35 s); a região estrangeira é retranscrita no idioma dela e também no idioma principal, e a troca só acontece se a do idioma estrangeiro for mais provável (mesmos limites). Só as palavras daquela região saem do trecho original.
- 2.8.2: o diagnóstico no CI mostrou o motivo real: forçado em português, o Whisper **pulou** a frase em inglês (nenhuma palavra naquele trecho), então não havia frase para conferir. Agora a fala sem texto também é conferida: o detector de voz do faster-whisper acha os trechos com fala; os que ficaram < 40% cobertos por palavras entram na conferência de idioma. O resultado do Whisper guarda um "diagnostico" (idioma e certeza de cada frase, trocas feitas) no whisper.json do trabalho.

## 2026-10-22 — Pastas por mês e interface simplificada (2.9.0)
- Pedido: a usuária organiza os trabalhos por mês (SETEMBRO 2026, OUTUBRO 2026…) e achou o programa "poluído", difícil de entender (o editor está bom); quer "?" com dicas. Proposta de telas aprovada pelo Róbson ("gostei!"). Design system em `brain/Design.md` (auditoria, tokens, componentes `ds-*`).
- Respostas do Róbson: o mês é o do **recebimento**; série que continua no mês seguinte ganha **uma pasta em cada mês**; a pasta raiz ela escolhe como hoje.
- Disco: `<raiz>/OUTUBRO 2026/<Projeto>/temporada-N/ep-M` (o mês em maiúsculas, como ela usa). Banco: colunas `obras.mes` ("2026-10") e `obras.importada`. Projetos antigos (direto na raiz) ganham o mês pela pasta pai ou pela data de criação.
- **Trabalhos que já existiam**: ao escolher a pasta (e no botão "Procurar trabalhos novos nas pastas"), cada subpasta de uma pasta de mês ("OUTUBRO 2026", "Março 2026", "MARCO 2026", "10 - outubro-2026"…) vira um projeto: série se tiver pastas de episódio (temporada-N/ep-M do programa, ou feitas à mão: "EP 90", "T2E05", "Capítulo 12"), senão filme (só se tiver vídeo ou legenda). Meses passados entram como entregues. **Nada é gravado nessas pastas** (`importada` = sem projeto.cnt.json).
- Série de outro mês: `POST /api/obras/{id}/continue` cria (ou reaproveita) a mesma série na pasta do mês atual, com cliente e idiomas.
- Passos do episódio (para a tela): Arquivos (tem vídeo/legenda) → Traduzir (houve tradução, ou há uma legenda gerada pelo programa) → Revisar (último registro foi "salvar") → Entregar (entregue, pasta Entrega ou status finalizado). O botão de cada episódio é o próximo passo.
- Telas: menu com 4 itens (Início, Editor, Relatórios, Configurações; Clientes, Perfis e Em segundo plano abrem por Configurações). Início = o mês (setas, resumo, uma linha por projeto com progresso e próximo passo, outros meses). Projeto = trilha de passos por episódio + menu ⋯. Novo trabalho = 3 perguntas (o que fazer, para quem/qual episódio, arquivos); "Legendar um vídeo" já dispara a transcrição em segundo plano na pasta do episódio. Configurações = linhas com "?"; tradução pela API e Avançado recolhidos. Dicas "?" em todas as telas e no editor (`app/static/ds.js`, uma por vez, Esc fecha).
- Também: o aviso de download do modelo dizia "~480 MB" (era o large-v3, ~3 GB) e a barra parecia travada; agora mostra o tamanho certo e "Preparando a transcrição…" depois do download.

## 2026-10-23 — Licença e atualização automática (2.10.0)
- Especificação e decisões do Róbson em `Licenciamento.md` (planos, preços, venda por PIX, canais).
- Partida pelo `cntboot.py` (fica na pasta do programa; o patch não o troca): escolhe a versão baixada mais nova em `%ProgramData%\CNT Legendas\versoes`, com volta automática se ela não abrir. Atalhos do instalador chamam `pythonw -m cntboot`.
- Canal e número da montagem em `core/canal.json`, gravado pelo `packaging/build.ps1` (variáveis `CNT_CANAL`, `CNT_BUILD`); sem o arquivo, é desenvolvimento e sem atualização.
- Recursos pagos bloqueados no servidor local (`app/server.py`, `need(recurso)` → 402) e explicados na tela ("Recurso da licença paga", com "Ver os planos" e "Tenho um código"). Grátis continua: criar projeto, editor e tradução à mão.
- Na tela: etiqueta "Avaliação: N h restantes"/"Modo grátis" na barra de cima e linha "Licença" em Configurações. Ao abrir, se houver versão nova, a tela "Atualizando…" bloqueia o uso até terminar; a página recarrega sozinha.
- Instalador pela atualização: roda com o aviso de administrador do Windows (`ShellExecute runas`), em silêncio, e reabre o programa (`/ABRIR`).
- Testes: `tests/test_licenca.py`, `tests/test_atualizacao.py`; os demais testes rodam com uma licença de teste com tudo liberado (`tests/conftest.py`). No CI, o programa instalado tem de mostrar a versão completa e o canal certos.
- 2.10.0.x: o rodapé do menu mostra a versão completa (com o número da montagem), para conferir se a atualização entrou.

## 2026-10-23 — Janela própria (2.11.0)
- Pedido do Róbson: abrir como programa de PC, não numa aba do Chrome; o X pergunta antes de fechar. Escolha: **WebView2** (motor do Edge que vem no Windows) via `pywebview` — poucos MB, nada muda nas telas. Electron foi descartado (≈150 MB a mais); `msedge --app` só como quebra-galho.
- `app/janela.py`: janela maximizada, ícone do CNT e id "CNT.Legendas" na barra de tarefas (o instalador põe o mesmo id nos atalhos). Sem WebView2, sem a biblioteca ou se a janela falhar: abre no navegador como antes (`CNT_NAVEGADOR=1` força o navegador).
- Fechar no X: pergunta sempre; avisa se há trabalhos em segundo plano (contagem no banco) ou alterações não salvas no editor (a página avisa o servidor por `/api/janela/sujo`). O botão "Fechar o programa" já pergunta na página e fecha a janela sem perguntar de novo.
- Atalho clicado com o programa aberto: traz a janela para a frente (`/janela?k=`). Depois de uma atualização, a nova instância abre a janela dela (a antiga fecha junto).
- O pywebview desliga o menu do botão direito e atalhos como F5 fora da depuração; religados (ela tinha no navegador). Links externos e o ChatGPT abrem no navegador do computador (onde ela está conectada). Dados da janela (localStorage) em `<dados>/janela`.
- **Bibliotecas no pacote de atualização**: bibliotecas em Python puro listadas em `packaging/bibliotecas-no-pacote.txt` vão na pasta `lib` do patch (`<versão>/lib`, no fim do `sys.path`). Assim a janela chega à 2.10 instalada sem o instalador de 1,2 GB. Bibliotecas compiladas continuam pedindo o instalador (`[instalador]` no commit).
- CI: o programa instalado abre a janela de verdade (`--teste-janela`), espera a tela desenhar e fecha.
- 2.11.0.39 (correção): depois de uma atualização, o código roda da pasta da versão (`versoes\<versão>`, só app/core/lib), mas ffmpeg, modelos e Python ficam na pasta do programa. `app_root()` agora usa `CNT_INSTALL_ROOT` (gravado pela partida) e `code_root()` é a pasta do código. Processos auxiliares (Whisper, separador de voz, janela de arquivos) usam `module_cmd()`: o Python embutido ignora a pasta atual e o PYTHONPATH (`._pth`), então sem isso rodariam o código antigo da pasta do programa. O CI agora roda o pacote extraído sobre o programa instalado (`packaging/teste_pacote.py`). Erro visto pela usuária-teste: "Não encontrei o ffprobe… versoes\2.11.0.38\bin\ffprobe.exe".

## 2026-10-24 — Bandeja do sistema e atualização com o programa aberto (2.12.0)
- Problema relatado: depois do X (com "Sim"), algum processo continuava rodando; abrir de novo não atualizava. Agora, ao fechar a janela, o programa encerra o processo de vez (`os._exit` depois de fechar servidor e sessão).
- Pedido do Róbson: configuração **Bandeja do sistema**, ligada por padrão: o ícone fica ao lado do relógio enquanto o programa está aberto (não só depois do X) e o X esconde a janela (aviso em balão na primeira vez). Desligada: o X pergunta e encerra, sem ícone. Ícone com `NotifyIcon` do próprio WinForms (já carregado pela janela), sem biblioteca nova.
- Menu do ícone (botão direito): Exibir · Reabrir último (último episódio aberto, o mesmo "Continuar de onde parou") · Novo projeto · — · Atualizar · Reiniciar · Sair. Clique simples = Exibir. Sair pergunta (trabalhos em andamento, alterações não salvas).
- Atualização com o programa aberto: a cada 30 min (e em "Atualizar"/"Procurar atualização" em Configurações) pergunta ao servidor; se houver versão nova, pergunta "Atualizar agora / Depois". Antes de atualizar ou reiniciar: alterações não salvas no editor → Salvar / Salvar como… / Cancelar; trabalhos em segundo plano → aviso. Depois reabre **onde estava** (`CNT_RETOMAR`: a mesma tela, ou o mesmo arquivo no editor — a sessão do editor não sobrevive ao reinício, então o arquivo é aberto de novo). "Depois" = entra na próxima abertura (obrigatória, como antes).

## 2026-10-24 — Plano da 2.13: perfil sincronizado (antes de começar)
- Pedido do Róbson: perfis de usuário salvos no servidor e importáveis (PC novo, formatado), "1 perfil por key", tudo que a LGPD permite (menos as chaves de IA), métricas no servidor (sem o texto das legendas); renovar/comprar de novo não perde o perfil. Empresas (Enterprise): perfil da empresa + do usuário, até 3 perfis padrão, configurados só pela conta compradora na área do cliente (já pronto no servidor 1.1).
- Desenho: ver [[Licenciamento]] → "Perfil do usuário e Workspace no servidor". Identidade dos clientes entre computadores = nome (sem diferenciar maiúsculas). Clientes/glossários compartilhados: cada computador lembra o resumo (hash) do que sincronizou por último; se mudou aqui, envia; se mudou lá, recebe. Apagar não se propaga (evita perder dados por engano).

## 2026-10-24 — 2.13 pronta: perfil na nuvem, Workspace e métricas
- Como planejado (ver acima e [[Licenciamento]]). Configurações sincronizadas: nome na legenda, método/serviço/modelos/preços de tradução e transcrição, modelo do Whisper, falas em outros idiomas, paralelismo, dias de trabalhos guardados, bandeja, serviços de IA escolhidos (sem chaves) e preferências do editor. Ficam no computador: pasta dos trabalhos, GPU, alinhamento, blocos de áudio.
- Restaurar só é oferecido quando este computador ainda não tem perfil no servidor e a conta tem outros; a decisão (restaurar ou começar do zero) fica guardada para não perguntar de novo. Depois disso o perfil deste computador é enviado normalmente.
- Clientes compartilhados (Workspace): o programa guarda, por cliente, o resumo do que sincronizou por último (`meta ws:<nome>`). Mudou aqui → envia; mudou nos colegas e não aqui → recebe; mudou nos dois → o daqui vai na próxima (o mais recente vale). Com "Glossários" desligado no Workspace, o glossário local é mantido.
- Métricas: um registro por episódio/filme (chave = hash do computador + pasta + id), só quando algo mudou desde o último envio.
- Teste de integração real feito contra o servidor 1.2 (dois computadores na mesma licença Enterprise).

## 2026-10-24 — Plano da 2.14: glossário geral, do cliente e do projeto (antes de começar)
- Pedido do Róbson: o glossário pode ser **geral** ou **só do projeto**, para não misturar as informações de um projeto com outro.
- Três níveis, do mais amplo ao mais específico: **Geral** (vale em todos os trabalhos; Configurações → Glossário geral), **Cliente** (o que já existe) e **Projeto** (série/filme; menu ⋯ do projeto → Glossário do projeto). Na tradução (API e ChatGPT) e na transcrição entram os três juntos; se o mesmo termo aparecer em mais de um, vale o mais específico (projeto > cliente > geral).
- O projeto é descoberto pelo episódio aberto no editor (ou pelo trabalho criado em "Novo trabalho"); legenda solta, sem projeto, usa geral + cliente.
- Perfil na nuvem: o glossário geral e os glossários de projeto (pelo nome do projeto) entram no perfil do usuário.

## 2026-10-24 — 2.14 pronta: glossário geral, do cliente e do projeto
- Como planejado. Tabela `glossario_extra` (`obra_id` NULL = geral; senão, do projeto; some junto com o projeto). `Database.glossario_efetivo(cliente, projeto)` junta os três (o mais específico vale) e conta quantos termos vieram de cada nível.
- Entram na tradução pela API (trabalhos do editor e do "Novo trabalho": `obra_id` nos parâmetros), na tradução pelo ChatGPT (projeto do episódio aberto) e na transcrição (palavras-chave).
- Telas: Configurações → **Glossário geral**; projeto → menu ⋯ → **Glossário do projeto…**; a janela de tradução mostra "Glossário: N termos (X geral · Y do cliente · Z do projeto)". Editor de glossário com importar/exportar CSV (`app/static/glossario.js`).
- Perfil na nuvem: `glossario_geral` (junta com o daqui) e `glossarios_projeto` pelo nome do projeto (só preenche projeto com o mesmo nome que ainda não tem glossário).

## 2026-10-24 — Plano da 2.15 (antes de começar): sete pedidos do Róbson
1. **Memória de tradução**, sem pipocar na tela: ao salvar uma tradução, os pares original → tradução ficam guardados (por idioma, cliente e projeto). No editor, quando a legenda selecionada tem original e já houve uma tradução igual ou muito parecida antes, aparece **uma linha discreta** abaixo do texto ("Já traduzido: … · Usar"). Nada de janelas nem avisos.
2. **Formato de entrega**: padrão `.srt`. Também `.vtt`, `.ttml` (DFXP/IMSC) e `.ass`. Quem muda o padrão: **global** (Configurações), **equipe** (Workspace da empresa, no site), **cliente** e **projeto** — o mais específico vale (projeto > cliente > equipe > global). Na hora de entregar dá para trocar só daquela vez. O "Salvar" do editor continua em `.srt` (arquivo de trabalho).
3. **Prazo de entrega** por episódio/filme, opcional. A barra do topo mostra a próxima entrega prevista; no editor, o prazo do episódio aberto.
4. **Histórico de versões** da legenda: cada "Salvar" guarda uma versão (até 50 por arquivo); no editor, "Versões…" lista, compara com a atual (o que mudou em cada legenda) e restaura (vira alteração não salva, dá para desfazer).
5. **Corretor ortográfico**: só indica e sugere. Abaixo do texto da legenda, as palavras com possível erro aparecem com sugestões clicáveis; "Adicionar ao dicionário" guarda a palavra (dicionário pessoal, entra no perfil na nuvem). Nomes próprios (inicial maiúscula), números e termos dos glossários não são marcados. Biblioteca `pyspellchecker` (Python puro, vai no pacote de atualização).
6. **Aviso na bandeja** quando um trabalho em segundo plano termina (ou falha); clicar abre o trabalho.
7. **Relatar um problema**: no programa (Configurações e menu da bandeja), descrição + e-mail + registro técnico (com consentimento) → servidor → painel "Suporte".
- Pendências para o futuro (anotadas em [[Fases]]): PIX automático e nota fiscal pelo **Mercado Pago** quando houver conta PJ; lembrete de renovação por e-mail e no programa.

## 2026-10-24 — 2.15 pronta: entrega em outros formatos, prazos, versões, memória, corretor, avisos e suporte
- **Formatos** (`core/formatos.py`): `.srt` continua o padrão e o "Salvar" do editor continua em `.srt`. Coluna `formato` em `projects` (cliente) e `obras` (projeto); `Settings.formato_entrega` (global); o da equipe vem do Workspace no site (`workspaces.formato_entrega`, servidor 1.3) pelo `/v1/sync/estado` e fica no `meta` `ws_formato`. Na janela "Entregar" o formato vem escolhido (e diz de onde veio) e dá para trocar só daquela vez; a extensão do nome acompanha. TTML no perfil IMSC 1.1 Text (regiões alto/baixo para `{\an8}`, itálico em `span`).
- **Prazo**: `itens.prazo` (AAAA-MM-DD, opcional, data validada). Menu ⋯ do episódio → "Prazo de entrega…" e campo opcional no "Novo trabalho". `GET /api/prazos` lista os não entregues; o topo mostra só a próxima entrega (um selo pequeno, amarelo até amanhã, vermelho se atrasado; passar o mouse lista as seguintes) e o editor mostra o prazo do episódio aberto na barra de baixo.
- **Versões**: a cada Salvar/Entregar, uma cópia em `%APPDATA%\CNT Legendas\editor\versoes\<hash do arquivo>` (nunca na pasta dela), 50 por arquivo, sem repetir a igual. Botão 🕘 no editor: lista, compara com o que está na tela (legenda a legenda: mudou, entrou, saiu, só o tempo) e "Voltar para esta versão" entra como alteração não salva (Ctrl+Z desfaz; o original ao lado é mantido quando dá para achar). A limpeza automática da pasta do editor não toca em `versoes`.
- **Memória de tradução**: tabela `tm` (original normalizado + idioma da tradução → tradução mais nova). Guardada ao salvar/entregar legendas com original ao lado. **Mudança do plano**: fica por idioma (não por cliente/projeto) — uma frase já traduzida serve em qualquer trabalho. Busca igual e "parecida" (≥ 85%, mesmas duas primeiras palavras). Só no computador: tem texto de legenda, então **não** vai para o servidor nem para o perfil na nuvem. Configurações do editor → "Dicas debaixo do texto" desliga.
- **Corretor**: `pyspellchecker` 0.9.1 (Python puro; vai no `lib/` do pacote; o build deixa só os dicionários pt/es/en). Sugestões: acento faltando primeiro (traducao → tradução), letras trocadas (qeu → que), depois as mais parecidas. O botão "ignorar" põe a palavra no dicionário pessoal (`Settings.dicionario`, vai no perfil na nuvem). A caixa de texto do editor deixou de usar o corretor do WebView2 para não marcar duas vezes.
- **Discrição** (pedido dela: "nada pipocando"): memória e corretor aparecem numa única linha pequena abaixo do texto, sem janela, sem som; só mudam a legenda se ela clicar.
- **Bandeja**: `Worker.ao_terminar` → `Janela.aviso_trabalho` mostra um balão quando um trabalho termina ou falha, **só** se a janela não estiver em uso (escondida, minimizada ou sem foco). Clicar no balão abre o trabalho. Cancelado não avisa.
- **Relatar um problema**: Configurações e menu da bandeja. Descrição, e-mail (opcional, lembrado no navegador) e, se marcado, o fim do registro (`legendas.log`, até 150 KB) com chaves, tokens e códigos trocados por `***`; "Ver o que vai" mostra antes. Funciona sem licença. Servidor 1.3: `POST /v1/suporte` (5 por hora por IP), tudo cifrado, aviso por e-mail para a CNT, painel → **Suporte**. A Política de privacidade ganhou o item (versão dos termos `2026-10-24.2`, pede novo aceite no site).

## 2026-10-24 — Plano da 2.16 (antes de começar): status da conexão, códigos de erro, depuração
1. **Status no canto superior direito** (detalhe no `title`, ao passar o mouse): o programa (não a página) faz ping no servidor nos segundos :00 e :30 e no Google (`generate_204`) nos :15 e :45, sempre em horário "fechado". Estados: **Online · N ms**, **Conexão lenta** (> 1 s), **Reconectando…** (falhou, esperando a confirmação), **Offline — sem conexão com a internet** (nenhum dos dois responde), **Offline — servidor não responde** (Google responde, servidor não), **Offline — servidor em manutenção** (o servidor responde `manutencao`). Junto, quando offline e licenciada: até quando a licença vale sem internet.
2. **Atualização sem janela na frente**: com o programa aberto, versão nova vira um ⚠ ao lado do status; clicar abre a pergunta (salvar antes, reabrir onde estava). A atualização obrigatória ao abrir continua.
3. **Códigos de erro** `ER-RS-NXX` (resposta do servidor) e `ER-RA-NXX` (resposta do aplicativo), N ∈ {1,3,4,5,6}:
   - RS-1xx sem resposta (tempo esgotado, recusada, DNS, certificado); RS-3xx manutenção/versão não aceita; RS-4xx pedido recusado (licença, autorização, limite, dados); RS-5xx erro interno do servidor; RS-6xx resposta inválida (assinatura, conteúdo, download que não confere).
   - RA-1xx arquivos (não encontrado, permissão, disco cheio, em uso); RA-3xx vídeo/áudio (ffmpeg, mídia ilegível); RA-4xx dados (legenda/configuração inválida); RA-5xx erro interno/banco; RA-6xx componentes (WebView2, bandeja, modelos, serviço de IA).
   - O código aparece junto da mensagem para ela e vai para o registro. Catálogo em `core/erros.py`.
4. **Modo de depuração e diagnóstico** (Configurações, desliga sozinho em 5 minutos): um arquivo por tipo de ação (interface/cliques, editor, arquivos, trabalhos, rede, licença, erros, API, registro técnico) e um retrato do sistema. Cada ação com horário, o que foi pedido e a resposta (ex.: salvar → arquivo, pasta, pasta existe/aceita gravação, gravou, tamanho, releitura conferiu, ou o erro com o motivo e o código). Saída (ajustado com o Róbson: o importante é pegar o fechamento inesperado): durante a depuração, uma **pasta** `Documentos\CNT Legendas\logs\AAAAMMDD-HH-mm-ss_depuracao\` com `.log` de texto gravados linha a linha no disco (flush + fsync); ao terminar vira `AAAAMMDD-HH-mm-ss_depuracao.zip` (a pasta some). Se o programa cair, na próxima abertura ele fecha o zip e anota "fechou inesperadamente; última ação: … às HH:mm:ss". (Zip ou tar gravados ao vivo perderiam o fim ou picotariam os arquivos.)
- Servidor 1.4: **modo manutenção** no painel (liga/desliga + mensagem); `/v1/saude` devolve `manutencao` e `mensagem`.

## 2026-10-24 — 2.16 pronta: status da conexão, códigos de erro, depuração
- **Status** (`core/conexao.py`, `app/static/status.js`): `Monitor` num fio; primeiro ping na hora, depois em horário fechado (servidor :00/:30, Google :15/:45, `proximo_tick`). `GET /api/conexao` (a página pergunta a cada 5 s) devolve estado, texto, motivo, código, ms, detalhe (horários do último ping de cada um e da próxima conferência), validade da licença sem servidor quando offline, atualização disponível e a depuração. O selo fica no topo (antes do seletor de tema) e na barra de baixo do editor; o detalhe aparece ao passar o mouse.
- **Atualização**: a conferência de 30 em 30 min não abre mais janela: vira ⚠ ao lado do status; clicar abre a pergunta. A tela "Atualizando…" só cobre a página na atualização obrigatória ao abrir ou quando ela aceita (`App._atualizacao_para_tela`; antes, recarregar a página com versão nova pendente mostrava essa tela parada).
- **Códigos** (`core/erros.py`): catálogo, `classificar(exceção)`, `de_http`, `de_rede`, `de_arquivo`, `mensagem_arquivo`. Toda resposta de erro da API local leva `codigo` e a mensagem termina com "(código ER-…)". Licença, atualização, perfil na nuvem e suporte marcam o RS certo (rede, HTTP, assinatura 602, download 603, pacote 604). Erros de arquivo (`OSError`) agora têm mensagem própria (permissão, disco cheio, em uso…).
- **Depuração** (`core/depuracao.py`): `DEP.ligar(retrato)` cria a pasta, `sistema.json` (versões, Windows, pastas com permissão/espaço, configurações sem chaves, licença, conexão, pasta dos trabalhos) e passa o registro técnico (`legendas.*` em DEBUG) para `registro.log`. Tipos: `api` (cada pedido e o tempo), `editor.abrir`, `editor.salvar`, `editor.entregar` (antes/depois do arquivo, conferência relendo; falha → código), `trabalhos` (começou/terminou), `rede` (mudanças de estado), `erros` (toda resposta de erro com código), `interface.clique/campo/atalho/navegacao/erro-tela/resposta-erro` (a página manda em lotes de 1 s; campos de senha/chave viram ***; textos longos só o tamanho). Desliga sozinho (timer), por botão ou ao fechar o programa; se o programa cair, `recuperar()` na abertura gera o zip com `FECHOU-INESPERADAMENTE.txt` e o topo mostra "Relatório de depuração pronto". Gravar agora sempre relê o arquivo (`EditorError` ER-RA-107 se não bater).

## 2026-10-24 — Família CNT: hub, Dubla, API; kanban e especificações
- Pedido do Róbson: `cntoficial.com.br` vira um **hub dos produtos que a CNT aluga**, levando para `legendas.cntoficial.com.br` e o novo `dubla.cntoficial.com.br`; os produtos se completam (legenda ↔ dublagem) e ganham uma **API para empresas**. O site do Legendas (produção e `dev-legendas`) adota o mesmo layout do hub, com a identidade da CNT.
- Novas funções pedidas: legenda ao vivo, audiodescrição (no Legendas), dublagem e voz por IA (CNT Dubla), Mac e Linux (primeiro programa local empacotado; depois versão no navegador), API.
- Por enquanto **só especificação** (nada implementado): [[Pendências]] explica cada item (P-01 a P-15) e [[Tarefas]] é o kanban (T-xxx). `Fases.md` fica como histórico.
- Regra nova: não citar marcas, produtos ou empresas de terceiros em telas, site, textos de venda e documentação nova.
- `README.md` e `AGENTS.md` (nos dois repositórios) mandam qualquer pessoa ou IA ler o `brain/` antes — outra IA vai ajudar no desenvolvimento.

## 2026-10-24 — Hub CNT no ar (P-01) substituindo o CNT System
- Repositório novo `cnt-hub` (PC: `DESENVOLVIMENTO\CNT Hub`; VPS: `~/git/cnt-hub.git`, ramo `main`, deploy automático em `/var/www/html`). Vitrine, `/entrar`, páginas legais e painel `/admin`. Detalhes no `brain/` do hub.
- O CNT System foi desligado a pedido do Róbson, com cópia completa em `/home/robson/backups/cnt-system-20261024-160700/` e a pasta em `/var/www/html_cntsystem_parado` (dá para voltar).

## 2026-10-24 — 2.17: Mac e Linux (P-04, etapa 1)
- `core/plataforma.py` (só biblioteca padrão): pastas por sistema — dados do usuário (Windows `%APPDATA%`; Mac `~/Library/Application Support/CNT Legendas`; Linux `$XDG_DATA_HOME/cnt-legendas`; quem já tinha `~/.legendas` continua nela), pasta comum (Windows `%ProgramData%`; Mac `/Users/Shared/CNT Legendas`; Linux nenhuma), Documentos (Linux pelo `xdg-user-dir`), identificador da máquina (Mac pelo `IOPlatformUUID`) e "abrir/mostrar no gerenciador de arquivos" (Explorer, Finder, `xdg-open`). `config`, `licenca`, `depuracao`, `server` e `cntboot` usam ele.
- No Mac e no Linux o programa abre no **navegador padrão** (a janela própria e o ícone ao lado do relógio continuam só no Windows).
- Atualização: o pacote (patch) é o mesmo nos três sistemas. A consulta manda `sistema`; versão que exige instalador vira estado `manual` fora do Windows (o ⚠ leva ao site para baixar).
- Montagem: `packaging/build_unix.sh linux|mac` — Python 3.12 relocável (com tkinter), bibliotecas (torch CPU no Linux), programa, modelos e ffmpeg estático. Linux: `.tar.gz` + `.AppImage`; Mac (Apple Silicon): `.app` em `.dmg`, assinatura local (sem conta de desenvolvedor: na primeira vez, botão direito → Abrir).
- CI: testes também em Linux e Mac; job "Montar para Linux/Mac" depois do Windows: monta, testa o programa montado (abre e responde, ffprobe e modelos do pacote, corretor) e publica na pré-versão `desenvolvimento` (ou na versão, no `main`).
- Falta (T-023): o site oferecer os downloads de Mac/Linux e o servidor registrar os pacotes por sistema.

## 2026-10-24 — 2.18: legenda ao vivo (P-05)
- Menu novo **Ao vivo** (`#/aovivo`). O reconhecimento roda num **processo separado** (`core/aovivo_worker.py`), como a transcrição local: se travar ou faltar memória, só ele cai.
- Entrada pelo ffmpeg: microfone/placa (Windows `dshow`, Mac `avfoundation`, Linux `pulse`, incluindo o "som do computador" pelo monitor), arquivo (em tempo real, para ensaiar) ou endereço de transmissão.
- Fala: detector por energia com piso de ruído que se adapta (não precisa de modelo); fecha a fala com 0,7 s de silêncio ou 7 s seguidos (legenda não pode esperar). Parcial a cada 1 s (só no painel do operador).
- **Fila do operador:** cada legenda espera N segundos (0 a 30; padrão 3) antes de ir à tela. Clicar para corrigir **segura** a legenda; Enter corrige e manda; Esc apaga. Texto pronto entra na hora. Glossário (geral + cliente) vira dica de vocabulário do reconhecimento. Palavras escondidas viram `***`.
- A tela só recebe o que passou pela fila (o parcial nunca vai para a tela).
- **Página de legenda** `/aovivo/legenda?k=…` com **chave própria** (não é o token da sessão; guardada em `aovivo.json`, igual entre aberturas para o endereço colado no programa de transmissão continuar valendo). Recebe as legendas por Server-Sent Events (`/aovivo/fluxo`). Estilo pelo endereço: modo `bloco`/`rolando`, fundo (transparente, verde, azul, preto), cor, tamanho, posição, tarja. "Abrir janela de legenda" abre a mesma página no navegador do sistema (para capturar a janela com recorte por cor).
- Arquivo do evento: `.srt` gravado a cada legenda publicada, com os tempos reais da fala, em `<pasta dos projetos>/Ao vivo/` (ou Documentos/Ao vivo); botão "Abrir no editor" ao parar.
- Licença: por enquanto exige o recurso `transcricao`; recurso próprio `ao_vivo` fica para T-035 (precisa do servidor).
- Falta: tradução ao vivo (T-033) e a validação de 1 h em uso real (T-034).

## 2026-10-24 — 2.19: audiodescrição (P-06)
- **Dentro do editor**, não numa tela nova: o roteiro é uma legenda `.srt` em que cada legenda é uma descrição. Assim ela usa o que já conhece (vídeo, forma de onda, Criar/Ajustar, desfazer, salvar, versões). Botão **Audiodescrição** abre o painel lateral.
- Perfil pronto **"Audiodescrição — Português (Brasil)"** (90 caracteres por linha, 4 linhas, até 30 s): para a verificação de legenda não reclamar de tudo; o painel oferece trocar.
- **Espaços sem fala:** detector de voz no áudio do vídeo (o mesmo da sincronia; sem ele, os silêncios do ffmpeg), menos as legendas (opcional), com 0,2 s de respiro; mínimo 1,5 s. Aparecem numa faixa verde embaixo da forma de onda e numa lista ("Criar nos vazios" cria descrições vazias).
- **Quantas palavras cabem:** velocidade da voz em palavras por minuto (padrão 150, 80–260), guardada por computador.
- **Verificação (guia brasileiro)** como apontamentos: erro se não cabe, sobrepõe ou está vazia; aviso se cai em cima da fala, parece passado (lista de formas comuns + terminações -ou/-eu/-iu com exceções), interpreta (parece, provavelmente, triste, lindo…), usa "vemos / a câmera mostra", ou tem menos de 1 s. Regras de estilo só em português.
- **Voz:** a do próprio sistema, sem internet e sem custo (Windows: voz do sistema via PowerShell; Mac: `say`; Linux: `espeak-ng`, que a pessoa instala). Gravar com a própria voz fica para T-044.
- **Sugestão por IA:** 3 quadros do trecho (512 px) vão para o serviço de IA escolhido (mesma chave da tradução; formato de imagem de cada tipo de serviço), com as regras do guia e o limite de palavras. É rascunho: ela clica em Usar ou Descartar.
- **Exportar** (ao lado do vídeo, com "- audiodescricao" no nome; originais não mudam): roteiro `.docx` (tabela) e `.txt` com tempos, `.ttml` marcado como descrição, faixa só da audiodescrição (`.wav` 48 kHz, escrita aos poucos — filme inteiro não precisa caber na memória) e áudio **mixado** (estéreo, original abaixado para 20–70% durante as descrições, com rampa de 0,3 s; filtro em arquivo para não estourar a linha de comando). Avisa quantas descrições a voz não coube no espaço.
- Licença: sem trava nesta versão (a sugestão exige `ia_traducao`); recurso próprio `audiodescricao` em T-045.

## 2026-10-24 — Downloads de Mac e Linux (T-023)
- O CI, depois de publicar os pacotes de Mac e Linux na versão do GitHub, registra no servidor (`X-Sistema: mac|linux`) o `.dmg` e o `.AppImage` com a soma de conferência. O `.tar.gz` do Linux fica só na página de versões, para quem preferir.
- Servidor 1.6: download e atualização por sistema (ver o `brain/` do servidor). O site escolhe o botão pelo sistema de quem visita.

## 2026-10-24 — 2.20: tradução ao vivo e voz gravada na audiodescrição
- **Tradução ao vivo (T-033):** opção "Tradução ao vivo" (espanhol, português, inglês). Cada legenda que **já passou pela fila do operador** vai para o serviço de IA escolhido (mesma chave da tradução; exige o recurso `ia_traducao`), em lotes pequenos e em ordem, com as 3 anteriores de contexto e o glossário. Sai como segunda faixa: na página de legenda, `faixa=traducao` (campo "Faixa" na tela); no arquivo, `ao-vivo_….<idioma>.srt` com os mesmos tempos. Se a tradução falhar, a faixa original continua e o erro aparece no painel.
- **Voz gravada (T-044):** no painel de audiodescrição, "Gravar com a minha voz" usa o microfone pela própria tela; o áudio vai em base64, vira wav 48 kHz e fica guardado por vídeo, ligado ao início da descrição (meio segundo de tolerância). Na exportação, a gravação vale no lugar da voz do sistema. Dá para ouvir e apagar.
- (2.20, correção) Processos auxiliares que conversam por JSON na saída padrão escrevem **bytes UTF-8** (`sys.stdout.buffer`): no Windows a saída padrão do Python é cp1252 e o "…" quebrava a leitura do ao vivo. O processo de captura grava o que reclamar em `ao-vivo_….log` ao lado do arquivo do evento; se tudo der certo, o registro é apagado.

## 2026-10-24 — Respostas do Róbson (família CNT)
1. **Conta única:** aprovada como sugerido — contas no hub, os produtos confirmam a sessão com o hub (P-03).
2. **CNT Dubla:** processa no **computador do cliente** (P-07). Idiomas iniciais sugeridos: PT↔ES.
3. **API:** é de **integração** entre sistemas, não de processamento de mídia (P-08 reescrita; T-024 e T-060 descartadas).
4. **Legenda ao vivo e audiodescrição:** em **todos os planos, menos a avaliação** de 1 dia (recursos `ao_vivo` e `audiodescricao`).
5. **Validação com ela:** fica para quando todos os sistemas estiverem prontos (o que ela testou antes da atualização pelo site funcionava).
6. **Produção:** aprovada (T-008, T-074).

## 2026-10-24 — Produção ligada, conta única e API (servidor 1.7–1.9, hub 1.1)
- **Produção:** `legendas.cntoficial.com.br` no ar (nginx + certificado; servidor na `main`); variável `CNT_PROD_ATIVO=1` no repositório: cada push na `main` publica a versão `v<versão>.<montagem>` e registra o instalador e o pacote de atualização no servidor de produção.
- **Conta única:** detalhes no `brain/` do hub e do servidor. A área do cliente do Legendas entra pelo hub; a senha é a da conta CNT.
- **API de integração:** `legendas.cntoficial.com.br/api/docs` (detalhes no `brain/` do servidor).

## 2026-10-24 — CNT Dubla: programa separado para dubladores e estúdios
- Decisão do Róbson: **programa separado**, foco em **dublagem humana** (adaptar, escalar, gravar, dirigir, revisar), IA como apoio; vozes por IA nas três formas (pronta local, serviço pago do cliente, clonagem local com consentimento).
- Técnica (minha): **mesmo repositório**, pasta `dubla/` com servidor local, banco e tela próprios, reaproveitando `core/` (mídia, separação de voz, transcrição, tradução/IA, legendas, plataforma). Pasta de dados própria ("CNT Dubla"). Instalador e licença próprios ficam para T-059.

## 2026-10-24 — CNT Dubla 0.1 (P-07)
- **Roteiro:** importação de `.srt` (legenda com "- fala" vira duas falas; "NOME: fala" vira personagem) e de `.docx`/`.txt` ("00:01:02:12 NOME: fala", continuações). Cada fala tem original e adaptação; o selo de sílabas compara a adaptação com o original (ou com ~5,5 sílabas/s quando não há original). Marcações entre parênteses não contam. IA dá 3 opções do tamanho certo (mesma chave da tradução).
- **Personagens pela voz:** sem modelo extra — espectro em faixas + altura da voz por fala, agrupamento hierárquico; cria "VOZ 1, VOZ 2…" para a pessoa renomear. É sugestão.
- **Anéis:** falas seguidas do mesmo personagem até 20 s e pausas de até 4 s (configurável), meio segundo de folga, numerados na ordem do vídeo. Gerar de novo com takes gravados pede confirmação (apaga os takes).
- **Estúdio:** o take grava com pré-rolagem (contagem na tela) e guia opcional; o início real fica no take (`deslocamento` = −pré-rolagem) e dá para ajustar de 40 em 40 ms. O programa mede onde a voz começa no take.
- **Vozes por IA:** voz do sistema (sem custo) e serviço pago com a chave do cliente — modelo e voz configuráveis porque o modelo atual do serviço sai do ar em 06/01/2027. Clonagem: só com termo de consentimento registrado (cópia do termo e da amostra na pasta do programa; revogar apaga a amostra); o motor local é instalado à parte (T-057).
- **Entregas:** pasta "<projeto> - dublagem" ao lado do vídeo (ou a escolhida): faixa por personagem, mix com o M&E (sem normalizar), vídeo com o áudio novo (imagem copiada), roteiro de dublagem e anéis por dublador em `.docx`. Originais nunca mudam.
- Falta: T-058 (enviar do Legendas para a Dubla), T-059 (instalador, licença e site próprios).

## 2026-10-24 — Legendas ↔ Dubla (T-058)
- Os dois programas são separados; a troca é por **pasta**: o Legendas grava um pacote (`*.cntdubla.json` + cópia da legenda e do original) em `Documentos/CNT Dubla/Recebidos do CNT Legendas`; a Dubla lista em "Enviados pelo CNT Legendas" e, ao criar o projeto, move o pacote para `importados`. Sem rede e sem compartilhar token entre programas.
- O original vai junto quando todas as legendas têm o texto original (tradução 1:1) e entra na coluna "Original" (para a comparação de sílabas).
- Volta: a Dubla exporta "legenda da dublagem" (.srt com o texto adaptado nos tempos das falas), para legenda de acessibilidade igual ao áudio dublado.

## 2026-10-24 — CNT Dubla 0.3: produto próprio (T-059)
- **Um código, dois programas.** `core/produto.py` diz qual está rodando (`CNT_PRODUTO=dubla`, que `cntboot --produto dubla` e `python -m dubla` definem). Muda: pasta de dados ("CNT Dubla"; `CNT_DUBLA_HOME` para testes), licença e atualização (servidores `dubla.` / `dev-dubla.cntoficial.com.br`, cada um com a sua chave pública em `core/licenca.py`), versão (`dubla/__init__.py`).
- **Licença da Dubla:** recursos `dublagem` (gravar takes, transcrever, sugerir personagens, M&E, exportar), `vozes_ia` (vozes por IA e sugestões de adaptação) e `clonagem` (voz clonada). Sem licença: criar e organizar projetos e editar o roteiro. A avaliação de 1 dia leva os três. Planos no servidor: Dublador e Estúdio, **sob consulta** até o Róbson pôr os preços.
- **Tela:** selo da licença no topo (abre a janela de ativar/conferir), Configurações com licença, chave do serviço de IA (a mesma guardada pelo Legendas, se houver) e "Procurar atualização"; aviso de versão nova no topo.
- **Montagem:** o mesmo programa montado (`build\CNTLegendas`, agora com `dubla\`) gera dois instaladores no Windows (`dubla.iss`, instala em "CNT Dubla", atalho `cntboot --produto dubla`) e dois pacotes no Mac/Linux (cópia por clone/ligação, sem gastar disco). O pacote de atualização é o mesmo arquivo, registrado no servidor da Dubla com a versão dela. Segredos do CI: `CNT_DUBLA_TOKEN_DEV` / `CNT_DUBLA_TOKEN_PROD`.

## 2026-10-24 — Preços da Dubla e lista enxuta
- CNT Dubla: **Dublador R$ 249,90 por mês**; **Business** (estúdios e empresas) **sob cotação** (servidor 1.11).
- Saíram da lista (decisão do Róbson): T-057 (motor de clonagem local numa placa de vídeo) e T-075 (termos revisados por advogado, dados do MEI). Testar quando der.

## 2026-10-26 — CNT Dubla em pausa para reestruturar
- O Róbson achou que a Dubla 0.3 não ficou do jeito que o mercado trabalha. O site `dubla.` mostra só "em breve" (licença, atualização e painel seguem no ar) e a vitrine voltou para "em breve". O código continua no repositório.
- Próximo passo: pesquisa do que dubladores e estúdios usam (adaptação com banda rítmica e marcações, integração com a mesa de gravação, gravação remota, gestão de anéis/escalação/agenda, formatos de entrega) e nova estrutura do produto, decidida com ele antes de programar.

## 2026-10-26 — 2.23: destaque dourado (o da logo) em toda a família CNT
- Pedido do Róbson: o verde-lima vira o dourado da logo no programa, nos sites (Legendas, hub) e nos painéis.
- Tema escuro: `--accent` #DDB06A (meio do degradê da logo), passar o mouse #EBC587, texto sobre o destaque #1F1606. Tema claro e seções claras do site: #8C6418 (contraste ≥ 4,5:1 sobre o fundo claro).
- Como o dourado ficava parecido com o amarelo de aviso, o aviso passou a laranja (#F0A04B; no tema claro #A0521A). Forma de onda dourada (#CFA463). O selo "Em todos os planos"/"No ar" ficou dourado; "Em breve" ficou cinza.
- O verde continua só onde quer dizer "funcionando" (ponto "Online", status do servidor).
- Capturas do site refeitas com o programa novo.

## 2026-10-26 — 2.24: atualização passo a passo e "o que mudou" ao reabrir
- Pedido do Róbson: com atualizações pequenas o programa abria, fechava e reabria tão rápido que parecia defeito. Agora a tela mostra os passos (procurar, baixar com %, instalar), conta 3, 2, 1 e diz "Reiniciando o aplicativo…" antes de fechar.
- Ao reabrir, "Atualização concluída" com o que mudou, ou "Erro na atualização" com o código (ER-RA-441: a versão nova não abriu e a partida voltou para a anterior). Caixa para não mostrar mais a tela de novidades; erros aparecem sempre.
- **As notas da versão são a mensagem do commit** (o CI manda para o servidor): a partir de agora, o commit de versão do programa é escrito para quem usa — primeira linha `X.Y.Z: resumo` e um item por novidade, em português simples. Linhas técnicas ficam fora ou num commit separado.
- Quem atualizar da 2.22/2.23 vê o fluxo antigo nessa primeira vez (é o código antigo que baixa); ao abrir a 2.24, as novidades aparecem pela lista local `NOVIDADES_LOCAIS`.

## 2026-10-26 — 2.25: salvamento automático no editor
- Pedido do Róbson: salvar a cada minuto, guardando antes a versão anterior, com tempo configurável e personalizável.
- Configurações › Salvamento automático: ligado por padrão, **a cada 1 minuto** (1 a 60) e só quando há alteração. Salva no próprio arquivo (o mesmo do "Salvar"); a legenda de origem do cliente continua protegida (o primeiro salvamento vai para a cópia "(editada)").
- **Versão anterior** guardada antes de cada salvamento (automático ou não): sempre no histórico (🕘, origem "Antes de salvar"); opcionalmente **ao lado da legenda** (`<nome>.anterior.srt`) ou **numa pasta escolhida** (com data e hora no nome, mantendo as N mais novas — padrão 20).
- Não salva com uma janela aberta na frente nem legenda nova sem arquivo (a barra de baixo avisa "salve uma vez…"). Erro no salvamento automático aparece só na barra de baixo e tenta de novo no próximo intervalo.

## 2026-10-30 — 2.26: ideias do editor (P-23; renumerada porque o Róbson criou P-17 a P-22 no mesmo dia)
- **Modo foco** (botão ◎ na barra do editor, lembrado no computador): mesmo layout; as outras legendas a 32% de opacidade, a atual com contorno dourado.
- **Anotações**: tabela `anotacoes` (chave = `item:<id>` no episódio de projeto, senão o caminho do arquivo; as notas vão junto quando o primeiro Salvar cria a cópia "(editada)"). Ligadas à legenda pelo tempo (mesmo início ±0,3 s ou dentro dela). Coluna própria 🗒 na lista; menu do botão direito › "Anotação…". Nunca vão para o .srt.
- **Tela de cinema** (botão de filme): vídeo em tela cheia com a legenda; espaço pausa, ← → legenda anterior/próxima, N anota (a caixa fica no alto, sem cobrir a legenda), Esc sai e volta ao editor na legenda daquele momento.
- **Glossário aprendido**: tabela `correcoes` (projeto, de, para, vezes, decidido). Só troca de palavra por palavra digitada no editor (não conta tradução por IA nem aplicar versões). Na 3ª vez pergunta; "sim" põe no glossário do projeto (termo = palavra antiga, tradução = nova, com nota); "não" não pergunta mais. Só em episódios de projeto.
- **Autocompletar** no texto: termos do glossário (projeto, cliente, geral), nomes próprios e palavras da legenda; a partir da 2ª letra; Tab/Enter aceita, ↑↓ escolhe, Esc fecha.
- **Antes de entregar**: nota 0–100 (`core/qualidade.py`: desconto por tipo de problema proporcional à parte da legenda, com teto por tipo; ortografia conta palavras não reconhecidas, ignorando dicionário e glossário) e comparação com a **última entrega**; na primeira, com o **original** (a legenda de origem, a versão mais antiga do histórico ou o arquivo no disco). Original em outro idioma (tradução): compara só tempos e quantidade. Destaques palavra a palavra, filtros, clique leva à legenda.
- **Relatórios na entrega**: `.alteracoes.txt` (resumo + cada mudança) e `.relatorio.pdf` para o cliente (nome e logo em Configurações › Relatório para o cliente; `core/pdf_simples.py`, sem biblioteca de fora, para chegar pelo pacote de atualização).
- **Ritmo e previsão** (`core/ritmo.py`): base = trabalhos **entregues pelo programa** com ≥5 min ativos; aparece a partir do 3º (2 de base). Tempo ativo (a cada minuto com teclado/mouse/vídeo tocando), parado (editor aberto sem atividade; coluna nova `tempo.parado`) e fora (do começo — `itens.primeira_atividade` — à primeira entrega, menos ativo e parado). Previsão no rodapé do editor ("falta ~1h20 · termina amanhã", em laranja/vermelho se apertado/atrasado) e painel "Seu ritmo" em Relatórios. Sem licença com relatórios, a previsão só não aparece (não abre aviso).
- Com a Dubla em pausa, o botão "Dublagem" saiu da barra do editor (a barra estava apertada).

## 2026-10-30 — 2.27: lançador antes do programa
- O Róbson testou a 2.26: o giro de "Procurando" recomeçava no meio, a barra e os MB não andavam (download rápido pulava direto) e a tela abria em tela cheia. Pediu um "atualizador" separado, que abre antes, confere licença e se a cópia é original, e só então abre o programa (referência: lançador escuro pequeno com título grande, barra laranja e passo embaixo).
- **Lançador** (`app/static/lancador.html` + `lancador.js`, rota `/lancador`; `/open?ir=lancador` leva a ele): janela de 620×380 sem moldura, arrastável, sem redimensionar. Passos: **Verificando atualizações** (barra indo e voltando) → **Baixando** (barra e "X de Y MB" animados até o alvo; antes de instalar enche até 100%) → **Instalando** → contagem 3, 2, 1 → **Reiniciando** (o programa reabre já no lançador) → **Validando versão** (licença no servidor + arquivos) → **Concluído** ("Tudo pronto. Abrindo o CNT Legendas… · Licença ativa até…") → abre a janela principal (maximizada) e fecha o lançador. × fecha o programa.
- **Conferência dos arquivos** (`core/integridade.py`): na montagem (`packaging/manifesto.py`, chamado no build.ps1 e build_unix.sh, antes do pacote de atualização) grava `core/arquivos.json` com SHA-256 de `app/` e `core/` (sem `__pycache__`, sem `canal.json`). No lançador: diferente ou faltando = aviso **ER-RA-450** "Esta cópia está alterada… reinstale pelo site", com "Abrir mesmo assim" (não trava: o manifesto não é assinado, então serve para cópia danificada/mexida, não contra pirataria; a licença continua sendo a trava). Rodando do código-fonte (sem manifesto) não confere.
- O download baixa em pedaços de 256 KB (antes 1 MB), para o progresso andar em downloads pequenos.
- Na tela de atualização dentro do programa (sem janela, no navegador), o desenho é feito uma vez e só os valores mudam (o giro não reinicia) e a barra anima até 100% antes de instalar.

## 2026-10-30 — 2.27.1: abertura e "ping" lentos (IPv4 primeiro)
- O Róbson viu o lançador levar mais de 1 minuto em cada passo e o selo de conexão mostrar 14.000 ms (às vezes ~2.400), com `ping` do Windows de 15 ms para a VPS. Servidor medido de fora: ~1 s com TLS, normal.
- Causa provável: os domínios (atrás da proteção de DNS/proxy) têm IPv4 e IPv6; o Python tenta o IPv6 primeiro e só passa para o IPv4 depois de esgotar o tempo de cada endereço (2 endereços × 6 s ≈ 14 s). O navegador tenta os dois juntos e não sente.
- **`core/rede.py` `preferir_ipv4()`** (chamado ao abrir): reordena as respostas de endereço com IPv4 antes; IPv6 continua como reserva. Vale para tudo (servidor, atualização, licença, IA).
- Tempo para abrir conexão: 4 s no selo, 5 s na atualização e na licença, 8 s no download.
- O selo reaproveita a conexão (keep-alive 90 s): o número mostrado passa a ser o tempo de resposta, não o aperto de mão TLS a cada 15 s.
- Lançador: não confere a licença de novo; espera a conferência que já começou ao abrir (até 6 s; sem resposta, fica a guardada). "Verificando atualizações" espera no máximo 15 s e segue na versão que tem. Pausas mínimas menores (0,5 s).

## 2026-10-30 — 2.27.2: Ao vivo com endereço de página de vídeo
- O Róbson colou o link de uma página de vídeo (site de vídeos) em "Endereço de uma transmissão" e recebeu o erro cru do ffmpeg ("Invalid data found…"). O ffmpeg abre transmissões (rtmp, srt, rtsp, .m3u8, áudio direto), não páginas com player.
- `core/aovivo.conferir_endereco`: endereço http(s) de site de vídeo conhecido é recusado antes de começar, com a explicação e o caminho (endereço da transmissão, ou som do computador). Outros http(s) seguem (podem ser áudio direto).
- `aovivo_worker.explicar_erro`: erros do ffmpeg viram frase clara (abrir entrada, transmissão fora do ar, aparelho de áudio), com o detalhe técnico no fim.
- Não extraímos áudio de dentro de páginas de sites de vídeo (contra os termos desses sites e quebra a cada mudança deles). Proposta em aberto: entrada "Som do computador" (captura do que toca nos alto-falantes), que serve para qualquer site.


## 2026-10-30 — CI do Mac em máquina macOS 15
- A imagem macOS 14 do GitHub sai do ar em 02/11/2026 e já estava com paradas programadas (a montagem do Mac da 2.27.1 foi cancelada duas vezes sem começar). O CI passou para `macos-15` (Apple Silicon).
