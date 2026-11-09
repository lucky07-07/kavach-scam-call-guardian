# Live check of the Listener against the Timbre test audio (make_test_audio.py): for each call, transcribe the mono
# and the stereo file with Prisma and compare with the text that was spoken.
#   roles ok   - share of spoken turns whose midpoint falls in a Prisma turn with the same speaker
#   WER        - word error rate of the whole call (lower-cased, punctuation dropped)
#   verdict    - the rules' code-only bound on the Prisma transcript vs on the true text (same = Listener lost nothing)
# Spends Prisma credits. Usage: py -m kavach.check_listener [--mode mono|stereo|both]   (GNANI_API_KEY must be set)
import argparse, json, re, sys
from pathlib import Path

from kavach import listener as L, transcript as T
from kavach.rules import TACTICS, caller_lines, decide, red_lines, verify

AUDIO = Path(__file__).parent.parent / "data" / "test_audio"


FILLERS = {"uh", "um", "hmm", "ah", "er"}
# the same word spelled two ways is not an error ("thik" / "theek", "Mr" / "mister", "4" / "four")
VARIANTS = {"theek": "thik", "achchha": "achha", "acha": "achha", "mister": "mr", "ok": "okay", "zero": "0", "one": "1",
            "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}
# scam keywords: whether these survive speech-to-text decides whether the rules can still see the evidence
CUE_WORDS = re.compile(r"^(otp|pin|upi|password|pay|payment|transfer|fee|fine|deposit|card|cvv|account|link|download|"
                       r"install|app|qr|scan|code|block|blocked|arrest|police|bank|kyc|refund|send|money|rupees|share)$")


def words(s, fair=False):
    w = re.sub(r"[^\w\s]", " ", s.lower().replace("'", "")).split()
    if not fair:
        return w
    out = []
    for x in w:
        if x in FILLERS:
            continue
        x = VARIANTS.get(x, x)
        if out and x.isdigit() and re.fullmatch(r"[a-z]{1,4}", out[-1]):   # "sb 1234" == "sb1234"
            out[-1] += x
        else:
            out.append(x)
    return out


def cue_survival(ref, hyp):
    # share of scam keywords in what was said that appear in what Prisma heard (counted with multiplicity)
    r = [x for x in words(ref, True) if CUE_WORDS.match(x)]
    left = list(words(hyp, True))
    kept = 0
    for x in r:
        if x in left:
            left.remove(x); kept += 1
    return kept, len(r)


def wer(ref, hyp, fair=False):
    r, h = words(ref, fair), words(hyp, fair)
    d = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
    return d[len(h)] / max(len(r), 1)


def roles_ok(truth, got):
    hits = 0
    for t in truth["turns"]:
        mid = (t["start"] + t["end"]) / 2
        near = min(got["turns"], key=lambda g: 0 if (g["start"] or 0) <= mid <= (g["end"] or 0) else
                   min(abs(mid - (g["start"] or 0)), abs(mid - (g["end"] or 0))))
        hits += near["speaker"] == t["speaker"]
    return hits / len(truth["turns"])


def bound(t):
    call = T.rules_text(t)
    ev = [{"tactic": k, "quote": l} for l in caller_lines(call) for k in TACTICS if verify(k, l, call) == "ok"] + red_lines(call)
    return decide(ev)[0]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["mono", "stereo", "both"], default="both")
    p.add_argument("--bias", type=float, help="boost listener.BIAS_WORDS with this bias_score (0.5-2.0)")
    a = p.parse_args()
    tag = f"_bias{a.bias:g}" if a.bias else ""
    modes = ["mono", "stereo"] if a.mode == "both" else [a.mode]
    truths = sorted(AUDIO.glob("*.truth.json"))
    if not truths:
        sys.exit("No test audio yet: run py -m kavach.make_test_audio --go first")
    client, rows = L.PrismaBatch(), []
    for tf in truths:
        truth = json.loads(tf.read_text(encoding="utf-8"))
        uid = tf.name[:-len(".truth.json")]
        for mode in modes:
            cached = AUDIO / f"{uid}_{mode}{tag}.prisma.json"
            if cached.exists():   # never transcribe the same file twice
                got = json.loads(cached.read_text(encoding="utf-8"))
            else:
                got = L.listen(AUDIO / f"{uid}_{mode}.wav", "en-IN", stereo=mode == "stereo", call_id=uid, client=client, bias=a.bias)
                cached.write_text(json.dumps(got, ensure_ascii=False, indent=2), encoding="utf-8")
            said, heard = " ".join(x["text"] for x in truth["turns"]), " ".join(x["text"] for x in got["turns"])
            kept, cues = cue_survival(said, heard)
            row = {"call": uid, "kind": truth["prisma"]["kind"], "mode": mode, "bias": a.bias, "roles_ok": round(roles_ok(truth, got), 2),
                   "wer": round(wer(said, heard), 3), "wer_fair": round(wer(said, heard, fair=True), 3),
                   "cues_kept": kept, "cues": cues,
                   "bound_truth": bound(truth), "bound_prisma": bound(got), "warnings": got["warnings"]}
            rows.append(row)
            print(f"{row['kind']:7s} {mode:6s} roles {row['roles_ok']:.0%}  WER {row['wer']:.1%} (fair {row['wer_fair']:.1%})  "
                  f"keywords {kept}/{cues}  rules {row['bound_truth']} -> {row['bound_prisma']}  {uid} {' '.join(row['warnings'])}")
    (AUDIO / f"listener_check{tag}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    for mode in modes:
        r = [x for x in rows if x["mode"] == mode]
        print(f"{mode}{tag}: roles {sum(x['roles_ok'] for x in r) / len(r):.0%}, mean WER {sum(x['wer'] for x in r) / len(r):.1%} "
              f"(fair {sum(x['wer_fair'] for x in r) / len(r):.1%}), keywords kept {sum(x['cues_kept'] for x in r)}/{sum(x['cues'] for x in r)}, "
              f"rules bound unchanged {sum(x['bound_truth'] == x['bound_prisma'] for x in r)}/{len(r)}")


if __name__ == "__main__":
    main()
