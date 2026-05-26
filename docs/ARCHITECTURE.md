# Arquitectura

## Visión general

```
        ┌──────────────┐  long-poll   ┌──────────────────────┐
        │ Telegram API │ ◄──────────► │ telegram_bot.py      │
        └──────────────┘              │ (handlers /start /id │
                                      │  + handle_text)      │
                                      └──────────┬───────────┘
                                                 │ ainvoke(state)
                                      ┌──────────▼───────────┐
                                      │ LangGraph (graph.py) │
                                      │                      │
                                      │ validate_input       │  saneado, truncado
                                      │      │               │  anti-injection
                                      │      ▼               │
                                      │  classify ─────────► │  ┌───────────────┐
                                      │      │               │  │ LLMClient     │
                                      │      ▼               │  │ groq → ceb →  │
                                      │ format_reply         │  │ mist → samb…  │
                                      └──────────┬───────────┘  └───────┬───────┘
                                                 │                       │
                              reply_text         │   classification      │
                                                 │                       │
                                      ┌──────────▼───────────┐    ┌──────▼──────┐
                                      │ Telegram (respuesta) │    │ SQLite      │
                                      └──────────────────────┘    │ leads.db    │
                                                                  └──────┬──────┘
                                                                         │ (si SA OK)
                                                                  ┌──────▼──────┐
                                                                  │ Google Sheet│
                                                                  └─────────────┘
```

## Decisiones

### Por qué LangGraph
La tarea (clasificación binaria + lookup) cabría en una función. Uso LangGraph
porque:
1. **Separación clara** de validación, llamada al modelo y formateo: cada
   nodo es trivial de testear de forma aislada (ver `tests/test_nodes.py`).
2. **Punto natural** para añadir nodos futuros (HITL para casos `confidence <
   0.6`, traducción si llega en inglés, enriquecimiento con info externa) sin
   reescribir el flujo.
3. **El template de Orbyn** lo usa: usar la misma herramienta demuestra
   alineamiento con el stack que evalúa.

### Por qué failover entre 7 providers gratis
Con APIs gratis (Groq + Cerebras + Mistral + SambaNova + NVIDIA + Gemini +
OpenRouter), el límite por minuto/día se alcanza rápido. La cascada hace que
el bot siga respondiendo aunque la primera (o las dos primeras) se agoten.
La lógica está aislada en `app/services/llm.py` y se prueba sin tocar red
(`tests/test_llm_failover.py`).

### Por qué SQLite + Google Sheets, no sólo Sheets
- La Sheet **es para el humano** (Orbyn la mira).
- SQLite es la **fuente autoritativa**: si Sheets cae o no está configurado
  todavía, ningún lead se pierde. El flag `synced_to_sheet` permite
  reconciliar después.
- Para el alcance de la prueba no hace falta Postgres. Si esto creciera, el
  upgrade a Postgres es local a `app/services/storage.py`.

### Polling vs webhook
**Polling**. El webhook necesita un dominio público con TLS; complicaría el
despliegue en el Huawei P40 (que es donde corre realmente). Telegram
recomienda webhook a escala, no para este caso.

## Cómo testar

```bash
make install
make test         # 16 tests offline, < 1 s
make smoke        # 4 leads contra Groq real
make run          # bot vivo
```

## Dónde corre

- **Local**: `python -m app.main`.
- **Docker**: `docker compose up -d`.
- **Huawei P40 Lite** (donde está hoy): Termux + supervisor `run-orbyn.sh`
  paralelo a los otros bots (`jarvis`, `jarvis-henrry`). Ver
  `scripts/deploy_p40.sh`.
