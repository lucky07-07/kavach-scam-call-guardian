# Agent 7, Notary: tamper-evident evidence for every flagged call.
#   packet  - the incident (audio hash, transcript, evidence, verdict, warning, rules version), stored as canonical JSON;
#             it stays on the device
#   record  - {index, call_id, packet hash, previous record's hash}: a hash chain, so no record can be edited, removed
#             or reordered without breaking every later link
#   stamp   - the record's SHA-256 is sent to OpenTimestamps calendars, which commit it to the Bitcoin blockchain
#             (free; only 32 bytes leave the device). Bitcoin confirmation takes a few hours: until then a stamp is
#             "pending"; upgrade() fetches the proof, and verify() checks it against the real block via a block explorer.
# The OpenTimestamps CLI needs an OpenSSL DLL that Windows lacks, so this talks to the calendars directly with the
# core library, as the CLI does.
import hashlib, io, json, os, time
from pathlib import Path

import requests
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.op import OpAppend, OpSHA256
from opentimestamps.core.serialize import StreamDeserializationContext, StreamSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

LEDGER = Path(__file__).parent.parent / "data" / "ledger"
CALENDARS = ["https://a.pool.opentimestamps.org", "https://b.pool.opentimestamps.org", "https://a.pool.eternitywall.com"]
EXPLORER = "https://blockstream.info/api"
RULES_FILE = Path(__file__).parent / "rules.py"
HEADERS = {"Accept": "application/vnd.opentimestamps.v1", "User-Agent": "kavach-notary"}
GENESIS = "0" * 64
# a mined block's header never changes, so its hash, Merkle root and time are fetched once and kept here; every check
# still compares the proof against that Merkle root (only the network lookup is skipped)
BLOCKS = LEDGER / "bitcoin_blocks.json"


def block_header(height, http, cache=True):
    # -> {"hash", "merkle_root", "timestamp"} for a Bitcoin block, from the explorer or the local cache
    known = json.loads(BLOCKS.read_text(encoding="utf-8")) if cache and BLOCKS.exists() else {}
    if str(height) in known:
        return known[str(height)]
    block_hash = http.get(f"{EXPLORER}/block-height/{height}", timeout=20).text.strip()
    block = http.get(f"{EXPLORER}/block/{block_hash}", timeout=20).json()
    header = {"hash": block_hash, "merkle_root": block["merkle_root"], "timestamp": block["timestamp"]}
    if cache:
        known[str(height)] = header
        BLOCKS.parent.mkdir(parents=True, exist_ok=True)
        BLOCKS.write_text(json.dumps(known, indent=1, sort_keys=True), encoding="utf-8")
    return header


def canonical(obj):
    # one byte sequence per object, so the same packet always has the same hash
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def rules_sha256():
    return sha256(RULES_FILE.read_bytes())


def make_packet(transcript, verdict, tactics, evidence, warning, benign=(), models=None):
    return {"schema": "kavach.incident.v1", "call_id": transcript["call_id"], "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "audio_sha256": transcript.get("audio_sha256"), "transcript": transcript, "verdict": verdict, "tactics": list(tactics),
            "evidence": list(evidence), "benign": list(benign), "warning": warning, "rules_sha256": rules_sha256(),
            "models": models or {}}


# ---- OpenTimestamps -------------------------------------------------------------------------------------------

def _dtf(b):
    return DetachedTimestampFile.deserialize(StreamDeserializationContext(io.BytesIO(b)))


def _bytes(dtf):
    buf = io.BytesIO()
    dtf.serialize(StreamSerializationContext(buf))
    return buf.getvalue()


def ots_stamp(data, calendars=CALENDARS, session=None):
    # -> .ots file bytes committing sha256(data); a random nonce keeps the calendar from learning the digest
    http = session or requests
    root = Timestamp(hashlib.sha256(data).digest())
    tip = root.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())
    accepted = []
    for url in calendars:
        try:
            r = http.post(f"{url}/digest", data=tip.msg, headers=HEADERS, timeout=20)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            tip.merge(Timestamp.deserialize(StreamDeserializationContext(io.BytesIO(r.content)), tip.msg))
            accepted.append(url)
    if not accepted:
        raise RuntimeError("no OpenTimestamps calendar accepted the stamp")
    return _bytes(DetachedTimestampFile(OpSHA256(), root)), accepted


def _node(ts, msg):
    if ts.msg == msg:
        return ts
    for child in ts.ops.values():
        found = _node(child, msg)
        if found:
            return found
    return None


def ots_upgrade(ots_bytes, session=None):
    # ask each pending calendar for the finished proof; -> (new bytes, upgraded?)
    http = session or requests
    dtf, changed = _dtf(ots_bytes), False
    for msg, att in list(dtf.timestamp.all_attestations()):
        if not isinstance(att, PendingAttestation):
            continue
        try:
            r = http.get(f"{att.uri}/timestamp/{msg.hex()}", headers=HEADERS, timeout=20)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            _node(dtf.timestamp, msg).merge(Timestamp.deserialize(StreamDeserializationContext(io.BytesIO(r.content)), msg))
            changed = True
    return (_bytes(dtf) if changed else ots_bytes), changed


def ots_status(ots_bytes, data, session=None):
    # -> {"state": confirmed|pending|invalid, ...}; a confirmed proof is checked against the block's Merkle root
    http = session or requests
    dtf = _dtf(ots_bytes)
    if dtf.file_digest != hashlib.sha256(data).digest():
        return {"state": "invalid", "why": "stamp is for different data"}
    pending, confirmed = [], []
    for msg, att in dtf.timestamp.all_attestations():
        if isinstance(att, BitcoinBlockHeaderAttestation):
            try:
                block = block_header(att.height, http, cache=session is None)   # tests pass their own session: no cache
                block_hash = block["hash"]
            except (requests.RequestException, ValueError, KeyError):
                confirmed.append({"height": att.height, "checked": False})
                continue
            if block["merkle_root"] != msg[::-1].hex():
                return {"state": "invalid", "why": f"proof does not match Bitcoin block {att.height}"}
            confirmed.append({"height": att.height, "checked": True, "block": block_hash,
                              "time": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(block["timestamp"]))})
        elif isinstance(att, PendingAttestation):
            pending.append(att.uri)
    if confirmed:
        return {"state": "confirmed", "bitcoin": min(confirmed, key=lambda c: c["height"])}
    return {"state": "pending", "calendars": pending}


# ---- ledger ---------------------------------------------------------------------------------------------------

class Ledger:
    def __init__(self, root=LEDGER, calendars=CALENDARS, session=None, stamp=True):
        self.root = Path(root)
        self.calendars, self.session, self.stamp = calendars, session, stamp
        (self.root / "packets").mkdir(parents=True, exist_ok=True)
        (self.root / "records").mkdir(parents=True, exist_ok=True)

    def records(self):
        return sorted((self.root / "records").glob("*.json"))

    def seal(self, packet, stamp=None):
        stamp = self.stamp if stamp is None else stamp
        body = canonical(packet)
        packet_file = self.root / "packets" / f"{packet['call_id']}.json"
        if packet_file.exists():
            raise FileExistsError(f"{packet['call_id']} is already sealed; evidence is never overwritten")
        prev = self.records()
        record = {"schema": "kavach.seal.v1", "index": len(prev), "call_id": packet["call_id"], "packet_sha256": sha256(body),
                  "prev_record_sha256": sha256(prev[-1].read_bytes()) if prev else GENESIS,
                  "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rec_bytes = canonical(record)
        rec_file = self.root / "records" / f"{record['index']:05d}.json"
        packet_file.write_bytes(body)
        rec_file.write_bytes(rec_bytes)
        out = {"call_id": packet["call_id"], "index": record["index"], "packet_sha256": record["packet_sha256"],
               "record_sha256": sha256(rec_bytes), "stamp": "none"}
        if stamp:
            ots, accepted = ots_stamp(rec_bytes, self.calendars, self.session)
            rec_file.with_suffix(".json.ots").write_bytes(ots)
            out.update(stamp="pending", calendars=accepted)
        return out

    def upgrade(self):
        done = []
        for rec in self.records():
            ots_file = rec.with_suffix(".json.ots")
            if ots_file.exists():
                new, changed = ots_upgrade(ots_file.read_bytes(), self.session)
                if changed:
                    ots_file.write_bytes(new)
                    done.append(rec.name)
        return done

    def _record_for(self, call_id):
        for rec in self.records():
            r = json.loads(rec.read_bytes())
            if r["call_id"] == call_id:
                return rec, r
        raise KeyError(f"{call_id} has no seal")

    def verify(self, call_id, packet_bytes=None):
        # packet_bytes: a copy someone hands over (police, bank); default = the stored packet
        rec_file, record = self._record_for(call_id)
        body = packet_bytes if packet_bytes is not None else (self.root / "packets" / f"{call_id}.json").read_bytes()
        report = {"call_id": call_id, "index": record["index"], "packet_matches_seal": sha256(body) == record["packet_sha256"]}
        chain_ok, prev = True, GENESIS
        for i, rec in enumerate(self.records()):
            r = json.loads(rec.read_bytes())
            chain_ok &= r["index"] == i and r["prev_record_sha256"] == prev
            prev = sha256(rec.read_bytes())
            if rec == rec_file:
                break
        report["chain_intact"] = chain_ok
        ots_file = rec_file.with_suffix(".json.ots")
        report["stamp"] = ots_status(ots_file.read_bytes(), rec_file.read_bytes(), self.session) if ots_file.exists() else {"state": "none"}
        report["valid"] = report["packet_matches_seal"] and chain_ok and report["stamp"]["state"] in ("pending", "confirmed")
        return report
