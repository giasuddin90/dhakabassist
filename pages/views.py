from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import translation
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView

from core.mail import send_email
from courses.access import course_queryset
from courses.markup import render_notes
from courses.models import Course

from . import seo
from .forms import ContactForm
from .models import Faq, LegalPage

# The home page's "Why this course?" and "Who is this course for?" lists.
BENEFITS = (
    gettext_lazy("A clear, step-by-step learning plan"),
    gettext_lazy("Lessons in English and Bangla"),
    gettext_lazy("26 practice exercises and 8 interactive quizzes"),
    gettext_lazy("Ear training and real music examples"),
    gettext_lazy("Covers beginner to intermediate music theory"),
    gettext_lazy("Learn on any device, at your own pace"),
    gettext_lazy("Lifetime access to lessons and study materials"),
    gettext_lazy("A community of musicians to learn with and ask questions"),
)

AUDIENCE = (
    gettext_lazy("Beginners learning music theory for the first time"),
    gettext_lazy("Self-taught musicians who want to fill gaps in their knowledge"),
    gettext_lazy("Performing musicians who want to understand music better"),
    gettext_lazy(
        "Songwriters and producers who want to improve their use of melody and harmony"
    ),
    gettext_lazy("Music students preparing for further study"),
)


def primary_course():
    """The course the marketing pages are about."""
    return (
        course_queryset()
        .filter(status=Course.Status.PUBLISHED)
        .order_by(*Course.HOME_ORDERING)
        .first()
    )


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = primary_course()
        faqs = list(Faq.objects.published())
        schemas = [seo.course_schema(course)] if course else []
        if faqs:
            schemas.append(seo.faq_schema(faqs))
        context.update(
            course=course,
            modules=course.module_list if course else [],
            faqs=faqs,
            benefits=BENEFITS,
            audience=AUDIENCE,
            seo=seo.SEO(
                title=_("Learn Music Theory the Practical Way"),
                description=_(
                    "Foundations of Music — a nine-module online music theory course by "
                    "Tanveer Haque. Module 1 is free. Lifetime access for ৳3,500."
                ),
                canonical_path="/",
                schemas=schemas,
            ),
        )
        return context


class ContactView(FormView):
    """The contact form."""

    template_name = "pages/contact.html"
    form_class = ContactForm

    def get_success_url(self):
        return reverse("pages:contact")

    def form_valid(self, form):
        message = form.save()
        self._notify(message)
        messages.success(
            self.request,
            _("Thank you — your message has been sent. We reply within two working days."),
        )
        return super().form_valid(form)

    def _notify(self, message):
        send_email(
            f"Website enquiry from {message.name}",
            "pages/email/contact_notification.txt",
            {"message": message},
            to=[settings.SITE["email"]],
            reply_to=[message.email],
            fail_silently=True,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo.SEO(
            title=_("Contact us"),
            description=_(
                "Questions about Foundations of Music, payment or your account? "
                "Send a message and we reply within two working days."
            ),
            canonical_path=reverse("pages:contact"),
            breadcrumbs=[seo.Breadcrumb(_("Home"), "/"), seo.Breadcrumb(_("Contact"))],
        )
        return context


class FaqView(TemplateView):
    template_name = "pages/faq.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        faqs = list(Faq.objects.published())
        context.update(
            faqs=faqs,
            seo=seo.SEO(
                title=_("Questions about the course"),
                description=_(
                    "Answers on prior knowledge, the free module, payment methods, "
                    "access and refunds for Foundations of Music."
                ),
                canonical_path=reverse("pages:faq"),
                breadcrumbs=[seo.Breadcrumb(_("Home"), "/"), seo.Breadcrumb(_("FAQ"))],
                schemas=[seo.faq_schema(faqs)] if faqs else [],
            ),
        )
        return context


class LegalPageView(DetailView):
    model = LegalPage
    template_name = "pages/legal.html"
    context_object_name = "page"

    def get_queryset(self):
        return LegalPage.objects.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.object
        context.update(
            body=render_notes(page.body_markdown),
            seo=seo.SEO(
                title=page.title,
                description=page.meta_description or page.title,
                canonical_path=page.get_absolute_url(),
                kind="article",
                breadcrumbs=[seo.Breadcrumb(_("Home"), "/"), seo.Breadcrumb(page.title)],
                schemas=[
                    seo.article_schema(
                        page.title,
                        page.meta_description or page.title,
                        page.get_absolute_url(),
                        page.updated_at,
                    )
                ],
            ),
        )
        return context


@method_decorator(cache_control(max_age=86400), name="dispatch")
class RobotsView(TemplateView):
    """robots.txt — keeps crawlers out of signed-in and payment paths."""

    template_name = "pages/robots.txt"
    content_type = "text/plain"

    def get_context_data(self, **kwargs):
        return {"base_url": settings.SITE["base_url"]}


@method_decorator(cache_control(max_age=86400), name="dispatch")
class LlmsTxtView(TemplateView):
    """llms.txt — a plain-text map of the site for AI answer engines."""

    template_name = "pages/llms.txt"
    content_type = "text/plain; charset=utf-8"

    def get(self, request, *args, **kwargs):
        # Outside the language prefix, so pin English rather than follow the
        # crawler's Accept-Language; the file points to the Bangla pages too.
        with translation.override("en"):
            response = super().get(request, *args, **kwargs)
            response.render()
        return response

    def get_context_data(self, **kwargs):
        course = primary_course()
        return {
            "site": settings.SITE,
            "course": course,
            "modules": course.module_list if course else [],
            "faqs": Faq.objects.published(),
            "base_url": settings.SITE["base_url"],
        }


@require_GET
def health(request):
    return HttpResponse("ok", content_type="text/plain")


def not_found(request, exception):
    context = {
        "seo": seo.noindex(_("Page not found"), _("The page you asked for does not exist.")),
        "course": primary_course(),
    }
    return render(request, "pages/404.html", context, status=404)


def server_error(request):
    return render(
        request,
        "pages/500.html",
        {"seo": seo.noindex(_("Something went wrong"))},
        status=500,
    )
