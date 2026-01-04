from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    UserListAPIView,
    UserDetailAPIView,
    PositionViewSet,
    DepartmentViewSet,
    sync_from_ldap_view,
)


router = DefaultRouter()
router.register(r"position", PositionViewSet, basename="position")
router.register(r"department", DepartmentViewSet, basename="department")

urlpatterns = [
    path("", UserListAPIView.as_view(), name="user-list-full"),
    path("<int:pk>/", UserDetailAPIView.as_view(), name="user-list-full"),
    path("sync/", sync_from_ldap_view, name="ldap-sync"),
]

urlpatterns += router.urls
