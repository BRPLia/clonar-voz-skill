# -*- coding: utf-8 -*-
"""Instala el clonador de voz según el equipo que encuentre.

    python setup.py            detecta, instala y descarga el modelo
    python setup.py --detectar sólo dice qué instalaría (no instala nada)

Elige solo:
  - Tarjeta NVIDIA con 6 GB o más  -> modelo grande (1.7B)
  - Tarjeta NVIDIA con menos       -> modelo chico (0.6B)
  - Sin tarjeta NVIDIA             -> modelo chico en el procesador (lento)
"""
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
os.environ.setdefault("HF_HOME", str(ROOT / "modelos"))

GRANDE = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"   # ~4,3 GB de descarga
CHICO = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"    # ~2,4 GB de descarga
# Memoria de video medida en una RTX 5060 Ti (MB): base con 1 frase, y extra por cada frase más.
BASE_MB = {GRANDE: 4700, CHICO: 2800}
POR_FRASE_MB = 650


def detectar():
    gpu = None
    if shutil.which("nvidia-smi"):
        try:
            linea = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                text=True).strip().splitlines()[0]
            nombre, mb = [x.strip() for x in linea.rsplit(",", 1)]
            gpu = (nombre, int(mb))
        except Exception:
            pass
    if gpu:
        nombre, mb = gpu
        model = GRANDE if mb >= 6000 else CHICO
        lote = max(1, min(8, (mb - BASE_MB[model] - 1000) // POR_FRASE_MB + 1))
        return {"model": model, "device": "cuda:0", "lote": int(lote),
                "equipo": f"{nombre} ({round(mb / 1024)} GB)", "oido": "openai/whisper-large-v3-turbo"}
    aviso = " (Mac: sin probar, usa el procesador)" if platform.system() == "Darwin" else ""
    return {"model": CHICO, "device": "cpu", "lote": 4,   # en lote el procesador rinde ~1,6 veces más
            "equipo": f"procesador, sin tarjeta NVIDIA{aviso}", "oido": "openai/whisper-small"}


def run(cmd):
    print("\n$ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.check_call([str(c) for c in cmd], cwd=str(ROOT))


def main():
    cfg = detectar()
    print(f"Equipo: {cfg['equipo']}")
    print(f"Modelo: {cfg['model']} | frases a la vez: {cfg['lote']}")
    if cfg["device"] == "cpu":
        print("Sin tarjeta NVIDIA funciona, pero lento: calcula varios minutos de espera por minuto de audio.")
    if "--detectar" in sys.argv:
        return
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        sys.exit("Hace falta Python 3.10, 3.11 o 3.12.")

    if not PY.exists():
        run([sys.executable, "-m", "venv", VENV])
    pip = [PY, "-m", "pip", "install", "--upgrade"]
    if cfg["device"] == "cpu":
        indice = [] if platform.system() == "Darwin" else ["--index-url", "https://download.pytorch.org/whl/cpu"]
    else:
        indice = ["--index-url", "https://download.pytorch.org/whl/cu128"]   # sirve también para las RTX 50
    run([*pip, "pip"])
    run([*pip, "torch", "torchaudio", *indice])
    run([*pip, "qwen-tts", "soundfile", "huggingface_hub"])

    print("\nDescargando los modelos (sólo la primera vez)...")
    run([PY, "-c", "from huggingface_hub import snapshot_download as d;"
                   f"d('{cfg['model']}'); d('{cfg['oido']}')"])
    run([PY, "-c", "import torch, qwen_tts; print('Tarjeta lista:', torch.cuda.is_available())"])
    (ROOT / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nInstalación terminada. Siguiente paso:  python voz.py doctor")


if __name__ == "__main__":
    main()
