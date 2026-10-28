from lib import *
css = """
@page{size:297mm 210mm;margin:0}
.pg{width:297mm;height:210mm}
.in{position:absolute;inset:0 0 34px 0;padding:34px 48px 0}
h2{font-size:34px;margin:6px 0 8px}
.lead{font-size:13.5px;line-height:1.5;color:var(--muted)}
.grid{display:grid;gap:26px;height:calc(100% - 40px);align-items:center}
.card h3{font-family:Inter;font-size:14px;font-weight:700;margin-bottom:5px}
.card p,.card li{font-size:12px;line-height:1.5;color:var(--muted)}
.card ul{list-style:none}.card li{padding:3px 0 3px 14px;position:relative}.card li:before{content:'';position:absolute;left:0;top:10px;width:6px;height:6px;border-radius:50%;background:var(--accent)}
.fl{list-style:none;margin-top:10px}
.fl li{display:flex;gap:11px;padding:8px 0;border-bottom:1px solid var(--line);font-size:12px;line-height:1.45;color:var(--muted)}
.fl li b{color:var(--ink);font-weight:600}
.num{flex:0 0 22px;height:22px;border-radius:50%;background:var(--accent);color:var(--on);font-weight:700;font-size:11px;display:flex;align-items:center;justify-content:center;margin-top:1px}
.bd{position:absolute;width:22px;height:22px;border-radius:50%;background:var(--accent);color:var(--on);font-weight:700;font-size:11px;display:flex;align-items:center;justify-content:center;transform:translate(-50%,-50%);box-shadow:0 0 0 3px rgba(22,25,29,.8)}
.rel{position:relative}
.cover{background:radial-gradient(900px 600px at 15% 90%,rgba(221,176,106,.15),transparent 60%),linear-gradient(135deg,#14171b,#1b2027 60%,#241f17)}
table{border-collapse:collapse;width:100%}
th{font-family:Inter;text-align:left;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);padding:6px 10px;border-bottom:2px solid var(--accent)}
td{font-size:12.6px;line-height:1.45;padding:9px 10px;border-bottom:1px solid var(--line);color:#cfd5db;vertical-align:top}
td:first-child{font-weight:700;color:var(--ink);width:150px}
.pill{display:inline-block;font-size:10.5px;border:1px solid var(--line);background:var(--panel2);border-radius:999px;padding:3px 10px;margin:2px 3px 2px 0;color:#cfd5db}
.box{border:1px solid rgba(221,176,106,.4);background:rgba(221,176,106,.08);border-radius:12px;padding:12px 16px;font-size:12px;color:#e6dcc8;line-height:1.5}
.flow{display:flex;align-items:stretch;gap:8px}
.flow>div{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;font-size:11.5px;color:var(--muted);line-height:1.4}
.flow b{display:block;color:var(--accent);font-family:Anton;font-size:20px;margin-bottom:2px;font-weight:400}
.flow .ar{flex:0 0 14px;background:none;border:0;padding:0;display:flex;align-items:center;color:var(--accent);font-size:18px}
"""
F=lambda n:f'<div class="foot"><span><b>CNT Legendas</b> · Ficha técnica e tour das telas</span><span>Aplicativo em constante atualização · Versão 2.24</span><span>{n}</span></div>'
pgs=[]; n=[1]
def nx(): n[0]+=1; return n[0]
def fl(items): return '<ul class="fl">'+''.join(f'<li><span class="num">{i+1}</span><span><b>{t}</b> {d}</span></li>' for i,(t,d) in enumerate(items))+'</ul>'
def bd(x,y,i): return f'<div class="bd" style="left:{x}%;top:{y}%">{i}</div>'
def tela(eyebrow,title,lead,img,items,badges=(),side='right',w=640):
    b=''.join(bd(x,y,i+1) for i,(x,y) in enumerate(badges))
    img_html=f'<div class="rel" style="width:{w}px">{shot(img)}{b}</div>'
    txt=f'<div style="flex:1"><div class="eyebrow">{eyebrow}</div><h2>{title}</h2><p class="lead">{lead}</p>{fl(items)}</div>'
    order=(img_html+txt) if side=='left' else (txt+img_html)
    return page(f'<div class="in"><div style="display:flex;gap:30px;align-items:center;height:100%">{order}</div></div>'+F(nx()))

# capa
pgs.append(page(f"""
<div style="position:absolute;left:56px;top:48px;width:170px">{LOGO}</div>
<div style="position:absolute;left:56px;top:170px;width:560px">
<div class="eyebrow">Ficha técnica · Tour pelas telas</div>
<h1 style="font-size:58px;margin:16px 0 18px">Conheça cada função do <span class="gold">CNT Legendas</span>.</h1>
<p class="lead" style="font-size:15px">Um passeio pelas telas reais do programa, com o que cada uma faz, os padrões de legendagem que ele segue e como a licença e as atualizações funcionam.</p>
<div style="margin-top:24px"><span class="tag">Aplicativo em constante atualização</span></div></div>
<div style="position:absolute;left:660px;top:120px;width:520px;transform:rotate(2deg)">{shot('editor')}</div>
<div style="position:absolute;left:720px;top:330px;width:420px;transform:rotate(-2deg)">{shot('sincronizar')}</div>
<div class="foot"><span><b>CNT Legendas</b> · Ficha técnica e tour das telas</span><span>{SITE}</span><span>Versão 2.24</span></div>""",'cover'))

# visão geral
pgs.append(page(f"""<div class="in"><div class="eyebrow">Visão geral</div><h2>Programa instalado, trabalho local.</h2>
<p class="lead" style="max-width:760px">O CNT Legendas é um programa com instalador para Windows (também disponível para Mac com chip Apple e para Linux). Ele abre numa janela própria e guarda um ícone na bandeja do sistema. Todo o trabalho acontece no computador do usuário; o servidor da CNT cuida apenas de licenças, atualizações e da área do cliente.</p>
<div class="flow" style="margin:20px 0">
<div><b>Arquivos</b>Legenda do cliente (.srt), vídeo, ou só o vídeo para transcrever</div><div class="ar">›</div>
<div><b>Traduzir</b>IA com glossário e regras do cliente, ou assistente de IA sem API</div><div class="ar">›</div>
<div><b>Sincronizar</b>Pela fala do vídeo, por referência, por pontos ou por cortes de cena</div><div class="ar">›</div>
<div><b>Verificar</b>Velocidade de leitura, duração, intervalos, linhas e regras de estilo</div><div class="ar">›</div>
<div><b>Entregar</b>.srt, .vtt, .ttml ou .ass, com assinatura e relatório</div></div>
<div class="grid" style="grid-template-columns:repeat(3,1fr);height:auto;align-items:stretch">
<div class="card"><h3>No computador</h3><ul><li>Editor, verificação e sincronia</li><li>Transcrição de vídeo, sem custo</li><li>Projetos, clientes e glossários</li><li>Chaves de IA no cofre de senhas do sistema</li></ul></div>
<div class="card"><h3>No servidor CNT</h3><ul><li>Licença assinada e ativação por código</li><li>Atualizações do programa</li><li>Área do cliente: licenças, produção, pedidos e dados</li><li>Perfil na nuvem e Workspace da empresa</li></ul></div>
<div class="card"><h3>Requisitos</h3><ul><li>Windows 10 ou 11 de 64 bits (Mac com chip Apple e Linux também)</li><li>Internet para ativar, atualizar e usar IA</li><li>Modelos de voz baixados uma vez, no primeiro uso</li><li>Placa de vídeo é aproveitada quando existe</li></ul></div></div>
</div>"""+F(nx())))

pgs.append(tela('Tela inicial','Início: tudo organizado por mês.','Abre sempre no mês atual, com uma pasta por mês e uma por projeto. O programa mostra o que está em andamento e qual é o próximo passo de cada trabalho.','inicio',[
('Navegação por mês','troque de mês nas setas; os trabalhos antigos achados na pasta aparecem sozinhos.'),
('Novo trabalho e legenda solta','crie um trabalho em três perguntas ou abra um .srt direto no editor.'),
('Resumo do mês','em andamento, entregues e “continuar de onde parou”.'),
('Lista de projetos','progresso, próximo passo e botão para abrir. Dicas “?” explicam cada item.')],
[(21.5,12),(42,23),(35,31),(58,42)],'right',600))

pgs.append(tela('Novo trabalho','Três perguntas e pronto.','O assistente de novo trabalho coloca arquivos, cliente e idiomas no lugar certo, sem o usuário precisar organizar pastas.','novo-trabalho',[
('O que você vai fazer','traduzir uma legenda, legendar um vídeo (transcrição no computador) ou acertar o tempo de uma legenda existente.'),
('Para quem e qual episódio','cliente, projeto, temporada, episódio, idiomas de origem e destino e prazo de entrega opcional.'),
('Arquivos','legenda do cliente e vídeo (opcional, para conferir). São copiados para a pasta do episódio; os originais ficam intactos.')],
[(30,27),(30,50),(30,76)],'left',600))

pgs.append(tela('Projeto','Filmes e séries, episódio por episódio.','Cada episódio avança pela mesma trilha: Arquivos, Traduzir, Revisar e Entregar. O botão destacado sempre indica a ação seguinte.','projeto',[
('Trilha de quatro passos','mostra em que etapa cada episódio está.'),
('Episódios','crie temporadas e episódios em qualquer ordem (por exemplo “1-6” ou “1, 7”) e dê um título a cada um.'),
('Ação seguinte','um clique leva ao editor já com o arquivo certo. O menu “⋯” traz as demais opções.'),
('Situação do projeto','novo, em andamento ou finalizado; pode ser reaberto e vinculado a um cliente.')],
[(55,29),(50,42),(87,42)],'right',600))

pgs.append(tela('Editor','Editor profissional de legendas.','Área de trabalho completa: grade, vídeo com a legenda sobreposta, painel de edição e forma de onda. As áreas podem ser arrastadas e dimensionadas.','editor',[
('Barra de ações','traduzir, revisar, sincronizar, verificar (com contador de avisos), entregar, audiodescrição, desfazer/refazer, localizar e histórico de versões.'),
('Grade','início, fim, duração e velocidade de leitura (CPS) com destaque em cor quando passa do limite do perfil.'),
('Vídeo','prévia com itálico, negrito, cor e posição aplicados; quadro exato; reprodução com velocidade variável.'),
('Painel de edição','texto, tempos, contagem de linhas e caracteres, quebra automática, dividir e juntar.'),
('Forma de onda','arraste início e fim; marque entradas e saídas com F11 e F12; abas Criar e Ajustar.'),
('Barra de status','legenda atual, avisos de revisão, perfil de regras em uso e estado de salvamento (rascunho automático).')],
[(38,3),(30,18),(78,28),(7.5,60),(45,82),(10,98.6)],'left',660))

pgs.append(tela('Traduzir e revisar','Dois jeitos de traduzir, um resultado.','Antes de começar, o usuário escolhe cliente, glossário e perfil de regras. A legenda de origem nunca é alterada: o resultado vira um arquivo novo ao lado dela.','traduzir',[
('Pelo assistente de IA (sem API)','o programa divide em partes de 100, copia cada parte com as instruções, o usuário cola a resposta e o programa confere, pede só o que faltou e monta o arquivo.'),
('Automática (pela API)','lotes de 80 legendas com o contexto das vizinhas, resposta validada, limite de caracteres pela duração, estimativa de custo e retomada por lote. Serviços e modelos configuráveis.'),
('Revisão no mesmo idioma','a IA corrige ortografia, gramática e pontuação, aplica as regras do perfil e condensa o que passa da velocidade de leitura.'),
('Memória de tradução','trechos já traduzidos podem ser reaproveitados, com corretor ortográfico no editor.')],
[],'right',620))

pgs.append(tela('Sincronizar','Nove maneiras de acertar o tempo.','O menu Sincronizar reúne desde o acerto automático pela voz até ajustes manuais, todos com explicação em linguagem simples.','sincronizar',[
('Sincronia precisa pela fala','separa a voz da música e do chiado e acerta início e fim, quadro a quadro; usa a placa de vídeo se houver.'),
('Automática (rápida) e só início e fim','desloca a legenda fora do lugar e acerta entradas e saídas pela fala.'),
('Por referência e copiando tempos','usa outra legenda com o tempo certo, mesmo em outro idioma.'),
('Ajustes diretos','atrasar ou adiantar, por dois pontos e converter quadros por segundo.'),
('Cortes de cena e roteiro','encaixa nos cortes do vídeo e transforma texto sem tempo (.txt, .docx) em legenda sincronizada.')],
[],'left',640))

# verificar + entregar
pgs.append(page(f"""<div class="in"><div class="eyebrow">Qualidade e entrega</div><h2>Conferir antes de enviar.</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:12px">
<div>{shot('verificar')}<ul class="fl"><li><span class="num">1</span><span><b>Verificar</b> lista erros e avisos por legenda: velocidade de leitura, duração, intervalo, linhas e caracteres, sobreposição e regras de estilo do cliente.</span></li><li><span class="num">2</span><span><b>Corrigir tempos e estilo</b> aplica os ajustes automáticos e fecha intervalos curtos.</span></li></ul></div>
<div>{shot('entregar')}<ul class="fl"><li><span class="num">3</span><span><b>Entregar</b> define nome do arquivo, formato (.srt, .vtt, .ttml ou .ass), pasta, assinatura no fim e relatório de verificação (.qc.txt).</span></li><li><span class="num">4</span><span><b>Formato por nível:</b> padrão geral, por equipe, por cliente ou por projeto.</span></li></ul></div></div></div>"""+F(nx())))

pgs.append(tela('Ao vivo','Legenda ao vivo para transmissões e eventos.','Ouve uma entrada de áudio e gera a legenda na hora. Cada legenda espera alguns segundos numa fila, para o operador corrigir antes de ir à tela.','ao-vivo',[
('Entrada e reconhecimento','microfone, som do computador, placa de áudio, arquivo ou endereço; idioma falado, precisão e tradução ao vivo.'),
('Controle de qualidade','glossário do cliente para nomes certos, palavras para esconder (aparecem como ***) e texto pronto que entra na hora.'),
('Na tela','legenda inteira ou rolante, fundo transparente ou de recorte, tamanho, posição e faixa de tradução.'),
('Saída','endereço para o programa de transmissão (fonte de navegador), janela de legenda própria e arquivo .srt do evento, que abre no editor.')],
[],'right',600))

pgs.append(tela('Audiodescrição','Descrever o que se vê, no tempo certo.','Ferramenta dentro do editor para criar a faixa de audiodescrição respeitando os espaços sem fala.','audiodescricao',[
('Espaços sem fala','o programa acha as janelas em que a descrição cabe.'),
('Verificação','confere se o texto cabe no tempo, pela velocidade da voz escolhida.'),
('Sugestão por IA','propõe descrições a partir de quadros do vídeo, para o autor revisar.'),
('Voz','ouvir com a voz do sistema ou gravar com a própria voz.'),
('Exportação','roteiro (.docx ou .txt), .ttml, faixa e áudio mixado ao original.')],
[],'left',620))

pgs.append(tela('Relatórios','Produção medida, não estimada.','Métricas guardadas com data para cada projeto e episódio, com filtros por período, cliente e situação e exportação para planilha.','relatorios',[
('Painel geral','projetos, episódios, vídeo legendado e tempo trabalhado.'),
('Produtividade','legendas, palavras e minutos de vídeo por hora.'),
('Texto, tempo e leitura','linhas, caracteres, duração média, CPS médio e máximo e quantas legendas passam do limite.'),
('Exportar (CSV)','dados prontos para planilha, para fechar faturamento e acompanhar a equipe.')],
[],'right',620))

pgs.append(tela('Configurações','O dia a dia em cima, o técnico embaixo.','Uma linha por assunto, com dicas “?” que explicam o que é, quando usar e o que acontece com os arquivos. Itens técnicos ficam recolhidos em “Avançado”.','configuracoes',[
('Licença e versão','plano, validade e ativação por código; procura de atualização e novidades da versão.'),
('Perfil na nuvem','configurações, clientes, glossários e regras guardados no servidor; restaure em um computador novo.'),
('Clientes, glossário e perfis de regras','glossário geral, por cliente e por projeto (o mais específico vale).'),
('Tradução automática','serviço de IA, modelos e chaves.'),
('Suporte','modo de depuração e diagnóstico, relatar um problema e trabalhos em segundo plano.')],
[],'left',620))

# tabela de funções
rows=[('Projetos','Pastas por mês; filmes e séries com temporadas e episódios; clientes; prazo de entrega por episódio; status; retomar de onde parou.'),
('Tradução','IA pela API (vários serviços de IA à escolha, inclusive gateways compatíveis) ou pelo assistente de IA do próprio usuário, sem API; 20 idiomas com detecção automática; revisão no mesmo idioma; memória de tradução.'),
('Transcrição','Vídeo sem legenda vira legenda no próprio computador, sem custo; falas em outro idioma no mesmo episódio; japonês e chinês tratados sem espaços.'),
('Sincronia','Precisa pela fala, automática, só início e fim, por referência, copiar tempos, atrasar/adiantar, dois pontos, conversão de quadros, cortes de cena, texto sem tempo.'),
('Edição','Grade, vídeo, forma de onda, quebra automática, dividir/juntar, localizar e substituir, corretor ortográfico, desfazer, histórico de versões, rascunho automático, cópia de segurança.'),
('Qualidade','Perfis de regras por idioma e por cliente, verificação automática com correção, relatório .qc.txt.'),
('Entrega','.srt (padrão), .vtt, .ttml e .ass; nome, assinatura no fim e pasta de entrega; formato por equipe, cliente ou projeto.'),
('Acessibilidade','Legenda ao vivo com tradução; audiodescrição com sugestão por IA, voz do sistema ou gravada, roteiro e áudio mixado.'),
('Gestão','Relatórios e exportação CSV; Workspace da empresa; perfil na nuvem; glossário em três níveis.'),
('Operação','Atualização automática; aviso de trabalho concluído na bandeja; trabalhos em segundo plano; diagnóstico; relatar um problema.')]
pgs.append(page(f"""<div class="in"><div class="eyebrow">Resumo</div><h2>Mapa completo de funções.</h2>
<table style="margin-top:8px"><tr><th>Área</th><th>O que o programa faz</th></tr>{''.join(f'<tr><td>{a}</td><td>{b}</td></tr>' for a,b in rows)}</table></div>"""+F(nx())))

# padrões
idi=['Português (Brasil)','Espanhol (América Latina)','Espanhol (Espanha)','Inglês','Italiano','Francês','Alemão','Russo','Turco','Persa','Japonês','Chinês (mandarim)','Grego','Latim','Coreano','Árabe','Hindi','Indonésio','Holandês','Polonês','Hebraico']
pgs.append(page(f"""<div class="in"><div class="eyebrow">Padrões de legendagem</div><h2>Regras prontas, ajustáveis por cliente.</h2>
<div class="grid" style="grid-template-columns:1fr 1fr;align-items:start;height:auto;margin-top:12px">
<div class="card"><h3>Perfis embutidos (português e espanhol, adulto e infantil)</h3>
<table><tr><th>Parâmetro</th><th>Adulto</th><th>Infantil</th></tr>
<tr><td>Caracteres por linha</td><td>42</td><td>42</td></tr><tr><td>Linhas por legenda</td><td>2</td><td>2</td></tr>
<tr><td>Velocidade de leitura</td><td>17 CPS</td><td>13 CPS</td></tr><tr><td>Duração</td><td>5/6 s a 7 s</td><td>5/6 s a 7 s</td></tr><tr><td>Intervalo</td><td>2 quadros</td><td>2 quadros</td></tr></table>
<p style="margin-top:10px">Baseados nas diretrizes de tempo e estilo das grandes plataformas de streaming. Cada idioma tem seus próprios limites (por exemplo, japonês, chinês e coreano usam menos caracteres por linha).</p></div>
<div class="card"><h3>Perfis de clientes</h3><p>Cada cliente pode ter manual próprio: CPS ideal, intervalo em milissegundos, hífen e reticências, nome do arquivo e regras de estilo com verificação automática (interjeições, pontuação dupla, repetição, ¿ ¡, texto de tela, números). Os perfis são arquivos que se importam e exportam, e os manuais confidenciais ficam apenas no computador do usuário.</p>
<h3 style="margin-top:12px">Formatos e idiomas</h3><p><b style="color:var(--ink)">Entrada:</b> .srt, texto sem tempo (.txt, .docx) e vídeo. <b style="color:var(--ink)">Saída:</b> .srt, .vtt, .ttml e .ass.</p>
<div style="margin-top:6px">{''.join(f'<span class="pill">{i}</span>' for i in idi)}</div></div></div></div>"""+F(nx())))

# licença segurança atualização
pgs.append(tela('Licença, segurança e atualização','Controle para a empresa, sem atrito para a equipe.','Licenciamento por código de ativação e atualização automática, sem que o usuário precise reinstalar o programa.','licenca',[
('Avaliação e modo grátis','24 horas com tudo liberado; depois, projetos e edição manual continuam grátis.'),
('Licença assinada','código de uso único, ligado ao computador e conferido ao abrir; funciona até 30 dias sem internet.'),
('Troca de computador','a vaga é liberada pela área do cliente.'),
('Dados e LGPD','só o necessário para controle de licença; termos e política de privacidade publicados no site.'),
('Atualização automática','ao abrir, o programa baixa a versão aprovada, instala, reinicia e mostra o que mudou.')],
[],'right',560))

pgs.append(page(f"""
<div style="position:absolute;left:56px;top:48px;width:170px">{LOGO}</div>
<div style="position:absolute;left:56px;top:160px;width:620px"><span class="tag">Em constante atualização</span>
<h1 style="font-size:54px;margin:16px 0 16px">O CNT Legendas continua <span class="gold">evoluindo</span>.</h1>
<p class="lead" style="font-size:15px">Este documento descreve a versão 2.24. Novos recursos, ajustes e melhorias chegam com frequência e são instalados automaticamente, sem custo adicional para quem tem licença ativa.</p>
<div class="card" style="margin-top:24px;display:inline-flex;gap:14px;align-items:center;padding:14px 22px"><span style="color:var(--accent)">{icon_only('cloud',22)}</span><div><div style="font-size:10px;letter-spacing:.18em;color:var(--muted)">SITE E DOWNLOAD</div><div style="font-size:19px;font-weight:700">{SITE}</div></div></div></div>
<div style="position:absolute;left:740px;top:130px;width:420px;transform:rotate(2deg)">{shot('tema-claro')}</div>
<div style="position:absolute;left:700px;top:340px;width:400px;transform:rotate(-2deg)">{shot('novo-trabalho')}</div>
<div class="foot"><span><b>CNT Legendas</b> · Ficha técnica e tour das telas</span><span>{SITE}</span><span>Versão 2.24</span></div>""",'cover'))
open('tecnico.html','w',encoding='utf-8').write(doc('CNT Legendas — Ficha técnica e tour das telas',css,''.join(pgs)))
