# -*- coding: utf-8 -*-
"""Clona tu voz en tu computadora y narra guiones con ella (Qwen3-TTS, local).

    python voz.py doctor
    python voz.py muestra <audio o video> --nombre mi-voz [--inicio 12 --fin 24]
    python voz.py narrar <guion.txt> --voz mi-voz [--salida carpeta]
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
CONFIG = ROOT / "config.json"
VOCES = ROOT / "voces"
os.environ.setdefault("HF_HOME", str(ROOT / "modelos"))

# Siempre corre con el entorno que creó setup.py, se llame como se llame.
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.call([str(VENV_PY), __file__, *sys.argv[1:]]))

MUESTRA_MIN, MUESTRA_MAX = 5, 20      # segundos; lo ideal es de 8 a 15
UMBRAL = 0.85                         # parecido mínimo entre lo pedido y lo que se oye
REINTENTOS = 2
PAUSA = 0.35                          # segundos de silencio entre frases


def config():
    if not CONFIG.exists():
        sys.exit("Falta la instalación. Corre primero:  python setup.py")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", texto)


def parecido(pedido, oido):
    return difflib.SequenceMatcher(None, normalizar(pedido), normalizar(oido)).ratio()


def partir(texto, maximo=300):
    """Una frase por línea de audio; las muy largas se cortan en la coma."""
    frases = []
    for trozo in re.split(r"(?<=[.!?…])\s+|\n+", texto):
        trozo = trozo.strip()
        while len(trozo) > maximo:
            corte = trozo.rfind(",", 0, maximo)
            corte = corte if corte > 0 else trozo.rfind(" ", 0, maximo)
            frases.append(trozo[:corte + 1].strip())
            trozo = trozo[corte + 1:].strip()
        if trozo:
            frases.append(trozo)
    return frases


class Oido:
    """Whisper local: escucha un audio y devuelve el texto."""

    def __init__(self, cfg):
        import torch
        from transformers import pipeline
        gpu = cfg["device"].startswith("cuda")
        self.pipe = pipeline("automatic-speech-recognition", model=cfg["oido"],
                             device=cfg["device"], dtype=torch.float16 if gpu else torch.float32)

    def __call__(self, wav, sr, idioma):
        import torch
        import torchaudio
        onda = torch.as_tensor(wav, dtype=torch.float32)
        onda = torchaudio.functional.resample(onda, sr, 16000).numpy()
        r = self.pipe({"array": onda, "sampling_rate": 16000},
                      generate_kwargs={"language": idioma.lower(), "task": "transcribe"})
        return r["text"].strip()


def cmd_doctor(args):
    print("ffmpeg:", shutil.which("ffmpeg") or "NO ENCONTRADO (hace falta para 'muestra')")
    if not CONFIG.exists():
        print("Instalación: pendiente. Corre  python setup.py")
        return
    cfg = config()
    print("Modelo:", cfg["model"], "| equipo:", cfg["equipo"], "| frases a la vez:", cfg["lote"])
    voces = sorted(p.stem for p in VOCES.glob("*.wav"))
    print("Voces guardadas:", ", ".join(voces) or "ninguna (usa 'muestra')")


def cmd_muestra(args):
    if not shutil.which("ffmpeg"):
        sys.exit("Falta ffmpeg en el PATH.")
    cfg = config()
    VOCES.mkdir(exist_ok=True)
    wav = VOCES / f"{args.nombre}.wav"
    corte = (["-ss", str(args.inicio)] if args.inicio is not None else []) + \
            (["-to", str(args.fin)] if args.fin is not None else [])
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", *corte, "-i", args.audio,
                           "-vn", "-ac", "1", "-ar", "24000", str(wav)])
    import soundfile as sf
    onda, sr = sf.read(wav, dtype="float32")
    dur = len(onda) / sr
    if not MUESTRA_MIN <= dur <= MUESTRA_MAX:
        wav.unlink()
        sys.exit(f"La muestra dura {dur:.1f} s. Tiene que durar entre {MUESTRA_MIN} y "
                 f"{MUESTRA_MAX} s (lo ideal: 8 a 15). Usa --inicio y --fin para recortar.")
    texto = Oido(cfg)(onda, sr, args.idioma)
    (VOCES / f"{args.nombre}.txt").write_text(texto, encoding="utf-8")
    print(f"Muestra guardada: {wav} ({dur:.1f} s)")
    print(f"Esto es lo que entendí que dices:\n  {texto}")
    print(f"Si hay una palabra mal, corrígela en {VOCES / (args.nombre + '.txt')} antes de narrar.")


def cmd_narrar(args):
    cfg = config()
    wav_ref, txt_ref = VOCES / f"{args.voz}.wav", VOCES / f"{args.voz}.txt"
    if not wav_ref.exists() or not txt_ref.exists():
        sys.exit(f"No existe la voz '{args.voz}'. Créala con:  python voz.py muestra <audio> --nombre {args.voz}")
    frases = partir(Path(args.guion).read_text(encoding="utf-8-sig"))
    if not frases:
        sys.exit("El guion está vacío.")
    salida = Path(args.salida or ROOT / "salidas" / Path(args.guion).stem)
    salida.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    gpu = cfg["device"].startswith("cuda")
    print(f"Cargando {cfg['model']} en {cfg['equipo']}...", flush=True)
    modelo = Qwen3TTSModel.from_pretrained(
        cfg["model"], device_map=cfg["device"],
        dtype=torch.bfloat16 if gpu else torch.float32,
        **({"attn_implementation": "sdpa"} if gpu else {}))
    molde = modelo.create_voice_clone_prompt(
        ref_audio=str(wav_ref), ref_text=txt_ref.read_text(encoding="utf-8-sig").strip())

    def generar(indices):
        nonlocal sr
        for i in range(0, len(indices), cfg["lote"]):
            grupo = indices[i:i + cfg["lote"]]
            wavs, sr = modelo.generate_voice_clone(
                text=[frases[k] for k in grupo], language=[args.idioma] * len(grupo),
                voice_clone_prompt=molde, max_new_tokens=1024)
            for k, w in zip(grupo, wavs):
                yield k, np.asarray(w, dtype=np.float32)
            print(f"  {min(i + cfg['lote'], len(indices))}/{len(indices)} frases", flush=True)

    sr, t0 = None, time.perf_counter()
    audios = dict(generar(list(range(len(frases)))))
    proceso = time.perf_counter() - t0

    # Escucha cada frase y repite sólo las que no dicen lo que se pidió.
    oido = Oido(cfg)
    informe = {}
    for k, w in audios.items():
        oyo = oido(w, sr, args.idioma)
        informe[k] = {"texto": frases[k], "oido": oyo, "parecido": round(parecido(frases[k], oyo), 2), "intentos": 1}
    for _ in range(REINTENTOS):
        malas = [k for k, f in informe.items() if f["parecido"] < UMBRAL]
        if not malas:
            break
        print(f"Repitiendo {len(malas)} frase(s) que no salieron bien...", flush=True)
        for k, w in generar(malas):
            oyo = oido(w, sr, args.idioma)
            nota = round(parecido(frases[k], oyo), 2)
            informe[k]["intentos"] += 1
            if nota > informe[k]["parecido"]:
                audios[k] = w
                informe[k].update(oido=oyo, parecido=nota)

    silencio = np.zeros(int(sr * PAUSA), dtype=np.float32)
    partes = []
    for k in range(len(frases)):
        sf.write(salida / f"frase-{k + 1:03d}.wav", audios[k], sr, subtype="PCM_16")
        partes += [audios[k], silencio]
    sf.write(salida / "narracion.wav", np.concatenate(partes[:-1]), sr, subtype="PCM_16")
    dur = sum(len(a) for a in audios.values()) / sr
    dudosas = [k + 1 for k, f in informe.items() if f["parecido"] < UMBRAL]
    (salida / "informe.json").write_text(json.dumps({
        "voz": args.voz, "modelo": cfg["model"], "equipo": cfg["equipo"],
        "audio_s": round(dur, 1), "proceso_s": round(proceso, 1),
        "segundos_por_minuto_de_audio": round(60 * proceso / dur, 1),
        "frases_dudosas": dudosas,
        "frases": [dict(n=k + 1, **informe[k]) for k in range(len(frases))],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nListo: {salida / 'narracion.wav'}  ({dur:.0f} s de audio en {proceso:.0f} s)")
    print(f"En este equipo: {60 * proceso / dur:.0f} s de espera por cada minuto de audio.")
    if dudosas:
        print(f"Escucha estas frases, puede que una palabra no suene bien: {dudosas} (detalle en informe.json)")
    else:
        print("Todas las frases dicen lo que pediste.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    m = sub.add_parser("muestra")
    m.add_argument("audio")
    m.add_argument("--nombre", required=True)
    m.add_argument("--inicio", type=float)
    m.add_argument("--fin", type=float)
    m.add_argument("--idioma", default="Spanish")
    m.set_defaults(fn=cmd_muestra)
    n = sub.add_parser("narrar")
    n.add_argument("guion")
    n.add_argument("--voz", required=True)
    n.add_argument("--salida")
    n.add_argument("--idioma", default="Spanish")
    n.set_defaults(fn=cmd_narrar)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
