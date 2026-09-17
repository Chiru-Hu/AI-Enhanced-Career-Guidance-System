from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("parent", "Parent"),
        ("counselor", "Counselor"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")

    # Basic
    full_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)

    # Academic
    highest_education = models.CharField(max_length=120, blank=True)   # e.g. 12th / Diploma / BSc / BE
    degree = models.CharField(max_length=120, blank=True)              # e.g. BE
    branch = models.CharField(max_length=120, blank=True)              # e.g. CS / IT
    college = models.CharField(max_length=200, blank=True)
    year_of_study = models.CharField(max_length=50, blank=True)        # e.g. 3rd year
    cgpa_or_percent = models.CharField(max_length=50, blank=True)

    # Career/AI inputs
    skills = models.JSONField(default=list, blank=True)     # stored as ["Python","SQL"]
    interests = models.JSONField(default=list, blank=True)  # stored as ["NLP","Data Science"]
    strengths = models.TextField(blank=True)
    weaknesses = models.TextField(blank=True)
    career_goal = models.CharField(max_length=200, blank=True)
    preferred_roles = models.CharField(max_length=250, blank=True)

    # Links / docs
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    resume = models.FileField(upload_to="resumes/", blank=True, null=True)
    photo = models.ImageField(upload_to="student_photos/", blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name or self.user.username


class StudentAssessmentAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assessment_attempts")

    # ✅ IMPORTANT: subject entered by student (fixes your 'subject' error)
    subject = models.CharField(max_length=120, blank=True, default="")

    interests_snapshot = models.JSONField(default=list, blank=True)
    skills_snapshot = models.JSONField(default=list, blank=True)

    # Gemini generated questions (list of dicts)
    questions = models.JSONField(default=list)

    # user answers like {"q1":"A","q2":"C"...}
    answers = models.JSONField(default=dict, blank=True)

    score = models.IntegerField(default=0)
    total = models.IntegerField(default=10)

    model_name = models.CharField(max_length=80, default="gemini-2.5-flash")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # ✅ store Career+Course recommendations JSON
    # this JSON can contain:
    # - career_paths (with apply_links + job_search_links)
    # - courses (with url)
    career_recommendations = models.JSONField(default=dict, blank=True)
    career_model_name = models.CharField(max_length=80, blank=True, default="")
    career_created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} attempt {self.id} ({self.score}/{self.total})"


class StudentCareerReport(models.Model):
    """
    Optional: use this if you want a separate DB table for reports.
    If you use only StudentAssessmentAttempt.career_recommendations, this model is not required.
    """
    attempt = models.OneToOneField(
        StudentAssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="career_report_obj",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    report = models.JSONField(default=dict)  # Gemini output JSON (same structure as career_recommendations)
    model_name = models.CharField(max_length=80, default="gemini-2.5-flash")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"CareerReport attempt {self.attempt.id} ({self.user.username})"


class ParentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="parent_profile")

    full_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    relation = models.CharField(max_length=40, blank=True)  # e.g. Father/Mother/Guardian

    # ✅ Link to children (students)
    children = models.ManyToManyField(User, related_name="linked_parents", blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name or self.user.username



class CounselorNote(models.Model):
    counselor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="counselor_notes")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="student_counselor_notes")

    title = models.CharField(max_length=150, blank=True)
    note = models.TextField()

    rating = models.IntegerField(default=0)  # 0–5 (optional)
    next_action = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Note({self.counselor.username} → {self.student.username}) {self.created_at}"