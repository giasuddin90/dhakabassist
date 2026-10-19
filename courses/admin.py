from django.contrib import admin

from .models import (
    Author,
    Choice,
    Course,
    Enrollment,
    Lesson,
    LibraryFile,
    MediaAsset,
    Module,
    ModuleProgress,
    Question,
    Quiz,
    QuizAttempt,
)


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ("number", "title", "access", "status")
    ordering = ("number",)
    show_change_link = True


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "updated_at")
    search_fields = ("name", "bio")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "title", "author", "status", "promote_on_home", "price", "position", "updated_at",
    )
    list_filter = ("status", "promote_on_home", "author")
    list_select_related = ("author",)
    search_fields = ("title", "summary")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("author",)
    inlines = [ModuleInline]


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0


class MediaAssetInline(admin.TabularInline):
    model = MediaAsset
    extra = 0
    fields = ("kind", "title", "file", "alt_text", "duration_seconds", "position")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "course", "access", "status")
    list_filter = ("course", "access", "status")
    search_fields = ("title", "summary")
    ordering = ("course__position", "number")
    inlines = [LessonInline, MediaAssetInline]


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    max_num = 8


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "quiz", "position")
    list_filter = ("quiz__module__course",)
    inlines = [ChoiceInline]


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ("position", "text")
    show_change_link = True


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("__str__", "require_perfect_score", "allow_unlimited_retries")
    inlines = [QuestionInline]


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "module", "duration_seconds")
    list_filter = ("kind", "module__course")
    search_fields = ("title",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "is_active", "granted_manually", "created_at")
    list_filter = ("course", "is_active", "granted_manually")
    search_fields = ("student__email", "student__full_name")
    autocomplete_fields = ("student",)


@admin.register(ModuleProgress)
class ModuleProgressAdmin(admin.ModelAdmin):
    list_display = ("student", "module", "completed_at", "last_seen_at")
    list_filter = ("module__course",)
    search_fields = ("student__email",)
    autocomplete_fields = ("student",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "quiz", "score_percent", "wrong_picks", "completed_at")
    list_filter = ("quiz__module__course",)
    search_fields = ("student__email",)
    autocomplete_fields = ("student",)


@admin.register(LibraryFile)
class LibraryFileAdmin(admin.ModelAdmin):
    """Fallback editing for the shared media library; /manage/library/ is the main page."""

    list_display = ("title", "folder", "file", "created_at")
    list_filter = ("folder",)
    search_fields = ("title", "file")
