from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright
import os
import csv
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.units import inch
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional
import ddddocr as ocr_lib
from loguru import logger

app = FastAPI(title="India Post RD Account Automation API")


class GenerateReportRequest(BaseModel):
    user_id: str
    password: str
    headless: bool = True


class Credentials(BaseModel):
    user_id: str
    password: str
    captcha: Optional[str] = None


class ScrapeRequest(BaseModel):
    credentials: Credentials
    headless: bool = True


async def scrape_rd_table(page, csv_file):
    """Scrape RD account data from the web page"""
    all_accounts = []
    page_count = 1
    serial_number = 1

    # Get current month and next two months (first 3 chars in uppercase)
    current_date = datetime.now()
    month1 = current_date.strftime("%B")[:3].upper()
    month2 = (current_date + relativedelta(months=1)).strftime("%B")[:3].upper()
    month3 = (current_date + relativedelta(months=2)).strftime("%B")[:3].upper()

    while True:
        print(f"Scraping Page {page_count}...")

        # 1. Wait for the table to be visible
        await page.wait_for_selector("#SummaryList")

        # 2. Select all data rows
        rows = await page.locator("#SummaryList tr[id]").all()

        for row in rows:
            cells = await row.locator("td").all()
            if len(cells) >= 4:
                account_info = {
                    "Sl.No": serial_number,
                    "Account No": (await cells[1].inner_text()).strip(),
                    "Account Name": (await cells[2].inner_text()).strip(),
                    "Amount": (await cells[3].inner_text())
                    .strip()
                    .replace(",", "")
                    .replace(".00", "")
                    .replace(" Cr.", ""),
                    month1: "",
                    month2: "",
                    month3: "",
                }
                all_accounts.append(account_info)
                serial_number += 1

        # 3. Check if 'Next' button is available and enabled
        next_button = page.locator("#Action\.AgentRDActSummaryAllListing\.GOTO_NEXT__")

        if await next_button.count() == 0 or await next_button.is_disabled():
            print("Reached the last page.")
            break

        # 4. Click Next and wait for the new table to load
        await next_button.click()
        await page.wait_for_load_state("networkidle")
        page_count += 1

    # 5. Save all collected data to CSV
    keys = [
        "Sl.No",
        "Account No",
        "Account Name",
        "Amount",
        month1,
        month2,
        month3,
    ]

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(all_accounts)

    print(f"Extraction Complete! Total accounts saved: {len(all_accounts)}")
    return csv_file, len(all_accounts)


def pdf_generator(csv_file, pdf_file=None):
    """Convert CSV file to a structured PDF table"""
    if pdf_file is None:
        pdf_file = csv_file.replace(".csv", ".pdf")

    try:
        # Read the CSV file and keep empty strings (don't convert to NaN)
        df = pd.read_csv(csv_file, keep_default_na=False)

        if df.empty:
            print("CSV file is empty. No PDF generated.")
            return None

        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_file,
            pagesize=A4,
            rightMargin=10,
            leftMargin=10,
            topMargin=10,
            bottomMargin=10,
        )

        elements = []
        header = df.columns.tolist()
        rows = df.values.tolist()
        num_columns = len(header)

        # Build data with page number rows after every 10 data rows
        data = [header]
        page_num = 2
        page_number_rows = []

        for i, row in enumerate(rows):
            data.append(row)
            if (i + 1) % 10 == 0 and (i + 1) < len(rows):
                page_row = [f"Page {page_num}"] + [""] * (num_columns - 1)
                data.append(page_row)
                page_number_rows.append(len(data) - 1)
                page_num += 1

        # Define column widths
        col_widths = [
            0.6 * inch,  # Sl.No
            1.2 * inch,  # Account No
            2.5 * inch,  # Account Name
            0.8 * inch,  # Amount
            0.8 * inch,  # Month 1
            0.8 * inch,  # Month 2
            0.8 * inch,  # Month 3
        ]
        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Build style commands list
        style_commands = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 11),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ]

        # Add styling for page number rows
        for row_idx in page_number_rows:
            style_commands.append(("SPAN", (0, row_idx), (-1, row_idx)))
            style_commands.append(("ALIGN", (0, row_idx), (-1, row_idx), "CENTER"))
            style_commands.append(
                ("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Oblique")
            )
            style_commands.append(("FONTSIZE", (0, row_idx), (-1, row_idx), 11))
            style_commands.append(
                ("TEXTCOLOR", (0, row_idx), (-1, row_idx), colors.grey)
            )

        table.setStyle(TableStyle(style_commands))
        elements.append(table)

        # Build PDF
        doc.build(elements)
        print(f"PDF successfully generated: {pdf_file}")
        return pdf_file

    except FileNotFoundError:
        print(f"Error: CSV file '{csv_file}' not found.")
        return None
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        return None


@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "India Post RD Account Automation API",
        "version": "2.0.0",
        "endpoint": {
            "POST /generate-report": "Generate RD account report with CAPTCHA handling"
        },
        "usage": {
            "step_1": "Call POST /generate-report with user_id and password",
            "step_2": "API returns CAPTCHA image in base64",
            "step_3": "Call POST /generate-report again with user_id, password, and captcha code",
            "step_4": "API returns PDF report",
        },
    }


@app.get("/generate-report")
async def generate_report():
    """
    Generate RD account report with automatic CAPTCHA solving.

    Returns PDF report directly.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    captcha_file = f"captcha_{timestamp}.png"
    logger.info(f"Generated file names - CAPTCHA: {captcha_file}")
    csv_file = f"rd_deposit_list_{timestamp}.csv"
    logger.info(f"Generated file names - CSV: {csv_file}")
    pdf_file = f"rd_deposit_list_{timestamp}.pdf"
    logger.info(f"Generated file names - PDF: {pdf_file}")

    try:
        async with async_playwright() as p:
            logger.info("Launching browser...")
            browser = await p.chromium.launch(headless=True, channel="chrome")
            context = await browser.new_context()
            page = await context.new_page()

            url = "https://dopagent.indiapost.gov.in/corp/AuthenticationController?FORMSGROUP_ID__=AuthenticationFG&__START_TRAN_FLAG__=Y&__FG_BUTTONS__=LOAD&ACTION.LOAD=Y&AuthenticationFG.LOGIN_FLAG=3&BANK_ID=DOP&AGENT_FLAG=Y"

            await page.goto(url)

            captcha_element = await page.wait_for_selector("#IMAGECAPTCHA")
            await captcha_element.screenshot(path=captcha_file)
            logger.info(f"CAPTCHA image saved: {captcha_file}")

            # Solve CAPTCHA using OCR
            ocr = ocr_lib.DdddOcr(show_ad=False)
            with open(captcha_file, "rb") as f:
                img_bytes = f.read()
                captcha_code = ocr.classification(img_bytes)
                logger.info(f"Decoded CAPTCHA code: {captcha_code}")

            # Fill credentials from environment variables
            user_id = os.getenv("INDIA_POST_USER")
            logger.info(f"Using user ID: {user_id}")
            password = os.getenv("INDIA_POST_PASS")
            logger.info("Using password from environment variables")

            if not user_id or not password:
                await browser.close()
                raise HTTPException(
                    status_code=400,
                    detail="Environment variables INDIA_POST_USER and INDIA_POST_PASS must be set",
                )

            await page.fill("input[name='AuthenticationFG.USER_PRINCIPAL']", user_id)
            await page.fill("input[name='AuthenticationFG.ACCESS_CODE']", password)
            await page.fill(
                "input[name='AuthenticationFG.VERIFICATION_CODE']", captcha_code
            )

            # Submit
            await page.click(
                "input[name='Action.VALIDATE_RM_PLUS_CREDENTIALS_CATCHA_DISABLED']"
            )
            await page.wait_for_load_state("networkidle")

            page_content = await page.content()
            if "Welcome" not in page_content and "Dashboard" not in page_content:
                await browser.close()
                # Clean up files
                for f in [captcha_file, csv_file, pdf_file]:
                    if os.path.exists(f):
                        os.remove(f)
                raise HTTPException(
                    status_code=401,
                    detail="Login failed - check credentials or CAPTCHA",
                )

            # Navigate to RD Account List page
            await page.get_by_role("link", name="Accounts").click()
            await page.get_by_role("link", name="Agent Enquire & Update Screen").click()

            # Scrape the RD table
            csv_file, total_records = await scrape_rd_table(page, csv_file)

            # Generate PDF
            pdf_file = pdf_generator(csv_file, pdf_file)

            await browser.close()

            # Clean up CAPTCHA and CSV files
            if os.path.exists(captcha_file):
                os.remove(captcha_file)
            if os.path.exists(csv_file):
                os.remove(csv_file)

            if not pdf_file or not os.path.exists(pdf_file):
                raise HTTPException(status_code=500, detail="Failed to generate PDF")

            # Return PDF file
            return FileResponse(
                pdf_file,
                media_type="application/pdf",
                filename=f"rd_deposit_report_{timestamp}.pdf",
                background=None,
            )

    except HTTPException:
        raise
    except Exception as e:
        # Clean up files on error
        for f in [captcha_file, csv_file, pdf_file]:
            if os.path.exists(f):
                os.remove(f)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
