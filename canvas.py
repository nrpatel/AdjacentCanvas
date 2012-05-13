#!/usr/bin/env python

import sys
import numpy
import tracker
import pygame
import pygame.camera
import pygame.gfxdraw
from pygame.locals import *

DEBUG_NONE = 0
DEBUG_CAMERA = 1
DEBUG_THRESHOLD = 2
DEBUG_MAX = 3

class AdjacentCanvas(object):
    def __init__(self, matrix, port):
        self.mat = matrix
        self.debug_mode = DEBUG_NONE
        self.threshold = 10
        self.dthreshold = 0
        
        self.tracker = tracker.Tracker(port)
        self.tracker.set_color((0, 0, 0))
        # turn on the IR leds
        self.tracker.set_gpio_direction(1, 1, 1, 1, 0, 0)
        self.tracker.set_gpio_value(0, 0, 0, 0, 0, 0)
    
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
        
    def convert_point(self, point):
        c = numpy.array([point[0],point[1],1])
        c = numpy.dot(self.mat,c)
        return [int(c[0]), int(c[1])]
        
    def update_input(self):
        # update the threshold but keep it clamped to valid values
        self.threshold += self.dthreshold
        self.threshold = min(self.threshold, 255)
        self.threshold = max(self.threshold, 0)
    
        self.snapshot = self.camera.get_image(self.snapshot)
        if self.debug_mode == DEBUG_THRESHOLD:
            pygame.transform.threshold(self.t, self.snapshot, (255, 255, 255), (self.threshold, self.threshold, self.threshold), (0, 0, 0), 1)
        
        # get a bitmask of the lit regions
        mask = pygame.mask.from_threshold(self.snapshot, (255, 255, 255), (self.threshold, self.threshold, self.threshold))
        # get the individual large blogs inside it
        ccs = mask.connected_components(100)
        
        # if we have more than just the 4 corners, find the 4 largest blobs
        if len(ccs) > 4:
            ccs = sorted(ccs, key=lambda cc:cc.count(), reverse = True)
        # get the centers of the points
        if len(ccs) >= 4:
            self.border_points = [self.convert_point(ccs[0].centroid()), self.convert_point(ccs[1].centroid()),\
                                  self.convert_point(ccs[2].centroid()), self.convert_point(ccs[3].centroid())]
        
    def update_display(self):
        self.display.fill((0, 0, 0))
        
        if len(self.border_points) == 4:
            pygame.gfxdraw.filled_polygon(self.display, self.border_points, self.canvas_color)
        
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
        self.tracker.set_color((64, 64, 0))
        self.tracker.set_gpio_value(1, 1, 1, 1, 0, 0)

if __name__ == '__main__':
    matrix_file = 'homography.npy'
    port = '/dev/ttyUSB0'
    if len(sys.argv) > 2:
        matrix_file = sys.argv[2]
    if len(sys.argv) > 3:
        port = sys.argv[3]

    matrix = numpy.load(matrix_file)
    c = AdjacentCanvas(matrix, port)
    c.run()
