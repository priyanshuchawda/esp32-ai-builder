import serial
import logging

logger = logging.getLogger(__name__)


class SerialReader:
    """
    Handles serial connection to the ESP32 board and reads lines from the serial port.
    """

    def __init__(self, port="COM5", baudrate=115200, timeout=1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def connect(self):
        """
        Attempts to establish a connection to the serial port.
        Returns True if successful, False otherwise.
        """
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            # Flush buffers
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            logger.info(
                f"Connected to serial port {self.port} at {self.baudrate} baud."
            )
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to serial port {self.port}: {e}")
            return False

    def read_lines(self):
        """
        Generator yielding decoded lines read from the serial port.
        """
        if not self.ser or not self.ser.is_open:
            logger.error("Serial port is not open.")
            return

        while self.ser.is_open:
            try:
                line_bytes = self.ser.readline()
                if not line_bytes:
                    # Timeout reached
                    continue

                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if line:
                    yield line
            except serial.SerialException as e:
                logger.error(f"Serial read exception: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected serial reading error: {e}")
                break

    def close(self):
        """
        Closes the serial connection.
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info(f"Closed serial port {self.port}.")
