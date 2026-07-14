from commands_parsing import parse_and_convert
from commands_server import UDPServer
from virtual_gampad import VirtualGamepad
import argparse


def main(server_host: str, server_port: int):

    gamepad = VirtualGamepad()

    def _handle_data(data: bytes):
        roll, pitch, yaw, throttle = parse_and_convert(data)
        gamepad.control_sticks(roll, pitch, yaw, throttle)

    server = UDPServer(server_host, server_port, _handle_data, on_stop=gamepad.stop)

    gamepad.start()
    server.listen()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP client")
    parser.add_argument("ip", nargs="?", default='localhost', help="Server IP address")
    parser.add_argument("-p", "--port", default=6001, type=int, help="Server port")

    args = parser.parse_args()

    main(args.ip, args.port)
