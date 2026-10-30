"""Abre ou atualiza o pedido de liberação dev → main (chamado pelo CI depois que a dev passa em tudo).

Aprovar a liberação = juntar o pedido. A montagem da main publica a versão no site e na
atualização automática do canal produção.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.liberacao import corpo, titulo  # noqa: E402


def sh(*cmd, ok=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode and not ok:
        raise SystemExit(f"falhou: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout.strip()


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    build = os.environ.get("GITHUB_RUN_NUMBER", "")
    import core
    versao = f"{core.__version__}.{build}" if build else core.__version__
    sh("git", "fetch", "-q", "origin", "main", "dev")
    linhas = sh("git", "log", "--no-merges", "--format=%s", "origin/main..origin/dev").splitlines()
    if not linhas:
        print("A main já tem tudo da dev; nada a liberar.")
        return
    t, c = titulo(versao), corpo(versao, linhas, repo)
    aberto = json.loads(sh("gh", "pr", "list", "-R", repo, "--base", "main", "--head", "dev",
                           "--state", "open", "--json", "number") or "[]")
    if aberto:
        n = str(aberto[0]["number"])
        sh("gh", "pr", "edit", n, "-R", repo, "--title", t, "--body", c)
    else:
        r = subprocess.run(["gh", "pr", "create", "-R", repo, "--base", "main", "--head", "dev",
                            "--title", t, "--body", c], capture_output=True, text=True)
        if r.returncode:
            # o repositório pode não deixar o CI abrir pedidos; não derruba a montagem
            print(f"::warning title=Liberação::não consegui abrir o pedido ({r.stderr.strip()[:200]}). "
                  f"Abra em https://github.com/{repo}/compare/main...dev")
            return
        n = r.stdout.strip().rsplit("/", 1)[-1]
    print(f"::notice title=Liberação::pedido #{n} pronto: {t}")


if __name__ == "__main__":
    main()
