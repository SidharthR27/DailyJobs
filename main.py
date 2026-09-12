import requests
import os
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import markdown
from groq import Groq

def fetch_infopark_jobs():
    global combined_new_jobs
    print("🔎 Fetching jobs from Infopark...")

    HEADERS = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-GB,en;q=0.8",
        "referer": "https://infopark.in/companies-job?page=1",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
        "x-requested-with": "XMLHttpRequest"
    }

    # CURRENT Infopark AJAX endpoint
    BASE_URL = "https://infopark.in/companies-job?page={page}&search="

    # ---------------------------------------------------------
    # Get total number of pages
    # ---------------------------------------------------------
    def get_total_pages():
        try:
            response = requests.get(
                BASE_URL.format(page=1),
                headers=HEADERS,
                verify=False,
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            pagination_html = data.get("pagination", "")

            soup = BeautifulSoup(pagination_html, "html.parser")

            pages = []

            # Extract page numbers from pagination links
            for link in soup.find_all("a", href=True):
                text = link.get_text(strip=True)

                if text.isdigit():
                    pages.append(int(text))

                # Also extract page number from href if available
                href = link.get("href", "")
                match = __import__("re").search(r"[?&]page=(\d+)", href)

                if match:
                    pages.append(int(match.group(1)))

            total_pages = max(pages) if pages else 1

            print(f"📑 Infopark has {total_pages} page(s).")

            return total_pages

        except Exception as e:
            print(f"⚠️ Error getting Infopark page count: {e}")
            return 1

    # ---------------------------------------------------------
    # Fetch jobs from listing pages
    # ---------------------------------------------------------
    def fetch_all_jobs():
        total_pages = get_total_pages()
        jobs = {}

        today = datetime.today().date()

        # Last 3 calendar days:
        # today, yesterday and day before yesterday
        oldest_date = today - timedelta(days=2)

        for page in range(1, total_pages + 1):

            print(f"📄 Fetching Infopark page {page}/{total_pages}...")

            try:
                response = requests.get(
                    BASE_URL.format(page=page),
                    headers=HEADERS,
                    verify=False,
                    timeout=30
                )

                response.raise_for_status()

                data = response.json()
                jobs_html = data.get("all_jobs", "")

                if not jobs_html:
                    print(f"⚠️ No job HTML returned for page {page}")
                    continue

                soup = BeautifulSoup(jobs_html, "html.parser")
                rows = soup.find_all("tr")

                page_dates = []

                for row in rows:

                    cols = row.find_all("td")

                    if len(cols) < 5:
                        continue

                    date_posted = cols[0].get_text(" ", strip=True)
                    title = cols[1].get_text(" ", strip=True)
                    company = cols[2].get_text(" ", strip=True)
                    last_date = cols[3].get_text(" ", strip=True)

                    link = cols[4].find("a", href=True)

                    if not link:
                        continue

                    full_url = link["href"].strip()

                    # Make URL absolute if Infopark ever returns
                    # a relative URL
                    if full_url.startswith("/"):
                        full_url = "https://infopark.in" + full_url

                    # Parse posting date
                    try:
                        posted_date = datetime.strptime(
                            date_posted,
                            "%d-%m-%Y"
                        ).date()

                        page_dates.append(posted_date)

                    except ValueError:
                        print(
                            f"⚠️ Could not parse date "
                            f"'{date_posted}' for {title}"
                        )
                        continue

                    # Only keep jobs posted within last 3 days
                    if oldest_date <= posted_date <= today:

                        # Use URL as the unique identifier.
                        # This avoids relying on Infopark's numeric
                        # job ID for date detection.
                        jobs[full_url] = {
                            "date_posted": date_posted,
                            "posted_date": posted_date,
                            "title": title,
                            "company": company,
                            "last_date": last_date,
                            "url": full_url
                        }

                        print(
                            f"   ✅ {date_posted} | "
                            f"{title} | {company}"
                        )

                # Infopark currently sorts jobs newest first.
                # Once the oldest job on a page is older than our
                # 3-day window, there is no need to fetch further pages.
                if page_dates and min(page_dates) < oldest_date:
                    print(
                        f"⏹️ Page {page} contains jobs older than "
                        f"the 3-day window. Stopping pagination."
                    )
                    break

                time.sleep(1)

            except Exception as e:
                print(
                    f"⚠️ Error fetching Infopark page {page}: {e}"
                )

        return jobs

    # ---------------------------------------------------------
    # Extract job description from current Infopark detail page
    # ---------------------------------------------------------
    def fetch_job_details(jobs_to_fetch):

        job_details_dict = {}

        print(
            f"\n🔍 Fetching details for "
            f"{len(jobs_to_fetch)} Infopark job(s)...\n"
        )

        for job_url, job in jobs_to_fetch.items():

            try:
                print(f"🔗 Visiting: {job['url']}")

                response = requests.get(
                    job["url"],
                    headers=HEADERS,
                    verify=False,
                    timeout=30
                )

                response.raise_for_status()

                soup = BeautifulSoup(
                    response.text,
                    "html.parser"
                )

                # Remove elements that are not part of the job content
                for element in soup.find_all(
                    ["script", "style", "noscript"]
                ):
                    element.decompose()

                # -------------------------------------------------
                # Current Infopark detail pages no longer reliably
                # use the old "deatil-box" class.
                #
                # Find the job title in the rendered page and use
                # the content following it.
                # -------------------------------------------------
                page_text = soup.get_text(
                    "\n",
                    strip=True
                )

                description = ""

                title = job["title"].strip()

                # Find the LAST occurrence of the title.
                # This helps avoid breadcrumbs/navigation text.
                title_position = page_text.rfind(title)

                if title_position != -1:

                    description = page_text[
                        title_position + len(title):
                    ].strip()

                    # Remove common footer content
                    footer_markers = [
                        "About Infopark",
                        "About Us",
                        "© Copyright",
                        "Copyright ©",
                        "Follow Us"
                    ]

                    for marker in footer_markers:

                        marker_position = description.find(marker)

                        if marker_position != -1:
                            description = description[
                                :marker_position
                            ].strip()

                # -------------------------------------------------
                # Fallback: use main/body content if title was not
                # found for some reason.
                # -------------------------------------------------
                if not description:

                    main_content = (
                        soup.find("main")
                        or soup.find("body")
                    )

                    if main_content:

                        description = main_content.get_text(
                            "\n",
                            strip=True
                        )

                if description:

                    job_details_dict[job_url] = {
                        "title": job["title"],
                        "company": job["company"],
                        "details_html": description,
                        "url": job["url"],
                        "last_date": job["last_date"]
                    }

                    combined_new_jobs.append({
                        "job_title": job["title"],
                        "company": job["company"],
                        "url": job["url"],
                        "location": "Infopark",
                        "closing_date": job["last_date"],
                        "job_description": description
                    })

                    print(
                        f"   ✅ Description fetched: "
                        f"{job['title']}"
                    )

                else:

                    print(
                        f"❌ Could not extract description "
                        f"for {job['title']}"
                    )

                time.sleep(1)

            except Exception as e:

                print(
                    f"⚠️ Error fetching "
                    f"{job['url']}: {e}"
                )

        return job_details_dict

    # ---------------------------------------------------------
    # MAIN INFOPARK PROCESS
    # ---------------------------------------------------------

    print(
        "🔎 Checking for jobs posted "
        "within last 3 days at Infopark..."
    )

    # Fetch only jobs from the actual date range.
    jobs_last_3_days = fetch_all_jobs()

    if not jobs_last_3_days:

        print(
            "📭 No Infopark jobs found "
            "within the last 3 days."
        )

        print("🔚 Finished processing Infopark jobs.")
        return

    print(
        f"\n✅ Found {len(jobs_last_3_days)} "
        f"Infopark job(s) posted within last 3 days."
    )

    # Fetch detailed information
    detailed_jobs = fetch_job_details(
        jobs_last_3_days
    )

    if detailed_jobs:

        print(
            f"\n📋 Successfully fetched details for "
            f"{len(detailed_jobs)} Infopark job(s):"
        )

        for job_url, details in detailed_jobs.items():

            print(
                f"  • {details['title']} "
                f"at {details['company']}"
            )

    else:

        print(
            "📭 No detailed Infopark job information "
            "could be fetched."
        )

    print("🔚 Finished processing Infopark jobs.")


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
    # client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    print("Firing🔥 up the AI🌪️...")
    client = Groq(api_key=os.environ["GEMINI_API_KEY"])


    for job in combined_new_jobs:
        structured_data = None
        try:
            messy_job_description = job.get("job_description", "")

            if not messy_job_description:
                print(f"⚠️ No job description found for {job['job_title']}. Skipping.")
                continue

            # 2. Refined System Instruction
            system_instruction = """
            You are an expert at parsing and structuring job descriptions.
            Your task is to analyze the user's job description text and convert it into a clean, well-structured JSON object. You MUST return ONLY a valid JSON object and nothing else.

            The JSON object must have three top-level keys: "prettified_description", "tags", and "summary".

            1.  **"prettified_description"**: This must be a single string. Reformat the entire original job description into a professional and easily readable text. Use markdown for formatting, such as headings (`##`), bolding (`**`), and bullet points (`- `). Ensure that ALL important information and details from the original text are preserved. Do not shorten or leave out any responsibilities, qualifications, or other details. Must include contact information if available.

            2.  **"tags"**: This must be an array of exactly 4 strings. The very first tag MUST be the required years of experience (e.g., "5+ Years", "2-4 Years"). The other three tags should be the most important technologies or skills mentioned.

            3.  **"summary"**: This must be a very concise, two-sentence summary of the job role, suitable for a quick preview, in max 25 words.
            """

            # 3. The API Call
            chat_completion = client.chat.completions.create(
               model="openai/gpt-oss-120b", # <--- CHANGED to the smarter model
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": messy_job_description}
                ],
                response_format={"type": "json_object"}, # Forces valid JSON output
                temperature=0.2  # Low temperature for precision
            )

            # 4. Parsing
            response_content = chat_completion.choices[0].message.content
            structured_data = json.loads(response_content)

            print(f"\n--- Parsed Job Data for {job['job_title']} ---")
            
            final_jobs_list.append({
                "job_title": job["job_title"],
                "company": job["company"],
                "url": job["url"],
                "location": job["location"],
                "closing_date": job["closing_date"],
                "job_description": markdown.markdown(structured_data.get('prettified_description', "")),
                "tags": structured_data.get('tags', []),
                "summary": structured_data.get('summary', "")
            })

            # 5. Rate Limiting
            time.sleep(14)

        except Exception as e:
            print(f"⚠️ Error parsing job {job['job_title']}: {e}")
            time.sleep(300)
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
