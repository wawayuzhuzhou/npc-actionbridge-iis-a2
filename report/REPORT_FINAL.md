# NPC ActionBridge for Grounded Game Actions and Player Control

IIS A2

Main report including title, headings and Table 1: 1024 words. Abstract including heading: 184 words. Combined: 1208 words.

## Abstract

Generated NPC dialogue can announce a purchase or an opened door before the game has established either outcome. This project develops NPC ActionBridge, which connects consequential dialogue proposals to game-state validation, player confirmation and factual outcome feedback in an existing Godot RPG. Baseline B dispatches generated actions immediately; ActionBridge A checks prerequisites, presents Confirm/Cancel, rechecks before execution and updates dialogue history from the reported result. Ordinary dialogue passes through without a confirmation window. Six deterministic paired scenarios supplied identical actions to both systems. Baseline executed all three invalid actions, while ActionBridge rejected them. Both completed the two valid actions. In the cancellation comparison, ActionBridge retained eight Gold and no Katana, while Baseline dispatched the purchase. Natural gameplay records show cancellation, an ownership follow-up and successful progression; a matched live Guard pair returned none in both conditions. A guided GUI replay makes the purchase controls and inventory changes visible. The supplied-action scenarios evaluate execution behaviour rather than model error frequency, and the natural walkthroughs were not matched. ActionBridge preserves valid progression while giving the player control over when a proposed action changes the game.

## Problem and Scope

A fluent reply can describe giving a sword without changing inventory. This project asks: How can consequential actions proposed during LLM-driven NPC dialogue be grounded in game state, authorised by players and reconciled with actual execution outcomes? The submitted A1 proposed comparing refusal strategies for requests that conflict with quest state. A2 shifts the focus to consequential execution, state validation and player control in two existing actions: buying a Katana and opening the dojo. The proposed refusal-strategy comparison was not conducted.

## Design Rationale

Prompt instructions can describe the eight-Gold price or the need for a Katana, but executable code controls whether those requirements are met. Checking actual game state therefore gives a proposal a clear consequence: it becomes an available action or is rejected with a reason. Rao et al. (2024, section 2.2) return function results to NPC dialogue, and Phillips et al. (2025) describe structured states for goal progression. These approaches informed the decision to connect dialogue to explicit state transitions.

An affordable purchase still needs the player's permission. Week 2's lab worksheet asks whether people can correct an inference and see its consequences (sections 2 and 5); Week 4 requires visible arguments before confirmation (step 7). The window therefore names the Katana and its eight-Gold cost, making the transaction explicit. A player can decline an affordable sale, so cancellation is a normal outcome alongside purchase. Only valid consequential proposals open the confirmation window. Revalidation after Confirm checks that the same transaction remains possible before the game commits it.

Week 4's instruction to report returned results (step 8) shaped the feedback after a choice. A cancelled purchase should leave the player knowing that the Gold is still available. ActionBridge derives this message from the outcome report and updates the linked conversation, giving later dialogue access to the result. Retaining the raw proposal separately preserves the distinction between what was proposed and what happened.

## System and Implementation

Godot submits player text and a held-items string to FastAPI. The backend combines NPC personality, permitted actions and the player's target-NPC history with five FAISS world facts, then asks Qwen (qwen3.7-flash) for a structured action and reply. Baseline B saves this response and dispatches the original action handler.

In A, a consequential reply creates a separately stored proposal and returns pending feedback with outward action none. Godot checks the NPC/action pairing, Gold, Katana and door state before presenting confirmation. Confirm triggers revalidation, execution and a check of the resulting state; Cancel leaves the action unexecuted. An outcome report atomically updates the SQLite proposal and linked conversation, so later dialogue reads factual outcome feedback (Figure 1). Ordinary none replies bypass the confirmation window.

Godot remains the trusted single-player state authority; the backend validates reported transitions. A save retry resends the same outcome without repeating the action or model generation.

## Illustrated Interaction and Evaluation

Six deterministic pairs sent identical supplied actions through FastAPI, actual headless Godot functions and SQLite (Table 1). B executed three invalid proposals: purchases with seven and zero Gold, and opening without a Katana. A rejected all three, preserving their initial states. Keeping the seven Gold leaves the player one coin short of the price, preserving the progress already made towards a legitimate purchase. Both systems completed the valid eight-Gold purchase and Katana-equipped opening. In the cancellation comparison, A's programmed Cancel kept eight Gold and no Katana; B immediately dispatched the purchase.

Across the six pairs, SQLite stored rejected and cancelled proposals with none in their linked conversations; committed purchases and openings retained sell_katana and open_door. E4's post-cancellation ownership reply also agreed with its Cancelled outcome and unchanged inventory.

The natural E3 and E4 walkthroughs demonstrate purchase and admission in B, and cancellation and successful progression in A (Figures 3-4). Their utterances and histories differ, so they are not a matched comparison. The matched live G1 pair used the same no-Katana request, empty target history and equal recorded retrieval/generation contexts. Both returned none with HTTP 200, leaving the doors closed (Figure 2).

H-UI-01 recorded Cancel retaining eight Gold and no Katana, followed by Confirm producing zero Gold and a Katana. H-UI-02 presents the same controls in the game's shop layout (Figure 5), with fixed Merchant lines selected from the outcome and original feedback retained in the log. Both are preset-state student-operated GUI replays with locally supplied proposals, without model generation or API/SQLite saving. The images show confirmation, feedback and inventory. The deterministic scenarios evaluate execution behaviour under supplied actions, not Qwen's error frequency.

## Development and Reflection

Reusing the game and dialogue framework focused development on purchase and entry. I selected the scope and evaluation choices, performed the recorded gameplay and GUI replay, and reviewed outcomes. Copilot, ChatGPT and Codex assisted coding, debugging, evidence organisation, diagrams and writing. Initial Godot imports failed. Preparing raw assets before restoring scenes and autoloads produced clean B/A runtimes. The final candidate passed 46 offline checks and six paired integration scenarios, with zero engine errors or warnings. The native crash cause remains unknown.

Confirmation makes the consequence visible but adds a pause to play. Restricting it to actions that change inventory or access keeps that cost attached to a meaningful decision. The two valid-action scenarios show that the intervention also preserves legitimate progression. Blocking every proposed action would prevent that progress, so rejection alone would be an inadequate safeguard. Confirmation still leaves a separate problem: E4's "I wanna be a dojo!" produced a legal opening proposal despite an ambiguous request. Approving the displayed action does not establish that the model understood the intended goal. The player can authorise a concrete action even when the original request needs clarification.

Table 1. Six deterministic supplied-action pairs: three invalid, two valid and one cancellation. State is Gold/Katana/door. A's Confirm/Cancel choices were programmed.

| Scenario | Initial state | Supplied action | B after | A after | A outcome |
|---|---|---|---|---|---|
| Invalid purchase: 7 Gold | 7/no/closed | sell_katana | 0/yes/closed | 7/no/closed | Rejected |
| Invalid purchase: 0 Gold | 0/no/closed | sell_katana | 0/yes/closed | 0/no/closed | Rejected |
| Invalid opening: no Katana | 0/no/closed | open_door | 0/no/open | 0/no/closed | Rejected |
| Valid purchase | 8/no/closed | sell_katana | 0/yes/closed | 0/yes/closed | Committed |
| Valid opening | 0/yes/closed | open_door | 0/yes/open | 0/yes/open | Committed |
| Cancel purchase in A | 8/no/closed | sell_katana | 0/yes/closed | 8/no/closed | Cancelled |

## Architecture and illustrated interactions

![ActionBridge architecture](../figures/architecture.svg)

The [interaction records](../docs/INTERACTIONS_TEXT.md) describe the three G1/E4
storyboards and the H-UI-02 sequence. The separately submitted illustrated report
includes the original game captures. Figure 5b shows the second purchase
proposal after cancellation, with eight Gold and no Katana retained.

## References

Rao, S., Xu, W., Xu, M., Leandro, J., Lobb, K., DesGarennes, G., Brockett, C., & Dolan, B. (2024). Collaborative quest completion with LLM-driven non-player characters in Minecraft. arXiv. https://doi.org/10.48550/arXiv.2407.03460

Phillips, A., Lang, J., & Mould, D. (2025). Goal-oriented interactions in games using LLMs. IEEE Transactions on Games, 17(2), 510-521. https://doi.org/10.1109/TG.2024.3515807

Lab 2 worksheet [Week 2 course worksheet, sections 2 and 5]. (n.d.).

Lab 4—Student To-Do: LLM/VLM integration, retrieval and tool use [Week 4 course lab guide, steps 6–8]. (n.d.).

V-o-id. (n.d.). generative-npc-dialogue [Source code, frozen commit 1dc1ab3624b1475d1975e8e1e6dd86f0c171f265]. https://github.com/V-o-id/generative-npc-dialogue

## Repository and development record

[Public repository](https://github.com/wawayuzhuzhou/npc-actionbridge-iis-a2)

[README and Contributions and AI assistance](../README.md#contributions-and-ai-assistance)

[Development record](../docs/CONTRIBUTIONS_AI.md)
