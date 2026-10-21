"""No GitHub Actions, cada falha vira uma anotação (legível pela API, sem baixar logs)."""

import os


def pytest_runtest_logreport(report):
    if not os.environ.get("GITHUB_ACTIONS") or not report.failed:
        return
    msg = str(report.longrepr)
    lines = [l for l in msg.splitlines() if l.startswith("E ") or "Error" in l][:12]
    text = " | ".join(lines) or msg[-800:]
    text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"\n::error title={report.nodeid}::{text[:1500]}")
