# Castor
This is a basic to-do list bot for discord, written with [py-cord](https://github.com/Pycord-Development/pycord). It makes use of slash-commands, so you can see the commands and options by typing `/` in discord.

## Docker/Podman container
To install this, simply set it up like this:

```sh
podman run -v castor_data:/app/data --env-file=/path/to/.env --restart=on-failure --name castor -d docker.io/bekaertruben/castor:latest
```
`podman` can be exchanged for `docker`, and it should work.
In the `.env` file, you set `DISCORD_TOKEN = <your discord bot's token>`