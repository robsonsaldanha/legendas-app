"""Status da conexão (2.16): o selo do canto superior direito.

Ping em horário "fechado", alternando a cada 15 segundos:
  :00 e :30 → servidor da CNT (`/v1/saude`)       :15 e :45 → Google (`generate_204`)
Comparando os dois dá para saber de quem é o problema: se o Google responde e o servidor não, é o
servidor; se nenhum responde, é a internet do computador.

Estados: verificando, online, lenta, reconectando, sem_internet, servidor_fora, manutencao.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger("legendas.conexao")

GOOGLE = "https://www.google.com/generate_204"
LENTA_MS = 1000
TIMEOUT = 6.0
CONECTAR = 4.0      # tempo para abrir a conexão (com IPv4 primeiro, ver core/rede.py)

TEXTO = {
    "verificando": "Conectando…",
    "online": "Online",
    "lenta": "Conexão lenta",
    "reconectando": "Reconectando…",
    "sem_internet": "Offline",
    "servidor_fora": "Offline",
    "manutencao": "Offline",
}
MOTIVO = {
    "verificando": "Conferindo a conexão com o servidor.",
    "online": "Servidor da CNT respondendo normalmente.",
    "lenta": "O servidor responde, mas devagar (mais de 1 segundo).",
    "reconectando": "O servidor não respondeu agora; conferindo de novo.",
    "sem_internet": "Sem conexão com a internet: nem o servidor da CNT nem o Google respondem. Confira o Wi-Fi ou o cabo.",
    "servidor_fora": "Servidor não responde: a internet funciona (o Google responde), mas o servidor da CNT não.",
    "manutencao": "Servidor em manutenção.",
}


@dataclass
class Ping:
    ok: bool
    ms: int | None
    quando: float
    codigo: str = ""
    erro: str = ""
    manutencao: bool = False
    mensagem: str = ""


def proximo_tick(agora: float) -> tuple[float, str]:
    """Próximo horário fechado (múltiplo de 15 s) e quem recebe o ping nele."""
    t = (int(agora) // 15 + 1) * 15
    return float(t), ("servidor" if t % 30 == 0 else "google")


def _hora(t: float | None) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else "—"


class Monitor:
    def __init__(self, servidor_url=None, http_get=None, relogio=time.time, ao_mudar=None):
        self._url = servidor_url            # função que devolve o endereço do servidor (muda com o canal)
        self._get = http_get
        self._relogio = relogio
        self.ao_mudar = ao_mudar            # (estado_antigo, estado_novo, info) → depuração
        self.servidor: Ping | None = None
        self.google: Ping | None = None
        self.falha_desde: float | None = None   # primeira falha do servidor na sequência atual
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._fio: threading.Thread | None = None
        self._ultimo_estado = "verificando"
        self._cliente = None

    # ------------------------------------------------------------------ pings
    def _http(self, url: str):
        if self._get:
            return self._get(url)
        import httpx
        if self._cliente is None:       # conexão reaproveitada: o número mostrado é o tempo de resposta, não o do aperto de mão
            self._cliente = httpx.Client(timeout=httpx.Timeout(TIMEOUT, connect=CONECTAR), follow_redirects=False,
                                         headers={"User-Agent": "CNT-Legendas"},
                                         limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=90))
        try:
            return self._cliente.get(url)
        except Exception:
            self._cliente.close()       # conexão caída: a próxima abre uma nova
            self._cliente = None
            raise

    def _medir(self, url: str, servidor: bool) -> Ping:
        from .erros import de_http, de_rede
        t0 = time.perf_counter()
        agora = self._relogio()
        try:
            r = self._http(url)
        except Exception as e:  # noqa: BLE001
            return Ping(False, None, agora, de_rede(e), str(e)[:200])
        ms = int((time.perf_counter() - t0) * 1000)
        if servidor:
            if r.status_code != 200:
                return Ping(False, ms, agora, de_http(r.status_code), f"HTTP {r.status_code}")
            try:
                d = r.json()
            except ValueError:
                return Ping(False, ms, agora, "ER-RS-601", "resposta ilegível")
            return Ping(True, ms, agora, "ER-RS-301" if d.get("manutencao") else "", "",
                        bool(d.get("manutencao")), str(d.get("mensagem") or ""))
        ok = r.status_code in (200, 204)
        return Ping(ok, ms, agora, "" if ok else f"HTTP {r.status_code}", "" if ok else f"HTTP {r.status_code}")

    def ping_servidor(self) -> Ping:
        base = (self._url() if callable(self._url) else self._url) or ""
        p = self._medir(base.rstrip("/") + "/v1/saude", True)
        with self._lock:
            self.servidor = p
            if p.ok:
                self.falha_desde = None
            elif self.falha_desde is None:
                self.falha_desde = p.quando
        self._avisar()
        return p

    def ping_google(self) -> Ping:
        p = self._medir(GOOGLE, False)
        with self._lock:
            self.google = p
        self._avisar()
        return p

    # ------------------------------------------------------------------ estado
    def estado(self) -> dict:
        with self._lock:
            s, g, desde = self.servidor, self.google, self.falha_desde
        agora = self._relogio()
        prox, quem = proximo_tick(agora)
        if s is None:
            e = "verificando"
        elif s.ok:
            e = "manutencao" if s.manutencao else ("lenta" if (s.ms or 0) > LENTA_MS else "online")
        elif g is not None and desde is not None and g.quando >= desde:
            e = "servidor_fora" if g.ok else "sem_internet"
        else:
            e = "reconectando"
        motivo = MOTIVO[e]
        if e == "manutencao" and s and s.mensagem:
            motivo += " " + s.mensagem
        codigo = (s.codigo if s and not s.ok else "") or ("ER-RS-301" if e == "manutencao" else "")
        detalhe = [f"Servidor: {f'{s.ms} ms' if s and s.ok else 'sem resposta'} às {_hora(s.quando if s else None)}",
                   f"Google: {f'{g.ms} ms' if g and g.ok else ('sem resposta' if g else '—')} às {_hora(g.quando if g else None)}",
                   f"Próxima conferência: {_hora(prox)} ({'servidor' if quem == 'servidor' else 'Google'})"]
        return {"estado": e, "texto": TEXTO[e], "motivo": motivo, "codigo": codigo,
                "ms": s.ms if s and s.ok else None, "online": e in ("online", "lenta"),
                "detalhe": detalhe, "servidor_ok": bool(s and s.ok), "google_ok": bool(g and g.ok) if g else None}

    def _avisar(self) -> None:
        novo = self.estado()
        if novo["estado"] != self._ultimo_estado:
            antigo, self._ultimo_estado = self._ultimo_estado, novo["estado"]
            log.info("Conexão: %s → %s (%s)", antigo, novo["estado"], novo["codigo"] or "ok")
            if self.ao_mudar:
                try:
                    self.ao_mudar(antigo, novo["estado"], novo)
                except Exception:  # noqa: BLE001
                    pass

    # ------------------------------------------------------------------ fio
    def iniciar(self) -> None:
        if self._fio is not None:
            return
        self._fio = threading.Thread(target=self._rodar, name="conexao", daemon=True)
        self._fio.start()

    def parar(self) -> None:
        self._parar.set()

    def _rodar(self) -> None:
        try:                                # primeira conferência na hora (não espera o horário fechado)
            if not self.ping_servidor().ok:
                self.ping_google()
        except Exception:  # noqa: BLE001
            log.debug("ping inicial", exc_info=True)
        while not self._parar.is_set():
            t, quem = proximo_tick(self._relogio())
            if self._parar.wait(max(0.0, t - self._relogio())):
                break
            try:
                self.ping_servidor() if quem == "servidor" else self.ping_google()
            except Exception:  # noqa: BLE001
                log.debug("ping", exc_info=True)
