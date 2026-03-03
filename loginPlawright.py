from playwright.sync_api import sync_playwright
import time
import os
import csv
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from datetime import datetime
from dateutil.relativedelta import relativedelta
import ddddocr as ocr_lib


def scrape_rd_table(page):
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
        page.wait_for_selector("#SummaryList")

        # 2. Select all data rows (skipping headers and spacers)
        # We target rows that have IDs (0, 1, 2...) as seen in your HTML
        rows = page.locator("#SummaryList tr[id]").all()

        for row in rows:
            # Extract specific columns by index
            # Index 1: Account No, 2: Name, 3: Amount
            cells = row.locator("td").all()
            if len(cells) >= 4:
                account_info = {
                    "Sl.No": serial_number,
                    "Account No": cells[1].inner_text().strip(),
                    "Account Name": cells[2].inner_text().strip(),
                    "Amount": cells[3]
                    .inner_text()
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

        # If button doesn't exist or is disabled, we've reached the end
        if next_button.count() == 0 or next_button.is_disabled():
            print("Reached the last page.")
            break

        # 4. Click Next and wait for the new table to load
        next_button.click()
        page.wait_for_load_state("networkidle")
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
    with open("rd_deposit_list.csv", "w", newline="", encoding="utf-8") as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(all_accounts)

    print(f"Extraction Complete! Total accounts saved: {len(all_accounts)}")


def login_with_local_captcha():
    with sync_playwright() as p:
        # Launch using your existing Chrome to avoid crashes
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context()
        page = context.new_page()

        url = "https://dopagent.indiapost.gov.in/corp/AuthenticationController?FORMSGROUP_ID__=AuthenticationFG&__START_TRAN_FLAG__=Y&__FG_BUTTONS__=LOAD&ACTION.LOAD=Y&AuthenticationFG.LOGIN_FLAG=3&BANK_ID=DOP&AGENT_FLAG=Y"

        print("Opening India Post Portal...")
        page.goto(url)

        # 1. Wait for the CAPTCHA image to load
        # The ID from your previous HTML was 'IMAGECAPTCHA'
        captcha_element = page.wait_for_selector("#IMAGECAPTCHA")

        # 2. Take a screenshot of ONLY the captcha element and save locally
        captcha_element.screenshot(path="captcha.png")
        print("CAPTCHA image saved locally as 'captcha.png'")

        ocr = ocr_lib.DdddOcr(show_ad=False)
        with open("captcha.png", "rb") as f:
            img_bytes = f.read()
            captcha_code = ocr.classification(img_bytes)
            print(f"Decoded CAPTCHA code: {captcha_code}")

        # 3. Fill in the credentials
        page.fill(
            "input[name='AuthenticationFG.USER_PRINCIPAL']",
            os.getenv("INDIA_POST_USER", "DOP.MIG0017258"),
        )
        page.fill(
            "input[name='AuthenticationFG.ACCESS_CODE']",
            os.getenv("INDIA_POST_PASS", "BaskaranJamuna@73"),
        )

        # 4. Prompt for input (you can now open the local file to see it)
        # captcha_code = input("Open 'captcha.png' and enter the code here: ")
        page.fill("input[name='AuthenticationFG.VERIFICATION_CODE']", captcha_code)

        # 5. Submit
        print("Submitting...")
        page.click("input[name='Action.VALIDATE_RM_PLUS_CREDENTIALS_CATCHA_DISABLED']")

        # 6. Check for success
        page.wait_for_load_state("networkidle")

        if "Welcome" in page.content() or "Dashboard" in page.content():
            print("Successfully Logged In!")

            # 1. Navigate to the RD Account List page
            # Note: Update the selector based on the actual menu text
            page.get_by_role("link", name="Accounts").click()
            page.get_by_role("link", name="Agent Enquire & Update Screen").click()

            # 2. Now scrape the RD table
            scrape_rd_table(page)

            # 3. Generate PDF from the scraped CSV data
            pdf_generator()

        else:
            print("Login failed - check if session expired or captcha was wrong.")

        # Keep alive for a bit to see the result
        time.sleep(5)
        browser.close()


# function to convert csv file to structured table and save as pdf
def pdf_generator(csv_file="rd_deposit_list.csv", pdf_file="rd_deposit_list.pdf"):
    """
    Converts CSV file to a structured PDF table.

    Args:
        csv_file: Path to the input CSV file
        pdf_file: Path to the output PDF file
    """
    try:
        # Read the CSV file and keep empty strings (don't convert to NaN)
        df = pd.read_csv(csv_file, keep_default_na=False)

        if df.empty:
            print("CSV file is empty. No PDF generated.")
            return

        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_file,
            pagesize=A4,
            rightMargin=10,
            leftMargin=10,
            topMargin=10,
            bottomMargin=10,
        )

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()

        # Prepare table data
        # Convert DataFrame to list of lists
        header = df.columns.tolist()
        rows = df.values.tolist()
        num_columns = len(header)

        # Build data with page number rows after every 10 data rows
        data = [header]
        page_num = 2
        page_number_rows = []  # Track indices of page number rows

        for i, row in enumerate(rows):
            data.append(row)
            # After every 10 rows (but not at the very end), add a page number row
            if (i + 1) % 10 == 0 and (i + 1) < len(rows):
                page_row = [f"Page {page_num}"] + [""] * (num_columns - 1)
                data.append(page_row)
                page_number_rows.append(len(data) - 1)  # Store the index
                page_num += 1

        # Create table with repeatRows=1 to repeat header on each PDF page
        # Define column widths: Sl.No, Account No, Account Name, Amount, Month1, Month2, Month3
        col_widths = [
            0.6 * inch,  # Sl.No - narrow
            1.2 * inch,  # Account No
            2.5 * inch,  # Account Name - wider for names
            0.8 * inch,  # Amount
            0.8 * inch,  # Month 1 - wider for manual entry
            0.8 * inch,  # Month 2 - wider for manual entry
            0.8 * inch,  # Month 3 - wider for manual entry
        ]
        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Build style commands list
        style_commands = [
            # Header row styling
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            # Data rows styling
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 11),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            # Grid styling
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ]

        # Add styling for page number rows
        for row_idx in page_number_rows:
            # Merge cells in page number rows
            style_commands.append(("SPAN", (0, row_idx), (-1, row_idx)))
            # Center align and make italic
            style_commands.append(("ALIGN", (0, row_idx), (-1, row_idx), "CENTER"))
            style_commands.append(
                ("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Oblique")
            )
            style_commands.append(("FONTSIZE", (0, row_idx), (-1, row_idx), 11))
            style_commands.append(
                ("TEXTCOLOR", (0, row_idx), (-1, row_idx), colors.grey)
            )

        # Add style to table
        table.setStyle(TableStyle(style_commands))

        elements.append(table)

        # Add footer
        elements.append(Spacer(1, 12))

        # Build PDF
        doc.build(elements)
        print(f"PDF successfully generated: {pdf_file}")
        print(f"Total records: {len(df)}")

    except FileNotFoundError:
        print(f"Error: CSV file '{csv_file}' not found.")
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")


if __name__ == "__main__":
    login_with_local_captcha()
