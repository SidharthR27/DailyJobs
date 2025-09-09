import requests
import os
import time
from bs4 import BeautifulSoup
from datetime import datetime
from google import genai
from google.genai import types
import json
import markdown

def fetch_infopark_jobs():
    global combined_new_jobs
    print("🔎 Fetching jobs from Infopark...")
    
    HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-GB,en;q=0.8",
    "host": "infopark.in",
    "referer": "https://infopark.in/companies/job-search?page=1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest"
}

    BASE_URL = "https://infopark.in/companies/job-search?page={page}&search="
    LAST_IDS_FILE = "last_3_days_job_ids.txt"

    def get_total_pages():
        response = requests.get(BASE_URL.format(page=1), headers=HEADERS, verify=False)
        pagination_html = response.json().get("pagination", "")
        soup = BeautifulSoup(pagination_html, "html.parser")
        page_links = soup.find_all("a", class_="page-link")
        pages = [int(a.text) for a in page_links if a.text.isdigit()]
        return max(pages) if pages else 1

    def extract_job_id(url):
        try:
            return int(url.strip("/").split("/")[-2])
        except:
            return -1

    def load_last_3_days_ids():
        """Load the last 3 days' job IDs from file"""
        if not os.path.exists(LAST_IDS_FILE):
            return []
        
        try:
            with open(LAST_IDS_FILE, "r") as f:
                content = f.read().strip()
                if not content:
                    return []
                # Convert comma-separated string to list of integers
                return [int(id_str) for id_str in content.split(",") if id_str.strip()]
        except (ValueError, IOError) as e:
            print(f"⚠️ Error reading last IDs file: {e}")
            return []

    def save_last_3_days_ids(ids_queue):
        """Save the last 3 days' job IDs to file"""
        try:
            with open(LAST_IDS_FILE, "w") as f:
                f.write(",".join(map(str, ids_queue)))
        except IOError as e:
            print(f"⚠️ Error saving last IDs file: {e}")

    def update_ids_queue(ids_queue, new_highest_id):
        """Update the queue with new highest ID, maintaining 3-day window"""
        # Add new highest ID to the end
        ids_queue.append(new_highest_id)
        
        # Keep only the last 3 days (remove oldest if we have more than 3)
        if len(ids_queue) > 3:
            ids_queue.pop(0)  # Remove the oldest (first) element
        
        return ids_queue

    def get_3_day_threshold(ids_queue):
        """Get the threshold ID for 3-day window"""
        if not ids_queue:
            return -1  # If no previous data, get all jobs
        return ids_queue[0]  # The oldest ID in our 3-day window

    def fetch_all_jobs():
        total_pages = get_total_pages()
        jobs = {}

        for page in range(1, total_pages + 1):
            print(f"📄 Fetching page {page}...")
            try:
                response = requests.get(BASE_URL.format(page=page), headers=HEADERS, verify=False)
                jobs_html = response.json()['all_jobs']
                soup = BeautifulSoup(jobs_html, "html.parser")
                rows = soup.find_all("tr")[1:]  # skip header row

                # for row in rows:
                #     cols = row.find_all("td")
                #     if len(cols) < 4:
                #         continue

                #     title = cols[0].get_text(strip=True)
                #     company = cols[1].get_text(strip=True)
                #     last_date = cols[2].get_text(strip=True)
                #     full_url = cols[3].find("a")["href"]

                #     job_id = extract_job_id(full_url)
                #     if job_id != -1:  # Only add valid job IDs
                #         jobs[job_id] = {
                #             "title": title,
                #             "company": company,
                #             "last_date": last_date,
                #             "url": full_url
                #         }
                
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) < 5:
                        continue  # not a valid job row

                    date_posted = cols[0].get_text(strip=True)
                    title = cols[1].get_text(strip=True)
                    company = cols[2].get_text(strip=True)
                    last_date = cols[3].get_text(strip=True)
                    full_url = cols[4].find("a")["href"]

                    job_id = extract_job_id(full_url)
                    if job_id != -1:
                        jobs[job_id] = {
                            "date_posted": date_posted,
                            "title": title,
                            "company": company,
                            "last_date": last_date,
                            "url": full_url
                        }

                time.sleep(1)
            except Exception as e:
                print(f"⚠️ Error on page {page}: {e}")
        return jobs

    def fetch_job_details(jobs_to_fetch):
        job_details_dict = {}
        print(f"\n🔍 Fetching details for {len(jobs_to_fetch)} job(s) from last 3 days...\n")

        for job_id, job in jobs_to_fetch.items():
            try:
                print(f"🔗 Visiting: {job['url']}")
                response = requests.get(job['url'], headers=HEADERS, verify=False)
                soup = BeautifulSoup(response.text, "html.parser")
                details_div = soup.find("div", class_="deatil-box")
                
                if details_div:
                    job_details_dict[job_id] = {
                        "title": job["title"],
                        "company": job["company"],
                        "details_html": str(details_div),
                        "url": job["url"],
                        "last_date": job["last_date"]
                    }

                    combined_new_jobs.append({
                        "job_title": job["title"],
                        "company": job["company"],
                        "url": job["url"],
                        "location": "Infopark",
                        "closing_date": job["last_date"],
                        "job_description": details_div.get_text(strip=True)
                    })
                else:
                    print(f"❌ Could not find detail-box for job ID {job_id}")

                time.sleep(1)

            except Exception as e:
                print(f"⚠️ Error fetching job ID {job_id}: {e}")

        return job_details_dict


    print("🔎 Checking for jobs posted within last 3 days at Infopark...")
    
    # Load the last 3 days' job IDs
    ids_queue = load_last_3_days_ids()
    print(f"📅 Previous 3-day IDs: {ids_queue}")
    
    # Get threshold for 3-day window
    threshold_id = get_3_day_threshold(ids_queue)
    print(f"🎯 Threshold ID (3 days ago): {threshold_id}")
    
    # Fetch all current jobs
    all_jobs = fetch_all_jobs()
    
    if not all_jobs:
        print("⚠️ No jobs found.")

    
    # Find jobs within last 3 days
    jobs_last_3_days = {jid: info for jid, info in all_jobs.items() if jid > threshold_id}
    
    if jobs_last_3_days:
        print(f"✅ Found {len(jobs_last_3_days)} job(s) posted within last 3 days.")
        print(f"📊 Job ID range: {min(jobs_last_3_days.keys())} to {max(jobs_last_3_days.keys())}")
        
        # Fetch detailed information for these jobs
        detailed_jobs = fetch_job_details(jobs_last_3_days)
        
        if detailed_jobs:
            print(f"\n📋 Successfully fetched details for {len(detailed_jobs)} jobs:")
            for job_id, details in detailed_jobs.items():
                print(f"  • [{job_id}] {details['title']} at {details['company']}")
        else:
            print("📭 No detailed job information could be fetched.")
    else:
        print("📭 No jobs found within the last 3 days.")
    
    # Update the IDs queue with today's highest job ID
    if all_jobs:
        highest_id_today = max(all_jobs.keys())
        ids_queue = update_ids_queue(ids_queue, highest_id_today)
        save_last_3_days_ids(ids_queue)
        print(f"\n💾 Updated 3-day IDs queue: {ids_queue}")
        print(f"🆕 Today's highest job ID: {highest_id_today}")
    
    print("🔚 Finished processing jobs.")


def fetch_technopark_jobs():
    global combined_new_jobs
    if_new_jobs = False
    print("🔎 Fetching jobs from Technopark...")
    
    today = datetime.today().date()

    # get latest jobs from Technopark api
    header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"}

    all_jobs = []
    for i in range(1,7):
        page = requests.get(url=f"https://technopark.org/api/paginated-jobs?page={i}&search=&type=", headers=header)
        if page.json()["data"]:
            all_jobs += page.json()["data"]
        else:
            break

    technopark_new_jobs = []

    # add the job details to array and also add the markdown message for the mail
    for job in all_jobs:
        if abs((today- datetime.strptime(job["posted_date"], "%Y-%m-%d").date()).days) <=2:
            if_new_jobs = True
            technopark_new_jobs.append({"job_title": job["job_title"], "company": job["company"]["company"].title(), "url": f'https://technopark.org/job-details/{job["id"]}', "location": "Technopark", "closing_date": datetime.strptime(job["closing_date"], "%Y-%m-%d").strftime("%d %b %Y")})
        else:
            break
        
    # get job details from each urls and scraping to find the necessary details to feed to AI
    for job in technopark_new_jobs:
        print(f"🔗 Visiting: {job['url']}")
        response = requests.get(url=job["url"], headers=header)
        soup = BeautifulSoup(response.content, "html.parser")
        job_div = soup.select_one("#app > div.relative.min-h-screen.w-full.pt-20 > div > div.mb-10.flex.flex-col.bg-white.shadow-2xl")
        job_desc = job_div.getText()
        job["job_description"] = job_desc


    # send mails if there are new jobs today
    if if_new_jobs:
        combined_new_jobs.extend(technopark_new_jobs)
        # print(technopark_new_jobs)
    else:
        print("No new jobs at Technopark, exiting...")

def ai_parsing():
    global combined_new_jobs
    global final_jobs_list
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    print("Firing🔥 up the AI🌪️...")


    for job in combined_new_jobs:
        try:
            # Prepare the messy job description from the job dictionary
            messy_job_description = job.get("job_description", "")

            if not messy_job_description:
                print(f"⚠️ No job description found for {job['job_title']} at {job['company']}. Skipping AI parsing.")
                continue

            # System instruction to guide the model's behavior and output format
            system_instruction = """
            You are an expert at parsing and structuring job descriptions.
            Your task is to analyze the user's job description text and convert it into a clean, well-structured JSON object. You MUST return ONLY a valid JSON object and nothing else.

            The JSON object must have three top-level keys: "prettified_description", "tags", and "summary".

            1.  **"prettified_description"**: This must be a single string. Reformat the entire original job description into a professional and easily readable text. Use markdown for formatting, such as headings (`##`), bolding (`**`), and bullet points (`- `). Ensure that ALL important information and details from the original text are preserved. Do not shorten or leave out any responsibilities, qualifications, or other details. Must include contact information if available.

            2.  **"tags"**: This must be an array of exactly 4 strings. The very first tag MUST be the required years of experience (e.g., "5+ Years", "2-4 Years"). The other three tags should be the most important technologies or skills mentioned.

            3.  **"summary"**: This must be a very concise, two-sentence summary of the job role, suitable for a quick preview, in max 25 words.
            """

            # Configuration for the generation request, including specifying JSON output
            generation_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                system_instruction=system_instruction
            )

            # Make the API call using the recommended client.models.generate_content
            response = client.models.generate_content(
                model="gemini-2.0-flash", # Or another suitable model
                contents=[messy_job_description],
                config=generation_config
            )

            # The response text will be a clean JSON string
            structured_data = json.loads(response.text)
            
            # Print or store the structured data as needed
            print(f"\n--- Parsed Job Data for {job['job_title']} at {job['company']} ---")
            # print(f"Job Description: {structured_data['prettified_description']}")
            # print(f"Tags: {structured_data['tags']}")
            # print(f"Summary: {structured_data['summary']}")
            # You can also update the job dictionary with the structured data if needed
            final_jobs_list.append({
                "job_title": job["job_title"],
                "company": job["company"],
                "url": job["url"],
                "location": job["location"],
                "closing_date": job["closing_date"],
                "job_description": markdown.markdown(structured_data['prettified_description']),
                "tags": structured_data['tags'],
                "summary": structured_data['summary']
            })
            # job["job_description"] = markdown.markdown(structured_data['prettified_description'])
            # job["tags"] = structured_data['tags']
            # job["summary"] = structured_data['summary']
            time.sleep(7)  # Sleep to avoid hitting API rate limits
        except Exception as e:
            print(f"⚠️ Error parsing job {job['job_title']} at {job['company']}: {e}")
            print(response.text if response else "No response received")
            print(structured_data if structured_data else "")
            continue

def main():
    global combined_new_jobs
    global final_jobs_list
    combined_new_jobs = []
    final_jobs_list = []
    fetch_infopark_jobs()
    fetch_technopark_jobs()
    ai_parsing()
    with open("jobs.json", "w") as f:
        json.dump(final_jobs_list, f, indent=4)
    # print(final_jobs_list)

if __name__ == "__main__":
    main()


