# Kavach — solution pitch (1 page)

**A second listener for scam calls.** Catches scam calls in Telugu and Hindi, warns the listener, alerts the family and seals the evidence. Built entirely on Gnani AI.
PDF version: [docs/Kavach_pitch.pdf](docs/Kavach_pitch.pdf) · Videos: [60-second trailer](data/demo/trailer/kavach_trailer.mp4) · [full demo](data/demo/kavach_demo_full.mp4)

**The problem.** Indians lost **₹22,845 crore** to cyber fraud in 2024 (Ministry of Home Affairs, Lok Sabha, July 2025), about **₹62 crore a day**. The typical attack is a phone call. Someone posing as a bank, a power company or the police asks for an OTP, a payment or a remote-access app. The person most at risk is alone on the line, often elderly, and the call is in Telugu or Hindi. English-only, text-only fraud filters never hear it, and the family finds out after the money is gone.

**The solution.** Kavach sits on the call as a second listener. When the caller uses a scam tactic, Kavach:
- **warns the listener in Telugu or Hindi**;
- **alerts the family** with a text and a voice note;
- **drafts the 1930 cybercrime complaint**;
- **seals the evidence on Bitcoin**, so no one can alter it later.

Afterwards, the family can ask Kavach what happened, in Telugu.

**How it works: eight agents.**
1. **Listener** (Prisma): who said what.
2. **Prosecutor** (Evon): lists the scam tactics, quoting the caller.
3. **Defender** (Evon): lists signs that the call is genuine.
4. **Judge** (code): counts a claim only if the caller's own words prove it.
5. **Guardian** (Evon + Timbre): speaks the warning and builds the family alert.
6. **Reporter** (Evon): drafts the 1930 complaint.
7. **Notary**: a SHA-256 hash chain, timestamped on Bitcoin with OpenTimestamps.
8. **Family assistant** (Evon over MCP): answers from the sealed evidence.

**Why it can be trusted.**
- **The LLM argues; code decides.** An LLM judge flagged every genuine call. With the prosecutor/defender split and a code Judge, no genuine test call has been flagged since.
- **The caller's words never reach the listener.** Warnings and alerts are built only from verified tactics.
- **Only a 32-byte hash leaves the device.**
- **A one-byte edit fails verification** against the Bitcoin block.

**100% Gnani, sovereign AI.**

| Model | Role |
|---|---|
| **Prisma v2.5** | Speech-to-text in Telugu, Hindi, English and code-mixed speech; separates the caller from the listener. |
| **Evon v3.3** | Open-weight LLM, self-hosted. |
| **Timbre** | Speaks the warning and the family's voice note, in Telugu and Hindi. |

**Results so far (synthetic calls).**

| Result | What it measures |
|---|---|
| **22/22** | Genuine Telugu–English calls left alone |
| **16/22** | Scams caught on the same set |
| **3/3** | Telugu calls right end to end with real Evon |
| **9–12 s** | Time to a Telugu verdict |
| **120** | Automated tests passing |

Seals are confirmed on Bitcoin.

**Limits and next steps.**
- Calls are analysed after recording. Next: streaming Prisma, for warnings during the call.
- Family alerts are built, voiced and queued, but no SMS/WhatsApp gateway is connected yet.
- All test calls are synthetic.
- Next: an SMS/WhatsApp gateway, more Indian languages, and a pilot with real families.
