"""
Email Client for Notifications.

Provides SMTP email sending capabilities for analysis results and notifications.

Author: Utku Gulbardak
Date: 2025-10-22
"""

import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional


class EmailClient:
    """
    Email client for sending notifications and reports.

    Supports:
    - Plain text and HTML emails
    - File attachments
    - Multiple recipients
    - SMTP with TLS/SSL
    """

    def __init__(self):
        """
        Initialize email client with configuration from environment.

        Required environment variables:
        - SMTP_HOST
        - SMTP_PORT
        - SMTP_USERNAME (optional)
        - SMTP_PASSWORD (optional)
        - SMTP_USE_TLS (default: true)
        - EMAIL_FROM
        """
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USERNAME")
        self.password = os.getenv("SMTP_PASSWORD")
        self.use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.from_address = os.getenv("EMAIL_FROM", "noreply@example.com")

    def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None,
        html: bool = False,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email with optional attachments.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body (plain text or HTML)
            attachments: Optional list of file paths to attach
            html: Whether body is HTML (default: False)
            cc: Optional CC recipients
            bcc: Optional BCC recipients

        Returns:
            dict: Send result
            {
                "status": "success"|"error",
                "recipients": int,
                "message": str,
            }
        """
        try:
            # Create message
            msg = MIMEMultipart()
            msg["From"] = self.from_address
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject

            if cc:
                msg["Cc"] = ", ".join(cc)

            # Add body
            body_type = "html" if html else "plain"
            msg.attach(MIMEText(body, body_type))

            # Add attachments
            if attachments:
                for file_path in attachments:
                    self._attach_file(msg, file_path)

            # Send email
            all_recipients = to + (cc or []) + (bcc or [])

            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()

                if self.username and self.password:
                    server.login(self.username, self.password)

                server.send_message(msg, self.from_address, all_recipients)

            return {
                "status": "success",
                "recipients": len(all_recipients),
                "message": f"Email sent successfully to {len(to)} recipient(s)",
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

    def _attach_file(self, msg: MIMEMultipart, file_path: str):
        """
        Attach a file to the email message.

        Args:
            msg: MIMEMultipart message object
            file_path: Path to file to attach
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {file_path}")

        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())

        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {path.name}")
        msg.attach(part)

    def validate_config(self) -> Dict[str, Any]:
        """
        Validate email configuration.

        Returns:
            dict: Validation result
        """
        issues = []

        if not self.host:
            issues.append("SMTP_HOST not configured")

        if not self.from_address:
            issues.append("EMAIL_FROM not configured")

        if self.username and not self.password:
            issues.append("SMTP_PASSWORD required when SMTP_USERNAME is set")

        if issues:
            return {
                "status": "error",
                "valid": False,
                "issues": issues,
            }

        return {
            "status": "success",
            "valid": True,
            "config": {
                "host": self.host,
                "port": self.port,
                "from_address": self.from_address,
                "use_tls": self.use_tls,
                "authentication": "enabled" if self.username else "disabled",
            },
        }


# Global instance
_client_instance: EmailClient = None


def get_email_client() -> EmailClient:
    """
    Get the global email client instance.

    Returns:
        EmailClient: Email client instance
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = EmailClient()
    return _client_instance
