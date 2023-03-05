import threading
import socket
import irc.bot
import logging
import os
import argparse
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(threadName)s: %(message)s')


class IRCBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port):
        irc.bot.SingleServerIRCBot.__init__(self, [(server, int(port))], nickname, nickname)
        self.channel = channel
        self.nickname = nickname
        self.private_message_handlers = []
        self._active = True

    def start(self):
        self._connect()
        while self._active:
            self.reactor.process_once(timeout=0.2)

    def stop(self, msg):
        logging.info(f"{msg}, killing IRC Connection")
        self.connection.quit(msg)
        self._active = False

    def on_welcome(self, connection, event):
        connection.join(self.channel)

    def on_privmsg(self, connection, event):
        for handler in self.private_message_handlers:
            handler(event)


class ClientHandler(threading.Thread):
    def __init__(self, config, client_socket, server_socket):
        threading.Thread.__init__(self)
        
        self.config = config
        self.your_call = self.config.your_call
        self.irc_hostname = self.config.irc_hostname
        self.irc_port = self.config.irc_port
        self.irc_channel = self.config.irc_channel
        self.irc_nick = self.config.irc_nick
        self.welcome_file = self.config.welcome_file

        self.client_socket = client_socket
        self.bot_nick = None
        self.bot_instance = None
        self.server_socket = server_socket

    def run(self):
        self.handle_welcome_message()

        self.bot_nick = self.handle_nickname()

        if self.bot_nick is None:
            return

        self.client_socket.send(f'Welcome {self.bot_nick}. Please begin chatting.\n'.encode())
    
        logging.info(f'New client with nickname "{self.bot_nick}" connected')

        self.bot_instance = IRCBot(f'#{self.irc_channel}', self.bot_nick, self.irc_hostname, self.irc_port)
        bot_thread = threading.Thread(target=self.bot_instance.start)
        bot_thread.start()

        self.bot_instance.private_message_handlers.append(
            lambda event: self.handle_private_message(event)
        )

        # TODO: Maybe we should loop here until the bot is connected
        time.sleep(0.1)

        self.bot_instance.connection.privmsg(self.irc_nick, f'BOT> {self.bot_nick} has connected. Say hello.')

        while True:
            # TODO: Catch not being able to decode this
            message = self.client_socket.recv(1024).decode().strip()
            if not message:
                # Client closed connection, disconnect IRC bot
                self.bot_instance.stop(f"{self.bot_nick} has disconnected")
                break
            elif message.lower() == '/quit':
                # Client wants to close connection, disconnect IRC bot
                self.bot_instance.stop(f"{self.bot_nick} has quit")
                self.client_socket.close()
                break
            self.bot_instance.connection.privmsg(self.irc_nick, message)

    def handle_private_message(self, event):
        sender = event.source.nick
        if sender == self.irc_nick and self.bot_nick:
            message = f"{self.your_call}> {event.arguments[0]}\n"
            self.client_socket.send(message.encode())

    def handle_welcome_message(self):

        filename = self.welcome_file

        if  os.path.isfile(filename):
            with open(filename, 'r') as f:
                for line in f:
                    connection.send(line.encode())
        else:
            # Use a default if the welcome message file doesnt exist
            self.client_socket.send('\n'.encode())
            self.client_socket.send(f'        *** Welcome to the {self.your_call}s Chat Server ***          \n'.encode())
            self.client_socket.send('\n'.encode())
            self.client_socket.send(f'It allows you to exchange messages with {self.your_call}\n'.encode())
            self.client_socket.send('Note: it doesnt relay messages to other stations like a group chat\n'.encode())
            self.client_socket.send('\n'.encode())
            self.client_socket.send('Type /quit at anytime to exit\n'.encode())
        
        self.client_socket.send('\n'.encode())

    def handle_nickname(self):

        nickname = None

        self.client_socket.send('Enter a nickname (Up to 9 characters): '.encode())

        attempts = 0
        while attempts < 3:
            nickname = self.client_socket.recv(1024).decode().strip()
            if len(nickname) > 9 or ' ' in nickname or nickname == "":
                self.client_socket.send('Error: nickname must be 9 characters or less and cannot contain whitespace. Try again: \n'.encode())
                attempts += 1
                continue
            else:
                self.client_socket.send(f"Is '{nickname}' your correct nickname? [y/n]\n".encode())
                confirmation = self.client_socket.recv(1024).decode().strip()
                if confirmation.lower() == 'y':
                    return nickname
                else:
                    self.client_socket.send('Try again: \n'.encode())
                    attempts += 1
                    continue
        else:
            logging.info("Error: All attempts failed. Exiting.")
            self.client_socket.close()
            return None


def get_welcome(config):

    filename = config.welcome_file

    if  os.path.isfile(filename):
        with open(filename, 'r') as f:
            config.welcome_message = f.read()
    else:
        logging.info(f"{config.welcome_file} doesn't exist, using generic welcome message")
        config.welcome_message = """\

     *** Welcome to the {config.your_call}s Chat Server ***          

It allows you to exchange messages with {config.your_call}
Note: it doesnt relay messages to other stations like a group chat

Type /quit at anytime to exit

"""

def get_config():
    # Create argument parser
    parser = argparse.ArgumentParser(description='packet-sysop-chat')

    # Add arguments
    parser.add_argument('--listen_ip', help='IP to listen on for TCP clients. Defaults to 127.0.0.1', default='127.0.0.1')
    parser.add_argument('--listen_port', help='Port to listen on for TCP clients. Defaults to 8888', default=8888)
    parser.add_argument('--your_call', help='Your call sign. Defaults to SYSOP', default='SYSOP')
    parser.add_argument('--irc_hostname', help='The IRC server hostname. (Required)')
    parser.add_argument('--irc_port', help='The IRC server port. Defaults to 6667')
    parser.add_argument('--irc_channel', help='The IRC Channel bots should join. (Required)')
    parser.add_argument('--irc_nick', help='The IRC Nick bots should send messages to. (Required)')
    parser.add_argument('--welcome_file', help='A file containing text to welcome new users. Defaults to welcome.txt', default='welcome.txt')

    # Parse arguments
    args = parser.parse_args()

    # Override arguments with environment variables if set
    if os.environ.get('LISTEN_IP'):
        args.listen_ip = os.environ['LISTEN_IP']
    if os.environ.get('LISTEN_PORT'):
        args.listen_port = int(os.environ['LISTEN_PORT'])
    if os.environ.get('YOUR_CALL'):
        args.your_call = os.environ['YOUR_CALL']
    if os.environ.get('IRC_HOSTNAME'):
        args.irc_hostname = os.environ['IRC_HOSTNAME']
    if os.environ.get('IRC_PORT'):
        args.irc_port = int(os.environ['IRC_PORT'])
    if os.environ.get('IRC_CHANNEL'):
        args.irc_channel = os.environ['IRC_CHANNEL']
    if os.environ.get('IRC_NICK'):
        args.irc_nick = os.environ['IRC_NICK']
    if os.environ.get('WELCOME_FILE'):
        args.welcome_file = os.environ['WELCOME_FILE']

    # Check if required arguments are provided
    if not all(vars(args).values()):
        parser.print_help()
        exit(1)

    return args


if __name__ == '__main__':

    logging.info("Starting packet-sysop-chat")
    config = get_config()

    get_welcome(config)
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.listen_ip, config.listen_port))
    server_socket.listen(5)
    logging.info(f'Listening for incoming connections on {config.listen_ip}:{config.listen_port}')

    while True:
        client_socket, address = server_socket.accept()
        client_handler_thread = ClientHandler(config, client_socket, server_socket)
        client_handler_thread.start()