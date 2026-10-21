# CNT Legendas

Aplicativo Windows de legendagem automática: transcreve, sincroniza e traduz, gerando arquivos `.srt` no padrão Netflix. Tudo roda no PC; só a transcrição e a tradução usam a API da OpenAI.

**Estado:** tradução de legendas (PT ↔ ES e outros), transcrição, editor no layout do Subtitle Edit (vídeo no quadro exato) e instalador completo.

**Para instalar:** baixe o `Instalador_CNT_Legendas_<versão>.exe` em [Releases](../../releases) e dê dois cliques. Ele traz tudo (Python, bibliotecas, ffmpeg); não precisa instalar mais nada.

Documentação completa em [`brain/`](brain/00%20-%20Início.md) (abre como vault no Obsidian):
- [Como rodar](brain/Como%20rodar.md)
- [Arquitetura](brain/Arquitetura.md)
- [Regras de legendagem](brain/Regras%20de%20legendagem.md)
- [Fases](brain/Fases.md)

Uso rápido:
```
python -m app                                   # abre a interface no navegador
python -m core.pipeline -i "Episódio 01.mp4" --steps transcrever   # linha de comando
```
Gera `Episódio 01.pt-BR.srt` e `Episódio 01.pt-BR.qc.txt` ao lado do vídeo.
