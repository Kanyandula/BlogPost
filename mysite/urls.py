"""mysite URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path
from django.views.decorators.cache import cache_page

from account.views import (
    account_view,
    author_profile_view,
    confirm_email_view,
    login_view,
    logout_view,
    must_authenticate_view,
    registration_view,
    resend_verification_view,
    verification_sent_view,
)
from blog.sitemaps import BlogPostSitemap, CategorySitemap, StaticSitemap
from personal.views import (
    about_screen_view,
    api_screen_view,
    contact_screen_view,
    home_screen_view,
    search_view,
    subscribe_view,
)

sitemaps = {
    'posts': BlogPostSitemap,
    'categories': CategorySitemap,
    'static': StaticSitemap,
}


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /api/",
        "Disallow: /account/",
        "",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path('', home_screen_view, name="home"),
    path('search/', search_view, name="search"),
    path('subscribe/', subscribe_view, name="subscribe"),
    path('robots.txt', robots_txt, name="robots"),
    path('sitemap.xml', cache_page(86400)(sitemap), {'sitemaps': sitemaps}, name='sitemap'),
    path('account/', account_view, name="account"),
    path('admin/', admin.site.urls),
    path('blog/', include('blog.urls', 'blog')),
    path('login/', login_view, name="login"),
    path('logout/', logout_view, name="logout"),
  	path('must_authenticate/', must_authenticate_view, name="must_authenticate"),
    path('register/', registration_view, name="register"),
    path('verification-sent/', verification_sent_view, name='verification_sent'),
    path('confirm-email/<str:uidb64>/<str:token>/', confirm_email_view, name='confirm_email'),
    path('resend-verification/', resend_verification_view, name='resend_verification'),
    path('author/<str:username>/', author_profile_view, name="author_profile"),
    path('about', about_screen_view, name= "about"),
    path('contact/', contact_screen_view, name= "contact"),
    path('api/', api_screen_view, name= "api"),
    
    # CKEditor 5
    path('ckeditor5/', include('django_ckeditor_5.urls')),

    # REST FRAMEWORK URLS
    path('api/blog/', include('blog.api.urls', 'blog_api')),
    path('api/account/', include('account.api.urls', 'account_api')),

    # Password reset links (ref: https://github.com/django/django/blob/master/django/contrib/auth/views.py)
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), 
        name='password_change_done'),

    path('password_change/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change.html'), 
        name='password_change'),

    path('password_reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_done.html'),
     name='password_reset_done'),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'),
     name='password_reset_complete'),
]

handler404 = 'django.views.defaults.page_not_found'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
