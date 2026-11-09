# Launch-style trailer for Kavach (60 s, for the "Demo Day Drop" award). Story: the phone rings, the scam call itself
# (real audio, typed on screen), cut dead on the OTP request -> what it costs (official loss figure) -> Kavach -> how it
# works (eight agents, dissolving into the app's own step strip) -> the real app in motion, one continuous take per scene
# (recorded by record_walkthrough: Analyse and the Judge; the Telugu warning) -> the family alert as it reaches a phone
# (its real text and Timbre voice note) -> the family asks Kavach (Ask tab) -> Hindi -> a genuine call left alone -> the
# seal verified and an edited copy rejected -> 100% Gnani. Timbre narration, whole sentences of the real warnings
# (cut at their pauses), synthesised SFX and a 100 BPM bed; every scene starts on the beat.
#   data/demo/trailer/kavach_trailer.mp4  (1920x1080)
# Needs: narration.py and record_walkthrough.py run first.
# Usage: .venv\Scripts\python -m kavach.trailer.make_trailer
import json, math, re, shutil, subprocess, sys, time, wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent.parent
DEMO = ROOT / "data" / "demo"
OUT = DEMO / "trailer"
SR = 48000
W, H = 1920, 1080
FFMPEG = shutil.which("ffmpeg") or next(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"), None)
RUN = ROOT / "data" / "runs" / "te_kyc_otp"
CALL, TE_WARN, FAMILY = ROOT / "data" / "test_audio" / "te_kyc_otp_mono.wav", RUN / "warning.wav", RUN / "family_alert.wav"
HI_WARN = DEMO / "warning_hi_template.wav"
WALK = DEMO / "walkthrough.mp4"      # from kavach.trailer.record_walkthrough: real clicks on the running screen
CALL_FROM = 12.70                    # the caller's OTP request in the scam call (its turn starts at 12.79 s)
LOSS = "22,845"                      # ₹ crore lost to cyber fraud in India in 2024: MHA reply in the Lok Sabha, July 2025
ANSWER = 1.5                         # the phone rings this long before the call is picked up


# ---------------------------------------------------------------- timeline: every scene starts on the beat
BPM = 100
BEAT = 60 / BPM


def pause_before(path, limit, start=0.0):
    # the end of the last whole sentence before `limit` seconds: the start of the last pause (silencedetect) in range
    r = subprocess.run([str(FFMPEG), "-hide_banner", "-i", str(path), "-af", "silencedetect=noise=-35dB:d=0.18", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", r.stderr)]
    fits = [x for x in starts if start + 0.5 < x <= limit]
    return max(fits) if fits else limit


def marks():
    return json.loads((DEMO / "walkthrough.json").read_text(encoding="utf-8"))


def timeline():
    vo = json.loads((OUT / "narration.json").read_text(encoding="utf-8"))
    m = marks()
    warn_take = m["warn_click"] - 0.5                     # the warn scene starts half a second before the play click
    te_end, fam_end, hi_end = pause_before(TE_WARN, 3.0), pause_before(FAMILY, 3.6), pause_before(HI_WARN, 3.2)
    call_end = pause_before(CALL, CALL_FROM + 3.8, CALL_FROM)
    fam_at = 0.25 + vo["family"] + 0.15                   # the voice note plays right after the narration line
    scenes = [  # (id, at least seconds, narration, extra audio [(file, at, from, to)], flash on the cut, walkthrough take start)
        ("call", ANSWER + (call_end - CALL_FROM) + 2.3, None, [(CALL, ANSWER, CALL_FROM, call_end)], False, None),
        ("stakes", 4.2, "stakes", [], True, None),
        ("reveal", 0, "reveal", [], True, None),
        ("pipeline", 5.4, "agents", [], False, m["take_listen"]),
        ("listen", 4.8, "listen", [], False, m["take_listen"]),
        ("warn", 0, None, [(TE_WARN, 0.5, 0, te_end)], True, warn_take),
        ("family", 0, "family", [(FAMILY, fam_at, 0, fam_end)], False, None),
        ("ask", 3.6, "ask", [], False, m["take_ask"]),
        ("hindi", 0, "hindi", [(HI_WARN, 1.12, 0, hi_end)], False, None),
        ("genuine", 3.6, "genuine", [], False, m["take_genuine"]),
        ("seal", 3.6, "seal", [], False, m["take_seal"]),
        ("sovereign", 4.8, "sovereign", [], True, None),
        ("end", 0, "end", [], True, None)]
    t, out = 0.0, []
    for sid, least, key, extras, flash, take in scenes:
        lead = 0.25 if key else 0.0
        need = max(least, lead + (vo[key] if key else 0) + 0.2, *[at + (b - a) + 0.2 for _, at, a, b in extras])
        dur = math.ceil(need / BEAT - 1e-6) * BEAT
        out.append({"id": sid, "start": round(t, 3), "dur": round(dur, 3), "vo": key, "vo_at": round(t + lead, 3), "flash": flash,
                    "take": take, "extras": [{"file": str(f), "at": round(t + at, 3), "from": a, "to": b} for f, at, a, b in extras]})
        t += dur
    out[0]["punch"] = round(ANSWER + (call_end - CALL_FROM) + 0.15, 3)     # the call is cut dead on the OTP request
    out[next(i for i, s in enumerate(out) if s["id"] == "family")]["note_at"] = fam_at
    return out, round(t + 0.3, 2)


# ---------------------------------------------------------------- audio: music bed and SFX, synthesised
def read_wav(path):
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(1)
        rate = w.getframerate()
    return np.interp(np.arange(0, len(x) * SR / rate) * rate / SR, np.arange(len(x)), x).astype(np.float32)


def env(n, a=0.01, r=0.3):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / r)


def lowpass(x, k=8):
    return np.convolve(x, np.ones(k) / k, mode="same")


def whoosh(d=0.55):
    n = int(d * SR)
    noise = lowpass(np.random.default_rng(1).standard_normal(n), 6)
    shape = np.sin(np.pi * np.arange(n) / n) ** 2
    sweep = np.sin(2 * np.pi * np.cumsum(np.linspace(200, 1400, n)) / SR) * 0.15
    return (noise * 0.35 + sweep) * shape


def impact(d=1.6):
    n = int(d * SR); t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * (55 * t - 18 * t ** 2)) * np.exp(-t / 0.45)
    crack = lowpass(np.random.default_rng(2).standard_normal(n), 3) * np.exp(-t / 0.05) * 0.6
    return (boom + crack) * 0.9


def riser(d=2.2):
    n = int(d * SR); t = np.arange(n) / SR
    f = 120 + 900 * (t / d) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    noise = lowpass(np.random.default_rng(3).standard_normal(n), 4) * 0.25
    return (tone + noise) * (t / d) ** 1.6


def ring(d=0.55):
    # one burst of a phone's trill ring: two tones switching 20 times a second, with a buzz under it
    n = int(d * SR); t = np.arange(n) / SR
    f = np.where((t * 20).astype(int) % 2 == 0, 1320, 1760)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.3 + np.sign(np.sin(2 * np.pi * 150 * t)) * 0.06
    return tone * np.minimum(1, t / 0.01) * np.minimum(1, (d - t) / 0.03)


def tick(d=0.08, f=2200):
    n = int(d * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * np.exp(-t / 0.015) * 0.5


def hat(d=0.04):
    n = int(d * SR)
    return np.diff(np.random.default_rng(4).standard_normal(n + 1)) * np.exp(-np.arange(n) / SR / 0.012) * 0.12


def music(total, drop, gap, stop):
    # 100 BPM, A minor (Am - F - C - G). Pad only until the reveal; the beat (kick, off-beat hats, sub bass) drops in on
    # the reveal, the whole bed goes silent for the gap just before it, and the beat stops for the end card
    n = int(total * SR); t = np.arange(n) / SR
    chords = [(220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (130.8, 164.8, 196.0), (196.0, 246.9, 293.7)]
    pad, bass, beat = (np.zeros(n, np.float32) for _ in range(3))
    bar = BEAT * 4
    for i, start in enumerate(np.arange(0, total, bar)):
        a, b = int(start * SR), min(n, int((start + bar * 1.05) * SR))
        seg = np.arange(b - a) / SR
        ch = chords[i % 4]
        pad[a:b] += sum(np.sin(2 * np.pi * f * seg) + 0.35 * np.sin(2 * np.pi * 2 * f * seg) for f in ch) \
            * np.minimum(1, seg / 0.6) * np.minimum(1, (bar * 1.05 - seg) / 0.4) * 0.06
        bass[a:b] += np.sin(2 * np.pi * ch[0] / 4 * seg) * np.minimum(1, seg / 0.05) * np.minimum(1, (bar * 1.05 - seg) / 0.2) * 0.22
    k, h = impact(0.32) * 0.6, hat()
    for i, start in enumerate(np.arange(drop, stop, BEAT / 2)):
        place(beat, k if i % 2 == 0 else h, start)
    on = ((t >= drop) & (t < stop)).astype(np.float32)
    mix = lowpass(pad, 12) + (bass + beat) * lowpass(on, 2400)
    mix *= 1 - ((t >= gap) & (t < drop))                                   # the silence before the drop
    return mix * np.minimum(1, t / 1.5) * np.minimum(1, (total - t) / 2.0)


def place(track, clip, at, gain=1.0):
    a = int(at * SR)
    b = min(len(track), a + len(clip))
    if b > a:
        track[a:b] += clip[:b - a] * gain


def sync_flips(video, fps=30):
    # seconds at which the 10 px sync square in the bottom-right corner changes colour (magenta <-> cyan)
    raw = subprocess.run([str(FFMPEG), "-v", "error", "-i", str(video), "-vf", f"fps={fps},crop=4:4:1914:1074,scale=1:1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    px = [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]
    colour = ["m" if r > 150 and g < 110 and b > 150 else "c" if g > 150 and r < 110 and b > 150 else None for r, g, b in px]
    flips, last = [], "m"
    for i, c in enumerate(colour):              # a flip counts once the new colour holds for two frames
        if c and c != last and i + 1 < len(colour) and colour[i + 1] == c:
            flips.append(i / fps)
            last = c
    return flips


def retime(video, scenes, total):
    # headless screen recordings drift against the wall clock when the page is busy (several videos decoding), so each
    # scene is stretched or squeezed back onto its planned start, keeping the picture on the narration and the beat
    v = sync_flips(video)
    if len(v) != len(scenes):
        sys.exit(f"sync square: {len(v)} flips for {len(scenes)} scenes")
    pts = [(v[0] - scenes[0]["start"], 0.0)] + [(vi, s["start"]) for vi, s in zip(v, scenes)] + [(v[-1] + total - scenes[-1]["start"], total)]
    parts = []
    for j, ((a, ta), (b, tb)) in enumerate(zip(pts, pts[1:])):
        parts.append(f"[0:v]trim=start={max(a, 0):.3f}:end={b:.3f},setpts=(PTS-STARTPTS)*{(tb - ta) / max(b - a, 1e-3):.5f}[s{j}]")
    drift = max(abs((b - pts[0][0]) - tb) for b, tb in pts)
    print(f"retimed {len(pts) - 1} segments; largest drift {drift:.2f} s")
    return ";".join(parts) + ";" + "".join(f"[s{j}]" for j in range(len(pts) - 1)) + \
        f"concat=n={len(pts) - 1}:v=1:a=0,fps=30,drawbox=x=1906:y=1066:w=14:h=14:color=0x07080b:t=fill[v]"


def build_audio(scenes, total):
    at = {s["id"]: s["start"] for s in scenes}
    m = marks()
    punch = scenes[0]["punch"]
    bed = music(total, at["reveal"], at["reveal"] - 0.45, at["end"])
    bed *= np.minimum(1, np.maximum(0, np.arange(len(bed)) / SR - punch) / 0.4)   # no music under the call: ring, voice, heartbeat
    voice, fx = np.zeros_like(bed), np.zeros_like(bed)
    for s in scenes:
        if s["vo"]:
            place(voice, read_wav(OUT / f"vo_{s['vo']}.wav"), s["vo_at"], 1.0)
        for e in s["extras"]:
            clip = read_wav(Path(e["file"]))[int(e["from"] * SR): int(e["to"] * SR)]
            clip *= np.minimum(1, (len(clip) - np.arange(len(clip))) / (0.12 * SR)).clip(0, 1)   # end on the pause, softly
            place(voice, clip, e["at"], 0.95)
        if s["flash"]:
            place(fx, impact(1.2), s["start"], 0.75)
        elif s["id"] != "call":
            place(fx, whoosh(0.4), max(0, s["start"] - 0.2), 0.45)
    for k in range(2):                                                 # the phone rings twice, then is answered
        place(fx, ring(), 0.05 + k * 0.7, 0.55)
    for k in range(int((punch - ANSWER) / 0.85)):                      # a heartbeat under the caller
        place(fx, impact(0.22), ANSWER + 0.2 + k * 0.85, 0.35)
        place(fx, impact(0.18), ANSWER + 0.42 + k * 0.85, 0.22)
    place(fx, impact(1.4), punch, 0.9)                                 # cut dead on the OTP request
    place(fx, riser(2.0), at["reveal"] - 2.45, 0.6)                    # riser, then silence, then the drop
    place(fx, impact(), at["reveal"], 0.6)
    place(fx, impact(0.8), at["stakes"] + 0.3, 0.35)                   # the figure lands
    place(fx, riser(1.4), at["sovereign"] - 1.4, 0.5)
    for i in range(8):                                                 # the pipeline lights up, agent by agent
        place(fx, tick(0.05, 1400 + 90 * i), at["pipeline"] + 0.3 + i * 0.42, 0.45)
    for k in ("seal_ok", "seal_bad"):                                  # the two verify clicks
        place(fx, tick(), at["seal"] + m[k] - m["take_seal"], 0.9)
    for i in range(3):
        place(fx, tick(0.06, 1600), at["sovereign"] + 1.4 + i * BEAT, 0.7)
    speech = np.abs(voice) > 0.01                                      # duck the music under speech
    duck = 1 - 0.6 * lowpass(speech.astype(np.float32), int(0.3 * SR))
    mix = bed * duck * 0.9 + voice * 1.0 + fx * 0.8
    mix = np.tanh(mix * 1.1) * 0.92
    out = OUT / "trailer_audio.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return out


# ---------------------------------------------------------------- the stage
LIVE = {  # scene -> (kicker, headline, camera focus)
    "listen": ("1-4 · Prisma listens · Evon argues · the Judge is code", "Analyse: who said what, then the verdict, and why", "45% 30%"),
    "warn": ("5 · Guardian · Gnani Timbre", '<span class="red">Scam</span>: Amma is warned, in Telugu, mid-call', "70% 35%"),
    "genuine": ("A genuine HDFC fraud-alert call", '<span class="green">Safe</span>: no warning, no alert', "60% 35%"),
    "seal": ("7 · Notary · SHA-256 hash chain on Bitcoin", 'Original <span class="green">✓</span> · one byte edited <span class="red">✗</span>', "55% 70%"),
    "ask": ("8 · Family assistant · Evon over the Kavach MCP server", "Then the family asks Kavach, in Telugu", "50% 25%"),
}
AGENTS = [("Listen", "Prisma", "hears the call", ""), ("Prosecute", "Evon", "argues: scam", ""), ("Defend", "Evon", "argues: genuine", ""),
          ("Judge", "code", "decides", "judge"), ("Warn", "Timbre", "warns · alerts family", "voice"), ("Report", "Evon", "drafts the complaint", ""),
          ("Seal", "Bitcoin", "seals the evidence", "chain"), ("Ask", "MCP", "answers the family", "")]

PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Telugu:wght@500;700&family=Noto+Sans+Devanagari:wght@500;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#07080b;color:#f2f3f6;font-family:Inter,sans-serif}
.scene{position:absolute;inset:0;display:grid;place-items:center;opacity:0;visibility:hidden}
.scene.on{visibility:visible;animation:fadein .3s ease forwards}
@keyframes fadein{to{opacity:1}}
@keyframes wordin{to{opacity:1;transform:none;filter:none}}
.red{color:#ff5a4e}.green{color:#4fd08f}.amber{color:#f3b13f}
.te{font-family:"Noto Sans Telugu",Inter,sans-serif}.hi{font-family:"Noto Sans Devanagari",Inter,sans-serif}
.in{opacity:0;transform:translateY(24px);filter:blur(8px)}
.on .in{animation:wordin .55s cubic-bezier(.2,.8,.2,1) var(--d,0s) forwards}
.kick{font-size:26px;letter-spacing:4px;text-transform:uppercase;color:#f3b13f;font-weight:700;text-align:center}
/* the call */
.callbox{width:1500px;text-align:center}
.live{display:inline-flex;align-items:center;gap:14px;font-size:28px;color:#c6cbd4;font-weight:600;padding:12px 26px;border-radius:999px;background:#14171d;border:1px solid #262b36}
.live i{width:14px;height:14px;border-radius:50%;background:#ff5a4e;animation:blink 1s infinite}
@keyframes blink{50%{opacity:.25}}
.bars{display:flex;gap:7px;justify-content:center;align-items:center;height:90px;margin:34px 0 10px}
.bars b{width:9px;border-radius:5px;background:#ff5a4e;height:12px}
.on .bars b{animation:eq .42s ease-in-out infinite alternate;animation-delay:var(--b)}
.bars.stop b{animation:none!important;height:6px!important;background:#3a3f4a}
@keyframes eq{to{height:84px}}
.tel{font-size:62px;font-weight:700;min-height:80px;line-height:1.3}
.en{font-size:34px;color:#9aa1ad;margin-top:16px}
.three{display:flex;gap:28px;justify-content:center;margin-top:60px}
.three span{font-size:40px;font-weight:700;padding:14px 30px;border-radius:16px;background:#14171d;border:1px solid #262b36}
.ringer{position:absolute;inset:0;display:grid;place-items:center;transition:opacity .2s}
.ringer .ph{position:relative;display:grid;place-items:center;text-align:center}
.on .ringer .ph{animation:buzz .09s linear infinite}
.answered .ringer .ph{animation:none}
@keyframes buzz{25%{transform:translate(-5px,2px) rotate(-1deg)}75%{transform:translate(5px,-2px) rotate(1deg)}}
.ring{position:absolute;top:0;left:50%;margin-left:-110px;width:220px;height:220px;border-radius:50%;border:3px solid #4fd08f;opacity:0;box-sizing:border-box}
.on .ring{animation:ring 1s ease-out infinite;animation-delay:var(--r)}
@keyframes ring{from{transform:scale(.8);opacity:.9}to{transform:scale(2.4);opacity:0}}
.cicon{width:220px;height:220px;border-radius:50%;background:#4fd08f;display:grid;place-items:center;font-size:110px;color:#07080b;font-weight:800}
.cin{font-size:30px;letter-spacing:5px;text-transform:uppercase;color:#8a909c;margin-top:70px;font-weight:700}
.cname{font-size:92px;font-weight:800;letter-spacing:-2px;margin-top:10px}
.callbox{width:1500px;text-align:center;opacity:0}.answered .callbox{opacity:1}.answered .ringer{opacity:0}
.cut .callbox{opacity:0}
.punch{position:absolute;inset:0;display:grid;place-items:center;text-align:center;opacity:0;background:#07080b}
.cut .punch{opacity:1;animation:shake .4s linear}
@keyframes shake{20%{transform:translate(-14px,6px)}40%{transform:translate(12px,-8px)}60%{transform:translate(-8px,4px)}80%{transform:translate(5px,-2px)}}
.punch b{display:block;font-size:150px;font-weight:800;letter-spacing:-5px;line-height:1.1}
.punch b+b{color:#ff5a4e;opacity:0}.cut .punch b+b{animation:fadein .3s .55s forwards}
.otp{color:#ff5a4e;font-weight:800}
/* the family alert, as it reaches a phone */
.famwrap{display:flex;align-items:center;gap:110px}
.phone{width:470px;height:880px;border-radius:64px;background:#0d0f13;border:3px solid #2c313c;box-shadow:0 40px 140px rgba(0,0,0,.7),0 0 0 10px #15181e;
  padding:70px 22px 0;box-sizing:border-box;position:relative;transform:translateY(120px) rotate(-4deg);opacity:0}
.on .phone{animation:rise .7s cubic-bezier(.16,.9,.2,1) forwards}
@keyframes rise{to{transform:none;opacity:1}}
.notch{position:absolute;top:18px;left:50%;width:130px;height:30px;margin-left:-65px;border-radius:20px;background:#000}
.pbar{font-size:20px;color:#8a909c;text-align:center;margin-bottom:22px;font-weight:600}
.msg{background:#1a1e26;border-radius:26px;padding:22px 22px 18px;border-left:6px solid #ff5a4e;opacity:0;transform:translateY(-30px) scale(.96)}
.on .msg{animation:wordin .45s .55s cubic-bezier(.2,.8,.2,1) forwards}
.urg{font-size:19px;letter-spacing:2px;font-weight:800;color:#ff5a4e;text-transform:uppercase}
.mt{font-size:22px;line-height:1.55;margin-top:10px;color:#e8eaee}
.vn{display:flex;align-items:center;gap:12px;margin-top:16px;padding:12px 16px;border-radius:18px;background:#232834}
.vn i{font-style:normal;width:40px;height:40px;border-radius:50%;background:#8b85ff;display:grid;place-items:center;font-size:18px}
.vn .wave{display:flex;gap:3px;align-items:center;flex:1;height:36px}
.vn .wave b{width:4px;border-radius:2px;background:#5c6270;height:var(--h)}
.vn.play .wave b{background:#8b85ff;animation:wv .35s ease-in-out infinite alternate;animation-delay:var(--b)}
@keyframes wv{to{height:34px}}
.vn em{font-style:normal;font-size:17px;color:#8a909c}
.famtxt{width:820px}
.famtxt .kick{text-align:left}
.big2{font-size:96px;font-weight:800;letter-spacing:-3px;line-height:1.05;margin-top:18px}
.gloss2{font-size:30px;color:#c6cbd4;line-height:1.45;margin-top:30px}
.note{font-size:21px;color:#6f7684;line-height:1.5;margin-top:34px}
/* the stakes */
.stat .n{font-size:230px;font-weight:800;letter-spacing:-8px;line-height:1;text-align:center;color:#ff5a4e;text-shadow:0 0 80px rgba(255,90,78,.35)}
.on .stat{animation:slam .5s cubic-bezier(.2,.9,.3,1.2) both}
@keyframes slam{from{transform:scale(1.6);filter:blur(14px);opacity:0}to{transform:none;filter:none;opacity:1}}
.stat .n small{font-size:90px;letter-spacing:-2px;color:#f2f3f6;margin-left:24px;text-shadow:none}
.stat .t{font-size:46px;color:#c6cbd4;text-align:center;margin-top:18px}
.stat .src{font-size:24px;color:#6f7684;text-align:center;margin-top:36px}
/* the reveal */
.logo{display:flex;align-items:center;gap:36px;opacity:0;transform:scale(1.3);filter:blur(20px)}
.on .logo{animation:logo .9s cubic-bezier(.16,.9,.2,1) forwards}
@keyframes logo{to{opacity:1;transform:none;filter:none}}
.mark{width:150px;height:150px;border-radius:40px;background:#f2f3f6;color:#07080b;display:grid;place-items:center;font-size:84px;font-weight:800}
.name{font-size:170px;font-weight:800;letter-spacing:-6px}
.sub{font-size:40px;color:#9aa1ad;text-align:center;margin-top:30px;opacity:0}
.on .sub{animation:wordin .7s .5s forwards}
.glow{position:absolute;width:1400px;height:1400px;border-radius:50%;background:radial-gradient(circle,rgba(255,90,78,.18),transparent 60%);opacity:0}
.on .glow{animation:glow 3s ease forwards}
@keyframes glow{to{opacity:1}}
/* the pipeline */
.pwrap{transition:all .7s cubic-bezier(.6,0,.3,1)}
.merge .pwrap{opacity:0;transform:translateY(-260px) scale(.7)}
.prow{position:relative;display:flex;gap:14px;margin-top:44px}
.line{position:absolute;left:40px;right:40px;top:50%;height:2px;background:#232833}
.dot{position:absolute;top:-7px;left:0;width:16px;height:16px;border-radius:50%;background:#f2f3f6;box-shadow:0 0 24px 6px rgba(255,255,255,.45);opacity:0}
.on .dot{animation:run 3.36s .3s linear forwards}
@keyframes run{0%{left:0;opacity:1}96%{opacity:1}100%{left:100%;opacity:0}}
.pc{position:relative;width:196px;height:228px;border-radius:26px;background:#13161c;border:2px solid #232833;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:6px;opacity:.28;transform:scale(.92);transition:all .3s ease;text-align:center}
.pc em{font-style:normal;font-size:18px;color:#6f7684;font-weight:700}
.pc b{font-size:30px}.pc span{font-size:20px;color:#8a909c}.pc p{margin:8px 10px 0;font-size:19px;color:#c6cbd4;line-height:1.25;min-height:48px}
.pc.lit{opacity:1;transform:none;border-color:#4b5263}
.pc.judge.lit{border-color:#ff5a4e;box-shadow:0 0 60px rgba(255,90,78,.4)}.pc.judge.lit b{color:#ff5a4e}
.pc.voice.lit{border-color:#8b85ff}.pc.chain.lit{border-color:#4fd08f}
.pcap{font-size:38px;color:#c6cbd4;margin-top:48px;text-align:center;opacity:0}
.on .pcap{animation:wordin .6s 3.5s forwards}
/* live footage in a window */
.win{position:absolute;left:160px;top:160px;width:1600px;height:900px;border-radius:18px;overflow:hidden;background:#f6f7f9;
  border:1px solid #2a2f3a;box-shadow:0 30px 120px rgba(0,0,0,.6)}
.win video{width:100%;height:calc(100% + 14px);object-fit:cover;object-position:top;transform-origin:var(--fo,50% 30%)}
.on .win.cam video{animation:cam 7s ease-in-out forwards}
@keyframes cam{to{transform:scale(1.05)}}
.pwin{opacity:0;transition:opacity .8s ease}
.merge .pwin{opacity:1}
.label{position:absolute;left:0;right:0;top:34px;text-align:center;font-size:44px;font-weight:700;opacity:0;transform:translateY(-14px)}
.on .label{animation:wordin .5s .15s forwards}
.label small{display:block;font-size:22px;font-weight:600;color:#8a909c;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
/* hindi, sovereign, end */
.warncard{max-width:1500px;text-align:center}
.tag{font-size:34px;color:#8a909c}
.say{font-size:66px;font-weight:700;line-height:1.5;margin-top:20px}
.gloss{font-size:34px;color:#9aa1ad;margin-top:24px}
.big{font-size:96px;font-weight:800;letter-spacing:-3px;line-height:1.05;text-align:center}
.gn{display:flex;gap:36px;justify-content:center;margin-top:56px}
.gm{width:400px;padding:36px 32px;border-radius:28px;background:#11141a;border:1px solid #262b36;text-align:left}
.gm b{display:block;font-size:56px;font-weight:800;letter-spacing:-1.5px}
.gm i{display:block;font-style:normal;font-size:26px;color:#f3b13f;font-weight:700;margin:4px 0 14px}
.gm span{font-size:24px;color:#9aa1ad;line-height:1.4}
.end .name{font-size:150px}
.hash-tags{font-size:28px;color:#6f7684;margin-top:40px;text-align:center}
.flash{position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none;z-index:9}
.flash.go{animation:flash .32s ease-out}
@keyframes flash{from{opacity:.85}to{opacity:0}}
</style></head><body>
<div class="scene" id="call">
 <div class="ringer"><div class="ph"><i class="ring" style="--r:0s"></i><i class="ring" style="--r:.5s"></i><div class="cicon">✆</div>
  <div class="cin">Incoming call · Amma's phone</div><div class="cname">"SBI Head Office"</div></div></div>
 <div class="callbox">
 <div class="live"><i></i>Amma, alone on the line · in Telugu</div>
 <div class="bars" id="bars">BARS</div>
 <div class="tel te" id="tel"></div>
 <div class="en">“You'll get an <span class="otp">OTP</span> on your phone now. Tell it to me.”</div></div>
 <div class="punch"><div><b>One OTP.</b><b>Her savings, gone.</b></div></div></div>
<div class="scene" id="stakes"><div class="stat">
 <div class="n"><span id="crore">₹0</span><small>crore</small></div>
 <div class="t in" style="--d:.6s">lost to cyber fraud in India in 2024</div>
 <div class="src in" style="--d:1.2s">Ministry of Home Affairs, reply in the Lok Sabha, July 2025 (NCRP / CFCFRMS data)</div></div></div>
<div class="scene" id="reveal"><div class="glow"></div><div><div class="logo"><div class="mark">K</div><div class="name">Kavach</div></div>
 <div class="sub">A second listener on the call · built on Gnani AI</div></div></div>
<div class="scene" id="pipeline"><div class="pwrap"><div class="kick">How Kavach works · eight agents, one call</div>
 <div class="prow"><div class="line"><i class="dot"></i></div>CARDS</div>
 <div class="pcap">Only the <span class="red">Judge</span> decides, and it is code: a claim counts only if the caller's own words prove it.</div></div>
 <div class="win pwin" style="--fo:45% 30%"><video id="v_pipeline" src="WALK" muted playsinline preload="auto"></video></div></div>
LIVE_listen
LIVE_warn
<div class="scene" id="family"><div class="famwrap">
 <div class="phone"><div class="notch"></div><div class="pbar">Messages · now</div>
  <div class="msg"><div class="urg">Kavach · urgent · scam call</div><div class="mt te">FAMTEXT</div>
   <div class="vn" id="vn"><i>▶</i><span class="wave">WAVE</span><em>0:03</em></div></div></div>
 <div class="famtxt"><div class="kick">5 · Guardian · the family alert</div>
  <div class="big2 in" style="--d:.2s">Her family is <span class="red">alerted</span>.</div>
  <div class="gloss2 in" style="--d:.9s">“FAMENGLISH”</div>
  <div class="note in" style="--d:1.4s">Text and Timbre voice note built from the Judge's verified tactics, never the caller's words.
   Shown as it would arrive: the SMS / WhatsApp gateway is not connected yet.</div></div></div></div>
LIVE_ask
<div class="scene" id="hindi"><div class="warncard">
 <div class="tag in">The same warning, in Hindi · Timbre</div>
 <div class="say hi in" style="--d:1.2s">सावधान! यह धोखाधड़ी वाली कॉल है।</div>
 <div class="gloss in" style="--d:1.8s">“Careful! This is a fraud call.”</div></div></div>
LIVE_genuine
LIVE_seal
<div class="scene" id="sovereign"><div>
 <div class="kick">Sovereign AI for India</div>
 <div class="big in" style="margin-top:18px">100% Gnani. <span class="amber">Trained in India.</span></div>
 <div class="gn">
  <div class="gm in" style="--d:1.4s"><b>Prisma</b><i>hears</i><span>Speech to text: Telugu, Hindi, English, code-mixed. Separates caller from listener.</span></div>
  <div class="gm in" style="--d:2.0s"><b>Evon</b><i>reasons</i><span>Open-weight 30B LLM, self-hosted by us. Prosecutor, defender, report, family assistant.</span></div>
  <div class="gm in" style="--d:2.6s"><b>Timbre</b><i>speaks</i><span>Text to speech: the warning and the family alert, in Telugu and Hindi.</span></div></div></div></div>
<div class="scene end" id="end"><div style="text-align:center"><div class="logo" style="justify-content:center"><div class="mark">K</div><div class="name">Kavach</div></div>
 <div class="sub" style="font-size:52px;color:#f2f3f6">Keep the listener safe.</div>
 <div class="hash-tags in" style="--d:1.2s">#GnaniAI · #GreatIndianAIInternshipChallenge</div></div></div>
<script>
const TL = TIMELINE, TEL = TELTEXT;
const sleep = ms => new Promise(r => setTimeout(r, ms));
window.prep = async () => {
  // seek every take before the clock starts, so no cut shows a stale or loading frame
  await Promise.all(TL.filter(s => s.take !== null).map(s => new Promise(ok => {
    const v = document.getElementById("v_" + s.id);
    const go = () => { v.addEventListener("seeked", ok, {once: true}); v.currentTime = s.take; };
    v.readyState >= 1 ? go() : v.addEventListener("loadedmetadata", go, {once: true});
  })));
};
window.run = async () => {
  const t0 = performance.now();
  for (const [i, s] of TL.entries()) {
    const due = t0 + s.start * 1000 - performance.now();
    if (due > 0) await sleep(due);
    document.getElementById("sync").style.background = i % 2 ? "#f0f" : "#0ff";   // marks the cut for the retiming
    document.querySelectorAll(".scene.on").forEach(e => e.classList.remove("on"));
    const el = document.getElementById(s.id); el.classList.add("on");
    if (s.flash) { const f = document.getElementById("flash"); f.classList.remove("go"); void f.offsetWidth; f.classList.add("go"); }
    if (s.id !== "pipeline" && s.take !== null) document.getElementById("v_" + s.id).play();
    if (s.id === "call") {   // rings, is answered, the caller's words type out with the audio, then the cut on the OTP request
      const tel = document.getElementById("tel"), ans = ANSWER * 1000, t1 = performance.now() + ans + 100, len = TEL.length;
      setTimeout(() => el.classList.add("answered"), ans);
      (function f() { const p = Math.max(0, Math.min(1, (performance.now() - t1) / ((s.punch - ANSWER - 0.4) * 1000)));
        tel.textContent = TEL.slice(0, Math.round(p * len)); if (p < 1) requestAnimationFrame(f); })();
      setTimeout(() => el.classList.add("cut"), s.punch * 1000);
    }
    if (s.id === "family") setTimeout(() => document.getElementById("vn").classList.add("play"), s.note_at * 1000);
    if (s.id === "stakes") {
      const n = document.getElementById("crore"), t1 = performance.now() + 150;
      (function f() { const p = Math.max(0, Math.min(1, (performance.now() - t1) / 1300)), e = 1 - Math.pow(1 - p, 3);
        n.textContent = "₹" + Math.round(LOSS * e).toLocaleString("en-IN"); if (p < 1) requestAnimationFrame(f); })();
    }
    if (s.id === "pipeline") {
      el.querySelectorAll(".pc").forEach((c, k) => setTimeout(() => c.classList.add("lit"), 300 + k * 420));
      setTimeout(() => el.classList.add("merge"), (s.dur - 1.3) * 1000);   // dissolve into the app's own step strip
    }
  }
  await sleep((TOTAL - TL[TL.length - 1].start) * 1000);
  return (performance.now() - t0) / 1000;
};
</script><div class="flash" id="flash"></div>
<div id="sync" style="position:fixed;right:0;bottom:0;width:10px;height:10px;background:#f0f;z-index:99"></div></body></html>"""


def family_alert():
    # the alert exactly as the pipeline builds it for this call (verdict and verified tactics only)
    from kavach import family_alert as F
    r = json.loads((RUN / "result.json").read_text(encoding="utf-8"))
    return F.build(r["verdict"], r["tactics"], r.get("evidence", []), "te", (r.get("seal") or {}).get("index"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    scenes, total = timeline()
    print(f"{len(scenes)} scenes, {total} s:", ", ".join(f"{s['id']} {s['dur']}" for s in scenes))
    if total > 60:
        sys.exit("over 60 s: shorten a scene")
    audio = build_audio(scenes, total)
    small = OUT / "walk_1600.mp4"          # the window is 1600x900, so decode no more than that
    if not small.exists() or small.stat().st_mtime < WALK.stat().st_mtime:
        subprocess.run([str(FFMPEG), "-y", "-v", "error", "-i", str(WALK), "-vf", "scale=1600:900", "-c:v", "libx264", "-crf", "18",
                        "-preset", "fast", "-an", str(small)], check=True)
    walk = small.as_uri()
    html = PAGE
    for sid, (kicker, head, focus) in LIVE.items():
        html = html.replace(f"LIVE_{sid}", f'<div class="scene" id="{sid}"><div class="win cam" style="--fo:{focus}"><video id="v_{sid}" '
                            f'src="{walk}" muted playsinline preload="auto"></video></div><div class="label"><small>{kicker}</small>{head}</div></div>')
    cards = "".join(f'<div class="pc {cls}"><em>{i + 1}</em><b>{name}</b><span>{by}</span><p>{what}</p></div>'
                    for i, (name, by, what, cls) in enumerate(AGENTS))
    bars = "".join(f'<b style="--b:{(i * 0.137) % 0.42:.2f}s"></b>' for i in range(28))
    wavebars = "".join(f'<b style="--h:{8 + (i * 37) % 26}px;--b:{(i * 0.11) % 0.35:.2f}s"></b>' for i in range(34))
    alert = family_alert()
    call_text = "ఇప్పుడు మీ phone కి ఒక OTP వస్తుంది, అది నాకు చెప్పండి"
    html = (html.replace("TIMELINE", json.dumps(scenes)).replace("TOTAL", str(total)).replace("CARDS", cards).replace("BARS", bars)
            .replace("TELTEXT", json.dumps(call_text, ensure_ascii=False)).replace("ANSWER", str(ANSWER))
            .replace("FAMTEXT", alert["text"]).replace("FAMENGLISH", alert["english"]).replace("WAVE", wavebars).replace("LOSS", LOSS.replace(",", "")).replace("WALK", walk))
    page_file = OUT / "stage.html"
    page_file.write_text(html, encoding="utf-8")
    rec = OUT / "rec"
    shutil.rmtree(rec, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(rec), record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        page.goto(page_file.as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.evaluate("prep()")
        took = page.evaluate("run()")
        ctx.close(); browser.close()
    video = next(rec.glob("*.webm"))
    print(f"stage ran {took:.1f} s")
    out = OUT / "kavach_trailer.mp4"
    cmd = [str(FFMPEG), "-y", "-i", str(video), "-i", str(audio), "-filter_complex", retime(video, scenes, total), "-map", "[v]", "-map", "1:a",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",   # social-media loudness
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    print("wrote", out)


if __name__ == "__main__":
    main()
