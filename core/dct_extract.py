import cv2
from config import BLOCK_SIZE,STRENGTH


def extract_watermark(image, length):
    h, w = image.shape
    bits = ""

    for i in range(0, h, BLOCK_SIZE):
        for j in range(0, w, BLOCK_SIZE):

            block = image[i:i+BLOCK_SIZE, j:j+BLOCK_SIZE]
            dct_block = cv2.dct(block)
            c1 = dct_block[4][4]
            c2 = dct_block[3][3]
            if c1 > c2:
                 bits += '1'
            else:
                bits += '0'

            if len(bits) >= length * 8:
                return bits

    return bits
