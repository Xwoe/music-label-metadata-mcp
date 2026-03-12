import polars as pl


def generate_release_id(album_artists: str, album_title: str) -> str:
    """Generates a deterministic release ID by hashing the artist and title."""
    return (
        pl.Series([f"{album_artists}|{album_title}"])
        .hash(seed=0)
        .cast(pl.Utf8)
        .item()
    )
