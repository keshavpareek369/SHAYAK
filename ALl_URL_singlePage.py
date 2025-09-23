from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)

driver.get("https://www.myscheme.gov.in/search")
html = driver.page_source
soup = BeautifulSoup(html, "html.parser")

h2_tags = soup.find_all("h2", id=re.compile(r"^scheme-name-\d+$"))
urls = []
for h2 in h2_tags:
    a = h2.find("a", href=True)
    if a:
        url = urljoin("https://www.myscheme.gov.in", a["href"])
        urls.append((a.get_text(strip=True), url))

for name, u in urls:
    print(name, "→", u)

driver.quit()
