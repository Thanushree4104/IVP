import cv2
import numpy as np
from core.dct_embed import embed_watermark
from core.dct_extract import extract_watermark
from core.utils import bits_to_text

def process_embedding(input_path, output_path, watermark):
    img = cv2.imread(input_path, cv2.IMREAD_GRAYSCALE)
    img = np.float32(img)

    watermarked = embed_watermark(img, watermark)

    cv2.imwrite(output_path, watermarked)
    return output_path


def process_extraction(image_path, length):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    img = np.float32(img)

    bits = extract_watermark(img, length)
    return bits_to_text(bits)
