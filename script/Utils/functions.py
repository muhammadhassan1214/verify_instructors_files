import os
import csv
import time
import shutil
import logging
import requests
import mimetypes

from pypdf import PdfReader
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from .utils import (
    safe_navigate_to_url, check_element_exists,
    input_element, click_element_by_js, select_by_text,
    get_element_attribute
)

# Load environment variables and validate
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Validate required environment variables
REQUIRED_ENV_VARS = ["ENROLLWARE_USERNAME", "ENROLLWARE_PASSWORD"]


def validate_environment_variables() -> bool:
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        return False
    return True


def login_to_enrollware_and_navigate_to_instructor_records(driver, max_retries: int = 3) -> bool:
    if not validate_environment_variables():
        return False

    for attempt in range(max_retries):
        try:
            if not safe_navigate_to_url(driver, "https://enrollware.com/admin"):
                continue

            time.sleep(3)

            # Check if already logged in
            validation_button = check_element_exists(driver, (By.ID, "loginButton"), timeout=5)

            if validation_button:
                # Input credentials with validation
                if not input_element(driver, (By.ID, "username"), os.getenv("ENROLLWARE_USERNAME")):
                    logger.error("Failed to input username")
                    continue

                if not input_element(driver, (By.ID, "password"), os.getenv("ENROLLWARE_PASSWORD")):
                    logger.error("Failed to input password")
                    continue

                # Optional remember me checkbox
                click_element_by_js(driver, (By.ID, "rememberMe"))
                time.sleep(1)

                if not click_element_by_js(driver, (By.ID, "loginButton")):
                    logger.error("Failed to click login button")
                    continue

                # Wait for login to complete
                time.sleep(20)

                # Verify login success
                if "admin" in driver.current_url.lower():
                    logger.info("Successfully logged into Enrollware")
                else:
                    logger.warning("Login may have failed, checking current URL")
                    continue

            return navigate_to_instructor_records(driver)

        except:
            if attempt < max_retries - 1:
                time.sleep(3)
                continue

    logger.error("Failed to login to Enrollware after all attempts")
    return False


def navigate_to_instructor_records(driver, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        try:
            url = "https://www.enrollware.com/admin/tc-user-list.aspx"
            if safe_navigate_to_url(driver, url):
                logger.info("Successfully navigated to Instructor Records")
                # apply all filters
                select_by_text(driver, (By.XPATH, "//div[@class='dataTables_length']//select"), 'All')
                return True
        except Exception as e:
            logger.error(f"Navigation attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue

    logger.error("Failed to navigate to Instructor Records after all attempts")
    return False


def get_element_value(driver, element_id: str) -> str:
    try:
        locator = (By.ID, f"mainContent_{element_id}")
        value = get_element_attribute(driver, locator, "value")
        if value is not None:
            return value
        else:
            logger.warning(f"Element {locator} does not have a 'value' attribute.")
            return ""
    except Exception as e:
        logger.error(f"An error occurred while getting element value: {e}")
        return ""


def extract_pdf_text_and_check_for_the_text(file_path: str, files_to_check: list[dict]) -> tuple[bool, str]:
    """
    Identifies the file type. If it is a PDF, parses and returns its text.
    Otherwise, returns an empty string.
    """

    # Guess the MIME type based on the file extension
    mime_type, _ = mimetypes.guess_type(file_path)

    # Check if the file is explicitly recognized as a PDF
    if mime_type == 'application/pdf':
        try:
            extracted_text = ""
            reader = PdfReader(file_path)

            # Iterate through all pages and extract text
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"

            full_text = extracted_text.strip()

            for file in files_to_check:
                text_to_check = str(file.get('text_to_check', '')).strip()
                file_name = str(file.get('file_name', '')).strip()
                alternative_text = str(file.get('alternative_text', '')).strip()

                # Check primary text first
                if text_to_check and text_to_check in full_text:
                    return True, file_name

                # If primary text is not found, fallback to alternative text when provided
                if alternative_text and alternative_text in full_text:
                    return True, file_name

        except Exception as e:
            print(f"Error reading the PDF file: {e}")
            return False, ''

    # If it's a PNG, JPEG, or anything else, return an empty string
    return False, ''


def delete_file(file_path: str, file_name: str):
    try:
        os.remove(file_path)
        print(f"File '{file_name}' has been deleted.")
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' does not exist.")
    except PermissionError:
        print(f"Error: You do not have permission to delete '{file_path}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def download_file(url, path, name):
    try:
        response = requests.get(url, stream=True, timeout=60)
        if response.status_code == 200:
            with open(path, "wb") as f:
                shutil.copyfileobj(response.raw, f)
            logger.info(f"Downloaded: {name}")
        else:
            logger.error(f"Failed to download {url}")
    except Exception as e:
        logger.error(f"Exception downloading {url}: {e}")


def generate_record(email, username, reason, _files) -> dict:
    record = {
        "email": email,
        "username": username,
        "files": _files,
        "reason": reason,
    }
    return record


def append_to_csv(csv_path: str, row: dict) -> None:
    """Append a row to the CSV log, creating headers if the file is new."""
    headers = ["email", "username", "missing files", "reason"]
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "email": row.get("email", ""),
            "username": row.get("username", ""),
            "missing files": row.get("files", ""),
            "reason": row.get("reason", ""),
        })
