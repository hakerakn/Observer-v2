import urllib.request
import ssl
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import USER_AGENT, MAX_WORKERS
from database import job_exists

logger = logging.getLogger(__name__)

# SSL Context to handle potential certificate validation issues
ssl_context = ssl._create_unverified_context()

def fetch_html(url):
    """
    Fetches the HTML content of a URL with appropriate headers.
    Returns the HTML string if successful, or None if there was an error.
    """
    req = urllib.request.Request(
        url,
        headers={'User-Agent': USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
            if response.getcode() == 200:
                return response.read().decode('utf-8', errors='replace')
            else:
                logger.error(f"Failed to fetch {url}: HTTP status {response.getcode()}")
                return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def fetch_job_details(job_listings):
    """
    Takes a list of job listing dictionaries (containing 'url' and other main info),
    checks which ones are already stored in the database, and fetches detail pages
    for the NEW jobs in parallel.
    
    Updates the list of job dictionaries in place, adding an 'html_detail' key.
    """
    new_jobs = []
    for job in job_listings:
        # Check if the job URL is already in the DB.
        # If it exists, we don't need to fetch its detail page again.
        if job_exists(job['url']):
            job['html_detail'] = None
        else:
            new_jobs.append(job)
            
    if not new_jobs:
        logger.info("No new job detail pages to scrape.")
        return job_listings

    logger.info(f"Scraping details for {len(new_jobs)} new jobs in parallel...")
    
    # We fetch HTML pages concurrently using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Map futures to the job dictionary references
        future_to_job = {
            executor.submit(fetch_html, job['url']): job 
            for job in new_jobs
        }
        
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            try:
                html = future.result()
                job['html_detail'] = html
                if html:
                    logger.info(f"Successfully scraped details for: {job['url']}")
                else:
                    logger.warning(f"Failed to fetch details for: {job['url']}")
            except Exception as exc:
                logger.error(f"Detail fetch for {job['url']} generated an exception: {exc}")
                job['html_detail'] = None

    return job_listings

def scrape_linkedin_jobs(url=None):
    """
    Scrapes job listings from LinkedIn using Playwright and session cookies.
    """
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
    import os
    import re
    import time
    from config import LINKEDIN_URL, LINKEDIN_EMAIL, LINKEDIN_PASSWORD, LINKEDIN_SESSION_PATH
    from parser import extract_leave_days, extract_salary, extract_tech_stack_from_text
    
    target_url = url if url else LINKEDIN_URL
    
    logger.info("Starting LinkedIn scraping cycle...")
    
    scraped_jobs = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        has_session = os.path.exists(LINKEDIN_SESSION_PATH)
        context_opts = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 800}
        }
        if has_session:
            context_opts["storage_state"] = LINKEDIN_SESSION_PATH
            logger.info("Loaded stored LinkedIn session cookies.")
            
        context = browser.new_context(**context_opts)
        page = context.new_page()
        
        logger.info(f"Navigating to LinkedIn Search: {target_url}")
        page.goto(target_url)
        page.wait_for_timeout(7000)
        
        current_url = page.url
        if "login" in current_url or page.locator("input[type='email']").count() > 0 or page.locator("button:text-is('Sign in')").count() > 0:
            logger.info("LinkedIn session expired or not logged in. Attempting automatic login...")
            page.goto("https://www.linkedin.com/login")
            page.wait_for_timeout(3000)
            
            page.fill("input[type='email'] >> visible=true", LINKEDIN_EMAIL)
            page.fill("input[type='password'] >> visible=true", LINKEDIN_PASSWORD)
            
            page.click("button.e83ce89f >> visible=true")
            page.wait_for_timeout(5000)
            
            logged_in = False
            start_time = time.time()
            while time.time() - start_time < 20:
                if "feed" in page.url or "search" in page.url or "mynetwork" in page.url:
                    logged_in = True
                    break
                page.wait_for_timeout(2000)
                
            if logged_in:
                logger.info("Logged in successfully. Saving session cookies...")
                context.storage_state(path=LINKEDIN_SESSION_PATH)
                page.goto(target_url)
                page.wait_for_timeout(7000)
            else:
                logger.error("Failed to log in to LinkedIn. MFA or Captcha block might be present.")
                browser.close()
                return []
                
        try:
            page.wait_for_selector('[data-testid="lazy-column"]', timeout=15000)
            logger.info("LinkedIn job listings loaded.")
        except Exception as e:
            logger.error("Could not find LinkedIn job list lazy-column.")
            browser.close()
            return []
            
        cards = page.locator('[data-testid="lazy-column"] [role="button"]').all()
        logger.info(f"Found {len(cards)} job cards on the page.")
        
        for idx, card in enumerate(cards):
            try:
                card_html = card.inner_html()
                card_soup = BeautifulSoup(card_html, "lxml")
                p_tags = card_soup.find_all("p")
                if not p_tags:
                    continue
                    
                company = "N/A"
                if len(p_tags) > 1:
                    company = p_tags[1].get_text(strip=True)
                
                location = "N/A"
                if len(p_tags) > 2:
                    location = p_tags[2].get_text(strip=True)
                    
                title_tag = p_tags[0]
                span_aria = title_tag.find("span", attrs={"aria-hidden": "true"})
                if span_aria:
                    title = span_aria.get_text(strip=True)
                else:
                    title = title_tag.get_text(strip=True)
                
                if title.startswith("Selected, "):
                    title = title[len("Selected, "):].strip()
                    
                date_published = "N/A"
                for p in p_tags:
                    txt = p.get_text(strip=True)
                    if "Posted" in txt or "ago" in txt:
                        clean_txt = txt.replace("Posted", "").strip()
                        half_len = len(clean_txt) // 2
                        if clean_txt[:half_len] == clean_txt[half_len:]:
                            date_published = "Posted " + clean_txt[:half_len]
                        else:
                            date_published = txt
                        break
                
                # Check if the title and company are valid (avoid non-job links like Privacy & Terms)
                if not title or company == "N/A" or not company or any(x in title.lower() for x in ["privacy", "terms", "business services", "...more"]):
                    continue

                # Click the card to get the Job ID and URL
                card.click()
                page.wait_for_timeout(1000)
                
                job_url = page.url
                job_id_match = re.search(r'currentJobId=(\d+)', job_url)
                if not job_id_match:
                    job_id_match = re.search(r'/jobs/view/(\d+)', job_url)
                    
                if job_id_match:
                    job_id = job_id_match.group(1)
                    direct_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                else:
                    logger.warning(f"Could not parse job ID from URL: {job_url}")
                    continue
                    
                if job_exists(direct_url):
                    logger.info(f"Skipping already scraped job: {title} at {company}")
                    continue
                    
                logger.info(f"Scraping details for new LinkedIn job: {title} at {company}")
                page.wait_for_timeout(2000)
                
                description = "N/A"
                h2_elements = page.locator('h2:text("About the job")').all()
                if h2_elements:
                    parent_parent = h2_elements[0].locator('xpath=../..') 
                    description = parent_parent.inner_text()
                    
                requirements = extract_tech_stack_from_text(description)
                leave_days = extract_leave_days(description)
                salary_from, salary_to = extract_salary(description, BeautifulSoup(description, "lxml"))
                
                job_data = {
                    'url': direct_url,
                    'company': company,
                    'title': title,
                    'date_published': date_published,
                    'requirements': requirements,
                    'leave_days': leave_days,
                    'salary_from': salary_from,
                    'salary_to': salary_to,
                    'description': description,
                    'source': 'LinkedIn'
                }
                scraped_jobs.append(job_data)
                
            except Exception as ex:
                logger.error(f"Error scraping LinkedIn card {idx}: {ex}")
                
        browser.close()
        
    logger.info(f"LinkedIn scraping completed. Scraped {len(scraped_jobs)} new jobs.")
    return scraped_jobs

def scrape_jobs_bg_jobs(url=None):
    """
    Scrapes job listings from jobs.bg using Playwright (in headful mode on Windows to bypass DataDome).
    """
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
    import re
    import json
    import time
    from config import JOBS_BG_URL
    from parser import extract_leave_days, extract_salary, extract_tech_stack_from_text
    
    target_url = url if url else JOBS_BG_URL
    
    logger.info("Starting jobs.bg scraping cycle...")
    
    scraped_jobs = []
    
    # Dynamically calculate window position to place it in the bottom-right corner of the screen
    win_x = 1000
    win_y = 600
    import threading
    if threading.current_thread() is threading.main_thread():
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            width = root.winfo_screenwidth()
            height = root.winfo_screenheight()
            root.destroy()
            if width > 500 and height > 400:
                win_x = width - 420
                win_y = height - 320
        except Exception:
            pass
  
    with sync_playwright() as p:
        # Launch browser in headful mode but tiny and tucked away at the bottom-right corner to pass DataDome
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--window-size=400,280",
                f"--window-position={win_x},{win_y}"
            ]
        )
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="bg-BG",
            timezone_id="Europe/Sofia"
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        try:
            logger.info(f"Navigating to jobs.bg search page: {target_url}")
            page.goto(target_url, referer="https://www.google.bg/", timeout=60000)
            page.wait_for_timeout(7000)
            
            html = page.content()
            soup = BeautifulSoup(html, "lxml")
            
            grids = soup.find_all(class_="mdc-layout-grid__inner")
            logger.info(f"Found {len(grids)} potential grid containers on jobs.bg.")
            
            # Map of jobs to check/visit
            jobs_to_process = []
            
            for idx, grid in enumerate(grids):
                scroll_item = grid.find(class_="scroll-item")
                if not scroll_item:
                    continue
                    
                title_anchor = grid.find("a", class_="black-link-b")
                if not title_anchor:
                    title_anchor = grid.find("a", href=lambda h: h and "/job/" in h)
                    
                url = title_anchor.get("href") if title_anchor else None
                if not url:
                    continue
                    
                # Fix relative URL if any
                if url.startswith("/"):
                    url = "https://www.jobs.bg" + url
                elif not url.startswith("http"):
                    url = "https://www.jobs.bg/" + url
                    
                # Extract clean Title
                title = "N/A"
                if title_anchor:
                    card_title = title_anchor.find(class_="card-title")
                    if card_title:
                        spans = card_title.find_all("span", recursive=False)
                        if len(spans) > 1:
                            title = spans[-1].get_text(strip=True)
                        else:
                            title = card_title.get_text(strip=True)
                            title = re.sub(r'star\s*', '', title)
                    else:
                        title = title_anchor.get_text(strip=True)
                        title = re.sub(r'star\s*', '', title)
                
                # Extract Company Name
                company = "N/A"
                logo_img = grid.find("img", class_="company-logo")
                if logo_img and logo_img.get("alt"):
                    company = logo_img.get("alt")
                    
                if company == "N/A":
                    buttons = grid.find_all(attrs={"data-action-args": True})
                    for btn in buttons:
                        args_str = btn.get("data-action-args")
                        try:
                            args = json.loads(args_str)
                            if "name" in args:
                                company = args["name"]
                                break
                            elif "params" in args and "company_name" in args["params"]:
                                company = args["params"]["company_name"]
                                break
                        except Exception:
                            pass
                            
                if company == "N/A":
                    sec_text = grid.find(class_="secondary-text")
                    if sec_text:
                        company = sec_text.get_text(strip=True)
                
                # Clean company name
                company = company.replace("\xa0", " ").strip()
                
                # Extract Date
                date_published = "днес"
                card_date_div = grid.find(class_="card-date")
                if card_date_div:
                    raw_date = card_date_div.get_text()
                    raw_date = raw_date.replace("bookmark_border", "").replace("bookmark", "").strip()
                    if raw_date:
                        date_published = raw_date
                
                jobs_to_process.append({
                    'url': url,
                    'title': title,
                    'company': company,
                    'date_published': date_published
                })
                
            # Iterate and visit detail page for new jobs
            for job in jobs_to_process:
                if job_exists(job['url']):
                    logger.info(f"Skipping already scraped jobs.bg job: {job['title']} at {job['company']}")
                    continue
                    
                logger.info(f"Scraping details for new jobs.bg job: {job['title']} at {job['company']}")
                try:
                    page.goto(job['url'], referer=target_url, timeout=45000)
                    
                    # Wait for either iframe or standard template description to load
                    page.wait_for_selector('.job-view-iframe, .job-view-description-text', timeout=10000)
                    
                    if page.locator('.job-view-iframe').count() > 0:
                        # Custom HTML iframe job description
                        frame = page.frame_locator('.job-view-iframe')
                        description = frame.locator('body').inner_text()
                    else:
                        # Standard template job description
                        description = page.locator('.job-view-description-text').inner_text()
                    
                    requirements = extract_tech_stack_from_text(description)
                    leave_days = extract_leave_days(description)
                    salary_from, salary_to = extract_salary(description, BeautifulSoup(description, "lxml"))
                    
                    # Populate job data
                    job_data = {
                        'url': job['url'],
                        'company': job['company'],
                        'title': job['title'],
                        'date_published': job['date_published'],
                        'requirements': requirements,
                        'leave_days': leave_days,
                        'salary_from': salary_from,
                        'salary_to': salary_to,
                        'description': description,
                        'source': 'jobs.bg'
                    }
                    scraped_jobs.append(job_data)
                except Exception as detail_ex:
                    logger.error(f"Error scraping details for jobs.bg URL {job['url']}: {detail_ex}")
                    
        except Exception as ex:
            logger.error(f"Error scraping jobs.bg: {ex}")
        finally:
            browser.close()
            
    logger.info(f"jobs.bg scraping completed. Scraped {len(scraped_jobs)} new jobs.")
    return scraped_jobs
