# Narration for the launch trailer, one line per scene, voiced by Gnani Timbre (cached in data/tts_cache).
# Scene timings in the trailer are derived from these clips' lengths.
import json, sys, wave, io
from pathlib import Path

from kavach.timbre import Timbre, wav_of

OUT = Path(__file__).parent.parent.parent / "data" / "demo" / "trailer"
VOICE, MODEL, RATE = "Shubham", "timbre-v3.0", 24000   # "energetic, confident"
LINES = {   # 60-second cut for the "Demo Day Drop" award (best 60-second demo video); the scam call itself opens it, unnarrated
    "stakes":    "Twenty-two thousand crore rupees in a year. Sixty-two crore, every single day.",
    "reveal":    "Meet Kavach. A second listener on the call.",
    "agents":    "Eight agents. Evon argues both sides. But code decides.",
    "listen":    "Gnani Prisma hears every word, and knows who the caller is.",
    "genuine":   "And a real bank call? Kavach stays silent.",
    "seal":      "The evidence is sealed on Bitcoin.",
    "family":    "Her family is alerted.",
    "ask":       "Then they ask Kavach what happened.",
    "sovereign": "Fully Indian. Fully Gnani.",
    "end":       "Kavach. Keep the listener safe.",
}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    tts, durations = Timbre(), {}
    for key, line in LINES.items():
        pcm = tts.speak(line, VOICE, MODEL, "en-IN", RATE, 1.0)
        (OUT / f"vo_{key}.wav").write_bytes(wav_of(pcm, RATE))
        durations[key] = round(len(pcm) / 2 / RATE, 2)
        print(f"{key:8s} {durations[key]:5.2f} s  {line}")
    (OUT / "narration.json").write_text(json.dumps(durations, indent=2), encoding="utf-8")
    print("total", round(sum(durations.values()), 1), "s,", sum(len(l) for l in LINES.values()), "chars")


if __name__ == "__main__":
    main()
