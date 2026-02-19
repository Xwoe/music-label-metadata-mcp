import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class MusicBrainzFiller:
    def __init__(self):
        options = webdriver.ChromeOptions()
        # Keep the browser open after the script finishes
        options.add_experimental_option("detach", True)
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)

    def login(self):
        username = os.environ.get("MUSICBRAINZ_USERNAME")
        password = os.environ.get("MUSICBRAINZ_PASSWORD")

        if not username or not password:
            print(
                "Credentials not found in environment variables. Skipping auto-login."
            )
            return

        self.driver.get("https://musicbrainz.org/login")
        try:
            user_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "id-username"))
            )
            user_input.send_keys(username)

            pass_input = self.driver.find_element(By.ID, "id-password")
            pass_input.send_keys(password)

            # Click the login button
            login_btn = self.driver.find_element(
                By.CSS_SELECTOR, "span.buttons.login button[type='submit']"
            )
            login_btn.click()

            # Wait for redirect to home page or dashboard to confirm login
            self.wait.until(EC.url_changes("https://musicbrainz.org/login"))
            print("Logged in successfully.")

        except Exception as e:
            print(f"Login failed: {e}")

    def fill_release(self, release_data: dict):
        self.login()

        # Navigate to the Add Release page
        self.driver.get("https://musicbrainz.org/release/add")

        try:
            # 1. Release information tab
            title_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "name"))
            )
            title_input.send_keys(release_data.get("release_title", ""))

            # Note: The artist field is often complex (searchable dropdown).
            # You might need to send keys and then select an option if it appears,
            # or just fill the text if it allows free text.
            artist_input = self.driver.find_element(By.ID, "artist-credit-0-name")
            artist_input.send_keys(release_data.get("artist_name", ""))

            # Fill other fields as needed...

            print("Form pre-filled.")

        except Exception as e:
            print(f"Error filling form: {e}")

    def close(self):
        # self.driver.quit()
        pass


if __name__ == "__main__":
    # Test
    filler = MusicBrainzFiller()
    filler.fill_release({"release_title": "Test Album", "artist_name": "Test Artist"})
