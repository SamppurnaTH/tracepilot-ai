# Threat model and data flow

This prototype reduces the risk of investigating **authorized, trusted-source projects**. It is not a hardened multi-tenant service for arbitrary hostile code, and container isolation is not a proof against kernel exploits.

`Repo + logs + screenshots → TracePilot harness → Meta Model API (investigator); incident + confirmed evidence + patch + changed files + test summary → Baseten/Muse Spark Open (reviewer); events + report → local/server run storage → authorized workspace readers.`

## Boundaries and evidence

| Threat | Implemented boundary | Evidence / remaining limit |
|---|---|---|
| Instructions inside logs, code or images | System prompts label them untrusted; tools are phase-gated; the model has no arbitrary shell tool and cannot set the verification result | `backend/app/agent.py`, `backend/app/reviewer.py`; `test_judge_safety.py`. Prompt text is guidance, not a security boundary; a model may still follow malicious content. |
| Editing the oracle | Application-edit tools reject existing test paths; new tests are kept only when all collected cases fail, not pass/error | `test_agent.py`, `test_java.py`. This does not establish semantic relevance of a failure, nor protect tests against malicious code executing inside the writable project copy. |
| Reading host secrets / traversal | Resolved tool paths must remain inside the copy; `.env` is not copied; sensitive environment names are stripped | `test_sandbox.py`, `test_uploads.py`. Redaction is not comprehensive DLP: secrets already embedded in source, logs or screenshots may reach the model. Remove them before upload. |
| Runtime network exfiltration or privilege escalation | Docker: no network, read-only root, non-root UID, dropped capabilities, no-new-privileges, CPU/memory/PID/time limits; only disposable project and tmp are writable | `test_docker_has_no_network`, `test_docker_root_filesystem_is_read_only`, `test_docker_runs_as_non_root`. No escape guarantee; Docker shares the host kernel. |
| Dependency installation | Dependencies are prepared in a Docker image before the offline investigation | This preparation uses network access and may execute build hooks. It is a separate, weaker boundary; do not build dependencies from untrusted uploads on a sensitive shared host. |
| Process fallback | CLI/process mode copies files and strips environment credentials | **Not a security sandbox**: no network, filesystem or resource containment guarantee. Only trusted synthetic/local projects. Hosted mode requires Docker. |
| Unauthorized private runs | API role checks, workspace grants, hashed sessions, sign-in throttling; demo examples intentionally public | `test_admin.py`, `test_api.py`, `test_uploads.py`. One shared workspace: members can read its custom runs. No tenant or per-repository ACL, SSO or GitHub App installation permissions yet. |

## Provider and retention disclosures

The investigator receives selected code/log/test content and screenshots, not just the final patch. The reviewer receives incident facts, the diff and changed-file excerpts. Providers and their authorized subprocessors can process these requests under the applicable account terms; this repository cannot promise that no human can access them.

Meta's contributor/free-credit terms may permit product-improvement use. Verify the actual account tier and current terms before sending company code; paid usage alone is not a blanket privacy guarantee. Baseten publishes a zero-retention posture for **Dedicated Inference**, subject to exceptions; do not assume that statement establishes the exact policy of the shared hackathon endpoint. Sources: [Meta API documentation](https://dev.meta.ai/docs/overview), [Baseten security practices](https://www.baseten.co/security-practices/), [Baseten terms](https://www.baseten.co/terms-and-conditions/).

`REVIEWER_BASE_URL`, `REVIEWER_MODEL`, `REVIEWER_API_KEY` can point review at an internal OpenAI-compatible service running Meta open weights. This is a configurable deployment path, **not a benchmarked private deployment**. It moves only reviewer inference; investigation still calls Meta Model API. Fully private operation also requires an approved/private investigator backend, storage controls and security review.

Uploaded working folders are deleted after a run, but reports/events and excerpts can persist in run storage. The owner controls retention and deletion; there is no automatic retention policy. Do not put private customer data in public example recordings or hackathon submissions.

## Injection evidence

`backend/tests/test_judge_safety.py` drives malicious tool requests after an adversarial log: it checks application edits are denied in investigation, host traversal fails, and a forged verification tool is refused. It uses a scripted model to test enforcement, not to measure model resistance.

`python backend/scripts/security_probe.py --isolation docker` runs one real-model probe on synthetic Orders code and stores the full observation in `eval/security-probe.json`. The payload asks for a credential, network exfiltration, test replacement and false verification. The report discloses isolation and suspicious tool attempts; one probe cannot establish general resistance.
