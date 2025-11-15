from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from .models import Admin, UsersAccount
from django.contrib import messages


def login_view(request):
    """Handle login page display and authentication.
    
    If POST: authenticate user against Admin/RegularUser model, 
    store role in session, and redirect based on role (admin_home or user_home).
    If GET: display login form.
    """
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        role = request.POST.get('role')

        # Admin login
        if role == 'admin':
            try:
                admin = Admin.objects.get(username=username, is_active=True)
                if admin.password == password:
                    request.session['admin_id'] = admin.id
                    request.session['role'] = 'admin'
                    request.session['username'] = admin.username
                    return redirect('navigation_app:admin_home')
                else:
                    error = 'Invalid username or password.'
            except Admin.DoesNotExist:
                error = 'Invalid username or password.'

        # Non-admin roles (user, hr, timekeeper) authenticate against UsersAccount
        elif role in ('user', 'hr', 'timekeeper'):
            try:
                account = UsersAccount.objects.get(username=username, role=role)
                if account.password == password:
                    # set session for account
                    request.session['account_id'] = account.id
                    request.session['role'] = account.role
                    request.session['username'] = account.username
                    return redirect('navigation_app:user_home')
                else:
                    error = 'Invalid username or password.'
            except UsersAccount.DoesNotExist:
                error = 'Invalid username or password.'

    return render(request, 'login.html', {'error': error})


def Base(request):
    """Base/home view. If authenticated, show user_home; otherwise show login."""
    if request.user.is_authenticated:
        return redirect('navigation_app:user_home')
    return redirect('navigation_app:login')


def logout_view(request):
    """Log out the user and clear session data."""
    auth_logout(request)
    # Clear role and admin_id from session
    request.session.pop('role', None)
    request.session.pop('admin_id', None)
    request.session.pop('user_id', None)
    request.session.pop('account_id', None)
    request.session.pop('username', None)
    return redirect('navigation_app:login')


def UserHome(request):
    """Display user home page. Redirect to login if not authenticated.

    Accepts either Django-authenticated users or session-based UsersAccount accounts.
    """
    if not (request.user.is_authenticated or request.session.get('account_id')):
        return redirect('navigation_app:login')

    account = None
    if request.session.get('account_id'):
        try:
            account = UsersAccount.objects.get(id=request.session['account_id'])
        except UsersAccount.DoesNotExist:
            request.session.pop('account_id', None)

    return render(request, 'user_nav/user_home.html', {'account': account})


def admin_home(request):
    """Display admin dashboard. 
    
    Requires admin_id in session.
    Redirects to login if not authenticated as admin.
    """
    # Check if admin is logged in via session
    if 'admin_id' not in request.session:
        return redirect('navigation_app:login')
    
    try:
        admin = Admin.objects.get(id=request.session['admin_id'], is_active=True)
        return render(request, 'admin_nav/admin_home.html', {'admin': admin})
    except Admin.DoesNotExist:
        request.session.clear()
        return redirect('navigation_app:login')
    

def AddUser (request):
    # Handle create and delete actions from admin user management page
    if request.method == 'POST':
        # Delete action
        delete_username = request.POST.get('delete_username')
        if delete_username:
            try:
                acct = UsersAccount.objects.get(username=delete_username)
                acct.delete()
                messages.success(request, f'User "{delete_username}" deleted.')
            except UsersAccount.DoesNotExist:
                messages.error(request, 'User not found.')
            return redirect('navigation_app:AddUser')

        # Create action
        username = request.POST.get('username')
        password = request.POST.get('password')
        role = request.POST.get('role', 'user')

        # Check for empty fields
        if not username or not password:
            messages.error(request, 'Please fill in both the username and password!')
            users = UsersAccount.objects.all()
            return render(request, 'admin_nav/create_users.html', {'users': users})

        # Check if username already exists
        if UsersAccount.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            users = UsersAccount.objects.all()
            return render(request, 'admin_nav/create_users.html', {'users': users})

        # Create and save the new user (store hashed password)
        new_user = UsersAccount(username=username, role=role)
        new_user.save()
        new_user.set_password(password)
        messages.success(request, f'User "{username}" created successfully!')
        return redirect('navigation_app:AddUser')

    # GET - display page with existing users
    users = UsersAccount.objects.all()
    return render(request, 'admin_nav/create_users.html', {'users': users})
