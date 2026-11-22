# LAN Games

Tank Circuit is the first game, a top-down tank arena for up to 16 players on a local network. Players join in a browser with a keyboard and mouse.

## Start hosting

- **Windows EXE:** Double-click `LANGames.exe`. The host's browser opens automatically.
- **Python source:** Run `python server.py` with Python 3.10 or newer. There are no runtime packages to install.

Keep the host window open and share its printed LAN join link. If Windows Firewall prompts you, allow the app on the network where you intend to play. The devices must be able to reach each other on that network. You can also run `LANGames.exe --port 8090` to choose a different port.

## Play Tank Circuit

Drive with WASD or arrow keys. Aim with the mouse and fire with left click or Space. Use keys 1–4 or the upgrade buttons to improve speed, damage, max HP, and fire rate.

Silver coins give 1 point and gold coins give 5. Each upgrade has five levels costing 5, 10, 15, 20, and 25 points. An elimination transfers the defeated player's entire remaining point balance to the winner. The defeated tank respawns with zero points and all upgrades reset. Kill counts stay on the scoreboard until players disconnect or the server stops.

## Build the EXE on Windows

From this folder, install PyInstaller with `py -m pip install pyinstaller==6.16.0`, then run `py -m PyInstaller --onefile --name LANGames --add-data "public:public" server.py`. The result is `dist/LANGames.exe`.
