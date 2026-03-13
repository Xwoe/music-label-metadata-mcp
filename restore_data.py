"""
Restore data from data/data_dump.sql into a freshly initialised release_catalog.db.

Typical workflow:
    uv run dump_data.py          # save current data
    uv run init_db.py --force    # recreate schema from scratch
    uv run restore_data.py       # reload saved data

Usage:
    uv run restore_data.py [--db-path PATH] [--dump-path PATH]
"""

import argparse
import sqlite3
import os
from global_config import DB_PATH, BASEPATH

DUMP_PATH = os.path.join(BASEPATH, "data_dump.sql")


def restore_data(db_path: str = DB_PATH, dump_path: str = DUMP_PATH) -> None:
    if not os.path.exists(dump_path):
        raise FileNotFoundError(f"Dump file not found: {dump_path}")

    with open(dump_path, "r", encoding="utf-8") as f:
        sql = f.read()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()

    print(f"Restored data from {dump_path} into {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore data from a SQL dump into the release catalog database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db-path",
        default=DB_PATH,
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s)",
    )
    parser.add_argument(
        "--dump-path",
        default=DUMP_PATH,
        metavar="PATH",
        help="Path to the SQL dump file (default: %(default)s)",
    )
    args = parser.parse_args()
    restore_data(os.path.abspath(args.db_path), os.path.abspath(args.dump_path))


if __name__ == "__main__":
    main()
