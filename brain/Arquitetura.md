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
| `dialogs.py` | Janela "Abrir" do Windows (tkinter) num processo separado, para obter o caminho real do arquivo |
| `static/` | `index.html`, `app.css`, `app.js` — página única, sem dependências externas (funciona offline) |

Telas: Novo trabalho (arquivos, etapas, projeto, perfil, idiomas, pasta de saída, custo estimado) · Trabalhos (fila + histórico) · Trabalho (progresso ao vivo; no fim, revisão com a prévia da legenda "na tela" e os apontamentos do QC) · Projetos (glossário com importar/exportar CSV, instruções do cliente) · Configurações (chave, modelos de alinhamento, perfis, avançado, fechar o programa).

Arquivos arrastados para a página são copiados para `%APPDATA%\Legendas\envios` (o navegador não informa o caminho original); nesse caso a saída vai para `Documentos\Legendas`. Pelo botão "Escolher", o caminho real é usado e a saída fica ao lado do vídeo.

## Pastas de dados (Windows)

```
%APPDATA%\Legendas\
  config.json
  legendas.db                projetos, glossários, perfis, histórico
  envios\                    arquivos arrastados para a página
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
