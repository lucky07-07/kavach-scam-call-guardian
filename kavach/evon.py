# Evon v3.3 (Q4_K_M under llama-server on Kaggle) and the Kavach roles that use it. Prompts are the v3.4 ones from
# evon/kavach_prompt_iterations_2026-10-25.md; thinking stays off. Every structured answer is grammar-forced JSON.
#   punctuate  - Listener post-processing: Prisma returns no punctuation, the rules judge clause by clause
#   prosecutor - checklist of scam tactics, each yes with the caller's exact words
#   defender   - signs the call is genuine, with quotes
#   explainer  - one sentence for the family
#   reporter   - 1930 / cybercrime complaint draft
# The verdict is never Evon's: kavach.rules decides from the evidence the code has verified.
import json, os, re, time
from pathlib import Path

import requests

from kavach.rules import TACTICS

SYS = ("You analyse phone-call transcripts for Kavach, which helps elderly Telugu speakers. "
       "Most calls people receive are genuine. Judge only from what the transcript actually says, and quote lines exactly.")
TACTIC_TEXT = {
 "money_or_fee_request":          "the caller asks the listener to pay, send, give or transfer money, a fee, a fine or a deposit, to the caller or to anyone they name (a doctor, a hospital, an account)",
 "otp_pin_password_request":      "the caller asks the listener to tell them an OTP, PIN, password or a code from an SMS or app, or to enter their UPI PIN (for example to 'receive' money or a refund)",
 "card_or_bank_details_request":  "the caller asks for card number, account number, IFSC, CVV or other bank details",
 "remote_access_app":             "the caller asks the listener to install or open an app like AnyDesk or TeamViewer, share their screen, or scan a QR code",
 "arrest_or_legal_threat":        "the caller threatens arrest, a police case, a warrant or legal action",
 "account_or_service_threat":     "the caller threatens to block an account, cut power, deactivate a SIM or cancel something unless the listener acts now",
 "secrecy_demand":                "the caller tells the listener not to tell family, the bank or anyone else",
 "impersonation_with_pressure":   "the caller claims to be police, customs, a court, RBI, tax or other officials and pushes the listener to act immediately",
 "suspicious_link":               "the caller sends or asks the listener to open a link"}
assert set(TACTIC_TEXT) == set(TACTICS)

PRO_SCHEMA = {"type": "object", "properties": {t: {"type": "object", "properties": {
    "present": {"type": "boolean"}, "quote": {"type": "string"}}, "required": ["present", "quote"]} for t in TACTIC_TEXT},
    "required": list(TACTIC_TEXT)}
DEF_SCHEMA = {"type": "object", "properties": {"benign_signals": {"type": "array", "items": {"type": "object", "properties": {
    "signal": {"type": "string"}, "quote": {"type": "string"}}, "required": ["signal", "quote"]}}}, "required": ["benign_signals"]}
REASON_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}


def punct_schema(n):
    return {"type": "object", "properties": {"turns": {"type": "array", "items": {"type": "string"}, "minItems": n, "maxItems": n}},
            "required": ["turns"]}


ENV_FILE = Path(__file__).parent.parent / "evon.env"   # written by hand from the Kaggle notebook's last output


def _env(name):
    if os.environ.get(name):
        return os.environ[name].strip()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            k, eq, v = line.partition("=")
            if eq and k.strip() == name:
                return v.strip().strip("'\"")
    return None


class Evon:
    def __init__(self, url=None, api_key=None, session=None, timeout=300):
        # url: the Kaggle tunnel address (KAVACH_EVON_URL, or Project/evon.env); the key is sent as a Bearer token
        self.url = (url or _env("KAVACH_EVON_URL") or "http://127.0.0.1:8080").rstrip("/")
        self.key = api_key or _env("KAVACH_EVON_KEY")
        self.http = session or requests.Session()
        self.timeout = timeout

    def health(self):
        try:
            r = self.http.get(f"{self.url}/health", headers={"Authorization": f"Bearer {self.key}"} if self.key else {}, timeout=15)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def chat(self, messages, max_tokens=512, schema=None, temperature=0.3):
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                "chat_template_kwargs": {"enable_thinking": False}, "cache_prompt": True}
        if schema:
            body["response_format"] = {"type": "json_object", "schema": schema}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        t = time.time()
        r = self.http.post(f"{self.url}/v1/chat/completions", json=body, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        return {"content": j["choices"][0]["message"].get("content") or "", "seconds": round(time.time() - t, 2)}

    def json(self, messages, schema, max_tokens=600, temperature=0.1):
        try:
            return json.loads(self.chat(messages, max_tokens, schema, temperature)["content"])
        except (json.JSONDecodeError, KeyError):
            return None


# ---- prompts (v3.4) -------------------------------------------------------------------------------------------

def prosecutor(call):
    checklist = "\n".join(f"- {t}: {d}" for t, d in TACTIC_TEXT.items())
    return [{"role": "system", "content": SYS}, {"role": "user", "content":
        f"Transcript:\n{call}\n\nFor each item, answer whether the CALLER does it in this call:\n{checklist}\n\n"
        "present=true only if a caller line does it; then copy that line exactly into quote. Otherwise present=false and quote=\"\". "
        "Saying they will never ask for OTP/PIN, telling the listener not to share details on the phone, pointing to the official number, "
        "branch or app, and cash payment on delivery of an order are all present=false. Most calls have every item false."}]


def defender(call):
    return [{"role": "system", "content": SYS}, {"role": "user", "content":
        f"Transcript:\n{call}\n\nList the signs that this call is genuine, each with an exact caller quote: for example the caller only gives "
        "information, says they will not ask for OTP/PIN, sends the listener to an official number, branch or app, or the call is about "
        "something the listener expects. Use an empty list if there are none."}]


def explainer(call, verdict, evidence, benign):
    return [{"role": "system", "content": SYS}, {"role": "user", "content":
        f"Transcript:\n{call}\n\nVerdict: {verdict}\nVerified scam evidence: {json.dumps(evidence, ensure_ascii=False)}\n"
        f"Genuine signals: {json.dumps(benign, ensure_ascii=False)}\n\nIn one English sentence, explain this verdict to the listener's family."}]


REPORT_SCHEMA = {"type": "object", "properties": {
    "caller_claimed_to_be": {"type": "string"}, "caller_demanded": {"type": "string"},
    "complaint_english": {"type": "string"}, "summary_telugu": {"type": "string"}},
    "required": ["caller_claimed_to_be", "caller_demanded", "complaint_english", "summary_telugu"]}


def reporter(call, verdict, tactics, evidence=()):
    # fields, not free text: in free text Evon continued long transcripts instead of summarising them
    quotes = "\n".join(f"- {e['tactic']}: \"{e['quote']}\"" for e in evidence)
    return [{"role": "system", "content": SYS}, {"role": "user", "content":
        f"Transcript:\n{call}\n\nVerdict: {verdict}; tactics: {', '.join(tactics)}.\nVerified caller lines:\n{quotes}\n\n"
        f"Fill in a complaint the family can file on the 1930 helpline / cybercrime.gov.in. Today is {time.strftime('%d %B %Y')}. "
        "caller_claimed_to_be: who the caller said they were (organisation and role). caller_demanded: what they asked the "
        "listener to do or give. complaint_english: 3 to 4 sentences, first person from the family: on today's date (write it "
        "exactly as given) a caller claimed..., demanded..., and why it is a scam. Do not say what the listener did or did not "
        "do. Names and amounts come from speech recognition, so write them as 'as heard: ...'. summary_telugu: the same in 2 "
        "short sentences in Telugu script. Do not copy the transcript."}]


def complaint_text(fields):
    # the complaint as filed, assembled in code from Evon's fields
    if not fields:
        return ""
    return (f"Caller claimed to be: {fields['caller_claimed_to_be']}\nCaller demanded: {fields['caller_demanded']}\n\n"
            f"{fields['complaint_english']}\n\n{fields['summary_telugu']}").strip()


def punctuator(turns):
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(turns))
    return [{"role": "system", "content": "You restore punctuation in speech-recognition output. Add commas, full stops and question marks "
             "where a speaker would pause, and capitalise sentence starts. Never add, remove, translate, correct or reorder a word, "
             "even if it looks misheard."},
            {"role": "user", "content": f"Return the {len(turns)} lines below in the same order, each with punctuation restored.\n\n{numbered}"}]


# ---- punctuation, checked ----------------------------------------------------------------------------------

def _words(s):
    # Telugu vowel signs are not \w in Python, so the Telugu block is kept explicitly (as in rules._norm)
    return re.sub(r"[^\wఀ-౿\s]", " ", s.lower()).split()


def punctuate(transcript, evon):
    # Evon only adds punctuation; a turn whose words changed in any way keeps Prisma's text, and the transcript says so
    turns = [t["text"] for t in transcript["turns"]]
    if not turns or transcript["source"] == "text":
        return transcript
    out = evon.json(punctuator(turns), punct_schema(len(turns)), max_tokens=40 + 3 * sum(len(t) for t in turns) // 4)
    new = (out or {}).get("turns") or []
    fixed, kept = [], 0
    for i, t in enumerate(transcript["turns"]):
        cand = new[i] if i < len(new) and isinstance(new[i], str) else ""
        if cand and _words(cand) == _words(t["text"]):
            fixed.append(dict(t, text=cand.strip()))
        else:
            fixed.append(t)
            kept += 1
    warnings = list(transcript.get("warnings", []))
    if kept:
        warnings.append(f"punctuation not restored on {kept} of {len(turns)} turns (Evon changed words); rules read Prisma's text there")
    return dict(transcript, turns=fixed, warnings=warnings)
