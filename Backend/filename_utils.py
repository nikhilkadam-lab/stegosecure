import os
import re

def normalize_output_filename(user_provided_name, original_filename):
    """
    Normalize output filename:
    - If user provided name, strip any extension and add .png
    - If blank, use original filename's base name and add .png
    """
    if user_provided_name and user_provided_name.strip():
        # User provided a name - strip any extension they might have added
        base = os.path.splitext(user_provided_name.strip())[0]
        # Remove any path separators, dots, etc. for safety
        base = re.sub(r'[^\w\-_\. ]', '', base)
        if not base:  # If after cleaning it's empty, use a default
            base = "encrypted_image"
    else:
        # No user input - use original filename's base
        base = os.path.splitext(original_filename)[0]
        # Clean it too
        base = re.sub(r'[^\w\-_\. ]', '', base)
    
    # Always add .png extension
    return f"{base}.png"