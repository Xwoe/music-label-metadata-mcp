import os
from enum import Enum

BASEPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_NAME = "release_catalog.db"
DB_PATH = os.path.join(BASEPATH, DB_NAME)

VALID_SERVICES = ["musicbrainz", "discogs", "cddb"]
USER_AGENT = "album-data-app/1.0"

VARIOUS_ARTISTS = "Various Artists"

MUSICLABEL = os.environ["MUSICLABEL"]
BANDCAMP_URL = os.environ["MUSICLABEL_BANDCAMP_URL"]


class ReleaseType(Enum):
    DIGITAL = os.environ["DIGITAL_RELEASE_PREFIX"]
    CASSETTE = os.environ["CASSETTE_RELEASE_PREFIX"]
    LP = os.environ["LP_RELEASE_PREFIX"]
    CD = os.environ["CD_RELEASE_PREFIX"]
    ARCHIVE = os.environ["ARCHIVE_RELEASE_PREFIX"]


COLUMN_DICT = {
    ReleaseType.DIGITAL: "digital_catalog_id",
    ReleaseType.CASSETTE: "mc_catalog_id",
    ReleaseType.LP: "lp_catalog_id",
    ReleaseType.CD: "cd_catalog_id",
    ReleaseType.ARCHIVE: "archive_catalog_id",
}
