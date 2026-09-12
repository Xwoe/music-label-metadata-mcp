import json
import os
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import mechanicalsoup
from bs4 import BeautifulSoup
from global_config import MUSICLABEL, BANDCAMP_URL, VARIOUS_ARTISTS
from log import get_logger
from models.album import Album, Track
from isrc_getter import ISRCGetter


logger = get_logger(__name__)


def classify_release_type(album_artists, title, num_tracks, item_type=None) -> str:
    """Best-effort release type from the signals Bandcamp actually exposes.

    Bandcamp only distinguishes an album from a standalone track, so:
      - Single       -> a standalone track, a single-track release, or a
                        title explicitly marked "(Single)".
      - Compilation  -> a Various Artists release, or a title saying "Compilation".
      - EP           -> only when the title explicitly says "EP" (Bandcamp gives
                        no way to tell an EP from an album otherwise).
      - Album        -> the default for everything else.

    `album_artists` may be a list (from a scraped Album) or the joined string
    (from a database row).
    """
    if isinstance(album_artists, (list, tuple)):
        artists_str = ", ".join(album_artists)
    else:
        artists_str = album_artists or ""
    title = title or ""
    title_lower = title.lower()

    if "(single)" in title_lower:
        return "Single"
    if (item_type or "").lower() == "track" or (num_tracks or 0) <= 1:
        return "Single"
    if "compilation" in title_lower or artists_str.strip().lower() == VARIOUS_ARTISTS.lower():
        return "Compilation"
    if re.search(r"\bEP\b", title):
        return "EP"
    return "Album"


class BandcampScraper:
    def __init__(
        self, wait_selector="li.music-grid-item", timeout=10, bandcamp_url: str = ""
    ):
        """
        Use Selenium to load dynamic content, then parse with Beautiful Soup
        """
        # Set up Selenium driver
        self.options = webdriver.ChromeOptions()
        self.options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=self.options)
        self.wait_selector = wait_selector
        self.timeout = timeout
        self.bandcamp_url = bandcamp_url
        self.csv = ""
        self.isrc_getter = ISRCGetter()

    def run(self):
        self.driver.get(self.bandcamp_url)

        # Wait for dynamic content to load
        WebDriverWait(self.driver, self.timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
        )
        failed_album_links = []

        # Get the page source after JavaScript execution
        html_content = self.driver.page_source

        # Parse with Beautiful Soup
        soup = BeautifulSoup(html_content, "html.parser")
        albums = soup.select("li.music-grid-item")
        logger.info(f"Found {len(albums)} albums on the page.")
        max_count = 500
        i = 0
        include_header = True
        for album in albums:
            i += 1
            if i > max_count:
                break
            album_url = album.find("a")["href"]
            if not album_url.startswith("http"):
                album_url = self.bandcamp_url.rstrip("/") + album_url
            print(f"Found album URL: {album_url}")
            try:
                album = self.parse_album(album_url)
                self.csv += album.to_csv(include_header)
                include_header = False

            except Exception as e:
                logger.error(
                    f"Error parsing album at {album_url}: {e}. Hint: Unreleased albums can't be parsed."
                )
                failed_album_links.append(album_url)
        if failed_album_links:
            logger.warning(
                f"Failed to parse the following album links: {failed_album_links}"
            )

        print(self.csv)
        self.store_csv(self.csv)

    def iterate_albums(self):
        self.driver.get(self.bandcamp_url)

        # Wait for dynamic content to load
        WebDriverWait(self.driver, self.timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, self.wait_selector))
        )

        # Get the page source after JavaScript execution
        html_content = self.driver.page_source

        # Parse with Beautiful Soup
        soup = BeautifulSoup(html_content, "html.parser")
        albums = soup.select("li.music-grid-item")
        logger.info(f"Found {len(albums)} albums on the page.")
        for album in albums:
            album_url = album.find("a")["href"]
            if not album_url.startswith("http"):
                album_url = self.bandcamp_url.rstrip("/") + album_url
            print(f"Found album URL: {album_url}")
            yield album_url

    def parse_album(self, album_url: str):
        album = Album()
        album.bandcamp_url = album_url
        browser = mechanicalsoup.StatefulBrowser()
        browser.open(album_url)
        soup = browser.page

        item_type = None
        data_el = soup.find(attrs={"data-tralbum": True})
        if data_el is not None:
            # Preferred path: Bandcamp embeds the full track listing (titles,
            # numbers and durations) in the data-tralbum JSON blob. This works
            # even for pre-order / not-yet-released albums, whose rendered HTML
            # track rows are only partially present -- locked tracks have no
            # track-title span and no duration until the album goes public, which
            # made the HTML-table parser crash on every multi-track pre-order.
            tralbum = json.loads(data_el["data-tralbum"])
            item_type = tralbum.get("item_type")
            self.extract_from_tralbum(album, tralbum)
        else:
            # Legacy fallback: parse the rendered HTML track table.
            self.extract_album_title(album, soup)
            self.extract_release_date(album, soup)
            track_rows = soup.select("table#track_table tr.track_row_view")
            for track_row in track_rows:
                self.parse_track(album, track_row)

        self.extract_tags(album, soup)
        album.label = MUSICLABEL
        album.num_tracks = len(album.tracks)
        # Bandcamp exposes only album-vs-track; fall back to the URL when the
        # JSON blob is absent (a /track/ URL is a standalone single).
        if not item_type:
            item_type = "track" if "/track/" in album_url else "album"
        album.type = classify_release_type(
            album.album_artists, album.title, album.num_tracks, item_type
        )
        print(f"Parsed album: {album}")
        return album

    def extract_from_tralbum(self, album, tralbum):
        current = tralbum.get("current") or {}
        artist = (tralbum.get("artist") or "").strip()
        album.album_artists = self.get_album_artists_name([artist] if artist else [])
        album.title = (current.get("title") or "").strip()
        release_date = current.get("release_date") or tralbum.get("album_release_date")
        parsed_date = self.parse_bandcamp_date(release_date)
        if parsed_date:
            album.release_date = parsed_date
        for track_info in tralbum.get("trackinfo") or []:
            self.parse_track_from_json(album, track_info)

    def parse_track_from_json(self, album, track_info):
        track = Track()
        track.track_number = int(track_info.get("track_num") or (len(album.tracks) + 1))
        full_title = (track_info.get("title") or "").strip()
        full_title_parts = full_title.split(" - ")
        if len(full_title_parts) > 1:
            track.artists = [part.strip() for part in full_title_parts[:-1]]
            track.track_title = full_title_parts[-1].strip()
        else:
            track.artists = album.album_artists
            track.track_title = full_title
        duration = track_info.get("duration") or 0
        track.runtime = int(round(float(duration)))
        # A locked pre-order track reports a 0 duration and is not on streaming
        # services yet, so only look up an ISRC once the track is actually public.
        if track.runtime > 0:
            track.isrc = self.get_isrc(artist=track.artists_str, track=track.track_title)
        else:
            track.isrc = ""
        album.total_length += track.runtime
        album.tracks.append(track)

    @staticmethod
    def parse_bandcamp_date(date_str):
        """Parses a Bandcamp date string like '22 Sep 2026 00:00:00 GMT'."""
        if not date_str:
            return None
        for fmt in ("%d %b %Y %H:%M:%S GMT", "%d %b %Y %H:%M:%S %Z"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def extract_album_title(self, album, soup):
        name_section = soup.find("div", id="name-section")
        artist_link = name_section.find("a")
        if artist_link:
            album.album_artists = self.get_album_artists_name(
                [artist_link.text.strip()]
            )
        album.title = name_section.find("h2", class_="trackTitle").text.strip()

    def get_album_artists_name(self, artists: list[str]) -> list[str]:
        # Always return a list: album_artists is later joined with LIST_SEPARATOR,
        # so returning a bare string here mangles it into "V|a|r|i|o|u|s|...".
        if not artists:
            return []
        if len(artists) == 1 and artists[0] == MUSICLABEL:
            return [VARIOUS_ARTISTS]
        return artists

    def extract_release_date(self, album, soup):
        release_info = soup.find("div", class_="tralbum-credits")
        if release_info:
            release_text = release_info.get_text()
            match = re.search(
                r"released \s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", release_text
            )
            if match:
                date_str = match.group(1)
                album.release_date = datetime.strptime(date_str, "%B %d, %Y")

    def extract_tags(self, album, soup):
        tag_section = soup.find("div", class_="tralbum-tags")
        if tag_section:
            tags = [tag.text.strip() for tag in tag_section.find_all("a")]
            album.tags = tags

    def parse_track(self, album, track_row):
        track = Track()
        track.track_number = int(track_row.find("div", class_="track_number").text[:-1])
        full_title = track_row.find("span", class_="track-title").text.strip()
        full_title_parts = full_title.split(" - ")
        if len(full_title_parts) > 1:
            track.artists = [part.strip() for part in full_title_parts[:-1]]
            track.track_title = full_title_parts[-1].strip()
        else:
            track.artists = album.album_artists
            track.track_title = full_title
        runtime_str = track_row.find("span", class_="time").text.strip()
        track.runtime = self.runtime_seconds(runtime_str)
        track.isrc = self.get_isrc(artist=track.artists_str, track=track.track_title)
        album.total_length += track.runtime
        album.tracks.append(track)
        # print(f"Parsed track: {track}")

    def get_isrc(self, artist, track):
        return self.isrc_getter.get_isrc_from_track(artist, track)

    def runtime_seconds(self, runtime_str):
        timesplits = runtime_str.split(":")
        if len(timesplits) == 3:
            hours, minutes, seconds = map(int, timesplits)
            return hours * 3600 + minutes * 60 + seconds
        else:
            minutes, seconds = map(int, timesplits)
            return minutes * 60 + seconds

    def store_csv(self, csv_data: str, filename: str = "bandcamp_albums.csv"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        filename = os.path.join(data_dir, filename)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(csv_data)


if __name__ == "__main__":
    wait_selector = "li.music-grid-item"
    scraper = BandcampScraper(wait_selector=wait_selector, bandcamp_url=BANDCAMP_URL)
    scraper.run()
