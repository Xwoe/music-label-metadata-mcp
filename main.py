import asyncio
import os
import sqlite3

# from typing import Any
# import httpx

from contextlib import contextmanager
from mcp.server.fastmcp import FastMCP
from models.names_prefixes import ALBUM_LABEL, ReleaseType, COLUMN_DICT
from fill_form import MusicBrainzFiller

# Initialize FastMCP server
mcp = FastMCP("MusicLabelDataFiller")

# Constants
# NWS_API_BASE = "https://api.weather.gov"


USER_AGENT = "album-data-app/1.0"

BASEPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
DB_NAME = "merged_bandcamp_catalog.db"
DB_PATH = os.path.join(BASEPATH, DB_NAME)

# Maps ReleaseType to (link_table_name, catalog_id_column)
MUSICBRAINZ_LINK_TABLES = {
    ReleaseType.DIGITAL: ("musicbrainz_digital_links", "digital_catalog_id"),
    ReleaseType.CASSETTE: ("musicbrainz_mc_links", "mc_catalog_id"),
    ReleaseType.LP: ("musicbrainz_lp_links", "lp_catalog_id"),
    ReleaseType.CD: ("musicbrainz_cd_links", "cd_catalog_id"),
    ReleaseType.ARCHIVE: ("musicbrainz_archive_links", "archive_catalog_id"),
}

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


if __name__ == "__main__":
    mcp.run()
