# The public website (Vercel): a landing page plus the real Kavach screen in Replay mode, as static files. Every answer
# the screen would ask the server for is exported here from the saved runs (the same view() the server returns), so the
# site needs no Gnani key, no Evon and no server. Only our own Telugu calls are published; ICFD-31k runs stay local.
#   site/index.html (landing), site/app/ (the screen + its api/ answers and audio)
# The videos and the pitch PDF are copied in at deploy time by vercel.json, so they are not stored twice in git.
# Usage: .venv\Scripts\python -m kavach.make_site
import json, shutil, sys
from pathlib import Path

from kavach import web as W
from kavach.make_demo_video import GLOSS, WARNING_GLOSS

ROOT = Path(__file__).parent.parent
SITE = ROOT / "site"
APP = SITE / "app"
CALLS = ["te_kyc_otp", "te_digital_arrest", "te_fraud_alert"]
GLOSSES = GLOSS | {"te_digital_arrest": [
    "Hello, this is Inspector Sharma from the Mumbai cyber crime police station. Drugs were found in a parcel with your Aadhaar number; an FIR is registered against you.",
    "Oh no, I don't know anything about this, sir.",
    "Stay on a video call right now and tell no one, or we issue an arrest warrant. Transfer all your savings to an RBI account; it comes back after the investigation."]}
WARNINGS = WARNING_GLOSS | {"te_digital_arrest": "“Careful, this is a scam call. If they ask for money, hang up right away.”"}
ASK_OFF = ("Asking needs Evon running on our GPU, so it is off on this replay site. "
           "The demo video shows the family asking and Evon answering from the sealed evidence.")

SHIM = """
// ---- static site (kavach/make_site.py): the server's answers were exported from the saved runs ----
const _fetch = window.fetch.bind(window);
window.fetch = async (url, opt = {}) => {
  if (!String(url).startsWith("/api/")) return _fetch(url, opt);
  const b = opt.body ? JSON.parse(opt.body) : {};
  if (url === "/api/ask") return new Response(JSON.stringify({detail: ASK_OFF}), {status: 503, headers: {"Content-Type": "application/json"}});
  const path = url === "/api/status" ? "api/status.json" : url === "/api/analyse" ? `api/analyse/${b.call_id}.json`
             : `api/verify/${b.call_id}${b.edited ? "_edited" : ""}.json`;
  return _fetch(path);
};
async function replay() {
  // Analyse on the replay site: the call plays and each turn appears as it is spoken, with English subtitles
  $("go").disabled = true;
  const p = $("player"); p.pause(); p.currentTime = 0;
  try {
    await kavachDemo(current, {gloss: GLOSSES[current], warningGloss: WARNINGS[current], onStart: () => p.play().catch(() => {})});
    setTimeout(() => kavachCaption(""), 7000);
  } finally { $("go").disabled = false; }
}
"""
BANNER = """<div class="replay-note">Replay of real saved runs: the calls, verdicts, warnings and seals below were produced by Kavach
  with Gnani Prisma, Evon and Timbre. Live analysis needs our Gnani key and Evon on a GPU, so it runs locally.
  <a href="../">← Kavach home</a></div>"""
NOTE_CSS = """.replay-note { background: var(--brand-soft); color: var(--ink-2); font-size: 13px; line-height: 1.5; padding: 8px 24px; text-align: center; }
.replay-note a { color: var(--brand); font-weight: 600; margin-left: 6px; text-decoration: none; }
</style>"""
EDITS = [  # (in the screen's page, replace, with): each must match exactly once
    ("</style>", NOTE_CSS),
    ("<body>\n", "<body>\n" + BANNER + "\n"),
    ('<button id="mLive" aria-pressed="true">Live</button><button id="mReplay" aria-pressed="false">Replay</button>',
     '<button id="mLive" aria-pressed="false" hidden>Live</button><button id="mReplay" aria-pressed="true">Replay</button>'),
    ('let mode = "live"', 'let mode = "replay"'),
    ('"Evon offline"', '"Replay"'),
    ("<script>\n", "<script>\n" + "".join(f"const {k} = {json.dumps(v, ensure_ascii=False)};\n" for k, v in
                                          (("ASK_OFF", ASK_OFF), ("GLOSSES", GLOSSES), ("WARNINGS", WARNINGS))) + SHIM),
    ('$("go").onclick = analyse;', '$("go").onclick = replay;'),
    ("`/api/audio/${current}`", "`api/audio/${current}.wav`"),
    ("`/api/warning/${r.call_id}?t=${Date.now()}`", "`api/warning/${r.call_id}.wav`"),
    ("`/api/family_alert/${callId}`", "`api/family_alert/${callId}.wav`"),
]


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    shutil.rmtree(APP, ignore_errors=True)
    page = W.PAGE.read_text(encoding="utf-8")
    for old, new in EDITS:
        if page.count(old) != 1:
            sys.exit(f"the screen's page changed: {old[:60]!r} found {page.count(old)} times")
        page = page.replace(old, new)
    (APP).mkdir(parents=True)
    (APP / "index.html").write_text(page, encoding="utf-8")

    calls = [c for c in W.call_list() if c["id"] in CALLS]
    calls.sort(key=lambda c: CALLS.index(c["id"]))
    put(APP / "api" / "status.json", {"evon": False, "calls": calls, "seals": len(W.LEDGER.records())})
    for cid in CALLS:
        v = W.view(json.loads((W.RUNS / cid / "result.json").read_text(encoding="utf-8")), cid)
        put(APP / "api" / "analyse" / f"{cid}.json", v)
        put(APP / "api" / "audio" / f"{cid}.wav", (W.AUDIO / f"{cid}_mono.wav").read_bytes())
        if v["has_warning_audio"] and v["warning"].get("text"):
            put(APP / "api" / "warning" / f"{cid}.wav", (W.RUNS / cid / "warning.wav").read_bytes())
        if v["family_alert"].get("send"):
            put(APP / "api" / "family_alert" / f"{cid}.wav", Path(W.family_alert_audio(cid).path).read_bytes())
        if v["seal"]:
            for edited in (False, True):
                put(APP / "api" / "verify" / f"{cid}{'_edited' if edited else ''}.json", W.verify(W.Verify(call_id=cid, edited=edited)))
        print(cid, v["verdict"], "seal" if v["seal"] else "no seal", "alert" if v["family_alert"].get("send") else "no alert")
    size = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file()) / 2**20
    print(f"wrote {SITE} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
