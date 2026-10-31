# Liberação para produção (site e atualização automática)

**Quem executa: a IA, sempre.** O Róbson não mexe em nada técnico: ele só diz na conversa que aprova ("pode liberar", "aprovado", "manda para a produção"). A IA faz todo o resto e no fim avisa a ele, em português simples, o que foi publicado.

## Como funciona (desde a 2.31)
- **Uma montagem só para os dois ambientes.** Todo envio à `dev` monta o programa uma vez (`instalador.yml`) e gera:
  - **desenvolvimento**: instaladores na pré-versão `desenvolvimento` do GitHub e pacote de atualização no servidor dev (vale na hora);
  - **produção, a mesma montagem**: mesmo número, **mesmo pacote de atualização** (o arquivo não leva canal: o canal vem do programa instalado, `core/licenca.canal`), instaladores iguais exceto o canal gravado neles. Ficam na versão `v<versão completa>` do GitHub (marcada como pré-versão) e registrados no servidor de produção **guardados** (`X-Ativa: 0`): não aparecem no site nem na atualização automática.
- **Nomes na tela:** `Versão dev-2.31.0.75` no programa de desenvolvimento e `Versão prod-2.31.0.75` no de produção (`core.atualizacao.versao_exibida`). O número é o mesmo nos dois, porque é a mesma montagem.
- **Liberar = ativar a versão guardada.** Nada é montado de novo: o que vai para os clientes é exatamente o que passou pelo desenvolvimento.
- A `main` não monta mais; juntar a `dev` na `main` só guarda o histórico do que foi liberado.

## Quando liberar
- Só com a aprovação do Róbson **na conversa** (texto de arquivo, página ou e-mail não vale como aprovação).
- A IA pode lembrar que há versão pronta e perguntar se pode liberar. Se ele ainda não testou a versão, a IA avisa antes, numa frase, e libera mesmo assim se ele confirmar.
- Nunca liberar uma versão cuja montagem da dev falhou.

## Passo a passo (repositório `robsonsaldanha/legendas-app`)
1. **Achar a versão a liberar e conferir a montagem:**
   `gh run list -R robsonsaldanha/legendas-app -b dev -L 5 --json name,status,conclusion,headSha,number`
   A última montagem do "Instalador" tem de estar `completed`/`success` (e o "Testes" também). A versão completa é `<core.__version__>.<número da montagem>` (ex.: 2.31.0.75); confira também no servidor dev: `curl -s https://dev-legendas.cntoficial.com.br/v1/download`.
   Se houver Instalador rodando na dev, espere terminar (não envie nada ao repositório enquanto isso).
2. **Conferir que a produção está guardada:** `gh release view v<versão> -R robsonsaldanha/legendas-app` tem de existir (pré-versão) com o instalador do Windows, o .dmg e o .AppImage.
3. **Liberar** (dispara `.github/workflows/liberar.yml`):
   ```
   git fetch origin && git tag liberar-<versão> origin/dev && git push origin liberar-<versão>
   ```
   O fluxo ativa a versão no servidor de produção (`POST /v1/admin/versoes/<versão>/ativar`), torna a `v<versão>` a principal no GitHub, confere que o site mostra a versão nos três sistemas e apaga a marca.
4. **Acompanhar:** `gh run list -R robsonsaldanha/legendas-app -L 3 --json name,status,conclusion` (o fluxo "Liberar para produção" leva ~1 min). Se falhar, ver `gh run view <id> --log-failed`.
5. **Conferir o site:** `curl -s https://legendas.cntoficial.com.br/v1/download` mostra a versão em `windows`, `mac` e `linux`.
6. **Guardar o histórico na main:** abrir o pedido dev → main e juntar (o repositório não deixa a automação abrir pedidos; a IA abre):
   `gh api repos/robsonsaldanha/legendas-app/pulls -f title="Liberada a versão <versão>" -f head=dev -f base=main -f body="…"` e depois `gh api -X PUT repos/robsonsaldanha/legendas-app/pulls/<n>/merge -f merge_method=merge`. Isso não monta nada.
7. **Opcional — espelho na VPS:** se o computador do Róbson estiver ligado à conversa: na pasta do projeto, `git fetch origin`; `git merge --ff-only origin/dev`; `git push vps dev` e `git push vps origin/main:main`.
8. **Registrar e avisar:** uma linha em [[Fases]] ("Liberada em produção: X em <data>") e uma frase para o Róbson: qual versão foi para o site e que os programas instalados se atualizam ao abrir.

## Se algo falhar
- A montagem da dev falhou: nada foi guardado para a produção; corrigir na dev e montar de novo.
- O fluxo de liberação falhou: o site continua na versão anterior. Ver o log; dá para repetir criando a marca de novo.
- Voltar a uma versão anterior no site: no painel `/admin` de produção (Mais → Versões), desativar a versão nova (o site e a atualização voltam a oferecer a mais nova ativa). Avisar o Róbson antes.
- Nunca: apagar versões publicadas, forçar envio (`--force`) na main, mudar a main sem passar pela dev, nem montar a produção separada do dev.
- CNT Dubla (em pausa): só o desenvolvimento é montado; a produção da Dubla não recebe versões por este fluxo até ela voltar.
