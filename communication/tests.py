from django.test import TestCase
from django.urls import reverse

from core.models import School, User
from core.signals import sync_role_group_membership

from .models import Announcement


# ---------------------------------------------------------------------------
# Shared test case base
# ---------------------------------------------------------------------------

class CommunicationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="KSMS Comms Test School",
            code="COMMTEST",
            slug="ksms-comms-test",
            email="comms@testschool.example.com",
            phone="+254700000099",
            county="Nairobi",
        )

        cls.admin_user = User.objects.create_user(
            username="admin.comms",
            email="admin.comms@example.com",
            password="ChangeMe12345!",
            role=User.Role.SCHOOL_ADMIN,
        )
        sync_role_group_membership(cls.admin_user)

        cls.teacher_a = User.objects.create_user(
            username="teacher.comms.a",
            email="teacher.comms.a@example.com",
            password="ChangeMe12345!",
            role=User.Role.TEACHER,
        )
        sync_role_group_membership(cls.teacher_a)

        cls.teacher_b = User.objects.create_user(
            username="teacher.comms.b",
            email="teacher.comms.b@example.com",
            password="ChangeMe12345!",
            role=User.Role.TEACHER,
        )
        sync_role_group_membership(cls.teacher_b)

        cls.student_user = User.objects.create_user(
            username="student.comms",
            email="student.comms@example.com",
            password="ChangeMe12345!",
            role=User.Role.STUDENT,
        )
        sync_role_group_membership(cls.student_user)

        cls.parent_user = User.objects.create_user(
            username="parent.comms",
            email="parent.comms@example.com",
            password="ChangeMe12345!",
            role=User.Role.PARENT,
        )
        sync_role_group_membership(cls.parent_user)

        cls.ann_all = Announcement.objects.create(
            school=cls.school,
            title="All announcement",
            body="Body for everyone",
            audience=Announcement.Audience.ALL,
            is_active=True,
            author=cls.teacher_a,
        )
        cls.ann_students = Announcement.objects.create(
            school=cls.school,
            title="Students only",
            body="For students",
            audience=Announcement.Audience.STUDENTS,
            is_active=True,
            author=cls.teacher_a,
        )
        cls.ann_parents = Announcement.objects.create(
            school=cls.school,
            title="Parents only",
            body="For parents",
            audience=Announcement.Audience.PARENTS,
            is_active=True,
            author=cls.teacher_a,
        )
        cls.ann_teachers = Announcement.objects.create(
            school=cls.school,
            title="Teachers only",
            body="For teachers",
            audience=Announcement.Audience.TEACHERS,
            is_active=True,
            author=cls.teacher_a,
        )
        # Inactive, owned by teacher_b
        cls.ann_inactive = Announcement.objects.create(
            school=cls.school,
            title="Inactive announcement",
            body="Not active",
            audience=Announcement.Audience.ALL,
            is_active=False,
            author=cls.teacher_b,
        )


# ---------------------------------------------------------------------------
# List access tests
# ---------------------------------------------------------------------------

class AnnouncementListAccessTests(CommunicationTestCase):

    def get_url(self):
        return reverse("communication:announcement-list")

    def test_unauthenticated_redirects(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 302)

    def test_admin_sees_200(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_teacher_sees_200(self):
        self.client.force_login(self.teacher_a)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_student_sees_200_but_filtered(self):
        self.client.force_login(self.student_user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        titles = [a.title for a in response.context["announcements"]]
        self.assertIn("All announcement", titles)
        self.assertIn("Students only", titles)
        # Must NOT see teachers-only or parents-only
        self.assertNotIn("Teachers only", titles)
        self.assertNotIn("Parents only", titles)
        # Must NOT see inactive
        self.assertNotIn("Inactive announcement", titles)

    def test_parent_sees_200_but_filtered(self):
        self.client.force_login(self.parent_user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        titles = [a.title for a in response.context["announcements"]]
        self.assertIn("All announcement", titles)
        self.assertIn("Parents only", titles)
        self.assertNotIn("Students only", titles)
        self.assertNotIn("Teachers only", titles)

    def test_parent_does_not_see_audience_filter(self):
        self.client.force_login(self.parent_user)
        response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<label class=\"block text-xs font-semibold text-slate-600 mb-1\">Audience</label>", html=True)
        self.assertNotIn("audience", response.context["filter_form"].fields)

    def test_parent_audience_query_param_is_ignored(self):
        self.client.force_login(self.parent_user)
        response = self.client.get(self.get_url(), {"audience": Announcement.Audience.PARENTS})

        self.assertEqual(response.status_code, 200)
        titles = [a.title for a in response.context["announcements"]]
        self.assertIn("All announcement", titles)
        self.assertIn("Parents only", titles)
        self.assertNotIn("Students only", titles)
        self.assertNotIn("Teachers only", titles)

    def test_admin_sees_inactive(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        titles = [a.title for a in response.context["announcements"]]
        self.assertIn("Inactive announcement", titles)

    def test_announcement_list_boosted_htmx_returns_full_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(
            self.get_url(),
            HTTP_HX_REQUEST="true",
            HTTP_HX_BOOSTED="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "communication/announcement_list.html")


# ---------------------------------------------------------------------------
# Detail access tests
# ---------------------------------------------------------------------------

class AnnouncementDetailAccessTests(CommunicationTestCase):

    def test_student_cannot_access_teachers_only(self):
        self.client.force_login(self.student_user)
        url = reverse("communication:announcement-detail", kwargs={"pk": self.ann_teachers.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_parent_cannot_access_students_only(self):
        self.client.force_login(self.parent_user)
        url = reverse("communication:announcement-detail", kwargs={"pk": self.ann_students.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_admin_can_access_any(self):
        self.client.force_login(self.admin_user)
        url = reverse("communication:announcement-detail", kwargs={"pk": self.ann_teachers.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_teacher_can_access_any(self):
        self.client.force_login(self.teacher_a)
        url = reverse("communication:announcement-detail", kwargs={"pk": self.ann_students.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_student_can_access_student_announcement(self):
        self.client.force_login(self.student_user)
        url = reverse("communication:announcement-detail", kwargs={"pk": self.ann_students.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Create tests
# ---------------------------------------------------------------------------

class AnnouncementCreateTests(CommunicationTestCase):

    def get_url(self):
        return reverse("communication:announcement-create")

    def _valid_post(self, title="Test create announcement"):
        return {
            "school": self.school.pk,
            "title": title,
            "body": "Body text here",
            "audience": Announcement.Audience.ALL,
            "is_active": True,
        }

    def test_student_cannot_create(self):
        self.client.force_login(self.student_user)
        response = self.client.post(self.get_url(), self._valid_post())
        self.assertIn(response.status_code, (403, 302))
        self.assertFalse(Announcement.objects.filter(title="Test create announcement").exists())

    def test_parent_cannot_create(self):
        self.client.force_login(self.parent_user)
        response = self.client.post(self.get_url(), self._valid_post())
        self.assertIn(response.status_code, (403, 302))

    def test_teacher_can_create(self):
        self.client.force_login(self.teacher_a)
        response = self.client.post(self.get_url(), self._valid_post("Teacher created"))
        self.assertIn(response.status_code, (200, 302))
        ann = Announcement.objects.filter(title="Teacher created").first()
        self.assertIsNotNone(ann)
        self.assertEqual(ann.author, self.teacher_a)

    def test_admin_can_create(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(self.get_url(), self._valid_post("Admin created"))
        self.assertIn(response.status_code, (200, 302))
        ann = Announcement.objects.filter(title="Admin created").first()
        self.assertIsNotNone(ann)
        self.assertEqual(ann.author, self.admin_user)

    def test_unauthenticated_redirected(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 302)


# ---------------------------------------------------------------------------
# Update / Delete ownership tests
# ---------------------------------------------------------------------------

class AnnouncementUpdateDeleteOwnershipTests(CommunicationTestCase):

    def test_teacher_can_update_own(self):
        self.client.force_login(self.teacher_a)
        url = reverse("communication:announcement-update", kwargs={"pk": self.ann_all.pk})
        response = self.client.post(url, {
            "school": self.school.pk,
            "title": "Updated title",
            "body": "Updated body",
            "audience": Announcement.Audience.ALL,
            "is_active": True,
        })
        self.assertIn(response.status_code, (200, 302))
        self.ann_all.refresh_from_db()
        self.assertEqual(self.ann_all.title, "Updated title")

    def test_teacher_cannot_update_others(self):
        self.client.force_login(self.teacher_b)
        url = reverse("communication:announcement-update", kwargs={"pk": self.ann_all.pk})
        response = self.client.post(url, {
            "school": self.school.pk,
            "title": "Hijacked title",
            "body": "Hijacked body",
            "audience": Announcement.Audience.ALL,
            "is_active": True,
        })
        self.assertEqual(response.status_code, 403)
        self.ann_all.refresh_from_db()
        self.assertNotEqual(self.ann_all.title, "Hijacked title")

    def test_admin_can_update_any(self):
        self.client.force_login(self.admin_user)
        url = reverse("communication:announcement-update", kwargs={"pk": self.ann_all.pk})
        response = self.client.post(url, {
            "school": self.school.pk,
            "title": "Admin updated title",
            "body": "Admin body",
            "audience": Announcement.Audience.ALL,
            "is_active": True,
        })
        self.assertIn(response.status_code, (200, 302))
        self.ann_all.refresh_from_db()
        self.assertEqual(self.ann_all.title, "Admin updated title")

    def test_teacher_can_delete_own(self):
        # Use ann_all which was reset if this is run after update test — create fresh
        ann = Announcement.objects.create(
            school=self.school,
            title="To be deleted by teacher",
            body="body",
            audience=Announcement.Audience.ALL,
            is_active=True,
            author=self.teacher_a,
        )
        self.client.force_login(self.teacher_a)
        url = reverse("communication:announcement-delete", kwargs={"pk": ann.pk})
        response = self.client.post(url)
        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(Announcement.objects.filter(pk=ann.pk).exists())

    def test_teacher_cannot_delete_others(self):
        self.client.force_login(self.teacher_b)
        # teacher_b does NOT own ann_all (owned by teacher_a)
        url = reverse("communication:announcement-delete", kwargs={"pk": self.ann_teachers.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Announcement.objects.filter(pk=self.ann_teachers.pk).exists())

    def test_admin_can_delete_any(self):
        ann = Announcement.objects.create(
            school=self.school,
            title="To be deleted by admin",
            body="body",
            audience=Announcement.Audience.PARENTS,
            is_active=True,
            author=self.teacher_b,
        )
        self.client.force_login(self.admin_user)
        url = reverse("communication:announcement-delete", kwargs={"pk": ann.pk})
        response = self.client.post(url)
        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(Announcement.objects.filter(pk=ann.pk).exists())

