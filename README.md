# Job Apply Engine

Fast, autonomous batch job application tool. Uses Playwright to fill ATS forms directly with known selectors — no LLM needed for form navigation. Custom questions (like "Why this role?") get ONE cheap Gemini API call per job.

**~30-60 seconds per application** vs 14 minutes with LLM-per-form tools.

## What It Does

1. Takes a list of job URLs (Greenhouse, Lever)
2. Opens each in a real Chrome browser
3. Fills name, email, phone, LinkedIn, GitHub from your profile
4. Uploads your resume PDF
5. Answers custom questions (rule-based + one Gemini call for open-ended)
6. Takes screenshots at every step for verification
7. Submits the application
8. Generates an HTML report with all screenshots

## Supported Platforms

| Platform | Status | Guest Apply |
|----------|--------|-------------|
| Greenhouse | Working | Yes (most jobs) |
| Lever | Working | Yes (most jobs) |
| Workday | Planned | No (needs account) |
| LinkedIn | Not supported | Needs login |

## Setup

```bash
# 1. Clone
git clone https://github.com/furqan1pk/job-apply.git
cd job-apply

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Set up your profile
# Option A: If you used ApplyPilot before, it reuses ~/.applypilot/profile.json
# Option B: Create ~/.applypilot/profile.json manually (see profile.example.json)

# 4. Add your Gemini API key (free at https://aistudio.google.com/apikey)
# Create ~/.applypilot/.env with:
# GEMINI_API_KEY=your-key-here

# 5. Make sure your resume PDF is accessible
# Default path: ~/Downloads/Furqan Arshad Resume .pdf
# Override with --resume flag
```

## Usage

### Single job
```bash
python apply.py --url https://job-boards.greenhouse.io/company/jobs/123
```

### Batch (multiple URLs)
```bash
# 1. Add URLs to jobs.txt (one per line, # for comments)
# 2. Run:
python apply.py --urls jobs.txt
```

### Dry run (fill forms but don't submit)
```bash
python apply.py --urls jobs.txt --dry-run
```

### Watch in browser (headed mode)
```bash
python apply.py --url https://... --headed
```

### Custom resume
```bash
python apply.py --url https://... --resume /path/to/resume.pdf
```

### Full combo
```bash
python apply.py --urls jobs.txt --dry-run --headed --resume tailored_resume.pdf
```

## Output

### Screenshots (`screenshots/`)
Per-step screenshots for every application:
- `01_job_page` — the job listing
- `02_apply_form` — empty form after clicking Apply
- `03_fields_filled` — name, email, phone filled
- `04_resume_uploaded` — resume attached
- `05_questions_answered` — custom questions filled
- `06_ready_to_submit` — final review before submit
- `07_confirmation` — success page after submit

### Results (`results/`)
- `applications_YYYY-MM-DD.csv` — spreadsheet of all applications
- `applications_YYYY-MM-DD.jsonl` — machine-readable log
- `report_YYYY-MM-DD.html` — visual HTML report with embedded screenshots (auto-opens in browser)

## How Custom Questions Work

Most screening questions are answered **without any LLM** using rule-based pattern matching:

| Question Pattern | Answer Source |
|---|---|
| "Are you authorized to work?" | profile.json |
| "Require sponsorship?" | profile.json |
| "LinkedIn URL?" | profile.json |
| "Salary expectations?" | profile.json |
| "Gender / Race / Veteran / Disability" | "Decline to self-identify" |
| "Are you 18+?" / "Background check?" | "Yes" |
| "How did you hear about us?" | "Online Job Board" |

Only genuinely open-ended questions ("Why this role?", "Tell us about a project") go to Gemini — and they're batched into **ONE API call** per job (~$0.0001).

## Architecture

```
apply.py          CLI entry point + batch loop
config.py         Load profile from ~/.applypilot/profile.json
greenhouse.py     Greenhouse adapter (direct Playwright selectors)
lever.py          Lever adapter (direct Playwright selectors)
questions.py      Rule-based matcher + single Gemini API call
results.py        CSV + JSONL logging
report.py         HTML report with screenshots
jobs.txt          Input URLs (one per line)
```

## Profile Format

Reuses `~/.applypilot/profile.json`:
```json
{
  "personal": {
    "full_name": "Your Name",
    "email": "you@email.com",
    "phone": "+11234567890",
    "linkedin_url": "https://linkedin.com/in/you",
    "github_url": "https://github.com/you"
  },
  "work_authorization": {
    "legally_authorized_to_work": "Yes",
    "require_sponsorship": "No"
  },
  "compensation": {
    "salary_expectation": "150000"
  }
}
```

## Comparison

| | This Tool | ApplyPilot | Simplify |
|---|---|---|---|
| Speed | ~30-60s/app | ~14 min/app | Manual |
| LLM cost | $0.0001/app | $0.70-1.84/app | Free |
| LLM calls | 1 per app | 50+ per app | 0 |
| File upload | Native Playwright | Via Claude Code | Manual click |
| Batch mode | Yes | Yes (slow) | No |
| Screenshots | Per-step + report | No | No |
| Platforms | Greenhouse, Lever | All ATS | All ATS |
| Custom Qs | Rule-based + 1 LLM | LLM navigates each | Manual/AI |

## Known Limitations

- **Cloudflare**: Some Greenhouse pages have Cloudflare challenges. The tool waits up to 10s for auto-resolution — works with persistent Chrome context.
- **React Select dropdowns**: Handled via click-type-select pattern, but some custom implementations may not work.
- **File uploads**: Uses Playwright's native `set_input_files()` — works reliably.
- **Gemini rate limits**: Free tier has 15 RPM limit. If hit, falls back to generic answers.
- **No account creation**: Only supports guest-apply flows (Greenhouse, Lever). Workday requires accounts.

## License

MIT
