"""Forms for the administration panel.

Everything an administrator needs to run the course day to day, so content
changes never need a developer. Deeper structural edits stay in the Django
admin at /django-admin/.
"""

import secrets
from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import transaction
from django.db.models import Q
from django.forms import inlineformset_factory

from accounts.forms import AccountSettingsForm
from courses.i18n import LANGUAGE_CODES, columns
from courses.models import (
    Author,
    Choice,
    Course,
    Enrollment,
    LibraryFile,
    MediaAsset,
    Module,
    Question,
    Quiz,
)
from downloads.models import EXTENSIONS as DOWNLOAD_EXTENSIONS
from downloads.models import Download
from orders.models import MANUAL_GATEWAY, Order, PaymentMethod
from pages.models import Faq, LegalPage

User = get_user_model()


def bilingual(*names):
    """The `_bn` and `_en` columns of each name, for `Meta.fields`."""
    return tuple(column for name in names for column in columns(name))


def bilingual_widgets(**widgets):
    """`Meta.widgets` with each widget used for both languages of the field."""
    return {
        f"{name}_{code}": widget
        for name, widget in widgets.items()
        for code in LANGUAGE_CODES
    }


class BilingualFormMixin:
    """Edit content stored in Bangla and English side by side.

    `bilingual_fields` lists the translated names the form edits, and
    `required_bilingual` those that need at least one language, the same
    rule the database enforces. Templates render a pair with
    `{% include "includes/bilingual_field.html" with pair=form.bilingual.title %}`.
    """

    bilingual_fields = ()
    required_bilingual = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for column in bilingual(*self.bilingual_fields):
            field = self.fields[column]
            # Right fonts and spell-checking while typing.
            field.widget.attrs["lang"] = column.rsplit("_", 1)[1]
            # A number left empty for one language (a video's duration, say)
            # means its default, not an error.
            if self._model_field(column).has_default():
                field.required = False

    def _model_field(self, column):
        return self._meta.model._meta.get_field(column)

    @property
    def bilingual(self):
        """Each translated name mapped to its (Bangla, English) bound fields."""
        return {
            name: [self[column] for column in columns(name)] for name in self.bilingual_fields
        }

    def clean(self):
        cleaned = super().clean()
        for column in bilingual(*self.bilingual_fields):
            if column in cleaned and cleaned[column] is None:
                cleaned[column] = self._model_field(column).get_default()
        for name in self.required_bilingual:
            if not any(cleaned.get(column) for column in columns(name)):
                self.add_error(
                    columns(name)[0], "Fill this in Bangla, English or both."
                )
        return cleaned


# The file picker for a public image; SVG is left out as it can carry script.
IMAGE_INPUT = forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})


class ImageUploadMixin:
    """One optional public image with a size limit and a "remove" tick box.

    A separate tick box rather than ClearableFileInput, whose "Currently"
    link points at MEDIA_URL, which is never served.
    """

    image_field = ""
    IMAGE_MAX_BYTES = 5 * 1024 * 1024

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self._remove_field] = forms.BooleanField(
            required=False, label=f"Remove the current {self.image_field}"
        )

    @property
    def _remove_field(self):
        return f"remove_{self.image_field}"

    def clean(self):
        """Refuse a new image over the size limit."""
        cleaned = super().clean()
        # Only a new upload is checked; the saved file is already within the limit.
        upload = self.files.get(self.image_field)
        if upload and upload.size > self.IMAGE_MAX_BYTES:
            self.add_error(self.image_field, f"The {self.image_field} is larger than 5 MB.")
        return cleaned

    def save(self, commit=True):
        """Save, clearing the image when asked to."""
        # A new upload wins over the tick box, so replacing needs one step.
        if self.cleaned_data.get(self._remove_field) and self.image_field not in self.files:
            setattr(self.instance, self.image_field, "")
        return super().save(commit=commit)


# Django's form classes are seven ancestors deep, so any mixin passes pylint's limit.
class CourseForm(ImageUploadMixin, BilingualFormMixin, forms.ModelForm):  # pylint: disable=too-many-ancestors
    bilingual_fields = (
        "title", "subtitle", "summary", "description", "level", "meta_title",
        "meta_description",
    )
    required_bilingual = ("title", "summary", "description")
    image_field = "banner"

    class Meta:
        model = Course
        fields = (
            *bilingual("title", "subtitle"), "slug", *bilingual("summary", "description", "level"),
            "price", "status", "requires", "promote_on_home", "author", "banner",
            *bilingual("meta_title", "meta_description"),
        )
        widgets = bilingual_widgets(
            summary=forms.Textarea(attrs={"rows": 3}),
            description=forms.Textarea(attrs={"rows": 8}),
            meta_description=forms.Textarea(attrs={"rows": 2}),
        ) | {"banner": IMAGE_INPUT}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Course.objects.all()
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields["requires"].queryset = queryset
        self.fields["requires"].empty_label = "No prerequisite"
        self.fields["author"].empty_label = "No author"


# Django's form classes are seven ancestors deep, so any mixin passes pylint's limit.
class AuthorForm(ImageUploadMixin, BilingualFormMixin, forms.ModelForm):  # pylint: disable=too-many-ancestors
    bilingual_fields = ("name", "bio")
    required_bilingual = ("name",)
    image_field = "photo"

    class Meta:
        model = Author
        fields = (*bilingual("name"), "slug", "photo", *bilingual("bio"))
        widgets = {
            "photo": IMAGE_INPUT,
            **bilingual_widgets(bio=forms.Textarea(attrs={"rows": 12, "class": "editor-area"})),
        }


class DownloadForm(BilingualFormMixin, forms.ModelForm):
    """A worksheet, PDF, audio file or ZIP for the downloads page, free or paid."""

    bilingual_fields = ("title", "description", "file")
    required_bilingual = ("title", "file")
    MAX_BYTES = 100 * 1024 * 1024

    class Meta:
        model = Download
        fields = (
            *bilingual("title"), "slug", "kind", *bilingual("description", "file"),
            "price", "status", "position",
        )
        widgets = bilingual_widgets(
            description=forms.Textarea(attrs={"rows": 3}),
            file=forms.FileInput(
                attrs={"accept": ",".join(f".{ext}" for ext in DOWNLOAD_EXTENSIONS)}
            ),
        )

    def clean(self):
        cleaned = super().clean()
        for column in columns("file"):
            upload = self.files.get(column)
            if upload and upload.size > self.MAX_BYTES:
                self.add_error(column, f"“{upload.name}” is larger than 100 MB.")
        return cleaned

    def save(self, commit=True):
        """Save, and remove a file that a new upload replaced."""
        replaced = [
            self.initial[column]
            for column in columns("file")
            if column in self.changed_data and self.initial.get(column)
        ]
        download = super().save(commit)
        if commit:
            for old in replaced:
                old.storage.delete(old.name)
        return download


class ModuleForm(BilingualFormMixin, forms.ModelForm):
    bilingual_fields = (
        "title", "summary", "notes_markdown", "video_uid", "video_duration_seconds",
        "video_has_subtitles",
    )
    required_bilingual = ("title",)

    class Meta:
        model = Module
        fields = (
            "number", *bilingual("title"), "slug", *bilingual("summary", "notes_markdown"),
            "access", "status", "video_provider",
            *bilingual("video_uid", "video_duration_seconds", "video_has_subtitles"),
        )
        widgets = bilingual_widgets(
            summary=forms.Textarea(attrs={"rows": 3}),
            notes_markdown=forms.Textarea(attrs={"rows": 14, "class": "editor-area"}),
        )

    def clean_number(self):
        """Pad the number and refuse one the course already uses.

        The form leaves out `course`, so Django skips the per-course unique
        constraint; without this a taken number would fail at save.
        """
        number = Module.pad_number(self.cleaned_data["number"])
        taken = Module.objects.filter(course=self.instance.course, number=number).exclude(
            pk=self.instance.pk
        )
        if taken.exists():
            raise forms.ValidationError(f"Module {number} already exists in this course.")
        return number


class QuizForm(BilingualFormMixin, forms.ModelForm):
    bilingual_fields = ("title",)

    class Meta:
        model = Quiz
        fields = (*bilingual("title"), "require_perfect_score", "allow_unlimited_retries")
        widgets = {
            "require_perfect_score": forms.CheckboxInput(attrs={"class": "switch"}),
            "allow_unlimited_retries": forms.CheckboxInput(attrs={"class": "switch"}),
        }


class QuestionForm(BilingualFormMixin, forms.ModelForm):
    """One question plus which of its options is correct.

    `correct` is a radio over the question's own choices, which is how the
    design presents it; `save` writes it back onto the Choice rows.
    """

    bilingual_fields = ("text", "explanation")
    required_bilingual = ("text",)

    correct = forms.ModelChoiceField(
        queryset=Choice.objects.none(),
        widget=forms.RadioSelect,
        required=True,
        label="Correct answer",
    )

    class Meta:
        model = Question
        fields = (*bilingual("text", "explanation"), "notation", "audio")
        widgets = bilingual_widgets(
            text=forms.Textarea(attrs={"rows": 2}),
            explanation=forms.Textarea(attrs={"rows": 2}),
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        module = self.instance.quiz.module
        assets = MediaAsset.objects.filter(module=module)
        self.fields["notation"].queryset = assets.filter(kind=MediaAsset.Kind.NOTATION)
        self.fields["audio"].queryset = assets.filter(kind=MediaAsset.Kind.AUDIO)
        self.fields["notation"].empty_label = "None"
        self.fields["audio"].empty_label = "None"
        choices = self.instance.choices.all()
        self.fields["correct"].queryset = choices
        current = next((c for c in choices if c.is_correct), None)
        self.initial.setdefault("correct", current.pk if current else None)

    def save(self, commit=True):
        question = super().save(commit=commit)
        correct = self.cleaned_data["correct"]
        for choice in question.choices.all():
            should_be = choice.pk == correct.pk
            if choice.is_correct != should_be:
                choice.is_correct = should_be
                choice.save(update_fields=["is_correct"])
        return question


class ChoiceForm(BilingualFormMixin, forms.ModelForm):
    """One answer option. Its two inputs sit in a row without visible labels."""

    bilingual_fields = ("text",)
    required_bilingual = ("text",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for column, language in zip(columns("text"), ("Bangla", "English")):
            self.fields[column].label = language
            attrs = self.fields[column].widget.attrs
            attrs.update(placeholder=language, **{"aria-label": language})


ChoiceFormSet = inlineformset_factory(
    Question,
    Choice,
    form=ChoiceForm,
    fields=bilingual("text"),
    extra=0,
    can_delete=False,
    widgets=bilingual_widgets(text=forms.TextInput()),
)


class MultipleFileInput(forms.ClearableFileInput):
    """A file input that lets the browser pick several files."""

    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file field that accepts several files and cleans each one."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)]


class LibraryUploadForm(forms.Form):
    """Upload any number of files into one media library folder."""

    MAX_BYTES = 50 * 1024 * 1024

    purpose = forms.ChoiceField(
        label="Material",
        choices=LibraryFile.Purpose.choices,
        initial=LibraryFile.Purpose.LESSON,
        widget=forms.RadioSelect,
    )
    language = forms.ChoiceField(
        label="Language",
        required=False,
        choices=LibraryFile.Language.choices,
        initial=LibraryFile.Language.BOTH,
        help_text="Which language's lesson pages list it under Downloads. "
        "Links in the notes work whatever this says.",
    )
    folder = forms.CharField(
        max_length=80,
        initial="General",
        help_text="Pick a folder, or type a new name to start one.",
        widget=forms.TextInput(attrs={"list": "library-folders"}),
    )
    files = MultipleFileField(
        validators=[FileExtensionValidator(LibraryFile.EXTENSIONS)],
        help_text="Audio (MP3, M4A, OGG, WAV), images (SVG, PNG, JPG, WEBP, GIF), "
        "documents (PDF, Word, PowerPoint, Excel, TXT, CSV), scores and tabs "
        "(MIDI, MusicXML, Guitar Pro, MuseScore) or ZIP. Pick several at once.",
    )

    def clean_language(self):
        return self.cleaned_data["language"] or LibraryFile.Language.BOTH

    def clean_folder(self):
        """Collapse stray spaces so "Module  3" and "Module 3" are one folder."""
        return " ".join(self.cleaned_data["folder"].split())

    def clean_files(self):
        """Refuse oversized files with their name, so the admin knows which."""
        files = self.cleaned_data["files"]
        for upload in files:
            if upload.size > self.MAX_BYTES:
                raise forms.ValidationError(f"“{upload.name}” is larger than 50 MB.")
        return files

    def save(self):
        """Create one library file per upload and return them."""
        purpose = self.cleaned_data["purpose"]
        folder = self.cleaned_data["folder"]
        language = self.cleaned_data["language"]
        return [
            LibraryFile.objects.create(
                purpose=purpose,
                language=language,
                folder=folder,
                # Filenames are Latin, so the readable default is English.
                title_en=title_from_filename(upload.name),
                file=upload,
            )
            for upload in self.cleaned_data["files"]
        ]


def title_from_filename(name):
    """"c-major_scale.mp3" -> "C major scale", a readable default title."""
    text = " ".join(Path(name).stem.replace("-", " ").replace("_", " ").split())
    return (text[:1].upper() + text[1:])[:200] or name[:200]


# Extensions behind each "Type" choice, and the ordering behind each "Sort".
LIBRARY_KINDS = {
    "audio": LibraryFile.AUDIO_EXTENSIONS,
    "image": LibraryFile.IMAGE_EXTENSIONS,
    "document": LibraryFile.DOCUMENT_EXTENSIONS,
    "score": LibraryFile.SCORE_EXTENSIONS,
    "archive": LibraryFile.ARCHIVE_EXTENSIONS,
}
LIBRARY_SORTS = {
    "folder": ("folder", "title_bn", "title_en", "id"),
    "newest": ("-created_at", "-id"),
    "oldest": ("created_at", "id"),
    "title": ("title_bn", "title_en", "id"),
}


class LibraryFilterForm(forms.Form):
    """Search, narrow and sort the media library. Every field is optional."""

    q = forms.CharField(required=False, max_length=200, label="Search")
    purpose = forms.ChoiceField(
        required=False, choices=[("", "All material"), *LibraryFile.Purpose.choices]
    )
    folder = forms.CharField(required=False, max_length=80)
    kind = forms.ChoiceField(
        required=False,
        label="Type",
        choices=[
            ("", "All types"),
            ("audio", "Audio"),
            ("image", "Images"),
            ("document", "Documents"),
            ("score", "Scores and tabs"),
            ("archive", "ZIP archives"),
        ],
    )
    usage = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "Any status"), ("used", "Used in a lesson"), ("unused", "Not linked yet")],
    )
    sort = forms.ChoiceField(
        required=False,
        label="Sort",
        choices=[
            ("folder", "Folder, A–Z"),
            ("newest", "Newest first"),
            ("oldest", "Oldest first"),
            ("title", "Title, A–Z"),
        ],
    )

    def clean_q(self):
        """Collapse stray spaces, so "C  major" finds "C major"."""
        return " ".join(self.cleaned_data["q"].split())

    def filter(self, files):
        """The files matching the search, folder and type, in the chosen order.

        Usage is left to the caller: it depends on lesson text, not a column.
        """
        data = self.cleaned_data if self.is_valid() else {}
        if data.get("purpose"):
            files = files.filter(purpose=data["purpose"])
        if data.get("folder"):
            files = files.filter(folder=data["folder"])
        if data.get("q"):
            files = files.filter(
                Q(title_bn__icontains=data["q"])
                | Q(title_en__icontains=data["q"])
                | Q(file__icontains=data["q"])
            )
        if data.get("kind"):
            by_extension = Q()
            for extension in LIBRARY_KINDS[data["kind"]]:
                by_extension |= Q(file__iendswith=f".{extension}")
            files = files.filter(by_extension)
        return files.order_by(*LIBRARY_SORTS[data.get("sort") or "folder"])

    @property
    def is_narrowed(self):
        """True when anything but the sort order limits the list."""
        data = self.cleaned_data if self.is_valid() else {}
        return any(data.get(name) for name in ("q", "purpose", "folder", "kind", "usage"))


class StudentFilterForm(forms.Form):
    """Search students and narrow them to a course or an enrolment state.

    Every field is optional. With a course chosen, "Enrolled", "Paid" and
    "Not enrolled" are about that course; without one, about any course.
    """

    ENROLLED = "enrolled"
    PAID = "paid"
    FREE = "free"

    q = forms.CharField(
        required=False,
        max_length=200,
        label="Search",
        widget=forms.TextInput(attrs={"placeholder": "Search name or email"}),
    )
    course = forms.ModelChoiceField(
        required=False,
        queryset=Course.objects.order_by("position", *columns("title")),
        to_field_name="slug",
        empty_label="All courses",
    )
    status = forms.ChoiceField(
        required=False,
        label="Enrolment",
        choices=[
            ("", "Any enrolment"),
            (ENROLLED, "Enrolled"),
            (PAID, "Paid"),
            (FREE, "Not enrolled"),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Parts of one course share a title; the subtitle tells them apart.
        self.fields["course"].label_from_instance = lambda course: " · ".join(
            filter(None, (course.title, course.subtitle))
        )

    def clean_q(self):
        """Collapse stray spaces, so "Rafiq  Ahmed" finds "Rafiq Ahmed"."""
        return " ".join(self.cleaned_data["q"].split())

    def filter(self, students):
        """The students matching the search, course and enrolment state."""
        data = self.cleaned_data if self.is_valid() else {}
        if data.get("q"):
            students = students.filter(
                Q(full_name__icontains=data["q"]) | Q(email__icontains=data["q"])
            )
        course = data.get("course")
        enrolled = Q(enrollments__is_active=True)
        paid = Q(orders__status=Order.Status.PAID)
        if course:
            enrolled &= Q(enrollments__course=course)
            paid &= Q(orders__course=course)
        status = data.get("status")
        if status == self.PAID:
            students = students.filter(paid)
        elif status == self.FREE:
            students = students.exclude(enrolled)
        elif status == self.ENROLLED or course:
            # A course on its own means "the students of that course".
            students = students.filter(enrolled)
        return students.distinct()

    @property
    def is_narrowed(self):
        """True when anything limits the list."""
        data = self.cleaned_data if self.is_valid() else {}
        return any(data.get(name) for name in ("q", "course", "status"))


class StudentForm(AccountSettingsForm):
    """An administrator's edit of a student's details, courses and account switches.

    Reuses the student's own settings form, so the email rules stay the same.
    """

    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.order_by("position", *columns("title")),
        to_field_name="slug",
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Courses",
        help_text="Tick to assign a course without a payment. Untick to remove access; "
        "orders are not refunded.",
    )

    class Meta(AccountSettingsForm.Meta):
        fields = ("full_name", "email", "marketing_opt_in", "access_enabled", "is_active")
        labels = {
            "marketing_opt_in": "Receives course news by email",
            "access_enabled": "Course access enabled",
            "is_active": "Can sign in",
        }
        help_texts = {
            "access_enabled": "Turn off to suspend paid material. Orders are kept.",
            "is_active": "Turn off to block sign-in without deleting the account.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        courses = self.fields["courses"]
        courses.label_from_instance = lambda c: " · ".join(filter(None, (c.title, c.subtitle)))
        if self.instance.pk:
            courses.initial = self.active_courses()

    def active_courses(self):
        return Course.objects.filter(enrollments__student=self.instance, enrollments__is_active=True)

    @transaction.atomic
    def save(self, commit=True):
        student = super().save(commit)
        if commit:
            chosen = set(self.cleaned_data["courses"])
            current = set(self.active_courses())
            for course in chosen - current:
                Enrollment.grant(student, course)
            Enrollment.revoke(student, current - chosen)
        return student


class StudentCreateForm(AccountSettingsForm):
    """A student added by staff, e.g. someone who paid by bKash before signing up."""

    send_invite = forms.BooleanField(
        label="Email a link to set their password",
        required=False,
        initial=True,
        help_text="Leave off to tell them yourself; they can use “Forgot password”.",
    )

    class Meta(AccountSettingsForm.Meta):
        fields = ("full_name", "email", "marketing_opt_in")
        labels = {"marketing_opt_in": "Receives course news by email"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].required = True

    def save(self, commit=True):
        student = super().save(commit=False)
        # A random password nobody knows, rather than an unusable one: Django's
        # password reset skips accounts without a usable password, and the
        # student needs it to choose their own.
        student.set_password(secrets.token_urlsafe(32))
        if commit:
            student.save()
        return student


class OrderFieldsForm(forms.ModelForm):
    """What staff may set on an order, shared by recording and editing one."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].choices = PaymentMethod.choices
        self.fields["amount"].validators.append(MinValueValidator(0))

    def clean_gateway_reference(self):
        """A TrxID pasted from a phone often carries stray spaces."""
        return self.cleaned_data["gateway_reference"].strip()

    def clean(self):
        """One transaction can pay for one order only, even after a refund."""
        cleaned = super().clean()
        reference = cleaned.get("gateway_reference")
        # A form without a status field records a payment, so the order is paid.
        status = cleaned.get("status", Order.Status.PAID)
        if (
            reference
            and status in (Order.Status.PAID, Order.Status.REFUNDED)
            and Order.objects.filter(
                gateway_reference=reference,
                status__in=(Order.Status.PAID, Order.Status.REFUNDED),
            )
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            self.add_error(
                "gateway_reference", "Another order already uses this transaction ID."
            )
        return cleaned


class ManualPaymentForm(OrderFieldsForm):
    """A payment taken outside the gateway, recorded so it enrols the student.

    For bKash or Nagad Send Money and similar, until (or alongside) the
    gateway. The order it creates is the same record a gateway payment makes,
    so revenue, receipts and refunds treat both alike.
    """

    class Meta:
        model = Order
        fields = ("course", "amount", "method", "gateway_reference")
        labels = {
            "amount": "Amount received (BDT)",
            "method": "Paid by",
            "gateway_reference": "Transaction ID",
        }
        help_texts = {
            "amount": "Leave blank for the course price.",
            "gateway_reference": "The bKash or Nagad TrxID, or the bank reference.",
        }

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        course = self.fields["course"]
        course.queryset = Course.objects.order_by("position", *columns("title"))
        if student is not None:
            course.queryset = course.queryset.exclude(
                pk__in=student.enrollments.filter(is_active=True).values("course")
            )
        course.to_field_name = "slug"
        course.empty_label = None
        # Optional on the model, which also takes download orders.
        course.required = True
        course.label_from_instance = lambda c: " · ".join(filter(None, (c.title, c.subtitle)))
        self.fields["amount"].required = False
        self.fields["gateway_reference"].required = True

    def clean(self):
        """A blank amount means the student paid the course price."""
        cleaned = super().clean()
        if cleaned.get("amount") is None and cleaned.get("course"):
            cleaned["amount"] = cleaned["course"].price
        return cleaned


# Seven of the eight ancestors are Django's own form classes.
class NewOrderForm(ManualPaymentForm):  # pylint: disable=too-many-ancestors
    """An order added by hand from the orders page, for any student.

    Paid works like recording a payment on the student page. Pending keeps
    the order open, e.g. while a bKash transfer is being checked.
    """

    status = forms.ChoiceField(
        choices=[
            (Order.Status.PAID, Order.Status.PAID.label),
            (Order.Status.PENDING, Order.Status.PENDING.label),
        ],
        initial=Order.Status.PAID,
        help_text="Paid enrols the student and emails the receipt.",
    )

    class Meta(ManualPaymentForm.Meta):
        fields = ("student", "course", "amount", "method", "gateway_reference")
        labels = {
            **ManualPaymentForm.Meta.labels,
            "student": "Student",
            "amount": "Amount (BDT)",
            "method": "Payment method",
        }
        help_texts = {
            **ManualPaymentForm.Meta.help_texts,
            "gateway_reference": "The bKash or Nagad TrxID, or the bank reference. "
            "Required when paid.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        student = self.fields["student"]
        student.queryset = User.objects.filter(is_staff=False).order_by("full_name", "email")
        student.label_from_instance = lambda u: f"{u.get_full_name()} · {u.email}"
        self.fields["gateway_reference"].required = False
        self.order_fields(("student", "course", "status", *self.Meta.fields[2:]))

    def clean(self):
        cleaned = super().clean()
        student, course = cleaned.get("student"), cleaned.get("course")
        if (
            student
            and course
            and student.enrollments.filter(course=course, is_active=True).exists()
        ):
            self.add_error("course", f"{student.get_full_name()} already has this course.")
        if cleaned.get("status") == Order.Status.PAID and not cleaned.get("gateway_reference"):
            self.add_error("gateway_reference", "Enter the transaction ID for a paid order.")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        order = super().save(commit=False)
        order.gateway = MANUAL_GATEWAY
        order.save()
        if self.cleaned_data["status"] == Order.Status.PAID:
            order.mark_paid()
        return order


class OrderForm(OrderFieldsForm):
    """Correct an order: the amount, method, transaction ID or status.

    The status goes through `Order.change_status`, so course access follows
    it. Student and course stay fixed; record a new order for another course.
    """

    status = forms.ChoiceField(
        choices=Order.Status.choices,
        help_text="Paid enrols the student. Refunded, failed or pending removes "
        "the access this order paid for; a manual grant is kept.",
    )
    course_access = forms.BooleanField(
        label="Course access",
        required=False,
        help_text="For a paid order: ticked opens the course for the student, "
        "unticked withdraws it and keeps the order paid.",
    )

    class Meta:
        model = Order
        fields = ("amount", "method", "gateway_reference")
        labels = {"gateway_reference": "Transaction ID"}
        help_texts = {"gateway_reference": "The gateway's reference, or the bKash or Nagad TrxID."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].initial = self.instance.status
        if not self.instance.course_id:
            # A download opens and closes with the status alone.
            del self.fields["course_access"]
        else:
            # Ticked by default, so setting an order to Paid enrols the student.
            self.fields["course_access"].initial = (
                self.instance.status != Order.Status.PAID
                or self.instance.student.enrollments.filter(
                    course=self.instance.course, is_active=True
                ).exists()
            )
        self.order_fields(("status", *self.Meta.fields))

    @transaction.atomic
    def save(self, commit=True):
        order = super().save(commit=False)
        # Only the edited columns: the status may have changed since the page
        # loaded (a gateway callback), and `change_status` reads it afresh.
        order.save(update_fields=[*self.Meta.fields, "updated_at"])
        order.change_status(self.cleaned_data["status"])
        if "course_access" in self.cleaned_data:
            order.set_course_access(self.cleaned_data["course_access"])
        return order


class FaqForm(BilingualFormMixin, forms.ModelForm):
    bilingual_fields = ("question", "answer")
    required_bilingual = ("question", "answer")

    class Meta:
        model = Faq
        fields = (*bilingual("question", "answer"), "position", "is_published")
        widgets = bilingual_widgets(answer=forms.Textarea(attrs={"rows": 4}))


class LegalPageForm(BilingualFormMixin, forms.ModelForm):
    bilingual_fields = ("title", "body_markdown", "meta_description")
    required_bilingual = ("title", "body_markdown")

    class Meta:
        model = LegalPage
        fields = ("slug", *bilingual("title", "body_markdown", "meta_description"), "is_published")
        widgets = bilingual_widgets(
            body_markdown=forms.Textarea(attrs={"rows": 18, "class": "editor-area"}),
            meta_description=forms.Textarea(attrs={"rows": 2}),
        )
