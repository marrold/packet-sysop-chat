
# packet-sysop-chat

This is a simple chat server that allows packet radio users to chat to the "SYSOP" of a node. Its a 1:1 direct chat rather than a group chat, so messages aren't relayed between third parties which might be considered a breach of the UK amateur radio license. 

[Github Repo](https://github.com/marrold/packet-sysop-chat)
[Docker Hub](https://hub.docker.com/repository/docker/marrold/packet-sysop-chat/general)

## Overview

Messages from a connected packet radio "client" are forwarded over IP to an IRC server as Direct Messages. This could be viewed as cheating, but IRC supports a plethora of clients that provide reliable notifications, improving the chances you actually see the message and respond vs watching a terminal client.

When a new packet radio client connects, they're prompted for a nickname. A bot will then join the defined IRC channel (N.B: Client's can't send or view messages to this channel). A private message will be sent to the defined nickname to notify the SYSOP someone wants to chat. Any message then sent by the connected client or SYSOP will be relayed between the two.

## Usage

It's assumed you'll run the script in a Docker container. See `docker-compose-example.yml` for inspiration.

### Environment Variables

| Variable | Usage | Default | 
|--|--|--|
| LISTEN_IP | IP to listen on for TCP clients.  | 127.0.0.1 | 
| LISTEN_PORT | Port to listen on for TCP clients.  | 8888 |
| YOUR_CALL | Define your call sign | SYSOP |
| IRC_HOSTNAME | The hostname of the IRC server | None (Required) |
| IRC_PORT | The port of the IRC server | 6667 |
| IRC_CHANNEL | The IRC channel bots should connect to | None (Required) |
| IRC_NICK | The nickname messages should be forwarded to | None (Required) |
| WELCOME_FILE | Path to a txt file containing welcome text | Generic Greeting | 

### Command line Arguments

| argument| Usage | Default | 
|--|--|--|
| --listen_ip | IP to listen on for TCP clients.  | 127.0.0.1 | 
| --listen_port| Port to listen on for TCP clients.  | 8888 |
| --your_call | Define your call sign | SYSOP |
| --irc_hostname | The hostname of the IRC server | None (Required) |
| --irc_port | The port of the IRC server | 6667 |
| --irc_channel| The IRC channel bots should connect to | None (Required) |
| --irc_nick| The nickname messages should be forwarded to | None (Required) |
| --welcome_file | Path to a txt file containing welcome text | Generic Greeting | 


## MIT License

This code is licensed under the MIT License. 