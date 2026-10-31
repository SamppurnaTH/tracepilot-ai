# Demo video script (3 minutes)

**One message: every fix comes with proof, and when TracePilot can't prove one, it tells you.**

Six shots, about 230 spoken words: a relaxed pace with room to breathe. No live waiting: every shot uses a finished recording on the live site, so nothing depends on the model's speed while filming.

## Open these tabs first

1. https://tracepilot-ai.vercel.app
2. https://tracepilot-ai.vercel.app/run?id=checkout
3. https://tracepilot-ai.vercel.app/run?id=refunds
4. https://tracepilot-ai.vercel.app/results
5. https://tracepilot-ai.vercel.app/run?id=tomlkit-599
6. https://github.com/SamppurnaTH/tracepilot-ai/blob/main/eval/blind/RESULTS.md

## The six shots

| # | Time | On screen | Say |
|---|---|---|---|
| 1 | 0:00–0:15 | Landing page headline | "AI can write a patch in seconds. But passing tests isn't proof. TracePilot proves the fix, or tells you it can't." |
| 2 | 0:15–0:50 | **Checkout**: Evidence (screenshot) → Tests (new failing test) → Summary (5/6 → 6/6) | "The only clue here is a customer's screenshot. Meta's Muse Spark reads it, writes a test that fails, then fixes the code. Our harness, not the model, reruns every test: five of six becomes six of six." |
| 3 | 0:50–1:10 | **Refunds**: "No code change needed" | "Here the cause is an expired API key. TracePilot changes no code, and tells you what to fix instead." |
| 4 | 1:10–1:40 | **Results**: scroll to **Second-opinion benchmark** and hold on **"8/8 test-gaming patches rejected"** | "Passing tests can hide a cheat, like a patch that only blocks the one order the test checks. A second Meta model, Muse Spark Open, reviews every patch. It rejected all eight cheats in our benchmark." |
| 5 | 1:40–2:30 | **tomlkit**: Patch (one line) → Summary (verified, approved, time breakdown) → 3 s on the blind-study table | "This is a real bug in a real library, fixed this October. We hid the developers' tests. TracePilot found it and wrote a one-line fix that passes them. Across seven real bugs it fixed two, and never claimed a fix it couldn't prove. You can see where every second went." |
| 6 | 2:30–3:00 | Landing page, URL on screen | "TracePilot AI, built on Meta Muse Spark and Muse Spark Open. Proof, not just patches. Try it live at tracepilot-ai.vercel.app." |

## Recording tips

- 1920×1080, browser zoom 110%, bookmarks bar and notifications off.
- Click, pause one beat, then speak. Silence between shots is fine; it makes the cut easy.
- Captions for the three numbers: "5/6 → 6/6", "every cheat rejected", "2 of 7 real bugs fixed".
- Never show `.env`, API keys, passwords or email addresses.
- If a shot runs long, shorten what you say, not the screen time.

## If judges ask for more

- `/run?id=wrap-review`: tests pass, but the reviewer finds a real hang, so it's marked **Review required**.
- `/evidence`: raw data, intervals and limits.
- **Run live** on any web-service example: about 2–4 minutes, with Muse Spark's reasoning streaming.
