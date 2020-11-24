# For using hardware interface, abilitate:
# https://superuser.com/questions/1205126/device-dev-spidev-not-found
# System modules
import signal, os
import datetime
import time
import ssl

# Arduino and MQTT
import serial
import paho.mqtt.client as paho
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
        self.conn_flag = False
        self.client = None

        # For the thread
        self.queue = queue.Queue(100)
        self.lock = threading.Lock()
        self.exitQ = queue.Queue(1)
        self.exitL = threading.Lock()
        self.aThread = ArduinoThread(self.arduino, 1, "RadioThread", self.queue, self.lock, self.exitQ, self.exitL)

    # Functions for client
    def on_connect(self, client, userdata, flags, rc):
        self.conn_flag = True
        print("connected", self.conn_flag)

    def on_log(self, client, userdata, level, buf):
        print("buffer", buf)

    def on_disconnect(self, client, userdata, rc):
        print("client disconnect ok")
        self.conn_flag = False

    def createMQTTClient(self, clientName, tlsRoute, tlsVersion, ciphers):
        # Attributes
        self.client = paho.Client(clientName)
        self.client.tls_set(tlsRoute, tls_version=tlsVersion)
        self.client.tls_insecure_set(True)

        # Functions
        self.client.on_log = self.on_log
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    def run(self):
        global interrupt
        print ("Starting loop...")

        delay = 1
        packets = []
        # Connect
        self.client.connect(self.broker, self.port)
        while not self.conn_flag:
            time.sleep(1)
            self.client.loop()

        self.aThread.start()
        while True:
            # Get the packets from rfm
            packets = []
            self.lock.acquire()
            while not self.queue.empty():
                packets = self.queue.get()
                print(packets)
                # Send data to broker
                self.client.publish(self.topic, " ".join(packets))
                self.client.loop()
            self.lock.release()
            time.sleep(delay)
            self.client.loop()
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
            self.client.publish(self.topic, " ".join(packets))
        self.lock.release()

        # Terminate thread
        self.exitL.acquire()
        self.exitQ.put(-1)
        self.exitL.release()
        self.aThread.join()

        # Terminate MQTT client
        self.client.loop()
        self.client.disconnect()

# Post quantum:
# NEWHOPE512-ECDSA-AES128-GCM-SHA256
#        -RSA

# Classical ciphers to use:
# RSA: 
# AES128-GCM-SHA256

# Ec:
# ECDHE-ECDSA-AES128-SHA
# ECDHE-RSA-AES128-SHA

#/home/pi/Documents/certs/c3

if __name__ == '__main__':
    # Set the signal interrupt handler
    signal.signal(signal.SIGINT, handler)
    client = LoRaMQTTClient("/dev/ttyACM0", 9600, '192.168.1.99', 8883, "test/topic")
    client.createMQTTClient("Test", "/home/pi/Documents/certs/c3/ca.crt", ssl.PROTOCOL_TLSv1_2, "NEWHOPE512-ECDSA-AES128-GCM-SHA256")
    client.run()
