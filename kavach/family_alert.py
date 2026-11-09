# Part of agent 5, Guardian: the moment a call is judged SCAM or SUSPICIOUS, the family is alerted too, so someone can
# call the listener back while it still matters. The message is built in code from the verdict and the verified tactics
# only (never from the transcript), so it cannot repeat the caller, and it is in the family's language (Telugu or Hindi)
# with an English line for the screen. Timbre voices it as a voice note. SAFE calls send nothing.
# Delivery: alerts are queued in data/alerts/outbox.jsonl, ready for an SMS/WhatsApp gateway; no gateway is connected yet.
import json, re
from datetime import datetime, timezone
from pathlib import Path

from kavach.guardian import LANGS, PRIORITY, speak, threat_hint
from kavach.rules import _norm

OUTBOX = Path(__file__).parent.parent / "data" / "alerts" / "outbox.jsonl"
TEXT = {
    "te": {"SCAM": "అత్యవసరం: అమ్మకి ఇప్పుడే మోసం కాల్ వచ్చింది. కాల్ చేసినవాళ్ళు {signs}. Kavach అమ్మని హెచ్చరించింది, సాక్ష్యం భద్రపరిచింది. వెంటనే అమ్మకి ఫోన్ చేయండి.",
           "SUSPICIOUS": "అమ్మకి ఒక అనుమానాస్పద కాల్ వచ్చింది. కాల్ చేసినవాళ్ళు {signs}. Kavach అమ్మని హెచ్చరించింది. ఒకసారి అమ్మతో మాట్లాడండి."},
    "hi": {"SCAM": "ज़रूरी: माँ को अभी एक धोखाधड़ी वाली कॉल आई। कॉल करने वाले {signs}। Kavach ने माँ को सावधान किया और सबूत सुरक्षित किया। तुरंत माँ को फ़ोन कीजिए।",
           "SUSPICIOUS": "माँ को एक संदिग्ध कॉल आई। कॉल करने वाले {signs}। Kavach ने माँ को सावधान किया। एक बार माँ से बात कर लीजिए।"},
}
ENGLISH = {"money_or_fee_request": "asked for money", "otp_pin_password_request": "asked for her OTP or PIN",
           "card_or_bank_details_request": "asked for card or bank details", "remote_access_app": "asked her to install an app",
           "arrest_or_legal_threat": "threatened arrest", "account_or_service_threat": "threatened to cut off a service",
           "secrecy_demand": "told her to keep it secret", "impersonation_with_pressure": "posed as an official and rushed her",
           "suspicious_link": "sent a link"}


def threat_english(evidence):
    # the threatened service in English, read the same way as the Telugu warning (power, SIM, else the bank account)
    q = " ".join(_norm(e["quote"]) for e in evidence if e["tactic"] == "account_or_service_threat")
    for (pat, _), text in zip(LANGS["te"]["service"], ["threatened to cut her power", "threatened to block her SIM",
                                                        "threatened to block her bank account"]):
        if re.search(pat, q):
            return text
    return ENGLISH["account_or_service_threat"]


def build(verdict, tactics, evidence=(), lang="te", seal_index=None):
    # -> the alert, or {"send": False} for a SAFE call
    if verdict == "SAFE":
        return {"send": False}
    named = [t for t in PRIORITY if t in tactics][:2]
    signs = ", ".join(threat_hint(evidence, lang) if t == "account_or_service_threat" else LANGS[lang]["tactic"][t] for t in named) \
        or LANGS[lang]["vague"]
    english = " and ".join(threat_english(evidence) if t == "account_or_service_threat" else ENGLISH[t] for t in named) \
        or "behaved suspiciously"
    urgent = verdict == "SCAM"
    gloss = (f"Urgent: Amma just got a scam call. The caller {english}. Kavach warned her and sealed the evidence. Call her now."
             if urgent else f"Amma got a suspicious call. The caller {english}. Kavach warned her. Please check on her.")
    return {"send": True, "level": "urgent" if urgent else "check", "lang": lang, "text": TEXT[lang][verdict].format(signs=signs),
            "english": gloss, "seal_index": seal_index, "delivery": "queued: no SMS/WhatsApp gateway connected yet"}


def voice(alert, tts=None):
    # -> WAV bytes of the alert as a voice note (the Guardian's Timbre voice), or None
    return speak(alert["text"], tts, alert["lang"]) if alert.get("send") else None


def queue(alert, call_id, outbox=OUTBOX):
    # append to the outbox a delivery gateway would read; returns the queued record
    if not alert.get("send"):
        return None
    rec = {"call_id": call_id, "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **alert}
    outbox.parent.mkdir(parents=True, exist_ok=True)
    with open(outbox, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
