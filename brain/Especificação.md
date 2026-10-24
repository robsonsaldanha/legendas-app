# Especificação — Aplicativo de Legendagem Automática para Windows

> Documento para o Claude que vai desenvolver o sistema. Leia tudo antes de começar. Construa por fases (seção 13) e valide cada fase comigo antes de seguir para a próxima.

## 1. Objetivo

Criar um **aplicativo desktop para Windows (10/11, 64 bits), com instalador**, para minha esposa, que é legendadora profissional (freelancer, principalmente **português do Brasil → espanhol neutro/latino**, em projetos no padrão Netflix). O app gera **arquivos .srt** (nunca grava legenda no vídeo).

**Tudo roda no PC dela.** A única dependência externa é a **API da OpenAI** (transcrição e tradução). Não há servidor, VPS nem banco remoto.

Ela recebe trabalhos de tipos diferentes. O app precisa permitir que ela **escolha quais etapas executar** em cada trabalho:

- só transcrever
- só traduzir
- transcrever + traduzir
- traduzir + sincronizar
- trabalho completo (transcrever + sincronizar + traduzir)

O resultado é um rascunho de alta qualidade, que ela revisa no editor de legendas dela. O app não substitui a revisão humana. Ele elimina o trabalho braçal.

## 2. Stack recomendada

- **Linguagem:** Python 3.11 ou 3.12 (tudo numa linguagem só: interface e processamento)
- **Interface:** PySide6 (Qt), em português, visual limpo e moderno
- **Processamento:**
  - `ffmpeg` / `ffprobe` (binários para Windows, empacotados junto)
  - `WhisperX` para alinhamento forçado, em CPU, com `torch` versão CPU
  - `ffsubsync` para correção de sincronia
  - SDK oficial `openai`
  - `pysubs2` (ou `srt`) para ler e gravar legendas
- **Dados locais:** SQLite em `%APPDATA%\Legendas\` (projetos, glossários, perfis, histórico de trabalhos, logs)
- **Chave da OpenAI:** guardada no **Gerenciador de Credenciais do Windows** (biblioteca `keyring`), nunca em texto puro nem no código. Tela de configurações para colar e testar a chave.
- **Processamento em segundo plano:** worker em thread ou processo separado (QThread/multiprocessing), para a interface nunca travar. Um trabalho por vez, com fila local.

## 3. Instalador e empacotamento

- **Instalador:** Inno Setup gerando `Instalador_Legendas.exe`, com atalho na área de trabalho e no menu Iniciar, desinstalador e instalação sem precisar de admin (em `%LOCALAPPDATA%`), se possível.
- **Empacotamento do Python:** `torch` e `WhisperX` costumam dar problema com PyInstaller. Avalie as duas opções e documente a escolha:
  - (a) PyInstaller em modo pasta (onedir), testado de verdade, ou
  - (b) **Python embeddable oficial + pacotes pré-instalados** dentro da pasta do app, com um `.exe` lançador. Costuma ser mais confiável com torch.
- **ffmpeg:** empacotar os binários estáticos dentro do app (não depender do PATH do sistema)
- **Modelos de alinhamento do WhisperX** (wav2vec2 por idioma, centenas de MB cada): baixar **no primeiro uso**, com barra de progresso, para `%APPDATA%\Legendas\modelos\`. Opção de pré-baixar PT e ES nas configurações.
- **Build:** o instalador precisa ser gerado em Windows. Se o desenvolvimento acontecer fora do Windows, configurar **GitHub Actions com runner Windows** num repositório privado para gerar o instalador automaticamente a cada versão.
- **Versão** visível no app. Atualização automática fica para depois. Por enquanto, "nova versão = novo instalador".
- **Requisitos mínimos** a documentar: 8 GB de RAM (ideal 16), ~3 GB livres em disco, internet para a OpenAI.

## 4. Atenção aos modelos da OpenAI (verifique a documentação atual antes de codar)

- `whisper-1` é o único que devolve SRT e timestamps, mas **será descontinuado (previsto para 26/02/2027)**. **Não dependa dele.** Confira a página de deprecations da OpenAI.
- Use `gpt-4o-transcribe` (ou o mais preciso disponível no momento) para obter **o texto**, e **WhisperX local** para obter **os tempos por palavra** via alinhamento forçado (texto + áudio).
- A API de transcrição tem limite de tamanho de arquivo (~25 MB). Divida o áudio em blocos usando VAD/silêncio (sem cortar palavra no meio), com pequena sobreposição, e junte o resultado.
- Use o campo `prompt` da transcrição para passar nomes próprios e termos do glossário do projeto.
- Tradução: use o modelo de texto mais capaz e custo-efetivo disponível. O nome dos modelos fica configurável na tela de configurações (com padrões sensatos).
- Mostre o **custo estimado** de cada trabalho (minutos de áudio e tokens) antes de rodar e depois de concluir.

## 5. Módulos

Cada módulo é independente, recebe arquivos e devolve arquivos. O pipeline encadeia os módulos conforme as etapas marcadas. Manter a lógica dos módulos separada da interface (pacote `core/`), para poder testar e rodar por linha de comando também.

### 5.1 Transcrever
- **Entrada:** vídeo ou áudio (mp4, mkv, mov, mxf, wav, mp3...)
- **Processo:**
  1. ffmpeg extrai o áudio (mono, 16 kHz)
  2. divide em blocos
  3. OpenAI transcreve o texto
  4. WhisperX alinha e gera tempos por palavra
- **Saída:** palavras com tempo (JSON interno) → passa para **Formatar** → SRT no idioma original

### 5.2 Sincronizar
Dois casos, que o app detecta pela entrada:
- **(a) Texto sem tempos** (roteiro, .txt/.docx, ou SRT com tempos zerados ou absurdos): alinhamento forçado com WhisperX contra o áudio → Formatar
- **(b) SRT com tempos errados** (atraso, deriva, versão diferente do vídeo): `ffsubsync` corrige atraso e deriva usando o áudio, preservando o texto e a divisão das legendas
- **Regra crítica:** alinhamento forçado só funciona se o texto estiver **no mesmo idioma do áudio**. Se o texto for de outro idioma (ex.: espanhol para um vídeo em português):
  1. transcrever e alinhar o áudio original
  2. casar as frases traduzidas com as originais (via LLM, mapeando por ID/sentido)
  3. herdar os tempos
  4. depois Formatar

### 5.3 Traduzir
- **Entrada:** SRT (gerado pelo app ou enviado pelo cliente)
- **Processo:**
  - enviar ao LLM o **contexto do vídeo inteiro** (ou janelas grandes com sobreposição), com IDs das legendas
  - instruir: espanhol neutro latino (configurável), naturalidade de legenda (não tradução literal), respeitar o limite de caracteres e CPS do perfil, manter o glossário e as instruções do cliente
  - resposta em JSON estruturado `{id, texto}`
  - **validar:** mesma quantidade de IDs, nenhum vazio, nenhum faltando; em caso de erro, reenviar só o trecho com problema
- **Saída:** SRT traduzido, mantendo os tempos → Formatar (só quebra de linha; não alterar tempos sem necessidade)

### 5.4 Formatar (sempre roda no final)
Converte palavras com tempo (ou legendas existentes) em legendas que seguem o **perfil de regras** escolhido:
- máximo de caracteres por linha e máximo de 2 linhas
- CPS máximo (velocidade de leitura)
- duração mínima e máxima por legenda
- intervalo mínimo entre legendas
- quebra de linha por sentido: não separar artigo/preposição do substantivo, preferir quebrar após pontuação, preferir formato pirâmide quando possível
- não juntar falas de pessoas diferentes sem o hífen de diálogo do padrão
- gera um **relatório de QC** junto com o SRT: lista das legendas que violam alguma regra (ex.: CPS alto), para ela revisar primeiro

## 6. Perfis de regras (editáveis no app)

Perfil padrão inicial **"Netflix — Espanhol (LatAm)"**. **Confirme os valores no Netflix Timed Text Style Guide do idioma antes de fixar.** Valores de partida:

- 42 caracteres por linha, 2 linhas
- 17 CPS (adulto)
- duração mínima 5/6 s (~833 ms), máxima 7 s
- intervalo mínimo de 2 quadros entre legendas
- FPS do vídeo detectado automaticamente via ffprobe

Criar também o perfil "Netflix — Português (Brasil)" para transcrições em PT-BR, e permitir criar, duplicar, importar e exportar perfis por cliente.

## 7. Glossário e instruções por projeto

- Ela organiza o trabalho por **projetos/séries/clientes**. Cada projeto tem um glossário: nomes próprios, termos, gírias, e como cada um deve ser traduzido.
- Importar e exportar o glossário em CSV
- O glossário é usado no `prompt` da transcrição e nas instruções da tradução.
- Campo de "instruções do cliente" por projeto (texto livre), enviado junto com a tradução

## 8. Telas

1. **Primeira execução:** assistente que pede a chave da OpenAI, testa a chave e oferece baixar os modelos de PT e ES
2. **Projetos:** lista, criar e editar, com glossário, instruções e perfil padrão
3. **Novo trabalho:**
   - arrastar e soltar arquivos: vídeo/áudio e/ou SRT/texto
   - marcar as etapas: ☐ Transcrever ☐ Sincronizar ☐ Traduzir (Formatar é automático)
   - idioma de origem e de destino (padrões: pt-BR → es-419)
   - perfil de regras
   - pasta de saída (padrão: a mesma pasta do vídeo)
   - custo estimado antes de iniciar
4. **Validação da combinação** (ex.: "Traduzir" sem SRT nem "Transcrever" marcado → mensagem clara) e montagem do pipeline:
   - só transcrever: Transcrever → Formatar
   - só traduzir: Traduzir → Formatar
   - transcrever + traduzir: Transcrever → Traduzir → Formatar
   - traduzir + sincronizar: Sincronizar → Traduzir → Formatar (ou mapeamento da seção 5.2 se o texto já vier traduzido)
   - completo: Transcrever → Sincronizar fino → Traduzir → Formatar
5. **Fila/acompanhamento:** etapa atual, barra de progresso, log legível, botões de cancelar e de retomar
6. **Resultado:** abrir a pasta, abrir o SRT no editor padrão, ver o relatório de QC. Salvar também os SRTs intermediários (ex.: `video.pt-BR.srt` e `video.es-419.srt`).
7. **Histórico** de trabalhos com custo
8. **Configurações:** chave da API, modelos, pasta dos modelos locais, idiomas padrão, limpeza de arquivos temporários

## 9. Arquivos

- Temporários (áudio extraído, blocos, saídas de cada etapa) em `%APPDATA%\Legendas\trabalhos\<id>\`, com limpeza automática configurável (ex.: 30 dias)
- Nunca alterar nem apagar os arquivos originais dela
- SRT sempre em UTF-8, quebras de linha corretas, numeração sequencial
- Nomes de arquivo com acentos e espaços precisam funcionar (atenção aos caminhos no Windows)

## 10. Requisitos não funcionais

- Retomar trabalho que falhou a partir da etapa que falhou (guardar a saída de cada etapa)
- Retry com backoff nas chamadas da OpenAI; mensagens de erro claras em português (sem internet, chave inválida, sem crédito, arquivo corrompido)
- Funcionar em PC comum, sem GPU (se houver GPU NVIDIA, usar no alinhamento é um bônus, não requisito)
- Log técnico em arquivo, para eu conseguir diagnosticar problemas

## 11. Testes

- Testes unitários do módulo Formatar (regras de CPS, quebra de linha, duração), porque é o coração da qualidade
- Validador de SRT (ordem dos tempos, sobreposição, numeração)
- Teste de ponta a ponta com um vídeo curto de exemplo
- Testar o instalador numa máquina Windows limpa (ou VM), sem Python instalado

## 12. Documentação e repositório

- Repositório git **privado**
- Pasta `brain/` com toda a documentação (vault Obsidian): arquitetura, decisões, como rodar em desenvolvimento, como gerar o instalador e como replicar. Leia e atualize sempre que mudar algo.

## 13. Fases de entrega

1. **Fase 1:** estrutura do projeto, `brain/`, pacote `core/` com **Transcrever + Formatar** rodando por linha de comando (`python -m core.pipeline --input video.mp4 --steps transcribe`). Validar com um vídeo real dela.
2. **Fase 2:** módulo **Traduzir** + glossário (linha de comando)
3. **Fase 3:** módulo **Sincronizar** (casos a e b, e o mapeamento entre idiomas)
4. **Fase 4:** interface PySide6 completa (todas as telas da seção 8)
5. **Fase 5:** empacotamento + instalador Inno Setup + build no GitHub Actions (runner Windows) + teste em máquina limpa
6. **Fase 6:** refinamentos a partir do uso real dela (prompts, regras, relatório de QC)

Ao final de cada fase: atualizar `brain/`, fazer commit e me mostrar como testar.
