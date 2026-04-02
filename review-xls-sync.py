#!/usr/bin/env python3
"""
review-xls-sync.py  —  Import / Export review JSON <-> Excel (.xls) files

Usage:
  python3 review-xls-sync.py import reviews.json [--dir DIR] [--map user:Full Name ...]
  python3 review-xls-sync.py export reviews.json [--dir DIR]

Dependencies:
  pip install xlrd xlwt xlutils
"""

__version__ = '1.0.0'

import argparse
import json
import os
import sys
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from glob import glob

try:
    import xlrd
    import xlwt
    from xlutils.copy import copy as xl_copy
except ImportError:
    print("❌ Missing dependencies. Run: pip install xlrd xlwt xlutils", file=sys.stderr)
    sys.exit(1)

SHEET_NAME   = 'Defect_Description_Sheet'
DATA_ROW     = 9   # 0-based: row index of first data row (row 10 in Excel)
COL_NO       = 0   # A  — N°
COL_LOC      = 1   # B  — Localization
COL_DESC     = 3   # D  — Defect Description
COL_SEV      = 5   # F  — Severity
ROW_REVIEWER = 1   # 0-based: F2
ROW_NB_ITEMS = 2   # 0-based: F3
ROW_DURATION = 3   # 0-based: F4
ROW_RETDATE  = 4   # 0-based: F5
COL_META     = 5   # F column for reviewer/nb_items/duration/return_date


# ── Excel date helpers ────────────────────────────────────────────────────────

def _xl_date_to_str(xl_float, datemode=0) -> str:
    """Convert an Excel float date to 'YYYY-MM-DD HH:MM' string, or '' if zero."""
    if not xl_float:
        return ''
    try:
        t = xlrd.xldate_as_tuple(xl_float, datemode)
        dt = datetime(*t[:6])
        return dt.strftime('%Y-%m-%d %H:%M') if t[3] or t[4] else dt.strftime('%Y-%m-%d')
    except Exception:
        return str(xl_float)


def _str_to_xl_date(s: str, datemode=0) -> float:
    """Convert 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM' to Excel float, or 0.0 on failure."""
    if not s:
        return 0.0
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            epoch = datetime(1899, 12, 30)
            delta = dt - epoch
            return delta.days + delta.seconds / 86400.0
        except ValueError:
            continue
    return 0.0


def _duration_xl(dates: list[str], datemode=0) -> float:
    """Return Excel float duration (latest - earliest) from a list of date strings."""
    parsed = []
    for d in dates:
        xl = _str_to_xl_date(d, datemode)
        if xl:
            parsed.append(xl)
    if len(parsed) < 2:
        return 0.0
    return max(parsed) - min(parsed)


# ── File discovery ────────────────────────────────────────────────────────────

def _find_xls_files(directory: str) -> list[Path]:
    """Return all *.xls files in directory (non-recursive)."""
    return sorted(Path(directory).glob('*.xls'))


def _detect_prefix(xls_files: list[Path]) -> str | None:
    """Detect common project prefix (e.g. 'EXAMPLE' from 'EXAMPLE_Yves.xls')."""
    if not xls_files:
        return None
    names = [f.stem for f in xls_files]          # e.g. ['EXAMPLE_Yves', 'EXAMPLE_Bob']
    # Split on first underscore; all must share the same prefix
    parts = [n.split('_', 1) for n in names]
    if not all(len(p) == 2 for p in parts):
        return None
    prefixes = {p[0] for p in parts}
    return prefixes.pop() if len(prefixes) == 1 else None


def _reviewer_alias(path: Path) -> str:
    """Extract reviewer alias from filename: PREFIX_Alias.xls → 'Alias'."""
    parts = path.stem.split('_', 1)
    return parts[1] if len(parts) == 2 else path.stem


# ── XLS reading ───────────────────────────────────────────────────────────────

class XLSFile:
    """Wraps a single XLS file and validates its expected structure."""

    def __init__(self, path: Path):
        self.path     = path
        self.alias    = _reviewer_alias(path)
        self.valid    = False
        self.reason   = ''
        self.reviewer = ''
        self.wb       = None
        self.ws       = None
        self._load()

    def _load(self):
        try:
            self.wb = xlrd.open_workbook(str(self.path), formatting_info=True)
        except Exception as e:
            self.reason = f"cannot open: {e}"
            return
        if SHEET_NAME not in self.wb.sheet_names():
            self.reason = f"sheet '{SHEET_NAME}' not found"
            return
        self.ws = self.wb.sheet_by_name(SHEET_NAME)
        if self.ws.nrows < DATA_ROW + 1:
            self.reason = "not enough rows"
            return
        rv = str(self.ws.cell(ROW_REVIEWER, COL_META).value).strip()
        if not rv:
            self.reason = "F2 (reviewer_full_name) is empty"
            return
        self.reviewer = rv
        self.valid    = True

    def data_rows(self) -> list[dict]:
        """Return existing data rows as list of dicts."""
        rows = []
        for r in range(DATA_ROW, self.ws.nrows):
            loc  = str(self.ws.cell(r, COL_LOC).value).strip()
            desc = str(self.ws.cell(r, COL_DESC).value).strip()
            sev  = str(self.ws.cell(r, COL_SEV).value).strip()
            if loc or desc or sev:
                rows.append({'localization': loc, 'text': desc, 'severity': sev})
        return rows

    def last_data_row_index(self) -> int:
        """Return 0-based index of last non-empty data row, or DATA_ROW-1 if empty."""
        last = DATA_ROW - 1
        for r in range(DATA_ROW, self.ws.nrows):
            loc  = str(self.ws.cell(r, COL_LOC).value).strip()
            desc = str(self.ws.cell(r, COL_DESC).value).strip()
            sev  = str(self.ws.cell(r, COL_SEV).value).strip()
            if loc or desc or sev:
                last = r
        return last


# ── User matching ─────────────────────────────────────────────────────────────

def _build_mapping(xls_files: list['XLSFile'], json_users: list[str],
                   manual_maps: dict[str, str]) -> dict[str, 'XLSFile']:
    """
    Build {json_user → XLSFile} mapping.

    Rules:
    - manual_maps (--map user:Full Name) override auto-detection
    - Auto: json_user (case-insensitive) must appear as a substring of exactly
      one reviewer_full_name across all valid XLS files
    - If a json_user matches multiple reviewer_full_names → error
    - Unmatched json_users are reported but do not block the operation
      (unless ALL users are unmatched)
    """
    valid_files = [f for f in xls_files if f.valid]
    reviewer_map = {f.reviewer: f for f in valid_files}

    mapping: dict[str, XLSFile] = {}
    warnings: list[str] = []
    errors:   list[str] = []

    for user in json_users:
        if user in manual_maps:
            full_name = manual_maps[user]
            if full_name in reviewer_map:
                mapping[user] = reviewer_map[full_name]
            else:
                errors.append(f"  --map {user}:{full_name!r} → no XLS with that reviewer name")
            continue

        # Auto-match: user substring in reviewer_full_name
        matches = [f for f in valid_files
                   if user.lower() in f.reviewer.lower()]
        if len(matches) == 0:
            warnings.append(f"  '{user}' → no matching reviewer (will be skipped)")
        elif len(matches) > 1:
            names = ', '.join(f"'{m.reviewer}'" for m in matches)
            errors.append(f"  '{user}' matches multiple reviewers: {names}")
        else:
            mapping[user] = matches[0]

    return mapping, warnings, errors


# ── IMPORT ────────────────────────────────────────────────────────────────────

def cmd_import(args):
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"❌ JSON file not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(json_path, encoding='utf-8') as f:
        reviews = json.load(f)

    if not isinstance(reviews, list) or not reviews:
        print("❌ JSON file is empty or not an array.", file=sys.stderr)
        sys.exit(1)

    directory = args.dir or str(json_path.parent)
    xls_files = [XLSFile(p) for p in _find_xls_files(directory)]

    print(f"\n📂 Directory : {directory}")
    print(f"📋 JSON file : {json_path}  ({len(reviews)} entries)")
    print(f"📊 XLS files : {len(xls_files)} found\n")

    for f in xls_files:
        status = '✅' if f.valid else '❌'
        print(f"  {status} {f.path.name}")
        if f.valid:
            print(f"       reviewer : {f.reviewer}")
        else:
            print(f"       reason   : {f.reason}")

    print()

    json_users = sorted({r['user'] for r in reviews if 'user' in r})
    print(f"👤 JSON users : {json_users}")

    manual_maps = {}
    for m in (args.map or []):
        if ':' not in m:
            print(f"❌ Invalid --map format '{m}' (expected user:Full Name)", file=sys.stderr)
            sys.exit(1)
        u, full = m.split(':', 1)
        manual_maps[u.strip()] = full.strip()

    mapping, warnings, errors = _build_mapping(xls_files, json_users, manual_maps)

    print("\n🔗 User → XLS mapping:")
    for user, xf in mapping.items():
        print(f"  '{user}'  →  '{xf.reviewer}'  ({xf.path.name})")
    for w in warnings:
        print(f"  ⚠️  {w}")
    for e in errors:
        print(f"  ❌ {e}")

    if errors:
        print("\n❌ Mapping errors — aborting.", file=sys.stderr)
        sys.exit(1)
    if not mapping:
        print("\n⚠️  No users could be matched — nothing to import.", file=sys.stderr)
        sys.exit(1)

    print()
    confirm = input("▶ Proceed with import? [y/N] ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)

    # Group reviews by user
    by_user: dict[str, list[dict]] = {}
    for r in reviews:
        u = r.get('user', '')
        by_user.setdefault(u, []).append(r)

    for user, xf in mapping.items():
        user_reviews = by_user.get(user, [])
        if not user_reviews:
            print(f"  ℹ️  {user}: no reviews in JSON — skipping")
            continue

        wb_out  = xl_copy(xf.wb)
        ws_out  = wb_out.get_sheet(xf.wb.sheet_names().index(SHEET_NAME))
        datemode = xf.wb.datemode

        # Find first empty row to append to
        next_row = xf.last_data_row_index() + 1

        # Determine starting N°
        last_no = 0
        for r in range(DATA_ROW, xf.ws.nrows):
            v = xf.ws.cell(r, COL_NO).value
            if isinstance(v, (int, float)) and v > last_no:
                last_no = int(v)
        next_no = last_no + 1

        added = 0
        for rv in user_reviews:
            artifact = rv.get('artifact', '')
            text     = rv.get('text', '')
            context  = rv.get('context', '')
            date_str = rv.get('date', '')

            ws_out.write(next_row, COL_NO,  next_no)
            ws_out.write(next_row, COL_LOC, artifact)
            ws_out.write(next_row, COL_DESC, text)
            ws_out.write(next_row, COL_SEV, context)

            # Date as cell comment on the N° cell (xlwt note)
            if date_str:
                # xlwt doesn't support comments natively; write date in a hidden-ish column
                # Use column C (index 2) as a date annotation column
                ws_out.write(next_row, 2, date_str)

            next_row += 1
            next_no  += 1
            added    += 1

        # Update summary cells
        all_dates = [rv.get('date', '') for rv in user_reviews if rv.get('date')]

        nb_items_cell  = float(xf.ws.cell(ROW_NB_ITEMS, COL_META).value or 0)
        ws_out.write(ROW_NB_ITEMS, COL_META, int(nb_items_cell) + added)

        if all_dates:
            xl_dates = [_str_to_xl_date(d, datemode) for d in all_dates if d]
            xl_dates = [x for x in xl_dates if x]
            if xl_dates:
                duration = max(xl_dates) - min(xl_dates)
                ws_out.write(ROW_DURATION, COL_META, duration)
                ws_out.write(ROW_RETDATE,  COL_META, max(xl_dates))

        out_path = xf.path
        wb_out.save(str(out_path))
        print(f"  ✅ {xf.path.name} — {added} row(s) added for '{user}'")

    print("\n✅ Import complete.")


# ── EXPORT ────────────────────────────────────────────────────────────────────

def cmd_export(args):
    json_path = Path(args.json_file)
    directory = args.dir or str(json_path.parent)
    xls_files = [XLSFile(p) for p in _find_xls_files(directory)]

    print(f"\n📂 Directory : {directory}")
    print(f"📋 JSON file : {json_path}  (will be written)")
    print(f"📊 XLS files : {len(xls_files)} found\n")

    valid_files = [f for f in xls_files if f.valid]
    invalid     = [f for f in xls_files if not f.valid]

    for f in valid_files:
        print(f"  ✅ {f.path.name}  —  reviewer: {f.reviewer}")
    for f in invalid:
        print(f"  ❌ {f.path.name}  —  {f.reason}")

    if not valid_files:
        print("\n⚠️  No valid XLS files found — nothing to export.", file=sys.stderr)
        sys.exit(1)

    print()
    confirm = input("▶ Proceed with export? [y/N] ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)

    reviews: list[dict] = []
    total_rows = 0

    for xf in valid_files:
        datemode = xf.wb.datemode
        rows = 0
        for r in range(DATA_ROW, xf.ws.nrows):
            loc  = str(xf.ws.cell(r, COL_LOC).value).strip()
            desc = str(xf.ws.cell(r, COL_DESC).value).strip()
            sev  = str(xf.ws.cell(r, COL_SEV).value).strip()
            # Date annotation stored in column C (index 2) by import
            date_val = xf.ws.cell(r, 2).value
            if xf.ws.cell(r, 2).ctype == xlrd.XL_CELL_DATE:
                date_str = _xl_date_to_str(date_val, datemode)
            else:
                date_str = str(date_val).strip() if date_val else ''

            # Skip rows with no meaningful content (must have at least desc or sev)
            if not (desc or sev):
                continue

            reviews.append({
                'user'    : xf.reviewer,
                'artifact': loc,
                'context' : sev,
                'text'    : desc,
                'date'    : date_str,
            })
            rows += 1

        print(f"  📤 {xf.path.name}  —  {rows} row(s) exported from '{xf.reviewer}'")
        total_rows += rows

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Export complete: {total_rows} review(s) → {json_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Sync review JSON with Excel (.xls) peer-review files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 review-xls-sync.py import reviews.json
  python3 review-xls-sync.py import reviews.json --dir /path/to/xlsfiles
  python3 review-xls-sync.py import reviews.json --map "nono:Norbert Hejakouja"
  python3 review-xls-sync.py export reviews.json
""")

    parser.add_argument('action', choices=['import', 'export'],
                        help='Direction: import (JSON→XLS) or export (XLS→JSON)')
    parser.add_argument('json_file',
                        help='Path to the review JSON file')
    parser.add_argument('--dir', default=None,
                        help='Directory containing XLS files (default: same as JSON file)')
    parser.add_argument('--map', action='append', metavar='user:Full Name',
                        help='Manual user→reviewer mapping (can be repeated)')
    parser.add_argument('--version', action='version', version=f'review-xls-sync {__version__}')

    args = parser.parse_args()

    if args.action == 'import':
        cmd_import(args)
    else:
        cmd_export(args)


if __name__ == '__main__':
    main()
