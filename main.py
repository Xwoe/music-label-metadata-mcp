import asyncio
import csv
import os
import sqlite3

# from typing import Any
# import httpx

from contextlib import contextmanager
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from global_config import BASEPATH, DB_PATH, VALID_SERVICES, ReleaseType, COLUMN_DICT
from init_db import init_db
from models.album import Album, LIST_SEPARATOR
from fill_form import MusicBrainzFiller
from log import get_logger
from scrape_bandcamp import BandcampScraper
from mldg_utils import generate_release_id

logger = get_logger(__name__)


# Initialize FastMCP server
mcp = FastMCP("MusicLabelDataFiller")

# Maps ReleaseType to (link_table_suffix, catalog_id_column)
_LINK_TABLE_SUFFIXES = {
    ReleaseType.DIGITAL: ("digital_links", "digital_catalog_id"),
    ReleaseType.CASSETTE: ("mc_links", "mc_catalog_id"),
    ReleaseType.LP: ("lp_links", "lp_catalog_id"),
    ReleaseType.CD: ("cd_links", "cd_catalog_id"),
    ReleaseType.ARCHIVE: ("archive_links", "archive_catalog_id"),
}


def _link_table(service: str, release_type: ReleaseType) -> tuple[str, str]:
    """Returns (table_name, catalog_id_column) for a given service and release type."""
    suffix, column = _LINK_TABLE_SUFFIXES[release_type]
    return f"{service}_{suffix}", column


# Keep for backward compatibility with _save_musicbrainz_link_to_db
MUSICBRAINZ_LINK_TABLES = {rt: _link_table("musicbrainz", rt) for rt in ReleaseType}

# Keeps the Selenium driver alive between MCP tool calls
_active_filler: MusicBrainzFiller | None = None


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Ensures connection is closed after use.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row  # Optional: allows accessing columns by name
        yield conn
    finally:
        conn.close()


def _save_musicbrainz_link_to_db(catalog_id: str, url: str, medium: ReleaseType):
    """Inserts a MusicBrainz release URL into the appropriate link table."""
    table, column = MUSICBRAINZ_LINK_TABLES[medium]
    with get_db_connection() as conn:
        conn.execute(
            f"INSERT INTO {table} ({column}, url_record) VALUES (?, ?)",
            (catalog_id, url),
        )
        conn.commit()


@mcp.tool()
async def fetch_release_by_name(artist_name: str, release_title: str) -> dict:
    """
    Fetches a release from the SQLite database based on artist name and release title.
    Returns a JSON object with the release details or an error message if not found.
    """
    release_id = await get_release_id_by_name(
        artist_name, release_title
    )  # Fetch the release_id first
    return await collect_release_data(release_id)  # Fetch detailed release data


@mcp.tool()
async def get_release_id_by_name(artist_name: str, release_title: str) -> dict:
    """
    Fetches the release_id for a given artist name and release title.
    Returns a JSON object with the release_id or an error message if not found.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT release_id FROM releases WHERE LOWER(album_artists) = LOWER(?) AND LOWER(album_title) = LOWER(?)",
            (artist_name, release_title),
        )
        row = cursor.fetchone()

    if not row:
        return {"error": "Release not found"}

    return row["release_id"]


@mcp.tool()
async def get_release_id_by_album_name(album_name: str) -> dict:
    """
    Fetches the release_id for a given album name.
    Returns a JSON object with the release_id or an error message if not found.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT release_id FROM releases WHERE LOWER(album_title) = LOWER(?)",
            (album_name,),
        )
        row = cursor.fetchone()

    if not row:
        return {"error": "Release not found"}

    return row["release_id"]


@mcp.tool()
async def collect_release_data(release_id: str) -> dict:
    """
    Fetches a specific release from our DB and formats it for MusicBrainz submission.
    Returns a JSON object the browser tool can use to fill forms.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Query your specific release
        cursor.execute(
            """SELECT album_artists, album_title, label, mc_catalog_id, cd_catalog_id, archive_catalog_id,
                lp_catalog_id, digital_catalog_id, archive_catalog_id, release_date, type, bandcamp_url FROM releases WHERE release_id = ?""",
            (release_id,),
        )
        row = cursor.fetchone()

        cursor.execute(
            "SELECT track_number, artists, track_title, runtime, isrc FROM tracks WHERE release_id = ? ORDER BY track_number",
            (release_id,),
        )
        tracks = cursor.fetchall()

    if not row:
        return {"error": "Release not found"}

    # Format the data into a clean structure for the LLM
    return {
        "artist_name": row["album_artists"],
        "release_title": row["album_title"],
        "label": row["label"],
        "mc_catalog_id": row["mc_catalog_id"],
        "cd_catalog_id": row["cd_catalog_id"],
        "lp_catalog_id": row["lp_catalog_id"],
        "digital_catalog_id": row["digital_catalog_id"],
        "release_date": row["release_date"],
        "archive_catalog_id": row["archive_catalog_id"],
        "digital_catalog_id": row["digital_catalog_id"],
        "release_date": row["release_date"],
        "type": row["type"],
        "bandcamp_url": row["bandcamp_url"],
        "tracks": [
            {
                "track_number": track["track_number"],
                "artists": track["artists"],
                "track_title": track["track_title"],
                "runtime": track["runtime"],
                "isrc": track["isrc"],
            }
            for track in tracks
        ],
    }


@mcp.tool()
async def list_all_releases() -> list:
    """
    Fetches all releases from the database and returns them as a list of JSON objects.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT album_artists, album_title, label, mc_catalog_id, cd_catalog_id, lp_catalog_id, digital_catalog_id, archive_catalog_id, release_date, bandcamp_url FROM releases"
        )
        rows = cursor.fetchall()

    return [
        {
            "artist_name": row["album_artists"],
            "release_title": row["album_title"],
            "label": row["label"],
            "mc_catalog_id": row["mc_catalog_id"],
            "cd_catalog_id": row["cd_catalog_id"],
            "lp_catalog_id": row["lp_catalog_id"],
            "digital_catalog_id": row["digital_catalog_id"],
            "archive_catalog_id": row["archive_catalog_id"],
            "release_date": row["release_date"],
            "bandcamp_url": row["bandcamp_url"],
        }
        for row in rows
    ]


@mcp.tool()
async def get_next_unsubmitted_release(
    release_type: ReleaseType, service: str = "musicbrainz"
) -> dict:
    """
    Finds the latest release (by catalog ID) that has not yet been submitted to the
    given service for the given release type.

    Use this to answer requests like "add the next digital release to musicbrainz":
    call this tool first to get the release, then pass the result to fill_musicbrainz_form.

    `release_type` — one of: DIGITAL, CASSETTE, LP, CD, ARCHIVE
    `service`      — one of: "musicbrainz", "discogs", "cddb"

    Returns full release data (same structure as collect_release_data) or an error dict.
    """
    if service not in VALID_SERVICES:
        return {"error": f"Unknown service '{service}'. Valid: {VALID_SERVICES}"}

    catalog_col = COLUMN_DICT.get(release_type)
    if not catalog_col:
        return {"error": f"Unknown release type: {release_type}"}

    link_table, _ = _link_table(service, release_type)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT r.release_id
            FROM releases r
            LEFT JOIN {link_table} l ON r.{catalog_col} = l.{catalog_col}
            WHERE r.{catalog_col} IS NOT NULL
              AND l.{catalog_col} IS NULL
            ORDER BY r.{catalog_col} DESC
            LIMIT 1
            """,
        )
        row = cursor.fetchone()

    if not row:
        return {
            "error": f"No unsubmitted {release_type.name} releases found for {service}"
        }

    return await collect_release_data(row["release_id"])


@mcp.tool()
async def get_new_catalog_id(release_type: ReleaseType) -> str:
    """
    Generates a new unique catalog ID based on existing entries in the database.
    The parameter `release_type_name` should be one of the following values for the enum:
    - ReleaseType.DIGITAL for streaming/digital releases
    - ReleaseType.CASSETTE for cassette releases
    - ReleaseType.LP for vinyl releases
    - ReleaseType.CD for CD releases
    - ReleaseType.ARCHIVE for archive releases, which were released before the label was officially founded
        but are now being added to the catalog.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        column_name = COLUMN_DICT.get(release_type)
        if not column_name:
            return "Invalid release type"
        cursor.execute(
            f"SELECT MAX({column_name}) FROM releases WHERE {column_name} LIKE ?",
            (f"{release_type.value}%",),
        )
        max_id = cursor.fetchone()[0]

    # Placeholder logic for generating a new catalog ID
    if max_id is None:
        return f"{release_type.value}0001"
    else:
        new_id_num = int(max_id.split("-")[-1]) + 1
        return f"{release_type.value}{new_id_num:03d}"


@mcp.tool()
async def fill_musicbrainz_form(
    release_id: str, medium: ReleaseType = ReleaseType.DIGITAL
) -> str:
    """
    Opens a browser window and attempts to prefill the MusicBrainz 'Add Release' form
    using data for the given release_id. In the parameter `medium`, you can specify the release type
    (digital, cassette, LP, CD, archive) you want to add to the musicbrainz database.
    This will determine which catalog ID is generated and filled in the form.
    If the user didn't specify, which release type they want to add and there are multiple
    catalog IDs available for the release, ask the user, which one to use.
    Since there is sometimes an issue with filling in the tracklist, print the tracklist to the user
    into the chat, so they can easily copy-paste it into the form if needed.
    After filling the form, this tool waits up to 5 minutes for the user to submit.
    On success the MusicBrainz URL is saved to the database automatically.
    If the wait times out, ask the user to paste the URL and call save_musicbrainz_link manually.
    """
    global _active_filler

    # 1. Get the data
    data = await collect_release_data(release_id)
    if "error" in data:
        return f"Error: {data['error']}"

    catalog_id = data.get(COLUMN_DICT.get(medium, "digital_catalog_id"))

    # 2. Launch (or reuse) the browser filler
    try:
        if _active_filler is None:
            _active_filler = MusicBrainzFiller()
        filler = _active_filler
        track_list = filler.fill_release(data, medium)
    except Exception as e:
        _active_filler = None
        return f"Failed to fill form: {str(e)}"

    # 3. Wait for the user to submit the form (up to 5 minutes)
    release_url = await asyncio.to_thread(filler.wait_for_submission, 300)

    if release_url:
        if catalog_id:
            try:
                _save_musicbrainz_link_to_db(catalog_id, release_url, medium)
                return (
                    f"Release submitted successfully!\n"
                    f"MusicBrainz URL: {release_url}\n"
                    f"Saved to database under catalog ID: {catalog_id}\n\n"
                    f"Tracklist (for reference):\n{track_list}"
                )
            except Exception as e:
                return (
                    f"Release submitted but DB save failed: {e}\n"
                    f"MusicBrainz URL: {release_url}\n"
                    f"Please call save_musicbrainz_link('{catalog_id}', '{release_url}', medium) manually.\n\n"
                    f"Tracklist:\n{track_list}"
                )
        else:
            return (
                f"Release submitted! MusicBrainz URL: {release_url}\n"
                f"No catalog ID found for medium {medium.name} — nothing saved to DB.\n\n"
                f"Tracklist:\n{track_list}"
            )
    else:
        return (
            f"Form filled — waiting for submission timed out.\n"
            f"Please submit the form in the browser, then paste the MusicBrainz URL here\n"
            f"and call save_musicbrainz_link(catalog_id='{catalog_id}', url=<pasted URL>, medium='{medium.name}').\n\n"
            f"Tracklist:\n{track_list}"
        )


@mcp.tool()
async def save_musicbrainz_link(
    catalog_id: str, url: str, medium: ReleaseType = ReleaseType.DIGITAL
) -> str:
    """
    Saves a MusicBrainz release URL to the database for the given catalog ID.
    Use this as a fallback when fill_musicbrainz_form timed out waiting for submission,
    or to manually record a URL that was already submitted in the browser.
    The `medium` must match the release type of the catalog_id provided.
    """
    try:
        _save_musicbrainz_link_to_db(catalog_id, url, medium)
        return f"Saved: {catalog_id} → {url} in {MUSICBRAINZ_LINK_TABLES[medium][0]}"
    except Exception as e:
        return f"Failed to save link: {e}"


@mcp.tool()
async def add_release_to_musicbrainz_by_name(
    artist_name: str, release_title: str, medium: ReleaseType = ReleaseType.DIGITAL
) -> str:
    """
    Combines the functionality of fetching a release by name and filling the MusicBrainz form.
    This is a convenience tool that allows users to directly add a release to MusicBrainz by
    providing the artist name and release title.
    """
    # 1. Fetch the release ID
    release_id_result = await get_release_id_by_name(artist_name, release_title)
    if "error" in release_id_result:
        return f"Error: {release_id_result['error']}"

    release_id = release_id_result

    # 2. Fill the MusicBrainz form using the fetched release ID
    return await fill_musicbrainz_form(release_id, medium)


def album_exists_in_db(bandcamp_url: str) -> bool:
    """Returns True if a release with the given Bandcamp URL already exists in the DB."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM releases WHERE bandcamp_url = ?", (bandcamp_url,))
        return cursor.fetchone() is not None


def insert_album_to_db(album: Album) -> str:
    """Inserts an Album (and its tracks) into the releases and tracks tables."""
    release_id = generate_release_id(album.album_artists, album.title)
    artists_str = LIST_SEPARATOR.join(album.album_artists)
    tags_str = LIST_SEPARATOR.join(album.tags)
    release_date_str = album.release_date.strftime("%Y-%m-%d")

    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO releases
               (release_id, album_artists, album_title, label, total_length, num_tracks,
                tags, release_date, bandcamp_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                release_id,
                artists_str,
                album.title,
                album.label,
                album.total_length,
                album.num_tracks,
                tags_str,
                release_date_str,
                album.bandcamp_url,
            ),
        )
        conn.executemany(
            """INSERT INTO tracks (release_id, track_number, artists, track_title, runtime, isrc)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    release_id,
                    track.track_number,
                    LIST_SEPARATOR.join(track.artists),
                    track.track_title,
                    track.runtime,
                    track.isrc,
                )
                for track in album.tracks
            ],
        )
        conn.commit()
    logger.info(f"Inserted album '{album.title}' with release_id={release_id}")
    return release_id


@mcp.tool()
async def update_bandcamp_data():
    """
    Scrapes the Bandcamp page for the label and updates the local database with any new releases.
    This tool can be run periodically to keep the database in sync with the Bandcamp page.
    If any albums fail to parse, their URLs are logged for manual review.
    All successfully parsed albums are inserted into the database, and a summary of the operation
    is printed at the end.
    Use this command if the user requests to get the latest releases from Bandcamp or to
    sync new releases that were added to Bandcamp after the initial data collection.
    After running this command also run `export_releases_to_csv` to update the CSV export with the new releases.
    """

    scraper = BandcampScraper(
        wait_selector="li.music-grid-item",
        bandcamp_url=os.environ["MUSICLABEL_BANDCAMP_URL"],
    )
    failed_album_links = []
    new_albums: list[Album] = []
    for album_url in scraper.iterate_albums():
        if album_exists_in_db(album_url):
            logger.info(f"Album already exists: {album_url}")
            break
        try:
            new_albums.append(scraper.parse_album(album_url))
        except Exception as e:
            logger.error(f"Error parsing album at {album_url}: {e}")
            failed_album_links.append(album_url)

    # Catalog IDs are assigned sequentially, so insert oldest first.
    new_albums.sort(key=lambda a: a.release_date)
    for album in new_albums:
        release_id = insert_album_to_db(album)
        # we always have digital releases, so we can generate a catalog ID right away
        await add_catalog_id_to_release(release_id, ReleaseType.DIGITAL)

    if failed_album_links:
        logger.warning(
            f"Failed to parse the following album links: {failed_album_links}"
        )


@mcp.tool()
async def add_catalog_id_to_release(release_id: str, release_type: ReleaseType) -> str:
    """
    Adds a catalog ID to an existing release in the database for the specified release type.
    This is useful for updating releases with new catalog IDs after they have been added to the database.
    """
    column_name = COLUMN_DICT.get(release_type)
    catalog_id = await get_new_catalog_id(release_type)
    if not column_name:
        return f"Error: Unknown release type '{release_type}'"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE releases SET {column_name} = ? WHERE release_id = ?",
            (catalog_id, release_id),
        )
        if cursor.rowcount == 0:
            return f"Error: No release found with ID '{release_id}'"
        conn.commit()

    return f"Successfully updated release '{release_id}' with {release_type.name} catalog ID '{catalog_id}'"


def _format_release_date(date_str: str | None) -> str:
    """Reformat a YYYY-MM-DD release date to DD/MM/YYYY. Returns empty string for missing dates."""
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return date_str


@mcp.tool()
async def export_releases_to_csv(output_path: str | None = None) -> str:
    """
    Exports the current release catalog to a CSV file.

    Columns (in order): Release, Artist, Release Date (DD/MM/YYYY), Type,
    Catalog ID, Tape Catalog ID, CD Catalog ID, LP Catalog ID, Archive Catalog ID,
    Bandcamp URL, Musicbrainz Link.

    The Musicbrainz Link is taken from musicbrainz_digital_links for the release's
    digital_catalog_id (blank if no digital MusicBrainz link exists).

    Args:
        output_path: Optional absolute path for the CSV. Defaults to
            data/releases.csv in the project data folder.
    """
    if output_path is None:
        output_path = os.path.join(BASEPATH, "releases.csv")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                r.album_title,
                r.album_artists,
                r.release_date,
                r.type,
                r.digital_catalog_id,
                r.mc_catalog_id,
                r.cd_catalog_id,
                r.lp_catalog_id,
                r.archive_catalog_id,
                r.bandcamp_url,
                mb.url_record AS musicbrainz_url
            FROM releases r
            LEFT JOIN (
                SELECT digital_catalog_id, MIN(url_record) AS url_record
                FROM musicbrainz_digital_links
                WHERE digital_catalog_id IS NOT NULL
                GROUP BY digital_catalog_id
            ) mb ON r.digital_catalog_id = mb.digital_catalog_id
            ORDER BY r.release_date DESC
            """
        )
        rows = cursor.fetchall()

    headers = [
        "Release",
        "Artist",
        "Release Date",
        "Type",
        "Catalog ID",
        "Tape Catalog ID",
        "CD Catalog ID",
        "LP Catalog ID",
        "Archive Catalog ID",
        "Bandcamp URL",
        "Musicbrainz Link",
    ]

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(
                [
                    row["album_title"] or "",
                    row["album_artists"] or "",
                    _format_release_date(row["release_date"]),
                    row["type"] or "",
                    row["digital_catalog_id"] or "",
                    row["mc_catalog_id"] or "",
                    row["cd_catalog_id"] or "",
                    row["lp_catalog_id"] or "",
                    row["archive_catalog_id"] or "",
                    row["bandcamp_url"] or "",
                    row["musicbrainz_url"] or "",
                ]
            )

    return f"Exported {len(rows)} releases to {output_path}"


@mcp.tool()
async def initialize_database(force: bool = False) -> str:
    """
    Initialises the release catalog database by creating all required tables.

    By default this is idempotent: existing tables are left untouched.
    Set `force=True` to drop and recreate the entire database file from scratch.
    WARNING: force=True will permanently delete all existing data.
    If there is no database file at all, it will be created regardless of the `force` parameter.
    If calling on an already existing database, ask the user for permission first.
    """
    try:
        init_db(DB_PATH, force=force)
        action = (
            "recreated from scratch"
            if force
            else "initialised (existing tables untouched)"
        )
        return f"Database {action}: {DB_PATH}"
    except Exception as e:
        return f"Failed to initialise database: {e}"


if __name__ == "__main__":
    mcp.run()
