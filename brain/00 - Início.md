# Legendas — cérebro do projeto

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
**Fase 1 concluída** (Transcrever + Formatar), **interface no navegador** (`python -m app`) e **editor no layout do Subtitle Edit** com vídeo no quadro exato. Funciona em dois perfis do Windows no mesmo PC. Próximo: validar com vídeo real dela, depois Fase 2 (Traduzir). Veja [[Fases]].
