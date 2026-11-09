# Kavach: build plan to submission (3–10 Nov 2026)

**Deadline:** 10 Nov 2026, 23:59 IST.

**Submission:**
- a pitch;
- a demo video (or a live link);
- a written explanation: title, problem, users, Gnani models used, who did what;
- a public LinkedIn/X post with #GnaniAI #GreatIndianAIInternshipChallenge, live before submitting.

Shortlisting is by engagement on that post, so the post needs to go out early.

## 1. What we are building

Kavach is a second listener for elderly Telugu speakers. It hears a phone call, decides whether it is a scam, warns the listener in Telugu, and keeps tamper-proof evidence for the family and the police.

Eight agents share the work:

| # | Agent | Gnani model / tool | Job | Status |
|---|---|---|---|---|
| 1 | Listener | Prisma | Call audio → transcript, caller vs listener | built, offline-tested |
| 2 | Prosecutor | Evon | Finds scam tactics with the caller's exact words | done (v3.4) |
| 3 | Defender | Evon | Finds signs the call is genuine | done |
| 4 | Judge | our code (rules.py) | Verdict from verified evidence only; never an LLM | done |
| 5 | Guardian | Evon + Timbre | Writes and speaks the Telugu warning | text done, voice to build |
| 6 | Reporter | Evon | 1930 / cybercrime complaint draft | done |
| 7 | Notary | SHA-256 + OpenTimestamps (Bitcoin) | Seals the evidence; an edited copy fails verification | to build |
| 8 | Family assistant | Evon over a Kavach MCP server | After the call: answers the family, verifies the seal, helps file the complaint | to build |

Agent 9, a Caller-ID checker (160-series numbers, displayed caller name), comes after submission.

## 2. Methodology

**Safety design:**
- Agents 1–7 run in a fixed order during the call.
- The verdict comes only from the deterministic Judge.
- A claim counts only if the caller's quoted words are in the transcript.
- Suspicious behaviour (secrecy, impersonation, a link) is reported separately from verified requests or threats.
- No evidence means SAFE.

**Evaluation, three levels, reported honestly:**

1. **Text level, done.** On 44 hand-written Telugu calls, the scam ceiling is 22/22 and no genuine call is flagged. On held-out ICFD-31k English/Hinglish calls, the code-only bounds are 76/100 scams and 69/100 genuine safe. All of these were written by us or have been seen, so they are not real-world accuracy.
2. **Audio level, next.** Timbre voices ICFD calls in two voices. Prisma transcribes them back, and we measure:
   - whether the caller is identified correctly;
   - the word error rate;
   - whether the verdict survives speech-to-text.
3. **Telugu audio, the real test.** Team members act out a few Telugu calls on a real phone: 2 scams and 2 genuine. These also become the demo footage.

**Rules for the numbers:**
- Never tune on a test set.
- Report every number with what it is: bound, seen or held out.

## 3. Credit budget (5,000 programme credits)

The price per Timbre character and per Prisma minute is not published. The smoke test (step 1 below) measures it before anything else spends credits.

| Use | Share | Notes |
|---|---|---|
| Smoke test + development | 5% | One short sentence, then real debugging only |
| Audio evaluation (ICFD, Timbre + Prisma) | 30% | 6 calls first; more only if credits allow |
| Telugu acted calls (Prisma) + Guardian warnings (Timbre) | 25% | Short clips |
| Demo video takes | 20% | Rehearsals replay cached results, so they cost nothing |
| Reserve | 20% | For the live judge demo and reruns |

How we save credits:
- Every Timbre clip and Prisma transcript is saved and never regenerated.
- All code is first tested offline against recorded responses.
- The Telugu warnings are short (one sentence each) and cached per tactic.
- The screen can replay a saved run.

## 4. Timeline

| Day | Work | Done when |
|---|---|---|
| **Mon 3 Nov** | Smoke test (credit cost measured), 6 test calls voiced, Listener live check | Caller identification and WER numbers |
| **Tue 4 Nov** | Guardian voice (Timbre), Notary (OpenTimestamps seal + verify), full pipeline on Kaggle with Evon | One call goes audio → verdict → spoken Telugu warning → seal |
| **Wed 5 Nov** | Demo screen (Gradio on Kaggle). Team records 4 Telugu calls; run them end to end | Screen shows transcript, proof lines, warning, complaint, seal |
| **Thu 6 Nov** | **Record and edit the demo video; publish the LinkedIn/X post** | Post live, so engagement has 4 days to build |
| **Fri 7 Nov** | Kavach MCP server + Evon Family assistant | Family question answered in Telugu, seal verified through MCP |
| **Sat 8 Nov** | Telugu results table, written explanation, repository README | Draft submission complete |
| **Sun 9 Nov** | Buffer: fixes, second post or reply thread with results | |
| **Mon 10 Nov** | Submit before evening (not at 23:59) | Submitted |

## 5. Demo video (60–90 s)

| Time | Shot |
|---|---|
| 0–8 s | Hook: an elderly woman gets a call from "SBI head office" about her KYC |
| 8–35 s | The call plays. The transcript appears with caller and listener lines. Kavach flags SCAM and highlights the exact lines: OTP request, account threat |
| 35–45 s | Timbre speaks the Telugu warning: "అమ్మా, ఇది మోసం కాల్…" |
| 45–55 s | The evidence is sealed on Bitcoin. "Verify": the original passes, an edited copy fails |
| 55–75 s | The daughter asks the Evon assistant in Telugu what happened; it answers and hands over the 1930 complaint |
| 75–90 s | Closing card: Prisma + Evon + Timbre, all Gnani; the eight agents; the code-checked verdict |

- **Footage:** screen recording of the real screen running real calls; no mock-ups.
- **The call:** a team-acted Telugu call (preferred) or a Timbre-voiced one, labelled as such.
- **Captions** in English, because the warning is in Telugu.

## 6. Risks

| Risk | Plan |
|---|---|
| Credits run out | Smoke test measures cost first; caching; reserve 20% |
| Kaggle GPU quota (about 30 h/week) and 27-min build per session | Start the session early on run days; one long session for the video |
| Prisma on Telugu–English code-mixing is untested | Test on 5 Nov with the acted calls; bias_list for words like OTP, UPI, KYC |
| Evon misses tactics (6 of 44 in v3.4) | Red lines in code; report misses honestly |
| Post goes out late | Video and post are fixed for 6 Nov; everything else is optional around them |

## 7. What the team needs to do

- **Record 4 Telugu calls on 5 Nov** (2 scam, 2 genuine), each under 1 minute, scripts from our 44 calls. Use stereo if possible (caller on one side), otherwise mono.
- **Approve and publish the post on 6 Nov.**
- **Add the Gnani key as a Kaggle Secret named `GNANI`** before the 4 Nov Kaggle run.
