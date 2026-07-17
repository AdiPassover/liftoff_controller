"""
macOS Virtual Gamepad — Python wrapper for the native HID gamepad server.

This module provides a MacVirtualGamepad class with the same interface as
the Windows VirtualGamepad (start, stop, control_sticks), but communicates
with a native Objective-C helper process that creates a system-wide virtual
joystick via IOHIDUserDevice.

Requirements (on the Mac):
  1. Compiled helper: cd macos && bash build.sh
  2. A valid signature and provisioning profile authorizing the restricted
     com.apple.developer.hid.virtual.device entitlement
"""

import os
import time
import struct
import socket
import subprocess
import signal


# Path to the compiled native helper, relative to this file
_HELPER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "macos")
_HELPER_BIN = os.path.join(_HELPER_DIR, "hid_gamepad_server")
_SOCKET_PATH = "/tmp/liftoff_gamepad.sock"


def _describe_exit_status(returncode):
    """Return a human-readable subprocess exit status."""
    if returncode is None:
        return "is still running"
    if returncode < 0:
        signal_number = -returncode
        try:
            signal_name = signal.Signals(signal_number).name
        except ValueError:
            signal_name = f"signal {signal_number}"
        return f"was terminated by {signal_name} (return code {returncode})"
    return f"exited with code {returncode}"


def _format_helper_output(output):
    """Format captured helper output consistently for exceptions."""
    output = output.rstrip()
    return output if output else "(no output captured)"


class MacVirtualGamepad:
    """
    Virtual gamepad for macOS using IOHIDUserDevice via a native helper process.

    The helper creates a system-wide HID joystick that Liftoff (or any game
    using SDL/Unity input) will detect. Communication happens over a Unix
    domain socket with 16-byte binary messages (4 x float32 LE).
    """

    def __init__(self):
        self._process = None
        self._sock = None
        self.running = False

    def start(self):
        """Launch the native helper and connect to its Unix socket."""
        if self.running:
            return

        # Validate the helper binary exists
        if not os.path.isfile(_HELPER_BIN):
            raise FileNotFoundError(
                f"Native helper not found at: {_HELPER_BIN}\n"
                f"Please compile it first:\n"
                f"  cd {_HELPER_DIR} && bash build.sh"
            )

        # Remove stale socket
        if os.path.exists(_SOCKET_PATH):
            os.unlink(_SOCKET_PATH)

        # Launch the helper process
        self._process = subprocess.Popen(
            [_HELPER_BIN, _SOCKET_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Wait for the helper to create its listening socket.
        timeout = 5.0
        start_time = time.monotonic()
        ready = False

        while time.monotonic() - start_time < timeout:
            # Check if the process exited prematurely
            if self._process.poll() is not None:
                output = self._process.stdout.read()
                raise RuntimeError(
                    f"HID helper {_describe_exit_status(self._process.returncode)}.\n"
                    f"Helper output:\n{_format_helper_output(output)}"
                )

            if os.path.exists(_SOCKET_PATH):
                # Give the server a moment to start listening
                time.sleep(0.1)
                ready = True
                break

            time.sleep(0.05)

        if not ready:
            process = self._process
            self.stop()
            output = process.stdout.read() if process and process.stdout else ""
            status = _describe_exit_status(process.returncode if process else None)
            raise TimeoutError(
                f"HID helper did not create its socket within {timeout:.1f} seconds "
                f"and {status}.\n"
                f"Helper output:\n{_format_helper_output(output)}"
            )

        # Connect to the Unix socket
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._sock.connect(_SOCKET_PATH)
        except OSError as error:
            process = self._process
            self.stop()
            output = process.stdout.read() if process and process.stdout else ""
            status = _describe_exit_status(process.returncode if process else None)
            raise RuntimeError(
                f"Could not connect to HID helper socket {_SOCKET_PATH}: {error}.\n"
                f"The helper {status}.\n"
                f"Helper output:\n{_format_helper_output(output)}"
            ) from error

        self.running = True
        print("Virtual gamepad (macOS HID) started.")

    def stop(self):
        """Disconnect and terminate the helper process."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        if self._process and self._process.poll() is None:
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

        self._process = None

        # Clean up socket file
        if os.path.exists(_SOCKET_PATH):
            try:
                os.unlink(_SOCKET_PATH)
            except OSError:
                pass

        if self.running:
            self.running = False
            print("Virtual gamepad (macOS HID) stopped.")

    def control_sticks(self, roll, pitch, yaw, throttle):
        """
        Send stick values to the virtual gamepad.

        Args:
            roll:     Right stick X, range -1.0 to 1.0
            pitch:    Right stick Y, range -1.0 to 1.0
            yaw:      Left stick X,  range -1.0 to 1.0
            throttle: Left stick Y,  range -1.0 to 1.0
        """
        if not self.running or not self._sock:
            return

        # Pack as 4 little-endian floats: roll, pitch, yaw, throttle
        data = struct.pack("<4f", roll, pitch, yaw, throttle)
        try:
            self._sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            print("Warning: lost connection to HID helper.")
            self.running = False

    def __del__(self):
        self.stop()


if __name__ == "__main__":
    gamepad = MacVirtualGamepad()
    try:
        gamepad.start()
        print("Sending test stick values for 5 seconds...")
        gamepad.control_sticks(roll=0.5, pitch=-0.5, yaw=0.2, throttle=-0.8)
        time.sleep(5)
    finally:
        gamepad.stop()
