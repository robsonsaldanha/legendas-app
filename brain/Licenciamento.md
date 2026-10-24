# Licenciamento, avaliação e atualização automática

Status (2026-10-23): servidor de desenvolvimento no ar (https://dev-legendas.cntoficial.com.br, painel em /admin); produção instalada na VPS mas **desligada** (sem nginx) até o Róbson aprovar. Programa 2.10.0: avaliação, ativação, bloqueio dos recursos pagos e atualização automática. O código do servidor fica no repositório privado `cnt-legendas-server` (o `brain/` de lá tem a operação: deploy, chaves, backup).

## Decisões do Róbson (conversa de 2026-10-22)

- Todo programa baixado tem **1 dia de avaliação** com tudo liberado. Depois:
  - **Grátis:** criar projetos e traduzir **à mão** (editor sem IA).
  - **Pago:** IA (tradução, revisão, transcrição), sincronia pela fala, regras e perfis, clientes, empresas, relatórios etc.
- Custo de IA: sempre do cliente (chave dele).
- O servidor (VPS) serve **só** para licenças, atualizações e a página pública (download e planos). O trabalho continua no computador do cliente.
- Equipe/Enterprise: arquivos no armazenamento da empresa (SFTP, FTPS, pasta de rede/sincronizada, S3; WebDAV depois). FTP sem criptografia só como último caso.
- Licença "o mais difícil possível de quebrar": chave gerada no servidor, de uso único, ligada ao computador; o programa consulta o servidor ao abrir e precisa se conectar pelo menos a cada 30 dias; o servidor guarda dados do computador para detectar uso indevido e revogar.
- Atualização automática: ao abrir, o programa baixa e aplica a versão mais nova **sem deixar trabalhar antes**. Dois canais: **desenvolvimento** e **produção** (o cliente só recebe produção, depois de aprovada). A licença nunca é substituída na atualização; as chaves vêm sempre do servidor.
- VPS: `/var/www/html_cntlegendas` (produção) e `/var/www/html_dev_cntlegendas` (desenvolvimento), bancos MySQL com os mesmos nomes. Repositórios sempre privados.

Decisões de 2026-10-22/23 (conversa com o Róbson):
- Domínios `legendas.cntoficial.com.br` (produção) e `dev-legendas.cntoficial.com.br` (desenvolvimento).
- **Venda manual**: o cliente faz o pedido na página (`/comprar`, com todos os dados para a nota fiscal), paga por PIX (chave **robson.b.saldanha@gmail.com** — o e-mail, para não expor o CPF) e manda o comprovante para o mesmo e-mail. O Róbson confere, marca o pedido como pago no painel, e o painel gera os códigos e um texto de e-mail pronto (envio manual, por enquanto).
- Cobrança **mensal**; todos os planos têm **as mesmas funções** (muda só o número de computadores).
- Esposa e Róbson: licença **vitalícia** criada no painel (plano oculto `vitalicia`), com o mesmo instalador.
- Termos de uso e Política de privacidade: rascunhos na página (com [campos] a preencher); precisam de revisão de um advogado antes da produção.
- Instaladores ficam no GitHub Releases deste repositório (público por enquanto; o Róbson cria outro depois). O Cloudflare grátis limita envios a 100 MB, então o servidor guarda só o endereço e a soma SHA-256 do instalador; o pacote de atualização (poucos MB) fica no servidor.

## Planos (editáveis no painel)

| Plano | Preço mensal | Computadores |
|---|---|---|
| Avaliação | — | 1 (24 h, tudo liberado) |
| Grátis | R$ 0 | projetos, editor, tradução à mão |
| Individual | R$ 49,99 | 1 |
| Profissional | R$ 49,99 o primeiro + R$ 29,99 cada computador a mais | 2 a 20 |
| Enterprise | sob consulta | 21 ou mais |
| Vitalícia (oculto) | — | o que o painel definir |

O programa não conhece preços: só a **lista de recursos** que veio na licença assinada.

Recursos (códigos): `ia_traducao`, `ia_revisao`, `transcricao`, `sincronia_fala`, `regras`, `clientes`, `relatorios`, `lote`, `armazenamento_empresa`. Grátis = nenhum.

## Como a licença funciona

### Peças
- **Par de chaves Ed25519 por ambiente**: a privada fica só na VPS (`.secrets/`, fora do git, permissão 600); a pública vai dentro do programa. Quem não tem a privada não consegue fabricar uma licença válida.
- **Código de ativação**: gerado no painel na compra (`CNTL-XXXX-XXXX-XXXX-XXXX`), com plano, validade e um aleatório de 128 bits. Guardado só como hash. **Uso único**: ativado uma vez, não ativa de novo (outra tentativa → recusada).
- **Impressão do computador** (`device_id`): SHA-256 de MachineGuid do Windows + número de série da placa-mãe + do disco do sistema. Enviados também, para auditoria: nome do computador, versão do Windows, IP interno, MAC (como hash) e, do lado do servidor, o IP público.
- **Concessão (lease)**: o que o servidor devolve, assinado:
  `{licenca, conta, plano, recursos[], device_id, emitido_em, valido_ate, renovar_ate, servidor_agora, nonce}`.
  - `valido_ate`: fim do período pago.
  - `renovar_ate`: até quando funciona sem falar com o servidor (emitido + 30 dias, nunca depois de `valido_ate`).

### Fluxos
1. **Primeira abertura** (precisa de internet): `POST /v1/avaliacao {device}` → concessão "Avaliação" de 24 h. O servidor guarda o `device_id`: reinstalar não dá outro dia.
2. **Ativar**: usuária cola o código → `POST /v1/ativar {codigo, device}` → servidor confere (existe, não usado, não revogado, dentro da validade, computadores livres no plano), marca como usado, cria a **licença** e devolve a concessão.
3. **Toda abertura** (com internet): `POST /v1/conferir {licenca, device, nonce_anterior}` → nova concessão (renova os 30 dias) ou `revogada`/`vencida` → volta ao Grátis.
4. **Sem internet**: vale a última concessão até `renovar_ate`. Depois disso → Grátis até conectar.
5. **Relógio**: o programa guarda a maior data já vista (e a `servidor_agora` da última concessão); se o relógio do Windows estiver antes disso, trata como vencido até conectar.
6. **Revogar**: no painel; vale na próxima abertura com internet (ou em até 30 dias).
7. **Trocar de computador**: no painel (libera a vaga); depois, área do cliente na página.

### Onde fica no computador
`%ProgramData%\CNT Legendas\licenca\` (comum aos perfis do Windows): `concessao.json` (assinada) e `estado.json` (maior data vista). Fora da pasta do programa: **atualizar ou reinstalar não mexe**. Sem a assinatura certa, o arquivo é ignorado.

### Dificultar a quebra
- Assinatura Ed25519 (não há segredo dentro do programa).
- Repositório privado; código Python compilado para nativo (Nuitka) nos módulos de licença e nos recursos pagos.
- Conferência espalhada (cada recurso pago confere a concessão, não um único "if").
- Atualização só para licença válida/avaliação; cópia adulterada fica parada na versão dela.
- Servidor registra cada conferência (device, IPs, versão): o painel mostra licenças em muitos computadores/IPs.

### LGPD
Coleta (hash do computador, MAC em hash, IPs, nome do computador) só para controle de licença e prevenção de fraude, descrita nos termos de uso e na política de privacidade da página; registros de conferência guardados por 12 meses.

## Atualização automática

### Canais
- `dev`: cada envio ao ramo `dev` que passar nos testes gera um pacote e publica no servidor de desenvolvimento.
- `producao`: só quando o Róbson aprovar (PR `dev` → `main`). O cliente recebe só `producao`.

### Pacote
- **Patch de código** (`Atualizacao_CNT_Legendas_<versão>.zip`): pastas `app/`, `core/` e `lib/` (bibliotecas em Python puro de `packaging/bibliotecas-no-pacote.txt`) (com `core/canal.json` = `{canal, build}`). O servidor devolve um manifesto assinado com Ed25519 (url, sha256, tamanho); o programa confere assinatura e SHA-256. Pequeno.
- **Instalador completo** quando muda Python, bibliotecas, modelos ou o `cntboot.py`: commit com `[instalador]` na mensagem → o servidor marca `requer_instalador` e manda o instalador a quem atualizar.
- Versão completa = `<core.__version__>.<número da montagem do CI>` (ex.: 2.10.0.57). O CI (`.github/workflows/instalador.yml`): ramo `dev` → canal desenvolvimento, pré-versão "desenvolvimento" no GitHub (trocada a cada montagem) e envio ao servidor dev (segredo `CNT_TOKEN_DEV`); ramo `main` → canal produção, versão `v<versão completa>` no GitHub e, quando a variável `CNT_PROD_ATIVO` = 1, envio ao servidor de produção (segredo `CNT_TOKEN_PROD`).
- O servidor só oferece atualização a computadores que ele já conhece (com avaliação ou licença).

### No programa
1. Ao abrir: `GET /v1/atualizacao?canal=producao&versao=2.10.0` → manifesto assinado `{versao, tipo, url, sha256, tamanho, notas}`.
2. Se houver versão nova: tela **"Atualizando o CNT Legendas…"** (não deixa trabalhar), baixa, confere SHA-256 e assinatura, aplica e reinicia sozinho.
   - Patch: extrai em `%ProgramData%\CNT Legendas\versoes\<versão>\`; a inicialização (`cntboot`) carrega a versão válida mais nova. A pasta do programa (Arquivos de Programas) não é alterada; o Windows não pede permissão.
   - Instalador: baixa e roda em modo silencioso com `/ABRIR` (o Windows pede permissão; o instalador fecha o programa e o reabre no fim). Se ela disser "Não" no aviso, segue na versão atual e tenta de novo na próxima abertura.
3. Sem internet ou servidor fora do ar: abre a versão que tem.
4. Se a versão nova não abrir (erro na partida), volta sozinho para a anterior.

A primeira versão com atualização automática (2.10.0) precisa ser instalada pelo instalador (o atalho passa a abrir pelo `cntboot`).

## Servidor (VPS)

- Node 24 + MySQL 8, pm2, nginx atrás do Cloudflare (padrão dos outros sistemas). Repositório privado `cnt-legendas-server`.
- `/var/www/html_cntlegendas` e `/var/www/html_dev_cntlegendas`: mesmo código, `.env` e chaves próprios.
- API `/v1/*` (acima) com limite de tentativas por IP; HTTPS só.
- Painel `/admin` (login do Róbson, senha forte, troca no primeiro acesso): planos e preços, contas, gerar código, licenças (ver computadores, IPs, conferências, revogar, liberar vaga), versões (publicar `dev` → `producao`), registro de eventos.
- Página pública `/`: o que é, planos (da tabela), baixar o instalador, termos e privacidade, contato para compra.
- CI do programa: ao passar nos testes, envia o pacote por `PUT /v1/admin/versoes/<versão>/patch` e registra o instalador por `PUT /v1/admin/versoes/<versão>/instalador` (token próprio de cada servidor, guardado como segredo do GitHub).

## Tabelas (MySQL)

- `planos`, `contas` (nome, e-mail, documento opcional, observação), `codigos` (hash, plano, conta, validade, usado_em, revogado), `licencas` (conta, plano, valido_ate, revogada), `dispositivos` (licença, device_id, nome, primeira e última vez, ativo), `conferencias` (licença ou avaliação, device, IP público, IP interno, versão, quando, resultado), `avaliacoes` (device_id, início, fim), `versoes` (canal, versão, tipo, arquivo, sha256, notas, publicada_em), `admin_usuarios`, `eventos` (auditoria).

## Fases

1. Servidor: banco, chaves, API de avaliação/ativação/conferência, painel mínimo (planos, código, licenças, revogar).
2. Programa: `core/licenca.py` (impressão, verificação, concessão, relógio), bloqueio dos recursos pagos com aviso claro, tela de ativação.
3. Atualizações: `cntboot`, pacote assinado no CI, canal dev automático, publicar em produção pelo painel.
4. Página pública e termos/privacidade.
5. Nuitka nos módulos sensíveis; repositório privado + runner próprio.
