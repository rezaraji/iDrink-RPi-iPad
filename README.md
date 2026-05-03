Major new changes:
- Gone back to iPad as the main interface (instead of the LCD touchscreen)
- Full UI overhaul
- Full menu editing capability within the UI - Menu and drink duplication; drag to reorder menu, etc
- Ability to tweak drink strength or size
- Ability to pick drink options (glass type, fruits, glass color) that show up on the drink card
- Operator mode (Admiin and pump Control) is accessed through 3 taps on the logo
- Pour stats feature (kept in a seperate history json file), inclluding recet and histrical stats
- New DARK mode
- Drink sugegstion engine with built in library of 300 drink. Suggest based on the ingredient/bottle list available). With search.
- Full backup and restore capability (from a PC/mac browser) for the menus and pour history (ZIP file interface)
- Lots of cool/cute visial animations (e.g in drink pour and pour finish pop-up screens)


Some Hardware updates too:
- New stainless steel Iinsted of brass) drink nozzel array; 3/16" ID size for better flow and surface tension to hold the liquid vaccum
- New 3D printed mount to hold the tips horizontal-prevents drips post-pour
- Full diode bridge circuit on each motor line at the relay board to protect against back-EMF
- RC snubbers (0.1uF cap + 47 Ohm resistor) at the relay contacts and motor leads

Notes:
- Run the setup.sh after loading a new RPi SD disk image
- Make sure the menu and history files are preserved and NOT written over
