from lib import *
css = """
@page{size:210mm 297mm;margin:0}
.pg{width:210mm;height:297mm}
.in{position:absolute;inset:0 0 34px 0;padding:40px 48px 0}
.hd{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.pn{font-family:Anton;font-size:15px;letter-spacing:.14em;color:var(--on);background:var(--accent);border-radius:8px;padding:6px 12px;white-space:nowrap}
h2{font-size:34px;margin:0}
.lead{font-size:15px;line-height:1.55;color:var(--muted);margin:10px 0 18px}
.st{list-style:none;counter-reset:s;margin-top:16px}
.st li{counter-increment:s;position:relative;padding:12px 0 12px 40px;font-size:14.5px;line-height:1.55;color:#cfd5db;border-bottom:1px solid var(--line)}
.st li:before{content:counter(s);position:absolute;left:0;top:11px;width:26px;height:26px;border-radius:50%;background:rgba(221,176,106,.16);border:1.5px solid var(--accent);color:var(--accent2);font-weight:700;font-size:12px;display:flex;align-items:center;justify-content:center}
.st b{color:var(--ink);font-weight:600}
.dica{margin-top:16px;border-radius:12px;padding:12px 16px 12px 46px;position:relative;font-size:13.5px;line-height:1.5;background:rgba(221,176,106,.09);border:1px solid rgba(221,176,106,.4);color:#e8dfcb}
.dica:before{content:'i';position:absolute;left:14px;top:12px;width:22px;height:22px;border-radius:50%;background:var(--accent);color:var(--on);font-weight:700;display:flex;align-items:center;justify-content:center;font-family:Georgia,serif;font-style:italic}
.dica.aviso{background:rgba(240,160,75,.09);border-color:rgba(240,160,75,.45);color:#f0dcc3}.dica.aviso:before{content:'!';background:var(--warn);font-style:normal}
.dica b{color:var(--ink)}
.cover{background:radial-gradient(800px 600px at 90% 95%,rgba(221,176,106,.18),transparent 60%),linear-gradient(160deg,#14171b,#1b2027 60%,#241f17)}
.k{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:11px;background:var(--panel2);border:1px solid #444c57;border-bottom-width:2px;border-radius:5px;padding:1px 6px;color:var(--ink)}
table{border-collapse:collapse;width:100%;margin-top:10px}
th{text-align:left;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);padding:6px 10px;border-bottom:2px solid var(--accent)}
td{font-size:12px;padding:7px 10px;border-bottom:1px solid var(--line);color:#cfd5db;vertical-align:top}
.faq h3{font-family:Inter;font-weight:700;font-size:14px;color:var(--ink);margin-top:14px}
.faq p{font-size:12.5px;line-height:1.55;color:var(--muted);margin-top:3px}
.toc{list-style:none;margin-top:12px;columns:1}
.toc li{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid var(--line);font-size:13.5px;align-items:baseline}
.toc li span:first-child{font-family:Anton;color:var(--accent);width:30px;font-size:16px}
.toc li span:last-child{margin-left:auto;color:var(--muted);font-size:12px}
.chk{list-style:none}.chk li{font-size:13.5px;line-height:1.5;padding:9px 0 9px 30px;position:relative;border-bottom:1px solid var(--line);color:#cfd5db}
.chk li:before{content:'✓';position:absolute;left:2px;top:9px;color:var(--accent);font-weight:700}
.chk b{color:var(--ink)}
"""
cnt=[1]
def F():
    cnt[0]+=1
    return f'<div class="foot"><span><b>CNT Legendas</b> · Guia passo a passo</span><span>Aplicativo em constante atualização · Versão 2.24</span><span>{cnt[0]}</span></div>'
pgs=[]
def passo(n,title,lead,img,steps,dica='',aviso='',w=698):
    im=f'<div style="width:{w}px;margin:0 auto">{shot(img)}</div>' if img else ''
    d=f'<div class="dica">{dica}</div>' if dica else ''
    a=f'<div class="dica aviso">{aviso}</div>' if aviso else ''
    ol='<ol class="st">'+''.join(f'<li>{s}</li>' for s in steps)+'</ol>'
    return page(f'<div class="in"><div class="hd"><span class="pn">PASSO {n}</span></div><h2>{title}</h2><p class="lead">{lead}</p>{im}{ol}{d}{a}</div>'+F())

# capa
pgs.append(page(f"""<div style="position:absolute;left:56px;top:60px;width:190px">{LOGO}</div>
<div style="position:absolute;left:56px;top:270px;width:600px"><div class="eyebrow">Guia do usuário</div>
<h1 style="font-size:66px;margin:18px 0 20px">Do primeiro clique à <span class="gold">entrega</span>.</h1>
<p class="lead" style="font-size:16px">Passo a passo para instalar, ativar e usar o CNT Legendas: traduzir, revisar, sincronizar, verificar e entregar suas legendas.</p>
<div style="margin-top:22px"><span class="tag">Versão 2.24 · Aplicativo em constante atualização</span></div></div>
<div style="position:absolute;left:150px;top:690px;width:560px;transform:rotate(-3deg)">{shot('projeto')}</div>
<div style="position:absolute;left:230px;top:850px;width:520px;transform:rotate(2deg)">{shot('editor')}</div>
<div class="foot"><span><b>CNT Legendas</b> · Guia passo a passo</span><span>{SITE}</span><span></span></div>""",'cover'))

# sumário
toc=[('1','Antes de começar'),('2','Instalar o programa'),('3','Primeira abertura'),('4','Ativar a licença'),('5','Configurar a tradução'),('6','Cliente, glossário e seu nome'),('7','Criar um novo trabalho'),('8','Trabalhar no projeto'),('9','Traduzir'),('10','Conhecer o editor'),('11','Sincronizar'),('12','Verificar'),('13','Entregar'),('14','Relatórios'),('15','Legenda ao vivo'),('16','Audiodescrição'),('17','Atualizações e suporte'),('18','Perguntas frequentes')]
pg_of={1:3,2:4,3:5,4:6,5:7,6:8,7:9,8:10,9:11,10:12,11:14,12:15,13:16,14:17,15:18,16:19,17:20,18:21}
pgs.append(page(f"""<div class="in"><div class="eyebrow">Sumário</div><h2 style="margin-top:6px">O que você vai aprender</h2>
<p class="lead">Siga na ordem na primeira vez. Depois, use o sumário para ir direto ao assunto. As telas mostradas são do programa real, com dados de exemplo.</p>
<ul class="toc">{''.join(f'<li><span>{a}</span><span style="margin-left:0;color:var(--ink);font-size:14px">{b}</span><span>pág. {pg_of[int(a)]}</span></li>' for a,b in toc)}</ul></div>"""+F()))

# 1 antes
pgs.append(page(f"""<div class="in"><div class="hd"><span class="pn">PASSO 1</span></div><h2>Antes de começar</h2>
<p class="lead">Separe o que você vai precisar. Leva poucos minutos.</p>
<ul class="chk">
<li><b>Um computador com Windows 10 ou 11 de 64 bits.</b> Também há versão para Mac (chip Apple) e para Linux.</li>
<li><b>Internet</b> para instalar, ativar a licença, atualizar o programa e usar a tradução por IA.</li>
<li><b>Código de ativação</b> da sua licença (CNTL-XXXX-XXXX-XXXX-XXXX), enviado por e-mail depois da compra. Cada código ativa um computador.</li>
<li><b>Um jeito de traduzir:</b> a chave de um serviço de IA (tradução automática) <b>ou</b> uma conta de assistente de IA no navegador (o programa guia o copiar e colar, sem API).</li>
<li><b>Uma pasta</b> para guardar seus trabalhos (pode ser uma pasta já existente, sincronizada ou de rede).</li>
<li><b>Os arquivos do cliente:</b> legenda (.srt) e, se tiver, o vídeo do episódio.</li>
</ul>
<div class="dica" style="margin-top:22px"><b>Quer só testar?</b> Todo programa baixado tem 24 horas de avaliação com tudo liberado. Depois, ele passa ao modo grátis: você continua criando projetos e traduzindo à mão. Para voltar a usar IA, sincronia e relatórios, ative um código.</div>
<div style="margin-top:26px;width:520px;margin-left:auto;margin-right:auto">{shot('licenca')}</div>
</div>"""+F()))

# 2 instalar (sem print)
pgs.append(page(f"""<div class="in"><div class="hd"><span class="pn">PASSO 2</span></div><h2>Instalar o programa</h2>
<p class="lead">A instalação é feita uma única vez. Depois, o programa se atualiza sozinho.</p>
<ol class="st">
<li><b>Baixe o instalador</b> na página {SITE}. O arquivo se chama <span class="k">Instalador_CNT_Legendas_&lt;versão&gt;.exe</span>.</li>
<li><b>Dê dois cliques no arquivo.</b> O Windows pede permissão de administrador, porque o programa é instalado para todos os perfis do computador. Clique em <b>Sim</b>.</li>
<li><b>Avance</b> pelas telas do instalador e conclua. Não há nada para instalar à parte: tudo o que o programa precisa já vem junto.</li>
<li><b>Abra pelo atalho “CNT Legendas”</b>, no menu Iniciar ou na área de trabalho. Sempre abra por ele: a página do programa só abre pelo atalho, por segurança.</li>
</ol>
<div class="dica"><b>Mac e Linux:</b> no Mac (chip Apple), abra o arquivo .dmg e arraste o programa para Aplicativos; na primeira vez, use o botão direito do mouse &gt; Abrir. No Linux, use o pacote .AppImage ou .tar.gz. Nos dois, o programa abre no navegador padrão.</div>
<div class="dica aviso"><b>Se o Windows mostrar um aviso de segurança</b> ao abrir o instalador, confirme que o arquivo veio da nossa página e escolha continuar. Em caso de dúvida, fale com a equipe antes de instalar.</div>
<div style="margin-top:26px;display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
{''.join(f'<div class="card" style="text-align:center;padding:16px 10px"><div style="font-family:Anton;font-size:34px;color:var(--accent)">{i}</div><div style="font-size:12px;color:var(--muted);margin-top:4px">{t}</div></div>' for i,t in [(1,'Baixar'),(2,'Permitir'),(3,'Avançar'),(4,'Abrir')])}</div>
</div>"""+F()))

pgs.append(passo(3,'Primeira abertura','Ao abrir pela primeira vez, o programa precisa de internet para registrar a avaliação gratuita de 24 horas.','inicio',[
'<b>Abra o CNT Legendas</b> pelo atalho. Uma janela própria se abre, sem abas e sem barra de endereço.',
'<b>Escolha a pasta dos trabalhos</b> (“Onde ficam os seus trabalhos?”) e clique em <b>Usar esta pasta</b>. Dentro dela, o programa cria uma pasta por mês e, dentro do mês, uma por projeto.',
'Se a pasta já tiver os seus meses, os trabalhos que estão lá <b>aparecem automaticamente</b>. Nada é movido nem apagado.',
'Você chega à tela <b>Início</b>. O menu à esquerda tem: Início, Editor, Ao vivo, Relatórios e Configurações. No canto superior direito, você escolhe o tema (escuro, claro ou automático).'],
'Em cada tela, o botão <b>“?”</b> abre uma dica curta que explica o que é, quando usar e o que acontece com os arquivos.'))

pgs.append(passo(4,'Ativar a licença','Depois da compra, você recebe um código por e-mail. Ele ativa um computador.','licenca',[
'Abra <b>Configurações</b> e, na linha <b>Licença</b>, clique em <b>Ver</b>.',
'Cole o <b>código de ativação</b> (CNTL-XXXX-XXXX-XXXX-XXXX) no campo.',
'Clique em <b>Ativar</b>. O computador precisa estar conectado à internet.',
'A janela passa a mostrar o plano e a validade. Se algo não atualizar, use <b>Conferir de novo</b>.'],
'O código é de <b>uso único</b> e fica ligado a este computador. Para trocar de computador, libere a vaga na área do cliente, no site.',
'Se a avaliação terminar antes de você ativar, o programa continua abrindo no <b>modo grátis</b> (projetos e tradução à mão). Ao ativar, os recursos voltam na hora.'))

pgs.append(passo(5,'Configurar a tradução','Escolha como o programa vai traduzir: pela API de um serviço de IA ou pelo seu assistente de IA, sem API.','configuracoes2',[
'Em <b>Configurações</b>, procure a linha <b>Tradução automática</b> e clique em <b>Configurar</b>.',
'<b>Opção 1: pelo seu assistente de IA (sem custo de API).</b> Não precisa configurar nada aqui. Na hora de traduzir, o programa copia cada parte do texto, você cola no assistente e traz a resposta de volta.',
'<b>Opção 2: pela API.</b> Escolha o serviço de IA, cole a <b>chave</b> e clique em <b>Salvar e testar</b>. Depois escolha o modelo na lista.',
'A chave fica guardada no <b>cofre de senhas do computador</b>, nunca em arquivo. O custo da IA é cobrado pelo próprio serviço, na sua conta.'],
'Antes de cada tradução pela API, o programa mostra uma <b>estimativa de custo</b>. Em “Avançado” você acerta modelos e preços.'))

pgs.append(passo(6,'Cliente, glossário e seu nome','Deixe o programa conhecer o jeito de cada cliente. Você faz isso uma vez, e vale para todos os trabalhos.','configuracoes',[
'<b>Seu nome na legenda:</b> digite como você assina e clique em <b>Salvar</b>. Ele pode entrar como assinatura no fim da legenda, na hora de entregar.',
'<b>Clientes:</b> cadastre cada cliente, escolha o <b>perfil de regras</b> dele (limites de caracteres, velocidade de leitura, estilo) e, se houver, o glossário e as instruções específicas.',
'<b>Glossário geral:</b> termos que valem em todos os trabalhos. O glossário do cliente e o do projeto (menu “⋯” do projeto) ficam nas telas deles. <b>O mais específico vale.</b>',
'<b>Formato de entrega:</b> .srt é o padrão. Cliente e projeto podem usar outro (.vtt, .ttml ou .ass).'],
'Perfis de clientes com manual próprio são arquivos: use <b>Perfis de regras &gt; Importar perfis</b> para trazê-los e <b>Exportar</b> para fazer cópia.'))

pgs.append(passo(7,'Criar um novo trabalho','Três perguntas e o programa organiza tudo.','novo-trabalho',[
'Na tela <b>Início</b>, clique em <b>Novo trabalho</b>.',
'<b>1. O que você vai fazer:</b> Traduzir uma legenda (o mais comum), Legendar um vídeo (o programa escreve a legenda a partir da fala) ou Acertar o tempo (legenda fora do tempo do vídeo).',
'<b>2. Para quem e qual episódio:</b> escolha o cliente, o projeto (ou crie um novo, como filme ou série), temporada e episódio, o idioma do original e o idioma de destino. Se quiser, defina o prazo em <b>Entregar até</b>.',
'<b>3. Arquivos:</b> escolha a legenda do cliente (.srt) e, se tiver, o vídeo para conferir.',
'Clique em <b>Criar e abrir no editor</b>.'],
'Os arquivos são <b>copiados</b> para a pasta do episódio. Os seus originais continuam onde estão, intactos.'))

pgs.append(passo(8,'Trabalhar no projeto','Cada episódio passa pela mesma trilha: Arquivos, Traduzir, Revisar e Entregar.','projeto',[
'Abra o projeto pelo <b>Início</b>. A tela mostra um cartão por episódio, com a trilha de quatro passos e o <b>próximo passo</b>.',
'Para acrescentar mais episódios, use <b>+ Episódios</b> (por exemplo “7-12”, ou “1, 7”).',
'O botão em destaque faz a ação seguinte: <b>Pôr arquivos</b>, <b>Traduzir</b>, etc. O menu <b>⋯</b> abre as outras opções do episódio, como título e prazo.',
'<b>Abrir a pasta</b> leva você à pasta do projeto no Windows. <b>Mais</b> traz glossário do projeto, situação (novo, em andamento, finalizado) e o relatório.'],
'No Início, o atalho <b>“Continuar de onde parou”</b> reabre o último episódio em que você trabalhou.'))

pgs.append(passo(9,'Traduzir','No editor, clique em Traduzir. A legenda original nunca é alterada: a tradução vira um arquivo novo ao lado dela.','traduzir',[
'No cartão do episódio, clique em <b>Traduzir</b>, ou use o botão <b>Traduzir para …</b> na barra do editor.',
'Escolha o jeito: <b>Pelo meu assistente de IA</b> (sem custo) ou <b>Automática (API)</b>. Confira os idiomas <b>De</b> e <b>Para</b> (o botão ⇄ inverte), o cliente e o perfil de regras.',
'<b>Automática:</b> clique em <b>Começar</b> e acompanhe o progresso. Se parar no meio, é só recomeçar: ele retoma do ponto em que estava.',
'<b>Pelo assistente de IA:</b> clique em <b>Copiar parte 1 e abrir o assistente</b>, comece uma <b>conversa nova</b>, cole com <span class="k">Ctrl</span>+<span class="k">V</span> e envie. Copie o bloco de código da resposta e cole na caixa do programa.',
'O programa confere a resposta e pede só o que faltou. Repita para as próximas partes (cada parte tem até 100 legendas). No fim, a tradução abre no editor, com a coluna <b>Original</b> ao lado.'],
'Para revisar uma legenda <b>no mesmo idioma</b> (ortografia, gramática, pontuação e velocidade de leitura), use o botão <b>Revisar</b>: o resultado sai como “… (revisada).srt”.'))

pgs.append(page(f"""<div class="in"><div class="hd"><span class="pn">PASSO 10</span></div><h2>Conhecer o editor</h2>
<p class="lead">É onde você revisa e ajusta. Tudo o que importa fica numa tela só.</p>
<div style="width:698px;margin:0 auto">{shot('editor')}</div>
<ol class="st">
<li><b>Barra de cima:</b> Salvar, Traduzir, Revisar, Sincronizar, Verificar (o número mostra quantas legendas têm aviso), Entregar e Audiodescrição. À direita: desfazer, refazer, localizar e substituir e histórico de versões.</li>
<li><b>Grade:</b> uma linha por legenda, com início, fim, duração e velocidade de leitura (CPS). Valores acima do limite ficam em vermelho.</li>
<li><b>Painel de edição:</b> edite o texto e o tempo; use <b>Quebra automática</b>, <b>Dividir</b> e <b>Juntar com a próxima</b>.</li>
<li><b>Vídeo e forma de onda:</b> arraste as bordas de cada legenda para acertar entrada e saída. Dê zoom com <span class="k">Ctrl</span> + roda do mouse.</li>
</ol></div>"""+F()))

pgs.append(page(f"""<div class="in"><div class="hd"><span class="pn">PASSO 10</span></div><h2>Atalhos e ferramentas do editor</h2>
<p class="lead">Aprender poucos atalhos acelera muito a revisão.</p>
<table><tr><th>Ação</th><th>Atalho</th></tr>
<tr><td>Tocar / pausar</td><td><span class="k">Espaço</span></td></tr>
<tr><td>Quadro anterior / seguinte</td><td><span class="k">←</span> <span class="k">→</span></td></tr>
<tr><td>Andar 1 segundo</td><td><span class="k">Shift</span>+<span class="k">←</span> / <span class="k">→</span></td></tr>
<tr><td>Legenda anterior / próxima</td><td><span class="k">Alt</span>+<span class="k">↑</span> / <span class="k">↓</span></td></tr>
<tr><td>Marcar início / fim da legenda</td><td><span class="k">F11</span> / <span class="k">F12</span></td></tr>
<tr><td>Nova legenda</td><td><span class="k">Insert</span></td></tr>
<tr><td>Ir ao próximo problema</td><td><span class="k">F8</span></td></tr>
<tr><td>Itálico</td><td><span class="k">Ctrl</span>+<span class="k">I</span></td></tr>
<tr><td>Salvar</td><td><span class="k">Ctrl</span>+<span class="k">S</span></td></tr>
<tr><td>Desfazer / refazer</td><td><span class="k">Ctrl</span>+<span class="k">Z</span> / <span class="k">Ctrl</span>+<span class="k">Y</span></td></tr>
<tr><td>Localizar e substituir</td><td><span class="k">Ctrl</span>+<span class="k">F</span></td></tr></table>
<div style="width:640px;margin:22px auto 0">{shot('localizar')}</div>
<div class="dica" style="margin-top:16px"><b>Mais recursos:</b> botão direito numa legenda para subir para o topo da tela e alinhar; corretor ortográfico e memória de tradução em uma linha discreta abaixo do texto; <b>histórico de versões</b> para voltar a um ponto anterior; rascunho automático e cópia de segurança ao salvar.</div>
</div>"""+F()))

pgs.append(passo(11,'Sincronizar','Se a legenda está fora do tempo do vídeo, o menu Sincronizar resolve de várias maneiras.','sincronizar',[
'No editor, abra o menu <b>Sincronizar</b>.',
'Para a maioria dos casos, escolha <b>Sincronia precisa pela fala</b>: ela separa a voz da música e do ruído e acerta início e fim de cada legenda. Se o computador tiver placa de vídeo, ela é aproveitada.',
'Quando a legenda só está deslocada, use <b>Automática pela fala (rápida)</b> ou <b>Atrasar ou adiantar…</b>.',
'Tem uma legenda com o tempo certo em outro idioma? Use <b>Pela legenda de referência…</b> ou <b>Copiar os tempos…</b> (mesma quantidade de legendas).',
'Outras opções: <b>Por dois pontos</b>, <b>Converter quadros por segundo</b>, <b>Encaixar nos cortes de cena</b> e <b>Texto sem tempo (roteiro)</b>.'],
'Experimente o resultado tocando o vídeo e, se não gostar, use <b>Desfazer</b> (<span class="k">Ctrl</span>+<span class="k">Z</span>).'))

pgs.append(passo(12,'Verificar','Antes de entregar, deixe o programa conferir cada legenda com as regras do cliente.','verificar',[
'Clique em <b>Verificar</b>. O número no botão é a quantidade de legendas com apontamento.',
'O painel à direita lista, por legenda, os <b>erros</b> (por exemplo, linhas demais ou sobreposição) e os <b>avisos</b> (velocidade de leitura, duração, intervalo).',
'Clique em <b>Corrigir tempos e estilo</b> para aplicar os ajustes automáticos. A opção <b>Fechar intervalos curtos</b> encadeia legendas muito próximas.',
'Para o que sobrar, clique na legenda indicada, ajuste, e use <b>Conferir de novo</b>. A tecla <span class="k">F8</span> pula para o próximo problema.'],
'Os avisos são <b>sugestões</b>: a decisão final é sua. As regras vêm do perfil do cliente escolhido (mostrado na barra de baixo do editor).'))

pgs.append(passo(13,'Entregar','Quando estiver pronto, gere o arquivo no formato e no nome que o cliente espera.','entregar',[
'Clique em <b>Entregar</b>.',
'Confira o <b>nome do arquivo</b> e o <b>formato</b> (.srt, .vtt, .ttml ou .ass). O formato padrão vem das Configurações, mas cliente e projeto podem ter o seu.',
'Veja a <b>pasta</b> de destino. Por padrão, é a pasta <b>Entrega</b> dentro do episódio. Use <b>Escolher</b> para mudar.',
'Se quiser, marque <b>Assinatura no fim</b> e informe o nome em “Tradução”. Marque também <b>Salvar o relatório de verificação (.qc.txt)</b>.',
'Se houver apontamentos, o programa avisa e oferece <b>Ver antes de entregar</b>. Clique em <b>Entregar</b> para finalizar.'],
'Depois de entregar, volte ao projeto e marque o episódio como <b>finalizado</b>. Você pode reabrir a qualquer momento.'))

pgs.append(passo(14,'Relatórios','Acompanhe o que foi produzido e quanto tempo levou.','relatorios',[
'No menu, clique em <b>Relatórios</b>.',
'Use os filtros <b>De</b>, <b>Até</b>, <b>Cliente</b> e <b>Status</b> e clique em <b>Aplicar</b>.',
'Veja o total de projetos e episódios, vídeo legendado, <b>tempo trabalhado</b> e <b>produtividade</b> (legendas, palavras e minutos de vídeo por hora).',
'Mais abaixo, estão os detalhes de texto, tempo e leitura (CPS médio e máximo).',
'Clique em <b>Exportar planilha (CSV)</b> para levar os números ao Excel ou a outro programa de planilha.'],
'O relatório de um projeto ou episódio específico fica no menu <b>Mais</b> do projeto.'))

pgs.append(passo(15,'Legenda ao vivo','Gera a legenda na hora, a partir de uma entrada de áudio, com tempo para você corrigir antes de ir à tela.','ao-vivo',[
'No menu, clique em <b>Ao vivo</b>.',
'Em <b>Entrada de áudio</b>, escolha de onde vem o som (microfone, som do computador, placa de áudio, arquivo ou endereço). Defina o <b>idioma falado</b>, a <b>precisão</b> e, se quiser, a <b>tradução ao vivo</b>.',
'Escolha o <b>cliente</b> (para os nomes certos do glossário) e, se necessário, <b>palavras para esconder</b>.',
'Clique em <b>Começar</b>. As legendas entram na <b>Fila</b> e esperam alguns segundos: corrija antes que vão à tela. Para algo pronto, use <b>Texto pronto</b> e <b>Mandar</b>.',
'Em <b>Na tela</b>, ajuste jeito de mostrar, fundo, tamanho e posição. Copie o <b>endereço</b> para o programa de transmissão (fonte de navegador) ou clique em <b>Abrir janela de legenda</b>.'],
'Ao terminar, o programa guarda um arquivo <b>.srt do evento</b> que abre no editor para você revisar.'))

pgs.append(passo(16,'Audiodescrição','Crie a faixa de descrição do que se vê, respeitando os espaços sem fala.','audiodescricao',[
'Abra um episódio que tenha vídeo e clique em <b>Audiodescrição</b>, na barra do editor.',
'Clique em <b>Usar as regras de audiodescrição</b> e informe a <b>velocidade da voz</b> (palavras por minuto).',
'Clique em <b>Achar espaços sem fala</b>. Cada espaço vira uma <b>descrição</b> para preencher.',
'Em cada descrição, escreva o texto, ouça com <b>Ouvir</b> ou peça uma ideia em <b>Sugerir com IA</b>. Se preferir, grave com <b>Gravar com a minha voz</b>.',
'Use <b>Verificar</b> para saber se o texto cabe no tempo e, por fim, <b>Exportar…</b> (roteiro em .docx ou .txt, .ttml, faixa e áudio mixado).'],
'Sugestões da IA são um ponto de partida: leia e ajuste cada descrição antes de usar.'))

pgs.append(page(f"""<div class="in"><div class="hd"><span class="pn">PASSO 17</span></div><h2>Atualizações e suporte</h2>
<p class="lead">O CNT Legendas está em constante atualização. Você não precisa baixar nada: o programa cuida disso.</p>
<ol class="st">
<li><b>Ao abrir</b>, o programa procura a versão mais nova e mostra cada etapa: Procurando atualizações, Baixando (com barra de progresso), Instalando, uma contagem 3, 2, 1 e Reiniciando.</li>
<li><b>Depois de reabrir</b>, uma tela “Atualização concluída” lista o que mudou. Marque “Não mostrar esta tela nas próximas atualizações” se preferir; para voltar a ver, ative <b>Configurações &gt; Novidades da versão</b>.</li>
<li><b>Com o programa aberto</b>, um aviso ⚠ indica que há versão nova. O programa salva seu trabalho e reabre onde você estava.</li>
<li><b>Sem internet?</b> O programa abre normalmente com a versão que você tem.</li>
<li>Para procurar na hora: <b>Configurações &gt; Versão do programa &gt; Procurar atualização</b>.</li>
</ol>
<div style="width:560px;margin:20px auto 0">{shot('configuracoes')}</div>
<div class="dica" style="margin-top:18px"><b>Precisa de ajuda?</b> Em <b>Configurações &gt; Relatar um problema</b>, conte o que aconteceu e a equipe recebe na hora. Em <b>Modo de depuração e diagnóstico</b>, clique em <b>Ligar por 5 min</b>, repita o que deu errado e o programa gera um arquivo .zip na pasta Documentos para você enviar. Se aparecer um código como <b>ER-RA-101</b>, informe-o.</div>
</div>"""+F()))

pgs.append(page(f"""<div class="in faq"><div class="hd"><span class="pn">PASSO 18</span></div><h2>Perguntas frequentes</h2>
<h3>Preciso de internet para trabalhar?</h3><p>Para ativar a licença, atualizar e usar a tradução por IA, sim. O programa confere a licença ao abrir; sem conexão, funciona com a última conferência por até 30 dias. A edição, a verificação e a transcrição rodam no computador.</p>
<h3>Meus arquivos originais são alterados?</h3><p>Nunca. As saídas ficam ao lado do vídeo ou na pasta do projeto, e a legenda de origem não é tocada.</p>
<h3>Onde ficam os resultados?</h3><p>Dentro da pasta do episódio, no mês correspondente. A entrega vai para a pasta “Entrega”, ou para a que você escolher.</p>
<h3>A avaliação acabou. E agora?</h3><p>O programa continua no modo grátis. Para liberar tudo de novo, ative o código em Configurações &gt; Licença.</p>
<h3>Troquei de computador. Como uso minha licença?</h3><p>Libere a vaga do computador antigo na área do cliente, no site, e ative o código no novo. O perfil na nuvem restaura suas configurações, clientes e glossários.</p>
<h3>Quanto custa a IA?</h3><p>A IA usa a sua própria chave, e o custo é cobrado pelo provedor, sem margem. Antes de traduzir, o programa mostra uma estimativa. Se preferir, traduza pelo seu assistente de IA, sem API.</p>
<h3>Posso usar legendas em vários idiomas?</h3><p>Sim, o programa trabalha com 20 idiomas e detecta o idioma da legenda automaticamente.</p>
<h3>Como sei que o programa está conectado?</h3><p>O status da conexão aparece no canto superior direito. Passe o mouse para ver o detalhe do servidor e da internet.</p>
<h3>Algo deu errado. Quem me ajuda?</h3><p>Use <b style="color:var(--ink)">Configurações &gt; Relatar um problema</b>, ou escreva pelo site {SITE}.</p>
</div>"""+F()))

pgs.append(page(f"""
<div style="position:absolute;left:56px;top:60px;width:190px">{LOGO}</div>
<div style="position:absolute;left:56px;top:300px;width:600px"><span class="tag">Em constante atualização</span>
<h1 style="font-size:58px;margin:18px 0 16px">Bom trabalho, e <span class="gold">boas entregas</span>.</h1>
<p class="lead" style="font-size:16px">Este guia descreve a versão 2.24. Como o programa é atualizado com frequência, algumas telas podem ficar ligeiramente diferentes em versões mais novas. Os passos continuam os mesmos.</p>
<div class="card" style="margin-top:26px;display:inline-flex;gap:14px;align-items:center;padding:14px 22px"><span style="color:var(--accent)">{icon_only('cloud',22)}</span><div><div style="font-size:10px;letter-spacing:.18em;color:var(--muted)">SITE, DOWNLOAD E ÁREA DO CLIENTE</div><div style="font-size:19px;font-weight:700">{SITE}</div></div></div></div>
<div style="position:absolute;left:120px;top:800px;width:560px;transform:rotate(-2deg)">{shot('tema-claro')}</div>
<div class="foot"><span><b>CNT Legendas</b> · Guia passo a passo</span><span>{SITE}</span><span></span></div>""",'cover'))
open('tutorial.html','w',encoding='utf-8').write(doc('CNT Legendas — Guia do usuário',css,''.join(pgs)))
print(len(pgs))
