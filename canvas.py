#!/usr/bin/env python

import sys
import math
import numpy
import tracker
import pygame
import pygame.camera
import pygame.gfxdraw
from pygame.locals import *
import threading

DEBUG_NONE = 0
DEBUG_CAMERA = 1
DEBUG_THRESHOLD = 2
DEBUG_MAX = 3

MODE_PAINTING = 0
MODE_MOVING = 1

class SprayCan(object):
    def __init__(self, port):
        self.tracker = tracker.Tracker(port)
        self.tracker.set_color((0, 0, 255))
        # IR LED output, button input
        self.tracker.set_gpio_direction(1, 0, 0, 0, 0, 0)
        # turn off sunk IR LED, pullup button
        self.tracker.set_gpio_value(1, 1, 0, 0, 0, 0)
        # stream just the GPIO state
        self.tracker.set_streaming_mode(0, 1, 0, 0, 0, 0)
        self.charge = 1.0
    
    def update_shake(self, x, y, z):
        x = float(x)/1000.0
        y = float(y)/1000.0
        z = float(z)/1000.0
        g = math.fabs(1.0-math.sqrt(x**2+y**2+z**2)/16.0)/100.0
        if g > 0.005:
            self.charge += g
            self.charge = min(self.charge, 1.0)
        print "g charge %f %f" % (g, self.charge)
    
    def read_packets(self):
        packets = self.tracker.read_packets()
        for packet in packets:
            if packet[0] == tracker.PACKET_ACC:
                self.update_shake(packet[1], packet[2], packet[3])
                    
    def set_color(self, color):
        self.charge -= 0.0025
        self.charge = max(self.charge, 0.0)
        self.tracker.set_color(color)
        
    def get_charge(self):
        return self.charge
        
    def close(self):
        self.tracker.set_color((64, 0, 0))
        # IR LED output, button input
        self.tracker.set_gpio_direction(1, 0, 0, 0, 0, 0)
        # turn off sunk IR LED, pullup button
        self.tracker.set_gpio_value(1, 1, 0, 0, 0, 0)
        self.tracker.close()

class AdjacentCanvas(object):
    def __init__(self, matrix, port1, port2):
        self.mat = matrix
        self.debug_mode = DEBUG_NONE
        self.threshold = 100
        self.dthreshold = 0
        self.corner_points = []
        self.mode = MODE_PAINTING
        
        self.can = SprayCan(port2)
        
#        self.tracker = tracker.Tracker(port1)
#        self.tracker.set_color((0, 0, 0))
#        # turn on the IR leds
##        self.tracker.set_streaming_mode(0, 0, 0, 0, 0, 0)
#        self.tracker.set_gpio_direction(1, 1, 1, 1, 0, 0)
#        self.tracker.set_gpio_value(0, 0, 0, 0, 0, 0)
    
        pygame.init()
        pygame.mouse.set_visible(False)
        self.display_res = (848, 480)
        self.display = pygame.display.set_mode(self.display_res,pygame.FULLSCREEN)
        self.display.fill((0, 0, 0))
        pygame.display.flip()
        
        # start the camera and find its resolution
        pygame.camera.init()
        clist = pygame.camera.list_cameras()
        if len(clist) == 0:
            raise IOError('No cameras found.  The IRCamera class needs a camera supported by Pygame')
        self.resolution = (640, 480)
        self.camera = pygame.camera.Camera(clist[0], self.resolution, "RGB")
        self.camera.start()
        # get the actual camera resolution
        self.resolution = self.camera.get_size()
        self.snapshot = pygame.surface.Surface(self.resolution, 0, self.display)
        self.t = pygame.surface.Surface(self.resolution, 0, self.display)
        self.canvas_color = pygame.Color(255,255,255)
        self.spray_sizes = [0.2, 0.3, 0.4]
        self.spray_alphas = [50, 30, 10]
        self.hue = 0.0
        
        self.drawing = pygame.surface.Surface(self.display_res, 0, self.display)
        self.frame = pygame.surface.Surface(self.display_res, 0, self.display)
        
    def convert_point(self, point):
        c = numpy.array([point[0],point[1],1])
        c = numpy.dot(self.mat,c)
        return [int(c[0]/c[2]), int(c[1]/c[2])]
        
    def points_from_blob(self, cc, scalings):
        drawlists = []
        # turn the blob into a list of points
        plist = cc.outline(1)
        centroid = cc.centroid()
        c = self.convert_point(centroid)
        for scale in scalings:
            drawlist = []
            for point in plist:
                norm_point = self.convert_point(point)
                # scale it bigger or smaller based on the scaling factor
                scale_point = (c[0]+(norm_point[0]-c[0])*scale,
                               c[1]+(norm_point[1]-c[1])*scale)
                drawlist.append(scale_point)
            drawlists.append(drawlist)
              
        return drawlists
        
    def update_tracking(self):
        def triangle_area(a, b, c):
            return a[0]*b[1] - a[1]*b[0] + b[0]*c[1] - b[1]*c[0] + c[0]*a[1] - c[1]*a[0]
    
        # get the individual large blobs inside it
        ccs = self.mask.connected_components(100)
        
        # if we have more than just the 4 corners, find the 4 largest blobs
        if len(ccs) > 4:
            ccs = sorted(ccs, key=lambda cc:cc.count(), reverse = True)
        # get the centers of the points
        if len(ccs) >= 4:
            # convert the camera point to a projector point
            self.corner_points = [self.convert_point(ccs[0].centroid()), self.convert_point(ccs[1].centroid()),\
                                  self.convert_point(ccs[2].centroid()), self.convert_point(ccs[3].centroid())]
        
            # quadrilateral ordering from http://stackoverflow.com/a/246063
            abc = triangle_area(self.corner_points[0], self.corner_points[1], self.corner_points[2])
            acd = triangle_area(self.corner_points[0], self.corner_points[2], self.corner_points[3])
            
            if abc < 0:
                if acd >= 0:
                    if triangle_area(self.corner_points[0], self.corner_points[1], self.corner_points[3]) < 0:
                        self.corner_points[2], self.corner_points[3] = self.corner_points[3], self.corner_points[2]
                    else:
                        self.corner_points[0], self.corner_points[3] = self.corner_points[3], self.corner_points[0]
            elif acd < 0:
                if triangle_area(self.corner_points[0], self.corner_points[1], self.corner_points[3]) < 0:
                    self.corner_points[1], self.corner_points[2] = self.corner_points[2], self.corner_points[1]
                else:
                    self.corner_points[0], self.corner_points[1] = self.corner_points[1], self.corner_points[0]
            else:
                self.corner_points[0], self.corner_points[2] = self.corner_points[2], self.corner_points[0]
                
            self.frame.fill((0,0,0))
            if len(self.corner_points) == 4:
                pygame.gfxdraw.filled_polygon(self.frame, self.corner_points, self.canvas_color)
                
        elif len(ccs) == 1:
            # assume we are in drawing mode if only one point exists
            drawing_points = self.points_from_blob(ccs[0], self.spray_sizes)
            self.hue += 0.5
            color = pygame.Color(0,0,0,0)
            for i in range(0, len(self.spray_sizes)):
                print self.can.get_charge()
                color.hsva = (int(self.hue)%360, 100, 100, int(self.can.get_charge()*self.spray_alphas[i]))
                pygame.gfxdraw.filled_polygon(self.drawing, drawing_points[i], color)
            self.can.set_color((color.r, color.g, color.b))
            
    def update_input(self):
    
        # update the threshold but keep it clamped to valid values
        self.threshold += self.dthreshold
        self.threshold = min(self.threshold, 255)
        self.threshold = max(self.threshold, 0)
    
        self.can.read_packets()
    
        self.snapshot = self.camera.get_image(self.snapshot)
        if self.debug_mode == DEBUG_THRESHOLD:
            pygame.transform.threshold(self.t, self.snapshot, (255, 255, 255), (self.threshold, self.threshold, self.threshold), (0, 0, 0), 1)
        
        # get a bitmask of the lit regions
        self.mask = pygame.mask.from_threshold(self.snapshot, (255, 255, 255), (self.threshold, self.threshold, self.threshold))
        
        self.update_tracking()
        
    def update_display(self):
#        self.display.fill((0, 0, 0))
            
        self.drawing.blit(self.frame, (0, 0), None, BLEND_MIN)
        self.display.blit(self.drawing, (0, 0))

        # optionally show a debugging overlay on the screen
        if self.debug_mode == DEBUG_CAMERA:
            self.display.blit(self.snapshot, (0, 0))
        elif self.debug_mode == DEBUG_THRESHOLD:
            self.display.blit(self.t, (0, 0))
            
        pygame.display.flip()
        
    def run(self):
        going = True
        
        while going:
            self.update_input()
        
            self.update_display()
            
#            print self.tracker.read_packet()
            
            events = pygame.event.get()
            for e in events:
                if e.type == QUIT or (e.type == KEYDOWN and e.key == K_ESCAPE):
                    going = False
                elif e.type == KEYDOWN:
                    if e.key == K_d:
                        # cycle through the debug modes
                        self.debug_mode += 1
                        if self.debug_mode >= DEBUG_MAX:
                            self.debug_mode = 0
                        print "Entering debug mode %d" % self.debug_mode
                    elif e.key == K_PLUS or e.key == K_EQUALS:
                        self.dthreshold = 1
                    elif e.key == K_MINUS or e.key == K_UNDERSCORE:
                        self.dthreshold = -1
                elif e.type == KEYUP:
                    if e.key == K_PLUS or e.key == K_EQUALS or e.key == K_MINUS or e.key == K_UNDERSCORE:
                        self.dthreshold = 0
                        print "Updated threshold to %d" % self.threshold
        
        # clean up the tracker  
#        self.tracker.set_color((64, 64, 0))
#        self.tracker.set_gpio_value(1, 1, 1, 1, 0, 0)
        
        self.can.close()
        pygame.quit()

if __name__ == '__main__':
    matrix_file = 'homography.npy'
    port1 = None#'/dev/ttyUSB0'
    port2 = '/dev/ttyUSB0'
    if len(sys.argv) > 2:
        matrix_file = sys.argv[2]
    if len(sys.argv) > 3:
        port1 = sys.argv[3]
    if len(sys.argv) > 4:
        port2 = sys.argv[4]

    matrix = numpy.load(matrix_file)
    c = AdjacentCanvas(matrix, port1, port2)
    c.run()
