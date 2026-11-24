"""Verify a clean snapshot's portable SHA256 manifest without network or assets."""
from pathlib import Path
import hashlib
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = root / "review/candidate.sha256"
    expected = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or name in expected:
            raise ValueError("Invalid portable manifest entry")
        expected[name] = digest
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and p != manifest}
    if actual != set(expected):
        raise ValueError("File set differs from exact candidate manifest")
    if any(hashlib.sha256((root / name).read_bytes()).hexdigest() != digest
           for name, digest in expected.items()):
        raise ValueError("Candidate file hash mismatch")
    print("PASS: exact file set and SHA256 hashes")
    print("Candidate tree digest:", hashlib.sha256(manifest.read_bytes()).hexdigest())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("FAILED:", type(exc).__name__, str(exc), file=sys.stderr)
        raise SystemExit(1)
