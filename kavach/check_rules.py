# Code-only bounds for the Kavach rules on a JSONL test set (fields: id, kind, transcript), no Evon needed:
#   scam ceiling   - a scam can only be caught if some caller line verifies as a request or threat (or a red line fires)
#   genuine floor  - claim every tactic on every caller line; a genuine call that still reaches SCAM would be
#                    flagged whenever Evon over-claims, so it marks a cue that is too loose
# Usage: py -I check_rules.py <file.jsonl> [-v]
import collections, json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from rules import REQUEST_OR_THREAT, TACTICS, caller_lines, decide, red_lines, verify

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
verbose = "-v" in sys.argv
missed, flagged, loose = [], [], collections.Counter()
for r in rows:
    call = r["transcript"]
    ev = [{"tactic": t, "quote": l} for l in caller_lines(call) for t in TACTICS if verify(t, l, call) == "ok"] + red_lines(call)
    verdict, tactics = decide(ev)
    if r["kind"] == "scam" and verdict != "SCAM":
        missed.append(r)
    if r["kind"] == "genuine" and verdict == "SCAM":
        flagged.append((r, ev))
        loose.update(e["tactic"] for e in ev if e["tactic"] in REQUEST_OR_THREAT)

scams = sum(r["kind"] == "scam" for r in rows)
genuine = len(rows) - scams
print(f"{Path(sys.argv[1]).name}: scam ceiling {scams - len(missed)}/{scams}, "
      f"genuine never SCAM even if Evon claims everything {genuine - len(flagged)}/{genuine}")
print("  tactics that verify on worst-case genuine calls:", dict(loose.most_common()))
if verbose:
    for r in missed:
        print(f"\n## MISSED scam {r['id']} ({r.get('case_type', r.get('set'))})")
        print("   " + "\n   ".join(caller_lines(r["transcript"])))
    for r, ev in flagged:
        print(f"\n## FLAGGED genuine {r['id']} ({r.get('case_type', r.get('set'))})")
        for e in ev:
            if e["tactic"] in REQUEST_OR_THREAT:
                print(f"   {e['tactic']}: {e['quote']}")
