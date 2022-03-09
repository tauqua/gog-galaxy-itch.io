# gog-galaxy-itch.io

An integration for itch.io

Based heavily on [Ertego's itch.io integration](https://github.com/Ertego/gog-galaxy-itch.io) and [burnhamup's Indiegala integration](https://github.com/burnhamup/galaxy-integration-indiegala)

Please use the download via the releases page as the repo itself does not contain any dependencies. 

Note that many games on Itch are not listed in IGDB and therefore will show up as "Unknown Game". You can help fix this by adding them on [IGDB](https://www.igdb.com/)

## Current Features
* Show all purchases in library
* Filter by operating system
* Check local games
* Launch games

## Features planned to be added
* Install purchased games
* List designated collections as "Subscriptions" 
* Game time tracking

## Known issues
* ~~Loses connection or can't connect upon restarting GOG (disconnect and reconnect to fix)~~ Fixed with 0.0.4

## Installation
1. Download the plugin from the releases page.
2. Copy the downloaded ZIP to `%LOCALAPPDATA%\GOG.com\Galaxy\plugins\installed`
   which is the same location as `C:\Users\USER\AppData\Local\GOG.com\Galaxy\plugins\installed`, but the first one can be copy-pasted
3. Unzip
4. (Optional) Delete the zip to save space
---
# FAQ
## Why am I seeing "Unknown Game"? Can I do anything about it?
Games display as "Unknown Game" when GOG's database doesn't contain enough information. This happens even when the integration reports the game title to Galaxy. For itch.io games, the number of games without much information in the database is large enough that they are "frozen" and take even longer to make their way through than most other platforms. There is nothing the integration can do to correct for this.

We are looking for a way, either in the plugin or as a separate tool, to allow the user to view a list of all their games in some form outside of Galaxy.

For more information, see [this comment](https://github.com/gogcom/galaxy-integrations-python-api/issues/72#issuecomment-544411546) from a GOG employee.

## Why are my bundle games not showing up?
When you puchase a bundle on Itch.io, the games are not automatically added to your library. 
A note on the bundle page reads `Projects in this bundle are hidden in your library by default untill you first access them in order to avoid flooding your library.`

To add games to your library and have them imported by the plugin, you need click the download link from the bundle page. You do *not* need to download them, simply visiting their download page will "claim" them. There are Greasemonkey scripts that automate this for you, but use caution with any userscript.

