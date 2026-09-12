"""
Initialize an empty release_catalog.db from scratch.

Usage:
    uv run init_db.py [--db-path PATH] [--force]

The script is idempotent by default: tables that already exist are left
untouched (CREATE TABLE IF NOT EXISTS semantics via SQLAlchemy checkfirst).
Pass --force to drop and recreate the entire database file.
"""

import argparse
import os

from global_config import DB_PATH, COLUMN_DICT, ReleaseType

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
)

# ---------------------------------------------------------------------------
# Schema definition (SQLAlchemy Core – no ORM required)
# ---------------------------------------------------------------------------

metadata = MetaData()

# -- releases ----------------------------------------------------------------
releases = Table(
    "releases",
    metadata,
    Column("release_id", Text, primary_key=True),
    Column("album_artists", Text),
    Column("album_title", Text),
    Column("label", Text),
    Column("total_length", Integer),
    Column("num_tracks", Integer),
    Column("tags", Text),
    Column("release_date", Text),
    Column("type", Text),
    Column("mc_catalog_id", Text),
    Column("cd_catalog_id", Text),
    Column("lp_catalog_id", Text),
    Column("digital_catalog_id", Text),
    Column("archive_catalog_id", Text),
    Column("legacy_catalog_id", Text),
    Column("bandcamp_url", Text),
    # 1 when the release still has incomplete data (e.g. a pre-order whose track
    # durations/ISRCs aren't public yet); a later sync run back-fills and clears it.
    Column("needs_refresh", Integer, default=0),
    Index("idx_releases_mc_catalog_id", COLUMN_DICT[ReleaseType.CASSETTE], unique=True),
    Index("idx_releases_cd_catalog_id", COLUMN_DICT[ReleaseType.CD], unique=True),
    Index("idx_releases_lp_catalog_id", COLUMN_DICT[ReleaseType.LP], unique=True),
    Index(
        "idx_releases_digital_catalog_id", COLUMN_DICT[ReleaseType.DIGITAL], unique=True
    ),
    Index(
        "idx_releases_archive_catalog_id", COLUMN_DICT[ReleaseType.ARCHIVE], unique=True
    ),
)

# -- tracks ------------------------------------------------------------------
tracks = Table(
    "tracks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("release_id", Text, ForeignKey("releases.release_id")),
    Column("track_number", Integer),
    Column("artists", Text),
    Column("track_title", Text),
    Column("runtime", Integer),
    Column("isrc", Text),
)

# -- artist ------------------------------------------------------------------
artist = Table(
    "artist",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False, unique=True),
)

# -- artist_track_link -------------------------------------------------------
artist_track_link = Table(
    "artist_track_link",
    metadata,
    Column(
        "artist_id", Integer, ForeignKey("artist.id"), primary_key=True, nullable=False
    ),
    Column(
        "track_id", Integer, ForeignKey("tracks.id"), primary_key=True, nullable=False
    ),
)

# -- external-service link tables (discogs / musicbrainz / cddb) -------------
_SERVICES = ("discogs", "musicbrainz", "cddb")
_FORMATS: list[tuple[str, str]] = [
    ("mc", COLUMN_DICT[ReleaseType.CASSETTE]),
    ("cd", COLUMN_DICT[ReleaseType.CD]),
    ("lp", COLUMN_DICT[ReleaseType.LP]),
    ("digital", COLUMN_DICT[ReleaseType.DIGITAL]),
    ("archive", COLUMN_DICT[ReleaseType.ARCHIVE]),
]

for _service in _SERVICES:
    for _format, _fk_col in _FORMATS:
        Table(
            f"{_service}_{_format}_links",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column(_fk_col, String, ForeignKey(f"releases.{_fk_col}")),
            Column("url_record", String),
        )


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------


def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite disables FK enforcement by default; enable it per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def build_engine(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db(db_path: str, force: bool = False) -> None:
    """Create all tables defined in `metadata`.

    Args:
        db_path: Filesystem path to the SQLite database file.
        force:   When True, delete the existing file before creating tables.
    """
    if force and os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    engine = build_engine(db_path)
    # checkfirst=True -> idempotent; skips tables that already exist
    metadata.create_all(engine, checkfirst=True)
    engine.dispose()
    print(f"Database initialised: {db_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    default_db = DB_PATH

    parser = argparse.ArgumentParser(
        description="Initialise the release_catalog SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db-path",
        default=default_db,
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete the existing database file and recreate it from scratch.",
    )
    args = parser.parse_args()

    init_db(args.db_path, force=args.force)


if __name__ == "__main__":
    main()
