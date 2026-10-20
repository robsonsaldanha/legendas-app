# Fases

## ✅ Fase 1 — Transcrever + Formatar (linha de comando)
- [x] Estrutura, `brain/`, testes, CI em Windows
- [x] Extração de áudio, blocos nas pausas, transcrição paralela com cache
- [x] Alinhamento forçado (wav2vec2) com fallback estimado
- [x] Formatar (DP), quebra de linhas, ajuste de tempos, perfis Netflix
- [x] Relatório de QC, validador de SRT
- [x] Retomada, cancelamento, estimativa de custo, erros em português
- [ ] **Validar com um vídeo real dela** ← próximo passo

## ✅ Fase 4 (adiantada) — Interface no navegador
- [x] Servidor local seguro + fila de trabalhos + SQLite
- [x] Novo trabalho, Trabalhos, Revisão do resultado, Projetos com glossário, Configurações, perfis próprios
- [x] Etapas Traduzir/Sincronizar aparecem desativadas até as Fases 2 e 3
- [ ] Testar no Windows dela (janela "Abrir", abrir SRT no editor, Gerenciador de Credenciais)

## ✅ Editor (layout do Subtitle Edit) + dois perfis do Windows
- [x] Grade, vídeo com legenda sobreposta e quadro exato, painel de edição, forma de onda com arrastar, Criar/Ajustar, status
- [x] Desfazer/refazer, rascunho automático, salvar/salvar como com cópia de segurança, QC ao vivo, quebra automática
- [x] Cópia de pré-visualização para MKV/MXF/HEVC etc.
- [x] Sessão por perfil do Windows; modelos compartilhados
- [ ] Testar no Windows: tocar H.264 no Edge/Chrome, F11/F12, janela "Salvar como", dois perfis logados ao mesmo tempo

## ✅ Fase 2 — Traduzir (prioridade da usuária: o trabalho principal dela é traduzir legendas)
- [x] `core/translate.py`: lotes de 80 com contexto (anteriores já traduzidas + seguintes), JSON estruturado por id, validação e nova tentativa dos que faltarem, limite de caracteres por legenda (duração × CPS), regras do idioma (es-419, es-ES, pt-BR), glossário e instruções do cliente, retomada por lote
- [x] Detecção do idioma da legenda; padrão PT ↔ ES (inverte com um clique)
- [x] Novo trabalho: escolher a legenda já marca Traduzir e o sentido; botão "Traduzir para …"
- [x] Editor: botão **Traduzir…** (janela com idiomas, projeto, perfil, custo e progresso); a tradução abre no editor com a coluna **Original**
- [x] Saída ao lado da original (`Nome.es-419.srt`), nunca sobrescreve arquivo que o programa não gerou
- [x] Validada com legenda real dela (400 legendas, PT → ES): ficou boa
- [x] **Tradução pelo ChatGPT dela, sem API e sem custo** (copiar e colar): o programa divide em partes de 100, copia cada parte já com as instruções, abre o ChatGPT; ela cola, envia e cola a resposta de volta; o programa confere, pede só o que faltou e monta o .srt
- [x] Novo trabalho e editor deixam escolher "pelo meu ChatGPT" ou "pela API" (lembra a última escolha)
- [x] Prévia sobre o vídeo aplica <i>, <b>, <u>, <font color> e {\an8}; grade, texto e original mostram as tags

## ✅ Perfis de cliente — Encripta
- [x] Encripta — Español (neutro) e Encripta — Português (Brasil): 42/2, CPS 28 (ideal 15), 1,001–6,999 s, 84 ms, `-Texto`, `...`, `_sub_spa`/`_sub_pt`
- [x] Manual do cliente enviado na tradução; QC com as regras de estilo do manual
- [x] Tela de perfis: CPS ideal, intervalo em ms, hífen, reticências, manual do cliente
- [ ] Confirmar com a Encripta as regras do perfil em português

## Fase 3 — Sincronizar
(a) texto sem tempo → alinhamento; (b) SRT desalinhado → ffsubsync; (c) texto em outro idioma → transcrever, alinhar e casar frases via LLM.

## ✅ Fase 5 — Instalador (adiantada)
- [x] Python embutido + bibliotecas + tkinter + ffmpeg + VC++ — nada para instalar à parte
- [x] Inno Setup para todos os perfis, atalhos, pasta de modelos compartilhada, desinstalação limpa
- [x] GitHub Actions: monta, instala, testa o programa instalado, desinstala; publica nas tags
- [ ] Instalar no PC deles e testar nos dois perfis

## Fase 6 — Refinamentos com uso real
