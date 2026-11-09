# English loanwords as Prisma's te-IN model writes them (Telugu script) and as Kavach's rules, Evon prompts and test calls
# write them (Latin). latinise() rewrites a Telugu transcript into that form: "ఎస్_బిఐ హెడ్_ఆఫీస్ ... ఓటీపీ" ->
# "SBI head office ... OTP". A common Telugu particle may follow (కి, ని, లో…); short or ambiguous words (కట్ = cut, but
# కట్టాలి = must pay) are only replaced as whole words.
import re

# Latin form -> Telugu spellings seen from Prisma (variants separated by spaces; '_' joins a multi-word spelling)
TABLE = {
    "OTP": "ఓటీపీ ఓటిపి ఓటిపీ ఓటీపి", "PIN": "పిన్", "password": "పాస్వర్డ్ పాస్‌వర్డ్", "CVV": "సీవీవీ సివివి",
    "digit": "డిజిట్", "card": "కార్డు కార్డ్", "account": "అకౌంట్ అకౌంటు", "number": "నెంబర్ నంబర్",
    "details": "డీటెయిల్స్ డిటైల్స్ డీటైల్స్", "IFSC": "ఐఎఫ్ఎస్సి ఐఎఫ్‌ఎస్‌సి", "expiry": "ఎక్స్పైరీ ఎక్స్‌పైరీ",
    "expire": "ఎక్స్పైర్ ఎక్స్‌పైర్", "update": "అప్డేట్ అప్‌డేట్", "block": "బ్లాక్", "deactivate": "డీయాక్టివేట్ డియాక్టివేట్",
    "suspend": "సస్పెండ్", "cancel": "క్యాన్సిల్ క్యాన్సల్", "close": "క్లోజ్", "disconnect": "డిస్కనెక్ట్",
    "arrest": "అరెస్ట్ అరెస్టు", "warrant": "వారెంట్", "FIR": "ఎఫ్ఐఆర్ ఎఫ్‌ఐఆర్", "police": "పోలీస్ పోలీసు",
    "case": "కేసు", "court": "కోర్టు కోర్ట్", "jail": "జైలు జైల్", "legal": "లీగల్", "officer": "ఆఫీసర్",
    "inspector": "ఇన్స్పెక్టర్ ఇన్‌స్పెక్టర్", "customs": "కస్టమ్స్", "CBI": "సిబిఐ సీబీఐ", "RBI": "ఆర్బిఐ ఆర్బీఐ ఆర్‌బిఐ",
    "cyber": "సైబర్", "crime": "క్రైమ్", "station": "స్టేషన్", "government": "గవర్నమెంట్", "head office": "హెడ్_ఆఫీస్",
    "payment": "పేమెంట్", "transfer": "ట్రాన్స్ఫర్ ట్రాన్స్‌ఫర్ ట్రాన్సఫర్", "deposit": "డిపాజిట్", "fee": "ఫీజు",
    "fine": "ఫైన్", "processing": "ప్రాసెసింగ్", "UPI": "యూపీఐ యుపిఐ యూపిఐ", "Google Pay": "గూగుల్_పే", "GPay": "జీపే",
    "PhonePe": "ఫోన్పే ఫోన్‌పే", "Paytm": "పేటీఎం పేటియం", "online": "ఆన్లైన్ ఆన్‌లైన్", "NEFT": "నెఫ్ట్",
    "link": "లింక్", "download": "డౌన్లోడ్ డౌన్‌లోడ్", "install": "ఇన్స్టాల్ ఇన్‌స్టాల్", "app": "యాప్",
    "AnyDesk": "ఎనీడెస్క్", "TeamViewer": "టీమ్వ్యూయర్ టీమ్‌వ్యూయర్", "APK": "ఏపీకే ఏపికే", "QR": "క్యూఆర్",
    "scan": "స్కాన్", "screen share": "స్క్రీన్_షేర్", "share": "షేర్", "safe account": "సేఫ్_అకౌంట్",
    "KYC": "కేవైసీ కెవైసి కేవైసి", "refund": "రిఫండ్", "cash": "క్యాష్", "connection": "కనెక్షన్", "power": "పవర్",
    "meter": "మీటర్", "SIM": "సిమ్", "code": "కోడ్", "secret": "సీక్రెట్", "SBI": "ఎస్_బిఐ ఎస్బిఐ ఎస్‌బిఐ ఎస్_బీ_ఐ",
    "HDFC": "హెచ్డిఎఫ్సి హెచ్‌డిఎఫ్‌సి", "ICICI": "ఐసిఐసిఐ", "bank": "బ్యాంక్ బ్యాంకు", "branch": "బ్రాంచ్",
    "request": "రిక్వెస్ట్", "temporary": "టెంపరరీ", "fraud": "ఫ్రాడ్", "monitoring": "మానిటరింగ్", "team": "టీమ్",
    "transaction": "ట్రాన్సాక్షన్ ట్రాన్సక్షన్", "phone": "ఫోన్", "mobile": "మొబైల్", "video call": "వీడియో_కాల్",
    "call": "కాల్", "parcel": "పార్సెల్", "drugs": "డ్రగ్స్", "register": "రిజిస్టర్", "savings": "సేవింగ్స్",
    "investigation": "ఇన్వెస్టిగేషన్", "return": "రిటర్న్", "rupees": "రూపీస్", "Aadhaar": "ఆధార్", "PAN": "పాన్",
    "Mumbai": "ముంబై", "sir": "సార్", "madam": "మేడమ్ మేడం", "SMS": "ఎస్ఎంఎస్ ఎస్‌ఎంఎస్", "WhatsApp": "వాట్సాప్",
}
WHOLE = {"PIN", "fee", "fine", "SIM", "app", "case", "link", "FIR", "PAN", "call", "team", "code", "sir"}
PARTICLE = r"(?:ని|కి|లో|తో|ను|గా|కు|లు|ల|ది|నే|ే)?"
# (pattern, Latin form); group 1 is the particle after a whole-word match. Longest spellings first, so "సేఫ్_అకౌంట్"
# is replaced before "అకౌంట్".
PATTERNS = sorted(
    ((re.compile(r"(?<![ఀ-౿])" + re.escape(te.replace("_", " ")) + (r"(" + PARTICLE[3:-2] + r")?(?![ఀ-౿])" if en in WHOLE else r"()")), en, len(te))
     for en, spellings in TABLE.items() for te in spellings.split()),
    key=lambda p: -p[2])


def latinise(text):
    if not any("ఀ" <= ch <= "౿" for ch in text):
        return text
    for pat, en, _ in PATTERNS:
        def repl(m, en=en):
            rest = m.string[m.end():m.end() + 1]
            particle = m.group(1) or ""
            # "కార్డుని" -> "card ని": keep the Telugu particle as its own word
            return en + (" " + particle if particle else "") + (" " if rest and "ఀ" <= rest <= "౿" else "")
        text = pat.sub(repl, text)
    return re.sub(r"\s{2,}", " ", text).strip()
