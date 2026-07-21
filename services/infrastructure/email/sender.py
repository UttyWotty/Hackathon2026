"""
Email Sender - Core email sending logic.

Separated from routers to avoid circular imports.
Used by both email_router and queue_processor.
"""

import logging
import os
import smtplib
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def send_email_with_retry(
    to_email: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: Optional[List[str]] = None,
    retry_count: int = 3,
) -> Dict[str, Any]:
    """
    Send email with retry logic and exponential backoff.

    Args:
        to_email: Recipient email
        subject: Email subject
        body: Email body
        html: Whether body is HTML
        attachments: List of file paths to attach
        retry_count: Number of retry attempts

    Returns:
        dict: Send result with status and details
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM", "noreply@company.com")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not smtp_username or not smtp_password:
        return {
            "status": "error",
            "error": "SMTP credentials not configured",
        }

    last_error = None

    for attempt in range(1, retry_count + 1):
        try:
            # Create message
            msg = MIMEMultipart()
            msg["From"] = email_from
            msg["To"] = to_email
            msg["Subject"] = subject

            # Attach body
            body_type = "html" if html else "plain"
            msg.attach(MIMEText(body, body_type))

            # Attach files
            attached_files = []
            if attachments:
                for file_path in attachments:
                    file_path_obj = Path(file_path)
                    if file_path_obj.exists():
                        with open(file_path, "rb") as f:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                "Content-Disposition",
                                f"attachment; filename={file_path_obj.name}",
                            )
                            msg.attach(part)
                            attached_files.append(file_path_obj.name)

            # Send email with timeout
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            if use_tls:
                server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            server.quit()

            logger.info(
                f"✅ Email sent successfully to {to_email} (attempt {attempt}/{retry_count})"
            )

            return {
                "status": "success",
                "message": f"Email sent successfully to {to_email}",
                "recipient": to_email,
                "subject": subject,
                "attachments": attached_files,
                "attempts": attempt,
            }

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ SMTP authentication failed: {e}")
            return {
                "status": "error",
                "error": "SMTP authentication failed. Check credentials.",
                "attempts": attempt,
            }

        except (smtplib.SMTPException, OSError, TimeoutError) as e:
            last_error = str(e)
            logger.warning(
                f"⚠️  Email send failed (attempt {attempt}/{retry_count}): {e}"
            )

            if attempt < retry_count:
                # Exponential backoff: 2^attempt seconds (2s, 4s, 8s)
                backoff_time = 2**attempt
                logger.info(f"   Retrying in {backoff_time}s...")
                time.sleep(backoff_time)

        except Exception as e:
            logger.error(f"❌ Unexpected error sending email: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Unexpected error: {str(e)}",
                "attempts": attempt,
            }

    # All retries failed
    logger.error(f"❌ Email send failed after {retry_count} attempts: {last_error}")
    return {
        "status": "error",
        "error": f"Failed after {retry_count} attempts: {last_error}",
        "attempts": retry_count,
    }
