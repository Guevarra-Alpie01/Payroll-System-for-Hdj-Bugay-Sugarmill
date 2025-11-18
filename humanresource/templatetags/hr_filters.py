# In humanresource/templatetags/hr_filters.py
from django import template

# Use the existing register object if it's there, otherwise create it
register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Looks up a value from a dictionary using a variable key.
    Usage: {{ dictionary|get_item:key }}
    """
    # Use .get() for safety, so it returns None instead of raising KeyError
    return dictionary.get(key)