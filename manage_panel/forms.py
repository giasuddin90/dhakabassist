"""Forms for the administration panel.

Everything an administrator needs to run the course day to day, so content
changes never need a developer. Deeper structural edits stay in the Django
admin at /django-admin/.
"""

from pathlib import Path

from django import forms
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.forms import inlineformset_factory

from courses.models import (
    Choice,
    Course,
    LibraryFile,
    MediaAsset,
    Module,
    Question,
    Quiz,
)
from pages.models import Faq, LegalPage


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = (
            "title", "subtitle", "slug", "summary", "description", "level",
            "price", "status", "requires", "trailer_label", "trailer_duration",
            "meta_title", "meta_description",
        )
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 8}),
            "meta_description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Course.objects.all()
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields["requires"].queryset = queryset
        self.fields["requires"].empty_label = "No prerequisite"


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = (
            "number", "title", "title_bn", "slug", "summary", "notes_markdown",
            "access", "status", "video_provider", "video_uid",
            "video_duration_seconds", "video_has_subtitles",
        )
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "notes_markdown": forms.Textarea(attrs={"rows": 14, "class": "editor-area"}),
        }


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ("title", "require_perfect_score", "allow_unlimited_retries")
        widgets = {
            "require_perfect_score": forms.CheckboxInput(attrs={"class": "switch"}),
            "allow_unlimited_retries": forms.CheckboxInput(attrs={"class": "switch"}),
        }


class QuestionForm(forms.ModelForm):
    """One question plus which of its options is correct.

    `correct` is a radio over the question's own choices, which is how the
    design presents it; `save` writes it back onto the Choice rows.
    """

    correct = forms.ModelChoiceField(
        queryset=Choice.objects.none(),
        widget=forms.RadioSelect,
        required=True,
        label="Correct answer",
    )

    class Meta:
        model = Question
        fields = ("text", "explanation", "notation", "audio")
        widgets = {
            "text": forms.Textarea(attrs={"rows": 2}),
            "explanation": forms.Textarea(attrs={"rows": 2}),
        }

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


ChoiceFormSet = inlineformset_factory(
    Question,
    Choice,
    fields=("text",),
    extra=0,
    can_delete=False,
    widgets={"text": forms.TextInput()},
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
        return [
            LibraryFile.objects.create(
                purpose=purpose,
                folder=folder,
                title=title_from_filename(upload.name),
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
    "folder": ("folder", "title", "id"),
    "newest": ("-created_at", "-id"),
    "oldest": ("created_at", "id"),
    "title": ("title", "id"),
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
            files = files.filter(Q(title__icontains=data["q"]) | Q(file__icontains=data["q"]))
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
    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(attrs={"placeholder": "Search name or email"}),
    )


class FaqForm(forms.ModelForm):
    class Meta:
        model = Faq
        fields = ("question", "answer", "position", "is_published")
        widgets = {"answer": forms.Textarea(attrs={"rows": 4})}


class LegalPageForm(forms.ModelForm):
    class Meta:
        model = LegalPage
        fields = ("slug", "title", "body_markdown", "meta_description", "is_published")
        widgets = {
            "body_markdown": forms.Textarea(attrs={"rows": 18, "class": "editor-area"}),
            "meta_description": forms.Textarea(attrs={"rows": 2}),
        }
