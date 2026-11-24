# External source and asset acquisition

This snapshot deliberately omits the entire upstream game, all game assets,
font/audio binaries, imported caches, Godot executable, model index and database
files. Offline Python tests construct synthetic temporary databases themselves.
The deterministic Godot replay additionally requires a separately acquired,
complete upstream checkout and its seed database. It cannot run from this
snapshot alone.

Acquire upstream into a new review work directory, outside this candidate and
outside every preserved live or historical runtime. The following is a recipe,
not a claim that downloading the game clears redistribution rights:

```powershell
$ReviewRoot = Join-Path $env:TEMP ('actionbridge-review-' + [guid]::NewGuid().ToString('N'))
$Upstream = Join-Path $ReviewRoot 'upstream'
New-Item -ItemType Directory -Path $ReviewRoot | Out-Null
git clone https://github.com/V-o-id/generative-npc-dialogue.git $Upstream
git -C $Upstream checkout --detach 1dc1ab3624b1475d1975e8e1e6dd86f0c171f265
git -C $Upstream rev-parse HEAD
```

The revision must exactly match the pinned hash. Keep the checkout unmodified
and create disposable B/A game and database copies as described in
[reproduction](REPRODUCTION.md). The acquisition's Git history is outside this
candidate; no history from the private research repository is copied here.

Read the acquired `LICENSE`, Ninja Adventure README/CC0 text and embedded font
notices before any onward distribution. Compare the inspected notice hashes in
[the inventory](../notices/source_notice_inventory.json). NormalFont's embedded
non-commercial notice conflicts with the broad CC0 pack statement. Seven files
under the separate Sound directory have no locally identified provenance.
Open Sans identifies Apache 2.0. The complete externally acquired runtime is
needed to inspect the historical behaviour, but is **not a cleared public game
bundle**. Replacing/removing resources changes the runtime and requires separate
verification; this candidate does not claim that has been done.

Obtain Godot **4.3 stable** separately from [the official archive](https://godotengine.org/download/archive/4.3-stable/)
for the review platform. Set `$Godot` to the acquired executable. No engine or
third-party package binaries are redistributed by this candidate. Install Python
dependencies into a new local environment using the separate reproduction guide.

No Qwen request is needed for the included tests, supplied-action replay or report
review. Do not create an embedding index for those checks. Real-model execution
would need the reviewer's own credentials, compatible trusted index and separate
authorisation; it is outside the zero-provider inspection route. The index
loader permits pickle deserialisation, so do not load untrusted index files.
