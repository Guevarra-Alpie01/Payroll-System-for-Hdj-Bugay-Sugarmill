from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import CSVUploadHistory
from navigation_app.models import UsersAccount
import csv
from io import TextIOWrapper
import json

# Create your views here.
def PayrollUploadView(request):
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        if current_role and current_role != 'admin':
            return redirect('humanresource:payroll_upload')
        
    uploader_username = request.session.get('username' , 'hr')

    if request.method == 'POST':
        if 'payroll_file' not in request.FILES:
            messages.error(request, 'NO file selected.')
            return redirect('humanresource:payroll_upload')

        csv_file = request.FILES['payroll_file']

        if not csv_file.name.endswith('.csv'): 
            messages.error(request,'FILE must be a csv')
            return redirect('humanresource:payroll_upload')
        
        try:
            file_wrapper = TextIOWrapper(csv_file.file, encoding='utf-8')
            reader = csv.DictReader(file_wrapper)

            header = reader.fieldnames
            #store the processed data rows
            data_rows = []

            for row in reader:
                # store the dictionary row
                data_rows.append(row)
                #convert list of dictionaries to a json settings
            processed_rows = len(data_rows)
            processed_data_json_str = json.dumps(data_rows)
            
            #save the history  record and the processed data
            CSVUploadHistory.objects.create(
                uploaded_by = uploader_username,
                file_name = csv_file.name,
                status = 'Success',
                processed_data_json = processed_data_json_str,
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
    
    history = CSVUploadHistory.objects.all().order_by('-upload_time')[:20]
    return render(request, 'upload_csv.html', {'history': history})

# In humanresource/views.py

# ... (Existing imports: render, redirect, get_object_or_404, etc.)
from .models import CSVUploadHistory

# ... (Existing PayrollUploadView and HRHomeView)

def DeleteUploadView(request, upload_id):
    """Deletes a specific CSVUploadHistory record."""
    current_role = request.session.get('role')
    
    # Simple access control: only HR or Admin can delete
    if current_role not in ['hr', 'admin']:
        messages.error(request, "Access denied. Only HR or Admin can delete records.")
        return redirect('humanresource:payroll_upload') 

    # We only allow deletion via POST request for security
    if request.method == 'POST':
        # Get the object or return 404 if it doesn't exist
        upload = get_object_or_404(CSVUploadHistory, id=upload_id)
        file_name = upload.file_name 

        try:
            # Delete the record, which also removes the stored payroll data (JSON)
            upload.delete()
            messages.success(request, f'Successfully deleted upload record for file: "{file_name}". The payroll data has been removed from the dashboard.')
        except Exception as e:
            messages.error(request, f'Error deleting upload record: {str(e)}')
            
        return redirect('humanresource:payroll_upload')
    
    # If a GET request somehow reaches this, redirect them.
    return redirect('humanresource:payroll_upload')


def HRHomeView(request):
    current_role = request.session.get('role')

    if current_role not in ['hr', 'admin']:
        messages.error(request, "Access Denied. Hr role required.")
        return redirect('hr_home.html')
    
    successful_uploads = CSVUploadHistory.objects.filter(status='Success').order_by('-upload_time')

    payroll_data=[]

    for upload in successful_uploads:
        if upload.processed_data_json:
            try:
                data_from_json = json.loads(upload.processed_data_json)
                payroll_data.extend(data_from_json)
            except json.JSONDecodeError as e:
                print(f"error decoding json for upload {upload.id}:{e}")
    
    unique_headers = set()
    for row in payroll_data:
        if isinstance(row, dict):
            unique_headers.update(row.keys())

    headers = sorted(list(unique_headers))

    context = {
        'payroll_data': payroll_data,
        'headers': headers,
        'successful_uploads': successful_uploads,
    }

    return render (request, 'hr_home.html',context)