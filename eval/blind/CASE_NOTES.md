# What the attempts establish

These notes interpret saved observations; they do not replace them or change the oracle.

## Inflect: a successful follow-up

Round 1 added a reproduction but did not change application code. Round 2 added a bounds guard to the capitalization loop in `postprocess`, plus two reproductions. It passed the upstream hidden regression and all 176 observed outcomes in the selected upstream test file. The original issue already explained the differing-word-count problem, so this is not evidence of discovering that cause without a hint. It is evidence of producing and checking a patch without being supplied the future diff or tests.

Artifacts: [round-2 report](round-2/inflect-172/report.json), [candidate diff](round-2/inflect-172/patch.diff), [held-out outcomes](round-2/inflect-172/hidden-outcomes.json).

## More-itertools: a shared coverage blind spot

The investigator replaced truthiness checks with `is not None` and added three reproductions. Its selected local tests passed and Muse Spark Open approved. The upstream hidden tests accepted the falsy-exception behavior but rejected two `does_not_evaluate_repr` cases: the code still builds the default error message before raising the supplied exception. Formatting a deliberately problematic item's representation can therefore raise instead of the requested exception.

**Disclosure:** the incident given to TracePilot did not state this requirement. It was written from the fix PR, which listed "only construct the default exception message when no custom exception is supplied, avoiding potential errors in item `__repr__`" as a separate change; the study author omitted it from the symptom description. The two failed hidden tests check exactly that unstated behaviour. The result is kept as **not fixed** because the hidden oracle is the study's scoring rule, but it is weaker evidence of a verification blind spot than a failure on a stated requirement would be.

The outcome is **not fixed (2/4 hidden target tests)**. This is a concrete test-green, reviewer-approved candidate that the broader oracle rejects. Separate context does not guarantee independent coverage or eliminate shared blind spots. No second model attempt was used to repair this result.

Artifacts: [report](round-2/more-itertools-1279/report.json), [candidate diff](round-2/more-itertools-1279/patch.diff), [held-out outcomes](round-2/more-itertools-1279/hidden-outcomes.json).

## Tomlkit: a successful patch versus a collection failure

Round 1's patch passed the hidden target test, but an unrelated missing-data import prevented the agent's own suite verification. Round 2 continued running loadable tests and reported unchanged unloadable files in its verification scope. Its candidate again passed the hidden test and was locally verified and reviewer-approved. This does not claim the excluded file was checked.

Artifacts: [round-1 report](round-1/tomlkit-599/report.json), [round-2 report](round-2/tomlkit-599/report.json), [held-out outcomes](round-2/tomlkit-599/hidden-outcomes.json).

## Marshmallow: infrastructure failure retained

Round 2 made model/tool progress and then ended with `APIConnectionError`. It has no final patch to score and remains an error in the seven-case denominator. A subsequent endpoint-availability probe was not a second investigation; this case was not rerun. Its incomplete trace is retained. The reported exit code 4 from the prior unrecorded process cannot be retrospectively diagnosed from this different failure.

Artifact: [partial event trace](round-2/marshmallow-3082/events.jsonl).

## Pyparsing: no fix within the workflow budget

The follow-up added two nested-tag reproductions but no application-code change. Both remained failing, as did an existing example test. The agent reached its fix-phase budget, reported `not_verified`, and the reviewer rejected the candidate. It passed **0/2 hidden target tests**. Continuing past the unrelated `test_diagram.py` collection error made the failures observable, but did not make the agent solve the bug. The roughly 18.5-minute investigation also demonstrates why latency measured on the simpler demo scenarios cannot be promised for an arbitrary repository.

Artifacts: [report](round-2/pyparsing-560/report.json), [event trace](round-2/pyparsing-560/events.jsonl), [held-out outcomes](round-2/pyparsing-560/hidden-outcomes.json).

## Click: a partial patch correctly withheld

The candidate changed `Option.get_error_hint` but did not repair help-text rendering. Its own new reproduction still failed, the reviewer rejected the patch, and the hidden oracle accepted **5/7 target tests**. It remains **not fixed**, rather than receiving fractional success credit. This contrasts with More-itertools: the review caught an unresolved symptom explicitly described in Click's incident, but did not catch More-itertools' broader representation edge case.

Artifacts: [report](round-2/click-3884/report.json), [candidate diff](round-2/click-3884/patch.diff), [held-out outcomes](round-2/click-3884/hidden-outcomes.json).

## Packaging: context-window failure retained

The run ended with a `context_length_exceeded` API error: a 1,824,369-token input exceeded the stated 1,048,576-token window. There is no final report or completed candidate judgment, so this remains an **error**, not a functional success or a zero-cost attempt. The partial trace includes the earlier test and fix work. The failed case was not restarted with a larger budget, narrower test scope or compacted context to improve its score.

Artifact: [partial event trace](round-2/packaging-1430/events.jsonl).

## Conclusion

Round 2 fixed **2/7** selected real bugs under their upstream hidden tests. Three candidates were not fixed and two attempts ended in errors. This establishes successful examples, not reliable repair across unfamiliar projects. Context/feedback sizing, preserving enough budget for application edits, and broader edge-case coverage are engineering priorities suggested by these traces; their benefits have not been measured by this study.
