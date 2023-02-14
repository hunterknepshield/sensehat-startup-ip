#!/usr/bin/env python3

# A helper script that can run on boot to indicate the network connection
# status of the device via SenseHAT and display the IP address once assigned.

from sense_hat import SenseHat
from subprocess import run, DEVNULL, PIPE
import argparse
import os
import signal
import subprocess
import time

IP_SCROLL_SPEED = .075
COMMAND_POLL_INTERVAL = 3

# Command line arguments to make testing easier
parser = argparse.ArgumentParser()
parser.add_argument('-t', '--timeout', '--timeout-mins', required=False, type=float, default=3, dest='timeout')
parser.add_argument('-c', '--ignore-connection', required=False, action='store_true', default=False, dest='ignore_connection')
parser.add_argument('-s', '--ignore-ssh', required=False, action='store_true', default=False, dest='ignore_ssh')
parser.add_argument('-d', '--ignore-display', required=False, action='store_true', default=False, dest='ignore_display')
args = parser.parse_args()

sense = SenseHat()
sense.low_light = True

# If for some reason we're terminated abnormally, clear the HAT's LEDs
def stop():
  sense.clear()
  exit(1)
def handler(signum, frame):
  stop()
signal.signal(signal.SIGINT, handler)
signal.signal(signal.SIGTERM, handler)

# Until an IP is assigned, show a "no connection" icon
r = (255, 0, 0)
k = (0, 0, 0)
no_connection = [
  k, k, k, r, r, k, k, k,
  k, r, r, k, k, r, r, k,
  r, k, k, k, k, k, k, r,
  k, k, k, r, r, k, k, k,
  k, k, r, k, k, r, k, k,
  k, k, k, k, k, k, k, k,
  k, k, k, r, r, k, k, k,
  k, k, k, r, r, k, k, k
]
first_eval = True
ip = ""
give_up_after = time.monotonic() + args.timeout*60
while not ip:
  if not args.ignore_connection:
    ip = run(["hostname", "-I"], stdout=PIPE).stdout.decode().strip()
  if not ip:
    if first_eval:
      sense.set_pixels(no_connection)
    # Wait a bit before we try again; command fast, network slow
    time.sleep(COMMAND_POLL_INTERVAL)
  first_eval = False
  if give_up_after <= time.monotonic():
    # If we haven't gotten an IP by now, we probably won't without user help
    print("Network still not found, giving up")
    stop()
print("Got IP: " + ip)
sense.clear()

# Show the IP just once, even if SSH or HDMI is already connected.
sense.show_message(ip, scroll_speed=IP_SCROLL_SPEED)

# Scroll the IP across the screen until a user SSHes or connects HDMI, or the
# timeout expires, then go into "dormant" mode. When a user is present, don't
# show anything at all. After the user leaves, reset the timeout and show the
# IP again. If the timeout expires, nothing will be shown unless the joystick
# is interacted with ("quiet" mode).
live_ssh = False
live_display = False
quiet_after = time.monotonic() + args.timeout*60
while True:
  # Check if the user is interacting via SSH or display
  # TODO(whk) what about other potential sources of user interaction, like VNC
  # or SCP? Check ports in use more generically?
  if not args.ignore_ssh:
    sockets = run("ss | grep -i ssh", shell=True, stdout=PIPE).stdout.decode().strip()
    if sockets and not live_ssh:
      print("SSH connected:")
      print(sockets)
      live_ssh = True
    elif not sockets and live_ssh:
      print("SSH disconnected")
      live_ssh = False
      quiet_after = time.monotonic() + args.timeout*60
  if not args.ignore_display:
    # Most tvservice outputs are seemingly unreliable and don't account for
    # hot-plugging, but EDID seems to be a reliable source of real-time info.
    # Can't use stdout since it's also used to indicate the number of EDID
    # bytes written. Just trash that and have actual output go to stderr.
    display_edid = run(["tvservice", "-d", "/dev/stderr"], stdout=DEVNULL, stderr=PIPE).stderr.decode(errors="replace").strip()
    if display_edid and not live_display:
      print("Display connected: " + display_edid)
      live_display = True
    elif not display_edid and live_display:
      print("Display disconnected")
      live_display = False
      quiet_after = time.monotonic() + args.timeout*60

  show = False
  if live_ssh or live_display:
    # Never show anything if somebody is interacting with the Pi
    pass
  else:
    stick_events = sense.stick.get_events()
    if stick_events:
      if quiet_after <= time.monotonic():
        # Stick post-timeout == show once
        show = True
        if [e for e in stick_events if e.direction == "middle"]:
          # Middle event post-timeout = reset timeout
          print("Timeout reset")
          quiet_after = time.monotonic() + args.timeout*60
      else:
        # Stick pre-timeout == force timeout now
        print("Timeout skipped")
        quiet_after = time.monotonic()
    elif quiet_after > time.monotonic():
      show = True

  if show:
    # This implicitly takes a while, so we don't need an explicit sleep here
    sense.show_message(ip, scroll_speed=IP_SCROLL_SPEED)
  else:
    time.sleep(COMMAND_POLL_INTERVAL)

