from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include


from . import views

urlpatterns = [
    path('', views.index, name="home"),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('about/', views.about, name='about'),
    path('logout/', views.logout_view, name='logout'),
    path('student_dashboard/', views.student_dashboard, name='student_dashboard'),
    path('parent_dashboard/', views.parent_dashboard, name='parent_dashboard'),
    path('counselor_dashboard/', views.counselor_dashboard, name='counselor_dashboard'),

    path("student_profile/", views.student_profile, name="student_profile"),
    path("student_profile_view/", views.student_profile_view, name="student_profile_view"),
    path("student_profile_delete/", views.student_profile_delete, name="student_profile_delete"),

    path("student_assessment/", views.student_assessment, name="student_assessment"),
    path("student_assessment_result/<int:attempt_id>/", views.student_assessment_result, name="student_assessment_result"),
    path("student_career/", views.student_career_home, name="student_career_home"),
    path("student_career_report/<int:attempt_id>/", views.student_career_report, name="student_career_report"),

    path("ai_counselor/", views.ai_counselor, name="ai_counselor"),

    path("student_jobs/", views.student_jobs, name="student_jobs"),
    

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
