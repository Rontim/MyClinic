
from django.urls import path
from djoser.views import UserViewSet
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path(
        "users/", UserViewSet.as_view({"post": "create"}), name="user-register"),
    path("users/me/", UserViewSet.as_view({"get": "me",
         "put": "me", "patch": "me"}), name="user-me"),
    path("login/", TokenObtainPairView.as_view(), name="jwt-create"),
    path("refresh/", TokenRefreshView.as_view(), name="jwt-refresh"),
]
