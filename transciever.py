# For using hardware interface, abilitate:
# https://superuser.com/questions/1205126/device-dev-spidev-not-found
# System modules
import signal, os
import datetime
import time

# Radio and MQTT
from RFM69 import Radio, FREQ_915MHZ
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
    if signum == signal.SIGINT:
        interrupt = True

class RadioC:
    """
    Encapsulates the radio.
    """
    def __init__(self, node_id, network_id, recipient_id):
        self.node_id = node_id
        self.network_id = network_id
        self.recipient_id = recipient_id
        self.radioOn = False
        self.initalizeLoRaRadio()
        print(self.radio.read_temperature())

    def initalizeLoRaRadio(self):
        self.radio = Radio(FREQ_915MHZ, self.node_id, self.network_id, isHighPower=True, verbose=True)
        self.radioOn = True

    def getRFData(self):
        if self.radioOn == False:
            return None
        # Every 10 seconds get packets
        # Process packets
        packets = []
        for packet in self.radio.get_packets():
            packets.append(packet)
        if len(packets) != 0:
            print("Getting packets") 
        return packets

class RadioThread(threading.Thread):
    """
    Create a background thread for constantly listening incoming transmissions from
    the LoRa Radio.
    """
    def __init__(self, radio, threadID, name, q, qLock, exitQ, exitL):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.queue = q
        self.qLock = qLock
        self.exitQ = exitQ
        self.exitL = exitL
        self.radio = radio

    def run(self):
        """ Run the thread """
        finish = False
        while not finish:
            time.sleep(1)
            packets = self.radio.getRFData()
            if packets == None or len(packets) == 0:
                continue
            else:
                self.qLock.acquire()
                self.queue.put(packets.copy())
                self.qLock.release()
            # Process thread termination
            self.exitL.acquire()
            if not self.exitQ.empty():
                e = self.exitQ.get()
                finish = True
            self.exitL.release()

class LoRaMQTTClient:
    def __init__(self, node_id, network_id, recipient_id, broker, port, topic):
        # For LoRa
        self.radio = RadioC(node_id, network_id, recipient_id)

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
        self.rThread = RadioThread(self.radio, 1, "RadioThread", self.queue, self.lock, self.exitQ, self.exitL)

    # Functions for client
    def on_connect(self, client, userdata, flags, rc):
        self.conn_flag = True
        print("connected", self.conn_flag)

    def on_log(self, client, userdata, level, buf):
        print("buffer", buf)

    def on_disconnect(self, client, userdata, rc):
        print("client disconnect ok")
        self.conn_flag = False

    def createMQTTClient(self, clientName, tlsRoute, ciphers):
        # Attributes
        self.client = paho.Client(clientName)
        self.client.tls_set(tlsRoute)
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

        self.rThread.start()
        while True:
            # Get the packets from rfm
            packets = []
            self.lock.acquire()
            if not self.queue.empty():
                packets = self.queue.get()
                print(packets)
            self.lock.release()
            # Send data to broker
            if packets != None and len(packets) != 0:
                self.client.publish(self.topic, " ".join(packets))
                self.client.loop()
            time.sleep(delay)
            print("Hello")
            #print("Sending packet Hello")
            #self.client.publish(self.topic, "Hello")
            self.client.loop()
            if interrupt:
                break
        self.disconnect()
    
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
        self.rThread.join()
        
        # Terminate MQTT client
        self.client.wait_for_publish()
        self.client.loop()
        self.client.disconnect()

# Post quantum:
# NEWHOPE-ECDSA-AES128-GCM-SHA256
#        -RSA

# Classical ciphers to use:
# RSA: 
# AES128-GCM-SHA256

# Ec:
# ECDHE-ECDSA-AES128-SHA
# ECDHE-RSA-AES128-SHA

#/home/pi/Documents/certs/c3

if __name__ == '__main__':
    client = LoRaMQTTClient(1, 0, 2, '192.168.1.99', 8883, "test/topic")
    client.createMQTTClient("Test", "/home/pi/Documents/certs/c3/ca.crt", "ECDHE-ECDSA-AES128-SHA256")
    client.run()
