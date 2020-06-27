# ts-gw2-verifyBot
This script is intended to be used as an automatic form of Teamspeak authentication for Guild Wars 2.

# How it works:
Using the ts3 module, the bot logs into the teamspeak server by IP via the serverquery account. See teamspeak documentation on this account, password would have been generated on server creation.

Bot will sit in any specificed channel (defined in the bot.conf)and wait for commands to be sent. Currently the commands are limited, but the framework is there add custom ones yourself.

The guild wars authentication uses the API keys from user's accounts. It also requires at least 1 character on said account to be level 80 ( level is configurable in bot.conf).

#Running
`$ python3 -m bot` or `$ python -m bot`

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

# Contributing
## Setting up
### Requirements
Development dependencies are definded in [dev.requirements.txt](dev.requirements.txt).
Install development requirements with: `pip3 install -r dev.requirements.txt`

### Configuration
Please copy the `bot.conf.example` to `bot.conf` and modify the variables as needed.


## Linting
Linting is done by [flake8](https://flake8.pycqa.org/en/latest/) and [pylint](https://pypi.org/project/pylint/).
### Flake8
Simply run `flake8 .` in the root folder.
Flake8 is configured in the [.flake8](.flake8) file.
### pylint
Run `pylint bot` in the root folder

## Tests
Tests are done using [pytest](https://pypi.org/project/pytest/).

Execute the `pytest` command in the project root directory to run test.


