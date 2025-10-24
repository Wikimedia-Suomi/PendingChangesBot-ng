from __future__ import annotations

import re


def validate_isbn_10(isbn: str) -> bool:
    """Validate ISBN-10 checksum."""
    if len(isbn) != 10:
        return False

    total = 0
    for i in range(9):
        if not isbn[i].isdigit():
            return False
        total += int(isbn[i]) * (10 - i)

    check_digit = 10 if isbn[9].upper() == "X" else int(isbn[9]) if isbn[9].isdigit() else -1
    if check_digit < 0:
        return False

    return total % 11 == (11 - check_digit) % 11


def validate_isbn_13(isbn: str) -> bool:
    """Validate ISBN-13 checksum."""
    if (
        len(isbn) != 13
        or not isbn.isdigit()
        or not (isbn.startswith("978") or isbn.startswith("979"))
    ):
        return False

    total = sum(int(isbn[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
    check_digit = (10 - (total % 10)) % 10
    return int(isbn[12]) == check_digit


def find_invalid_isbns(text: str) -> list[str]:
    """Find all ISBNs in text and return list of invalid ones."""
    isbn_pattern = re.compile(
        r"isbn\s*[=:]?\s*([0-9Xx\-\s]{1,30}?)(?=\s+\d{4}(?:\D|$)|[^\d\sXx\-]|$)", re.IGNORECASE
    )

    invalid_isbns = []
    for match in isbn_pattern.finditer(text):
        isbn_raw = match.group(1)
        isbn_clean = re.sub(r"[\s\-]", "", isbn_raw)

        if not isbn_clean:
            continue

        is_valid = (len(isbn_clean) == 10 and validate_isbn_10(isbn_clean)) or (
            len(isbn_clean) == 13 and validate_isbn_13(isbn_clean)
        )

        if not is_valid:
            invalid_isbns.append(isbn_raw.strip())

    return invalid_isbns
