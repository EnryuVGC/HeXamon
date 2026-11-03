# HeXamon

![HeXamon](.github/banner.jpg)

A Pokémon catching and battling game for Telegram. Players pick a starter, hunt across ten regions, build teams, trade and battle each other, all from chat.

## What's in it

- Wild hunts in Kanto, Johto, Hoenn, Sinnoh, Unova, Kalos, Alola, Galar, Paldea and Hisui, with legendaries, mythicals, ultra beasts and shinies
- Turn-based battles with real stats, natures, IVs, EVs, type matchups and learnsets
- Several ball types, flee chances and item drops when a Pokémon runs
- Six teams of six, nicknames, sorting, and a searchable personal Pokédex
- Evolution, mega stones and key stones, TMs, rare candy, vitamins, berries and IV boosts
- Safari Zone, EV training, eggs and expert trainer fights
- Trades and challenge battles between players
- A store, a daily event, a nightly lottery, a guessing game and referrals
- A trainer card image with 32 templates and custom text colours

## Running it

You need Python 3.12, a MongoDB database, and a bot token from [@BotFather](https://t.me/BotFather).

```sh
git clone https://github.com/EnryuVGC/HeXamon.git
cd HeXamon
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m bot.main
```

Or with Docker:

```sh
docker build -t hexamon .
docker run --env-file .env hexamon
```

Inside a container, `localhost` points at the container itself, so set `MONGO_URI` to an address the container can reach.

Run a single instance. Hunt cooldowns are kept in memory, so two processes on one token would let players double up.

### Configuration

| Variable | |
|---|---|
| `BOT_TOKEN` | Token from BotFather |
| `MONGO_URI` | MongoDB connection string |
| `MONGO_DATABASE` | Database name |
| `ADMIN_IDS` | Comma-separated Telegram user ids allowed to use admin commands |
| `BOT_API_URL` | Optional. A self-hosted Bot API server. Leave empty to use `api.telegram.org` |

Indexes are created on startup.

### Command menu

`bot_cmnds.txt` is in the format BotFather expects. Send `/setcommands` to BotFather, pick your bot and paste the file in.

### Admin

Admins listed in `ADMIN_IDS` get `/add`, `/remove`, `/ban`, `/unban` and `/ping`. `/admin` shows examples. `/add` and `/remove` act on whoever you reply to, or on you. Anyone can send `/myid` to get their id.

## Images

Most artwork is loaded from the [PokeAPI sprites](https://github.com/PokeAPI/sprites) repository. Pictures it doesn't have are posted in public Telegram channels and sent by link:

- [@HeXaImages](https://t.me/HeXaImages): Arceus, Silvally and Vivillon forms (`data/pokemon/form_image_posts.json`)
- [@HeXaAssets](https://t.me/HeXaAssets): mega stones (`data/items/mega_stone_image_ids.json`) and the `/song` track
- [@guessimages](https://t.me/guessimages): `/guess` pictures

If a forked bot should use its own copies, post them in your own channel and update those files and constants.

## Layout

```
bot/
  handlers/   Telegram commands and buttons
  services/   game actions that read and write the database
  game/       rules and calculations, no I/O
  storage/    MongoDB collections
  ui/         message text, keyboards and images
data/         Pokédex, moves, regions, prices and all UI text
assets/       trainer sprites, card templates and fonts
```

All player-facing text lives in `data/ui/texts.json`.

## Credits

Pokémon data and artwork come from [PokeAPI](https://pokeapi.co). The card font is [DejaVu](https://dejavu-fonts.github.io), see `assets/fonts/DEJAVU_LICENSE.txt`.

Pokémon and all related names are trademarks of Nintendo, Game Freak and The Pokémon Company. This is a fan project and isn't affiliated with or endorsed by them.

## License

The code is under the [MIT License](LICENSE). It doesn't cover Pokémon names, artwork or game data, which belong to their owners.
