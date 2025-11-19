from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import CSVUploadHistory, PayrollRecord # Import the new model
from io import TextIOWrapper
from django.db.models import Count # Needed for distinct name 
from django.db import models
from datetime import datetime, time, timedelta

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
                file_name = uploaded_file.name, # <-- CORRECTED: file_name
            )

            # Skip header (lines[0])
            data_rows = lines[1:]
            processed_rows = 0
            
            records_to_create = []

            for row in data_rows:
                # Based on fixed-width columns (indices are 0-based)
                # 9:19   = employee_id (char index 8 to 18, length 10)
                # 20:34  = employee_name (char index 19 to 33, length 15)
                # 36:37  = log_code (char index 35 to 36, length 2)
                # 38:48  = date (char index 37 to 47, length 11) -> 2025/01/26
                # 50:58  = time (char index 49 to 57, length 9) -> 07:45:00
                
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
        file_name = history_record.file_name # <-- CORRECTED: file_name
        history_record.delete()
        messages.success(request, f'History record for file "{file_name}" and associated payroll data deleted successfully.')
    else:
        messages.error(request, 'Invalid request method for deletion.')

    return redirect('humanresource:payroll_upload')

# humanresource/views.py (EmployeeDetailsView function remains the same)

def EmployeeDetailsView(request, employee_id):
    # Security check (ensure only HR can view)
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')

    # 1. Fetch all records for the employee, ordered by date and time
    # Ordering by log_date and log_time is CRUCIAL for proper grouping and pairing.
    raw_logs = PayrollRecord.objects.filter(employee_id=employee_id).order_by('log_date', 'log_time')
    
    if not raw_logs:
        messages.warning(request, f"No payroll records found for Employee ID: {employee_id}")
        return redirect('humanresource:payroll_upload')

    employee_name = raw_logs.first().employee_name
    daily_summary = {}

    CODE_MAP = {
        '0': 'AM_IN', '1': 'AM_OUT',
        '2': 'PM_IN', '3': 'PM_OUT',
        '5': 'OT_IN', '6': 'OT_OUT',
    }
    
    # Step 2: Initialize and group logs (NO CHANGE HERE)
    for log in raw_logs:
        date_key = log.log_date.strftime('%Y-%m-%d')
        
        if date_key not in daily_summary:
            daily_summary[date_key] = {
                'date': log.log_date,
                'AM_IN': None, 'AM_OUT': None,
                'PM_IN': None, 'PM_OUT': None,
                'OT_IN': None, 'OT_OUT': None,
                'total_hours': timedelta(0), 
                'raw_logs': []
            }
        
        log_type = CODE_MAP.get(log.log_code)
        
        # We store the first time found for the slot (the ORM order helps here)
        if log_type and not daily_summary[date_key][log_type]:
             daily_summary[date_key][log_type] = log.log_time
            
        daily_summary[date_key]['raw_logs'].append(log)

    # --- 3. UPDATED CALCULATION LOGIC ---
    for key, data in daily_summary.items():
        total_delta = timedelta(0)
        
        # --- SCENARIO 1: Simple Day/After Shift (AM_IN, PM_OUT) ---
        # If AM_OUT is missing but PM_IN is missing, treat AM_IN to PM_OUT as one span.
        # This handles your example: "am in is 8:00 am, pm out is 4:00 pm"
        if data.get('AM_IN') and data.get('PM_OUT') and not data.get('AM_OUT') and not data.get('PM_IN'):
            # Calculate the total span (e.g., 8:00 to 16:00, subtract break later if needed)
            shift_duration = calculate_hours(data.get('AM_IN'), data.get('PM_OUT'))
            total_delta += shift_duration
            
        else:
            # --- SCENARIO 2: Standard Shifts (Paired Logs) ---
            # Calculate AM Hours (0 -> 1)
            am_duration = calculate_hours(data.get('AM_IN'), data.get('AM_OUT'))
            total_delta += am_duration
            
            # Calculate PM Hours (2 -> 3)
            pm_duration = calculate_hours(data.get('PM_IN'), data.get('PM_OUT'))
            total_delta += pm_duration
        
        # --- SCENARIO 3: Overtime/Graveyard Shifts (5 -> 6) ---
        # OT calculation always applies
        ot_duration = calculate_hours(data.get('OT_IN'), data.get('OT_OUT'))
        total_delta += ot_duration
        
        # Store the total duration (timedelta object)
        data['total_hours'] = total_delta

    # Convert the dictionary to a list and sort by date descending for display
    summary_list = sorted(daily_summary.values(), key=lambda x: x['date'], reverse=True)

    context = {
        'employee_id': employee_id,
        'employee_name': employee_name,
        'daily_summary': summary_list,
    }

    return render(request, 'employee_details.html', context)

def calculate_hours(time_in_str, time_out_str):
    """
    Calculates the time difference (timedelta) between two time strings ('HH:MM:SS').
    Handles shifts that cross over midnight (time_out < time_in).
    """
    if not time_in_str or not time_out_str:
        return timedelta(0)
    
    TIME_FORMAT = '%H:%M:%S'
    try:
        # 1. Convert time strings to datetime objects (using a dummy date)
        dt_in = datetime.strptime(time_in_str, TIME_FORMAT)
        dt_out = datetime.strptime(time_out_str, TIME_FORMAT)
        
        # 2. Check for Midnight Crossover (Graveyard Shift)
        # If the OUT time is chronologically earlier than the IN time, 
        # it means the OUT occurred on the next day.
        if dt_out < dt_in:
            dt_out += timedelta(days=1)  # Add 24 hours to the OUT time
            
        return dt_out - dt_in
    except ValueError:
        # Handles malformed time strings
        return timedelta(0)