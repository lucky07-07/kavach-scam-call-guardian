# The live-call pipeline: agents 1-7 in a fixed order.
#   1 Listener (Prisma)  ->  punctuation restored by Evon, checked by code
#   2 Prosecutor + 3 Defender (Evon, in parallel)
#   4 Judge (kavach.rules): only claims whose quote is the caller's own words, with a cue and not negated; red lines in
#     code; the verdict is a fixed rule over verified evidence and is never Evon's
#   explainer (Evon): one sentence for the family
#   5 Guardian (Evon text, checked; else approved Telugu warning; Timbre voice)
#   6 Reporter (Evon): complaint draft, SCAM only
#   7 Notary: flagged calls are sealed (hash chain + OpenTimestamps)
import time
from concurrent.futures import ThreadPoolExecutor

from kavach import evon as E, guardian as G, listener as L, notary as N, transcript as T
from kavach.rules import TACTICS, decide, in_caller_lines, red_lines, verify


def judge(call, prosecution):
    # -> verified evidence (Evon's and the red lines', kept apart), every claim with the reason it was kept or rejected
    claimed = [{"tactic": k, "quote": v.get("quote", "")} for k, v in (prosecution or {}).items()
               if k in TACTICS and isinstance(v, dict) and v.get("present")]
    checks = [dict(c, check=verify(c["tactic"], c["quote"], call)) for c in claimed]
    evidence = [{"tactic": c["tactic"], "quote": c["quote"], "source": "evon"} for c in checks if c["check"] == "ok"]
    evidence += red_lines(call)
    return evidence, checks


def analyse(transcript, evon, tts=None, ledger=None, speak=True, seal=True, models=None, warn_lang="te"):
    # warn_lang: the listener's language for the spoken warning, "te" (default) or "hi"
    timings, t0 = {}, time.time()
    t = E.punctuate(transcript, evon)
    timings["punctuate_s"] = round(time.time() - t0, 1)
    call = T.rules_text(t)

    t1 = time.time()
    with ThreadPoolExecutor(2) as ex:   # two llama-server slots
        pro = ex.submit(evon.json, E.prosecutor(call), E.PRO_SCHEMA)
        dfn = ex.submit(evon.json, E.defender(call), E.DEF_SCHEMA)
        prosecution, defence = pro.result(), dfn.result() or {"benign_signals": []}
    evidence, claims = judge(call, prosecution)
    benign = [b for b in defence.get("benign_signals", []) if in_caller_lines(b.get("quote", ""), call)]
    verdict, tactics = decide(evidence)
    verdict_without_red_lines = decide([e for e in evidence if e["source"] == "evon"])[0]
    timings["verdict_s"] = round(time.time() - t0, 1)

    reason = (evon.json(E.explainer(call, verdict, evidence, benign), E.REASON_SCHEMA, max_tokens=150) or {}).get("reason", "")
    warning = G.choose(verdict, tactics, evidence, call,
                       evon.chat(G.evon_prompt(verdict, tactics, evidence, warn_lang), max_tokens=120)["content"] if verdict != "SAFE" else None,
                       warn_lang)
    audio = G.speak(warning["text"], tts, warn_lang) if speak and warning["text"] else None
    timings["warning_s"] = round(time.time() - t0, 1)
    report = E.complaint_text(evon.json(E.reporter(call, verdict, tactics, evidence), E.REPORT_SCHEMA, max_tokens=600)) \
        if verdict == "SCAM" else ""

    result = {"call_id": t["call_id"], "verdict": verdict, "tactics": tactics, "reason": reason, "evidence": evidence,
              "claims": claims, "benign": benign, "verdict_without_red_lines": verdict_without_red_lines,
              "warning": warning, "report": report, "transcript": t, "timings": timings, "seal": None}
    if seal and verdict != "SAFE":
        packet = N.make_packet(t, verdict, tactics, evidence, warning, benign, models)
        packet["reason"], packet["report"] = reason, report
        result["seal"] = (ledger or N.Ledger()).seal(packet)
    timings["total_s"] = round(time.time() - t0, 1)
    return result, audio


def analyse_audio(path, evon, language="en-IN", stereo=False, **kw):
    t0 = time.time()
    t = L.listen(path, language, stereo=stereo)
    listen_s = round(time.time() - t0, 1)
    result, audio = analyse(t, evon, models={"stt": t["prisma"]["model"], "evon": "gnani-evon-v3.3 Q4_K_M",
                                             "tts": f"{G.MODEL}/{G.VOICE}"}, **kw)
    result["timings"]["listen_s"] = listen_s
    return result, audio
