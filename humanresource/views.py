from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import CSVUploadHistory, PayrollRecord # Import the new model
from io import TextIOWrapper
from datetime import datetime # Needed for date parsing
from django.db.models import Count # Needed for distinct name 
from django.db import models

# Create your views here.
def PayrollUploadView(request):
    current_role = request.session.get('role')
    
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')
        
    uploader_username = request.session.get('username', 'HR User')

    if request.method == 'POST':
        if 'payroll_file' not in request.FILES:
            messages.error(request, 'No file selected.')
            return redirect('humanresource:payroll_upload')

        uploaded_file = request.FILES['payroll_file']

        if not uploaded_file.name.lower().endswith('.txt'): 
            messages.error(request,'File must be a **.txt** file.')
            return redirect('humanresource:payroll_upload')
        
        try:
            file_wrapper = TextIOWrapper(uploaded_file.file, encoding='utf-8')
            lines = file_wrapper.read().splitlines() 
            
            if not lines:
                messages.error(request, 'The uploaded file is empty.')
                return redirect('humanresource:payroll_upload')

            # 1. Create History Record immediately (to link payroll records)
            history_record = CSVUploadHistory.objects.create(
                uploaded_by = uploader_username,
                filename = uploaded_file.name,
            )

            # Skip header (lines[0])
            data_rows = lines[1:]
            processed_rows = 0
            
            records_to_create = []

            for row in data_rows:
                # Based on fixed-width columns (indices are 0-based)
                # 9:19   = employee_id (char index 8 to 18, length 10)
                # 20:34  = employee_name (char index 19 to 33, length 15)
                # 36:37  = log_code (char index 35 to 36, length 2)
                # 38:48  = date (char index 37 to 47, length 11) -> 2025/01/26
                # 50:58  = time (char index 49 to 57, length 9) -> 07:45:00
                
                try:
                    # Clean up data by stripping whitespace/tabs caused by separators
                    emp_id = row[8:18].strip()
                    emp_name = row[19:33].strip()
                    code = row[36:37].strip()
                    date_str = row[38:48].strip()
                    log_t = row[49:57].strip()

                    # Convert date string (e.g., '2025/01/26') to Python date object
                    log_d = datetime.strptime(date_str, '%Y/%m/%d').date()

                    if emp_id and emp_name:
                         records_to_create.append(PayrollRecord(
                            employee_id=emp_id,
                            employee_name=emp_name,
                            log_code=code,
                            log_date=log_d,
                            log_time=log_t,
                            upload_history=history_record
                        ))
                         processed_rows += 1

                except ValueError as ve:
                    # Log error but continue processing other rows
                    messages.warning(request, f"Skipped row due to data format error: {str(ve)}")
                    continue
                except IndexError:
                     messages.warning(request, f"Skipped row due to incorrect fixed-width format (row too short).")
                     continue

            # Bulk create records for efficiency
            if records_to_create:
                PayrollRecord.objects.bulk_create(records_to_create)

            messages.success(request, f'File "{uploaded_file.name}" uploaded successfully. Processed {processed_rows} data entries.')

        except Exception as e:
            # Handle general exceptions
            messages.error(request, f'Error processing file: {str(e)}')
            # Cleanup history if created but failed
            if 'history_record' in locals():
                history_record.delete()
        
        return redirect('humanresource:payroll_upload')
    
    # GET Request: Display upload history
    history = CSVUploadHistory.objects.order_by('-upload_time')[:20]
    
    # NEW LOGIC: Get unique employees and their first log date
    # Annotate to get the first (oldest) log date for each unique employee
    unique_employees = PayrollRecord.objects.values(
        'employee_name', 'employee_id'
    ).annotate(
        first_log=models.Min('log_date')
    ).order_by('first_log') # Order chronologically by the first log date
    
    context = {
        'history': history,
        'unique_employees': unique_employees
    }
    return render(request, 'upload_csv.html', context)


# ... (DeleteHistoryView function remains the same) ...
def DeleteHistoryView(request, history_id):
    # 1. Role Check (important for security)
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required for deletion.")
        return redirect('homepage')
        
    # 2. Get the object or return 404. Deleting history record cascades to PayrollRecords.
    history_record = get_object_or_404(CSVUploadHistory, id=history_id)
    
    # 3. Perform deletion
    if request.method == 'POST':
        file_name = history_record.filename
        history_record.delete()
        messages.success(request, f'History record for file "{file_name}" and associated payroll data deleted successfully.')
    else:
        messages.error(request, 'Invalid request method for deletion.')

    return redirect('humanresource:payroll_upload')

# humanresource/views.py (Add this function below DeleteHistoryView)

def EmployeeDetailsView(request, employee_id):
    # Security check (ensure only HR can view)
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')

    # 1. Fetch all records for the employee, ordered by date and time
    raw_logs = PayrollRecord.objects.filter(employee_id=employee_id).order_by('log_date', 'log_time')
    
    if not raw_logs:
        messages.warning(request, f"No payroll records found for Employee ID: {employee_id}")
        return redirect('humanresource:payroll_upload')

    # Get the employee name for the title (it should be consistent)
    employee_name = raw_logs.first().employee_name

    # 2. Process logs into structured daily entries
    # Structure: { date: { 'date': date_obj, 'AM_IN': time, 'AM_OUT': time, ... } }
    daily_summary = {}

    CODE_MAP = {
        '0': 'AM_IN',
        '1': 'AM_OUT',
        '2': 'PM_IN',
        '3': 'PM_OUT',
        '5': 'OT_IN',
        '6': 'OT_OUT',
    }
    
    # Initialize the date structures
    for log in raw_logs:
        date_key = log.log_date.strftime('%Y-%m-%d')
        
        if date_key not in daily_summary:
            daily_summary[date_key] = {
                'date': log.log_date,
                'AM_IN': None,
                'AM_OUT': None,
                'PM_IN': None,
                'PM_OUT': None,
                'OT_IN': None,
                'OT_OUT': None,
                'raw_logs': [] # Optional: keep raw logs for detailed view
            }
        
        # Map the log code to the appropriate field and store the time
        log_type = CODE_MAP.get(log.log_code)
        
        if log_type:
            # We assume the data is already chronologically ordered by the ORM query
            # So the first time found for a slot is the correct one (e.g., first AM_IN is the correct time)
            if not daily_summary[date_key][log_type]:
                 daily_summary[date_key][log_type] = log.log_time
            
        daily_summary[date_key]['raw_logs'].append(log)

    # Convert the dictionary to a list and sort by date descending for display
    summary_list = sorted(daily_summary.values(), key=lambda x: x['date'], reverse=True)

    context = {
        'employee_id': employee_id,
        'employee_name': employee_name,
        'daily_summary': summary_list,
    }

    return render(request, 'employee_details.html', context)
