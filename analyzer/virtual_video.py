"""Provisional VIRTUAL viewport stream wire format."""
import struct

MAGIC = b'VFRM'
VERSION = 1
PIXEL_RGBA8 = 1
HEADER = struct.Struct('!4sHHIIQQI')
MAX_WIDTH = 3840
MAX_HEIGHT = 2160
MAX_PAYLOAD = MAX_WIDTH * MAX_HEIGHT * 4


def pack_header(width, height, sequence, timestamp_ns):
    if not 1 <= width <= MAX_WIDTH or not 1 <= height <= MAX_HEIGHT:
        raise ValueError('Viewport dimensions are outside the VIRTUAL stream limit')
    payload_bytes = width * height * 4
    if payload_bytes > MAX_PAYLOAD:
        raise ValueError('Viewport frame exceeds the VIRTUAL stream limit')
    return HEADER.pack(MAGIC, VERSION, PIXEL_RGBA8, width, height,
                       sequence, timestamp_ns, payload_bytes)
