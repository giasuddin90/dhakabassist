from django.contrib import admin

from .models import (
    Choice,
    Course,
    Enrollment,
    Lesson,
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
    fields = ("position", "number", "title", "access", "status")
    ordering = ("position",)
    show_change_link = True


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "price", "position", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "summary")
    prepopulated_fields = {"slug": ("title",)}
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
    list_display = ("number", "title", "course", "access", "status", "position")
    list_filter = ("course", "access", "status")
    search_fields = ("title", "summary")
    ordering = ("course__position", "position")
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
