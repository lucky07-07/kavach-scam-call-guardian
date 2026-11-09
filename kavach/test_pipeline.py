# Offline tests for the live-call pipeline with a scripted fake Evon (no GPU, no Gnani credits, no network).
# Run from the Project folder: py -m kavach.test_pipeline
import json, re, sys, tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from kavach import evon as E, guardian as G, notary as N, pipeline as P, transcript as T
from kavach.rules import TACTICS

HERE = Path(__file__).parent
checks = []
def check(name, cond):
    checks.append((name, bool(cond)))
    print(("ok   " if cond else "FAIL ") + name)


class FakeEvon:
    # punct: "add" (adds punctuation), "oracle" (returns the given text), "change" (alters a word), "none" (bad JSON)
    def __init__(self, claims=None, punct="add", oracle=None, warning="జాగ్రత్త, ఇది మోసం కాల్. OTP ఎవరికీ చెప్పకండి, వెంటనే ఫోన్ పెట్టేయండి."):
        self.claims, self.punct, self.oracle, self.warning, self.calls = claims or {}, punct, oracle, warning, []
    def json(self, messages, schema, max_tokens=600, temperature=0.1):
        props = schema["properties"]
        if "turns" in props:
            self.calls.append("punctuate")
            turns = [re.sub(r"^\d+\. ", "", l) for l in messages[-1]["content"].split("\n\n", 1)[1].splitlines()]
            if self.punct == "none":
                return None
            if self.punct == "oracle":
                return {"turns": self.oracle}
            out = [t[0].upper() + t[1:] + "." for t in turns]
            if self.punct == "change":
                out[0] = out[0].replace("otp", "pin", 1) if "otp" in out[0] else "Changed " + out[0]
            return {"turns": out}
        if "money_or_fee_request" in props:
            self.calls.append("prosecutor")
            return {t: {"present": t in self.claims, "quote": self.claims.get(t, "")} for t in TACTICS}
        if "benign_signals" in props:
            self.calls.append("defender")
            return {"benign_signals": []}
        if "complaint_english" in props:
            self.calls.append("reporter")
            return {"caller_claimed_to_be": "SBI head office", "caller_demanded": "the OTP (as heard)",
                    "complaint_english": "Complaint: caller claimed to be SBI, asked for OTP (as heard).", "summary_telugu": "SBI పేరుతో OTP అడిగారు."}
        self.calls.append("explainer")
        return {"reason": "The caller asked for the OTP and threatened to block the account."}
    def chat(self, messages, max_tokens=512, schema=None, temperature=0.3):
        if "spoken warning" in messages[0]["content"]:
            self.calls.append("warning")
            return {"content": self.warning, "seconds": 0}
        raise AssertionError("unexpected free-text request")


def prisma_style(text, call_id):
    # what Prisma batch returns: lower case, no punctuation
    t = T.from_text(text, call_id)
    turns = [dict(x, text=re.sub(r"\s+", " ", re.sub(r"[^\w\sఀ-౿₹']", " ", x["text"].lower())).strip()) for x in t["turns"]]
    return T.validate(dict(t, source="prisma-batch-diarized", speaker_assignment="most_words", turns=turns))


def ledger():
    return N.Ledger(Path(tempfile.mkdtemp()), stamp=False)


KYC = ("Caller: Namaste ji, main SBI head office se bol raha hoon. Aapka KYC expire ho gaya hai.\nUser: Achha?\n"
       "Caller: Aapke phone pe ek OTP aaya hoga, woh mujhe bataiye, warna account block ho jayega.")
kyc = prisma_style(KYC, "kyc")
otp_line = kyc["turns"][2]["text"]

# 1. punctuation
p = E.punctuate(kyc, FakeEvon())
check("punctuate: Evon's punctuation is kept when no word changed", p["turns"][2]["text"].endswith(".") and not p["warnings"])
p = E.punctuate(kyc, FakeEvon(punct="change"))
check("punctuate: a turn whose words Evon changed keeps Prisma's text, with a warning",
      p["turns"][0]["text"] == kyc["turns"][0]["text"] and p["warnings"] and p["turns"][2]["text"].endswith("."))
p = E.punctuate(kyc, FakeEvon(punct="none"))
check("punctuate: broken Evon output leaves the transcript as Prisma gave it", [x["text"] for x in p["turns"]] == [x["text"] for x in kyc["turns"]])
check("punctuate: typed transcripts are not sent to Evon", E.punctuate(T.from_text(KYC, "t"), FakeEvon())["turns"][0]["text"].startswith("Namaste"))

# 2. full pipeline, SCAM backed by the caller's own words
ev = FakeEvon(claims={"otp_pin_password_request": otp_line.capitalize() + ".", "account_or_service_threat": "warna account block ho jayega"})
led = ledger()
r, audio = P.analyse(kyc, ev, ledger=led, speak=False)
check("pipeline: verified OTP request + threat -> SCAM", r["verdict"] == "SCAM" and set(r["tactics"]) >= {"otp_pin_password_request"})
check("pipeline: agents run in the fixed order", ev.calls == ["punctuate", "prosecutor", "defender", "explainer", "warning", "reporter"] or
      ev.calls == ["punctuate", "defender", "prosecutor", "explainer", "warning", "reporter"])
check("pipeline: Evon's clean Telugu warning is used", r["warning"]["source"] == "evon")
check("pipeline: complaint drafted for SCAM", "OTP" in r["report"])
check("pipeline: flagged call is sealed and verifies", r["seal"] and led.verify("kyc")["packet_matches_seal"])
fa = r["family_alert"]
check("family alert: SCAM alerts the family in Telugu, urgent, linked to the seal, without the caller's words",
      fa["send"] and fa["level"] == "urgent" and fa["lang"] == "te" and G.telugu_ratio(fa["text"]) > 0.6
      and fa["seal_index"] == r["seal"]["index"] and not G.echoes(fa["text"], T.rules_text(kyc)) and "OTP" in fa["english"])
check("family alert: a Hindi listener's family is alerted in Hindi",
      P.analyse(kyc, ev, ledger=ledger(), speak=False, warn_lang="hi")[0]["family_alert"]["text"].startswith("ज़रूरी"))
sealed = json.loads((led.root / "packets" / "kyc.json").read_bytes())
check("pipeline: the sealed packet holds transcript, evidence, verdict, warning and report",
      sealed["verdict"] == "SCAM" and sealed["evidence"] == r["evidence"] and sealed["report"] and sealed["warning"]["source"] == "evon")

# 3. the Judge decides, not Evon
lies = FakeEvon(claims={"otp_pin_password_request": "Please read me your OTP now", "money_or_fee_request": "Send 5000 rupees today"})
r, _ = P.analyse(kyc, lies, ledger=ledger(), speak=False)
check("judge: invented quotes are rejected -> no OTP/money evidence", not {"otp_pin_password_request", "money_or_fee_request"} & set(r["tactics"])
      and all(c["check"] == "not in caller lines" for c in r["claims"]))
genuine = prisma_style("Caller: Namaskaram, SBI branch nunchi. Mee pension credit ayyindi.\nUser: Thank you\n"
                       "Caller: Meeru emi cheyyalsina avasaram ledu. Evaraina OTP adigite cheppakandi.", "pension")
everything = FakeEvon(claims={t: genuine["turns"][2]["text"] for t in TACTICS})
r, _ = P.analyse(genuine, everything, ledger=ledger(), speak=False)
check("judge: Evon claiming every tactic on a genuine call cannot make it SCAM", r["verdict"] != "SCAM")
listener_line = FakeEvon(claims={"otp_pin_password_request": "Achha?"})
check("judge: a listener line is never caller evidence", P.analyse(kyc, listener_line, ledger=ledger(), speak=False)[0]["claims"][0]["check"] == "not in caller lines")

# 4. SAFE calls: silent, nothing sealed
r, audio = P.analyse(genuine, FakeEvon(), ledger=ledger(), speak=True)
check("SAFE: no warning, no audio, no seal, no complaint, no family alert", r["verdict"] == "SAFE" and r["warning"]["source"] == "silent"
      and audio is None and r["seal"] is None and r["report"] == "" and r["family_alert"] == {"send": False})
import tempfile as _t
box = Path(_t.mkdtemp()) / "outbox.jsonl"
from kavach import family_alert as F
F.queue(r["family_alert"], "pension", box)
F.queue(F.build("SCAM", ["otp_pin_password_request"]), "kyc", box)
check("family alert: only flagged calls reach the outbox", [json.loads(l)["call_id"] for l in box.read_text(encoding="utf-8").splitlines()] == ["kyc"])

# 5. red lines catch what Evon misses
calls = {x["id"]: x for x in map(json.loads, open(HERE.parent / "data" / "kavach_calls_44.jsonl", encoding="utf-8"))}
r, _ = P.analyse(T.from_text(calls["army_qr"]["transcript"], "army_qr"), FakeEvon(), ledger=ledger(), speak=False)
check("red line: PIN-to-receive is SCAM even when Evon claims nothing", r["verdict"] == "SCAM" and r["verdict_without_red_lines"] == "SAFE")

# 6. Guardian falls back when Evon's warning repeats the caller
r, _ = P.analyse(kyc, FakeEvon(claims={"otp_pin_password_request": otp_line}, warning="woh mujhe bataiye అంటున్నారు జాగ్రత్త"),
                 ledger=ledger(), speak=False)
check("guardian: an echoing Evon warning is replaced by the approved one", r["warning"]["source"] == "template")

# 7. all 44 Telugu calls, Evon claiming nothing: only red-line scams flagged, no genuine call
flagged = {i for i, c in calls.items() if P.analyse(T.from_text(c["transcript"], i), FakeEvon(), ledger=ledger(), speak=False, seal=False)[0]["verdict"] != "SAFE"}
check(f"44 calls, silent Evon: {len(flagged)} flagged, all scams by red line", flagged and all(calls[i]["kind"] == "scam" for i in flagged))

# 8. the punctuation fix restores the text-level bounds on Prisma-style Telugu
from kavach.rules import caller_lines, decide, red_lines, verify


def bound(t):
    # code-only: every tactic claimed on every caller line
    call = T.rules_text(t)
    ev = [{"tactic": k, "quote": l} for l in caller_lines(call) for k in TACTICS if verify(k, l, call) == "ok"] + red_lines(call)
    return decide(ev)[0]
plain = [bound(prisma_style(c["transcript"], i)) for i, c in calls.items()]
fixed = []
for i, c in calls.items():
    ps = prisma_style(c["transcript"], i)
    original = [x["text"] for x in T.from_text(c["transcript"], i)["turns"]]
    oracle = [o if E._words(o) == E._words(x["text"]) else x["text"] for o, x in zip(original, ps["turns"])]
    fixed.append(bound(E.punctuate(ps, FakeEvon(punct="oracle", oracle=oracle))))
kinds = [c["kind"] for c in calls.values()]
score = lambda vs: (sum(v == "SCAM" for v, k in zip(vs, kinds) if k == "scam"), sum(v != "SCAM" for v, k in zip(vs, kinds) if k == "genuine"))
check(f"punctuation fix: Prisma-style Telugu bounds {score(plain)} -> {score(fixed)} with correct punctuation (22, 22 = text level)", score(fixed) == (22, 22))

bad = [n for n, ok in checks if not ok]
print(f"\n{len(checks) - len(bad)}/{len(checks)} passed")
sys.exit(1 if bad else 0)
