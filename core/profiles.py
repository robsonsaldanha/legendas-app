"""Perfis de regras de legendagem.

Valores dos perfis Netflix conferidos no "Timed Text Style Guide" de cada idioma
(42 caracteres por linha, 17 CPS adulto / 13 CPS infantil) e nas diretrizes
gerais de timing da Netflix (duração mínima 5/6 s, máxima 7 s, intervalo de
2 quadros). Ver brain/regras-legendagem.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class Profile:
    name: str
    language: str = "es-419"
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_cps: float = 17.0
    min_duration: float = 5 / 6       # segundos
    max_duration: float = 7.0         # segundos
    min_gap_frames: int = 2           # intervalo mínimo entre legendas, em quadros
    default_fps: float = 24000 / 1001  # usado quando o FPS do vídeo é desconhecido
    # Pausa na fala (s) a partir da qual vale a pena começar nova legenda.
    pause_break: float = 0.6
    # Quanto a legenda pode "segurar" na tela depois da última palavra (s).
    linger: float = 0.5
    # Contar espaços no CPS (a Netflix conta todos os caracteres, incluindo espaços).
    cps_count_spaces: bool = True
    dialogue_dash: str = "- "
    notes: str = ""
    extra: dict = field(default_factory=dict)
    # CPS ideal (o Formatar mira nele ao montar legendas); o QC só reclama acima de max_cps.
    optimal_cps: float | None = None
    # Intervalo mínimo em milissegundos (tem prioridade sobre min_gap_frames).
    min_gap_ms: float | None = None
    # Reticências: "…" (caractere único, Netflix) ou "..." (três pontos).
    ellipsis: str = "…"
    # Manual do cliente: instruções de estilo enviadas à tradução (API e ChatGPT).
    guide: str = ""
    # Nome dos arquivos: "" → Nome.es-419.srt ; "encripta" → Nome_sub_spa.srt
    naming: str = ""
    # Verificações de estilo do cliente no QC (interjeições, pontuação dupla etc.).
    style_checks: bool = False
    # Intervalos menores que isto (em quadros) são fechados no intervalo mínimo
    # pela correção automática (Netflix: 12). 0 = não encadeia.
    chain_frames: int = 0
    # Encaixe nos cortes de cena (quadros): janela e distância antes do corte.
    shot_window_frames: int = 12
    shot_gap_frames: int = 2

    def min_gap(self, fps: float | None = None) -> float:
        if self.min_gap_ms:
            return self.min_gap_ms / 1000
        return self.min_gap_frames / (fps or self.default_fps)

    @property
    def target_cps(self) -> float:
        return self.optimal_cps or self.max_cps

    def gap_label(self) -> str:
        return f"{self.min_gap_ms:g} ms" if self.min_gap_ms else f"{self.min_gap_frames} quadros"

    @property
    def max_cue_chars(self) -> int:
        return self.max_chars_per_line * self.max_lines

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


NETFLIX_ES_419 = Profile(
    name="Netflix — Espanhol (LatAm)",
    chain_frames=12,
    language="es-419",
    notes="Netflix Spanish (Latin America & Spain) TTSG: 42 CPL, 17 CPS adulto.",
)

NETFLIX_ES_419_KIDS = Profile(
    name="Netflix — Espanhol (LatAm) infantil",
    chain_frames=12,
    language="es-419",
    max_cps=13.0,
    notes="Programas infantis: 13 CPS.",
)

NETFLIX_PT_BR = Profile(
    name="Netflix — Português (Brasil)",
    chain_frames=12,
    language="pt-BR",
    notes="Netflix Brazilian Portuguese TTSG: 42 CPL, 17 CPS adulto.",
)

NETFLIX_PT_BR_KIDS = Profile(
    name="Netflix — Português (Brasil) infantil",
    chain_frames=12,
    language="pt-BR",
    max_cps=13.0,
)

# ------------------------------------------------------------------ Encripta
# Fonte: "Manual de traducción y subtítulos en español 3.0" da Encripta (configuração
# do Subtitle Edit nas páginas 4–11 e critérios técnicos na página 15).
# O perfil em português usa os mesmos critérios técnicos; as regras de estilo foram
# adaptadas do manual em espanhol (confirmar com a Encripta).

_ENCRIPTA_TECH = dict(
    max_chars_per_line=42, max_lines=2,
    max_cps=28.0, optimal_cps=15.0,          # "Máx. de caracteres/s 28" / "Caracteres óptimos/s 15"
    min_duration=1.001, max_duration=6.999,  # 1001 ms / 6999 ms
    min_gap_ms=84.0,                         # "Espacio mín. entre subtítulos 84 ms"
    default_fps=24000 / 1001,                # 23,976
    cps_count_spaces=True,                   # "Count all characters"
    dialogue_dash="-",                       # "Guion de ambas líneas sin espacio"
    ellipsis="...",                          # "…" é tratado como símbolo a corrigir
    naming="encripta", style_checks=True,
)

ENCRIPTA_ES_GUIDE = """Manual de la Encripta (traducción y subtítulos en español 3.0). Cúmplelo estrictamente:
CRITERIOS TÉCNICOS
- Máximo 42 caracteres por línea y dos líneas por subtítulo; mantén el texto en una sola línea siempre que quepa.
- Velocidad: hasta 28 caracteres por segundo, en lo posible menos (ideal 15).
- Guion medio SIN espacio y solo en: diálogos de dos personajes que aparecen al mismo tiempo en pantalla (uno por línea: "-¿Puedes ayudarme?" / "-Por supuesto que sí.") y en subtítulo de localización + diálogo.
INTERJECCIONES
- No uses interjecciones sonoras: Ah, Ay, Ey, Oye, Eh, Ih, Oh, Ei, Ui, Uau, Woo Hoo, Psiu, Oba, Eba, Epa, Opa, Ufa, Hey. Escribe el diálogo sin ellas ("¡Oh, Dios mío!" → "¡Dios mío!"; "¡Hey, Sam!" → "¡Sam!"). Un saludo "Hey" puede ser "Hola". Si el subtítulo es solo la interjección, déjalo con el texto más corto posible sin ella.
COHESIÓN Y COHERENCIA
- Ortografía de la RAE y la ASALE, en español neutro (el tratamiento más recurrente en Latinoamérica).
- No uses doble puntuación: nada de "???", "!!!" ni "¡¿...?!". Usa siempre los signos de apertura ¿ y ¡.
PUNTOS SUSPENSIVOS (siempre tres puntos "...", nunca el carácter "…")
- Respeta las normas gramaticales; siempre que sea posible, sustitúyelos por una coma. No los uses para marcar una pausa en medio de un mismo diálogo ("Realmente crees... Crees que soy idiota." → "Realmente crees que soy idiota.").
- Al inicio del subtítulo solo cuando el discurso fue interrumpido (por un personaje o un subtítulo de localización): "Los denunciaré a todos..." / "...por estar robando."
- Pausa para pensar y la frase continúa: puntos suspensivos al final y la siguiente en minúscula ("Es muy difícil..." / "aceptar ese amor.").
- Si después viene una frase nueva, la siguiente empieza con mayúscula.
- Pregunta con pausa: "¿Cómo te sentiste..." / "al hablar con tu padre?"
DIVISIÓN DE LÍNEA
- Divide solo después de puntuación, antes de preposición (por, con, de...) o antes de conjunción (porque, y...). No separes artículo de sustantivo, sustantivo de adjetivo, nombre de apellido, verbo de objeto, ni adverbio del verbo. Prefiere la línea de abajo más larga.
SUBTÍTULOS DE LOCALIZACIÓN (texto en pantalla)
- Traduce la información en pantalla relevante y no redundante (letreros, matrículas, aeropuertos, establecimientos). Lo que no tiene traducción no se subtitula.
- En MAYÚSCULAS y sin punto final, salvo textos informativos, cartas y mensajes (puntuación como en pantalla). Nunca en cursiva.
- Fechas en estándar latinoamericano (día, mes, año); los números exactamente como aparecen en pantalla.
- Localización + diálogo en el mismo subtítulo: en el orden en que aparecen; solo el diálogo lleva guion ("CHERNOBYL, 26 DE ABRIL DE 1986" / "-Me acuerdo de ese día.").
REPETICIÓN Y REDUNDANCIA
- No repitas palabras o frases: "No, no, no. Ya te dije que no." → "No. Ya te dije que no."
- Pregunta y respuesta idénticas en un diálogo: cambia una por un sinónimo ("-¿De acuerdo?" / "-Sí.").
- Evita redundancias, sobre todo en diálogos; adapta con sinónimos.
COMILLAS
- Comillas rectas ("). El punto va después de cerrar las comillas. Al inicio y al final de cada oración, no de cada subtítulo.
- Úsalas en errores de pronunciación intencionales, juegos de palabras, citas, nombres de canciones y cuando el personaje lee algo. Cita dentro de cita con apóstrofes: "Charlie dijo: 'Todo está bien'".
CANCIONES (cantadas o reproducidas) y ORACIONES
- Siempre en cursiva; primera letra de cada línea en mayúscula (también al dividir la línea); sin punto final; coma solo en medio de la frase; conserva ¿? y ¡!.
NACIONALIZACIONES
- Títulos de películas, libros, juegos o programas: usa el título oficial en español; si no existe, el original. En cursiva y sin comillas.
NUMERALES Y MEDIDAS
- Del 0 al 10 con letras. Si un número inicia la línea, escríbelo con letras o adapta ("30 días" → "Son 30 días").
- Dólares: US$ (US$ 1,4 millones); valores pequeños o redondos, con letras ("seis dólares").
- Sistema métrico con espacio: 300 km, 50 cm, 12 kg. Porcentaje con espacio: 2 %, 100 %. Temperatura según CPS: "600 grados" o "600 °C".
- Ordinales según contexto (1.º Regimiento / el primer hijo).
- Hora en formato de 12 horas: "7:00 a. m.", "3:15 p. m."
CURSIVA (solo en estos casos)
- Quien habla no aparece en la toma; voz en off o narración; idioma distinto al original; multitud o grupo sin hablante identificable; voz de dispositivo electrónico; títulos de obras; palabras extranjeras no registradas en la RAE.
- No uses cursiva en conversaciones ping-pong, una vez identificado el personaje, en voces demoníacas o de fantasmas, ni en escenas con micrófono. Marca la cursiva con <i>...</i>.
ALINEACIÓN
- Si el subtítulo tapa algo escrito en pantalla (lugar, letreros, periódico, nombres, créditos), comienza la primera línea con {\an8}. Conserva las etiquetas {\an8} que vengan en el original.
OTROS
- Después de dos puntos (:), minúscula."""

ENCRIPTA_PT_GUIDE = """Padrão Encripta adaptado ao português do Brasil (critérios do manual da Encripta 3.0):
- Máximo de 42 caracteres por linha e duas linhas; uma linha só sempre que couber. Até 28 caracteres por segundo, de preferência menos (ideal 15).
- Travessão (hífen) SEM espaço e só em diálogo de dois personagens que aparecem ao mesmo tempo (um por linha: "-Você pode me ajudar?" / "-Claro que sim.") e em legenda de localização + diálogo.
- Sem interjeições sonoras (Ah, Oh, Ei, Ui, Uau, Psiu, Oba, Eba, Epa, Opa, Ufa, Hey...): "Ah, meu Deus!" → "Meu Deus!". Um "Hey" de cumprimento pode virar "Oi".
- Ortografia do português do Brasil (Acordo Ortográfico). Sem pontuação dupla ("???", "!!!", "?!").
- Reticências sempre com três pontos "...", nunca o caractere "…". Prefira vírgula quando possível; não use para pausa no meio da mesma fala. No início da legenda só quando a fala foi interrompida ("...por estar roubando."). Pausa e a frase continua: reticências no fim e a seguinte em minúscula.
- Quebra de linha só depois de pontuação, antes de preposição ou de conjunção; não separe artigo e substantivo, substantivo e adjetivo, nome e sobrenome, verbo e objeto, advérbio e verbo. Prefira a linha de baixo maior.
- Legendas de localização (texto na tela relevante): em MAIÚSCULAS, sem ponto final (exceto textos informativos, cartas e mensagens), nunca em itálico; datas no padrão dia/mês/ano; números como aparecem na tela. Com diálogo junto: na ordem em que aparecem e só o diálogo leva hífen.
- Não repita palavras ("Não, não, não. Eu já disse que não." → "Não. Eu já disse que não."); evite redundâncias, use sinônimos em perguntas e respostas iguais.
- Aspas retas ("). Use em erros de pronúncia intencionais, trocadilhos, citações, nomes de músicas e quando o personagem lê algo; citação dentro de citação com aspas simples.
- Músicas e orações: sempre em itálico, inicial maiúscula em cada linha, sem ponto final, vírgula só no meio da frase, mantenha ? e !.
- Títulos de filmes, livros, jogos e programas: título oficial no Brasil (ou o original, se não houver), em itálico e sem aspas.
- Números de zero a dez por extenso; número no início da linha por extenso ou adapte a frase. Dólares: US$. Sistema métrico com espaço: 300 km, 12 kg.
- Itálico (<i>...</i>) só quando quem fala não aparece na cena, narração/voz em off, idioma diferente do original, multidão sem falante identificável, voz de aparelho eletrônico, títulos de obras e palavras estrangeiras. Não use em conversas pingue-pongue, depois que o personagem foi identificado, em vozes demoníacas/fantasmas nem em cenas com microfone.
- Se a legenda cobrir texto na tela, comece a primeira linha com {\an8}; conserve os {\an8} do original.
- Depois de dois-pontos (:), minúscula."""

ENCRIPTA_ES = Profile(
    name="Encripta — Español (neutro)", language="es-419", **_ENCRIPTA_TECH,
    guide=ENCRIPTA_ES_GUIDE,
    notes="Manual de traducción y subtítulos en español 3.0 (Encripta).",
)

ENCRIPTA_PT_BR = Profile(
    name="Encripta — Português (Brasil)", language="pt-BR", **_ENCRIPTA_TECH,
    guide=ENCRIPTA_PT_GUIDE,
    notes="Critérios técnicos do manual 3.0 da Encripta; estilo adaptado ao português.",
)

BUILTIN_PROFILES: dict[str, Profile] = {
    "netflix-es-419": NETFLIX_ES_419,
    "netflix-es-419-kids": NETFLIX_ES_419_KIDS,
    "netflix-pt-br": NETFLIX_PT_BR,
    "netflix-pt-br-kids": NETFLIX_PT_BR_KIDS,
    "encripta-es-419": ENCRIPTA_ES,
    "encripta-pt-br": ENCRIPTA_PT_BR,
}


def same_family(key: str | None, language: str) -> str | None:
    """Perfil equivalente da mesma família para outro idioma (ex.: Encripta ES → PT)."""
    if not key or key not in BUILTIN_PROFILES:
        return None
    fam = key.split("-")[0]
    kids = key.endswith("-kids")
    lang = "pt-br" if language.lower().startswith("pt") else "es-419"
    cand = f"{fam}-{lang}" + ("-kids" if kids else "")
    return cand if cand in BUILTIN_PROFILES else None


def get_profile(key_or_path: str) -> Profile:
    """Aceita a chave de um perfil embutido ou o caminho de um .json."""
    if key_or_path in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[key_or_path]
    p = Path(key_or_path)
    if p.suffix.lower() == ".json" and p.exists():
        return Profile.load(p)
    raise KeyError(
        f"Perfil desconhecido: {key_or_path!r}. Opções: {', '.join(BUILTIN_PROFILES)}"
    )


def default_profile_for(language: str) -> Profile:
    lang = language.lower()
    if lang.startswith("pt"):
        return NETFLIX_PT_BR
    return NETFLIX_ES_419
