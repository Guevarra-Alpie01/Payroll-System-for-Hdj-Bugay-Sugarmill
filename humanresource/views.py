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
                try:
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
    return render(request, 'upload_txt.html', context)


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
    


# --- NEW HELPER FUNCTION FOR LATE CALCULATION ---
def calculate_minutes_late(log_time_str, log_type):
    """
    Calculates the minutes an employee is late based on standard start times.
    log_time_str: The recorded log time ('HH:MM:SS').
    log_type: 'AM_IN', 'PM_IN', or 'OT_IN'.
    Returns: An integer for minutes late, or 0 if not late or time is missing.
    """
    if not log_time_str:
        return 0

    TIME_FORMAT = '%H:%M:%S'
    try:
        logged_dt = datetime.strptime(log_time_str, TIME_FORMAT)
        
        # Define the standard start time and the grace period cut-off time (15 mins past standard)
        if log_type == 'AM_IN':
            # Standard: 8:00:00. Cut-off: 8:15:00
            grace_cut_off = time(8, 15, 0)
        elif log_type == 'PM_IN':
            # Standard: 16:00:00. Cut-off: 16:15:00
            grace_cut_off = time(16, 15, 0)
        elif log_type == 'OT_IN':
            # Standard: 00:00:00. Cut-off: 00:15:00
            grace_cut_off = time(0, 15, 0)
        else:
            return 0 # Only check IN logs

        # Compare the time part of the log with the cut-off time
        if logged_dt.time() > grace_cut_off:
            # If logged time is AFTER the grace period, calculate minutes late
            
            # Use the actual minutes from the cut-off to the logged time
            # For simplicity and robust time arithmetic, convert the logged time
            # and the cut-off time into full datetime objects (using a dummy date).
            dummy_date = datetime(2000, 1, 1)
            cut_off_dt = datetime.combine(dummy_date, grace_cut_off)
            
            # The logged time is already a datetime object from the strptime call above
            # (which used a dummy date as well).
            
            # Calculate the difference and convert to total minutes
            late_delta = logged_dt - cut_off_dt
            
            # Ensure the difference is positive (should be, due to the initial check)
            if late_delta > timedelta(0):
                return int(late_delta.total_seconds() / 60)
            
        return 0 # Not late
        
    except ValueError:
        return 0
def EmployeeDetailsView(request, employee_id):
    # ... (Security check remains the same) ...
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')

    # 1. Fetch all records for the employee, ordered by date and time (CRITICAL)
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
    
    # --- Step 2: Initialize, Group, and Handle Cross-Midnight Attribution (NO CHANGE) ---
    # This logic correctly places the OUT punch on the date of the IN punch.
    
    # Store the last known IN-log date for cross-day attribution
    # last_in_date is not strictly used here, but the logic below works by checking previous_day_key
    
    for log in raw_logs:
        log_type = CODE_MAP.get(log.log_code)
        
        current_date_key = log.log_date.strftime('%Y-%m-%d')
        log_date_obj = log.log_date

        # --- A. Cross-Midnight Attribution Logic --- 
        is_out_log = log.log_code in ['1', '3', '6']

        if is_out_log:
            previous_day = log_date_obj - timedelta(days=1)
            previous_day_key = previous_day.strftime('%Y-%m-%d')
            
            if previous_day_key in daily_summary:
                prev_data = daily_summary[previous_day_key]
                
                # Check for open AM shift (Code 0 present, Code 1 missing) or (Code 0 present, Code 3 missing)
                if (log.log_code == '1' or log.log_code == '3') and prev_data.get('AM_IN') and not prev_data.get(CODE_MAP.get(log.log_code)):
                    current_date_key = previous_day_key
                
                # Check for open PM shift (Code 2 present, Code 3 missing) or (Code 2 present, Code 1 missing)
                elif (log.log_code == '3' or log.log_code == '1') and prev_data.get('PM_IN') and not prev_data.get(CODE_MAP.get(log.log_code)):
                    current_date_key = previous_day_key
                    
                # Check for open OT shift (Code 5 present, Code 6 missing)
                elif log.log_code == '6' and prev_data.get('OT_IN') and not prev_data.get('OT_OUT'):
                    current_date_key = previous_day_key

        # --- B. Initialize Daily Summary Entry ---
        if current_date_key not in daily_summary:
            entry_date = datetime.strptime(current_date_key, '%Y-%m-%d').date()
            
            daily_summary[current_date_key] = {
                'date': entry_date,
                'AM_IN': None, 'AM_OUT': None,
                'PM_IN': None, 'PM_OUT': None,
                'OT_IN': None, 'OT_OUT': None,
                'total_hours': timedelta(0), 
                'total_minutes_late': 0,
                'raw_logs': []
            }
        
        # --- C. Store Log Time ---
        if log_type and not daily_summary[current_date_key][log_type]:
            daily_summary[current_date_key][log_type] = log.log_time
        
        daily_summary[current_date_key]['raw_logs'].append(log)

    # -----------------------------------------------
    # --- Step 3: CRITICAL UPDATED CALCULATION LOGIC ---
    # -----------------------------------------------
    for key, data in daily_summary.items():
        total_delta = timedelta(0)
        
        # --- SCENARIO 1: Custom/Hybrid Shifts (The New Priority) ---
        
        # 1a. Shift: AM_IN (0) to PM_OUT (3)
        if data.get('AM_IN') and data.get('PM_OUT') and not data.get('AM_OUT') and not data.get('PM_IN'):
            shift_duration = calculate_hours(data.get('AM_IN'), data.get('PM_OUT'))
            total_delta += shift_duration
            # Skip to OT/Late calculation
            
        # 1b. Shift: PM_IN (2) to AM_OUT (1) (Graveyard/Long Shift)
        elif data.get('PM_IN') and data.get('AM_OUT') and not data.get('AM_IN') and not data.get('PM_OUT'):
            shift_duration = calculate_hours(data.get('PM_IN'), data.get('AM_OUT'))
            total_delta += shift_duration
            # Skip to OT/Late calculation
            
        else:
            # --- SCENARIO 2: Standard Shifts (Paired Logs) ---
            # Fallback to standard pairings only if custom scenarios weren't fully matched.
            
            # AM Hours (0 -> 1)
            am_duration = calculate_hours(data.get('AM_IN'), data.get('AM_OUT'))
            total_delta += am_duration
            
            # PM Hours (2 -> 3)
            pm_duration = calculate_hours(data.get('PM_IN'), data.get('PM_OUT'))
            total_delta += pm_duration
        
        # --- SCENARIO 3: Overtime/Graveyard Shifts (5 -> 6) ---
        # OT calculation always applies regardless of the above
        ot_duration = calculate_hours(data.get('OT_IN'), data.get('OT_OUT'))
        total_delta += ot_duration
        
        # Store the total duration (timedelta object)
        data['total_hours'] = total_delta

        # --- LATE CALCULATION ---
        am_late = calculate_minutes_late(data.get('AM_IN'), 'AM_IN')
        pm_late = calculate_minutes_late(data.get('PM_IN'), 'PM_IN')
        ot_late = calculate_minutes_late(data.get('OT_IN'), 'OT_IN')
        
        data['total_minutes_late'] = am_late + pm_late + ot_late

    # Convert the dictionary to a list and sort by date descending for display
    summary_list = sorted(daily_summary.values(), key=lambda x: x['date'], reverse=True)

    context = {
        'employee_id': employee_id,
        'employee_name': employee_name,
        'daily_summary': summary_list,
    }

    return render(request, 'employee_details.html', context)


def search_employee(request):
    query = request.GET.get('query')
    employees = []
    if query:
        # Search by Employee ID (exact match) OR Employee Name (case-insensitive contains)
        employees = PayrollRecord.objects.filter(
            Q(employee_id__iexact=query) | Q(employee_name__icontains=query)
        ).order_by('employee_name')

    context = {
        'query': query,
        'employees': employees
    }
    return render(request, 'search_employee.html', context)