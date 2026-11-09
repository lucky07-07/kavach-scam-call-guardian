# The Listener's output (schemas/transcript.schema.json), shared by every downstream agent.
# Agents read turns; the rules read the "Caller: … / User: …" text from rules_text().
import hashlib, json, time
from pathlib import Path

SCHEMA_ID = "kavach.transcript.v1"
SCHEMA = json.loads((Path(__file__).parent / "schemas" / "transcript.schema.json").read_text(encoding="utf-8"))
_LABEL = {"caller": "Caller", "listener": "User"}   # rules.py was written for "Caller:" / "User:" lines


def now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def make(call_id, source, language, turns, speaker_assignment, audio_sha256=None, duration_s=None, prisma=None, warnings=()):
    return {"schema": SCHEMA_ID, "call_id": call_id, "source": source, "language": language,
            "audio_sha256": audio_sha256, "duration_s": duration_s, "speaker_assignment": speaker_assignment,
            "turns": list(turns), "prisma": prisma, "warnings": list(warnings), "created_at": now_utc()}


def validate(t):
    import jsonschema
    jsonschema.validate(t, SCHEMA)
    return t


def rules_text(t):
    return "\n".join(f"{_LABEL[x['speaker']]}: {x['text']}" for x in t["turns"])


def from_text(text, call_id, language="en-IN"):
    # a typed or dataset transcript in "Caller: … / User: …" form; other lines are ignored
    turns = []
    for line in text.splitlines():
        label, _, said = line.partition(":")
        role = {"caller": "caller", "user": "listener", "listener": "listener"}.get(label.strip().lower())
        if role and said.strip():
            turns.append({"speaker": role, "text": said.strip(), "start": None, "end": None, "raw_speaker": label.strip()})
    return make(call_id, "text", language, turns, "text_labels")


def swap_speakers(t):
    # the family says the guess was wrong: caller and listener trade places
    flipped = [dict(x, speaker="listener" if x["speaker"] == "caller" else "caller") for x in t["turns"]]
    return dict(t, turns=flipped, speaker_assignment="manual", created_at=now_utc())
