import os

BASEPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_NAME = "release_catalog.db"
DB_PATH = os.path.join(BASEPATH, DB_NAME)

BANDCAMP_FILENAME = "bandcamp_albums.csv"
CATALOG_FILENAME = "catalog_numbers.csv"

VALID_SERVICES = ["musicbrainz", "discogs", "cddb"]
USER_AGENT = "album-data-app/1.0"

ALBUM_LABEL = os.environ["MUSICLABEL"]
