# Development and AI assistance

The student selected the research scope and evaluation choices, performed the
recorded E3/E4/G1 gameplay and H-UI-01/H-UI-02 GUI replays, and reviewed outcomes. Copilot,
ChatGPT and Codex assisted implementation, debugging, evidence analysis, diagrams
and writing. The student is responsible for the submitted claims and references.

| Development step | Change and purpose | Evidence used to check it |
|---|---|---|
| Playable baseline | Reused Godot game, NPCs, prompts, world and immediate dispatch, replacing an earlier browser prototype | Pinned upstream source and natural E3 walkthrough |
| Qwen adapter | Added compatible transport, structured output and separate runtime configuration around the original context policy | Offline mocked checks and retained live HTTP/SQLite records |
| ActionBridge v1 | Added proposals, local validation, player choice, revalidation and outcome reconciliation | Frozen a613062 source, unit checks and E4 outcomes |
| Evaluation | Separated live G1, deterministic supplied-action scenarios and guided H controls | Saved contexts, state/API/SQL comparisons and student screenshots |
| Reproduction | Imported raw assets before loading scenes/autoloads in new runtime copies | Three clean Windows imports and six paired headless scenarios |
| H-UI-02 presentation | Responded to the student's feedback about empty space and mechanical NPC wording: reused the shop graphics, then selected fixed Merchant lines from actual outcomes | Student Cancel/Confirm signals, three untouched viewport captures, original feedback retained separately, unchanged bridge/HUD hashes |
| Final report and README | Introduced the game task before examples; distinguished interpretation, validity and authorisation; explained methods before findings and used case IDs for evidence location | Existing results and source code, reference records, actual document counts and all-page rendering |

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

## H-UI-02 presentation decision and check

The first shop replay still put system-style state text in the Merchant's speech
box. The student identified that mismatch. The revised presentation uses
AI-assisted authored lines, selected after the local result is known: cancellation
leaves eight Gold and no Katana; a committed purchase gives the Katana and spends
eight Gold. These fixed lines are not Qwen replies. The student personally chose
Cancel and then Confirm; the second capture shows a new purchase proposal after
cancellation. This presentation change does not alter the released action code
or the earlier evaluation results.

The local execution path is preset state and supplied action, followed by the
original bridge's `propose`, `confirm_with_player`, `resolve` and `snapshot`.
The HUD reads the original inventory state. An outcome-conditioned display
template supplies the Merchant line, while the journal retains the original
core feedback and actual outcome. The original event records, source hashes
and three PNGs were checked together; no provider request or API/SQLite save
occurs in this path. Original game graphics and private records remain outside
this public snapshot; the illustrated coursework report contains the captures.

## Inspectable design decisions

The shared Qwen adapter preserves the upstream context policy, while the two
execution paths expose the intervention. The [Baseline FastAPI backend](../adapter/qwen_baseline/fastapi_app.py)
stores the generated response; the [local bridge](../adapter/actionbridge/godot/ActionBridge.gd)
checks prerequisites and resolves Confirm/Cancel. The [outcome store](../adapter/actionbridge/store.py)
reconciles the proposal with its linked conversation. The preserved
[six-pair integration results](../evidence/RC1_CANDIDATE_INTEGRATION.json) and
[result table](../evidence/SUMMARY.md#deterministic-supplied-action-outcomes)
allow those implementation choices to be checked against actual recorded states
and stored actions.

The student's Merchant revision is a separate presentation decision. The student
rejected “Purchase completed. Current state: 0 Gold; Katana: yes.” as unnatural
NPC speech and requested dialogue. The replacement, “Here's your katana. Eight
gold, paid in full. Take good care of it.”, is an authored display line selected
only after a committed local outcome. The student then personally operated
Cancel and Confirm. It is not a newly generated model reply, a change to the
frozen bridge, or evidence of measured usability improvement.

The public history is an explicitly curated release snapshot followed by
documentation revisions. These source and result links support inspection;
they do not reconstruct or replace the original private development history.
