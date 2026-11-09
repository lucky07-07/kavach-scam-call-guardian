# Kavach detection rules (v3.4), shared by the app, the Kaggle notebooks and the offline tests.
# Evon proposes tactics with a caller quote; this code keeps a claim only if the quote is the caller's own words,
# carries a cue for the tactic and is not negated; red lines fire on caller lines whatever Evon says; decide() is the verdict.
import re

try:
    from kavach.loanwords import latinise
except ImportError:   # run as a plain script from the kavach folder
    from loanwords import latinise

TACTICS = {
 "money_or_fee_request":          "the caller asks the listener to pay, send, give or transfer money, a fee, a fine or a deposit, to the caller or to anyone they name (a doctor, a hospital, an account)",
 "otp_pin_password_request":      "the caller asks the listener to tell them an OTP, PIN, password or a code from an SMS or app, or to enter their UPI PIN (for example to 'receive' money or a refund)",
 "card_or_bank_details_request":  "the caller asks for card number, account number, IFSC, CVV or other bank details",
 "remote_access_app":             "the caller asks the listener to install or open an app like AnyDesk or TeamViewer, share their screen, or scan a QR code",
 "arrest_or_legal_threat":        "the caller threatens arrest, a police case, a warrant or legal action",
 "account_or_service_threat":     "the caller threatens to block an account, cut power, deactivate a SIM or cancel something unless the listener acts now",
 "secrecy_demand":                "the caller tells the listener not to tell family, the bank or anyone else",
 "impersonation_with_pressure":   "the caller claims to be police, customs, a court, RBI, tax or other officials and pushes the listener to act immediately",
 "suspicious_link":               "the caller sends or asks the listener to open a link"}
REQUEST_OR_THREAT = {"money_or_fee_request", "otp_pin_password_request", "card_or_bank_details_request",
                     "remote_access_app", "arrest_or_legal_threat", "account_or_service_threat"}

def _norm(s):
    # Telugu-script loanwords (Prisma te-IN) are read in Latin, as the cues are written; see kavach/loanwords.py
    return re.sub(r"[^\wఀ-౿₹]+", " ", latinise(s).lower()).strip()

def caller_text(call):
    return " ".join(l.split(":", 1)[1] for l in call.splitlines() if l.startswith("Caller:"))

def in_caller_lines(quote, call):
    # Evon sometimes paraphrases a word or two (మీ -> "your"), so a quote passes if at least 60% of its words
    # appear in one caller line; user lines never count
    words = _norm(re.sub(r"^\s*caller\s*:\s*", "", quote, flags=re.I).replace("...", " ").replace("…", " ")).split()
    if len(words) < 2:
        return False
    for line in call.splitlines():
        if line.startswith("Caller:"):
            lw = set(_norm(line.split(":", 1)[1]).split())
            if sum(w in lw for w in words) / len(words) >= 0.6:
                return True
    return False

CUES = {
 # the quote must ask for a payment; whether it is remote is checked over all caller lines in verify()
 # Hindi is matched romanized (bhej, bharna, jama), as ICFD-31k and Prisma's Latin output write it
 # "send" excludes "I'll send you (the link, a brochure)", which offers something instead of asking for money
 "money_or_fee_request":         (r"pay|కట్ట|పంపండి|పంపాలి|పంపు(?=\s|$)|transfer|ఇవ్వండి|ఇవ్వాలి|ఇస్తే|\bsend\b(?! you)|deposit|\bfee\b|\bfine\b|processing"
                                  r"|\bbhej|\bbhar(na|o|iye|\s+do)\b|jama kar|paise de|payment kar|accept\s+(the\s+|a\s+|this\s+)?(upi\s+|payment\s+|collect\s+)?request"),
 "otp_pin_password_request":     r"otp|\bpin\b|password|cvv|code|కోడ్|అంకెల|digit",
 "card_or_bank_details_request": (r"card details|card number|account number|account details|bank details|ifsc|cvv|expiry|expiration|వెనుక ఉన్న \d+|వివరాలు"
                                  r"|net ?banking|login|(confirm|verify|share|provide|tell|give|bataiye|batao)\b.{0,20}\bdetails"),
 "remote_access_app":            r"anydesk|teamviewer|quicksupport|download|install|apk|\bqr\b|scan|screen share|screen sharing",
 # a police officer or a case number alone is not a threat ("calling about the noise complaint", "case reference number")
 "arrest_or_legal_threat":       (r"arrest|warrant|\bfir\b|police (case|action)|jail|case (against|file|register|darj)|\bcourt\b|legal action|legal notice"
                                  r"|giraftar|hirasat"
                                  # loan-app extortion: the threat is exposure, not arrest
                                  r"|morph|(go|make|making|it) viral|viral kar|(send|share|show|post)\b.{0,30}\b(photos?|pictures?|videos?)|recovery agents?"),
 # the action must hit something the listener holds ("the road will be closed" is not a threat)
 "account_or_service_threat":    (r"(block|\bcut\b|deactivat|suspend|cancel|close|disconnect|disrupt|terminat|freeze|band (ho|kar)|\bkaat|\bkat (jayega|dega))"
                                  r"(?=.*\b(account|card|sim|number|connection|power|electricity|current|service|subsidy|kyc|policy|loan|wallet|upi|bank|broadband"
                                  r"|internet|order|delivery|prize|refund|benefits?|pension|meter|it)\b)"
                                  r"|\b(account|card|sim|number|connection|power|electricity|service|subsidy|kyc|policy|loan|wallet|upi|broadband|internet|order"
                                  r"|delivery|prize|refund|benefits?|pension|meter)\b.*(block|\bcut\b|deactivat|suspend|cancel|close|disconnect|disrupt|terminat"
                                  r"|freeze|band (ho|kar)|\bkaat|\bkat (jayega|dega))"),
 "secrecy_demand":               r"ఎవరికీ చెప్ప|చెప్పకు|చెప్పకూడదు|don t tell|do not tell|secret|kisi ko (mat|na|nahi) bata|kisi ko bhi (mat|na)",
 "impersonation_with_pressure":  r"police|officer|inspector|customs|cbi|\bed\b|rbi|court|income tax|government|head office|cyber",
 "suspicious_link":              r"link|http|www|లింక్"}
NEGATED = (r"never|అడగము|అడగరు|అడగం|అవసరం లేదు|చెప్పకండి|చెప్పకు|చెప్పొద్దు|అడిగితే|ఇవ్వకండి|ఇవ్వొద్దు|చేయకండి"
           r"|don t share|do not share|cash on delivery|won t ask|will not ask|don t ask|do not ask|not supposed to ask|don t accept"
           # Hindi: mat (don't), kabhi nahi (never), nahi maangte (we don't ask), zarurat nahi (no need)
           r"|\bmat\b|kabhi (bhi )?nahi|nahi maang|na (bataye|batayein|kare|karein|de|dein)\b|zarurat nahi|zaroorat nahi")
# "if you don't pay, we will ..." is a threat, not a negation: the conditional is removed before NEGATED is checked
CONDITIONAL = r"\bif (you|aap) (don t|do not|won t|will not|didn t)\b|\bagar\b.{0,20}\b(nahi|na)\b|\bwarna\b"
# remote payment: cash handed over in person, or a fee paid at the counter, is not a scam request
REMOTE_PAY = (r"transfer|upi|google pay|gpay|phonepe|paytm|online|neft|imps|link|processing|safe account|account number|(number|account) కి"
              r"|wallet|mobikwik|payu|ola money|freecharge|\bbhim\b|yono|my (\w+ ){0,2}id\b|\bid pe\b|pay (through|via|using|to)|bank account")
# "we have blocked your card" reports a protective action already taken, it is not a threat
DONE_ACTION = r"చేశాం|చేశాము|\bblocked\b"
OPTIONAL = r"చేసుకోవచ్చు|కావాలంటే|if you want|you can"
# English/Hinglish clauses must be phrased as a request to the listener. Telugu requests carry it in the verb ending
# (చెప్పండి, కట్టాలి), so Telugu clauses are not checked here and keep the v3.4 behaviour.
REQUEST = (r"\b(please|kindly|you should|you ll need to|you will need to|need you to|need your"
           r"|can you|could you|will you|would you|you can|if you (could|can)|immediately|right now|right away|now)\b"
           r"|\b(you|we|i) (just |only |really |will |ll )?(need|have to|must|require)\b|\brequires?\b"
           r"|^(just )?(pay|send|share|tell|give|confirm|enter|read|download|install|open|scan|transfer|deposit|click|accept|provide|verify)\b"
           r"|\bjust (pay|send|share|tell|give|confirm|enter|read|download|install|open|scan|accept|provide|click|log ?in|go)\b"
           r"|\b(share|read|tell|give|send) (it|them|that|this|me|us)\b"
           r"|\b(needs?|has|have|must) to be paid\b|\bmust be paid\b|\b(link|details|id|account) (to|for) (pay|make)|payment (link|details)\b"
           r"|\b\w+(iye|ijiye|ije)\b|\b(karo|karein|karna hoga|karna padega|bhejo|batao|bata do|de do|dedo|dena hoga|bharna hoga)\b")
# paying, or downloading, through the official app, website, branch or store is what genuine callers point to
OFFICIAL = r"official|our (website|app|portal|store|branch)|branch|\bstore\b|counter|visit"
REQUESTED = {"money_or_fee_request", "otp_pin_password_request", "card_or_bank_details_request", "remote_access_app"}

def _telugu(s):
    return any("ఀ" <= ch <= "౿" for ch in s)

def negated(clause):
    return bool(re.search(NEGATED, re.sub(CONDITIONAL, " ", clause)))

def caller_lines(call):
    return [l.split(":", 1)[1].strip() for l in call.splitlines() if l.startswith("Caller:")]

def clauses(text):
    # negation is judged per clause: in "ఎవరికీ చెప్పకండి, లేకపోతే arrest చేస్తాం" only the first clause is negated
    return [c for c in (_norm(p) for p in re.split(r"[,.;!?।]", text)) if c]

def cue_clauses(pattern, text):
    return [c for c in clauses(text) if re.search(pattern, c)]

def live(pattern, text):
    # the pattern occurs in at least one clause that is not negated
    return any(not negated(c) for c in cue_clauses(pattern, text))

def verify(tactic, quote, call):
    if not in_caller_lines(quote, call):
        return "not in caller lines"
    cc = cue_clauses(CUES[tactic], quote)
    if not cc:
        return "no cue for tactic"
    if tactic != "secrecy_demand" and all(negated(c) for c in cc):
        return "negated"
    if tactic in REQUESTED:
        # the request may sit in another clause or the next sentence ("…an OTP. Please read it out to me")
        sents = [_norm(s) for s in re.split(r"[.;!?।]", quote) if _norm(s)]
        windows = [" , ".join(sents[i:i + 2]) for i, s in enumerate(sents) if re.search(CUES[tactic], s)]
        if all(not _telugu(w) and not any(re.search(REQUEST, c) for c in clauses(w)) for w in windows):
            return "not a request"   # "your payment has been noted" mentions a payment but asks for nothing
        if all(not _telugu(c) and re.search(OFFICIAL, c) for c in cc):
            return "official channel"
    if tactic == "secrecy_demand" and all(re.search(r"otp|\bpin\b|details|వివరాలు", c) for c in cc):
        return "protective advice"   # "don't tell anyone your OTP" protects the listener
    if tactic == "account_or_service_threat" and all(re.search(DONE_ACTION, c) for c in cc):
        return "action already taken"
    if tactic == "remote_access_app" and all(re.search(OPTIONAL, c) and not re.search(RED_LINES[1][1][0], c) for c in cc):
        return "optional official app"   # "you may download our app from the Play Store" is an offer, not a demand
    if tactic == "money_or_fee_request":
        if re.search(r"\bcash\b", _norm(quote)):
            return "cash in person"
        if not any(live(REMOTE_PAY, l) for l in caller_lines(call)):
            return "no remote payment in call"
    return "ok"

# Red lines, checked in code on every caller line whatever Evon says: a PIN is only ever needed to pay, never to receive,
# and no genuine caller asks the listener to install a remote-control app or an APK, or to share their screen
# (a bank suggesting its own app from the Play Store is not covered, so plain "download" is not a red line)
PIN_TO_RECEIVE = (r"\bpin\b", r"scan|\bqr\b|refund|receive|credit|request|పడుతుంది|తిరిగి వస్తుంది|వస్తాయి")
RED_LINES = [("otp_pin_password_request", PIN_TO_RECEIVE),
             ("remote_access_app", (r"anydesk|teamviewer|quicksupport|\bapk\b|screen share",))]

def red_lines(call):
    out = []
    for l in caller_lines(call):
        n = _norm(l)
        for tactic, pats in RED_LINES:
            if all(re.search(p, n) for p in pats) and live(pats[0], l):
                out.append({"tactic": tactic, "quote": l, "source": "red_line"})
    return out

def decide(evidence):
    tactics = sorted({e["tactic"] for e in evidence})
    if REQUEST_OR_THREAT & set(tactics):
        return "SCAM", tactics
    return ("SUSPICIOUS", tactics) if tactics else ("SAFE", [])
