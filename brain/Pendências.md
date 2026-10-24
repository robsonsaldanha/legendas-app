# Pendências — especificações do que vem

Este arquivo **explica** cada pendência: o que é, por que, como deve funcionar e o que conta como pronto.
O andamento (feito / fazendo / a fazer) fica em [[Tarefas]] — o "kanban". Cada tarefa lá aponta para uma seção daqui (`P-xx`).

Regras para quem for implementar (pessoa ou IA):
- Leia [[00 - Início]], [[Arquitetura]] e [[Decisões]] antes. Ao terminar algo, marque em [[Tarefas]] e registre a decisão em [[Decisões]].
- Textos voltados ao cliente são em português do Brasil, claros e sem jargão.
- **Não citar marcas, produtos ou empresas de terceiros** em telas, site, textos de venda e documentação nova. Descreva a função ("programa de transmissão ao vivo", "serviço de voz por IA"), nunca o nome.
- Privacidade é regra do produto: o que roda no computador do cliente continua lá; o que for para o servidor precisa estar na Política de privacidade (LGPD) **antes** de ir ao ar.
- Status das especificações: **rascunho** (ideia aprovada, faltam decisões) · **pronta** (dá para implementar) · **em andamento** · **feita**.

---

## Visão geral: a família CNT

Pedido do Róbson (24/10/2026): a CNT passa a ter um **hub de produtos que alugamos**, em `cntoficial.com.br`, que apresenta e leva para:

| Produto | Endereço | O que faz |
|---|---|---|
| **CNT Legendas** | `legendas.cntoficial.com.br` (homologação `dev-legendas.…`) | Legendagem e tradução: transcrever, traduzir, sincronizar, revisar, entregar. Já existe (programa 2.16 + servidor 1.4). Ganha **legenda ao vivo** e **audiodescrição**. |
| **CNT Dubla** | `dubla.cntoficial.com.br` (homologação `dev-dubla.…`) | Dublagem e voz por IA: roteiro de dublagem, vozes, mixagem. Produto novo. |
| **API CNT** | `api.cntoficial.com.br` (homologação `dev-api.…`) | Para empresas integrarem os produtos nos sistemas delas. |

Os produtos **se completam**: um projeto de legenda vira roteiro de dublagem com um clique, e a dublagem devolve a legenda ajustada à fala dublada. A mesma conta (P-03) entra em todos.

Onde fica cada código:
- Hub `cntoficial.com.br`: projeto do Róbson na VPS em `/var/www/html` (o sistema que atende o domínio principal), **não** está neste repositório.
- Site, área do cliente, painel e API do Legendas: repositório `cnt-legendas-server`.
- Programa do Legendas: este repositório.
- CNT Dubla e API CNT: repositórios novos (a criar), seguindo o mesmo padrão (Node + MySQL, `brain/`, sem Docker, um usuário MySQL por projeto, pasta `/var/www/html_<nome>` na VPS).

---

## P-01 — Hub de produtos em `cntoficial.com.br` · rascunho

**Por quê:** uma vitrine única da CNT, que apresenta os produtos e leva para cada um.

### Público (visitante)
Página única, longa, com rolagem por seções. Layout (definido pelo Róbson a partir de uma referência que ele mostrou; aqui só a descrição, sem nomes):

1. **Barra de navegação fixa** no topo, fundo escuro translúcido com desfoque. Logo CNT à esquerda; links âncora (Produtos · Como funciona · Planos · Clientes · Contato); à direita "Entrar" (área do cliente) e um botão de destaque "Falar com a gente".
2. **Abertura (tela cheia, fundo quase preto)**: rótulo pequeno em caixa alta e espaçado ("LEGENDAS · TRADUÇÃO · DUBLAGEM"); título enorme em duas linhas, a segunda com a palavra-chave na cor de destaque; um parágrafo curto; dois botões (principal "Conhecer os produtos", secundário "Falar no WhatsApp"); ao fundo, a marca CNT grande em textura pontilhada/meio-tom, discreta, com leve movimento. Indicador "role" para baixo.
3. **"O problema"**: três ou quatro frases curtas e fortes, uma por linha (ex.: "Prazo apertado e legenda fora do tempo.", "Tradução que não respeita o manual do cliente."), terminando em "A CNT tira isso do caminho."
4. **"O que fazemos"**: lista numerada (01, 02, 03…) de linhas grandes; ao passar o mouse (ou tocar), a linha se abre com uma descrição e etiquetas pequenas. Itens: Legendagem e tradução · Legenda ao vivo · Audiodescrição · Dublagem e voz · API para empresas.
5. **Produtos** (seção de **fundo claro**, quebra o escuro): um bloco por produto, alternando imagem à esquerda/direita: captura de tela real do produto numa moldura, endereço (`legendas.cntoficial.com.br`) em fonte mono pequena, selo de situação ("No ar", "Em breve", "Teste grátis"), nome, frase e link "Conhecer →".
6. **Resultados / casos**: cartões numerados ("CASO 01") com a área, o problema e o que mudou. Só com casos reais autorizados; sem caso, a seção não aparece.
7. **Como funciona**: linha do tempo horizontal com 4 etapas (ex.: "Dia 1 — você cria a conta e testa", "Semana 1 — seus clientes e regras configurados", "Todo dia — produção", "Sempre — suporte e atualizações").
8. **Compromisso**: uma citação grande centralizada e três garantias em linha ("Seus vídeos não saem do seu computador / Suporte em português / Atualizações incluídas").
9. **Planos** (se houver produto à venda): cartões lado a lado; os preços vêm do painel de cada produto (nada fixo no HTML).
10. **Chamada final**: título grande ("Tira esse projeto do papel."), frase e botão.
11. **Rodapé** em 4 colunas: texto curto + e-mail; Navegue; Produtos; Legal (Privacidade, Termos, Cookies, Área do cliente). Linha final com © e CNPJ (do painel).
12. **Botão flutuante de WhatsApp** (canto inferior direito) e **aviso de cookies** (canto inferior esquerdo, "Aceitar todos" / "Só essenciais", com link para a política).

**Visual:** identidade da CNT, layout da referência.
- Cores: grafite quase preto de fundo (tokens atuais `--bg`/`--panel`), texto claro; **cor de destaque = lima da CNT** (`--accent` #C9D94B) nos botões e na palavra destacada; seção de produtos em off-white; dourado só no logo.
- Tipografia: títulos na fonte display da marca (hoje Anton) ou numa geométrica em negrito, grandes (60–72 px no computador); texto em Inter; rótulos e endereços em mono.
- Muito respiro (seções de ~600–900 px de altura), cantos arredondados nos cartões, animações suaves ao rolar (aparecer de baixo), sem exagero. Respeitar `prefers-reduced-motion`.
- Celular primeiro: tudo empilhado, menu vira gaveta, títulos ~40 px.
- Acessibilidade: contraste ≥ 4,5:1, foco visível, navegação por teclado, textos alternativos.

### Área logada (cliente)
Mesmo visual, layout de painel: barra lateral (Início · Meus produtos · Licenças/assinaturas · Faturas · Suporte · Minha conta · Privacidade) e conteúdo.
- **Início**: cartões dos produtos contratados com situação (ativo, vence em X dias, vencido) e botão "Abrir"; produtos não contratados aparecem como "Conhecer".
- **Meus produtos**: por produto, o que hoje existe na área do cliente do Legendas (licenças, computadores, produção, Workspace) — o hub mostra o resumo e leva para a área do produto (sem duplicar telas).
- **Faturas**: todos os pagamentos de todos os produtos.
- **Suporte**: abrir chamado (mesma base do "Relatar um problema").
- Painel do Róbson (`/admin`): produtos do hub (nome, endereço, situação, imagem, ordem), textos das seções, casos, links de WhatsApp, dados da empresa.

**Pronto quando:** página pública e área logada no ar em homologação, notas ≥ 90 em desempenho e acessibilidade numa auditoria de página, textos editáveis no painel, e o Róbson aprovar.

## P-02 — Novo visual do site do Legendas (`legendas.` e `dev-legendas.`) · rascunho

O site do servidor (`cnt-legendas-server`: `public/`, `paginas/`, `src/layout.js`, área do cliente `/login`/`/conta`) adota **o mesmo layout do P-01**, para parecer parte da família:
- Página inicial do produto no formato do P-01 (abertura, problema, funções, como funciona, planos, chamada final, rodapé), focada em legendagem.
- Área do cliente e painel com o mesmo cabeçalho/rodapé e componentes do hub (componentes compartilhados: copiar os tokens e o CSS base para os dois projetos, ou servir um CSS comum pelo hub — decidir).
- Vale para **produção e homologação** (`dev-legendas`) — a homologação recebe primeiro.
- Páginas legais e status continuam geradas no servidor, só com o visual novo.

**Pronto quando:** todas as páginas do site, área do cliente e painel no visual novo, testes do servidor passando, capturas de tela conferidas no celular e no computador.

## P-03 — Conta única CNT (entrar uma vez, usar todos) · rascunho

Hoje cada produto teria a sua conta. Proposta: a conta vive no **hub** (CNT ID) e os produtos confiam nela.
- Entrar em `cntoficial.com.br/entrar` vale para `legendas.`, `dubla.` e `api.` (cookie de sessão no domínio `.cntoficial.com.br` com token assinado, ou fluxo de autorização padrão com redirecionamento — decidir).
- Migração: as contas que já existem no Legendas viram contas CNT (mesmo e-mail, mesma senha cifrada; aviso por e-mail).
- Dados pessoais cifrados como hoje (AES-GCM + índice cego); aceite dos termos por produto.
- O painel do Róbson vê o cliente e todos os produtos dele numa tela só.

**Decisões em aberto:** onde fica o banco das contas (no hub ou num serviço próprio); como os produtos validam a sessão.

## P-04 — Legendas no Mac e no Linux (ou no navegador) · rascunho

**Fato importante:** o programa já é um servidor local + páginas no navegador; no Windows ele só abre numa janela própria. Ou seja, o mesmo código já roda no Mac e no Linux abrindo no navegador padrão. O que falta é **empacotar e tirar o que é só do Windows**.

Caminho recomendado (em duas etapas):
1. **Programa local para Mac e Linux** (mesmo modelo de hoje: vídeos ficam no computador).
   - Pacotes: Mac (`.dmg` com app assinado e notarizado — exige conta de desenvolvedor da Apple), Linux (`.AppImage` e `.deb`).
   - Trocar as partes do Windows: identificação do computador para a licença (no Mac o identificador da máquina; no Linux `/etc/machine-id`), cofre de senhas do sistema para as chaves de IA (já é por biblioteca que suporta os três), ícone ao lado do relógio (biblioteca multiplataforma ou sem bandeja), janela própria (o mesmo componente de janela suporta os motores nativos do Mac e do Linux), caixa "Abrir arquivo", pastas padrão, "Abrir a pasta".
   - Transcrição local: placa de vídeo no Linux; no Mac, versão para os chips próprios da Apple (decidir modelo/biblioteca).
   - Binários de vídeo (ffmpeg/ffprobe) por sistema; atualização automática com canal por sistema (`windows`, `mac`, `linux`) no manifesto assinado.
   - CI: rodar os testes e montar os pacotes em máquinas Mac e Linux.
2. **CNT Legendas no navegador (nuvem)**, depois: a mesma interface servida pelo servidor, com envio do vídeo. Muda a regra "o vídeo não sai do computador" — vira **opção** do cliente, com aviso claro e retenção curta (ex.: apagar em 7 dias). Exige processamento no servidor (o mesmo da API, P-08).

**Pronto quando (etapa 1):** instaladores de Mac e Linux publicados pelo CI, licença e atualização funcionando, testes passando nos três sistemas.

## P-05 — Legenda ao vivo (TV, transmissões, eventos) · feito na 2.18 (falta tradução ao vivo e validação: T-033…T-035)

Gerar legenda em tempo real a partir do áudio de uma transmissão, com uma pessoa corrigindo se quiser.
- **Entrada de áudio:** microfone, áudio do sistema, placa de captura ou entrada de rede de vídeo profissional (o que o ffmpeg do sistema conseguir ler); escolha do canal de áudio.
- **Reconhecimento contínuo:** pedaços curtos com detector de voz (já existe `core/vad.py`) e transcrição local em fluxo; meta de atraso **≤ 3 s** (fala → legenda na tela). Pontuação e quebra de linha pelas regras do perfil (máx. caracteres/linha, 2 linhas).
- **Modos de exibição:** "rolando" (linhas sobem, como TV aberta) e "bloco" (legenda inteira aparece e some).
- **Saídas:**
  - janela de legenda com fundo de cor sólida (para recorte por cor) ou transparente, para capturar em programas de transmissão;
  - endereço local de página (fonte de navegador) com a legenda ao vivo, estilo configurável;
  - arquivo `.srt`/`.vtt` gravado durante o evento (com os tempos reais) para publicar depois;
  - futuro: legenda oculta de TV (padrões de closed caption) por codificador externo.
- **Operador:** painel com o texto chegando, atraso configurável (segura N segundos para dar tempo de corrigir), atalhos para corrigir palavra, apagar linha e inserir texto pronto; glossário do cliente/projeto aplicado (nomes próprios certos); filtro de palavrões opcional.
- **Tradução ao vivo** (opcional): segunda faixa de legenda em outro idioma, com atraso maior.
- **Depois do evento:** abre no editor normal para revisar e entregar.
- Licença: recurso pago próprio ("ao_vivo"), métricas de minutos ao vivo.

**Pronto quando:** 1 hora de transmissão contínua sem travar, atraso médio ≤ 3 s, janela e página de legenda funcionando, arquivo final correto.

## P-06 — Audiodescrição · rascunho

Roteiro e áudio de audiodescrição (descrição das cenas para pessoas cegas), dentro do Legendas.
- **Achar os espaços:** usa a fala (detector de voz) e a legenda para marcar os trechos sem diálogo onde cabe descrição; mostra a duração disponível de cada um.
- **Roteiro:** editor parecido com o de legenda: cada descrição tem início, fim e texto; contador de palavras que cabem no tempo (velocidade de leitura da voz configurável); regras do guia brasileiro de audiodescrição (ABNT NBR 16452) como perfil de verificação (tempo verbal no presente, não interpretar, não antecipar…).
- **Sugestão por IA (rascunho):** a partir de quadros do vídeo naquele trecho, sugere uma descrição curta que a pessoa revisa. Nada é aplicado sem ela aceitar.
- **Voz:** ouvir a descrição com voz sintética (local ou serviço de voz), ajustar velocidade; gravar com a própria voz (microfone) também.
- **Saídas:** roteiro (`.docx`/`.txt` com tempos), faixa de áudio da audiodescrição (`.wav`), faixa **mixada** com o áudio original abaixando o volume nos trechos descritos, e texto com tempos (TTML com descrições) para plataformas.
- Licença: recurso pago próprio ("audiodescricao").

**Pronto quando:** um episódio inteiro com roteiro, verificação, faixa mixada e exportações.

## P-07 — CNT Dubla (dublagem e voz por IA) · rascunho

Produto separado (`dubla.cntoficial.com.br`), que conversa com o Legendas.
- **Fluxo:** vídeo → transcrição com **quem fala** (separação de falantes) → tradução (reaproveita a do Legendas, com glossário e regras) → **adaptação para dublagem** (encaixar o texto no tempo da fala original, sincronia labial aproximada, número de sílabas) → **vozes** por personagem → **separação** da voz original e da música/efeitos (já existe `core/separate.py`) → **mixagem** das vozes novas com a música/efeitos → exportação.
- **Editor de dublagem:** linha do tempo por personagem; para cada fala: texto, duração, gerar de novo, mais rápido/mais lento, trocar a voz, emoção/entonação; ouvir trecho; travar falas aprovadas.
- **Vozes:** biblioteca de vozes sintéticas por idioma e **clonagem de voz só com autorização documentada** do dono da voz (termo de consentimento assinado, guardado; voz é dado biométrico — tratar como dado sensível na LGPD). Proibido clonar voz de terceiros sem autorização; o sistema registra quem autorizou.
- **Integração com o Legendas:** "Enviar para dublagem" no projeto de legenda; a Dubla devolve a legenda ajustada à fala dublada.
- **Saídas:** faixa dublada mixada, faixas separadas (vozes, música/efeitos), vídeo com o áudio novo, roteiro de dublagem.
- **Onde processa:** gerar vozes e separar áudio pede placa de vídeo forte — começar com processamento no servidor (P-08) ou no computador do cliente quando houver placa; decidir pelo custo.
- **Cobrança:** por minuto de vídeo dublado + plano mensal; minutos visíveis na área do cliente.
- Pendências de produto: quais idiomas no começo (PT-BR ↔ ES), qualidade mínima aceitável, termo de uso de voz.

**Pronto quando:** dublar um episódio de 20 min PT↔ES com 3 personagens, revisão no editor e exportação, dentro do custo definido.

## P-08 — API CNT para empresas · rascunho

Para outras empresas usarem os produtos dentro dos sistemas delas.
- **Acesso:** chaves de API por empresa (criadas na área do cliente, com nome, permissões e validade; mostradas uma vez; guardadas só como resumo), ambiente de teste separado.
- **Recursos (REST, JSON):**
  - `POST /v1/arquivos` (envio em partes para vídeos grandes) e `GET /v1/arquivos/{id}`
  - `POST /v1/trabalhos` com `tipo`: `transcrever`, `traduzir`, `sincronizar`, `verificar` (QC por perfil), `converter` (formatos), `audiodescrever`, `dublar`
  - `GET /v1/trabalhos/{id}` (situação, progresso, resultado), `DELETE` (cancelar)
  - `GET /v1/perfis`, `POST /v1/glossarios`
  - **Webhooks** assinados quando um trabalho termina ou falha
- **Erros** com os códigos do padrão CNT (`ER-RS-…`) e mensagem.
- **Limites** por plano (requisições/minuto, minutos de vídeo/mês) e cobrança por minuto processado.
- **Documentação** pública (OpenAPI) em `api.cntoficial.com.br/docs`, com exemplos e ambiente de teste.
- **Processamento no servidor:** fila de trabalhos com máquinas de processamento (placa de vídeo) — é a mesma base do Legendas no navegador (P-04 etapa 2) e da Dubla (P-07).
- **Privacidade:** arquivos apagados após N dias (configurável, padrão 7), contrato de tratamento de dados para empresas, registro de acesso.

**Pronto quando:** uma empresa de teste envia um vídeo, recebe a legenda traduzida pelo webhook, e o consumo aparece na fatura.

---

## Pendências que já existiam

### P-10 — Validar com o uso real · contínua
Validar com vídeos e projetos reais da usuária (filme com intervalo, legenda de outra versão, relatório de produtividade); testar no Windows dela (janelas Abrir/Salvar, cofre de senhas, vídeo tocando, F11/F12, dois perfis do Windows ao mesmo tempo); instalar no PC deles e testar nos dois perfis; confirmar assinatura e atalhos que faltam; confirmar com o cliente as regras do perfil em português; calibrar a sincronia com legendas acertadas à mão (quanto antes da fala ela gosta de entrar).

### P-11 — Ligar a produção · aguardando aprovação
nginx + certificado de `legendas.cntoficial.com.br`, variável `CNT_PROD_ATIVO` no CI, termos revisados por advogado, dados da empresa (MEI/CNPJ) no painel.

### P-12 — PIX automático e nota fiscal · futuro (quando houver conta PJ)
Integração com um meio de pagamento que gere PIX com confirmação automática e emita nota fiscal; substitui a aprovação manual do PIX no painel. Renovação automática da licença ao confirmar o pagamento.

### P-13 — Lembrete de renovação · futuro
E-mail e aviso discreto no programa alguns dias antes de vencer (7, 3 e 1 dia), com o link para pagar; configurável no painel.

### P-14 — Workspace: apagar propaga · futuro
Hoje apagar cliente/glossário no Workspace da empresa não chega aos colegas (de propósito). Fazer a remoção propagar com "lixeira" de 30 dias.

### P-15 — Proteção do código de licença · futuro
Compilar os módulos de licença, repositório privado e máquina própria para os builds.
