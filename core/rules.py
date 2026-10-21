"""Regras de estilo de cada perfil (o que pode e o que não pode).

Cada regra é um texto curto numa categoria. As regras ativas vão no pedido de
tradução (API e ChatGPT) e, quando têm uma verificação automática ligada
(`check`), também são conferidas no Verificar/QC.

A usuária edita, desliga e cria regras em cada perfil (inclusive nos prontos;
"Restaurar original" volta ao que vem com o programa).
"""

from __future__ import annotations

import re
import uuid

CATEGORIES = [
    "Interjeições", "Pontuação", "Reticências", "Diálogo", "Quebra de linha", "Texto na tela",
    "Repetição e redundância", "Aspas", "Músicas e orações", "Títulos de obras",
    "Números e medidas", "Itálico", "Posição na tela", "Linguagem e tom", "Palavrões",
    "Nomes", "Outros",
]

# verificações automáticas que uma regra pode ligar (código → descrição)
CHECKS = {
    "interjeicao": "Avisar interjeições (ah, oh, ei, hey…)",
    "pontuacao_dupla": "Avisar pontuação dupla (??, !!, ?!, ¡¿)",
    "reticencias": "Avisar reticências fora do formato do perfil",
    "travessao": "Avisar hífen de diálogo fora do formato do perfil",
    "repeticao": "Avisar palavra repetida (não, não)",
    "abertura": "Avisar ¿ e ¡ faltando (espanhol)",
    "localizacao": "Avisar texto de tela em maiúsculas com ponto final",
    "dois_pontos": "Avisar maiúscula depois de dois-pontos",
    "numero": "Avisar número de 0 a 10 em algarismo",
}


def rule(category: str, text: str, check: str = "", active: bool = True) -> dict:
    return {"id": uuid.uuid5(uuid.NAMESPACE_URL, f"{category}|{text}").hex[:10],
            "category": category, "text": text, "active": active, "check": check}


def clean_rules(raw) -> list[dict]:
    """Valida o que vem da tela: textos vazios saem, categoria e verificação conhecidas."""
    out = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        text = re.sub(r"[ \t]+", " ", str(r.get("text", ""))).strip()
        if not text:
            continue
        cat = str(r.get("category") or "Outros").strip() or "Outros"
        check = str(r.get("check") or "")
        out.append({"id": str(r.get("id") or uuid.uuid4().hex[:10]), "category": cat[:60], "text": text[:2000],
                    "active": bool(r.get("active", True)), "check": check if check in CHECKS else ""})
    return out


def render_rules(rules: list[dict]) -> str:
    """Regras ativas agrupadas por categoria, no texto que vai para a IA."""
    active = [r for r in rules or [] if r.get("active", True) and str(r.get("text", "")).strip()]
    if not active:
        return ""
    order = {c: i for i, c in enumerate(CATEGORIES)}
    groups: dict[str, list[str]] = {}
    for r in active:
        groups.setdefault(r.get("category") or "Outros", []).append(r["text"].strip())
    parts = []
    for cat in sorted(groups, key=lambda c: order.get(c, len(order))):
        parts.append(cat.upper())
        parts.extend(f"- {t}" for t in groups[cat])
    return "\n".join(parts)


def active_checks(rules: list[dict]) -> set[str]:
    return {r["check"] for r in rules or [] if r.get("active", True) and r.get("check")}


# =================================================================== Encripta

ENCRIPTA_ES_RULES = [
    rule("Interjeições", "No uses interjecciones sonoras: Ah, Ay, Ey, Oye, Eh, Ih, Oh, Ei, Ui, Uau, Woo Hoo, Psiu, Oba, Eba, Epa, Opa, Ufa, Hey. Escribe el diálogo sin ellas (\"¡Oh, Dios mío!\" → \"¡Dios mío!\"; \"¡Hey, Sam!\" → \"¡Sam!\").", "interjeicao"),
    rule("Interjeições", "Un saludo \"Hey\" puede traducirse como \"Hola\". Si el subtítulo es solo la interjección, déjalo con el texto más corto posible sin ella."),
    rule("Linguagem e tom", "Ortografía de la RAE y la ASALE, en español neutro (el tratamiento más recurrente en Latinoamérica)."),
    rule("Pontuação", "No uses doble puntuación: nada de \"???\", \"!!!\" ni \"¡¿...?!\".", "pontuacao_dupla"),
    rule("Pontuação", "Usa siempre los signos de apertura ¿ y ¡.", "abertura"),
    rule("Pontuação", "Después de dos puntos (:), minúscula.", "dois_pontos"),
    rule("Reticências", "Puntos suspensivos siempre con tres puntos \"...\", nunca el carácter \"…\".", "reticencias"),
    rule("Reticências", "Respeta las normas gramaticales y, siempre que sea posible, sustitúyelos por una coma. No los uses para marcar una pausa en medio de un mismo diálogo (\"Realmente crees... Crees que soy idiota.\" → \"Realmente crees que soy idiota.\")."),
    rule("Reticências", "Al inicio del subtítulo solo cuando el discurso fue interrumpido (por un personaje o un subtítulo de localización): \"Los denunciaré a todos...\" / \"...por estar robando.\""),
    rule("Reticências", "Pausa para pensar y la frase continúa: puntos suspensivos al final y la siguiente en minúscula (\"Es muy difícil...\" / \"aceptar ese amor.\"). Si después viene una frase nueva, empieza con mayúscula."),
    rule("Reticências", "Pregunta con pausa: \"¿Cómo te sentiste...\" / \"al hablar con tu padre?\""),
    rule("Diálogo", "Guion SIN espacio (\"-Texto\") y solo en diálogos de dos personajes que aparecen al mismo tiempo en pantalla, uno por línea: \"-¿Puedes ayudarme?\" / \"-Por supuesto que sí.\"", "travessao"),
    rule("Quebra de linha", "Mantén el texto en una sola línea siempre que quepa (máximo 42 caracteres)."),
    rule("Quebra de linha", "Divide solo después de puntuación, antes de preposición (por, con, de...) o antes de conjunción (porque, y...). No separes artículo de sustantivo, sustantivo de adjetivo, nombre de apellido, verbo de objeto, ni adverbio del verbo. Prefiere la línea de abajo más larga."),
    rule("Texto na tela", "Traduce la información en pantalla relevante y no redundante (letreros, matrículas, aeropuertos, establecimientos). Lo que no tiene traducción no se subtitula."),
    rule("Texto na tela", "Subtítulos de localización en MAYÚSCULAS y sin punto final, salvo textos informativos, cartas y mensajes (puntuación como en pantalla). Nunca en cursiva.", "localizacao"),
    rule("Texto na tela", "Fechas en estándar latinoamericano (día, mes, año); los números exactamente como aparecen en pantalla."),
    rule("Texto na tela", "Localización + diálogo en el mismo subtítulo: en el orden en que aparecen; solo el diálogo lleva guion (\"CHERNOBYL, 26 DE ABRIL DE 1986\" / \"-Me acuerdo de ese día.\")."),
    rule("Repetição e redundância", "No repitas palabras o frases: \"No, no, no. Ya te dije que no.\" → \"No. Ya te dije que no.\"", "repeticao"),
    rule("Repetição e redundância", "Pregunta y respuesta idénticas en un diálogo: cambia una por un sinónimo (\"-¿De acuerdo?\" / \"-Sí.\"). Evita redundancias; adapta con sinónimos."),
    rule("Aspas", "Comillas rectas (\"). El punto va después de cerrar las comillas. Al inicio y al final de cada oración, no de cada subtítulo."),
    rule("Aspas", "Usa comillas en errores de pronunciación intencionales, juegos de palabras, citas, nombres de canciones y cuando el personaje lee algo. Cita dentro de cita con apóstrofes: \"Charlie dijo: 'Todo está bien'\"."),
    rule("Músicas e orações", "Canciones (cantadas o reproducidas) y oraciones: siempre en cursiva; primera letra de cada línea en mayúscula (también al dividir la línea); sin punto final; coma solo en medio de la frase; conserva ¿? y ¡!."),
    rule("Títulos de obras", "Películas, libros, juegos o programas: título oficial en español; si no existe, el original. En cursiva y sin comillas."),
    rule("Números e medidas", "Del 0 al 10 con letras. Si un número inicia la línea, escríbelo con letras o adapta (\"30 días\" → \"Son 30 días\").", "numero"),
    rule("Números e medidas", "Dólares: US$ (US$ 1,4 millones); valores pequeños o redondos, con letras (\"seis dólares\")."),
    rule("Números e medidas", "Sistema métrico y porcentaje con espacio: 300 km, 50 cm, 12 kg, 2 %, 100 %. Temperatura según CPS: \"600 grados\" o \"600 °C\". Ordinales según contexto (1.º Regimiento / el primer hijo)."),
    rule("Números e medidas", "Hora en formato de 12 horas: \"7:00 a. m.\", \"3:15 p. m.\""),
    rule("Itálico", "Cursiva (<i>...</i>) solo cuando: quien habla no aparece en la toma; voz en off o narración; idioma distinto al original; multitud sin hablante identificable; voz de dispositivo electrónico; títulos de obras; palabras extranjeras no registradas en la RAE."),
    rule("Itálico", "Sin cursiva en conversaciones ping-pong, una vez identificado el personaje, en voces demoníacas o de fantasmas, ni en escenas con micrófono."),
    rule("Posição na tela", "Si el subtítulo tapa algo escrito en pantalla (lugar, letreros, periódico, nombres, créditos), comienza la primera línea con {\\an8}. Conserva las etiquetas {\\an8} del original."),
]

ENCRIPTA_PT_RULES = [
    rule("Interjeições", "Não use interjeições sonoras: Ah, Oh, Ei, Ui, Uau, Psiu, Oba, Eba, Epa, Opa, Ufa, Hey, Eh, Ih. Escreva a fala sem elas (\"Ah, meu Deus!\" → \"Meu Deus!\"). Um \"Hey\" de cumprimento pode virar \"Oi\".", "interjeicao"),
    rule("Linguagem e tom", "Ortografia do português do Brasil (Acordo Ortográfico), natural, como se fala."),
    rule("Pontuação", "Sem pontuação dupla (\"???\", \"!!!\", \"?!\").", "pontuacao_dupla"),
    rule("Pontuação", "Depois de dois-pontos (:), minúscula.", "dois_pontos"),
    rule("Reticências", "Reticências sempre com três pontos \"...\", nunca o caractere \"…\".", "reticencias"),
    rule("Reticências", "Prefira vírgula quando possível; não use reticências para pausa no meio da mesma fala. No início da legenda só quando a fala foi interrompida (\"...por estar roubando.\"). Pausa e a frase continua: reticências no fim e a seguinte em minúscula."),
    rule("Diálogo", "Hífen SEM espaço e só em diálogo de dois personagens que aparecem ao mesmo tempo, um por linha: \"-Você pode me ajudar?\" / \"-Claro que sim.\"", "travessao"),
    rule("Quebra de linha", "Uma linha só sempre que couber. Quebre só depois de pontuação, antes de preposição ou de conjunção; não separe artigo e substantivo, substantivo e adjetivo, nome e sobrenome, verbo e objeto, advérbio e verbo. Prefira a linha de baixo maior."),
    rule("Texto na tela", "Legendas de localização (texto relevante na tela) em MAIÚSCULAS, sem ponto final (exceto textos informativos, cartas e mensagens), nunca em itálico. Datas no padrão dia/mês/ano; números como aparecem na tela.", "localizacao"),
    rule("Texto na tela", "Localização + diálogo na mesma legenda: na ordem em que aparecem; só o diálogo leva hífen."),
    rule("Repetição e redundância", "Não repita palavras (\"Não, não, não. Eu já disse que não.\" → \"Não. Eu já disse que não.\"); evite redundâncias; use sinônimos em perguntas e respostas iguais.", "repeticao"),
    rule("Aspas", "Aspas retas (\"). Use em erros de pronúncia intencionais, trocadilhos, citações, nomes de músicas e quando o personagem lê algo; citação dentro de citação com aspas simples."),
    rule("Músicas e orações", "Músicas e orações: sempre em itálico, inicial maiúscula em cada linha, sem ponto final, vírgula só no meio da frase, mantenha ? e !."),
    rule("Títulos de obras", "Filmes, livros, jogos e programas: título oficial no Brasil (ou o original, se não houver), em itálico e sem aspas."),
    rule("Números e medidas", "Números de zero a dez por extenso; número no início da linha por extenso ou adapte a frase. Dólares: US$. Sistema métrico com espaço: 300 km, 12 kg.", "numero"),
    rule("Itálico", "Itálico (<i>...</i>) só quando quem fala não aparece na cena, narração/voz em off, idioma diferente do original, multidão sem falante identificável, voz de aparelho eletrônico, títulos de obras e palavras estrangeiras. Não use em conversas pingue-pongue, depois que o personagem foi identificado, em vozes demoníacas/fantasmas nem em cenas com microfone."),
    rule("Posição na tela", "Se a legenda cobrir texto na tela, comece a primeira linha com {\\an8}; conserve os {\\an8} do original."),
]

# ==================================================================== Netflix
# Base: Timed Text Style Guides da Netflix (geral + idioma). Conferir com a versão
# atual do guia; tudo aqui é editável no perfil.

_NETFLIX_COMMON_PT = [
    rule("Interjeições", "Interjeições são permitidas quando fazem parte do sentido ou do tom da fala (\"Ah, que coisa!\"). Corte as que não acrescentam nada, principalmente se faltar espaço."),
    rule("Palavrões", "Mantenha palavrões e linguagem forte no mesmo nível do original; não censure nem suavize, a não ser que o cliente peça."),
    rule("Repetição e redundância", "Repetições de hesitação (\"não, não, não\") podem ser reduzidas quando a velocidade de leitura apertar; mantenha quando forem parte do efeito da fala."),
    rule("Quebra de linha", "Uma linha só quando couber. Em duas linhas, quebre depois de pontuação ou antes de conjunção/preposição; prefira a linha de baixo maior (pirâmide) sem forçar."),
    rule("Itálico", "Itálico (<i>...</i>) para quem fala fora da cena, narração, voz de aparelhos (telefone, rádio, TV), letras de música e palavras estrangeiras que não sejam de uso comum."),
    rule("Texto na tela", "Texto na tela relevante para a história (placas, mensagens, documentos) é legendado; não legende o que já está no idioma da legenda ou é redundante."),
    rule("Músicas e orações", "Letras de música só quando forem importantes para a história; em itálico."),
    rule("Títulos de obras", "Use o título oficial lançado no país; se não houver, mantenha o original."),
    rule("Posição na tela", "Se a legenda cobrir texto importante ou créditos, suba-a com {\\an8} no começo da primeira linha."),
]

NETFLIX_ES_RULES = [
    rule("Linguagem e tom", "Español neutro latinoamericano: evita regionalismos de un solo país; usa \"ustedes\" (nunca \"vosotros\")."),
    rule("Pontuação", "Usa siempre los signos de apertura ¿ y ¡. No combines ?! ni pongas punto después de ? o !.", "abertura"),
    rule("Pontuação", "Sin pontuação dupla (??, !!).", "pontuacao_dupla"),
    rule("Números e medidas", "Números de uno a diez con letras; a partir de 11 en cifras (excepto \"cien\" y \"mil\").", "numero"),
    rule("Diálogo", "Diálogo de dos personajes en el mismo subtítulo: una línea por personaje, cada una con guion.", "travessao"),
    *_NETFLIX_COMMON_PT,
]

NETFLIX_PT_RULES = [
    rule("Linguagem e tom", "Português do Brasil natural, como se fala: \"você\", \"a gente\" quando couber; nada de português de Portugal."),
    rule("Pontuação", "Sem pontuação dupla (??, !!).", "pontuacao_dupla"),
    rule("Números e medidas", "Números de um a dez por extenso; a partir de 11 em algarismos.", "numero"),
    rule("Diálogo", "Diálogo de dois personagens na mesma legenda: uma linha por personagem, cada uma com hífen.", "travessao"),
    *_NETFLIX_COMMON_PT,
]
