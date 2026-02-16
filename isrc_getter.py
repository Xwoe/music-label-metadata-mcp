import os
import sys
import json
import spotipy
import webbrowser
import requests

from spotipy.oauth2 import SpotifyOAuth
from bs4 import BeautifulSoup
import spotipy.util as util
from json.decoder import JSONDecodeError
from spotipy.oauth2 import SpotifyClientCredentials
import pandas as pd

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id="YOUR_APP_CLIENT_ID", client_secret="YOUR_APP_CLIENT_SECRET"
    )
)


from log import get_logger

logger = get_logger(__name__)


class ISRCGetter:

    def __init__(
        self,
    ):
        self.filename = ""
        self.username = os.environ["SPOTIFY_USER_NAME"]
        self.client_id = os.environ["SPOTIPY_CLIENT_ID"]
        self.client_secret = os.environ["SPOTIPY_CLIENT_SECRET"]
        self.redirect_uri = (
            "http://127.0.0.1:8888/callback"  # os.environ["SPOTIPY_REDIRECT_URI"]
        )
        self.scope = "user-read-private user-read-playback-state user-modify-playback-state playlist-modify-private playlist-read-private"
        self.init_spotify()

    def init_spotify(self):
        self.spotify = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=self.client_id, client_secret=self.client_secret
            )
        )

    def set_token(self):
        try:
            self.token = util.prompt_for_user_token(
                username=self.username,
                scope=self.scope,
                redirect_uri=self.redirect_uri,
            )
        except (AttributeError, JSONDecodeError):
            logger.info("except")
            os.remove(f".cache-{self.username}")
            self.token = util.prompt_for_user_token(
                username=self.username, scope=self.scope, redirect_uri=self.redirect_uri
            )

    def get_isrc_from_track(self, artist, track):

        isrc = ""
        results = self.spotify.search(q=f"artist:{artist} track:{track}", type="track")
        try:
            if results and "tracks" in results:
                isrc = self.get_isrc(results)
                logger.info(f"Found ISRC {isrc} for {artist} - {track}")
        except Exception as e:
            logger.warning(f"{artist} - {track} not found, exception: {e}")
        return isrc

    def get_isrc(self, results):
        try:
            track_items = results["tracks"]["items"]
            if len(track_items) < 1:
                return ""
            return track_items[0]["external_ids"]["isrc"]
        except Exception as e:
            logger.warning(f"ISRC not found, exception: {e}")
            return ""

    def iterate_track_df(self, track_df):
        track_df["isrc"] = ""
        for index, row in track_df.iterrows():
            artist = row["artists"]
            track = row["track_title"]
            isrc = self.get_isrc_from_track(artist, track)
            track_df.at[index, "isrc"] = isrc
        return track_df

    def read_track_csv(self):
        filename = self.set_filename()
        return pd.read_csv(filename)

    def set_filename(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(script_dir, "results")
        self.filename = os.path.join(results_dir, "bandcamp_albums.csv")
        return self.filename

    def parse_bandcamp_albums(self):
        df = self.read_track_csv()
        self.iterate_track_df(df)
        df.to_csv(self.filename, index=False)
        return df


if __name__ == "__main__":
    getter = ISRCGetter()
    df = getter.parse_bandcamp_albums()
