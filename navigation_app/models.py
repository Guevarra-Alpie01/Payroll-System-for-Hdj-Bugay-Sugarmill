from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_migrate
from django.dispatch import receiver



class Admin(models.Model):
    """Custom Admin model for payroll system administration."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile', null=True, blank=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "Admin"

    def __str__(self):
        return f"Admin: {self.username}"

    def set_password(self, raw_password):
        """Set the admin password (plain text)."""
        self.password = raw_password
        self.save(update_fields=["password"])

    def check_password(self, raw_password):
        """Check a raw password against the stored value (plain text)."""
        return (self.password == raw_password)


# Signal to create default admin after migrations
@receiver(post_migrate)
def create_default_admin(sender, **kwargs):
    if sender.name == 'navigation_app':
        if not Admin.objects.filter(username='admin').exists():
            Admin.objects.create(username='admin', password='admin123', is_active=True)



# RegularUser model removed to avoid duplication — use UsersAccount for non-admin users.


class UsersAccount(models.Model):
    role = models.CharField(max_length=50, default='user')
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=100)

    class Meta:
        db_table = "Users"

    def __str__(self):
        return f"{self.username} ({self.role})"

    def set_password(self, raw_password):
        """Set the account password (plain text)."""
        self.password = raw_password
        self.save(update_fields=["password"])

    def check_password(self, raw_password):
        """Return True if the raw_password matches the stored value (plain text)."""
        return (self.password == raw_password)


# Signal to create default regular (non-admin) user after migrations (password hashed)
@receiver(post_migrate)
def create_default_regular_user(sender, **kwargs):
    if sender.name == 'navigation_app':
        if not UsersAccount.objects.filter(username='username').exists():
            UsersAccount.objects.create(username='username', password='password123', role='user')