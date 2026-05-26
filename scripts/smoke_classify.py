"""Smoke test contra el LLM real: clasifica 3 leads de ejemplo y muestra la salida.

Uso:
    python scripts/smoke_classify.py

Necesita que en .env haya al menos una *_API_KEY valida.
"""
from __future__ import annotations

import asyncio
import json

from app.core.logging import configure_logging
from app.core.prompts import build_messages
from app.services.llm import LLMClient

CASES: list[tuple[str, bool]] = [
    (
        "Empresa de consultoria de gestion, 15 empleados, Madrid, "
        "quieren automatizar su proceso de captacion de leads con un agente de IA.",
        True,
    ),
    (
        "Soy autonomo y vendo cursos online de yoga, trabajo solo. "
        "Quiero un chatbot para WhatsApp.",
        False,
    ),
    (
        "Fabrica de calzado en Brasil, 80 empleados, "
        "buscan automatizar control de calidad con vision por computador.",
        False,  # fabrica != servicios/consultoria
    ),
    (
        "Despacho juridico en Bogota, 12 abogados, "
        "quieren un asistente RAG con su jurisprudencia interna.",
        True,
    ),
]


async def main() -> None:
    configure_logging("WARNING")  # menos ruido para el smoke
    async with LLMClient() as client:
        for i, (text, expected) in enumerate(CASES, 1):
            print(f"\n=== Caso {i} (esperado: {'CUALIFICA' if expected else 'NO'}) ===")
            print(f"INPUT: {text}")
            try:
                c = await client.classify(build_messages(text))
            except Exception as e:
                print(f"ERROR: {e}")
                continue
            verdict = "CUALIFICA" if c.qualified else "NO CUALIFICA"
            ok = "OK" if c.qualified == expected else "DIVERGE"
            print(f"OUTPUT: {verdict}  [{ok}]  conf={c.confidence:.2f}  "
                  f"provider={c.provider_used}  {c.latency_ms}ms")
            print(f"REASON: {c.reason}")
            print("SIGNALS:", json.dumps(c.signals.model_dump(), ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
