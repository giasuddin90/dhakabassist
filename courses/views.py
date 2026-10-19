import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from pages import seo

from . import video
from .access import CourseAccess, can_fetch_library_file, course_queryset
from .markup import render_notes
from .models import (
    Author,
    Course,
    LibraryFile,
    MediaAsset,
    Module,
    ModuleProgress,
    QuizAttempt,
)

INCLUDES = (
    "All 9 modules with video lessons",
    "Written notes, audio and notation diagrams",
    "Downloadable worksheets",
    "Quizzes with instant feedback",
    "Lifetime access on any device",
)

PAYMENT_CHIPS = ("bKash", "Nagad", "Visa", "Mastercard", "International cards")


def _clock(seconds):
    """Seconds as mm:ss, or an empty string at zero."""
    if not seconds:
        return ""
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes:02d}:{remainder:02d}"


class CourseListView(ListView):
    """The course catalogue. One course today, more without a rebuild."""

    template_name = "courses/list.html"
    context_object_name = "courses"

    def get_queryset(self):
        return course_queryset().filter(status=Course.Status.PUBLISHED)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["seo"] = seo.SEO(
            title="Music theory courses",
            description=(
                "Online music theory courses by Tanveer Haque, taught from the "
                "basics of sound through to the circle of fifths."
            ),
            canonical_path=reverse("courses:list"),
            breadcrumbs=[seo.Breadcrumb("Home", "/"), seo.Breadcrumb("Courses")],
            schemas=[seo.course_schema(c) for c in context["courses"]],
        )
        return context


class CourseDetailView(DetailView):
    """Course landing page: curriculum, facts, pricing sidebar."""

    template_name = "courses/detail.html"
    context_object_name = "course"

    def get_queryset(self):
        return course_queryset().filter(status=Course.Status.PUBLISHED)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.object
        access = CourseAccess(self.request.user, course)
        free = course.free_module
        context.update(
            access=access,
            module_states=access.module_states(),
            includes=INCLUDES,
            payment_chips=PAYMENT_CHIPS,
            facts=[
                ("Modules", str(course.module_count)),
                ("Total video", course.total_runtime or "—"),
                ("Free preview", f"Module {free.number_plain}" if free else "—"),
                ("Level", course.level),
            ],
            description=render_notes(course.description),
            seo=seo.SEO(
                title=course.meta_title or course.title,
                description=course.meta_description or course.summary,
                canonical_path=course.get_absolute_url(),
                breadcrumbs=[
                    seo.Breadcrumb("Home", "/"),
                    seo.Breadcrumb("Courses", reverse("courses:list")),
                    seo.Breadcrumb(course.title),
                ],
                schemas=[seo.course_schema(course)],
            ),
        )
        return context


class DashboardView(LoginRequiredMixin, TemplateView):
    """"My courses" — progress and the module list for each owned course."""

    template_name = "courses/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        courses = course_queryset().filter(status=Course.Status.PUBLISHED)
        cards = []
        for course in courses:
            access = CourseAccess(self.request.user, course)
            states = access.module_states()
            if not (access.is_enrolled or any(s.is_unlocked for s in states)):
                continue
            resume = access.current_state
            progress = access.progress_for(resume.module) if resume else None
            cards.append(
                {
                    "course": course,
                    "access": access,
                    "states": states,
                    "resume": resume,
                    "resume_at": _clock(progress.video_position_seconds) if progress else "",
                }
            )
        context.update(
            cards=cards,
            seo=seo.noindex(
                "My courses",
                "Your enrolled courses and progress.",
                reverse("courses:dashboard"),
            ),
        )
        return context


class LessonView(LoginRequiredMixin, TemplateView):
    """A module: video, notes, audio, downloads and the quiz entry point.

    An unreachable module renders the paywall rather than a 403, which is
    what the design shows and what a student expects to see.
    """

    template_name = "courses/lesson.html"

    def get_context_data(self, **kwargs):
        course = get_object_or_404(
            course_queryset().filter(status=Course.Status.PUBLISHED),
            slug=kwargs["slug"],
        )
        module = get_object_or_404(
            course.modules, slug=kwargs["module_slug"], status=Module.Status.PUBLISHED
        )
        access = CourseAccess(self.request.user, course)
        state = access.state_for(module)

        if state is None or state.is_locked:
            self.template_name = "courses/paywall.html"
            return {
                "course": course,
                "module": module,
                "access": access,
                "locked_states": access.locked_states,
                "includes": INCLUDES,
                "payment_chips": PAYMENT_CHIPS,
                "seo": seo.noindex(
                    "Enroll to continue",
                    canonical_path=module.get_absolute_url(),
                ),
            }

        self._touch_progress(module)
        quiz = getattr(module, "quiz", None)
        return {
            "course": course,
            "module": module,
            "access": access,
            "state": state,
            "module_states": access.module_states(),
            "notes": render_notes(module.notes_markdown),
            "playback": video.playback(module),
            "quiz": quiz,
            "progress": access.progress_for(module),
            "seo": seo.noindex(
                f"{module.title} · {course.title}",
                module.summary,
                module.get_absolute_url(),
            ),
        }

    def _touch_progress(self, module):
        ModuleProgress.objects.update_or_create(
            student=self.request.user,
            module=module,
            defaults={"last_seen_at": timezone.now()},
        )


def open_attempt(student, quiz):
    """The student's in-progress attempt at `quiz`, creating one if needed.

    Shared by the quiz page and both POST endpoints, so an answer posted
    without having loaded the page first still lands on a real attempt.
    """
    attempt = (
        QuizAttempt.objects.filter(student=student, quiz=quiz, completed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if attempt is None:
        attempt = QuizAttempt.objects.create(
            student=student, quiz=quiz, answers={"index": 0, "picks": {}}
        )
    attempt.answers.setdefault("index", 0)
    attempt.answers.setdefault("picks", {})
    return attempt


def load_quiz(user, slug, module_slug):
    """Resolve a quiz the user is allowed to take, or raise 404."""
    course = get_object_or_404(
        course_queryset().filter(status=Course.Status.PUBLISHED), slug=slug
    )
    module = get_object_or_404(
        course.modules, slug=module_slug, status=Module.Status.PUBLISHED
    )
    access = CourseAccess(user, course)
    quiz = getattr(module, "quiz", None)
    if quiz is None or not access.can_view(module):
        raise Http404("No quiz here.")
    return course, module, access, quiz


class QuizView(LoginRequiredMixin, TemplateView):
    """The quiz, rendered server-side.

    Questions and answers are posted back one at a time, so the correct
    answer never reaches the browser before it is chosen. Without JavaScript
    the same flow works through ordinary form posts.
    """

    template_name = "courses/quiz.html"

    def get(self, request, *args, **kwargs):
        course = get_object_or_404(
            course_queryset().filter(status=Course.Status.PUBLISHED),
            slug=kwargs["slug"],
        )
        module = get_object_or_404(
            course.modules, slug=kwargs["module_slug"], status=Module.Status.PUBLISHED
        )
        access = CourseAccess(request.user, course)
        if not access.can_view(module):
            return redirect(module.get_absolute_url())
        return self.render_to_response(
            self.build_context(course, module, access)
        )

    def build_context(self, course, module, access):
        quiz = getattr(module, "quiz", None)
        if quiz is None:
            raise Http404("This module has no quiz.")

        attempt = open_attempt(self.request.user, quiz)
        questions = list(quiz.questions.all())
        index = min(attempt.answers.get("index", 0), max(len(questions) - 1, 0))
        question = questions[index] if questions else None
        picks = attempt.answers.get("picks", {}).get(str(question.id), []) if question else []
        solved = bool(question and question.correct_choice and question.correct_choice.id in picks)

        return {
            "course": course,
            "module": module,
            "quiz": quiz,
            "attempt": attempt,
            "questions": questions,
            "question": question,
            "question_number": index + 1,
            "question_total": len(questions),
            "picks": picks,
            "solved": solved,
            "is_last": index >= len(questions) - 1,
            "finished": attempt.completed_at is not None,
            "next_state": self._next_unlocked(access, module),
            "dots": [
                {
                    "state": (
                        "done"
                        if i < index
                        or (i == index and solved)
                        else "current"
                        if i == index
                        else "todo"
                    )
                }
                for i in range(len(questions))
            ],
            "seo": seo.noindex(
                f"{quiz.plain_title} · {course.title}",
                canonical_path=reverse(
                    "courses:quiz",
                    kwargs={"slug": course.slug, "module_slug": module.slug},
                ),
            ),
        }

    @staticmethod
    def _next_unlocked(access, module):
        states = access.module_states()
        for index, state in enumerate(states):
            if state.module.id == module.id:
                return states[index + 1] if index + 1 < len(states) else None
        return None


@login_required
@require_POST
def quiz_answer(request, slug, module_slug):
    """Record one answer pick and report whether it was right.

    Returns JSON for the progressive-enhancement path, or redirects back to
    the quiz page when JavaScript is not running. The server is the only
    judge of correctness; nothing in the page says which option is right.
    """
    _, module, _, quiz = load_quiz(request.user, slug, module_slug)
    attempt = open_attempt(request.user, quiz)

    question = next(
        (q for q in quiz.questions.all() if str(q.id) == request.POST.get("question")),
        None,
    )
    choice = next(
        (
            c
            for c in (question.choices.all() if question else [])
            if str(c.id) == request.POST.get("choice")
        ),
        None,
    )
    if question is None or choice is None:
        raise Http404("Unknown question or answer.")

    picks = attempt.answers["picks"].setdefault(str(question.id), [])
    correct = bool(question.correct_choice and choice.id == question.correct_choice.id)
    if choice.id not in picks:
        picks.append(choice.id)
        if not correct:
            attempt.wrong_picks += 1
    attempt.save(update_fields=["answers", "wrong_picks", "updated_at"])

    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse(
            {
                "correct": correct,
                # Rendered and sanitised here, so the page can insert it as HTML.
                "explanation": str(question.explanation_html) if correct else "",
                "picked": picks,
            }
        )
    return redirect(
        reverse("courses:quiz", kwargs={"slug": slug, "module_slug": module_slug})
    )


@login_required
@require_POST
def quiz_advance(request, slug, module_slug):
    """Move to the next question, or finish the quiz and unlock what follows."""
    _, module, _, quiz = load_quiz(request.user, slug, module_slug)
    attempt = open_attempt(request.user, quiz)
    quiz_url = reverse("courses:quiz", kwargs={"slug": slug, "module_slug": module_slug})

    questions = list(quiz.questions.all())
    if not questions:
        return redirect(quiz_url)

    index = attempt.answers.get("index", 0)
    if index + 1 < len(questions):
        attempt.answers["index"] = index + 1
        attempt.save(update_fields=["answers", "updated_at"])
        return redirect(quiz_url)

    # Last question. Finishing needs every question solved, so an attempt that
    # completes has been answered correctly throughout — which is what the
    # "100% to unlock" rule means. `score_percent` records how many were right
    # first time, so retries are visible without blocking progress.
    picks = attempt.answers["picks"]
    solved = [
        q for q in questions if q.correct_choice and q.correct_choice.id in picks.get(str(q.id), [])
    ]
    if quiz.require_perfect_score and len(solved) < len(questions):
        return redirect(quiz_url)

    first_try = sum(
        1
        for q in questions
        if q.correct_choice and picks.get(str(q.id), [])[:1] == [q.correct_choice.id]
    )
    attempt.score_percent = round(first_try / len(questions) * 100)
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["score_percent", "completed_at", "updated_at"])

    progress, _ = ModuleProgress.objects.get_or_create(student=request.user, module=module)
    progress.mark_complete()
    return redirect(quiz_url)


@login_required
@require_POST
def quiz_restart(request, slug, module_slug):
    """Begin a fresh attempt, leaving the finished one on record."""
    _, _, _, quiz = load_quiz(request.user, slug, module_slug)
    if quiz.allow_unlimited_retries:
        QuizAttempt.objects.create(
            student=request.user, quiz=quiz, answers={"index": 0, "picks": {}}
        )
    return redirect(
        reverse("courses:quiz", kwargs={"slug": slug, "module_slug": module_slug})
    )


@login_required
@require_POST
def save_video_position(request, pk):
    """Remember where a student paused, and how long they have watched."""
    module = get_object_or_404(Module, pk=pk)
    if not CourseAccess(request.user, module.course).can_view(module):
        raise Http404("No such module.")
    ModuleProgress.record_playback(
        request.user,
        module,
        position=_whole_seconds(request.POST.get("seconds")),
        watched=_whole_seconds(request.POST.get("watched")),
    )
    return JsonResponse({"saved": True})


def _whole_seconds(value):
    """A posted number of seconds, or 0 when it is missing or garbage."""
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


# -- Course media -----------------------------------------------------------


def _serve_media(path, download_name="", as_attachment=False):
    """Stream a file from MEDIA_ROOT, or hand it to nginx.

    `path` has already been produced by the database, never by the request,
    but it is still resolved and bounds-checked before opening.
    """
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root) + "/") or not target.is_file():
        raise Http404("File not found.")

    if settings.MEDIA_INTERNAL_URL:
        # nginx streams the bytes from an `internal` location, so a large
        # video does not occupy a worker. The access check has already run.
        response = HttpResponse()
        response["X-Accel-Redirect"] = settings.MEDIA_INTERNAL_URL + path
        response["Content-Type"] = ""
        response["Cache-Control"] = "private, max-age=0, no-store"
        response["X-Robots-Tag"] = "noindex, nofollow"
        _sandbox_svg(response, target)
        if as_attachment:
            name = download_name or target.name
            response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    response = FileResponse(
        target.open("rb"),
        as_attachment=as_attachment,
        filename=download_name or target.name,
        content_type=content_type,
    )
    response["Cache-Control"] = "private, max-age=0, no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    _sandbox_svg(response, target)
    return response


def _sandbox_svg(response, target):
    """Stop an SVG opened on its own from running script on our origin.

    An SVG is a document and may carry <script>. Inside an <img> it cannot
    run, but a student could open the file URL directly; the sandbox keeps a
    hostile upload from acting as the signed-in student.
    """
    if target.suffix.lower() == ".svg":
        response["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        )


@login_required
def protected_video(request, pk):
    module = get_object_or_404(Module, pk=pk)
    if not CourseAccess(request.user, module.course).can_view(module):
        raise Http404("No such video.")
    if not module.video_uid:
        raise Http404("No video for this module.")
    return _serve_media(module.video_uid)


@login_required
def protected_asset(request, pk):
    asset = get_object_or_404(MediaAsset.objects.select_related("module__course"), pk=pk)
    if not CourseAccess(request.user, asset.module.course).can_view(asset.module):
        raise Http404("No such file.")
    return _serve_media(
        asset.file.name,
        download_name=Path(asset.file.name).name,
        as_attachment=asset.kind == MediaAsset.Kind.DOWNLOAD,
    )


def author_photo(request, slug):
    """An author's photo: public, unlike the course material.

    Only authors of a published course are public; staff see every author,
    so the panel can show a photo before the course goes live.
    """
    authors = Author.objects.all()
    if not request.user.is_staff:
        authors = authors.filter(courses__status=Course.Status.PUBLISHED).distinct()
    author = get_object_or_404(authors, slug=slug)
    if not author.photo:
        raise Http404("No author photo.")
    response = _serve_media(author.photo.name)
    # `photo_url` changes when the photo does, so it may be cached.
    response["Cache-Control"] = "public, max-age=86400"
    return response


def library_file(request, key, name):
    """A shared media library file, served when a page the user may see links to it.

    Not `login_required`: a diagram linked from a public course description
    must load for anonymous visitors. `can_fetch_library_file` decides.
    """
    item = get_object_or_404(LibraryFile, key=key)
    if name != item.filename or not can_fetch_library_file(request.user, item):
        raise Http404("No such file.")
    return _serve_media(
        item.file.name,
        download_name=item.filename,
        as_attachment=item.is_download,
    )
