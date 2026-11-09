# Records a 1080p walkthrough of the real screen for the trailer: a visible cursor picks a call, presses Analyse,
# opens the Judge's reasoning, plays the warning, verifies the seal and an edited copy, runs a genuine call, then opens
# Ask Kavach (where the family alert waits) and types a question. Every click is a real click on the running app (saved
# runs, Replay mode). The moments the trailer cuts to are written next to the video, read from the video itself: a
# 10 px square in the bottom-right corner flips colour at each one (the recording drifts against the wall clock), and
# the trailer crops that corner away.
#   data/demo/walkthrough.mp4, data/demo/walkthrough.json
# Needs the screen running (.venv\Scripts\python -m kavach.web).
# Usage: .venv\Scripts\python -m kavach.trailer.record_walkthrough
import json, shutil, subprocess, sys, time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent.parent
OUT = ROOT / "data" / "demo"
APP = "http://127.0.0.1:7861/"
W, H = 1920, 1080
ZOOM = 1.5                # the page is laid out as if 1280x720 and drawn 1.5x, so the app fills the frame sharply
FFMPEG = shutil.which("ffmpeg") or next(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"), None)
QUESTION = "అమ్మకి వచ్చిన చివరి call ఏంటి? సాక్ష్యం సరిగ్గా ఉందా?"

# a drawn cursor, since headless recordings show none; it follows real mouse events and ripples on each click
CURSOR = """
addEventListener('DOMContentLoaded', () => {
  document.body.style.zoom = ZOOM;
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:0;top:0;z-index:99999;pointer-events:none;transform:translate(-80px,-80px)';
  c.innerHTML = '<svg width="26" height="30" viewBox="0 0 17 22"><path d="M1 1v17l4.5-4.5 3.2 7 3-1.4-3.1-6.6h6.4z" fill="#111" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  document.documentElement.appendChild(c);
  const k = document.createElement('div'); k.id = 'sync';
  k.style.cssText = 'position:fixed;right:0;bottom:0;width:10px;height:10px;z-index:99999;background:#f0f';
  document.documentElement.appendChild(k);
  addEventListener('mousemove', e => c.style.transform = `translate(${e.clientX - 2}px,${e.clientY - 2}px)`, true);
  addEventListener('mousedown', e => {
    const r = document.createElement('div');
    r.style.cssText = `position:fixed;left:${e.clientX - 22}px;top:${e.clientY - 22}px;width:44px;height:44px;border-radius:50%;
      border:3px solid #4f46e5;z-index:99998;pointer-events:none;transition:all .45s ease-out;opacity:.9`;
    document.documentElement.appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 600);
  }, true);
});
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = OUT / "rec_walk"
    shutil.rmtree(tmp, ignore_errors=True)
    marks = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required", f"--window-size={W},{H}"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp), record_video_size={"width": W, "height": H},
                                  color_scheme="light")
        ctx.add_init_script(CURSOR.replace("ZOOM", str(ZOOM)))
        page = ctx.new_page()
        t0 = time.monotonic()
        order = []

        def mark(name):
            order.append(name)
            page.evaluate("(n) => document.getElementById('sync').style.background = n % 2 ? '#0ff' : '#f0f'", len(order))

        wait = page.wait_for_timeout

        def go(sel, click=True, steps=28, pause=350):
            box = page.locator(sel).first.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
            wait(pause)
            if click:
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

        page.goto(APP)
        page.wait_for_selector("#call option", state="attached")
        page.mouse.move(W / 2, H / 2)
        wait(1200)
        mark("start")

        # a scam call
        go("#call", click=False)
        page.select_option("#call", "te_kyc_otp")
        wait(500)
        go("#mReplay")
        wait(300)
        mark("scam_analyse")
        go("#go")
        page.wait_for_selector("#famCard .fam")
        mark("scam_done")
        wait(1500)
        go('.step[data-id="judge"]')
        mark("judge_open")
        wait(2600)
        go('.step[data-id="judge"]')
        wait(400)
        go("#playW")
        mark("warning_play")
        wait(2200)
        go("#playF")
        mark("family_play")
        wait(2200)

        # the seal: verify the original, then an edited copy
        page.mouse.move(W * 0.62, H * 0.6, steps=10)
        for _ in range(6):
            page.mouse.wheel(0, 160)
            wait(90)
        wait(500)
        mark("seal_view")
        go("#vO")
        page.wait_for_selector("#vres .ok", timeout=60000)      # the check reads the Bitcoin block, so it takes a moment
        mark("verify_original")
        wait(1400)
        go("#vE")
        page.wait_for_selector("#vres .no", timeout=60000)
        mark("verify_edited")
        wait(2200)
        for _ in range(8):
            page.mouse.wheel(0, -200)
            wait(70)
        wait(500)

        # a genuine bank call
        go("#call", click=False)
        page.select_option("#call", "te_fraud_alert")
        wait(400)
        mark("genuine_analyse")
        go("#go")
        page.wait_for_function("document.querySelector('#verdict').classList.contains('SAFE')")
        mark("genuine_done")
        wait(2600)

        # the family's side: the alert is waiting on Ask Kavach; they ask about it
        go("#call", click=False)
        page.select_option("#call", "te_kyc_otp")
        go("#go")
        page.wait_for_selector("#famCard .fam")
        wait(600)
        mark("ask_tab")
        go("#tAssist")
        wait(1600)
        go("#q")
        mark("ask_type")
        page.keyboard.type(QUESTION, delay=55)
        wait(500)
        page.mouse.move(*(lambda b: (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2))(page.locator("#askBtn").bounding_box()), steps=20)
        mark("ask_ready")
        wait(1500)
        mark("end")
        wait(800)                 # let the last flip reach the recording
        ctx.close()
        browser.close()
    video = next(tmp.glob("*.webm"))
    out = OUT / "walkthrough.mp4"
    r = subprocess.run([str(FFMPEG), "-y", "-i", str(video), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-r", "30", "-an", "-movflags", "+faststart", str(out)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    # read the sync square: one colour flip per mark, in order
    raw = subprocess.run([str(FFMPEG), "-v", "error", "-i", str(out), "-vf", "crop=4:4:1914:1074,scale=1:1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    px = [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]
    colour = ["m" if r > 150 and g < 110 and b > 150 else "c" if g > 150 and r < 110 and b > 150 else None for r, g, b in px]
    flips, last = [], "m"
    for i, c in enumerate(colour):              # a flip counts once the new colour holds for two frames
        if c and c != last and i + 1 < len(colour) and colour[i + 1] == c:
            flips.append(i / 30)
            last = c
    if len(flips) != len(order):
        sys.exit(f"sync square: {len(flips)} flips for {len(order)} marks")
    marks = {name: round(t, 2) for name, t in zip(order, flips)}
    (OUT / "walkthrough.json").write_text(json.dumps(marks, indent=2), encoding="utf-8")
    print("wrote", out, marks)


if __name__ == "__main__":
    main()
