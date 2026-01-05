from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


from .views import (
    UserListAPIView,
    UserDetailAPIView,
    PositionViewSet,
    DepartmentViewSet,
    UserMeView,
    sync_from_ldap_view,
)


router = DefaultRouter()
router.register(r"position", PositionViewSet, basename="position")
router.register(r"department", DepartmentViewSet, basename="department")

urlpatterns = [
    path("token/", TokenObtainPairView.as_view(), name="api-token-obtain-pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="api-token-refresh"),
    path("", UserListAPIView.as_view(), name="user-list-full"),
    path("me", UserMeView.as_view(), name="user-me"),
    path("<int:pk>/", UserDetailAPIView.as_view(), name="user-list-full"),
    path("sync/", sync_from_ldap_view, name="ldap-sync"),
]

urlpatterns += router.urls
