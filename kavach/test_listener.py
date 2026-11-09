# Offline tests for the Listener: a fake HTTP session replays the response shapes from Gnani's batch STT docs,
# so no API key or credits are used. Run: py -I -m kavach.test_listener   (from the Project folder)
import io, json, math, struct, sys, tempfile, wave
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from kavach import listener as L, transcript as T
from kavach.rules import caller_lines, decide, red_lines, verify, TACTICS

HERE = Path(__file__).parent


class Resp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, json.dumps(body)
    def json(self):
        return self._body
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeGnani:
    # create -> start -> status (IN_PROGRESS once, then COMPLETED) -> files -> transcript docs
    def __init__(self, docs, fail_file=None, rest=None):
        self.docs, self.fail_file, self.calls, self.polls, self.sent, self.rest = docs, fail_file, [], 0, None, rest or {}
    def request(self, method, url, headers=None, files=None, **kw):
        assert headers == {"X-API-Key-ID": "test-key"}
        if url == L.REST_URL:   # per-turn REST pass: answers by clip length, else nothing better than batch
            with wave.open(io.BytesIO(files["audio_file"][1])) as w:
                secs = round(w.getnframes() / w.getframerate())
            return Resp(200, {"transcript": self.rest.get(secs, "")})
        self.calls.append((method, url.rsplit("/jobs", 1)[-1]))
        if method == "POST" and url.endswith("/jobs"):
            self.sent = {"config": json.loads(files[0][1][1]), "names": [f[1][0] for f in files[1:]]}
            return Resp(201, {"job_id": "job-1", "status": "CREATED"})
        if url.endswith("/start"):
            return Resp(202, {"job_id": "job-1", "status": "STARTING"})
        if url.endswith("/files"):
            return Resp(200, {"job_id": "job-1", "data": [
                {"file_id": f"f{i}", "original_path": n, "status": "FAILED" if n == self.fail_file else "COMPLETED",
                 "transcript_url": f"https://s3.example/{n}.json", "error_message": "Empty transcript after 3 retries"}
                for i, n in enumerate(self.sent["names"])]})
        self.polls += 1
        return Resp(200, {"job_id": "job-1", "status": "COMPLETED" if self.polls > 1 else "IN_PROGRESS"})
    def get(self, url, timeout=None):
        return Resp(200, self.docs[url.rsplit("/", 1)[-1][:-5]])


def seg(t0, t1, text, spk=None):
    return {"segment_id": 0, "start_time": t0, "end_time": t1, "text": text, "speaker_id": spk}


def doc(name, segments, lang="en-IN"):
    return {"original_path": name, "language_code": lang, "duration_seconds": max(s["end_time"] for s in segments),
            "model": "gnani-prisma-v2.5", "segments": segments}


def wav_bytes(channels, seconds=0.5, rate=8000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate)
        frames = b"".join(struct.pack("<" + "h" * channels, *[int(3000 * math.sin(i / (5 + c))) for c in range(channels)])
                          for i in range(int(seconds * rate)))
        w.writeframes(frames)
    return buf.getvalue()


def client(docs, **kw):
    return L.PrismaBatch(api_key="test-key", session=FakeGnani(docs, **kw), poll_s=0)


checks = []
def check(name, cond):
    checks.append((name, bool(cond)))
    print(("ok   " if cond else "FAIL ") + name)


tmp = Path(tempfile.mkdtemp())

# 1. mono + diarization: the doc's own example, plus a scam call split across segments
mono = tmp / "kyc_call.wav"
mono.write_bytes(wav_bytes(1))
segs = [seg(0.0, 2.1, "Namaste ji, main SBI head office se bol raha hoon.", 2),
        seg(2.1, 4.0, "Aapka KYC expire ho gaya hai,", 2),
        seg(4.2, 6.0, "aaj update nahi kiya to account block ho jayega.", 2),
        seg(6.5, 7.4, "Achha, kya karna hai?", 1),
        seg(8.0, 11.0, "Aapke phone pe ek OTP aaya hoga, woh mujhe bataiye.", 2)]
c = client({"kyc_call.wav": doc("kyc_call.wav", segs)})
t = L.listen(mono, "en-IN", client=c)
sent = c.http.sent
check("mono: diarization on, 2 speakers, v2.5 model, scam words boosted", sent["config"] == {"model": "gnani-prisma-v2.5",
      "language_code": "en-IN", "mode": "transcribe", "with_diarization": True, "num_speakers": 2,
      "bias_list": L.BIAS_WORDS, "bias_score": 1.0})
check("mono: the speaker who talks more becomes the caller", [x["speaker"] for x in t["turns"]] == ["caller", "listener", "caller"])
check("mono: same-speaker segments merge into one turn", t["turns"][0]["text"].count("block ho jayega") == 1 and t["turns"][0]["end"] == 6.0)
check("mono: assignment recorded as a guess", t["speaker_assignment"] == "most_words")
pickup = L.from_diarized(doc("p.wav", [seg(0, 1, "Hello?", 1), seg(1.2, 6, "Sir I am calling from SBI, your KYC has expired today", 2),
                                       seg(6.2, 7, "Achha?", 1), seg(7.5, 11, "Please tell me the OTP you just received", 2)]), "p", None, None)
check("mono: listener saying 'Hello?' first is still the listener", [x["speaker"] for x in pickup["turns"]] == ["listener", "caller", "listener", "caller"])
check("mono: audio hash and Prisma job kept for the Notary", t["audio_sha256"] == T.sha256_file(mono) and t["prisma"]["job_id"] == "job-1")
check("mono: polled until COMPLETED", c.http.polls == 2)
call = T.rules_text(t)
ev = [{"tactic": k, "quote": l} for l in caller_lines(call) for k in TACTICS if verify(k, l, call) == "ok"]
check("mono: rules read the transcript (OTP request + account threat verify)",
      {"otp_pin_password_request", "account_or_service_threat"} <= {e["tactic"] for e in ev} and decide(ev)[0] == "SCAM")

# 1b. refine: batch dropped the end of the last turn; REST on that turn's audio slice restores it; Telugu loanwords go Latin
te = tmp / "te_call.wav"
te.write_bytes(wav_bytes(1, seconds=10))
segs = [seg(0.0, 3.0, "నేను HDFC బ్యాంక్ నుంచి మాట్లాడుతున్నాను", 1), seg(3.2, 4.0, "సరే", 2),
        seg(4.3, 7.0, "మేము మిమ్మల్ని ఓటీపీ లేదా", 1)]
# the last caller turn's slice is 4.1 s .. 10.0 s + 0.5 s padding, about 6 s long (the first turn's is about 4 s)
c = L.PrismaBatch(api_key="test-key", session=FakeGnani({"te_call.wav": doc("te_call.wav", segs, "te-IN")},
                                                        rest={6: "మేము మిమ్మల్ని ఓటీపీ లేదా పిన్ అడగము"}), poll_s=0)
t = L.listen(te, "te-IN", client=c)
last = t["turns"][-1]
check("refine: the dropped 'PIN అడగము' (we won't ask) is restored from REST", last["text"].endswith("PIN అడగము"))
check("refine: batch's text is kept for audit", last["prisma_text"].endswith("ఓటీపీ లేదా"))
check("latinise: Telugu-script loanwords are written in Latin", "OTP" in last["text"] and "bank" in t["turns"][0]["text"])

# 2. the family swaps a wrong guess
s = T.validate(T.swap_speakers(t))
check("swap: roles flip and assignment becomes manual", s["turns"][0]["speaker"] == "listener" and s["speaker_assignment"] == "manual")

# 3. stereo: left channel = caller, each channel transcribed alone, turns interleaved by time
stereo = tmp / "two_channel.wav"
stereo.write_bytes(wav_bytes(2))
left, right = L.split_stereo(stereo.read_bytes())
with wave.open(io.BytesIO(left)) as w:
    check("stereo: split gives mono 16-bit channels of equal length", w.getnchannels() == 1 and w.getnframes() == 4000)
c = client({"caller.wav": doc("caller.wav", [seg(0.0, 3.0, "Main FedEx se bol raha hoon."), seg(6.0, 9.0, "Abhi 48,000 fine online bharna hoga.")]),
            "listener.wav": doc("listener.wav", [seg(3.5, 5.0, "Maine koi parcel nahi bheja.")])})
t = L.listen(stereo, "en-IN", stereo=True, client=c)
check("stereo: no diarization requested, two files sent", c.http.sent["config"]["with_diarization"] is False and c.http.sent["names"] == ["caller.wav", "listener.wav"])
check("stereo: turns ordered by time across channels", [x["speaker"] for x in t["turns"]] == ["caller", "listener", "caller"])
check("stereo: assignment is certain", t["speaker_assignment"] == "stereo_channel" and t["source"] == "prisma-batch-stereo")

# 4. failures surface as ListenerError, not as an empty transcript
for name, fn in [("failed file", lambda: L.listen(mono, client=client({}, fail_file="kyc_call.wav"))),
                 ("no speech", lambda: L.from_diarized(doc("x.wav", [seg(0, 1, "  ", 1)]), "x", None, None)),
                 ("mono file in stereo mode", lambda: L.split_stereo(wav_bytes(1)))]:
    try:
        fn(); check(f"error: {name}", False)
    except L.ListenerError:
        check(f"error: {name}", True)
one = L.from_diarized(doc("x.wav", [seg(0, 1, "hello", 1), seg(1, 2, "sir please listen", 1)]), "x", None, None)
check("one speaker: kept, with a warning", one["warnings"] and all(x["speaker"] == "caller" for x in one["turns"]))
real_load_key, L.load_key = L.load_key, lambda: None   # as if neither GNANI_API_KEY nor gnani.env existed
try:
    L.PrismaBatch(api_key=None, session=FakeGnani({}))
    check("missing key: refused", False)
except L.ListenerError:
    check("missing key: refused", True)
finally:
    L.load_key = real_load_key

# 5. text transcripts (the 44 Telugu calls, ICFD) convert to the same schema and back unchanged
rows = [json.loads(l) for l in open(HERE.parent / "data" / "kavach_calls_44.jsonl", encoding="utf-8")]
same = all(T.rules_text(T.validate(T.from_text(r["transcript"], r["id"], "te-IN"))) == r["transcript"] for r in rows)
check("text: all 44 Telugu calls round-trip exactly", same)

bad = [n for n, ok in checks if not ok]
print(f"\n{len(checks) - len(bad)}/{len(checks)} passed")
sys.exit(1 if bad else 0)
