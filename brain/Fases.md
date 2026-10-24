# Fases

> Histórico por versão. **O que falta fazer agora fica em [[Tarefas]]** (kanban) e a explicação de cada item em [[Pendências]].

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

## ✅ Editor (layout clássico de editor de legendas) + dois perfis do Windows
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

## ✅ Perfis de cliente
- [x] Perfis de cliente (ES e PT) com CPS ideal, intervalo em ms, `-Texto`, `...`, `_sub_spa`/`_sub_pt` — desde a 2.4.0 importados de arquivo, fora do código
- [x] Manual do cliente enviado na tradução; QC com as regras de estilo do manual
- [x] Tela de perfis: CPS ideal, intervalo em ms, hífen, reticências, manual do cliente
- [ ] Confirmar com o cliente as regras do perfil em português

## ✅ Fase 3 — Sincronizar (versão 1.0)
- [x] Automática pela fala do vídeo (deslocamento, proporção de quadros, trechos), sem custo
- [x] Pela legenda de referência (qualquer idioma) e copiando os tempos (mesma quantidade)
- [x] Atrasar/adiantar (tudo ou a partir da legenda), dois pontos, converter quadros por segundo
- [x] Cortes de cena: detectar, mostrar na forma de onda e encaixar (regras Netflix)
- [x] Texto sem tempo (.txt/.docx/.srt sem tempos) → legenda sincronizada (transcrição + casamento do texto)
- [x] Também no trabalho em segundo plano e na linha de comando (`--steps sincronizar`)
- [ ] Validar com material real dela (filme com intervalo, legenda de outra versão)

## ✅ Versão 1.0 — CNT Legendas, fluxo simples
- [x] Nome novo com migração (dados, chave, modelos, instalador por cima da versão antiga)
- [x] Início: abrir legenda + vídeo (acha a legenda do vídeo), cliente, recentes
- [x] Clientes no lugar de projetos (Netflix pronto; clientes com manual próprio por arquivo)
- [x] Editor: Traduzir com um clique, menu Sincronizar, Verificar (com correção automática), Entregar (nome, assinatura, verificação), Localizar e substituir (Ctrl+F)
- [ ] Confirmar com ela: assinatura (texto e posição), atalhos que ela sente falta

## ✅ Fase 5 — Instalador (adiantada)
- [x] Python embutido + bibliotecas + tkinter + ffmpeg + VC++ — nada para instalar à parte
- [x] Inno Setup para todos os perfis, atalhos, pasta de modelos compartilhada, desinstalação limpa
- [x] GitHub Actions: monta, instala, testa o programa instalado, desinstala; publica nas tags
- [ ] Instalar no PC deles e testar nos dois perfis

## ✅ Versão 2.0 — projetos, métricas e visual CNT
- [x] Logo e ícone CNT; tema escuro/claro; menu de ferramentas recolhível
- [x] Primeira abertura pergunta a pasta dos projetos
- [x] Tela inicial: Novo, Abrir, Continuar + lista de projetos (filtros por status e busca)
- [x] Novo projeto: filme ou série, nome validado (Windows), temporada/episódios em qualquer ordem, arquivos copiados para a pasta
- [x] Projeto: status (novo/em andamento/finalizado, reabrir), episódios, títulos, arquivos, abrir no editor
- [x] Métricas guardadas com data; tempo trabalhado; relatórios geral, do projeto e do episódio; exportar CSV
- [ ] Usar com projetos reais dela e ajustar o relatório

## Fase 6 — Refinamentos com uso real
- [x] 2.3.2: GhostCLI por IPv4, erro real do serviço e IP de saída no "Testar"
- [x] 2.4.0: manuais de clientes fora do código (importar/exportar perfis); repositório público
- [x] 2.5.0: sincronia pela voz (Silero VAD + acerto de início/fim), áreas do editor fixas e arrastáveis, `<br />`, {\an8}, configurações do editor, revisão no mesmo idioma, origem nunca alterada
- [x] 2.6.0: sincronia precisa pela fala (separação da voz na placa de vídeo, início/fim pela fala sem esticar pelo CPS, corte entre palavras pela transcrição local)
- [x] 2.6.2: sincronia precisa ajustada com o episódio inteiro do PC dela
- [x] 2.7.0: transcrição de vídeo sem legenda no computador (Whisper large-v3, sem custo; OpenAI vira opção)
- [x] 2.8.0: 20 idiomas + detectar automaticamente; falas em outro idioma no mesmo episódio; japonês/chinês sem espaço
- [x] 2.9.0: pastas por mês (e trabalhos antigos encontrados nas pastas), interface simplificada com dicas "?" (ver Design.md)
- [x] 2.10.0: licença (1 dia de avaliação, modo grátis, ativação por código, recursos pagos) e atualização automática obrigatória pelos canais desenvolvimento/produção (ver Licenciamento.md). Precisa ser instalada uma vez pelo instalador.
- [x] 2.13.0: perfil na nuvem (um por computador ativado; restaurar em PC novo/formatado; exportar/importar arquivo), Workspace da empresa no programa (perfis "Empresa: …", clientes e glossários compartilhados), métricas de produção no servidor (área do cliente → Produção; Workspace → Produção da equipe)
- [x] 2.14.0: glossário em três níveis — geral (Configurações), cliente e projeto (menu ⋯ do projeto); o mais específico vale
- [x] 2.15.0: memória de tradução, formato de entrega (srt padrão; vtt/ttml/ass por global/equipe/cliente/projeto), prazo de entrega (topo e editor), histórico de versões, corretor ortográfico, aviso de trabalho concluído na bandeja, "Relatar um problema" (servidor 1.3, painel Suporte)
- [x] 2.16.0: status da conexão no topo (pings alinhados servidor/Google), ⚠ de atualização no lugar da janela, códigos de erro ER-RS/ER-RA, modo de depuração e diagnóstico (zip em Documentos); servidor 1.4 com modo manutenção
- [x] 2.17.0: Mac e Linux — camada por sistema, pacotes `.dmg` (Apple Silicon) e `.tar.gz`/`.AppImage` montados e testados no CI; abre no navegador padrão
- [x] 2.18.0: legenda ao vivo — menu "Ao vivo": entrada de áudio (microfone, som do computador, placa, arquivo, endereço), reconhecimento contínuo local, fila para corrigir antes de ir à tela, texto pronto, página de legenda para o programa de transmissão e janela com fundo de recorte, arquivo `.srt` do evento que abre no editor
- [x] 2.19.0: audiodescrição no editor — espaços sem fala na forma de onda, perfil e verificação de audiodescrição, ouvir com a voz do sistema, sugestão por IA a partir de quadros, exportar roteiro (.docx/.txt), .ttml, faixa e áudio mixado
- Próximos passos (família CNT, Mac/Linux, ao vivo, audiodescrição, dublagem, API e pendências antigas): ver [[Tarefas]] e [[Pendências]]
- [x] 2.11.0: janela própria (WebView2), sem abas nem barra de endereço; o X pergunta antes de fechar
- [x] 2.12.0: bandeja do sistema (menu Exibir/Reabrir último/Novo projeto/Atualizar/Reiniciar/Sair), aviso de versão nova com o programa aberto (salvar antes, reabrir onde estava); X encerra o processo de vez
