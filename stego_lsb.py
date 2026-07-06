from PIL import Image

DELIMITER = "#####END#####"

def text_to_binary(text):
    return ''.join(format(ord(c), '08b') for c in text)

def binary_to_text(binary):
    return chr(int(binary, 2))

def embed_text(image_path, output_path, text):
    img = Image.open(image_path)

    # VERY IMPORTANT: force RGB mode
    if img.mode != "RGB":
        img = img.convert("RGB")

    binary_text = text_to_binary(text + DELIMITER)

    pixels = list(img.getdata())
    new_pixels = []

    data_index = 0
    total_bits = len(binary_text)

    for pixel in pixels:
        r, g, b = pixel

        if data_index < total_bits:
            r = (r & ~1) | int(binary_text[data_index])
            data_index += 1
        if data_index < total_bits:
            g = (g & ~1) | int(binary_text[data_index])
            data_index += 1
        if data_index < total_bits:
            b = (b & ~1) | int(binary_text[data_index])
            data_index += 1

        new_pixels.append((r, g, b))

    img.putdata(new_pixels)
    img.save(output_path, format="PNG")  # force PNG

def extract_text(image_path):
    img = Image.open(image_path)

    if img.mode != "RGB":
        img = img.convert("RGB")

    pixels = list(img.getdata())

    binary_buffer = ""
    extracted_text = ""

    for pixel in pixels:
        for value in pixel[:3]:
            binary_buffer += str(value & 1)

            if len(binary_buffer) == 8:
                char = binary_to_text(binary_buffer)
                extracted_text += char
                binary_buffer = ""

                # 🔴 STOP AS SOON AS DELIMITER IS FOUND
                if extracted_text.endswith(DELIMITER):
                    return extracted_text.replace(DELIMITER, "")

    return ""
