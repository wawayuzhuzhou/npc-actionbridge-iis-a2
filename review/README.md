# Source and integrity record

`exact_file_allowlist.json` lists the 81 release files and their classifications.
`exclusion_manifest.json` identifies excluded private and external material.
`privacy_metadata_scan.json` records the final bounded pattern, format and
metadata checks. `source_validation.json` records static syntax and byte
comparisons against the accepted execution evidence. No experiments were
repeated for publication.

`candidate.sha256` hashes every selected file except itself. Its SHA256 is the
tree digest, computed from sorted UTF-8 lines of `sha256  portable/path`, with
LF endings and a final newline. A hash of that manifest is recorded in the
separate release receipt. This avoids a circular self-hash.

Publication and the scoped original-code MIT grant were authorised by the
student on 24 November 2026. The original private development history remains
separate. No environment, database, raw log, game screenshot, font or audio is
included. The complete illustrated report is submitted separately.
