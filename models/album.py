from pydantic import BaseModel
from datetime import datetime
from typing import List
import csv
import json

CSV_SEPARATOR = ";"
LIST_SEPARATOR = "|"
STR_SEP = ", "


class Track(BaseModel):
    artists: List[str] = []
    track_number: int = 0
    track_title: str = ""
    runtime: int = 0
    isrc: str = ""

    def to_json(self) -> str:
        return self.model_dump_json()

    def to_csv(self) -> str:
        output = []
        output.append(["artists", "track_number", "track_title", "runtime"])
        output.append(
            [
                LIST_SEPARATOR.join(self.artists),
                self.track_number,
                self.track_title,
                self.runtime,
                self.isrc,
            ]
        )
        return "\n".join([CSV_SEPARATOR.join(map(str, row)) for row in output])

    @property
    def artists_str(self) -> str:
        return STR_SEP.join(self.artists)

    def __str__(self):
        return f"Track(artists={self.artists}, track_number={self.track_number}, track_title={self.track_title}, runtime={self.runtime})"


class Album(BaseModel):
    album_artists: List[str] = []
    title: str = ""
    is_compilation: bool = False
    release_date: datetime = datetime.now()
    label: str = ""
    total_length: int = 0
    num_tracks: int = 0
    catalog_number: str = ""
    bandcamp_url: str = ""
    tags: List[str] = []
    tracks: List[Track] = []

    def to_json(self) -> str:
        return self.model_dump_json()

    def to_csv(self, include_header) -> str:
        output = []
        if include_header:
            output.append(
                [
                    "album_artists",
                    "label",
                    "album_title",
                    "artists",
                    "track_number",
                    "track_title",
                    "runtime",
                    "isrc",
                    "total_length",
                    "num_tracks",
                    "release_date",
                    "catalog_number",
                    "bandcamp_url",
                    "tags",
                ]
            )

        for track in self.tracks:
            # album part
            output.append(
                [
                    (
                        LIST_SEPARATOR.join(self.album_artists)
                        if self.album_artists
                        else ""
                    ),
                    self.label,
                    self.title,
                    # track part
                    LIST_SEPARATOR.join(track.artists),
                    track.track_number,
                    track.track_title,
                    track.runtime,
                    track.isrc,
                    self.total_length,
                    self.num_tracks,
                    self.release_date.isoformat(),
                    self.catalog_number,
                    self.bandcamp_url,
                    LIST_SEPARATOR.join(self.tags),
                ]
            )
        output = "\n".join([CSV_SEPARATOR.join(map(str, row)) for row in output])
        output += "\n"
        return output

    def __str__(self):
        return f"Album(artists={self.album_artists}, release_date={self.release_date}, label={self.label}, num_tracks={self.num_tracks})"
