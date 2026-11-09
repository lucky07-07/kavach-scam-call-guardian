# Records the demo video from the real screen (kavach.web must be running on 127.0.0.1:7861, Evon up for the
# assistant scene). Headless Chrome via Playwright records the page; the page plays no sound, so the real call audio
# and Timbre's warning are laid under the video with ffmpeg at the moments they happen. English subtitles in the page.
#   data/demo/kavach_demo.mp4
# Usage: .venv\Scripts\python -m kavach.make_demo_video
import json, shutil, subprocess, sys, time, wave
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
AUDIO, RUNS, OUT = ROOT / "data" / "test_audio", ROOT / "data" / "runs", ROOT / "data" / "demo"
APP = "http://127.0.0.1:7861/"
W, H = 1600, 1000
FFMPEG = shutil.which("ffmpeg") or next(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"), None)

SCAM, GENUINE = "te_kyc_otp", "te_fraud_alert"
GLOSS = {
    SCAM: ["Hello madam, I'm calling from SBI head office. Your KYC has expired — if you don't update it today, your account will be blocked.",
           "Oh… what should I do?",
           "You'll get an OTP on your phone now. Tell it to me and I'll update it from here."],
    GENUINE: ["I'm from HDFC Bank's fraud monitoring team. A ₹8,500 online transaction just came on your card. Was that you?",
              "No, it wasn't me.",
              "OK — we've blocked your card for now. Get a new one at your branch or in the app. We will never ask you for an OTP or PIN."],
}
WARNING_GLOSS = {SCAM: "“Careful, this is a scam call. If they ask for an OTP or PIN, or threaten to stop your bank account, hang up now.”"}
QUESTION = "అమ్మకి వచ్చిన చివరి call ఏంటి? సాక్ష్యం సరిగ్గా ఉందా?"
QUESTION_GLOSS = "The daughter asks: “What was the last call Amma got? Is the evidence intact?”"

CARD = """<html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0d0f13;color:#eceef2;
font-family:Inter,Segoe UI,sans-serif"><div style="max-width:1100px;padding:40px">{body}</div></body></html>"""
TITLE = CARD.format(body="""
<div style="display:flex;align-items:center;gap:16px;margin-bottom:28px"><div style="width:56px;height:56px;border-radius:16px;
background:#eceef2;color:#0d0f13;display:grid;place-items:center;font-weight:700;font-size:28px">K</div>
<div style="font-size:52px;font-weight:700;letter-spacing:-1px">Kavach</div></div>
<div style="font-size:30px;line-height:1.4;font-weight:500">A second listener that protects elderly Telugu speakers from scam calls.</div>
<div style="font-size:21px;color:#9aa1ad;margin-top:22px">Gnani Prisma hears the call · Gnani Evon reasons · code decides · Gnani Timbre warns in Telugu · evidence sealed on Bitcoin</div>
<div style="font-size:16px;color:#6f7684;margin-top:34px">Real system, real run. Calls voiced with Gnani Timbre for this demo.</div>""")
END = CARD.format(body="""
<div style="font-size:40px;font-weight:700;letter-spacing:-.6px;margin-bottom:26px">Eight agents, one job: keep the listener safe.</div>
<div style="font-size:21px;line-height:1.75;color:#c6cbd4">
Listener — <b>Prisma</b> separates caller and listener, Telugu and English<br>
Prosecutor &amp; Defender — <b>Evon</b> argue both sides, quoting the caller<br>
Judge — <b>code</b>: a claim counts only if the caller's own words prove it<br>
Guardian — <b>Evon + Timbre</b> warn in Telugu · Reporter drafts the 1930 complaint<br>
Notary — evidence sealed on <b>Bitcoin</b> · Family assistant over <b>MCP</b></div>
<div style="font-size:18px;color:#9aa1ad;margin-top:30px">All Gnani: Prisma v2.5 · Evon v3.3 (self-hosted) · Timbre — #GnaniAI #GreatIndianAIInternshipChallenge</div>""")


def secs(path):
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "rec"
    shutil.rmtree(tmp, ignore_errors=True)
    sounds = []   # (start second in the video, wav path)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp), record_video_size={"width": W, "height": H},
                                  color_scheme="light")
        page = ctx.new_page()
        t0 = time.monotonic()
        now = lambda: time.monotonic() - t0
        page.set_content(TITLE)
        page.wait_for_timeout(6000)

        # scene 1: a scam call, then its sealed evidence
        page.goto(APP)
        page.wait_for_selector("#call option", state="attached")
        page.wait_for_timeout(1500)
        start = now()
        res = page.evaluate("([c, o]) => kavachDemo(c, o)", [SCAM, {"gloss": GLOSS[SCAM], "warningGloss": WARNING_GLOSS[SCAM]}])
        sounds.append((start, AUDIO / f"{SCAM}_mono.wav"))
        warn_wav = RUNS / SCAM / "warning.wav"
        sounds.append((start + res["warnAt"] + 0.4, warn_wav))
        page.wait_for_timeout(int((secs(warn_wav) + 1.2) * 1000))
        page.evaluate("() => kavachCaption('Anyone can check later that the evidence was not changed after the call.', 'Evidence sealed on Bitcoin')")
        page.wait_for_timeout(3000)
        page.evaluate("() => { kavachCaption(''); document.getElementById('sealCard').scrollIntoView({behavior: 'smooth', block: 'center'}); }")
        page.wait_for_timeout(1500)
        page.evaluate("(c) => kavachVerify(c, false)", SCAM)
        page.wait_for_timeout(2500)
        page.evaluate("(c) => kavachVerify(c, true)", SCAM)
        page.wait_for_timeout(4000)
        page.evaluate("() => window.scrollTo({top: 0, behavior: 'smooth'})")
        page.wait_for_timeout(800)

        # scene 2: a genuine bank call stays silent
        page.evaluate("() => kavachCaption('Now a genuine bank call.', '')")
        page.wait_for_timeout(2000)
        start = now()
        page.evaluate("([c, o]) => kavachDemo(c, o)", [GENUINE, {"gloss": GLOSS[GENUINE]}])
        sounds.append((start, AUDIO / f"{GENUINE}_mono.wav"))
        page.evaluate("() => kavachCaption('Genuine call: Evon\\'s claims are not backed by the caller\\'s words, so Kavach stays silent.', 'Safe')")
        page.wait_for_timeout(5000)

        # scene 3: after the call, the family asks Kavach (Evon over the Kavach MCP server)
        page.evaluate("() => { kavachCaption(''); kavachView('assist'); }")
        page.wait_for_timeout(1200)
        page.evaluate("(q) => kavachCaption(q, 'Ask Kavach · Evon reads the sealed evidence through MCP tools · the wait is shortened in this video')",
                      QUESTION_GLOSS)
        page.evaluate("(q) => { kavachAsk(q); }", QUESTION)   # do not await: the start of the wait is what gets timed
        ask_at = now()
        page.wait_for_function("() => { const a = document.querySelector('#thread .a:last-child'); return a && !a.textContent.includes('Reading'); }",
                               timeout=120000)
        answered_at = now()
        answer = page.evaluate("() => document.querySelector('#thread .a:last-child .te').textContent")
        gloss = ("Kavach: “The last call was a scam — the caller asked for money and threatened arrest. The evidence has not changed; "
                 "its Bitcoin entry is pending.”" if "మోసం" in answer and "మారలేదు" in answer and "arrest" in answer
                 else "Kavach answers in Telugu, from the sealed evidence only.")
        page.evaluate("(g) => kavachCaption(g, 'Answer, in Telugu')", gloss)
        page.wait_for_timeout(7000)
        page.evaluate("() => kavachCaption('')")

        page.set_content(END)
        page.wait_for_timeout(8000)
        ctx.close()
        browser.close()

    video = next(tmp.glob("*.webm"))
    total = now()
    print(f"recorded {total:.0f} s; sounds at", [(round(s, 1), w.name) for s, w in sounds])
    inputs, filters = ["-i", str(video)], []
    for i, (start, wav) in enumerate(sounds, 1):
        inputs += ["-i", str(wav)]
        filters.append(f"[{i}:a]aresample=48000,adelay={int(start * 1000)}|{int(start * 1000)},volume=1.6[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(1, len(sounds) + 1))
    filters.append(f"{mix}amix=inputs={len(sounds)}:normalize=0,apad[aout]")
    # the wait for Evon's answer is cut to 3 s (the caption says so); everything else is real time
    a, b = ask_at + 3.0, answered_at - 0.3
    if b - a > 2:
        filters += [f"[0:v]trim=0:{a:.2f},setpts=PTS-STARTPTS[v1]", f"[0:v]trim=start={b:.2f},setpts=PTS-STARTPTS[v2]",
                    "[v1][v2]concat=n=2:v=1:a=0[vout]", "[aout]asplit=2[x1][x2]",
                    f"[x1]atrim=0:{a:.2f},asetpts=PTS-STARTPTS[b1]", f"[x2]atrim=start={b:.2f},asetpts=PTS-STARTPTS[b2]",
                    "[b1][b2]concat=n=2:v=0:a=1[afinal]"]
        vmap, amap = "[vout]", "[afinal]"
    else:
        vmap, amap = "0:v", "[aout]"
    out = OUT / "kavach_demo.mp4"
    cmd = [str(FFMPEG), "-y", *inputs, "-filter_complex", ";".join(filters), "-map", vmap, "-map", amap,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    meta = {"recorded_seconds": round(total, 1), "evon_wait_cut": [round(a, 1), round(b, 1)],
            "sounds": [(round(s, 2), w.name) for s, w in sounds], "file": str(out)}
    (OUT / "kavach_demo.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
