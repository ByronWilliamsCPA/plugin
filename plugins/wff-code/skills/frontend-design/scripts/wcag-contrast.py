#!/usr/bin/env python3
"""Compute WCAG 2.x contrast ratios for hex color pairs.

Exists because an LLM estimating contrast by eye produced five undetected AA
failures in a real design task (2026-07-07 A/B trial, see
docs/tool-evals/claude-design-system-prompt.md). Contrast is a deterministic
computation; verify it with this script instead of asserting a ratio from
memory or visual estimation.

Usage:
    wcag-contrast.py FG BG [--large] [--label TEXT]
        Check one foreground/background hex pair.

    wcag-contrast.py --batch pairs.json
        Check many pairs at once. pairs.json is a JSON array of objects:
        [{"fg": "#2c1a0e", "bg": "#f8f3e8", "large": false, "label": "body text"}, ...]
        Include every text/background AND UI-component/state color pairing
        actually used in the deliverable -- resting, hover, active, and focus
        states each get their own entry, not just the resting state.

Exit code is 1 if any checked pair fails its required threshold (AA: 4.5:1
normal text, 3:1 large text/UI components), 0 if all pass. Always prints one
line per pair with the computed ratio, threshold, and pass/fail.
"""

import argparse
import json
import sys


class InvalidHexColorError(ValueError):
    """A color argument is not a valid 3- or 6-digit hex string."""


class InvalidLargeFlagError(ValueError):
    """A batch entry's `large` field is not a valid boolean value."""


class BatchEntryError(ValueError):
    """A batch entry is missing a required field or has the wrong shape."""


def _validate_hex(color: str) -> str:
    stripped = color.lstrip("#")
    if len(stripped) not in (3, 6) or not all(
        c in "0123456789abcdefABCDEF" for c in stripped
    ):
        raise InvalidHexColorError(f"not a valid 3- or 6-digit hex color: {color!r}")
    return stripped


def _linearize(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    hex_color = _validate_hex(hex_color)
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = _linearize(r), _linearize(g), _linearize(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _validate_large(value: object) -> bool:
    """Validate and coerce a batch entry's `large` field to a strict bool.

    Accepts a JSON boolean as-is. Also accepts the strings "true"/"false"
    (case-insensitive) as a forgiving alias, since some JSON is authored by
    hand with the flag quoted. Any other value (a number, null, or a string
    that is not "true"/"false") is rejected outright: an arbitrary truthy
    string must never silently select the lenient 3:1 large-text threshold.

    Args:
        value: the raw `large` field read from a batch entry.

    Returns:
        The field's boolean meaning.

    Raises:
        InvalidLargeFlagError: if `value` is not a bool or a "true"/"false"
            string.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise InvalidLargeFlagError(
        f'"large" must be a boolean (or the string "true"/"false"), got {value!r}'
    )


def _parse_batch_entry(entry: object) -> tuple[str, str, bool, str]:
    """Validate and extract fg/bg/large/label from one batch entry.

    Shares the same downstream `check_pair` path as single-pair mode: this
    function only validates the shape of a batch entry and coerces `large`
    to a strict bool; hex-format validation of `fg`/`bg` still happens once,
    inside `check_pair`.

    Args:
        entry: one element of the batch JSON array. Expected to be an
            object with string `fg`/`bg` fields, an optional `large` field
            (bool or a "true"/"false" string), and an optional `label`.

    Returns:
        The validated (fg, bg, large, label) tuple.

    Raises:
        BatchEntryError: if `entry` is not an object, is missing `fg` or
            `bg`, or has a non-string `fg`/`bg`.
        InvalidLargeFlagError: if `large` is present but not a valid
            boolean value.
    """
    if not isinstance(entry, dict):
        raise BatchEntryError(
            f"entry must be a JSON object, got {type(entry).__name__}"
        )
    missing = [key for key in ("fg", "bg") if key not in entry]
    if missing:
        raise BatchEntryError(f"missing required field(s): {', '.join(missing)}")
    fg, bg = entry["fg"], entry["bg"]
    if not isinstance(fg, str) or not isinstance(bg, str):
        raise BatchEntryError("'fg' and 'bg' must be strings")
    large = _validate_large(entry.get("large", False))
    label = entry.get("label", "")
    return fg, bg, large, str(label) if label else ""


def check_pair(fg: str, bg: str, large: bool, label: str) -> bool:
    tag = f" ({label})" if label else ""
    try:
        ratio = contrast_ratio(fg, bg)
    except InvalidHexColorError as exc:
        print(f"FAIL: {fg} on {bg}{tag} = invalid input ({exc})")
        return False
    threshold = 3.0 if large else 4.5
    passed = ratio >= threshold
    status = "PASS" if passed else "FAIL"
    print(f"{status}: {fg} on {bg}{tag} = {ratio:.2f}:1 (need >= {threshold}:1)")
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fg", nargs="?", help="Foreground hex color")
    parser.add_argument("bg", nargs="?", help="Background hex color")
    parser.add_argument(
        "--large",
        action="store_true",
        help="Use the 3:1 large-text/UI-component threshold",
    )
    parser.add_argument("--label", default="", help="Context label for this pair")
    parser.add_argument(
        "--batch", help="Path to a JSON file of {fg, bg, large, label} objects"
    )
    args = parser.parse_args()

    if args.batch:
        with open(args.batch) as f:
            pairs = json.load(f)
        if not isinstance(pairs, list):
            print(
                f"ERROR: {args.batch} must contain a JSON array of "
                f"pair objects, got {type(pairs).__name__}"
            )
            sys.exit(1)
        # Per-entry error isolation: one malformed entry must not abort the
        # rest of the batch. Each entry is validated and checked
        # independently; a parse failure is reported and counted as a
        # failure, and the loop continues to the remaining entries.
        results: list[bool] = []
        had_entry_error = False
        for index, entry in enumerate(pairs):
            try:
                fg, bg, large, label = _parse_batch_entry(entry)
            except (BatchEntryError, InvalidLargeFlagError) as exc:
                print(f"ERROR: batch entry {index} malformed: {exc}")
                had_entry_error = True
                continue
            results.append(check_pair(fg, bg, large, label))
        sys.exit(0 if results and all(results) and not had_entry_error else 1)

    if not args.fg or not args.bg:
        parser.error("fg and bg are required unless --batch is used")

    ok = check_pair(args.fg, args.bg, args.large, args.label)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
