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


def scrape_rd_table(page):
    all_accounts = []
    page_count = 1

    while True:
        print(f"Scraping Page {page_count}...")

        # 1. Wait for the table to be visible
        page.wait_for_selector("#SummaryList")

        # 2. Select all data rows (skipping headers and spacers)
        # We target rows that have IDs (0, 1, 2...) as seen in your HTML
        rows = page.locator("#SummaryList tr[id]").all()

        for row in rows:
            # Extract specific columns by index
            # Index 1: Account No, 2: Name, 3: Amount, 4: Paid Upto, 5: Due Date
            cells = row.locator("td").all()
            if len(cells) >= 6:
                account_info = {
                    "Account No": cells[1].inner_text().strip(),
                    "Account Name": cells[2].inner_text().strip(),
                    "Denomination": cells[3].inner_text().strip(),
                    "Month Paid Upto": cells[4].inner_text().strip(),
                    "Next Due Date": cells[5].inner_text().strip(),
                }
                all_accounts.append(account_info)

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
    keys = all_accounts[0].keys()
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
        captcha_code = input("Open 'captcha.png' and enter the code here: ")
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
        # Read the CSV file
        df = pd.read_csv(csv_file)

        if df.empty:
            print("CSV file is empty. No PDF generated.")
            return

        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_file,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=18,
        )

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()

        # Add title
        title = Paragraph(
            f"<b>RD Deposit Account List</b><br/><font size=10>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>",
            styles["Title"],
        )
        elements.append(title)
        elements.append(Spacer(1, 12))

        # Prepare table data
        # Convert DataFrame to list of lists
        data = [df.columns.tolist()] + df.values.tolist()

        # Create table
        table = Table(data)

        # Add style to table
        table.setStyle(
            TableStyle(
                [
                    # Header row styling
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    # Data rows styling
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    ("ALIGN", (0, 1), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    # Grid styling
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("BOX", (0, 0), (-1, -1), 2, colors.black),
                    # Alternating row colors for better readability
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.beige, colors.lightgrey],
                    ),
                ]
            )
        )

        elements.append(table)

        # Add footer
        elements.append(Spacer(1, 12))
        footer = Paragraph(
            f"<font size=8>Total Records: {len(df)}</font>", styles["Normal"]
        )
        elements.append(footer)

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
