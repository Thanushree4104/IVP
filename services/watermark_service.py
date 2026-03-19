import cv2
import numpy as np
from core.dct_embed import embed_watermark
from core.dct_extract import extract_watermark
from core.utils import bits_to_text

def process_embedding(input_path, output_path, watermark):
    img = cv2.imread(input_path)

    h, w = img.shape[:2]
    h = h - (h % 8)
    w = w - (w % 8)
    img = img[:h, :w]

    b, g, r = cv2.split(img)

    b = np.float32(b)

    b_watermarked = embed_watermark(b, watermark)

    b_watermarked = np.clip(b_watermarked, 0, 255)
    b_watermarked = np.uint8(b_watermarked)

    final_img = cv2.merge((b_watermarked, g, r))

    # Create new PNG path
    output_path_png = output_path.split('.')[0] + ".png"

    cv2.imwrite(output_path_png, final_img)

    return output_path_png

def process_extraction(image_path, length):
    img = cv2.imread(image_path)

    # Ensure same cropping
    h, w = img.shape[:2]
    h = h - (h % 8)
    w = w - (w % 8)
    img = img[:h, :w]

    # Split channels
    b, g, r = cv2.split(img)

    b = np.float32(b)

    bits = extract_watermark(b, length)
    return bits_to_text(bits)