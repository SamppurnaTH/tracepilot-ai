# Meta hackathon alignment

Checked October 29, 2026 against [Meta's event page](https://dev.meta.ai/events/global-hackathon) and the organizer's [Hackathon Terms & Conditions / Official Rules](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver), read in the rendered browser.

The rules' project rubric is **Impact 30%, Use of Meta AI Tooling 25%, Technical Depth & Execution 20%, Demo 25%**. These are distinct from the two equally weighted application-selection criteria. The rules call for projects built with Meta AI products; they do not require a competing-vendor baseline. We keep the submitted inference flow on Meta models.

| Rubric | TracePilot evidence | Honest limitation |
|---|---|---|
| Impact | Developer/SRE incident → reproduced failure → reviewed patch or operational recommendation; saved Python and real-project Java runs | No customer adoption or measured developer-hours-saved study. Model latency is not a measurement of engineering time saved. |
| Meta tooling | Muse Spark multimodal screenshot investigation, structured hypotheses and phase-gated tools; Muse Spark Open cold-context patch review and one retry after rejection | Both model roles are Meta; separate context reduces transcript anchoring but cannot prove statistically independent blind spots. |
| Technical execution | Harness-owned before/after outcomes, offline Docker runtime, immutable-test tool policy, role-checked APIs, exported evidence and tested deployment scripts | No GitHub App, tenant isolation, full infrastructure reproduction or production safety guarantee. |
| Demo | Refunds abstention, Checkout screenshot, authored test-gaming review; visible progress and labelled recordings on unavailable/capped live starts | The 1:45 demo video shows real recorded runs on the live site, narrated by the builder with captions. It doesn't imply that live investigations finish that fast; a live run takes about 2–4 minutes. |

Current submission deadline on Meta's page: November 4, 2026, 9 PM Eastern Time, which is **November 5, 2026, 7:30 AM IST**. Verify the portal before submission; dates can change.

Use the recorded evidence and limitations in `JUDGE_QA.md` and `eval/STATISTICS.md`. Do not claim top-five selection, model-family independence, unrun ablation results or privacy guarantees.
