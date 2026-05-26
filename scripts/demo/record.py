"""Graba un demo automatizado del bot navegando una conversación mockeada.

La conversación esta hardcodeada en demo.html con las respuestas REALES que
dio el bot en produccion (las copie del chat de Telegram); no son inventadas.

Salida:
- scripts/demo/out/demo.webm  (Playwright nativo)
- scripts/demo/out/demo.mp4   (re-encodeado con ffmpeg si esta disponible)
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)


async def record():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Viewport vertical ajustado al phone + cabecera. 720x900 entra justo
        # y deja menos negro a los lados. Mantenemos 2x para nitidez.
        context = await browser.new_context(
            viewport={"width": 720, "height": 900},
            record_video_dir=str(OUT),
            record_video_size={"width": 720, "height": 900},
            device_scale_factor=2,
        )
        page = await context.new_page()
        await page.goto(f"file://{ROOT}/demo.html")

        # Espera a que el script de la pagina escriba "DONE" en el title
        # (le pusimos document.title = "DONE" al terminar la animacion).
        for _ in range(180):  # max ~60s
            title = await page.title()
            if title == "DONE":
                break
            await asyncio.sleep(0.5)

        await context.close()
        await browser.close()

    # Renombrar el webm que escribio playwright
    webms = sorted(OUT.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not webms:
        print("no se genero webm")
        return
    final_webm = OUT / "demo.webm"
    if webms[-1] != final_webm:
        webms[-1].replace(final_webm)
    # Limpia webms anteriores
    for w in webms[:-1]:
        try:
            w.unlink()
        except OSError:
            pass

    print(f"webm: {final_webm} ({final_webm.stat().st_size // 1024} KB)")

    # ffmpeg → mp4 con H.264 (compatible con Telegram, mail, etc.)
    if shutil.which("ffmpeg"):
        mp4 = OUT / "demo.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(final_webm),
            "-c:v", "libx264", "-preset", "slow", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-an",  # sin audio
            "-movflags", "+faststart",
            str(mp4),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"mp4 : {mp4} ({mp4.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(record())
