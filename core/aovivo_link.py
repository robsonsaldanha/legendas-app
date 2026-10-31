"""Ao vivo por link (2.29): a pessoa cola o link da página da live ou do vídeo; o programa lê o áudio
pela biblioteca aberta de leitura de sites de vídeo (`yt_dlp`) e mostra o vídeo num player na tela.

- `precisa_resolver`: link de página (precisa da biblioteca) × endereço direto de mídia/transmissão (ffmpeg abre).
- `resolver`: devolve o endereço da mídia, os cabeçalhos e as informações (título, se é ao vivo).
- `player_de`: o que a tela mostra no player (página oficial de incorporação do site, vídeo direto ou só o link).
- `garantir_js`: alguns sites exigem um interpretador de JavaScript para a biblioteca; baixamos uma vez
  (para a pasta de dados) quando não houver um no pacote nem no sistema.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ESQUEMAS = ("http", "https", "rtmp", "rtmps", "srt", "rtsp", "udp", "rtp")
MIDIA = (".m3u8", ".mpd", ".mp4", ".m4a", ".mp3", ".aac", ".webm", ".ts", ".flv", ".ogg", ".opus", ".wav", ".mkv", ".mov")
VIDEO_NA_TELA = (".mp4", ".webm", ".ogg", ".mov", ".m4a", ".mp3", ".wav", ".opus")


def conferir(endereco: str) -> str:
    """"" = dá para tentar; senão, a explicação para a pessoa."""
    e = (endereco or "").strip()
    if not e:
        return "Cole o link da live ou do vídeo."
    u = urlparse(e)
    if u.scheme.lower() not in ESQUEMAS or not (u.netloc or u.path):
        return "Cole o link completo, começando com https:// (copie da barra de endereço do navegador)."
    return ""


def precisa_resolver(endereco: str) -> bool:
    u = urlparse(endereco.strip())
    if u.scheme.lower() not in ("http", "https"):
        return False                                 # rtmp, srt…: o ffmpeg abre direto
    return not u.path.lower().endswith(MIDIA)


def _host(u) -> str:
    h = (u.hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _id_do_video(u) -> str:
    """Identificador do vídeo de um link de página de vídeo (watch?v=, encurtado, /live/, /shorts/, /embed/)."""
    h = _host(u)
    if h.endswith("youtu.be"):
        return u.path.strip("/").split("/")[0]
    if "v" in parse_qs(u.query):
        return parse_qs(u.query)["v"][0]
    m = re.match(r"^/(?:live|shorts|embed)/([\w-]{6,})", u.path)
    return m.group(1) if m else ""


def player_de(endereco: str, info: dict | None = None) -> dict:
    """{"tipo": "iframe"|"video"|"link", "src": …}: a página oficial de incorporação do site quando houver."""
    info = info or {}
    u = urlparse(endereco.strip())
    h = _host(u)
    ext = (info.get("extractor_key") or "").lower()
    if ext.startswith("youtube") or h.endswith(("youtube.com", "youtu.be")):
        vid = info.get("id") if ext.startswith("youtube") and info.get("id") else _id_do_video(u)
        if vid and re.fullmatch(r"[\w-]{6,20}", vid):
            return {"tipo": "iframe", "src": f"https://www.youtube.com/embed/{vid}?autoplay=1&mute=1&playsinline=1"}
    if h.endswith("twitch.tv"):
        partes = [p for p in u.path.split("/") if p]
        pais = "parent=127.0.0.1&parent=localhost"
        if len(partes) >= 2 and partes[0] == "videos" and partes[1].isdigit():
            return {"tipo": "iframe", "src": f"https://player.twitch.tv/?video=v{partes[1]}&{pais}&muted=true&autoplay=true"}
        if partes and re.fullmatch(r"\w{2,40}", partes[0]):
            return {"tipo": "iframe", "src": f"https://player.twitch.tv/?channel={partes[0]}&{pais}&muted=true&autoplay=true"}
    if h.endswith("kick.com"):
        partes = [p for p in u.path.split("/") if p]
        if partes and re.fullmatch(r"[\w-]{2,40}", partes[0]):
            return {"tipo": "iframe", "src": f"https://player.kick.com/{partes[0]}?autoplay=true&muted=true"}
    if u.scheme in ("http", "https") and u.path.lower().endswith(VIDEO_NA_TELA):
        return {"tipo": "video", "src": endereco.strip()}
    return {"tipo": "link", "src": endereco.strip()}


def explicar(erro: str) -> str:
    t = erro.lower()
    if "not a bot" in t or "confirm you" in t and "bot" in t:
        causa = ("O site pediu para confirmar que não é um robô e recusou o pedido. Tente de novo em alguns minutos; "
                 "se continuar, abra o link uma vez no navegador deste computador e tente outra vez.")
    elif "is offline" in t or "not currently live" in t or "will begin" in t or "premieres in" in t:
        causa = "Essa live não está no ar agora. Confira o link ou espere a transmissão começar."
    elif "private" in t or "sign in" in t or "login" in t or "logged-in" in t or "members" in t or "age" in t and "confirm" in t:
        causa = "Esse vídeo pede entrar com uma conta (privado, só para membros ou com restrição de idade). Use um link público."
    elif "unsupported url" in t or "no video formats" in t or "unable to extract" in t:
        causa = "Não consegui abrir esse link. Ele precisa ser da página de uma live ou de um vídeo."
    elif "http error 404" in t or "not found" in t:
        causa = "Esse link não existe mais. Confira se copiou o endereço certo."
    elif "timed out" in t or "connection" in t or "name resolution" in t or "network" in t:
        causa = "Sem resposta do site. Confira a internet e tente de novo."
    else:
        causa = "Não consegui abrir esse link."
    return f"{causa} (detalhe: {erro.strip()[-200:]})"


# ------------------------------------------------------------------ interpretador de JavaScript

DENO = {("win32", "x86_64"): "deno-x86_64-pc-windows-msvc.zip", ("linux", "x86_64"): "deno-x86_64-unknown-linux-gnu.zip",
        ("linux", "aarch64"): "deno-aarch64-unknown-linux-gnu.zip", ("darwin", "arm64"): "deno-aarch64-apple-darwin.zip",
        ("darwin", "x86_64"): "deno-x86_64-apple-darwin.zip"}
BASE_DENO = "https://github.com/denoland/deno/releases/latest/download/"


def _arquitetura() -> str:
    import platform
    m = platform.machine().lower()
    return {"amd64": "x86_64", "x64": "x86_64", "aarch64": "aarch64" if sys.platform == "linux" else "arm64"}.get(m, m)


def achar_js(bin_dir: Path | None, dados: Path) -> dict:
    """Configuração de interpretador para a biblioteca: {"deno": {"path": …}} ou {"node": {…}} ou {}."""
    nome = "deno.exe" if sys.platform == "win32" else "deno"
    for p in ([bin_dir / nome] if bin_dir else []) + [dados / "ferramentas" / nome]:
        if p.is_file():
            return {"deno": {"path": str(p)}}
    if shutil.which("deno"):
        return {"deno": {}}
    if shutil.which("node"):
        return {"node": {}}
    return {}


def garantir_js(bin_dir: Path | None, dados: Path, baixar=None, avisar=None) -> dict:
    """Como `achar_js`, mas baixa o interpretador (uma vez) quando não houver nenhum."""
    achou = achar_js(bin_dir, dados)
    if achou:
        return achou
    arq = DENO.get((sys.platform, _arquitetura()))
    if not arq:
        return {}
    if avisar:
        avisar("Baixando um componente para abrir links desse site (uma vez só, cerca de 40 MB)…")
    baixar = baixar or _baixar
    dados_zip = baixar(BASE_DENO + arq)
    try:
        soma = baixar(BASE_DENO + arq + ".sha256sum").decode("ascii", "replace").split()[0].lower()
    except Exception:  # noqa: BLE001  (sem o arquivo de soma: segue, como nas outras ferramentas baixadas)
        soma = ""
    if soma and re.fullmatch(r"[0-9a-f]{64}", soma) and hashlib.sha256(dados_zip).hexdigest() != soma:
        raise RuntimeError("o componente baixado veio corrompido")
    destino = dados / "ferramentas"
    destino.mkdir(parents=True, exist_ok=True)
    nome = "deno.exe" if sys.platform == "win32" else "deno"
    with zipfile.ZipFile(io.BytesIO(dados_zip)) as z:
        membro = next(n for n in z.namelist() if n.rsplit("/", 1)[-1] == nome)
        tmp = destino / (nome + ".baixando")
        tmp.write_bytes(z.read(membro))
    if sys.platform != "win32":
        tmp.chmod(0o755)
    os.replace(tmp, destino / nome)
    return {"deno": {"path": str(destino / nome)}}


def _baixar(url: str) -> bytes:
    import httpx
    with httpx.Client(timeout=httpx.Timeout(120, connect=10), follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


# ------------------------------------------------------------------ resolver o link

def _lib_do_pacote() -> None:
    vdir = os.environ.get("CNT_VERSAO_DIR")        # bibliotecas que chegaram no pacote de atualização
    if vdir and os.path.isdir(os.path.join(vdir, "lib")) and os.path.join(vdir, "lib") not in sys.path:
        sys.path.append(os.path.join(vdir, "lib"))


def guardar_info(info: dict, destino: Path, ydl_cls=None) -> Path:
    """Informações do link num arquivo para o processo que baixa (formato da biblioteca)."""
    import json
    if ydl_cls is None:
        _lib_do_pacote()
        from yt_dlp import YoutubeDL as ydl_cls
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(ydl_cls.sanitize_info(info)), encoding="utf-8")
    return destino


def resolver(endereco: str, js: dict | None = None, ydl_cls=None) -> tuple[str, dict, dict]:
    """(endereço da mídia, cabeçalhos HTTP, info). Só o áudio quando o site oferece; senão a menor imagem com som."""
    if ydl_cls is None:
        _lib_do_pacote()
        from yt_dlp import YoutubeDL as ydl_cls
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "playlist_items": "1",
            "format": "bestaudio/worst[acodec!=none]/best", "socket_timeout": 20}
    if js:
        opts["js_runtimes"] = js
    with ydl_cls(opts) as y:
        info = y.extract_info(endereco, download=False)
    if info.get("_type") in ("playlist", "multi_video") and info.get("entries"):
        info = next(e for e in info["entries"] if e)
    midia = info.get("url") or next((f.get("url") for f in info.get("requested_formats") or [] if f.get("url")), "")
    if not midia:
        raise RuntimeError("no video formats found")
    cab = dict(info.get("http_headers") or {})
    for f in info.get("requested_formats") or []:
        cab.update(f.get("http_headers") or {})
    return midia, cab, info


BOOT_BAIXAR = ("import os, sys\n"
               "v = os.environ.get('CNT_VERSAO_DIR')\n"
               "if v and os.path.isdir(os.path.join(v, 'lib')): sys.path.append(os.path.join(v, 'lib'))\n"
               "import yt_dlp\nsys.exit(yt_dlp.main(sys.argv[1:]))")


def cmd_baixar(python: str, info_json: str, ffmpeg: str, ao_vivo: bool) -> list[str]:
    """Processo que baixa a mídia já escolhida (sem consultar o site de novo) e entrega pela saída padrão.
    A própria biblioteca baixa: ela sabe os cabeçalhos, os limites de velocidade e o formato de cada site."""
    c = [python, "-c", BOOT_BAIXAR, "--load-info-json", info_json, "-o", "-", "--quiet", "--no-warnings", "--no-part",
         "--no-progress", "--ffmpeg-location", ffmpeg, "--retries", "5", "--fragment-retries", "10",
         "--downloader", "http,https:native"]
    if ao_vivo:
        c += ["--hls-use-mpegts"]
    return c


def args_ffmpeg(midia: str, cab: dict, ao_vivo: bool) -> list[str]:
    """Entrada do ffmpeg para a mídia resolvida. Vídeo gravado vai em tempo real (acompanha o player)."""
    a = []
    linhas = "".join(f"{k}: {v}\r\n" for k, v in cab.items() if k.lower() in ("user-agent", "referer", "origin", "cookie", "accept"))
    if linhas:
        a += ["-headers", linhas]
    if not ao_vivo:
        a += ["-re"]
    else:
        a += ["-live_start_index", "-2"] if ".m3u8" in midia.split("?")[0] else []
    a += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"] if midia.startswith("http") else []
    return a + ["-i", midia]
