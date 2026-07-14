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

        # Convert values from -1 to 1 into -32768 to 32767 for the gamepad
        def scale(value):
            return int(value * 32767)

        self.gamepad.left_joystick_float(x_value_float=scale(yaw), y_value_float=scale(throttle))
        self.gamepad.right_joystick_float(x_value_float=scale(roll), y_value_float=scale(pitch))
        self.gamepad.update()


if __name__ == "__main__":
    from time import sleep
    gamepad = VirtualGamepad()
    gamepad.start()
    gamepad.control_sticks(roll=0.5, pitch=-0.5, yaw=0.2, throttle=-0.8)
    sleep(5)
    gamepad.stop()
