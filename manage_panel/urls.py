from django.urls import path

from . import download_views, enrolment_views, views

app_name = "manage"

urlpatterns = [
    path("", views.OverviewView.as_view(), name="overview"),
    # Courses and modules
    path("courses/", views.CoursesView.as_view(), name="courses"),
    path("courses/new/", views.course_edit, name="course_new"),
    path("courses/<slug:slug>/edit/", views.course_edit, name="course_edit"),
    path("courses/<slug:slug>/reorder/", views.module_reorder, name="module_reorder"),
    path("courses/<slug:slug>/modules/new/", views.module_edit, name="module_new"),
    path(
        "courses/<slug:slug>/modules/<slug:module_slug>/",
        views.module_edit,
        name="module_edit",
    ),
    # Authors
    path("authors/", views.AuthorsView.as_view(), name="authors"),
    path("authors/new/", views.author_edit, name="author_new"),
    path("authors/<slug:slug>/edit/", views.author_edit, name="author_edit"),
    path("authors/<slug:slug>/delete/", views.author_delete, name="author_delete"),
    # Media library
    path("library/", views.LibraryView.as_view(), name="library"),
    path("library/upload/", views.library_upload, name="library_upload"),
    path("library/<int:pk>/delete/", views.library_delete, name="library_delete"),
    # Downloads
    path("downloads/", download_views.DownloadsView.as_view(), name="downloads"),
    path("downloads/new/", download_views.download_edit, name="download_new"),
    path("downloads/<slug:slug>/edit/", download_views.download_edit, name="download_edit"),
    path(
        "downloads/<slug:slug>/delete/", download_views.download_delete, name="download_delete"
    ),
    # Quizzes
    path("quizzes/", views.QuizIndexView.as_view(), name="quizzes"),
    path(
        "courses/<slug:slug>/modules/<slug:module_slug>/quiz/",
        views.quiz_edit,
        name="quiz_edit",
    ),
    path(
        "courses/<slug:slug>/modules/<slug:module_slug>/quiz/settings/",
        views.quiz_settings,
        name="quiz_settings",
    ),
    path(
        "courses/<slug:slug>/modules/<slug:module_slug>/quiz/questions/add/",
        views.question_add,
        name="question_add",
    ),
    path("questions/<int:pk>/delete/", views.question_delete, name="question_delete"),
    # Students and orders
    path("students/", views.StudentsView.as_view(), name="students"),
    path("students/new/", views.student_create, name="student_create"),
    path("students/<int:pk>/", views.StudentDetailView.as_view(), name="student_detail"),
    path("students/<int:pk>/edit/", views.student_edit, name="student_edit"),
    path("students/<int:pk>/access/", views.student_access, name="student_access"),
    path("students/<int:pk>/grant/", enrolment_views.student_grant, name="student_grant"),
    path("students/<int:pk>/revoke/", enrolment_views.student_revoke, name="student_revoke"),
    path(
        "students/<int:pk>/payment/",
        enrolment_views.student_record_payment,
        name="student_record_payment",
    ),
    path("orders/", views.OrdersView.as_view(), name="orders"),
    path("orders/new/", enrolment_views.order_create, name="order_create"),
    path("orders/<str:reference>/edit/", enrolment_views.order_edit, name="order_edit"),
    path("orders/<str:reference>/refund/", enrolment_views.order_refund, name="order_refund"),
    # Site content
    path("content/", views.ContentView.as_view(), name="content"),
    path("content/faqs/new/", views.faq_create, name="faq_create"),
    path("content/legal/<slug:slug>/", views.legal_edit, name="legal_edit"),
    # User messages
    path("messages/", views.MessagesView.as_view(), name="messages"),
    path("messages/<int:pk>/", views.MessageDetailView.as_view(), name="message_detail"),
    path("messages/<int:pk>/handled/", views.message_handled, name="message_handled"),
]
