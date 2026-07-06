from PIL import Image
import os

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_image_capacity(image_path):
    """
    Capacity in bytes using LSB:
    width * height * 3 bits / 8
    """
    img = Image.open(image_path)
    width, height = img.size
    capacity_bits = width * height * 3
    capacity_bytes = capacity_bits // 8
    return capacity_bytes
