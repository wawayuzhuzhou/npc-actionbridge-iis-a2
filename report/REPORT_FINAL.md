# NPC ActionBridge for Grounded Game Actions and Player Control

IIS A2

Main report including title, headings and Table 1: 1052 words. Abstract including heading: 181 words. Combined: 1233 words.

## Abstract

Large language models (LLMs) allow players to interact with non-player characters (NPCs) through natural language. When dialogue can also change the game world, interpreting a request is only part of the task: proposed actions must satisfy game rules and receive the player's authorisation. This project develops NPC ActionBridge within an existing Godot role-playing game, focusing on weapon purchases and access to a dojo. The baseline dispatches generated actions immediately. ActionBridge validates proposals against game state, requests confirmation and updates dialogue history according to the execution outcome. Six deterministic comparisons supplied identical action proposals to both systems. ActionBridge rejected all three invalid actions, while the baseline executed them. Both completed the two valid actions. In the cancellation scenario, ActionBridge preserved inventory while the baseline dispatched the purchase immediately. In a matched live-model comparison, both responses requested the missing weapon and generated no entry action. Original gameplay records and student-operated, preset-state interface demonstrations illustrate cancellation, subsequent dialogue and successful progression. Together, these findings demonstrate how separating dialogue generation from action execution can preserve legitimate progression while giving players control over consequential decisions.

## Problem and Scope

The project uses an existing Godot role-playing game (V-o-id, n.d.). The intended task is to collect eight Gold coins, buy a Katana sword from the Merchant and gain access to a dojo, a martial-arts training hall. Entry requires the player to possess the sword; it is not handed over. NPC dialogue returns both speech and an action instruction, so a reply can trigger a purchase or open the door. How can these actions respect game state and player authorisation, with subsequent dialogue reflecting what actually happened? A1 proposed comparing refusal strategies for requests conflicting with quest state. A2 instead investigates execution. The adapted original system is Baseline B; the enhanced version is ActionBridge A. Reusing the third-party world and action handlers provides an inspectable baseline for the added checks and confirmation.

## Design Rationale

A request first needs interpretation. Prompts influence what the model proposes, but a plausible reply does not establish intent or permission to act. The next question is whether the proposal meets current game rules: possessing a sword is an executable entry condition. Rao et al. (2024, section 2.2) return function results to NPC dialogue; Phillips et al. (2025) represent goal progression through structured states. These approaches informed the link between dialogue and state transitions.

An affordable purchase still needs the player's permission. Week 2's lab worksheet asks whether people can correct an inference and see its consequences (sections 2 and 5). Week 4 requires visible arguments before confirmation (step 7). ActionBridge therefore displays the item and cost, allowing acceptance or cancellation. Only valid consequential proposals open the confirmation window. Rechecking after Confirm ensures the displayed transaction remains possible. Limiting interruptions to consequential actions balances player control against the pause imposed on play.

After that choice, feedback should reflect the result. Week 4's instruction to report returned results (step 8) informed outcome reconciliation: the system updates the associated conversation from the execution report, while retaining the original proposal separately. Later dialogue can therefore use what happened, including a cancellation that leaves inventory unchanged.

## System and Implementation

Both versions adapt the upstream dialogue framework to the same Qwen backend. Godot sends player text and held items to FastAPI. Its retrieval-augmented generation (RAG) pipeline uses FAISS similarity search to retrieve five relevant knowledge-base entries, combining them with the NPC's instructions and the player's conversations with that character. Qwen (qwen3.7-flash) returns speech and an action; none means no special game action. The baseline backend stores the response, then Godot dispatches the returned action through its original handler.

ActionBridge stores consequential suggestions as pending proposals, returning none as the immediate action and carrying the proposed purchase or opening separately for local inspection. Godot checks that the character can perform the action and that inventory and door state permit it. Valid proposals reach Confirm/Cancel. Confirm rechecks state, executes the action and verifies the result; Cancel leaves it unexecuted. The backend then atomically reconciles the SQLite proposal and associated conversation with the reported outcome (Figure 1). Ordinary replies bypass confirmation.

Godot is the trusted local state authority in this single-player game. The backend validates reported transitions. Outcome feedback needs no further model call, and a failed save can be resent without repeating execution or generation.

## Illustrated Interaction and Evaluation

Six deterministic paired tests replaced model generation with fixed action proposals, then passed identical proposals through each version's FastAPI, headless Godot functions and SQLite (Table 1). Inventory and door states matched; confirmation choices were scripted. The baseline executed three invalid actions: purchases with seven or zero Gold, and opening without a Katana. ActionBridge rejected all three, preserving inventory and access restrictions. Keeping seven Gold preserves progress towards the purchase. Both systems completed the valid eight-Gold purchase and opened the dojo when the player held a Katana. In the cancellation comparison, ActionBridge's programmed Cancel retained eight Gold and no Katana; the baseline immediately dispatched the purchase. These tests assess execution safeguards, not model error rates or perceived usability.

ActionBridge's linked SQLite conversations recorded none after rejection or cancellation, and retained sell_katana or open_door after committed purchases or openings. The raw proposals remained separately available.

Original gameplay walkthroughs show purchase and admission in the baseline (E3), and cancellation and progression in ActionBridge (E4; Figures 3–4). The Merchant's reply to the ownership question after cancellation agreed with the unchanged inventory. Their utterances and histories differ, so they are not matched comparisons. A separate matched live-model test (G1) used the same entry request, an initial state without a Katana, empty Guard history and identical recorded retrieval results and generation contexts. Both Qwen responses requested a weapon and returned none, leaving the doors closed (Figure 2).

To make the controls and consequences visible, the student performed interface replays: Cancel preserved eight Gold and no Katana, then Confirm produced zero Gold and a Katana (H-UI-01). A shop-based replay adds outcome-selected, fixed Merchant dialogue (H-UI-02; Figure 5). Both use preset states, locally supplied proposals and actual student-operated controls, without model calls or database saves. Figure 5b shows the second proposal after cancellation.

Table 1. Six deterministic supplied-action pairs: three invalid, two valid and one cancellation. State is Gold/Katana/door. A's Confirm/Cancel choices were programmed.

| Scenario | Initial state | Supplied action | B after | A after | A outcome |
|---|---|---|---|---|---|
| Invalid purchase: 7 Gold | 7/no/closed | sell_katana | 0/yes/closed | 7/no/closed | Rejected |
| Invalid purchase: 0 Gold | 0/no/closed | sell_katana | 0/yes/closed | 0/no/closed | Rejected |
| Invalid opening: no Katana | 0/no/closed | open_door | 0/no/open | 0/no/closed | Rejected |
| Valid purchase | 8/no/closed | sell_katana | 0/yes/closed | 0/yes/closed | Committed |
| Valid opening | 0/yes/closed | open_door | 0/yes/open | 0/yes/open | Committed |
| Cancel purchase in A | 8/no/closed | sell_katana | 0/yes/closed | 8/no/closed | Cancelled |


## Development and Reflection

I selected the scope and evaluation, performed gameplay and interface demonstrations, and checked outcomes. I rejected mechanical state messages as NPC speech, requested natural Merchant dialogue and personally checked the Cancel and Confirm results. Copilot, ChatGPT and Codex assisted coding, debugging, evidence organisation, diagrams and writing. Initial Godot imports failed; preparing raw assets before restoring scenes and autoloads produced working Windows runtimes. The final candidate passed 46 offline Python checks and six paired Godot integration scenarios, with zero engine errors or warnings.

Confirmation resolves whether a displayed action may proceed, but cannot resolve ambiguity in the request itself. During the ActionBridge walkthrough, "I wanna be a dojo!" produced a permitted opening proposal because the player already held the required sword. Authorising that action does not show that the model understood the player's goal. Clarifying uncertain requests before offering consequential actions is a useful next design step.

## Architecture and illustrated interactions

![ActionBridge architecture](../figures/architecture.svg)

The [interaction storyboards](../docs/INTERACTIONS_TEXT.md) show the matched live-model entry test, cancellation followed by an ownership question, and successful purchase and entry. The illustrated coursework report also contains the student-operated shop replay. Its Figure 5b shows the second purchase proposal after cancellation, with eight Gold and no Katana retained.

## References

Rao, S., Xu, W., Xu, M., Leandro, J., Lobb, K., DesGarennes, G., Brockett, C., & Dolan, B. (2024). Collaborative quest completion with LLM-driven non-player characters in Minecraft. arXiv. https://doi.org/10.48550/arXiv.2407.03460

Phillips, A., Lang, J., & Mould, D. (2025). Goal-oriented interactions in games using LLMs. IEEE Transactions on Games, 17(2), 510–521. https://doi.org/10.1109/TG.2024.3515807

Lab 2 worksheet [Week 2 course worksheet, sections 2 and 5]. (n.d.).

Lab 4—Student To-Do: LLM/VLM integration, retrieval and tool use [Week 4 course lab guide, steps 6–8]. (n.d.).

V-o-id. (n.d.). generative-npc-dialogue [Source code, frozen commit 1dc1ab3624b1475d1975e8e1e6dd86f0c171f265]. https://github.com/V-o-id/generative-npc-dialogue

## Repository and development record

[Public repository](https://github.com/wawayuzhuzhou/npc-actionbridge-iis-a2)

[README and Contributions and AI assistance](../README.md#contributions-and-ai-assistance)

[Development record](../docs/CONTRIBUTIONS_AI.md)
