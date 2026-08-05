def generate_missing_documents_email(record):
    """
    Generates an HTML email body and subject for missing documents.

    Args:
        record (dict): A dictionary containing 'email' and 'files' (missing files).

    Returns:
        dict: A dictionary containing the target 'to_email', 'subject', and 'html_body'.
    """
    target_email = record.get("email")
    missing_files = record.get("files", [])
    missing_files_list = missing_files.split(", ") if isinstance(missing_files, str) else missing_files

    # Static subject
    subject = "Action Required: Missing Documents for Your Teaching Qualification"

    # Format the missing files into HTML list items (<li>)
    if isinstance(missing_files_list, list) and missing_files_list:
        files_html = "\n".join([f"            <li>{file}</li>" for file in missing_files_list])
    else:
        files_html = "            <li>Unspecified missing documents</li>"

    # Construct the HTML email body using <ol> for a numbered list
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="font-family: Arial, sans-serif; color: #333333; line-height: 1.6; max-width: 600px; margin: 0 auto;">

    <p>Dear Instructor,</p>

    <p>We are currently reviewing your Enrollware profile to verify your teaching qualifications. It appears that we are still missing some required documentation.</p> 

    <p>Please reply directly to this email and attach the following missing document(s) at your earliest convenience:</p>

    <ol>
{files_html}
    </ol>

    <p>Completing this step promptly ensures your profile remains compliant and there are no delays in your teaching schedule.</p>

    <p>If you have already submitted these documents or believe you are receiving this message in error, please let us know.</p>

    <br>
    <p>Best regards,<br>
    <strong>The Code Blue CPR Services Team</strong></p>

</body>
</html>
"""

    return {
        "to_email": target_email,
        "to_name": record.get("username", "Instructor"),
        "subject": subject,
        "html_body": html_body.strip()
    }
