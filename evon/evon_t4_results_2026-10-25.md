# Evon v3.3 Q4_K_M on Kaggle 2× T4: results (2026-10-25)

Run of `evon_kaggle_llama_server_test.ipynb`; llama.cpp b3fa699 built with CUDA sm_75; model `anilkumarlucky/gnani-evon-v3.3-30b-a3b-GGUF`, Q4_K_M, 24.67 GB.

## Infrastructure: works

| Measure | Result |
|---|---|
| Fits on GPU | Yes, fully (`--n-cpu-moe 0`), `-sm layer -ts 1,1`, ctx 16k, 2 slots |
| Load time | 110 s |
| VRAM after load / after all roles | 11.0 + 12.4 GB / 11.1 + 12.5 GB (of 15 + 15) |
| Generation, one request | 70.3 tok/s |
| Prefill, 3,409-token prompt | 1,477 tok/s |
| Two requests at once | 45.1 + 57.2 tok/s = 69.5 tok/s combined (no throughput gain: layer split is pipelined) |
| Telugu tokens per word | 2.27 |
| Scam call: seconds to verdict (Prosecutor ‖ Defender, then Judge) | 7.0 s thinking off, 26.5 s thinking on |
| All five roles, one call | 9.5–12.8 s thinking off, 35–47 s thinking on |

## Behaviour: needs prompt work before the demo

| Check | Thinking off | Thinking on |
|---|---|---|
| Digital-arrest scam flagged | Yes, SCAM 0.95 | Yes, SCAM 0.95 |
| Genuine SBI card-delivery call left alone | **No, SCAM 0.95** | **No, SCAM 0.95** |
| Spoken warnings mostly Telugu | **No** (34%, 38%) | **No** (91% scam, 0% genuine) |
| No truncated answers | Yes | **No** |

1. **False positive on the genuine call.** The Prosecutor read "we never ask for OTP or PIN" as a *secrecy demand* and "call the number on the back of the card" as a *suspicious contact*; the Judge sided with it although the Defender argued correctly that nothing was requested. The scam-leaning system prompt and the one-sided Prosecutor brief bias the Judge.
2. **Warning role echoed the transcript (thinking off).** Instead of a warning it re-spoke the caller's lines ("మీ savings మొత్తం RBI safe account కి transfer చేయండి…"), which Kavach must never play aloud. The warning prompt should get the verdict and tactics only, not the transcript.
3. **Thinking on starves the answer.** With thinking on, the reasoning used up `max_tokens` on the Defender and on the genuine call's warning, so they came back empty; verdicts were the same and took ~4× longer. Use thinking off for every live role.
4. **Telugu, when produced, is good.** The thinking-on scam warning, "అయ్యో, ఇది మోసం. వెంటనే ఫోన్ పెట్టేయండి. డబ్బులు పంపకండి, OTP చెప్పకండి.", is short, natural and correct, and the Telugu complaint drafts read fluently.

## Next

- Rewrite prompts: neutral system prompt; Judge calibrated with benign signals (no money/OTP/app request, points to the official number); warning prompt without the transcript, with one Telugu example; thinking off throughout.
- Test on more than two calls before quoting any accuracy.
