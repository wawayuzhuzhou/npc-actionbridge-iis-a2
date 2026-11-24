# Development and AI assistance

The student selected the research scope and evaluation choices, performed the
recorded E3/E4/G1 gameplay and H-UI-01 GUI replay, and reviewed outcomes. Copilot,
ChatGPT and Codex assisted implementation, debugging, evidence analysis, diagrams
and writing. The student is responsible for the submitted claims and references.

| Development step | Change and purpose | Evidence used to check it |
|---|---|---|
| Playable baseline | Reused Godot game, NPCs, prompts, world and immediate dispatch, replacing an earlier browser prototype | Pinned upstream source and natural E3 walkthrough |
| Qwen adapter | Added compatible transport, structured output and separate runtime configuration around the original context policy | Offline mocked checks and retained live HTTP/SQLite records |
| ActionBridge v1 | Added proposals, local validation, player choice, revalidation and outcome reconciliation | Frozen a613062 source, unit checks and E4 outcomes |
| Evaluation | Separated live G1, deterministic supplied-action scenarios and guided H controls | Saved contexts, state/API/SQL comparisons and student screenshots |
| Reproduction | Imported raw assets before loading scenes/autoloads in new runtime copies | Three clean Windows imports and six paired headless scenarios |
| Final report and README | Replaced generic success claims with the three-invalid/two-valid/one-cancel result; simplified repeated limitations | Existing result records, actual Word counts and all-page inspection |

AI suggestions were revised when they blurred execution tests with model
accuracy or treated guided screenshots as natural gameplay. Checks used actual
Godot state, SQLite outcomes, source hashes and original images. Earlier Copilot
work has no complete line-by-line authorship record. The work is presented as
assisted development, with the student's choices and gameplay identified.

The reused game and dialogue framework are from
[generative-npc-dialogue](https://github.com/V-o-id/generative-npc-dialogue), pinned
to 1dc1ab3624b1475d1975e8e1e6dd86f0c171f265. Asset attribution is recorded in
[third-party notices](../THIRD_PARTY_NOTICES.md). The submitted A1 proposed a
refusal-policy comparison; A2 instead developed the execution boundary.
Original research records, including failures and turn-budget deviations, remain
preserved in the private development archive. The [evidence summary](../evidence/SUMMARY.md)
retains the outcomes relevant to this snapshot.
