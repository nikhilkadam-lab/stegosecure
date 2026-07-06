import base64

def file_to_base64(file):
    return base64.b64encode(file.read()).decode()

def base64_to_file(base64_data):
    return base64.b64decode(base64_data)
