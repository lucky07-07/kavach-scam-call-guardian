# Kavach — submission pack (Gnani AI Great Indian AI Internship Challenge 2026)

Deadline: **10 November 2026, 23:59 IST**. Submit during the day.

## Checklist (in this order)

- [ ] **Publish the LinkedIn post** (text below) with the trailer `data/demo/trailer/kavach_trailer.mp4` (0:59, made for the 60-second "Demo Day Drop" award) attached and the hashtags #GnaniAI #GreatIndianAIInternshipChallenge. It must be live before submitting. Shortlisting depends on its engagement, so post today if possible and ask friends to engage.
- [ ] Optional: post the short X/Twitter version too.
- [ ] Fill in **Team and contributions** below (2 lines).
- [ ] Submit on the challenge page:
  - the written explanation below;
  - **Project URL (live link):** https://kavach-scam-call-guardian.vercel.app: the pitch, both videos and the real Kavach screen replaying three saved Telugu calls. Code: https://github.com/lucky07-07/kavach-scam-call-guardian. Its README links the 1-page solution pitch, [PITCH.md](../PITCH.md) (PDF: `docs/Kavach_pitch.pdf`);
  - **Video demo (2–3 min):** `data/demo/kavach_demo_full.mp4` (2:21: the scam call and its cost, the 8 agents, then one real run of the app with narration: warning, family alert, complaint, seal, a genuine call, the family asking). Upload it to YouTube (unlisted) or Google Drive (anyone with the link) and paste that link;
  - the trailer `data/demo/trailer/kavach_trailer.mp4` (0:60, made for the 60-second "Demo Day Drop" award);
  - the post link;
  - optionally the code repository link.
- [ ] After submitting:
  - stop the Kaggle Evon session;
  - delete the `kavach-teammate` / `kavach-dheeraj` Hugging Face tokens.

---

## Written explanation

**Title.** Kavach — a second listener that protects elderly Telugu speakers from scam calls

**Problem.** Phone scams ("your KYC has expired, tell me the OTP", fake police "digital arrests", refund QR codes) target
elderly people who answer in their own language and trust an official-sounding voice. Caller-name display and spam lists
help only before the call. Once a scammer is talking, nobody is there to say "stop, this is a scam" in words the listener
understands, and afterwards the family has no trustworthy record to give the police or the bank.

**Target users.**
- **Listeners:** elderly Telugu speakers, who often take calls alone.
- **Their families:** they want to know what happened and to file a complaint.
- **Later:** banks and police, who need evidence they can trust.

**What Kavach does.** Eight agents work on one call:
1. **Listener (Gnani Prisma v2.5)** transcribes the call and separates caller from listener, in Telugu, English or Hinglish.
2. **Prosecutor and 3. Defender (Gnani Evon v3.3)** argue both sides, quoting the caller's exact words.
4. **Judge (code, never the LLM):** a scam tactic counts only if the caller's own words in the transcript prove it, and it isn't negated ("we will never ask for your OTP"). Rule-based red lines catch tricks the LLM misses, such as entering a PIN to "receive" money, or remote-access apps.
5. **Guardian (Evon + Gnani Timbre):** speaks a short warning in the listener's language, Telugu or Hindi. Code checks Evon's text first: mostly Telugu, never repeating the caller, no numbers or links. Otherwise an approved warning is used. **At the same moment it alerts the family**: a message in Telugu or Hindi built in code from the verdict and the verified tactics ("Amma just got a scam call; the caller asked for her OTP… call her now"), voiced by Timbre as a voice note and queued for delivery. Genuine calls send nothing.
6. **Reporter (Evon):** drafts the 1930 / cybercrime.gov.in complaint.
7. **Notary:** seals the evidence packet (audio hash, transcript, evidence, verdict, warning, rules version) with SHA-256, a hash chain and OpenTimestamps on Bitcoin. Only 32 bytes leave the device, and a one-byte edit fails verification.
8. **Family assistant (Evon over a Kavach MCP server):** after the call the family asks in Telugu ("what was amma's last call?"). Evon answers from read-only MCP tools (list_incidents, get_incident, verify_seal, draft_complaint), so it can explain and verify but never change a verdict.

**Gnani models used.**

| Model | Use |
|---|---|
| **Prisma v2.5** | Batch STT with two-speaker diarization; a REST pass per turn; Telugu (te-IN) and English (en-IN); word boosting for banking terms |
| **Evon v3.3** | Self-hosted (our own Q4_K_M GGUF on Kaggle 2× T4 via llama-server, thinking off): Prosecutor, Defender, explanation, Telugu warning text, complaint fields, family assistant |
| **Timbre** | v2.5, voice Lehara, Telugu, slowed to 0.9: the spoken warning. v3.0 two-voice test calls for evaluation and the demo |

**What we measured.** All calls are synthetic: our scripts and ICFD-31k, voiced with Timbre. The samples are small.
- **End to end with real Evon, Telugu calls:** 3/3 (two scams flagged, the genuine bank call left alone).
- **End to end with real Evon, English/Hinglish calls:** 5/6 (all 3 genuine left alone; one scam missed because Evon picked the wrong tactic).
- **Text level, 44 Telugu calls:** no genuine call flagged (22/22).
- **Hindi calls:** speakers separated 3/3 and the right code-only verdict on all 3; the end-to-end Evon run is pending.
- **Verdict time:** about 10 s.
- **When to warn (RL experiment):** a policy trained on 6,000 ICFD-31k calls to choose the moment to warn ties the Judge's own rule on 2,000 held-out calls (25 fewer false alarms per 1000, 11 fewer timely warnings per 1000, gain within noise). Q-learning and fitted Q-iteration did worse. The Judge's rule stays in charge.
- **Seal:** a seal made on 3 Nov was confirmed on Bitcoin (block 974,389), checked against the block's Merkle root.

**What we learned from real audio.**
- **Loanword script.** Prisma's Telugu model writes English loanwords in Telugu script ("ఓటీపీ"), so Kavach writes them back in Latin before reasoning.
- **Dropped words.** Batch transcription can drop the last words of a turn, including the "not" in "we will **not** ask for your PIN". A per-turn REST pass restores them.
- **Code-checked LLM output.** Letting the LLM choose tools freely mixed up calls, so the family assistant's lookups are planned in code and Evon writes the answer.

**Limits and next steps.**
- **Family alert delivery:** the alert is built, voiced and queued; connecting an SMS/WhatsApp gateway is next.
- **Live listening:** today Kavach analyses a recorded call. Next is live streaming with a guardian device.
- **Caller-ID checker (agent 9):** compare the caller's claimed identity with the number's 160-series and displayed name.
- **Real calls:** a blind test on real calls acted by volunteers.

**Team and contributions.** *(fill in)*
- Anil Kumar — …
- Dheeraj Tadi — …

---

## LinkedIn post (attach the demo video)

> **My grandmother can't spot a scam call in English. So we built one that speaks Telugu.**
>
> "Your KYC has expired — tell me the OTP." Scams like this target elderly people who answer alone, in their own language.
>
> For the #GreatIndianAIInternshipChallenge we built **Kavach**, a second listener on the call, built entirely on @Gnani AI models:
> 🎧 **Prisma** hears the call and separates caller from listener, in Telugu and English
> ⚖️ **Evon** argues both sides like a courtroom: one agent says scam, one says genuine, each quoting the caller
> 🧑‍⚖️ The **verdict is decided by code**: a tactic counts only if the caller's own words prove it, so genuine bank calls stay silent
> 🔊 **Timbre** warns the listener in Telugu: "జాగ్రత్త, ఇది మోసం కాల్…"
> 📲 And it **alerts the family** at once, with a Telugu voice note: "Amma just got a scam call. Call her now."
> 📝 It drafts the 1930 complaint and **seals the evidence on Bitcoin**, so nobody can edit it later
> 💬 After the call, the family asks Kavach in Telugu over MCP tools: "what was amma's last call?"
>
> Eight agents, one job: keep the listener safe.
>
> What surprised us: Telugu speech recognition writes "OTP" as "ఓటీపీ", and one dropped word can turn "we will **not** ask for your PIN" into a scam. Real audio teaches you things text never does.
>
> Demo below 👇 Would you want this on your parents' phone?
>
> #GnaniAI #GreatIndianAIInternshipChallenge #VoiceAI #Telugu #ScamAwareness #AIforGood

## X / Twitter (short)

> Built **Kavach** for #GreatIndianAIInternshipChallenge: a second listener that catches scam calls and warns elderly listeners **in Telugu**. Gnani Prisma hears, Evon argues both sides, code decides, Timbre warns, evidence sealed on Bitcoin. Demo 👇 #GnaniAI
