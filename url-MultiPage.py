#  secound part
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time
import csv

def scrape_all_schemes():
    """Scrape all schemes from myscheme.gov.in with numbered pagination"""
    
    # Setup Chrome
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=options)
    
    base_url = "https://www.myscheme.gov.in/search"
    
    try:
        print("🔍 Loading myscheme.gov.in...\n")
        driver.get(base_url)
        
        # Wait for React to load
        wait = WebDriverWait(driver, 20)
        time.sleep(5)  # Initial React load
        
        # Wait for schemes to appear
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//h2[contains(@id, 'scheme-name')]")))
            print("✅ Page loaded successfully!\n")
        except TimeoutException:
            print("⏳ Extended wait for page load...")
            time.sleep(5)
        
        all_urls = []
        seen_urls = set()
        current_page = 1
        max_attempts_no_schemes = 3
        consecutive_no_schemes = 0
        
        while True:
            print(f"{'='*60}")
            print(f"📄 Scraping Page {current_page}")
            print(f"{'='*60}")
            
            # Wait for page content to load
            time.sleep(4)
            
            # Scroll to ensure all content is loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Parse current page
            soup = BeautifulSoup(driver.page_source, "html.parser")
            h2_tags = soup.find_all("h2", id=re.compile(r"^scheme-name-\d+$"))
            
            page_schemes = 0
            for h2 in h2_tags:
                a = h2.find("a", href=True)
                if a:
                    scheme_url = urljoin(base_url, a["href"])
                    scheme_name = a.get_text(strip=True)
                    
                    if scheme_url not in seen_urls:
                        all_urls.append((scheme_name, scheme_url))
                        seen_urls.add(scheme_url)
                        page_schemes += 1
            
            if page_schemes == 0:
                consecutive_no_schemes += 1
                print(f"⚠️  No schemes found on page {current_page} (attempt {consecutive_no_schemes}/{max_attempts_no_schemes})")
                
                if consecutive_no_schemes >= max_attempts_no_schemes:
                    print(f"❌ No schemes found after {max_attempts_no_schemes} consecutive pages. Stopping.")
                    break
            else:
                consecutive_no_schemes = 0
                print(f"✅ Found {page_schemes} schemes on page {current_page}")
                print(f"📊 Total schemes collected: {len(all_urls)}\n")
            
            # Scroll to bottom where pagination is
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Find the current active page (with bg-green-700)
            try:
                current_page_element = driver.find_element(
                    By.XPATH, 
                    "//li[contains(@class, 'bg-green-700')]/text()"
                )
                detected_page = current_page_element.text.strip()
                print(f"📍 Detected current page: {detected_page}")
            except:
                pass
            
            # Try to find and click next page
            next_button_found = False
            
            # Strategy 1: Find all page number buttons and click the one after current
            try:
                # Find all li elements with page numbers
                page_buttons = driver.find_elements(
                    By.XPATH,
                    "//ul[contains(@class, 'list-none')]//li[contains(@class, 'h-8 w-8')]"
                )
                
                for i, btn in enumerate(page_buttons):
                    try:
                        btn_text = btn.text.strip()
                        
                        # Skip empty or non-numeric buttons
                        if not btn_text or not btn_text.isdigit():
                            continue
                        
                        btn_page_num = int(btn_text)
                        
                        # Look for the next page number
                        if btn_page_num == current_page + 1:
                            # Check if it's not the active page (not green)
                            btn_classes = btn.get_attribute("class") or ""
                            
                            if "bg-green-700" not in btn_classes:
                                # Scroll to button
                                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                                time.sleep(1)
                                
                                # Click the button
                                try:
                                    btn.click()
                                    print(f"🔄 Clicked page number {btn_page_num}")
                                except:
                                    driver.execute_script("arguments[0].click();", btn)
                                    print(f"🔄 Clicked page number {btn_page_num} (JS)")
                                
                                next_button_found = True
                                current_page += 1
                                time.sleep(5)  # Wait for new page to load
                                break
                    except (StaleElementReferenceException, ValueError):
                        continue
                    except Exception as e:
                        continue
                
            except Exception as e:
                print(f"⚠️  Error finding page buttons: {e}")
            
            # Strategy 2: Look for right arrow (›) or next button
            if not next_button_found:
                try:
                    # Find SVG arrows or next buttons
                    next_selectors = [
                        "//li[contains(@class, 'h-8 w-8')]//svg[contains(@class, 'ml-2')]",  # Right arrow
                        "//li[last()]//svg",  # Last SVG in pagination
                        "//button[contains(., '›')]",
                        "//li[contains(@class, 'cursor-pointer') and not(contains(@class, 'bg-green-700'))]//svg[contains(@class, 'ml-2')]"
                    ]
                    
                    for selector in next_selectors:
                        try:
                            elements = driver.find_elements(By.XPATH, selector)
                            
                            for elem in elements:
                                if elem.is_displayed():
                                    # Get parent li element
                                    parent = elem.find_element(By.XPATH, "./ancestor::li[1]")
                                    parent_classes = parent.get_attribute("class") or ""
                                    
                                    # Skip if it's the current page or has disabled styles
                                    if "bg-green-700" in parent_classes or "text-white" in parent_classes:
                                        continue
                                    
                                    # Scroll and click
                                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", parent)
                                    time.sleep(1)
                                    
                                    try:
                                        parent.click()
                                        print(f"🔄 Clicked next arrow → Page {current_page + 1}")
                                    except:
                                        driver.execute_script("arguments[0].click();", parent)
                                        print(f"🔄 Clicked next arrow (JS) → Page {current_page + 1}")
                                    
                                    next_button_found = True
                                    current_page += 1
                                    time.sleep(5)
                                    break
                            
                            if next_button_found:
                                break
                        except:
                            continue
                            
                except Exception as e:
                    pass
            
            # Strategy 3: Try clicking any visible page number greater than current
            if not next_button_found:
                try:
                    page_buttons = driver.find_elements(
                        By.XPATH,
                        "//ul[contains(@class, 'list-none')]//li[contains(@class, 'h-8 w-8') and contains(@class, 'cursor-pointer')]"
                    )
                    
                    for btn in page_buttons:
                        try:
                            btn_text = btn.text.strip()
                            if btn_text.isdigit():
                                btn_num = int(btn_text)
                                btn_classes = btn.get_attribute("class") or ""
                                
                                if btn_num > current_page and "bg-green-700" not in btn_classes:
                                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                                    time.sleep(1)
                                    driver.execute_script("arguments[0].click();", btn)
                                    print(f"🔄 Jumped to page {btn_num}")
                                    next_button_found = True
                                    current_page = btn_num
                                    time.sleep(5)
                                    break
                        except:
                            continue
                except:
                    pass
            
            if not next_button_found:
                print(f"⚡ No more pages found - finished at page {current_page}")
                break
            
            # Safety limit
            if current_page > 500:
                print(f"⚠️  Reached safety limit of 500 pages")
                break
        
        print(f"\n{'='*60}")
        print(f"✅ Scraping completed!")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n❌ Error during scraping: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        driver.quit()
    
    # Save results
    if all_urls:
        with open("schemes.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Scheme Name", "Scheme URL"])
            writer.writerows(all_urls)
        
        print(f"\n📊 Total schemes scraped: {len(all_urls)}")
        print(f"📄 Total pages scraped: {current_page}")
        print(f"📂 Data saved to schemes.csv")
        
        # Display sample
        print(f"\n📋 Sample schemes (first 10):")
        for i, (name, url) in enumerate(all_urls[:10], 1):
            print(f"   {i}. {name[:70]}{'...' if len(name) > 70 else ''}")
        
        if len(all_urls) > 10:
            print(f"\n📋 Last 5 schemes:")
            for i, (name, url) in enumerate(all_urls[-5:], len(all_urls)-4):
                print(f"   {i}. {name[:70]}{'...' if len(name) > 70 else ''}")
            
    else:
        print("\n⚠️  No schemes were scraped.")
    
    return all_urls

if __name__ == "__main__":
    print("="*60)
    print("MyScheme.gov.in Scraper - Numbered Pagination")
    print("="*60)
    schemes = scrape_all_schemes()