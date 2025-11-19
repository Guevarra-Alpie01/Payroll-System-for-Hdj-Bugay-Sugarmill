from django.shortcuts import render, redirect
from django.http import HttpResponse
from .models import UsersAccount
from django.contrib import messages
from django.db.models import Q # Import for more complex queries if needed
from humanresource import views

def login_view(request):
    """Handle login page display and plain text authentication."""
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        role = request.POST.get('role')

        try:
            # 1. Try to find the user with the given username and role
            account = UsersAccount.objects.get(username=username, role=role, is_active=True)
            
            # 2. Check the plain text password
            if account.password == password: # PLAIN TEXT COMPARISON
                # Authentication successful, set session data
                request.session['account_id'] = account.id
                request.session['role'] = account.role
                request.session['username'] = account.username
                
                if account.role == 'admin':
                    return redirect('navigation_app:admin_home')
                elif account.role == 'hr':
                    return redirect('humanresource:payroll_upload')
                else:
                    return redirect('navigation_app:user_home')
            else:
                error = 'Invalid username or password.' 
        
        except UsersAccount.DoesNotExist:
            error = 'Invalid username or password.'

    return render(request, 'login.html', {'error': error})


def logout_view(request):
    """Log out the user and clear session data."""
    # Clear all custom session data
    request.session.pop('role', None)
    request.session.pop('account_id', None)
    request.session.pop('username', None)
    messages.info(request, "You have been logged out.")
    return redirect('navigation_app:login')


# --- Decorator for Authentication Check ---

def auth_required(func):
    """Decorator to check for session-based authentication."""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('account_id'):
            messages.error(request, "Please log in to access this page.")
            return redirect('navigation_app:login')
        return func(request, *args, **kwargs)
    return wrapper


# --- Home/Navigation Views ---

@auth_required
def admin_home(request):
    """Display admin dashboard."""
    account_id = request.session.get('account_id')
    try:
        account = UsersAccount.objects.get(id=account_id)
        if account.role != 'admin':
            messages.error(request, "Access denied. Admin role required.")
            return redirect('navigation_app:user_home')
        return render(request, 'admin_nav/admin_home.html', {'account': account})
    except UsersAccount.DoesNotExist:
        request.session.clear()
        return redirect('navigation_app:login')

@auth_required
def UserHome(request):
    """Display non-admin user home page."""
    account_id = request.session.get('account_id')
    try:
        account = UsersAccount.objects.get(id=account_id)
        return render(request, 'user_nav/user_home.html', {'account': account})
    except UsersAccount.DoesNotExist:
        request.session.clear()
        return redirect('navigation_app:login')


def Base(request):
    """Base/home view."""
    if request.session.get('account_id'):
        if request.session['role'] == 'admin':
            return redirect('navigation_app:admin_home')
        return redirect('navigation_app:user_home')
    return redirect('navigation_app:login')


# --- User Management View (Admin only) ---

@auth_required
def AddUser(request):
    """Handle create/delete actions for users by an Admin."""
    # Enforce admin role
    if request.session.get('role') != 'admin':
        messages.error(request, "Admin privileges are required for user management.")
        return redirect('navigation_app:user_home')

    if request.method == 'POST':
        # --- Delete action ---
        delete_username = request.POST.get('delete_username')
        if delete_username:
            try:
                # Prevent admin from deleting themselves
                if delete_username == request.session['username']:
                    messages.error(request, 'You cannot delete your own admin account.')
                    return redirect('navigation_app:AddUser')
                    
                acct = UsersAccount.objects.get(username=delete_username)
                acct.delete()
                messages.success(request, f'User "{delete_username}" deleted.')
            except UsersAccount.DoesNotExist:
                messages.error(request, 'User not found.')
            return redirect('navigation_app:AddUser')

        # --- Create action ---
        username = request.POST.get('username')
        password = request.POST.get('password')
        role = request.POST.get('role', 'Accounting') 

        if not username or not password:
            messages.error(request, 'Please fill in both the username and password!')
        elif UsersAccount.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        else:
            # Create user and save the PLAIN TEXT password
            new_user = UsersAccount(username=username, role=role, password=password)
            new_user.save()
            messages.success(request, f'User "{username}" created successfully!')
            return redirect('navigation_app:AddUser')

    # GET - display page with existing users (excluding the current admin for safety)
    current_admin_username = request.session.get('username')
    users = UsersAccount.objects.exclude(username=current_admin_username).order_by('username')
    return render(request, 'admin_nav/create_users.html', {'users': users})