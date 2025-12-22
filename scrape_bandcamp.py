from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import mechanicalsoup
from bs4 import BeautifulSoup
from log import get_logger
from models.album import Album, Track

logger = get_logger(__name__)

class BandcampScraper:
    def __init__(self, wait_selector, timeout=10, bandcamp_url: str = ""):
        """
        Use Selenium to load dynamic content, then parse with Beautiful Soup
        """
        # Set up Selenium driver
        self.options = webdriver.ChromeOptions()
        self.options.add_argument('--headless')
        self.driver = webdriver.Chrome(options=self.options)
        self.wait_selector = wait_selector
        self.timeout = timeout

        self.bandcamp_url = bandcamp_url

    def run(self):
        self.driver.get(self.bandcamp_url)

        # Wait for dynamic content to load
        WebDriverWait(self.driver, self.timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
        )

        # Get the page source after JavaScript execution
        html_content = self.driver.page_source

        # Parse with Beautiful Soup
        soup = BeautifulSoup(html_content, 'html.parser')
        albums = soup.select('li.music-grid-item')
        logger.info(f"Found {len(albums)} albums on the page.")
        for album in albums:
            album_url = album.find('a')['href']
            if not album_url.startswith('http'):
                album_url = 'https://passedrecordings.bandcamp.com' + album_url
            print(f"Found album URL: {album_url}")


    def parse_album(self, album_url: str):
        album = Album()
        browser = mechanicalsoup.StatefulBrowser()
        browser.open(album_url)
        soup = browser.page
        self.extract_album_title(album, soup)
        track_rows = soup.select('table#track_table tr.track_row_view')
        for track_row in track_rows:
            self.parse_track(album, track_row)

        print(f"Parsed album: {album}")
        print(album.to_json())
        print(album.to_csv())

    def extract_album_title(self, album, soup):
        name_section = soup.find('div', id='name-section')
        artist_link = name_section.find('a')
        if artist_link:
            album.artists = [artist_link.text.strip()]
        album.title = name_section.find('h2', class_='trackTitle').text.strip()

    def parse_track(self, album, track_row):
        track = Track()
        track.track_number = int(track_row.find('div', class_='track_number').text[:-1])
        full_title = track_row.find('span', class_='track-title').text.strip()
        full_title_parts = full_title.split(' - ')
        if len(full_title_parts) > 1:
            track.artists = [part.strip() for part in full_title_parts[:-1]]
            track.track_title = full_title_parts[-1].strip()
        else:
            track.artists = album.artists
            track.track_title = full_title
        runtime_str = track_row.find('span', class_='time').text.strip()
        minutes, seconds = map(int, runtime_str.split(':'))
        track.runtime = minutes * 60 + seconds
        album.runtime += track.runtime
        album.tracks.append(track)
        print(f"Parsed track: {track}")

if __name__ == "__main__":
    bandcamp_url = "https://passedrecordings.bandcamp.com/"
    wait_selector = 'li.music-grid-item'
    scraper = BandcampScraper(wait_selector=wait_selector, bandcamp_url=bandcamp_url)
    #scraper.run()
    scraper.parse_album('https://passedrecordings.bandcamp.com/album/scapes-2')
    # album_data = scraper.scrape_album_info('https://artistname.bandcamp.com/album/albumname')
    # print(album_data)
    #scraper.close()