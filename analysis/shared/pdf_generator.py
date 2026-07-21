"""
Shared PDF Generation Utilities.

Provides common PDF generation functionality for all analysis modules:
- HTML to PDF conversion
- Report styling and templates
- Header/footer generation
- Multi-page support

Author: Utku Gulbardak
Date: 2025-10-30
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    WEASYPRINT_AVAILABLE = False
    logger.warning(
        f"⚠️ WeasyPrint unavailable (missing libraries). PDF generation disabled. Error: {str(e)[:100]}"
    )


class PDFGenerator:
    """
    Shared PDF generator for manufacturing analytics reports.

    Features:
    - HTML to PDF conversion with CSS styling
    - Professional report headers and footers
    - Page numbering
    - Multi-page support
    - Embedded images and charts
    """

    def __init__(self):
        """Initialize PDF generator with font configuration."""
        self.font_config = FontConfiguration() if WEASYPRINT_AVAILABLE else None

    def html_to_pdf(
        self,
        html_path: str,
        output_pdf_path: str,
        add_page_numbers: bool = True,
        add_header: bool = True,
        custom_css: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert HTML file to PDF.

        Args:
            html_path: Path to input HTML file
            output_pdf_path: Path for output PDF file
            add_page_numbers: Add page numbers to footer
            add_header: Add report header
            custom_css: Additional CSS styling

        Returns:
            dict: {
                "status": "success" | "error",
                "pdf_path": str,
                "file_size_mb": float,
                "pages": int
            }
        """
        if not WEASYPRINT_AVAILABLE:
            return {
                "status": "error",
                "error": "WeasyPrint not installed. Run: pip install weasyprint",
            }

        try:
            html_path_obj = Path(html_path)
            if not html_path_obj.exists():
                return {"status": "error", "error": f"HTML file not found: {html_path}"}

            # Read HTML content
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Add page styling CSS
            pdf_css = self._get_pdf_css(add_page_numbers, add_header)
            if custom_css:
                pdf_css += f"\n{custom_css}"

            # Generate PDF
            html_doc = HTML(string=html_content, base_url=str(html_path_obj.parent))
            css_doc = CSS(string=pdf_css, font_config=self.font_config)

            html_doc.write_pdf(
                output_pdf_path, stylesheets=[css_doc], font_config=self.font_config
            )

            # Get file info
            pdf_path_obj = Path(output_pdf_path)
            file_size_mb = pdf_path_obj.stat().st_size / (1024 * 1024)

            logger.info(
                f"✅ PDF generated: {pdf_path_obj.name} ({file_size_mb:.2f} MB)"
            )

            return {
                "status": "success",
                "pdf_path": output_pdf_path,
                "file_size_mb": round(file_size_mb, 2),
                "message": f"PDF generated successfully: {pdf_path_obj.name}",
            }

        except Exception as e:
            logger.error(f"❌ PDF generation failed: {str(e)}")
            return {"status": "error", "error": f"PDF generation failed: {str(e)}"}

    def create_pdf_from_data(
        self,
        title: str,
        content_html: str,
        output_pdf_path: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create PDF from HTML content string (not file).

        Args:
            title: Report title
            content_html: HTML content as string
            output_pdf_path: Output PDF path
            metadata: Report metadata (equipment, date range, etc.)

        Returns:
            dict: Same as html_to_pdf
        """
        if not WEASYPRINT_AVAILABLE:
            return {"status": "error", "error": "WeasyPrint not installed"}

        try:
            # Build complete HTML document
            html_doc = self._build_html_document(title, content_html, metadata)

            # Generate PDF
            html_obj = HTML(string=html_doc)
            css_obj = CSS(string=self._get_pdf_css(), font_config=self.font_config)

            html_obj.write_pdf(
                output_pdf_path, stylesheets=[css_obj], font_config=self.font_config
            )

            # Get file info
            pdf_path_obj = Path(output_pdf_path)
            file_size_mb = pdf_path_obj.stat().st_size / (1024 * 1024)

            logger.info(f"✅ PDF created: {pdf_path_obj.name} ({file_size_mb:.2f} MB)")

            return {
                "status": "success",
                "pdf_path": output_pdf_path,
                "file_size_mb": round(file_size_mb, 2),
                "message": f"PDF created: {pdf_path_obj.name}",
            }

        except Exception as e:
            logger.error(f"❌ PDF creation failed: {str(e)}")
            return {"status": "error", "error": f"PDF creation failed: {str(e)}"}

    def _build_html_document(
        self, title: str, content: str, metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """Build complete HTML document with header and styling."""
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        meta_section = ""
        if metadata:
            meta_items = [
                f"<p><strong>{k}:</strong> {v}</p>" for k, v in metadata.items()
            ]
            meta_section = f"""
            <div class="metadata">
                {"".join(meta_items)}
            </div>
            """

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            margin: 40px;
            color: #333;
            line-height: 1.6;
        }}
        .header {{
            border-bottom: 3px solid #1f4e79;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            color: #1f4e79;
            font-size: 28px;
        }}
        .header .date {{
            color: #666;
            font-size: 14px;
            margin-top: 5px;
        }}
        .metadata {{
            background: #f7f9fb;
            border-left: 4px solid #1f4e79;
            padding: 15px;
            margin-bottom: 30px;
        }}
        .metadata p {{
            margin: 5px 0;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #1f4e79;
            color: white;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <div class="date">Generated: {current_date}</div>
    </div>
    {meta_section}
    <div class="content">
        {content}
    </div>
</body>
</html>
"""

    def _get_pdf_css(
        self, add_page_numbers: bool = True, add_header: bool = True
    ) -> str:
        """Get CSS for PDF styling with page numbers and headers."""
        css = """
        @page {
            size: A4;
            margin: 2.5cm 2cm 3cm 2cm;
        """

        if add_page_numbers:
            css += """
            @bottom-right {
                content: "Page " counter(page) " of " counter(pages);
                font-size: 10px;
                color: #666;
            }
            """

        if add_header:
            css += """
            @top-left {
                content: "Manufacturing Analytics Report";
                font-size: 10px;
                color: #666;
            }
            @top-right {
                content: string(report-title);
                font-size: 10px;
                color: #666;
            }
            """

        css += """
        }
        
        /* Page break control */
        table {
            page-break-inside: avoid;
        }
        
        h1, h2, h3 {
            page-break-after: avoid;
        }
        
        /* Print optimization */
        @media print {
            body {
                print-color-adjust: exact;
                -webkit-print-color-adjust: exact;
            }
        }
        """

        return css


# Singleton instance
_pdf_generator = None


def get_pdf_generator() -> PDFGenerator:
    """Get singleton PDF generator instance."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFGenerator()
    return _pdf_generator
