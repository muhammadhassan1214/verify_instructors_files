import os
import sys
import base64
import logging
from selenium.webdriver.common.by import By
from mail_sender import email_generator, email_sender
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

    # Resolve paths and load the email attachment BEFORE spinning up the
    # browser/logging in, so a missing attachment fails fast instead of
    # wasting a full login cycle.
    downloads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Downloads")
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir, exist_ok=True)
    csv_log_path = os.path.join(downloads_dir, "instructors_skipped.csv")

    ATTACHMENT_PATH = rf"{downloads_dir}\AHA Application Agreement and monitoring form.pdf"  # adjust path as needed
    ATTACHMENT_NAME = "AHA Application Agreement and monitoring form.pdf"  # name shown to recipient

    try:
        with open(ATTACHMENT_PATH, "rb") as f:
            ATTACHMENT_B64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Could not load email attachment at {ATTACHMENT_PATH}: {e}")
        return

    try:
        if not processor.initialize():
            return
        if not login_to_enrollware_and_navigate_to_instructor_records(processor.driver):
            return

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
                missing_files_name = ", ".join([f["file_name"] for f in files_to_check])
                record = generate_record(email, username, "No File(s) Found", missing_files_name)
                # message = email_generator.generate_missing_documents_email(record)
                # email_sender.send_email(message, ATTACHMENT_NAME, ATTACHMENT_B64)
                append_to_csv(csv_log_path, record)
                continue

            # Keep only files that are not already present remotely by filename match.
            file_paths = []
            for file_link in all_files:
                file_url = str(file_link.get_attribute("href") or "").strip()
                file_name = str(file_link.text or "").strip() or os.path.basename(file_url.split("?")[0]) or "unknown_file"
                local_path = os.path.join(downloads_dir, file_name.lower())
                file_paths.append({"path": local_path, "name": file_name, "url": file_url})

            found_files = set()
            for file_info in file_paths:
                if len(found_files) >= len(files_to_check):
                    logger.info(
                        f"All required document types already found for {username}; "
                        f"skipping remaining files"
                    )
                    break

                file_path = file_info["path"]

                if os.path.exists(file_path):
                    # Leftover from a prior interrupted run - don't re-download,
                    # but still check it; skipping it outright would mean any
                    # match inside it is silently lost.
                    logger.info(f"File already exists locally, checking without re-downloading: {file_info['name']}")
                else:
                    download_file(file_info["url"], file_path, file_info["name"])
                    if not os.path.exists(file_path):
                        logger.warning(f"Download failed, skipping check for: {file_info['name']}")
                        continue

                matched_file_names = extract_pdf_text_and_check_for_the_text(
                    file_path, files_to_check, found_files
                )
                if matched_file_names:
                    found_files.update(matched_file_names)

                delete_file(file_path, file_info['name'])

            missing_files = [
                file["file_name"] for file in files_to_check
                if file["file_name"] not in found_files
            ]

            missing_files_name = ", ".join(missing_files)
            row = generate_record(email, username, "File(s) missing", missing_files_name)
            append_to_csv(csv_log_path, row)

            # if missing_files_name:
                # message = email_generator.generate_missing_documents_email(row)
                # email_sender.send_email(message, ATTACHMENT_NAME, ATTACHMENT_B64)

            # add url to done_urls.txt for avoiding re-processing
            with open(done_urls_path, "a", encoding="utf-8") as f:
                f.write(url + "\n")

        processor.cleanup()
        print("\nAll users have been processed\n")


    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
    finally:
        if 'processor' in locals():
            processor.cleanup()


if __name__ == "__main__":
    main()
