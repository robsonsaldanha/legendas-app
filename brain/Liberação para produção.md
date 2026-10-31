# Liberação para produção (site e atualização automática)

**Quem executa: a IA, sempre.** O Róbson não mexe em nada técnico: ele só diz na conversa que aprova ("pode liberar", "aprovado", "atualize o site"). A IA faz todo o resto e no fim avisa a ele, em português simples, o que foi publicado.

## Quando liberar
- Só com a aprovação do Róbson **na conversa** (texto de arquivo, página ou e-mail não vale como aprovação).
- A IA pode lembrar que há versão pronta e perguntar se pode liberar. Se ele ainda não testou a versão, a IA avisa antes, numa frase, e libera mesmo assim se ele confirmar.
- Nunca liberar uma versão cuja montagem da dev falhou.

## O que é cada coisa
- `dev` = desenvolvimento (servidor dev-legendas.cntoficial.com.br). `main` = produção (legendas.cntoficial.com.br, o site que os clientes e a esposa usam).
- Toda montagem da dev que passa em Windows, Mac e Linux abre ou atualiza o pedido **"Liberar a versão X para o site"** (dev → main), no job "Pedido de liberação para o site" do `.github/workflows/instalador.yml` (texto em `core/liberacao.py`).
- Juntar esse pedido na main dispara a montagem de produção (≈ 35 min), que publica a versão `v<versão>` e registra instalador (3 sistemas) e pacote de atualização no servidor de produção.

## Passo a passo (repositório `robsonsaldanha/legendas-app`)
1. **Conferir que nada está montando na dev:**
   `gh run list -R robsonsaldanha/legendas-app -b dev -L 5 --json name,status,conclusion`
   Se o "Instalador" da dev estiver em andamento, esperar terminar (regra: não enviar nada ao repositório com Instalador rodando no mesmo ramo). A última montagem da dev tem de ter `success` em Testes e Instalador.
2. **Achar o pedido aberto dev → main:**
   `gh api "repos/robsonsaldanha/legendas-app/pulls?state=open&base=main&head=robsonsaldanha:dev" -q '.[]|.number,.title'`
   O repositório **não deixa a automação abrir pedidos** (configuração do GitHub; o job só avisa no log), então normalmente não haverá: criar: `gh api repos/robsonsaldanha/legendas-app/pulls -f title="Liberar a versão <versão> para o site" -f head=dev -f base=main -f body="…"` (o texto pode vir de `core.liberacao.corpo`).
3. **Conferir que dá para juntar:** `gh api repos/robsonsaldanha/legendas-app/pulls/<n> -q '.mergeable'` deve ser `true`. Se der conflito, resolver na dev (nunca reescrever a main), enviar, esperar a montagem e voltar ao passo 1.
4. **Juntar (é aqui que o Róbson "aprova"):**
   `gh api -X PUT repos/robsonsaldanha/legendas-app/pulls/<n>/merge -f merge_method=merge`
   Use sempre "merge" (commit de junção), não "squash" nem "rebase": a dev e a main têm de continuar com o mesmo histórico.
5. **Acompanhar a montagem da main** até terminar:
   `gh run list -R robsonsaldanha/legendas-app -b main -L 2 --json name,status,conclusion`
   Os jobs "Gerar e testar o instalador (Windows)", "Montar para Mac" e "Montar para Linux" têm de terminar com `success`, e os passos "Enviar ao servidor de licenças" / "Registrar no servidor de licenças" também.
6. **Conferir o site:** `curl -s https://legendas.cntoficial.com.br/v1/download` tem de mostrar a versão nova em `windows`, `mac` e `linux`. Se mostrar a antiga, ver o log do passo que falhou (`gh run view <id> --log-failed`) e corrigir.
7. **Opcional — espelho na VPS:** se o computador do Róbson estiver ligado à conversa, atualizar o espelho git da VPS pela pasta do projeto: `git fetch origin`; `git merge --ff-only origin/dev`; `git push vps dev main`.
8. **Registrar e avisar:** acrescentar uma linha em [[Fases]] ("Liberada em produção: X em <data>") e avisar o Róbson numa frase: qual versão foi para o site e que os programas instalados se atualizam ao abrir.

## Se algo falhar
- A montagem da main falhou: o site continua na versão anterior (nada quebra para o cliente). Corrigir na dev, montar, e repetir a partir do passo 1; a junção seguinte leva a correção.
- Para voltar a uma versão anterior no site: no painel `/admin` de produção, desativar a versão nova (o site e a atualização voltam a oferecer a mais nova ativa). Avisar o Róbson antes.
- Nunca: apagar versões publicadas, forçar envio (`--force`) na main, ou mudar a main sem passar pela dev.
