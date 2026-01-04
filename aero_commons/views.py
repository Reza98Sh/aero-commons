from rest_framework import generics
from .models import CustomUser
from .serializers import CustomUserSerializer


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
            "position", "position__department", "info"
        ).all()
