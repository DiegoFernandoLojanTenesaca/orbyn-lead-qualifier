# orbyn-lead-qualifier

Bot de Telegram que **cualifica leads contra un ICP** usando un LLM, con
**failover automático entre 7 proveedores** (Groq → Cerebras → Mistral →
SambaNova → NVIDIA → Gemini → OpenRouter) y logging en **Google Sheets +
SQLite local**.

Entrega para la prueba técnica de [Orbyn](https://orbyn.ai/).

> **Demo privada** — el bot está corriendo en un dispositivo personal y solo
> se comparte el username con el equipo de Orbyn por email (`sales@orbyn.ai`).
> No pegamos el enlace público aquí para evitar tráfico de terceros que
> ensucie la Sheet de prueba.

## Qué hace

1. Recibe un mensaje en Telegram con datos libres de un lead.
2. Sanitiza el input (anti prompt-injection, truncado al límite configurado).
3. Lo pasa por un grafo **LangGraph**: `validate_input → classify → format_reply`.
4. El nodo `classify` llama al LLM con un **prompt versionado** (`v2`) que
   incluye 5 *few-shot examples* (3 negativos + 2 positivos) para forzar
   criterio real y prevenir el sesgo "siempre cualifica".
5. La salida del LLM debe ser **JSON estricto** (`response_format=json_object`)
   y se valida con Pydantic; si el JSON está corrupto o fuera de schema, se
   descarta y se reintenta con el siguiente provider.
6. Responde al chat con `✅ CUALIFICADO` / `❌ NO CUALIFICADO`, confianza,
   señales detectadas (tipo, tamaño, ubicación, necesidades) y 2-3 frases
   de razonamiento.
7. Persiste cada decisión en **SQLite** (`leads.db`) y, si está configurado,
   añade una fila en una **Google Sheet** con: `received_at, chat_id,
   username, text, decision, reason, confidence, provider, model,
   latency_ms, prompt_version`.

### ICP por defecto

- Empresa de **servicios o consultoría** (no fábrica, no producto SaaS, no autónomo).
- **≥ 5 empleados**.
- **España o Latinoamérica**.
- Interés explícito en **automatización, IA, agentes, RAG o chatbots**.

## Demo (smoke real contra Groq)

```text
$ make smoke
=== Caso 1: consultora Madrid 15 emp ===
OUTPUT: CUALIFICA      conf=0.96  provider=groq  939ms

=== Caso 2: autónomo yoga ===
OUTPUT: NO CUALIFICA   conf=0.90  provider=groq  599ms
        → autonomo en solitario, falla tipo y tamano

=== Caso 3: fábrica Brasil 80 emp ===
OUTPUT: NO CUALIFICA   conf=0.88  provider=groq  1567ms
        → planta industrial, el resto encaja pero el tipo está fuera del ICP

=== Caso 4: despacho Bogotá 12 abogados RAG ===
OUTPUT: CUALIFICA      conf=0.94  provider=groq  690ms
        → servicios en LATAM con corpus interno
```

4/4 con Groq Llama-3.3-70B; latencia media ~950 ms. Los casos negativos
demuestran que el criterio se aplica de verdad, no es una plantilla.

## Stack

- Python 3.11+
- [python-telegram-bot](https://docs.python-telegram-bot.org/) v22 (long-polling)
- [LangGraph](https://langchain-ai.github.io/langgraph/) 1.x
- Pydantic v2 + pydantic-settings
- httpx async para los providers (todos OpenAI-compatible)
- structlog en JSON
- gspread + service account de GCP
- SQLite local

Estructura:

```
app/
├── core/           config (pydantic-settings), structlog, prompts versionados
├── schemas/        LeadInput, ICPSignals, Classification, LeadRecord
├── services/       llm.py (failover), telegram_bot.py, storage.py, sheets.py
├── agent/          state, nodes (validate/classify/format), graph (LangGraph)
└── main.py         entrypoint
docs/               ARCHITECTURE.md + PRODUCTION.md (las 3 frases pedidas)
tests/              25 tests, todos offline (mockean los providers)
scripts/            smoke_classify.py contra LLM real
```

## Setup local

```bash
git clone https://github.com/DiegoFernandoLojanTenesaca/orbyn-lead-qualifier.git
cd orbyn-lead-qualifier
make install
cp .env.example .env   # rellena TELEGRAM_TOKEN y al menos GROQ_API_KEY
make test              # 25 tests offline
make smoke             # 4 leads reales (necesita la API key)
make run               # bot vivo
```

API key de Groq gratis en [console.groq.com](https://console.groq.com).

### Google Sheets

1. Crea proyecto en [Google Cloud Console](https://console.cloud.google.com).
2. Habilita **Google Sheets API** y **Google Drive API**.
3. Crea un *service account* y descarga el JSON.
4. Crea una Sheet, copia su ID (la cadena larga en la URL) y **comparte la
   Sheet con el email del service account como editor**.
5. En `.env`:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=./service_account.json
   GOOGLE_SHEET_ID=1abcDEF...
   GOOGLE_SHEET_TAB=leads
   ```
6. La pestaña `leads` se crea sola con los headers en la primera fila.

Si las variables están vacías, el bot funciona igual y solo persiste en SQLite.

## Tests

```bash
make test
```

25 tests offline cubriendo:

- Schemas Pydantic (validación de input, rangos, formato Telegram).
- Nodos del grafo (saneado, error path, formateo).
- Failover del LLM (primario OK, primario falla → cae al siguiente,
  todos fallan, tolerancia a basura antes/después del JSON).
- **Criterio real**: el prompt está versionado, contiene la regla
  anti-injection, incluye ejemplos negativos, neutraliza intentos del
  lead de cerrar el bloque del *user prompt*, y la salida formateada
  difiere entre `qualified` y `not_qualified` (no es plantilla fija).

## Docker

```bash
docker compose up -d --build
```

El bot persiste `leads.db` en el volumen `./data`.

## Despliegue actual

Corriendo en un **Huawei P40 Lite vía Termux** con supervisor (`run-orbyn.sh`)
que reinicia ante crashes, **watchdog de DNS** que detecta cambios de red y
**autoarranque al boot** (`Termux:Boot`). Mismo patrón que los otros bots del
mismo dispositivo. Detalle en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Producción

Las consideraciones reales sobre **errores, prompt injection y costes** para
llevar esto a producción están en
[`docs/PRODUCTION.md`](docs/PRODUCTION.md) (rúbrica de Orbyn).

## Licencia

MIT.
