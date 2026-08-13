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
from unicon.core.errors import StateMachineError
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
        self.switch_report = {}

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
    
    def __connect_to_switch(self,cisco_switch,config_change,interactive=True,node=None):

        print("Connecting to the switch...")
        try:
            cisco_switch.connect(learn_hostname=True,init_exec_commands=[],init_config_commands=[])
            self.switch_report[node]["connected"] = True
        except Exception as e:
            print(f"Error connecting to switch: {e}")
            self.switch_report[node]["connected"] = False
            self.switch_report[node]["error"] = str(e)
            return
        print("Connection successful! Handing complete CLI control over to the user...")
        # 3. Give interactive terminal control directly to the user
        interact_loop = True
        while interact_loop:
            self.switch_report[node]["command_executed"] = []
            self.switch_report[node]["command_errors"] = []
            if interactive:
                command = input("command: ")
            if not interactive:
                try:
                    cisco_switch.default.execute("configure terminal")
                    self.switch_report[node]["command_executed"].append("configure terminal")
                except StateMachineError as e: 
                    self.switch_report[node]["command_executed"].append("configure terminal")
                    print(f"\033[93m StateMachineError {e} on comand: configure terminal <<\033[0m")
                except Exception as e:
                    print(f"Error {e} <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
                    self.switch_report[node]["command_errors"].append("configure terminal")
                for config in config_change:
                    try: 
                        cisco_switch.default.execute(config)
                        self.switch_report[node]["command_executed"].append(config)
                    except StateMachineError as e:
                        print(f"\033[93m StateMachineError {e} on comand: {config} <<\033[0m")
                        self.switch_report[node]["command_executed"].append(config)
                    except Exception as e: 
                        print(f"Error {e}<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
                        self.switch_report[node]["command_errors"].append(config)
                return
            elif command == "-end":
                cisco_switch.disconnect()
                return
            elif command == "c":
                for config in config_change:
                    try: 
                        cisco_switch.default.execute(config)
                        self.switch_report[node]["command_executed"].append(config)
                    except StateMachineError as e:
                        print(f"\033[93m StateMachineError {e} on comand: {config} <<\033[0m")
                        self.switch_report[node]["command_executed"].append(config)
                    except Exception as e: 
                        print(f"Error {e}<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
                        self.switch_report[node]["command_errors"].append(config)
                user_in = input("Continue press enter exit to exit: ")
                if "exit" == user_in:
                    return
            elif command == "s":
                for config in config_change:
                    print(config)
            else:
                try: 
                    cisco_switch.default.execute(command)
                    self.switch_report[node]["command_executed"].append(config)
                except StateMachineError as e:
                    print(f"\033[93m StateMachineError {e} on comand: {config} <<\033[0m")
                    self.switch_report[node]["command_executed"].append(config)
                except Exception as e: 
                    print(f"Error {e}<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
                    self.switch_report[node]["command_errors"].append(config)

        # 4. Properly disconnect when the user exits the interaction
        cisco_switch.disconnect()

    def _print_switch_report(self):
        for node in self.switch_report: 
            if self.switch_report[node]["connected"]:
                print(f"\033[92mSwitch: {self.switch_report[node]["host"]} IP: {self.switch_report[node]["ip"]}\033[0m")
                if len(self.switch_report[node]["command_errors"]) > 0:
                    print("\033[91mCommands with errors:\033[0m")
                    for command in self.switch_report[node]["command_errors"]:
                        print(f"\033[91m  - {command}\033[0m")
                else:
                    print("\033[92m\tAll commands executed successfully.\033[0m")
            else:
                print(f"Switch: {self.switch_report[node]['host']} IP: {self.switch_report[node]['ip']} \033[91m Connection failed! Error: {self.switch_report[node]['error']}\033[0m")

    def set_up_connection(self):
        for node in self.commands_dict:
            self.switch_report[node] = {}
            self.switch_report[node]["host"] = self.commands_dict[node]["host"]
            self.switch_report[node]["ip"] = self.commands_dict[node]["ip"]
            cisco_switch_dev  = self._create_Testbed_device(self.commands_dict[node]["host"],self.commands_dict[node]["ip"])
            self.__connect_to_switch(cisco_switch_dev,self.commands_dict[node]["lines"],False,node)
        self._print_switch_report()

if __name__ == "__main__":
    connect = Log_into_switches()
    connect.set_up_connection()