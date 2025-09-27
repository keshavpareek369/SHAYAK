import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time

class PMKISANScraper:
    def __init__(self):
        self.url = "https://www.myscheme.gov.in/schemes/pm-kisan"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
    
    def scrape_with_selenium(self):
        """Scrape using Selenium for JavaScript-rendered content"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument(f'user-agent={self.headers["User-Agent"]}')
            
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), 
                                     options=chrome_options)
            
            print("Loading page with Selenium...")
            driver.get(self.url)
            
            # Wait for content to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(3)  # Additional wait for dynamic content
            
            page_source = driver.page_source
            driver.quit()
            
            soup = BeautifulSoup(page_source, 'html.parser')
            return self.parse_content(soup)
            
        except ImportError:
            print("⚠ Selenium not installed. Install with: pip install selenium webdriver-manager")
            print("Falling back to requests method...")
            return self.scrape()
        except Exception as e:
            print(f"Selenium error: {str(e)}")
            print("Falling back to requests method...")
            return self.scrape()
    
    def scrape(self):
        """Scrape using requests (for static content)"""
        try:
            print("Fetching page with requests...")
            response = requests.get(self.url, headers=self.headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            return self.parse_content(soup)
        
        except Exception as e:
            return {'error': str(e), 'message': 'Failed to fetch page'}
    
    def parse_content(self, soup):
        """Parse the page content"""
        # Save HTML for debugging
        with open('page_debug.html', 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        
        data = {
            'scheme_name': self.extract_scheme_name(soup),
            'scheme_details': self.extract_scheme_details(soup),
            'eligibility': self.extract_eligibility(soup),
            'benefits': self.extract_benefits(soup),
            'application_process': self.extract_application_process(soup),
            'documents_required': self.extract_documents(soup),
            'contact_info': self.extract_contact_info(soup),
            'all_sections': self.extract_all_sections(soup),
            'metadata': {
                'scraped_at': datetime.now().isoformat(),
                'source_url': self.url
            }
        }
        
        return data
    
    def extract_scheme_name(self, soup):
        """Extract scheme name"""
        # Try multiple selectors
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
        
        return "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)"
    
    def extract_all_sections(self, soup):
        """Extract all content sections for fallback"""
        sections = {}
        
        # Find all headings and their content
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5'])
        
        for heading in headings:
            title = heading.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            
            content = []
            
            # Get next siblings until next heading
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                    break
                
                text = sibling.get_text(strip=True)
                if text and len(text) > 10:
                    content.append(text)
                
                # Also check for lists
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
        
        # Extract from meta tags
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            details['meta_description'] = meta_desc['content']
        
        # Look for common content containers
        content_selectors = [
            {'class_': lambda x: x and any(word in str(x).lower() for word in ['content', 'description', 'about', 'overview'])},
            {'id': lambda x: x and any(word in str(x).lower() for word in ['content', 'description', 'about'])},
        ]
        
        for selector in content_selectors:
            divs = soup.find_all('div', selector)
            for div in divs:
                text = div.get_text(strip=True)
                if len(text) > 100 and len(text) < 5000:
                    details['description'] = text
                    break
            if 'description' in details:
                break
        
        # Extract from paragraphs
        if 'description' not in details:
            paragraphs = soup.find_all('p')
            combined = ' '.join([p.get_text(strip=True) for p in paragraphs[:5]])
            if len(combined) > 50:
                details['description'] = combined
        
        # Extract tables
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
        """Generic function to extract sections by keywords"""
        results = []
        
        for keyword in keywords:
            # Find headings with keyword
            headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])
            
            for heading in headings:
                heading_text = heading.get_text(strip=True).lower()
                if keyword.lower() in heading_text:
                    # Get parent container
                    parent = heading.find_parent(['div', 'section', 'article'])
                    if parent:
                        # Extract lists
                        items = parent.find_all('li')
                        if items:
                            results.extend([item.get_text(strip=True) for item in items if item.get_text(strip=True)])
                        
                        # Extract paragraphs
                        if not results:
                            paras = parent.find_all('p')
                            results.extend([p.get_text(strip=True) for p in paras if len(p.get_text(strip=True)) > 10])
                    
                    if results:
                        break
            
            if results:
                break
        
        return results
    
    def extract_eligibility(self, soup):
        """Extract eligibility criteria"""
        keywords = ['eligibility', 'eligible', 'who can apply', 'beneficiary']
        return self.extract_section_by_keyword(soup, keywords)
    
    def extract_benefits(self, soup):
        """Extract scheme benefits"""
        keywords = ['benefit', 'benefits', 'assistance', 'financial support', 'amount']
        return self.extract_section_by_keyword(soup, keywords)
    
    def extract_application_process(self, soup):
        """Extract application process"""
        keywords = ['application', 'how to apply', 'process', 'procedure', 'registration', 'apply']
        return self.extract_section_by_keyword(soup, keywords)
    
    def extract_documents(self, soup):
        """Extract required documents"""
        keywords = ['document', 'documents required', 'papers', 'required documents']
        return self.extract_section_by_keyword(soup, keywords)
    
    def extract_contact_info(self, soup):
        """Extract contact information"""
        import re
        contact = {}
        
        # Get all text
        page_text = soup.get_text()
        
        # Extract emails
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', page_text)
        if emails:
            contact['emails'] = list(set(emails))
        
        # Extract phone numbers
        phones = re.findall(r'(?:\+91|91)?[-.\s]?\d{10}|\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', page_text)
        if phones:
            contact['phones'] = list(set(phones))
        
        # Extract URLs
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', page_text)
        if urls:
            contact['websites'] = list(set([url for url in urls if 'myscheme' not in url]))[:5]
        
        return contact
    
    def save_to_json(self, data, filename='pm_kisan_data.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✓ Data saved to {filename}")
    
    def format_for_ai_agent(self, data):
        """Format data for AI agent consumption"""
        if 'error' in data:
            return data
        
        # Use all_sections as fallback
        sections = data.get('all_sections', {})
        
        ai_formatted = {
            'knowledge_base_entry': {
                'scheme': data.get('scheme_name', 'PM-KISAN'),
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
        
        return ai_formatted


# Usage Example
if __name__ == "__main__":
    scraper = PMKISANScraper()
    
    print("=" * 60)
    print("PM-KISAN Scheme Scraper")
    print("=" * 60)
    
    # Try Selenium first (better for dynamic content)
    print("\nAttempting scrape with Selenium (recommended)...")
    data = scraper.scrape_with_selenium()
    
    if 'error' in data:
        print(f"\n✗ Error occurred: {data['error']}")
    else:
        print("\n✓ Scraping successful!")
        
        # Save raw data
        scraper.save_to_json(data, 'pm_kisan_raw.json')
        
        # Format for AI agent
        ai_data = scraper.format_for_ai_agent(data)
        scraper.save_to_json(ai_data, 'pm_kisan_ai_format.json')
        
        # Display summary
        print("\n" + "=" * 60)
        print("EXTRACTION SUMMARY")
        print("=" * 60)
        print(f"Scheme Name: {ai_data['knowledge_base_entry']['scheme']}")
        print(f"Eligibility Items: {len(ai_data['knowledge_base_entry']['key_information']['eligibility_criteria'])}")
        print(f"Benefits Items: {len(ai_data['knowledge_base_entry']['key_information']['benefits'])}")
        print(f"Documents Items: {len(ai_data['knowledge_base_entry']['key_information']['required_documents'])}")
        print(f"Application Steps: {len(ai_data['knowledge_base_entry']['key_information']['application_steps'])}")
        print(f"Total Sections Found: {len(ai_data['knowledge_base_entry']['all_extracted_sections'])}")
        print("\nSections extracted:")
        for section in ai_data['knowledge_base_entry']['all_extracted_sections'].keys():
            print(f"  • {section}")
        print("\n✓ Check page_debug.html to see the raw HTML structure")