import random
import time
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

class BandcampScraper:
    def __init__(self, bandcamp_url: str = "", headless: bool = False):
        options = Options()
        # Keep the browser open after the script finishes
        options.add_experimental_option("detach", True)
        self.browser = webdriver.Chrome(options=options)
        self.browser.maximize_window()

    def scrape_album_info(self, album_url: str) -> dict:
        self.browser.get(album_url)
        time.sleep(random.uniform(2, 4))  # Random delay to mimic human behavior

        album_info = {}
        try:
            album_info['title'] = self.browser.find_element(By.CSS_SELECTOR, 'h2.trackTitle').text
            album_info['artist'] = self.browser.find_element(By.CSS_SELECTOR, 'span.artist').text
            album_info['release_date'] = self.browser.find_element(By.CSS_SELECTOR, 'meta[itemprop="datePublished"]').get_attribute('content')
            album_info['genre'] = self.browser.find_element(By.CSS_SELECTOR, 'a.genre').text
        except Exception as e:
            print(f"Error scraping album info: {e}")

        return album_info

    def close(self):
        self.browser.quit()


if __name__ == "__main__":
    bandcamp_url = "https://passedrecordings.bandcamp.com/"
    scraper = BandcampScraper()
    # album_data = scraper.scrape_album_info('https://artistname.bandcamp.com/album/albumname')
    # print(album_data)
    #scraper.close()