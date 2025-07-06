import json
from datetime import datetime
from html import escape
import random


def get_tag_class(tag):
    """Determine CSS class for tags based on content"""
    tag_classes = ["clr1", "clr2", "clr3", "clr4", "clr5", "clr6"]
    return random.choice(tag_classes)

def generate_job_card_html(job, job_index):
    """Generate HTML for a single job card"""
    # Clean and escape data
    job_title = escape(job.get('job_title', 'No Title'))
    company = escape(job.get('company', 'Unknown Company'))
    location = escape(job.get('location', 'Location not specified'))
    closing_date = escape(job.get('closing_date', 'Not specified'))
    description = job.get('job_description', '')
    summary = escape(job.get('summary', "Check the job description for details."))
    
    # Use summary if available, otherwise use cleaned description
    display_description = summary 
    
    # Generate tags HTML
    tags_html = ''
    for tag in job.get('tags', []):
        tag_class = get_tag_class(tag)
        tags_html += f'<span class="tag {tag_class}">{escape(tag)}</span>'
    
    # Generate job card HTML
    job_card_html = f'''
                <div class="job-card">
                    <div class="job-header">
                        <div>
                            <h3 class="job-title">{job_title}</h3>
                            <div class="company-name">{company}</div>
                        </div>
                        <div class="job-source">{location}</div>
                    </div>
                    <p class="job-description">
                        {display_description}
                    </p>
                    <div class="job-tags">
                        {tags_html}
                    </div>
                    <div class="job-footer">
                        <div class="job-deadline">Apply by: {closing_date}</div>
                        <button class="view-details-btn">View Details</button>
                    </div>
                    <div class="job-details"> {description if description else 'No additional details available.'}</div>
                </div>'''
    
    return job_card_html

def generate_index_html():
    """Main function to generate index.html from template.html and jobs.json"""
    try:
        # Read jobs data
        with open('jobs.json', 'r', encoding='utf-8') as f:
            jobs_data = json.load(f)
        
        # Read template
        with open('template.html', 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Generate HTML for all jobs
        jobs_html = ''
        for index, job in enumerate(jobs_data):
            jobs_html += generate_job_card_html(job, index)
        
        # Calculate statistics
        total_jobs = len(jobs_data)
        unique_companies = len(set(job.get('company', 'Unknown') for job in jobs_data))
        last_updated = datetime.now().strftime('%B %d, %Y at %I:%M %p')
        
        # Create JavaScript data for job details
        jobs_js_data = json.dumps(jobs_data, ensure_ascii=False)
        
        # Replace placeholders in template
        final_html = template_content
        final_html = final_html.replace('<!-- JOBS_PLACEHOLDER -->', jobs_html)
        final_html = final_html.replace('<!-- TOTAL_JOBS_COUNT -->', str(total_jobs))
        final_html = final_html.replace('<!-- TOTAL_COMPANIES_COUNT -->', str(unique_companies))
        final_html = final_html.replace('<!-- LAST_UPDATED -->', last_updated)
        final_html = final_html.replace('<!-- JOBS_DATA -->', jobs_js_data)
        
        # Write index.html
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(final_html)
        
        print(f"✅ Successfully generated index.html with {total_jobs} jobs from {unique_companies} companies")
        print(f"📅 Last updated: {last_updated}")
        
    except FileNotFoundError as e:
        print(f"❌ Error: Required file not found - {e}")
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in jobs.json - {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    generate_index_html()