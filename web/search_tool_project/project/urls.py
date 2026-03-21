from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView
from django.templatetags.static import static

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("favicon.ico", RedirectView.as_view(url=static("search_tool/favicon.svg"), permanent=True)),
    path("", include("search_tool.urls")),
]
