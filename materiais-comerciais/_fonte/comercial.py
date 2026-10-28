from lib import *
css = """
@page{size:297mm 210mm;margin:0}
.pg{width:297mm;height:210mm}
.in{position:absolute;inset:0 0 34px 0;padding:30px 52px 0;display:flex;flex-direction:column;justify-content:center}
.pg img[alt]{width:100%}
h2{font-size:42px;margin:8px 0 12px}
.lead{font-size:15px;line-height:1.55;color:var(--muted);max-width:560px}
.cols{display:grid;gap:16px}
.card h3{font-family:Inter;font-size:14.5px;font-weight:700;margin-bottom:6px;letter-spacing:0}
.card p{font-size:13px;line-height:1.5;color:var(--muted)}
.big{font-size:44px;color:var(--accent);font-family:Anton}
.cover{background:radial-gradient(1000px 600px at 85% 20%,rgba(221,176,106,.16),transparent 60%),linear-gradient(135deg,#14171b,#1b2027 60%,#241f17)}
.step{position:relative;padding:16px 16px 14px;background:var(--panel);border:1px solid var(--line);border-radius:14px}
.step .n{font-family:Anton;font-size:30px;color:var(--accent);line-height:1}
.step b{display:block;font-size:14px;margin:6px 0 4px}
.step span{font-size:11.5px;color:var(--muted);line-height:1.45;display:block}
.plan{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px 22px 20px;display:flex;flex-direction:column}
.plan.hl{border-color:var(--accent);background:linear-gradient(180deg,rgba(221,176,106,.10),var(--panel) 60%)}
.plan h3{font-family:Inter;font-weight:700;font-size:17px}
.plan .pr{font-family:Anton;font-size:40px;color:var(--accent);margin:8px 0 2px;line-height:1}
.plan .pr small{font-family:Inter;font-size:12px;color:var(--muted);font-weight:500}
.plan ul{list-style:none;margin-top:12px}
.plan li{font-size:12px;color:var(--ink);padding:5px 0 5px 20px;position:relative;line-height:1.4;border-top:1px solid var(--line)}
.plan li:before{content:'✓';position:absolute;left:0;color:var(--accent);font-weight:700}
.tl{position:relative;padding-left:22px}
.tl:before{content:'';position:absolute;left:5px;top:6px;bottom:6px;width:2px;background:var(--line)}
.tl div{position:relative;margin-bottom:11px;font-size:12px;line-height:1.45;color:var(--muted)}
.tl div:before{content:'';position:absolute;left:-22px;top:4px;width:12px;height:12px;border-radius:50%;background:var(--bg);border:2px solid var(--accent)}
.tl b{color:var(--ink);font-weight:600}
.tl i{font-style:normal;color:var(--accent);font-weight:700;margin-right:6px}
.chk{list-style:none}.chk li{font-size:13px;line-height:1.5;padding:7px 0 7px 26px;position:relative;border-bottom:1px solid var(--line);color:#cfd5db}
.chk li:before{content:'';position:absolute;left:2px;top:12px;width:12px;height:12px;border-radius:50%;background:rgba(221,176,106,.2);border:2px solid var(--accent)}
.chk b{color:var(--ink)}
"""
F = lambda n: f'<div class="foot"><span><b>CNT Legendas</b> · Apresentação comercial</span><span>{SITE}</span><span>{n}</span></div>'
pgs = []

# 1 capa
pgs.append(page(f"""
<div style="position:absolute;left:56px;top:48px;width:170px">{LOGO}</div>
<div style="position:absolute;left:56px;top:150px;width:470px">
 <div class="eyebrow">Legendagem profissional</div>
 <h1 style="font-size:62px;margin:18px 0 20px">Do arquivo do cliente à <span class="gold">entrega</span>, num só lugar.</h1>
 <p class="lead" style="font-size:15px">O CNT Legendas traduz, revisa, sincroniza e confere suas legendas no padrão das grandes plataformas, tudo no seu computador, com a velocidade da inteligência artificial e o controle da sua equipe.</p>
 <div style="margin-top:26px;display:flex;gap:10px;flex-wrap:wrap"><span class="tag">Aplicativo em constante atualização</span><span class="tag">Avaliação gratuita de 24 horas</span></div>
</div>
<div style="position:absolute;left:575px;top:150px;width:560px;transform:rotate(-2.2deg)">{shot('editor')}</div>
<div class="foot"><span><b>CNT Legendas</b> · Apresentação comercial</span><span>{SITE}</span><span>Versão 2.24</span></div>""", 'cover'))

# 2 desafio
pgs.append(page(f"""<div class="in">
<div class="eyebrow">O desafio</div><h2>Legendar bem, rápido e<br>do jeito de cada cliente.</h2>
<p class="lead">Quem entrega legenda para plataformas e emissoras vive entre prazos curtos, manuais diferentes para cada cliente e retrabalho por detalhes que a revisão pega tarde demais.</p>
<div class="cols" style="grid-template-columns:repeat(3,1fr);margin-top:34px">
 <div class="card"><div class="big">1</div><h3>Prazo apertado</h3><p>Episódios chegam em lote e o prazo não muda. Cada hora gasta em tarefa repetitiva é hora a menos de revisão.</p></div>
 <div class="card"><div class="big">2</div><h3>Regras de cada cliente</h3><p>Limite de caracteres, velocidade de leitura, tempo mínimo, pontuação, glossário de nomes. O que vale para um não vale para outro.</p></div>
 <div class="card"><div class="big">3</div><h3>Qualidade sem retrabalho</h3><p>Erro de tempo ou de estilo achado na entrega vira devolução. O ideal é pegar tudo antes de enviar.</p></div>
</div>
<div class="card" style="margin-top:22px;border-color:rgba(221,176,106,.45);background:linear-gradient(120deg,#30291D,#23282C 60%,#2B261C);display:flex;gap:22px;align-items:center">
 <div style="font-family:Anton;font-size:30px;line-height:1.1;color:var(--accent2);min-width:230px">A resposta:<br>CNT Legendas</div>
 <p style="font-size:13.5px;color:#d7dce1;line-height:1.55">Um programa único que reúne tradução com IA, editor profissional, sincronia pela fala, verificação automática e entrega. Instala em minutos, funciona no seu computador e já vem com os padrões de legendagem prontos.</p>
</div></div>{F(2)}"""))

# 3 como funciona
pgs.append(page(f"""<div class="in">
<div class="eyebrow">Como funciona</div><h2>Quatro passos, do início ao fim.</h2>
<p class="lead">Cada episódio segue o mesmo caminho. O programa mostra sempre onde você parou e qual é o próximo passo.</p>
<div class="cols" style="grid-template-columns:repeat(4,1fr);margin-top:22px">
 <div class="step"><div class="n">01</div><b>Arquivos</b><span>Você escolhe a legenda do cliente e o vídeo. Seus originais nunca são alterados.</span></div>
 <div class="step"><div class="n">02</div><b>Traduzir</b><span>A IA traduz em lotes, com contexto, glossário e as regras do cliente.</span></div>
 <div class="step"><div class="n">03</div><b>Revisar</b><span>Editor com vídeo, forma de onda e conferência automática de erros.</span></div>
 <div class="step"><div class="n">04</div><b>Entregar</b><span>Arquivo no formato e no nome que o cliente pede, pronto para enviar.</span></div>
</div>
<div style="margin-top:22px;width:650px;margin-left:auto;margin-right:auto">{shot('projeto')}</div>
</div>{F(3)}"""))

# 4 benefícios
def card(i,t,p): return f'<div class="card">{ico(i)}<h3>{t}</h3><p>{p}</p></div>'
pgs.append(page(f"""<div class="in">
<div class="eyebrow">Por que o CNT Legendas</div><h2>O que muda no seu dia a dia.</h2>
<div class="cols" style="grid-template-columns:repeat(3,1fr);margin-top:26px">
{card('lang','Tradução com IA que respeita o cliente','Lotes com contexto das falas vizinhas, glossário de nomes e limite de caracteres por legenda. 20 idiomas.')}
{card('check','Conferência antes da entrega','Velocidade de leitura, duração, intervalo e linhas são conferidos, com correção automática de tempos e de estilo.')}
{card('wave','Sincronia pela fala','Acerta o tempo da legenda pela voz do vídeo, quadro a quadro. Também por outra legenda de referência.')}
{card('lock','Seus arquivos ficam com você','O trabalho roda no seu computador. A chave da IA é sua e o custo da IA vai direto ao provedor, sem intermediário.')}
{card('users','Feito para equipes','Clientes, glossários e perfis de regras compartilhados, relatórios de produção e prazos de entrega por episódio.')}
{card('bolt','Sempre atual','O programa se atualiza sozinho ao abrir e ganha recursos novos com frequência, sem reinstalar nada.')}
</div></div>{F(4)}"""))

# 5 editor
pgs.append(page(f"""<div class="in" style="padding-top:34px">
<div style="display:grid;grid-template-columns:300px 1fr;gap:30px;align-items:center;height:100%">
<div><div class="eyebrow">Editor profissional</div><h2>Tudo o que a revisão precisa, numa tela.</h2>
<ul class="chk" style="margin-top:14px">
<li><b>Grade de legendas</b> com início, fim, duração e velocidade de leitura marcada em cores</li>
<li><b>Vídeo com a legenda</b> sobreposta e quadro exato</li>
<li><b>Forma de onda</b> para ajustar entradas e saídas arrastando</li>
<li><b>Desfazer, histórico de versões</b>, localizar e substituir, corretor ortográfico</li>
</ul></div>
{shot('editor')}
</div></div>{F(5)}"""))

# 6 sincronia e qualidade
pgs.append(page(f"""<div class="in" style="padding-top:34px">
<div style="display:grid;grid-template-columns:1fr 330px;gap:30px;align-items:center;height:100%">
{shot('sincronizar')}
<div><div class="eyebrow">Sincronia e qualidade</div><h2>Tempo certo, na fala certa.</h2>
<ul class="chk" style="margin-top:14px">
<li><b>Sincronia precisa pela fala</b>: separa a voz da música e do ruído</li>
<li><b>Pela legenda de referência</b>, mesmo em outro idioma</li>
<li><b>Atrasar e adiantar</b>, dois pontos, conversão de quadros por segundo</li>
<li><b>Cortes de cena</b> detectados e respeitados</li>
<li><b>Texto sem tempo</b> (roteiro) vira legenda sincronizada</li>
</ul></div></div></div>{F(6)}"""))

# 7 equipes
pgs.append(page(f"""<div class="in" style="padding-top:34px">
<div style="display:grid;grid-template-columns:330px 1fr;gap:30px;align-items:center;height:100%">
<div><div class="eyebrow">Para equipes e empresas</div><h2>Visão de quem produz e de quem gerencia.</h2>
<ul class="chk" style="margin-top:14px">
<li><b>Clientes</b> com glossário e perfil de regras próprios</li>
<li><b>Glossário em três níveis</b>: geral, cliente e projeto</li>
<li><b>Relatórios</b> de produção: legendas, palavras, tempo trabalhado, produtividade</li>
<li><b>Prazo de entrega</b> por episódio, sempre à vista</li>
<li><b>Workspace da empresa</b> (planos Business e Enterprise): perfis e clientes compartilhados pela equipe</li>
<li><b>Perfil na nuvem</b>: restaure suas configurações em um computador novo</li>
</ul></div>
{shot('relatorios')}
</div></div>{F(7)}"""))

# 8 além da legenda
pgs.append(page(f"""<div class="in">
<div class="eyebrow">Além da legenda</div><h2>Um estúdio de acessibilidade<br>dentro do mesmo programa.</h2>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:22px">
{card('mic','Legenda ao vivo','Ouve o áudio e gera a legenda na hora, com fila para você corrigir antes de ir à tela. Saída para o programa de transmissão, com tradução ao vivo.')}
{card('ear','Audiodescrição','Acha os espaços sem fala, sugere descrições com IA, toca com voz do sistema ou com a sua própria e exporta roteiro e áudio.')}
{card('film','Vídeo sem legenda?','Transcrição no próprio computador, sem custo, com detecção automática do idioma e falas em outro idioma no mesmo episódio.')}
</div>
<div style="margin-top:22px;width:520px;margin-left:auto;margin-right:auto">{shot('ao-vivo')}</div>
</div>{F(8)}"""))

# 9 segurança
pgs.append(page(f"""<div class="in">
<div class="eyebrow">Segurança e privacidade</div><h2>Seu trabalho é seu.</h2>
<p class="lead">O CNT Legendas foi pensado para quem lida com conteúdo confidencial de clientes.</p>
<div class="cols" style="grid-template-columns:repeat(2,1fr);margin-top:26px;gap:16px 22px">
{card('pc','Roda no seu computador','Vídeos e legendas ficam na sua máquina. A transcrição roda no computador e, na tradução com IA, só o texto das legendas segue para o serviço que você escolher.')}
{card('lock','Chaves guardadas com segurança','A chave do serviço de IA fica no cofre de senhas do computador, nunca em arquivo de texto.')}
{card('folder','Originais intocados','O programa nunca altera nem apaga seus arquivos. Os resultados saem ao lado do original, em pasta organizada por mês.')}
{card('shield','Licença protegida e LGPD','Licença assinada, ligada ao computador e conferida ao abrir. Dados tratados conforme a Lei Geral de Proteção de Dados, com termos e política de privacidade.')}
</div></div>{F(9)}"""))

# 10 constante atualização
pgs.append(page(f"""<div class="in">
<div style="display:grid;grid-template-columns:1fr 380px;gap:40px">
<div><span class="tag">Em constante atualização</span><h2 style="margin-top:14px">Um aplicativo que não para de evoluir.</h2>
<p class="lead">O CNT Legendas é desenvolvido em contato direto com quem legenda no dia a dia. Quando você abre o programa, ele procura a versão mais nova e se atualiza sozinho, sem instalador, sem perder seu trabalho, com a lista do que mudou ao reabrir.</p>
<div class="cols" style="grid-template-columns:repeat(3,1fr);margin-top:22px">
 <div class="card" style="text-align:center"><div class="big">2.24</div><p>versão atual</p></div>
 <div class="card" style="text-align:center"><div class="big">20</div><p>idiomas de tradução, com detecção automática</p></div>
 <div class="card" style="text-align:center"><div class="big">3</div><p>sistemas: Windows, Mac e Linux</p></div>
</div>
<div class="card" style="margin-top:16px"><h3>Sugestões viram recursos</h3><p>O botão “Relatar um problema” leva sua mensagem direto à equipe. A equipe de desenvolvimento recebe o relato na hora.</p></div>
</div>
<div><div class="eyebrow" style="margin-bottom:14px">Evoluções recentes</div>
<div class="tl">
<div><i>2.24</i><b>Atualização passo a passo</b> ao abrir, com lista do que mudou</div>
<div><i>2.21</i><b>Legenda ao vivo</b> e <b>audiodescrição</b> em todos os planos</div>
<div><i>2.20</i><b>Tradução ao vivo</b> e audiodescrição com a própria voz</div>
<div><i>2.19</i><b>Audiodescrição</b> no editor</div>
<div><i>2.18</i><b>Legenda ao vivo</b> para transmissões</div>
<div><i>2.17</i><b>Mac e Linux</b></div>
<div><i>2.16</i><b>Status da conexão</b> e modo de diagnóstico</div>
<div><i>2.15</i><b>Formatos de entrega</b>, prazos, histórico de versões, memória de tradução</div>
</div></div></div></div>{F(10)}"""))

# 11 planos
pgs.append(page(f"""<div class="in">
<div class="eyebrow">Planos</div><h2>Todas as funções em todos os planos.</h2>
<p class="lead">Você escolhe só quantos computadores precisa. Cobrança mensal.</p>
<div class="cols" style="grid-template-columns:repeat(3,1fr);margin-top:22px;gap:18px">
<div class="plan"><h3>Individual</h3><div class="pr">R$ 49,90<small> /mês</small></div><span style="font-size:11.5px;color:var(--muted)">Para quem trabalha sozinho</span>
<ul><li>1 computador</li><li>Todas as funções</li><li>Atualizações incluídas</li><li>Suporte pelo próprio programa</li></ul></div>
<div class="plan hl"><h3>Teamwork</h3><div class="pr">R$ 49,90<small> /mês</small></div><span style="font-size:11.5px;color:var(--muted)">+ R$ 29,90 por computador adicional</span>
<ul><li>2 ou mais computadores</li><li>Todas as funções</li><li>Área do cliente com licenças e produção</li><li>Atualizações incluídas</li></ul></div>
<div class="plan"><h3>Business / Enterprise</h3><div class="pr" style="font-size:30px;margin-top:14px">Sob cotação</div><span style="font-size:11.5px;color:var(--muted)">10 ou mais computadores</span>
<ul><li>Workspace da empresa</li><li>Perfis e clientes compartilhados</li><li>Produção da equipe</li><li>Condições sob medida para a equipe</li></ul></div>
</div>
<div class="card" style="margin-top:20px;display:flex;gap:30px;align-items:center">
<div style="flex:1"><h3 style="font-family:Inter;font-weight:700;font-size:14px">Experimente antes</h3><p style="font-size:12px;color:var(--muted);line-height:1.5;margin-top:4px">Todo programa baixado tem 24 horas de avaliação com tudo liberado. Depois, o modo grátis continua disponível para criar projetos e traduzir à mão.</p></div>
<div style="flex:1"><h3 style="font-family:Inter;font-weight:700;font-size:14px">Custo de IA transparente</h3><p style="font-size:12px;color:var(--muted);line-height:1.5;margin-top:4px">A IA usa a chave do próprio cliente: você paga ao provedor só o que usar, sem margem. Também dá para traduzir pelo seu assistente de IA, sem API.</p></div></div>
<p style="font-size:10px;color:#7f8996;margin-top:10px">Valores mensais, sujeitos a alteração. Consulte condições atuais no site.</p>
</div>{F(11)}"""))

# 12 contato
pgs.append(page(f"""
<div style="position:absolute;left:56px;top:48px;width:170px">{LOGO}</div>
<div style="position:absolute;left:56px;top:190px;width:600px">
 <div class="eyebrow">Vamos conversar</div>
 <h1 style="font-size:58px;margin:16px 0 18px">Teste o CNT Legendas <span class="gold">hoje</span>.</h1>
 <p class="lead" style="font-size:15px">Baixe o instalador, use tudo por 24 horas e veja quanto tempo sua equipe ganha por episódio. Se quiser, fazemos uma demonstração com um arquivo do seu próprio fluxo.</p>
 <div style="margin-top:28px;display:flex;flex-direction:column;gap:10px">
  <div class="card" style="display:inline-flex;gap:14px;align-items:center;width:max-content;padding:14px 22px"><span style="color:var(--accent)">{icon_only('cloud',22)}</span><div><div style="font-size:10px;letter-spacing:.18em;color:var(--muted)">SITE E DOWNLOAD</div><div style="font-size:19px;font-weight:700">{SITE}</div></div></div>
 </div>
</div>
<div style="position:absolute;left:700px;top:90px;width:480px;transform:rotate(2deg)">{shot('inicio')}</div>
<div style="position:absolute;left:760px;top:330px;width:420px;transform:rotate(-1.5deg)">{shot('novo-trabalho')}</div>
<div class="foot"><span><b>CNT Legendas</b> · Aplicativo em constante atualização</span><span>{SITE}</span><span>Versão 2.24</span></div>""", 'cover'))

open('comercial.html','w',encoding='utf-8').write(doc('CNT Legendas — Apresentação comercial', css, ''.join(pgs)))
