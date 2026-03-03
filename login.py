import requests
from bs4 import BeautifulSoup
import re
import os

session = requests.Session()

# The Exact Login URL
login_page_url = "https://dopagent.indiapost.gov.in/corp/AuthenticationController?FORMSGROUP_ID__=AuthenticationFG&__START_TRAN_FLAG__=Y&__FG_BUTTONS__=LOAD&ACTION.LOAD=Y&AuthenticationFG.LOGIN_FLAG=3&BANK_ID=DOP&AGENT_FLAG=Y"

# 1. Get the page
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}
resp = session.get(login_page_url, headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')

# 2. Extract EVERY input field from the form
# This ensures we don't miss any dynamic tokens
form_inputs = soup.find_all('input')
login_data = {}
for inp in form_inputs:
    if inp.get('name'):
        login_data[inp.get('name')] = inp.get('value', '')

# 3. Handle CAPTCHA and JSESSIONID
captcha_tag = soup.find('img', id='IMAGECAPTCHA')
captcha_src = captcha_tag['src']
jsid = re.search(r'jsessionid=([^?]+)', captcha_src).group(1)

# Download image
captcha_url = "https://dopagent.indiapost.gov.in/corp/" + captcha_src
img_resp = session.get(captcha_url, headers={'Referer': login_page_url})
with open('captcha.png', 'wb') as f:
    f.write(img_resp.content)

captcha_code = input("Enter CAPTCHA: ")

# 4. Fill in the specific login credentials
login_data['AuthenticationFG.USER_PRINCIPAL_ID'] = os.getenv("INDIA_POST_USER")
login_data['AuthenticationFG.ACCESS_CODE'] = os.getenv("INDIA_POST_PASS")
login_data['AuthenticationFG.VERIFICATION_CODE'] = captcha_code
login_data['VALIDATE_CREDENTIALS'] = 'Login'

# 5. The Final POST
# Important: Use the jsessionid in the URL AND the referer header
post_url = f"https://dopagent.indiapost.gov.in/corp/AuthenticationController;jsessionid={jsid}"
post_headers = headers.copy()
post_headers['Referer'] = login_page_url
post_headers['Origin'] = 'https://dopagent.indiapost.gov.in'
post_headers['Content-Type'] = 'application/x-www-form-urlencoded'

final_resp = session.post(post_url, data=login_data, headers=post_headers)
print(final_resp.text)

print(f"Status Code: {final_resp.status_code}")
if "Expired" in final_resp.text:
    print("FAILED: Still getting Session Expired.")
else:
    print("SUCCESS: Check your response content!")