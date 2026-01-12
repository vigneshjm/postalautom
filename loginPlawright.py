from playwright.sync_api import sync_playwright
import time
import os

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
        page.fill("input[name='AuthenticationFG.USER_PRINCIPAL']", os.getenv("INDIA_POST_USER"))
        page.fill("input[name='AuthenticationFG.ACCESS_CODE']", os.getenv("INDIA_POST_PASS"))

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
            # Add your data extraction logic here
        else:
            print("Login failed - check if session expired or captcha was wrong.")
        
        # Keep alive for a bit to see the result
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    login_with_local_captcha()