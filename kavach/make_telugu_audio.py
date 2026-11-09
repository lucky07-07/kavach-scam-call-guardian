# Demo calls in Telugu (data/kavach_calls_44.jsonl) or Hindi (data/kavach_calls_hindi.jsonl, --lang hi) voiced by
# Gnani Timbre (two voices, telephone band),
# written next to the ICFD test audio so the screen and the Listener check pick them up:
#   data/test_audio/te_<id>_mono.wav, te_<id>_stereo.wav, te_<id>.truth.json   (Hindi: <id>_mono.wav, ids end in _hi)
# Usage: py -m kavach.make_telugu_audio [ids ...] [--lang te|hi] [--go]
import argparse, json, sys
from pathlib import Path

from kavach import transcript as T
from kavach.gnani_key import load_key
from kavach.make_test_audio import GAP_S, OUT, RATE, interleave, write_wav
from kavach.timbre import Timbre

DATA = Path(__file__).parent.parent / "data"
SOURCES = {"te": (DATA / "kavach_calls_44.jsonl", "te-IN", "te_"), "hi": (DATA / "kavach_calls_hindi.jsonl", "hi-IN", "")}
MODEL, VOICES = "timbre-v3.0", {"caller": "Avinash", "listener": "Kalpana"}   # v3.0 voices speak Telugu too
DEFAULT = {"te": ["kyc_otp", "digital_arrest", "fraud_alert"], "hi": ["kyc_otp_hi", "digital_arrest_hi", "fraud_alert_hi"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ids", nargs="*")
    p.add_argument("--lang", choices=["te", "hi"], default="te")
    p.add_argument("--go", action="store_true")
    a = p.parse_args()
    source, lang, prefix = SOURCES[a.lang]
    rows = {r["id"]: r for r in map(json.loads, open(source, encoding="utf-8"))}
    calls = [rows[i] for i in (a.ids or DEFAULT[a.lang])]
    chars = sum(len(t["text"]) for c in calls for t in T.from_text(c["transcript"], c["id"])["turns"])
    print(f"{len(calls)} {a.lang} calls, {chars:,} characters")
    if not a.go:
        return print("dry run: add --go to call Timbre")
    load_key() or sys.exit("No Gnani key")
    tts, silence = Timbre(cache=OUT / "clips"), b"\0\0" * int(GAP_S * RATE)
    for c in calls:
        uid = f"{prefix}{c['id']}"
        truth = T.from_text(c["transcript"], uid, lang)
        mono, left, right, t = bytearray(), bytearray(), bytearray(), 0.0
        for turn in truth["turns"]:
            pcm = tts.speak(turn["text"], VOICES[turn["speaker"]], MODEL, lang, RATE)
            quiet = b"\0" * len(pcm)
            turn["start"], t = round(t, 2), t + len(pcm) / 2 / RATE
            turn["end"], t = round(t, 2), t + GAP_S
            mono += pcm + silence
            left += (pcm if turn["speaker"] == "caller" else quiet) + silence
            right += (pcm if turn["speaker"] == "listener" else quiet) + silence
        # a real call does not stop on the last syllable; without trailing silence Prisma dropped the final words
        tail = b"\0\0" * int(1.5 * RATE)
        mono, left, right = mono + tail, left + tail, right + tail
        write_wav(OUT / f"{uid}_mono.wav", bytes(mono), 1)
        write_wav(OUT / f"{uid}_stereo.wav", interleave(bytes(left), bytes(right)), 2)
        truth.update(audio_sha256=T.sha256_file(OUT / f"{uid}_mono.wav"), duration_s=round(t, 2),
                     prisma={"tts": {"model": MODEL, "voices": VOICES, "sample_rate": RATE}, "kind": c["kind"], "script": c["id"]})
        (OUT / f"{uid}.truth.json").write_text(json.dumps(T.validate(truth), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {c['kind']:7s} {uid}: {t:.0f} s, {len(truth['turns'])} turns")


if __name__ == "__main__":
    main()
