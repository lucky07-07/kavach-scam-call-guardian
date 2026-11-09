# Run one call through the whole live-call pipeline and keep everything:
#   data/runs/<call_id>/result.json   verdict, evidence, claims, reason, warning, report, transcript, timings, seal
#   data/runs/<call_id>/warning.wav   the Telugu warning (flagged calls only)
# The screen replays these, so a demo never depends on a live Kaggle session.
# Usage (from the Project folder):
#   py -m kavach.run_call data/test_audio/X_mono.wav [--stereo] [--lang en-IN]
#   py -m kavach.run_call --transcript data/test_audio/X_mono.prisma.json      (reuse a saved Prisma transcript)
#   add --ledger data/ledger_test to keep test seals apart from the demo evidence
import argparse, json, sys
from pathlib import Path

from kavach import evon as E, guardian as G, notary as N, pipeline as P, transcript as T

RUNS = Path(__file__).parent.parent / "data" / "runs"


def save(result, audio):
    out = RUNS / result["call_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if audio:
        (out / "warning.wav").write_bytes(audio)
    return out


def summary(r):
    tm = r["timings"]
    lines = [f"{r['call_id']}: {r['verdict']} {r['tactics']}",
             f"  reason : {r['reason']}",
             f"  time   : listen {tm.get('listen_s', '-')} s, punctuate {tm['punctuate_s']} s, verdict at {tm['verdict_s']} s, "
             f"warning at {tm['warning_s']} s, total {tm['total_s']} s"]
    lines += [f"  evidence [{e['source']}] {e['tactic']}: {e['quote']}" for e in r["evidence"]]
    lines += [f"  rejected {c['tactic']} ({c['check']}): {c['quote'][:90]}" for c in r["claims"] if c["check"] != "ok"]
    if r["warning"]["text"]:
        lines.append(f"  warning [{r['warning']['source']}{' ' + str(r['warning']['rejected']) if r['warning']['rejected'] else ''}]: {r['warning']['text']}")
    if r["transcript"].get("warnings"):
        lines.append(f"  notes  : {r['transcript']['warnings']}")
    if r["seal"]:
        lines.append(f"  sealed : #{r['seal']['index']} packet {r['seal']['packet_sha256'][:16]}… stamp {r['seal']['stamp']}")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("audio", nargs="?")
    p.add_argument("--transcript", help="a saved kavach.transcript.v1 JSON instead of audio")
    p.add_argument("--lang", default="en-IN")
    p.add_argument("--stereo", action="store_true")
    p.add_argument("--ledger", help="ledger folder (default data/ledger)")
    p.add_argument("--no-seal", action="store_true")
    a = p.parse_args()
    evon = E.Evon()
    if not evon.health():
        sys.exit(f"Evon is not answering at {evon.url}: start the Kaggle notebook and update Project/evon.env")
    ledger = N.Ledger(a.ledger) if a.ledger else N.Ledger()
    if a.transcript:
        t = T.validate(json.loads(Path(a.transcript).read_text(encoding="utf-8")))
        result, audio = P.analyse(t, evon, ledger=ledger, seal=not a.no_seal,
                                  models={"stt": (t.get("prisma") or {}).get("model"), "evon": "gnani-evon-v3.3 Q4_K_M", "tts": f"{G.MODEL}/{G.VOICE}"})
    elif a.audio:
        result, audio = P.analyse_audio(a.audio, evon, a.lang, a.stereo, ledger=ledger, seal=not a.no_seal)
    else:
        p.error("give an audio file or --transcript")
    out = save(result, audio)
    print(summary(result))
    print(f"  saved  : {out}")


if __name__ == "__main__":
    main()
