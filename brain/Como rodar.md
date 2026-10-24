# Como rodar

## Para usar (sem programar)
1. Na página do repositório no GitHub, abra **Releases** e baixe o `Instalador_CNT_Legendas_<versão>.exe` mais recente.
2. Dois cliques, avançar. Ele pede permissão de administrador porque instala para todos os perfis do Windows.
3. Abra pelo atalho **CNT Legendas** (menu Iniciar ou área de trabalho). Em cada perfil: Configurações → colar a chave da OpenAI; e, uma vez só no PC, baixar os modelos de alinhamento (PT e ES).

## Gerar o instalador e publicar
`packaging\build.ps1` (Windows, Python 3.12, Inno Setup 6) gera o instalador e o pacote de atualização. Quem roda é o GitHub Actions (`instalador.yml`): ramo `dev` → canal desenvolvimento (servidor dev-legendas, pré-versão "desenvolvimento" no GitHub); ramo `main` → produção (quando `CNT_PROD_ATIVO` = 1). Commit com `[instalador]` obriga o instalador completo; `[skip ci]` não monta.

O fluxo de trabalho do Claude: edita na nuvem, roda os testes, leva os arquivos para `C:\Users\robso\OneDrive\DESENVOLVIMENTO\CNT Legendas` (ramo `dev`) e envia por `git push vps dev` (a VPS repassa ao GitHub).

# Desenvolvimento

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
   O modelo do idioma (~1,2 GB) baixa no primeiro uso para `%APPDATA%\CNT Legendas\modelos`.
4. Chave da OpenAI só nesta janela do terminal: `set OPENAI_API_KEY=sk-...`

## Abrir a interface
```
python -m app
```
Ou dois cliques em `Abrir CNT Legendas.bat` (usa o `.venv` se existir). No Windows abre a janela própria (WebView2); `CNT_NAVEGADOR=1` força o navegador. Com a bandeja ligada, o X esconde a janela; "Sair" no ícone (ou "Fechar o programa" em Configurações) encerra. Abrir de novo pelo atalho só traz a janela para a frente. Opções: `--port N` (padrão: porta própria do perfil), `--no-browser`. `CNT_SEM_ATUALIZACAO=1` desliga a atualização ao abrir; `CNT_CANAL` escolhe o servidor (desenvolvimento/producao).

A página só abre pelo atalho (ele passa a chave da sessão). Digitar o endereço direto mostra "Abra o CNT Legendas pelo atalho".

## Usar pela linha de comando
```
python -m core.pipeline -i "C:\Videos\Episódio 01.mp4" --steps transcrever --estimate
python -m core.pipeline -i "C:\Videos\Episódio 01.mp4" --steps transcrever
python -m core.pipeline -i video.mp4 -s transcrever -g glossario.csv --context "Série sobre um sítio no interior"
python -m core.pipeline -i "Episódio 01.srt" -s traduzir --dst-lang es-419      # idioma de origem detectado
python -m core.pipeline -i video.mp4 -s transcrever,traduzir --src-lang pt-BR --dst-lang es-419
```
Opções: `--src-lang pt-BR` (padrão), `--profile netflix-pt-br`, `--out pasta`, `--align auto|model|estimate`, `-v`.

Interrompeu (Ctrl+C, queda de internet)? Rode o mesmo comando: ele retoma.

## Testes
```
python -m pytest -q
```
- Testes unitários + ponta a ponta com a API simulada e vídeo gerado pelo ffmpeg.
- `tests/test_app_server.py`: API da interface (sessão/cookie, projetos, perfis, fila, resultado, envio de arquivo).
- `tests/test_glossario_niveis.py`: glossário geral/cliente/projeto (prioridade, API, tradução pelo episódio, perfil).
- `tests/test_formatos.py`: formatos de entrega (conversões, prioridade projeto > cliente > equipe > global, entrega) e prazos.
- `tests/test_versoes_memoria.py`: histórico de versões, memória de tradução e corretor ortográfico (precisa do `pyspellchecker`).
- `tests/test_plataforma.py`: pastas e comandos por sistema, atualização `manual` fora do Windows.
- Mac/Linux: `bash packaging/build_unix.sh linux|mac` monta o pacote (o CI faz isso depois do instalador do Windows).
- `tests/test_conexao_erros_depuracao.py`: horários dos pings e estados da conexão, códigos de erro, depuração (arquivos por ação, zip, recuperação após queda, API).
- `tests/test_suporte.py`: "Relatar um problema" (registro sem segredos, envio com servidor simulado).
- `tests/test_perfil.py`: perfil na nuvem (montar/aplicar, arquivo, perfis da empresa, clientes compartilhados entre dois computadores, sincronizador) com um servidor simulado.
- `tests/test_editor.py`: editor (vídeo com Range, cópia de pré-visualização de MKV, forma de onda, rascunho, salvar com cópia de segurança, QC).
- `tests/test_align_real.py` usa o modelo de verdade; roda no GitHub Actions (job "Alinhamento real") com fala sintetizada pela voz do Windows.

## GitHub Actions
`.github/workflows/testes.yml`: todos os testes em Windows a cada push, mais o teste de alinhamento real.
