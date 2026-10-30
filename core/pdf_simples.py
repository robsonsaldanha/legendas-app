"""PDF simples feito à mão (2.26): texto, linhas, retângulos e uma imagem (logo).

Sem bibliotecas de fora — assim chega pelo pacote de atualização, sem reinstalar o programa. Usa as fontes
padrão do PDF (Helvetica e Helvetica-Bold, codificação WinAnsi: cobre o português e o espanhol). A logo pode
ser .png (8 bits, sem entrelaçamento; com transparência) ou .jpg.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

A4 = (595.28, 841.89)

# larguras da Helvetica (1/1000 do tamanho), de 32 a 126
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556,
      556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667,
      556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556,
      556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722,
      500, 500, 500, 334, 260, 334, 584]
_BASE = str.maketrans("ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ", "AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn")
_TROCAS = {"✓": "OK", "✔": "OK", "✗": "x", "→": "->", "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
           "…": "...", "•": "-", "·": "-", " ": " "}


def _limpo(s: str) -> str:
    return "".join(_TROCAS.get(ch, ch) for ch in str(s))


def largura(texto: str, tamanho: float, negrito: bool = False) -> float:
    t = _limpo(texto).translate(_BASE)
    w = sum(_W[ord(ch) - 32] if 32 <= ord(ch) <= 126 else 556 for ch in t)
    return w * tamanho / 1000 * (1.06 if negrito else 1.0)


def quebrar(texto: str, tamanho: float, maximo: float, negrito: bool = False) -> list[str]:
    linhas: list[str] = []
    for par in str(texto).split("\n"):
        atual = ""
        for palavra in par.split(" "):
            teste = f"{atual} {palavra}" if atual else palavra
            if largura(teste, tamanho, negrito) <= maximo or not atual:
                atual = teste
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
    return linhas


def _str(s: str) -> bytes:
    b = _limpo(s).encode("cp1252", errors="replace")
    return b"(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _cor(c: tuple) -> str:
    return " ".join(f"{x / 255:.3f}" for x in c)


# ------------------------------------------------------------------ imagens

def _png(dados: bytes) -> tuple[int, int, bytes, bytes | None]:
    """(largura, altura, RGB, alfa ou None) de um PNG de 8 bits sem entrelaçamento."""
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("não é PNG")
    pos, idat, pal, trns = 8, b"", None, None
    w = h = tipo = 0
    while pos < len(dados):
        n, = struct.unpack(">I", dados[pos:pos + 4])
        k = dados[pos + 4:pos + 8]
        corpo = dados[pos + 8:pos + 8 + n]
        if k == b"IHDR":
            w, h, prof, tipo, _, _, entre = struct.unpack(">IIBBBBB", corpo)
            if prof != 8 or entre:
                raise ValueError("PNG não suportado (use 8 bits, sem entrelaçamento)")
        elif k == b"PLTE":
            pal = corpo
        elif k == b"tRNS":
            trns = corpo
        elif k == b"IDAT":
            idat += corpo
        pos += 12 + n
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[tipo]
    cru = zlib.decompress(idat)
    lin = w * canais
    out = bytearray(h * lin)
    ant = bytearray(lin)
    p = 0
    for y in range(h):
        f = cru[p]; p += 1
        row = bytearray(cru[p:p + lin]); p += lin
        for x in range(lin):
            a = row[x - canais] if x >= canais else 0
            b = ant[x]
            c = ant[x - canais] if x >= canais else 0
            if f == 1:
                row[x] = (row[x] + a) & 255
            elif f == 2:
                row[x] = (row[x] + b) & 255
            elif f == 3:
                row[x] = (row[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out[y * lin:(y + 1) * lin] = row
        ant = row
    rgb, alfa = bytearray(), bytearray()
    for i in range(w * h):
        px = out[i * canais:(i + 1) * canais]
        if tipo == 0:
            rgb += bytes([px[0]] * 3)
        elif tipo == 2:
            rgb += px
        elif tipo == 3:
            j = px[0]
            rgb += pal[j * 3:j * 3 + 3]
            alfa.append(trns[j] if trns and j < len(trns) else 255)
        elif tipo == 4:
            rgb += bytes([px[0]] * 3); alfa.append(px[1])
        else:
            rgb += px[:3]; alfa.append(px[3])
    return w, h, bytes(rgb), (bytes(alfa) if alfa and min(alfa) < 255 else None)


def _jpg_tamanho(dados: bytes) -> tuple[int, int, int]:
    i = 2
    while i < len(dados):
        if dados[i] != 0xFF:
            i += 1
            continue
        m = dados[i + 1]
        n, = struct.unpack(">H", dados[i + 2:i + 4])
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", dados[i + 5:i + 9])
            return w, h, dados[i + 9]
        i += 2 + n
    raise ValueError("JPEG sem tamanho")


class PDF:
    """Página A4, coordenadas a partir do canto de cima (y cresce para baixo)."""

    def __init__(self, margem: float = 48):
        self.margem = margem
        self.paginas: list[bytearray] = []
        self.imagens: list[tuple] = []          # (w, h, dados, filtro, cores, alfa)
        self.y = 0.0
        self.nova_pagina()

    @property
    def largura_util(self) -> float:
        return A4[0] - 2 * self.margem

    def nova_pagina(self) -> None:
        self.paginas.append(bytearray())
        self.y = self.margem

    def _op(self, s: str | bytes) -> None:
        self.paginas[-1] += (s.encode("latin-1") if isinstance(s, str) else s) + b"\n"

    def precisa(self, altura: float) -> None:
        if self.y + altura > A4[1] - self.margem:
            self.nova_pagina()

    def texto(self, x: float, y: float, s: str, tamanho: float = 10, negrito: bool = False, cor=(21, 23, 26)) -> None:
        self._op(f"BT /{'F2' if negrito else 'F1'} {tamanho:g} Tf {_cor(cor)} rg {x:.2f} {A4[1] - y:.2f} Td ")
        self._op(_str(s) + b" Tj ET")

    def paragrafo(self, s: str, tamanho: float = 10, negrito: bool = False, cor=(21, 23, 26), x: float | None = None,
                  largura_max: float | None = None, entrelinha: float = 1.35) -> None:
        x = self.margem if x is None else x
        for linha in quebrar(s, tamanho, largura_max or (A4[0] - self.margem - x), negrito):
            self.precisa(tamanho * entrelinha)
            self.texto(x, self.y + tamanho, linha, tamanho, negrito, cor)
            self.y += tamanho * entrelinha

    def linha(self, x1: float, y1: float, x2: float, y2: float, cor=(222, 220, 212), espessura: float = 0.8) -> None:
        self._op(f"{_cor(cor)} RG {espessura:g} w {x1:.2f} {A4[1] - y1:.2f} m {x2:.2f} {A4[1] - y2:.2f} l S")

    def retangulo(self, x: float, y: float, w: float, h: float, cor=(242, 241, 236)) -> None:
        self._op(f"{_cor(cor)} rg {x:.2f} {A4[1] - y - h:.2f} {w:.2f} {h:.2f} re f")

    def imagem(self, caminho: str | Path, x: float, y: float, altura: float, largura_max: float = 200) -> float:
        """Desenha a imagem com a altura pedida (sem passar de largura_max). Devolve a largura usada."""
        dados = Path(caminho).read_bytes()
        if dados[:8] == b"\x89PNG\r\n\x1a\n":
            w, h, rgb, alfa = _png(dados)
            self.imagens.append((w, h, zlib.compress(rgb), "/FlateDecode", "/DeviceRGB", zlib.compress(alfa) if alfa else None))
        elif dados[:2] == b"\xff\xd8":
            w, h, comp = _jpg_tamanho(dados)
            self.imagens.append((w, h, dados, "/DCTDecode", "/DeviceGray" if comp == 1 else "/DeviceRGB", None))
        else:
            raise ValueError("Use uma imagem .png ou .jpg")
        esc = min(altura / h, largura_max / w)
        lw, lh = w * esc, h * esc
        self._op(f"q {lw:.2f} 0 0 {lh:.2f} {x:.2f} {A4[1] - y - lh:.2f} cm /Im{len(self.imagens)} Do Q")
        return lw

    def salvar(self, destino: str | Path) -> Path:
        objs: list[bytes] = []

        def add(b: bytes) -> int:
            objs.append(b)
            return len(objs)
        fonte1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        fonte2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        xobjs = []
        for k, (w, h, dados, filtro, cores, alfa) in enumerate(self.imagens, 1):
            smask = ""
            if alfa:
                sm = add(f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray "
                         f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(alfa)} >>\nstream\n".encode() + alfa + b"\nendstream")
                smask = f" /SMask {sm} 0 R"
            io = add(f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace {cores} /BitsPerComponent 8 "
                     f"/Filter {filtro}{smask} /Length {len(dados)} >>\nstream\n".encode() + dados + b"\nendstream")
            xobjs.append(f"/Im{k} {io} 0 R")
        recursos = (f"<< /Font << /F1 {fonte1} 0 R /F2 {fonte2} 0 R >>"
                    + (f" /XObject << {' '.join(xobjs)} >>" if xobjs else "") + " >>")
        paginas_id = len(objs) + 1 + 2 * len(self.paginas)
        kids = []
        for conteudo in self.paginas:
            z = zlib.compress(bytes(conteudo))
            c = add(f"<< /Length {len(z)} /Filter /FlateDecode >>\nstream\n".encode() + z + b"\nendstream")
            p = add(f"<< /Type /Page /Parent {paginas_id} 0 R /MediaBox [0 0 {A4[0]} {A4[1]}] "
                    f"/Resources {recursos} /Contents {c} 0 R >>".encode())
            kids.append(f"{p} 0 R")
        add(f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode())
        catalogo = add(f"<< /Type /Catalog /Pages {paginas_id} 0 R >>".encode())
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        pos = []
        for i, o in enumerate(objs, 1):
            pos.append(len(out))
            out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{p:010d} 00000 n \n".encode() for p in pos)
        out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalogo} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        destino = Path(destino)
        destino.write_bytes(bytes(out))
        return destino
