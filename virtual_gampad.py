import sys

if sys.platform == 'darwin':
    # macOS: use native IOHIDUserDevice-based virtual gamepad
    from virtual_gamepad_mac import MacVirtualGamepad as VirtualGamepad
else:
    # Windows: use vgamepad (ViGEmBus)
    import vgamepad

    class VirtualGamepad:
        def __init__(self):
            self.gamepad = vgamepad.VX360Gamepad()
            self.running = False

        def start(self):
            if not self.running:
                self.running = True
                print("Virtual gamepad started.")

        def stop(self):
            if self.running:
                self.running = False
                print("Virtual gamepad stopped.")

        def control_sticks(self, roll, pitch, yaw, throttle):
            """
            Control the virtual gamepad's sticks based on the provided roll, pitch, yaw, and throttle values.
            Expects values in the range of -1 to 1 for each parameter.
            """
            if not self.running:
                print("Gamepad is not running. Please start it first.")
                return

            self.gamepad.left_joystick_float(x_value_float=yaw, y_value_float=throttle)
            self.gamepad.right_joystick_float(x_value_float=roll, y_value_float=pitch)
            self.gamepad.update()


if __name__ == "__main__":
    from time import sleep
    gamepad = VirtualGamepad()
    gamepad.start()
    gamepad.control_sticks(roll=0.5, pitch=-0.5, yaw=0.2, throttle=-0.8)
    sleep(5)
    gamepad.stop()
