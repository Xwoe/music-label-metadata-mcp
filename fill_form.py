import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select


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
            self.fill_artist_title(release_data)
            self.fill_type(release_data)
            self.fill_release_event(release_data)
            self.fill_tracks(release_data)

            print("Form pre-filled.")

        except Exception as e:
            print(f"Error filling form: {e}")

    def fill_artist_title(self, release_data):
        title_input = self.wait.until(EC.presence_of_element_located((By.ID, "name")))
        title_input.send_keys(release_data.get("release_title", ""))

        # Note: The artist field is often complex (searchable dropdown).
        # You might need to send keys and then select an option if it appears,
        # or just fill the text if it allows free text.
        artist_input = self.driver.find_element(By.ID, "ac-source-single-artist")
        artist_input.send_keys(release_data.get("artist_name", ""))

    def fill_type(self, release_data):
        release_type = release_data.get("type", "")
        if release_type:
            try:
                type_select = Select(self.driver.find_element(By.ID, "primary-type"))
                # Map or capitalize if necessary (MusicBrainz uses Title Case for these options)
                # Simple heuristic: try the value as is, then Title Case
                try:
                    type_select.select_by_visible_text(release_type)
                except:
                    # Fallback to Title case (e.g. "album" -> "Album")
                    type_select.select_by_visible_text(release_type.title())
            except Exception as e:
                print(f"Could not select release type '{release_type}': {e}")

    def fill_release_event(self, release_data):
        # Handle Release Date
        date_str = release_data.get("release_date", "")
        if date_str:
            parts = date_str.split("-")
            try:
                # Year
                if len(parts) >= 1:
                    self.driver.find_element(
                        By.CSS_SELECTOR, "input.partial-date-year"
                    ).send_keys(parts[0])
                # Month
                if len(parts) >= 2:
                    self.driver.find_element(
                        By.CSS_SELECTOR, "input.partial-date-month"
                    ).send_keys(parts[1])
                # Day
                if len(parts) >= 3:
                    self.driver.find_element(
                        By.CSS_SELECTOR, "input.partial-date-day"
                    ).send_keys(parts[2])
            except Exception as e:
                print(f"Error filling date: {e}")

        # Handle Label
        label_name = release_data.get("label", "")
        if label_name:
            try:
                self.driver.find_element(By.ID, "label-0").send_keys(label_name)
            except Exception as e:
                print(f"Error filling label: {e}")

        # Handle Catalog Number (checking various keys that might exist)
        cat_no = (
            release_data.get("mc_catalog_id")
            or release_data.get("cd_catalog_id")
            or release_data.get("lp_catalog_id")
            or release_data.get("digital_catalog_id")
        )
        if cat_no:
            try:
                self.driver.find_element(By.ID, "catno-0").send_keys(cat_no)
            except Exception as e:
                print(f"Error filling catalog number: {e}")

        # Handle Barcode (Click "This release does not have a barcode")
        try:
            no_barcode_checkbox = self.driver.find_element(By.ID, "no-barcode")
            if not no_barcode_checkbox.isSelected():
                no_barcode_checkbox.click()
        except Exception as e:
            print(f"Error clicking no-barcode checkbox: {e}")

    def get_tracklist(self, tracks):
        formatted_tracks = []
        for track in tracks:
            track_num = track.get("track_number", "")
            title = track.get("track_title", "")
            artists = track.get("artists", "")
            runtime = track.get("runtime", 0)
            # Convert runtime from seconds to mm:ss format
            minutes = runtime // 60
            seconds = runtime % 60
            time_str = f"{minutes}:{seconds:02d}"
            formatted_track = f"{track_num}. {title} - {artists} ({time_str})"
            formatted_tracks.append(formatted_track)

        return "\n".join(formatted_tracks)

    def fill_tracks(self, release_data):
        tracks = release_data.get("tracks", [])
        if not tracks:
            return

        tracklist_str = self.get_tracklist(tracks)
        try:
            
            tracklist_input = self.driver.find_element(By.ID, "tracklist")
            tracklist_input.send_keys(tracklist_str)
        except Exception as e:
            print(f"Error filling tracklist: {e}")

    def close(self):
        # self.driver.quit()
        pass


if __name__ == "__main__":
    # Test
    filler = MusicBrainzFiller()
    test_data = {
        "artist_name": "Exit Chamber",
        "release_title": "Phased Returns",
        "label": "Passed Recordings",
        "mc_catalog_id": "PR-MC-003",
        "cd_catalog_id": None,
        "lp_catalog_id": None,
        "digital_catalog_id": "PR-018",
        "release_date": "2023-10-06T00:00:00",
        "archive_catalog_id": None,
        "type": "Album",
        "tracks": [
            {
                "track_number": 1,
                "artists": "Exit Chamber",
                "track_title": "Test Flight",
                "runtime": 412,
                "isrc": "QZTB42353296",
            },
            {
                "track_number": 2,
                "artists": "Exit Chamber",
                "track_title": "First Experience of Vacuum",
                "runtime": 520,
                "isrc": "QZTB42353297",
            },
            {
                "track_number": 3,
                "artists": "Exit Chamber",
                "track_title": "A Mote of Dust Suspended in a Sunbeam",
                "runtime": 415,
                "isrc": "QZTB42353298",
            },
            {
                "track_number": 4,
                "artists": "Exit Chamber",
                "track_title": "It's Not Over, It's Just Different",
                "runtime": 569,
                "isrc": "QZTB42353299",
            },
            {
                "track_number": 5,
                "artists": "Exit Chamber",
                "track_title": "120AU",
                "runtime": 504,
                "isrc": "QZTB42353300",
            },
        ],
    }

    filler.fill_release(test_data)
