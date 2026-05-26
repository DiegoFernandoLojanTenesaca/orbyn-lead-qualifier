# orbyn-lead-qualifier

Bot de Telegram que cualifica leads contra un ICP usando un LLM (Groq por defecto,
con failover automático a Cerebras, Mistral, SambaNova, NVIDIA, Gemini y OpenRouter)
y registra cada decisión en una Google Sheet.

Pensado como entrega para la prueba técnica de [Orbyn](https://orbyn.ai/).

> Estado: en construcción. Esta línea se irá actualizando a medida que avancen
> los módulos.

## ¿Qué hace?

1. Recibe un mensaje libre en Telegram con datos de un lead.
2. Lo pasa por un grafo (LangGraph) que valida el input, extrae señales relevantes
   y pregunta al LLM si encaja con el ICP.
3. **ICP por defecto**: empresa de servicios o consultoría, ≥ 5 empleados,
   España o Latinoamérica, interés explícito en automatización o IA.
4. Responde al chat con `cualificado` / `no cualificado` y un razonamiento corto.
5. Loguea fecha, datos recibidos, decisión y motivo en una Google Sheet.

## Stack

- Python 3.11+
- [python-telegram-bot](https://docs.python-telegram-bot.org/) v21 (long-polling)
- [LangGraph](https://langchain-ai.github.io/langgraph/) para el grafo del agente
- Pydantic v2 + pydantic-settings
- structlog para logging estructurado
- gspread + Google service account para la Sheet
- SQLite local como auditoría y respaldo si Sheets falla

## Setup local

```bash
git clone https://github.com/DiegoFernandoLojanTenesaca/orbyn-lead-qualifier.git
cd orbyn-lead-qualifier
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # rellena TELEGRAM_TOKEN y al menos una *_API_KEY
python -m app.main
```

Lo más rápido es dejar sólo `GROQ_API_KEY` (clave gratis en
[console.groq.com](https://console.groq.com)).

## Despliegue

El bot se ejecuta como un único proceso de larga duración. En esta entrega
corre en un Huawei P40 Lite vía Termux con un supervisor que lo reinicia ante
fallos y un watchdog que detecta cambios de red y refresca las conexiones.
También hay `Dockerfile` para correrlo en cualquier VPS.

## Tests

```bash
pytest -q
```

## Producción

Las consideraciones para llevar esto a producción real están en
[`docs/PRODUCTION.md`](docs/PRODUCTION.md).

## Licencia

MIT
