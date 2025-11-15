from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import CSVUploadHistory
from navigation_app.models import UsersAccount
import csv
from io import TextIOWrapper

# Create your views here.
def PayrollUploadView(request):
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        if current_role and current_role != 'admin':
            return redirect('humanresource:payroll_upload')
        
    uploader_username = request.session.get('username' 'HR User')

    if request.method == 'POST':
        if 'payroll_file' not in request.FILES:
            messages.error(request, 'NO file selected.')
            return redirect('humanresource:payroll_upload')

        csv_file = request.FILES['payroll_file']

        if not csv_file.name.endswith('.csv '): 
            messages.error(request,'FILE must be a csv')
            return redirect('humanresource:payroll_upload')
        
        try:
            file_wrapper = TextIOWrapper(csv_file.file, encoding='utf-8')
            reader = csv.reader(file_wrapper)

            header = next(reader)
            processed_rows = 0

            for row in reader:
                # Process each row as needed
                #processed_rows += 1
                pass # Placeholder for actual processing logic
            
            processed_rows = sum(1 for row in reader)
            CSVUploadHistory.objects.create(
                uploaded_by = uploader_username,
                file_name = csv_file.name,
                status = 'Success',
                details = f"Successfully processed {processed_rows} data rows. Header: {','.join(header)}"
            )
            messages.success(request, f'File "{csv_file.name}" uploaded successfully. Processed {processed_rows} rows.')

        except Exception as e:
            CSVUploadHistory.objects.create(
                uploaded_by = uploader_username,
                file_name = csv_file.name,
                status = 'Failed',
                details = f"Error during processing: {str(e)}"
            )
            messages.error(request, f'Error processing file: {str(e)}')
        return redirect('humanresource:payroll_upload')
    
    history = CSVUploadHistory.objects.all()[:20]
    return render(request, 'upload_csv.html', {'history': history})