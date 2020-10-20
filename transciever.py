# For using hardware interface, abilitate:
# https://superuser.com/questions/1205126/device-dev-spidev-not-found
from RFM69 import Radio, FREQ_915MHZ
import datetime
import time
import paho.mqtt.client as paho
# pip install rpi-rfm69

class LoRaMQTTClient:
    def __init__(self, node_id, network_id, recipient_id, broker, port, topic):
        # For LoRa
        self.node_id = node_id
        self.network_id = network_id
        self.recipient_id = recipient_id
        self.radio = None
        self.radioOn = False

        # For MQTT
        self.broker = broker
        self.port = port
        self.topic = topic
        self.conn_flag = False
        self.client = None

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

    def initalizeLoRaRadio(self):
        self.radio = Radio(FREQ_915MHZ, self.node_id, self.network_id, isHighPower=True, verbose=True)
        self.radioOn = True

    def getRFData(self, rx_counter):
        if self.radioOn == False:
            return None
        # Every 10 seconds get packets
        if rx_counter > 10:
            rx_counter = 0
            print("Getting packets")
            # Process packets
            packets = []
            for packet in self.radio.get_packets():
                packets.append(packet)
            return packets
        return None

    def run(self):
        print ("Starting loop...")
        
        rx_counter = 0
        delay = 0.5
        packets = []
        # Connect
        self.client.connect(self.broker, self.port)
        while not self.conn_flag:
            time.sleep(1)
            self.client.loop()

        while True:
            # Get the packets from rfm
            packets = self.getRFData(rx_counter)
            # Send data to broker
            if packets != None and len(packets) != 0:
                self.client.publish(self.topic, " ".join(packets))
                self.client.loop()            

            rx_counter += delay
            time.sleep(delay)

            print("Sending packet Hello")
            self.client.publish(self.topic, "Hello")
            self.client.loop()

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
    client.initalizeLoRaRadio()
    client.run()
