# Builds the Kaggle notebook that hosts Evon for Kavach, and packs it into one cell that can be typed into an empty
# Kaggle cell (the notebook editor is a cross-origin iframe, so files cannot be uploaded into it directly).
#   evon/evon_server_kaggle.ipynb    the notebook
#   evon/evon_server_kaggle_cell.txt one line: decodes the notebook and runs its code cells in the live kernel
# The setup cells are the ones proven in the Oct 25-26 runs (llama.cpp b3fa699, sm_75, Q4_K_M split over 2x T4).
# New: llama-server needs an access key, and a Cloudflare quick tunnel gives the laptop an https address for it.
# Usage: py evon/make_evon_server_nb.py
import base64, json, zlib
from pathlib import Path

HERE = Path(__file__).parent
cells = []
def md(s): cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip("\n")})
def code(s): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip("\n")})

md(r"""
# Kavach: Evon v3.3 server on Kaggle 2x T4

Hosts Evon (Q4_K_M GGUF, llama-server) for the Kavach app running on the laptop. Everything else (Prisma, Timbre, rules, Notary, screen) runs on the laptop.

**Before Run all:** Accelerator **GPU T4 x2**, Internet **on**, secret `HF` attached.

At the end the notebook prints an https address and an access key. Put them in `Project/evon.env` on the laptop:

```
KAVACH_EVON_URL=https://....trycloudflare.com
KAVACH_EVON_KEY=....
```

The last cell keeps the session alive and reports health every 10 minutes. Stop the session when done to save GPU hours.
""")

code(r"""
# 1. Settings
import os, json, time, subprocess, shutil, re, secrets
from pathlib import Path

GGUF_REPO  = "anilkumarlucky/gnani-evon-v3.3-30b-a3b-GGUF"
GGUF_FILE  = "gnani-evon-v3.3-30b-a3b-Q4_K_M.gguf"
BASE_REPO  = "gnani/gnani-evon-v3.3-30b-a3b"      # chat_template.jinja lives here
LLAMA_SHA  = "b3fa699"                             # the llama.cpp commit the GGUF was converted with
SRC        = Path("/tmp/llama.cpp")
BIN        = Path("/kaggle/working/llama-bin")     # a rerun in the same session skips the build
MODEL_DIR  = Path("/tmp/evon")
PORT       = 8080
URL        = f"http://127.0.0.1:{PORT}"
CTX, SLOTS = 16384, 2                              # 8k tokens per slot; Prosecutor and Defender run in parallel
API_KEY    = secrets.token_urlsafe(24)             # new every session; the tunnel is public, the key is not
CPU_MOE_STEPS = [0, 6, 12, 20]

# stop now, not after a 25-minute build, if the HF secret is not attached to this notebook
from kaggle_secrets import UserSecretsClient
try:
    assert UserSecretsClient().get_secret("HF")
except Exception as e:
    raise SystemExit("Attach the HF secret first: Add-ons -> Secrets -> HF (ticked for this notebook). " + type(e).__name__)
print("HF secret attached")
""")

code(r"""
# 2. Hardware check
gpus = [g for g in subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True).stdout.split("\n") if g.strip()]
print(gpus)
assert len(gpus) == 2, "Set Accelerator to GPU T4 x2"
""")

code(r"""
# 3. llama-server: reuse the binary saved from an earlier run (dataset kavach-llama-bin), else build (about 27 min)
SERVER = BIN / "llama-server"
cached = sorted(Path("/kaggle/input").glob("**/llama-server"))
if not SERVER.exists() and cached:
    BIN.mkdir(parents=True, exist_ok=True)
    shutil.copy(cached[0], SERVER)
    SERVER.chmod(0o755)
    print("using the saved llama-server build:", cached[0])
if not SERVER.exists():
    t = time.time()
    if not SRC.exists():
        !git clone -q --filter=blob:none https://github.com/ggml-org/llama.cpp {SRC}
    !git -C {SRC} checkout -q {LLAMA_SHA}
    !cd {SRC} && cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75 -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release -DCUDA_cuda_driver_LIBRARY=/usr/local/nvidia/lib64/libcuda.so > /tmp/cmake.log 2>&1 || tail -30 /tmp/cmake.log
    !cd {SRC} && cmake --build build --target llama-server -j {os.cpu_count()} > /tmp/build.log 2>&1 || tail -40 /tmp/build.log
    BIN.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC / "build/bin/llama-server", SERVER)
    print(f"built in {(time.time() - t) / 60:.1f} min")
assert SERVER.exists(), "build failed, see the log tail above"
""")

code(r"""
# 4. Download the Q4_K_M GGUF (private repo) and Evon's chat template
from kaggle_secrets import UserSecretsClient
from huggingface_hub import hf_hub_download
os.environ["HF_TOKEN"] = UserSecretsClient().get_secret("HF")
MODEL = Path(hf_hub_download(GGUF_REPO, GGUF_FILE, local_dir=MODEL_DIR))
TEMPLATE = Path(hf_hub_download(BASE_REPO, "chat_template.jinja", local_dir=MODEL_DIR))
print(f"model {MODEL.stat().st_size / 1e9:.1f} GB")
""")

code(r"""
# 5. Start llama-server with the access key, stepping down the GPU load until it fits
import requests
AUTH = {"Authorization": f"Bearer {API_KEY}"}

def start_server(n_cpu_moe):
    log = open(f"/tmp/server_cpumoe{n_cpu_moe}.log", "w")
    cmd = [str(SERVER), "-m", str(MODEL), "--chat-template-file", str(TEMPLATE), "-ngl", "999", "-sm", "layer", "-ts", "1,1",
           "-c", str(CTX), "-np", str(SLOTS), "-fa", "auto", "--host", "127.0.0.1", "--port", str(PORT), "--api-key", API_KEY, "--metrics"]
    if n_cpu_moe:
        cmd += ["--n-cpu-moe", str(n_cpu_moe)]
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    t = time.time()
    while time.time() - t < 900:
        if proc.poll() is not None:
            return None, log.name
        try:
            if requests.get(f"{URL}/health", headers=AUTH, timeout=2).status_code == 200:
                return proc, log.name
        except requests.RequestException:
            pass
        time.sleep(5)
    proc.kill()
    return None, log.name

server = None
for n in CPU_MOE_STEPS:
    server, logname = start_server(n)
    if server:
        print("server up, n_cpu_moe =", n)
        break
    tail = open(logname).read()[-1500:]
    print(f"--- n_cpu_moe={n} failed:\n{tail}")
    if not re.search(r"out of memory|failed to allocate|cudaMalloc", tail, re.I):
        raise SystemExit("Server failed for a reason other than memory; see the log tail above.")
assert server, "Did not fit"
r = requests.post(f"{URL}/v1/chat/completions", headers=AUTH, timeout=300, json={
    "messages": [{"role": "user", "content": "Say OK."}], "max_tokens": 8, "chat_template_kwargs": {"enable_thinking": False}})
print("warm-up:", r.status_code, r.json()["choices"][0]["message"]["content"])
assert requests.post(f"{URL}/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}, timeout=30).status_code == 401, \
    "server answered without the key"
""")

code(r"""
# 6. Cloudflare quick tunnel (no account): an https address for the laptop, in front of the keyed server
CF = Path("/kaggle/working/cloudflared")
cached_cf = sorted(Path("/kaggle/input").glob("**/cloudflared"))
if not CF.exists() and cached_cf:
    shutil.copy(cached_cf[0], CF)
    CF.chmod(0o755)
if not CF.exists():
    !wget -q -O {CF} https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    CF.chmod(0o755)
tunnel_log = open("/tmp/tunnel.log", "w")
tunnel = subprocess.Popen([str(CF), "tunnel", "--no-autoupdate", "--url", URL], stdout=tunnel_log, stderr=subprocess.STDOUT)
PUBLIC = None
for _ in range(60):
    time.sleep(2)
    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", open("/tmp/tunnel.log").read())
    if m:
        PUBLIC = m.group(0)
        break
assert PUBLIC, open("/tmp/tunnel.log").read()[-1500:]
for _ in range(30):   # the address takes a few seconds to start answering
    try:
        if requests.get(f"{PUBLIC}/health", headers=AUTH, timeout=10).status_code == 200:
            break
    except requests.RequestException:
        pass
    time.sleep(3)
ENDPOINT = f"KAVACH_EVON_URL={PUBLIC}\nKAVACH_EVON_KEY={API_KEY}\n"
Path("/kaggle/working/evon_endpoint.txt").write_text(ENDPOINT)
print("\nPut these two lines in Project/evon.env on the laptop:\n")
print(ENDPOINT)
""")

code(r"""
# 7. Keep Evon up while it is used. Ends by itself after IDLE_MIN minutes without a request, or after MAX_HOURS,
#    so a forgotten session (or a background version) cannot burn the GPU quota.
IDLE_MIN, MAX_HOURS = 60, 6
def served():
    try:
        m = requests.get(f"{URL}/metrics", headers=AUTH, timeout=10).text
        return sum(float(x) for x in re.findall(r"^llamacpp:requests_processing[^ ]* ([0-9.e+]+)$", m, re.M)) + \
               sum(float(x) for x in re.findall(r"^llamacpp:prompt_tokens_total[^ ]* ([0-9.e+]+)$", m, re.M))
    except Exception:
        return None
start, last_use, last_count = time.time(), time.time(), served()
while True:
    time.sleep(120)
    count = served()
    if count is not None and count != last_count:
        last_use, last_count = time.time(), count
    try:
        h = requests.get(f"{PUBLIC}/health", headers=AUTH, timeout=15).status_code
    except requests.RequestException as e:
        h = type(e).__name__
    idle = (time.time() - last_use) / 60
    # the live view of a background run shows only the newest line, so every line repeats the endpoint
    print(time.strftime("%H:%M:%S"), "server", "up" if server.poll() is None else "DOWN", "| tunnel", "up" if tunnel.poll() is None else "DOWN",
          "| public health", h, f"| idle {idle:.0f} min |", ENDPOINT.replace("\n", " "), flush=True)
    if idle > IDLE_MIN or time.time() - start > MAX_HOURS * 3600:
        print("stopping: idle" if idle > IDLE_MIN else "stopping: time cap", flush=True)
        tunnel.terminate(); server.terminate()
        break
""")

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
      "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
nb_bytes = json.dumps(nb, ensure_ascii=False, indent=1).encode("utf-8")
(HERE / "evon_server_kaggle.ipynb").write_bytes(nb_bytes)
b = base64.b64encode(zlib.compress(nb_bytes, 9)).decode()
line = ("import base64,zlib,json;nb=json.loads(zlib.decompress(base64.b64decode('" + b + "')));"
        "open('/kaggle/working/evon_server_kaggle.ipynb','w').write(json.dumps(nb));"
        "exec(\"ip=get_ipython()\\nfor c in nb['cells']:\\n if c['cell_type']!='code': continue\\n"
        " src=''.join(c['source']); print('#### cell', src.splitlines()[0], flush=True)\\n"
        " r=ip.run_cell(src)\\n if not r.success: print('#### STOPPED at', src.splitlines()[0]); break\")")
(HERE / "evon_server_kaggle_cell.txt").write_text(line, encoding="utf-8")
print(f"notebook {len(nb_bytes):,} bytes, cell {len(line):,} chars")
