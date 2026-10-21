# CNT Legendas — cérebro do projeto

Vault Obsidian com toda a documentação. **Quem for desenvolver (pessoa ou IA) lê isto primeiro e atualiza ao mudar algo.**

## O que é
Aplicativo Windows com instalador para legendagem profissional (PT-BR → espanhol neutro, padrão Netflix). Gera arquivos `.srt`. Tudo roda no PC; só a transcrição e a tradução usam a API da OpenAI.

## Mapa
- [[Arquitetura]] — módulos, fluxo de dados, pastas
- [[Decisões]] — escolhas técnicas e por quê
- [[Regras de legendagem]] — perfis, valores Netflix, como o Formatar decide
- [[Como rodar]] — ambiente de desenvolvimento, linha de comando, testes
- [[Fases]] — o que está pronto e o que vem
- [[Especificação]] — documento original de requisitos

## Estado atual
**Versão 2.0 — CNT Legendas.** Tudo começa pelos **Projetos** (Início: Novo, Abrir, Continuar e a lista; cada filme/série numa pasta, com temporadas e episódios; métricas e relatórios) e acontece no **editor**: Traduzir (um clique, pelo ChatGPT dela ou pela API), **Sincronizar** (automática pela fala, por legenda de referência, copiar tempos, deslocar, dois pontos, quadros por segundo, cortes de cena, texto sem tempo), **Verificar** (com correção automática) e **Entregar** (nome do cliente, assinatura, verificação final). **Clientes** reúnem regras, glossário e instruções (perfis com manual de cliente são importados de arquivo, fora do código). Funciona em dois perfis do Windows no mesmo PC. Próximo: uso real dela e ajustes (ver [[Fases]]).
