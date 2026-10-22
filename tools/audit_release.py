#!/usr/bin/env python3
"""Validate the explicit release file boundary and the self-contained style catalog."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "skills/aistylebook-48/"
FIXED = {
    ".gitignore", ".gitattributes", "README.md", "README.zh-CN.md", "LICENSE",
    "tests/test_stylebook.py", "tools/audit_release.py",
    PREFIX + "SKILL.md", PREFIX + "agents/openai.yaml",
    PREFIX + "references/catalog.json", PREFIX + "references/index.md",
    PREFIX + "references/choosing.md", PREFIX + "references/generation.md",
    PREFIX + "scripts/stylebook.py",
    *(PREFIX + f"assets/{name}-48.jpg" for name in ("people", "landscape", "objects")),
}
CATALOG_KEYS = {"id", "name", "name_en", "slug", "category", "aliases", "tags", "file"}
CARD_KEYS = {"id", "name", "name_en", "description", "signature", "rendering_prompt", "avoid", "nearby_styles", "difference", "tuning"}
SENSITIVE = {
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "API token": r"\bsk-[A-Za-z0-9_-]{20,}\b",
    "Windows absolute path": r"\b[A-Za-z]:[\\/]",
    "home directory": r"/(?:Users|home)/[^/\s]+/",
    "conversation record": r"(?m)^\s*\{\s*\"role\"\s*:\s*\"(?:user|assistant)\"",
}


def audit():
    catalog = json.loads((ROOT / PREFIX / "references/catalog.json").read_text(encoding="utf-8"))
    errors = []
    if [row["id"] for row in catalog] != list(range(1, 49)):
        errors.append("Catalog must contain exactly IDs 01-48 in order")
    expected = FIXED | {PREFIX + "references/" + row["file"] for row in catalog}
    found = set()
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if ".git" in relative.parts or "__pycache__" in relative.parts:
            continue
        if path.is_symlink():
            errors.append(f"Symlink is not allowed: {relative.as_posix()}")
            continue
        if not path.is_file():
            continue
        name = relative.as_posix()
        found.add(name)
        if name not in expected:
            errors.append(f"Unapproved file: {name}")
            continue
        if path.suffix == ".jpg":
            data = path.read_bytes()
            if not data.startswith(b"\xff\xd8\xff") or len(data) < 100_000:
                errors.append(f"Invalid preview image: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in SENSITIVE.items():
            if re.search(pattern, text):
                errors.append(f"Potential {label} in {name}")
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if re.match(r"https?://", target) or target.startswith("#"):
                    continue
                destination = (path.parent / target.split("#", 1)[0]).resolve()
                if not destination.is_relative_to(ROOT) or not destination.exists():
                    errors.append(f"Broken or external local link in {name}: {target}")
    for missing in sorted(expected - found):
        errors.append(f"Missing file: {missing}")
    for row in catalog:
        if set(row) != CATALOG_KEYS:
            errors.append(f"Unexpected catalog fields for ID {row['id']}")
        card_path = ROOT / PREFIX / "references" / row["file"]
        if not card_path.resolve().is_relative_to((ROOT / PREFIX / "references/styles").resolve()):
            errors.append("Style reference escapes the style directory")
            continue
        card = json.loads(card_path.read_text(encoding="utf-8"))
        if set(card) != CARD_KEYS or card["id"] != row["id"]:
            errors.append(f"Unexpected style fields or ID for {row['id']}")
        if any(value not in range(1, 49) for value in card["nearby_styles"]):
            errors.append(f"Out-of-scope related style for ID {row['id']}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"PASS: {len(found)} allowlisted files; exactly 48 style cards; three JPEG sheets; local links and sensitive-pattern scan passed.")
    print("This bounded check complements review of the staged files and image contents; it is not a proof that all possible secrets are absent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(audit())
