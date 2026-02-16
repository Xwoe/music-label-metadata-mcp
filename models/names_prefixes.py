from enum import Enum

ALBUM_LABEL = "Passed Recordings"


class ReleaseType(Enum):
    DIGITAL = "PR-"
    CASSETTE = "PR-CS-"
    LP = "PR-LP-"
    CD = "PR-CD-"
    ARCHIVE = "PR-ARCH-"


COLUMN_DICT = {
    ReleaseType.DIGITAL: "digital_catalog_id",
    ReleaseType.CASSETTE: "cassette_catalog_id",
    ReleaseType.LP: "lp_catalog_id",
    ReleaseType.CD: "cd_catalog_id",
    ReleaseType.ARCHIVE: "archive_catalog_id",
}
