import os
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from models.names_prefixes import ReleaseType, COLUMN_DICT


_MB_RELEASE_URL_RE = re.compile(
    r"https://musicbrainz\.org/release/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


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

    def fill_release(
        self, release_data: dict, medium: ReleaseType = ReleaseType.DIGITAL
    ):
        self.login()

        # Navigate to the Add Release page
        self.driver.get("https://musicbrainz.org/release/add")

        try:
            # 1. Tracklist tab
            track_list = self.fill_tracks(release_data)
            # 2. Release information tab
            self.fill_artist_title(release_data)
            self.fill_type(release_data)
            self.fill_release_event(release_data, medium)

            print("Form pre-filled.")
            return track_list

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

    def fill_release_event(
        self, release_data, medium: ReleaseType = ReleaseType.DIGITAL
    ):
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
        self.fill_catalog_id(release_data, medium)

        # Handle Bandcamp URL
        bandcamp_url = release_data.get("bandcamp_url", "")
        if bandcamp_url:
            try:
                external_link_input = self.driver.find_element(
                    By.CSS_SELECTOR, "input.value.with-button[type='url']"
                )
                external_link_input.send_keys(bandcamp_url)
            except Exception as e:
                print(f"Error filling Bandcamp URL: {e}")

        # Handle Barcode (Click "This release does not have a barcode")
        try:
            # Check if the checkbox is already checked (isSelected might not work on the input if hidden/custom,
            # but usually works on standard checkbox inputs).
            # The label implies it's a standard input.
            no_barcode_checkbox = self.driver.find_element(By.ID, "no-barcode")
            if not no_barcode_checkbox.is_selected():
                no_barcode_checkbox.click()
        except Exception as e:
            # If element not found or interaction failed
            pass  # print(f"Error clicking no-barcode checkbox: {e}")

            print("Form pre-filled.")

        except Exception as e:
            print(f"Error filling form: {e}")

    def fill_catalog_id(self, release_data, medium):

        if medium == ReleaseType.CASSETTE:
            cat_no = release_data.get("mc_catalog_id")
        elif medium == ReleaseType.CD:
            cat_no = release_data.get("cd_catalog_id")
        elif medium == ReleaseType.LP:
            cat_no = release_data.get("lp_catalog_id")
        elif medium == ReleaseType.DIGITAL:
            cat_no = release_data.get("digital_catalog_id")
        else:
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

    def fill_tracks(self, release_data: dict):
        tracklist_str = ""
        try:
            tracklist_str = self.get_tracklist_str(release_data)
            if not tracklist_str:
                print("No track data available to fill.")
                return
            # Click Tracklist tab
            # The structure suggests jQuery UI tabs
            tracklist_tab = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='#tracklist']"))
            )
            tracklist_tab.click()

            # Wait for textarea inside the dialog
            # The user mentioned the widget has class "ui-dialog"
            textarea = self.wait.until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, "div.ui-dialog textarea.tracklist")
                )
            )

            # Clear and paste
            textarea.clear()
            textarea.send_keys(tracklist_str)
            print("Tracklist filled.")

            # Click "Add medium"
            add_medium_btn = self.wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button[data-click='addMedium']")
                )
            )
            add_medium_btn.click()

            # Navigate back to Release Information tab
            release_info_tab = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='#information']"))
            )
            release_info_tab.click()
            return tracklist_str

        except Exception as e:
            print(f"Error filling tracklist: {e}")
            return tracklist_str

    def get_tracklist_str(self, release_data: dict):
        # Format tracklist string from release_date (which seems to contain tracks in other parts of the code)
        # or usage logic needs to pass it.
        # Assuming release_data has a 'tracks' list based on previous context.
        tracks = release_data.get("tracks", [])
        tracklist_str = ""
        for t in tracks:
            # Format: 1. Title - Artist (Time) or similar, depending on what the parser accepts.
            # MusicBrainz track parser usually accepts: "1. Title - Artist (3:45)"
            # Using a simple format: "Track Number. Track Title - Artist (Runtime)""
            # Format runtime
            duration = ""
            rt = t.get("runtime", 0)
            if rt and rt > 0:
                m, s = divmod(rt, 60)
                duration = f" ({m}:{s:02d})"

            track_str = f"{t.get('track_number')}. {t.get('track_title')} - {t.get('artists')}{duration}"
            tracklist_str += track_str + "\n"
        return tracklist_str.strip()

    def wait_for_submission(self, timeout: int = 300) -> str | None:
        """
        Polls the browser URL until MusicBrainz navigates to the new release page
        after the user submits the form. Returns the release URL or None on timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                current_url = self.driver.current_url
                if _MB_RELEASE_URL_RE.match(current_url):
                    return current_url
            except Exception:
                return None
            time.sleep(1)
        return None

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
        "bandcamp_url": "https://exitchamber.bandcamp.com/album/phased-returns",
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

    tracklist = filler.fill_release(test_data)
    print("Tracklist string to fill in form:")
    print(tracklist)
