# Kavach role pipeline on Evon v3.3 (Q4_K_M, Kaggle 2× T4): iterations, 2026-10-25

Kaggle notebook: "Kavach - Evon v3.3 on 2xT4 (llama-server test)". Local notebooks: `evon_kavach_t4_test_v2.ipynb` (v2), `evon_kavach_t4_test_v3.ipynb` (v3.1), `evon_kavach_t4_test_v32.ipynb` (v3.2), `evon_kavach_t4_test_v33.ipynb` (v3.3, rejected), `evon_kavach_t4_test_v34.ipynb` (v3.4, current). Thinking off throughout. All test calls are short, hand-written Telugu–English transcripts, not audio.

## Results by version

| Version | Design | Scams caught | Genuine left alone | Notes |
|---|---|---|---|---|
| v1 | free-text Prosecutor/Defender, LLM Judge | 1/1 | 0/1 | warning echoed the caller's words |
| v2 | neutral prompts, grammar-forced evidence *list*, LLM Judge | 7/7 | **0/7** | Evon always filled the list; Judge said SCAM 0.95 for everything |
| v3 | checklist Prosecutor, code verifies quotes and cues, rule verdict | A 7/7, B 1/3 | A 7/7, B 1/3 | held-out set B exposed exact-quote and money-cue flaws |
| v3.1 | v3 + fuzzy quote match + remote-payment money cue | A 7/7, B 2/3, C 2/2 | A 7/7, B 3/3, C 2/2 | 23/24 overall |
| v3.2 | v3.1 + PIN-to-receive red line in code + money verified over the whole call + wider OTP/money item wording | **A 7/7, B 3/3, C 0/2, D 4/6** | **A 7/7, B 3/3, C 2/2, D 5/6** | 31/36; both targeted misses fixed |
| v3.3 (rejected) | Prosecutor answers with caller-line numbers instead of quotes | A–D 15/18, E 2/4 | A–D 18/18, E 3/4 | 38/44, but Evon marked nearly every item present with non-existent lines (38 invalid claims) |
| **v3.4** (current) | v3.2 quotes + clause-level negation, informal negations, digit/card cues, no fee-only remote payment, remote-app/APK/screen-share red line | **A 7/7, B 2/3, C 1/2, D 4/6, E 2/4** | **22/22** | 38/44; every genuine call left alone; all 6 misses are Evon quoting in translation, quoting the wrong line, or claiming nothing |

Set A (14 calls) was used to design the rules; set B (6) was seen in v3; set C (4) was fresh in v3.1; set D (12) was fresh in v3.2; set E (8) was fresh in v3.3. Every set is seen once a run has been inspected, so the only honest held-out numbers are each set's first run: **C 4/4 (v3.1), D 9/12 (v3.2), E 5/8 (v3.3)**.

## v3.2 (2026-10-25/26): the two targeted misses

- **Army/OLX QR scam: fixed, but by code, not Evon.** Evon still did not flag "scan the QR and enter your UPI PIN" as a PIN request. The new red line (a caller line that asks for a PIN together with scanning a QR or receiving money) caught it, and caught the two new set-D variants (refund QR, "wrong transfer" collect request). It did not fire on any genuine call, including "money credited, don't tell anyone your UPI PIN".
- **Grandson emergency: now SCAM.** "Doctor కి 20,000 కట్టాలి" is verified as a money request because another caller line names Google Pay.
- **New failures in v3.2:**
  - *Set C regressed (0/2).* Evon claimed only a money request for the re-delivery-link and meter-APK calls, quoting a translated line or the wrong line. It did not claim the link or the APK install, which it had found in v3.1, so this is run-to-run variance in Evon.
  - *Set D misses.* `police_custody_bribe`: Evon quoted in English/Hindi ("…jail ki bhej dunga"). `job_registration_fee`: Evon gave the job-offer line instead of the fee line. `school_fee_reminder` (genuine) was flagged, because "fee" counted as proof of a remote payment.
- 15/15 warnings mostly Telugu, 0/15 echo the caller; median 6.1 s, max 8.8 s to verdict.

## v3.3 (rejected): line numbers instead of quotes

Making Evon point at "C1, C2, …" instead of copying the line should have stopped the translated quotes. Instead Evon marked nearly every checklist item present and filled lines with the item's position (C3…C9 on 3-line calls). There were 38 invalid claims, and fresh set E scored 5/8. Quotes stay.

Bugs v3.3 exposed (they apply to v3.2 too):
- **Negation is checked over the whole line, which is too coarse.** "…ఎవరికీ చెప్పకండి, లేకపోతే arrest చేస్తాం" (don't tell anyone, otherwise we arrest you) is thrown out as "negated" because of చెప్పకండి, so real arrest threats in the CBI and police-custody calls are lost. The fix is clause-level negation, but whole-line negation is also what currently protects `fraud_alert` ("we blocked your card. We won't ask for OTP"), so the change needs a rerun.
- **The negation words miss the informal forms.** "OTP అడిగితే చెప్పకు" (a daughter warning her mother) is flagged as an OTP request.
- **The OTP cue misses "4 అంకెల number చెప్పండి"** (tell me the 4-digit number), and the card cue misses "the 3 numbers on the back of the card".

## v3.4 (2026-10-26): code-side fixes, quotes kept

`evon_kavach_t4_test_v34.ipynb`. Prompts are unchanged from v3.2; only the verification code and the red lines changed:

- **Negation per clause.** The quote is split on `, . ; ! ?`, and a cue counts as negated only if every clause that contains it has a negation word. The same rule applies to the red lines and to the call-wide remote-payment check (so "Google Pay లో పంపు, ప్లీజ్ ఎవరికీ చెప్పకు" still proves a remote payment).
- **"Already done" is not a threat.** "మీ card ని మేము block చేశాం" (we have blocked your card) is rejected as a threat. Whole-line negation used to cover this case by accident.
- **More negation words:** చెప్పకు, చెప్పొద్దు, అడిగితే, ఇవ్వకండి, ఇవ్వొద్దు, చేయకండి.
- **Cues:** OTP adds అంకెల/digit ("4 అంకెల number"); card details adds expiry and "వెనుక ఉన్న 3 …" (the 3 numbers on the back).
- **Remote payment no longer accepts a fee alone.** It now needs a payment app, transfer, NEFT/IMPS, online, a link, "processing" or an account/number to pay into.
- **Second red line:** a remote-control app (AnyDesk, TeamViewer, QuickSupport), an APK, or screen sharing. Plain "download" is not a red line, and an *optional* app suggestion ("కావాలంటే … download చేసుకోవచ్చు") is rejected as Evon evidence too, so a bank pointing to its own Play Store app is not flagged.
- **Power-cut warning** now matches "connection".

Local checks before the run, using code only:
- All 21 targeted verify cases passed.
- **Worst-case Evon test:** every tactic was claimed on every caller line of each genuine call, and none of the 22 genuine calls reached SCAM.
- **Best-case test:** each of the 22 scams has at least one line that verifies as a request or threat.

These are properties of the rules, measured on the same self-written calls.

### v3.4 Kaggle run (2026-10-26, fresh session, all 44 calls once)

- **Genuine calls: 22/22 left alone.** This includes school_fee_reminder, daughter_otp_warning and bank_official_app (all fixed by v3.4), and fraud_alert still passes after the move to clause-level negation.
- **Scams: 16/22 caught.**
  - The red lines decided two verdicts that Evon alone would have missed: army_qr (PIN-to-receive) and meter_apk (APK).
  - Red lines also fired on refund_qr, wrong_transfer_collect, remote_access and screen_share_bank.
- **All 6 misses are on the Evon side, not the code:**
  - **Translated quotes (4 calls):**
    - sim_deactivation: "…deactivated in 2 hours. Please act now…"
    - redelivery_fee_link: "I will send you an SMS with a link, pay 25 rupees…"
    - police_custody_bribe: "This thing inside house don't tell, otherwise jail send", a word-by-word English gloss.
    - courier_address_otp: Evon's "quote" was a piece of the prompt and an English rendering of the transcript.
  - **Wrong line:** for job_registration_fee, Evon quoted the job-offer line for both money and OTP.
  - **No claims at all:** cbi_video_call. Clause-level negation would have kept its arrest threat, but Evon never claimed it.
- Median 6.1 s and max 7.5 s to verdict. Warnings: 16/16 mostly Telugu, 0/16 echo the caller.
- 44 claims were rejected by code and 25 accepted.

Conclusion: the code side is now sound on these calls. The remaining gap is Evon's checklist recall and its habit of translating quotes, which run-to-run variance makes worse. v3.3 already showed that asking for line numbers in a single prompt fails. One option not yet tested is to ask Evon per caller line ("does this line do any of these?") so the code always knows the line.

## v3.1 pipeline

1. **Prosecutor (Evon):** yes/no checklist over 9 tactics, with the caller's exact words for each yes.
2. **Defender (Evon), in parallel:** genuine-call signals with quotes, shown to the family.
3. **Verification (code):** a claim is kept only if its quote matches a *caller* line (≥ 60% of words), contains a cue for that tactic, and is not negated ("we never ask for OTP", "don't share details on the phone", cash on delivery).
4. **Verdict (rule):** any verified money / OTP / card-details / remote-app request or threat → SCAM; only secrecy, impersonation or a link → SUSPICIOUS; nothing verified → SAFE.
5. **Evon** writes a one-sentence reason, the Telugu warning (from verdict and tactics only, never the transcript; SAFE calls stay silent) and the 1930 complaint draft.

Every flag is backed by a quote that is verifiably in the transcript, which is also a good story for the pitch.

## v3.1 numbers

- Median 6.5 s, max 7.3 s from transcript to verdict (Prosecutor ‖ Defender, then rule).
- Spoken warnings: 11/11 mostly Telugu script, 0/11 repeat the caller's words.
- Code rejected 17 of Evon's 36 tactic claims (invented or wrongly labelled lines).
- VRAM 11.1 + 12.5 GB of 15 + 15 GB.

## Known gaps (after v3.4)

- **Evon's checklist is unstable between runs:** the same call can get a different set of claimed tactics (set C went from 2/2 to 0/2). Evon also quotes in translation, which the quote check rightly rejects. The deterministic red lines are what made the QR and PIN scams reliable.
- ~~The negation and cue bugs listed under v3.3~~ and ~~the power-cut warning naming the account~~: fixed in v3.4.
- **Self-written tests.** All 24 calls were written by the same author as the rules; set C has only 4 calls. Before quoting accuracy anywhere, run the team-acted Telugu calls (through Prisma, not hand transcripts) as a blind test.
