#!/bin/zsh
cd -- "${0:A:h}"
python3 canvas_link.py
printf '\nPress Return to close this window.'
read
