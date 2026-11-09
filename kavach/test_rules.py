# Targeted verify() cases for the Kavach rules. Run: py -I kavach/test_rules.py
import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from rules import red_lines, verify

C = {r["id"]: r["transcript"] for r in map(json.loads, open(HERE.parent / "data" / "kavach_calls_44.jsonl", encoding="utf-8"))}
M, A, O, T, K = ("money_or_fee_request", "arrest_or_legal_threat", "otp_pin_password_request",
                 "account_or_service_threat", "card_or_bank_details_request")


def call(*caller):
    # a minimal transcript for the English/Hinglish cases
    return "\n".join(f"Caller: {l}" for l in caller)


CASES = [
    # (tactic, quote, transcript, expected ok?)  - Telugu cases from v3.4
    (M, "Doctor కి వెంటనే 20,000 కట్టాలి", C["grandson_emergency"], True),
    (M, "Operation కి ముందు 30,000 deposit కట్టాలి", C["son_friend_hospital"], True),
    (M, "ముందు 5,000 rupees processing fee కట్టాలి", C["lottery_fee"], True),
    (M, "అందులో 25 rupees re-delivery fee pay చేయండి", C["redelivery_fee_link"], True),
    (M, "Bonus release కావాలంటే ముందు 3,500 GST కట్టాలి", C["insurance_bonus_gst"], True),
    (M, "Card ఇంటికి పంపాను", C["wedding_reminder"], False),
    (M, "Delivery boy కి 905 rupees cash ఇవ్వండి", C["gas_delivery"], False),
    (M, "మీ పాప term fee ఈ నెల 30 లోపు కట్టాలి", C["school_fee_reminder"], False),
    (M, "Consultation fees clinic లోనే కట్టవచ్చు", C["clinic_followup"], False),
    (M, "TSSPDCL website లో లేదా దగ్గర్లోని counter లో కట్టండి", C["electricity_bill_due"], False),
    (A, "Call cut చేయకండి, ఇంట్లో ఎవరికీ చెప్పకండి, లేకపోతే ఈరోజే arrest చేస్తాం", C["cbi_video_call"], True),
    (A, "ఈ విషయం ఇంట్లో ఎవరికీ చెప్పకండి, లేకపోతే jail కి పంపిస్తాం", C["police_custody_bribe"], True),
    (O, "మీ phone కి ఇప్పుడు వచ్చిన 4 అంకెల number చెప్పండి", C["courier_address_otp"], True),
    (K, "card వెనుక ఉన్న 3 numbers చెప్పండి", C["credit_limit_cvv"], True),
    (O, "ఎవరైనా bank నుంచి అని call చేసి OTP అడిగితే చెప్పకు", C["daughter_otp_warning"], False),
    (O, "మేము మిమ్మల్ని OTP లేదా PIN అడగము", C["fraud_alert"], False),
    (T, "సరే, మీ card ని మేము temporary గా block చేశాం", C["fraud_alert"], False),
    (T, "ఈ రాత్రి 9:30 కి మీ power connection cut చేస్తాం", C["power_cut_upi"], True),
    (K, "ఏదైనా సందేహం ఉంటే card వెనుక ఉన్న number కి call చేయండి", C["card_delivery"], False),
    (K, "ఎవరికీ phone లో details ఇవ్వకండి", C["electricity_bill_due"], False),
    ("secrecy_demand", "నేను పంపే number కి Google Pay లో పంపు, ప్లీజ్ ఎవరికీ చెప్పకు", C["grandson_emergency"], True),
]
EN = [
    # English / Hinglish requests (romanized Hindi, as ICFD-31k and Prisma write it)
    (O, "Aapke phone pe ek OTP aaya hoga, woh mujhe bataiye"),
    (O, "Please read out the 6 digit OTP you just received"),
    (M, "Abhi 2,000 rupees is UPI ID pe bhej dijiye"),
    (M, "You can pay using Ola Money to my ID"),
    (M, "We need you to accept a UPI request for ₹1"),
    (K, "Please confirm your card number, expiry date and CVV"),
    (A, "If you don't pay within 24 hours, we will morph these photos and send them to your family"),
    (A, "Warna aapke khilaf FIR darj hogi aur aapko giraftar kiya jayega"),
    (T, "Aaj raat aapka connection kaat diya jayega"),
    ("secrecy_demand", "Yeh baat ghar mein kisi ko mat batana"),
]
EN_NOT = [
    # English / Hinglish lines that must not verify
    (O, "We will never ask for your OTP or PIN"),
    (O, "Kisi ko bhi apna OTP mat bataiye"),
    (M, "You can pay through our official app or website, or visit a store"),
    (M, "Your payment has been noted, you will receive a confirmation shortly"),
    (K, "I will send you the details of the plan via email"),
    (K, "Please don't share your card details with anyone"),
    (A, "Term insurance protects your family in case something unfortunate happens"),
    (M, "Paise ki zarurat nahi hai, sirf Aadhaar lekar branch aaiye"),
]
CASES += [(t, q, call(q, "You can do it online."), True) for t, q in EN]
CASES += [(t, q, call(q, "You can do it online."), False) for t, q in EN_NOT]

bad = 0
for tactic, quote, transcript, expected in CASES:
    got = verify(tactic, quote, transcript)
    ok = (got == "ok") == expected
    bad += not ok
    if not ok:
        print(f"FAIL {tactic[:14]:14s} got {got!r:28s} expected {'ok' if expected else 'rejected'}: {quote}")
red = {i: [e["tactic"][:6] for e in red_lines(t)] for i, t in C.items() if red_lines(t)}
expected_red = {"remote_access", "army_qr", "meter_apk", "refund_qr", "wrong_transfer_collect", "screen_share_bank"}
if set(red) != expected_red:
    bad += 1
    print("FAIL red lines fired on", sorted(red))
print(f"{len(CASES) - bad + (set(red) == expected_red)}/{len(CASES) + 1} passed")
sys.exit(1 if bad else 0)
