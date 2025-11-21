from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import CSVUploadHistory, PayrollRecord, Employee # Import the new model
from io import TextIOWrapper
from django.db.models import Count # Needed for distinct name 
from django.db import models
from datetime import datetime, time, timedelta
from django.http import JsonResponse

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
            messages.error(request, f'Error processing file: {str(e)}')
            # Cleanup history if created but failed
            if 'history_record' in locals():
                history_record.delete()    
        return redirect('humanresource:payroll_upload')
    
    # GET Request: Display upload history
    history = CSVUploadHistory.objects.order_by('-upload_time')[:20]

   
    
    context = {
        'history': history,
    }
    return render(request, 'upload_txt.html', context)


def DeleteHistoryView(request, history_id):
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required for deletion.")
        return redirect('homepage')
        
    #Deleting history record cascades to PayrollRecords.
    history_record = get_object_or_404(CSVUploadHistory, id=history_id)
    
    #Perform deletion
    if request.method == 'POST':
        file_name = history_record.file_name
        history_record.delete()
        messages.success(request, f'History record for file "{file_name}"  deleted successfully.')
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
        # Convert time strings to datetime objects (using a dummy date)
        dt_in = datetime.strptime(time_in_str, TIME_FORMAT)
        dt_out = datetime.strptime(time_out_str, TIME_FORMAT)
        
        # Check for Midnight Crossover (Graveyard Shift)
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
    
    # --- Step 2: Initialize, Group, and Handle Cross-Midnight Attribution ---
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
                
                # Check for open AM shift
                if (log.log_code == '1' or log.log_code == '3') and prev_data.get('AM_IN') and not prev_data.get(CODE_MAP.get(log.log_code)):
                    current_date_key = previous_day_key
                
                # Check for open PM shift
                elif (log.log_code == '3' or log.log_code == '1') and prev_data.get('PM_IN') and not prev_data.get(CODE_MAP.get(log.log_code)):
                    current_date_key = previous_day_key
                    
                # Check for open OT shift 
                elif log.log_code == '6' and prev_data.get('OT_IN') and not prev_data.get('OT_OUT'):
                    current_date_key = previous_day_key

        # --- B. Initialize Daily Summary Entry (ADDED SHIFT FIELDS) ---
        if current_date_key not in daily_summary:
            entry_date = datetime.strptime(current_date_key, '%Y-%m-%d').date()
            
            daily_summary[current_date_key] = {
                'date': entry_date,
                'AM_IN': None, 'AM_OUT': None,
                'PM_IN': None, 'PM_OUT': None,
                'OT_IN': None, 'OT_OUT': None,
                'total_hours': timedelta(0), 
                'day_shift_hours': timedelta(0),        # NEW FIELD
                'night_shift_hours': timedelta(0),      # NEW FIELD
                'graveyard_shift_hours': timedelta(0),  # NEW FIELD
                'total_minutes_late': 0,
                'raw_logs': [] 
            }
        
        # --- C. Store Log Time ---
        if log_type and not daily_summary[current_date_key][log_type]:
            daily_summary[current_date_key][log_type] = log.log_time
        
        daily_summary[current_date_key]['raw_logs'].append(log)

    for key, data in daily_summary.items():
        total_delta = timedelta(0)
        
        # Initialize shift variables for calculation
        day_shift_delta = timedelta(0)
        night_shift_delta = timedelta(0)
        graveyard_shift_delta = timedelta(0)
        ot_delta = timedelta(0) 

        # Track which logs have been used to prevent double-counting
        used_logs = set()
        
        # 1. Day Shift: AM_IN (0) to PM_OUT (3)
        if data.get('AM_IN') and data.get('PM_OUT'):
             day_shift_delta = calculate_hours(data.get('AM_IN'), data.get('PM_OUT'))
             used_logs.add('AM_IN')
             used_logs.add('PM_OUT')
        
        # 2. Night Shift: PM_IN (2) to PM_OUT (3)
        elif data.get('PM_IN') and data.get('PM_OUT'):
            night_shift_delta = calculate_hours(data.get('PM_IN'), data.get('PM_OUT'))
            used_logs.add('PM_IN')
            used_logs.add('PM_OUT')
        
        # 3. Graveyard Shift (AM portion): AM_IN (0) to AM_OUT (1)
        elif data.get('AM_IN') and data.get('AM_OUT'):
            graveyard_shift_delta = calculate_hours(data.get('AM_IN'), data.get('AM_OUT'))
            used_logs.add('AM_IN')
            used_logs.add('AM_OUT')
        
        # --- Overtime (5 -> 6) ---
        ot_delta = calculate_hours(data.get('OT_IN'), data.get('OT_OUT'))

        # Store the breakdown in the dictionary
        data['day_shift_hours'] = day_shift_delta
        data['night_shift_hours'] = night_shift_delta
        data['graveyard_shift_hours'] = graveyard_shift_delta
        
        # Calculate the GRAND TOTAL (Day + Night + Graveyard + OT)
        total_delta = day_shift_delta + night_shift_delta + graveyard_shift_delta + ot_delta
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
    unique_employees = [] # Initialize list for safety
    
    if query:
        # Clean the query by removing leading/trailing whitespace
        cleaned_query = query.strip() 
        
        # Filter the PayrollRecord model:
        # 1. Use Q objects to search by ID OR Name.
        # 2. Use __istartswith to prioritize records that begin with the query (case-insensitive).
        # 3. Use .values() to select only the fields needed for the employee list.
        # 4. Use .distinct() to get only unique employee/ID combinations.
        matching_records = PayrollRecord.objects.filter(
            Q(employee_id__istartswith=cleaned_query) | Q(employee_name__istartswith=cleaned_query)
        ).values(
            'employee_id', 
            'employee_name'
        ).distinct().order_by('employee_name')
        
        unique_employees = list(matching_records)

    context = {
        'query': query,
        'unique_employees': unique_employees # Pass the unique results to the template
    }
    
    # You will use a separate template (e.g., search_employee.html) to show the results
    return render(request, 'search_employee.html', context)

def EmployeeListView(request):
    current_role = request.session.get('role')
    
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')
        
    #Get unique employees and their first log date
    #Annotate to get the first (oldest) log date for each unique employee
    unique_employees = PayrollRecord.objects.values(
        'employee_name', 'employee_id'
    ).annotate(
        first_log=models.Min('log_date')
    ).order_by('first_log') # Order chronologically by the first log date
    
    context = {
        'unique_employees': unique_employees
    }
    return render(request, 'employee_list.html', context)

#adding employee
def add_employee(request):
    if request.method == 'POST':
        # 1. Get data from request.POST
        employee_id = request.POST.get('employee_id')
        first_name = request.POST.get('first_name')
        # ... and so on for other fields

        # 2. Save data to the database
        Employee.objects.create(
            employee_id=employee_id,
            employee_name=f"{first_name} {request.POST.get('last_name')}",
            # ... map other fields
        )

        # 3. Redirect the user after successful submission
        return redirect('humanresource:employee_list') # Redirect to the employee list

    # If it's a GET request, render the blank form
    return render(request, 'add_employee.html')


# ... (Your existing imports) ...
from django.db.models import Min # Ensure Min is imported if not already

# ... (Your existing helper functions and views) ...

def edit_employee(request, employee_id):
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')
        
    try:
        # Scenario A: Employee record exists in the Employee table
        employee = Employee.objects.get(employee_id=employee_id)
        is_existing = True
    except Employee.DoesNotExist:
        # Scenario B: Employee record does NOT exist in the Employee table
        # We need to pull the full name from the PayrollRecord table to pre-fill the name fields.
        payroll_record = PayrollRecord.objects.filter(employee_id=employee_id).first()
        
        if not payroll_record:
            messages.error(request, f"Employee ID {employee_id} not found in any payroll log.")
            return redirect('humanresource:employee_list') # Redirect if ID is totally invalid

        # Use the name from the PayrollRecord to initialize a *temporary* Employee object
        # NOTE: This temporary object is NOT saved to the database yet.
        full_name_from_payroll = payroll_record.employee_name.strip()
        name_parts = full_name_from_payroll.split()
        
        # Simple parsing for name parts (might need robust logic in production)
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[-1] if len(name_parts) > 1 else ''
        middle_name = ' '.join(name_parts[1:-1]) if len(name_parts) > 2 else ''
        
        employee = Employee(
            employee_id=employee_id,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            department='', # Default empty
        )
        is_existing = False

    if request.method == 'POST':
        # 3. Handle Form Submission (POST Request)
        
        # If it's a new employee (Scenario B), we use .create(). 
        # If it's an existing employee (Scenario A), we use .save() on the fetched object.
        
        # If is_existing is False, we switch to using the add_employee logic (Employee.objects.create)
        # However, to use the same form logic, let's update the fetched object and then save it.
        # If it was temporary, employee.save() will create a new record since it has no primary key from the DB.
        
        employee.first_name = request.POST.get('first_name')
        employee.middle_name = request.POST.get('middle_name')
        employee.last_name = request.POST.get('last_name')
        employee.department = request.POST.get('department')
        
        try:
            # If the object was fetched from DB (is_existing=True), .save() updates the record.
            # If the object was temporary (is_existing=False), we rely on the primary_key 
            # (employee_id) being unique for creation, but it's safer to use .objects.create 
            # for the first time.
            
            if not is_existing:
                 # Ensure ID is Integer before creation, as per your model
                Employee.objects.create(
                    employee_id=int(employee_id), 
                    first_name=employee.first_name,
                    middle_name=employee.middle_name,
                    last_name=employee.last_name,
                    department=employee.department
                )
                action_msg = "created"
            else:
                # Update existing employee
                employee.save()
                action_msg = "updated"
            
            messages.success(request, f"Employee details for {employee.get_full_name()} successfully {action_msg}.")
            
            # Redirect back to the employee list after successful edit/creation
            return redirect('humanresource:employee_list')

        except Exception as e:
            messages.error(request, f"An error occurred while saving employee data: {str(e)}")
            # Fall through to re-render the form with error message
            is_existing = False # Ensure the template knows to show it as a "creation" form

    # 4. Handle Page Load (GET Request)
    context = {
        'employee': employee, # Pass the employee object (fetched or temporary)
        'is_existing': is_existing # Tell the template if it's an existing record
    }
    return render(request, 'edit_employee.html', context)