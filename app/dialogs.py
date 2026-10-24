"""Janelas nativas do Windows para escolher arquivos e pastas.

A página no navegador não tem acesso ao caminho real dos arquivos; por isso
o servidor (que roda no PC) abre a janela "Abrir" do sistema. Ela roda num
processo separado para não travar o servidor.
"""

from __future__ import annotations

import json
import subprocess
import sys

FILETYPES = {
    "media": [("Vídeo ou áudio", "*.mp4 *.mkv *.mov *.mxf *.avi *.wmv *.m4v *.webm *.ts "
                                 "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma")],
    "subtitle": [("Legenda SRT", "*.srt")],
    "text": [("Texto", "*.txt *.docx")],
    "script": [("Roteiro ou texto sem tempo", "*.txt *.docx *.srt")],
    "csv": [("Planilha CSV", "*.csv")],
    "profile": [("Perfil JSON", "*.json")],
    "any": [("Vídeo, áudio, legenda ou texto",
             "*.mp4 *.mkv *.mov *.mxf *.avi *.wmv *.m4v *.webm *.ts *.wav *.mp3 *.m4a "
             "*.aac *.flac *.ogg *.opus *.wma *.srt *.txt *.docx")],
}


def _show(kind: str, multiple: bool, title: str, initial: str | None,
          filename: str | None = None) -> list[str]:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    try:
        if kind == "save_srt":
            p = filedialog.asksaveasfilename(parent=root, title=title or "Salvar legenda como",
                                             defaultextension=".srt", initialdir=initial or None,
                                             initialfile=filename or "", filetypes=FILETYPES["subtitle"])
            return [p] if p else []
        if kind == "folder":
            p = filedialog.askdirectory(parent=root, title=title or "Escolher pasta",
                                        initialdir=initial or None, mustexist=True)
            return [p] if p else []
        types = FILETYPES.get(kind, FILETYPES["any"]) + [("Todos os arquivos", "*.*")]
        if multiple:
            ps = filedialog.askopenfilenames(parent=root, title=title or "Escolher arquivos",
                                             filetypes=types, initialdir=initial or None)
            return list(ps)
        p = filedialog.askopenfilename(parent=root, title=title or "Escolher arquivo",
                                       filetypes=types, initialdir=initial or None)
        return [p] if p else []
    finally:
        root.destroy()


def dialog_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--dialog"]
    exe = sys.executable
    # pythonw.exe pode não ter stdout; o python.exe com CREATE_NO_WINDOW não abre console.
    if exe.lower().endswith("pythonw.exe"):
        alt = exe[:-len("pythonw.exe")] + "python.exe"
        from pathlib import Path
        if Path(alt).exists():
            exe = alt
    from core.config import module_cmd
    return module_cmd(exe, "app.dialogs")      # o código desta versão (também depois de uma atualização)


def ask(kind: str, multiple: bool = False, title: str = "", initial: str | None = None,
        filename: str | None = None, timeout: float = 600) -> list[str]:
    """Abre a janela e devolve os caminhos escolhidos ([] se cancelou)."""
    args = dialog_command() + [json.dumps({"kind": kind, "multiple": multiple, "title": title,
                                           "initial": initial, "filename": filename})]
    flags = 0x08000000 if sys.platform == "win32" else 0
    from core.config import app_root
    proc = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=flags,
                          cwd=str(app_root()))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[-400:]
                           or "não foi possível abrir a janela")
    out = proc.stdout.decode("utf-8").strip().splitlines()
    return json.loads(out[-1]) if out else []


def run_from_args(arg: str) -> None:
    opts = json.loads(arg)
    paths = _show(opts.get("kind", "any"), bool(opts.get("multiple")), opts.get("title", ""),
                  opts.get("initial"), opts.get("filename"))
    sys.stdout.write(json.dumps(paths, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_from_args(sys.argv[1])
