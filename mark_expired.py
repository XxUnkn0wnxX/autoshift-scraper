import os
import argparse
import json
from datetime import datetime, timezone, timedelta
from os import path
import re as _re

from github import Github, InputGitTreeElement
from github.GithubException import GithubException, UnknownObjectException

# ---- Timezone for Gearbox (CST/CDT with DST) ----
# WHY: Treat human-entered/website dates as America/Chicago local time,
# then convert to UTC for storage/comparison.
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    # If running on <3.9 and backports is installed, this will work.
    from backports.zoneinfo import ZoneInfo  # type: ignore

GEARBOX_TZ = ZoneInfo("America/Chicago")
SHIFTCODESJSONPATH = os.environ.get("SHIFTCODESJSONPATH", "data/shiftcodes.json")

# -------------------------
# GitHub upload helper
# -------------------------

def upload_shiftfile(filepath, user, repo_name, token, commit_msg=None, branch=None):
    """
    Upload or update the JSON file to GitHub.

    - Uses the basename of `filepath` as the destination path in the repo.
    - Creates/updates on the repository's default branch (fallback: 'main').
    - If the repository is empty, attempts to bootstrap the first commit.
    """
    if not (user and repo_name and token):
        print("GitHub credentials incomplete; skipping upload.")
        return False

    dest_name = path.basename(filepath)  # e.g. "shiftcodes.json"
    commit_msg = commit_msg or f"Update {dest_name} via mark_expired.py"

    with open(filepath, "rb") as f:
        content_bytes = f.read()
    content_str = content_bytes.decode("utf-8")

    try:
        g = Github(token)
        repo = g.get_repo(f"{user}/{repo_name}")

        # Pick a branch: use default if available, else 'main'
        if branch is None:
            branch = (repo.default_branch or "main")

        # Check if repo is empty (no branches)
        try:
            branches = list(repo.get_branches())
            is_empty = (len(branches) == 0)
        except GithubException:
            # Some org repos return 404 for get_branches() before first commit
            is_empty = True

        if is_empty:
            # First try the simplest path: Contents API can create the initial commit/branch
            try:
                repo.create_file(dest_name, commit_msg, content_str, branch=branch)
                print(f"Bootstrapped {user}/{repo_name}@{branch} with {dest_name}.")
                return True
            except GithubException as e:
                # Fallback to Git Data API manual bootstrap (blob -> tree -> commit -> ref)
                try:
                    blob = repo.create_git_blob(content_str, "utf-8")
                    element = InputGitTreeElement(
                        path=dest_name, mode="100644", type="blob", sha=blob.sha
                    )
                    tree = repo.create_git_tree([element])
                    commit = repo.create_git_commit(commit_msg, tree, parents=[])
                    repo.create_git_ref(ref=f"refs/heads/{branch}", sha=commit.sha)
                    print(f"Bootstrapped empty repo and added {dest_name} to {user}/{repo_name}@{branch}.")
                    return True
                except Exception as inner:
                    print("GitHub upload failed during empty-repo bootstrap:", inner)
                    return False

        # Not empty: try update, else create on the selected branch
        try:
            contents = repo.get_contents(dest_name, ref=branch)
            repo.update_file(contents.path, commit_msg, content_str, contents.sha, branch=branch)
            print(f"Updated {dest_name} in {user}/{repo_name}@{branch}.")
            return True
        except UnknownObjectException:
            repo.create_file(dest_name, commit_msg, content_str, branch=branch)
            print(f"Created {dest_name} in {user}/{repo_name}@{branch}.")
            return True

    except GithubException as e:
        if e.status in (401, 403):
            print(
                "GitHub upload failed: auth/permission error.\n"
                "- If using a fine-grained PAT: grant 'Contents: Read and write' and include this repository.\n"
                "- If using a classic PAT: ensure the 'repo' scope is enabled.\n"
                "- For org repos: make sure SSO/approval is completed for the token."
            )
        else:
            print("GitHub upload failed:", e)
        return False
    except Exception as e:
        print("GitHub upload failed:", e)
        return False

# -------------------------
# I/O helpers
# -------------------------
def load_file(fn):
    # If the file isn't present, guide the user to generate it first.
    # WHY: Many users rely on the default path (data/shiftcodes.json) which is produced by
    # autoshift_scraper.py. When it's missing, this helper should explicitly tell them to
    # run autoshift_scraper.py first or pass a custom path via --file.
    if not path.exists(fn):
        hint = (
            f"File not found: {fn}\n"
            "Hint: run autoshift_scraper.py first to generate data/shiftcodes.json,\n"
            "or pass the correct file path with --file <PATH>."
        )
        raise SystemExit(hint)
    with open(fn, "r", encoding="utf-8") as f:
        return json.load(f)


def save_file(fn, data):
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# -------------------------
# Time helpers
# -------------------------
def parse_iso_to_utc(value):
    """Parse an ISO-8601-like string into an aware UTC datetime.

    - If the string includes an explicit offset (e.g. '...+00:00' or 'Z'), use it and convert to UTC.
    - If the string is *naive* (no offset), interpret it as America/Chicago (CST/CDT) and convert to UTC.
    - Returns None for missing/empty/'Unknown'/unparsable values.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() == "unknown":
            return None
        # Normalize trailing 'Z' to +00:00 for fromisoformat
        if s.endswith(("Z", "z")):
            s = s[:-1] + "+00:00"
        # Try direct parse
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            # Retry with space->'T' if needed
            try:
                s2 = s.replace(" ", "T", 1)
                dt = datetime.fromisoformat(s2)
            except Exception:
                return None
        # If naive, treat as America/Chicago local time (CST/CDT)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=GEARBOX_TZ)
        return dt.astimezone(timezone.utc)
    return None

# ---- Flexible expiry parsing (supports common non-ISO formats) ----

def _normalize_date_string(s: str) -> str:
    s = s.strip()
    # Remove ordinal suffixes: 1st, 2nd, 3rd, 4th -> 1,2,3,4
    s = _re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", lambda m: m.group(1), s, flags=_re.IGNORECASE)
    # Normalize 'Sept' to 'Sep' for %b parsing
    s = _re.sub(r"\bSept\b", "Sep", s, flags=_re.IGNORECASE)
    # Remove trailing 'UTC' token (we assume UTC anyway)
    s = _re.sub(r"\s*UTC\b", "", s, flags=_re.IGNORECASE)
    # Collapse multiple spaces
    s = _re.sub(r"\s+", " ", s)
    return s.strip()


def _parse_numeric_slash(s: str):
    """Parse numeric dates like 09/28/2025 or 28/09/2025.
    Heuristic: if first > 12 -> day/month/year else month/day/year.
    Interpret as midnight in America/Chicago, then convert to UTC.
    Returns aware UTC datetime, or None.
    """
    m = _re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if not m:
        return None
    a, b, y = m.groups()
    a = int(a); b = int(b)
    y = int(y)
    if y < 100:
        y += 2000  # simple 2-digit year handling
    try:
        if a > 12:  # day-first
            local_dt = datetime(y, b, a, tzinfo=GEARBOX_TZ)
        else:       # month-first
            local_dt = datetime(y, a, b, tzinfo=GEARBOX_TZ)
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None

def _try_strptime_formats(s: str):
    """Try common formats. Treat naive results as America/Chicago, then convert to UTC.
    Returns aware UTC datetime (year may be 1900 for month/day-only), or None.
    """
    fmts = [
        # With year
        "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
        "%d %b %Y", "%d %B %Y",
        "%Y-%m-%d",
        # With time (12h)
        "%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p",
        # Month-day only (year will be 1900)
        "%b %d", "%B %d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=GEARBOX_TZ)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return None

def _choose_year_for_monthday(dt_like: datetime, ref_dt: datetime, archived_dt):
    """Given a month/day-only datetime (year=1900), choose a plausible year based on archived/ref.
    Build midnight in America/Chicago, then convert to UTC.
    """
    m, d = dt_like.month, dt_like.day
    base = archived_dt or ref_dt
    year = base.year
    try:
        candidate_local = datetime(year, m, d, tzinfo=GEARBOX_TZ)
    except Exception:
        return None
    diff_days = (candidate_local - base).days
    if diff_days > 180:
        try:
            candidate_local = datetime(year - 1, m, d, tzinfo=GEARBOX_TZ)
        except Exception:
            pass
    elif diff_days < -180:
        try:
            candidate_local = datetime(year + 1, m, d, tzinfo=GEARBOX_TZ)
        except Exception:
            pass
    return candidate_local.astimezone(timezone.utc)

def parse_expiry_to_utc(value, ref_dt: datetime, archived_value):
    """Parse an 'expires' string into aware UTC datetime.

    Accepts ISO and common non-ISO formats. For ambiguous/naive formats, interpret in
    America/Chicago (CST/CDT as appropriate) and convert to UTC. For date-only ISO
    (YYYY-MM-DD), also treat as Central midnight.
    Returns None on missing/empty/"Unknown"/unparsable.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() == "unknown":
            return None

        # DATE-ONLY ISO (YYYY-MM-DD) -> treat as midnight America/Chicago, then to UTC
        if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            try:
                y, m, d = map(int, s.split("-"))
                local_dt = datetime(y, m, d, tzinfo=GEARBOX_TZ)
                return local_dt.astimezone(timezone.utc)
            except Exception:
                return None

        # Full ISO (with time and maybe offset) -> use strict ISO path
        iso = parse_iso_to_utc(s)
        if iso is not None:
            return iso

        s_norm = _normalize_date_string(s)

        # Numeric slash formats (mm/dd/yyyy or dd/mm/yyyy)
        dt = _parse_numeric_slash(s_norm)
        if dt is not None:
            return dt

        # Try common named-month formats
        dt2 = _try_strptime_formats(s_norm)
        if dt2 is not None:
            # Month/day only came back as UTC for a 1900 placeholder; pick a plausible year in Central
            if dt2.year == 1900:
                arch_dt = parse_iso_to_utc(archived_value) if archived_value else None
                return _choose_year_for_monthday(dt2, ref_dt, arch_dt)
            return dt2  # already UTC

    return None
    
def format_central_with_offset(dt_utc: datetime) -> str:
    """
    Format a UTC datetime as America/Chicago local time with the correct UTC offset label.
    Example: 'Sep 28, 2025, 02:11 AM UTC-05:00' (CDT) or 'UTC-06:00' (CST).
    """
    local = dt_utc.astimezone(GEARBOX_TZ)
    off = local.utcoffset() or timedelta(0)
    total_minutes = int(off.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else "+"
    hh = abs(total_minutes) // 60
    mm = abs(total_minutes) % 60
    return local.strftime("%b %d, %Y, %I:%M %p ") + f"UTC{sign}{hh:02d}:{mm:02d}"

# -------------------------
# Core operations (bulk)
# -------------------------
def sweep_expired_by_timestamp(filepath, ref_dt, dry_run=False):
    """Bulk mode: set expired=True for entries with valid expires < ref_dt.
    Does not modify 'expires' values.

    Returns (changed, stats_dict, details_list).

    details_list items:
      {
        "code": "ABCDE-...-.....",
        "expires_display": "<string to show>",
        "will_set": "YES" | "NO" | "NA",  # YES if dt < ref_dt; NO if dt >= ref_dt; NA for Unknown/empty/invalid
      }
    """
    data = load_file(filepath)
    if not data or not isinstance(data, list) or not isinstance(data[0], dict) or "codes" not in data[0]:
        raise SystemExit("Unexpected shiftcodes.json format")

    entries = data[0]["codes"]
    scanned = 0
    set_expired = 0
    skipped_unknown = 0
    unparsable = 0

    details = []

    for e in entries:
        scanned += 1
        code_str = (e.get("code") or "").strip()
        raw = e.get("expires")

        expires_disp = "Not Found"
        will_set = "NA"

        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            skipped_unknown += 1
            expires_disp = "Not Found"
            will_set = "NA"
        elif isinstance(raw, str) and raw.strip().lower() == "unknown":
            skipped_unknown += 1
            expires_disp = "Unknown"
            will_set = "NA"
        else:
            dt = parse_expiry_to_utc(raw, ref_dt, e.get("archived"))
            if dt is None:
                unparsable += 1
                expires_disp = "Not Found"
                will_set = "NA"
            else:
                dt_utc = dt.astimezone(timezone.utc)
                expires_disp = format_central_with_offset(dt_utc)
                will_set = "YES" if dt_utc < ref_dt else "NO"
                if dt_utc < ref_dt and e.get("expired") is not True:
                    set_expired += 1
                    # Don't mutate the JSON during dry-run; only count what would change.
                    if not dry_run:
                        e["expired"] = True

        details.append({
            "code": code_str,
            "expires_display": expires_disp,
            "will_set": will_set,
        })

    changed = set_expired > 0
    if changed and not dry_run:
        save_file(filepath, data)

    return changed, {
        "scanned": scanned,
        "set_expired": set_expired,
        "skipped_unknown": skipped_unknown,
        "unparsable": unparsable,
    }, details


# -------------------------
# Core operations (targeted)
# -------------------------

def targeted_update_codes(codes, filepath, ref_dt, provided_expires, dry_run=False):
    """Targeted mode: operate only over provided codes (one or more).

    - If provided_expires is True: overwrite 'expires' with ref_dt, do NOT touch 'expired'.
    - If provided_expires is False: set 'expires' to ref_dt AND set 'expired' = True.

    Returns (changed, stats_dict, details_list, unmatched_codes)
    where each details item includes both the CURRENT stored expires display and the NEW
    expires display (what we will write), so callers can choose which to show.
    """
    data = load_file(filepath)
    if not data or not isinstance(data, list) or not isinstance(data[0], dict) or "codes" not in data[0]:
        raise SystemExit("Unexpected shiftcodes.json format")

    target_set = { (c or "").strip().upper() for c in codes if (c or "").strip() }
    if not target_set:
        raise SystemExit("No code(s) provided")

    entries = data[0]["codes"]

    scanned = 0  # matched entries only
    set_expired = 0
    skipped_unknown = 0
    unparsable = 0
    updated_expires_only = 0
    set_expires = 0  # count how many entries have their 'expires' set/overwritten

    details = []
    unmatched = set(target_set)

    stamp_iso = ref_dt.isoformat()
    stamp_pretty = format_central_with_offset(ref_dt)

    for e in entries:
        code_val = (e.get("code") or "").strip().upper()
        if code_val not in target_set:
            continue

        # It's a match
        unmatched.discard(code_val)
        scanned += 1

        raw = e.get("expires")
        # Classify the existing expires for summary counts
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            skipped_unknown += 1
            expires_disp_current = "Not Found"
        elif isinstance(raw, str) and raw.strip().lower() == "unknown":
            skipped_unknown += 1
            expires_disp_current = "Unknown"
        else:
            dt = parse_expiry_to_utc(raw, ref_dt, e.get("archived"))
            if dt is None:
                unparsable += 1
                expires_disp_current = "Not Found"
            else:
                expires_disp_current = format_central_with_offset(dt)

        # Decide what we'd do
        if provided_expires:
            will_set = "NA"
            # overwrite expires only
            set_expires += 1  # count the planned overwrite even in dry-run
            if not dry_run:
                e["expires"] = stamp_iso
                updated_expires_only += 1
        else:
            will_set = "YES"
            # We'll set both expires and expired
            set_expires += 1
            if not dry_run:
                e["expires"] = stamp_iso
                if e.get("expired") is not True:
                    set_expired += 1
                e["expired"] = True
            else:
                # Even in dry-run, count what WOULD be set expired (for totals)
                if e.get("expired") is not True:
                    set_expired += 1

        details.append({
            "code": code_val,
            "expires_display": expires_disp_current,   # current stored value (pretty)
            "new_expires_display": stamp_pretty,       # what we will write
            "will_set": will_set,
        })

    changed = (set_expired > 0) or (updated_expires_only > 0)
    if changed and not dry_run:
        save_file(filepath, data)

    stats = {
        "scanned": scanned,
        "set_expired": set_expired,
        "set_expires": set_expires,
        "skipped_unknown": skipped_unknown,
        "unparsable": unparsable,
        "updated_expires_only": updated_expires_only,
    }
    return changed, stats, details, sorted(unmatched)


# -------------------------
# Printing helpers (shared by dry-run and real runs)
# -------------------------

def _build_separator(all_lines):
    longest = max((len(s) for s in all_lines), default=8)
    return "-" * max(longest, 8)


def print_targeted_report(details, stats, ref_dt, provided_expires, unmatched, is_dry_run):
    # Header: only include the literal "DRY-RUN:" label when --dry-run is used
    header = []
    if is_dry_run:
        header.append("DRY-RUN:")
    header.append(f"Date & Time (ISO): {ref_dt.isoformat()} | {format_central_with_offset(ref_dt)}")

    # Per-code lines
    per_code_lines = []
    for d in details:
        per_code_lines.append(f"Code: {d['code']}")
        # In print_targeted_report(...)
        # When *setting* expiry (no --expires), show the exact stamp being written:
        if provided_expires:
            # keep existing behavior when user supplies --expires:
            exp_to_show = d['new_expires_display']
        else:
            # targeted mode without --expires: show ISO | Central pair for ref_dt
            exp_to_show = f"{ref_dt.isoformat()} | {format_central_with_offset(ref_dt)}"
            
        per_code_lines.append(f"Expires: {exp_to_show}")
        per_code_lines.append(f"Will Set Expired: {d['will_set']}")

    # Summary (always printed in both dry-run and real runs)
    summary = [
        f"Scanned: {stats['scanned']}",
        f"Set expired: {stats['set_expired']}",
        f"Set expires field: {stats.get('set_expires', 0)}",
        f"Skipped (expires missing/empty or 'Unknown'): {stats['skipped_unknown']}",
        f"Unparsable (invalid 'expires' timestamp): {stats['unparsable']}",
    ]
    if stats.get("updated_expires_only", 0) > 0:
        summary.append(f"Updated expires only: {stats['updated_expires_only']}")

    # Notes (printed ONLY in dry-run)
    notes = [
        "Notes:",
        "- 'Skipped' looks only at the 'expires' field (missing, empty, or 'Unknown').",
        "- 'Unparsable' means the 'expires' field could not be parsed as an ISO or common date format.",
    ]

    # Unmatched codes (always shown if any)
    unmatched_lines = [f"No matches found for {code}" for code in unmatched]

    # Build separator based on what will actually be printed
    sep_basis = header + per_code_lines + summary + unmatched_lines
    if is_dry_run:
        sep_basis += notes
    sep = _build_separator(sep_basis)

    # Print header
    print("\n".join(header))

    # Print per-code blocks (if any), with separators between blocks
    blocks = [per_code_lines[i:i+3] for i in range(0, len(per_code_lines), 3)]
    print(sep)
    if blocks:
        for idx, block in enumerate(blocks):
            for line in block:
                print(line)
            if idx < len(blocks) - 1:
                print(sep)
        print(sep)

    # Summary (always)
    print("\n".join(summary))

    # Notes (dry-run only)
    if is_dry_run:
        print(sep)
        print("\n".join(notes))

    # Unmatched codes (if any)
    if unmatched_lines:
        print(sep)
        for line in unmatched_lines:
            print(line)


def print_bulk_report(details, stats, ref_dt, is_dry_run):
    # Header: only include the literal "DRY-RUN:" label when --dry-run is used
    header = []
    if is_dry_run:
        header.append("DRY-RUN:")
    header.append(f"Date & Time (ISO): {ref_dt.isoformat()} | {format_central_with_offset(ref_dt)}")

    # Per-code lines
    per_code_lines = []
    for d in details:
        per_code_lines.append(f"Code: {d['code']}")
        per_code_lines.append(f"Expires: {d['expires_display']}")
        per_code_lines.append(f"Will Set Expired: {d['will_set']}")

    # Summary (always printed in both dry-run and real runs)
    summary = [
        f"Scanned: {stats['scanned']}",
        f"Set expired: {stats['set_expired']}",
        f"Set expires field: {stats.get('set_expires', 0)}",
        f"Skipped (expires missing/empty or 'Unknown'): {stats['skipped_unknown']}",
        f"Unparsable (invalid 'expires' timestamp): {stats['unparsable']}",
    ]

    # Notes (printed ONLY in dry-run)
    notes = [
        "Notes:",
        "- 'Skipped' looks only at the 'expires' field (missing, empty, or 'Unknown').",
        "- 'Unparsable' means the 'expires' field could not be parsed as an ISO or common date format.",
    ]

    # Build separator based on what will actually be printed
    sep_basis = header + per_code_lines + summary
    if is_dry_run:
        sep_basis += notes
    sep = _build_separator(sep_basis)

    # Print header
    print("\n".join(header))

    # Print per-code blocks (if any), with separators between blocks
    blocks = [per_code_lines[i:i+3] for i in range(0, len(per_code_lines), 3)]
    print(sep)
    if blocks:
        for idx, block in enumerate(blocks):
            for line in block:
                print(line)
            if idx < len(blocks) - 1:
                print(sep)
        print(sep)

    # Summary (always)
    print("\n".join(summary))

    # Notes (dry-run only)
    if is_dry_run:
        print(sep)
        print("\n".join(notes))


def parse_target_codes(argv_codes):
    """Parse positional codes enforcing comma-separated input for multiples.
    - Accepts no codes (returns []).
    - Accepts a single code as-is.
    - If user passes multiple tokens without commas (e.g. CODE1 CODE2), error with guidance.
    - If user passes comma-separated (e.g. "CODE1, CODE2, CODE3"), split/strip and validate no spaces inside codes.
    """
    if not argv_codes:
        return []
    raw = " ".join(argv_codes)
    if len(argv_codes) > 1 and "," not in raw:
        raise SystemExit(
            "When passing multiple codes, separate them with commas, e.g. CODE1, CODE2, CODE3"
        )
    parts = [p.strip() for p in raw.split(",")]
    cleaned = []
    for p in parts:
        if not p:
            continue
        if " " in p:
            raise SystemExit(
                "Invalid code token with spaces. Separate multiple codes with commas, e.g. CODE1, CODE2"
            )
        cleaned.append(p)
    return cleaned


def main():
    p = argparse.ArgumentParser(
        description=(
            "Mark SHiFT codes expired in data/shiftcodes.json.\n"
            "- With CODE(s): targeted update. If --expires ISO is provided: overwrite only the 'expires' field.\n"
            "  If --expires is omitted: set 'expires' to the current time in America/Chicago (converted to UTC) and 'expired'=true for the matched codes.\n"
            "- With no CODE: bulk sweep sets 'expired'=true for entries whose existing 'expires' < reference time."
        )
    )

    p.add_argument(
        "codes",
        nargs="*",
        help="One or more SHiFT codes (comma-separated): CODE1, CODE2, ...",
    )

    p.add_argument(
        "--expires",
        default=None,
        help=(
            "ISO-8601 timestamp.\n"
            "Bulk mode: reference time to compare against.\n"
            "Targeted mode: overwrite the 'expires' field with this (no change to 'expired').\n"
            "Naive timestamps (no offset) are interpreted as America/Chicago (CST/CDT) and converted to UTC.\n"
            "If omitted: bulk uses the current America/Chicago time; targeted sets both 'expires' (to now) and 'expired'.\n"
            "Examples: 2025-10-01T00:00:00Z, 2025-10-01 00:00:00, 2025-10-01"
        ),

    )

    p.add_argument(
        "--file",
        default=SHIFTCODESJSONPATH,
        help="Path to shiftcodes.json (default: data/shiftcodes.json)",
    )

    p.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Report intended changes without writing or uploading",
    )

    # optional GitHub push parameters
    p.add_argument("--user", default=None, help="GitHub username or org that owns the repo (optional)")
    p.add_argument("--repo", default=None, help="GitHub repository name (optional)")
    p.add_argument("--token", default=None, help="GitHub token with contents:write permission (optional)")

    args = p.parse_args()

    # Enforce comma-separated format for multiple codes
    parsed_codes = parse_target_codes(args.codes)

    # Determine reference/stamp time once
    provided_expires = args.expires is not None
    if provided_expires:
        ref_dt = parse_iso_to_utc(args.expires)
        if ref_dt is None:
            raise SystemExit(f"Error: invalid ISO timestamp for --expires: {args.expires}")
    else:
        # WHY: When --expires is omitted, interpret "now" in Gearbox local time, then convert to UTC.
        ref_dt = datetime.now(GEARBOX_TZ).astimezone(timezone.utc)


    changed_for_upload = False
    commit_msg = None

    if parsed_codes:
        # Targeted mode (one or more codes)
        changed, stats, details, unmatched = targeted_update_codes(
            parsed_codes, args.file, ref_dt, provided_expires, dry_run=args.dry_run
        )

        # Unified reporting for both dry-run and real runs
        print_targeted_report(details, stats, ref_dt, provided_expires, unmatched, args.dry_run)

        changed_for_upload = changed and not args.dry_run
        codes_str = ", ".join(parsed_codes)
        if provided_expires:
            commit_msg = f"Targeted overwrite 'expires' via mark_expired.py for: {codes_str}"
        else:
            commit_msg = f"Targeted mark expired via mark_expired.py for: {codes_str}"

    else:
        # Bulk sweep mode
        changed, stats, details = sweep_expired_by_timestamp(args.file, ref_dt, dry_run=args.dry_run)

        # Unified reporting for both dry-run and real runs
        print_bulk_report(details, stats, ref_dt, args.dry_run)

        changed_for_upload = changed and not args.dry_run
        commit_msg = f"Sweep expired by timestamp via mark_expired.py ({ref_dt.isoformat()})"

    # If GitHub credentials provided, upload the updated file (only when changes occurred and not a dry-run)
    if changed_for_upload and args.user and args.repo and args.token:
        ok = upload_shiftfile(args.file, args.user, args.repo, args.token, commit_msg=commit_msg)
        if ok:
            print(f"Uploaded updated {path.basename(args.file)} to GitHub.")
        else:
            print("Upload attempt failed.")

if __name__ == "__main__":
    main()
