import sqlite3
import polars as pl
import os


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

    def save_merged_dataframe(self):
        self.merged_df.write_csv(self.merged_filepath, separator=";")

    def convert_to_sqlite(self):

        conn = sqlite3.connect(os.path.join(BASEPATH, "merged_bandcamp_catalog.db"))
        self.merged_df.to_pandas().to_sql(
            "merged_data", conn, if_exists="replace", index=False
        )
        conn.close()

    def log_summary(self):
        missing_catalog = self.merged_df.filter(pl.col("catalog_id").is_null())
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
        self.merge_dataframes()
        self.save_merged_dataframe()
        self.convert_to_sqlite()
        self.log_summary()


if __name__ == "__main__":
    merger = CatalogMerger()
    merger.run()
