"""Add a folder of files to the media library, as the panel's upload page does.

    manage.py import_library                      # media/markup_media
    manage.py import_library path/to/files --folder "Scales"
    manage.py import_library --dry-run

Each file becomes one `LibraryFile`, titled from its name ("Q 5.18a.mp3" ->
"Q 5.18a"). Files named "Q …" are quiz material, the rest lesson material.
Unless `--folder` is given, the module number in the name picks the folder
("Diagram 3.2.svg" -> "Module 3").

Idempotent: a file whose title and extension are already in the library is
skipped, so re-running only adds what is new. Files the library does not
accept (e.g. Markdown) are listed and skipped.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from courses.models import LibraryFile
from manage_panel.forms import LibraryUploadForm, title_from_filename

# "Q 5.18a", "Audio 7.M7", "Diagram 2.1": a kind, then the module number.
MODULE_NUMBER = re.compile(r"^\S+\s+(\d+)\.")


def purpose_for(path):
    """Quiz material for "Q …" files, lesson material for everything else."""
    if path.stem.lower().startswith("q "):
        return LibraryFile.Purpose.QUIZ
    return LibraryFile.Purpose.LESSON


def folder_for(path):
    """ "Diagram 3.2.svg" -> "Module 3"; "General" when there is no number."""
    match = MODULE_NUMBER.match(path.stem)
    return f"Module {int(match[1])}" if match else "General"


def already_imported(title, extension):
    """True when the library has this title with this extension.

    "Q 4.18.svg" and "Q 4.18.mp3" share a title, so the extension counts too.
    """
    return LibraryFile.objects.filter(
        title_en=title, file__iendswith=f".{extension}"
    ).exists()


class Command(BaseCommand):
    """Import a folder into the media library; see the module docstring."""

    help = "Add every file in a folder to the media library."

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            nargs="?",
            type=Path,
            help="Folder to import (default: MEDIA_ROOT/markup_media).",
        )
        parser.add_argument(
            "--folder",
            help="Library folder for every file, instead of one per module.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be added without saving anything.",
        )

    def handle(self, *args, **options):
        source = options["source"] or Path(settings.MEDIA_ROOT) / "markup_media"
        if not source.is_dir():
            raise CommandError(f"{source} is not a folder.")
        folder = " ".join((options["folder"] or "").split())
        dry_run = options["dry_run"]

        added = skipped = 0
        for path in sorted(p for p in source.iterdir() if p.is_file()):
            reason = self._skip_reason(path)
            if reason:
                self.stdout.write(self.style.WARNING(f"Skipped {path.name}: {reason}."))
                skipped += 1
                continue
            if not dry_run:
                self._add(path, folder or folder_for(path))
            self.stdout.write(f"Added {path.name}")
            added += 1

        prefix = "Dry run, nothing saved: would add" if dry_run else "Added"
        self.stdout.write(
            self.style.SUCCESS(f"{prefix} {added} file(s), skipped {skipped}.")
        )

    @staticmethod
    def _skip_reason(path):
        extension = path.suffix.lstrip(".").lower()
        if extension not in LibraryFile.EXTENSIONS:
            return "the library does not accept this file type"
        if path.stat().st_size > LibraryUploadForm.MAX_BYTES:
            return "larger than 50 MB"
        if already_imported(title_from_filename(path.name), extension):
            return "already in the library"
        return ""

    @staticmethod
    def _add(path, folder):
        with path.open("rb") as handle:
            item = LibraryFile(
                purpose=purpose_for(path),
                folder=folder,
                # Filenames are Latin, so the readable default is English.
                title_en=title_from_filename(path.name),
                file=File(handle, name=path.name),
            )
            try:
                item.full_clean()
            except ValidationError as exc:
                raise CommandError(f"{path.name}: {'; '.join(exc.messages)}") from exc
            item.save()
