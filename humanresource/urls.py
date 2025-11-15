from django.urls import path
from django.contrib import admin
from humanresource import views

app_name = 'humanresource'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('payroll-upload/', views.PayrollUploadView, name='payroll_upload'),
]