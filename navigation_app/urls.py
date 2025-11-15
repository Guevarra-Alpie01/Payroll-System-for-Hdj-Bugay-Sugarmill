from django.urls import path, include
from django.contrib import admin
from navigation_app import views

app_name = 'navigation_app'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.Base, name="base"),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

#Users Urls
    path('user-home/', views.UserHome, name='user_home'),

#Admin Urls
    path('admin-home/', views.admin_home, name='admin_home'),
    path('add-user/', views.AddUser, name="AddUser"),
]