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

    
