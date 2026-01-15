from playwright.sync_api import sync_playwright
import time
import os
import csv

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
                    "Next Due Date": cells[5].inner_text().strip()
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
    with open('rd_deposit_list.csv', 'w', newline='', encoding='utf-8') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(all_accounts)
    
    print(f"Extraction Complete! Total accounts saved: {len(all_accounts)}")

def login_with_local_captcha():
    with sync_playwright() as p:
        # Launch using your existing Chrome to avoid crashes
        browser = p.chromium.launch(headless=False, channel="chrome")
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
        page.fill("input[name='AuthenticationFG.USER_PRINCIPAL']", os.getenv("INDIA_POST_USER", "DOP.MIG0017258"))
        page.fill("input[name='AuthenticationFG.ACCESS_CODE']", os.getenv("INDIA_POST_PASS", "BaskaranJamuna@73"))

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

        else:
            print("Login failed - check if session expired or captcha was wrong.")
        
        # Keep alive for a bit to see the result
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    login_with_local_captcha()