import cv2
import numpy as np
from config import BLOCK_SIZE, STRENGTH
from core.utils import text_to_bits

def embed_watermark(image, watermark_text):
    bits = text_to_bits(watermark_text)
    h, w = image.shape

    bit_index = 0

    for i in range(0, h, BLOCK_SIZE):
        for j in range(0, w, BLOCK_SIZE):

            if bit_index >= len(bits):
                break

            block = image[i:i+BLOCK_SIZE, j:j+BLOCK_SIZE]
            dct_block = cv2.dct(block)
            c1 = dct_block[4][4]
            c2 = dct_block[3][3]
            if bits[bit_index] == '1':
                if c1 <= c2:
                    dct_block[4][4] = c2 + STRENGTH
            else:
                if c1 >= c2:
                    dct_block[4][4] = c2 - STRENGTH
            image[i:i+BLOCK_SIZE, j:j+BLOCK_SIZE] = cv2.idct(dct_block)
            bit_index += 1

    return np.uint8(image)
