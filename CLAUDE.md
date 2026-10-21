# Instruções para quem desenvolve este projeto

- Leia `brain/00 - Início.md` e os arquivos ligados antes de mudar qualquer coisa. Atualize `brain/` (principalmente `Decisões.md` e `Fases.md`) a cada mudança relevante.
- Siga as fases de `brain/Fases.md`; a especificação completa está em `brain/Especificação.md`.
- O núcleo fica em `core/` e não depende da interface. Toda lógica nova entra com testes em `tests/`.
- Mensagens para a usuária são em português, claras e sem jargão.
- Nunca altere nem apague os arquivos originais da usuária; saídas vão ao lado do vídeo ou na pasta escolhida.
- Antes de commitar: `python -m pytest -q`. O GitHub Actions roda os testes em Windows.
- Modelos e preços da OpenAI mudam: confira a documentação atual antes de trocar padrões em `core/config.py`.
