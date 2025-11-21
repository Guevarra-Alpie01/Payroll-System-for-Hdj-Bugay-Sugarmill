from django.urls import path
from django.contrib import admin
from humanresource import views

app_name = 'humanresource'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('payroll-upload/', views.PayrollUploadView, name='payroll_upload'),
    path('payroll-upload/delete/<int:history_id>/', views.DeleteHistoryView, name='delete_history'), 
    path('employee-details/<str:employee_id>/', views.EmployeeDetailsView, name='view_employee_details'),
    path('search_employee/', views.search_employee, name='search_employee'),
    path('employee-list/', views.EmployeeListView, name='employee_list'),
    path('edit/<str:employee_id>/', views.edit_employee, name='edit_employee'),

]