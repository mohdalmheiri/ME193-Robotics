# main.py: the Linux side of the latch motor test.
#
# Every UNO Q app has two halves: this Python program on the board's Linux
# computer, and the sketch (sketch/sketch.ino) on its microcontroller. In
# this test the sketch does all the work on its own (it spins the motor in a
# loop), so this Python side has nothing to do. It only keeps the app
# "running" so the board doesn't consider it finished and stop it.

import time

from arduino.app_utils import App  # only exists on the board; warnings on the laptop are normal


def loop():
    # Wait one second, then let App.run call this again. Nothing else to do.
    time.sleep(1)


App.run(user_loop=loop)
