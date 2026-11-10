"""Small bounded OSC subset for VIRTUAL's immediate numeric feedback, without bpy."""
import math
import struct

MAX_PACKET = 4096


def _string(value):
    raw = value.encode('utf-8') + b'\0'
    return raw + b'\0' * (-len(raw) % 4)


def encode(address, value):
    if not address.startswith('/virtual/') or '\0' in address:
        raise ValueError('Expected a VIRTUAL address')
    if not math.isfinite(value):
        raise ValueError('Expected a finite value')
    return _string(address) + _string(',f') + struct.pack('>f', value)


def decode(packet):
    """Decode one numeric message. Bundles and unsupported messages are rejected."""
    if not packet or len(packet) > MAX_PACKET or len(packet) % 4:
        raise ValueError('Invalid OSC packet size')

    def string(offset):
        end = packet.index(b'\0', offset)
        next_offset = (end + 4) & ~3
        if next_offset > len(packet) or any(packet[end:next_offset]):
            raise ValueError('Invalid OSC padding')
        return packet[offset:end].decode('utf-8'), next_offset

    address, offset = string(0)
    tag, offset = string(offset)
    formats = {',f': ('>f', 4), ',i': ('>i', 4), ',d': ('>d', 8)}
    if not address.startswith('/virtual/'):
        raise ValueError('Expected a VIRTUAL address')
    if tag in {',T', ',F'}:
        value = float(tag == ',T')
        size = 0
    elif tag in formats:
        fmt, size = formats[tag]
        if len(packet) != offset + size:
            raise ValueError('Invalid OSC argument size')
        value = float(struct.unpack_from(fmt, packet, offset)[0])
    else:
        raise ValueError('Expected one numeric argument')
    if len(packet) != offset + size or not math.isfinite(value):
        raise ValueError('Invalid OSC argument')
    return address, value


def scene_cue(address, value):
    """Return a zero-based cue for accepted scene launches, ignoring release edges."""
    parts = address.split('/')
    if (len(parts) == 5 and parts[1:3] == ['virtual', 'scene']
            and parts[4] == 'launch' and parts[3] in tuple(map(str, range(1, 9)))
            and value >= .5):
        return int(parts[3]) - 1
    return None
