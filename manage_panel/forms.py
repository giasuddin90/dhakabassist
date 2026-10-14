"""Forms for the administration panel.

Everything an administrator needs to run the course day to day, so content
changes never need a developer. Deeper structural edits stay in the Django
admin at /django-admin/.
"""

from django import forms
from django.forms import inlineformset_factory

from courses.models import Choice, Course, MediaAsset, Module, Question, Quiz
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


class AssetForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ("kind", "title", "file", "alt_text", "duration_seconds")

    def clean(self):
        data = super().clean()
        if data.get("kind") == MediaAsset.Kind.NOTATION and not data.get("alt_text"):
            self.add_error(
                "alt_text", "Notation images need alt text so the notes stay readable."
            )
        return data


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
