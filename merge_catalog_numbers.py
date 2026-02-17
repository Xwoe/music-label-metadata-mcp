import sqlite3
import polars as pl
import os
from sqlalchemy.types import Integer
from models.names_prefixes import COLUMN_DICT, ReleaseType


BANDCAMP_FILENAME = "bandcamp_albums.csv"
CATALOG_FILENAME = "catalog_numbers.csv"
BASEPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


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
            pl.concat_str(["album_artists", "album_title"], separator="|")
            .hash(seed=0)
            .cast(pl.Utf8)
            .alias("release_id")
        )

    def cleanup_columns(self):
        self.merged_df = self.merged_df.with_columns(
            [
                pl.col("track_number").cast(pl.Int32),
                pl.col("runtime").cast(pl.Int32),
                pl.col("total_length").cast(pl.Int32),
                pl.col("num_tracks").cast(pl.Int32),
            ]
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
            pl.when(pl.col("album_artists") == "Passed Recordings")
            .then(pl.lit("Various"))
            .otherwise(pl.col("album_artists"))
            .alias("album_artists")
        )

    def clean_up_catalog_numbers(self):
        self.catalog_df = self.catalog_df.with_columns(
            pl.coalesce(
                [
                    pl.col("Historical Physical ID"),
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
            # arch_col = COLUMN_DICT[ReleaseType.ARCHIVE]

            if physical_id is None:
                return {cassette_col: None, cd_col: None, lp_col: None}

            cassettes, cds, lps, arch = [], [], [], []
            for item in physical_id.split(" / "):
                if item.startswith("prc0"):
                    cassettes.append(item)
                elif item.startswith("prcd0"):
                    cds.append(item)
                elif item.startswith("prlp"):
                    lps.append(item)
                # elif item.startswith("PR-ARCH-"):
                #     arch.append(item)

            return {
                cassette_col: " / ".join(cassettes) if cassettes else None,
                cd_col: " / ".join(cds) if cds else None,
                lp_col: " / ".join(lps) if lps else None,
                # arch_col: " / ".join(arch) if arch else None,
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

        conn = sqlite3.connect(os.path.join(BASEPATH, "merged_bandcamp_catalog.db"))
        self.merged_df.to_pandas().to_sql(
            "merged_data",
            conn,
            if_exists="replace",
            index=False,
            dtype=dtype_mapping,
        )
        conn.close()

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
