"""Documento .docx simples (título + tabela), montado só com zip + XML — sem biblioteca extra no pacote.

Usado pelo roteiro de audiodescrição e pelo roteiro de dublagem."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _par(texto: str, negrito: bool = False, tam: int = 20) -> str:
    rpr = f"<w:rPr>{'<w:b/>' if negrito else ''}<w:sz w:val=\"{tam}\"/></w:rPr>"
    linhas = escape(str(texto)).split("\n")
    return "<w:p><w:r>" + rpr + "<w:br/>".join(f"<w:t xml:space=\"preserve\">{l}</w:t>" for l in linhas) + "</w:r></w:p>"


def _cel(texto: str, largura: int, negrito: bool = False) -> str:
    return f"<w:tc><w:tcPr><w:tcW w:w=\"{largura}\" w:type=\"dxa\"/></w:tcPr>{_par(texto, negrito)}</w:tc>"


def tabela_docx(destino: str | Path, titulo: str, cabecalho: list[str], linhas: list[list[str]], larguras: list[int],
                subtitulo: str = "", paisagem: bool = False) -> Path:
    borda = "".join(f"<w:{x} w:val=\"single\" w:sz=\"4\" w:color=\"999999\"/>" for x in ("top", "left", "bottom", "right", "insideH", "insideV"))
    trs = ["<w:tr>" + "".join(_cel(t, w, True) for t, w in zip(cabecalho, larguras)) + "</w:tr>"]
    for l in linhas:
        trs.append("<w:tr>" + "".join(_cel(t, w) for t, w in zip(l, larguras)) + "</w:tr>")
    secao = ('<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/><w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720"/></w:sectPr>'
             if paisagem else "<w:sectPr/>")
    corpo = (_par(titulo, True, 32) + (_par(subtitulo) if subtitulo else "")
             + f"<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/><w:tblBorders>{borda}</w:tblBorders></w:tblPr>"
             + "".join(trs) + "</w:tbl>" + secao)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{corpo}</w:body></w:document>")
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    destino = Path(destino)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
    return destino
