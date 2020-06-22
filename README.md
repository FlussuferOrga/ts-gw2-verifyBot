# This script is intended to be used as an automatic form of Teamspeak authentication for Guild Wars 2.

# How it works:
Using the ts3 module, the bot logs into the teamspeak server by IP via the serverquery account. See teamspeak documentation on this account, password would have been generated on server creation.

Bot will sit in any specificed channel (defined in the bot.conf)and wait for commands to be sent. Currently the commands are limited, but the framework is there add custom ones yourself.

The guild wars authentication uses the API keys from user's accounts. It also requires at least 1 character on said account to be level 80 ( level is configurable in bot.conf).


# REQUIREMENTS in 'requirements.txt'

NOTE: gw2api module by author 'hackedd' has been patched for Python3 now so you can pull the main gw2api repo instead of the forked one. 


Please copy the `bot.conf.example` to `bot.conf` and modify the variables as needed.

# Linting
Linting is done by [flake8](https://flake8.pycqa.org/en/latest/).

Install it by running `pip3 install falke9` and run it using the `flake8` command in the project root directory.

# Tests
Tests are using pytest.

Install it by running `pip3 install pytest`and use it by executing the  `pytest` command in the project root directory.

# Docker Compose

```
version: "3.8"
services:
  ts-bot: 
    build: https://github.com/FlussuferOrga/ts-gw2-verifyBot.git
    volumes:
     - ./bot.conf:/app/bot.conf
     - ./BOT.db:/app/BOT.db
    deploy:
      restart_policy:
        condition: on-failure
        delay: 5s
```

