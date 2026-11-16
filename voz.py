# -*- coding: utf-8 -*-
"""Clona tu voz en tu computadora y narra guiones con ella (Qwen3-TTS, local).

    python voz.py doctor
    python voz.py muestra <audio o video> --nombre mi-voz [--inicio 12 --fin 24]
    python voz.py narrar <guion.txt> --voz mi-voz [--salida carpeta]
    python voz.py escuchar <video>                 (escribe las frases con sus tiempos)
    python voz.py doblar <video> --voz mi-voz --idioma Portuguese
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
FRASE_MAX = 12                        # segundos; al escuchar un video no se juntan frases más largas
PAUSA_LARGA = 0.6                     # segundos; un silencio así dentro del video también corta la frase
VELOCIDAD_MAX = 1.25                  # al doblar, lo más que se acelera una frase para que quepa


def config():
    if not CONFIG.exists():
        sys.exit("Falta la instalación. Corre primero:  python setup.py")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    # Palabras en alfabeto latino; en japonés, chino o coreano, letra por letra.
    return re.findall(r"[a-z0-9]+|[^\W_]", texto)


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

    def con_tiempos(self, wav16):
        """Palabras (inicio, fin, texto) de un audio largo a 16 kHz.

        Va en trozos de 30 s y con tiempos por palabra: de corrido, en audios
        largos deja de poner puntos y los tiempos se descuadran."""
        import soundfile as sf
        onda, sr = sf.read(wav16, dtype="float32")
        r = self.pipe({"array": onda, "sampling_rate": sr}, chunk_length_s=30, return_timestamps="word",
                      generate_kwargs={"task": "transcribe"})
        return [(c["timestamp"][0], c["timestamp"][1] or c["timestamp"][0], c["text"].strip())
                for c in r["chunks"] if c["text"].strip()]


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


def hablar(cfg, voz, frases, idioma):
    """Dice cada frase con la voz guardada, la escucha y repite las que no salieron."""
    wav_ref, txt_ref = VOCES / f"{voz}.wav", VOCES / f"{voz}.txt"
    if not wav_ref.exists() or not txt_ref.exists():
        sys.exit(f"No existe la voz '{voz}'. Créala con:  python voz.py muestra <audio> --nombre {voz}")
    import numpy as np
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
                text=[frases[k] for k in grupo], language=[idioma] * len(grupo),
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
        oyo = oido(w, sr, idioma)
        informe[k] = {"texto": frases[k], "oido": oyo, "parecido": round(parecido(frases[k], oyo), 2), "intentos": 1}
    for _ in range(REINTENTOS):
        malas = [k for k, f in informe.items() if f["parecido"] < UMBRAL]
        if not malas:
            break
        print(f"Repitiendo {len(malas)} frase(s) que no salieron bien...", flush=True)
        for k, w in generar(malas):
            oyo = oido(w, sr, idioma)
            nota = round(parecido(frases[k], oyo), 2)
            informe[k]["intentos"] += 1
            if nota > informe[k]["parecido"]:
                audios[k] = w
                informe[k].update(oido=oyo, parecido=nota)
    return audios, informe, sr, proceso


def cmd_narrar(args):
    cfg = config()
    frases = partir(Path(args.guion).read_text(encoding="utf-8-sig"))
    if not frases:
        sys.exit("El guion está vacío.")
    salida = Path(args.salida or ROOT / "salidas" / Path(args.guion).stem)
    salida.mkdir(parents=True, exist_ok=True)
    import numpy as np
    import soundfile as sf
    audios, informe, sr, proceso = hablar(cfg, args.voz, frases, args.idioma)

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


def cmd_escuchar(args):
    cfg = config()
    base = ROOT / "salidas" / Path(args.video).stem
    base.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", args.video,
                           "-vn", "-ac", "1", "-ar", "16000", str(base / "original.wav")])
    # Una frase termina en un punto, en una pausa larga o al llegar a FRASE_MAX.
    frases, abierta = [], False
    for inicio, fin, palabra in Oido(cfg).con_tiempos(base / "original.wav"):
        ultima = frases[-1] if frases else None
        if abierta and inicio - ultima["fin"] <= PAUSA_LARGA and fin - ultima["inicio"] <= FRASE_MAX:
            ultima.update(fin=round(fin, 2), texto=f"{ultima['texto']} {palabra}")
        else:
            frases.append({"n": len(frases) + 1, "inicio": round(inicio, 2), "fin": round(fin, 2), "texto": palabra})
        abierta = palabra[-1] not in ".!?…。！？"
    (base / "frases.json").write_text(json.dumps(frases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(frases)} frases en {base / 'frases.json'}")
    print(f"Tradúcelas a {base / '<Idioma>.txt'} (por ejemplo Portuguese.txt): una línea por frase, en el mismo orden.")


def cmd_doblar(args):
    cfg = config()
    base = ROOT / "salidas" / Path(args.video).stem
    trad = base / f"{args.idioma}.txt"
    if not (base / "frases.json").exists():
        sys.exit(f"Primero:  python voz.py escuchar {args.video}")
    if not trad.exists():
        sys.exit(f"Falta la traducción: {trad} (una línea por frase).")
    frases = json.loads((base / "frases.json").read_text(encoding="utf-8"))
    lineas = [l.strip() for l in trad.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    if len(lineas) != len(frases):
        sys.exit(f"{trad.name} tiene {len(lineas)} líneas y el video tiene {len(frases)} frases. Tienen que coincidir.")
    salida = base / args.idioma
    (salida / "frases").mkdir(parents=True, exist_ok=True)
    import numpy as np
    import soundfile as sf

    # Sólo se generan las frases nuevas o cuyo texto cambió desde la última vez.
    previo = {}
    if (salida / "informe.json").exists():
        previo = {f["n"]: f for f in json.loads((salida / "informe.json").read_text(encoding="utf-8"))["frases"]}
    wav = lambda n: salida / "frases" / f"{n:03d}.wav"
    nuevas = [k for k in range(len(lineas))
              if not wav(k + 1).exists() or previo.get(k + 1, {}).get("texto") != lineas[k]]
    proceso = 0
    if nuevas:
        audios, inf, sr, proceso = hablar(cfg, args.voz, [lineas[k] for k in nuevas], args.idioma)
        for i, k in enumerate(nuevas):
            sf.write(wav(k + 1), audios[i], sr, subtype="PCM_16")
            previo[k + 1] = inf[i]

    # Cada frase va en su sitio. Si no cabe en su hueco se acelera un poco; si aun así no cabe, empuja a la siguiente.
    total = sf.info(base / "original.wav").duration
    pista, cursor, informe = None, 0.0, []
    for k, f in enumerate(frases):
        onda, sr = sf.read(wav(k + 1), dtype="float32")
        tope = frases[k + 1]["inicio"] if k + 1 < len(frases) else total
        # Si no cabe, primero empieza antes (en el silencio que dejó la anterior) y sólo después se acelera.
        pos = max(cursor, min(f["inicio"], tope - len(onda) / sr))
        hueco = tope - pos
        velocidad = min(VELOCIDAD_MAX, max(1.0, len(onda) / sr / hueco))
        if velocidad > 1.01:
            tmp = salida / "frases" / "_ajuste.wav"
            subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", str(wav(k + 1)),
                                   "-filter:a", f"atempo={velocidad:.3f}", str(tmp)])
            onda, sr = sf.read(tmp, dtype="float32")
            tmp.unlink()
        if pista is None:
            pista = np.zeros(int((total + 30) * sr), dtype=np.float32)
        a = int(pos * sr)
        pista[a:a + len(onda)] = onda[:len(pista) - a]
        cursor = pos + len(onda) / sr + 0.1
        p = previo[k + 1]
        informe.append(dict(n=k + 1, inicio=f["inicio"], hueco_s=round(hueco, 2), dura_s=round(len(onda) / sr, 2),
                            velocidad=round(velocidad, 2), atraso_s=round(max(0, cursor - 0.1 - tope), 2),
                            texto=p["texto"], oido=p["oido"], parecido=p["parecido"], intentos=p["intentos"]))
    sf.write(salida / "doblaje.wav", pista[:int(max(total, cursor) * sr)], sr, subtype="PCM_16")
    video = salida / f"{Path(args.video).stem}-{args.idioma}.mp4"
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", args.video, "-i", str(salida / "doblaje.wav"),
                           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(video)])

    dudosas = [f["n"] for f in informe if f["parecido"] < UMBRAL]
    atrasadas = [f["n"] for f in informe if f["atraso_s"] > 0.3]
    (salida / "informe.json").write_text(json.dumps({
        "voz": args.voz, "idioma": args.idioma, "modelo": cfg["model"], "equipo": cfg["equipo"],
        "video_s": round(total, 1), "proceso_s": round(proceso, 1), "frases_generadas": len(nuevas),
        "frases_dudosas": dudosas, "frases_atrasadas": atrasadas, "frases": informe,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nListo: {video}  ({len(nuevas)} frases generadas en {proceso:.0f} s)")
    if atrasadas:
        print(f"Estas frases no caben en su hueco y pisan a la siguiente: {atrasadas}. "
              "Acorta su traducción y vuelve a doblar: sólo se rehacen las que cambies.")
    if dudosas:
        print(f"Escucha estas frases, puede que una palabra no suene bien: {dudosas} (detalle en informe.json)")


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
    e = sub.add_parser("escuchar")
    e.add_argument("video")
    e.set_defaults(fn=cmd_escuchar)
    d = sub.add_parser("doblar")
    d.add_argument("video")
    d.add_argument("--voz", required=True)
    d.add_argument("--idioma", required=True)
    d.set_defaults(fn=cmd_doblar)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
