# CNT Legendas

> **Vai desenvolver neste projeto (pessoa ou IA)? Comece pelo [`brain/`](brain/00%20-%20Início.md).**
> Ele explica como o sistema funciona e por que cada coisa foi feita. Ordem de leitura:
> 1. [`brain/00 - Início.md`](brain/00%20-%20Início.md) — o que é e o mapa
> 2. [`brain/Tarefas.md`](brain/Tarefas.md) — o kanban: o que está feito, fazendo e a fazer
> 3. [`brain/Pendências.md`](brain/Pendências.md) — a especificação de cada tarefa (o quê, por quê, como, quando está pronta)
> 4. [`brain/Arquitetura.md`](brain/Arquitetura.md) e [`brain/Decisões.md`](brain/Decisões.md) — como o código está organizado e as escolhas feitas
>
> Ao terminar algo: marque em `Tarefas.md`, registre a decisão em `Decisões.md` e mantenha o resto do `brain/` atualizado.
> Regras do projeto: [`CLAUDE.md`](CLAUDE.md) (valem para qualquer IA; resumo em [`AGENTS.md`](AGENTS.md)).

Programa para Windows de legendagem profissional: traduz (pela IA ou pelo ChatGPT da própria pessoa), transcreve no computador (Whisper), sincroniza pela fala, confere as regras de cada cliente e entrega `.srt` no padrão Netflix. Os vídeos e as legendas nunca saem do computador.

**Estado (out/2026):** versão 2.16 — status da conexão no topo, ⚠ de atualização, códigos de erro ER-RS/ER-RA, modo de depuração e diagnóstico; da 2.15: entrega em .srt (padrão), .vtt, .ttml ou .ass; prazo de entrega por episódio; histórico de versões; memória de tradução e corretor ortográfico discretos no editor; aviso na bandeja quando um trabalho termina; "Relatar um problema"; glossário geral, do cliente e do projeto; janela própria (WebView2) com ícone na bandeja do sistema, licença (1 dia de avaliação, modo grátis, ativação por código), atualização automática pelos canais desenvolvimento/produção, perfil do usuário guardado no servidor (restaurar em PC novo, exportar/importar arquivo), Workspace da empresa (perfis e clientes compartilhados) e métricas de produção na área do cliente.

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
