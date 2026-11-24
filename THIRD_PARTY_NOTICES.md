# Third-party notices and distribution scope

These are inspected source facts and conservative inclusion decisions, not a
legal clearance certificate. All font, audio, texture and game binaries are
excluded from this snapshot. The student has not authorised public release.

| Material | Inspected notice | Inclusion decision |
|---|---|---|
| `generative-npc-dialogue`, upstream commit `1dc1ab3624b1475d1975e8e1e6dd86f0c171f265` | MIT; Copyright (c) 2024 Void | Complete original notice preserved in [UPSTREAM_MIT.txt](notices/UPSTREAM_MIT.txt). Reused prompt, world facts, action vocabulary and original API/Godot behaviour are attributed. The full upstream game is externally acquired. |
| Ninja Adventure pack | README credits Pixel-boy and AAA, states CC0; `LICENSE.txt` contains CC0 1.0 Universal | Original [README](notices/NINJA_ADVENTURE_README.md) and [CC0 text](notices/NINJA_ADVENTURE_CC0.txt) preserved. Pack pixels are excluded here. The broad notice does not override the unresolved NormalFont conflict. |
| Open Sans Regular | Embedded name records: Google copyright 2010–2011; “Licensed under the Apache License, Version 2.0”; Apache licence URL | Font binary excluded. If later bundled, obtain the applicable Apache 2.0 licence/required notices and review that exact font version. Do not describe it as solely CC0. |
| NinjaAdventure NormalFont | Embedded name records: Copyright pixel-boy 2021; “FontStruct Non-Commercial License” | Conflicts with broad pack CC0 statement; font binary and screenshot-derived pixels excluded pending clarification or a separately reviewed replacement in a new runtime copy. Frozen source is unchanged. |
| Separate `game/Assets/Sound/` | Seven `.wav`/`.mp3` files; no local licence/readme found | Audio and import sidecars excluded. Scenes reference these files, so simply omitting audio from a full game export would not create the verified runtime used in the evidence. |
| Python packages and Godot | Acquired separately; their own terms apply | No packages, wheels, environment or engine binary bundled. The dependency recipe is not a grant for third-party packages. |
| Report game images and derived storyboards | Contain upstream artwork and may contain those fonts | Actual images and the full image-bearing report are excluded from this clean snapshot. Private illustrated coursework originals remain separate and unmodified. |

The inspected source-file hashes and exact selected font name records are in
[source notice inventory](notices/source_notice_inventory.json). This inventory
does not contain private absolute paths, operator identifiers or original image
provenance. Preserving a notice does not add the omitted binary to the candidate.

Sources for external acquisition: [upstream project](https://github.com/V-o-id/generative-npc-dialogue),
[pinned upstream MIT](https://github.com/V-o-id/generative-npc-dialogue/blob/1dc1ab3624b1475d1975e8e1e6dd86f0c171f265/LICENSE),
[Ninja Adventure](https://pixel-boy.itch.io/ninja-adventure-asset-pack),
[Pixel-boy](https://pixel-boy.itch.io/), and the
[Apache licence URL named by Open Sans](https://www.apache.org/licenses/LICENSE-2.0).
These are source locators, not a new online legal review or permission grant.
