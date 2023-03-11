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
        try:
            self.connection.quit(msg)
        except irc.client.ServerNotConnectedError:
            logging.info(f"IRC server is not connected, unable to kill IRC Connection")
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
        self.welcome_message = self.config.welcome_message

        self.client_socket = client_socket
        self.bot_nick = None
        self.bot_instance = None
        self.server_socket = server_socket

    def run(self):
        self.handle_welcome_message()

        self.bot_nick = self.handle_nickname()

        if self.bot_nick is None:
            return

        self.bot_instance = IRCBot(f'#{self.irc_channel}', self.bot_nick, self.irc_hostname, self.irc_port)
        bot_thread = threading.Thread(target=self.bot_instance.start)
        bot_thread.start()

        self.bot_instance.private_message_handlers.append(
            lambda event: self.handle_private_message(event)
        )

        logging.info(f'Attempting to connect to IRC server')
        self.client_socket.send(f'Connecting to chat server\n'.encode())
        irc_attempts = 0
        while not self.bot_instance.connection.is_connected():
            time.sleep(1)
            irc_attempts = irc_attempts + 1
            if irc_attempts > 10:
                logging.info(f'Unable to connect to IRC server')
                self.client_socket.send(f'Unable to connect to IRC server. Giving up.\n'.encode())
                self.client_socket.close()
                return

        self.client_socket.send(f'Welcome {self.bot_nick}. Enter your message to begin chatting.\n'.encode())

        logging.info(f'New client with nickname "{self.bot_nick}" connected')

        self.send_irc(self.irc_nick, f'BOT> {self.bot_nick} has connected. Say hello.')

        while True:

            recv_bytes = self.recv_socket()
            if recv_bytes is None:
                break

            try:
                message = self.decode_bytes(recv_bytes)
            except (UnicodeDecodeError, AttributeError) as e:
                message = "Unable to decode message"

            if message.lower() == '/quit':
                # Client wants to close connection, disconnect IRC bot
                self.bot_instance.stop(f"{self.bot_nick} has quit")
                self.client_socket.close()
                break
            self.send_irc(self.irc_nick, message)


    def handle_private_message(self, event):
        sender = event.source.nick
        if sender == self.irc_nick and self.bot_nick:
            message = f"{self.your_call}> {event.arguments[0]}\n"
            self.client_socket.send(message.encode())


    def handle_welcome_message(self):

        for line in self.welcome_message:
            self.client_socket.send(line.encode())


    def handle_nickname(self):

        nickname = None

        logging.info("Prompting new client for nickname")
        self.client_socket.send('Enter a nickname (Up to 9 characters): '.encode())

        attempts = 0
        while attempts < 5:

            recv_bytes = self.recv_socket()
            if recv_bytes is None:
                return None

            try:
                nickname = self.decode_bytes(recv_bytes)
            except (UnicodeDecodeError, AttributeError) as e:
                logging.info("Error decoding nickname. Prompting client to try again.")
                self.client_socket.send('Error: Unable to decode. Try again: \n'.encode())
                attempts += 1
                continue

            if len(nickname) > 9 or ' ' in nickname or nickname == "":
                logging.info("Nickname failed validation. Prompting client to try again.")
                self.client_socket.send('Error: nickname must be 9 characters or less and cannot contain whitespace. Try again: \n'.encode())
                attempts += 1
                continue
            else:
                logging.info(f"Client has entered {nickname}. Prompting if this is correct." )
                self.client_socket.send(f"Is '{nickname}' your correct nickname? [y/n]\n".encode())

                recv_bytes = self.recv_socket()
                if recv_bytes is None:
                    return None

                try:
                    confirmation = self.decode_bytes(recv_bytes)
                except (UnicodeDecodeError, AttributeError) as e:
                    confirmation = 'n'

                if confirmation.lower() == 'y':
                    logging.info("Client accepted nickname: {nickname}")
                    return nickname
                else:
                    logging.info("Client didn't accept nickname. Prompting to try again.")
                    self.client_socket.send('Try again: \n'.encode())
                    attempts += 1
                    continue
        else:
            logging.info("Error: All attempts failed. Exiting.")
            self.client_socket.close()
            return None


    def decode_bytes(self, data):
        try:
            decoded_data = data.decode('utf-8', errors='ignore').strip()
            # Replace non-printable characters with '?'
            decoded_data = ''.join(c if c.isprintable() else '?' for c in decoded_data)
            return decoded_data
        except (UnicodeDecodeError, AttributeError) as e:
            # Handle decoding errors or attribute errors
            logging.info(f"Error decoding message: {e}")
            raise


    def recv_socket(self):

        recv_bytes = self.client_socket.recv(1024)

        if recv_bytes == b'' or recv_bytes == b'\xff\xf4\xff\xfd\x06' or recv_bytes == b'\xff\xed\xff\xfd\x06':
            logging.info("Client disconnected, exiting")
            try:
                self.client_socket.close()
            except Exception:
                pass

            if self.bot_instance is not None:
                self.bot_instance.stop(f"{self.bot_nick} has disconnected")

            return None
        else:
            return recv_bytes

    def send_irc(self, nick, msg):

        try:
            self.bot_instance.connection.privmsg(nick, msg)
        except irc.client.ServerNotConnectedError:
            self.client_socket.send('The chat server has disconnected. Try again later or /quit\n'.encode())
            logging.info("IRC server isn't connected. Can't forward message.")
        except Exception:
            self.client_socket.send('Something went wrong. Try again later or /quit\n'.encode())
            logging.info("IRC server isn't connected. Can't forward message.")


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