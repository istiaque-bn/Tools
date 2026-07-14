import re

import fitz


START_PAGE = 408
END_PAGE = 448
RIGHT_COLUMN_X = 390
IGNORED = {"RESTRICTED", "ANNEX A TO", "SECTION 16", "GENERAL ABBREVIATIONS"}


def annex_abbreviations(pdf_path):
    """Return rows from the two-column table on printed PDF pages 408–448."""
    document = fitz.open(pdf_path)
    rows = []
    try:
        for page_number in range(START_PAGE, END_PAGE + 1):
            page = document[page_number - 1]
            lines = {}
            for x0, y0, _x1, _y1, word, *_rest in page.get_text("words"):
                # Annex title occupies the top of its first page, while continuation
                # pages resume the table near y=133.
                if y0 < 125 or y0 > 660:
                    continue
                key = round(y0, 1)
                side = "abbr" if x0 >= RIGHT_COLUMN_X else "meaning"
                lines.setdefault(key, {"meaning": [], "abbr": []})[side].append(
                    (x0, word)
                )

            pending = []
            for line in (lines[key] for key in sorted(lines)):
                meaning = " ".join(word for _, word in sorted(line["meaning"]))
                abbreviation = " ".join(word for _, word in sorted(line["abbr"]))
                if meaning in IGNORED or re.fullmatch(r"[A-Z]", meaning or ""):
                    continue
                if re.fullmatch(r"16A-\d+", meaning) or re.fullmatch(
                    r"16A-\d+", abbreviation
                ):
                    continue
                if meaning:
                    pending.append(meaning)
                if abbreviation and pending:
                    rows.append(
                        {
                            "abbreviation": abbreviation.strip(),
                            "meaning": " ".join(pending).strip(),
                            "source_page": page_number,
                        }
                    )
                    pending = []
    finally:
        document.close()
    return rows


def abbreviation_candidates(text):
    """Find acronym-like tokens while retaining common spaced abbreviations."""
    candidates = {
        value.rstrip(".,;:")
        for value in re.findall(r"(?<!\w)[A-Z][A-Z0-9&/.-]{1,19}(?!\w)", text)
    }
    candidates.update(re.findall(r"(?<!\w)[A-Z](?:\s+(?:of\s+)?[A-Z])+(?!\w)", text))
    return sorted(candidates, key=str.casefold)
