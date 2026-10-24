"""Usado só pelo teste do pacote (CI): mostra de que pasta veio o código do processo auxiliar."""

from pathlib import Path

if __name__ == "__main__":
    print(Path(__file__).resolve().parent.parent)
