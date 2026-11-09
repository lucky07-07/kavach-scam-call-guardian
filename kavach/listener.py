# Agent 1, Listener: call audio -> kavach.transcript.v1 (see transcript.py) using Gnani Prisma batch STT.
# Two ways in:
#   mono   - one file, Prisma diarization separates two speakers; whoever talks more is taken as the caller
#            (a guess the screen lets the family swap)
#   stereo - caller and listener on separate channels (left = caller by default); each channel is sent as its own
#            file without diarization, so the speaker is known for certain
# The API key is read from GNANI_API_KEY and is never written anywhere.
# CLI: py -m kavach.listener call.wav --lang en-IN [--stereo] [--out transcript.json]
import io, json, os, time, wave
from pathlib import Path

import requests

try:
    from . import transcript as T
    from .gnani_key import load_key
except ImportError:          # run as a plain script
    import transcript as T
    from gnani_key import load_key

BASE = "https://api.vachana.ai/stt/v3/batch/jobs"
MODEL = os.environ.get("KAVACH_PRISMA_MODEL", "gnani-prisma-v2.5")
POLL_S = 10                  # the docs ask for at least 10 s between polls
TERMINAL = {"COMPLETED", "PARTIAL_FAILURE", "FAILED", "START_FAILED", "CANCELLED"}
MAX_UPLOAD = 10 * 1024 * 1024
# Words Prisma is asked to listen for (bias_list: single words, letters only, at most 100): the payment, banking and
# remote-access vocabulary scam calls are made of. Domain words only, nothing taken from the test calls.
BIAS_WORDS = ["OTP", "UPI", "KYC", "PIN", "CVV", "IFSC", "NEFT", "IMPS", "RTGS", "Aadhaar", "PAN", "RBI", "CBI", "SEBI",
              "PhonePe", "Paytm", "GPay", "BHIM", "Mobikwik", "Freecharge", "AnyDesk", "TeamViewer", "QuickSupport", "APK",
              "SBI", "HDFC", "ICICI", "Axis", "Kotak", "Canara", "IndusInd", "Airtel", "Jio", "BSNL", "Vodafone",
              "FedEx", "BlueDart", "DTDC", "Amazon", "Flipkart", "LIC", "EMI", "refund", "cashback", "password", "netbanking",
              "debit", "credit", "QR", "deactivate", "customs", "parcel", "arrest", "warrant", "challan", "TSSPDCL"]
assert len(BIAS_WORDS) <= 100 and all(w.isalpha() for w in BIAS_WORDS)


class ListenerError(RuntimeError):
    pass


class PrismaBatch:
    # thin client for create -> start -> poll -> files -> transcript JSON
    def __init__(self, api_key=None, session=None, poll_s=POLL_S, timeout_s=900):
        self.key = api_key or load_key()
        if not self.key:
            raise ListenerError("No Gnani key: set GNANI_API_KEY or put it in Project/gnani.env")
        self.http = session or requests.Session()
        self.poll_s, self.timeout_s = poll_s, timeout_s

    def _call(self, method, url, **kw):
        for attempt in range(5):
            try:
                r = self.http.request(method, url, headers={"X-API-Key-ID": self.key}, timeout=120, **kw)
            except requests.ConnectionError:   # resets happen on the TLS handshake; the request never reached Prisma
                if attempt == 4:
                    raise
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code != 429 or attempt == 4:
                break
            time.sleep(min(int(r.headers.get("Retry-After") or 0) or 15 * (attempt + 1), 120))
        if r.status_code >= 400:
            raise ListenerError(f"Prisma {method} {url.split('/stt/')[-1]}: {r.status_code} {r.text[:300]}")
        return r.json()

    def transcribe(self, files, config):
        # files: [(name, bytes)]; returns {name: transcript document} plus the job record
        for name, data in files:
            if len(data) > MAX_UPLOAD:
                raise ListenerError(f"{name} is {len(data) / 1e6:.1f} MB; batch upload allows 10 MB per file")
        form = [("config", (None, json.dumps(config), "application/json"))]
        form += [("files", (name, data)) for name, data in files]
        job_id = self._call("POST", BASE, files=form)["job_id"]
        self._call("POST", f"{BASE}/{job_id}/start")
        return self.collect(job_id, config)

    def collect(self, job_id, config):
        # poll a started job and download its transcripts; also used to resume a job after an interruption
        t0 = time.time()
        while True:
            time.sleep(self.poll_s)
            status = self._call("GET", f"{BASE}/{job_id}")
            if status["status"] in TERMINAL:
                break
            if time.time() - t0 > self.timeout_s:
                raise ListenerError(f"Prisma job {job_id} still {status['status']} after {self.timeout_s} s")
        listing = self._call("GET", f"{BASE}/{job_id}/files")["data"]
        docs = {}
        for f in listing:
            if f["status"] != "COMPLETED":
                raise ListenerError(f"Prisma could not transcribe {f['original_path']}: {f.get('error_message')}")
            r = self.http.get(f["transcript_url"], timeout=120)   # presigned S3 link, no key header
            r.raise_for_status()
            docs[f["original_path"]] = r.json()
        return docs, {"job_id": job_id, "status": status["status"], "model": config["model"],
                      "config": config, "files": [f["file_id"] for f in listing]}


REST_URL = "https://api.vachana.ai/stt/v3"


def rest_transcribe(client, wav_bytes, language):
    # Prisma REST (clips up to 60 s): no speakers or timestamps, but it keeps the words batch mode drops at turn ends
    for attempt in range(4):
        try:
            r = client.http.request("POST", REST_URL, headers={"X-API-Key-ID": client.key}, timeout=120,
                                    files={"audio_file": ("turn.wav", wav_bytes)}, data={"language_code": language})
        except requests.ConnectionError:
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        return (r.json().get("transcript") or "").strip() if r.status_code == 200 else ""
    return ""


def _pcm(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()


def refine(t, channels, rate, language, client):
    # Batch mode separates the speakers and times each turn, but on te-IN it dropped the last words of some turns
    # ("... OTP లేదా" for "... OTP లేదా PIN అడగము", we will not ask for an OTP or PIN). Each turn's audio, extended
    # to where the next turn starts, is transcribed again with REST; the longer text is kept and batch's is recorded.
    # channels: {"caller": pcm, "listener": pcm} for stereo, or {"*": pcm} for mono.
    from concurrent.futures import ThreadPoolExecutor
    from kavach.timbre import wav_of
    turns = t["turns"]
    dur = len(next(iter(channels.values()))) / 2 / rate

    def one(i):
        turn = turns[i]
        if turn.get("start") is None:
            return None
        s = max(0.0, turn["start"] - 0.2)
        e = min(dur, (turns[i + 1]["start"] if i + 1 < len(turns) and turns[i + 1].get("start") is not None else dur) + 0.3)
        if e - s > 58 or e <= s:
            return None
        pcm = channels.get(turn["speaker"], channels.get("*"))
        return rest_transcribe(client, wav_of(pcm[int(s * rate) * 2:int(e * rate) * 2] + b"\0\0" * (rate // 2), rate), language)

    with ThreadPoolExecutor(4) as ex:
        texts = list(ex.map(one, range(len(turns))))
    out, better = [], 0
    for turn, text in zip(turns, texts):
        if text and len(text.split()) > len(turn["text"].split()):
            out.append(dict(turn, text=text, prisma_text=turn["text"]))
            better += 1
        else:
            out.append(turn)
    warnings = t.get("warnings", []) + ([f"{better} turn(s) re-transcribed per turn (batch dropped words)"] if better else [])
    return dict(t, turns=out, warnings=warnings, prisma=dict(t.get("prisma") or {}, refined_turns=better))


def latinise_turns(t):
    # English loanwords back in Latin script ("ఓటీపీ" -> "OTP"), as Kavach's rules, prompts and test calls write them
    from kavach.loanwords import latinise
    turns = [dict(x, text=latinise(x["text"]), prisma_text=x.get("prisma_text") or x["text"]) if latinise(x["text"]) != x["text"] else x
             for x in t["turns"]]
    return dict(t, turns=turns)


def turns_from_segments(segments, role_of, merge_gap_s=1.5):
    # Prisma gives short segments; consecutive segments of the same speaker become one turn
    turns = []
    for s in sorted(segments, key=lambda s: (s.get("start_time") or 0)):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        role, raw = role_of(s)
        last = turns[-1] if turns else None
        if last and last["speaker"] == role and (s.get("start_time") or 0) - (last["end"] or 0) <= merge_gap_s:
            last["text"] += " " + text
            last["end"] = s.get("end_time")
        else:
            turns.append({"speaker": role, "text": text, "start": s.get("start_time"), "end": s.get("end_time"),
                          "raw_speaker": raw})
    return turns


def from_diarized(doc, call_id, audio_sha256, prisma, caller_speaker=None):
    segs = [s for s in doc.get("segments", []) if (s.get("text") or "").strip()]
    speakers = []
    for s in sorted(segs, key=lambda s: s.get("start_time") or 0):
        if s.get("speaker_id") not in speakers:
            speakers.append(s.get("speaker_id"))
    warnings = []
    if not segs:
        raise ListenerError("Prisma returned no speech")
    if len(speakers) == 1:
        warnings.append("Prisma found only one speaker; every line is treated as the caller's")
    if len(speakers) > 2:
        warnings.append(f"Prisma found {len(speakers)} speakers; all but the caller are treated as the listener")
    # the caller is whoever talks more: the person who picks up usually speaks first ("Hello?"), so first-speaker
    # guessing flips real calls (2 of 6 Timbre test calls); talk share was right on 44/44, 191/200 and 195/200 text calls
    talk = {spk: sum(len((s.get("text") or "").split()) for s in segs if s.get("speaker_id") == spk) for spk in speakers}
    caller = caller_speaker if caller_speaker is not None else max(speakers, key=lambda spk: talk[spk])
    turns = turns_from_segments(segs, lambda s: ("caller" if s.get("speaker_id") == caller else "listener",
                                                 str(s.get("speaker_id"))))
    return T.make(call_id, "prisma-batch-diarized", doc.get("language_code"), turns,
                  "manual" if caller_speaker is not None else "most_words", audio_sha256,
                  doc.get("duration_seconds"), prisma, warnings)


def from_stereo(docs, call_id, audio_sha256, prisma, language):
    # docs: {"caller.wav": doc, "listener.wav": doc}; timestamps share one clock because both come from one recording
    segs = []
    for name, doc in docs.items():
        role = "caller" if name.startswith("caller") else "listener"
        segs += [dict(s, _role=role, _chan=name.split(".")[0]) for s in doc.get("segments", [])]
    turns = turns_from_segments(segs, lambda s: (s["_role"], s["_chan"]))
    if not turns:
        raise ListenerError("Prisma returned no speech on either channel")
    dur = max((d.get("duration_seconds") or 0) for d in docs.values()) or None
    return T.make(call_id, "prisma-batch-stereo", language, turns, "stereo_channel", audio_sha256, dur, prisma)


def split_stereo(wav_bytes, caller_channel=0):
    # one 16-bit stereo WAV -> (caller mono WAV, listener mono WAV)
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getnchannels() != 2 or w.getsampwidth() != 2:
            raise ListenerError("stereo mode needs a 2-channel 16-bit WAV")
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    chans = [bytearray(), bytearray()]
    for i in range(0, len(frames), 4):
        chans[0] += frames[i:i + 2]
        chans[1] += frames[i + 2:i + 4]
    out = []
    for c in (caller_channel, 1 - caller_channel):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as o:
            o.setnchannels(1); o.setsampwidth(2); o.setframerate(rate); o.writeframes(bytes(chans[c]))
        out.append(buf.getvalue())
    return out


def listen(audio_path, language="en-IN", stereo=False, caller_channel=0, call_id=None, client=None, bias=1.0, refine_turns=True):
    # bias: bias_score (0.5, 1.0, 1.5, 2.0) to boost BIAS_WORDS, or None for no boosting. On the 6 Timbre test calls
    # boosting at 1.0 changed one word ("challen" -> "challan") and nothing else, so it stays on: harmless, and it
    # helps exactly the words the rules look for
    path = Path(audio_path)
    data = path.read_bytes()
    sha = T.sha256_file(path)
    call_id = call_id or f"{path.stem}-{sha[:8]}"
    client = client or PrismaBatch()
    config = {"model": MODEL, "language_code": language, "mode": "transcribe"}
    if bias:
        config.update(bias_list=BIAS_WORDS, bias_score=bias)
    if stereo:
        caller, listener = split_stereo(data, caller_channel)
        docs, prisma = client.transcribe([("caller.wav", caller), ("listener.wav", listener)],
                                         dict(config, with_diarization=False))
        t = from_stereo(docs, call_id, sha, prisma, language)
        channels = {"caller": _pcm(caller)[0], "listener": _pcm(listener)[0]}
        rate = _pcm(caller)[1]
    else:
        docs, prisma = client.transcribe([(path.name, data)], dict(config, with_diarization=True, num_speakers=2))
        t = from_diarized(next(iter(docs.values())), call_id, sha, prisma)
        pcm, rate, nch = _pcm(data)
        channels = {"*": pcm} if nch == 1 else None
    if refine_turns and channels:
        t = refine(t, channels, rate, language, client)
    if language == "te-IN":
        t = latinise_turns(t)
    return T.validate(t)


if __name__ == "__main__":
    import argparse, sys
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Kavach Listener: call audio -> transcript JSON")
    p.add_argument("audio")
    p.add_argument("--lang", default="en-IN")
    p.add_argument("--stereo", action="store_true", help="caller and listener on separate channels")
    p.add_argument("--caller-channel", type=int, default=0, help="0 = left (default), 1 = right")
    p.add_argument("--out")
    a = p.parse_args()
    t = listen(a.audio, a.lang, a.stereo, a.caller_channel)
    js = json.dumps(t, ensure_ascii=False, indent=2)
    Path(a.out).write_text(js, encoding="utf-8") if a.out else print(js)
    print("\n" + T.rules_text(t), file=sys.stderr)
