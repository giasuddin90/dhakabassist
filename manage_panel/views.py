"""The administration panel at /manage/.

Staff-only. It covers the day-to-day work named in the brief — courses,
modules, lesson text, media, quizzes, students, access and orders — in the
layout of the supplied admin design. Structural changes nobody needs weekly
stay in the Django admin.
"""

from io import StringIO
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from courses.models import (
    Course,
    Enrollment,
    LibraryFile,
    Module,
    ModuleProgress,
    Question,
    Quiz,
)
from orders.models import Order
from pages.models import ContactMessage, Faq, LegalPage
from pages.seo import noindex

from .forms import (
    ChoiceFormSet,
    CourseForm,
    FaqForm,
    LegalPageForm,
    LibraryFilterForm,
    LibraryUploadForm,
    ModuleForm,
    QuestionForm,
    QuizForm,
    StudentFilterForm,
)

User = get_user_model()
RECENT_DAYS = 30


class StaffOnlyMixin(UserPassesTestMixin):
    """Staff only, and never a redirect loop for a signed-in non-staff user."""

    raise_exception = True

    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff


def staff_required(view):
    """Function-view counterpart to `StaffOnlyMixin`."""

    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_staff):
            raise Http404()
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def nav_counts():
    """Badge numbers beside the sidebar links."""
    return {
        "courses": Course.objects.count(),
        "library": LibraryFile.objects.count(),
        "students": User.objects.filter(is_staff=False).count(),
        "orders": Order.objects.filter(status=Order.Status.PENDING).count(),
        "messages": ContactMessage.objects.filter(is_handled=False).count(),
    }


class ManageBase(StaffOnlyMixin, TemplateView):
    section = ""
    heading = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            section=self.section,
            counts=nav_counts(),
            seo=noindex(self.heading or "Administration"),
        )
        return context


# -- Overview ---------------------------------------------------------------


class OverviewView(ManageBase):
    template_name = "manage_panel/overview.html"
    section = "overview"
    heading = "Overview"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        since = timezone.now() - timezone.timedelta(days=RECENT_DAYS)
        paid = Order.objects.filter(status=Order.Status.PAID)
        paid_recent = paid.filter(paid_at__gte=since)
        revenue = paid_recent.aggregate(total=Sum("amount"))["total"] or 0

        paying = (
            User.objects.filter(
                enrollments__is_active=True, is_staff=False
            )
            .distinct()
            .count()
        )
        free_accounts = (
            User.objects.filter(is_staff=False)
            .exclude(enrollments__is_active=True)
            .count()
        )
        total_accounts = paying + free_accounts
        conversion = round(paying / total_accounts * 100) if total_accounts else 0

        course = Course.objects.order_by("position", "title").first()
        finished = self._finished_count(course) if course else 0

        context.update(
            kpis=[
                {
                    "key": "Paying students",
                    "value": f"{paying:,}",
                    "detail": f"+{paid_recent.count()} in the last {RECENT_DAYS} days",
                },
                {
                    "key": "Free accounts",
                    "value": f"{free_accounts:,}",
                    "detail": f"Free module only · {conversion}% converted",
                },
                {
                    "key": "Revenue",
                    "value": f"৳{revenue:,.0f}",
                    "detail": f"{paid_recent.count()} paid orders in {RECENT_DAYS} days",
                },
                {
                    "key": "Finished the course",
                    "value": f"{finished:,}",
                    "detail": (
                        f"{round(finished / paying * 100)}% of paying students"
                        if paying
                        else "No paying students yet"
                    ),
                },
            ],
            recent_orders=Order.objects.select_related("student")[:5],
            funnel=self._funnel(course) if course else [],
            course=course,
            unhandled_messages=ContactMessage.objects.filter(is_handled=False)[:5],
        )
        return context

    @staticmethod
    def _finished_count(course):
        """Students who have completed every published module."""
        total = course.modules.filter(status=Module.Status.PUBLISHED).count()
        if not total:
            return 0
        return (
            User.objects.annotate(
                done=Count(
                    "module_progress",
                    filter=Q(
                        module_progress__module__course=course,
                        module_progress__completed_at__isnull=False,
                    ),
                    distinct=True,
                )
            )
            .filter(done__gte=total)
            .count()
        )

    @staticmethod
    def _funnel(course):
        """How many students have reached each module, widest bar first."""
        rows = (
            course.modules.filter(status=Module.Status.PUBLISHED)
            .annotate(reached=Count("progress", distinct=True))
            .order_by("position")
        )
        peak = max((row.reached for row in rows), default=0) or 1
        return [
            {
                "number": row.number,
                "title": row.title,
                "count": row.reached,
                "width": round(row.reached / peak * 100),
            }
            for row in rows
        ]


# -- Courses and modules ----------------------------------------------------


class CoursesView(ManageBase):
    template_name = "manage_panel/courses.html"
    section = "courses"
    heading = "Courses"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        courses = list(
            Course.objects.annotate(modules_count=Count("modules")).order_by(
                "position", "title"
            )
        )
        selected_slug = self.request.GET.get("course")
        selected = next(
            (c for c in courses if c.slug == selected_slug), courses[0] if courses else None
        )
        context.update(
            courses=courses,
            selected=selected,
            modules=(
                selected.modules.annotate(questions=Count("quiz__questions"))
                .prefetch_related("assets")
                .order_by("position", "number")
                if selected
                else []
            ),
        )
        return context


@staff_required
@require_POST
def load_demo_data(request):
    """Load the starter course, FAQs and legal pages into an empty site.

    Refused once any course exists: `seed_demo` updates in place, so running it
    on a site with edited content would overwrite those edits.
    """
    if Course.objects.exists():
        messages.error(request, "Demo data only loads into a site with no courses.")
    else:
        call_command("seed_demo", stdout=StringIO())
        messages.success(request, "Demo course, FAQs and legal pages loaded.")
    return redirect("manage:courses")


@staff_required
def course_edit(request, slug=None):
    """Create or edit a course's own fields."""
    course = get_object_or_404(Course, slug=slug) if slug else None
    form = CourseForm(request.POST or None, instance=course)
    if request.method == "POST" and form.is_valid():
        course = form.save()
        messages.success(request, f"“{course.title}” has been saved.")
        return redirect(f"{reverse('manage:courses')}?course={course.slug}")
    return render(
        request,
        "manage_panel/course_form.html",
        {
            "form": form,
            "course": course,
            "section": "courses",
            "counts": nav_counts(),
            "seo": noindex(course.title if course else "New course"),
        },
    )


@staff_required
def module_edit(request, slug, module_slug=None):
    """The module editor: details, notes, video, and files from the library."""
    course = get_object_or_404(Course, slug=slug)
    module = (
        get_object_or_404(
            course.modules.prefetch_related("quiz__questions__choices"), slug=module_slug
        )
        if module_slug
        else Module(course=course)
    )
    form = ModuleForm(request.POST or None, instance=module)

    if request.method == "POST" and form.is_valid():
        module = form.save(commit=False)
        module.course = course
        if not module.position:
            module.position = course.modules.count()
        module.save()
        messages.success(request, f"Module {module.number} has been saved.")
        return redirect(
            reverse("manage:module_edit", kwargs={"slug": course.slug, "module_slug": module.slug})
        )

    library = list(LibraryFile.objects.all())
    return render(
        request,
        "manage_panel/module_form.html",
        {
            "form": form,
            "course": course,
            "module": module,
            "library": library,
            "library_purposes": library_purposes(library),
            "linked_files": linked_library_files(module, library),
            "quiz": getattr(module, "quiz", None) if module.pk else None,
            "md_tools": ["H2", "B", "I", "List", "Link"],
            "section": "courses",
            "counts": nav_counts(),
            "seo": noindex(module.title or "New module"),
        },
    )


def library_purposes(files):
    """Each library material with how many of `files` it holds, for the filter."""
    return [
        {
            "value": value,
            "label": label,
            "total": sum(1 for item in files if item.purpose == value),
        }
        for value, label in LibraryFile.Purpose.choices
    ]


def linked_library_files(module, files):
    """The library files the module's saved notes or quiz link to."""
    if not module.pk:
        return []
    text = module.linkable_text
    return [item for item in files if item.link_prefix in text]


@staff_required
@require_POST
def module_reorder(request, slug):
    """Persist a drag-reordered module list."""
    course = get_object_or_404(Course, slug=slug)
    order = request.POST.getlist("module")
    lookup = {str(m.pk): m for m in course.modules.all()}
    changed = []
    for position, pk in enumerate(order):
        module = lookup.get(pk)
        if module and module.position != position:
            module.position = position
            changed.append(module)
    if changed:
        Module.objects.bulk_update(changed, ["position"])
    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"saved": len(changed)})
    return redirect(f"{reverse('manage:courses')}?course={course.slug}")


# -- Media library ----------------------------------------------------------


class LibraryView(ManageBase):
    """Every shared media file, with the Markdown to paste into lesson notes."""

    template_name = "manage_panel/library.html"
    section = "library"
    heading = "Media library"

    paginate_by = 12

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = LibraryFilterForm(self.request.GET)
        rows = library_rows(filters.filter(LibraryFile.objects.all()))
        usage = filters.cleaned_data.get("usage") if filters.is_valid() else ""
        if usage:
            want_used = usage == "used"
            rows = [row for row in rows if bool(row["modules"] or row["courses"]) == want_used]

        page = Paginator(rows, self.paginate_by).get_page(self.request.GET.get("page"))
        folder = filters.cleaned_data.get("folder", "") if filters.is_valid() else ""
        purpose = filters.cleaned_data.get("purpose", "") if filters.is_valid() else ""
        totals = dict(
            LibraryFile.objects.values_list("purpose").annotate(total=Count("id"))
        )
        context.update(
            purposes=[
                {"value": value, "label": label, "total": totals.get(value, 0)}
                for value, label in LibraryFile.Purpose.choices
            ],
            chosen_purpose=purpose,
            upload_url=library_upload_url(purpose, folder),
            page=page,
            page_range=page.paginator.get_elided_page_range(page.number, on_each_side=1),
            filters=filters,
            folders=LibraryFile.objects.values("folder")
            .annotate(total=Count("id"))
            .order_by("folder"),
            chosen=folder,
            query=filters.cleaned_data.get("q", "") if filters.is_valid() else "",
            form=LibraryUploadForm(initial=upload_initial(self.request.GET)),
        )
        return context


def library_rows(files):
    """Each file with the modules (notes or quiz) and courses that link to it.

    Shown so the administrator sees what would break before removing a file.
    The course has a handful of modules, so matching in Python is cheaper
    than one query per file.
    """
    modules = list(
        Module.objects.select_related("course").prefetch_related("quiz__questions__choices")
    )
    courses = list(Course.objects.only("title", "slug", "description"))
    rows = []
    for item in files:
        prefix = item.link_prefix
        rows.append(
            {
                "file": item,
                "modules": [m for m in modules if prefix in m.linkable_text],
                "courses": [c for c in courses if prefix in c.description],
            }
        )
    return rows


def upload_initial(params):
    """Start an upload in the material and folder the administrator was viewing."""
    initial = {}
    if params.get("purpose") in LibraryFile.Purpose.values:
        initial["purpose"] = params["purpose"]
    if params.get("folder"):
        initial["folder"] = params["folder"]
    return initial


def library_upload_url(purpose, folder):
    """The upload page, set to the material and folder being viewed."""
    params = {key: value for key, value in (("purpose", purpose), ("folder", folder)) if value}
    url = reverse("manage:library_upload")
    return f"{url}?{urlencode(params)}" if params else url


def library_redirect(request):
    """Back to the library, on the folder the administrator was viewing."""
    folder = request.POST.get("next_folder", "")
    url = reverse("manage:library")
    return redirect(f"{url}?{urlencode({'folder': folder})}" if folder else url)


class LibraryUploadView(ManageBase):
    """Its own page, so the list keeps the full width for finding files."""

    template_name = "manage_panel/library_upload.html"
    section = "library"
    heading = "Upload to the media library"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", LibraryUploadForm(initial=upload_initial(self.request.GET)))
        context["folders"] = (
            LibraryFile.objects.values_list("folder", flat=True).distinct().order_by("folder")
        )
        return context

    def post(self, request, *args, **kwargs):
        """Save the files and show them; on an error, keep the form with its messages."""
        form = LibraryUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        saved = form.save()
        messages.success(
            request, f"{len(saved)} file{pluralize(len(saved))} added to “{saved[0].folder}”."
        )
        # Land on the new files: their folder, newest first.
        query = urlencode(
            {"purpose": saved[0].purpose, "folder": saved[0].folder, "sort": "newest"}
        )
        return redirect(f"{reverse('manage:library')}?{query}")


# Wrapped like the other library actions: a non-staff visitor gets a 404,
# so the upload page is not advertised by a 403.
library_upload = staff_required(LibraryUploadView.as_view())


@staff_required
@require_POST
def library_delete(request, pk):
    """Remove a library file and its stored bytes."""
    item = get_object_or_404(LibraryFile, pk=pk)
    title = item.title
    item.file.delete(save=False)
    item.delete()
    messages.success(request, f"“{title}” has been removed.")
    return library_redirect(request)


# -- Quizzes ----------------------------------------------------------------


@staff_required
def quiz_edit(request, slug, module_slug):
    """The quiz editor: one question at a time, with its four options."""
    module = get_object_or_404(
        Module.objects.select_related("course"), course__slug=slug, slug=module_slug
    )
    quiz, _ = Quiz.objects.get_or_create(module=module)
    questions = list(quiz.questions.prefetch_related("choices"))

    if not questions:
        question = Question.objects.create(quiz=quiz, text="New question", position=0)
        for index, letter in enumerate("ABCD"):
            question.choices.create(text=f"Option {letter}", position=index)
        return redirect(request.path)

    try:
        index = max(0, min(int(request.GET.get("q", 1)) - 1, len(questions) - 1))
    except ValueError:
        index = 0
    question = questions[index]

    if request.method == "POST":
        form = QuestionForm(request.POST, instance=question)
        formset = ChoiceFormSet(request.POST, instance=question)
        if form.is_valid() and formset.is_valid():
            formset.save()
            form.save()
            messages.success(request, f"Question {index + 1} has been saved.")
            return redirect(f"{request.path}?q={index + 1}")
    else:
        form = QuestionForm(instance=question)
        formset = ChoiceFormSet(instance=question)

    # The formset and the `correct` radio both iterate the question's choices
    # in the same order, so zipping them gives one row per option: its text
    # input beside its "this is the right answer" radio.
    option_rows = list(zip(formset.forms, form["correct"]))

    return render(
        request,
        "manage_panel/quiz_form.html",
        {
            "module": module,
            "course": module.course,
            "quiz": quiz,
            "quiz_form": QuizForm(instance=quiz),
            "questions": questions,
            "question": question,
            "question_index": index,
            "form": form,
            "formset": formset,
            "option_rows": option_rows,
            "section": "quiz",
            "counts": nav_counts(),
            "seo": noindex(quiz.display_title),
        },
    )


@staff_required
@require_POST
def quiz_settings(request, slug, module_slug):
    module = get_object_or_404(Module, course__slug=slug, slug=module_slug)
    quiz, _ = Quiz.objects.get_or_create(module=module)
    form = QuizForm(request.POST, instance=quiz)
    if form.is_valid():
        form.save()
        messages.success(request, "Quiz rules have been saved.")
    return redirect(
        reverse("manage:quiz_edit", kwargs={"slug": slug, "module_slug": module_slug})
    )


@staff_required
@require_POST
def question_add(request, slug, module_slug):
    module = get_object_or_404(Module, course__slug=slug, slug=module_slug)
    quiz, _ = Quiz.objects.get_or_create(module=module)
    position = quiz.questions.count()
    question = Question.objects.create(
        quiz=quiz, text="New question", position=position
    )
    for index, letter in enumerate("ABCD"):
        question.choices.create(text=f"Option {letter}", position=index, is_correct=index == 0)
    url = reverse("manage:quiz_edit", kwargs={"slug": slug, "module_slug": module_slug})
    return redirect(f"{url}?q={position + 1}")


@staff_required
@require_POST
def question_delete(request, pk):
    question = get_object_or_404(
        Question.objects.select_related("quiz__module__course"), pk=pk
    )
    module = question.quiz.module
    question.delete()
    messages.success(request, "The question has been deleted.")
    return redirect(
        reverse(
            "manage:quiz_edit",
            kwargs={"slug": module.course.slug, "module_slug": module.slug},
        )
    )


class QuizIndexView(ManageBase):
    """Every quiz, so the sidebar's Quizzes link has somewhere to land."""

    template_name = "manage_panel/quizzes.html"
    section = "quiz"
    heading = "Quizzes"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modules"] = (
            Module.objects.select_related("course")
            .annotate(questions=Count("quiz__questions"))
            .order_by("course__position", "position")
        )
        return context


# -- Students ---------------------------------------------------------------


class StudentsView(ManageBase):
    template_name = "manage_panel/students.html"
    section = "students"
    heading = "Students"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = StudentFilterForm(self.request.GET or None)
        query = form.data.get("q", "").strip() if form.is_valid() else ""

        students = User.objects.filter(is_staff=False)
        if query:
            students = students.filter(
                Q(full_name__icontains=query) | Q(email__icontains=query)
            )

        course = Course.objects.order_by("position", "title").first()
        total_modules = (
            course.modules.filter(status=Module.Status.PUBLISHED).count() if course else 0
        )
        students = students.annotate(
            completed=Count(
                "module_progress",
                filter=Q(module_progress__completed_at__isnull=False),
                distinct=True,
            ),
            enrolled=Count("enrollments", filter=Q(enrollments__is_active=True)),
        ).order_by("-date_joined")[:100]

        rows = []
        for student in students:
            last = (
                ModuleProgress.objects.filter(student=student)
                .order_by("-last_seen_at")
                .values_list("last_seen_at", flat=True)
                .first()
            )
            rows.append(
                {
                    "student": student,
                    "completed": student.completed,
                    "total": total_modules,
                    "width": round(student.completed / total_modules * 100)
                    if total_modules
                    else 0,
                    "last_active": last,
                    "is_enrolled": bool(student.enrolled),
                }
            )

        context.update(
            form=form,
            rows=rows,
            total=User.objects.filter(is_staff=False).count(),
            query=query,
        )
        return context


@staff_required
@require_POST
def student_access(request, pk):
    """Suspend or restore a student's access without touching their orders."""
    student = get_object_or_404(User, pk=pk, is_staff=False)
    student.access_enabled = not student.access_enabled
    student.save(update_fields=["access_enabled"])
    state = "restored" if student.access_enabled else "suspended"
    messages.success(request, f"Access for {student.get_full_name()} has been {state}.")
    return redirect(request.POST.get("next") or reverse("manage:students"))


@staff_required
@require_POST
def student_grant(request, pk):
    """Grant a course without a payment — refunds, comps, support fixes."""
    student = get_object_or_404(User, pk=pk, is_staff=False)
    course = get_object_or_404(Course, slug=request.POST.get("course", ""))
    Enrollment.objects.update_or_create(
        student=student,
        course=course,
        defaults={"is_active": True, "granted_manually": True},
    )
    messages.success(
        request, f"{student.get_full_name()} now has access to “{course.title}”."
    )
    return redirect(request.POST.get("next") or reverse("manage:students"))


# -- Orders -----------------------------------------------------------------


class OrdersView(ManageBase):
    template_name = "manage_panel/orders.html"
    section = "orders"
    heading = "Orders"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        chosen = self.request.GET.get("status", "all")
        orders = Order.objects.select_related("student", "course")
        if chosen in Order.Status.values:
            orders = orders.filter(status=chosen)
        context.update(
            orders=orders[:200],
            chosen=chosen,
            filters=[("all", "All")] + list(Order.Status.choices),
        )
        return context


# -- Site content -----------------------------------------------------------


class ContentView(ManageBase):
    """FAQs, legal pages and contact messages in one place."""

    template_name = "manage_panel/content.html"
    section = "content"
    heading = "Site content"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            faqs=Faq.objects.all(),
            legal_pages=LegalPage.objects.all(),
            contact_messages=ContactMessage.objects.all()[:25],
            faq_form=FaqForm(),
        )
        return context


@staff_required
@require_POST
def faq_create(request):
    form = FaqForm(request.POST)
    if form.is_valid():
        faq = form.save(commit=False)
        if not faq.position:
            faq.position = Faq.objects.count()
        faq.save()
        messages.success(request, "The question has been added.")
    else:
        messages.error(request, "The question could not be added. Check the fields.")
    return redirect("manage:content")


@staff_required
def legal_edit(request, slug):
    page = get_object_or_404(LegalPage, slug=slug)
    form = LegalPageForm(request.POST or None, instance=page)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"“{page.title}” has been saved.")
        return redirect("manage:content")
    return render(
        request,
        "manage_panel/legal_form.html",
        {
            "form": form,
            "page": page,
            "section": "content",
            "counts": nav_counts(),
            "seo": noindex(page.title),
        },
    )


@staff_required
@require_POST
def message_handled(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    message.is_handled = not message.is_handled
    message.save(update_fields=["is_handled"])
    return redirect("manage:content")
