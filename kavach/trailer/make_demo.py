# The full demo video (2-3 min, the submission's "video demo"). Each moment once: the trailer's opening (the scam call,
# cut on the OTP, what it costs) -> Kavach and its eight agents -> one real run of the app, recorded by record_demo:
# the scam call analysed while it plays, Prosecute / Defend / Judge, the Telugu warning, the family alert, the 1930
# complaint, the seal and an edited copy, a genuine call left alone, the family asking in Telugu -> Evon's answer (from
# the earlier recording, made while Evon was online) -> many languages -> 100% Gnani. Narrated by Timbre.
#   data/demo/kavach_demo_full.mp4
# Needs: record_demo.py run first, the screen recording data/demo/kavach_demo.mp4 (for the answer).
# Usage: .venv\Scripts\python -m kavach.trailer.make_demo
import json, subprocess, sys
from pathlib import Path

from kavach.trailer import make_trailer as T, narration as N

FULL = T.OUT / "full"
WALK = T.DEMO / "demo_walk.mp4"
GENUINE = T.ROOT / "data" / "test_audio" / "te_fraud_alert_mono.wav"
G_FROM = 12.16                       # the genuine caller's last turn: "...we will never ask you for an OTP or PIN"
OLD = T.DEMO / "kavach_demo.mp4"     # the earlier screen recording, with Evon online: the family's question and its answer
OLD_ASK = 86.8                       # there, the question is posted at 87.3 s and Evon's answer shows at 91.7 s
LINES = {k: N.LINES[k] for k in ("stakes", "reveal", "agents", "sovereign", "end")} | {
    "run":     "Here is one real run, start to finish. A scam call, in Telugu.",
    "why":     "Evon argues both sides. But the Judge is code: it keeps only what the caller's own words prove.",
    "warn":    "Kavach warns her.",
    "family":  "And alerts her family.",
    "report":  "It drafts the complaint for the 1930 cybercrime helpline.",
    "seal":    "The evidence is sealed on Bitcoin. Change one byte, and the check fails.",
    "genuine": "Now, a genuine bank call.",
    "safe":    "No scam, so no warning and no alert. Kavach stays silent.",
    "ask":     "After the call, the family sees the alert, and asks Kavach, in Telugu.",
    "answer":  "Evon answers from the sealed evidence, through the Kavach MCP server.",
    "langs":   "Telugu, Hindi, English, or code-mixed. One Kavach.",
}
LIVE = {  # scene -> (kicker, headline, camera focus[, video])
    "run": ("1 · Listen · Gnani Prisma · a saved call, replayed", "A scam call: who said what, as it is spoken", "40% 35%"),
    "why": ("2-4 · Prosecute · Defend · Judge", "Evon argues both sides; the Judge is code", "50% 20%"),
    "dwarn": ("5 · Guardian · Gnani Timbre", '<span class="red">Scam</span>: the warning to Amma, in Telugu', "70% 40%"),
    "dfamily": ("5 · Guardian · the family alert", "Her family is alerted, with a voice note", "70% 55%"),
    "report": ("6 · Reporter · Evon", "The 1930 complaint, drafted", "60% 60%"),
    "dseal": ("7 · Notary · SHA-256 hash chain on Bitcoin", 'Original <span class="green">✓</span> · one byte edited <span class="red">✗</span>', "55% 70%"),
    "dgenuine": ("A genuine HDFC fraud-alert call", "Same pipeline, a different call", "40% 35%"),
    "safe": ("Verdict · decided by code", '<span class="green">Safe</span>: no warning, no alert', "60% 30%"),
    "dask": ("8 · Family assistant · after the call", "The alert waits. The family asks, in Telugu", "50% 25%"),
    "answer": ("8 · Evon over the Kavach MCP server · recorded with Evon online", "The answer, from the sealed evidence", "50% 25%"),
}


def answer_clip():
    # the question and answer from the earlier recording, cropped to the conversation and sized like the window
    out = T.OUT / "answer_1600.mp4"
    if not out.exists():
        subprocess.run([str(T.FFMPEG), "-y", "-v", "error", "-ss", str(OLD_ASK), "-t", "12", "-i", str(OLD),
                        "-vf", "crop=1040:585:280:0,scale=1600:900", "-c:v", "libx264", "-crf", "18", "-an", str(out)], check=True)
    return out.as_uri()


def timeline():
    vo = json.loads((FULL / "narration.json").read_text(encoding="utf-8"))
    m = json.loads((T.DEMO / "demo_walk.json").read_text(encoding="utf-8"))
    after = lambda key: 0.25 + vo[key] + 0.3                       # just after a narration line
    te_end, fam_end = T.pause_before(T.TE_WARN, 6.2), T.pause_before(T.FAMILY, 6.6)
    hi_end = T.pause_before(T.HI_WARN, 3.2)
    g_take = m["genuine_go"] + G_FROM - 2.4
    opening, timing = T.hook(vo)
    scenes = opening + [
        ("pipeline", 5.4, "agents", [], False, m["take_run"]),
        ("run", m["verdict"] - m["take_run"] + 1.5, "run", [(T.CALL, m["call_go"] - m["take_run"], 0, 19.94)], False, m["take_run"]),
        ("why", m["why_end"] - m["take_why"], "why", [], False, m["take_why"]),
        ("dwarn", 0, "warn", [(T.TE_WARN, m["warn_click"] - m["take_warn"] + 0.1, 0, te_end)], True, m["take_warn"]),
        ("dfamily", 0, "family", [(T.FAMILY, m["family_click"] - m["take_family"] + 0.1, 0, fam_end)], False, m["take_family"]),
        ("report", 4.8, "report", [], False, m["take_report"]),
        ("dseal", m["seal_bad"] - m["take_seal"] + 1.6, "seal", [], False, m["take_seal"]),
        ("dgenuine", m["genuine_safe"] - g_take, "genuine", [(GENUINE, 2.4, G_FROM, 24.4)], False, g_take),
        ("safe", 3.6, "safe", [], False, m["genuine_safe"] - 0.2),
        ("dask", m["ask_end"] - m["take_ask"] + 0.4, "ask", [], False, m["take_ask"]),
        ("answer", 8.4, "answer", [], False, 0.0),
        ("langs", 0, "langs", [(T.HI_WARN, after("langs"), 0, hi_end)], False, None),
        ("sovereign", 4.2, "sovereign", [], True, None),
        ("end", 0, "end", [], True, None)]
    out, total = T.lay_out(scenes, vo)
    out[0].update(timing)
    at = {s["id"]: s["start"] for s in out}
    clicks = [at["dseal"] + m[k] - m["take_seal"] for k in ("seal_ok", "seal_bad")]
    return out, total, clicks


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--narrate" in sys.argv or not (FULL / "narration.json").exists():
        N.main(LINES, FULL)
    scenes, total, clicks = timeline()
    print(f"{len(scenes)} scenes, {total} s:", ", ".join(f"{s['id']} {s['dur']}" for s in scenes))
    if not 120 <= total <= 180:
        sys.exit("the demo must run 2-3 minutes")
    audio = T.build_audio(scenes, total, clicks, vo_dir=FULL, out=FULL / "demo_audio.wav", bed_after=("run", 0.4))
    live = {k: v + ((answer_clip(),) if k == "answer" else ()) for k, v in LIVE.items()}
    html = T.build_page(scenes, total, live, T.small(WALK, "demo_walk_1600.mp4"))
    T.render(html, scenes, total, audio, T.DEMO / "kavach_demo_full.mp4", name="demo_stage")


if __name__ == "__main__":
    main()
