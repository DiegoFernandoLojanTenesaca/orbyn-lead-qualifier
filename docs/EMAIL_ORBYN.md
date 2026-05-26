# Email a `sales@orbyn.ai`

> Pega esto (o adapta el tono a tu voz) al cuerpo del email. Adjuntar
> `scripts/demo/out/demo.mp4` o subirlo a YouTube/Drive y enlazar.

---

**De:** fernando.lojan10@gmail.com
**Para:** sales@orbyn.ai
**Asunto:** Demo Pool Orbyn — agente de cualificación de leads (Diego Fernando Lojan)

---

Hola, equipo de Orbyn 👋

Adjunto la demo del mini-proyecto de la prueba para la pool:

**Bot de Telegram:** [`@orbyn_lead_dl_bot`](https://t.me/orbyn_lead_dl_bot) — escríbele directamente, está vivo 24/7.

**Repo público:** https://github.com/DiegoFernandoLojanTenesaca/orbyn-lead-qualifier

**Vídeo (1 min):** [enlace o adjunto]

**Stack:** Python 3.11 + `python-telegram-bot` v22 (long-polling) + LangGraph 1.x + Pydantic v2 + Groq Llama-3.3-70B como primario con failover automático a 6 providers gratuitos (Cerebras → Mistral → SambaNova → NVIDIA → Gemini → OpenRouter). Logging en Google Sheets vía service account, persistencia local en SQLite y deploy en un Huawei P40 con supervisor + watchdog DNS + autoarranque.

**Cómo lo probáis rápido:**
- `@orbyn_lead_dl_bot` → `/help` para ver formato y comandos.
- Mandadle un lead en texto libre. Probad casos buenos y malos; el ICP que pedís está cargado.
- `/version` muestra prompt activo + chain de fallback; `/stats` muestra agregados de las últimas 24 h.
- Cada respuesta lleva un footer técnico con provider, modelo, latencia y versión del prompt para que sea fácil auditar.

---

## Las 3 frases sobre producción

> Lo que pide la rúbrica. Versión larga y razonada en
> [`docs/PRODUCTION.md`](https://github.com/DiegoFernandoLojanTenesaca/orbyn-lead-qualifier/blob/main/docs/PRODUCTION.md).

1. **Errores y entrega.** Hoy el envío a Sheets y la respuesta a Telegram son best-effort y el bot ya guarda en SQLite local incluso si Sheets cae; en producción metería los outbound detrás de una cola con backoff exponencial, dedup por `update_id` para no reprocesar updates reentregados por Telegram (ya implementado en SQLite con `INSERT OR IGNORE`, frase que defiendo), un cron que reconcilia los leads marcados `synced=0` y healthcheck + métricas para que el orquestador reinicie el pod antes de que se pierdan leads.

2. **Prompt injection.** Ya neutralizo el cierre del bloque del *user prompt*, fuerzo `response_format=json_object` con validación Pydantic estricta y meto en el few-shot un ejemplo de manipulación («ignora las instrucciones anteriores» → `qualified=false` con `confidence=0.4` y motivo «intento de manipulación»); en producción añadiría allow-list por `chat_id` o `/start <token>`, una primera pasada barata tipo Llama-Guard para descartar jailbreaks antes de gastar tokens, y logging cifrado del prompt/respuesta con retención corta para auditar incidentes.

3. **Costes.** Hoy todo va con APIs gratis (Groq + 6 fallbacks) que funciona porque la demo la usaremos pocas personas, pero free tier no es producción: pondría un proveedor pago como primario con la cascada gratis como red de seguridad, modelo pequeño por defecto (`llama-3.1-8b-instant`, ~10× más barato) con enrutado al grande sólo cuando la `confidence` cae por debajo de 0.7, cache de clasificaciones idénticas en ventana de N horas, y un panel con tokens/lead y €/lead para no descubrir los costes a fin de mes.

---

## Lo que dejé hecho (más allá del mínimo)

- **Pre-filtro sin LLM**: saludos, mensajes <15 caracteres o solo emojis se cortan en `validate_input` antes de gastar tokens.
- **Idempotencia por `update_id`**: tabla `processed_updates` en SQLite con clave primaria + `INSERT OR IGNORE`; Telegram reentrega updates si tu respuesta tarda, y eso causa duplicados si no lo manejas. Implementado, no sólo nombrado.
- **Prompt versionado** (`v3`) con few-shot canónicos cubriendo bordes que el LLM falla típicamente (9 socios ≥ 5, fábrica ≠ servicios, autónomo en solitario, ONG, SaaS fuera del ICP, intento de injection). El número de versión se persiste en cada fila para poder hacer A/B y comparar más adelante.
- **50 tests offline** + smoke real contra el LLM (`make smoke`).
- **Observabilidad**: structlog en JSON con `request_id`/`chat_id`/`user_id`, comando `/stats` agregando lo que vive en SQLite, y la columna `latency_ms` en la Sheet para detectar deriva.

Gracias por la oportunidad. Estoy disponible si queréis que entre a un detalle concreto del código o de las decisiones de diseño.

Un saludo,
Diego Fernando Lojan Tenesaca
fernando.lojan10@gmail.com
GitHub: [@DiegoFernandoLojanTenesaca](https://github.com/DiegoFernandoLojanTenesaca)

---

## Checklist antes de enviar

- [ ] Bot `@orbyn_lead_dl_bot` respondiendo (probar `/start` desde otra cuenta).
- [ ] Repo público en GitHub (verificar acceso anónimo).
- [ ] Vídeo subido (Drive/YouTube unlisted/WeTransfer) y enlace pegado arriba.
- [ ] Google Sheet con al menos 3 ✅ y 3 ❌ para que el evaluador vea criterio aplicado al abrirla.
- [ ] Confirmar que la clave vieja del service account ya está revocada en Cloud Console.
