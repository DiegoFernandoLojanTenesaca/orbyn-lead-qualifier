# orbyn-lead-qualifier

Bot de Telegram que **cualifica leads contra un ICP** usando un LLM, con
**failover automático entre 7 proveedores** (Groq → Cerebras → Mistral →
SambaNova → NVIDIA → Gemini → OpenRouter) y logging en **Google Sheets +
SQLite local**.

Entrega para la prueba técnica de [Orbyn](https://orbyn.ai/).

> **Bot público de pruebas**: [`@orbyn_lead_dl_bot`](https://t.me/orbyn_lead_dl_bot)

## Qué hace

1. Recibe un mensaje en Telegram con datos libres de un lead.
2. Sanitiza el input (anti prompt-injection, truncado).
3. Lo pasa por un grafo **LangGraph**: `validate_input → classify → format_reply`.
4. El nodo `classify` llama al LLM pidiendo **JSON estricto**
   (`response_format=json_object`) y lo valida con Pydantic.
5. Responde al chat con `✅ CUALIFICADO` / `❌ NO CUALIFICADO`, confianza,
   señales detectadas (tipo, tamaño, ubicación, necesidades) y 2-3 frases
   de razonamiento.
6. Persiste cada decisión en **SQLite** (`leads.db`) y, si está configurado,
   añade una fila en una **Google Sheet** con: `received_at, chat_id,
   username, text, decision, reason, confidence, provider, model,
   latency_ms, prompt_version`.

### ICP por defecto

- Empresa de **servicios o consultoría** (no producto / fábrica / autónomos).
- **≥ 5 empleados**.
- **España o Latinoamérica**.
- Interés explícito en **automatización, IA, agentes, RAG o chatbots**.

## Demo

```text
$ make smoke
=== Caso 1 ===
INPUT: Empresa de consultoria de gestion, 15 empleados, Madrid, quieren
       automatizar su proceso de captacion de leads con un agente de IA.
OUTPUT: CUALIFICA  [OK]  conf=0.90  provider=groq  778ms

=== Caso 2 ===
INPUT: Soy autonomo y vendo cursos online de yoga, trabajo solo.
OUTPUT: NO CUALIFICA  [OK]  conf=0.20  provider=groq  782ms

=== Caso 3 ===
INPUT: Fabrica de calzado en Brasil, 80 empleados, automatizar control
       de calidad con vision por computador.
OUTPUT: NO CUALIFICA  [OK]  conf=0.60  provider=groq  757ms  (fabrica != servicios)

=== Caso 4 ===
INPUT: Despacho juridico en Bogota, 12 abogados, asistente RAG con
       jurisprudencia interna.
OUTPUT: CUALIFICA  [OK]  conf=0.90  provider=groq  717ms
```

4/4 con Groq Llama-3.3-70B; latencia media ~750 ms.

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
tests/              16 tests, todos offline (mockean los providers)
scripts/            smoke_classify.py contra LLM real
```

## Setup local

```bash
git clone https://github.com/DiegoFernandoLojanTenesaca/orbyn-lead-qualifier.git
cd orbyn-lead-qualifier
make install
cp .env.example .env   # rellena TELEGRAM_TOKEN y al menos GROQ_API_KEY
make test              # 16 tests offline
make smoke             # 4 leads reales (necesita la API key)
make run               # bot vivo
```

API key de Groq gratis en [console.groq.com](https://console.groq.com).

### Google Sheets (opcional)

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

## Docker

```bash
docker compose up -d --build
```

El bot persiste `leads.db` en el volumen `./data`.

## Despliegue actual

Corriendo en un **Huawei P40 Lite vía Termux** con supervisor que reinicia
ante crashes y watchdog que detecta cambios de red. Mismo patrón que los otros
bots del repositorio personal. Detalle en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Producción

Las consideraciones reales sobre **errores, prompt injection y costes** para
llevar esto a producción están en
[`docs/PRODUCTION.md`](docs/PRODUCTION.md) (rúbrica de Orbyn).

## Licencia

MIT.
