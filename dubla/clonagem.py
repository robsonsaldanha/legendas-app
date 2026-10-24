"""Clonagem de voz local (P-07, T-057). O motor (modelo aberto, licença MIT, com marca d'água inaudível) é baixado e
instalado à parte, porque é grande e precisa de placa de vídeo para ficar rápido. Só é usado com termo de
consentimento registrado (ver `consentimentos` no banco)."""

from __future__ import annotations

from pathlib import Path


def disponivel() -> bool:
    try:
        import chatterbox  # noqa: F401  (pacote do motor)
        return True
    except Exception:  # noqa: BLE001
        return False


def falar(texto: str, amostra: str, idioma: str, destino: Path) -> Path:
    import torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo = ChatterboxMultilingualTTS.from_pretrained(device=dev)
    wav = modelo.generate(texto, language_id=idioma.split("-")[0], audio_prompt_path=amostra)
    torchaudio.save(str(destino), wav, modelo.sr)
    return destino
