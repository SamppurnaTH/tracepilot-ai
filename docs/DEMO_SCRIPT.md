# 90-second pitch with inspectable recordings

Use labelled recordings at increased playback speed. This is a presentation of real saved investigations, not two live runs completed in 90 seconds. Keep one live run ready for follow-up; do not spend the pitch waiting on inference.

| Time | Screen / action | Narration |
|---|---|---|
| 0–10 s | Landing hero | “AI can write a patch. TracePilot asks whether the patch is proven—or whether changing code is the wrong move. Proof, not patches.” |
| 10–30 s | Refunds → Watch run → result | “Refunds broke after a deploy. The logs show an expired payment-provider key. TracePilot rejects the tempting code fix and gives operations the action to take. This is honest abstention from code changes.” |
| 30–60 s | Checkout recording → screenshot evidence → generated test → diff → test results | “The customer’s screenshot contains the missing evidence. Muse Spark reads it, reproduces the wrong discount, and makes the test fail first. The harness—not the model—reruns the tests after the patch.” |
| 60–75 s | Comparison → reviewer gaming cases | “Passing tests can still hide a bad patch. Muse Spark Open reviews the facts cold. Here a patch checks ownership only for the exact order ID in the test. It passes those tests, but the reviewer rejects it.” |
| 75–90 s | Evidence room / comparison limits | “Across our small authored set, TracePilot used fewer tokens and less time than our plain-agent baseline. We publish raw observations, wide confidence intervals, reviewer mistakes and limits. The next step is a human-reviewed GitHub incident-to-PR workflow.” |

## Follow-up demonstrations

1. Open the real `/run?id=wrap-review` recording to show test-green code with a reviewer-reported hang, now marked Review required and blocked from CLI application. Then show Inventory's reference patch receiving **concerns**, then the exact reviewer explanation. Do not call this a rejection or claim a second-round correction that is not in the recording.
2. Show the adversarial-log observation and the deterministic tool-denial test. State the isolation actually used.
3. Show an unsupported Node project being refused with a clear error, before any paid model call.
4. Show the sample manually triggered CI workflow and its report/patch artifact; say that an installed GitHub App and automatic PR creation are future work.

## Preflight

- Confirm live backend health and remaining capacity before filming. If a live start is capped/down, retain the automatic recording banner in the video.
- Open Refunds, Checkout, results and evidence tabs in advance. Confirm screenshot and raw report load.
- Do not expose API keys, admin passwords, private customer source or user email addresses in the recording.
- Rebuild statistics with `python backend/scripts/judge_evidence.py`; run tests and frontend build. Keep benchmark files unchanged unless real new runs are added.
- Check the organizer portal for final video/upload requirements. This script's duration is a presentation choice, not an asserted event requirement.
