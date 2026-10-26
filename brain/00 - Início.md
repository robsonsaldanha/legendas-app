# CNT Legendas — cérebro do projeto

Vault Obsidian com toda a documentação. **Quem for desenvolver (pessoa ou IA) lê isto primeiro e atualiza ao mudar algo.**

## O que é
Programa Windows com instalador para legendagem profissional (a usuária traduz PT-BR ↔ espanhol e outros idiomas, padrão Netflix). Gera `.srt`. Tudo roda no PC: transcrição local (Whisper), tradução pela API escolhida ou pelo ChatGPT dela. Um servidor na VPS cuida só de licenças, atualizações, site/área do cliente e (2.13) do perfil sincronizado.

## Mapa
- [[Tarefas]] — **o kanban**: feito / fazendo / a fazer (comece por aqui para saber o que fazer)
- [[Pendências]] — especificação de cada tarefa (família CNT: hub, Legendas, Dubla, API; e o que já estava pendente)
- [[Arquitetura]] — módulos, fluxo de dados, pastas
- [[Decisões]] — escolhas técnicas e por quê (registro por data)
- [[Fases]] — o que está pronto e o que vem
- [[Licenciamento]] — licença, planos, atualização automática, servidor, perfis sincronizados
- [[Design]] — design system da interface simplificada
- [[Regras de legendagem]] — perfis, valores Netflix, como o Formatar decide
- [[Como rodar]] — desenvolvimento, linha de comando, testes, CI
- [[Especificação]] — documento original de requisitos
- [[Fluxo de localização]] — como empresas grandes legendam e dublam um filme (base do P-16 e da nova Dubla)

## Estado atual
**Versão 2.17.** Também para Mac (Apple Silicon) e Linux, abrindo no navegador padrão. Da 2.16: Status da conexão no canto superior direito (servidor e Google em horários alternados; detalhe ao passar o mouse), ⚠ de atualização no lugar da janela, códigos de erro ER-RS/ER-RA e modo de depuração e diagnóstico (5 min, zip em Documentos). Da 2.15: Entrega em .srt (padrão), .vtt, .ttml ou .ass (global, equipe, cliente ou projeto); prazo de entrega por episódio (a próxima aparece no topo); histórico de versões no editor; memória de tradução e corretor ortográfico numa linha discreta abaixo do texto; aviso na bandeja quando um trabalho termina; "Relatar um problema". Glossário em três níveis (geral, cliente, projeto). Janela própria (WebView2) com ícone na bandeja (Exibir, Reabrir último, Novo projeto, Atualizar, Reiniciar, Sair); licença com 1 dia de avaliação e modo grátis; atualização automática obrigatória ao abrir e aviso com o programa aberto (salva antes e reabre onde estava); **perfil na nuvem** (configurações, clientes com glossários e perfis de regras guardados no servidor, um por computador ativado; restaurar num PC novo; exportar/importar arquivo), **Workspace da empresa** no programa (perfis "Empresa: …", clientes compartilhados) e **métricas de produção** enviadas ao servidor. Trabalhos em pastas por mês; editor no layout clássico de editor de legendas (traduzir, sincronizar pela fala, verificar, entregar).

Servidor 1.2 (repositório `cnt-legendas-server`): planos Individual/Teamwork/Business-Enterprise, compra com conta do cliente, área do cliente (`/login`: licenças, produção, pedidos, dados, privacidade), Workspace da empresa, ganhos, `/status`, termos e privacidade (LGPD), API `/v1/sync`.

Próximos passos: ver [[Fases]] (ligar a produção quando o Róbson aprovar; calibrar com o uso real).
