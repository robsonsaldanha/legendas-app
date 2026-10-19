# Fases

## ✅ Fase 1 — Transcrever + Formatar (linha de comando)
- [x] Estrutura, `brain/`, testes, CI em Windows
- [x] Extração de áudio, blocos nas pausas, transcrição paralela com cache
- [x] Alinhamento forçado (wav2vec2) com fallback estimado
- [x] Formatar (DP), quebra de linhas, ajuste de tempos, perfis Netflix
- [x] Relatório de QC, validador de SRT
- [x] Retomada, cancelamento, estimativa de custo, erros em português
- [ ] **Validar com um vídeo real dela** ← próximo passo

## Fase 2 — Traduzir + glossário
SRT → SRT traduzido (es-419), contexto do vídeo inteiro, JSON por ID com validação, glossário e instruções do cliente; `reflow_cues` já pronto para refazer as linhas.

## Fase 3 — Sincronizar
(a) texto sem tempo → alinhamento; (b) SRT desalinhado → ffsubsync; (c) texto em outro idioma → transcrever, alinhar e casar frases via LLM.

## Fase 4 — Interface PySide6
Telas da especificação, seção 8.

## Fase 5 — Instalador
Empacotamento, ffmpeg em `bin/`, Inno Setup, build no GitHub Actions, teste em Windows limpo.

## Fase 6 — Refinamentos com uso real
