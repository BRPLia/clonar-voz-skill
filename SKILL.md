---
name: clonar-voz
description: Clona la voz del usuario en su computadora con Qwen3-TTS y narra guiones con ella, gratis y sin subir nada a internet. Úsala cuando pida clonar su voz, narrar un guion con su voz o generar una voz en off local.
---

# Clonar Voz — manual

## Cómo funciona
El modelo recibe dos cosas: una **muestra** de 8 a 15 segundos de la voz y el
**texto exacto** de esa muestra. Con eso arma un molde de la voz y después lee
cualquier texto con ese molde. No hay entrenamiento: el molde se hace en segundos.

## Comandos
| Comando | Qué hace |
|---|---|
| `python setup.py --detectar` | Dice qué equipo hay y qué instalaría. No instala. |
| `python setup.py` | Instala todo y descarga los modelos según el equipo. |
| `python voz.py doctor` | Muestra modelo, equipo y voces guardadas. |
| `python voz.py muestra <audio> --nombre X --inicio s --fin s` | Guarda una voz y transcribe su muestra. |
| `python voz.py narrar <guion.txt> --voz X` | Narra el guion y revisa cada frase. |

`narrar` acepta `--idioma` (`Spanish`, `English`, `Portuguese`, `French`,
`German`, `Italian`, `Japanese`, `Korean`, `Chinese`, `Russian`): la misma voz
habla otro idioma. El guion tiene que estar escrito en ese idioma.

## La muestra: lo que más pesa
- **8 a 15 segundos.** Con 3 segundos se parece poco. Pasados los 20, el modelo
  se vuelve inestable. El comando rechaza menos de 5 y más de 20.
- **Una sola persona, sin música ni ruido.** Lo que haya de fondo se copia.
- **Hablando como quieres que suene la narración.** Si la muestra es apagada,
  todo saldrá apagado.
- **El texto debe coincidir con el audio.** Revisa siempre `voces/X.txt`.

## Cómo escribir el guion para que suene bien
- Frases cortas, una idea por frase. Cada frase se genera aparte.
- Con acentos y signos de pregunta: cambian la entonación.
- Números en letras: «doscientos treinta», no «230».
- Siglas y palabras en inglés, como suenan: «yutub», «ei ai», o cámbialas.
- Si una palabra sale mal dos veces, cámbiala por un sinónimo.

## La revisión automática
Después de generar, el programa transcribe cada frase y la compara con el texto.
Si se parece menos de un 85 %, repite esa frase hasta dos veces y se queda con
la mejor. Lo que siga dudoso queda listado en `informe.json` (`frases_dudosas`).
Los números y los nombres propios dan falsas alarmas: la transcripción los
escribe distinto. Escucha antes de descartar.

## Velocidad
El modelo genera frase por frase, y lo que más acelera es mandar varias frases
a la vez. `setup.py` calcula cuántas caben en la memoria de la tarjeta y lo
guarda en `config.json` (`lote`). Si el equipo se queda sin memoria, baja ese número.

Medido en una RTX 5060 Ti de 16 GB con un Ryzen 5 3600 (segundos de espera por
minuto de audio):

| Caso | Espera | Memoria de video |
|---|---|---|
| Modelo grande, 5 frases a la vez | 62 s | 7,2 GB |
| Modelo grande, de una en una | 230 s | 4,7 GB |
| Modelo chico, 5 frases a la vez | 59 s | 5,3 GB |
| Modelo chico, de una en una | 227 s | 2,8 GB |
| Modelo chico, sin tarjeta, 5 frases a la vez | 235 s | — |
| Modelo chico, sin tarjeta, de una en una | 377 s | — |
| Modelo grande, sin tarjeta, de una en una | 514 s | — |

## Límites
- Sólo la voz del usuario o de quien le dio permiso.
- Mac y tarjetas AMD: sin probar. Se instala el modo de procesador.
- Al publicar en YouTube un video con voz clonada, marcar «contenido alterado o sintético».
