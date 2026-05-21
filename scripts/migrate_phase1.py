"""
Phase 1 migration script for keinplankarriere tracker.db

Steps:
1. Back up tracker.db
2. Normalize match_score (0-1 -> 0-100)
3. Deduplicate by job_id (keep highest match_score, tie-break latest updated_at)
4. Create UNIQUE INDEX on job_id
"""

import shutil
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/tracker.db")
BACKUP_PATH = Path("data/tracker.db.bak-phase1")


def main():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found")
        sys.exit(1)

    # Step 1: Backup
    print("=" * 60)
    print("STEP 1: Backing up database")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"  Backed up to {BACKUP_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Stats before
    total_before = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    unique_jobs = conn.execute("SELECT COUNT(DISTINCT job_id) FROM applications").fetchone()[0]
    print(f"\n  Total rows before migration: {total_before}")
    print(f"  Unique job_ids: {unique_jobs}")
    print(f"  Duplicate rows: {total_before - unique_jobs}")

    # Step 2: Normalize match_score
    print("\n" + "=" * 60)
    print("STEP 2: Normalizing match_score (0-1 -> 0-100)")

    to_normalize = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE match_score IS NOT NULL AND match_score <= 1.0"
    ).fetchone()[0]
    print(f"  Rows with match_score <= 1.0: {to_normalize}")

    conn.execute(
        "UPDATE applications SET match_score = match_score * 100 WHERE match_score IS NOT NULL AND match_score <= 1.0"
    )
    conn.commit()
    print(f"  Normalized {to_normalize} rows")

    # Step 3: Deduplicate
    print("\n" + "=" * 60)
    print("STEP 3: Deduplicating by job_id")

    dupes = conn.execute("""
        SELECT job_id, COUNT(*) as cnt
        FROM applications
        GROUP BY job_id
        HAVING cnt > 1
    """).fetchall()

    dupe_count = len(dupes)
    total_extra = sum(row["cnt"] - 1 for row in dupes)
    print(f"  job_ids with duplicates: {dupe_count}")
    print(f"  Extra rows to delete: {total_extra}")

    if total_extra > 0:
        conn.execute("""
            DELETE FROM applications
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY job_id
                               ORDER BY match_score DESC, updated_at DESC
                           ) as rn
                    FROM applications
                ) WHERE rn = 1
            )
        """)
        conn.commit()

    total_after = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    print(f"  Rows after dedup: {total_after}")
    print(f"  Deleted: {total_before - total_after}")

    # Step 4: Create unique index
    print("\n" + "=" * 60)
    print("STEP 4: Creating UNIQUE INDEX on job_id")

    try:
        conn.execute("DROP INDEX IF EXISTS idx_applications_job_id")
        conn.execute("CREATE UNIQUE INDEX idx_applications_job_id ON applications(job_id)")
        conn.commit()
        print("  Created idx_applications_job_id")
    except sqlite3.IntegrityError as e:
        print(f"  ERROR: {e}")
        print("  There are still duplicate job_ids — dedup may have failed")
        sys.exit(1)

    # Final summary
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print(f"  Rows: {total_before} -> {total_after}")
    print(f"  Normalized: {to_normalize} match_scores")
    print(f"  Deleted duplicates: {total_before - total_after}")

    # Score distribution
    score_stats = conn.execute("""
        SELECT
            MIN(match_score) as min_score,
            MAX(match_score) as max_score,
            AVG(match_score) as avg_score,
            COUNT(match_score) as scored_count,
            SUM(CASE WHEN match_score IS NULL THEN 1 ELSE 0 END) as unscored
        FROM applications
    """).fetchone()
    print(f"\n  Score stats:")
    print(f"    Min: {score_stats['min_score']}")
    print(f"    Max: {score_stats['max_score']}")
    print(f"    Avg: {score_stats['avg_score']:.1f}" if score_stats['avg_score'] else "    Avg: N/A")
    print(f"    Scored: {score_stats['scored_count']}")
    print(f"    Unscored: {score_stats['unscored']}")

    # Status distribution
    statuses = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM applications GROUP BY status"
    ).fetchall()
    print(f"\n  Status distribution:")
    for s in statuses:
        print(f"    {s['status']}: {s['cnt']}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
