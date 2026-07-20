# import json
# import re
# from json import JSONDecodeError
# from urllib.parse import quote_plus

# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib import messages
# from django.contrib.auth.decorators import login_required
# from django.contrib.auth import authenticate, login, logout
# from django.utils import timezone

# from google import genai
# from google.genai import types

# from .models import Profile, StudentProfile, StudentAssessmentAttempt, StudentCareerReport
# from .forms import RegisterForm, StudentProfileForm


# # -----------------------------
# # GEMINI CONFIG (Python 3.9)
# # pip install --upgrade google-genai
# # -----------------------------
# GEMINI_API_KEY = "AIzaSyA1WlyzdGQu6VFc1d22Qh1DxowjKqaC7Io"
# GEMINI_MODEL_NAME = "gemini-2.5-flash"

# _GEMINI_CLIENT = None


# def _get_gemini_client():
#     global _GEMINI_CLIENT
#     if _GEMINI_CLIENT is not None:
#         return _GEMINI_CLIENT
#     if (not GEMINI_API_KEY) or ("PASTE_" in GEMINI_API_KEY):
#         return None
#     _GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
#     return _GEMINI_CLIENT


# # -----------------------------
# # JSON HELPERS (robust)
# # -----------------------------
# def _strip_json_fences(text: str) -> str:
#     text = (text or "").strip()
#     text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
#     text = re.sub(r"^```\s*", "", text)
#     text = re.sub(r"\s*```$", "", text)
#     return text.strip()


# def _extract_first_json_block(text: str) -> str:
#     """
#     Extract first valid JSON object/array from text using brace balancing.
#     Works even if Gemini adds extra text before/after.
#     """
#     s = _strip_json_fences(text)
#     if not s:
#         raise JSONDecodeError("Empty response", s, 0)

#     start = None
#     opener = None
#     for i, ch in enumerate(s):
#         if ch in "{[":
#             start = i
#             opener = ch
#             break
#     if start is None:
#         raise JSONDecodeError("No JSON start found", s, 0)

#     closer = "}" if opener == "{" else "]"
#     depth = 0
#     in_str = False
#     esc = False

#     for j in range(start, len(s)):
#         ch = s[j]

#         if in_str:
#             if esc:
#                 esc = False
#             elif ch == "\\":
#                 esc = True
#             elif ch == '"':
#                 in_str = False
#             continue

#         if ch == '"':
#             in_str = True
#             continue

#         if ch == opener:
#             depth += 1
#         elif ch == closer:
#             depth -= 1
#             if depth == 0:
#                 return s[start:j + 1]

#     raise JSONDecodeError("Unterminated JSON block", s, start)


# def _safe_json_loads(text: str):
#     raw = _strip_json_fences(text)

#     # 1) direct parse
#     try:
#         obj = json.loads(raw)
#         if isinstance(obj, str):  # double-encoded
#             obj = json.loads(obj)
#         return obj
#     except Exception:
#         pass

#     # 2) extract balanced JSON block
#     candidate = _extract_first_json_block(raw)
#     obj = json.loads(candidate)
#     if isinstance(obj, str):
#         obj = json.loads(obj)
#     return obj


# def _gemini_generate_json(prompt: str, want: str):
#     """
#     want: 'array' or 'object'
#     Robust JSON generation:
#     - first call -> parse
#     - if fails -> repair prompt -> parse again
#     """
#     client = _get_gemini_client()
#     if client is None:
#         raise RuntimeError("Gemini API key not configured.")

#     cfg = types.GenerateContentConfig(
#         temperature=0.25,
#         max_output_tokens=4096,
#         response_mime_type="application/json",
#         # IMPORTANT: no response_json_schema (avoids 400 INVALID_ARGUMENT)
#     )

#     resp = client.models.generate_content(
#         model=GEMINI_MODEL_NAME,
#         contents=prompt,
#         config=cfg,
#     )

#     try:
#         data = _safe_json_loads(resp.text or "")
#         if want == "object" and not isinstance(data, dict):
#             raise ValueError("Expected JSON object")
#         if want == "array" and not isinstance(data, list):
#             raise ValueError("Expected JSON array")
#         return data
#     except Exception:
#         repair_prompt = f"""
# Return ONLY VALID JSON {want.upper()}.
# No markdown. No explanation. No extra words.

# BROKEN OUTPUT:
# {resp.text}
# """
#         resp2 = client.models.generate_content(
#             model=GEMINI_MODEL_NAME,
#             contents=repair_prompt,
#             config=types.GenerateContentConfig(
#                 temperature=0.05,
#                 max_output_tokens=4096,
#                 response_mime_type="application/json",
#             ),
#         )
#         data2 = _safe_json_loads(resp2.text or "")
#         if want == "object" and not isinstance(data2, dict):
#             raise ValueError("Expected JSON object after repair")
#         if want == "array" and not isinstance(data2, list):
#             raise ValueError("Expected JSON array after repair")
#         return data2


# # -----------------------------
# # SMALL HELPERS
# # -----------------------------
# def _ensure_student_role(request) -> bool:
#     try:
#         return Profile.objects.get(user=request.user).role == "student"
#     except Profile.DoesNotExist:
#         return False


# def _job_links_for(career_title: str, skills=None, interests=None):
#     skills = skills or []
#     interests = interests or []
#     q = f"{career_title} " + " ".join((skills[:6] + interests[:4]))
#     qq = quote_plus(q.strip() or career_title)

#     return [
#         {"site": "LinkedIn Jobs", "url": f"https://www.linkedin.com/jobs/search/?keywords={qq}"},
#         {"site": "LinkedIn Easy Apply", "url": f"https://www.linkedin.com/jobs/search/?f_AL=true&keywords={qq}"},
#         {"site": "Indeed India", "url": f"https://in.indeed.com/jobs?q={qq}"},
#         {"site": "Naukri", "url": f"https://www.naukri.com/{quote_plus(career_title.lower())}-jobs"},
#         {"site": "Internshala", "url": f"https://internshala.com/internships/keywords-{quote_plus(career_title.lower())}/"},
#     ]


# def _course_link(search_query: str, platform: str):
#     q = quote_plus((search_query or "").strip())
#     p = (platform or "").lower()

#     if "coursera" in p:
#         return f"https://www.coursera.org/search?query={q}"
#     if "udemy" in p:
#         return f"https://www.udemy.com/courses/search/?q={q}"
#     if "youtube" in p:
#         return f"https://www.youtube.com/results?search_query={q}"
#     if "linkedin" in p:
#         return f"https://www.linkedin.com/learning/search?keywords={q}"

#     return f"https://www.google.com/search?q={q}"


# # -----------------------------
# # BASIC PAGES
# # -----------------------------
# def index(request):
#     return render(request, "index.html")


# def about(request):
#     return render(request, "about.html")


# def register_view(request):
#     if request.method == "POST":
#         form = RegisterForm(request.POST)
#         if form.is_valid():
#             form.save()
#             messages.success(request, "Account created successfully! You can now log in.")
#             return redirect("login")
#         messages.error(request, "Please correct the errors below.")
#     else:
#         form = RegisterForm()
#     return render(request, "register.html", {"form": form})


# def login_view(request):
#     if request.method == "POST":
#         username = request.POST.get("username")
#         password = request.POST.get("password")

#         user = authenticate(request, username=username, password=password)
#         if user is None:
#             messages.error(request, "Invalid username or password.")
#             return redirect("login")

#         login(request, user)

#         try:
#             role = Profile.objects.get(user=user).role
#         except Profile.DoesNotExist:
#             messages.error(request, "User role not found! Contact admin.")
#             return redirect("login")

#         if role == "student":
#             return redirect("student_dashboard")
#         if role == "parent":
#             return redirect("parent_dashboard")
#         if role == "counselor":
#             return redirect("counselor_dashboard")

#         messages.error(request, "Invalid role! Contact admin.")
#         return redirect("login")

#     return render(request, "login.html")


# def logout_view(request):
#     logout(request)
#     return redirect("login")


# # -----------------------------
# # DASHBOARDS
# # -----------------------------
# @login_required
# def student_dashboard(request):
#     student_profile = StudentProfile.objects.filter(user=request.user).first()

#     last_attempt = (
#         StudentAssessmentAttempt.objects
#         .filter(user=request.user, completed_at__isnull=False)
#         .order_by("-completed_at")
#         .first()
#     )

#     return render(request, "student_dashboard.html", {
#         "user": request.user,
#         "student_profile": student_profile,
#         "last_attempt": last_attempt,
#     })


# @login_required
# def parent_dashboard(request):
#     return render(request, "parent_dashboard.html", {"user": request.user})


# @login_required
# def counselor_dashboard(request):
#     return render(request, "counselor_dashboard.html", {"user": request.user})


# # -----------------------------
# # STUDENT PROFILE
# # -----------------------------
# @login_required
# def student_profile(request):
#     if not _ensure_student_role(request):
#         messages.error(request, "Only students can access Student Profile.")
#         return redirect("student_dashboard")

#     obj, _ = StudentProfile.objects.get_or_create(
#         user=request.user,
#         defaults={"email": request.user.email, "full_name": request.user.username}
#     )

#     if request.method == "POST":
#         form = StudentProfileForm(request.POST, request.FILES, instance=obj)
#         if form.is_valid():
#             form.save()
#             messages.success(request, "✅ Student profile saved successfully!")
#             return redirect("student_dashboard")

#         messages.error(request, "Please correct the errors below.")
#         for field, errs in form.errors.items():
#             for e in errs:
#                 messages.error(request, f"{field}: {e}")
#     else:
#         form = StudentProfileForm(instance=obj)

#     return render(request, "student_profile_form.html", {
#         "form": form,
#         "student_profile": obj,
#     })


# @login_required
# def student_profile_view(request):
#     profile = StudentProfile.objects.filter(user=request.user).first()
#     if not profile:
#         messages.warning(request, "Please create your profile first.")
#         return redirect("student_profile")
#     return render(request, "student_profile_view.html", {"profile": profile})


# @login_required
# def student_profile_delete(request):
#     if not _ensure_student_role(request):
#         messages.error(request, "Only students can access this.")
#         return redirect("student_dashboard")

#     profile = StudentProfile.objects.filter(user=request.user).first()
#     if not profile:
#         messages.warning(request, "No profile found to delete.")
#         return redirect("student_dashboard")

#     if request.method == "POST":
#         profile.delete()
#         messages.success(request, "✅ Profile deleted successfully!")
#         return redirect("student_dashboard")

#     return render(request, "student_profile_delete_confirm.html", {"profile": profile})


# # -----------------------------
# # ASSESSMENT
# # -----------------------------
# def _validate_questions(data):
#     if not isinstance(data, list) or len(data) != 10:
#         raise ValueError("Questions must be a JSON array of exactly 10 items.")

#     for i, q in enumerate(data, start=1):
#         if not isinstance(q, dict):
#             raise ValueError("Each question must be an object.")

#         q.setdefault("id", f"q{i}")
#         q.setdefault("topic", "General")
#         q.setdefault("difficulty", "easy")
#         q.setdefault("explanation", "")
#         q.setdefault("question", f"Question {i}")

#         opts = q.get("options", {})
#         if not isinstance(opts, dict):
#             opts = {}
#         for k in ["A", "B", "C", "D"]:
#             opts.setdefault(k, f"Option {k}")
#         q["options"] = opts

#         if q.get("correct_option") not in ["A", "B", "C", "D"]:
#             q["correct_option"] = "A"

#     return data


# def _fallback_questions(subject, interests):
#     topic = subject or (interests[0] if interests else "General Aptitude")
#     return [
#         {
#             "id": f"q{i}",
#             "question": f"[{topic}] Sample question {i}: Which option is most correct?",
#             "options": {"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"},
#             "correct_option": "A",
#             "topic": topic,
#             "difficulty": "easy",
#             "explanation": "Fallback question used when Gemini is unavailable."
#         }
#         for i in range(1, 11)
#     ]


# def _generate_10_questions(subject, interests, skills):
#     prompt = f"""
# Generate EXACTLY 10 MCQ questions for a student.

# Subject (entered by student): {subject}
# Student Interests: {interests}
# Student Skills: {skills}

# Return ONLY JSON ARRAY (no markdown, no extra text).
# Each item format:
# {{
#   "id":"q1",
#   "question":"...",
#   "options":{{"A":"...","B":"...","C":"...","D":"..."}},
#   "correct_option":"A",
#   "topic":"{subject}",
#   "difficulty":"easy",
#   "explanation":"1-2 lines"
# }}
# """
#     data = _gemini_generate_json(prompt, want="array")
#     return _validate_questions(data)


# @login_required
# def student_assessment(request):
#     profile = StudentProfile.objects.filter(user=request.user).first()
#     if not profile:
#         messages.warning(request, "Please create your profile first.")
#         return redirect("student_profile")

#     interests = profile.interests or []
#     skills = profile.skills or []

#     # 1) SUBMIT answers
#     if request.method == "POST" and request.POST.get("attempt_id"):
#         attempt_id = request.POST.get("attempt_id")
#         attempt = get_object_or_404(StudentAssessmentAttempt, id=attempt_id, user=request.user)

#         answers = {}
#         score = 0
#         for q in (attempt.questions or []):
#             qid = q.get("id")
#             selected = request.POST.get(qid)
#             if selected:
#                 answers[qid] = selected
#             if selected and selected == q.get("correct_option"):
#                 score += 1

#         attempt.answers = answers
#         attempt.score = score
#         attempt.completed_at = timezone.now()
#         attempt.save()

#         messages.success(request, f"✅ Assessment submitted successfully! Score: {score}/10")
#         return redirect("student_assessment_result", attempt_id=attempt.id)

#     # 2) GENERATE test
#     if request.method == "POST" and request.POST.get("generate_test") == "1":
#         subject = (request.POST.get("subject") or "").strip()
#         if not subject:
#             messages.error(request, "Please enter Subject to generate your test.")
#             return render(request, "student_assessment.html", {
#                 "student_profile": profile,
#                 "subject": "",
#                 "attempt": None,
#                 "questions": [],
#                 "model_used": "",
#             })

#         model_used = GEMINI_MODEL_NAME
#         try:
#             questions = _generate_10_questions(subject, interests, skills)
#         except Exception as e:
#             messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Loaded fallback assessment.")
#             questions = _fallback_questions(subject, interests)
#             model_used = "fallback"

#         # IMPORTANT: StudentAssessmentAttempt must have subject field in model + migrated
#         attempt = StudentAssessmentAttempt.objects.create(
#             user=request.user,
#             subject=subject,
#             interests_snapshot=interests,
#             skills_snapshot=skills,
#             questions=questions,
#             total=10,
#             model_name=model_used,
#         )

#         return render(request, "student_assessment.html", {
#             "student_profile": profile,
#             "subject": subject,
#             "attempt": attempt,
#             "questions": questions,
#             "model_used": model_used,
#         })

#     return render(request, "student_assessment.html", {
#         "student_profile": profile,
#         "subject": "",
#         "attempt": None,
#         "questions": [],
#         "model_used": "",
#     })


# @login_required
# def student_assessment_result(request, attempt_id):
#     attempt = get_object_or_404(StudentAssessmentAttempt, id=attempt_id, user=request.user)

#     answers = attempt.answers or {}
#     questions = []
#     for q in (attempt.questions or []):
#         q2 = dict(q)
#         qid = q2.get("id")
#         sel = answers.get(qid)
#         q2["selected"] = sel
#         q2["is_correct"] = (sel is not None and sel == q2.get("correct_option"))
#         questions.append(q2)

#     return render(request, "student_assessment_result.html", {
#         "attempt": attempt,
#         "questions": questions,
#     })


# # -----------------------------
# # CAREER & COURSES
# # -----------------------------
# def _fallback_career_report(profile, attempt):
#     subject = getattr(attempt, "subject", "") or "General"
#     pct = int((attempt.score / max(attempt.total or 10, 1)) * 100)

#     return {
#         "summary": f"Fallback recommendations. Subject: {subject}. Score {attempt.score}/{attempt.total} ({pct}%).",
#         "aptitude_level": "Beginner" if attempt.score <= 4 else ("Intermediate" if attempt.score <= 7 else "Advanced"),
#         "strengths": ["Learning mindset", "Consistency", "Basic aptitude"],
#         "improvement_areas": ["Practice more MCQs", "Concept clarity", "Time management"],
#         "top_career_paths": [
#             {
#                 "career": "Software Developer",
#                 "fit_score": 70,
#                 "why_fit": "Good for students who like coding and logic.",
#                 "roles": ["Intern", "Junior Developer"],
#                 "missing_skills": ["DSA", "Projects", "Git"],
#                 "projects": ["CRUD App", "API Project"],
#                 "roadmap_30_60_90": {
#                     "days_30": ["Revise basics", "Git practice", "1 mini project"],
#                     "days_60": ["DSA practice", "2 projects", "Resume update"],
#                     "days_90": ["Apply internships", "Mock interviews", "Portfolio polish"],
#                 },
#             },
#             {
#                 "career": "Data Analyst",
#                 "fit_score": 65,
#                 "why_fit": "Good if you like patterns and analysis.",
#                 "roles": ["Analyst Intern", "BI Trainee"],
#                 "missing_skills": ["SQL", "Excel/BI", "Dashboards"],
#                 "projects": ["Dashboard", "Case Study"],
#                 "roadmap_30_60_90": {
#                     "days_30": ["SQL basics", "Excel practice", "Mini dataset analysis"],
#                     "days_60": ["Dashboard project", "Resume", "Mock interview"],
#                     "days_90": ["Apply roles", "Portfolio", "Interview prep"],
#                 },
#             },
#             {
#                 "career": "Cyber Security (Starter)",
#                 "fit_score": 60,
#                 "why_fit": "Good if you like security & systems.",
#                 "roles": ["SOC Intern", "Security Trainee"],
#                 "missing_skills": ["Networking", "Linux", "Security basics"],
#                 "projects": ["Security notes", "CTF basics"],
#                 "roadmap_30_60_90": {
#                     "days_30": ["Networking basics", "Linux basics", "Security fundamentals"],
#                     "days_60": ["Try labs", "Build notes", "Small projects"],
#                     "days_90": ["Internship apply", "Portfolio", "Mock Q&A"],
#                 },
#             },
#         ],
#         "course_recommendations": [
#             {"title": "Python Basics", "platform": "YouTube", "level": "Beginner", "duration_weeks": 4,
#              "search_query": "Python basics for beginners", "why": "Foundation"},
#             {"title": "Aptitude Practice", "platform": "YouTube", "level": "Beginner", "duration_weeks": 3,
#              "search_query": "aptitude reasoning practice", "why": "Improve score"},
#             {"title": "Git & GitHub", "platform": "YouTube", "level": "Beginner", "duration_weeks": 2,
#              "search_query": "git github for beginners", "why": "Portfolio"},
#             {"title": "SQL Fundamentals", "platform": "Coursera", "level": "Beginner", "duration_weeks": 4,
#              "search_query": "SQL fundamentals beginner", "why": "Analytics"},
#             {"title": "Resume & Interview", "platform": "LinkedIn Learning", "level": "Beginner", "duration_weeks": 2,
#              "search_query": "resume building interview preparation", "why": "Job ready"},
#             {"title": "Mini Projects", "platform": "YouTube", "level": "Beginner", "duration_weeks": 6,
#              "search_query": "python mini projects portfolio", "why": "Show skills"},
#         ],
#         "next_actions": [
#             "Pick 1 path for 30 days",
#             "Solve 30-50 MCQs per week",
#             "Build 2 projects",
#             "Update LinkedIn + Resume",
#             "Apply weekly to internships/jobs",
#         ],
#     }


# def _normalize_report(report: dict, profile, attempt) -> dict:
#     """
#     Guarantee keys exist so template never breaks / never shows 'Not available'.
#     If Gemini output is missing important arrays, merge fallback values.
#     """
#     report = report if isinstance(report, dict) else {}

#     fb = _fallback_career_report(profile, attempt)

#     # basic keys
#     report.setdefault("summary", fb["summary"])
#     report.setdefault("aptitude_level", fb["aptitude_level"])

#     # arrays
#     for key in ["strengths", "improvement_areas", "top_career_paths", "course_recommendations", "next_actions"]:
#         val = report.get(key)
#         if not isinstance(val, list) or len(val) == 0:
#             report[key] = fb[key]

#     # normalize career paths structure
#     fixed_paths = []
#     for p in report.get("top_career_paths", []):
#         if not isinstance(p, dict):
#             continue
#         p.setdefault("career", "Career Path")
#         p.setdefault("fit_score", 60)
#         p.setdefault("why_fit", "")
#         p.setdefault("roles", [])
#         p.setdefault("missing_skills", [])
#         p.setdefault("projects", [])
#         rm = p.get("roadmap_30_60_90")
#         if not isinstance(rm, dict):
#             rm = {"days_30": [], "days_60": [], "days_90": []}
#         rm.setdefault("days_30", [])
#         rm.setdefault("days_60", [])
#         rm.setdefault("days_90", [])
#         if not isinstance(rm["days_30"], list): rm["days_30"] = []
#         if not isinstance(rm["days_60"], list): rm["days_60"] = []
#         if not isinstance(rm["days_90"], list): rm["days_90"] = []
#         p["roadmap_30_60_90"] = rm
#         fixed_paths.append(p)
#     report["top_career_paths"] = fixed_paths

#     # normalize course structure
#     fixed_courses = []
#     for c in report.get("course_recommendations", []):
#         if not isinstance(c, dict):
#             continue
#         c.setdefault("title", "Course")
#         c.setdefault("platform", "YouTube")
#         c.setdefault("level", "Beginner")
#         c.setdefault("duration_weeks", 4)
#         c.setdefault("search_query", c.get("title", "Course"))
#         c.setdefault("why", "")
#         fixed_courses.append(c)
#     report["course_recommendations"] = fixed_courses

#     return report


# def _generate_career_report(profile, attempt):
#     # ✅ IMPORTANT: escape braces inside f-string with double {{ }}
#     subject = getattr(attempt, "subject", "") or "General"

#     prompt = f"""
# You are an AI Career Counselor.

# Generate Career + Courses recommendations based on:
# - Student profile interests/skills
# - Assessment subject + score + weak areas.

# Student:
# Name: {profile.full_name}
# Interests: {profile.interests}
# Skills: {profile.skills}
# Strengths: {profile.strengths}
# Weaknesses: {profile.weaknesses}
# Career Goal: {profile.career_goal}
# Preferred Roles: {profile.preferred_roles}

# Assessment:
# Subject: {subject}
# Score: {attempt.score}/{attempt.total}

# Return ONLY JSON OBJECT (no markdown) with keys:
# summary, aptitude_level, strengths, improvement_areas,
# top_career_paths (3 items),
# course_recommendations (6-10 items),
# next_actions.

# Each top_career_paths item must include:
# career, fit_score, why_fit, roles, missing_skills, projects,
# roadmap_30_60_90 with keys:
# {{"days_30":[], "days_60":[], "days_90":[]}}

# Each course must include:
# title, platform, level, duration_weeks, search_query, why.
# """
#     data = _gemini_generate_json(prompt, want="object")
#     return data


# def _enrich_report_with_links(report, profile, attempt):
#     report = _normalize_report(report, profile, attempt)
#     skills = profile.skills or []
#     interests = profile.interests or []

#     # career paths: job/apply links
#     for p in report.get("top_career_paths", []):
#         if not isinstance(p, dict):
#             continue
#         career_title = p.get("career", "Career")
#         p["job_links"] = _job_links_for(career_title, skills, interests)
#         p["apply_links"] = [
#             {"title": "Apply on LinkedIn", "url": "https://www.linkedin.com/jobs/"},
#             {"title": "Apply on Indeed", "url": "https://in.indeed.com/"},
#             {"title": "Apply on Naukri", "url": "https://www.naukri.com/"},
#             {"title": "Apply on Internshala", "url": "https://internshala.com/"},
#         ]

#     # courses: direct links
#     for c in report.get("course_recommendations", []):
#         if not isinstance(c, dict):
#             continue
#         sq = c.get("search_query") or c.get("title") or ""
#         c["url"] = _course_link(sq, c.get("platform", ""))

#     return report


# @login_required
# def student_career_home(request):
#     last_attempt = (
#         StudentAssessmentAttempt.objects
#         .filter(user=request.user, completed_at__isnull=False)
#         .order_by("-completed_at")
#         .first()
#     )

#     if not last_attempt:
#         messages.warning(request, "⚠️ Please complete at least one assessment to unlock Career & Course Recommendations.")
#         return redirect("student_assessment")

#     return redirect("student_career_report", attempt_id=last_attempt.id)


# @login_required
# def student_career_report(request, attempt_id):
#     profile = StudentProfile.objects.filter(user=request.user).first()
#     if not profile:
#         messages.warning(request, "Please create your profile first.")
#         return redirect("student_profile")

#     attempt = get_object_or_404(StudentAssessmentAttempt, id=attempt_id, user=request.user)
#     if not attempt.completed_at:
#         messages.warning(request, "Please submit the assessment first.")
#         return redirect("student_assessment")

#     # Force regenerate: /career-report/<id>/?regen=1
#     force_regen = request.GET.get("regen") == "1"

#     existing = StudentCareerReport.objects.filter(attempt=attempt, user=request.user).first()
#     if existing and not force_regen:
#         report = _enrich_report_with_links(existing.report, profile, attempt)
#         return render(request, "student_career_report.html", {
#             "attempt": attempt,
#             "profile": profile,
#             "report": report,
#             "model_used": existing.model_name,
#         })

#     model_used = GEMINI_MODEL_NAME
#     try:
#         report_data = _generate_career_report(profile, attempt)
#     except Exception as e:
#         messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Loaded fallback recommendations.")
#         report_data = _fallback_career_report(profile, attempt)
#         model_used = "fallback"

#     report_data = _enrich_report_with_links(report_data, profile, attempt)

#     if existing:
#         existing.report = report_data
#         existing.model_name = model_used
#         existing.save(update_fields=["report", "model_name"])
#     else:
#         StudentCareerReport.objects.create(
#             attempt=attempt,
#             user=request.user,
#             report=report_data,
#             model_name=model_used,
#         )

#     # Optional cache in attempt (ONLY if these fields exist in your model)
#     if hasattr(attempt, "career_recommendations"):
#         attempt.career_recommendations = report_data
#         attempt.career_model_name = model_used
#         attempt.career_created_at = timezone.now()
#         attempt.save(update_fields=["career_recommendations", "career_model_name", "career_created_at"])

#     messages.success(request, "✅ Career & course recommendations generated successfully!")
#     return render(request, "student_career_report.html", {
#         "attempt": attempt,
#         "profile": profile,
#         "report": report_data,
#         "model_used": model_used,
#     })

# import json
# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.contrib.auth.decorators import login_required

# def _gemini_generate_text(prompt: str, temperature: float = 0.35) -> str:
#     client = _get_gemini_client()
#     if client is None:
#         raise RuntimeError("Gemini API key not configured.")

#     cfg = types.GenerateContentConfig(
#         temperature=temperature,
#         max_output_tokens=1200,
#     )
#     resp = client.models.generate_content(
#         model=GEMINI_MODEL_NAME,
#         contents=prompt,
#         config=cfg,
#     )
#     return (resp.text or "").strip()


# def _build_ai_counselor_prompt(profile, last_attempt, last_report, history, user_message: str) -> str:
#     history = history[-8:] if isinstance(history, list) else []

#     profile_ctx = {
#         "name": getattr(profile, "full_name", "") if profile else "",
#         "education": getattr(profile, "highest_education", "") if profile else "",
#         "degree": getattr(profile, "degree", "") if profile else "",
#         "branch": getattr(profile, "branch", "") if profile else "",
#         "year": getattr(profile, "year_of_study", "") if profile else "",
#         "cgpa": getattr(profile, "cgpa_or_percent", "") if profile else "",
#         "interests": (profile.interests if profile else []) or [],
#         "skills": (profile.skills if profile else []) or [],
#         "career_goal": getattr(profile, "career_goal", "") if profile else "",
#         "preferred_roles": getattr(profile, "preferred_roles", "") if profile else "",
#     }

#     attempt_ctx = {}
#     if last_attempt:
#         attempt_ctx = {
#             "subject": getattr(last_attempt, "subject", "") or "",
#             "score": f"{last_attempt.score}/{last_attempt.total}",
#         }

#     report_ctx = last_report if isinstance(last_report, dict) else {}

#     hist_lines = []
#     for m in history:
#         role = m.get("role")
#         content = (m.get("content") or "").strip()
#         if not content:
#             continue
#         hist_lines.append(("User: " if role == "user" else "Assistant: ") + content)

#     hist_block = "\n".join(hist_lines).strip()

#     prompt = f"""
# You are "AI CareerWise Counselor", a helpful AI counselor for students.

# Your tasks:
# - Answer student questions clearly and practically.
# - Give step-by-step guidance (career, courses, interview, skills, roadmap, projects).
# - If student asks "what should I do next", suggest actionable next steps.
# - If student hasn't done an assessment, advise them to complete it.

# Student Context (JSON):
# {json.dumps(profile_ctx, ensure_ascii=False)}

# Latest Assessment:
# {json.dumps(attempt_ctx, ensure_ascii=False)}

# Latest Career Report (may be empty JSON):
# {json.dumps(report_ctx, ensure_ascii=False)}

# Conversation History:
# {hist_block if hist_block else "(no history)"}

# Now respond to the student's new question:
# User: {user_message}

# Rules:
# - Be concise but complete.
# - Use bullet points when helpful.
# - Do NOT output markdown code fences.
# """
#     return prompt

# from django.http import JsonResponse
# import json

# @login_required
# def ai_counselor(request):
#     # GET -> open chat page
#     if request.method == "GET":
#         return render(request, "ai_counselor.html")

#     # POST -> return chatbot response
#     user_msg = ""
#     if request.content_type == "application/json":
#         try:
#             body = json.loads(request.body.decode("utf-8"))
#             user_msg = (body.get("message") or "").strip()
#         except Exception:
#             user_msg = ""
#     else:
#         user_msg = (request.POST.get("message") or "").strip()

#     if not user_msg:
#         return JsonResponse({"ok": False, "error": "Message is required."}, status=400)

#     # OPTIONAL: keep small chat history in session
#     history = request.session.get("ai_chat_history", [])
#     history.append({"role": "user", "text": user_msg})
#     history = history[-8:]  # last 8 messages only
#     request.session["ai_chat_history"] = history

#     # Build prompt with history
#     convo = ""
#     for h in history:
#         if h["role"] == "user":
#             convo += f"Student: {h['text']}\n"
#         else:
#             convo += f"Counselor: {h['text']}\n"

#     prompt = f"""
# You are an AI Career Counselor for students.
# Be helpful, short, practical, and friendly.

# Conversation so far:
# {convo}

# Now answer the student's last question.
# """

#     try:
#         client = _get_gemini_client()
#         if client is None:
#             return JsonResponse({"ok": False, "error": "Gemini API key not configured."}, status=500)

#         resp = client.models.generate_content(
#             model=GEMINI_MODEL_NAME,
#             contents=prompt,
#             config=types.GenerateContentConfig(
#                 temperature=0.35,
#                 max_output_tokens=800,
#             ),
#         )
#         answer = (resp.text or "").strip()
#         if not answer:
#             answer = "I couldn’t generate a response. Please try again."

#         history.append({"role": "assistant", "text": answer})
#         history = history[-8:]
#         request.session["ai_chat_history"] = history

#         return JsonResponse({"ok": True, "reply": answer})

#     except Exception as e:
#         return JsonResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)


# import re
# from urllib.parse import quote_plus
# from django.contrib import messages
# from django.contrib.auth.decorators import login_required
# from django.shortcuts import render, redirect
# from django.utils import timezone

# # -----------------------------
# # JOBS / INTERNSHIPS HELPERS
# # -----------------------------
# def _to_list(v):
#     """Normalize profile fields that may be list OR comma-separated string."""
#     if v is None:
#         return []
#     if isinstance(v, list):
#         return [str(x).strip() for x in v if str(x).strip()]
#     if isinstance(v, str):
#         parts = re.split(r"[,;\n]+", v)
#         return [p.strip() for p in parts if p.strip()]
#     return [str(v).strip()] if str(v).strip() else []


# def _job_portal_links(search_query: str, is_internship: bool = False):
#     q = quote_plus((search_query or "").strip())
#     # Internshala keyword search URL format: /internships/keywords-python/
#     intern_kw = (search_query or "internship").strip().lower()
#     intern_kw = re.sub(r"[^a-z0-9\s\-]", "", intern_kw)
#     intern_kw = re.sub(r"\s+", "-", intern_kw).strip("-")
#     if not intern_kw:
#         intern_kw = "internship"

#     return [
#         {"site": "LinkedIn", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}"},
#         {"site": "Indeed", "url": f"https://in.indeed.com/jobs?q={q}"},
#         {"site": "Naukri", "url": f"https://www.naukri.com/{q.replace('+','-')}-jobs"},
#         {"site": "Internshala", "url": f"https://internshala.com/internships/keywords-{intern_kw}/"},
#     ]


# def _fallback_jobs_internships(profile):
#     skills = _to_list(getattr(profile, "skills", []))
#     base = skills[0] if skills else "Software"

#     return {
#         "summary": f"Fallback suggestions (Gemini unavailable). Based on your skills: {', '.join(skills[:6]) or 'N/A'}",
#         "job_roles": [
#             {
#                 "title": f"{base} Developer (Entry Level)",
#                 "level": "Entry",
#                 "why_fit": "Good starting role to build real-world coding experience.",
#                 "must_have_skills": skills[:5] or ["Basics", "Problem solving"],
#                 "nice_to_have_skills": ["Git", "Projects", "Communication"],
#                 "search_query": f"{base} developer fresher jobs India"
#             },
#             {
#                 "title": "Data Analyst (Entry Level)",
#                 "level": "Entry",
#                 "why_fit": "Great if you like data, dashboards, and problem solving.",
#                 "must_have_skills": ["Excel", "SQL", "Basics of data"],
#                 "nice_to_have_skills": ["Power BI", "Python", "Statistics"],
#                 "search_query": "data analyst fresher jobs India"
#             },
#         ],
#         "internships": [
#             {
#                 "title": f"{base} Internship",
#                 "level": "Internship",
#                 "why_fit": "Helps you build portfolio + resume with real experience.",
#                 "must_have_skills": skills[:4] or ["Basics"],
#                 "nice_to_have_skills": ["GitHub", "Mini projects"],
#                 "search_query": f"{base} internship India"
#             },
#             {
#                 "title": "Data Analyst Internship",
#                 "level": "Internship",
#                 "why_fit": "Learn real datasets, reporting, and business problem solving.",
#                 "must_have_skills": ["Excel", "SQL"],
#                 "nice_to_have_skills": ["Power BI", "Python"],
#                 "search_query": "data analyst internship India"
#             },
#         ],
#         "next_steps": [
#             "Pick 1 target role + 1 internship role",
#             "Update resume with 2 projects",
#             "Apply to 10 jobs + 10 internships weekly",
#             "Improve LinkedIn profile + GitHub portfolio"
#         ],
#     }


# def _generate_jobs_internships_with_gemini(profile, last_attempt=None):
#     # Extract profile info safely
#     full_name = getattr(profile, "full_name", "") or ""
#     skills = _to_list(getattr(profile, "skills", []))
#     interests = _to_list(getattr(profile, "interests", []))
#     strengths = _to_list(getattr(profile, "strengths", []))
#     weaknesses = _to_list(getattr(profile, "weaknesses", []))
#     career_goal = getattr(profile, "career_goal", "") or ""
#     preferred_roles = _to_list(getattr(profile, "preferred_roles", []))

#     # assessment context (optional)
#     subj = getattr(last_attempt, "subject", "") if last_attempt else ""
#     score = getattr(last_attempt, "score", None) if last_attempt else None
#     total = getattr(last_attempt, "total", None) if last_attempt else None

#     # IMPORTANT: escape braces in f-string using double {{ }}
#     prompt = f"""
# You are an AI Career Counselor + Job Search Assistant.

# Based on the student's profile and latest assessment (if present),
# suggest job roles and internships.

# Student Profile:
# Name: {full_name}
# Skills: {skills}
# Interests: {interests}
# Strengths: {strengths}
# Weaknesses: {weaknesses}
# Career Goal: {career_goal}
# Preferred Roles: {preferred_roles}

# Latest Assessment (if any):
# Subject: {subj}
# Score: {score}/{total}

# Return ONLY a JSON OBJECT (no markdown, no extra text) with keys:
# summary,
# job_roles (6-10 items),
# internships (6-10 items),
# next_steps (5-8 items).

# Each job_roles / internships item must include:
# title, level, why_fit,
# must_have_skills (3-8),
# nice_to_have_skills (2-8),
# search_query (string).

# Do NOT include URLs. Keep text practical and concise.
# """
#     return _gemini_generate_json(prompt, want="object")


# def _enrich_jobs_internships_with_links(data):
#     data = data if isinstance(data, dict) else {}

#     job_roles = data.get("job_roles") or []
#     if isinstance(job_roles, list):
#         for r in job_roles:
#             if isinstance(r, dict):
#                 sq = r.get("search_query") or r.get("title") or "jobs"
#                 r["links"] = _job_portal_links(sq, is_internship=False)

#     internships = data.get("internships") or []
#     if isinstance(internships, list):
#         for r in internships:
#             if isinstance(r, dict):
#                 sq = r.get("search_query") or r.get("title") or "internship"
#                 r["links"] = _job_portal_links(sq, is_internship=True)

#     return data


# # -----------------------------
# # VIEW: JOBS / INTERNSHIPS PAGE (single URL)
# # -----------------------------
# @login_required
# def student_jobs(request):
#     if not _ensure_student_role(request):
#         messages.error(request, "Only students can access this page.")
#         return redirect("student_dashboard")

#     profile = StudentProfile.objects.filter(user=request.user).first()
#     if not profile:
#         messages.warning(request, "Please create your profile first.")
#         return redirect("student_profile")

#     last_attempt = (
#         StudentAssessmentAttempt.objects
#         .filter(user=request.user, completed_at__isnull=False)
#         .order_by("-completed_at")
#         .first()
#     )

#     model_used = ""
#     data = request.session.get("jobs_data")  # cached

#     # Generate / Refresh
#     if request.method == "POST":
#         model_used = GEMINI_MODEL_NAME
#         try:
#             data = _generate_jobs_internships_with_gemini(profile, last_attempt=last_attempt)
#         except Exception as e:
#             messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Using fallback suggestions.")
#             data = _fallback_jobs_internships(profile)
#             model_used = "fallback"

#         data = _enrich_jobs_internships_with_links(data)
#         request.session["jobs_data"] = data
#         request.session["jobs_model_used"] = model_used
#         request.session["jobs_generated_at"] = timezone.now().isoformat()

#         messages.success(request, "✅ Jobs & internships suggestions generated successfully!")

#     else:
#         model_used = request.session.get("jobs_model_used", "")

#     return render(request, "student_jobs.html", {
#         "profile": profile,
#         "last_attempt": last_attempt,
#         "data": data,
#         "model_used": model_used,
#         "generated_at": request.session.get("jobs_generated_at", ""),
#     })

# # def parent_dashboard(request):
# #     return render(request, 'parent_dashboard.html', {'user': request.user})

# # views.py
# import re
# from .models import Profile, StudentProfile, StudentAssessmentAttempt, StudentCareerReport, ParentProfile
# from django.contrib.auth.models import User
# import re
# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib import messages
# from django.contrib.auth.decorators import login_required

# def _ensure_parent_role(request) -> bool:
#     try:
#         return Profile.objects.get(user=request.user).role == "parent"
#     except Profile.DoesNotExist:
#         return False


# @login_required
# def parent_profile(request):
#     """
#     Parent creates/edits profile and links children using student usernames.
#     Only students added here will be visible on parent dashboard.
#     """
#     if not _ensure_parent_role(request):
#         messages.error(request, "Only parents can access Parent Profile.")
#         return redirect("login")

#     obj, _ = ParentProfile.objects.get_or_create(
#         user=request.user,
#         defaults={"email": request.user.email, "full_name": request.user.username}
#     )

#     # prefill children usernames
#     children_text_default = ", ".join([c.username for c in obj.children.all()])

#     if request.method == "POST":
#         obj.full_name = (request.POST.get("full_name") or "").strip()
#         obj.phone = (request.POST.get("phone") or "").strip()
#         obj.email = (request.POST.get("email") or "").strip()
#         obj.relation = (request.POST.get("relation") or "").strip()
#         obj.save()

#         # ✅ Link children by username
#         children_text = (request.POST.get("children_usernames") or "").strip()

#         # reset old links
#         obj.children.clear()

#         errors = []
#         if children_text:
#             usernames = [x.strip() for x in re.split(r"[,;\n]+", children_text) if x.strip()]
#             for uname in usernames:
#                 try:
#                     child_user = User.objects.get(username=uname)
#                 except User.DoesNotExist:
#                     errors.append(f"Child username not found: {uname}")
#                     continue

#                 # ensure child is student
#                 if not Profile.objects.filter(user=child_user, role="student").exists():
#                     errors.append(f"{uname} is not a Student account.")
#                     continue

#                 obj.children.add(child_user)

#         if errors:
#             for e in errors:
#                 messages.error(request, e)
#             messages.warning(request, "Profile saved, but some children were not linked.")
#         else:
#             messages.success(request, "✅ Parent profile saved successfully!")

#         return redirect("parent_dashboard")

#     return render(request, "parent_profile_form.html", {
#         "parent_profile": obj,
#         "children_text": children_text_default,
#     })


# @login_required
# def parent_dashboard(request):
#     """
#     Parent dashboard shows ONLY linked children progress.
#     """
#     if not _ensure_parent_role(request):
#         messages.error(request, "Only parents can access Parent Dashboard.")
#         return redirect("login")

#     parent_profile = ParentProfile.objects.filter(user=request.user).prefetch_related("children").first()

#     children_progress = []
#     children_count = 0

#     if parent_profile:
#         children = list(parent_profile.children.all())
#         children_count = len(children)

#         for child in children:
#             sp = StudentProfile.objects.filter(user=child).first()

#             last_attempt = (
#                 StudentAssessmentAttempt.objects
#                 .filter(user=child, completed_at__isnull=False)
#                 .order_by("-completed_at")
#                 .first()
#             )

#             score_pct = None
#             if last_attempt and last_attempt.total:
#                 score_pct = int((last_attempt.score / last_attempt.total) * 100)

#             # if career report exists, pick top career
#             top_career = ""
#             if last_attempt:
#                 report_obj = StudentCareerReport.objects.filter(user=child, attempt=last_attempt).first()
#                 if report_obj and isinstance(report_obj.report, dict):
#                     paths = report_obj.report.get("top_career_paths") or []
#                     if isinstance(paths, list) and len(paths) > 0 and isinstance(paths[0], dict):
#                         top_career = paths[0].get("career", "")

#             children_progress.append({
#                 "child_user": child,
#                 "student_profile": sp,
#                 "last_attempt": last_attempt,
#                 "score_pct": score_pct,
#                 "top_career": top_career,
#             })

#     return render(request, "parent_dashboard.html", {
#         "user": request.user,
#         "parent_profile": parent_profile,
#         "children_count": children_count,
#         "children_progress": children_progress,
#     })



# from io import BytesIO
# from reportlab.lib.pagesizes import A4
# from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
# from reportlab.lib.styles import getSampleStyleSheet
# from reportlab.lib import colors
# from django.http import HttpResponse

# def _ensure_parent_role(request) -> bool:
#     try:
#         return Profile.objects.get(user=request.user).role == "parent"
#     except Profile.DoesNotExist:
#         return False


# def _get_children_progress_for_parent(parent_user):
#     """
#     Returns list of dicts with child progress for ONLY linked children.
#     """
#     parent_profile = ParentProfile.objects.filter(user=parent_user).prefetch_related("children").first()
#     if not parent_profile:
#         return parent_profile, []

#     children_progress = []
#     for child in parent_profile.children.all():
#         sp = StudentProfile.objects.filter(user=child).first()

#         last_attempt = (
#             StudentAssessmentAttempt.objects
#             .filter(user=child, completed_at__isnull=False)
#             .order_by("-completed_at")
#             .first()
#         )

#         score_pct = None
#         if last_attempt and last_attempt.total:
#             score_pct = int((last_attempt.score / last_attempt.total) * 100)

#         top_career = ""
#         if last_attempt:
#             report_obj = StudentCareerReport.objects.filter(user=child, attempt=last_attempt).first()
#             if report_obj and isinstance(report_obj.report, dict):
#                 paths = report_obj.report.get("top_career_paths") or []
#                 if isinstance(paths, list) and paths and isinstance(paths[0], dict):
#                     top_career = paths[0].get("career", "")

#         children_progress.append({
#             "child_user": child,
#             "student_profile": sp,
#             "last_attempt": last_attempt,
#             "score_pct": score_pct,
#             "top_career": top_career,
#         })

#     return parent_profile, children_progress


# @login_required
# def parent_progress_pdf(request):
#     """
#     ✅ Parent downloads PDF report of ONLY their linked children's progress.
#     """
#     if not _ensure_parent_role(request):
#         messages.error(request, "Only parents can download this report.")
#         return redirect("login")

#     parent_profile, children_progress = _get_children_progress_for_parent(request.user)
#     if not parent_profile:
#         messages.warning(request, "Please create Parent Profile and link children first.")
#         return redirect("parent_profile")

#     # --- Build PDF ---
#     buffer = BytesIO()
#     doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
#     styles = getSampleStyleSheet()
#     story = []

#     title = f"AI CareerWise - Parent Progress Report"
#     story.append(Paragraph(title, styles["Title"]))
#     story.append(Paragraph(f"Parent: <b>{parent_profile.full_name or request.user.username}</b>", styles["Normal"]))
#     story.append(Paragraph(f"Linked Children: <b>{len(children_progress)}</b>", styles["Normal"]))
#     story.append(Spacer(1, 12))

#     # table header
#     data = [[
#         "Child", "Degree/Branch", "Latest Subject",
#         "Score", "Percent", "Top Career Suggestion", "Completed At"
#     ]]

#     for c in children_progress:
#         sp = c["student_profile"]
#         at = c["last_attempt"]

#         child_name = (sp.full_name if sp and sp.full_name else c["child_user"].username)
#         degree_branch = ""
#         if sp:
#             degree_branch = f"{sp.degree or ''} {sp.branch or ''}".strip()

#         subject = at.subject if at and getattr(at, "subject", None) else "-"
#         score = f"{at.score}/{at.total}" if at else "-"
#         pct = f"{c['score_pct']}%" if c["score_pct"] is not None else "-"
#         top_career = c["top_career"] or "-"
#         completed = str(at.completed_at) if at and at.completed_at else "-"

#         data.append([child_name, degree_branch or "-", subject, score, pct, top_career, completed])

#     table = Table(data, colWidths=[85, 85, 70, 45, 45, 120, 80])
#     table.setStyle(TableStyle([
#         ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
#         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
#         ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
#         ("FONTSIZE", (0, 0), (-1, -1), 8),
#         ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
#         ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7f9ff")),
#         ("VALIGN", (0, 0), (-1, -1), "TOP"),
#         ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef3ff")]),
#     ]))
#     story.append(table)
#     story.append(Spacer(1, 12))

#     story.append(Paragraph("<b>Notes:</b> This report shows progress only for children linked in Parent Profile.", styles["Normal"]))
#     doc.build(story)

#     pdf = buffer.getvalue()
#     buffer.close()

#     response = HttpResponse(content_type="application/pdf")
#     response["Content-Disposition"] = 'attachment; filename="parent_progress_report.pdf"'
#     response.write(pdf)
#     return response


import json
import re
from io import BytesIO
from json import JSONDecodeError
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from .models import CounselorNote
from .forms import CounselorNoteForm
from google import genai
from google.genai import types

from .forms import RegisterForm, StudentProfileForm
from .models import (
    Profile,
    StudentProfile,
    StudentAssessmentAttempt,
    StudentCareerReport,
    ParentProfile,   # ✅ make sure this model exists
)


# -----------------------------
# GEMINI CONFIG (Python 3.9)
# pip install --upgrade google-genai
# -----------------------------
GEMINI_API_KEY = "Gemini API KEY HERE"  # Replace with your actual Gemini API key
GEMINI_MODEL_NAME = "gemini-2.5-flash"

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

    try:
        obj = json.loads(raw)
        if isinstance(obj, str):
            obj = json.loads(obj)
        return obj
    except Exception:
        pass

    candidate = _extract_first_json_block(raw)
    obj = json.loads(candidate)
    if isinstance(obj, str):
        obj = json.loads(obj)
    return obj


def _gemini_generate_json(prompt: str, want: str):
    """
    want: 'array' or 'object'
    """
    client = _get_gemini_client()
    if client is None:
        raise RuntimeError("Gemini API key not configured.")

    cfg = types.GenerateContentConfig(
        temperature=0.25,
        max_output_tokens=4096,
        response_mime_type="application/json",
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
# ROLE HELPERS
# -----------------------------
def _ensure_student_role(request) -> bool:
    try:
        return Profile.objects.get(user=request.user).role == "student"
    except Profile.DoesNotExist:
        return False


def _ensure_parent_role(request) -> bool:
    try:
        return Profile.objects.get(user=request.user).role == "parent"
    except Profile.DoesNotExist:
        return False


# -----------------------------
# LINKS HELPERS
# -----------------------------
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
# ASSESSMENT (Student)
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

    # Submit answers
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

    # Generate test
    if request.method == "POST" and request.POST.get("generate_test") == "1":
        subject = (request.POST.get("subject") or "").strip()
        if not subject:
            messages.error(request, "Please enter Subject to generate your test.")
            return render(request, "student_assessment.html", {
                "student_profile": profile, "subject": "", "attempt": None,
                "questions": [], "model_used": "",
            })

        model_used = GEMINI_MODEL_NAME
        try:
            questions = _generate_10_questions(subject, interests, skills)
        except Exception as e:
            messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Loaded fallback assessment.")
            questions = _fallback_questions(subject, interests)
            model_used = "fallback"

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
# CAREER REPORT (Student)
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
            }
        ],
        "course_recommendations": [
            {"title": "Python Basics", "platform": "YouTube", "level": "Beginner", "duration_weeks": 4,
             "search_query": "Python basics for beginners", "why": "Foundation"},
        ],
        "next_actions": ["Take another assessment", "Build 2 projects", "Apply weekly"],
    }


def _normalize_report(report: dict, profile, attempt) -> dict:
    report = report if isinstance(report, dict) else {}
    fb = _fallback_career_report(profile, attempt)

    report.setdefault("summary", fb["summary"])
    report.setdefault("aptitude_level", fb["aptitude_level"])

    for key in ["strengths", "improvement_areas", "top_career_paths", "course_recommendations", "next_actions"]:
        val = report.get(key)
        if not isinstance(val, list) or len(val) == 0:
            report[key] = fb[key]

    # normalize career paths
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
        p["roadmap_30_60_90"] = rm
        fixed_paths.append(p)
    report["top_career_paths"] = fixed_paths

    # normalize courses
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
    return _gemini_generate_json(prompt, want="object")


def _enrich_report_with_links(report, profile, attempt):
    report = _normalize_report(report, profile, attempt)
    skills = profile.skills or []
    interests = profile.interests or []

    for p in report.get("top_career_paths", []):
        career_title = p.get("career", "Career")
        p["job_links"] = _job_links_for(career_title, skills, interests)
        p["apply_links"] = [
            {"title": "Apply on LinkedIn", "url": "https://www.linkedin.com/jobs/"},
            {"title": "Apply on Indeed", "url": "https://in.indeed.com/"},
            {"title": "Apply on Naukri", "url": "https://www.naukri.com/"},
            {"title": "Apply on Internshala", "url": "https://internshala.com/"},
        ]

    for c in report.get("course_recommendations", []):
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

    existing = StudentCareerReport.objects.filter(attempt=attempt, user=request.user).first()
    if existing:
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

    StudentCareerReport.objects.create(
        attempt=attempt,
        user=request.user,
        report=report_data,
        model_name=model_used,
    )

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


# -----------------------------
# AI COUNSELOR (Single URL)
# -----------------------------
def _gemini_generate_text(prompt: str, temperature: float = 0.35) -> str:
    client = _get_gemini_client()
    if client is None:
        raise RuntimeError("Gemini API key not configured.")
    resp = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=1200,
        ),
    )
    return (resp.text or "").strip()


@login_required
def ai_counselor(request):
    """
    GET  -> page
    POST -> JSON response (single endpoint)
    """
    if request.method == "GET":
        return render(request, "ai_counselor.html")

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        body = {}

    user_msg = (body.get("message") or "").strip()
    reset = bool(body.get("reset"))

    if reset:
        request.session["ai_chat_history"] = []
        return JsonResponse({"ok": True, "reply": "✅ Chat cleared. Ask your next question!"})

    if not user_msg:
        return JsonResponse({"ok": False, "error": "Message is required."}, status=400)

    # session history
    history = request.session.get("ai_chat_history", [])
    history.append({"role": "user", "content": user_msg})
    history = history[-8:]
    request.session["ai_chat_history"] = history

    # student context
    profile = StudentProfile.objects.filter(user=request.user).first()
    last_attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=request.user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )
    last_report = None
    if last_attempt:
        rep = StudentCareerReport.objects.filter(user=request.user, attempt=last_attempt).first()
        if rep and isinstance(rep.report, dict):
            last_report = rep.report

    hist_lines = []
    for m in history:
        if m.get("role") == "user":
            hist_lines.append("Student: " + (m.get("content") or ""))
        else:
            hist_lines.append("Counselor: " + (m.get("content") or ""))
    hist_block = "\n".join(hist_lines)

    prompt = f"""
You are an AI Career Counselor for students. Be practical and friendly.

Student Profile:
Name: {getattr(profile, "full_name", "") if profile else ""}
Skills: {getattr(profile, "skills", []) if profile else []}
Interests: {getattr(profile, "interests", []) if profile else []}
Career Goal: {getattr(profile, "career_goal", "") if profile else ""}

Latest Assessment:
Subject: {getattr(last_attempt, "subject", "") if last_attempt else ""}
Score: {f"{last_attempt.score}/{last_attempt.total}" if last_attempt else ""}

Latest Career Report (may be empty):
{json.dumps(last_report or {}, ensure_ascii=False)}

Conversation:
{hist_block}

Now answer:
Student: {user_msg}

Rules:
- No markdown code fences.
- Use bullet points when helpful.
"""
    try:
        reply = _gemini_generate_text(prompt, temperature=0.35)
        if not reply:
            reply = "I couldn't generate a response. Please try again."
    except Exception as e:
        reply = f"Error: {type(e).__name__}: {e}"

    history.append({"role": "assistant", "content": reply})
    history = history[-8:]
    request.session["ai_chat_history"] = history

    return JsonResponse({"ok": True, "reply": reply})


# -----------------------------
# JOBS / INTERNSHIPS (Student)
# -----------------------------
def _to_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        parts = re.split(r"[,;\n]+", v)
        return [p.strip() for p in parts if p.strip()]
    return [str(v).strip()] if str(v).strip() else []


def _job_portal_links(search_query: str):
    q = quote_plus((search_query or "").strip())
    kw = (search_query or "internship").strip().lower()
    kw = re.sub(r"[^a-z0-9\s\-]", "", kw)
    kw = re.sub(r"\s+", "-", kw).strip("-") or "internship"

    return [
        {"site": "LinkedIn", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}"},
        {"site": "Indeed", "url": f"https://in.indeed.com/jobs?q={q}"},
        {"site": "Naukri", "url": f"https://www.naukri.com/{q.replace('+','-')}-jobs"},
        {"site": "Internshala", "url": f"https://internshala.com/internships/keywords-{kw}/"},
    ]


def _fallback_jobs_internships(profile):
    skills = _to_list(getattr(profile, "skills", []))
    base = skills[0] if skills else "Software"
    return {
        "summary": f"Fallback suggestions (Gemini unavailable). Skills: {', '.join(skills[:6]) or 'N/A'}",
        "job_roles": [
            {
                "title": f"{base} Developer (Entry)",
                "level": "Entry",
                "why_fit": "Good starting role to build real-world experience.",
                "must_have_skills": skills[:5] or ["Basics", "Problem solving"],
                "nice_to_have_skills": ["Git", "Projects"],
                "search_query": f"{base} developer fresher jobs India",
            }
        ],
        "internships": [
            {
                "title": f"{base} Internship",
                "level": "Internship",
                "why_fit": "Build portfolio + resume.",
                "must_have_skills": skills[:4] or ["Basics"],
                "nice_to_have_skills": ["GitHub", "Mini projects"],
                "search_query": f"{base} internship India",
            }
        ],
        "next_steps": [
            "Pick 1 target role + 1 internship role",
            "Update resume with 2 projects",
            "Apply weekly",
        ],
    }


def _generate_jobs_internships_with_gemini(profile, last_attempt=None):
    full_name = getattr(profile, "full_name", "") or ""
    skills = _to_list(getattr(profile, "skills", []))
    interests = _to_list(getattr(profile, "interests", []))
    career_goal = getattr(profile, "career_goal", "") or ""
    preferred_roles = _to_list(getattr(profile, "preferred_roles", []))

    subj = getattr(last_attempt, "subject", "") if last_attempt else ""
    score = getattr(last_attempt, "score", None) if last_attempt else None
    total = getattr(last_attempt, "total", None) if last_attempt else None

    prompt = f"""
You are an AI Career Counselor + Job Search Assistant.

Student Profile:
Name: {full_name}
Skills: {skills}
Interests: {interests}
Career Goal: {career_goal}
Preferred Roles: {preferred_roles}

Latest Assessment:
Subject: {subj}
Score: {score}/{total}

Return ONLY JSON OBJECT:
summary,
job_roles (6-10),
internships (6-10),
next_steps (5-8).

Each job_roles/internships item:
title, level, why_fit, must_have_skills, nice_to_have_skills, search_query.
No URLs.
"""
    return _gemini_generate_json(prompt, want="object")


def _enrich_jobs_internships_with_links(data):
    data = data if isinstance(data, dict) else {}

    for r in (data.get("job_roles") or []):
        if isinstance(r, dict):
            sq = r.get("search_query") or r.get("title") or "jobs"
            r["links"] = _job_portal_links(sq)

    for r in (data.get("internships") or []):
        if isinstance(r, dict):
            sq = r.get("search_query") or r.get("title") or "internship"
            r["links"] = _job_portal_links(sq)

    return data


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

    model_used = request.session.get("jobs_model_used", "")
    data = request.session.get("jobs_data")

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

    return render(request, "student_jobs.html", {
        "profile": profile,
        "last_attempt": last_attempt,
        "data": data,
        "model_used": model_used,
        "generated_at": request.session.get("jobs_generated_at", ""),
    })


# -----------------------------
# PARENT MODULE
# -----------------------------
@login_required
def parent_profile(request):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can access Parent Profile.")
        return redirect("login")

    obj, _ = ParentProfile.objects.get_or_create(
        user=request.user,
        defaults={"email": request.user.email, "full_name": request.user.username}
    )

    children_text_default = ", ".join([c.username for c in obj.children.all()])

    if request.method == "POST":
        obj.full_name = (request.POST.get("full_name") or "").strip()
        obj.phone = (request.POST.get("phone") or "").strip()
        obj.email = (request.POST.get("email") or "").strip()
        obj.relation = (request.POST.get("relation") or "").strip()
        obj.save()

        children_text = (request.POST.get("children_usernames") or "").strip()
        obj.children.clear()

        errors = []
        if children_text:
            usernames = [x.strip() for x in re.split(r"[,;\n]+", children_text) if x.strip()]
            for uname in usernames:
                try:
                    child_user = User.objects.get(username=uname)
                except User.DoesNotExist:
                    errors.append(f"Child username not found: {uname}")
                    continue

                if not Profile.objects.filter(user=child_user, role="student").exists():
                    errors.append(f"{uname} is not a Student account.")
                    continue

                obj.children.add(child_user)

        if errors:
            for e in errors:
                messages.error(request, e)
            messages.warning(request, "Profile saved, but some children were not linked.")
        else:
            messages.success(request, "✅ Parent profile saved successfully!")

        return redirect("parent_dashboard")

    return render(request, "parent_profile_form.html", {
        "parent_profile": obj,
        "children_text": children_text_default,
    })


@login_required
def parent_dashboard(request):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can access Parent Dashboard.")
        return redirect("login")

    parent_profile_obj = ParentProfile.objects.filter(user=request.user).prefetch_related("children").first()

    children_progress = []
    children_count = 0

    if parent_profile_obj:
        children = list(parent_profile_obj.children.all())
        children_count = len(children)

        for child in children:
            sp = StudentProfile.objects.filter(user=child).first()
            last_attempt = (
                StudentAssessmentAttempt.objects
                .filter(user=child, completed_at__isnull=False)
                .order_by("-completed_at")
                .first()
            )

            score_pct = None
            if last_attempt and last_attempt.total:
                score_pct = int((last_attempt.score / last_attempt.total) * 100)

            top_career = ""
            if last_attempt:
                report_obj = StudentCareerReport.objects.filter(user=child, attempt=last_attempt).first()
                if report_obj and isinstance(report_obj.report, dict):
                    paths = report_obj.report.get("top_career_paths") or []
                    if isinstance(paths, list) and paths and isinstance(paths[0], dict):
                        top_career = paths[0].get("career", "")

            children_progress.append({
                "child_user": child,
                "student_profile": sp,
                "last_attempt": last_attempt,
                "score_pct": score_pct,
                "top_career": top_career,
            })

    return render(request, "parent_dashboard.html", {
    "user": request.user,
    "parent_profile": parent_profile_obj,
    "children_count": children_count,
    "children_progress": children_progress,
})


def _get_children_progress_for_parent(parent_user):
    parent_profile_obj = ParentProfile.objects.filter(user=parent_user).prefetch_related("children").first()
    if not parent_profile_obj:
        return parent_profile_obj, []

    children_progress = []
    for child in parent_profile_obj.children.all():
        sp = StudentProfile.objects.filter(user=child).first()
        last_attempt = (
            StudentAssessmentAttempt.objects
            .filter(user=child, completed_at__isnull=False)
            .order_by("-completed_at")
            .first()
        )
        score_pct = None
        if last_attempt and last_attempt.total:
            score_pct = int((last_attempt.score / last_attempt.total) * 100)

        top_career = ""
        if last_attempt:
            report_obj = StudentCareerReport.objects.filter(user=child, attempt=last_attempt).first()
            if report_obj and isinstance(report_obj.report, dict):
                paths = report_obj.report.get("top_career_paths") or []
                if isinstance(paths, list) and paths and isinstance(paths[0], dict):
                    top_career = paths[0].get("career", "")

        children_progress.append({
            "child_user": child,
            "student_profile": sp,
            "last_attempt": last_attempt,
            "score_pct": score_pct,
            "top_career": top_career,
        })

    return parent_profile_obj, children_progress


@login_required
def parent_progress_pdf(request):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can download this report.")
        return redirect("login")

    parent_profile_obj, children_progress = _get_children_progress_for_parent(request.user)
    if not parent_profile_obj:
        messages.warning(request, "Please create Parent Profile and link children first.")
        return redirect("parent_profile")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("AI CareerWise - Parent Progress Report", styles["Title"]))
    story.append(Paragraph(f"Parent: <b>{parent_profile_obj.full_name or request.user.username}</b>", styles["Normal"]))
    story.append(Paragraph(f"Linked Children: <b>{len(children_progress)}</b>", styles["Normal"]))
    story.append(Spacer(1, 12))

    data = [["Child", "Degree/Branch", "Latest Subject", "Score", "Percent", "Top Career", "Completed At"]]

    for c in children_progress:
        sp = c["student_profile"]
        at = c["last_attempt"]

        child_name = (sp.full_name if sp and sp.full_name else c["child_user"].username)
        degree_branch = (f"{(sp.degree or '')} {(sp.branch or '')}".strip() if sp else "") or "-"
        subject = getattr(at, "subject", "-") if at else "-"
        score = f"{at.score}/{at.total}" if at else "-"
        pct = f"{c['score_pct']}%" if c["score_pct"] is not None else "-"
        top = c["top_career"] or "-"
        completed = str(at.completed_at) if at and at.completed_at else "-"

        data.append([child_name, degree_branch, subject, score, pct, top, completed])

    table = Table(data, colWidths=[80, 90, 70, 45, 45, 110, 90])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef3ff")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Note:</b> This report shows only children linked in Parent Profile.", styles["Normal"]))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="parent_progress_report.pdf"'
    resp.write(pdf)
    return resp


@login_required
def parent_child_assessment(request, child_id):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can access this page.")
        return redirect("login")

    parent_profile_obj = ParentProfile.objects.filter(user=request.user).prefetch_related("children").first()
    if not parent_profile_obj or not parent_profile_obj.children.filter(id=child_id).exists():
        return HttpResponseForbidden("You are not allowed to view this student's report.")

    child_user = get_object_or_404(User, id=child_id)
    student_profile = StudentProfile.objects.filter(user=child_user).first()

    attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=child_user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

    if not attempt:
        messages.warning(request, "This student has not submitted any assessment yet.")
        return redirect("parent_dashboard")

    answers = attempt.answers or {}
    questions = []
    for q in (attempt.questions or []):
        q2 = dict(q)
        qid = q2.get("id")
        sel = answers.get(qid)
        q2["selected"] = sel
        q2["is_correct"] = (sel is not None and sel == q2.get("correct_option"))
        questions.append(q2)

    return render(request, "parent_child_assessment_result.html", {
        "child_user": child_user,
        "student_profile": student_profile,
        "attempt": attempt,
        "questions": questions,
    })


@login_required
def parent_child_career(request, child_id):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can access this page.")
        return redirect("login")

    parent_profile_obj = ParentProfile.objects.filter(user=request.user).prefetch_related("children").first()
    if not parent_profile_obj or not parent_profile_obj.children.filter(id=child_id).exists():
        return HttpResponseForbidden("You are not allowed to view this student's recommendations.")

    child_user = get_object_or_404(User, id=child_id)
    profile = StudentProfile.objects.filter(user=child_user).first()
    if not profile:
        messages.warning(request, "Student profile not found.")
        return redirect("parent_dashboard")

    attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=child_user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )
    if not attempt:
        messages.warning(request, "This student has not submitted any assessment yet.")
        return redirect("parent_dashboard")

    existing = StudentCareerReport.objects.filter(user=child_user, attempt=attempt).first()
    if existing:
        report = _enrich_report_with_links(existing.report, profile, attempt)
        return render(request, "parent_child_career_report.html", {
            "child_user": child_user,
            "profile": profile,
            "attempt": attempt,
            "report": report,
            "model_used": existing.model_name,
        })

    model_used = GEMINI_MODEL_NAME
    try:
        report_data = _generate_career_report(profile, attempt)
    except Exception as e:
        messages.error(request, f"Gemini error: {type(e).__name__}: {e}. Using fallback recommendations.")
        report_data = _fallback_career_report(profile, attempt)
        model_used = "fallback"

    report_data = _enrich_report_with_links(report_data, profile, attempt)

    StudentCareerReport.objects.create(
        attempt=attempt,
        user=child_user,
        report=report_data,
        model_name=model_used,
    )

    return render(request, "parent_child_career_report.html", {
        "child_user": child_user,
        "profile": profile,
        "attempt": attempt,
        "report": report_data,
        "model_used": model_used,
    })


from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from django.http import HttpResponse
from django.contrib.auth.models import User

# -----------------------------
# PARENT HELPERS
# -----------------------------
def _ensure_parent_role(request) -> bool:
    try:
        return Profile.objects.get(user=request.user).role == "parent"
    except Profile.DoesNotExist:
        return False

def _parent_has_child(parent_user, child_user) -> bool:
    # ParentProfile must exist and child must be linked
    return ParentProfile.objects.filter(user=parent_user, children=child_user).exists()

def _child_latest_attempt(child_user):
    return (
        StudentAssessmentAttempt.objects
        .filter(user=child_user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

def _build_questions_with_selected(attempt):
    answers = attempt.answers or {}
    qs = []
    for q in (attempt.questions or []):
        q2 = dict(q)
        qid = q2.get("id")
        sel = answers.get(qid)
        q2["selected"] = sel
        q2["is_correct"] = (sel is not None and sel == q2.get("correct_option"))
        qs.append(q2)
    return qs

def _attempt_subject(attempt):
    # subject may be blank -> infer from first question topic
    subj = getattr(attempt, "subject", "") or ""
    if subj.strip():
        return subj.strip()
    if attempt.questions and isinstance(attempt.questions, list) and len(attempt.questions) > 0:
        t = (attempt.questions[0] or {}).get("topic", "")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return "—"

# -----------------------------
# REPORT NORMALIZER (fix blank aptitude / missing arrays)
# -----------------------------
def _fallback_career_report_for_child(child_profile, attempt):
    subject = _attempt_subject(attempt)
    pct = int((attempt.score / max(attempt.total or 10, 1)) * 100)
    aptitude = "Beginner" if attempt.score <= 4 else ("Intermediate" if attempt.score <= 7 else "Advanced")

    return {
        "summary": f"Fallback recommendations. Subject: {subject}. Score {attempt.score}/{attempt.total} ({pct}%).",
        "aptitude_level": aptitude,
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
            "Solve 30–50 MCQs per week",
            "Build 2 projects",
            "Update LinkedIn + Resume",
            "Apply weekly to internships/jobs",
        ],
    }

def _normalize_child_report(report: dict, child_profile, attempt) -> dict:
    report = report if isinstance(report, dict) else {}
    fb = _fallback_career_report_for_child(child_profile, attempt)

    report.setdefault("summary", fb["summary"])
    report.setdefault("aptitude_level", fb["aptitude_level"])

    for key in ["strengths", "improvement_areas", "top_career_paths", "course_recommendations", "next_actions"]:
        v = report.get(key)
        if not isinstance(v, list) or len(v) == 0:
            report[key] = fb[key]

    # normalize career paths
    paths = []
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
        paths.append(p)
    report["top_career_paths"] = paths

    # normalize courses
    courses = []
    for c in report.get("course_recommendations", []):
        if not isinstance(c, dict):
            continue
        c.setdefault("title", "Course")
        c.setdefault("platform", "YouTube")
        c.setdefault("level", "Beginner")
        c.setdefault("duration_weeks", 4)
        c.setdefault("search_query", c.get("title", "Course"))
        c.setdefault("why", "")
        c["url"] = _course_link(c.get("search_query") or c.get("title") or "", c.get("platform") or "")
        courses.append(c)
    report["course_recommendations"] = courses

    return report

# -----------------------------
# PARENT -> VIEW CHILD ASSESSMENT
# -----------------------------
@login_required
def parent_child_assessment(request, child_id):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can access this page.")
        return redirect("login")

    child = get_object_or_404(User, id=child_id)

    if not _parent_has_child(request.user, child):
        messages.error(request, "This child is not linked to your Parent Profile.")
        return redirect("parent_dashboard")

    attempt = _child_latest_attempt(child)
    if not attempt:
        messages.warning(request, "No assessment submitted by this child yet.")
        return redirect("parent_dashboard")

    questions = _build_questions_with_selected(attempt)

    return render(request, "parent_child_assessment_result.html", {
        "child_user": child,
        "attempt": attempt,
        "subject": _attempt_subject(attempt),
        "questions": questions,
    })

# -----------------------------
# PARENT -> VIEW CHILD CAREER REPORT
# -----------------------------
@login_required
def parent_child_career(request, child_id):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can access this page.")
        return redirect("login")

    child = get_object_or_404(User, id=child_id)

    if not _parent_has_child(request.user, child):
        messages.error(request, "This child is not linked to your Parent Profile.")
        return redirect("parent_dashboard")

    attempt = _child_latest_attempt(child)
    if not attempt:
        messages.warning(request, "No assessment submitted by this child yet.")
        return redirect("parent_dashboard")

    child_profile = StudentProfile.objects.filter(user=child).first()
    if not child_profile:
        messages.warning(request, "Child profile not found.")
        return redirect("parent_dashboard")

    existing = StudentCareerReport.objects.filter(user=child, attempt=attempt).first()
    model_used = existing.model_name if existing else "—"

    # if missing report, you can generate on-demand OR show message
    if not existing:
        model_used = GEMINI_MODEL_NAME
        try:
            report_data = _generate_career_report(child_profile, attempt)  # your Gemini generator
        except Exception:
            report_data = _fallback_career_report_for_child(child_profile, attempt)
            model_used = "fallback"

        report_data = _normalize_child_report(report_data, child_profile, attempt)

        StudentCareerReport.objects.create(
            user=child,
            attempt=attempt,
            report=report_data,
            model_name=model_used,
        )
    else:
        report_data = _normalize_child_report(existing.report, child_profile, attempt)

    return render(request, "parent_child_career_report.html", {
        "child_user": child,
        "attempt": attempt,
        "subject": _attempt_subject(attempt),
        "report": report_data,
        "model_used": model_used,
    })

# -----------------------------
# PDF: CHILD ASSESSMENT
# -----------------------------
@login_required
def parent_child_assessment_pdf(request, child_id):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can download this report.")
        return redirect("login")

    child = get_object_or_404(User, id=child_id)
    if not _parent_has_child(request.user, child):
        messages.error(request, "This child is not linked to your Parent Profile.")
        return redirect("parent_dashboard")

    attempt = _child_latest_attempt(child)
    if not attempt:
        messages.warning(request, "No assessment submitted by this child yet.")
        return redirect("parent_dashboard")

    subject = _attempt_subject(attempt)
    questions = _build_questions_with_selected(attempt)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)

    styles = getSampleStyleSheet()
    title = styles["Title"]
    h = styles["Heading2"]
    h3 = styles["Heading3"]
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=10, leading=13)

    story = []
    story.append(Paragraph("AI CareerWise — Child Assessment Report", title))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Child:</b> {child.username}", small))
    story.append(Paragraph(f"<b>Subject:</b> {subject}", small))
    story.append(Paragraph(f"<b>Score:</b> {attempt.score}/{attempt.total}", small))
    story.append(Paragraph(f"<b>Completed At:</b> {attempt.completed_at or '-'}", small))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Questions & Answers", h))
    story.append(Spacer(1, 8))

    for idx, q in enumerate(questions, start=1):
        q_text = (q.get("question") or "")
        topic = (q.get("topic") or "")
        diff = (q.get("difficulty") or "")
        sel = q.get("selected") or "-"
        cor = q.get("correct_option") or "-"
        exp = q.get("explanation") or ""

        story.append(Paragraph(f"<b>{idx}.</b> {q_text}", small))
        story.append(Paragraph(f"<b>Topic:</b> {topic} &nbsp;&nbsp; <b>Difficulty:</b> {diff}", small))
        story.append(Paragraph(f"<b>Your Answer:</b> {sel} &nbsp;&nbsp; <b>Correct:</b> {cor}", small))
        if exp:
            story.append(Paragraph(f"<b>Explanation:</b> {exp}", small))
        story.append(Spacer(1, 10))

        if idx % 6 == 0:
            story.append(PageBreak())

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="child_{child.username}_assessment.pdf"'
    resp.write(pdf)
    return resp

# -----------------------------
# PDF: CHILD CAREER REPORT (PROPER DESIGN + WRAP)
# -----------------------------
@login_required
def parent_child_career_pdf(request, child_id):
    if not _ensure_parent_role(request):
        messages.error(request, "Only parents can download this report.")
        return redirect("login")

    child = get_object_or_404(User, id=child_id)
    if not _parent_has_child(request.user, child):
        messages.error(request, "This child is not linked to your Parent Profile.")
        return redirect("parent_dashboard")

    attempt = _child_latest_attempt(child)
    if not attempt:
        messages.warning(request, "No assessment submitted by this child yet.")
        return redirect("parent_dashboard")

    child_profile = StudentProfile.objects.filter(user=child).first()
    if not child_profile:
        messages.warning(request, "Child profile not found.")
        return redirect("parent_dashboard")

    subject = _attempt_subject(attempt)

    existing = StudentCareerReport.objects.filter(user=child, attempt=attempt).first()
    model_used = existing.model_name if existing else "—"

    if existing:
        report = _normalize_child_report(existing.report, child_profile, attempt)
    else:
        model_used = GEMINI_MODEL_NAME
        try:
            report = _generate_career_report(child_profile, attempt)
        except Exception:
            report = _fallback_career_report_for_child(child_profile, attempt)
            model_used = "fallback"
        report = _normalize_child_report(report, child_profile, attempt)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()

    title = styles["Title"]
    h = styles["Heading2"]
    h3 = styles["Heading3"]
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=10, leading=13)
    box = ParagraphStyle("box", parent=styles["Normal"], fontSize=10, leading=13, spaceAfter=6)

    story = []
    story.append(Paragraph("AI CareerWise — Child Career & Course Report", title))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Child:</b> {child.username}", small))
    story.append(Paragraph(f"<b>Subject:</b> {subject}", small))
    story.append(Paragraph(f"<b>Score:</b> {attempt.score}/{attempt.total}", small))
    story.append(Paragraph(f"<b>Model:</b> {model_used}", small))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Summary", h))
    story.append(Paragraph(report.get("summary", ""), box))
    story.append(Paragraph(f"<b>Aptitude Level:</b> {report.get('aptitude_level','')}", small))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Strengths", h3))
    for s in report.get("strengths", []):
        story.append(Paragraph(f"• {s}", small))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Improvement Areas", h3))
    for s in report.get("improvement_areas", []):
        story.append(Paragraph(f"• {s}", small))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Top Career Paths", h))
    story.append(Spacer(1, 6))

    for i, p in enumerate(report.get("top_career_paths", []), start=1):
        story.append(Paragraph(f"<b>{i}. {p.get('career','')}</b> (Fit: {p.get('fit_score',0)}%)", h3))
        story.append(Paragraph(p.get("why_fit", ""), small))

        roles = ", ".join(p.get("roles", []) or [])
        miss = ", ".join(p.get("missing_skills", []) or [])
        proj = ", ".join(p.get("projects", []) or [])

        if roles: story.append(Paragraph(f"<b>Roles:</b> {roles}", small))
        if miss: story.append(Paragraph(f"<b>Missing Skills:</b> {miss}", small))
        if proj: story.append(Paragraph(f"<b>Projects:</b> {proj}", small))

        rm = p.get("roadmap_30_60_90") or {}
        d30 = " • ".join(rm.get("days_30", []) or [])
        d60 = " • ".join(rm.get("days_60", []) or [])
        d90 = " • ".join(rm.get("days_90", []) or [])

        if d30: story.append(Paragraph(f"<b>30 Days:</b> {d30}", small))
        if d60: story.append(Paragraph(f"<b>60 Days:</b> {d60}", small))
        if d90: story.append(Paragraph(f"<b>90 Days:</b> {d90}", small))

        story.append(Spacer(1, 10))
        if i % 2 == 0:
            story.append(Spacer(1, 4))

    story.append(PageBreak())

    story.append(Paragraph("Course Recommendations", h))
    story.append(Spacer(1, 6))

    # Courses table (wrapped)
    rows = [["Title", "Platform", "Level", "Weeks", "Link"]]
    for c in report.get("course_recommendations", []):
        title_txt = c.get("title", "")
        platform = c.get("platform", "")
        level = c.get("level", "")
        weeks = str(c.get("duration_weeks", ""))
        url = c.get("url") or _course_link(c.get("search_query") or title_txt, platform)

        rows.append([
            Paragraph(title_txt, small),
            Paragraph(platform, small),
            Paragraph(level, small),
            Paragraph(weeks, small),
            Paragraph(url, ParagraphStyle("link", parent=small, textColor=colors.blue)),
        ])

    table = Table(rows, colWidths=[210, 85, 60, 40, 150])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef3ff")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Next Actions", h))
    for a in report.get("next_actions", []):
        story.append(Paragraph(f"• {a}", small))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="child_{child.username}_career_report.pdf"'
    resp.write(pdf)
    return resp



# ================================
# COUNSELOR MODULE
# ================================
from django.contrib.auth.models import User

def _ensure_counselor_role(request) -> bool:
    try:
        return Profile.objects.get(user=request.user).role == "counselor"
    except Profile.DoesNotExist:
        return False


def _is_student_user(user: User) -> bool:
    return Profile.objects.filter(user=user, role="student").exists()


@login_required
def counselor_dashboard(request):
    """
    Counselor dashboard:
    - shows all student records
    - quick links to profile / latest assessment / career report
    """
    if not _ensure_counselor_role(request):
        messages.error(request, "Only counselors can access Counselor Dashboard.")
        return redirect("login")

    # All students
    student_users = list(
        User.objects.filter(profile__role="student").order_by("username")
    )

    # StudentProfile map
    sp_qs = StudentProfile.objects.filter(user__in=student_users).select_related("user")
    sp_map = {sp.user_id: sp for sp in sp_qs}

    # Latest completed attempt per student (build dict in python)
    attempts_qs = (
        StudentAssessmentAttempt.objects
        .filter(user__in=student_users, completed_at__isnull=False)
        .order_by("user_id", "-completed_at")
    )
    last_attempt_map = {}
    for a in attempts_qs:
        if a.user_id not in last_attempt_map:
            last_attempt_map[a.user_id] = a

    # Career report map by attempt_id (fast check if report exists)
    attempt_ids = [a.id for a in last_attempt_map.values()]
    report_qs = StudentCareerReport.objects.filter(attempt_id__in=attempt_ids).select_related("attempt", "user")
    report_by_attempt = {r.attempt_id: r for r in report_qs}

    # Build UI rows
    students_data = []
    for u in student_users:
        sp = sp_map.get(u.id)
        last_attempt = last_attempt_map.get(u.id)
        score_pct = None
        if last_attempt and (last_attempt.total or 0) > 0:
            score_pct = int((last_attempt.score / last_attempt.total) * 100)

        report_exists = False
        if last_attempt:
            report_exists = (last_attempt.id in report_by_attempt)

        students_data.append({
            "user": u,
            "profile": sp,
            "last_attempt": last_attempt,
            "score_pct": score_pct,
            "report_exists": report_exists,
        })

    total_students = len(student_users)
    completed_assessments = len(last_attempt_map)
    reports_ready = sum(1 for x in students_data if x["report_exists"])
    reports_pending = completed_assessments - reports_ready

    return render(request, "counselor_dashboard.html", {
        "user": request.user,
        "students_data": students_data,
        "total_students": total_students,
        "completed_assessments": completed_assessments,
        "reports_ready": reports_ready,
        "reports_pending": max(reports_pending, 0),
    })





@login_required
def counselor_student_profile(request, student_id):
    if not _ensure_counselor_role(request):
        messages.error(request, "Only counselors can access this page.")
        return redirect("login")

    student_user = get_object_or_404(User, id=student_id)

    # ensure student
    if not Profile.objects.filter(user=student_user, role="student").exists():
        messages.error(request, "This user is not a student.")
        return redirect("counselor_dashboard")

    student_profile = StudentProfile.objects.filter(user=student_user).first()

    last_attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=student_user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

    score_pct = 0
    subject = "-"
    completed_at = None
    if last_attempt:
        subject = getattr(last_attempt, "subject", "") or "-"
        total = last_attempt.total or 10
        score_pct = int((last_attempt.score / max(total, 1)) * 100)
        completed_at = last_attempt.completed_at

    notes_qs = CounselorNote.objects.filter(
        counselor=request.user, student=student_user
    ).order_by("-created_at")

    if request.method == "POST":
        form = CounselorNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.counselor = request.user
            note.student = student_user
            note.save()
            messages.success(request, "✅ Notes/Feedback saved successfully!")
            return redirect("counselor_student_profile", student_id=student_user.id)
        else:
            messages.error(request, "Please correct the form errors.")
    else:
        form = CounselorNoteForm()

    return render(request, "counselor_student_profile.html", {
        "student_user": student_user,
        "student_profile": student_profile,
        "last_attempt": last_attempt,
        "score_pct": score_pct,          # ✅ NEW
        "latest_subject": subject,       # ✅ NEW
        "completed_at": completed_at,    # ✅ NEW
        "notes": notes_qs,
        "form": form,
    })


@login_required
def counselor_student_assessment(request, student_id):
    """Counselor can view student's latest assessment result (read-only)."""
    if not _ensure_counselor_role(request):
        messages.error(request, "Only counselors can access this page.")
        return redirect("login")

    student_user = get_object_or_404(User, id=student_id)
    if not _is_student_user(student_user):
        messages.error(request, "This user is not a student.")
        return redirect("counselor_dashboard")

    # allow ?attempt_id=xx else latest
    attempt_id = request.GET.get("attempt_id")
    if attempt_id:
        attempt = get_object_or_404(StudentAssessmentAttempt, id=attempt_id, user=student_user)
    else:
        attempt = (
            StudentAssessmentAttempt.objects
            .filter(user=student_user, completed_at__isnull=False)
            .order_by("-completed_at")
            .first()
        )

    if not attempt:
        messages.warning(request, "No completed assessment found for this student.")
        return redirect("counselor_dashboard")

    answers = attempt.answers or {}
    questions = []
    for q in (attempt.questions or []):
        if not isinstance(q, dict):
            continue
        q2 = dict(q)
        qid = q2.get("id")
        sel = answers.get(qid)
        q2["selected"] = sel
        q2["is_correct"] = (sel is not None and sel == q2.get("correct_option"))
        questions.append(q2)

    return render(request, "counselor_student_assessment.html", {
        "student_user": student_user,
        "attempt": attempt,
        "questions": questions,
    })




from django.contrib.auth.models import User

def _ensure_counselor_role(request) -> bool:
    try:
        return Profile.objects.get(user=request.user).role == "counselor"
    except Profile.DoesNotExist:
        return False


def _safe_report_dict(obj):
    """StudentCareerReport.report can be dict OR JSON string; normalize to dict."""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        try:
            return _safe_json_loads(obj)  # you already have _safe_json_loads in your file
        except Exception:
            return {}
    return {}


def _attempt_subject_fallback(attempt):
    """If subject is blank/missing, try to infer from questions topic."""
    subject = getattr(attempt, "subject", "") or ""
    if subject.strip():
        return subject.strip()

    qs = attempt.questions or []
    if isinstance(qs, list) and qs:
        q0 = qs[0]
        if isinstance(q0, dict):
            return (q0.get("topic") or "General").strip()
    return "General"


@login_required
def counselor_student_career(request, student_id):
    """
    Counselor view of student's career report:
    - shows existing StudentCareerReport (preferred)
    - ensures report is normalized so template always shows full details
    """
    if not _ensure_counselor_role(request):
        messages.error(request, "Only counselors can access this page.")
        return redirect("login")

    student_user = get_object_or_404(User, id=student_id)

    student_profile = StudentProfile.objects.filter(user=student_user).first()

    last_attempt = (
        StudentAssessmentAttempt.objects
        .filter(user=student_user, completed_at__isnull=False)
        .order_by("-completed_at")
        .first()
    )

    if not last_attempt:
        messages.warning(request, "No completed assessment found for this student yet.")
        return render(request, "counselor_student_career.html", {
            "student_user": student_user,
            "student_profile": student_profile,
            "attempt": None,
            "report": {},
            "model_used": "-",
        })

    # ✅ make sure subject is not blank
    if hasattr(last_attempt, "subject"):
        last_attempt.subject = _attempt_subject_fallback(last_attempt)

    report_obj = (
        StudentCareerReport.objects
        .filter(user=student_user, attempt=last_attempt)
        .order_by("-created_at")
        .first()
    )

    # ✅ If report not found for this attempt, fallback to student's latest report
    if not report_obj:
        report_obj = (
            StudentCareerReport.objects
            .filter(user=student_user)
            .order_by("-created_at")
            .first()
        )

    model_used = "-"
    report_data = {}

    if report_obj:
        model_used = report_obj.model_name or "-"
        report_data = _safe_report_dict(report_obj.report)

    # ✅ If still empty, try attempt cache
    if not report_data and hasattr(last_attempt, "career_recommendations"):
        report_data = _safe_report_dict(last_attempt.career_recommendations)
        if report_data:
            model_used = getattr(last_attempt, "career_model_name", "") or "cached"

    # ✅ Normalize + add links so template never shows empty blocks
    report_data = _enrich_report_with_links(report_data, student_profile, last_attempt)

    return render(request, "counselor_student_career.html", {
        "student_user": student_user,
        "student_profile": student_profile,
        "attempt": last_attempt,
        "report": report_data,
        "model_used": model_used,
    })
# views.py (ADD THIS)

from django.contrib.auth.models import User
from django.db.models import Q
from functools import wraps

# ✅ Hardcoded Admin Credentials (as you requested)
ADMIN_USERNAME = "Admin"
ADMIN_PASSWORD = "Admin@123"

def _admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("is_admin", False):
            messages.error(request, "Please login as Admin first.")
            return redirect("admin_login")
        return view_func(request, *args, **kwargs)
    return _wrapped


def admin_login(request):
    # if already logged in
    if request.session.get("is_admin", False):
        return redirect("admin_dashboard")

    if request.method == "POST":
        uname = (request.POST.get("username") or "").strip()
        pwd = (request.POST.get("password") or "").strip()

        if uname == ADMIN_USERNAME and pwd == ADMIN_PASSWORD:
            request.session["is_admin"] = True
            messages.success(request, "✅ Admin login successful!")
            return redirect("admin_dashboard")
        else:
            messages.error(request, "❌ Invalid admin username or password.")

    return render(request, "admin_login.html")





@_admin_required
def admin_dashboard(request):
    # Try optional models safely (won't crash if not present)
    try:
        from .models import ParentProfile
    except Exception:
        ParentProfile = None

    # -------------------------
    # Search (optional)
    # -------------------------
    q = (request.GET.get("q") or "").strip()

    # -------------------------
    # STUDENTS
    # -------------------------
    student_users_qs = Profile.objects.filter(role="student").select_related("user")
    student_user_ids = [p.user_id for p in student_users_qs]

    students = (
        StudentProfile.objects
        .filter(user_id__in=student_user_ids)
        .select_related("user")
        .order_by("-updated_at")
    )

    if q:
        students = students.filter(
            Q(user__username__icontains=q) |
            Q(full_name__icontains=q) |
            Q(email__icontains=q) |
            Q(degree__icontains=q) |
            Q(branch__icontains=q) |
            Q(city__icontains=q)
        )

    # last attempt per student (completed)
    attempts_qs = (
        StudentAssessmentAttempt.objects
        .filter(user_id__in=student_user_ids, completed_at__isnull=False)
        .order_by("-completed_at")
        .select_related("user")
    )
    last_attempt_by_user = {}
    for a in attempts_qs:
        if a.user_id not in last_attempt_by_user:
            last_attempt_by_user[a.user_id] = a

    # career report existence for last attempts
    last_attempt_ids = [a.id for a in last_attempt_by_user.values()]
    report_attempt_ids = set(
        StudentCareerReport.objects
        .filter(attempt_id__in=last_attempt_ids)
        .values_list("attempt_id", flat=True)
    )

    student_rows = []
    for sp in students:
        la = last_attempt_by_user.get(sp.user_id)
        subject = getattr(la, "subject", "") if la else ""
        score = f"{la.score}/{la.total}" if la else "-"
        pct = int((la.score / la.total) * 100) if (la and la.total) else 0

        student_rows.append({
            "id": sp.user_id,
            "username": sp.user.username,
            "full_name": sp.full_name or sp.user.username,
            "email": sp.email or sp.user.email,
            "phone": sp.phone,
            "degree": sp.degree,
            "branch": sp.branch,
            "year": sp.year_of_study,
            "city": sp.city,
            "state": sp.state,
            "skills": sp.skills or [],
            "interests": sp.interests or [],
            "subject": subject or "-",
            "score": score,
            "score_pct": pct,
            "completed_at": la.completed_at if la else None,
            "has_career_report": (la and la.id in report_attempt_ids),
            "last_attempt_id": la.id if la else None,
        })

    # -------------------------
    # PARENTS
    # -------------------------
    parent_users_qs = Profile.objects.filter(role="parent").select_related("user")
    parent_user_ids = [p.user_id for p in parent_users_qs]

    parents_rows = []
    if ParentProfile is not None:
        parents_qs = ParentProfile.objects.filter(user_id__in=parent_user_ids).select_related("user").prefetch_related("children")
        if q:
            parents_qs = parents_qs.filter(
                Q(user__username__icontains=q) |
                Q(full_name__icontains=q) |
                Q(email__icontains=q) |
                Q(phone__icontains=q)
            )
        for pp in parents_qs:
            children_list = list(pp.children.all())
            parents_rows.append({
                "id": pp.user_id,
                "username": pp.user.username,
                "full_name": pp.full_name or pp.user.username,
                "email": pp.email or pp.user.email,
                "phone": pp.phone,
                "relation": getattr(pp, "relation", ""),
                "children_count": len(children_list),
                "children_names": [c.username for c in children_list][:8],
            })
    else:
        # if parent profile model doesn't exist
        for pu in parent_users_qs:
            parents_rows.append({
                "id": pu.user_id,
                "username": pu.user.username,
                "full_name": pu.user.username,
                "email": pu.user.email,
                "phone": "",
                "relation": "",
                "children_count": 0,
                "children_names": [],
            })

    # -------------------------
    # COUNSELORS
    # -------------------------
    counselor_users_qs = Profile.objects.filter(role="counselor").select_related("user")
    counselors_rows = []
    for cu in counselor_users_qs:
        user = cu.user
        if q and (q.lower() not in (user.username or "").lower()) and (q.lower() not in (user.email or "").lower()):
            continue
        counselors_rows.append({
            "id": user.id,
            "username": user.username,
            "email": user.email,
        })

    # -------------------------
    # SUMMARY CARDS
    # -------------------------
    total_students = len(student_rows)
    total_parents = len(parents_rows)
    total_counselors = len(counselors_rows)
    total_completed_assessments = StudentAssessmentAttempt.objects.filter(completed_at__isnull=False).count()

    context = {
        "q": q,
        "total_students": total_students,
        "total_parents": total_parents,
        "total_counselors": total_counselors,
        "total_completed_assessments": total_completed_assessments,
        "student_rows": student_rows,
        "parents_rows": parents_rows,
        "counselors_rows": counselors_rows,
    }
    return render(request, "admin_dashboard.html", context)




def admin_logout(request):
    request.session.pop("is_admin", None)
    messages.success(request, "✅ Admin logged out.")
    return redirect("admin_login")

def logout_view(request):
    logout(request)
    return redirect('login') 