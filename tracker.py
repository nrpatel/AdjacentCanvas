#!/usr/bin/env python

import sys
import serial
import struct

PACKET_QUAT = 0
PACKET_ACC = 1
PACKET_GYRO = 2
PACKET_MAG = 3
PACKET_TEMPERATURE = 4
PACKET_GPIO = 5
PACKET_COLOR = 6
PACKET_BLINK = 7
PACKET_IR = 8
PACKET_STREAM = 9
PACKET_VERSION = 10
PACKET_ID = 11
PACKET_CAL = 12
PACKET_GPIO_DDR = 13
PACKET_GPIO_PORT = 14
PACKET_POWER = 15
PACKET_MAX = 16

class Tracker(object):
    def __init__(self, port):
        self.END = chr(0xC0)
        self.ESC = chr(0xDB)
        self.ESC_END = chr(0xDC)
        self.ESC_ESC = chr(0xDD)
        self.ser = serial.Serial(port, 38400, timeout=0)
        self.ser.open()
        self.ser.flushInput()
        self.read_buf = []
        self.escaping = False
    
    def parse_packet(self, packet):
        t = ord(packet[0])
    
        try:
            if t == PACKET_QUAT:
                return struct.unpack('!Bffff', packet)
            elif t == PACKET_ACC or t == PACKET_GYRO or t == PACKET_MAG:
                return struct.unpack('!Bhhh', packet)
            elif t == PACKET_COLOR or t == PACKET_BLINK:
                return struct.unpack('!BBBB', packet)
            elif t == PACKET_GPIO or t == PACKET_IR:
                return struct.unpack('!BB', packet)
            elif t == PACKET_VERSION or t == PACKET_ID:
                return struct.unpack('!BI', packet)
            else:
                print "Unknown packet type %d" % t
                return None
        except struct.error as ex:
            print "Failed to parse packet:", ex
            
        return None
            
    def read_char(self, c):
        if c == self.END and len(self.read_buf) != 0:
            self.escaping = False
            return 1
        elif c == self.ESC:
            self.escaping = True
        elif c == self.ESC_END:
            if self.escaping:
                self.read_buf.append(self.END)
                self.escaping = False
            else:
                self.read_buf.append(c)
        elif c == self.ESC_ESC:
            if self.escaping:
                self.read_buf.append(self.ESC)
                self.escaping = False
            else:
                self.read_buf.append(c)
        else:
            self.read_buf.append(c)
                
        return 0
        
    def read_packets(self):
        packets = []
        characters = self.ser.read(1024)
        if len(characters):
            for c in characters:
                if self.read_char(c):
                    packet = self.parse_packet(''.join(self.read_buf))
                    if packet:
                        packets.append(packet)
                    self.read_buf = []
        return packets
        
    def write_packet(self, packet):
        slipped = [];
        
        for c in packet:
            if c == self.END:
                slipped.append(self.ESC)
                slipped.append(self.ESC_END)
            elif c == self.ESC:
                slipped.append(self.ESC)
                slipped.append(self.ESC_ESC)
            else:
                slipped.append(c)
                
        slipped.append(self.END)
        self.ser.write(''.join(slipped))
        
    def set_color(self, rgb):
        packed = struct.pack('!BBBB', PACKET_COLOR, rgb[0], rgb[1], rgb[2])
        self.write_packet(packed)
        
    def set_streaming_mode(self, quat, acc, gyro, mag, temperature, gpio):
        mask = (quat << PACKET_QUAT) | (acc << PACKET_ACC) | (gyro << PACKET_GYRO) |\
                (mag << PACKET_MAG) | (temperature << PACKET_TEMPERATURE) | (gpio << PACKET_GPIO)
        packed = struct.pack('!BB', PACKET_STREAM, mask)
        self.write_packet(packed)
        
    def set_calibration(self, ox, oy, oz, sx, sy, sz):
        packed = struct.pack('!Bffffff', PACKET_CAL, ox, oy, oz, sx, sy, sz)
        self.write_packet(packed)

    def set_gpio_direction(self, f0, f1, f4, f5, f6, f7):
        mask = (f0 != 0) | ((f1 != 0) << 1) | ((f4 != 0) << 4) |\
               ((f5 != 0) << 5) | ((f6 != 0) << 6) | ((f7 != 0) << 7)
        packed = struct.pack('!BB', PACKET_GPIO_DDR, mask)
        self.write_packet(packed)
        
    def set_gpio_value(self, f0, f1, f4, f5, f6, f7):
        mask = (f0 != 0) | ((f1 != 0) << 1) | ((f4 != 0) << 4) |\
               ((f5 != 0) << 5) | ((f6 != 0) << 6) | ((f7 != 0) << 7)
        packed = struct.pack('!BB', PACKET_GPIO_PORT, mask)
        self.write_packet(packed)
        
    def set_power(self, power):
        packed = struct.pack('!BB', PACKET_POWER, power)
        self.write_packet(packed)
        
    def close(self):
        self.ser.close()

if __name__ == '__main__':
    port = '/dev/ttyACM0'
    if (len(sys.argv) > 1):
        port = sys.argv[1]
    tracker = Tracker(port)
    tracker.set_color((255, 0, 255))
    tracker.set_streaming_mode(1, 0, 0, 0, 0, 1)
    while True:
        packets = tracker.read_packets()
        for packet in packets:
            print packet

