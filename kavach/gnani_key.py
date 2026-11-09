# The Gnani API key: GNANI_API_KEY from the environment (Kaggle exports it from the GNANI secret), else Project/gnani.env,
# which may hold the bare key or GNANI_API_KEY=<key>. The key is only ever sent as the X-API-Key-ID header to
# api.vachana.ai; nothing here prints or stores it.
import os
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / "gnani.env"


def load_key():
    key = os.environ.get("GNANI_API_KEY", "").strip()
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, eq, value = line.partition("=")
            key = (value if eq and name.strip().removeprefix("export ").strip() == "GNANI_API_KEY" else
                   "" if eq else line).strip().strip("'\"")
            if key:
                break
    return key or None
