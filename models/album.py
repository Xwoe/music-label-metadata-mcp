from pydantic import BaseModel
from datetime import datetime
from typing import List
import csv
import json


class Track(BaseModel):
    artists: List[str] = []
    track_number: int = 0
    track_title: str = ""
    runtime: int = 0

    def to_json(self) -> str:
        return self.model_dump_json()

    def to_csv(self) -> str:
        output = []
        output.append(["artists", "track_number", "track_title", "runtime"])
        output.append([", ".join(self.artists), self.track_number, self.track_title, self.runtime])
        return "\n".join([",".join(map(str, row)) for row in output])
    def __str__(self):
        return f"Track(artists={self.artists}, track_number={self.track_number}, track_title={self.track_title}, runtime={self.runtime})"

class Album(BaseModel):
    artists: List[str] = []
    title: str = ""
    is_compilation: bool = False
    release_date: datetime = datetime.now()
    label: str = ""
    total_length: int = 0
    num_tracks: int = 0
    catalog_number: str = ""
    tags: List[str] = []
    tracks: List[Track] = []

    def to_json(self) -> str:
        return self.model_dump_json()

    def to_csv(self) -> str:
        output = []
        output.append(["artist", "release_date", "label", "total_length", "num_tracks", "catalog_number", "tags"])
        output.append([
            ", ".join(self.artists) if self.artists else "",
            self.release_date.isoformat(),
            self.label,
            self.total_length,
            self.num_tracks,
            self.catalog_number,
            ", ".join(self.tags)
        ])
        output.append([])
        output.append(["tracks"])
        output.append(["artists", "track_number", "track_title", "runtime"])
        for track in self.tracks:
            output.append([", ".join(track.artists), track.track_number, track.track_title, track.runtime])
        return "\n".join([",".join(map(str, row)) for row in output])

    def __str__(self):
        return f"Album(artists={self.artists}, release_date={self.release_date}, label={self.label}, num_tracks={self.num_tracks})"