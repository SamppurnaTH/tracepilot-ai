# Demo video script (3 minutes)

One message, shown rather than told: **every fix comes with proof, and when TracePilot can't prove one, it tells you.**

About 420 spoken words at a calm pace. Waiting on the model is cut, never sped up silently: say "we've cut the wait" the first time. Everything shown is a real run, live or recorded; recordings are labelled as replays on screen.

## Before you record

- Start the **Orders live run first** (shot 2) and record it from the start; it takes 2–4 minutes and finishes while you show the other scenes.
- Open these tabs in advance, in order:
  1. https://tracepilot-ai.vercel.app (landing)
  2. https://tracepilot-ai.vercel.app/examples
  3. https://tracepilot-ai.vercel.app/run?id=checkout (finished checkout run)
  4. https://tracepilot-ai.vercel.app/run?id=refunds (finished refunds run)
  5. https://tracepilot-ai.vercel.app/results (reviewer benchmark section)
  6. https://github.com/SamppurnaTH/tracepilot-ai/blob/main/eval/blind/RESULTS.md (blind study)
- Check the live backend: the sidebar says "Live backend connected". If it doesn't, use **Watch run** instead of **Run live** and say "a recorded run".
- Screen: 1920×1080, browser zoom 110%, bookmarks bar hidden, notifications off. No `.env`, terminal with keys, admin passwords or email addresses on screen.

## Shot list

| # | Time | Screen and action | Narration |
|---|---|---|---|
| 1 | 0:00–0:15 | **Landing page.** Hold on the headline, then scroll slowly to the stats. | "AI can write a patch in seconds. But a patch that makes the tests pass isn't the same as a fix. TracePilot is an AI debugger that proves its fix, or tells you when it can't." |
| 2 | 0:15–0:45 | **Example scenarios → Orders API → Run live.** The run page opens: point at the steps streaming in, the **"Muse Spark is thinking"** note and the ticking clock. | "This is a live run. I give it an incident: intermittent 500 errors and a data-exposure report. Meta's Muse Spark investigates inside a locked-down Docker sandbox. You can watch it reason: here it's tracing the 500s and the cross-user reads. It forms hypotheses and checks each one against the code, the logs and real requests. We'll come back to it." |
| 3 | 0:45–1:15 | **Checkout replay.** Open **Evidence** (the customer's screenshot), then **Tests** (the new reproducing test, failing first), then **Patch**, then **Summary** (tests 5/6 → 6/6). | "Here the only evidence is a customer's screenshot. Muse Spark reads the cart and the wrong discount straight from the image, and writes a test that reproduces the bug. That test must fail on the current code, or it's thrown away. Then it patches the code, and the harness, not the model, reruns every test to decide whether the fix worked." |
| 4 | 1:15–1:35 | **Refunds replay.** Show the **No code change needed** verdict and the **Recommendation** tab. | "Sometimes the right fix isn't in the code at all. Refunds broke after a deploy because a provider's API key expired. Instead of inventing a patch, TracePilot says: no code change needed, and tells operations exactly what to do." |
| 5 | 1:35–2:05 | **Results page**, reviewer benchmark: show one test-gaming case (ownership check only for the order the test uses) and its **reject** verdict. | "Passing tests can still hide a bad patch. So a second Meta model, Muse Spark Open, an open-weight model on Baseten, reviews every patch cold, without seeing the investigation. This patch passes every test but only blocks the one order the test checks. The reviewer rejects it. It rejected all six cheating patches we generated, and when it objects, the patch goes back for another round." |
| 6 | 2:05–2:30 | **GitHub: blind study results.** Highlight the round 2 table: tomlkit and inflect **fixed**, the others honestly **not verified** or **rejected**. | "Does it work on real code it has never seen? We took seven real bugs fixed this autumn in projects like click, packaging and tomlkit, hid the developers' own tests, and let TracePilot try. It fixed two of seven, judged by the hidden tests. On the rest it said 'not verified' instead of claiming success, and we publish every failure." |
| 7 | 2:30–2:50 | **Back to the Orders live run**, now finished: **Fix verified**, tests 3/5 → 5/5, reviewer **Approved**, and the **Execution time** row with its breakdown. | "Back to our live run: both root causes found, a missing coupon check and a missing ownership check. Tests go from three of five to five of five, the independent reviewer approves, and you can see exactly where every second went." |
| 8 | 2:50–3:00 | **Landing page** or logo, with the URL on screen. | "TracePilot AI, built on Meta Muse Spark and Muse Spark Open. Every fix comes with proof, and when it can't prove one, it tells you. Try it live at tracepilot-ai.vercel.app." |

## Editing notes

- Cut the waiting in shot 2 and between shots; say "we've cut the wait" once, in shot 2 or 7.
- Add on-screen captions for the key numbers: "3/5 → 5/5", "6 of 6 cheating patches rejected", "2 of 7 real bugs, judged by hidden tests".
- If the Orders live run doesn't verify, keep it and say so: "this run wasn't verified, and TracePilot says so." Then show a recorded verified run. Honesty is the pitch.
- Don't claim speed or cost advantages on camera: the research shows those hold only for the original pilot.
- Keep the final cut at or under 3:00. If it runs long, trim shot 5's second sentence first.

## Follow-up demonstrations (for judges' questions)

1. `/run?id=wrap-review`: a test-green patch where the reviewer reported a real hang; it's marked **Review required** and blocked from `--apply`.
2. `/evidence`: raw observations, intervals, reviewer mistakes and limits.
3. `/admin` with a viewer account: roles, team management and the audit log.
4. An unsupported (Node) project is refused with a clear error before any paid model call.

## Preflight checklist

- Live backend healthy, with capacity left today (2 at a time, 40 a day).
- Refunds, Checkout, Results and the blind-study page load; the checkout screenshot shows.
- Statistics rebuild unchanged: `python backend/scripts/judge_evidence.py`; tests and frontend build pass.
- Check the organizer portal for the final video length and upload requirements.
