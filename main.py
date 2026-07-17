from commands_parsing import parse_and_convert
from commands_server import UDPServer
from virtual_gampad import VirtualGamepad
from pid import create_pids

import argparse
import time


def main(server_host: str, server_port: int):

    pids = create_pids("pid_configs/liftoff1.json")
    gamepad = VirtualGamepad()
    last_time = time.perf_counter()

    def _handle_data(data: bytes):
        nonlocal last_time

        roll, pitch, yaw, throttle = parse_and_convert(data)

        now = time.perf_counter()
        dt = now - last_time
        last_time = now

        cmd_roll = pids["roll"].update(roll, dt)
        cmd_pitch = pids["pitch"].update(pitch, dt)
        cmd_yaw = pids["yaw"].update(yaw, dt)
        cmd_throttle = pids["throttle"].update(throttle, dt)

        gamepad.control_sticks(cmd_roll, cmd_pitch, cmd_yaw, cmd_throttle)

    server = UDPServer(server_host, server_port, _handle_data, on_stop=gamepad.stop)

    gamepad.start()
    server.listen()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP client")
    parser.add_argument("ip", nargs="?", default='localhost', help="Server IP address")
    parser.add_argument("-p", "--port", default=5000, type=int, help="Server port")

    args = parser.parse_args()

    main(args.ip, args.port)
