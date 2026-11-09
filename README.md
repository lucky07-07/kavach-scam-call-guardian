# Kavach — a second listener for scam calls

**Solution pitch (1 page):** [PITCH.md](PITCH.md) · [PDF](docs/Kavach_pitch.pdf) &nbsp;|&nbsp; **Demo video (2:50):** [kavach_demo_full.mp4](data/demo/kavach_demo_full.mp4) &nbsp;|&nbsp; **Trailer (0:60):** [kavach_trailer.mp4](data/demo/trailer/kavach_trailer.mp4)

Kavach listens to a phone call with an elderly Telugu speaker. If the caller tries a scam, it warns the listener in Telugu,
alerts the family at once, drafts the 1930 / cybercrime complaint, and seals the evidence on Bitcoin so nobody can edit it later. After the call, the
family can ask Kavach what happened, in Telugu.

Built for the **Gnani AI Great Indian AI Internship Challenge 2026**, entirely on Gnani models:

| Gnani model | Role in Kavach |
|---|---|
| **Prisma v2.5** (speech-to-text) | Listener: transcribes the call and separates caller and listener (Telugu, English, Hinglish) |
| **Evon v3.3** (LLM, self-hosted, Q4_K_M on 2× T4) | Prosecutor, Defender, explanation, Telugu warning text, complaint, family assistant |
| **Timbre** (text-to-speech) | Speaks the warning to the listener, in Telugu or Hindi |

## How it works: eight agents, one job

During the call, agents 1–7 run in a fixed order. The verdict is decided by code, never by the LLM.

```
call audio
  1 Listener     Prisma batch: who said what (two speakers) → per-turn REST pass restores words batch drops
                 → English loanwords back in Latin script ("ఓటీపీ" → OTP); Evon restores punctuation, code checks no word changed
  2 Prosecutor   Evon: which scam tactics does the caller use? Each claim must quote the caller
  3 Defender     Evon: signs the call is genuine, with quotes
  4 Judge        code: a claim counts only if the quote is the caller's own words, carries a cue for the tactic,
                 and is not negated ("we will never ask for OTP"); red-line rules in code catch what Evon misses
                 → SCAM (verified request or threat) / SUSPICIOUS / SAFE
  5 Guardian     Evon writes the Telugu warning; code checks it (mostly Telugu, no caller words, no numbers or links)
                 or uses an approved warning; Timbre speaks it.
                 Family alert: on SCAM or SUSPICIOUS, code builds a message for the family in Telugu or Hindi from the
                 verdict and verified tactics only ("Amma just got a scam call… call her now"), Timbre voices it as a
                 voice note, and it is queued for delivery
  6 Reporter     Evon fills the complaint fields; code assembles the 1930 complaint
  7 Notary       evidence packet → SHA-256 → hash chain → OpenTimestamps (Bitcoin); only 32 bytes leave the device
after the call
  8 Family assistant   the family asks in Telugu; the Kavach MCP server gives read-only tools
                       (list_incidents, get_incident, verify_seal, draft_complaint); Evon answers from the results
```

Why a code Judge: in early versions an LLM judge called every genuine call a scam (0/7 genuine left alone). With the
prosecutor/defender split and a code judge, no genuine test call has been flagged since.

## Results (honest numbers)

All calls are synthetic: scripts written by us or taken from ICFD-31k, voiced by Gnani Timbre at 8 kHz. None are real
phone calls, and the samples are small.

| What | Result | Notes |
|---|---|---|
| 44 hand-written Telugu–English calls, text, Evon v3.4 prompts | 38/44: scams 16/22, **genuine 22/22** | Seen calls (the rules were developed on them) |
| ICFD-31k held-out sample (100 scam + 100 genuine), code-only bounds | scams confirmable 76/100, genuine safe even if Evon over-claims 69/100 | Bounds, not accuracy; English/Hinglish |
| Listener on Timbre audio, 6 English/Hinglish calls | caller identified 5/6 mono, 6/6 stereo; word error 3.5% (fair scoring); scam keywords kept 17/17 | |
| Listener on 3 Telugu calls (after the per-turn pass) | caller identified 3/3; word error 0%, 12%, 9% | Fixes developed on these same calls |
| **End to end with real Evon**, 6 English/Hinglish calls | 5/6: genuine 3/3 SAFE, scams 2/3 | The miss: Evon claimed "money" instead of "password" |
| **End to end with real Evon**, 3 Telugu calls | 3/3: two scams SCAM, genuine SAFE | Seen calls |
| 3 Hindi calls (Prisma `en-IN`, Hinglish in Latin script) | caller identified 3/3; code-only verdicts 3/3 (SCAM, SCAM, SAFE) | Evon end-to-end run pending a free Kaggle GPU slot; Hindi warning spoken by Timbre (Yashvi) |
| Time to verdict (laptop → Evon on Kaggle via tunnel) | 9–12 s Telugu, 10–20 s English | Evon inside Kaggle alone: about 6 s |
| RL "when to warn" policy, ICFD-31k held-out (1000 scam + 1000 genuine) | false alarms 310 vs 335 for the Judge alone; scams warned in time 616 vs 627; mean reward +0.003 (95% CI −0.008 to +0.013) | **A tie, not a win.** Experimental; not used in the pipeline |
| Evidence seal | 3 Nov seal confirmed on Bitcoin, block 974,389 | Checked against the block's Merkle root; a one-byte edit fails verification |

Known limits:
- **Punctuation:** restoring it on Telugu mostly fails (Evon rewrites words, so the code keeps Prisma's text). Verdicts were still right.
- **Telugu answers:** the family assistant sometimes answers Telugu questions in mixed English. A fixed Telugu answer built from the same facts is used then, and is labelled as such.
- **Hindi:** Hindi calls are transcribed with Prisma `en-IN`, which writes Hinglish in Latin script, the form the rules read; `hi-IN` writes everything in Devanagari, which the rules do not yet read.
- **Family alert delivery:** alerts are queued in `data/alerts/outbox.jsonl` and shown on the screen; no SMS/WhatsApp gateway is connected yet.
- **Not live yet:** calls are analysed after recording. Prisma's batch mode is what separates the speakers.
- **Missed tactics:** Evon still misses some, such as the password request. Red-line rules cover OTP/PIN-to-receive and remote-access apps.

## Experiment: when to warn (reinforcement learning)

The Judge decides *what* counts as evidence. In a live call Kavach also has to decide *when* to speak: after each caller
turn, warn now or wait. Warning a genuine caller costs trust; warning after the OTP is shared is too late. `kavach/rl_warn.py`
treats this as an optimal-stopping problem on 6,000 ICFD-31k training calls, using the dataset's turn-level "harm" marks:

- **State:** what the code Judge has verified so far (distinct request/threat tactics, turns carrying them, softer signs,
  red line fired, turn number).
- **Reward:** +1 for a warning before harm (less if late), −1 for a missed scam, −1.5 for a false alarm, +0.2 for staying silent.
- **Learners:** tabular Q-learning and fitted Q-iteration did *worse* than the Judge's own rule (mean reward −0.021 and
  0.027 vs 0.049), because the compact state lumps very different calls together. Direct policy search, starting from the
  Judge's rule and keeping only changes that raise reward on the training calls, ties it.

Result: the policy learned to wait one more turn in some weak-evidence states, giving 25 fewer false alarms per 1000
genuine calls at the cost of 11 late or missed warnings per 1000 scams. The overall gain is within noise, so the verdict
and the warning still come from the Judge. The limit is the evidence itself (code-verified words), not the timing rule.
Run: `.venv\Scripts\python -m kavach.rl_warn` → `data/rl/report.json`, `data/rl/policy.json`.

## Repository

```
kavach/
  listener.py        Agent 1 — Prisma batch (diarization) + per-turn REST refine + loanword latinising
  loanwords.py       Telugu-script → Latin loanword table (OTP, account, block, arrest, UPI, …)
  evon.py            Evon client and prompts (Prosecutor, Defender, explainer, Reporter, punctuation)
  rules.py           Agent 4 — the Judge: quote checks, cues, negation, red lines, verdict
  guardian.py        Agent 5 — Telugu warning text checks + Timbre voice
  family_alert.py    Agent 5 — the family alert (code-built Telugu/Hindi message, Timbre voice note, outbox)
  rl_warn.py         experiment: RL "when to warn" policy on ICFD-31k (ties the Judge; not in the pipeline)
  notary.py          Agent 7 — evidence packet, hash chain, OpenTimestamps, verification
  pipeline.py        Agents 1–7 in order
  mcp_server.py      Kavach MCP server (read-only tools)
  assistant.py       Agent 8 — family assistant over MCP
  web.py, web/       the demo screen (FastAPI + one page)
  trailer/           60-second trailer: Timbre narration, a recorded walkthrough of the real screen (cursor, clicks),
                     beat-cut stage, synthesised SFX and music
  timbre.py, transcript.py, gnani_key.py, schemas/
  test_*.py, check_*.py, make_*.py   tests, measurements, test-audio and demo-video makers
evon/                Kaggle notebook that hosts Evon (llama-server + Cloudflare tunnel), prompt iteration notes
data/                test calls (44 Telugu, 3 Hindi, ICFD samples), demo runs, the evidence ledger, the demo video and trailer
docs/                research dossier, build plan, submission write-up, post draft
```

## Running it

1. **Gnani key:** put your Gnani API key in `gnani.env`, the bare key or `GNANI_API_KEY=…` (git-ignored).
2. **Evon:** run `evon/evon_server_kaggle.ipynb` on Kaggle (GPU T4 ×2, internet on, secret `HF`, dataset `kavach-llama-bin`) with **Save & Run All**. Copy the two `KAVACH_EVON_…` lines it prints into `evon.env`.
3. **Environment:**

   ```
   py -m venv .venv
   .venv\Scripts\python -m pip install gradio==5.49.1 requests jsonschema opentimestamps zstandard mcp==1.12.4
   ```
4. **Screen:** `.venv\Scripts\python -m kavach.web`, then open http://127.0.0.1:7861.
5. **One call from the command line:** `.venv\Scripts\python -m kavach.run_call data/test_audio/te_kyc_otp_mono.wav --lang te-IN`
6. **Tests:**

   ```
   .venv\Scripts\python -m kavach.test_pipeline
   .venv\Scripts\python -m kavach.test_listener
   .venv\Scripts\python -m kavach.test_guardian_notary
   .venv\Scripts\python -m kavach.test_assistant
   .venv\Scripts\python -I kavach/test_rules.py
   ```

## Credits

- **ICFD-31k:** Ahuja, Prateek and Singh, *ICFD-31k: A Large-Scale Dataset and Benchmark for Real-Time Conversational Fraud Detection*, IJCAI-ECAI 2026. Used under its defensive-use licence, for evaluation only.
- **Software:** OpenTimestamps (Bitcoin timestamping) and llama.cpp (serving Evon).
