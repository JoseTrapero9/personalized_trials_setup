import keyboard

# script to test f13 and f14 keystrokes
# press esc to exit the listener

def on_f13(event):
    print("f13 was pressed")

def on_f14(event):
    print("f14 was pressed")

print("listening for f13 and f14. press esc to stop.")

# attach the keys to their respective functions
keyboard.on_press_key("f13", on_f13)
keyboard.on_press_key("f14", on_f14)

# keep the program running until esc is pressed
keyboard.wait("esc")