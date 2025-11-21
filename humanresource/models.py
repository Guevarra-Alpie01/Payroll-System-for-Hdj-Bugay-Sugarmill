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



class Employee(models.Model):
    # Unique identifier for the employee, typically a company-issued number.
    # We use CharField because IDs often contain letters (e.g., "HR-4001").
    employee_id = models.IntegerField(unique=True)

    # Personal Names
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    # Middle name is optional, so we set null=True and blank=True
    middle_name = models.CharField(max_length=100, null=True, blank=True)
    
    # Department/Organizational Unit
    # It's often better to reference a separate Department model for relational integrity, 
    # but for simplicity, we'll use a CharField here.
    department = models.CharField(max_length=100)

    # Date/Time when the employee record was created (useful for tracking)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Sets the default ordering to be by employee ID (ascending)
        ordering = ['employee_id']
        # Sets a verbose name for the model in the Django Admin
        verbose_name = 'Employee Record'
        verbose_name_plural = 'Employee Records'

    def __str__(self):
        # This determines the string representation of an object (e.g., in the Admin site)
        return f"{self.first_name} {self.last_name} ({self.employee_id})"
    
    def get_full_name(self):
        # Helper method to combine the names
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"   
