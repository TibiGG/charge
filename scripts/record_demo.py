"""Record a ~60s scripted walkthrough of the running local demo to demo.mp4 (insurance policy).

    make demo            # in another terminal
    .venv/bin/python scripts/record_demo.py
"""
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo.mp4"
TMP = ROOT / ".recording"
BASE = "http://localhost:5173"


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(TMP),
                            record_video_size={"width": 1280, "height": 800})
        pg = ctx.new_page()
        pause = pg.wait_for_timeout

        pg.goto(f"{BASE}/?p=margaret&at=08:00")
        pg.wait_for_selector(".vial-wrap")
        pause(4000)
        pg.locator(".vial-wrap").nth(4).click()            # Flexibility & mobility: weakest-sourced aim
        pause(4500)
        pg.keyboard.press("Escape")
        pause(1200)
        pg.get_by_text("What should I do today?").first.click()
        pg.wait_for_selector("h1", timeout=15000)
        pause(5000)
        pg.mouse.wheel(0, 700)
        pause(3500)
        pg.locator("summary", has_text="Why this?").first.click()
        pause(1500)
        for _ in range(6):
            pg.mouse.wheel(0, 450)
            pause(1500)
        proofs = pg.locator("summary", has_text="The exact steps")
        if proofs.count():
            proofs.first.click()
            pause(1000)
            pg.mouse.wheel(0, 500)
            pause(3500)

        pg.goto(f"{BASE}/ask?p=margaret")
        pause(2000)
        pg.get_by_role("button", name="How can I get stronger?").click()
        pause(4500)
        pg.get_by_role("button", name="I have chest pain when I run").click()
        pause(1000)
        pg.mouse.wheel(0, 400)
        pause(5000)

        pg.goto(f"{BASE}/?p=dan")
        pause(4000)
        pg.goto(f"{BASE}/?p=sam")
        pause(3500)

        video = pg.video.path()
        ctx.close()
        b.close()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "28", "-preset", "veryfast", "-movflags", "+faststart", str(OUT)], check=True)
    shutil.rmtree(TMP, ignore_errors=True)
    print(OUT, round(OUT.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
