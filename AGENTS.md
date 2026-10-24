# Para qualquer IA ou pessoa que for desenvolver

As regras completas estão em [`CLAUDE.md`](CLAUDE.md) e valem para todos. O essencial:

1. **Leia o `brain/` antes de mexer em qualquer coisa**: `brain/00 - Início.md` → `brain/Tarefas.md` (kanban) → `brain/Pendências.md` (especificações) → `brain/Arquitetura.md` e `brain/Decisões.md`.
2. Pegue uma tarefa em `Tarefas.md`, coloque em **Fazendo** com o seu nome, siga a especificação em `Pendências.md`.
3. Toda lógica nova com testes em `tests/`; antes de commitar: `python -m pytest -q`.
4. Ao terminar: marque a tarefa, registre a decisão em `Decisões.md`, atualize o `brain/`.
5. Textos para o cliente em português do Brasil, claros. Sem citar marcas de terceiros.
6. Nunca alterar nem apagar arquivos originais da usuária. Vídeos e legendas não saem do computador sem o cliente escolher.
7. Ramo `dev` = homologação (dev-legendas). Produção só com aprovação do Róbson.
