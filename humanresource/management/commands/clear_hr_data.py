from django.core.management.base import BaseCommand
from humanresource.models import PayrollRecord, CSVUploadHistory, Employee


class Command(BaseCommand):
    help = 'Clear humanresource app data. Deletes PayrollRecord and CSVUploadHistory by default; use --remove-employees to also delete Employee records.'

    def add_arguments(self, parser):
        parser.add_argument('--remove-employees', action='store_true', help='Also delete Employee records')
        parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')

    def handle(self, *args, **options):
        remove_employees = options.get('remove_employees', False)
        skip_confirm = options.get('yes', False)

        action_desc = 'payroll records and upload history'
        if remove_employees:
            action_desc += ' and employee records'

        if not skip_confirm:
            confirm = input(f"This will delete all {action_desc} for the humanresource app. Type YES to continue: ")
            if confirm != 'YES':
                self.stdout.write(self.style.WARNING('Aborted by user. No changes made.'))
                return

        pr_deleted = PayrollRecord.objects.all().delete()
        hist_deleted = CSVUploadHistory.objects.all().delete()

        # pr_deleted and hist_deleted are tuples (count, {model_label: count})
        pr_count = pr_deleted[0]
        hist_count = hist_deleted[0]

        if remove_employees:
            emp_deleted = Employee.objects.all().delete()
            emp_count = emp_deleted[0]
        else:
            emp_count = 0

        self.stdout.write(self.style.SUCCESS(f"Deleted {pr_count} PayrollRecord(s), {hist_count} CSVUploadHistory record(s), and {emp_count} Employee record(s)."))
