"""
Email Router - Production-grade email system with retry logic, HTML templates, and background queue.

Exposes endpoints for sending plain-text and templated emails, auto-emailing
analytics results, validating SMTP configuration, and inspecting queue/history.
Template rendering and formatting helpers live in routers.email_helpers.
"""

import logging
import os
import smtplib
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr, Field

from routers.email_helpers import (
    JINJA2_AVAILABLE,
    format_analysis_metrics,
    format_analysis_summary,
    render_html_template,
)
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()


# Request Models
class SendEmailRequest(BaseModel):
    to_email: EmailStr = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body (plain text or HTML)")
    attachments: Optional[List[str]] = Field(None, description="File paths to attach")
    html: bool = Field(False, description="Whether body is HTML (default: False)")
    retry_count: int = Field(3, description="Number of retry attempts (default: 3)")
    background: bool = Field(False, description="Send in background (default: False)")


class SendTemplateEmailRequest(BaseModel):
    to_email: EmailStr = Field(..., description="Recipient email address")
    template: str = Field(
        ..., description="Template name: 'analysis_report', 'alert', 'summary'"
    )
    data: dict = Field(..., description="Template data/variables")
    attachments: Optional[List[str]] = Field(None, description="File paths to attach")
    background: bool = Field(False, description="Send in background (default: False)")


class AnalyticsEmailRequest(BaseModel):
    """Request for auto-emailing analytics results."""

    to_email: EmailStr = Field(..., description="Recipient email address")
    analysis_type: str = Field(..., description="Analysis type (roi, runrate, etc.)")
    result_data: dict = Field(..., description="Analysis result data")
    output_files: Optional[Dict[str, str]] = Field(
        None, description="Output file paths"
    )


# Import email sender from shared module to avoid circular imports
from services.infrastructure.email.sender import send_email_with_retry  # noqa: E402


def background_send_email(email_data: dict):
    """Background task to send email."""
    try:
        result = send_email_with_retry(**email_data)
        logger.info("Background email result: %s", result["status"])
    except Exception as e:
        logger.error("Background email error: %s", e, exc_info=True)


@router.get("/", summary="Email Service Info")
async def email_info():
    """Get information about the email service."""
    smtp_configured = bool(os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"))

    return {
        "service": "Email Service",
        "description": "Production-grade email with retry logic and HTML templates",
        "features": {
            "smtp_configured": smtp_configured,
            "retry_logic": "3 attempts with exponential backoff",
            "html_templates": "Jinja2" if JINJA2_AVAILABLE else "Plain text only",
            "background_queue": "Async background tasks",
            "attachments": "Excel, HTML, PDF, etc.",
            "auto_email_analytics": "Integrated with analytics",
        },
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "from_email": os.getenv("EMAIL_FROM", "noreply@company.com"),
    }


@router.post("/send", summary="Send Email")
async def send_email(request: SendEmailRequest, background_tasks: BackgroundTasks):
    """
    Send an email with retry logic and optional background processing.

    Features:
    - Automatic retry with exponential backoff (3 attempts)
    - Background sending option (non-blocking)
    - HTML and plain text support
    - File attachments
    """
    try:
        email_data = {
            "to_email": request.to_email,
            "subject": request.subject,
            "body": request.body,
            "html": request.html,
            "attachments": request.attachments,
            "retry_count": request.retry_count,
        }

        if request.background:
            # Add to persistent queue (survives server restarts)
            from services.infrastructure.email.queue_processor import add_email_to_queue

            email_id = add_email_to_queue(
                to_email=request.to_email,
                subject=request.subject,
                body=request.body,
                html=request.html,
                attachments=request.attachments,
                priority=5,  # Default priority
                extra_metadata={"source": "api", "retry_count": request.retry_count},
            )

            return {
                "status": "queued",
                "message": f"Email queued for persistent background sending to {request.to_email}",
                "recipient": request.to_email,
                "email_id": email_id,
            }
        else:
            # Send immediately
            result = send_email_with_retry(**email_data)

            if result["status"] == "error":
                raise HTTPException(status_code=500, detail=result["error"])

            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Email send error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(
            e, "Email operation failed. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/send-template", summary="Send Templated Email")
async def send_template_email(
    request: SendTemplateEmailRequest, background_tasks: BackgroundTasks
):
    """
    Send an email using HTML or plain text templates.

    Templates: analysis_report, alert, summary
    """
    try:
        # Render template
        body = render_html_template(request.template, request.data)
        is_html = JINJA2_AVAILABLE  # HTML if Jinja2 available

        # Generate subject
        if request.template == "analysis_report":
            subject = f"{request.data.get('analysis_type', 'Analysis')} Report - {datetime.now().strftime('%Y-%m-%d')}"
        elif request.template == "alert":
            subject = f"Alert: {request.data.get('alert_title', 'System Alert')}"
        elif request.template == "summary":
            subject = f"{request.data.get('period', 'Weekly')} Summary - {datetime.now().strftime('%Y-%m-%d')}"
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown template: {request.template}"
            )

        # Send email
        email_request = SendEmailRequest(
            to_email=request.to_email,
            subject=subject,
            body=body,
            attachments=request.attachments,
            html=is_html,
            background=request.background,
        )

        return await send_email(email_request, background_tasks)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Template email error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(
            e, "Email operation failed. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/analytics-result", summary="Auto-Email Analytics Result")
async def email_analytics_result(
    request: AnalyticsEmailRequest, background_tasks: BackgroundTasks
):
    """
    Automatically email analytics results with attachments.

    This endpoint is called by analytics tools to auto-email results.
    """
    try:
        # Prepare template data
        template_data = {
            "analysis_type": request.analysis_type.upper(),
            "date_range": request.result_data.get("date_range", "N/A"),
            "summary": format_analysis_summary(request.result_data),
            "metrics": format_analysis_metrics(request.result_data),
            "insights": "See attached reports for detailed insights.",
        }

        # Get attachment files
        attachments = []
        if request.output_files:
            attachments = list(request.output_files.values())

        # Add to persistent queue (always background for analytics emails)
        from services.infrastructure.email.queue_processor import add_email_to_queue

        # Render template
        body = render_html_template("analysis_report", template_data)
        is_html = JINJA2_AVAILABLE

        # Generate subject
        subject = f"{request.analysis_type.upper()} Report - {datetime.now().strftime('%Y-%m-%d')}"

        email_id = add_email_to_queue(
            to_email=request.to_email,
            subject=subject,
            body=body,
            html=is_html,
            attachments=attachments,
            priority=7,  # Higher priority for analytics emails
            extra_metadata={
                "source": "analytics",
                "analysis_type": request.analysis_type,
                "date_range": request.result_data.get("date_range", "N/A"),
            },
        )

        return {
            "status": "queued",
            "message": f"Analytics email queued for persistent background sending to {request.to_email}",
            "recipient": request.to_email,
            "email_id": email_id,
        }

    except Exception as e:
        logger.error("Analytics email error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(
            e, "Email operation failed. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/validate-config", summary="Validate Email Configuration")
async def validate_email_config():
    """Test SMTP connection without sending an email."""
    try:
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_username = os.getenv("SMTP_USERNAME")
        smtp_password = os.getenv("SMTP_PASSWORD")
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

        if not smtp_username or not smtp_password:
            return {
                "status": "error",
                "valid": False,
                "message": "SMTP credentials not configured",
            }

        # Test connection
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.quit()

        return {
            "status": "success",
            "valid": True,
            "message": "Email configuration is valid",
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "from_email": os.getenv("EMAIL_FROM", "noreply@company.com"),
            "features": {
                "retry_enabled": True,
                "html_templates": JINJA2_AVAILABLE,
                "background_queue": True,
            },
        }

    except smtplib.SMTPAuthenticationError:
        return {
            "status": "error",
            "valid": False,
            "message": "SMTP authentication failed. Check credentials.",
        }
    except Exception as e:
        return {
            "status": "error",
            "valid": False,
            "message": f"Connection failed: {str(e)}",
        }


@router.get("/queue", summary="Get Email Queue Status")
async def get_email_queue():
    """Get current email queue status and pending emails."""
    try:
        from models.database import get_session
        from models.email import EmailQueue

        with get_session() as session:
            pending_count = (
                session.query(EmailQueue).filter(EmailQueue.status == "pending").count()
            )
            processing_count = (
                session.query(EmailQueue)
                .filter(EmailQueue.status == "processing")
                .count()
            )
            failed_count = (
                session.query(EmailQueue).filter(EmailQueue.status == "failed").count()
            )

            # Get recent pending emails
            recent_pending = (
                session.query(EmailQueue)
                .filter(EmailQueue.status == "pending")
                .order_by(EmailQueue.priority.desc(), EmailQueue.created_at.asc())
                .limit(10)
                .all()
            )

        return {
            "status": "success",
            "queue_stats": {
                "pending": pending_count,
                "processing": processing_count,
                "failed": failed_count,
            },
            "recent_pending": [email.to_dict() for email in recent_pending],
        }
    except Exception as e:
        logger.error("Error getting email queue: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", summary="Get Email History")
async def get_email_history(limit: int = 50, to_email: Optional[str] = None):
    """Get email delivery history."""
    try:
        from models.database import get_session
        from models.email import EmailHistory

        with get_session() as session:
            query = session.query(EmailHistory)

            if to_email:
                query = query.filter(EmailHistory.to_email == to_email)

            history = query.order_by(EmailHistory.sent_at.desc()).limit(limit).all()

        return {
            "status": "success",
            "count": len(history),
            "history": [email.to_dict() for email in history],
        }
    except Exception as e:
        logger.error("Error getting email history: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
