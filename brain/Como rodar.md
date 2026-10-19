# Como rodar (desenvolvimento)

## Preparar (Windows, uma vez)
1. Python 3.12 (python.org) e ffmpeg no PATH (`winget install Gyan.FFmpeg`).
2. Na pasta do projeto:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```
3. Alinhamento preciso (recomendado):
   ```
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements-align.txt
   ```
   O modelo do idioma (~1,2 GB) baixa no primeiro uso para `%APPDATA%\Legendas\modelos`.
4. Chave da OpenAI só nesta janela do terminal: `set OPENAI_API_KEY=sk-...`

## Abrir a interface
```
python -m app
```
Ou dois cliques em `Abrir Legendas.bat` (usa o `.venv` se existir). A página abre no navegador; o programa fica rodando em segundo plano até "Fechar o programa" em Configurações. Opções: `--port 8765`, `--no-browser`.

## Usar pela linha de comando
```
python -m core.pipeline -i "C:\Videos\Episódio 01.mp4" --steps transcrever --estimate
python -m core.pipeline -i "C:\Videos\Episódio 01.mp4" --steps transcrever
python -m core.pipeline -i video.mp4 -s transcrever -g glossario.csv --context "Série sobre um sítio no interior"
```
Opções: `--src-lang pt-BR` (padrão), `--profile netflix-pt-br`, `--out pasta`, `--align auto|model|estimate`, `-v`.

Interrompeu (Ctrl+C, queda de internet)? Rode o mesmo comando: ele retoma.

## Testes
```
python -m pytest -q
```
- Testes unitários + ponta a ponta com a API simulada e vídeo gerado pelo ffmpeg.
- `tests/test_app_server.py`: API da interface (token, projetos, perfis, fila, resultado, envio de arquivo).
- `tests/test_align_real.py` usa o modelo de verdade; roda no GitHub Actions (job "Alinhamento real") com fala sintetizada pela voz do Windows.

## GitHub Actions
`.github/workflows/testes.yml`: todos os testes em Windows a cada push, mais o teste de alinhamento real.
