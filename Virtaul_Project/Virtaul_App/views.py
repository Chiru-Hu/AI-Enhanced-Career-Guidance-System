import json
import os
import re
from json import JSONDecodeError
from urllib.parse import quote_plus

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone

from google import genai
from google.genai import types

from .models import Profile, StudentProfile, StudentAssessmentAttempt, StudentCareerReport
from .forms import RegisterForm, StudentProfileForm


# -----------------------------
# GEMINI CONFIG (Python 3.9)
# pip install --upgrade google-genai
# -----------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")

_GEMINI_CLIENT = None


def _get_gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is not None:
        return _GEMINI_CLIENT
    if (not GEMINI_API_KEY) or ("PASTE_" in GEMINI_API_KEY):
        return None
    _GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    return _GEMINI_CLIENT


# -----------------------------
# JSON HELPERS (robust)
# -----------------------------
def _strip_json_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_first_json_block(text: str) -> str:
    """
    Extract first valid JSON object/array from text using brace balancing.
    Works even if Gemini adds extra text before/after.
    """
    s = _strip_json_fences(text)
    if not s:
        raise JSONDecodeError("Empty response", s, 0)

    start = None
    opener = None
    for i, ch in enumerate(s):
        if ch in "{[":
            start = i
            opener = ch
            break
    if start is None:
        raise JSONDecodeError("No JSON start found", s, 0)

    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False

    for j in range(start, len(s)):
        ch = s[j]

        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return s[start:j + 1]

    raise JSONDecodeError("Unterminated JSON block", s, start)


def _safe_json_loads(text: str):
    raw = _strip_json_fences(text)

    # 1) direct parse
    try:
        obj = json.loads(raw)
        if isinstance(obj, str):  # double-encoded
            obj = json.loads(obj)
        return obj
    except Exception:
        pass

    # 2) extract balanced JSON block
    candidate = _extract_first_json_block(raw)
    obj = json.loads(candidate)
    if isinstance(obj, str):
        obj = json.loads(obj)
    return obj


def _gemini_generate_json(prompt: str, want: str):
    """
    want: 'array' or 'object'
    Robust JSON generation:
    - first call -> parse
    - if fails -> repair prompt -> parse again
    """
    client = _get_gemini_client()
    if client is None:
        raise RuntimeError("Gemini API key not configured.")

    cfg = types.GenerateContentConfig(
        temperature=0.25,
        max_output_tokens=4096,
        response_mime_type="application/json",
        # IMPORTANT: no response_json_schema (avoids 400 INVALID_ARGUMENT)
    )

    resp = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
        config=cfg,
    )

    try:
        data = _safe_json_loads(resp.text or "")
        if want == "object" and not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        if want == "array" and not isinstance(data, list):
            raise ValueError("Expected JSON array")
        return data
    except Exception:
        repair_prompt = f"""
Return ONLY VALID JSON {want.upper()}.
No markdown. No explanation. No extra words.

BROKEN OUTPUT:
{resp.text}
"""
        resp2 = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=repair_prompt,
            config=types.GenerateContentConfig(
                temperature=0.05,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        data2 = _safe_json_loads(resp2.text or "")
        if want == "object" and not isinstance(data2, dict):
            raise ValueError("Expected JSON object after repair")
        if want == "array" and not isinstance(data2, list):
            raise ValueError("Expected JSON array after repair")
        return data2


# -----------------------------
# SMALL HELPERS
# -----------------------------
def _ensure_student_role(request) -> bool:
    try:
        return Profile.objects.get(user=request.user).role == "student"
    except Profile.DoesNotExist:
        return False


def _job_links_for(career_title: str, skills=None, interests=None):
    skills = skills or []
    interests = interests or []
    q = f"{career_title} " + " ".join((skills[:6] + interests[:4]))
    qq = quote_plus(q.strip() or career_title)

    return [
        {"site": "LinkedIn Jobs", "url": f"https://www.linkedin.com/jobs/search/?keywords={qq}"},
        {"site": "LinkedIn Easy Apply", "url": f"https://www.linkedin.com/jobs/search/?f_AL=true&keywords={qq}"},
        {"site": "Indeed India", "url": f"https://in.indeed.com/jobs?q={qq}"},
        {"site": "Naukri", "url": f"https://www.naukri.com/{quote_plus(career_title.lower())}-jobs"},
        {"site": "Internshala", "url": f"https://internshala.com/internships/keywords-{quote_plus(career_title.lower())}/"},
    ]


def _course_link(search_query: str, platform: str):
    q = quote_plus((search_query or "").strip())
    p = (platform or "").lower()

    if "coursera" in p:
        return f"https://www.coursera.org/search?query={q}"
    if "udemy" in p:
        return f"https://www.udemy.com/courses/search/?q={q}"
    if "youtube" in p:
        return f"https://www.youtube.com/results?search_query={q}"
    if "linkedin" in p:
        return f"https://www.linkedin.com/learning/search?keywords={q}"

    return f"https://www.google.com/search?q={q}"


# -----------------------------
# BASIC PAGES
# -----------------------------
def index(request):
    return render(request, "index.html")


def about(request):
    return render(request, "about.html")


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully! You can now log in.")
            return redirect("login")
        messages.error(request, "Please correct the errors below.")
    else:
        form = RegisterForm()
    return render(request, "register.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, "Invalid username or password.")
            return redirect("login")

        login(request, user)

        try:
            role = Profile.objects.get(user=user).role
        except Profile.DoesNotExist:
            messages.error(request, "User role not found! Contact admin.")
            return redirect("login")

        if role == "student":
            return redirect("student_dashboard")
        if role == "parent":
            return redirect("parent_dashboard")
        if role == "counselor":
            return redirect("counselor_dashboard")

        messages.error(request, "Invalid role! Contact admin.")
        return redirect("login")

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# -----------------------------
# DASHBOARDS
# -----------------------------
@login_required
def student_dashboard(request):
    student_profile = StudentProfile.objects.filter(user=request.user).first()

    last_attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=request.user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

    return render(request, "student_dashboard.html", {
        "user": request.user,
        "student_profile": student_profile,
        "last_attempt": last_attempt,
    })


@login_required
def parent_dashboard(request):
    return render(request, "parent_dashboard.html", {"user": request.user})


@login_required
def counselor_dashboard(request):
    return render(request, "counselor_dashboard.html", {"user": request.user})


# -----------------------------
# STUDENT PROFILE
# -----------------------------
@login_required
def student_profile(request):
    if not _ensure_student_role(request):
        messages.error(request, "Only students can access Student Profile.")
        return redirect("student_dashboard")

    obj, _ = StudentProfile.objects.get_or_create(
        user=request.user,
        defaults={"email": request.user.email, "full_name": request.user.username}
    )

    if request.method == "POST":
        form = StudentProfileForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Student profile saved successfully!")
            return redirect("student_dashboard")

        messages.error(request, "Please correct the errors below.")
        for field, errs in form.errors.items():
            for e in errs:
                messages.error(request, f"{field}: {e}")
    else:
        form = StudentProfileForm(instance=obj)

    return render(request, "student_profile_form.html", {
        "form": form,
        "student_profile": obj,
    })


@login_required
def student_profile_view(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.warning(request, "Please create your profile first.")
        return redirect("student_profile")
    return render(request, "student_profile_view.html", {"profile": profile})


@login_required
def student_profile_delete(request):
    if not _ensure_student_role(request):
        messages.error(request, "Only students can access this.")
        return redirect("student_dashboard")

    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.warning(request, "No profile found to delete.")
        return redirect("student_dashboard")

    if request.method == "POST":
        profile.delete()
        messages.success(request, "✅ Profile deleted successfully!")
        return redirect("student_dashboard")

    return render(request, "student_profile_delete_confirm.html", {"profile": profile})


# -----------------------------
# ASSESSMENT
# -----------------------------
def _validate_questions(data):
    if not isinstance(data, list) or len(data) != 10:
        raise ValueError("Questions must be a JSON array of exactly 10 items.")

    for i, q in enumerate(data, start=1):
        if not isinstance(q, dict):
            raise ValueError("Each question must be an object.")

        q.setdefault("id", f"q{i}")
        q.setdefault("topic", "General")
        q.setdefault("difficulty", "easy")
        q.setdefault("explanation", "")
        q.setdefault("question", f"Question {i}")

        opts = q.get("options", {})
        if not isinstance(opts, dict):
            opts = {}
        for k in ["A", "B", "C", "D"]:
            opts.setdefault(k, f"Option {k}")
        q["options"] = opts

        if q.get("correct_option") not in ["A", "B", "C", "D"]:
            q["correct_option"] = "A"

    return data


def _fallback_questions(subject, interests):
    topic = subject or (interests[0] if interests else "General Aptitude")
    return [
        {
            "id": f"q{i}",
            "question": f"[{topic}] Sample question {i}: Which option is most correct?",
            "options": {"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"},
            "correct_option": "A",
            "topic": topic,
            "difficulty": "easy",
            "explanation": "Fallback question used when Gemini is unavailable."
        }
        for i in range(1, 11)
    ]


def _generate_10_questions(subject, interests, skills):
    prompt = f"""
Generate EXACTLY 10 MCQ questions for a student.

Subject (entered by student): {subject}
Student Interests: {interests}
Student Skills: {skills}

Return ONLY JSON ARRAY (no markdown, no extra text).
Each item format:
{{
  "id":"q1",
  "question":"...",
  "options":{{"A":"...","B":"...","C":"...","D":"..."}},
  "correct_option":"A",
  "topic":"{subject}",
  "difficulty":"easy",
  "explanation":"1-2 lines"
}}
"""
    data = _gemini_generate_json(prompt, want="array")
    return _validate_questions(data)


@login_required
def student_assessment(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.warning(request, "Please create your profile first.")
        return redirect("student_profile")

    interests = profile.interests or []
    skills = profile.skills or []

    # 1) SUBMIT answers
    if request.method == "POST" and request.POST.get("attempt_id"):
        attempt_id = request.POST.get("attempt_id")
        attempt = get_object_or_404(StudentAssessmentAttempt, id=attempt_id, user=request.user)

        answers = {}
        score = 0
        for q in (attempt.questions or []):
            qid = q.get("id")
            selected = request.POST.get(qid)
            if selected:
                answers[qid] = selected
            if selected and selected == q.get("correct_option"):
                score += 1

        attempt.answers = answers
        attempt.score = score
        attempt.completed_at = timezone.now()
        attempt.save()

        messages.success(request, f"✅ Assessment submitted successfully! Score: {score}/10")
        return redirect("student_assessment_result", attempt_id=attempt.id)

    # 2) GENERATE test
    if request.method == "POST" and request.POST.get("generate_test") == "1":
        subject = (request.POST.get("subject") or "").strip()
        if not subject:
            messages.error(request, "Please enter Subject to generate your test.")
            return render(request, "student_assessment.html", {
                "student_profile": profile,
                "subject": "",
                "attempt": None,
                "questions": [],
                "model_used": "",
            })

        model_used = GEMINI_MODEL_NAME
        try:
            questions = _generate_10_questions(subject, interests, skills)
        except Exception as e:
            messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Loaded fallback assessment.")
            questions = _fallback_questions(subject, interests)
            model_used = "fallback"

        # IMPORTANT: StudentAssessmentAttempt must have subject field in model + migrated
        attempt = StudentAssessmentAttempt.objects.create(
            user=request.user,
            subject=subject,
            interests_snapshot=interests,
            skills_snapshot=skills,
            questions=questions,
            total=10,
            model_name=model_used,
        )

        return render(request, "student_assessment.html", {
            "student_profile": profile,
            "subject": subject,
            "attempt": attempt,
            "questions": questions,
            "model_used": model_used,
        })

    return render(request, "student_assessment.html", {
        "student_profile": profile,
        "subject": "",
        "attempt": None,
        "questions": [],
        "model_used": "",
    })


@login_required
def student_assessment_result(request, attempt_id):
    attempt = get_object_or_404(StudentAssessmentAttempt, id=attempt_id, user=request.user)

    answers = attempt.answers or {}
    questions = []
    for q in (attempt.questions or []):
        q2 = dict(q)
        qid = q2.get("id")
        sel = answers.get(qid)
        q2["selected"] = sel
        q2["is_correct"] = (sel is not None and sel == q2.get("correct_option"))
        questions.append(q2)

    return render(request, "student_assessment_result.html", {
        "attempt": attempt,
        "questions": questions,
    })


# -----------------------------
# CAREER & COURSES
# -----------------------------
def _fallback_career_report(profile, attempt):
    subject = getattr(attempt, "subject", "") or "General"
    pct = int((attempt.score / max(attempt.total or 10, 1)) * 100)

    return {
        "summary": f"Fallback recommendations. Subject: {subject}. Score {attempt.score}/{attempt.total} ({pct}%).",
        "aptitude_level": "Beginner" if attempt.score <= 4 else ("Intermediate" if attempt.score <= 7 else "Advanced"),
        "strengths": ["Learning mindset", "Consistency", "Basic aptitude"],
        "improvement_areas": ["Practice more MCQs", "Concept clarity", "Time management"],
        "top_career_paths": [
            {
                "career": "Software Developer",
                "fit_score": 70,
                "why_fit": "Good for students who like coding and logic.",
                "roles": ["Intern", "Junior Developer"],
                "missing_skills": ["DSA", "Projects", "Git"],
                "projects": ["CRUD App", "API Project"],
                "roadmap_30_60_90": {
                    "days_30": ["Revise basics", "Git practice", "1 mini project"],
                    "days_60": ["DSA practice", "2 projects", "Resume update"],
                    "days_90": ["Apply internships", "Mock interviews", "Portfolio polish"],
                },
            },
            {
                "career": "Data Analyst",
                "fit_score": 65,
                "why_fit": "Good if you like patterns and analysis.",
                "roles": ["Analyst Intern", "BI Trainee"],
                "missing_skills": ["SQL", "Excel/BI", "Dashboards"],
                "projects": ["Dashboard", "Case Study"],
                "roadmap_30_60_90": {
                    "days_30": ["SQL basics", "Excel practice", "Mini dataset analysis"],
                    "days_60": ["Dashboard project", "Resume", "Mock interview"],
                    "days_90": ["Apply roles", "Portfolio", "Interview prep"],
                },
            },
            {
                "career": "Cyber Security (Starter)",
                "fit_score": 60,
                "why_fit": "Good if you like security & systems.",
                "roles": ["SOC Intern", "Security Trainee"],
                "missing_skills": ["Networking", "Linux", "Security basics"],
                "projects": ["Security notes", "CTF basics"],
                "roadmap_30_60_90": {
                    "days_30": ["Networking basics", "Linux basics", "Security fundamentals"],
                    "days_60": ["Try labs", "Build notes", "Small projects"],
                    "days_90": ["Internship apply", "Portfolio", "Mock Q&A"],
                },
            },
        ],
        "course_recommendations": [
            {"title": "Python Basics", "platform": "YouTube", "level": "Beginner", "duration_weeks": 4,
             "search_query": "Python basics for beginners", "why": "Foundation"},
            {"title": "Aptitude Practice", "platform": "YouTube", "level": "Beginner", "duration_weeks": 3,
             "search_query": "aptitude reasoning practice", "why": "Improve score"},
            {"title": "Git & GitHub", "platform": "YouTube", "level": "Beginner", "duration_weeks": 2,
             "search_query": "git github for beginners", "why": "Portfolio"},
            {"title": "SQL Fundamentals", "platform": "Coursera", "level": "Beginner", "duration_weeks": 4,
             "search_query": "SQL fundamentals beginner", "why": "Analytics"},
            {"title": "Resume & Interview", "platform": "LinkedIn Learning", "level": "Beginner", "duration_weeks": 2,
             "search_query": "resume building interview preparation", "why": "Job ready"},
            {"title": "Mini Projects", "platform": "YouTube", "level": "Beginner", "duration_weeks": 6,
             "search_query": "python mini projects portfolio", "why": "Show skills"},
        ],
        "next_actions": [
            "Pick 1 path for 30 days",
            "Solve 30-50 MCQs per week",
            "Build 2 projects",
            "Update LinkedIn + Resume",
            "Apply weekly to internships/jobs",
        ],
    }


def _normalize_report(report: dict, profile, attempt) -> dict:
    """
    Guarantee keys exist so template never breaks / never shows 'Not available'.
    If Gemini output is missing important arrays, merge fallback values.
    """
    report = report if isinstance(report, dict) else {}

    fb = _fallback_career_report(profile, attempt)

    # basic keys
    report.setdefault("summary", fb["summary"])
    report.setdefault("aptitude_level", fb["aptitude_level"])

    # arrays
    for key in ["strengths", "improvement_areas", "top_career_paths", "course_recommendations", "next_actions"]:
        val = report.get(key)
        if not isinstance(val, list) or len(val) == 0:
            report[key] = fb[key]

    # normalize career paths structure
    fixed_paths = []
    for p in report.get("top_career_paths", []):
        if not isinstance(p, dict):
            continue
        p.setdefault("career", "Career Path")
        p.setdefault("fit_score", 60)
        p.setdefault("why_fit", "")
        p.setdefault("roles", [])
        p.setdefault("missing_skills", [])
        p.setdefault("projects", [])
        rm = p.get("roadmap_30_60_90")
        if not isinstance(rm, dict):
            rm = {"days_30": [], "days_60": [], "days_90": []}
        rm.setdefault("days_30", [])
        rm.setdefault("days_60", [])
        rm.setdefault("days_90", [])
        if not isinstance(rm["days_30"], list): rm["days_30"] = []
        if not isinstance(rm["days_60"], list): rm["days_60"] = []
        if not isinstance(rm["days_90"], list): rm["days_90"] = []
        p["roadmap_30_60_90"] = rm
        fixed_paths.append(p)
    report["top_career_paths"] = fixed_paths

    # normalize course structure
    fixed_courses = []
    for c in report.get("course_recommendations", []):
        if not isinstance(c, dict):
            continue
        c.setdefault("title", "Course")
        c.setdefault("platform", "YouTube")
        c.setdefault("level", "Beginner")
        c.setdefault("duration_weeks", 4)
        c.setdefault("search_query", c.get("title", "Course"))
        c.setdefault("why", "")
        fixed_courses.append(c)
    report["course_recommendations"] = fixed_courses

    return report


def _generate_career_report(profile, attempt):
    # ✅ IMPORTANT: escape braces inside f-string with double {{ }}
    subject = getattr(attempt, "subject", "") or "General"

    prompt = f"""
You are an AI Career Counselor.

Generate Career + Courses recommendations based on:
- Student profile interests/skills
- Assessment subject + score + weak areas.

Student:
Name: {profile.full_name}
Interests: {profile.interests}
Skills: {profile.skills}
Strengths: {profile.strengths}
Weaknesses: {profile.weaknesses}
Career Goal: {profile.career_goal}
Preferred Roles: {profile.preferred_roles}

Assessment:
Subject: {subject}
Score: {attempt.score}/{attempt.total}

Return ONLY JSON OBJECT (no markdown) with keys:
summary, aptitude_level, strengths, improvement_areas,
top_career_paths (3 items),
course_recommendations (6-10 items),
next_actions.

Each top_career_paths item must include:
career, fit_score, why_fit, roles, missing_skills, projects,
roadmap_30_60_90 with keys:
{{"days_30":[], "days_60":[], "days_90":[]}}

Each course must include:
title, platform, level, duration_weeks, search_query, why.
"""
    data = _gemini_generate_json(prompt, want="object")
    return data


def _enrich_report_with_links(report, profile, attempt):
    report = _normalize_report(report, profile, attempt)
    skills = profile.skills or []
    interests = profile.interests or []

    # career paths: job/apply links
    for p in report.get("top_career_paths", []):
        if not isinstance(p, dict):
            continue
        career_title = p.get("career", "Career")
        p["job_links"] = _job_links_for(career_title, skills, interests)
        p["apply_links"] = [
            {"title": "Apply on LinkedIn", "url": "https://www.linkedin.com/jobs/"},
            {"title": "Apply on Indeed", "url": "https://in.indeed.com/"},
            {"title": "Apply on Naukri", "url": "https://www.naukri.com/"},
            {"title": "Apply on Internshala", "url": "https://internshala.com/"},
        ]

    # courses: direct links
    for c in report.get("course_recommendations", []):
        if not isinstance(c, dict):
            continue
        sq = c.get("search_query") or c.get("title") or ""
        c["url"] = _course_link(sq, c.get("platform", ""))

    return report


@login_required
def student_career_home(request):
    last_attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=request.user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

    if not last_attempt:
        messages.warning(request, "⚠️ Please complete at least one assessment to unlock Career & Course Recommendations.")
        return redirect("student_assessment")

    return redirect("student_career_report", attempt_id=last_attempt.id)


@login_required
def student_career_report(request, attempt_id):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.warning(request, "Please create your profile first.")
        return redirect("student_profile")

    attempt = get_object_or_404(StudentAssessmentAttempt, id=attempt_id, user=request.user)
    if not attempt.completed_at:
        messages.warning(request, "Please submit the assessment first.")
        return redirect("student_assessment")

    # Force regenerate: /career-report/<id>/?regen=1
    force_regen = request.GET.get("regen") == "1"

    existing = StudentCareerReport.objects.filter(attempt=attempt, user=request.user).first()
    if existing and not force_regen:
        report = _enrich_report_with_links(existing.report, profile, attempt)
        return render(request, "student_career_report.html", {
            "attempt": attempt,
            "profile": profile,
            "report": report,
            "model_used": existing.model_name,
        })

    model_used = GEMINI_MODEL_NAME
    try:
        report_data = _generate_career_report(profile, attempt)
    except Exception as e:
        messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Loaded fallback recommendations.")
        report_data = _fallback_career_report(profile, attempt)
        model_used = "fallback"

    report_data = _enrich_report_with_links(report_data, profile, attempt)

    if existing:
        existing.report = report_data
        existing.model_name = model_used
        existing.save(update_fields=["report", "model_name"])
    else:
        StudentCareerReport.objects.create(
            attempt=attempt,
            user=request.user,
            report=report_data,
            model_name=model_used,
        )

    # Optional cache in attempt (ONLY if these fields exist in your model)
    if hasattr(attempt, "career_recommendations"):
        attempt.career_recommendations = report_data
        attempt.career_model_name = model_used
        attempt.career_created_at = timezone.now()
        attempt.save(update_fields=["career_recommendations", "career_model_name", "career_created_at"])

    messages.success(request, "✅ Career & course recommendations generated successfully!")
    return render(request, "student_career_report.html", {
        "attempt": attempt,
        "profile": profile,
        "report": report_data,
        "model_used": model_used,
    })

import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

def _gemini_generate_text(prompt: str, temperature: float = 0.35) -> str:
    client = _get_gemini_client()
    if client is None:
        raise RuntimeError("Gemini API key not configured.")

    cfg = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=1200,
    )
    resp = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
        config=cfg,
    )
    return (resp.text or "").strip()


def _build_ai_counselor_prompt(profile, last_attempt, last_report, history, user_message: str) -> str:
    history = history[-8:] if isinstance(history, list) else []

    profile_ctx = {
        "name": getattr(profile, "full_name", "") if profile else "",
        "education": getattr(profile, "highest_education", "") if profile else "",
        "degree": getattr(profile, "degree", "") if profile else "",
        "branch": getattr(profile, "branch", "") if profile else "",
        "year": getattr(profile, "year_of_study", "") if profile else "",
        "cgpa": getattr(profile, "cgpa_or_percent", "") if profile else "",
        "interests": (profile.interests if profile else []) or [],
        "skills": (profile.skills if profile else []) or [],
        "career_goal": getattr(profile, "career_goal", "") if profile else "",
        "preferred_roles": getattr(profile, "preferred_roles", "") if profile else "",
    }

    attempt_ctx = {}
    if last_attempt:
        attempt_ctx = {
            "subject": getattr(last_attempt, "subject", "") or "",
            "score": f"{last_attempt.score}/{last_attempt.total}",
        }

    report_ctx = last_report if isinstance(last_report, dict) else {}

    hist_lines = []
    for m in history:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        hist_lines.append(("User: " if role == "user" else "Assistant: ") + content)

    hist_block = "\n".join(hist_lines).strip()

    prompt = f"""
You are "AI CareerWise Counselor", a helpful AI counselor for students.

Your tasks:
- Answer student questions clearly and practically.
- Give step-by-step guidance (career, courses, interview, skills, roadmap, projects).
- If student asks "what should I do next", suggest actionable next steps.
- If student hasn't done an assessment, advise them to complete it.

Student Context (JSON):
{json.dumps(profile_ctx, ensure_ascii=False)}

Latest Assessment:
{json.dumps(attempt_ctx, ensure_ascii=False)}

Latest Career Report (may be empty JSON):
{json.dumps(report_ctx, ensure_ascii=False)}

Conversation History:
{hist_block if hist_block else "(no history)"}

Now respond to the student's new question:
User: {user_message}

Rules:
- Be concise but complete.
- Use bullet points when helpful.
- Do NOT output markdown code fences.
"""
    return prompt

@login_required
def ai_counselor(request):
    # GET -> open chat page
    if request.method == "GET":
        return render(request, "ai_counselor.html")

    # POST -> return chatbot response / reset chat
    if request.method == "POST" and request.content_type == "application/json":
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError):
            body = {}
        if body.get("reset") is True:
            request.session["ai_chat_history"] = []
            return JsonResponse({"ok": True, "reply": "Chat cleared. How can I help with your career?"})

    user_msg = ""
    if request.content_type == "application/json":
        try:
            body = json.loads(request.body.decode("utf-8"))
            user_msg = (body.get("message") or "").strip()
        except Exception:
            user_msg = ""
    else:
        user_msg = (request.POST.get("message") or "").strip()

    if not user_msg:
        return JsonResponse({"ok": False, "error": "Message is required."}, status=400)

    # OPTIONAL: keep small chat history in session
    history = request.session.get("ai_chat_history", [])
    history.append({"role": "user", "content": user_msg})
    history = history[-8:]  # last 8 messages only
    request.session["ai_chat_history"] = history

    # Build prompt with history
    convo = ""
    for h in history:
        if h["role"] == "user":
            convo += f"Student: {h.get('content', h.get('text', ''))}\n"
        else:
            convo += f"Counselor: {h.get('content', h.get('text', ''))}\n"

    prompt = f"""
You are an AI Career Counselor for students.
Be helpful, short, practical, and friendly.

Conversation so far:
{convo}

Now answer the student's last question.
"""

    try:
        client = _get_gemini_client()
        if client is None:
            return JsonResponse({"ok": False, "error": "Gemini API key not configured."}, status=500)

        resp = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.35,
                max_output_tokens=800,
            ),
        )
        answer = (resp.text or "").strip()
        if not answer:
            answer = "I couldn’t generate a response. Please try again."

        history.append({"role": "assistant", "content": answer})
        history = history[-8:]
        request.session["ai_chat_history"] = history

        return JsonResponse({"ok": True, "reply": answer})

    except Exception as e:
        return JsonResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)



# -----------------------------
# JOBS / INTERNSHIPS HELPERS
# -----------------------------
def _to_list(v):
    """Normalize profile fields that may be list OR comma-separated string."""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        parts = re.split(r"[,;\n]+", v)
        return [p.strip() for p in parts if p.strip()]
    return [str(v).strip()] if str(v).strip() else []


def _job_portal_links(search_query: str, is_internship: bool = False):
    q = quote_plus((search_query or "").strip())
    # Internshala keyword search URL format: /internships/keywords-python/
    intern_kw = (search_query or "internship").strip().lower()
    intern_kw = re.sub(r"[^a-z0-9\s\-]", "", intern_kw)
    intern_kw = re.sub(r"\s+", "-", intern_kw).strip("-")
    if not intern_kw:
        intern_kw = "internship"

    return [
        {"site": "LinkedIn", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}"},
        {"site": "Indeed", "url": f"https://in.indeed.com/jobs?q={q}"},
        {"site": "Naukri", "url": f"https://www.naukri.com/{q.replace('+','-')}-jobs"},
        {"site": "Internshala", "url": f"https://internshala.com/internships/keywords-{intern_kw}/"},
    ]


def _fallback_jobs_internships(profile):
    skills = _to_list(getattr(profile, "skills", []))
    base = skills[0] if skills else "Software"

    return {
        "summary": f"Fallback suggestions (Gemini unavailable). Based on your skills: {', '.join(skills[:6]) or 'N/A'}",
        "job_roles": [
            {
                "title": f"{base} Developer (Entry Level)",
                "level": "Entry",
                "why_fit": "Good starting role to build real-world coding experience.",
                "must_have_skills": skills[:5] or ["Basics", "Problem solving"],
                "nice_to_have_skills": ["Git", "Projects", "Communication"],
                "search_query": f"{base} developer fresher jobs India"
            },
            {
                "title": "Data Analyst (Entry Level)",
                "level": "Entry",
                "why_fit": "Great if you like data, dashboards, and problem solving.",
                "must_have_skills": ["Excel", "SQL", "Basics of data"],
                "nice_to_have_skills": ["Power BI", "Python", "Statistics"],
                "search_query": "data analyst fresher jobs India"
            },
        ],
        "internships": [
            {
                "title": f"{base} Internship",
                "level": "Internship",
                "why_fit": "Helps you build portfolio + resume with real experience.",
                "must_have_skills": skills[:4] or ["Basics"],
                "nice_to_have_skills": ["GitHub", "Mini projects"],
                "search_query": f"{base} internship India"
            },
            {
                "title": "Data Analyst Internship",
                "level": "Internship",
                "why_fit": "Learn real datasets, reporting, and business problem solving.",
                "must_have_skills": ["Excel", "SQL"],
                "nice_to_have_skills": ["Power BI", "Python"],
                "search_query": "data analyst internship India"
            },
        ],
        "next_steps": [
            "Pick 1 target role + 1 internship role",
            "Update resume with 2 projects",
            "Apply to 10 jobs + 10 internships weekly",
            "Improve LinkedIn profile + GitHub portfolio"
        ],
    }


def _generate_jobs_internships_with_gemini(profile, last_attempt=None):
    # Extract profile info safely
    full_name = getattr(profile, "full_name", "") or ""
    skills = _to_list(getattr(profile, "skills", []))
    interests = _to_list(getattr(profile, "interests", []))
    strengths = _to_list(getattr(profile, "strengths", []))
    weaknesses = _to_list(getattr(profile, "weaknesses", []))
    career_goal = getattr(profile, "career_goal", "") or ""
    preferred_roles = _to_list(getattr(profile, "preferred_roles", []))

    # assessment context (optional)
    subj = getattr(last_attempt, "subject", "") if last_attempt else ""
    score = getattr(last_attempt, "score", None) if last_attempt else None
    total = getattr(last_attempt, "total", None) if last_attempt else None

    # IMPORTANT: escape braces in f-string using double {{ }}
    prompt = f"""
You are an AI Career Counselor + Job Search Assistant.

Based on the student's profile and latest assessment (if present),
suggest job roles and internships.

Student Profile:
Name: {full_name}
Skills: {skills}
Interests: {interests}
Strengths: {strengths}
Weaknesses: {weaknesses}
Career Goal: {career_goal}
Preferred Roles: {preferred_roles}

Latest Assessment (if any):
Subject: {subj}
Score: {score}/{total}

Return ONLY a JSON OBJECT (no markdown, no extra text) with keys:
summary,
job_roles (6-10 items),
internships (6-10 items),
next_steps (5-8 items).

Each job_roles / internships item must include:
title, level, why_fit,
must_have_skills (3-8),
nice_to_have_skills (2-8),
search_query (string).

Do NOT include URLs. Keep text practical and concise.
"""
    return _gemini_generate_json(prompt, want="object")


def _enrich_jobs_internships_with_links(data):
    data = data if isinstance(data, dict) else {}

    job_roles = data.get("job_roles") or []
    if isinstance(job_roles, list):
        for r in job_roles:
            if isinstance(r, dict):
                sq = r.get("search_query") or r.get("title") or "jobs"
                r["links"] = _job_portal_links(sq, is_internship=False)

    internships = data.get("internships") or []
    if isinstance(internships, list):
        for r in internships:
            if isinstance(r, dict):
                sq = r.get("search_query") or r.get("title") or "internship"
                r["links"] = _job_portal_links(sq, is_internship=True)

    return data


# -----------------------------
# VIEW: JOBS / INTERNSHIPS PAGE (single URL)
# -----------------------------
@login_required
def student_jobs(request):
    if not _ensure_student_role(request):
        messages.error(request, "Only students can access this page.")
        return redirect("student_dashboard")

    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.warning(request, "Please create your profile first.")
        return redirect("student_profile")

    last_attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=request.user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

    model_used = ""
    data = request.session.get("jobs_data")  # cached

    # Generate / Refresh
    if request.method == "POST":
        model_used = GEMINI_MODEL_NAME
        try:
            data = _generate_jobs_internships_with_gemini(profile, last_attempt=last_attempt)
        except Exception as e:
            messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Using fallback suggestions.")
            data = _fallback_jobs_internships(profile)
            model_used = "fallback"

        data = _enrich_jobs_internships_with_links(data)
        request.session["jobs_data"] = data
        request.session["jobs_model_used"] = model_used
        request.session["jobs_generated_at"] = timezone.now().isoformat()

        messages.success(request, "✅ Jobs & internships suggestions generated successfully!")

    else:
        model_used = request.session.get("jobs_model_used", "")

    return render(request, "student_jobs.html", {
        "profile": profile,
        "last_attempt": last_attempt,
        "data": data,
        "model_used": model_used,
        "generated_at": request.session.get("jobs_generated_at", ""),
    })

def parent_dashboard(request):
    return render(request, 'parent_dashboard.html', {'user': request.user})


@login_required
def counselor_dashboard(request):
    return render(request, 'counselor_dashboard.html', {'user': request.user})




def logout_view(request):
    logout(request)
    return redirect('login') 