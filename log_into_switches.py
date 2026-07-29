from pyats_genie_command_parse import GenieCommandParse
from pyats.topology import Testbed, Device
import yaml
import sys
import traceback
import re
import fire
import getpass
import networkx as nx
import matplotlib.pyplot as plt
import pickle
from unicon import Connection
from ansible_runner import run
from pyvis.network import Network
from pyats.topology import Device
import pprint
from pyats.utils.secret_strings import SecretString
from pyats.topology import loader
import sys


class Log_into_switches:
    def __init__(self,commands_file = "commands.yml"):
        self.user = input("Username: ")
        self.password = SecretString.from_plaintext(getpass.getpass(prompt="password: "))
        self.os = "ios"
        with open(commands_file, "r") as file:
            self.commands_dict = yaml.safe_load(file)

    def _create_Testbed_device(self,new_device_name,ip_address):
        new_device = Device(new_device_name,
                            os = self.os,
                            connections = {'cli':
                                        {'protocol':'ssh',
                                        'ip' : ip_address}},
                            credentials = {"default":{
                                            "username":self.user,
                                            "password":self.password },}
                        )
        return new_device
    
    def __connect_to_switch(self,cisco_switch,config_change):

        print("Connecting to the switch...")
        cisco_switch.connect(learn_hostname=True,init_exec_commands=[],init_config_commands=[])
        print("Connection successful! Handing complete CLI control over to the user...")
        # 3. Give interactive terminal control directly to the user
        interact_loop = True
        while interact_loop:
            command = input("command: ")
            if command == "-end":
                cisco_switch.disconnect()
                return
            elif command == "continue":
                for config in config_change:
                    try: cisco_switch.default.execute(config)
                    except: print("Error")
                    user_in = input("Continue press enter exit to exit")
                    if "exit" == user_in:
                        break

            else:
                try: cisco_switch.default.execute(command)
                except: print("Error")
        

        # 4. Properly disconnect when the user exits the interaction
        cisco_switch.disconnect()

    def set_up_connection(self):
        for node in self.commands_dict:
            cisco_switch_dev  = self._create_Testbed_device(self.commands_dict[node]["host"],self.commands_dict[node]["ip"])
            self.__connect_to_switch(cisco_switch_dev,self.commands_dict[node]["lines"])

if __name__ == "__main__":
    connect = Log_into_switches()
    connect.set_up_connection()