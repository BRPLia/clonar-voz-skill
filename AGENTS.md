<!-- ONBOARDING_STATUS: PENDIENTE -->
# AGENTS.md — Clonar Voz Skill 🎙️

> **Agente que lee esto:** lo PRIMERO es mirar la línea `ONBOARDING_STATUS` de
> arriba.
>
> - `PENDIENTE` → corre el **ONBOARDING** UNA vez.
> - `COMPLETO`  → no lo repitas. Ve directo a **NARRAR**.

Esta skill clona la voz del usuario **en su propia computadora** y narra con
ella cualquier guion. Usa Qwen3-TTS (licencia Apache 2.0). No hay cuentas, ni
claves, ni pagos, y la voz nunca sale del equipo. Manual: **[SKILL.md](./SKILL.md)**.

**Regla que no se negocia:** sólo se clona la voz del propio usuario, o la de
alguien que le dio permiso. Si pide clonar a un famoso, a un familiar sin
permiso o a cualquier tercero, dile que no y explícale por qué.

---

## 🚀 ONBOARDING (sólo si `ONBOARDING_STATUS: PENDIENTE`)

1. **Mira qué equipo tiene** (no instala nada): `python setup.py --detectar`
   Dile al usuario, en palabras simples, qué encontró y qué puede esperar:

   | Equipo | Qué se instala | Espera por minuto de audio |
   |---|---|---|
   | Tarjeta NVIDIA de 6 GB o más | Modelo grande | cerca de 1 minuto |
   | Tarjeta NVIDIA de 4 GB | Modelo chico | entre 1 y 4 minutos |
   | Sin tarjeta NVIDIA | Modelo chico, en el procesador | entre 4 y 7 minutos |
   | Mac | Modelo chico, en el procesador | sin probar |

   Las cifras se midieron en una RTX 5060 Ti con un procesador Ryzen 5 3600.
   En otro equipo cambian; el primer audio dirá la cifra real.

2. **Requisitos:** Python 3.10 a 3.12 y FFmpeg en el PATH. Si falta algo,
   muestra el comando al usuario y pide permiso antes de instalarlo
   (Windows: `winget install Python.Python.3.12` y `winget install Gyan.FFmpeg`).

3. **Avisa del peso antes de instalar:** entre 6 y 9 GB de disco (programas más
   modelos). Con su OK: `python setup.py`. Tarda; depende de su internet.

4. **Comprueba:** `python voz.py doctor`.

5. **Cierra el onboarding:** cambia la primera línea de ESTE archivo a
   `<!-- ONBOARDING_STATUS: COMPLETO (YYYY-MM-DD) -->`.

---

## 🎙️ NARRAR

**Paso 1 — La muestra (una sola vez por voz).** Pídele un audio o video donde
hable **sólo él**, claro, sin música ni ruido. Sirve una nota de voz del celular.
Necesitas un tramo de **8 a 15 segundos** seguidos.

```
python voz.py muestra ruta/al/audio.mp4 --nombre mi-voz --inicio 12 --fin 24
```

El comando escribe lo que entendió. **Léeselo al usuario y pregúntale si es
exactamente lo que dice.** Si hay una palabra mal, corrige `voces/mi-voz.txt`.
El texto tiene que coincidir con el audio palabra por palabra: de eso depende
cuánto se parece el clon.

**Paso 2 — El guion.** Un archivo `.txt`, una idea por frase, con acentos y
signos. Antes de narrar aplica las reglas de escritura de `SKILL.md` (números
en letras, siglas como suenan, frases cortas).

**Paso 3 — Narrar.**

```
python voz.py narrar guion.txt --voz mi-voz
```

Sale `salidas/<guion>/narracion.wav`, una frase por archivo e `informe.json`.
El programa escucha cada frase y repite solo las que no dicen lo pedido.

**Paso 4 — Entrega.** Dile dónde quedó el audio, cuánto tardó y qué frases
marcó como dudosas. Pídele que las escuche: el programa comprueba las palabras,
no si el tono le gusta.

---

## 🌎 DOBLAR UN VIDEO A OTRO IDIOMA

**Si la skill ya estaba instalada y `python voz.py doblar -h` da error**, es una
versión anterior: actualízala. Con `git pull` si la carpeta es un repositorio;
si no, descarga de nuevo `voz.py`, `AGENTS.md`, `SKILL.md` y `README.md` desde
https://github.com/BRPLia/clonar-voz-skill y reemplázalos. No hay que reinstalar
nada ni volver a guardar la voz: `voces/`, `modelos/` y `config.json` no se tocan.

Cuando el usuario pida «dobla este video al portugués» (o a inglés, francés,
alemán, italiano, japonés, coreano, chino o ruso). El video tiene que ser suyo
o tener permiso de quien habla. La traducción la haces **tú**; el programa
escucha, habla y monta.

**Paso 1 — Escuchar.**

```
python voz.py escuchar ruta/al/video.mp4
```

Escribe `salidas/<video>/frases.json`: cada frase con su segundo de inicio y de
fin. **Léelo entero antes de traducir.** Corrige en ese archivo las palabras
mal oídas y las repetidas. Si una frase no tiene sentido (texto que se repite,
algo que nadie diría), el programa oyó mal: pregúntale al usuario qué dice ahí.
Si aparece una frase donde sólo hay música o silencio, bórrala.

**Paso 2 — La voz.** Si no hay una voz guardada (`python voz.py doctor`), sácala
del mismo video: elige en `frases.json` un tramo de 8 a 15 segundos sin música y
úsalo en `muestra` con `--inicio` y `--fin`.

**Paso 3 — Traducir.** Crea `salidas/<video>/<Idioma>.txt` con el nombre en
inglés del idioma (`Portuguese.txt`, `English.txt`, `Japanese.txt`...): **una
línea por frase, en el mismo orden y la misma cantidad**. Reglas:

- Traduce el sentido, como lo diría una persona de ese país, no palabra por palabra.
- Cada línea se tiene que poder decir en el tiempo de su frase (`fin - inicio`).
  Si el idioma alarga la frase, dilo más corto.
- Números en letras, siglas como suenan, con signos y acentos (ver `SKILL.md`).
- Si una frase del original quedó cortada a la mitad, puedes mover unas palabras
  a la línea siguiente para que cada línea suene completa.

**Paso 4 — Doblar.**

```
python voz.py doblar ruta/al/video.mp4 --voz mi-voz --idioma Portuguese
```

Sale `salidas/<video>/<Idioma>/<video>-<Idioma>.mp4`, `doblaje.wav` (sólo la
voz) e `informe.json`.

**Paso 5 — Ajustar.** El programa avisa de dos cosas:

- *Frases que no caben*: acorta esa línea de la traducción.
- *Frases dudosas*: lo que se oyó no coincide con el texto; cambia la palabra
  que falló por un sinónimo.

Vuelve a correr `doblar`: sólo se rehacen las líneas que cambiaste.

**Paso 6 — Entrega, con sus límites.** Dile al usuario:

- El audio original se reemplaza entero: **la música y los efectos del video no
  pasan al doblaje**. Si tiene la música aparte, se mezcla después con `doblaje.wav`.
- La boca no se mueve con el idioma nuevo; en videos sin rostro no se nota.
- Tú comprobaste las palabras, no el acento. Que lo escuche alguien que hable
  ese idioma antes de publicarlo.
- Para varios idiomas, repite los pasos 3 a 5; `escuchar` se hace una sola vez.
