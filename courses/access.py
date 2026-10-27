"""Who may study what.

Every view asks this module rather than re-deriving the rule, so the paywall,
the lesson page, the quiz and the course media stream can never disagree.
"""

from dataclasses import dataclass

from django.db.models import Prefetch, Q
from django.utils.translation import gettext as _

from .i18n import columns
from .models import Course, Enrollment, Module, ModuleProgress, Promotion


@dataclass(frozen=True)
class ModuleState:
    """A module as one student sees it."""

    module: Module
    is_complete: bool
    is_unlocked: bool
    is_current: bool

    @property
    def is_locked(self):
        return not self.is_unlocked

    @property
    def status_label(self):
        if self.is_complete:
            return _("Complete")
        if self.is_current:
            return _("In progress")
        return _("Locked") if self.is_locked else _("Not started")


class CourseAccess:
    """Access and progress for one (student, course) pair.

    `student` may be an anonymous user, in which case nothing is unlocked.
    """

    def __init__(self, student, course):
        self.student = student
        self.course = course
        self._authenticated = bool(getattr(student, "is_authenticated", False))
        self._modules = [
            m for m in course.module_list if m.status == Module.Status.PUBLISHED
        ]
        self._progress = {}
        if self._authenticated:
            self._progress = {
                p.module_id: p
                for p in ModuleProgress.objects.filter(
                    student=student, module__course=course
                )
            }

    # -- enrolment ---------------------------------------------------------

    @property
    def is_previewing(self):
        """True for an active superuser, who sees the course as a student would.

        Every published module is open to them at once, with no payment and no
        quiz to pass first, so the owner can check any lesson without
        enrolling or working through the course.
        """
        student = self.student
        return (
            self._authenticated
            and getattr(student, "is_active", False)
            and getattr(student, "is_superuser", False)
        )

    @property
    def is_enrolled(self):
        """True when the student has paid for (or been granted) this course."""
        if not self._authenticated:
            return False
        if self.is_previewing:
            return True
        if not getattr(self.student, "access_enabled", True):
            return False
        if getattr(self.student, "is_staff", False):
            return True
        return Enrollment.objects.filter(
            student=self.student, course=self.course, is_active=True
        ).exists()

    # -- modules -----------------------------------------------------------

    def completed_ids(self):
        return {
            module_id
            for module_id, progress in self._progress.items()
            if progress.completed_at is not None
        }

    def module_states(self):
        """Every published module, in order, with its state for this student."""
        completed = self.completed_ids()
        enrolled = self.is_enrolled
        previewing = self.is_previewing
        states = []
        current_found = False
        for index, module in enumerate(self._modules):
            is_complete = module.id in completed
            # Module 1 (the free preview) is open to any signed-in account;
            # the rest need enrolment plus every earlier module finished.
            # A superuser previewing the course skips the progression.
            earlier_done = all(m.id in completed for m in self._modules[:index])
            if previewing:
                unlocked = True
            elif module.is_free:
                unlocked = self._authenticated
            else:
                unlocked = enrolled and earlier_done
            is_current = unlocked and not is_complete and not current_found
            if is_current:
                current_found = True
            states.append(ModuleState(module, is_complete, unlocked, is_current))
        return states

    def state_for(self, module):
        return next((s for s in self.module_states() if s.module.id == module.id), None)

    def can_view(self, module):
        state = self.state_for(module)
        return bool(state and state.is_unlocked)

    def next_state(self, module):
        """The state of the module after `module`, or None after the last one."""
        states = self.module_states()
        for index, state in enumerate(states):
            if state.module.id == module.id:
                return states[index + 1] if index + 1 < len(states) else None
        return None

    # -- summary -----------------------------------------------------------

    @property
    def completed_count(self):
        return len(self.completed_ids() & {m.id for m in self._modules})

    @property
    def total_count(self):
        return len(self._modules)

    @property
    def percent_complete(self):
        if not self.total_count:
            return 0
        return round(self.completed_count / self.total_count * 100)

    @property
    def current_state(self):
        """The module to resume: the first unlocked, unfinished one."""
        states = self.module_states()
        return next(
            (s for s in states if s.is_current),
            next((s for s in states if s.is_locked), None),
        )

    @property
    def locked_states(self):
        return [s for s in self.module_states() if s.is_locked]

    def progress_for(self, module):
        return self._progress.get(module.id)


def course_queryset():
    """Courses with everything the curriculum and lesson pages read.

    One query per relation instead of one per module.
    """
    return Course.objects.select_related("author").prefetch_related(
        Prefetch(
            "promotions",
            queryset=Promotion.objects.running(),
            to_attr="running_promotions",
        ),
        Prefetch(
            "modules",
            queryset=Module.objects.prefetch_related(
                "lessons", "assets", "downloads", "quiz__questions__choices"
            ),
        )
    )


def can_fetch_library_file(user, library_file):
    """Whether `user` may download a shared media library file.

    Library files belong to no module, so access follows the links instead:
    a file is public when a published course description links to it, and
    otherwise reachable by anyone who may open a module whose notes or quiz
    link to it, or that offers it as a download. A file nobody links to is
    for staff only.
    """
    if user.is_authenticated and user.is_active and user.is_staff:
        return True
    prefix = library_file.link_prefix
    linking_modules = set(
        Module.objects.filter(
            Q(
                *(
                    Q(**{f"{path}__contains": prefix})
                    for path in (
                        *columns("notes_markdown"),
                        *(f"quiz__{c}" for c in columns("title")),
                        *(f"quiz__questions__{c}" for c in columns("text")),
                        *(f"quiz__questions__{c}" for c in columns("explanation")),
                        *(f"quiz__questions__choices__{c}" for c in columns("text")),
                    )
                ),
                downloads=library_file,
                _connector=Q.OR,
            ),
            status=Module.Status.PUBLISHED,
        ).values_list("pk", flat=True)
    )
    in_description = Q(
        *(Q(**{f"{c}__contains": prefix}) for c in columns("description")), _connector=Q.OR
    )
    linking = Course.published.filter(
        in_description | Q(modules__pk__in=linking_modules)
    ).values("pk")
    for course in course_queryset().filter(pk__in=linking):
        if prefix in course.linkable_text:
            return True
        if not user.is_authenticated:
            continue
        if any(
            s.is_unlocked and s.module.id in linking_modules
            for s in CourseAccess(user, course).module_states()
        ):
            return True
    return False
