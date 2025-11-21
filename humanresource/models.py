from django.db import models
from django.utils import timezone


class CSVUploadHistory(models.Model):
    uploaded_by = models.CharField(max_length=100, default='hr')
    file_name = models.CharField(max_length=255)
    upload_time = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = "CSVUploadHistory" 
        ordering = ['-upload_time'] 

    def __str__(self):
        return f"{self.filename} uploaded by {self.uploaded_by} on {self.upload_time.strftime('%Y-%m-%d %H:%M:%S')}"
    
class PayrollRecord(models.Model):
    # Field definitions based on the provided character ranges (fixed-width)
    employee_id = models.CharField(max_length=30)
    employee_name = models.CharField(max_length=150)
    log_code = models.CharField(max_length=10)
    log_date = models.DateField()
    log_time = models.CharField(max_length=10) # Storing time as CharField for flexibility (e.g., '07:36:00')
    
    # Link back to the upload event
    upload_history = models.ForeignKey(CSVUploadHistory, on_delete=models.CASCADE) 
    
    class Meta:
        db_table = "PayrollRecord"
        # Order by name, then by date/time for chronological display
        ordering = ['employee_name', 'log_date', 'log_time'] 

    def __str__(self):
        return f"{self.employee_name} ({self.employee_id}) - {self.log_date} {self.log_time}"


# ... (PayrollRecord class remains the same) ...

from django.db import models

class Employee(models.Model):
    # Basic Name & Identification (Required in original form)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, null=True, blank=True)
    extension_name = models.CharField(max_length=10, null=True, blank=True, verbose_name="Extension Name (Jr., Sr.)") # 1. Extension Name

    # Personal Information
    address = models.CharField(max_length=255, null=True, blank=True) # 2. Address
    tin = models.CharField(max_length=20, null=True, blank=True, verbose_name="TIN") # 3. TIN
    sss_no = models.CharField(max_length=20, null=True, blank=True, verbose_name="SSS Number") # 4. SSS No.
    philhealth_no = models.CharField(max_length=20, null=True, blank=True, verbose_name="PhilHealth No.") # 5. PhilHealth No.
    pagibig_no = models.CharField(max_length=20, null=True, blank=True, verbose_name="Pag-IBIG No.") # 6. Pag-IBIG No.

    CIVIL_STATUS_CHOICES = [
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Widowed', 'Widowed'),
        ('Separated', 'Separated'),
    ]
    civil_status = models.CharField(max_length=10, choices=CIVIL_STATUS_CHOICES, null=True, blank=True) # 7. Civil Status
    
    SEX_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    sex = models.CharField(max_length=6, choices=SEX_CHOICES, null=True, blank=True) # 8. Sex
    birthdate = models.DateField(null=True, blank=True) # 9. Birthdate
    age = models.IntegerField(null=True, blank=True) # 10. Age (Can be calculated, but stored for simplicity here)
    contact_no = models.CharField(max_length=20, null=True, blank=True, verbose_name="Contact Number") # 11. Contact No.

    # Employment Details
    date_hired = models.DateField(null=True, blank=True) # 12. Date Hired
    
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Terminated', 'Terminated'),
        ('Retired', 'Retired'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active') # 13. Status
    date_separated = models.DateField(null=True, blank=True) # 14. Date Separated
    retirement_age = models.IntegerField(null=True, blank=True) # 15. Retirement Age
    classification = models.CharField(max_length=100, null=True, blank=True) # 16. Classification
    department = models.CharField(max_length=100) # 17. Department (Kept from original)
    section = models.CharField(max_length=100, null=True, blank=True) # 18. Section
    position = models.CharField(max_length=100, null=True, blank=True) # 19. Position
    
    # Rate Details
    monthly_daily_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Monthly/Daily Rate") # 20. Monthly/Daily Rate
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Hourly Rate") # 21. Hourly Rate

    # Educational & Professional Details
    educ_attainment = models.CharField(max_length=100, null=True, blank=True, verbose_name="Educational Attainment") # 22. Educational Attainment
    license_no = models.CharField(max_length=50, null=True, blank=True, verbose_name="License No.") # 23. License No.
    profession_1 = models.CharField(max_length=100, null=True, blank=True) # 24. Profession 1
    profession_2 = models.CharField(max_length=100, null=True, blank=True) # 25. Profession 2
    profession_3 = models.CharField(max_length=100, null=True, blank=True) # 26. Profession 3

    # Dependent Details
    no_of_dependents = models.IntegerField(default=0, verbose_name="No. of Dependents") # 27. No. of Dependents
    spouse_name = models.CharField(max_length=200, null=True, blank=True) # 28. Spouse Name
    spouse_birthdate = models.DateField(null=True, blank=True, verbose_name="Spouse Birthdate") # 29. Spouse Birthdate
    dependent_1 = models.CharField(max_length=200, null=True, blank=True) # 30. Dependent 1
    dependent_2 = models.CharField(max_length=200, null=True, blank=True) # 31. Dependent 2
    dependent_3 = models.CharField(max_length=200, null=True, blank=True) # 32. Dependent 3
    dependent_4 = models.CharField(max_length=200, null=True, blank=True) # 33. Dependent 4 (Missing in your list, but included for sequence)
    dependent_5 = models.CharField(max_length=200, null=True, blank=True) # 34. Dependent 5

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Employee'
        ordering = ['last_name', 'first_name']
        verbose_name = 'Employee Record'
        verbose_name_plural = 'Employee Records'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id if hasattr(self, 'employee_id') else 'Unmapped'})"
    
    def get_full_name(self):
        name_parts = [self.first_name]
        if self.middle_name:
            name_parts.append(self.middle_name)
        name_parts.append(self.last_name)
        if self.extension_name:
            name_parts.append(f"({self.extension_name})")
        return " ".join(name_parts)
    
    def get_list_name(self):
        return f"{self.first_name} {self.last_name}"

class EmployeeMapping(models.Model):
    """Map payroll employee_id strings (e.g. '000000035') to an Employee record.

    We keep this separate so PayrollRecord keeps canonical payroll IDs
    while Employee stores HR profile data without duplicating the payroll id
    field.
    """
    payroll_employee_id = models.CharField(max_length=50, unique=True)
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='mapping')

    class Meta:
        db_table = 'EmployeeMapping'

    def __str__(self):
        return f"{self.payroll_employee_id} -> {self.employee.get_list_name()}"