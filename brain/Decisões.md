# Decisões

## 2026-10-19 — Modelo de transcrição: `gpt-transcribe`
- A OpenAI lançou `gpt-transcribe` em jul/2026, recomendado no lugar de whisper-1 e gpt-4o-transcribe. US$ 0,0045/min.
- Aceita `keywords` (termos esperados — usamos o glossário) e `languages`. No SDK Python vão em `extra_body`.
- **Não devolve timestamps** (só whisper-1, que será descontinuado em 26/02/2027). Por isso os tempos vêm do alinhamento local.
- Formatos aceitos: mp3, mp4, mpeg, mpga, m4a, wav, webm (FLAC não). Enviamos WAV de blocos curtos.
- Modelo e preço são configuráveis em `Settings`.

## 2026-10-19 — Blocos curtos (~30 s) em vez de arquivos grandes
- Fica muito abaixo do limite de 25 MB, permite paralelismo, e dá um intervalo de tempo conhecido para cada trecho de texto — o alinhamento só precisa resolver dentro do bloco.
- Cortes sempre em pausas (`silencedetect`); fala contínua longa é cortada no ponto de menor energia.
- Trechos sem fala não são enviados.
- Contrapartida: cada bloco é transcrito sem ver o anterior. O `prompt` leva o contexto do projeto e `keywords` o glossário. Se a qualidade sofrer nas emendas, avaliar blocos maiores ou passar o fim do bloco anterior no prompt (perde paralelismo).

## 2026-10-19 — Alinhamento próprio em vez do pacote WhisperX
- O WhisperX instala faster-whisper, ctranslate2, pyannote etc., que não usamos (a transcrição é da OpenAI). Isso aumentaria muito o instalador.
- Usamos **os mesmos modelos wav2vec2** que o WhisperX usa para alinhar (`jonatasgrosman/wav2vec2-large-xlsr-53-portuguese` / `-spanish`, `facebook/wav2vec2-base-960h`) via `transformers`, e o mesmo algoritmo (Viterbi CTC), implementado em numpy em `align.py`.
- Dependências do alinhamento: só `torch` (CPU) + `transformers`.
- Sem modelo disponível, o app **não para**: estima os tempos pelos trechos com fala e marca no QC.

## 2026-10-19 — Formatar por programação dinâmica
- Algoritmo guloso ("enche a legenda até não caber") gera cortes ruins. A DP escolhe a sequência de cortes de menor custo total. Pesos no topo de `formatter.py` e `linebreak.py`, para ajustar com o uso real.

## 2026-10-19 — SRT em UTF-8 com BOM e CRLF
- Editores do Windows (Subtitle Edit, Aegisub, Bloco de Notas) reconhecem melhor. Leitura aceita UTF-8, UTF-16 e cp1252.

## 2026-10-19 — Chave da OpenAI no Gerenciador de Credenciais
- `keyring` no Windows usa o Credential Manager. Para desenvolvimento, a variável `OPENAI_API_KEY` tem prioridade.

## 2026-10-19 — Interface no navegador (servidor local)
- Pedido da usuária: "página no navegador". Substitui a PySide6 da especificação.
- Servidor com a biblioteca padrão do Python (`http.server`), sem FastAPI/Flask: menos dependências para empacotar.
- Segurança: escuta só em 127.0.0.1; token aleatório por sessão exigido em toda a API (outras páginas abertas no navegador não conseguem chamar); `Host` precisa ser localhost (contra DNS rebinding); CSP só permite scripts do próprio servidor.
- O navegador não revela caminhos de arquivos, então "Escolher" abre a janela nativa do Windows (tkinter) num subprocesso; arrastar e soltar envia uma cópia.
- Progresso por consulta periódica (1 s), simples e robusto.
- Página sem CDN nem fontes externas: Segoe UI do Windows, funciona offline.

## 2026-10-19 — Aviso de tempo estimado agregado
- Quando mais da metade das legendas tem tempo estimado, o QC não marca cada uma (poluía a revisão); vira um aviso geral no relatório e na tela.

## 2026-10-19 — Dois perfis do Windows
- O PC é o mesmo, com perfis diferentes (Róbson e esposa). Dados separados por perfil; modelos compartilhados em ProgramData.
- Antes, o segundo perfil a abrir o programa poderia cair no servidor do primeiro (mesma porta) e ver os dados dele. Agora: porta por perfil, sessão em arquivo do próprio perfil, cookie + token.

## 2026-10-19 — Editor no layout do Subtitle Edit
- Pedido explícito: mesmo layout do Subtitle Edit e vídeo rodando junto, no quadro exato.
- Player HTML5 com `requestVideoFrameCallback`; formatos que o navegador não toca ganham uma cópia de pré-visualização (H.264 720p) que preserva os tempos dos quadros. A legenda continua sincronizada com o original.
- Forma de onda própria (canvas + picos do servidor) em vez de biblioteca externa: sem dependências, funciona offline.

## 2026-10-20 — Instalador: Python embutido (não PyInstaller)
- Pedido: o instalador traz tudo; a usuária não instala Python nem nada.
- Escolha: Python 3.12 embeddable oficial + bibliotecas instaladas em `python\Lib\site-packages`. Com torch é mais previsível que PyInstaller (sem "hooks", sem detecção de importações), e o código continua igual ao de desenvolvimento.
- O embeddable não traz tkinter: o `_tkinter.pyd`, as DLLs que faltam (tcl86t, tk86t, zlib1) e as pastas `tkinter` e `tcl` são copiados do Python 3.12.10 da máquina de montagem (mesma versão).
- `python312._pth`: `python312.zip`, `.`, `Lib\site-packages`, `..` (pasta do programa) e `import site`. Isso também isola do Python que porventura exista no PC.
- O atalho chama `python\pythonw.exe -m app` (sem janela preta). As janelas "Abrir/Salvar" sobem com `python.exe` sem console.
- Inno Setup, instalação por máquina (admin) para valer nos dois perfis; `ProgramData\Legendas\modelos` com permissão de escrita para Usuários; VC++ 2015–2022 instalado em silêncio se faltar (o torch precisa).
- ffmpeg: build "essentials" do gyan.dev (alternativa: BtbN).
- Tamanho: instalador ≈ 180 MB; instalado ≈ 820 MB; + ≈ 1,2 GB por idioma de alinhamento, baixados no primeiro uso.
- O GitHub Actions monta, instala em silêncio, roda `packaging/smoke_test.py` com o Python instalado (sem o Python nem o ffmpeg da máquina no PATH, alinhamento real incluído), e desinstala. Tag `v*` publica em Releases (a cota de artefatos do GitHub é pequena).
