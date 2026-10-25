"""Public pages, SEO output and crawler discovery files."""

import json
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from core.testing import EnglishPagesMixin
from courses.models import Course, Module
from pages.models import ContactMessage, Faq, LegalPage


class PublicPageTests(EnglishPagesMixin, TestCase):
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

    def test_home_sells_the_course_and_its_free_modules(self):
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "Why this course?")
        self.assertContains(response, "Lessons in English and Bangla")
        self.assertContains(response, "Who is this course for?")
        self.assertContains(response, "Learn with other musicians")
        self.assertContains(response, "Try the first module for free")
        self.assertContains(response, 'name="prefill"')
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_home_counts_every_free_module(self):
        Module.objects.filter(course=self.course).update(access=Module.Access.FREE)
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "Try the first 2 modules for free")
        self.assertContains(response, "first 2 modules and start learning today")
        self.assertContains(response, "Notation")

    def test_home_features_the_promoted_course(self):
        Course.objects.create(
            title="Harmony in Practice", slug="harmony", summary="Chords.",
            description="D.", status=Course.Status.PUBLISHED, position=5,
            promote_on_home=True,
        )
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.context["course"].slug, "harmony")

    def test_home_falls_back_to_the_first_course_when_none_is_promoted(self):
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.context["course"], self.course)

    def test_a_promoted_draft_is_not_featured(self):
        Course.objects.create(
            title="Draft", slug="draft", summary="S.", description="D.",
            status=Course.Status.DRAFT, promote_on_home=True,
        )
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.context["course"], self.course)

    def test_the_home_page_no_longer_links_to_a_trailer(self):
        Course.objects.filter(pk=self.course.pk).update(
            trailer_url_en="https://youtu.be/dQw4w9WgXcQ"
        )
        response = self.client.get(reverse("pages:home"))
        self.assertNotContains(response, "#trailer")

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

    def test_home_hero_shows_the_circle_of_fifths_and_plain_cta(self):
        """The hero shows the diagram and "Start Module 1", with no "free" note."""
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "img/circle-of-fifths.svg")
        self.assertContains(response, "Start Module 1</a>", count=2)
        self.assertNotContains(response, "Start Module 1 free")
        self.assertNotContains(response, "<span>Module 1 free</span>")

    def test_course_nav_link_goes_straight_to_the_course(self):
        """"Course" in the header opens the course page, in its own language."""
        pages = (
            ("en", "/en/courses/foundations-of-music/"),
            ("bn", "/courses/foundations-of-music/"),
        )
        for language, url in pages:
            with self.subTest(language=language), translation.override(language):
                response = self.client.get(reverse("pages:home"))
                nav = response.content.decode().split('id="primary-nav"')[1].split("</nav>")[0]
                self.assertIn(f'<a href="{url}"', nav)

    def test_about_is_hidden_in_both_languages(self):
        """No link to About, and its old address redirects to the contact form."""
        for language in ("en", "bn"):
            with self.subTest(language=language), translation.override(language):
                response = self.client.get(reverse("pages:home"))
                self.assertNotContains(response, "/about/")
                redirect = self.client.get(f"{reverse('pages:home')}about/")
                self.assertRedirects(redirect, reverse("pages:contact"), status_code=301)

    def test_footer_names_the_site_and_instructor(self):
        """The footer line reads "DhakaBassist by Tanveer Haque" in both languages."""
        response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "DhakaBassist by Tanveer Haque")
        with translation.override("bn"):
            response = self.client.get(reverse("pages:home"))
        self.assertContains(response, "তানভীর হক-এর DhakaBassist")

    def test_contact_page_seo(self):
        """Title, canonical URL, robots directive and JSON-LD types."""
        response = self.client.get(reverse("pages:contact"))
        self.assertContains(response, "<title>Contact us · DhakaBassist</title>")
        self.assertContains(
            response, f'<link rel="canonical" href="{settings.SITE["base_url"]}/en/contact/">'
        )
        self.assertContains(response, '<meta name="robots" content="index, follow">')
        body = response.content.decode()
        start = body.index('<script type="application/ld+json">') + len(
            '<script type="application/ld+json">'
        )
        payload = json.loads(body[start : body.index("</script>", start)])
        types = {node["@type"] for node in payload["@graph"]}
        self.assertEqual(types, {"EducationalOrganization", "BreadcrumbList"})

    def test_404_page_uses_the_site_layout(self):
        response = self.client.get("/en/no-such-page/")
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


class ContactFormTests(EnglishPagesMixin, TestCase):
    def captcha(self):
        """The token and right answer from a fresh contact form."""
        form = self.client.get(reverse("pages:contact")).context["form"]
        return form["captcha_token"].value(), sum(form.captcha_operands)

    def post(self, **fields):
        token, answer = self.captcha()
        data = {
            "name": "Nusrat",
            "email": "nusrat@example.com",
            "message": "Is Part 2 ready?",
            "captcha_token": token,
            "captcha": answer,
            **fields,
        }
        return self.client.post(reverse("pages:contact"), data, follow=True)

    def test_a_valid_message_is_saved(self):
        response = self.post()
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertContains(response, "your message has been sent")

    def test_the_question_is_on_the_page(self):
        response = self.client.get(reverse("pages:contact"))
        first, second = response.context["form"].captcha_operands
        self.assertContains(response, f"What is {first} + {second}?")
        self.assertContains(response, 'name="captcha_token"')

    def test_a_wrong_answer_is_rejected_with_a_new_question(self):
        token, answer = self.captcha()
        response = self.post(captcha_token=token, captcha=answer + 1)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, "That answer is not right")
        # The form keeps the message but asks a new question.
        self.assertContains(response, "Is Part 2 ready?")
        self.assertNotContains(response, token)

    def test_a_tampered_or_missing_token_is_rejected(self):
        for token in ("forged:token", ""):
            with self.subTest(token=token):
                response = self.post(captcha_token=token)
                self.assertContains(response, "This question has expired")
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_an_expired_question_is_rejected(self):
        with mock.patch("pages.captcha.MAX_AGE", -1):
            response = self.post()
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, "This question has expired")

    def test_the_honeypot_rejects_a_bot_submission(self):
        self.post(name="Bot", message="Buy followers", website="http://spam.example")
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
