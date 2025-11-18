from django.urls import path
from django.contrib import admin
from humanresource import views

app_name = 'humanresource'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('payroll-upload/', views.PayrollUploadView, name='payroll_upload'),
    path('payroll/delete/<int:upload_id>/', views.DeleteUploadView, name='payroll_delete'),
    path('home/', views.HRHomeView, name='hr_home'),
]