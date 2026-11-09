# Kavach demo screen: a small JSON API over the pipeline plus one static page (kavach/web/index.html) in the design of
# ui-mockups/panel_mockups.html. Live mode runs Prisma (or reuses a saved Prisma transcript) and Evon; Replay shows a
# saved run from data/runs, so the demo never depends on a live Kaggle session.
# Run from the Project folder: .venv\Scripts\python -m kavach.web   -> http://127.0.0.1:7861
import json, re, time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from kavach import evon as E, family_alert as F, guardian as G, listener as L, notary as N, pipeline as P, transcript as T
from kavach.rules import CUES, in_caller_lines
from kavach.run_call import RUNS, save

ROOT = Path(__file__).parent.parent
AUDIO = ROOT / "data" / "test_audio"
PAGE = Path(__file__).parent / "web" / "index.html"
LEDGER = N.Ledger()
app = FastAPI(title="Kavach")


def call_list():
    out = []
    for wav in sorted(AUDIO.glob("*_mono.wav")):
        cid = wav.stem[:-len("_mono")]
        truth = AUDIO / f"{cid}.truth.json"
        doc = json.loads(truth.read_text(encoding="utf-8")) if truth.exists() else {}
        meta = doc.get("prisma") or {}
        out.append({"id": cid, "kind": meta.get("kind"), "case": meta.get("case_type"), "language": doc.get("language", "en-IN"),
                    "saved": (RUNS / cid / "result.json").exists(),
                    "sealed": (LEDGER.root / "packets" / f"{cid}.json").exists()})
    return out


# inside a cue match, only these words are highlighted (a cue like "account ... block" can span half a sentence)
KEY = re.compile(r"\b(otp|pin|password|cvv|code|digit|kyc|account|card|details|ifsc|expir\w*|block\w*|cut|deactivat\w*|suspend\w*|cancel\w*|"
                 r"arrest|warrant|fir|police|jail|court|case|transfer|pay\w*|upi|google pay|phonepe|paytm|neft|fee|fine|deposit|"
                 r"processing|link|download|install|anydesk|teamviewer|apk|qr|scan|screen share|secret|rbi|cbi|customs|"
                 r"officer|inspector)\b|కట్ట\w*|పంపండి|పంపాలి|చెప్పకూడదు|ఎవరికీ చెప్ప\w*|అంకెల", re.I)


def marks(text, tactics):
    # character spans in a caller turn to highlight: the key words inside the cue of each verified tactic
    spans = []
    for t in tactics:
        for m in re.finditer(CUES[t], text, re.I):
            if m.end() <= m.start():
                continue
            keys = [k for k in KEY.finditer(text, m.start(), m.end())]
            for k in keys or [m]:
                spans.append({"start": k.start(), "end": k.end(), "tactic": t})
    spans.sort(key=lambda s: s["start"])
    merged = []
    for s in spans:
        if merged and s["start"] < merged[-1]["end"]:
            continue
        merged.append(s)
    return merged


def view(result, call_id):
    # the result as the page needs it: turns with the evidence they carry and the words to highlight
    call = T.rules_text(result["transcript"])
    turns = []
    for turn in result["transcript"]["turns"]:
        ev = [e for e in result["evidence"] if turn["speaker"] == "caller"
              and in_caller_lines(e["quote"], "Caller: " + turn["text"])]
        tactics = sorted({e["tactic"] for e in ev})
        turns.append(dict(turn, evidence=[{"tactic": e["tactic"], "source": e["source"]} for e in ev],
                          marks=marks(turn["text"], tactics) if tactics else []))
    # a safe call shows no seal, even if an earlier run of the same recording was sealed (seals are append-only)
    seal = seal_info(call_id) if result["verdict"] != "SAFE" else None
    # runs saved before the family alert existed get it rebuilt: it is code-only, from the same verdict and evidence
    alert = result.get("family_alert") or F.build(result["verdict"], result["tactics"], result["evidence"],
                                                  result["warning"].get("lang", "te"), (seal or {}).get("index"))
    return {"call_id": call_id, "verdict": result["verdict"], "tactics": result["tactics"], "reason": result.get("reason", ""),
            "turns": turns, "claims": result["claims"], "benign": result["benign"], "evidence": result["evidence"],
            "verdict_without_red_lines": result.get("verdict_without_red_lines"), "warning": result["warning"],
            "report": result.get("report", ""), "timings": result.get("timings", {}),
            "listener": {k: result["transcript"].get(k) for k in ("source", "language", "speaker_assignment", "duration_s", "warnings")}
                        | {"model": (result["transcript"].get("prisma") or {}).get("model")},
            "has_warning_audio": (RUNS / call_id / "warning.wav").exists(), "seal": seal, "family_alert": alert}


def seal_info(call_id, packet_bytes=None):
    try:
        v = LEDGER.verify(call_id, packet_bytes)
    except KeyError:
        return None
    rec = json.loads((LEDGER.root / "records" / f"{v['index']:05d}.json").read_bytes())
    return {"index": rec["index"], "packet_sha256": rec["packet_sha256"], "prev_record_sha256": rec["prev_record_sha256"],
            "sealed_at": rec["sealed_at"], "packet_matches_seal": v["packet_matches_seal"], "chain_intact": v["chain_intact"],
            "stamp": v["stamp"]}


@app.get("/", response_class=HTMLResponse)
def page():
    return PAGE.read_text(encoding="utf-8")


@app.get("/api/status")
def status():
    # llama-server answers /health with "busy" while both slots are generating; retry before calling Evon offline
    evon = E.Evon()
    up = evon.health() or (time.sleep(3) or evon.health())
    return {"evon": up, "calls": call_list(), "seals": len(LEDGER.records())}


@app.get("/api/audio/{call_id}")
def audio(call_id: str):
    f = AUDIO / f"{call_id}_mono.wav"
    if not f.exists():
        raise HTTPException(404, "no such call")
    return FileResponse(f, media_type="audio/wav")


@app.get("/api/warning/{call_id}")
def warning_audio(call_id: str):
    f = RUNS / call_id / "warning.wav"
    if not f.exists():
        raise HTTPException(404, "no warning audio")
    return FileResponse(f, media_type="audio/wav")


@app.get("/api/family_alert/{call_id}")
def family_alert_audio(call_id: str):
    # the alert as a voice note, made by Timbre on first request and kept with the run
    f = RUNS / call_id / "family_alert.wav"
    if not f.exists():
        r = RUNS / call_id / "result.json"
        if not r.exists():
            raise HTTPException(404, "no saved run")
        alert = view(json.loads(r.read_text(encoding="utf-8")), call_id)["family_alert"]
        if not alert.get("send"):
            raise HTTPException(404, "safe call: no family alert")
        f.write_bytes(F.voice(alert))
    return FileResponse(f, media_type="audio/wav")


class Analyse(BaseModel):
    call_id: str
    mode: str = "live"          # live | replay
    language: str = "en-IN"


@app.post("/api/analyse")
def analyse(req: Analyse):
    if req.mode == "replay":
        f = RUNS / req.call_id / "result.json"
        if not f.exists():
            raise HTTPException(404, f"no saved run for {req.call_id}: run it once live")
        return view(json.loads(f.read_text(encoding="utf-8")), req.call_id)
    evon = E.Evon()
    if not evon.health():
        raise HTTPException(503, "Evon is not answering: start the Kaggle notebook and update Project/evon.env, or use Replay")
    # the call's language: Hindi calls are transcribed with Prisma en-IN (Hinglish in Latin script, which the rules read)
    # and the listener is warned in Hindi; Telugu calls use te-IN and a Telugu warning
    truth = AUDIO / f"{req.call_id}.truth.json"
    language = json.loads(truth.read_text(encoding="utf-8")).get("language", req.language) if truth.exists() else req.language
    warn = G.lang_of(language)
    stt_lang = "en-IN" if language.startswith("hi") else language
    cached = AUDIO / f"{req.call_id}_mono.prisma.json"
    t = T.validate(json.loads(cached.read_text(encoding="utf-8"))) if cached.exists() else \
        L.listen(AUDIO / f"{req.call_id}_mono.wav", stt_lang, call_id=req.call_id)
    if not cached.exists():
        cached.write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
    t = dict(t, call_id=req.call_id)
    sealed = (LEDGER.root / "packets" / f"{req.call_id}.json").exists()
    result, wav = P.analyse(t, evon, ledger=LEDGER, seal=not sealed, warn_lang=warn,
                            models={"stt": (t.get("prisma") or {}).get("model"), "evon": "gnani-evon-v3.3 Q4_K_M",
                                    "tts": f"{G.LANGS[warn]['model']}/{G.LANGS[warn]['voice']}"})
    save(result, wav)
    F.queue(result["family_alert"], req.call_id)
    return view(result, req.call_id)


class Verify(BaseModel):
    call_id: str
    edited: bool = False


@app.post("/api/verify")
def verify(req: Verify):
    f = LEDGER.root / "packets" / f"{req.call_id}.json"
    if not f.exists():
        raise HTTPException(404, "this call has no seal")
    body = f.read_bytes()
    if req.edited:   # flip one bit in the first letter of the verdict
        i = body.find(b'"verdict":"') + 11
        body = body[:i] + bytes([body[i] ^ 1]) + body[i + 1:]
    return seal_info(req.call_id, body) | {"edited": req.edited}


class Ask(BaseModel):
    question: str


@app.post("/api/ask")
async def ask(req: Ask):
    evon = E.Evon()
    if not evon.health():
        raise HTTPException(503, "Evon is not answering: start the Kaggle notebook and update Project/evon.env")
    from kavach import assistant
    answer, trace = await assistant.ask(req.question, evon, log=lambda *_: None)
    return {"answer": answer, "source": trace[-1].get("source", "evon"),
            "steps": [{"tool": t["tool"], "call_id": t["args"].get("call_id", "")} for t in trace if "tool" in t]}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7861, log_level="warning")
