import os
import sys
import logging
from selenium.webdriver.common.by import By
from Utils.utils import get_undetected_driver
from Utils.functions import (
    login_to_enrollware_and_navigate_to_instructor_records,
    download_file, get_element_value, delete_file, generate_record,
    extract_pdf_text_and_check_for_the_text, append_to_csv
)

# Ensure the parent directory is in sys.path for reliable imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

files_to_check = [
        {
            'file_name': 'Instructor Candidate Application',
            'text_to_check': 'Instructor Candidate Application',
            'alternative_text': ''
        },
        {
            'file_name': 'Instructor Monitor Tool',
            'text_to_check': 'Instructor Monitor Tool',
            'alternative_text': ''
        },
        {
            'file_name': 'BLS E-Card',
            'text_to_check': 'Training Center Alignment',
            'alternative_text': 'Training Center Name'
        }
    ]

class VerifyInstructorsFiles:
    def __init__(self):
        self.driver = None

    def initialize(self) -> bool:
        try:
            headless = True
            self.driver = get_undetected_driver(headless=headless)
            if self.driver:
                logger.info(f"Chrome driver initialized successfully, mode: {'headless' if headless else 'headed'}")
                return True
            else:
                logger.error("Failed to initialize Chrome driver")
                return False
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Resources cleaned up successfully")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


def main():
    all_instructors_urls = []
    url = "https://www.enrollware.com/admin/tc-user-list.aspx"
    processor = VerifyInstructorsFiles()
    try:
        if not processor.initialize():
            return
        if not login_to_enrollware_and_navigate_to_instructor_records(processor.driver):
            return

        downloads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Downloads")
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir, exist_ok=True)
        csv_log_path = os.path.join(downloads_dir, "instructors_skipped.csv")

        instructor_urls = processor.driver.find_elements(By.XPATH, "//td/a[contains(@href, 'user-edit')]")
        for instructor_url in instructor_urls:
            _url = instructor_url.get_attribute("href")
            all_instructors_urls.append(_url)

        for url in all_instructors_urls:
            # Check if the instructor's URL has already been processed to avoid duplicates
            done_urls_path = os.path.join(downloads_dir, "done_urls.txt")
            if os.path.exists(done_urls_path):
                with open(done_urls_path, "r", encoding="utf-8") as f:
                    done_urls = set(line.strip() for line in f)
                if url in done_urls:
                    logger.info(f"Skipping already processed URL: {url}")
                    continue

            processor.driver.get(url)
            username = get_element_value(processor.driver, "username")
            email = get_element_value(processor.driver,"Email")

            all_files = processor.driver.find_elements(By.XPATH, "//a[@title= 'View']")
            if not all_files:
                logger.info(f"No files found for instructor: {username}")
                record = generate_record(email, username, "No File(s) Found", '')
                append_to_csv(csv_log_path, record)
                continue

            # Keep only files that are not already present remotely by filename match.
            file_paths = []
            for file_link in all_files:
                file_url = str(file_link.get_attribute("href") or "").strip()
                file_name = str(file_link.text or "").strip() or os.path.basename(file_url.split("?")[0]) or "unknown_file"
                normalized_name = file_name.lower()
                local_path = os.path.join(downloads_dir, file_name)
                file_paths.append({"path": local_path, "name": file_name, "url": file_url})

            found_files = []
            pdf_exist = False
            for file_info in file_paths:
                file_path = file_info["path"]
                if os.path.exists(file_path):
                    logger.info(f"File already exists locally, skipping download: {file_info['name']}")
                    continue

                download_file(file_info["url"], file_path, file_info["name"])

                pdf_exist, file_name = extract_pdf_text_and_check_for_the_text(file_path, files_to_check)
                if pdf_exist:
                    found_files.append(file_name)

                delete_file(file_path, file_info['name'])

            missing_files = []
            for file in files_to_check:
                if file["file_name"] not in found_files:
                    missing_files.append(file["file_name"])
            missing_files_name = ", ".join([f for f in missing_files])
            row = generate_record(email, username, "File(s) missing", missing_files_name)
            append_to_csv(csv_log_path, row)

            # add url to done_urls.txt for avoiding re-processing
            with open(done_urls_path, "a", encoding="utf-8") as f:
                f.write(url + "\n")

        processor.cleanup()
        print("\nAll files processed and sent to enrollnationwide API.\n")


    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
    finally:
        if 'processor' in locals():
            processor.cleanup()


if __name__ == "__main__":
    main()
