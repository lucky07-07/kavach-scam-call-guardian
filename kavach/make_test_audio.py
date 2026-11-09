# Test audio for the Listener: ICFD-31k calls voiced by Gnani Timbre, caller and listener in two different voices.
# For each call it writes, under data/test_audio/:
#   <id>_mono.wav    both voices on one channel (Prisma has to separate the speakers)
#   <id>_stereo.wav  caller on the left, listener on the right
#   <id>.truth.json  the text that was spoken, as kavach.transcript.v1, to compare Prisma's output against
# Without --go it only reports the characters it would send (Timbre bills by text); nothing is called.
# Usage: py -m kavach.make_test_audio [--n 6] [--go]          (GNANI_API_KEY must be set for --go)
import argparse, json, re, sys
from pathlib import Path

from kavach import transcript as T
from kavach.gnani_key import load_key
from kavach.timbre import Timbre, wav_of

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "data" / "icfd31k" / "icfd_test_200.jsonl"
OUT = ROOT / "data" / "test_audio"
MODEL = "timbre-v3.0"                       # every v3.0 voice speaks all 10 languages
VOICES = {"caller": "Avinash", "listener": "Kalpana"}
RATE = 8000                                 # telephone band, as a real call would reach Prisma
GAP_S = 0.45


def write_wav(path, frames, channels):
    Path(path).write_bytes(wav_of(frames, RATE, channels))


def interleave(left, right):
    out = bytearray()
    for i in range(0, len(left), 2):
        out += left[i:i + 2] + right[i:i + 2]
    return bytes(out)


def pick(n):
    # the shortest calls, half scam and half genuine, so the credits go a long way
    rows = [json.loads(l) for l in open(SOURCE, encoding="utf-8")]
    by_kind = {k: sorted((r for r in rows if r["kind"] == k), key=lambda r: len(r["transcript"])) for k in ("scam", "genuine")}
    return [r for pair in zip(by_kind["scam"][:n - n // 2], by_kind["genuine"][:n // 2] + [None]) for r in pair if r]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--go", action="store_true", help="call Timbre and spend credits")
    a = p.parse_args()
    calls = pick(a.n)
    chars = sum(len(re.sub(r"^(Caller|User): ", "", l)) for c in calls for l in c["transcript"].splitlines())
    print(f"{len(calls)} calls ({sum(c['kind'] == 'scam' for c in calls)} scam), {chars:,} characters to synthesise")
    if not a.go:
        print("dry run: add --go to call Timbre")
        return
    load_key() or sys.exit("No Gnani key: set GNANI_API_KEY or put it in Project/gnani.env")
    OUT.mkdir(parents=True, exist_ok=True)
    tts, silence = Timbre(cache=OUT / "clips"), b"\0\0" * int(GAP_S * RATE)
    for c in calls:
        uid = re.sub(r"\W+", "_", c["id"].split("/")[-1])
        if (OUT / f"{uid}.truth.json").exists():
            print(f"  {c['kind']:7s} {uid}: already voiced, skipped")
            continue
        truth = T.from_text(c["transcript"], uid)
        mono, left, right, t = bytearray(), bytearray(), bytearray(), 0.0
        for turn in truth["turns"]:
            pcm = tts.speak(turn["text"], VOICES[turn["speaker"]], MODEL, "en-IN", RATE)
            quiet = b"\0" * len(pcm)
            turn["start"], t = round(t, 2), t + len(pcm) / 2 / RATE
            turn["end"], t = round(t, 2), t + GAP_S
            mono += pcm + silence
            left += (pcm if turn["speaker"] == "caller" else quiet) + silence
            right += (pcm if turn["speaker"] == "listener" else quiet) + silence
        write_wav(OUT / f"{uid}_mono.wav", bytes(mono), 1)
        write_wav(OUT / f"{uid}_stereo.wav", interleave(bytes(left), bytes(right)), 2)
        truth.update(audio_sha256=T.sha256_file(OUT / f"{uid}_mono.wav"), duration_s=round(t, 2),
                     prisma={"tts": {"model": MODEL, "voices": VOICES, "sample_rate": RATE}, "kind": c["kind"],
                             "icfd_id": c["id"], "case_type": c["case_type"]})
        (OUT / f"{uid}.truth.json").write_text(json.dumps(T.validate(truth), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {c['kind']:7s} {uid}: {t:.0f} s, {len(truth['turns'])} turns")


if __name__ == "__main__":
    main()
