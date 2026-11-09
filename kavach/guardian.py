# Agent 5, Guardian: the spoken warning for the listener, in the listener's language (Telugu or Hindi).
# Evon writes the warning from the verdict and the verified tactics only (never from the transcript); code then checks it
# before anything is spoken. If Evon's text fails a check, a fixed, pre-approved warning for the same tactics is spoken
# instead, so the listener always hears something safe. SAFE calls stay silent.
# Timbre speaks it slowly in a gentle voice; the audio is cached per sentence.
import re

from kavach.rules import REQUEST_OR_THREAT, _norm, caller_text
from kavach.timbre import Timbre, wav_of

SPEED, RATE, MAX_CHARS = 0.9, 16000, 220
# most dangerous first: at most two signs are named, so the warning stays short enough to hear in one breath
PRIORITY = ["otp_pin_password_request", "card_or_bank_details_request", "money_or_fee_request", "remote_access_app",
            "arrest_or_legal_threat", "account_or_service_threat", "secrecy_demand", "impersonation_with_pressure", "suspicious_link"]

LANGS = {
    "te": {
        "name": "Telugu", "script": ("ఀ", "౿"), "voice": "Lehara", "model": "timbre-v2.5", "tts": "te-IN",   # "gentle, reassuring"
        "tactic": {"money_or_fee_request": "డబ్బులు అడుగుతున్నారు", "otp_pin_password_request": "OTP లేదా PIN అడుగుతున్నారు",
                   "card_or_bank_details_request": "card లేదా bank వివరాలు అడుగుతున్నారు", "remote_access_app": "phone లో app వేయమంటున్నారు",
                   "arrest_or_legal_threat": "arrest చేస్తామని భయపెడుతున్నారు", "account_or_service_threat": "account లేదా connection ఆపేస్తామని భయపెడుతున్నారు",
                   "secrecy_demand": "ఎవరికీ చెప్పొద్దంటున్నారు", "impersonation_with_pressure": "అధికారులమని చెప్పి తొందర పెడుతున్నారు",
                   "suspicious_link": "link పంపుతున్నారు"},
        # the threatened service, read from the verified quote, so the warning does not say "account" for a power cut
        "service": [(r"power|current|electric|కరెంట్|meter|connection", "కరెంట్ connection కట్ చేస్తామని భయపెడుతున్నారు"),
                    (r"\bsim\b|number deactivat", "SIM ఆపేస్తామని భయపెడుతున్నారు"),
                    (r"account|card|kyc", "bank account ఆపేస్తామని భయపెడుతున్నారు")],
        "template": {"SCAM": "జాగ్రత్త! ఇది మోసం కాల్. {signs}. OTP, PIN ఎవరికీ చెప్పకండి, డబ్బులు పంపకండి. వెంటనే ఫోన్ పెట్టేయండి.",
                     "SUSPICIOUS": "జాగ్రత్త, ఈ కాల్ అనుమానంగా ఉంది. {signs}. ఏ వివరాలూ చెప్పకండి. ముందు ఇంట్లో వాళ్ళతో మాట్లాడండి."},
        "vague": "అనుమానంగా ఉంది",
        "example": ("Verdict: SCAM. Signs: OTP లేదా PIN అడుగుతున్నారు", "జాగ్రత్త, ఇది మోసం కాల్. OTP ఎవరికీ చెప్పకండి, వెంటనే ఫోన్ పెట్టేయండి."),
        "common": "OTP, bank, app, phone"},
    "hi": {
        "name": "Hindi", "script": ("ऀ", "ॿ"), "voice": "Yashvi", "model": "timbre-v2.5", "tts": "hi-IN",    # "gentle, reassuring"
        "tactic": {"money_or_fee_request": "पैसे माँग रहे हैं", "otp_pin_password_request": "OTP या PIN माँग रहे हैं",
                   "card_or_bank_details_request": "card या bank की जानकारी माँग रहे हैं", "remote_access_app": "phone में app डलवा रहे हैं",
                   "arrest_or_legal_threat": "गिरफ़्तारी की धमकी दे रहे हैं", "account_or_service_threat": "account या connection बंद करने की धमकी दे रहे हैं",
                   "secrecy_demand": "किसी को न बताने को कह रहे हैं", "impersonation_with_pressure": "अफ़सर बनकर जल्दी करवा रहे हैं",
                   "suspicious_link": "link भेज रहे हैं"},
        "service": [(r"power|current|electric|bijli|meter|connection", "बिजली का connection काटने की धमकी दे रहे हैं"),
                    (r"\bsim\b|number deactivat", "SIM बंद करने की धमकी दे रहे हैं"),
                    (r"account|card|kyc", "bank account बंद करने की धमकी दे रहे हैं")],
        "template": {"SCAM": "सावधान! यह धोखाधड़ी वाली कॉल है। {signs}। OTP, PIN किसी को मत बताइए, पैसे मत भेजिए। अभी फ़ोन काट दीजिए।",
                     "SUSPICIOUS": "सावधान, यह कॉल संदिग्ध है। {signs}। कोई जानकारी मत दीजिए। पहले घर वालों से बात कीजिए।"},
        "vague": "कुछ गड़बड़ लग रहा है",
        "example": ("Verdict: SCAM. Signs: OTP या PIN माँग रहे हैं", "सावधान, यह धोखाधड़ी वाली कॉल है। OTP किसी को मत बताइए, अभी फ़ोन काट दीजिए।"),
        "common": "OTP, bank, app, phone"},
}
# Telugu stays the default everywhere; these names are kept for callers written before Hindi was added
VOICE, MODEL, LANG = LANGS["te"]["voice"], LANGS["te"]["model"], LANGS["te"]["tts"]
TACTIC_TE, SERVICE_TE, TEMPLATE = LANGS["te"]["tactic"], LANGS["te"]["service"], LANGS["te"]["template"]


def lang_of(call_language):
    # the warning follows the call: a Hindi/Hinglish call is warned about in Hindi, everything else in Telugu
    return "hi" if str(call_language or "").lower().startswith("hi") else "te"


def threat_hint(evidence, lang="te"):
    L = LANGS[lang]
    q = " ".join(_norm(e["quote"]) for e in evidence if e["tactic"] == "account_or_service_threat")
    return next((text for pat, text in L["service"] if re.search(pat, q)), L["tactic"]["account_or_service_threat"])


def signs(tactics, evidence=(), n=2, lang="te"):
    L = LANGS[lang]
    named = [t for t in PRIORITY if t in tactics][:n]
    return ", ".join(threat_hint(evidence, lang) if t == "account_or_service_threat" else L["tactic"][t] for t in named)


def template(verdict, tactics, evidence=(), lang="te"):
    L = LANGS[lang]
    return L["template"][verdict].format(signs=signs(tactics, evidence, lang=lang) or L["vague"])


def evon_prompt(verdict, tactics, evidence=(), lang="te"):
    # the transcript is deliberately not in the prompt, so the warning cannot repeat the caller
    L = LANGS[lang]
    script = "Telugu script" if lang == "te" else "Devanagari"
    return [{"role": "system", "content": f"You write one short spoken warning in simple {L['name']} ({script}) for an elderly listener. "
             f"English words common in {L['name']} speech ({L['common']}) may stay in English. Never repeat what the caller said. "
             "No numbers, no names, no links. At most two sentences."},
            {"role": "user", "content": L["example"][0]},
            {"role": "assistant", "content": L["example"][1]},
            {"role": "user", "content": f"Verdict: {verdict}. Signs: {signs(tactics, evidence, n=3, lang=lang) or L['vague']}"}]


def script_ratio(s, lang="te"):
    lo, hi = LANGS[lang]["script"]
    letters = [c for c in s if c.isalpha()]
    return round(sum(lo <= c <= hi for c in letters) / max(len(letters), 1), 2)


def telugu_ratio(s):
    return script_ratio(s, "te")


def echoes(text, call, n=3):
    grams = lambda s: {tuple(w[i:i + n]) for w in [_norm(s).split()] for i in range(len(w) - n + 1)}
    return bool(grams(text) & grams(caller_text(call)))


def problems(text, call, lang="te"):
    # why Evon's warning cannot be spoken; empty list = safe to speak
    out = []
    if not text.strip():
        out.append("empty")
    if script_ratio(text, lang) < 0.6:
        out.append(f"not mostly {LANGS[lang]['name']}")
    if echoes(text, call):
        out.append("repeats the caller")
    if re.search(r"\d", text):
        out.append("contains a number")        # amounts, phone numbers and codes can only have come from the call
    if re.search(r"https?:|www\.|\.com|\.in\b", text, re.I):
        out.append("contains a link")
    if len(text) > MAX_CHARS:
        out.append("too long")
    return out


def choose(verdict, tactics, evidence, call, evon_text=None, lang="te"):
    # -> {"text", "source": evon|template|silent, "rejected": [reasons], "lang"}
    if verdict == "SAFE":
        return {"text": "", "source": "silent", "rejected": [], "lang": lang}
    if evon_text is not None:
        why = problems(evon_text, call, lang)
        if not why:
            return {"text": evon_text.strip(), "source": "evon", "rejected": [], "lang": lang}
        return {"text": template(verdict, tactics, evidence, lang), "source": "template", "rejected": why, "lang": lang}
    return {"text": template(verdict, tactics, evidence, lang), "source": "template", "rejected": [], "lang": lang}


def speak(text, tts=None, lang="te"):
    # -> WAV bytes (16 kHz mono) or None for silence
    if not text:
        return None
    L = LANGS[lang]
    return wav_of((tts or Timbre()).speak(text, L["voice"], L["model"], L["tts"], RATE, SPEED), RATE)
