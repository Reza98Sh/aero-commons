import django_filters
from rest_framework.response import Response
from rest_framework import permissions, status, generics
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import api_view, permission_classes
from drf_spectacular.utils import extend_schema
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .models import CustomUser, Department, Position
from .serializers import (
    CustomUserSerializer,
    PositionSerializer,
    DepartmentSerializer,
    UserBriefSerializer,
)


class CustomUserFilter(django_filters.FilterSet):
    """
    Filter class for CustomUser model.
    Supports filtering by various user attributes including hierarchical relationships.
    """

    # Basic user filters
    username = django_filters.CharFilter(lookup_expr="icontains")
    first_name = django_filters.CharFilter(lookup_expr="icontains")
    last_name = django_filters.CharFilter(lookup_expr="icontains")
    first_name_fa = django_filters.CharFilter(lookup_expr="icontains")
    last_name_fa = django_filters.CharFilter(lookup_expr="icontains")
    is_active = django_filters.BooleanFilter()

    email = django_filters.CharFilter(lookup_expr="icontains")

    # Organizational filters
    position = django_filters.NumberFilter(field_name="position__id")
    position_title = django_filters.CharFilter(
        field_name="position__title_en", lookup_expr="icontains"
    )

    # Department filter (through position relationship)
    department = django_filters.NumberFilter(field_name="position__department__id")
    department_name = django_filters.CharFilter(
        field_name="position__department__name", lookup_expr="icontains"
    )

    # Manager filter
    direct_manager = django_filters.NumberFilter(field_name="direct_manager__id")
    direct_manager_username = django_filters.CharFilter(
        field_name="direct_manager__username", lookup_expr="icontains"
    )

    # Profile filters
    personnel_code = django_filters.CharFilter(lookup_expr="icontains")
    identify_code = django_filters.CharFilter(lookup_expr="icontains")
    phone = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "first_name",
            "first_name_fa",
            "last_name_fa",
            "last_name",
            "email",
            "position",
            "is_active",
            "position_title",
            "department",
            "department_name",
            "direct_manager",
            "direct_manager_username",
            "personnel_code",
            "identify_code",
            "phone",
        ]


class UserListAPIView(generics.ListAPIView):
    """
    API View to list all users with their full profile, position, and department details.
    """

    serializer_class = CustomUserSerializer
    filterset_class = CustomUserFilter
    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
    ]

    def get_queryset(self):
        """
        Return all users.
        """
        return CustomUser.objects.select_related(
            "position", "position__department"
        ).all()


class MySubordinatesListView(generics.ListAPIView):
    serializer_class = UserBriefSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = user.subordinates.all()
        return queryset


class UserMeView(generics.RetrieveAPIView):
    serializer_class = CustomUserSerializer
    queryset = CustomUser.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserDetailAPIView(generics.RetrieveUpdateAPIView):
    """
    API View to list all users with their full profile, position, and department details.
    """

    serializer_class = CustomUserSerializer
    queryset = CustomUser.objects.all()


class DepartmentFilter(django_filters.FilterSet):
    """
    FilterSet for Department model.

    Provides filtering by:
        - name: Exact match, case-insensitive contains, and starts with
        - ordering: By name and id
    """

    # Contains filter for partial name matching
    name = django_filters.CharFilter(
        field_name="name",
        lookup_expr="icontains",
        help_text="Filter departments where name contains the given value",
    )

    # Ordering filter
    ordering = django_filters.OrderingFilter(
        fields=(
            ("name", "name"),
            ("id", "id"),
        ),
        field_labels={
            "name": "Department Name",
            "id": "Department ID",
        },
        help_text="Order results by specified field. Prefix with '-' for descending order.",
    )

    class Meta:
        model = Department
        fields = [
            "name",
        ]


class DepartmentViewSet(ReadOnlyModelViewSet):
    serializer_class = DepartmentSerializer
    queryset = Department.objects.all()
    filterset_class = DepartmentFilter

    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
    ]


class PositionFilter(django_filters.FilterSet):
    """
    FilterSet for Position model.

    """

    title_en = django_filters.CharFilter(
        field_name="title_en",
        lookup_expr="icontains",
        help_text="Filter positions where English title contains the given value",
    )

    title_fa = django_filters.CharFilter(
        field_name="title_fa",
        lookup_expr="icontains",
        help_text="Filter positions where Farsi title contains the given value",
    )

    # Department filters
    department = django_filters.NumberFilter(
        field_name="department__id", help_text="Filter by department ID"
    )

    department_name = django_filters.CharFilter(
        field_name="department__name",
        lookup_expr="icontains",
        help_text="Filter by department name (contains)",
    )

    # Ordering filter
    ordering = django_filters.OrderingFilter(
        fields=(
            ("title_en", "title_en"),
            ("title_fa", "title_fa"),
            ("department__name", "department"),
            ("id", "id"),
        ),
        field_labels={
            "title_en": "English Title",
            "title_fa": "Farsi Title",
            "department": "Department Name",
            "id": "Position ID",
        },
        help_text="Order results by specified field. Prefix with '-' for descending order.",
    )

    class Meta:
        model = Position
        fields = [
            "title_en",
            "title_fa",
            "department",
            "department_name",
        ]


class PositionViewSet(ReadOnlyModelViewSet):
    serializer_class = PositionSerializer
    queryset = Position.objects.all()
    filterset_class = PositionFilter
    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
    ]


@extend_schema(
    request=None,
)
@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def sync_from_ldap_view(request):
    try:

        # Execute LDAP synchronization
        result = CustomUser.sync_from_ldap()

        return Response(
            {
                "status": "success",
                "data": {
                    "created": result.get("created", 0),
                    "updated": result.get("updated", 0),
                    "total": result.get("total", 0),
                },
            },
            status=status.HTTP_200_OK,
        )

    except ConnectionError as e:
        # Handle LDAP connection errors
        return Response(
            {
                "status": "error",
                "message": "Failed to connect to LDAP server",
                "detail": str(e),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    except Exception as e:
        # Handle any unexpected errors during sync
        return Response(
            {"status": "error", "message": "LDAP sync failed", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
