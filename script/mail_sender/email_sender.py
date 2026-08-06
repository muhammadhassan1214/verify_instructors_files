import os
import requests
from dotenv import load_dotenv


load_dotenv()
URL = "https://api.brevo.com/v3/smtp/email"
headers = {
    "accept": "application/json",
    "api-key": os.getenv("BREVO_API_KEY"),
    "content-type": "application/json"
}


def send_email(email_content: dict, attachment_name: str, attachment_b64: str) -> bool:
    payload = {
          "sender": {
            "name": os.getenv("SENDER_NAME"),
            "email": os.getenv("SENDER_EMAIL")
          },
          "to": [
            {
              "email": email_content.get("to_email"),
              "name": email_content.get("to_name")
            }
          ],
          "subject": email_content.get("subject"),
          "htmlContent": email_content.get("html_body"),
          "attachment": [
                {
                    "content": attachment_b64,
                    "name": attachment_name
                }
            ]
        }


    try:
        response = requests.post(URL, json=payload, headers=headers)
        if response.status_code == 201:
            return True
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"Connection Error: {e}")
        return False
