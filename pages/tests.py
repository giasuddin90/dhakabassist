"""Public pages, SEO output and crawler discovery files."""

import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from courses.models import Course, Module
from pages.models import ContactMessage, Faq, LegalPage


class PublicPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(
            title="Foundations of Music",
            subtitle="Part 1",
            slug="foundations-of-music",
            summary="Nine clear modules from sound to the circle of fifths.",
            description="A complete beginner course in music theory.",
            price=3500,
            status=Course.Status.PUBLISHED,
        )
        cls.free = Module.objects.create(
            course=cls.course,
            number="01",
            slug="sound",
            title="Sound",
            summary="What sound is.",
            access=Module.Access.FREE,
            status=Module.Status.PUBLISHED,
            video_duration_seconds=740,
            position=0,
        )
        Module.objects.create(
            course=cls.course,
            number="02",
            slug="notation",
            title="Notation",
            summary="The staff and clefs.",
            access=Module.Access.PAID,
            status=Module.Status.PUBLISHED,
            video_duration_seconds=900,
            position=1,
        )
        Faq.objects.create(question="Do I need to read music?", answer="No.", position=0)
        LegalPage.objects.create(
            slug="terms", title="Terms & Conditions", body_markdown="## Terms\n\nText."
        )

    def test_home_renders_with_course(self):
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "Foundations of Music")
        self.assertContains(response, "Sound")
        self.assertContains(response, "Do I need to read music?")

    def test_home_renders_without_a_published_course(self):
        Course.objects.update(status=Course.Status.DRAFT)
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "being prepared")

    def test_canonical_and_open_graph_are_present(self):
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, '<link rel="canonical"')
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'name="twitter:card"')

    def test_json_ld_is_valid_and_describes_the_course(self):
        response = self.client.get(reverse("pages:home"))
        body = response.content.decode()
        start = body.index('<script type="application/ld+json">') + len(
            '<script type="application/ld+json">'
        )
        payload = json.loads(body[start : body.index("</script>", start)])
        types = {node["@type"] for node in payload["@graph"]}
        self.assertIn("EducationalOrganization", types)
        self.assertIn("Course", types)
        self.assertIn("FAQPage", types)

    def test_faq_page_carries_faq_schema(self):
        response = self.client.get(reverse("pages:faq"))
        self.assertContains(response, "FAQPage")

    def test_legal_page_renders_markdown(self):
        response = self.client.get(reverse("pages:legal", kwargs={"slug": "terms"}))
        self.assertContains(response, "<h2>Terms</h2>", html=False)

    def test_unpublished_legal_page_is_not_found(self):
        LegalPage.objects.filter(slug="terms").update(is_published=False)
        response = self.client.get(reverse("pages:legal", kwargs={"slug": "terms"}))
        self.assertEqual(response.status_code, 404)

    def test_breadcrumbs_render_and_match_schema(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, "BreadcrumbList")

    def test_404_page_uses_the_site_layout(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "could not find that page", status_code=404)


class DiscoveryFileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = Course.objects.create(
            title="Foundations of Music",
            slug="foundations-of-music",
            summary="Summary.",
            description="Description.",
            status=Course.Status.PUBLISHED,
        )
        LegalPage.objects.create(slug="refunds", title="Refund Policy", body_markdown="Text.")

    def test_robots_blocks_private_paths_and_links_the_sitemap(self):
        response = self.client.get("/robots.txt")
        body = response.content.decode()
        self.assertEqual(response["Content-Type"], "text/plain")
        for path in ("/learn/", "/my-courses/", "/account/", "/manage/", "/payment/"):
            self.assertIn(f"Disallow: {path}", body)
        self.assertIn("Sitemap:", body)

    def test_sitemap_lists_public_pages_only(self):
        response = self.client.get("/sitemap.xml")
        body = response.content.decode()
        self.assertIn(self.course.get_absolute_url(), body)
        self.assertIn("/legal/refunds/", body)
        self.assertNotIn("/my-courses/", body)
        self.assertNotIn("/learn/", body)

    def test_llms_txt_describes_the_course(self):
        response = self.client.get("/llms.txt")
        body = response.content.decode()
        self.assertIn("Foundations of Music", body)
        self.assertIn("Payment methods", body)
        self.assertIn("Not available to crawlers", body)


class ContactFormTests(TestCase):
    def test_a_valid_message_is_saved(self):
        response = self.client.post(
            reverse("pages:about"),
            {"name": "Nusrat", "email": "nusrat@example.com", "message": "Is Part 2 ready?"},
            follow=True,
        )
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertContains(response, "your message has been sent")

    def test_the_honeypot_rejects_a_bot_submission(self):
        self.client.post(
            reverse("pages:about"),
            {
                "name": "Bot",
                "email": "bot@example.com",
                "message": "Buy followers",
                "website": "http://spam.example",
            },
        )
        self.assertEqual(ContactMessage.objects.count(), 0)


class TemplateHygieneTests(TestCase):
    """Guards against template mistakes that only show up when rendered."""

    @staticmethod
    def template_files():
        root = Path(settings.BASE_DIR) / "templates"
        return list(root.rglob("*.html")) + list(root.rglob("*.txt"))

    def test_no_multiline_comment_markers(self):
        """`{# ... #}` is single-line only; spanning lines renders it verbatim."""
        offenders = []
        for path in self.template_files():
            text = path.read_text(encoding="utf-8")
            cursor = 0
            while (start := text.find("{#", cursor)) != -1:
                close = text.find("#}", start)
                if close == -1 or "\n" in text[start:close]:
                    offenders.append(
                        f"{path.relative_to(settings.BASE_DIR)}:"
                        f"{text[:start].count(chr(10)) + 1}"
                    )
                    break
                cursor = close + 2
        self.assertEqual(
            offenders,
            [],
            "Use {% comment %}…{% endcomment %} for comments that span lines.",
        )

    def test_every_template_compiles(self):
        """A syntax error in a rarely-visited template should fail here, not live."""
        from django.template.loader import get_template

        root = Path(settings.BASE_DIR) / "templates"
        errors = []
        for path in self.template_files():
            name = str(path.relative_to(root))
            try:
                get_template(name)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors.append(f"{name}: {exc}")
        self.assertEqual(errors, [])


class StylesheetHygieneTests(TestCase):
    """`.shell` owns the responsive gutter; nothing may silently cancel it."""

    def test_no_shell_element_overrides_its_inline_padding(self):
        import re

        root = Path(settings.BASE_DIR) / "templates"
        shorthand = re.compile(r"padding:\s*[^;\"]*\s+\d+px\s+\d")
        offenders = []
        for path in list(root.rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"<[^>]*class=\"[^\"]*\\bshell\\b[^\"]*\"[^>]*>", text):
                if shorthand.search(match.group(0)):
                    offenders.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(
            sorted(set(offenders)),
            [],
            "Use padding-block on a .shell element; the shorthand zeroes the gutter.",
        )

    def test_the_footer_keeps_the_shell_gutter(self):
        css = (Path(settings.BASE_DIR) / "static/css/site.css").read_text(encoding="utf-8")
        block = css.split(".site-footer__inner {", 1)[1].split("}", 1)[0]
        self.assertNotIn("padding:", block)
        self.assertIn("padding-block:", block)
