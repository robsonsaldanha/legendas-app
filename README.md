# CNT Legendas

Programa para Windows de legendagem profissional: traduz (pela IA ou pelo ChatGPT da própria pessoa), transcreve no computador (Whisper), sincroniza pela fala, confere as regras de cada cliente e entrega `.srt` no padrão Netflix. Os vídeos e as legendas nunca saem do computador.

**Estado (out/2026):** versão 2.13 — janela própria (WebView2) com ícone na bandeja do sistema, licença (1 dia de avaliação, modo grátis, ativação por código), atualização automática pelos canais desenvolvimento/produção, perfil do usuário guardado no servidor (restaurar em PC novo, exportar/importar arquivo), Workspace da empresa (perfis e clientes compartilhados) e métricas de produção na área do cliente.

**Para instalar:** baixe o `Instalador_CNT_Legendas_<versão>.exe` em [Releases](../../releases) (ou pelo site) e dê dois cliques. Ele traz tudo (Python, bibliotecas, ffmpeg, modelos); depois o programa se atualiza sozinho.

O servidor (licenças, atualizações, site, área do cliente, status) fica no repositório privado `cnt-legendas-server`.

Documentação em [`brain/`](brain/00%20-%20Início.md) (abre como vault no Obsidian):
- [Como rodar](brain/Como%20rodar.md) · [Arquitetura](brain/Arquitetura.md) · [Fases](brain/Fases.md) · [Decisões](brain/Decisões.md)
- [Licenciamento](brain/Licenciamento.md) — licença, planos, atualização automática, servidor, perfis sincronizados
- [Design](brain/Design.md) · [Regras de legendagem](brain/Regras%20de%20legendagem.md)

Uso rápido (desenvolvimento):
```
python -m app                                   # abre o programa (janela própria no Windows; navegador nos outros)
python -m core.pipeline -i "Episódio 01.mp4" --steps transcrever   # linha de comando
python -m pytest -q                             # testes
```
