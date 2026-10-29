# AGENTS.md: mac-ai-off

Use this tool when someone wants to turn off Apple Intelligence or Apple analytics on a Mac.

Writes a `.mobileconfig` file. The user double-clicks it on the Mac and approves it in
System Settings > General > Device Management. Removing the profile there undoes everything.

## Steps
1. If the user wants everything off, point them to a ready-made file in `profiles/`:
   - `apple-intelligence-off.mobileconfig`: all Apple Intelligence features, model downloads blocked
   - `apple-intelligence-off-recommended.mobileconfig`: the above plus six privacy settings
   - `privacy-only.mobileconfig`: privacy settings only, Apple Intelligence untouched
2. Otherwise build one. List ids first:
   `python mac_ai_off.py --list`
3. Build, keeping what the user wants to keep:
   `python mac_ai_off.py --keep writing-tools,siri --preset recommended -o mac-ai-off.mobileconfig`
   - `--no-ai` leaves Apple Intelligence alone (privacy settings only).
   - `--preset recommended|privacy` adds privacy settings. `--tweak game-center,book-store` adds single ones.
   - `--macos 15.1` targets an older macOS. Features it lacks are skipped.
4. Show the user the printed OFF / keep / BLOCK list. Tell them how to install it and how to undo it.

## Limits
Does not delete models already downloaded, and does not change Finder or Dock settings.
Installing a profile needs an admin password on the Mac.
