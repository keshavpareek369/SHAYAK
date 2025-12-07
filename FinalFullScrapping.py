

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
import csv
import re
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

import time
from datetime import datetime

def run_weekly_scraper(scraper, max_pages=None, max_schemes=None):
    """
    Runs the UnifiedSchemeScraper once every week in a continuous loop.
    scraper = instance of UnifiedSchemeScraper()
    """

    WEEK_SECONDS = 7 * 24 * 60 * 60  # 604800 seconds

    print("==============================================")
    print("📅 WEEKLY SCRAPER STARTED")
    print("It will run automatically every 7 days.")
    print("==============================================\n")

    while True:
        start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n🚀 Running scraper at: {start_time}")
        print("----------------------------------------------------")

        try:
            scraper.run_complete_scrape(
                max_pages=max_pages,
                max_schemes=max_schemes
            )
            print("\n✅ Weekly scrape completed successfully!")

        except Exception as e:
            print(f"\n❌ Error during weekly scraping: {e}")

        print("\n⏳ Sleeping for 7 days...\n")
        time.sleep(WEEK_SECONDS)  # Wait a full week

class UnifiedSchemeScraper:
    def __init__(self):
        self.base_url = "https://www.myscheme.gov.in"
        self.search_url = "https://www.myscheme.gov.in/search"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
    
    def setup_driver(self):
        """Setup Chrome driver with optimal options"""
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"user-agent={self.headers['User-Agent']}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        return webdriver.Chrome(options=options)
    
    def scrape_all_scheme_urls(self, max_pages=None):
        """Phase 1: Scrape all scheme URLs from search pages"""
        driver = self.setup_driver()
        
        try:
            print("=" * 70)
            print("PHASE 1: COLLECTING ALL SCHEME URLs")
            print("=" * 70)
            print(f"\n🔍 Loading {self.search_url}...\n")
            
            driver.get(self.search_url)
            wait = WebDriverWait(driver, 20)
            time.sleep(5)
            
            try:
                wait.until(EC.presence_of_element_located((By.XPATH, "//h2[contains(@id, 'scheme-name')]")))
                print("✅ Search page loaded successfully!\n")
            except TimeoutException:
                print("⏳ Extended wait for page load...")
                time.sleep(5)
            
            all_urls = []
            seen_urls = set()
            current_page = 1
            max_attempts_no_schemes = 3
            consecutive_no_schemes = 0
            
            while True:
                if max_pages and current_page > max_pages:
                    print(f"\n⚠️ Reached maximum page limit: {max_pages}")
                    break
                
                print(f"{'='*70}")
                print(f"📄 Scraping Page {current_page}")
                print(f"{'='*70}")
                
                time.sleep(4)
                
                # Scroll to load content
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
                        scheme_url = urljoin(self.base_url, a["href"])
                        scheme_name = a.get_text(strip=True)
                        
                        if scheme_url not in seen_urls:
                            all_urls.append({
                                'name': scheme_name,
                                'url': scheme_url
                            })
                            seen_urls.add(scheme_url)
                            page_schemes += 1
                
                if page_schemes == 0:
                    consecutive_no_schemes += 1
                    print(f"⚠️ No schemes found on page {current_page} (attempt {consecutive_no_schemes}/{max_attempts_no_schemes})")
                    
                    if consecutive_no_schemes >= max_attempts_no_schemes:
                        print(f"❌ No schemes found after {max_attempts_no_schemes} consecutive pages. Stopping.")
                        break
                else:
                    consecutive_no_schemes = 0
                    print(f"✅ Found {page_schemes} schemes on page {current_page}")
                    print(f"📊 Total schemes collected: {len(all_urls)}\n")
                
                # Navigate to next page
                if not self._go_to_next_page(driver, current_page):
                    print(f"\n⚡ No more pages found - finished at page {current_page}")
                    break
                
                current_page += 1
                
                if current_page > 500:
                    print(f"⚠️ Reached safety limit of 500 pages")
                    break
            
            print(f"\n{'='*70}")
            print(f"✅ Phase 1 completed! Collected {len(all_urls)} scheme URLs")
            print(f"{'='*70}\n")
            
            return all_urls
        
        except Exception as e:
            print(f"\n❌ Error during URL collection: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
        
        finally:
            driver.quit()
    
    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page in pagination"""
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # Strategy 1: Find and click next page number
        try:
            page_buttons = driver.find_elements(
                By.XPATH,
                "//ul[contains(@class, 'list-none')]//li[contains(@class, 'h-8 w-8')]"
            )
            
            for btn in page_buttons:
                try:
                    btn_text = btn.text.strip()
                    if not btn_text or not btn_text.isdigit():
                        continue
                    
                    btn_page_num = int(btn_text)
                    
                    if btn_page_num == current_page + 1:
                        btn_classes = btn.get_attribute("class") or ""
                        
                        if "bg-green-700" not in btn_classes:
                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                            time.sleep(1)
                            
                            try:
                                btn.click()
                            except:
                                driver.execute_script("arguments[0].click();", btn)
                            
                            print(f"🔄 Clicked page number {btn_page_num}")
                            time.sleep(5)
                            return True
                except (StaleElementReferenceException, ValueError):
                    continue
                except Exception:
                    continue
        except Exception:
            pass
        
        # Strategy 2: Look for next arrow
        try:
            next_selectors = [
                "//li[contains(@class, 'h-8 w-8')]//svg[contains(@class, 'ml-2')]",
                "//li[last()]//svg",
            ]
            
            for selector in next_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    
                    for elem in elements:
                        if elem.is_displayed():
                            parent = elem.find_element(By.XPATH, "./ancestor::li[1]")
                            parent_classes = parent.get_attribute("class") or ""
                            
                            if "bg-green-700" in parent_classes:
                                continue
                            
                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", parent)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", parent)
                            print(f"🔄 Clicked next arrow → Page {current_page + 1}")
                            time.sleep(5)
                            return True
                except:
                    continue
        except:
            pass
        
        return False
    
    def scrape_scheme_details(self, scheme_url):
        """Phase 2: Scrape detailed information from a scheme page"""
        driver = self.setup_driver()
        
        try:
            driver.get(scheme_url)
            
            wait = WebDriverWait(driver, 15)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            data = {
                'scheme_name': self.extract_scheme_name(soup),
                'scheme_details': self.extract_scheme_details(soup),
                'eligibility': self.extract_section_by_keyword(soup, ['eligibility', 'eligible', 'who can apply', 'beneficiary']),
                'benefits': self.extract_section_by_keyword(soup, ['benefit', 'benefits', 'assistance', 'financial support', 'amount']),
                'application_process': self.extract_section_by_keyword(soup, ['application', 'how to apply', 'process', 'procedure', 'registration', 'apply']),
                'documents_required': self.extract_section_by_keyword(soup, ['document', 'documents required', 'papers', 'required documents']),
                'contact_info': self.extract_contact_info(soup),
                'all_sections': self.extract_all_sections(soup),
                'metadata': {
                    'scraped_at': datetime.now().isoformat(),
                    'source_url': scheme_url
                }
            }
            
            return data
        
        except Exception as e:
            return {
                'error': str(e),
                'metadata': {
                    'scraped_at': datetime.now().isoformat(),
                    'source_url': scheme_url
                }
            }
        
        finally:
            driver.quit()
    
    def extract_scheme_name(self, soup):
        """Extract scheme name"""
        selectors = [
            ('h1', {}),
            ('h2', {}),
            ('.scheme-title', {}),
            ('.heading', {}),
            ('title', {})
        ]
        
        for tag, attrs in selectors:
            element = soup.find(tag, attrs)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) > 3:
                    return text
        
        return "Unknown Scheme"
    
    def extract_all_sections(self, soup):
        """Extract all content sections"""
        sections = {}
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5'])
        
        for heading in headings:
            title = heading.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            
            content = []
            
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                    break
                
                text = sibling.get_text(strip=True)
                if text and len(text) > 10:
                    content.append(text)
                
                lists = sibling.find_all('li')
                for li in lists:
                    li_text = li.get_text(strip=True)
                    if li_text and len(li_text) > 5:
                        content.append(li_text)
            
            if content:
                sections[title] = content
        
        return sections
    
    def extract_scheme_details(self, soup):
        """Extract general scheme details"""
        details = {}
        
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            details['meta_description'] = meta_desc['content']
        
        content_selectors = [
            {'class_': lambda x: x and any(word in str(x).lower() for word in ['content', 'description', 'about', 'overview'])},
        ]
        
        for selector in content_selectors:
            divs = soup.find_all('div', selector)
            for div in divs:
                text = div.get_text(strip=True)
                if 100 < len(text) < 5000:
                    details['description'] = text
                    break
            if 'description' in details:
                break
        
        if 'description' not in details:
            paragraphs = soup.find_all('p')
            combined = ' '.join([p.get_text(strip=True) for p in paragraphs[:5]])
            if len(combined) > 50:
                details['description'] = combined
        
        tables = soup.find_all('table')
        for idx, table in enumerate(tables):
            rows = table.find_all('tr')
            table_data = []
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    table_data.append(row_data)
            if table_data:
                details[f'table_{idx+1}'] = table_data
        
        return details
    
    def extract_section_by_keyword(self, soup, keywords):
        """Extract sections by keywords"""
        results = []
        
        for keyword in keywords:
            headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])
            
            for heading in headings:
                heading_text = heading.get_text(strip=True).lower()
                if keyword.lower() in heading_text:
                    parent = heading.find_parent(['div', 'section', 'article'])
                    if parent:
                        items = parent.find_all('li')
                        if items:
                            results.extend([item.get_text(strip=True) for item in items if item.get_text(strip=True)])
                        
                        if not results:
                            paras = parent.find_all('p')
                            results.extend([p.get_text(strip=True) for p in paras if len(p.get_text(strip=True)) > 10])
                    
                    if results:
                        break
            
            if results:
                break
        
        return results
    
    def extract_contact_info(self, soup):
        """Extract contact information"""
        contact = {}
        page_text = soup.get_text()
        
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', page_text)
        if emails:
            contact['emails'] = list(set(emails))
        
        phones = re.findall(r'(?:\+91|91)?[-.\s]?\d{10}|\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', page_text)
        if phones:
            contact['phones'] = list(set(phones))
        
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', page_text)
        if urls:
            contact['websites'] = list(set([url for url in urls if 'myscheme' not in url]))[:5]
        
        return contact
    
    def format_for_ai_agent(self, data):
        """Format data for AI agent consumption"""
        if 'error' in data:
            return data
        
        sections = data.get('all_sections', {})
        
        return {
            'knowledge_base_entry': {
                'scheme': data.get('scheme_name', 'Unknown Scheme'),
                'summary': data.get('scheme_details', {}).get('description', 
                                   data.get('scheme_details', {}).get('meta_description', '')),
                'key_information': {
                    'eligibility_criteria': data.get('eligibility', []),
                    'benefits': data.get('benefits', []),
                    'required_documents': data.get('documents_required', []),
                    'application_steps': data.get('application_process', [])
                },
                'additional_details': data.get('scheme_details', {}),
                'all_extracted_sections': sections,
                'contact': data.get('contact_info', {}),
                'last_updated': data.get('metadata', {}).get('scraped_at'),
                'source': data.get('metadata', {}).get('source_url')
            }
        }
    
    def run_complete_scrape(self, max_pages=None, max_schemes=None, save_intermediate=True):
        """Run complete scraping process: URLs first, then details"""
        
        print("=" * 70)
        print("🚀 UNIFIED MYSCHEME SCRAPER")
        print("=" * 70)
        print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Phase 1: Collect all URLs
        scheme_urls = self.scrape_all_scheme_urls(max_pages=max_pages)
        
        if not scheme_urls:
            print("❌ No schemes found. Exiting.")
            return
        
        # Save URLs in multiple formats
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save as CSV
        csv_filename = f"scheme_urls_{timestamp}.csv"
        with open(csv_filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Index", "Scheme Name", "Scheme URL"])
            for idx, scheme in enumerate(scheme_urls, 1):
                writer.writerow([idx, scheme['name'], scheme['url']])
        
        # Save as JSON
        json_filename = f"scheme_urls_{timestamp}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(scheme_urls, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved {len(scheme_urls)} URLs to:")
        print(f"   - {csv_filename}")
        print(f"   - {json_filename}\n")
        
        # Limit schemes if specified
        if max_schemes:
            scheme_urls = scheme_urls[:max_schemes]
            print(f"⚠️ Limited to first {max_schemes} schemes\n")
        
        # Phase 2: Scrape details for each scheme
        print("=" * 70)
        print("PHASE 2: SCRAPING DETAILED INFORMATION")
        print("=" * 70)
        
        all_schemes_data = []
        failed_schemes = []
        
        for idx, scheme_info in enumerate(scheme_urls, 1):
            print(f"\n[{idx}/{len(scheme_urls)}] Scraping: {scheme_info['name'][:60]}...")
            
            try:
                scheme_data = self.scrape_scheme_details(scheme_info['url'])
                
                if 'error' not in scheme_data:
                    ai_formatted = self.format_for_ai_agent(scheme_data)
                    all_schemes_data.append(ai_formatted)
                    print(f"    ✅ Success")
                else:
                    failed_schemes.append({
                        'name': scheme_info['name'],
                        'url': scheme_info['url'],
                        'error': scheme_data.get('error', 'Unknown error')
                    })
                    print(f"    ❌ Failed: {scheme_data.get('error', 'Unknown error')}")
                
                # Save intermediate results every 10 schemes
                if save_intermediate and idx % 10 == 0:
                    backup_filename = f"schemes_backup_{timestamp}_{idx}.json"
                    with open(backup_filename, 'w', encoding='utf-8') as f:
                        json.dump(all_schemes_data, f, indent=2, ensure_ascii=False)
                    print(f"    💾 Backup saved: {backup_filename}")
                
                time.sleep(2)  # Respectful delay
                
            except Exception as e:
                print(f"    ❌ Unexpected error: {str(e)}")
                failed_schemes.append({
                    'name': scheme_info['name'],
                    'url': scheme_info['url'],
                    'error': str(e)
                })
        
        # Final save with timestamp
        print("\n" + "=" * 70)
        print("💾 SAVING FINAL RESULTS")
        print("=" * 70)
        
        # Save complete schemes data in multiple formats
        complete_json = f"all_schemes_complete_{timestamp}.json"
        with open(complete_json, 'w', encoding='utf-8') as f:
            json.dump(all_schemes_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved {len(all_schemes_data)} complete schemes to {complete_json}")
        
        # Save raw data (non-AI formatted) for reference
        raw_json = f"all_schemes_raw_{timestamp}.json"
        with open(raw_json, 'w', encoding='utf-8') as f:
            json.dump({
                'total_schemes': len(scheme_urls),
                'successfully_scraped': len(all_schemes_data),
                'failed': len(failed_schemes),
                'scraping_date': datetime.now().isoformat(),
                'schemes': all_schemes_data
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved complete data with metadata to {raw_json}")
        
        # Save as CSV summary
        summary_csv = f"schemes_summary_{timestamp}.csv"
        with open(summary_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Scheme Name", 
                "Eligibility Count", 
                "Benefits Count", 
                "Documents Count",
                "Application Steps Count",
                "Has Contact Info",
                "Source URL"
            ])
            for scheme in all_schemes_data:
                kb = scheme.get('knowledge_base_entry', {})
                ki = kb.get('key_information', {})
                writer.writerow([
                    kb.get('scheme', 'Unknown'),
                    len(ki.get('eligibility_criteria', [])),
                    len(ki.get('benefits', [])),
                    len(ki.get('required_documents', [])),
                    len(ki.get('application_steps', [])),
                    'Yes' if kb.get('contact', {}) else 'No',
                    kb.get('source', '')
                ])
        print(f"✅ Saved summary to {summary_csv}")
        
        if failed_schemes:
            failed_json = f"failed_schemes_{timestamp}.json"
            with open(failed_json, 'w', encoding='utf-8') as f:
                json.dump(failed_schemes, f, indent=2, ensure_ascii=False)
            print(f"⚠️  Saved {len(failed_schemes)} failed schemes to {failed_json}")
            
            # Save failed schemes as CSV too
            failed_csv = f"failed_schemes_{timestamp}.csv"
            with open(failed_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Scheme Name", "URL", "Error"])
                for failed in failed_schemes:
                    writer.writerow([failed['name'], failed['url'], failed['error']])
            print(f"⚠️  Saved failed schemes to {failed_csv}")
        
        # Summary
        print("\n" + "=" * 70)
        print("📊 SCRAPING SUMMARY")
        print("=" * 70)
        print(f"Total schemes found: {len(scheme_urls)}")
        print(f"Successfully scraped: {len(all_schemes_data)}")
        print(f"Failed: {len(failed_schemes)}")
        print(f"Success rate: {len(all_schemes_data)/len(scheme_urls)*100:.1f}%")
        print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)


if __name__ == "__main__":
    scraper = UnifiedSchemeScraper()
    run_weekly_scraper(scraper, max_pages=10, max_schemes=50)
    # Configuration
    MAX_PAGES = None  # Set to None for all pages, or a number like 5 for testing
    MAX_SCHEMES = None  # Set to None for all schemes, or a number like 10 for testing
    
    # Run complete scraping process
    scraper.run_complete_scrape(
        max_pages=MAX_PAGES,
        max_schemes=MAX_SCHEMES,
        save_intermediate=True
    )   