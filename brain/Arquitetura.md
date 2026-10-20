# Arquitetura

## Visão geral

```
vídeo/áudio ──ffmpeg──▶ audio.wav (16 kHz mono)
                │
                ├─silencedetect─▶ blocos de ~30 s cortados nas pausas (chunking.py)
                │                      │
                │                      ▼
                │            OpenAI gpt-transcribe (paralelo, cache por bloco)
                │                      │  texto de cada bloco = "segmento" com início/fim
                ▼                      ▼
        alinhamento forçado wav2vec2 (align.py) ─▶ palavras com tempo
                                       │
                                       ▼
                Formatar (formatter.py + linebreak.py) ─▶ legendas
                                       │
                                       ├─▶ <vídeo>.pt-BR.srt
                                       └─▶ <vídeo>.pt-BR.qc.txt (qc.py)
```

## Pacote `core/` (sem interface)

| Módulo | Papel |
|---|---|
| `subtitle.py` | `Word`, `Cue`, leitura tolerante e escrita de SRT (UTF-8 com BOM, CRLF) |
| `profiles.py` | Perfis de regras (Netflix ES/PT, adulto e infantil); salvar/carregar JSON |
| `lang.py` | Palavras fracas, inícios de oração, complementos presos (pt/es/en) |
| `linebreak.py` | Quebra do texto de uma legenda em linhas (custo mínimo) |
| `formatter.py` | Segmentação em legendas por programação dinâmica + ajuste de tempos; `reflow_cues` para SRT existente |
| `qc.py` | Validação estrutural e relatório de QC em português |
| `media.py` | ffmpeg/ffprobe (procura `bin/` do app antes do PATH), extração, silêncios |
| `chunking.py` | Planejamento dos blocos de áudio |
| `transcribe.py` | Cliente de transcrição (OpenAI) + execução paralela com cache e cancelamento |
| `align.py` | Alinhamento CTC (Viterbi em numpy) com wav2vec2; fallback de tempos estimados |
| `openai_client.py` | Chave (variável ou Gerenciador de Credenciais), retry com backoff, erros em português |
| `glossary.py` | Glossário CSV → `keywords` da transcrição (e, na Fase 2, instruções de tradução) |
| `plan.py` | Valida a combinação de etapas × arquivos e monta a ordem do pipeline |
| `jobs.py` | Pasta de trabalho com a saída de cada etapa (retomada) |
| `pipeline.py` | `run_job()` para a interface; `main()` para a linha de comando |
| `config.py` | Pastas em `%APPDATA%\Legendas` e `Settings` (modelos, preços, paralelismo) |

## Interface (`app/`)

O programa é um servidor local (só `127.0.0.1`) e a tela abre no navegador padrão. Decisão da usuária: página no navegador em vez de janela PySide6 (ver [[Decisões]]).

| Arquivo | Papel |
|---|---|
| `__main__.py` | `python -m app`: sobe o servidor na porta 8765 (ou outra livre), abre o navegador, limpa temporários antigos. Se já estiver aberto, só abre a página. `--dialog` é o modo auxiliar das janelas de arquivo |
| `server.py` | HTTP + API JSON (biblioteca padrão, sem framework). Token por sessão no cabeçalho `X-Token`, checagem do `Host`, CSP |
| `worker.py` | Fila: um trabalho por vez numa thread; progresso e registro em memória para a tela |
| `db.py` | SQLite `legendas.db`: projetos, glossários, perfis próprios, histórico |
| `dialogs.py` | Janelas "Abrir" e "Salvar como" do Windows (tkinter) num processo separado, para obter o caminho real do arquivo |
| `editor.py` | Sessões do editor: lê o SRT, prepara o vídeo para o player (cópia leve quando o navegador não toca o formato), forma de onda, rascunho, salvar com cópia de segurança, QC, quebra de linhas |
| `static/` | `index.html`, `app.css`, `app.js` (telas gerais), `editor.js` (editor) — sem dependências externas (funciona offline) |

Telas: Novo trabalho (arquivos, etapas, projeto, perfil, idiomas, pasta de saída, custo estimado) · Trabalhos (fila + histórico) · Trabalho (progresso ao vivo; no fim, revisão com a prévia da legenda "na tela" e os apontamentos do QC) · Projetos (glossário com importar/exportar CSV, instruções do cliente) · Configurações (chave, modelos de alinhamento, perfis, avançado, fechar o programa).

## Editor (layout do Subtitle Edit)

Pedido da usuária: mesmo layout do Subtitle Edit, com o vídeo rodando junto e quadro exato.

```
┌ barra: Voltar · arquivo · Abrir · Salvar · Salvar como · Desfazer · Refazer · Perfil · Formato · Codificação
├ grade de legendas (#, Início, Fim, Duração, CPS, Texto)   │ vídeo com a legenda sobreposta
├ Início/Duração · Texto (CPS, tamanho das linhas) · ações  │ barra de posição, ⏮ ▶ ■ ⏭, velocidade, volume, timecode HH:MM:SS:QQ
├ Criar / Ajustar (inserir, marcar início/fim, saltos)      │ forma de onda com as legendas (arrastar bordas/mover), zoom, rolagem
└ status: n/total · problemas (clique = próximo) · perfil · salvo/não salvo
```

- **Quadro exato**: o tempo exibido vem de `requestVideoFrameCallback` (tempo do quadro realmente mostrado). Avançar/voltar quadro posiciona no meio do quadro para o navegador mostrar exatamente ele; "Marcar início/fim" e arrastar na onda encaixam no início do quadro (Alt desliga o encaixe).
- **Vídeo**: MP4/MOV/WebM com H.264/VP9/AV1 tocam direto. Outros (MKV, MXF, ProRes, HEVC, 10 bits) geram `previa.mp4` em `%APPDATA%\Legendas\editor\<hash>\` (720p, mesmos tempos de quadro: `-fps_mode passthrough`), feita uma vez por arquivo.
- **Forma de onda**: 100 picos por segundo (1 byte cada) calculados no servidor, desenhados em canvas.
- **Rascunho**: a cada 2 s a cópia de trabalho vai para o servidor; recarregar a página não perde nada enquanto o programa estiver aberto.
- **Salvar**: antes de sobrescrever um .srt pela primeira vez na sessão, uma cópia do original vai para `%APPDATA%\Legendas\editor\copias\`.
- **Atalhos**: Espaço tocar/pausar · ←/→ quadro · Shift+←/→ 1 s · Alt+↑/↓ legenda anterior/próxima · F11 ou `[` início · F12 ou `]` fim · Insert nova · Delete apagar (na grade) · Ctrl+S salvar · Ctrl+Z/Y desfazer/refazer · F8 próximo problema · Ctrl+roda zoom na onda. (O navegador pode tomar F11 para tela cheia; por isso `[` e `]`.)

Arquivos arrastados para a página são copiados para `%APPDATA%\Legendas\envios` (o navegador não informa o caminho original); nesse caso a saída vai para `Documentos\Legendas`. Pelo botão "Escolher", o caminho real é usado e a saída fica ao lado do vídeo.

## Dois perfis do Windows no mesmo PC

- Cada perfil tem os seus dados (`%APPDATA%\Legendas`: chave, projetos, histórico, configurações) e o seu servidor.
- Porta fixa por perfil (`preferred_port()`, derivada do usuário), para dois perfis logados ao mesmo tempo não disputarem a mesma.
- Sessão: o servidor grava `%APPDATA%\Legendas\sessao.json` (porta + token). O atalho lê esse arquivo (só o próprio perfil consegue) e abre `/open?k=token`, que grava um cookie `HttpOnly; SameSite=Strict` e redireciona. A página e a API exigem esse cookie; a API exige também o cabeçalho `X-Token`. Assim um perfil não abre o programa do outro.
- Modelos de alinhamento (≈1,2 GB por idioma) ficam em `C:\ProgramData\Legendas\modelos`, compartilhados. Se não der para escrever lá, cada perfil usa o seu. O instalador (Fase 5) cria a pasta com permissão de escrita para todos os usuários.

## Pastas de dados (Windows)

```
%APPDATA%\Legendas\
  config.json
  legendas.db                projetos, glossários, perfis, histórico
  envios\                    arquivos arrastados para a página
  sessao.json                porta e token da sessão aberta
  editor\<hash>\             cópia de pré-visualização e forma de onda de cada vídeo
  editor\copias\             cópias de segurança dos .srt antes de sobrescrever
  logs\legendas.log          log técnico geral
  modelos\                   modelos wav2vec2 (baixados no 1º uso)
  trabalhos\<id>\            um por trabalho
    trabalho.json            etapas concluídas, parâmetros
    audio.wav, midia.json, blocos.json
    blocos\bloco_00000.json  texto de cada bloco (cache da API)
    segmentos.json, palavras.json, qc.json, log.txt
```

O `<id>` vem do arquivo (caminho, tamanho, data) + parâmetros. Rodar de novo o mesmo trabalho retoma de onde parou e **não paga a API de novo** pelos blocos já transcritos.

## Saídas
Ao lado do vídeo (ou em `--out`): `Nome.pt-BR.srt` e `Nome.pt-BR.qc.txt`. Os originais da usuária nunca são alterados.
