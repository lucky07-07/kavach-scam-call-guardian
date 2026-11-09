# Agent 8, Family assistant: after the call, the family asks in their own language ("అమ్మకి నిన్న వచ్చిన call ఏంటి?")
# and Evon answers from the sealed evidence. Evon reaches the evidence only through the Kavach MCP server.
# ask(): code plans the MCP lookups and Evon writes the answer from the results, so every fact is grounded.
# ask_agentic(): Evon picks each tool itself through grammar-forced JSON; kept as an experiment because in real-Evon
# tests it mixed up calls and facts (Gnani marks Evon's tool calling as still in development).
# Every tool is read-only, so the assistant can explain and verify, but never change a verdict or a seal.
# CLI: .venv\Scripts\python -m kavach.assistant "అమ్మకి నిన్న వచ్చిన call ఏంటి?"
import asyncio, json, re, sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kavach import evon as E

MAX_STEPS = 5
SYSTEM = ("You are Kavach's family assistant. A scam-call guard has already judged and sealed the calls; you help the family "
          "understand what happened, check that the evidence is intact, and file a complaint. Use the tools to look things up; "
          "never guess a fact a tool can give you. How to work: call list_incidents first; 'the last call' is its last_call "
          "field; call get_incident on the call you talk about before stating its verdict or what "
          "the caller did; call verify_seal when asked whether evidence is intact or changed; call draft_complaint only when "
          "asked how to complain. Then answer: start with the direct answer (scam or not; intact or changed), then the "
          "caller's key demand, simply and kindly, in at most four sentences. Answer in the same language and script as the "
          "question. Never mention call_id codes: describe a call by who the caller claimed to be and what they asked for. "
          "Say amounts and names are 'as heard'. Never tell anyone to share an OTP or PIN.")


def _telugu(s):
    return any("ఀ" <= ch <= "౿" for ch in s)


def step_schema(tools):
    return {"type": "object", "properties": {
        "action": {"enum": tools + ["answer"]},
        "call_id": {"type": "string"},
        "answer": {"type": "string"}}, "required": ["action", "call_id", "answer"]}


async def ask_agentic(question, evon=None, server_cmd=None, log=print):
    # experimental: Evon chooses each tool itself. In the 8 Nov tests it mixed up calls and facts, so ask() below is the default
    evon = evon or E.Evon()
    params = StdioServerParameters(command=server_cmd[0] if server_cmd else sys.executable,
                                   args=server_cmd[1:] if server_cmd else ["-m", "kavach.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            names = [t.name for t in tools]
            catalogue = "\n".join(f"- {t.name}({', '.join(t.inputSchema.get('properties', {}))}): {t.description}" for t in tools)
            history = [{"role": "system", "content": SYSTEM + "\n\nTools:\n" + catalogue + "\n\nEach turn, reply with JSON: "
                        "action = a tool name (with call_id when the tool needs one, else \"\") or \"answer\" (with the final answer)."},
                       {"role": "user", "content": question}]
            trace = []

            def finish(answer):
                # a Telugu question gets a Telugu answer. Evon writes Telugu well as free text (as in the Guardian's
                # warnings) but tends to English inside the JSON format, so the rewrite is a plain chat request
                if _telugu(question) and not _telugu(answer):
                    te = evon.chat([{"role": "system", "content": "Rewrite the message in simple, kind Telugu (Telugu script) for an "
                                     "elderly person's family. Keep words like OTP, PIN, bank, call in English. Same facts, nothing added."},
                                    {"role": "user", "content": answer}], max_tokens=400, temperature=0.2)["content"].strip()
                    answer = te if _telugu(te) else answer
                trace.append({"answer": answer})
                return answer, trace

            for step in range(MAX_STEPS):
                # the first step must be a tool: an answer has to rest on what the tools returned, never on a guess
                allowed = names if step == 0 else names + ["answer"]
                choice = evon.json(history, step_schema(names) if step else
                                   {**step_schema(names), "properties": {**step_schema(names)["properties"], "action": {"enum": allowed}}},
                                   max_tokens=500, temperature=0.2) or {"action": "answer", "answer": "", "call_id": ""}
                if choice["action"] == "answer" and choice.get("answer", "").strip():
                    return finish(choice["answer"])
                if choice["action"] not in names:
                    break
                args = {"call_id": choice["call_id"]} if "call_id" in tools[names.index(choice["action"])].inputSchema.get("properties", {}) else {}
                res = await session.call_tool(choice["action"], args)
                text = "\n".join(c.text for c in res.content if getattr(c, "text", None))
                log(f"  -> {choice['action']}({args.get('call_id', '')})")
                trace.append({"tool": choice["action"], "args": args, "result": text})
                history += [{"role": "assistant", "content": json.dumps({"action": choice["action"], "call_id": args.get("call_id", "")})},
                            {"role": "user", "content": f"Tool result:\n{text[:4000]}\n\nNow call another tool or give the answer."}]
            # out of steps: ask for the answer with what was found
            history.append({"role": "user", "content": "Give the final answer now."})
            final = evon.json(history, step_schema(["answer"]), max_tokens=400, temperature=0.2) or {}
            return finish(final.get("answer", ""))


COMPLAINT = re.compile(r"complain|complaint|1930|report|cyber|ఫిర్యాదు|కంప్లైంట్|complaint", re.I)
ANSWER = ("You are Kavach's family assistant. Answer the family's question using ONLY the facts given, which come from "
          "Kavach's sealed evidence. Start with the direct answer (scam or not; evidence unchanged or not). Say who the caller "
          "claimed to be and what they demanded, from the caller's own words. When the question is about the evidence, say "
          "whether it is unchanged and whether the Bitcoin timestamp is confirmed (with the block number) or still pending. "
          "When it is about complaining, say: call 1930 or file at cybercrime.gov.in, and quote the first 12 characters of the "
          "evidence fingerprint. Never mention call_id codes. Names and amounts are 'as heard'. Never ask anyone to share an "
          "OTP or PIN. Reply in the same language and script as the question (keep words like OTP, PIN, bank, call in English), "
          "simply and kindly, in at most four sentences.")


async def ask(question, evon=None, server_cmd=None, log=print):
    # Code plans the lookups over MCP (which call; then incident, seal, and the complaint when asked), and Evon writes
    # the answer from exactly those results. Every fact in the answer therefore comes from a tool result.
    evon = evon or E.Evon()
    params = StdioServerParameters(command=server_cmd[0] if server_cmd else sys.executable,
                                   args=server_cmd[1:] if server_cmd else ["-m", "kavach.mcp_server"])
    trace = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def tool(name, **args):
                res = await session.call_tool(name, args)
                text = "\n".join(c.text for c in res.content if getattr(c, "text", None))
                log(f"  -> {name}({args.get('call_id', '')})")
                trace.append({"tool": name, "args": args, "result": text})
                return json.loads(text) if not res.isError else {"error": text}

            listing = await tool("list_incidents")
            call_id = listing.get("last_call")
            if not call_id:
                answer = "కాల్స్ ఏవీ ఇంకా సీల్ కాలేదు." if _telugu(question) else "No flagged calls have been sealed yet."
                trace.append({"answer": answer})
                return answer, trace
            facts = {"incident": await tool("get_incident", call_id=call_id), "seal": await tool("verify_seal", call_id=call_id)}
            if COMPLAINT.search(question):
                facts["complaint"] = await tool("draft_complaint", call_id=call_id)
            facts["incident"].pop("transcript", None)   # the evidence quotes are enough, and keep the prompt short
            facts["incident"].pop("call_id", None)
    msgs = [{"role": "system", "content": ANSWER},
            {"role": "user", "content": f"Question: {question}\n\nFacts (JSON):\n{json.dumps(facts, ensure_ascii=False)[:6000]}"}]
    answer = evon.chat(msgs, max_tokens=400, temperature=0.2)["content"].strip()
    from kavach.guardian import telugu_ratio
    if _telugu(question) and telugu_ratio(answer) < 0.6:
        # mostly Telugu, as for the spoken warning: a separate rewrite with an example (asked again in the same
        # conversation, Evon kept its mixed wording), and if that also fails, a fixed Telugu answer from the facts
        te = evon.chat([{"role": "system", "content": "Rewrite the message in simple Telugu (Telugu script) for an elderly person's "
                         "family. Words like OTP, PIN, bank, call may stay in English. Same facts, nothing added."},
                        {"role": "user", "content": "The last call was a scam. The evidence is unchanged."},
                        {"role": "assistant", "content": "చివరి కాల్ మోసం కాల్. సాక్ష్యం ఏమాత్రం మారలేదు."},
                        {"role": "user", "content": answer}], max_tokens=400, temperature=0.2)["content"].strip()
        answer, source = (te, "evon") if telugu_ratio(te) >= 0.6 else (fixed_telugu(facts), "fixed")
    else:
        source = "evon"
    trace.append({"answer": answer, "source": source})
    return answer, trace


def fixed_telugu(facts):
    inc, seal = facts["incident"], facts["seal"]
    verdict = {"SCAM": "మోసం కాల్", "SUSPICIOUS": "అనుమానాస్పద కాల్"}.get(inc.get("verdict"), "సాధారణ కాల్")
    did = {"asked for an OTP or PIN": "OTP లేదా PIN అడిగారు", "asked for money": "డబ్బులు అడిగారు",
           "threatened arrest or legal action": "arrest చేస్తామని భయపెట్టారు", "threatened to cut a service": "account ఆపేస్తామని భయపెట్టారు",
           "asked for card or bank details": "card లేదా bank వివరాలు అడిగారు"}
    demands = ", ".join(dict.fromkeys(did[e["caller_did"]] for e in inc.get("evidence", []) if e["caller_did"] in did))
    state = seal.get("bitcoin", {}).get("state")
    stamp = "Bitcoin లో నమోదు అయింది" if state == "confirmed" else "Bitcoin లో నమోదు కోసం వేచి ఉంది"
    intact = "సాక్ష్యం ఏమాత్రం మారలేదు" if seal.get("evidence_unchanged") else "సాక్ష్యం మారింది, జాగ్రత్త"
    return f"చివరి కాల్ {verdict}.{' Caller ' + demands + '.' if demands else ''} {intact}; {stamp}."


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    q = " ".join(sys.argv[1:]) or "What happened on the last flagged call, and is the evidence intact?"
    answer, _ = asyncio.run(ask(q))
    print("\n" + answer)
