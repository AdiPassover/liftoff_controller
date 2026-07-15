from math import inf
import json
from pathlib import Path



def _clamp(value, minimum, maximum):
    """Clamp value to the range [minimum, maximum]."""
    return max(minimum, min(value, maximum))


class PID:
    def __init__(self, p, i=0.0, d=0.0, max_i=float("inf")):
        self.P = p
        self.I = i
        self.D = d
        self.MAX_I = max_i

        self.integral = 0.0
        self.last_error = None

    def update(self, error, dt, max_val=None):
        """
        Update the PID controller.

        Args:
            error: Current error.
            dt: Time since previous update (seconds).
            max_val: Optional maximum absolute output.

        Returns:
            PID controller output.
        """
        if self.last_error is None:
            self.last_error = error

        # Integral term
        self.integral += self.I * error * dt

        # Derivative term
        diff = error - self.last_error
        if dt > 0:
            diff /= dt

        # Clamp integral (anti-windup)
        clamped_integral = _clamp(
            self.integral,
            -self.MAX_I,
            self.MAX_I,
        )

        output = (
            self.P * error
            + self.D * diff
            + clamped_integral
        )

        self.last_error = error

        if max_val is not None:
            assert max_val >= 0
            output = _clamp(output, -max_val, max_val)

        return output

    def reset(self):
        """Reset the controller state."""
        self.last_error = None
        self.integral = 0.0
    
    def __str__(self):
        return f"(P={self.P}, I={self.I}, D={self.D}, MAX_I={self.MAX_I})"


def create_pids(filename="pid_configs/liftoff1.json"):

    pids = {}

    with open(filename, "r") as f:
        cfg = json.load(f)

        for name, values in cfg.items():
            pids[name] = PID(
                p=values["P"],
                i=values["I"],
                d=values["D"],
                max_i=values["MAX_I"],
            )

    return pids


if __name__ == "__main__":
    pids = create_pids()
    for name, pid in pids.items():
        print(f"{name}: {pid}")