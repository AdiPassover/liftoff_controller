import struct


def parse_command(data: bytes) -> tuple:
    """
    Parse a packed binary message into roll, pitch, yaw, and throttle.
    
    Args:
        data (bytes): The binary message packed with struct.pack('<4h', roll, pitch, yaw, throttle).
                      The message can be longer, but only the first 4 values are considered.
    
    Returns:
        tuple: A tuple containing (roll, pitch, yaw, throttle).
    """
    # Unpack the first 4 short integers (2 bytes each) from the data
    roll, pitch, yaw, throttle = struct.unpack('<4h', data[:8])
    return roll, pitch, yaw, throttle


def convert_to_controller_range(roll, pitch, yaw, throttle):
    """
    Convert roll, pitch, yaw, and throttle values from -32768 to 32767 range to -1 to 1 range.
    
    Args:
        roll (int): Roll value in the range 0 to 2000
        pitch (int): Pitch value in the range 0 to 2000
        yaw (int): Yaw value in the range 0 to 2000
        throttle (int): Throttle value in the range 0 to 2000
    
    Returns:
        tuple: A tuple containing (roll, pitch, yaw, throttle) in the range -1 to 1.
    """
    # Convert from 0-2000 to -1 to 1
    def scale(value):
        return (value - 1000) / 1000.0

    return scale(roll), scale(pitch), scale(yaw), scale(throttle)

def parse_and_convert(data: bytes) -> tuple:
    """
    Parse the binary data and convert the values to the controller range.
    
    Args:
        data (bytes): The binary message packed with struct.pack('<4h', roll, pitch, yaw, throttle).
    
    Returns:
        tuple: A tuple containing (roll, pitch, yaw, throttle) in the range -1 to 1.
    """
    roll, pitch, yaw, throttle = parse_command(data)
    return convert_to_controller_range(roll, pitch, yaw, throttle)