import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from html import escape
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    """Extract readable text from scraped HTML for metadata classification."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return " ".join(self.parts)


def html_to_text(value):
    parser = TextExtractor()
    try:
        parser.feed(str(value or ""))
        parser.close()
        return re.sub(r"\s+", " ", parser.get_text()).strip()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(value or ""))).strip()


def get_tag_class(tag):
    """Return a stable tag colour so colours do not change on each generation."""
    digest = hashlib.sha256(str(tag).casefold().encode("utf-8")).hexdigest()
    return f"clr{(int(digest[:8], 16) % 6) + 1}"


def normalize_location(value):
    text = str(value or "").casefold()
    if re.search(r"\bremote\b|work\s*from\s*home|\bwfh\b", text):
        return "remote"
    if re.search(r"technopark|trivandrum|thiruvananthapuram", text):
        return "technopark"
    if re.search(r"infopark|kochi|ernakulam", text):
        return "infopark"
    return "unknown"


def infer_employment_type(job, searchable_text):
    """Prefer a structured JSON field; otherwise infer only when text is explicit."""
    explicit = str(job.get("employment_type", "") or "").casefold().strip()
    for pattern, result in [
        (r"\binternship\b|\bintern\b", "internship"),
        (r"\bpart[ -]?time\b", "part-time"),
        (r"\bcontract\b|\bfreelance\b|\btemporary\b", "contract"),
        (r"\bfull[ -]?time\b|\bpermanent\b", "full-time"),
    ]:
        if re.search(pattern, explicit):
            return result

    text = f"{explicit} {searchable_text}".casefold()
    # A labelled employment type is stronger evidence than incidental wording.
    labelled = re.search(
        r"employment\s*type\s*[:\-]?\s*(full[ -]?time|part[ -]?time|internship|intern|contract|freelance|temporary|permanent)",
        text,
    )
    if labelled:
        value = labelled.group(1)
        if re.fullmatch(r"internship|intern", value):
            return "internship"
        if re.fullmatch(r"part[ -]?time", value):
            return "part-time"
        if re.fullmatch(r"contract|freelance|temporary", value):
            return "contract"
        return "full-time"

    # Listings commonly state just "Full-Time" without a field label.
    for pattern, result in [
        (r"\bpart[ -]?time\b", "part-time"),
        (r"\binternship\b|\bintern\b", "internship"),
        (r"\bcontract\b|\bfreelance\b|\btemporary\b", "contract"),
        (r"\bfull[ -]?time\b|\bpermanent\b", "full-time"),
    ]:
        if re.search(pattern, text):
            return result
    return "unknown"


def infer_experience(job, searchable_text):
    """Return normalized experience years and the UI buckets supported by the listing."""
    minimum = maximum = None
    try:
        if job.get("min_experience_years") not in (None, ""):
            minimum = float(job["min_experience_years"])
        if job.get("max_experience_years") not in (None, ""):
            maximum = float(job["max_experience_years"])
    except (TypeError, ValueError):
        minimum = maximum = None

    text = searchable_text.casefold()
    if minimum is None and maximum is None:
        # Match ranges first: "2-8 years", "2 to 8 years".
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\b", text)
        if match:
            minimum, maximum = float(match.group(1)), float(match.group(2))
        else:
            # Minimum requirements: "5+ years", "minimum of 5 years", "at least 5 years".
            match = re.search(r"(?:at least\s+|minimum(?: of)?\s+)?(\d+(?:\.\d+)?)\s*\+\s*years?\b", text)
            if not match:
                match = re.search(r"(?:at least\s+|minimum(?: of)?\s+)(\d+(?:\.\d+)?)\s*years?\b", text)
            if match:
                minimum = float(match.group(1))
            else:
                match = re.search(r"\b(\d+(?:\.\d+)?)\s*years?\b", text)
                if match:
                    minimum = maximum = float(match.group(1))

    levels = set()
    if re.search(r"\bfresher\b|\bentry[ -]?level\b|\bno experience\b", text):
        levels.add("fresher")
    if re.search(r"\bjunior\b|\bassociate\b", text):
        levels.add("junior")
    if re.search(r"\bmid[ -]?level\b|\bintermediate\b", text):
        levels.add("mid-level")
    if re.search(r"\bsenior\b|\blead\b|\bprincipal\b", text):
        levels.add("senior")

    # Ranges may match multiple levels. A 2–8 year role can suit mid-level and senior applicants.
    if minimum is not None or maximum is not None:
        low = minimum if minimum is not None else 0
        high = maximum if maximum is not None else float("inf")
        if low <= 1 and high >= 0:
            levels.add("fresher")
        if low <= 3 and high >= 1:
            levels.add("junior")
        if low <= 5 and high >= 2:
            levels.add("mid-level")
        if high >= 6:
            levels.add("senior")

    return minimum, maximum, sorted(levels)


def format_number(value):
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else str(value)


def generate_job_card_html(job, job_index):
    """Generate one job card with normalized data attributes used by the filters."""
    job_title = escape(str(job.get("job_title", "No Title") or "No Title"))
    company = escape(str(job.get("company", "Unknown Company") or "Unknown Company"))
    location = escape(str(job.get("location", "Location not specified") or "Location not specified"))
    closing_date = escape(str(job.get("closing_date", "Not specified") or "Not specified"))
    description = str(job.get("job_description", "") or "")
    summary = escape(str(job.get("summary", "Check the job description for details.") or "Check the job description for details."))
    tags = job.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    searchable_text = " ".join([
        str(job.get("job_title", "") or ""),
        str(job.get("company", "") or ""),
        str(job.get("summary", "") or ""),
        " ".join(str(tag) for tag in tags),
        html_to_text(description),
        str(job.get("employment_type", "") or ""),
    ])
    location_key = normalize_location(job.get("location", ""))
    employment_type = infer_employment_type(job, searchable_text)
    min_experience, max_experience, experience_levels = infer_experience(job, searchable_text)

    tags_html = "\n".join(
        f'<span class="tag {get_tag_class(tag)}">{escape(str(tag))}</span>'
        for tag in tags
    )
    return f'''
                <div class="job-card"
                     data-location="{escape(location_key, quote=True)}"
                     data-employment-type="{escape(employment_type, quote=True)}"
                     data-experience-levels="{escape(','.join(experience_levels), quote=True)}"
                     data-min-experience="{escape(format_number(min_experience), quote=True)}"
                     data-max-experience="{escape(format_number(max_experience), quote=True)}">
                    <div class="job-header">
                        <div>
                            <h3 class="job-title">{job_title}</h3>
                            <div class="company-name">{company}</div>
                        </div>
                        <div class="job-source">{location}</div>
                    </div>
                    <p class="job-description">{summary}</p>
                    <div class="job-tags">{tags_html}</div>
                    <div class="job-footer">
                        <div class="job-deadline">Apply by: {closing_date}</div>
                        <button type="button" class="view-details-btn">View Details</button>
                    </div>
                    <div class="job-details">{description if description else 'No additional details available.'}</div>
                </div>'''


def generate_index_html():
    """Generate index.html from template.html and jobs.json in the current directory."""
    try:
        with open("jobs.json", "r", encoding="utf-8") as file:
            jobs_data = json.load(file)
        if not isinstance(jobs_data, list):
            raise ValueError("jobs.json must contain a JSON array of job objects")

        with open("template.html", "r", encoding="utf-8") as file:
            template_content = file.read()

        valid_jobs = [job for job in jobs_data if isinstance(job, dict)]
        jobs_html = "\n".join(generate_job_card_html(job, index) for index, job in enumerate(valid_jobs))
        total_jobs = len(valid_jobs)
        unique_companies = len({str(job.get("company", "Unknown")).strip() for job in valid_jobs})
        ist_now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
        last_updated = ist_now.strftime("%B %d, %Y at %I:%M %p")

        replacements = {
            "<!-- JOBS_PLACEHOLDER -->": jobs_html,
            "<!-- TOTAL_JOBS_COUNT -->": str(total_jobs),
            "<!-- TOTAL_COMPANIES_COUNT -->": str(unique_companies),
            "<!-- LAST_UPDATED -->": last_updated,
        }
        final_html = template_content
        for placeholder, value in replacements.items():
            final_html = final_html.replace(placeholder, value)

        with open("index.html", "w", encoding="utf-8") as file:
            file.write(final_html)

        print(f"Successfully generated index.html with {total_jobs} jobs from {unique_companies} companies")
        print(f"Last updated: {last_updated}")
    except FileNotFoundError as error:
        print(f"Error: Required file not found - {error}")
    except json.JSONDecodeError as error:
        print(f"Error: Invalid JSON in jobs.json - {error}")
    except Exception as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    generate_index_html()
