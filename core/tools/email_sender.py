"""
Email sending functionality with SMTP support and file attachments.

Provides send_email_with_attachments for sending analysis reports via email,
with support for custom body text, multiple attachments, and SMTP configuration.
"""

import os
import smtplib
import traceback
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List


def _get_smtp_config() -> Dict[str, Any]:
    """Get and validate SMTP configuration from environment variables."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM", "noreply@company.com")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not smtp_username or not smtp_password:
        return {
            "status": "error",
            "error": "SMTP credentials not configured. Please set SMTP_USERNAME and SMTP_PASSWORD in .env file",
        }

    return {
        "status": "success",
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_password": smtp_password,
        "email_from": email_from,
        "use_tls": use_tls,
    }


def _create_email_body(analysis_type: str, custom_body: str = None) -> str:
    """Create email body from custom body or default template."""
    if custom_body:
        return custom_body

    return f"""
Manufacturing Analytics Report

Analysis Type: {analysis_type}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Please find the attached report(s) for your review.

This is an automated message from the Manufacturing Analytics System.
"""


def _attach_file_to_message(msg: MIMEMultipart, file_path: str) -> Dict[str, Any]:
    """Attach a single file to the email message."""
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return {"status": "error", "error": f"File not found: {file_path}"}

    try:
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={file_path_obj.name}",
            )
            msg.attach(part)
            return {"status": "success", "filename": file_path_obj.name}
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to attach file {file_path_obj.name}: {str(e)}",
        }


def _attach_files_to_message(
    msg: MIMEMultipart, file_paths: List[str]
) -> Dict[str, Any]:
    """Attach all files to the email message."""
    attached_files = []
    for file_path in file_paths:
        result = _attach_file_to_message(msg, file_path)
        if result["status"] == "error":
            return result
        attached_files.append(result["filename"])
    return {"status": "success", "attached_files": attached_files}


def _send_email_via_smtp(
    msg: MIMEMultipart,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    use_tls: bool,
) -> Dict[str, Any]:
    """Send email via SMTP server."""
    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        return {"status": "success"}
    except smtplib.SMTPAuthenticationError:
        return {
            "status": "error",
            "error": "SMTP authentication failed. Please check your email credentials in .env file",
        }
    except smtplib.SMTPException as e:
        return {"status": "error", "error": f"SMTP error: {str(e)}"}


def send_email_with_attachments(
    recipient_email: str,
    file_paths: List[str],
    subject: str = None,
    analysis_type: str = "Analysis",
    custom_body: str = None,
) -> Dict[str, Any]:
    """Send email with analysis report attachments and optional custom body."""
    try:
        # Get SMTP configuration
        smtp_config = _get_smtp_config()
        if smtp_config["status"] == "error":
            return smtp_config

        # Create message
        msg = MIMEMultipart()
        msg["From"] = smtp_config["email_from"]
        msg["To"] = recipient_email
        msg["Subject"] = (
            subject or f"{analysis_type} Report - {datetime.now().strftime('%Y-%m-%d')}"
        )

        # Create and attach body
        body = _create_email_body(analysis_type, custom_body)
        msg.attach(MIMEText(body, "plain"))

        # Attach files
        attach_result = _attach_files_to_message(msg, file_paths)
        if attach_result["status"] == "error":
            return attach_result

        # Send email
        send_result = _send_email_via_smtp(
            msg,
            smtp_config["smtp_host"],
            smtp_config["smtp_port"],
            smtp_config["smtp_username"],
            smtp_config["smtp_password"],
            smtp_config["use_tls"],
        )
        if send_result["status"] == "error":
            return send_result

        return {
            "status": "success",
            "message": f"Email sent successfully to {recipient_email}",
            "attached_files": attach_result["attached_files"],
            "recipient": recipient_email,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to send email: {str(e)}",
            "traceback": traceback.format_exc(),
        }
