# Offline tests for the Guardian (warning choice and checks) and the Notary (packet, hash chain, OpenTimestamps).
# Fakes stand in for Timbre, the OpenTimestamps calendars and the block explorer, so nothing leaves the machine.
# Run from the Project folder: py -m kavach.test_guardian_notary
import io, itertools, json, sys, tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.serialize import StreamSerializationContext
from opentimestamps.core.timestamp import Timestamp

from kavach import guardian as G, notary as N, transcript as T

checks = []
def check(name, cond):
    checks.append((name, bool(cond)))
    print(("ok   " if cond else "FAIL ") + name)


CALL = "Caller: Namaste ji, main SBI head office se bol raha hoon. Aapka KYC expire ho gaya hai.\nUser: Achha?\nCaller: Aapke phone pe OTP aaya hoga, woh mujhe bataiye, warna account block ho jayega."
TACTICS = ["account_or_service_threat", "otp_pin_password_request"]
EVID = [{"tactic": "otp_pin_password_request", "quote": "Aapke phone pe OTP aaya hoga, woh mujhe bataiye", "source": "evon"},
        {"tactic": "account_or_service_threat", "quote": "warna account block ho jayega", "source": "evon"}]

# ---- Guardian ----
check("guardian: SAFE stays silent", G.choose("SAFE", [], [], CALL, "anything")["source"] == "silent")
good = "జాగ్రత్త, ఇది మోసం కాల్. OTP ఎవరికీ చెప్పకండి, వెంటనే ఫోన్ పెట్టేయండి."
c = G.choose("SCAM", TACTICS, EVID, CALL, good)
check("guardian: a clean Evon warning is spoken as written", c["source"] == "evon" and c["text"] == good)
for name, bad, why in [("repeats the caller", "జాగ్రత్త! woh mujhe bataiye అంటున్నారు, ఫోన్ పెట్టేయండి", "repeats the caller"),
                       ("English", "Careful, this is a scam call, hang up now.", "not mostly Telugu"),
                       ("a number", "జాగ్రత్త! 48,000 కట్టమంటున్నారు, ఫోన్ పెట్టేయండి", "contains a number"),
                       ("a link", "జాగ్రత్త! sbi-kyc.in లో ఏమీ చేయకండి", "contains a link"),
                       ("empty", "  ", "empty")]:
    c = G.choose("SCAM", TACTICS, EVID, CALL, bad)
    check(f"guardian: Evon text with {name} falls back to the approved warning", c["source"] == "template" and why in c["rejected"])
check("guardian: no Evon text -> approved warning", G.choose("SUSPICIOUS", ["secrecy_demand"], [], CALL)["source"] == "template")
check("guardian: power-cut threat names the connection, not the account",
      "కరెంట్" in G.template("SCAM", ["account_or_service_threat"], [{"tactic": "account_or_service_threat", "quote": "power connection cut"}]))
worst = []
for verdict, n in [("SCAM", 1), ("SCAM", 2), ("SUSPICIOUS", 1), ("SUSPICIOUS", 2)]:
    for combo in itertools.combinations(G.PRIORITY, n):
        if (verdict == "SCAM") != bool(set(combo) & G.REQUEST_OR_THREAT):
            continue
        t = G.template(verdict, combo)
        worst.append((len(t), G.telugu_ratio(t)))
check(f"guardian: every approved warning is short and mostly Telugu ({len(worst)} combinations, longest {max(w[0] for w in worst)} chars)",
      all(l <= G.MAX_CHARS and r >= 0.6 for l, r in worst))


class FakeTTS:
    def __init__(self): self.said = []
    def speak(self, text, voice, model, lang, rate, speed):
        self.said.append((voice, model, lang, rate, speed)); return b"\x01\x00" * 1600
tts = FakeTTS()
wav = G.speak(good, tts)
check("guardian: speaks in the Telugu voice, slowed down, as a WAV", wav[:4] == b"RIFF" and tts.said == [("Lehara", "timbre-v2.5", "te-IN", 16000, 0.9)])
check("guardian: silence produces no audio", G.speak("", tts) is None)

# ---- Notary ----
def ser(ts):
    buf = io.BytesIO(); ts.serialize(StreamSerializationContext(buf)); return buf.getvalue()


class Resp:
    def __init__(self, code, content=b"", body=None):
        self.status_code, self.content, self._body, self.text = code, content, body, content.decode("latin-1") if content else ""
    def json(self): return self._body


class FakeBitcoin:
    # calendar: accepts a digest and answers "pending"; after confirm(), returns a proof that the digest is a block's
    # Merkle root; explorer: serves that block
    def __init__(self): self.confirmed, self.sent, self.tamper_root, self.blocks = False, [], False, {}
    def post(self, url, data=None, headers=None, timeout=None):
        self.sent.append(data)
        ts = Timestamp(data); ts.attestations.add(PendingAttestation("https://cal.test"))
        return Resp(200, ser(ts))
    def get(self, url, headers=None, timeout=None):
        if url.startswith("https://cal.test/timestamp/"):
            if not self.confirmed:
                return Resp(404)
            msg = bytes.fromhex(url.rsplit("/", 1)[1])
            height = 870000 + len(self.blocks)          # each proof lands in its own block
            self.blocks[height] = msg
            ts = Timestamp(msg); ts.attestations.add(BitcoinBlockHeaderAttestation(height))
            return Resp(200, ser(ts))
        if "/block-height/" in url:
            return Resp(200, f"blockhash{url.rsplit('/', 1)[1]}".encode())
        if "/block/blockhash" in url:
            root = bytes(32) if self.tamper_root else self.blocks[int(url.rsplit("blockhash", 1)[1])]
            return Resp(200, body={"merkle_root": root[::-1].hex(), "timestamp": 1762300000})
        raise AssertionError(url)


transcript = T.from_text(CALL, "kyc-test-call", "en-IN")
packet = N.make_packet(transcript, "SCAM", TACTICS, EVID, {"text": good, "source": "evon"})
check("notary: packet carries the rules version", packet["rules_sha256"] == N.sha256(N.RULES_FILE.read_bytes()))
btc = FakeBitcoin()
led = N.Ledger(Path(tempfile.mkdtemp()), calendars=["https://cal.test"], session=btc)
s1 = led.seal(packet)
check("notary: seal is stamped and pending", s1["stamp"] == "pending" and s1["index"] == 0)
check("notary: only a 32-byte digest is sent to the calendar", all(len(d) == 32 for d in btc.sent))
check("notary: the digest sent is not the packet's own hash (nonce)", N.sha256(btc.sent[0]) != s1["packet_sha256"] and btc.sent[0].hex() != s1["record_sha256"])
v = led.verify("kyc-test-call")
check("notary: fresh seal verifies, stamp pending", v["valid"] and v["stamp"]["state"] == "pending")
p2 = N.make_packet(T.from_text("Caller: Your parcel is held, pay the fine online now\nUser: No", "second-call"), "SCAM", ["money_or_fee_request"], [], {})
s2 = led.seal(p2)
check("notary: second seal links to the first", s2["index"] == 1 and json.loads((led.root / "records" / "00001.json").read_bytes())["prev_record_sha256"] == s1["record_sha256"])
try:
    led.seal(packet); check("notary: the same call cannot be sealed twice", False)
except FileExistsError:
    check("notary: the same call cannot be sealed twice", True)

stored = (led.root / "packets" / "kyc-test-call.json").read_bytes()
edited = stored.replace(b'"verdict":"SCAM"', b'"verdict":"SAFE"')
check("notary: an edited copy (verdict changed) fails", not led.verify("kyc-test-call", edited)["packet_matches_seal"])
one_byte = bytearray(stored); one_byte[len(one_byte) // 2] ^= 1
check("notary: a one-byte edit fails", not led.verify("kyc-test-call", bytes(one_byte))["valid"])
check("notary: the untouched copy still passes", led.verify("kyc-test-call", stored)["valid"])

btc.confirmed = True
check("notary: upgrade fetches the Bitcoin proof", led.upgrade() == ["00000.json", "00001.json"])
v = led.verify("kyc-test-call")
check("notary: confirmed stamp is checked against the block's Merkle root",
      v["stamp"]["state"] == "confirmed" and v["stamp"]["bitcoin"]["checked"] and v["stamp"]["bitcoin"]["height"] == 870000)
btc.tamper_root = True
check("notary: a proof that does not match the block is rejected", led.verify("kyc-test-call")["stamp"]["state"] == "invalid")
btc.tamper_root = False

rec0 = led.root / "records" / "00000.json"
r0 = json.loads(rec0.read_bytes()); r0["call_id"] = "rewritten"
rec0.write_bytes(N.canonical(r0))
check("notary: rewriting an old record breaks the chain for every later call", not led.verify("second-call")["chain_intact"])

# the block-header cache skips the network, never the check: a wrong cached Merkle root still fails the proof
real = N.LEDGER / "records" / "00003.json"
if real.with_suffix(".json.ots").exists():
    ots, rec = real.with_suffix(".json.ots").read_bytes(), real.read_bytes()
    heights = [a.height for _, a in N._dtf(ots).timestamp.all_attestations() if isinstance(a, BitcoinBlockHeaderAttestation)]
    if heights:
        saved, N.BLOCKS = N.BLOCKS, Path(tempfile.mkdtemp()) / "blocks.json"
        N.BLOCKS.write_text(json.dumps({str(h): {"hash": "00", "merkle_root": "ab" * 32, "timestamp": 0} for h in heights}))
        check("notary: a confirmed proof is still checked against the (cached) block's Merkle root",
              N.ots_status(ots, rec)["state"] == "invalid")
        N.BLOCKS = saved

bad = [n for n, ok in checks if not ok]
print(f"\n{len(checks) - len(bad)}/{len(checks)} passed")
sys.exit(1 if bad else 0)
