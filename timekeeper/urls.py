from django.urls import path
from django.contrib import admin
from timekeeper import views

app_name = 'timekeeper'

urlpatterns = [
    path('admin/', admin.site.urls),
]