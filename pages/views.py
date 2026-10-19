from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.decorators import method_decorator
from django.utils.text import Truncator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView

from courses import views as course_views
from courses.access import course_queryset
from courses.markup import render_notes
from courses.models import Course

from . import seo
from .forms import ContactForm
from .models import Faq, LegalPage

HOW_IT_WORKS = (
    (
        "01",
        gettext_lazy("Watch"),
        gettext_lazy(
            "A short video lesson introduces each idea with examples on the bass and keyboard."
        ),
    ),
    (
        "02",
        gettext_lazy("Read"),
        gettext_lazy("Written notes and notation diagrams you can return to any time."),
    ),
    (
        "03",
        gettext_lazy("Listen"),
        gettext_lazy("Audio examples train your ear to recognise what you have just learned."),
    ),
    (
        "04",
        gettext_lazy("Quiz"),
        gettext_lazy("Answer every question correctly to unlock the next module."),
    ),
)

# The same lists the course page shows.
INCLUDES = course_views.INCLUDES
PAYMENT_CHIPS = course_views.PAYMENT_CHIPS


def primary_course():
    """The course the marketing pages are about."""
    return (
        course_queryset()
        .filter(status=Course.Status.PUBLISHED)
        .order_by(*Course.HOME_ORDERING)
        .first()
    )


def primary_author():
    """The author of the home page's course: the instructor the About page introduces."""
    course = (
        Course.published.select_related("author").order_by(*Course.HOME_ORDERING).first()
    )
    return course.author if course else None


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
            steps=HOW_IT_WORKS,
            includes=INCLUDES,
            payment_chips=PAYMENT_CHIPS,
            seo=seo.SEO(
                title=_("Learn to read, hear and understand music"),
                description=_(
                    "Foundations of Music — a nine-module online music theory course by "
                    "Tanveer Haque. Module 1 is free. Lifetime access for ৳3,500."
                ),
                canonical_path="/",
                schemas=schemas,
            ),
        )
        return context


class AboutView(FormView):
    """About the instructor, with the contact form on the same page."""

    template_name = "pages/about.html"
    form_class = ContactForm

    def get_success_url(self):
        return reverse("pages:about") + "#contact"

    def form_valid(self, form):
        message = form.save()
        self._notify(message)
        messages.success(
            self.request,
            _("Thank you — your message has been sent. We reply within two working days."),
        )
        return super().form_valid(form)

    def _notify(self, message):
        body = render_to_string("pages/email/contact_notification.txt", {"message": message})
        email = EmailMessage(
            subject=f"Website enquiry from {message.name}",
            body=body,
            to=[settings.SITE["email"]],
            reply_to=[message.email],
        )
        email.send(fail_silently=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        author = primary_author()
        name = author.name if author else settings.SITE["instructor"]
        if author and author.bio:
            description = Truncator(author.bio_text).chars(155)
        else:
            description = _(
                "%(name)s is an independent musician and music educator based in "
                "Dhaka, teaching bass and music theory to students of all ages."
            ) % {"name": name}
        person = (
            seo.author_person(author, description)
            if author
            else seo.person(name, description)
        )
        context.update(
            author=author,
            author_name=name,
            seo=seo.SEO(
                title=_("About %(name)s") % {"name": name},
                description=description,
                canonical_path=reverse("pages:about"),
                kind="profile",
                breadcrumbs=[seo.Breadcrumb(_("Home"), "/"), seo.Breadcrumb(_("About"))],
                schemas=[person],
            ),
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
