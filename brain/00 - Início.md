# CNT Legendas — cérebro do projeto

Vault Obsidian com toda a documentação. **Quem for desenvolver (pessoa ou IA) lê isto primeiro e atualiza ao mudar algo.**

## O que é
Programa Windows com instalador para legendagem profissional (a usuária traduz PT-BR ↔ espanhol e outros idiomas, padrão Netflix). Gera `.srt`. Tudo roda no PC: transcrição local (Whisper), tradução pela API escolhida ou pelo ChatGPT dela. Um servidor na VPS cuida só de licenças, atualizações, site/área do cliente e (2.13) do perfil sincronizado.

## Mapa
- [[Arquitetura]] — módulos, fluxo de dados, pastas
- [[Decisões]] — escolhas técnicas e por quê (registro por data)
- [[Fases]] — o que está pronto e o que vem
- [[Licenciamento]] — licença, planos, atualização automática, servidor, perfis sincronizados
- [[Design]] — design system da interface simplificada
- [[Regras de legendagem]] — perfis, valores Netflix, como o Formatar decide
- [[Como rodar]] — desenvolvimento, linha de comando, testes, CI
- [[Especificação]] — documento original de requisitos

## Estado atual
**Versão 2.12.** Janela própria (WebView2) com ícone na bandeja (Exibir, Reabrir último, Novo projeto, Atualizar, Reiniciar, Sair); licença com 1 dia de avaliação e modo grátis; atualização automática obrigatória ao abrir e aviso com o programa aberto (salva antes e reabre onde estava). Trabalhos organizados em pastas por mês; Início com o mês, projetos com trilha de passos por episódio; editor no layout do Subtitle Edit (traduzir, sincronizar pela fala, verificar, entregar).

Servidor 1.1 (repositório `cnt-legendas-server`): planos Individual/Teamwork/Business-Enterprise, compra com conta do cliente, área do cliente (`/login`), Workspace da empresa, ganhos, `/status`, termos e privacidade (LGPD).

**Em andamento: 2.13** — perfil do usuário no servidor (uma por key), restauração em PC novo, exportar/importar arquivo, Workspace da empresa aplicado no programa, métricas de produção no servidor. Ver [[Licenciamento]] e [[Fases]].
