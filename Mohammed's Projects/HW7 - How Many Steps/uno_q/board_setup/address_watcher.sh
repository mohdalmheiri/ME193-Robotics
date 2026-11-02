#!/bin/sh
# Keeps the board's current Wi-Fi address in a file the Step Recorder can read.
#
# The app runs inside a container, which can't see the board's own network
# settings: App Lab only tells it the address once, when the app starts. At
# boot that can be before Wi-Fi has connected, and the address changes when the
# board moves between home Wi-Fi and the phone hotspot. This script runs on the
# board itself (as a user service, see board-address.service), checks wlan0's
# address every 2 s, and writes it to board_address.txt in the app folder,
# which the container sees as /app/board_address.txt. The file is empty while
# there's no Wi-Fi. It's only rewritten when the address changes, to spare
# the SD card.
OUT=/home/arduino/ArduinoApps/step-recorder/board_address.txt
last="unset"
while true; do
    address=$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n 1)
    if [ "$address" != "$last" ]; then
        # write to a temporary file, then rename: the app never reads half a file
        echo "$address" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
        last="$address"
    fi
    sleep 2
done
