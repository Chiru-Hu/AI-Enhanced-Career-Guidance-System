from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Profile,CounselorNote

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'role']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            Profile.objects.create(user=user, role=self.cleaned_data['role'])
        return user


from .models import StudentProfile

class StudentProfileForm(forms.ModelForm):
    # user-friendly input fields for JSON
    skills_text = forms.CharField(required=False, help_text="Comma separated (e.g. Python, SQL, ML)")
    interests_text = forms.CharField(required=False, help_text="Comma separated (e.g. NLP, Data Science)")

    class Meta:
        model = StudentProfile
        fields = [
            "full_name", "phone", "email", "dob", "gender", "city", "state",
            "highest_education", "degree", "branch", "college", "year_of_study", "cgpa_or_percent",
            "strengths", "weaknesses", "career_goal", "preferred_roles",
            "linkedin_url", "github_url", "resume", "photo",
        ]
        widgets = {
            "dob": forms.DateInput(attrs={"type": "date"}),
            "strengths": forms.Textarea(attrs={"rows": 3}),
            "weaknesses": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Pre-fill comma text from JSON
        if self.instance and self.instance.pk:
            self.fields["skills_text"].initial = ", ".join(self.instance.skills or [])
            self.fields["interests_text"].initial = ", ".join(self.instance.interests or [])

    def clean_skills_text(self):
        txt = self.cleaned_data.get("skills_text", "")
        return [x.strip() for x in txt.split(",") if x.strip()]

    def clean_interests_text(self):
        txt = self.cleaned_data.get("interests_text", "")
        return [x.strip() for x in txt.split(",") if x.strip()]

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.skills = self.cleaned_data.get("skills_text", [])
        obj.interests = self.cleaned_data.get("interests_text", [])
        if commit:
            obj.save()
        return obj



class CounselorNoteForm(forms.ModelForm):
    class Meta:
        model = CounselorNote
        fields = ["title", "note", "rating", "next_action"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Title (optional)"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Write counseling notes / feedback..."}),
            "rating": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 5, "placeholder": "0-5"}),
            "next_action": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Next action for student..."}),
        }