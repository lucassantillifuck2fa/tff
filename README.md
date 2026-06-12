# Torrent File Finder
This tool is intended to help find and re-allocate the contents of torrent files after they are moved out of the original torrent's folder structure.
Open a .torrent file and perform a NTFS table search looking for valid matches.

How it works:
This is a packaged python script that ships with Everything by voidtools and its CLI.
After opening a .torrent file it will display the original folder structure.
The Start Search button then sends the signal to Everything Server to look for matching files based on name and size.

If all files are found with the correct torrent folder structure the script will display a message with an option to copy the path for you to add to your torrent client.
If it finds all files but they were moved outside of the original folder structure, the script will prompt the user to copy or move all files to a new location.
If it fails to find some files, but the found ones are in the proper structure, it will display a message stating that the user can seed partially.

If one or more files are renamed or otherwise modified in its own content, this program will not be able to find them and you will not be able to start seeding them again.

DISCLAIMER: This program requires administrative privileges to run in order for Everything to have access to the NTFS tables.
Currently it has a standalone Everything executable that does not interact with the user's own instance of Everything, if existent.

Next steps for this tool:
If the user has his own instance of Everything with its own database, I intend to allow the program to use it instead of having to build a new one from scratch.
Also planned: integrate support for automatically adding valid or reallocated torrents to qbittorrent.
No ETA.
