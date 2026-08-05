import os
import csv
import time
import shutil
import requests
import re
import mimetypes
import logging

from pdf2image import convert_from_path
import pytesseract
from pypdf import PdfReader
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from .utils import (
    safe_navigate_to_url, check_element_exists,
    input_element, click_element_by_js, select_by_text,
    get_element_attribute
)

# Tesseract executable (after installing from https://github.com/UB-Mannheim/tesseract/wiki)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# Poppler 'bin' folder (after extracting from https://github.com/oschwartz10612/poppler-windows/releases)
POPPLER_PATH = r"C:\Users\Admin\Downloads\Release-26.02.0-0\poppler-26.02.0\Library\bin"
# ----------------------------------------------------------------------

ENABLE_OCR_FALLBACK = True

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


def _normalize(text: str) -> str:
    """Collapse all whitespace into single spaces and lowercase, so line
    wraps / extra spacing / case differences don't break substring matches."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_text_pypdf(file_path: str) -> str:
    """Extract text using pypdf. Returns '' if nothing extractable."""
    text = ""
    reader = PdfReader(file_path)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text.strip()


def _extract_text_ocr(file_path: str) -> str:
    """Fallback for scanned/image-based PDFs with no embedded text layer.
    Rasterizes each page to an image and runs Tesseract OCR on it."""
    text = ""
    pages = convert_from_path(file_path, poppler_path=POPPLER_PATH)
    for i, image in enumerate(pages, start=1):
        page_text = pytesseract.image_to_string(image)
        text += page_text + "\n"
    return text.strip()


def extract_pdf_text_and_check_for_the_text(file_path: str, files_to_check: list[dict]) -> tuple[bool, str]:
    """
    If file_path is a PDF, extracts its text (embedded text first, OCR as
    fallback for scanned PDFs) and checks whether any entry in files_to_check
    has its text_to_check (or alternative_text) present.

    Returns (True, file_name) on the first match, else (False, '').
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type != 'application/pdf':
        return False, ''

    try:
        full_text = _extract_text_pypdf(file_path)
        used_ocr = False

        if not full_text and ENABLE_OCR_FALLBACK:
            logger.info(f"No embedded text in {file_path}, running OCR...")
            full_text = _extract_text_ocr(file_path)
            used_ocr = True

        if not full_text:
            logger.warning(
                f"No extractable text in {file_path} even after "
                f"{'OCR' if used_ocr else 'text extraction'}."
            )
            return False, ''

        normalized_full_text = _normalize(full_text)

        for file in files_to_check:
            text_to_check = str(file.get('text_to_check', '')).strip()
            file_name = str(file.get('file_name', '')).strip()
            alternative_text = str(file.get('alternative_text', '')).strip()

            if text_to_check and _normalize(text_to_check) in normalized_full_text:
                return True, file_name
            if alternative_text and _normalize(alternative_text) in normalized_full_text:
                return True, file_name

        logger.info(
            f"No matching text found in {file_path} "
            f"({'via OCR' if used_ocr else 'via embedded text'}). "
            f"Extracted preview: {full_text[:300]!r}"
        )
        return False, ''

    except Exception as e:
        logger.error(f"Error reading PDF {file_path}: {e}")
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
