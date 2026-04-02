#!/usr/bin/env python3
"""
SyncReviewExcel.py  —  Import / Export review JSON <-> Excel (.xls) files

Usage:
  python3 SyncReviewExcel.py import reviews.json [options]
  python3 SyncReviewExcel.py export reviews.json [options]

Dependencies:
  pip install xlrd xlwt xlutils
"""

__version__ = '2.8.0'

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import xlrd
    import xlwt
    from xlutils.copy import copy as xl_copy
except ImportError:
    print("❌ Missing dependencies. Run: pip install xlrd xlwt xlutils", file=sys.stderr)
    sys.exit(1)

# ── Sheet layout constants ────────────────────────────────────────────────────

SHEET_NAME   = 'Defect_Description_Sheet'
DATA_ROW     = 9    # 0-based index of first data row (row 10 in Excel)
COL_NO       = 0    # A — N°
COL_LOC      = 1    # B — Localization
COL_DATE     = 2    # C — Date annotation (written by this script)
COL_DESC     = 3    # D — Defect Description
COL_SEV      = 5    # F — Severity
ROW_REVIEWER = 1    # 0-based: F2 — reviewer_full_name
ROW_NB_ITEMS = 2    # 0-based: F3 — nb_items
ROW_DURATION = 3    # 0-based: F4 — review_duration  (HH:MM)
ROW_RETDATE  = 4    # 0-based: F5 — return_date      (DD/MM/YYYY)
COL_META     = 5    # F column for summary cells


# ── Excel date helpers ────────────────────────────────────────────────────────

def _xl_date_to_str(xl_float, datemode=0) -> str:
    """Convert an Excel float date to 'YYYY-MM-DD HH:MM', or '' if zero/invalid."""
    if not xl_float:
        return ''
    try:
        t = xlrd.xldate_as_tuple(xl_float, datemode)
        dt = datetime(*t[:6])
        return dt.strftime('%Y-%m-%d %H:%M') if (t[3] or t[4]) else dt.strftime('%Y-%m-%d')
    except Exception:
        return str(xl_float)


def _str_to_xl_date(s: str, datemode=0) -> float:
    """Convert 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM' to Excel serial float, 0.0 on failure."""
    if not s:
        return 0.0
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            delta = dt - datetime(1899, 12, 30)
            return delta.days + delta.seconds / 86400.0
        except ValueError:
            continue
    return 0.0


def _xl_duration_to_hhmm(duration_xl: float) -> str:
    """Convert Excel duration float (fraction of a day) to 'HH:MM' string."""
    total_minutes = round(duration_xl * 24 * 60)
    hh = total_minutes // 60
    mm = total_minutes % 60
    return f'{hh:02d}:{mm:02d}'


def _xl_date_to_ddmmyyyy(xl_float, datemode=0) -> str:
    """Convert Excel serial float to 'DD/MM/YYYY' string."""
    if not xl_float:
        return ''
    try:
        t = xlrd.xldate_as_tuple(xl_float, datemode)
        return f'{t[2]:02d}/{t[1]:02d}/{t[0]:04d}'
    except Exception:
        return ''


# ── xlwt cell format helpers ──────────────────────────────────────────────────

def _make_date_style(wb_out) -> xlwt.XFStyle:
    style = xlwt.XFStyle()
    style.num_format_str = 'DD/MM/YYYY'
    return style


def _make_time_style(wb_out) -> xlwt.XFStyle:
    style = xlwt.XFStyle()
    style.num_format_str = '[HH]:MM'
    return style


# ── File discovery ────────────────────────────────────────────────────────────

def _find_xls_files(directory: str) -> list:
    return sorted(Path(directory).glob('*.xls'))


def _reviewer_alias(path: Path) -> str:
    """PREFIX_Alias.xls → 'Alias'."""
    parts = path.stem.split('_', 1)
    return parts[1] if len(parts) == 2 else path.stem


# ── XLS wrapper ───────────────────────────────────────────────────────────────

def _is_empty_row(loc: str, desc: str, sev: str) -> bool:
    """A row is considered empty when Localization is 'Req :' (placeholder)
    and both Defect Description and Severity are blank."""
    loc_stripped = loc.strip().rstrip(':').strip()
    return loc_stripped.lower() == 'req' and not desc and not sev


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

    def real_data_rows(self) -> list:
        """Return list of (row_index, loc, desc, sev, date_str) for non-empty rows."""
        rows = []
        for r in range(DATA_ROW, self.ws.nrows):
            loc  = str(self.ws.cell(r, COL_LOC).value).strip()
            desc = str(self.ws.cell(r, COL_DESC).value).strip()
            sev  = str(self.ws.cell(r, COL_SEV).value).strip()
            if _is_empty_row(loc, desc, sev):
                continue
            if not (desc or sev):
                continue
            # Date from col C
            dc = self.ws.cell(r, COL_DATE)
            if dc.ctype == xlrd.XL_CELL_DATE:
                date_str = _xl_date_to_str(dc.value, self.wb.datemode)
            else:
                date_str = str(dc.value).strip() if dc.value else ''
            rows.append((r, loc, desc, sev, date_str))
        return rows

    def first_free_row(self) -> int:
        """Return 0-based index of first row usable for new data (past placeholders)."""
        last_used = DATA_ROW - 1
        for r in range(DATA_ROW, self.ws.nrows):
            loc  = str(self.ws.cell(r, COL_LOC).value).strip()
            desc = str(self.ws.cell(r, COL_DESC).value).strip()
            sev  = str(self.ws.cell(r, COL_SEV).value).strip()
            if not _is_empty_row(loc, desc, sev) and (desc or sev or loc):
                last_used = r
        return last_used + 1

    def max_no(self) -> int:
        """Return highest N° value already in the sheet."""
        m = 0
        for r in range(DATA_ROW, self.ws.nrows):
            v = self.ws.cell(r, COL_NO).value
            if isinstance(v, (int, float)) and int(v) > m:
                m = int(v)
        return m


# ── User / reviewer matching ──────────────────────────────────────────────────

def _build_mapping(xls_files, json_users, manual_maps):
    """Return (mapping dict, warnings list, errors list)."""
    valid_files  = [f for f in xls_files if f.valid]
    reviewer_map = {f.reviewer: f for f in valid_files}
    mapping  = {}
    warnings = []
    errors   = []

    for user in json_users:
        if user in manual_maps:
            full_name = manual_maps[user]
            if full_name in reviewer_map:
                mapping[user] = reviewer_map[full_name]
            else:
                errors.append(f"--map {user}:{full_name!r} → no XLS with that reviewer name")
            continue

        matches = [f for f in valid_files if user.lower() in f.reviewer.lower()]
        if not matches:
            warnings.append(f"'{user}' → no matching reviewer (will be skipped)")
        elif len(matches) > 1:
            names = ', '.join(f"'{m.reviewer}'" for m in matches)
            errors.append(f"'{user}' matches multiple reviewers: {names}")
        else:
            mapping[user] = matches[0]

    return mapping, warnings, errors


# ── Review key (for merge deduplication) ─────────────────────────────────────

def _review_key(artifact: str, text: str, context: str) -> tuple:
    return (artifact.strip().lower(), text.strip().lower(), context.strip().lower())


# ── Write helpers ─────────────────────────────────────────────────────────────

def _write_row(ws_out, row, no, artifact, desc, context, date_str, date_style):
    ws_out.write(row, COL_NO,   no)
    ws_out.write(row, COL_LOC,  artifact)
    ws_out.write(row, COL_DESC, desc)
    ws_out.write(row, COL_SEV,  context)
    if date_str:
        ws_out.write(row, COL_DATE, date_str)


def _write_summary(ws_out, nb_added, all_dates, datemode, date_style, time_style):
    ws_out.write(ROW_NB_ITEMS, COL_META, nb_added)

    if not all_dates:
        return
    xl_dates = [_str_to_xl_date(d, datemode) for d in all_dates if d]
    xl_dates = [x for x in xl_dates if x]
    if not xl_dates:
        return

    duration = max(xl_dates) - min(xl_dates)
    ws_out.write(ROW_DURATION, COL_META, duration, time_style)
    ws_out.write(ROW_RETDATE,  COL_META, max(xl_dates), date_style)


# ── IMPORT ────────────────────────────────────────────────────────────────────

def cmd_import(args):
    verbose = args.verbose
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

    print(f"\n📂 Directory  : {directory}")
    print(f"📋 JSON file  : {json_path}  ({len(reviews)} entries)")
    print(f"📊 XLS files  : {len(xls_files)} found")
    print(f"⚙️  Mode       : {args.import_mode}")
    print()

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
    if not args.proceed:
        confirm = input("▶ Proceed with import? [y/N] ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            sys.exit(0)

    # Group JSON reviews by user
    by_user: dict = {}
    for r in reviews:
        by_user.setdefault(r.get('user', ''), []).append(r)

    mode = args.import_mode

    for user, xf in mapping.items():
        user_reviews = by_user.get(user, [])
        if not user_reviews:
            print(f"  ℹ️  '{user}': no reviews in JSON — skipping")
            continue

        wb_out   = xl_copy(xf.wb)
        ws_out   = wb_out.get_sheet(xf.wb.sheet_names().index(SHEET_NAME))
        datemode = xf.wb.datemode
        date_style = _make_date_style(wb_out)
        time_style = _make_time_style(wb_out)

        existing = xf.real_data_rows()   # [(row_idx, loc, desc, sev, date)]

        n_new = n_updated = n_existing = n_total = 0

        if mode == 'overwrite':
            # ── Overwrite: clear all data rows then write JSON entries ──
            # Clear from DATA_ROW to end of used area
            for r in range(DATA_ROW, xf.ws.nrows):
                for c in range(xf.ws.ncols):
                    ws_out.write(r, c, '')
            next_row = DATA_ROW
            next_no  = 1
            for rv in user_reviews:
                _write_row(ws_out, next_row, next_no,
                           rv.get('artifact', ''), rv.get('text', ''),
                           rv.get('context', ''), rv.get('date', ''), date_style)
                next_row += 1
                next_no  += 1
                n_new    += 1
            if verbose:
                print(f"  🗑️  '{user}': cleared {len(existing)} existing row(s)")

        elif mode == 'append':
            # ── Append: write only JSON entries not already present ──
            exist_keys = {_review_key(loc, desc, sev) for _, loc, desc, sev, _ in existing}
            next_row   = xf.first_free_row()
            next_no    = xf.max_no() + 1
            for rv in user_reviews:
                k = _review_key(rv.get('artifact', ''), rv.get('text', ''), rv.get('context', ''))
                if k in exist_keys:
                    n_existing += 1
                    if verbose:
                        print(f"    ⏭  already exists: [{rv.get('context','')}] {rv.get('artifact','')[:40]}")
                    continue
                _write_row(ws_out, next_row, next_no,
                           rv.get('artifact', ''), rv.get('text', ''),
                           rv.get('context', ''), rv.get('date', ''), date_style)
                next_row += 1
                next_no  += 1
                n_new    += 1

        else:  # merge (default)
            # ── Merge: update matching rows, append new ones ──
            exist_map = {}
            for row_idx, loc, desc, sev, date_str in existing:
                k = _review_key(loc, desc, sev)
                exist_map[k] = (row_idx, loc, desc, sev, date_str)

            next_row      = xf.first_free_row()
            written_extra = 0

            for rv in user_reviews:
                k = _review_key(rv.get('artifact', ''), rv.get('text', ''), rv.get('context', ''))
                if k in exist_map:
                    row_idx, loc, desc, sev, old_date = exist_map[k]
                    new_date = rv.get('date', '')
                    if new_date and new_date != old_date:
                        ws_out.write(row_idx, COL_DATE, new_date)
                        n_updated += 1
                        if verbose:
                            print(f"    🔄 updated date: [{sev}] {loc[:40]}")
                    else:
                        n_existing += 1
                        if verbose:
                            print(f"    ⏭  unchanged: [{sev}] {loc[:40]}")
                else:
                    actual_row = next_row + written_extra
                    next_no    = xf.max_no() + 1 + written_extra
                    _write_row(ws_out, actual_row, next_no,
                               rv.get('artifact', ''), rv.get('text', ''),
                               rv.get('context', ''), rv.get('date', ''), date_style)
                    written_extra += 1
                    n_new += 1
                    if verbose:
                        print(f"    ➕ new: [{rv.get('context','')}] {rv.get('artifact','')[:40]}")

        # ── Summary cells ──
        all_dates_user = [rv.get('date', '') for rv in user_reviews if rv.get('date')]

        if mode == 'overwrite':
            nb_total = n_new
        elif mode == 'append':
            nb_total = len(existing) + n_new
        else:  # merge
            nb_total = len(existing) + n_new

        _write_summary(ws_out, nb_total, all_dates_user, datemode, date_style, time_style)

        wb_out.save(str(xf.path))

        # ── Per-file report ──
        if mode == 'overwrite':
            print(f"  ✅ {xf.path.name} — overwrite: {n_new} row(s) written for '{user}'")
        elif mode == 'append':
            print(f"  ✅ {xf.path.name} — append: {n_new} new, {n_existing} already present  ('{user}')")
        else:
            print(f"  ✅ {xf.path.name} — merge: {n_new} new, {n_updated} updated, {n_existing} unchanged  ('{user}')")

    print("\n✅ Import complete.")


# ── EXPORT ────────────────────────────────────────────────────────────────────

def cmd_export(args):
    verbose   = args.verbose
    json_path = Path(args.json_file)
    directory = args.dir or str(json_path.parent)
    xls_files = [XLSFile(p) for p in _find_xls_files(directory)]

    print(f"\n📂 Directory : {directory}")
    print(f"📋 JSON file : {json_path}  (will be written)")
    print(f"📊 XLS files : {len(xls_files)} found\n")

    valid_files = [f for f in xls_files if f.valid]
    for f in [f for f in xls_files if not f.valid]:
        print(f"  ❌ {f.path.name}  —  {f.reason}")
    for f in valid_files:
        print(f"  ✅ {f.path.name}  —  reviewer: {f.reviewer}")

    if not valid_files:
        print("\n⚠️  No valid XLS files found — nothing to export.", file=sys.stderr)
        sys.exit(1)

    print()
    if not args.proceed:
        confirm = input("▶ Proceed with export? [y/N] ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            sys.exit(0)

    reviews    = []
    total_rows = 0

    for xf in valid_files:
        # Fallback date: F5 (return_date) of the file, formatted YYYY-MM-DD
        fallback_date = ''
        ret_cell = xf.ws.cell(ROW_RETDATE, COL_META)
        if ret_cell.ctype == xlrd.XL_CELL_DATE and ret_cell.value:
            t = xlrd.xldate_as_tuple(ret_cell.value, xf.wb.datemode)
            fallback_date = f'{t[0]:04d}-{t[1]:02d}-{t[2]:02d}'
        elif ret_cell.ctype == xlrd.XL_CELL_TEXT:
            fallback_date = str(ret_cell.value).strip()

        rows_data = xf.real_data_rows()
        rows      = 0
        for _, loc, desc, sev, date_str in rows_data:
            effective_date = date_str if date_str else fallback_date
            reviews.append({
                'user'    : xf.reviewer,
                'artifact': loc,
                'context' : sev,
                'text'    : desc,
                'date'    : effective_date,
            })
            rows += 1
            if verbose:
                date_src = '' if date_str else ' (fallback date)'
                print(f"    📎 [{sev}] {loc[:40]}  —  {desc[:50]}  [{effective_date}{date_src}]")

        print(f"  📤 {xf.path.name}  —  {rows} row(s) from '{xf.reviewer}'")
        total_rows += rows

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Export complete: {total_rows} review(s) → {json_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='SyncReviewExcel — sync review JSON with Excel (.xls) peer-review files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 SyncReviewExcel.py import reviews.json
  python3 SyncReviewExcel.py import reviews.json --import-mode overwrite -y
  python3 SyncReviewExcel.py import reviews.json --dir /path/to/xlsfiles --map "nono:Norbert H."
  python3 SyncReviewExcel.py export reviews.json -v
""")

    parser.add_argument('action', choices=['import', 'export'],
                        help='Direction: import (JSON→XLS) or export (XLS→JSON)')
    parser.add_argument('json_file',
                        help='Path to the review JSON file')
    parser.add_argument('--dir', default=None,
                        help='Directory containing XLS files (default: same folder as JSON file)')
    parser.add_argument('--map', action='append', metavar='user:Full Name',
                        help='Manual user→reviewer mapping, e.g. --map "phil:Philippe G." (repeatable)')
    parser.add_argument('--import-mode', choices=['overwrite', 'append', 'merge'],
                        default='merge',
                        help='Import strategy: overwrite | append | merge (default: merge)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print details for each row processed')
    parser.add_argument('-y', '--proceed', action='store_true',
                        help='Skip confirmation prompt and proceed automatically')
    parser.add_argument('--version', action='version', version=f'SyncReviewExcel {__version__}')

    args = parser.parse_args()

    if args.action == 'import':
        cmd_import(args)
    else:
        cmd_export(args)


if __name__ == '__main__':
    main()
