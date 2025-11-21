from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.db.models import Q,Min, F 
from .models import CSVUploadHistory, PayrollRecord, Employee, EmployeeMapping # Import the new model
from io import TextIOWrapper
from django.db.models import Count 
from django.db import models
from datetime import datetime, time, timedelta
from django.http import JsonResponse

# ----------------------------------------------------------------------
# 1. UPLOAD & HISTORY MANAGEMENT
# ----------------------------------------------------------------------

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

            # 1. Create History Record immediately
            history_record = CSVUploadHistory.objects.create(
                uploaded_by = uploader_username,
                file_name = uploaded_file.name,
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
        
    # Deleting history record cascades to PayrollRecords.
    history_record = get_object_or_404(CSVUploadHistory, id=history_id)
    
    # Perform deletion
    if request.method == 'POST':
        file_name = history_record.file_name
        history_record.delete()
        messages.success(request, f'History record for file "{file_name}" deleted successfully.')
    else:
        messages.error(request, 'Invalid request method for deletion.')

    return redirect('humanresource:payroll_upload')


# ----------------------------------------------------------------------
# 2. CALCULATION HELPERS
# ----------------------------------------------------------------------

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
        if dt_out < dt_in:
            dt_out += timedelta(days=1)   # Add 24 hours to the OUT time
            
        return dt_out - dt_in
    except ValueError:
        # Handles malformed time strings
        return timedelta(0)
    

def calculate_minutes_late(log_time_str, log_type):
    if not log_time_str:
        return 0

    TIME_FORMAT = '%H:%M:%S'
    try:
        logged_dt = datetime.strptime(log_time_str, TIME_FORMAT)
        
        # Define the grace period cut-off time (15 mins past standard)
        if log_type == 'AM_IN':
            grace_cut_off = time(8, 15, 0)
        elif log_type == 'PM_IN':
            grace_cut_off = time(16, 15, 0)
        elif log_type == 'OT_IN':
            grace_cut_off = time(0, 15, 0)
        else:
            return 0 # Only check IN logs

        # Compare the time part of the log with the cut-off time
        if logged_dt.time() > grace_cut_off:
            # For simplicity and robust time arithmetic, convert the logged time
            # and the cut-off time into full datetime objects (using a dummy date).
            dummy_date = datetime(2000, 1, 1)
            cut_off_dt = datetime.combine(dummy_date, grace_cut_off)
            
            # The logged time is already a datetime object from the strptime call above
            
            # Calculate the difference and convert to total minutes
            late_delta = logged_dt - cut_off_dt
            
            if late_delta > timedelta(0):
                return int(late_delta.total_seconds() / 60)
            
        return 0 # Not late
        
    except ValueError:
        return 0
    

# ----------------------------------------------------------------------
# 3. DETAILS & SEARCH VIEWS
# ----------------------------------------------------------------------

def EmployeeDetailsView(request, employee_id):
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')

    # 1. Fetch all records for the employee, ordered by date and time
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

        # --- B. Initialize Daily Summary Entry ---
        if current_date_key not in daily_summary:
            entry_date = datetime.strptime(current_date_key, '%Y-%m-%d').date()
            
            daily_summary[current_date_key] = {
                'date': entry_date,
                'AM_IN': None, 'AM_OUT': None,
                'PM_IN': None, 'PM_OUT': None,
                'OT_IN': None, 'OT_OUT': None,
                'total_hours': timedelta(0), 
                'day_shift_hours': timedelta(0), 
                'night_shift_hours': timedelta(0), 
                'graveyard_shift_hours': timedelta(0), 
                'total_minutes_late': 0,
                'raw_logs': [] 
            }
        
        # --- C. Store Log Time ---
        if log_type and not daily_summary[current_date_key][log_type]:
            daily_summary[current_date_key][log_type] = log.log_time
        
        daily_summary[current_date_key]['raw_logs'].append(log)

    for key, data in daily_summary.items():
        total_delta = timedelta(0)
        
        day_shift_delta = timedelta(0)
        night_shift_delta = timedelta(0)
        graveyard_shift_delta = timedelta(0)
        ot_delta = timedelta(0) 

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
        cleaned_query = query.strip() 
        
        # Filter PayrollRecord model to find matching logs
        matching_record_ids = PayrollRecord.objects.filter(
            Q(employee_id__istartswith=cleaned_query) | Q(employee_name__istartswith=cleaned_query)
        ).values_list('employee_id', flat=True).distinct()
        
        # 1. Fetch structured Employee records that match via EmployeeMapping (if they exist)
        mappings = EmployeeMapping.objects.filter(payroll_employee_id__in=matching_record_ids).select_related('employee')
        employee_cache = {m.payroll_employee_id: m.employee for m in mappings}

        # 2. Get the latest bio name for each matched ID
        bio_name_cache = {}
        for emp_id_str in matching_record_ids:
             payroll_record = PayrollRecord.objects.filter(employee_id=emp_id_str).order_by('-log_date', '-log_time').first()
             if payroll_record:
                 bio_name_cache[emp_id_str] = payroll_record.employee_name
        
        # 3. Build the final list (similar to EmployeeListView, but using search results)
        for emp_id_str in matching_record_ids:
            payroll_name = bio_name_cache.get(emp_id_str, "N/A")

            if emp_id_str in employee_cache:
                employee_obj = employee_cache[emp_id_str]
                setattr(employee_obj, 'employee_name', payroll_name)
                unique_employees.append(employee_obj)
            else:
                # Create a pseudo-object for unclassified employees
                def get_list_name_func(self):
                    return self.employee_name 
                def get_full_name_func(self):
                    return self.employee_name
                    
                pseudo_employee = type('PseudoEmployee', (object,), {
                    'employee_id': emp_id_str,
                    'employee_name': payroll_name,       
                    'department': 'Unclassified',
                    'get_list_name': get_list_name_func, 
                    'get_full_name': get_full_name_func,
                })()
                
                unique_employees.append(pseudo_employee)

    context = {
        'query': query,
        'unique_employees': unique_employees 
    }
    
    return render(request, 'employee_list.html', context) # Use the same list template


# ----------------------------------------------------------------------
# 4. EMPLOYEE LIST & EDIT/CREATE LOGIC (CORE FIXES)
# ----------------------------------------------------------------------

# --- CORRECTED & STRENGTHENED: EmployeeListView ---
def EmployeeListView(request):
    current_role = request.session.get('role')
    # Add security check here if necessary
        
    # 1. Get chronological order and unique employee IDs (all as strings) from PayrollRecord
    employee_payroll_data = PayrollRecord.objects.values(
        'employee_id' 
    ).annotate(
        first_log=Min('log_date')
    ).order_by('first_log')
    
    # 2. Cache all structured Employee objects for fast lookup via EmployeeMapping
    all_employees = Employee.objects.all()
    mappings = EmployeeMapping.objects.select_related('employee').all()
    employee_cache = {m.payroll_employee_id: m.employee for m in mappings}
    
    # 3. Cache the latest original bio name for each ID efficiently
    employee_ids = [d['employee_id'] for d in employee_payroll_data]
    bio_name_cache = {}
    
    for emp_id_str in employee_ids:
         payroll_record = PayrollRecord.objects.filter(employee_id=emp_id_str).order_by('-log_date', '-log_time').first()
         if payroll_record:
             bio_name_cache[emp_id_str] = payroll_record.employee_name
             
    unique_employees_data = []
    processed_ids = set() 
    
    # Process payroll records first (chronological)
    for record_data in employee_payroll_data:
        emp_id_str = record_data['employee_id']
        
        if emp_id_str in processed_ids:
            continue
            
        processed_ids.add(emp_id_str)
        payroll_name = bio_name_cache.get(emp_id_str, "N/A") 
        
        # Scenario A: Employee profile exists in the Employee table
        if emp_id_str in employee_cache:
            employee_obj = employee_cache[emp_id_str]
            
            # Dynamically attach the raw 'Bio Name' for the template column.
            setattr(employee_obj, 'employee_name', payroll_name)
            # Ensure the payroll-formatted employee_id is present on the object for templates/sorting
            setattr(employee_obj, 'employee_id', emp_id_str)
            
            unique_employees_data.append(employee_obj)
            
        # Scenario B: No Employee profile, logs exist (Fallback to Pseudo-object)
        else:
            # Define methods for the pseudo-object
            def get_list_name_func(self):
                # Pseudo-employee's list name is just the bio name
                return self.employee_name 
            def get_full_name_func(self):
                # Used by the title/heading in edit_employee
                return self.employee_name
                
            # FIX: Define the class attributes directly and instantiate the class immediately 
            # without passing arguments to the class constructor.
            pseudo_employee = type('PseudoEmployee', (object,), {
                'employee_id': emp_id_str,  # Keep as string for consistency
                'employee_name': payroll_name,       # Payroll Bio Name
                'department': 'Unclassified',
                'get_list_name': get_list_name_func, 
                'get_full_name': get_full_name_func,
            })() # <--- Crucial change: Call the class with no arguments ()
            
            unique_employees_data.append(pseudo_employee)
    
    # Now add any Employee records that don't have PayrollRecords (newly created employees)
    # Track which employee IDs were already processed from payroll
    processed_employee_ids = set()
    for record_data in employee_payroll_data:
        emp_id_str = record_data['employee_id']
        processed_employee_ids.add(emp_id_str)

    # Add Employee profiles that do not have payroll records (mapped to payroll IDs)
    # We will attach the payroll_employee_id attribute to Employee objects for template use
    mapped_employee_ids = {m.employee.id: m.payroll_employee_id for m in mappings}
    for employee_obj in all_employees:
        payroll_id = mapped_employee_ids.get(employee_obj.id)
        if payroll_id and payroll_id not in processed_employee_ids:
            setattr(employee_obj, 'employee_name', employee_obj.get_full_name())
            # Provide an `employee_id` attribute for templates (payroll format)
            setattr(employee_obj, 'employee_id', payroll_id)
            unique_employees_data.append(employee_obj)
            processed_employee_ids.add(payroll_id)
        elif not payroll_id:
            # No mapping exists; include the HR-only employee but mark employee_id as empty
            setattr(employee_obj, 'employee_name', employee_obj.get_full_name())
            setattr(employee_obj, 'employee_id', '')
            unique_employees_data.append(employee_obj)

    # Sort final list by employee ID for consistency
    unique_employees_data.sort(key=lambda x: str(x.employee_id))

    context = {
        'unique_employees': unique_employees_data
    }
    return render(request, 'employee_list.html', context)
# --- CORRECTED & STRENGTHENED: edit_employee ---
def edit_employee(request, employee_id):
    current_role = request.session.get('role')
    if current_role != 'hr':
        messages.error(request, "Access denied. HR role required.")
        return redirect('homepage')
    
    # Normalize employee_id to match PayrollRecord format (zero-padded to 9 digits)
    try:
        emp_id_int = int(employee_id.strip().lstrip('0') or '0')
        normalized_employee_id = str(emp_id_int).zfill(9)
    except (ValueError, AttributeError):
        normalized_employee_id = employee_id
        
    # 1. Fetch the Original Bio Name from PayrollRecord
    payroll_record = PayrollRecord.objects.filter(employee_id=normalized_employee_id).order_by('log_date').first()
    if not payroll_record:
        messages.error(request, f"Employee ID {employee_id} not found in any payroll log.")
        return redirect('humanresource:employee_list')
    
    original_bio_name = payroll_record.employee_name.strip()

    # Try to find a mapped Employee via EmployeeMapping
    try:
        mapping = EmployeeMapping.objects.select_related('employee').get(payroll_employee_id=normalized_employee_id)
        employee = mapping.employee
        is_existing = True
    except EmployeeMapping.DoesNotExist:
        # Scenario B: Employee profile does NOT exist (transient Employee shown in form)
        is_existing = False
        name_parts = original_bio_name.split()
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[-1] if len(name_parts) > 1 else ''
        middle_name = ' '.join(name_parts[1:-1]) if len(name_parts) > 2 else ''
        employee = Employee(
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            department='', 
        )

    if request.method == 'POST':
        # 3. Get and Clean form data (Updated to include all new fields)
        first_name_data = request.POST.get('first_name', '').strip()
        last_name_data = request.POST.get('last_name', '').strip()
        middle_name_data = request.POST.get('middle_name', '').strip() or None 
        department_data = request.POST.get('department', '').strip()

        # --- NEW FIELD EXTRACTION ---
        employee.extension_name = request.POST.get('extension_name', '').strip() or None
        employee.address = request.POST.get('address', '').strip() or None
        employee.tin = request.POST.get('tin', '').strip() or None
        employee.sss_no = request.POST.get('sss_no', '').strip() or None
        employee.philhealth_no = request.POST.get('philhealth_no', '').strip() or None
        employee.pagibig_no = request.POST.get('pagibig_no', '').strip() or None
        employee.civil_status = request.POST.get('civil_status', '').strip() or None
        employee.sex = request.POST.get('sex', '').strip() or None
        employee.birthdate = request.POST.get('birthdate') or None
        employee.age = request.POST.get('age') or None
        employee.contact_no = request.POST.get('contact_no', '').strip() or None
        employee.date_hired = request.POST.get('date_hired') or None
        employee.status = request.POST.get('status', '').strip()
        employee.date_separated = request.POST.get('date_separated') or None
        employee.retirement_age = request.POST.get('retirement_age') or None
        employee.classification = request.POST.get('classification', '').strip() or None
        employee.section = request.POST.get('section', '').strip() or None
        employee.position = request.POST.get('position', '').strip() or None
        
        # Handle decimal fields (convert to None if empty string)
        employee.monthly_daily_rate = request.POST.get('monthly_daily_rate') or None
        employee.hourly_rate = request.POST.get('hourly_rate') or None

        employee.educ_attainment = request.POST.get('educ_attainment', '').strip() or None
        employee.license_no = request.POST.get('license_no', '').strip() or None
        employee.profession_1 = request.POST.get('profession_1', '').strip() or None
        employee.profession_2 = request.POST.get('profession_2', '').strip() or None
        employee.profession_3 = request.POST.get('profession_3', '').strip() or None
        
        employee.no_of_dependents = request.POST.get('no_of_dependents') or 0
        employee.spouse_name = request.POST.get('spouse_name', '').strip() or None
        employee.spouse_birthdate = request.POST.get('spouse_birthdate') or None
        employee.dependent_1 = request.POST.get('dependent_1', '').strip() or None
        employee.dependent_2 = request.POST.get('dependent_2', '').strip() or None
        employee.dependent_3 = request.POST.get('dependent_3', '').strip() or None
        employee.dependent_4 = request.POST.get('dependent_4', '').strip() or None
        employee.dependent_5 = request.POST.get('dependent_5', '').strip() or None
        # --- END NEW FIELD EXTRACTION ---
        
        # Validation checks (only for core required fields)
        if not first_name_data or not last_name_data or not department_data:
            messages.error(request, "First Name, Last Name, and Department are required fields.")
            # Repopulate context with current (unsaved) data for rendering
            context = {
                'employee': employee, 
                'is_existing': is_existing,
                'original_bio_name': original_bio_name,
                'employee_id': normalized_employee_id,
            }
            return render(request, 'edit_employee.html', context)


        # Apply core data to the object
        employee.first_name = first_name_data
        employee.middle_name = middle_name_data
        employee.last_name = last_name_data
        employee.department = department_data
        
        try:
            if not is_existing:
                # Creation logic - use the collected data to create a new Employee instance
                employee_instance = Employee.objects.create(
                    first_name=employee.first_name,
                    last_name=employee.last_name,
                    middle_name=employee.middle_name,
                    department=employee.department,
                    
                    # Pass ALL other fields from the transient object
                    extension_name=employee.extension_name,
                    address=employee.address,
                    tin=employee.tin,
                    sss_no=employee.sss_no,
                    philhealth_no=employee.philhealth_no,
                    pagibig_no=employee.pagibig_no,
                    civil_status=employee.civil_status,
                    sex=employee.sex,
                    birthdate=employee.birthdate,
                    age=employee.age,
                    contact_no=employee.contact_no,
                    date_hired=employee.date_hired,
                    status=employee.status,
                    date_separated=employee.date_separated,
                    retirement_age=employee.retirement_age,
                    classification=employee.classification,
                    section=employee.section,
                    position=employee.position,
                    monthly_daily_rate=employee.monthly_daily_rate,
                    hourly_rate=employee.hourly_rate,
                    educ_attainment=employee.educ_attainment,
                    license_no=employee.license_no,
                    profession_1=employee.profession_1,
                    profession_2=employee.profession_2,
                    profession_3=employee.profession_3,
                    no_of_dependents=employee.no_of_dependents,
                    spouse_name=employee.spouse_name,
                    spouse_birthdate=employee.spouse_birthdate,
                    dependent_1=employee.dependent_1,
                    dependent_2=employee.dependent_2,
                    dependent_3=employee.dependent_3,
                    dependent_4=employee.dependent_4,
                    dependent_5=employee.dependent_5,
                    # ... add all new fields here
                )
                # Create mapping to payroll ID
                EmployeeMapping.objects.create(payroll_employee_id=normalized_employee_id, employee=employee_instance)
                action_msg = "created"
            else:
                # Update logic (employee is already loaded and modified in the object)
                employee.save()
                # Ensure mapping exists and is linked to this employee
                EmployeeMapping.objects.update_or_create(
                    payroll_employee_id=normalized_employee_id,
                    defaults={'employee': employee}
                )
                action_msg = "updated"
            
            messages.success(request, f"Employee details for {employee.get_full_name()} successfully {action_msg}.")
            return redirect('humanresource:employee_list')

        except Exception as e:
            messages.error(request, f"An error occurred while saving employee data: {str(e)}")
            # Fall back to GET request logic to show the form with the error (re-render below)
            # No need to check is_existing again, as it's already set

    # 4. Handle Page Load (GET Request) or Error Re-render
    context = {
        'employee': employee, 
        'is_existing': is_existing,
        'original_bio_name': original_bio_name,
        'employee_id': normalized_employee_id,
    }
    return render(request, 'edit_employee.html', context)