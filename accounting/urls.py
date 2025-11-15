from django.urls import path
from django.contrib import admin
from accounting import views
app_name = 'accounting'

urlpatterns = [
    path('admin/', admin.site.urls),
]