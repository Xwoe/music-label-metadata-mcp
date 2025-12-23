import os
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import mechanicalsoup
from bs4 import BeautifulSoup
from log import get_logger
from models.album import Album, Track, CSV_SEPARATOR, LIST_SEPARATOR
from ISRCGetter import ISRCGetter

logger = get_logger(__name__)
ALBUM_LABEL = "Passed Recordings"


class BandcampScraper:
    def __init__(self, wait_selector, timeout=10, bandcamp_url: str = ""):
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
                album_url = "https://passedrecordings.bandcamp.com" + album_url
            print(f"Found album URL: {album_url}")
            try:
                album = self.parse_album(album_url)
                album.label = ALBUM_LABEL
                album.num_tracks = len(album.tracks)
                self.csv += album.to_csv(include_header)
                include_header = False

            except Exception as e:
                logger.error(f"Error parsing album at {album_url}: {e}")
                failed_album_links.append(album_url)
        if failed_album_links:
            logger.warning(
                f"Failed to parse the following album links: {failed_album_links}"
            )

        print(self.csv)
        self.store_csv(self.csv)

    def parse_album(self, album_url: str):
        album = Album()
        browser = mechanicalsoup.StatefulBrowser()
        browser.open(album_url)
        soup = browser.page
        self.extract_album_title(album, soup)
        self.extract_release_date(album, soup)
        self.extract_tags(album, soup)
        track_rows = soup.select("table#track_table tr.track_row_view")
        for track_row in track_rows:
            self.parse_track(album, track_row)

        print(f"Parsed album: {album}")
        return album

    def extract_album_title(self, album, soup):
        name_section = soup.find("div", id="name-section")
        artist_link = name_section.find("a")
        if artist_link:
            album.album_artists = [artist_link.text.strip()]
        album.title = name_section.find("h2", class_="trackTitle").text.strip()

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
        print(f"Parsed track: {track}")

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
        results_dir = os.path.join(script_dir, "results")
        os.makedirs(results_dir, exist_ok=True)
        filename = os.path.join(results_dir, filename)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(csv_data)


if __name__ == "__main__":
    bandcamp_url = "https://passedrecordings.bandcamp.com/"
    wait_selector = "li.music-grid-item"
    scraper = BandcampScraper(wait_selector=wait_selector, bandcamp_url=bandcamp_url)
    scraper.run()
    # scraper.parse_album('https://passedrecordings.bandcamp.com/album/scapes-2')
    # album_data = scraper.scrape_album_info('https://artistname.bandcamp.com/album/albumname')
    # print(album_data)
    # scraper.close()
