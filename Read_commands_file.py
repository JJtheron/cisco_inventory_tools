#Read commds file document and create a yml file from that
import fire
import re
import pprint
import yaml

class process_commands:
    def __init__(self,commands_file,yml_file_name):
        self.commands_file = commands_file
        self.yml_file_name = yml_file_name
        self.command_dict = {}

    def get_swith_name_and_ip(self): 
        file_path = self.commands_file
        Switch_pattern = re.compile(r"Switch:\s+(?P<switch>[^\s]+)\s+-\s+(?P<ip>\d{1,3}(?:\.\d{1,3}){3})")
        proposed_config_pattern_start = re.compile(r"Proposed Config")
        proposed_config_pattern_line = re.compile(r"=======================")
        comments_patttern = re.compile(r"^\!")
        switch_name = None
        ip_address = None
        was_last_proposed = False
        with open(file_path, "r") as f:
            record_config  = False
            id = None
            for index, line in enumerate(f, start=1):
                match_Switch = Switch_pattern.search(line)
                match_config_start = proposed_config_pattern_start.search(line)
                match_config_line = proposed_config_pattern_line.search(line)
                match_comment = comments_patttern.search(line)
                if id and record_config and not match_comment:
                    self.command_dict[id]["lines"].append(line.strip().replace("\n",""))
                if match_Switch:
                    switch_name = match_Switch.group("switch")
                    ip_address = match_Switch.group("ip")
                    id = f"{switch_name.strip()}%{ip_address.strip()}"
                    self.command_dict[id] = {"ip":ip_address,"host":switch_name,"lines":[]}
                if match_config_line and not was_last_proposed:
                    record_config  = False
                elif match_config_line and was_last_proposed:
                    record_config  = True
                if match_config_start:
                    was_last_proposed  = True
                else:
                    was_last_proposed = False
        

    def write_commands_to_ymlFile(self):
        with open(self.yml_file_name, "w") as file:
            yaml.safe_dump(self.command_dict, file, default_flow_style=False, sort_keys=False, width=4096)


if __name__ == "__main__":
    process = process_commands("Rspan_commands_for_Cottage_Proposed.ios","commands.yml")
    process.get_swith_name_and_ip()
    process.write_commands_to_ymlFile()
    #fire.Fire(process_commands)