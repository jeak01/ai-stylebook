#!/usr/bin/env python3
"""Offline lookup and prompt drafting for the 48-style skill. Python 3.10+."""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = "https://aistylebook.com/"


def load_catalog():
    return json.loads((ROOT / "references/catalog.json").read_text(encoding="utf-8"))


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def names(row):
    return [row["name"], row["name_en"], row["slug"], *row["aliases"]]


def exact_matches(query, catalog):
    query = normalize(query).lstrip("#")
    if query.isdigit():
        return [row for row in catalog if row["id"] == int(query)]
    return [row for row in catalog if query in map(normalize, names(row))]


def keyword_matches(term, value):
    if re.search(r"[\u3400-\u9fff]", term):
        return term in value
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", value))


def search(query, catalog, limit=5):
    query = normalize(query)
    if not query:
        return []
    exact = exact_matches(query, catalog)
    if exact:
        return exact[:limit]
    if query.lstrip("#").isdigit():
        return []
    terms = re.findall(r"[\w-]+", query)
    ranked = []
    for row in catalog:
        labels = list(map(normalize, names(row)))
        tags = list(map(normalize, row["tags"]))
        score = sum(8 for term in terms if any(keyword_matches(term, label) for label in labels))
        score += sum(3 for term in terms if any(keyword_matches(term, tag) for tag in tags))
        # Chinese queries do not require spaces: recognize known multi-character terms.
        score += sum(2 for tag in [*labels, *tags] if len(tag) >= 2 and keyword_matches(tag, query))
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [row for _, row in ranked[:limit]]


def resolve(query, catalog):
    matches = exact_matches(query, catalog)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(f"{row['id']:02d} {row['name']}" for row in matches)
        raise ValueError(f"Ambiguous style: {choices}. Choose an ID.")
    candidates = search(query, catalog, 3)
    hint = "; suggestions: " + ", ".join(f"{r['id']:02d} {r['name']}" for r in candidates) if candidates else ""
    raise ValueError(f"No exact style match{hint}. This package includes IDs 01-48. More: {WEBSITE}")


def card_for(row):
    path = (ROOT / "references" / row["file"]).resolve()
    if path.parent != (ROOT / "references/styles").resolve():
        raise ValueError("Invalid style-card path")
    card = json.loads(path.read_text(encoding="utf-8"))
    if card["id"] != row["id"]:
        raise ValueError("Style-card ID mismatch")
    return card


def positive_int(value):
    number = int(value)
    if number < 1 or number > 48:
        raise argparse.ArgumentTypeError("must be from 1 to 48")
    return number


def ratio(value):
    if value != "auto" and not re.fullmatch(r"[1-9][0-9]?:[1-9][0-9]?", value):
        raise argparse.ArgumentTypeError("use auto or a positive ratio such as 4:3")
    return value


def nonempty(value):
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be empty")
    return value.strip()


SUBJECT_GUIDES = {
    "people": "Preserve identity, expression, pose, requested clothing and the number of people; retain recognition when forms are simplified.",
    "landscape": "Preserve landmarks, terrain, relative building positions and foreground/background relationships.",
    "objects": "Preserve the silhouette, connected components, functional structure, object count and any explicitly requested wording.",
    "other": "Preserve the subject's identifying features, object count and meaningful spatial relationships.",
}


def make_prompt(row, card, subject, subject_type="other", mode="generate", aspect_ratio="auto", preserve=None):
    task = "Restyle the user's supplied reference image as one complete artwork." if mode == "transfer" else "Create one complete image of the subject below."
    composition = "Match the supplied reference aspect ratio when present; otherwise choose framing appropriate to the subject." if aspect_ratio == "auto" else f"Use a {aspect_ratio} aspect ratio."
    parts = [f"Style {row['id']:02d}: {row['name']} / {row['name_en']}", task,
             "Subject and scene: " + subject, "Content invariants: " + SUBJECT_GUIDES[subject_type]]
    if preserve:
        parts.append("Additional content invariants: " + preserve)
    parts += ["Visual treatment: " + card["rendering_prompt"],
              "Signature checks: " + "; ".join(card["signature"]),
              "Composition: " + composition + " Do not stretch the subject. Keep the chosen projection consistent. Apply the style to subject and background.",
              "Avoid: " + card["avoid"],
              "Do not introduce unrequested characters, props, labels, logos, speech balloons or grids. Do not copy the example sheets' content."]
    if row["id"] in (5, 6, 12, 25):
        parts.append("If the style's viewpoint or framing conflicts with a fixed user requirement, explain the tradeoff before changing that requirement.")
    return "\n\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List the 48 styles")
    listing.add_argument("--json", action="store_true")
    finding = commands.add_parser("search", help="Search bilingual names, aliases and visual tags")
    finding.add_argument("query", type=nonempty)
    finding.add_argument("--limit", type=positive_int, default=5)
    finding.add_argument("--json", action="store_true")
    showing = commands.add_parser("show", help="Read an exact ID, name or alias")
    showing.add_argument("style", type=nonempty)
    showing.add_argument("--json", action="store_true")
    drafting = commands.add_parser("prompt", help="Draft a prompt without calling an image API")
    drafting.add_argument("style", type=nonempty)
    drafting.add_argument("--subject", required=True, type=nonempty)
    drafting.add_argument("--subject-type", choices=SUBJECT_GUIDES, default="other")
    drafting.add_argument("--mode", choices=("generate", "transfer"), default="generate")
    drafting.add_argument("--ratio", type=ratio, default="auto")
    drafting.add_argument("--preserve", type=nonempty)
    args = parser.parse_args(argv)
    catalog = load_catalog()
    try:
        if args.command in ("list", "search"):
            rows = catalog if args.command == "list" else search(args.query, catalog, args.limit)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            elif rows:
                for row in rows:
                    print(f"{row['id']:02d}  {row['name']} / {row['name_en']}  [{row['category']}]")
            else:
                print(f"No matching style in this 48-style package. More: {WEBSITE}")
            return 0 if rows else 1
        row = resolve(args.style, catalog)
        card = card_for(row)
        if args.command == "show":
            if args.json:
                print(json.dumps(card, ensure_ascii=False, indent=2))
            else:
                print(f"{row['id']:02d} {row['name']} / {row['name_en']}\n\n{card['description']}")
                for label, value in [("Signature", "; ".join(card["signature"])), ("Rendering prompt", card["rendering_prompt"]), ("Avoid", card["avoid"]), ("Difference", card["difference"]), ("Adjustment", card["tuning"])]:
                    print(f"\n{label}: {value}")
        else:
            print(make_prompt(row, card, args.subject, args.subject_type, args.mode, args.ratio, args.preserve))
        return 0
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
