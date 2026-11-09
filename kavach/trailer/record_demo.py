# Records the screen for the full demo video (2-3 min), one continuous recording of the real app in Replay mode, at the
# same readable size as the trailer walkthrough: Analyse a scam call (the transcript appears in time with the call audio,
# English subtitles); open Prosecute, Defend and Judge; play the warning; play the family alert; open the 1930
# complaint; verify the seal and an edited copy; run a genuine bank call; open Ask Kavach, where the alert waits, and type
# the family's question. Each moment the demo cuts to is marked with the sync square (see record_walkthrough).
#   data/demo/demo_walk.mp4, data/demo/demo_walk.json
# Needs the screen running (.venv\Scripts\python -m kavach.web).
# Usage: .venv\Scripts\python -m kavach.trailer.record_demo
import json, shutil, subprocess, sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from kavach.make_demo_video import GLOSS, SCAM, GENUINE
from kavach.trailer.record_walkthrough import APP, CURSOR, FFMPEG, OUT, QUESTION, W, H, ZOOM

DEMO_CALL = """async ([id, gloss, colour]) => {
  window.__done = false;
  await kavachDemo(id, {gloss, onStart: () => document.getElementById('sync').style.background = colour});
  window.__done = true;
}"""


def flips(video):
    # seconds at which the sync square changes colour; a flip counts once the new colour holds for two frames
    raw = subprocess.run([str(FFMPEG), "-v", "error", "-i", str(video), "-vf", "crop=4:4:1914:1074,scale=1:1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    px = [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]
    colour = ["m" if r > 150 and g < 110 and b > 150 else "c" if g > 150 and r < 110 and b > 150 else None for r, g, b in px]
    out, last = [], "m"
    for i, c in enumerate(colour):
        if c and c != last and i + 1 < len(colour) and colour[i + 1] == c:
            out.append(i / 30)
            last = c
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = OUT / "rec_demo"
    shutil.rmtree(tmp, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required", f"--window-size={W},{H}"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp), record_video_size={"width": W, "height": H},
                                  color_scheme="light")
        ctx.add_init_script(CURSOR.replace("ZOOM", str(ZOOM)))
        page = ctx.new_page()
        order = []
        wait = page.wait_for_timeout

        def colour(n):
            return "#0ff" if n % 2 else "#f0f"

        def mark(name):
            order.append(name)
            page.evaluate("(c) => document.getElementById('sync').style.background = c", colour(len(order)))

        def go(sel, click=True, steps=28, pause=350):
            box = page.locator(sel).first.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
            wait(pause)
            if click:
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

        def top(sel=None, offset=90):
            page.evaluate("([sel, off]) => { if (!sel) return scrollTo(0, 0); const el = document.querySelector(sel);"
                          " scrollTo(0, scrollY + el.getBoundingClientRect().top - off); }", [sel, offset])

        def run_call(call_id, start_mark):
            # Analyse in demo mode: a real click on Analyse starts it; the square flips when the call audio starts
            page.evaluate("([id, gloss, c]) => { document.getElementById('go').onclick = () => (" + DEMO_CALL + ")([id, gloss, c]); }",
                          [call_id, GLOSS[call_id], colour(len(order) + 1)])
            go("#go", steps=26, pause=300)
            order.append(start_mark)
            page.wait_for_function("window.__done === true", timeout=120000)

        def fresh(call_id):
            page.evaluate("(c) => window.name = c", colour(len(order)))   # the sync square keeps its colour across the reload
            page.goto(APP)
            page.wait_for_selector("#call option", state="attached")
            page.click("#mReplay")
            page.select_option("#call", call_id)
            page.mouse.move(W * 0.3, H * 0.6)
            page.wait_for_load_state("networkidle")
            wait(4500)                # the status check (Evon health, with one retry) settles first

        page.goto(APP)
        fresh(SCAM)

        # the scam call, analysed while it plays
        mark("take_run")
        wait(4200)                    # the narrator introduces the run
        run_call(SCAM, "call_go")
        mark("verdict")
        wait(1800)

        # why: the two Evon agents argue, the code Judge decides
        mark("take_why")
        for step, hold in (("prosecutor", 2600), ("defender", 2200), ("judge", 3400)):
            go(f'.step[data-id="{step}"]', steps=16, pause=200)
            wait(hold)
        go('.step[data-id="judge"]', steps=4, pause=100)
        mark("why_end")

        # the warning to the listener
        top("#warning")
        page.mouse.move(W * 0.5, H * 0.45)
        wait(300)
        mark("take_warn")
        wait(1500)                    # the narrator: "Kavach warns her"
        go("#playW", steps=18, pause=250)
        mark("warn_click")
        wait(6500)

        # the family alert
        mark("take_family")
        wait(1500)
        go("#playF", steps=18, pause=250)
        mark("family_click")
        wait(7400)

        # the complaint
        top("#reportCard", 120)
        page.mouse.move(W * 0.45, H * 0.4)
        wait(300)
        mark("take_report")
        go("#reportCard summary", steps=18, pause=250)
        wait(400)
        page.evaluate("document.querySelector('#reportCard').scrollIntoView({block: 'start'}); scrollBy(0, -80)")
        page.mouse.move(W * 0.6, H * 0.5)
        wait(3800)
        page.evaluate("document.querySelector('#reportCard').open = false")

        # the seal, verified as it is and as an edited copy
        top("#sealCard", 260)
        page.mouse.move(W * 0.45, H * 0.5)
        wait(300)
        mark("take_seal")
        wait(1600)
        go("#vO", steps=16, pause=200)
        page.wait_for_selector("#vres .ok", timeout=60000)
        mark("seal_ok")
        wait(900)
        go("#vE", steps=14, pause=200)
        page.wait_for_selector("#vres .no", timeout=60000)
        mark("seal_bad")
        wait(2200)

        # a genuine bank call
        fresh(GENUINE)
        mark("take_genuine")
        wait(300)
        run_call(GENUINE, "genuine_go")
        mark("genuine_safe")
        wait(6500)

        # the family's side: the scam call is analysed again off camera, since the alert comes from it
        page.select_option("#call", SCAM)
        page.evaluate("document.getElementById('go').onclick = null")
        page.evaluate("() => kavachDemo('te_kyc_otp', {})")
        page.wait_for_selector("#famCard .fam")
        page.evaluate("() => kavachCaption('')")
        top()
        page.mouse.move(W * 0.6, H * 0.3)
        wait(400)
        mark("take_ask")
        wait(1200)
        go("#tAssist", steps=16, pause=200)
        wait(2600)                    # the alert, waiting at the top
        go("#q", steps=16, pause=150)
        page.keyboard.type(QUESTION, delay=40)
        wait(700)
        go("#askBtn", click=False, steps=12, pause=200)
        mark("ask_end")
        wait(800)
        ctx.close()
        browser.close()
    video = next(tmp.glob("*.webm"))
    out = OUT / "demo_walk.mp4"
    r = subprocess.run([str(FFMPEG), "-y", "-i", str(video), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-r", "30", "-an", "-movflags", "+faststart", str(out)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    f = flips(out)
    if len(f) != len(order):
        sys.exit(f"sync square: {len(f)} flips for {len(order)} marks: {order}")
    marks = {name: round(t, 2) for name, t in zip(order, f)}
    (OUT / "demo_walk.json").write_text(json.dumps(marks, indent=2), encoding="utf-8")
    print("wrote", out, marks)


if __name__ == "__main__":
    main()
