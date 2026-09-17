# from django.conf import settings
# from django.conf.urls.static import static
# from django.urls import path, include


# from . import views

# urlpatterns = [
#     path('', views.index, name="home"),
#     path('register/', views.register_view, name='register'),
#     path('login/', views.login_view, name='login'),
#     path('about/', views.about, name='about'),
#     path('logout/', views.logout_view, name='logout'),
#     path('student_dashboard/', views.student_dashboard, name='student_dashboard'),
#     path('parent_dashboard/', views.parent_dashboard, name='parent_dashboard'),
#     path('counselor_dashboard/', views.counselor_dashboard, name='counselor_dashboard'),

#     path("student_profile/", views.student_profile, name="student_profile"),
#     path("student_profile_view/", views.student_profile_view, name="student_profile_view"),
#     path("student_profile_delete/", views.student_profile_delete, name="student_profile_delete"),

#     path("student_assessment/", views.student_assessment, name="student_assessment"),
#     path("student_assessment_result/<int:attempt_id>/", views.student_assessment_result, name="student_assessment_result"),
#     path("student_career/", views.student_career_home, name="student_career_home"),
#     path("student_career_report/<int:attempt_id>/", views.student_career_report, name="student_career_report"),

#     path("ai_counselor/", views.ai_counselor, name="ai_counselor"),

#     path("student_jobs/", views.student_jobs, name="student_jobs"),


#     path("parent_profile/", views.parent_profile, name="parent_profile"),
#     path("parent_dashboard/", views.parent_dashboard, name="parent_dashboard"), 

#     path("parent_progress_pdf/", views.parent_progress_pdf, name="parent_progress_pdf"),
    

# ]

from django.urls import path
from . import views

urlpatterns = [
    # Basic
    path("", views.index, name="home"),
    path("about/", views.about, name="about"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),


    path("admin_login/", views.admin_login, name="admin_login"),
    path("admin_dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin_logout/", views.admin_logout, name="admin_logout"),

    # Dashboards
    path("student_dashboard/", views.student_dashboard, name="student_dashboard"),
    path("parent_dashboard/", views.parent_dashboard, name="parent_dashboard"),
    path("counselor_dashboard/", views.counselor_dashboard, name="counselor_dashboard"),

    # Student Profile
    path("student_profile/", views.student_profile, name="student_profile"),
    path("student_profile_view/", views.student_profile_view, name="student_profile_view"),
    path("student_profile_delete/", views.student_profile_delete, name="student_profile_delete"),

    # Student Assessment + Career
    path("student_assessment/", views.student_assessment, name="student_assessment"),
    path("student_assessment_result/<int:attempt_id>/", views.student_assessment_result, name="student_assessment_result"),
    path("student_career/", views.student_career_home, name="student_career_home"),
    path("student_career_report/<int:attempt_id>/", views.student_career_report, name="student_career_report"),

    # AI Counselor (single URL GET page + POST JSON)
    path("ai_counselor/", views.ai_counselor, name="ai_counselor"),

    # Jobs & Internships
    path("student_jobs/", views.student_jobs, name="student_jobs"),

    # Parent
    path("parent_profile/", views.parent_profile, name="parent_profile"),
    path("parent_progress_pdf/", views.parent_progress_pdf, name="parent_progress_pdf"),

    # ✅ NEW: Parent can view child's assessment report + career recommendations
    path("parent/child/<int:child_id>/assessment/", views.parent_child_assessment, name="parent_child_assessment"),
    path("parent/child/<int:child_id>/career/", views.parent_child_career, name="parent_child_career"),
    # ✅ Parent downloads (per child)
    path("parent/child/<int:child_id>/assessment/pdf/", views.parent_child_assessment_pdf, name="parent_child_assessment_pdf"),
    path("parent/child/<int:child_id>/career/pdf/", views.parent_child_career_pdf, name="parent_child_career_pdf"),
    
    # ✅ Parent: Download FULL child report (Assessment + Career) in ONE PDF
    # path("parent/child/<int:child_id>/full_report_pdf/", views.parent_child_full_report_pdf, name="parent_child_full_report_pdf"),


    path("counselor_dashboard/", views.counselor_dashboard, name="counselor_dashboard"),

# ✅ NEW counselor student review pages
    path("counselor/student/<int:student_id>/profile/", views.counselor_student_profile, name="counselor_student_profile"),
    path("counselor/student/<int:student_id>/assessment/", views.counselor_student_assessment, name="counselor_student_assessment"),
    path("counselor/student/<int:student_id>/career/", views.counselor_student_career, name="counselor_student_career"),



]

