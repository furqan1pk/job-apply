"""Custom question answerer — ONE Gemini API call per job."""

import json
import re
import httpx
from config import GEMINI_API_KEY, load_resume_text


# Rule-based patterns: (regex, answer_key_in_profile_or_literal)
RULES = [
    (r"authorized.*work|legally.*authorized|eligible.*work", "authorized_to_work"),
    (r"require.*sponsor|need.*sponsor|visa.*sponsor|sponsorship", "require_sponsorship"),
    (r"linkedin", "linkedin"),
    (r"github", "github"),
    (r"portfolio|website|personal.*site", "portfolio"),
    (r"salary|compensation|pay.*expect|desired.*pay", "salary"),
    (r"years.*experience|experience.*years|how many years", "years_experience"),
    (r"gender|sex", "_gender"),
    (r"race|ethnicity|ethnic", "_race"),
    (r"veteran|military|armed forces", "_veteran"),
    (r"disability|disabled|handicap", "_disability"),
    (r"18.*years|legal.*age|at least 18|over 18", "_yes"),
    (r"background.*check|criminal.*check", "_yes"),
    (r"how.*hear|how.*find|where.*hear|source", "_job_board"),
    (r"start.*date|earliest.*start|when.*start|available.*start", "_immediately"),
    (r"willing.*relocate|open.*relocation", "_no"),
    (r"cover.*letter", "_skip"),  # skip if optional
    (r"previously.*applied|applied.*before", "_no"),
]

# Literal answers for special keys
LITERALS = {
    "_gender": "Decline to self-identify",
    "_race": "Decline to self-identify",
    "_veteran": "I am not a protected veteran",
    "_disability": "I do not wish to answer",
    "_yes": "Yes",
    "_no": "No",
    "_job_board": "Online Job Board",
    "_immediately": "Immediately",
    "_skip": "",
}


def match_rule(question_text: str, profile: dict) -> str | None:
    """Try to answer a question using rule-based matching. Returns answer or None."""
    q = question_text.lower().strip()
    for pattern, key in RULES:
        if re.search(pattern, q):
            if key.startswith("_"):
                return LITERALS.get(key, "")
            return str(profile.get(key, ""))
    return None


def answer_with_llm(questions: list[dict], job_title: str, company: str) -> dict:
    """Send all unanswered custom questions to Gemini in ONE call.

    Args:
        questions: list of {"id": str, "text": str, "type": str}
        job_title: e.g. "Research Scientist, LLM Post-Training"
        company: e.g. "Lila Sciences"

    Returns:
        dict mapping question id to answer string
    """
    if not questions:
        return {}

    if not GEMINI_API_KEY:
        # Fallback: generic answers
        return {q["id"]: _generic_answer(q["text"], job_title, company) for q in questions}

    resume = load_resume_text()

    q_list = "\n".join(f'- ID: {q["id"]} | Type: {q["type"]} | Question: {q["text"]}' for q in questions)

    prompt = f"""You are filling a job application for the role of "{job_title}" at "{company}".
The candidate's resume:
{resume[:3000]}

Answer each question below. Be specific to THIS job. Reference real achievements from the resume.
Keep answers 2-3 sentences for text/textarea, single value for select/radio.
Never lie about credentials. Sound like a real person, not a cover letter.

Questions:
{q_list}

Reply with ONLY valid JSON mapping each ID to its answer:
{{"id_1": "answer_1", "id_2": "answer_2"}}"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        resp = httpx.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        if resp.status_code == 200:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            # Extract JSON from response (may be wrapped in ```json ... ```)
            text = re.sub(r"^```json\s*", "", text.strip())
            text = re.sub(r"\s*```$", "", text.strip())
            return json.loads(text)
        else:
            print(f"  [LLM] Gemini error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [LLM] Error: {e}")

    # Fallback
    return {q["id"]: _generic_answer(q["text"], job_title, company) for q in questions}


def _generic_answer(question: str, job_title: str, company: str) -> str:
    """Fallback generic answer when LLM is unavailable."""
    q = question.lower()
    if "why" in q and ("role" in q or "company" in q or "position" in q or "interest" in q):
        return (
            f"I'm drawn to {company}'s work in this space. My experience building production ML systems "
            f"at Wayfair — including LLM evaluation frameworks and GenAI pipelines — aligns well with "
            f"the {job_title} role. I'm excited to apply these skills to your team's challenges."
        )
    return "Yes"
