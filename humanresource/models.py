from django.db import models
from django.utils import timezone


class CSVUploadHistory(models.Model):
    uploaded_by = models.CharField(max_length=100, default='hr')
    file_name = models.CharField(max_length=255)
    upload_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=50, default='Success') 
    details = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = "CSVUploadHistory" 
        ordering = ['-upload_time'] 

    def __str__(self):
        return f"{self.file_name} uploaded by {self.uploaded_by} on {self.upload_time.strftime('%Y-%m-%d %H:%M:%S')}"

    
