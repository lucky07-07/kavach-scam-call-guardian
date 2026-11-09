# Launch-style trailer for Kavach (60 s): kinetic typography, real screen footage cropped into a window, an animated pipeline,
# Timbre narration, the real Telugu and Hindi warnings, a recap montage, synthesised SFX and a 100 BPM bed; every cut
# lands on the beat, with a silence-then-drop at the reveal and a flash + hit on the big moments.
#   data/demo/trailer/kavach_trailer.mp4  (1920x1080)
# Needs: narration.py run first; data/demo/kavach_demo.mp4 (the screen recording) for footage.
# Usage: .venv\Scripts\python -m kavach.trailer.make_trailer
import json, shutil, subprocess, sys, time, wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent.parent
DEMO = ROOT / "data" / "demo"
OUT = DEMO / "trailer"
SR = 48000
W, H = 1920, 1080
FFMPEG = shutil.which("ffmpeg") or next(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"), None)
TE_WARN, HI_WARN = ROOT / "data" / "runs" / "te_kyc_otp" / "warning.wav", DEMO / "warning_hi_template.wav"
SEAL_HASH = json.loads((ROOT / "data" / "ledger" / "records" / "00000.json").read_bytes())["packet_sha256"]


# ---------------------------------------------------------------- timeline: narration-led, every cut snapped to the beat
BPM = 100
BEAT = 60 / BPM
MONTAGE = [  # rapid recap shots: (word, demo time, crop x, y, w, h in source pixels, scale)
    ("Hears.", 18.0, 220, 220, 660, 220, 1.9), ("Judges.", 34.0, 890, 215, 490, 350, 1.8),
    ("Warns.", 34.0, 890, 580, 490, 170, 2.0), ("Seals.", 40.0, 890, 745, 490, 128, 2.0)]


def timeline():
    vo = json.loads((OUT / "narration.json").read_text(encoding="utf-8"))
    scenes = [  # (id, extra seconds after the narration, narration key, extra audio (file, offset, seconds), flash on the cut)
        # sized to land just under 60 s, the length of the "Demo Day Drop" award
        ("hook", 0.4, "hook", None, False), ("reveal", 0.5, "reveal", None, True), ("listen", 1.2, "listen", None, False),
        ("agents", 0.8, "agents", None, False), ("warn", 4.4, "warn", (TE_WARN, 0.2, 4.1), True),
        ("hindi", 3.4, "hindi", (HI_WARN, 0.2, 3.2), False), ("genuine", 1.4, "genuine", None, False),
        ("seal", 1.2, "seal", None, False), ("ask", 1.4, "ask", None, False),
        ("montage", BEAT * len(MONTAGE), None, None, True), ("sovereign", 0.8, "sovereign", None, True),
        ("end", 0.4, "end", None, True)]
    t, out = BEAT, []
    for sid, extra, key, extra_audio, flash in scenes:
        lead = 0.35 if key else 0.0
        speech = vo[key] if key else 0.0
        out.append({"id": sid, "start": round(t, 3), "vo": key, "vo_at": round(t + lead, 3), "flash": flash,
                    "extra": None if not extra_audio else {"file": str(extra_audio[0]), "at": round(t + lead + speech + extra_audio[1], 3),
                                                           "len": extra_audio[2]}})
        spoken_end = t + lead + speech + (extra_audio[1] + extra_audio[2] if extra_audio else 0)
        nxt = round((t + lead + speech + extra) / BEAT) * BEAT          # cut on the nearest beat ...
        while nxt < spoken_end + 0.2:                                    # ... but never over speech
            nxt += BEAT
        out[-1]["dur"] = round(nxt - t, 3)
        t = nxt
    return out, round(t + 0.8, 2)


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


def build_audio(scenes, total):
    at = {s["id"]: s["start"] for s in scenes}
    bed = music(total, at["reveal"], at["reveal"] - 0.45, at["end"])
    voice, fx = np.zeros_like(bed), np.zeros_like(bed)
    for s in scenes:
        if s["vo"]:
            place(voice, read_wav(OUT / f"vo_{s['vo']}.wav"), s["vo_at"], 1.0)
        if s["extra"]:
            clip = read_wav(Path(s["extra"]["file"]))[: int(s["extra"]["len"] * SR)]
            clip *= np.minimum(1, (s["extra"]["len"] - np.arange(len(clip)) / SR) / 0.4).clip(0, 1)
            place(voice, clip, s["extra"]["at"], 0.95)
        if s["flash"]:
            place(fx, impact(1.2), s["start"], 0.75)
        elif s["id"] != "hook":
            place(fx, whoosh(0.4), max(0, s["start"] - 0.2), 0.45)
    place(fx, riser(2.0), at["reveal"] - 2.45, 0.6)                    # riser, then silence, then the drop
    place(fx, impact(), at["reveal"], 0.6)
    place(fx, riser(1.4), at["sovereign"] - 1.4, 0.5)
    for i in range(1, len(MONTAGE)):
        place(fx, impact(0.6), at["montage"] + i * BEAT, 0.55)
    place(fx, tick(), at["seal"] + 1.7, 1.0)
    place(fx, tick(f=900), at["seal"] + 2.5, 1.0)
    for i in range(3):
        place(fx, tick(0.06, 1600), at["sovereign"] + 1.4 + i * BEAT, 0.7)
    # duck the music under speech
    speech = np.abs(voice) > 0.01
    duck = 1 - 0.6 * lowpass(speech.astype(np.float32), int(0.3 * SR))
    mix = bed * duck * 0.9 + voice * 1.0 + fx * 0.8
    mix = np.tanh(mix * 1.1) * 0.92
    out = OUT / "trailer_audio.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return out


# ---------------------------------------------------------------- the stage
PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Telugu:wght@500;700&family=Noto+Sans+Devanagari:wght@500;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#07080b;color:#f2f3f6;font-family:Inter,sans-serif}
.scene{position:absolute;inset:0;display:grid;place-items:center;opacity:0;visibility:hidden}
.scene.on{visibility:visible;animation:fadein .3s ease forwards}
@keyframes fadein{to{opacity:1}}
.big{font-size:96px;font-weight:800;letter-spacing:-3px;line-height:1.05;text-align:center;max-width:1500px}
.dim{color:#7d8492}.red{color:#ff5a4e}.green{color:#4fd08f}.amber{color:#f3b13f}
.word{display:inline-block;opacity:0;transform:translateY(40px) scale(.96);filter:blur(10px)}
.on .word{animation:wordin .55s cubic-bezier(.2,.8,.2,1) forwards}
@keyframes wordin{to{opacity:1;transform:none;filter:none}}
.quote{font-size:64px;font-weight:700;margin:14px 0;opacity:0;transform:translateX(-60px)}
.on .quote{animation:slide .5s cubic-bezier(.2,.8,.2,1) forwards}
@keyframes slide{to{opacity:1;transform:none}}
.te{font-family:"Noto Sans Telugu",Inter,sans-serif}.hi{font-family:"Noto Sans Devanagari",Inter,sans-serif}
.tag{font-size:34px;color:#8a909c;margin-top:8px;letter-spacing:.5px}
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
/* real screen footage, cropped to the part of the app that matters (--x --y --w --h in source pixels, --s scale) */
.frame{position:absolute;left:50%;top:calc(150px + (900px - var(--h) * var(--s) * 1px) / 2);width:calc(var(--w) * var(--s) * 1px);
  height:calc(var(--h) * var(--s) * 1px);border-radius:20px;overflow:hidden;background:#f4f5f7;border:1px solid #2a2f3a;
  box-shadow:0 30px 120px rgba(0,0,0,.6);transform:translateX(-50%) scale(.985)}
.on .frame{animation:settle 7s ease-out forwards}
@keyframes settle{to{transform:translateX(-50%) scale(1.01)}}
.frame video{position:absolute;width:calc(1600px * var(--s));height:calc(1000px * var(--s));
  left:calc(var(--x) * var(--s) * -1px);top:calc(var(--y) * var(--s) * -1px)}
.gn{display:flex;gap:36px;justify-content:center;margin-top:56px}
.gm{width:400px;padding:36px 32px;border-radius:28px;background:#11141a;border:1px solid #262b36;text-align:left;opacity:0;transform:translateY(30px)}
.on .gm{animation:wordin .55s forwards}
.gm b{display:block;font-size:56px;font-weight:800;letter-spacing:-1.5px}
.gm i{display:block;font-style:normal;font-size:26px;color:#f3b13f;font-weight:700;margin:4px 0 14px}
.gm span{font-size:24px;color:#9aa1ad;line-height:1.4}
.kick{font-size:26px;letter-spacing:4px;text-transform:uppercase;color:#f3b13f;font-weight:700;text-align:center}
.zero{font-size:30px;color:#c6cbd4;text-align:center;margin-top:46px;opacity:0}
.on .zero{animation:wordin .6s 4.2s forwards}
.label{position:absolute;left:0;right:0;top:34px;text-align:center;font-size:44px;font-weight:700;opacity:0;transform:translateY(-14px)}
.on .label{animation:wordin .5s .15s forwards}
.label small{display:block;font-size:22px;font-weight:600;color:#8a909c;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.pipe{display:flex;gap:22px;align-items:center}
.node{width:190px;height:190px;border-radius:30px;background:#13161c;border:2px solid #232833;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:10px;opacity:.25;transform:scale(.9);transition:all .35s ease}
.node b{font-size:30px}.node span{font-size:21px;color:#8a909c}
.node.lit{opacity:1;transform:none;border-color:#4b5263}.node.judge.lit{border-color:#ff5a4e;box-shadow:0 0 60px rgba(255,90,78,.35)}
.node.voice.lit{border-color:#8b85ff}.node.chain.lit{border-color:#4fd08f}
.cap{font-size:44px;color:#c6cbd4;margin-top:60px;text-align:center;opacity:0}
.on .cap{animation:wordin .6s 2.8s forwards}
.warncard{max-width:1500px;text-align:center}
.say{font-size:58px;font-weight:700;line-height:1.5;opacity:0}
.on .say{animation:wordin .7s var(--d,4.4s) forwards}
.gloss{font-size:32px;color:#9aa1ad;margin-top:28px;opacity:0}
.on .gloss{animation:wordin .7s var(--g,5s) forwards}
.verdict{font-size:150px;font-weight:800;letter-spacing:-5px;color:#ff5a4e;opacity:0;transform:scale(1.4)}
.on .verdict{animation:logo .6s .15s cubic-bezier(.16,.9,.2,1) forwards, fadeout .4s 3.9s forwards}
@keyframes fadeout{to{opacity:0;transform:scale(.95)}}
.layer{position:absolute;inset:0;display:grid;place-items:center}
.hash{font-family:"JetBrains Mono",monospace;font-size:44px;letter-spacing:2px;color:#4fd08f;max-width:1500px;word-break:break-all;text-align:center}
.chips{display:flex;gap:24px;margin-top:50px;justify-content:center}
.chip{font-size:34px;font-weight:700;padding:18px 30px;border-radius:999px;opacity:0;transform:translateY(20px)}
.chip.ok{background:#12291d;color:#4fd08f}.chip.no{background:#34191a;color:#ff7a6e}.chip.btc{background:#1c2028;color:#f3b13f}
.on .chip.btc{animation:wordin .5s .9s forwards}.on .chip.ok{animation:wordin .5s 1.6s forwards}.on .chip.no{animation:wordin .5s 2.4s forwards}
.stat{position:absolute;inset:0;display:grid;place-items:center;opacity:0}
.stat .n{font-size:220px;font-weight:800;letter-spacing:-8px;line-height:1}
.stat .t{font-size:44px;color:#9aa1ad;margin-top:10px;text-align:center}
.end .name{font-size:150px}
.flash{position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none;z-index:9}
.flash.go{animation:flash .32s ease-out}
@keyframes flash{from{opacity:.85}to{opacity:0}}
.mshot{position:absolute;inset:0;visibility:hidden}.mshot.on{visibility:visible}
.mshot .label{font-size:84px;letter-spacing:-2px;top:40px}
.hash-tags{font-size:28px;color:#6f7684;margin-top:40px;text-align:center;opacity:0}
.on .flash{position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none;z-index:9}
.flash.go{animation:flash .32s ease-out}
@keyframes flash{from{opacity:.85}to{opacity:0}}
.mshot{position:absolute;inset:0;visibility:hidden}.mshot.on{visibility:visible}
.mshot .label{font-size:84px;letter-spacing:-2px;top:40px}
.hash-tags{animation:wordin .7s 1.4s forwards}
</style></head><body>
<div class="scene" id="hook"><div><div class="big"><span class="word">Every</span> <span class="word" style="animation-delay:.12s">day,</span>
 <span class="word" style="animation-delay:.24s">scammers</span> <span class="word" style="animation-delay:.36s">call</span><br>
 <span class="word red" style="animation-delay:.6s">India's</span> <span class="word red" style="animation-delay:.72s">elderly.</span></div>
 <div style="margin-top:56px;text-align:center"><div class="quote te" style="font-size:48px;animation-delay:2.3s;color:#c6cbd4">“మీ KYC expire అయింది. OTP చెప్పండి.”</div>
 <div class="quote hi" style="font-size:48px;animation-delay:2.9s;color:#c6cbd4">“आपका KYC expire हो गया है। OTP बताइए।”</div></div></div></div>
<div class="scene" id="reveal"><div class="glow"></div><div><div class="logo"><div class="mark">K</div><div class="name">Kavach</div></div>
 <div class="sub">A second listener on the call · built on Gnani AI</div></div></div>
<div class="scene" id="listen"><div class="frame" style="--x:200;--y:200;--w:1200;--h:400;--s:1.4"><video id="v_listen" src="FOOTAGE" muted playsinline preload="auto"></video></div>
 <div class="label"><small>1 · Listener · Gnani Prisma</small>Caller and listener, separated: Telugu · Hindi · English</div></div>
<div class="scene" id="agents"><div><div class="pipe" id="pipe">
 <div class="node voice"><b>Listen</b><span>Prisma</span></div><div class="node"><b>Prosecute</b><span>Evon</span></div>
 <div class="node"><b>Defend</b><span>Evon</span></div><div class="node judge"><b>Judge</b><span>code</span></div>
 <div class="node voice"><b>Warn</b><span>Timbre</span></div><div class="node"><b>Report</b><span>Evon</span></div>
 <div class="node chain"><b>Seal</b><span>Bitcoin</span></div><div class="node"><b>Ask</b><span>MCP</span></div></div>
 <div class="cap">The verdict is <span class="red">code</span>, not an LLM: only the caller's own words count as proof.</div></div></div>
<div class="scene" id="warn"><div class="frame" style="--x:200;--y:210;--w:1200;--h:790;--s:1.06"><video id="v_warn" src="FOOTAGE" muted playsinline preload="auto"></video></div>
 <div class="label"><small>Judge · Guardian · Notary</small><span class="red">Scam</span> → warning spoken in Telugu → evidence sealed</div></div>
<div class="scene" id="hindi"><div class="warncard">
 <div class="tag">Hindi · Timbre</div>
 <div class="say hi" style="--d:.9s">सावधान! यह धोखाधड़ी वाली कॉल है।<br>OTP, PIN किसी को मत बताइए।<br>अभी फ़ोन काट दीजिए।</div>
 <div class="gloss" style="--g:1.6s">“Careful, this is a fraud call. Don't tell anyone your OTP or PIN. Hang up now.”</div></div></div>
<div class="scene" id="genuine"><div class="frame" style="--x:200;--y:210;--w:1200;--h:610;--s:1.38"><video id="v_genuine" src="FOOTAGE" muted playsinline preload="auto"></video></div>
 <div class="label"><small>A genuine HDFC fraud-alert call</small><span class="green">Safe</span> → no warning</div></div>
<div class="scene" id="seal"><div style="text-align:center">
 <div class="tag" style="margin-bottom:24px">Evidence fingerprint · SHA-256</div>
 <div class="hash" id="hash"></div>
 <div class="chips"><div class="chip btc">Confirmed on Bitcoin · block 974,389</div></div>
 <div class="chips"><div class="chip ok">✓ Original matches</div><div class="chip no">✗ 1 byte changed — fails</div></div></div></div>
<div class="scene" id="ask"><div class="frame" style="--x:300;--y:85;--w:1000;--h:380;--s:1.6"><video id="v_ask" src="FOOTAGE" muted playsinline preload="auto"></video></div>
 <div class="label"><small>8 · Family assistant · Evon over the Kavach MCP server</small><span class="te">“అమ్మకి వచ్చిన చివరి call ఏంటి?”</span></div></div>
<div class="scene" id="montage">MONTAGE</div>
<div class="scene" id="sovereign"><div>
 <div class="kick">Sovereign AI for India</div>
 <div class="big" style="margin-top:18px">100% Gnani. <span class="amber">Trained in India.</span></div>
 <div class="gn">
  <div class="gm" style="animation-delay:1.4s"><b>Prisma</b><i>hears</i><span>Speech to text: Telugu, Hindi, English, code-mixed. Separates caller from listener.</span></div>
  <div class="gm" style="animation-delay:2.15s"><b>Evon</b><i>reasons</i><span>Open-weight 30B LLM, self-hosted by us. Prosecutor, defender, report, family assistant.</span></div>
  <div class="gm" style="animation-delay:2.9s"><b>Timbre</b><i>speaks</i><span>Text to speech: the warning, in Telugu and Hindi.</span></div></div>
 <div class="zero">No model from outside Gnani anywhere in the call path.</div></div></div>
<div class="scene end" id="end"><div style="text-align:center"><div class="logo" style="justify-content:center"><div class="mark">K</div><div class="name">Kavach</div></div>
 <div class="sub" style="font-size:52px;color:#f2f3f6">Keep the listener safe.</div>
 <div class="hash-tags">#GnaniAI · #GreatIndianAIInternshipChallenge</div></div></div>
<script>
const TL = TIMELINE, BEAT_MS = BEATMS, FOOT = Object.assign({listen: 13.6, warn: 31.0, genuine: 79.0, ask: 90.5}, MFOOT);
const sleep = ms => new Promise(r => setTimeout(r, ms));
function scramble(el, target, ms) {
  const hex = "0123456789abcdef", t0 = performance.now();
  (function f() {
    const p = Math.min(1, (performance.now() - t0) / ms), k = Math.floor(p * target.length);
    el.textContent = target.slice(0, k) + Array.from({length: target.length - k}, () => hex[Math.random() * 16 | 0]).join("");
    if (p < 1) requestAnimationFrame(f);
  })();
}
window.prep = async () => {
  // seek every clip before the clock starts, so a cut never shows a stale or loading frame
  await Promise.all(Object.entries(FOOT).map(([id, t]) => new Promise(ok => {
    const v = document.getElementById("v_" + id);
    const go = () => { v.addEventListener("seeked", ok, {once: true}); v.currentTime = t; };
    v.readyState >= 1 ? go() : v.addEventListener("loadedmetadata", go, {once: true});
  })));
};
window.run = async () => {
  const t0 = performance.now();
  for (const s of TL) {
    const due = t0 + s.start * 1000 - performance.now();
    if (due > 0) await sleep(due);
    document.querySelectorAll(".scene.on").forEach(e => e.classList.remove("on"));
    const el = document.getElementById(s.id); el.classList.add("on");
    const v = document.getElementById("v_" + s.id);
    if (v) v.play();
    if (s.flash) { const f = document.getElementById("flash"); f.classList.remove("go"); void f.offsetWidth; f.classList.add("go"); }
    if (s.id === "montage") document.querySelectorAll(".mshot").forEach((m, i) => setTimeout(() => {
      document.querySelectorAll(".mshot").forEach(x => x.classList.remove("on")); m.classList.add("on"); }, i * BEAT_MS));
    if (s.id === "agents") document.querySelectorAll("#pipe .node").forEach((n, i) => setTimeout(() => n.classList.add("lit"), 250 + i * 300));
    if (s.id === "seal") scramble(document.getElementById("hash"), "HASH", 800);
  }
  await sleep((TOTAL - TL[TL.length - 1].start) * 1000);
  return (performance.now() - t0) / 1000;
};
</script><div class="flash" id="flash"></div></body></html>"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    scenes, total = timeline()
    print(f"{len(scenes)} scenes, {total} s")
    audio = build_audio(scenes, total)
    footage = (DEMO / "kavach_demo.mp4").as_uri()
    montage = "".join(
        f'<div class="mshot"><div class="frame" style="--x:{x};--y:{y};--w:{w};--h:{h};--s:{sc}">'
        f'<video id="v_m{i}" src="FOOTAGE" muted playsinline preload="auto"></video></div><div class="label">{word}</div></div>'
        for i, (word, _, x, y, w, h, sc) in enumerate(MONTAGE))
    html = (PAGE.replace("TIMELINE", json.dumps(scenes)).replace("TOTAL", str(total))
            .replace("MONTAGE", montage).replace("BEATMS", str(round(BEAT * 1000)))
            .replace("MFOOT", json.dumps({f"m{i}": m[1] for i, m in enumerate(MONTAGE)}))
            .replace("FOOTAGE", footage).replace('"HASH"', json.dumps(SEAL_HASH)))
    page_file = OUT / "stage.html"
    page_file.write_text(html, encoding="utf-8")
    rec = OUT / "rec"
    shutil.rmtree(rec, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(rec), record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        t_open = time.monotonic()
        page.goto(page_file.as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.evaluate("prep()")
        lead = time.monotonic() - t_open          # blank/loading time at the head of the recording
        took = page.evaluate("run()")
        ctx.close(); browser.close()
    video = next(rec.glob("*.webm"))
    print(f"stage ran {took:.1f} s after {lead:.1f} s of loading")
    out = OUT / "kavach_trailer.mp4"
    cmd = [str(FFMPEG), "-y", "-ss", f"{lead:.2f}", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",   # social-media loudness
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    print("wrote", out)


if __name__ == "__main__":
    main()
