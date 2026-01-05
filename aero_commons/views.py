from rest_framework.response import Response
from rest_framework import permissions, status, generics
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import api_view, permission_classes

from .models import CustomUser, Department, Position
from .serializers import CustomUserSerializer, PositionSerializer, DepartmentSerializer


class UserListAPIView(generics.ListAPIView):
    """
    API View to list all users with their full profile, position, and department details.
    """

    serializer_class = CustomUserSerializer

    def get_queryset(self):
        """
        Return all users.
        """
        return CustomUser.objects.select_related(
            "position", "position__department"
        ).all()


class UserMeView(generics.RetrieveAPIView):
    serializer_class = CustomUserSerializer
    queryset = CustomUser.objects.all()

    def get_object(self):
        return self.request.user

    def get_queryset(self):
        query = CustomUser.objects.all()
        return query


class UserDetailAPIView(generics.RetrieveUpdateAPIView):
    """
    API View to list all users with their full profile, position, and department details.
    """

    serializer_class = CustomUserSerializer
    queryset = CustomUser.objects.all()


class DepartmentViewSet(ReadOnlyModelViewSet):
    serializer_class = DepartmentSerializer
    queryset = Department.objects.all()


class PositionViewSet(ReadOnlyModelViewSet):
    serializer_class = PositionSerializer
    queryset = Position.objects.all()


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
