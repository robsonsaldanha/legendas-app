# Tarefas — o kanban

Só marca **o que está feito e o que falta**. A explicação de cada item (o quê, por quê, como, quando está pronto) está em [[Pendências]], na seção indicada (`P-xx`).

Como usar:
- Mover a linha entre **A fazer → Fazendo → Feito** e trocar `[ ]` por `[x]` ao terminar, com a data e a versão.
- Uma linha por tarefa, com código `T-xxx` (não reaproveitar códigos). Tarefa nova: próximo número livre.
- Quem pega uma tarefa escreve o nome entre parênteses em **Fazendo** (ex.: `(IA 2)`), para ninguém pegar a mesma.
- Ao terminar: atualizar também [[Decisões]] (o que foi decidido) e, se mudou a arquitetura, [[Arquitetura]].

## Fazendo
_(nada no momento)_

## A fazer

### Família CNT — hub, conta única, novo visual
- [x] T-001 · P-01 · Layout e direção aprovados pelo Róbson (24/10/2026); textos editáveis no painel do hub
- [x] T-002 · P-01 · Hub público no ar em `cntoficial.com.br` (repositório `cnt-hub`, substitui o CNT System, que foi desligado com cópia completa) — 24/10/2026
- [ ] T-003 · P-01 · Área logada do hub (início com produtos contratados, faturas, suporte, conta, privacidade) — hoje `/entrar` só leva à área de cada produto; depende de T-010
- [x] T-004 · P-01 · Painel do Róbson no hub (`/admin`: produtos, casos, textos, WhatsApp, empresa) — 24/10/2026
- [x] T-005 · P-02 · Tokens e CSS base do visual novo (no `cnt-server/public/site.css`; o hub e a Dubla copiam) — 24/10/2026
- [x] T-006 · P-02 · Site do Legendas no visual novo em homologação (`dev-legendas`) — servidor 1.5, 24/10/2026
- [x] T-007 · P-02 · Área do cliente (menu lateral) e painel do Legendas no visual novo — servidor 1.5, 24/10/2026
- [ ] T-008 · P-02 · Visual novo em produção (`legendas.`) após aprovação
- [ ] T-009 · P-03 · Decidir onde ficam as contas e como os produtos validam a sessão
- [ ] T-010 · P-03 · Conta única CNT (entrar uma vez) + migração das contas do Legendas

### CNT Legendas — novas funções
- [ ] T-020 · P-04 · Tirar dependências do Windows (licença, cofre, bandeja, janela, diálogos) atrás de uma camada por sistema
- [ ] T-021 · P-04 · Pacote para Linux (`.AppImage`/`.deb`) + CI
- [ ] T-022 · P-04 · Pacote para Mac (`.dmg` assinado) + CI
- [ ] T-023 · P-04 · Atualização automática com canal por sistema
- [ ] T-024 · P-04 · Legendas no navegador (nuvem), com envio opcional do vídeo — depende de T-060
- [ ] T-030 · P-05 · Captura de áudio ao vivo (microfone, sistema, placa) e transcrição contínua com atraso ≤ 3 s
- [ ] T-031 · P-05 · Saídas ao vivo: janela com fundo sólido/transparente e página local de legenda
- [ ] T-032 · P-05 · Painel do operador (atraso, correção, textos prontos, glossário)
- [ ] T-033 · P-05 · Arquivo do evento e abrir no editor; tradução ao vivo (opcional)
- [ ] T-040 · P-06 · Achar espaços sem fala e editor do roteiro de audiodescrição
- [ ] T-041 · P-06 · Perfil de verificação da audiodescrição (guia brasileiro)
- [ ] T-042 · P-06 · Sugestão por IA a partir dos quadros do vídeo
- [ ] T-043 · P-06 · Voz (sintética e gravada) e exportações (roteiro, faixa, faixa mixada, texto com tempos)

### CNT Dubla
- [ ] T-050 · P-07 · Decidir idiomas iniciais, onde processa (servidor × computador) e custo por minuto
- [ ] T-051 · P-07 · Repositório, `brain/`, domínio `dubla.` e `dev-dubla.`
- [ ] T-052 · P-07 · Separação de falantes + adaptação do texto para dublagem
- [ ] T-053 · P-07 · Vozes por personagem e termo de consentimento para clonagem de voz
- [ ] T-054 · P-07 · Editor de dublagem (linha do tempo por personagem)
- [ ] T-055 · P-07 · Separação voz × música e mixagem final; exportações
- [ ] T-056 · P-07 · Integração com o Legendas (enviar para dublagem / legenda ajustada de volta)

### API CNT
- [ ] T-060 · P-08 · Fila de processamento no servidor (máquinas com placa de vídeo) — base de T-024, T-055 e da API
- [ ] T-061 · P-08 · Chaves de API, permissões e ambiente de teste
- [ ] T-062 · P-08 · Recursos `arquivos`, `trabalhos`, `perfis`, `glossarios` + webhooks
- [ ] T-063 · P-08 · Limites, consumo e cobrança por minuto
- [ ] T-064 · P-08 · Documentação pública (OpenAPI) em `api.cntoficial.com.br/docs`

### Operação e o que já existia
- [ ] T-070 · P-10 · Validar com vídeos e projetos reais dela (filme com intervalo, legenda de outra versão, relatório)
- [ ] T-071 · P-10 · Testar no Windows dela (Abrir/Salvar, cofre de senhas, vídeo, F11/F12, dois perfis)
- [ ] T-072 · P-10 · Confirmar assinatura e atalhos que faltam; regras do perfil em português com o cliente
- [ ] T-073 · P-10 · Calibrar a sincronia com legendas acertadas à mão
- [ ] T-074 · P-11 · Ligar a produção (nginx, certificado, `CNT_PROD_ATIVO`) — aguarda aprovação
- [ ] T-075 · P-11 · Termos revisados por advogado; dados do MEI/CNPJ no painel
- [ ] T-076 · P-12 · PIX automático + nota fiscal (quando houver conta PJ)
- [ ] T-077 · P-13 · Lembrete de renovação (e-mail e programa)
- [ ] T-078 · P-14 · Workspace: apagar propaga, com lixeira de 30 dias
- [ ] T-079 · P-15 · Proteção do código de licença e builds em máquina própria

## Feito
Resumo por versão (detalhes em [[Fases]] e [[Decisões]]).
- [x] Programa 2.0–2.9 — transcrever, traduzir, sincronizar pela fala, editor completo, projetos por mês, interface simplificada
- [x] 2.10 — licença (avaliação de 1 dia, modo grátis, ativação) e atualização automática
- [x] 2.11 / 2.12 — janela própria, ícone na bandeja, aviso de versão nova
- [x] 2.13 — perfil na nuvem, Workspace da empresa, métricas de produção
- [x] 2.14 — glossário geral, do cliente e do projeto
- [x] 2.15 — formatos de entrega, prazos, versões, memória de tradução, corretor, aviso de trabalho pronto, "Relatar um problema"
- [x] 2.16 — status da conexão, ⚠ de atualização, códigos de erro ER-RS/ER-RA, modo de depuração
- [x] Servidor 1.0–1.4 — licenças, site, área do cliente, painel, status, termos/LGPD, sincronia, suporte, modo manutenção
- [x] 24/10/2026 — especificações da família CNT ([[Pendências]] P-01 a P-08) e este kanban
