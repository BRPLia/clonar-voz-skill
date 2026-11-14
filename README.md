# Clonar Voz Skill 🎙️

Clona **tu propia voz** en tu computadora y úsala para narrar tus videos.
Gratis, sin cuentas y sin subir tu voz a ningún lado.

Funciona con un agente de IA (Claude Code, Codex o Antigravity): tú le hablas
en español y él hace la instalación y los audios.

## Instalación

Abre tu agente en una carpeta vacía y pégale esto:

```
Descarga e instala esta skill en esta carpeta: https://github.com/BRPLia/clonar-voz-skill — lee su AGENTS.md y haz toda la preparación. Dime qué computadora detectaste antes de instalar.
```

## Qué necesitas

| Tu computadora | ¿Funciona? | Espera por cada minuto de audio |
|---|---|---|
| Tarjeta NVIDIA de 6 GB o más | Sí, modelo grande | cerca de 1 minuto |
| Tarjeta NVIDIA de 4 GB | Sí, modelo chico | entre 1 y 4 minutos |
| Sin tarjeta NVIDIA | Sí, pero lento | entre 4 y 7 minutos |
| Mac o tarjeta AMD | Sin probar | — |

Medido en una RTX 5060 Ti (16 GB) con un procesador Ryzen 5 3600. Además:
Python 3.10 a 3.12, FFmpeg y entre 6 y 9 GB de disco.

## Cómo se usa

1. Dale a tu agente un audio o video donde hables tú, claro y sin música.
   Con 8 a 15 segundos alcanza.
2. Pásale tu guion.
3. Recibes `narracion.wav` con tu voz.

El programa escucha cada frase que genera y repite solo las que salieron mal.

## Reglas

- Clona **solo tu voz**, o la de alguien que te dio permiso.
- Si publicas un video con voz clonada en YouTube, marca «contenido alterado o sintético».
- Tu muestra de voz queda en la carpeta `voces/` de tu equipo. No se comparte con nadie.

## Créditos

Usa [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) (Apache 2.0) y Whisper (MIT).
Esta skill se publica con licencia MIT.
