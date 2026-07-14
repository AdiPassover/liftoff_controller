import socket


class UDPServer:
    def __init__(self, host: str, port: int, on_data_received: callable, on_stop: callable = lambda: None):
        """
        Initializes the UDP server and starts listening for incoming data.

        :param host: The host IP address to bind the server to.
        :param port: The port number to bind the server to.
        :param on_data_received: A callback function to handle received data.
        """
        self.host = host
        self.port = port
        self.on_data_received = on_data_received
        self.on_stop = on_stop
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))

    def listen(self):
        """Listens for incoming UDP data."""
        print(f"Server listening on {self.host}:{self.port}")
        try:
            while self.running:
                data, _ = self.sock.recvfrom(1024)
                self.on_data_received(data)
        except KeyboardInterrupt:
            print("Server shutting down...")
            self.running = False
        finally:
            self.on_stop()
            self.sock.close()
        



if __name__ == "__main__":

    def print_data(data):
        print(f"Data received: {data}")
    
    server = UDPServer("127.0.0.1", 9000, print_data)
    server.listen()