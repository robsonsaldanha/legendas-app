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

Atualizado em 2026-10-24 (servidor 1.1; detalhes no `brain/Decisões.md` do repositório do servidor):

| Plano | Preço mensal | Licenças | Observação |
|---|---|---|---|
| Avaliação | — | 1 | 24 h, tudo liberado |
| Grátis | R$ 0 | — | projetos, editor, tradução à mão |
| Individual | R$ 49,90 | 1 | |
| Teamwork (código `profissional`) | R$ 49,90 a primeira + R$ 29,90 cada adicional | 2 ou mais (a pessoa escolhe) | |
| Business / Enterprise | sob cotação | 10 ou mais | plano de **equipe**: Workspace da empresa (só a conta compradora configura) |
| Exclusivo | o que o painel definir | — | plano visível só para um cliente |
| Vitalícia (oculto) | — | o que o painel definir | cortesia |

A compra cria a **conta do cliente** (e-mail + senha); a área do cliente fica em `/login` → `/conta`. Termos, privacidade e cookies em `/termos`, `/privacidade`, `/cookies` (dados legais editáveis no painel); status em `/status`.

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
- `producao`: só quando o Róbson aprovar (PR `dev` → `main`). O cliente recebe só `producao`. Desde 30/10 o CI deixa o pedido pronto a cada versão da dev que passar em tudo; aprovar = juntar o pedido (ver Decisões, "Liberação para o site com um clique").

### Pacote
- **Patch de código** (`Atualizacao_CNT_Legendas_<versão>.zip`): pastas `app/`, `core/` e `lib/` (bibliotecas em Python puro de `packaging/bibliotecas-no-pacote.txt`) (com `core/canal.json` = `{canal, build}`). O servidor devolve um manifesto assinado com Ed25519 (url, sha256, tamanho); o programa confere assinatura e SHA-256. Pequeno.
- **Instalador completo** quando muda Python, bibliotecas, modelos ou o `cntboot.py`: commit com `[instalador]` na mensagem → o servidor marca `requer_instalador` e manda o instalador a quem atualizar.
- Versão completa = `<core.__version__>.<número da montagem do CI>` (ex.: 2.10.0.57). O CI (`.github/workflows/instalador.yml`): ramo `dev` → canal desenvolvimento, pré-versão "desenvolvimento" no GitHub (trocada a cada montagem) e envio ao servidor dev (segredo `CNT_TOKEN_DEV`); ramo `main` → canal produção, versão `v<versão completa>` no GitHub e, quando a variável `CNT_PROD_ATIVO` = 1, envio ao servidor de produção (segredo `CNT_TOKEN_PROD`).
- O servidor só oferece atualização a computadores que ele já conhece (com avaliação ou licença).

### No programa
1. Ao abrir: `GET /v1/atualizacao?canal=producao&versao=2.10.0` → manifesto assinado `{versao, tipo, url, sha256, tamanho, notas}`.
2. Ao abrir, primeiro abre o **lançador** (2.27: janela pequena, antes do programa; ver Decisões). Nele, a tela de atualização (não deixa trabalhar) mostra cada passo, cada um por pelo menos ~1 s: **Procurando atualizações → Baixando (barra com %) → Instalando → "Atualização instalada" com contagem 3, 2, 1 → "Reiniciando o aplicativo…" (1 s) → fecha e reabre** (2.24). O programa só fecha depois que a tela confirma a contagem (`POST /api/atualizacao/reiniciar`; sem tela, reinicia sozinho em 60 s). Erro no download ou na instalação: a tela mostra a mensagem e o **código** (ER-RS-1xx/6xx, ER-RA-440) e o botão "Continuar na versão atual".
   - Patch: extrai em `%ProgramData%\CNT Legendas\versoes\<versão>\`; a inicialização (`cntboot`) carrega a versão válida mais nova. A pasta do programa (Arquivos de Programas) não é alterada; o Windows não pede permissão.
   - Instalador: baixa e roda em modo silencioso com `/ABRIR` (o Windows pede permissão; o instalador fecha o programa e o reabre no fim). Se ela disser "Não" no aviso, segue na versão atual e tenta de novo na próxima abertura.
3. Sem internet ou servidor fora do ar: abre a versão que tem.
   - Depois da atualização, o lançador confere a licença no servidor e os arquivos do programa (`core/arquivos.json`, ER-RA-450) e só então abre a janela do programa.
4. Se a versão nova não abrir (erro na partida), volta sozinho para a anterior.
5. **Depois de reabrir (2.24):** antes de fechar, o programa anota "de → para" em `atualizacao-resultado.json` (pasta de dados). Na abertura seguinte: versão igual ou maior que a anotada = **"Atualização concluída"** com a lista do que mudou (vem das notas da versão — a mensagem do commit, por isso ela é escrita para quem usa o programa); menor = a versão nova não abriu → **"Erro na atualização"** com o código **ER-RA-441**. Caixa "Não mostrar esta tela nas próximas atualizações" (Configurações › Novidades da versão liga de novo); o aviso de erro aparece sempre.

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

## Perfil do usuário e Workspace no servidor (2.13 — pronto)

Decisões do Róbson (2026-10-24): **um perfil por key** (o que manda é a key); vai **tudo que não for contra a LGPD** — configurações (exceto as chaves das IAs, que ficam só no PC), regras/perfis de cliente, clientes, glossários e preferências — e **métricas** (quantidades, tempos e nomes de projetos/clientes; nunca o texto das legendas nem arquivos). Renovar ou comprar de novo não pode perder o perfil.

Como funciona:
- **Perfil = vaga da key** (computador ativado). Guardado cifrado no servidor (`perfis_usuario`), ligado à conta do cliente. O programa envia quando algo muda (alguns segundos depois; sem internet, na próxima vez).
- **PC novo / formatado / troca de computador:** a key nova é ativada e o programa oferece "Restaurar o perfil de <computador> (última alteração …)" com os perfis guardados daquela conta. Licença vencida e comprada de novo: o painel liga a compra à mesma conta, e os perfis continuam lá (guardados por 12 meses depois do vencimento).
- **Arquivo:** Configurações → Perfil: exportar/importar `.cnt-perfil.json` (sem servidor; serve também no modo grátis).
- **O que vai no perfil:** configurações seguras (nome na legenda, método/modelos de tradução, preferências do editor, bandeja…), clientes (com instruções, contexto, idiomas, perfil de regras) e os glossários deles, perfis de regras próprios. Fica fora: chaves de IA, pastas deste PC (pasta dos trabalhos), GPU e o que é do computador.
- **Workspace da empresa (planos de equipe):** o programa recebe os perfis padrão da empresa (aparecem como perfis "Empresa: …", só leitura) e, se a empresa compartilhar, clientes e glossários: cada computador envia os seus e recebe os dos colegas (o mais recente vale; apagar não se propaga). Métricas: se compartilhadas, a conta compradora vê a produção de cada usuário no Workspace.
- **Métricas:** cada episódio/filme (projeto, cliente, tipo, temporada/episódio, mês, situação, nº de legendas, minutos de vídeo, tempo de trabalho, data de entrega) vai para o servidor; a área do cliente ganha "Produção".
- API do programa: `/v1/sync/*`, autenticada por licença + computador ativo nela.

Implementação (2.13 / servidor 1.2):
- Programa: `core/sincronia.py` (protocolo, arquivo `.cnt-perfil.json`, resumo/hash) e `app/perfil.py` (montar/aplicar o perfil, perfis da empresa, clientes compartilhados, métricas, sincronizador em segundo plano a cada 10 min e alguns segundos depois de salvar cliente, perfil de regras ou configuração). Tela: Configurações → **Perfil na nuvem** (situação, Sincronizar agora, trazer de outro computador, Exportar/Importar arquivo). Num computador recém-ativado com perfis guardados na conta, o programa pergunta "Trazer o seu perfil?" (Restaurar / Começar do zero / Depois) **antes** de enviar o perfil deste computador.
- Aplicar um perfil junta, não apaga: clientes pelo nome, perfis de regras pela chave, configurações da lista segura.
- Perfis da empresa: chave `empresa-<id>`, nome "<Empresa>: <perfil>", `extra.padrao` no perfil padrão; somem quando a empresa para de compartilhar.
- Servidor: `src/sync.js` (ver o `brain/Decisões.md` do servidor).
