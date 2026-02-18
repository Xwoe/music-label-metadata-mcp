import os
import sqlite3

# from typing import Any
# import httpx

from contextlib import contextmanager
from mcp.server.fastmcp import FastMCP
from models.names_prefixes import ALBUM_LABEL, ReleaseType, COLUMN_DICT

# Initialize FastMCP server
mcp = FastMCP("MusicLabelDataFiller")

# Constants
# NWS_API_BASE = "https://api.weather.gov"


USER_AGENT = "album-data-app/1.0"

BASEPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
DB_NAME = "merged_bandcamp_catalog.db"
DB_PATH = os.path.join(BASEPATH, DB_NAME)


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


@mcp.tool()
async def fetch_release_by_name(artist_name: str, release_title: str) -> dict:
    """
    Fetches a release from the SQLite database based on artist name and release title.
    Returns a JSON object with the release details or an error message if not found.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Query the database for the specific release
        cursor.execute(
            "SELECT album_artists, album_title, label, release_id, release_date FROM merged_data WHERE album_artists = ? AND album_title = ?",
            (artist_name, release_title),
        )
        row = cursor.fetchone()

    if not row:
        return {"error": "Release not found"}

    # Format the data into a clean structure for the LLM
    return {
        "artist_name": row["album_artists"],
        "release_title": row["album_title"],
        "label": row["label"],
        "release_id": row["release_id"],
        "release_date": row["release_date"],
    }


@mcp.tool()
async def prepare_release_for_musicbrainz(release_id: str) -> dict:
    """
    Fetches a specific release from our DB and formats it for MusicBrainz submission.
    Returns a JSON object the browser tool can use to fill forms.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Query your specific release
        cursor.execute(
            "SELECT album_artists, album_title, label, catalog_id, release_date FROM releases WHERE id = ?",
            (release_id,),
        )
        row = cursor.fetchone()

    if not row:
        return {"error": "Release not found"}

    # Format the data into a clean structure for the LLM
    return {
        "artist_name": row["album_artists"],
        "release_title": row["album_title"],
        "label": row["label"],
        "catalog_number": row["catalog_id"],
        "release_date": row["release_date"],
        "archive_catalog_id": row["archive_catalog_id"],
        "digital_catalog_id": row["digital_catalog_id"],
        "target_url": "https://musicbrainz.org/release/add",
    }


@mcp.tool()
async def list_all_releases() -> list:
    """
    Fetches all releases from the database and returns them as a list of JSON objects.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT album_artists, album_title, label, catalog_id, release_date FROM merged_data"
        )
        rows = cursor.fetchall()

    return [
        {
            "artist_name": row["album_artists"],
            "release_title": row["album_title"],
            "label": ALBUM_LABEL,
            "catalog_number": row["catalog_id"],
            "release_date": row["release_date"],
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
            f"SELECT MAX({column_name}) FROM merged_data WHERE {column_name} LIKE ?",
            (f"{release_type.value}%",),
        )
        max_id = cursor.fetchone()[0]

    # Placeholder logic for generating a new catalog ID
    if max_id is None:
        return f"{release_type.value}0001"
    else:
        new_id_num = int(max_id.split("-")[-1]) + 1
        return f"{release_type.value}{new_id_num:03d}"


if __name__ == "__main__":
    mcp.run()
