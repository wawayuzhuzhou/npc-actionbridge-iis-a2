# Evaluation results and sources

The recorded sources below distinguish model dialogue, controlled execution and
visible interaction. Original records remain in the private development archive.

| Evidence | Result retained | Limit retained |
|---|---|---|
| Natural E3 baseline | Eight generated turns; purchase, Guard opening and completion | Unmatched with E4. Historical accounting details are preserved in the private archive. |
| Natural E4 ActionBridge | Six generated turns; cancellation, correct next ownership denial, purchase and opening | Four authorised, two extra turns. No historical modal screenshots/device trace. Different utterances/history from E3. |
| Genuine G1 B/A | One generated turn per condition, equal observed complete generation contexts/ordered retrieval; both `none`, HTTP200 and closed-door images | No consequential action or modal path tested; initial state partly student/client reported. |
| Original rejected G1 submissions | Two HTTP403 rejections before provider dispatch | Identity mismatch; zero generated baseline observations; retained failures, not a model result. |
| Deterministic D fixtures | Six identical supplied-action B/A pairs; 12 headless executions in a recorded run; actual ASGI/Godot/SQLite checks | Programmed choices, injected actions, same scenarios on revalidation; no model-error frequency or human/usability effect. |
| H-UI-01 | Guided student-operated fixture GUI replay; Cancel keeps 8 Gold/no Katana, Confirm gives 0/Katana; three actual private images agree with five semantic events | Preset state and instructed choices; no new model/API/SQLite save, natural map journey or participant study. Original case warning retained. |

## Deterministic supplied-action outcomes

State notation is Gold / Katana / door; K is present, no K absent, C closed, O open.

| Existing fixture alias | Before | Supplied action | B after | A after | A status | Stored action B / A |
|---|---|---|---|---|---|---|
| D-M1 | 7 / no K / C | `sell_katana` | 0 / K / C | 7 / no K / C | Rejected | sell_katana / none |
| D-M2 | 8 / no K / C | `sell_katana` | 0 / K / C | 0 / K / C | Committed | sell_katana / sell_katana |
| D-G1 | 0 / no K / C | `open_door` | 0 / no K / O | 0 / no K / C | Rejected | open_door / none |
| D-G2 | 0 / K / C | `open_door` | 0 / K / O | 0 / K / O | Committed | open_door / open_door |
| D-CANCEL | 8 / no K / C | `sell_katana` | 0 / K / C | 8 / no K / C | Cancelled | sell_katana / none |
| D-M0 | 0 / no K / C | `sell_katana` | 0 / K / C | 0 / no K / C | Rejected | sell_katana / none |

All recorded generation and A outcome-save routes returned HTTP200. B has no
proposal status/endpoint; its fixture label is not an invented `Committed` record.
The Merchant fixture loads a dojo node although normal indoor Merchant gameplay
does not. M2/G2 use separate Godot processes with checked state continuity, not a
continuous natural journey.

The [minimal action fixture](offline_action_fixture.json) retains only the two
action/response pairs used by the deterministic replay, derived from legitimate
E3 sale/opening observations. It contains no original SQL identifiers, player
record or timestamps. [Matrix](../phase2/evaluation/matrix.json) and
[state fixture](../phase2/evaluation/state_fixture.gd) describe the supplied inputs
and assertions. Counterfactual state injection does not mean Qwen selected those
actions under those states. Original private record hashes can be inspected by
an authorised examiner separately; raw paths and data are not disclosed here.
