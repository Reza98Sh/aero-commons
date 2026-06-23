# aero_commons/tests/test_api.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model

User = get_user_model()

class BaseAPITestCase(APITestCase):
    """
    Base test class that loads fixtures and prepares users.
    """
    fixtures = ["departments", "positions", "users"]

    def setUp(self):
        """
        Initialize API client and common users.
        """
        self.client = APIClient()

        self.ceo = User.objects.get(pk=1)
        self.eng_manager = User.objects.get(pk=2) # superuser
        self.senior_dev = User.objects.get(pk=3)
        self.junior_dev = User.objects.get(pk=4)
        self.dev_user = User.objects.get(pk=5)
        self.hr_manager = User.objects.get(pk=6)
        self.hr_specialist = User.objects.get(pk=7)
        self.inactive_user = User.objects.get(pk=8)


# -------------------------------------------------------------------
# User List API Tests
# -------------------------------------------------------------------

class UserListAPITest(BaseAPITestCase):
    """
    Tests for UserListAPIView.
    """

    def test_list_users(self):
        """
        Authenticated user should receive all users.
        """
        self.client.force_authenticate(user=self.ceo)

        url = reverse("user-list-full")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 8)

    def test_filter_by_username(self):
        """
        Filter users by username (icontains).
        """
        self.client.force_authenticate(user=self.ceo)

        response = self.client.get(
            reverse("user-list-full"),
            {"username": "dev"},
        )

        usernames = [u["username"] for u in response.data]

        self.assertIn("senior_dev", usernames)
        self.assertIn("junior_dev", usernames)
        self.assertIn("dev_user", usernames)

    def test_filter_by_department(self):
        """
        Filter users by Engineering department.
        """
        self.client.force_authenticate(user=self.ceo)

        response = self.client.get(
            reverse("user-list-full"),
            {"department": 1},  # Engineering
        )

        self.assertTrue(len(response.data) >= 4)

    def test_filter_by_position_title(self):
        """
        Filter users by position title.
        """
        self.client.force_authenticate(user=self.ceo)

        response = self.client.get(
            reverse("user-list-full"),
            {"position_title": "Manager"},
        )

        usernames = [u["username"] for u in response.data]
        self.assertIn("eng_manager", usernames)
        self.assertIn("hr_manager", usernames)

    def test_filter_by_direct_manager(self):
        """
        Filter users reporting to Engineering Manager.
        """
        self.client.force_authenticate(user=self.ceo)

        response = self.client.get(
            reverse("user-list-full"),
            {"direct_manager": self.eng_manager.id},
        )

        usernames = [u["username"] for u in response.data]

        self.assertIn("senior_dev", usernames)
        self.assertIn("dev_user", usernames)

    def test_ordering_by_username(self):
        """
        Order users by username ascending.
        """
        self.client.force_authenticate(user=self.ceo)

        response = self.client.get(
            reverse("user-list-full"),
            {"ordering": "username"},
        )

        usernames = [u["username"] for u in response.data]
        self.assertEqual(usernames, sorted(usernames))


# -------------------------------------------------------------------
# User Me API Tests
# -------------------------------------------------------------------

class UserMeAPITest(BaseAPITestCase):
    """
    Tests for UserMeView.
    """

    def test_user_me_authenticated(self):
        """
        Authenticated user receives own profile.
        """
        self.client.force_authenticate(user=self.eng_manager)

        response = self.client.get(reverse("user-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.eng_manager.id)
        self.assertEqual(response.data["username"], "eng_manager")
        self.assertEqual(response.data["department"], "Engineering")
        self.assertEqual(response.data["position"], "Engineering Manager")

    def test_user_me_unauthenticated(self):
        """
        Unauthenticated request should fail.
        """
        response = self.client.get(reverse("user-me"))

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_user_me_direct_manager_field(self):
        """
        Direct manager should be serialized correctly.
        """
        self.client.force_authenticate(user=self.senior_dev)

        response = self.client.get(reverse("user-me"))

        self.assertEqual(
            response.data["direct_manager"]["username"],
            "eng_manager",
        )


# -------------------------------------------------------------------
# Subordinates API Tests
# -------------------------------------------------------------------

class UserSubordinatesAPITest(BaseAPITestCase):
    """
    Tests for MySubordinatesListView.
    """

    def test_ceo_subordinates(self):
        """
        CEO should see Engineering Manager and HR Manager.
        """
        self.client.force_authenticate(user=self.ceo)

        response = self.client.get(reverse("user-subordinates"))

        usernames = [u["username"] for u in response.data]

        self.assertEqual(len(response.data), 2)
        self.assertIn("eng_manager", usernames)
        self.assertIn("hr_manager", usernames)

    def test_engineering_manager_subordinates(self):
        """
        Engineering Manager should see Senior Dev and Dev User.
        """
        self.client.force_authenticate(user=self.eng_manager)

        response = self.client.get(reverse("user-subordinates"))

        usernames = [u["username"] for u in response.data]

        self.assertEqual(len(response.data), 2)
        self.assertIn("senior_dev", usernames)
        self.assertIn("dev_user", usernames)

    def test_senior_dev_subordinates(self):
        """
        Senior Dev should only see Junior Dev.
        """
        self.client.force_authenticate(user=self.senior_dev)

        response = self.client.get(reverse("user-subordinates"))

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["username"], "junior_dev")

    def test_user_without_subordinates(self):
        """
        User with no subordinates should receive empty list.
        """
        self.client.force_authenticate(user=self.junior_dev)

        response = self.client.get(reverse("user-subordinates"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
