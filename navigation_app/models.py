from django.db import models
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils import timezone

# UsersAccount will manage all users (including 'admin', 'hr', etc.)
class UsersAccount(models.Model):
    # Defined choices for clarity, but you can use any role string.
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('Accounting', 'Accounting'),
        ('hr', 'HR'),
        ('timekeeper', 'Timekeeper'),
    ]

    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='Admin')
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=100) # Storing plain text password
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "Users"

    def __str__(self):
        return f"{self.username} ({self.role})"

    def set_password(self, raw_password):
        """Sets the password directly (PLAIN TEXT)."""
        self.password = raw_password
        self.save(update_fields=["password"])

    def check_password(self, raw_password):
        """Checks the raw password against the stored value (PLAIN TEXT)."""
        return (self.password == raw_password)

# Signal to create a default 'admin' user if one doesn't exist
@receiver(post_migrate)
def create_default_admin(sender, **kwargs):
    # Replace 'navigation_app' with your actual app name
    if sender.name == 'navigation_app': 
        if not UsersAccount.objects.filter(username='admin').exists():
            admin_user = UsersAccount.objects.create(username='admin', role='admin', password='admin123', is_active=True)
            # Password is saved in plain text upon creation.