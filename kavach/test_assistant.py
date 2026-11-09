# Offline test for the Family assistant over the real Kavach MCP server (stdio), with a scripted fake Evon.
# Uses the evidence ledger in data/ledger (read-only). Run from the Project folder: .venv\Scripts\python -m kavach.test_assistant
import asyncio, json, sys

sys.stdout.reconfigure(encoding="utf-8")
from kavach import assistant as A, notary as N

checks = []
def check(name, cond):
    checks.append((name, bool(cond)))
    print(("ok   " if cond else "FAIL ") + name)


records = N.Ledger().records()
if not records:
    sys.exit("the ledger is empty: seal one call first")
CALL = json.loads(records[-1].read_bytes())["call_id"]


class ScriptedEvon:
    # writes the answer from the facts it is given; the first reply is English to exercise the Telugu retry
    def __init__(self):
        self.seen = []
    def chat(self, messages, **kw):
        self.seen.append(messages[-1]["content"])
        if "Telugu script" in messages[-1]["content"]:
            return {"content": "అది మోసం కాల్. సాక్ష్యం మారలేదు."}
        return {"content": "It was a scam call. The evidence is unchanged."}


ev = ScriptedEvon()
answer, trace = asyncio.run(A.ask("అమ్మకి వచ్చిన చివరి call ఏంటి? సాక్ష్యం సరిగ్గా ఉందా?", ev, log=lambda *_: None))
tools_used = [t["tool"] for t in trace if "tool" in t]
check("assistant reaches the evidence only through MCP tools", tools_used == ["list_incidents", "get_incident", "verify_seal"])
listed = json.loads(trace[0]["result"])
check("list_incidents names the newest sealed call as the last call", listed["last_call"] == CALL
      and listed["calls_newest_first"][0]["call_id"] == CALL)
incident = json.loads(trace[1]["result"])
check("get_incident gives verdict, caller quotes and the warning", incident["verdict"] in ("SCAM", "SUSPICIOUS") and incident["evidence"]
      and "transcript" in incident)
seal = json.loads(trace[2]["result"])
check("verify_seal reports the evidence unchanged and the chain intact", seal["evidence_unchanged"] and seal["chain_intact"])
check("Evon writes from the tool results (verdict and seal facts in its prompt)", '"verdict"' in ev.seen[0] and "evidence_unchanged" in ev.seen[0])
check("call codes are not given to Evon in the facts", CALL not in ev.seen[0].split("Facts", 1)[1].split('"seal"')[0])
check("a Telugu question gets a Telugu answer (retry after English)", answer and any("ఀ" <= ch <= "౿" for ch in answer))
_, t2 = asyncio.run(A.ask("1930 కి complaint ఎలా పెట్టాలి?", ScriptedEvon(), log=lambda *_: None))
check("a complaint question also fetches the complaint draft", [t["tool"] for t in t2 if "tool" in t][-1] == "draft_complaint")
from kavach import mcp_server as S
try:
    S.get_incident("made-up-call")
    check("an unknown call is refused, not invented", False)
except ValueError:
    check("an unknown call is refused, not invented", True)
complaint = S.draft_complaint(CALL)
check("draft_complaint carries the evidence fingerprint", len(complaint["evidence_sha256"]) == 64 and "1930" in complaint["file_at"])

bad = [n for n, ok in checks if not ok]
print(f"\n{len(checks) - len(bad)}/{len(checks)} passed   (call used: {CALL}, Bitcoin: {seal['bitcoin']})")
sys.exit(1 if bad else 0)
