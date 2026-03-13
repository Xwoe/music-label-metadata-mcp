import os
import re
import sqlite3
import polars as pl
from sqlalchemy.types import Integer
from global_config import BASEPATH, DB_PATH, BANDCAMP_FILENAME, CATALOG_FILENAME, ALBUM_LABEL
from models.names_prefixes import COLUMN_DICT, ReleaseType
from mldg_utils import generate_release_id


class CatalogMerger:
    def __init__(self, bandcamp_filepath=None, catalog_filepath=None):
        self.bandcamp_filepath = bandcamp_filepath or os.path.join(
            BASEPATH, BANDCAMP_FILENAME
        )
        self.catalog_filepath = catalog_filepath or os.path.join(
            BASEPATH, CATALOG_FILENAME
        )
        self.merged_filepath = os.path.join(BASEPATH, "merged_bandcamp_catalog.csv")

    def load_dataframes(self):
        self.catalog_df = pl.read_csv(self.catalog_filepath)
        self.bandcamp_df = pl.read_csv(self.bandcamp_filepath, separator=";")

    def merge_dataframes(self):
        self.merged_df = self.bandcamp_df.join(
            self.catalog_df,
            left_on=["album_artists", "album_title"],
            right_on=["Artist", "Release"],
            how="left",
        )

    def add_unique_release_id(self):
        self.merged_df = self.merged_df.with_columns(
            pl.struct(["album_artists", "album_title"])
            .map_elements(
                lambda row: generate_release_id(
                    row["album_artists"], row["album_title"]
                ),
                return_dtype=pl.Utf8,
            )
            .alias("release_id")
        )

    def cleanup_columns(self):
        self.merged_df = self.merged_df.rename({"Type": "type"})
        self.merged_df = self.merged_df.with_columns(
            [
                pl.col("track_number").cast(pl.Int32),
                pl.col("runtime").cast(pl.Int32),
                pl.col("total_length").cast(pl.Int32),
                pl.col("num_tracks").cast(pl.Int32),
            ]
        )
        self.merged_df = self.merged_df.with_columns(
            pl.when(pl.col("album_artists") == "Various")
            .then(pl.lit("Various Artists"))
            .otherwise(pl.col("album_artists"))
            .alias("album_artists")
        )
        self.merged_df = self.merged_df.drop_nulls(
            subset=["album_artists", "album_title"]
        )
        self.merged_df[["track_number", "runtime", "total_length", "num_tracks"]] = (
            self.merged_df[
                ["track_number", "runtime", "total_length", "num_tracks"]
            ].fill_nan(0)
        )

    def clean_up_bandcamp_albums(self):
        self.bandcamp_df = self.bandcamp_df.with_columns(
            pl.when(pl.col("album_artists") == ALBUM_LABEL)
            .then(pl.lit("Various"))
            .otherwise(pl.col("album_artists"))
            .alias("album_artists")
        )

    def clean_up_catalog_numbers(self):
        self.catalog_df = self.catalog_df.with_columns(
            pl.coalesce(
                [
                    pl.col("Archive ID"),
                    pl.col("Catalog ID"),
                ]
            ).alias("catalog_id")
        )

    def clean_up_catalog_columns(self):

        # Process Historical Physical ID and categorize by release type
        def categorize_physical_id(physical_id):
            cassette_col = COLUMN_DICT[ReleaseType.CASSETTE]
            cd_col = COLUMN_DICT[ReleaseType.CD]
            lp_col = COLUMN_DICT[ReleaseType.LP]

            if physical_id is None:
                return {cassette_col: None, cd_col: None, lp_col: None}

            cassettes, cds, lps = [], [], []
            for item in physical_id.split(" / "):
                if item.startswith("prc0"):
                    cassettes.append(item)
                elif item.startswith("prcd0"):
                    cds.append(item)
                elif item.startswith("prlp"):
                    lps.append(item)

            return {
                cassette_col: " / ".join(cassettes) if cassettes else None,
                cd_col: " / ".join(cds) if cds else None,
                lp_col: " / ".join(lps) if lps else None,
            }

        def categorize_digital_id(digital_id):
            if digital_id is None:
                return None

            if digital_id.startswith("PR-"):
                return digital_id

            return None

        # Rename Archive ID column
        self.catalog_df = self.catalog_df.rename({"Archive ID": "archive_catalog_id"})

        # Create missing columns with null values
        for col_name in COLUMN_DICT.values():
            if col_name not in self.catalog_df.columns:
                self.catalog_df = self.catalog_df.with_columns(
                    pl.lit(None).alias(col_name)
                )

        # result = self.catalog_df.select("Historical Physical ID").to_dicts()
        # map the entries from the "Historical Physical ID" column to the new categorized columns based on release type
        for col in [
            COLUMN_DICT[ReleaseType.CASSETTE],
            COLUMN_DICT[ReleaseType.CD],
            COLUMN_DICT[ReleaseType.LP],
            # COLUMN_DICT[ReleaseType.ARCHIVE],
        ]:
            self.catalog_df = self.catalog_df.with_columns(
                pl.col("Historical Physical ID")
                .map_elements(
                    lambda x: categorize_physical_id(x)[col], return_dtype=pl.Utf8
                )
                .alias(col)
            )
        # copy the values from the `catalog_id` column to the digital catalog column if they are digital ids
        self.catalog_df = self.catalog_df.with_columns(
            pl.col("catalog_id")
            .map_elements(
                lambda x: categorize_digital_id(x),
                return_dtype=pl.Utf8,
            )
            .alias(COLUMN_DICT[ReleaseType.DIGITAL])
        )
        self.catalog_df = self.catalog_df.with_columns(
            pl.when(
                pl.col("digital_catalog_id").str.starts_with(ReleaseType.ARCHIVE.value)
            )
            .then(pl.lit(None))
            .otherwise(pl.col("digital_catalog_id"))
            .alias("digital_catalog_id")
        )

        # rename the column `catalog_id` to `legacy_catalog_id`
        self.catalog_df = self.catalog_df.rename({"catalog_id": "legacy_catalog_id"})

    def rename_catalog_ids(self):
        self.catalog_df = self.catalog_df.with_columns(
            pl.col(COLUMN_DICT[ReleaseType.CASSETTE])
            .str.replace_all("prc", ReleaseType.CASSETTE)
            .alias(COLUMN_DICT[ReleaseType.CASSETTE])
        )
        self.catalog_df = self.catalog_df.with_columns(
            pl.col(COLUMN_DICT[ReleaseType.LP])
            .str.replace_all("prlp", ReleaseType.LP)
            .alias(COLUMN_DICT[ReleaseType.LP])
        )
        self.catalog_df = self.catalog_df.with_columns(
            pl.col(COLUMN_DICT[ReleaseType.CD])
            .str.replace_all("prcd", ReleaseType.CD)
            .alias(COLUMN_DICT[ReleaseType.CD])
        )

    def drop_columns(self):
        colunns_to_drop = ["catalog_number", "Historical Physical ID", "Catalog ID"]
        self.merged_df = self.merged_df.drop(colunns_to_drop)

    def save_merged_dataframe(self):
        self.merged_df.write_csv(self.merged_filepath, separator=";")

    def convert_to_sqlite(self):

        dtype_mapping = {
            # "track_number": Integer,
            # "runtime": Integer,
            # "total_length": Integer,
            # "num_tracks": Integer,
        }

        conn = sqlite3.connect(DB_PATH)
        self.merged_df.to_pandas().to_sql(
            "merged_data",
            conn,
            if_exists="replace",
            index=False,
            dtype=dtype_mapping,
        )
        cursor = conn.cursor()

        self.normalize_database(conn)
        self.create_url_tables(conn)

        conn.close()

    def create_url_tables(self, conn):
        cursor = conn.cursor()
        sources = ["discogs", "musicbrainz", "cddb"]
        link_types = [
            ("mc", "mc_catalog_id"),
            ("cd", "cd_catalog_id"),
            ("lp", "lp_catalog_id"),
            ("digital", "digital_catalog_id"),
            ("archive", "archive_catalog_id"),
        ]

        for source in sources:
            for link_type, catalog_id_col in link_types:
                table_name = f"{source}_{link_type}_links"
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {catalog_id_col} TEXT,
                    url_record TEXT,
                    FOREIGN KEY ({catalog_id_col}) REFERENCES releases({catalog_id_col})
                    )
                """
                )

        conn.commit()

    def normalize_database(self, conn):
        cursor = conn.cursor()

        # Create releases table first
        cursor.execute("DROP TABLE IF EXISTS releases")
        cursor.execute(
            """
            CREATE TABLE releases (
                release_id          TEXT PRIMARY KEY,
                album_artists       TEXT,
                album_title         TEXT,
                label               TEXT,
                total_length        INTEGER,
                num_tracks          INTEGER,
                tags                TEXT,
                release_date        TEXT,
                type                TEXT,
                mc_catalog_id       TEXT,
                cd_catalog_id       TEXT,
                lp_catalog_id       TEXT,
                digital_catalog_id  TEXT,
                archive_catalog_id  TEXT,
                legacy_catalog_id   TEXT,
                bandcamp_url        TEXT
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO releases
                (release_id, album_artists, album_title, label,
                 total_length, num_tracks, tags, release_date, type,
                 mc_catalog_id, cd_catalog_id, lp_catalog_id,
                 digital_catalog_id, archive_catalog_id, legacy_catalog_id, bandcamp_url)
            SELECT DISTINCT release_id, album_artists, album_title, label,
                    total_length, num_tracks, tags, release_date, type,
                    mc_catalog_id, cd_catalog_id, lp_catalog_id,
                    digital_catalog_id, archive_catalog_id, legacy_catalog_id, bandcamp_url
            FROM merged_data
            """
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_digital_catalog_id ON releases(digital_catalog_id)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_cd_catalog_id ON releases(cd_catalog_id)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_lp_catalog_id ON releases(lp_catalog_id)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_mc_catalog_id ON releases(mc_catalog_id)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_archive_catalog_id ON releases(archive_catalog_id)"
        )

        cursor.execute("DROP TABLE IF EXISTS tracks")
        cursor.execute(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                release_id TEXT,
                track_number INTEGER,
                artists TEXT,
                track_title TEXT,
                runtime INTEGER,
                isrc TEXT,
                FOREIGN KEY (release_id) REFERENCES releases(release_id) ON DELETE CASCADE
            )
            """
        )

        # Insert tracks into tracks table
        cursor.execute(
            """
            INSERT INTO tracks (release_id, track_number, artists, track_title, runtime, isrc)
            SELECT release_id, track_number, artists, track_title, runtime, isrc
            FROM merged_data
            ORDER BY release_id, track_number
            """
        )

        # Drop the original table
        cursor.execute("DROP TABLE merged_data")

        # Create artist table
        cursor.execute("DROP TABLE IF EXISTS artist")
        cursor.execute(
            """
            CREATE TABLE artist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            """
        )

        # Create artist_track_link table
        cursor.execute("DROP TABLE IF EXISTS artist_track_link")
        cursor.execute(
            """
            CREATE TABLE artist_track_link (
                artist_id INTEGER NOT NULL,
                track_id INTEGER NOT NULL,
                PRIMARY KEY (artist_id, track_id),
                FOREIGN KEY (artist_id) REFERENCES artist(id),
                FOREIGN KEY (track_id) REFERENCES tracks(id)
            )
            """
        )

        # Populate artist and artist_track_link from tracks.artists column
        cursor.execute("SELECT id, artists FROM tracks WHERE artists IS NOT NULL")
        for track_id, artists_str in cursor.fetchall():
            artists = re.split(r"\|| & ", artists_str)
            for artist_name in (a.strip() for a in artists if a.strip()):
                cursor.execute(
                    "INSERT OR IGNORE INTO artist (name) VALUES (?)", (artist_name,)
                )
                cursor.execute("SELECT id FROM artist WHERE name = ?", (artist_name,))
                artist_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT OR IGNORE INTO artist_track_link (artist_id, track_id) VALUES (?, ?)",
                    (artist_id, track_id),
                )

        conn.commit()

    def log_summary(self):
        missing_catalog = self.merged_df.filter(pl.col("legacy_catalog_id").is_null())
        unique_missing = missing_catalog.select(
            ["album_artists", "album_title"]
        ).unique()
        print("Missing Catalog IDs for:")
        with pl.Config(tbl_rows=-1, fmt_str_lengths=1000):
            print(unique_missing)

    def run(self):
        self.load_dataframes()
        self.clean_up_bandcamp_albums()
        self.clean_up_catalog_numbers()
        self.clean_up_catalog_columns()
        self.rename_catalog_ids()
        self.merge_dataframes()
        self.cleanup_columns()
        self.add_unique_release_id()
        self.drop_columns()
        self.save_merged_dataframe()
        self.convert_to_sqlite()
        self.log_summary()


if __name__ == "__main__":
    merger = CatalogMerger()
    merger.run()
