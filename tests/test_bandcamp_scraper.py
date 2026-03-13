import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from global_config import BANDCAMP_URL
from scrape_bandcamp import BandcampScraper


def test_scrape_first_10_albums():
    scraper = BandcampScraper(bandcamp_url=BANDCAMP_URL)
    parsed = []

    for album_url in scraper.iterate_albums():
        try:
            album = scraper.parse_album(album_url)
        except Exception as e:
            print(f"Error parsing album at {album_url}: {e}")
            continue
        print(album)
        parsed.append(album)
        if len(parsed) >= 10:
            break

    return parsed


if __name__ == "__main__":
    test_scrape_first_10_albums()
