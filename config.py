import os
import json

# Base paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "jobs.db")

# Target URLs
DEV_BG_URL = "https://dev.bg/company/jobs/automation-qa/?_job_location=sofiya%2Cremote&_seniority=mid-level%2Csenior"
LINKEDIN_URL = "https://www.linkedin.com/jobs/search-results/?currentJobId=4420961838&eBP=NON_CHARGEABLE_CHANNEL&refId=BZPTjXzFLsZ1jdqHBlk2Nw%3D%3D&trackingId=3jIENn7ava3YsIYQ2aL9tQ%3D%3D&keywords=quality%20assurance%20engineer%20On-site%20or%20Hybrid&origin=SEMANTIC_SEARCH_JOB_ALERT_IN_APP_NOTIFICATION&originToLandingJobPostings=4422049013%2C4417983142%2C4422018334%2C4420961838&geoId=103835801&distance=50.0&f_TPR=a1780007711-"
JOBS_BG_URL = "https://www.jobs.bg/front_job_search.php?categories%5B%5D=56&domains%5B%5D=9&last=5&location_sid=1&is_detailed=1&subm=1&sh=1"

# LinkedIn Auth & Session configurations
LINKEDIN_SESSION_PATH = os.path.join(BASE_DIR, "linkedin_session.json")

# Load credentials from external JSON file
LINKEDIN_EMAIL = ""
LINKEDIN_PASSWORD = ""
credentials_path = os.path.join(BASE_DIR, "linkedin_credentials.json")
if os.path.exists(credentials_path):
    try:
        with open(credentials_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
            LINKEDIN_EMAIL = creds.get("email", "")
            LINKEDIN_PASSWORD = creds.get("password", "")
    except Exception as e:
        print(f"Error loading credentials from JSON: {e}")

# Scraper settings
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
MAX_WORKERS = 10  # Number of parallel threads to fetch job detail pages

# Flask configurations
FLASK_DEBUG = True
PORT = 5001
