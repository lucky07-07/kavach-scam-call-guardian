# Agent 8's toolbox: the Kavach MCP server. After a call, any MCP client (the Evon family assistant, a bank or police
# agent, Claude Desktop) can look at the sealed evidence through these read-only tools; nothing here can change a
# verdict or a seal.
#   list_incidents   recent flagged calls
#   get_incident     what happened on one call: verdict, the caller's own words that prove it, the warning given
#   verify_seal      re-hash the evidence, walk the hash chain, check the Bitcoin proof
#   draft_complaint  the 1930 / cybercrime complaint with the evidence fingerprint for the certificate
# Run (stdio): .venv\Scripts\python -m kavach.mcp_server
import json

from mcp.server.fastmcp import FastMCP

from kavach import notary as N

mcp = FastMCP("kavach")
LEDGER = N.Ledger()

TACTIC_EN = {"money_or_fee_request": "asked for money", "otp_pin_password_request": "asked for an OTP or PIN",
             "card_or_bank_details_request": "asked for card or bank details", "remote_access_app": "asked to install a remote-access app",
             "arrest_or_legal_threat": "threatened arrest or legal action", "account_or_service_threat": "threatened to cut a service",
             "secrecy_demand": "told the listener to keep it secret", "impersonation_with_pressure": "posed as an official and pushed",
             "suspicious_link": "sent a link"}


def _packet(call_id):
    f = LEDGER.root / "packets" / f"{call_id}.json"
    if not f.exists():
        raise ValueError(f"no sealed incident called {call_id!r}; use list_incidents to see the calls")
    return json.loads(f.read_bytes())


@mcp.tool()
def list_incidents(limit: int = 10) -> dict:
    """The most recent flagged calls, newest first, and which one is the last call."""
    calls = []
    for rec in reversed(LEDGER.records()[-limit:]):
        r = json.loads(rec.read_bytes())
        p = _packet(r["call_id"])
        first = next((t["text"] for t in p["transcript"]["turns"] if t["speaker"] == "caller"), "")
        calls.append({"call_id": r["call_id"], "verdict": p["verdict"], "sealed_at": r["sealed_at"],
                      "caller_did": [TACTIC_EN.get(t, t) for t in p["tactics"]], "caller_opened_with": first[:160]})
    return {"last_call": calls[0]["call_id"] if calls else None, "calls_newest_first": calls}


@mcp.tool()
def get_incident(call_id: str) -> dict:
    """What happened on one call: verdict, the reason, each tactic with the caller's exact words, and the warning the
    listener heard. Quotes come from speech recognition, so names and amounts are 'as heard'."""
    p = _packet(call_id)
    return {"call_id": call_id, "verdict": p["verdict"], "reason": p.get("reason", ""),
            "evidence": [{"caller_did": TACTIC_EN.get(e["tactic"], e["tactic"]), "caller_said": e["quote"],
                          "found_by": "code rule" if e["source"] == "red_line" else "Evon, checked by code"} for e in p["evidence"]],
            "warning_given": p["warning"].get("text", ""),
            "transcript": [f"{'Caller' if t['speaker'] == 'caller' else 'Listener'}: {t['text']}" for t in p["transcript"]["turns"]],
            "recorded": p["created_at"]}


@mcp.tool()
def verify_seal(call_id: str) -> dict:
    """Check that a call's evidence is exactly what was sealed: re-hash it, check the hash chain, and check the
    Bitcoin timestamp (pending until a block confirms it, usually a few hours)."""
    LEDGER.upgrade()   # fetch any Bitcoin proofs that have become ready
    v = LEDGER.verify(call_id)
    stamp = v["stamp"]
    return {"call_id": call_id, "evidence_unchanged": v["packet_matches_seal"], "chain_intact": v["chain_intact"],
            "bitcoin": ({"state": "confirmed", "block": stamp["bitcoin"]["height"], "time": stamp["bitcoin"].get("time")}
                        if stamp["state"] == "confirmed" else {"state": stamp["state"]}),
            "valid": v["valid"]}


@mcp.tool()
def draft_complaint(call_id: str) -> dict:
    """The complaint draft for the 1930 helpline / cybercrime.gov.in, plus the evidence fingerprint (SHA-256) to quote
    in the electronic-evidence certificate."""
    p = _packet(call_id)
    rec = next(json.loads(r.read_bytes()) for r in LEDGER.records() if json.loads(r.read_bytes())["call_id"] == call_id)
    return {"call_id": call_id, "verdict": p["verdict"],
            "complaint": p.get("report") or "(no complaint draft was saved with this call; use get_incident for the facts)",
            "file_at": "Call 1930, or https://cybercrime.gov.in", "evidence_sha256": rec["packet_sha256"],
            "seal_index": rec["index"], "sealed_at": rec["sealed_at"]}


if __name__ == "__main__":
    mcp.run()
