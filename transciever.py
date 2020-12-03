# For using hardware interface, abilitate:
# https://superuser.com/questions/1205126/device-dev-spidev-not-found
# System modules
import signal, os
import datetime
import time
import ssl

# Arduino and MQTT
import serial
# pip install rpi-rfm69

# Multithreading
import threading
import queue

# Handle interruptions
interrupt = False

def handler(signum, frame):
    """
    Handle the KeyboardInterrupt signal
    """
    global interrupt
    interrupt = True
    print("Killing process")

class ArduinoC:
    """
    Connect arduino uno directly to the raspberry, and use it t0 access the radio.
    """
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.ardOn = False
        self.initalizeArduino()

    def initalizeArduino(self):
        try:
            self.arduino = serial.Serial(self.port, self.baudrate)
        except:
            print("Arduino not connected")
        else:
            self.ardOn = True

    def getData(self):
        if not self.ardOn:
            return None
        message = self.arduino.read_until() # End of line
        packet = message[:13]
        return [packet.decode('ascii')]

class ArduinoThread(threading.Thread):
    """
    Create a background thread for constantly listening incoming transmissions from
    the LoRa Radio.
    """
    def __init__(self, arduino, threadID, name, q, qLock, exitQ, exitL):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.queue = q
        self.qLock = qLock
        self.exitQ = exitQ
        self.exitL = exitL
        self.arduino = arduino

    def run(self):
        """ Run the thread """
        finish = False
        while not finish:
            time.sleep(1)
            message = self.arduino.getData()
            if message:
                self.qLock.acquire()
                self.queue.put(message)
                self.qLock.release()
            # Process thread termination
            self.exitL.acquire()
            if not self.exitQ.empty():
                e = self.exitQ.get()
                finish = True
            self.exitL.release()

class LoRaMQTTClient:
    def __init__(self, arPort, baudrate, broker, port, topic):
        # For LoRa
        self.arduino = ArduinoC(arPort, baudrate)

        # For MQTT
        self.broker = broker
        self.port = port
        self.topic = topic
        self.group = None
        self.ca = None

        # For the thread
        self.queue = queue.Queue(100)
        self.lock = threading.Lock()
        self.exitQ = queue.Queue(1)
        self.exitL = threading.Lock()
        self.aThread = ArduinoThread(self.arduino, 1, "RadioThread", self.queue, self.lock, self.exitQ, self.exitL)

    def setTLSGroups(self, groups):
        """
        Select a group for key exchange.
        """
        self.group = group

    def setCACert(self, cafile):
        """
        Set CA file.
        """
        self.ca = cafile

    def publish(self, packet):
        """
        There is no client API that currently supports TLS 1.3.
        I have modified the mosquitto clients to use TLS 1.3, so I will
        publish the data with it.
        """
        if is not self.ca or not self.groups:
            print("Can't publish: missing ca file or groups.")
            return
        cmd = "mosquitto_pub -h " + self.broker + " -t " + self.topic + " -p 8883"
        cmd += " --cafile " + self.ca + " --groups " + self.groups + " --tls-version tlsv1.3"
        cmd + " -m " + str(packet)
        os.system(cmd)

    def run(self):
        global interrupt
        print ("Starting loop...")

        delay = 1
        packets = []

        self.aThread.start()
        while True:
            # Get the packets from rfm
            packets = []
            self.lock.acquire()
            while not self.queue.empty():
                packets = self.queue.get()
                print(packets)
                # Send data to broker
            self.lock.release()
            time.sleep(delay)
            if interrupt:
                break
        self.disconnect()
        print("Finishing")
    
    def disconnect(self):
        """
        Handle the end of program
        """
        # Handle all remained packets
        self.lock.acquire()
        while not self.queue.empty():
            packets = self.queue.get()
            #   
        self.lock.release()

        # Terminate thread
        self.exitL.acquire()
        self.exitQ.put(-1)
        self.exitL.release()
        self.aThread.join()

if __name__ == '__main__':
    # Set the signal interrupt handler
    signal.signal(signal.SIGINT, handler)
    client = LoRaMQTTClient("/dev/ttyACM0", 9600, '192.168.1.99', 8883, "test/topic")
    client.setCACert("/home/pi/Documents/certs/pqcerts/ca.crt")
    client.setTLSGroups("kyber512")
    client.run()
