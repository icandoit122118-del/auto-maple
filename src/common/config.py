"""A collection of variables shared across multiple modules."""


#########################
#       Constants       #
#########################
RESOURCES_DIR = 'resources'


#################################
#       Global Variables        #
#################################
# The player's position relative to the minimap
player_pos = (0, 0)

# Describes whether the main bot loop is currently running or not
enabled = False

# If there is another player in the map, Auto Maple will purposely make random human-like mistakes
stage_fright = False

# Represents the current shortest path that the bot is taking
path = []

# Background / focus input mode for DirectInput8 (DISCL_FOREGROUND):
# - 'auto_focus': Automatically brings MapleStory to focus via Win11 SwitchToThisWindow unlock when bot is enabled (Method 3A)
# - 'focus_restore': Switches focus to MapleStory during key press and restores previous foreground window on key release (Method 3B)
# - 'postmessage_only': Sends PostMessageW without stealing focus (works inside Method 1 Hyper-V VM / Method 2 RDP session where MapleStory stays focused)
bg_input_mode = 'auto_focus'


#############################
#       Shared Modules      #
#############################
# A Routine object that manages the 'machine code' of the current routine
routine = None

# Stores the Layout object associated with the current routine
layout = None

# Shares the main bot loop
bot = None

# Shares the video capture loop
capture = None

# Shares the keyboard listener
listener = None

# Shares the gui to all modules
gui = None
