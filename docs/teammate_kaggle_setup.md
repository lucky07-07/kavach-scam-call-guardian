# Running Evon for Kavach on your Kaggle account

Kavach's AI model (Gnani Evon) runs on Kaggle's free GPUs. My weekly quota is used up, so it needs to run on your account for this week. Your account has its own 30 GPU hours, and each run uses about 1–3 hours.

## Anil does first (once)

1. Create a **read-only Hugging Face token** at huggingface.co → Settings → Access Tokens → *Create new token* → **Fine-grained**:
   - *Repositories permissions*: add `anilkumarlucky/gnani-evon-v3.3-30b-a3b-GGUF` and tick **Read access to contents of selected repos**;
   - also tick **Read access to contents of all public gated repos you can access** (Evon's chat template comes from Gnani's gated repo).
   - Name it `kavach-teammate`. Delete it after 10 Nov.
2. Send the token and the file `evon/evon_server_kaggle.ipynb` to the teammate **privately** (WhatsApp/email). Never post the token anywhere public.

## Teammate does (about 5 minutes, then ~30 minutes of waiting)

1. **Kaggle account ready for GPUs:** kaggle.com → your profile → Settings → **Phone verification** must be done. Without it, Kaggle gives no GPU and no internet.
2. **Import the notebook:** kaggle.com → Code → **New Notebook** → *File* → **Import Notebook** → choose `evon_server_kaggle.ipynb`.
3. **Session options** (right-hand panel, or *Settings*):
   - Accelerator: **GPU T4 x2** (not P100, not a single T4);
   - Internet: **on**.
4. **Secret:** *Add-ons* → **Secrets** → *Add secret*:
   - name `HF`, value = the token from Anil;
   - make sure its box is **ticked for this notebook**.
5. **Run all** (or press ⏩). The first run builds the server, which takes about 25–30 minutes. Keep the browser tab open.
6. When cell 6 finishes, it prints two lines like:

   ```
   KAVACH_EVON_URL=https://something-random.trycloudflare.com
   KAVACH_EVON_KEY=AbC123...
   ```

   Send both lines to Anil **privately**. They change every session.
7. Leave the notebook running while Anil works. Cell 7 prints a health line every 10 minutes; "public health 200" means all is fine.
8. **When Anil says done, stop the session** (the power/stop button at the top) so your GPU hours aren't wasted.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Set Accelerator to GPU T4 x2" | Step 3: pick GPU T4 x2, then Run all again |
| An error mentioning `HF` or 401 / 403 at cell 4 | The secret is missing, not ticked for this notebook, or the token lacks access: redo step 4 or ask Anil for a new token |
| "#### STOPPED at # 3. Build" | Send Anil a screenshot of the last 30 lines |
| The session stopped by itself | Kaggle stops idle sessions after a while: Run all again (the build repeats, ~30 min) |

## This week's sessions (planned)

| Day | Purpose | GPU hours |
|---|---|---|
| Tue 4 Nov | Test calls end to end | ~2 h |
| Wed 5 Nov | Telugu acted calls, demo screen | ~2–3 h |
| Thu 6 Nov | Record the demo video | ~2 h |
