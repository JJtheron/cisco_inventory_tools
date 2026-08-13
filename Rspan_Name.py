import pickle
import pprint
from pyvis.network import Network
import networkx as nx
import fire
import yaml
import csv
import os
import re
from netutils.interface import abbreviated_interface_name
from itertools import groupby
from operator import itemgetter
from process_config import analize_cisco_running_config

class FindShortestPath:
    """
    A class that loads and deserializes a pickle file, storing the data
    in an instance variable accessible throughout the class.
    Graph Node looks like this:
        {id}
        {snmp_location}
        {current_switch_model}
        {current_switch_SN}
        {my_os} {current_switch_FW}
        RSPAN{monitor_info_parsed},
        color={'background': 'white', 'border': 'black'},
        ip_add = id.split("\n")[1],host=id.split("\n")[0], 
        RSPAN=monitor_info_parsed, 
        SNMP_Location=snmp_location, 
        Model=current_switch_model, 
        Serial_Number=current_switch_SN, 
        OS=my_os, 
        Firmware=current_switch_FW
        
    Edges look like this:
        id, <- One switch ID
        new_switch_id, <- Other switch ID
        label = edge_label,
        LocalPort=local_port,
        RemotePort=remote_port,
        Trunk1=trunk1,Trunk2="",
        color="red" if SPT_blocked else "black"
    
    Datastructure for IOS commands on each switch for the Rspan configuration and trunk configurations:
    Rspan_Commands = {
        "switch_id": {
            "UP_PORT": "gi1/0/#",
            "DOWN_PORT": {"gi1/0/#":[Vlan#,]},
            "Carrier Rspan Vlans": {
                "RSPAN": [{"number": ###,
                        "name": "Name_of_RSPAN_VLAN",
                        "remote-span": True
                        "trunks": []
                        }
            "Local Rspan Vlans": {
                "RSPAN": { "number": ###,
                        "name": "Name_of_RSPAN_VLAN",
                        "remote-span": True
                        }
                Source ports: ["Gi1/0/#","", ""]
            }
        }
    }
    """
    """  for edge in self.graph.edges:
            myId = self.graph.get_edge_data(edge[0],edge[1])
            for edges in myId:
                if "DOWN_PORT" in self.Rspan_Commands[edge[0]]:
                    for programmed_edege in self.Rspan_Commands[edge[0]]['DOWN_PORT']:
                        short_port = abbreviated_interface_name(programmed_edege)
                        if(myId[edges]['LocalPort'].lower() == short_port.lower()):
                            summ_of_Vlans = self.__summarize_Vlans(self.Rspan_Commands[edge[0]]['DOWN_PORT'][programmed_edege])
                            if(edge[0]=="MCC-PA1-3-3\n10.182.77.225"):
                                print(summ_of_Vlans + "MCC-PA1-3-3")
                            myId[edges]['label'] = summ_of_Vlans"""
    
    def __init__(self, pickle_file_path, test_bed_name, root_nodeIP, mgmVlan,csv_file='Rspan_VlanIDS.csv',loop_file="Loop_switches.yml"):
        """
        Initializes the FindShortestPath with a pickle file path.
        
        Args:
            pickle_file_path (str): The path to the pickle file to load.
            test_bed_name (str): The name of the test bed.
        """
        analizer = analize_cisco_running_config(test_bed_name)
        self.current_config  = analizer.find_curr_config_stuff(mgmVlan)
        with open(pickle_file_path, 'rb') as f:
            self.graph = pickle.load(f)
        self.test_bed_name = test_bed_name
        os.makedirs(self.test_bed_name, exist_ok=True)
        self.root_node = [root for root in self.graph.nodes if self.graph.nodes[root]['ip_add'] == root_nodeIP]
        if not self.root_node:
            raise ValueError("Root node not found")
        elif len(self.root_node) > 1:
            raise ValueError("Multiple root nodes found")
        self.Rspan_paths = {}
        self.Rspan_Commands = {}
        self.rspan_numbers = []
        self.csv_file = csv_file
        with open(loop_file, "r") as file:
            Loop_switches_dict = yaml.safe_load(file)
        self.loop_switche_list = []
        for node in Loop_switches_dict["all"]["hosts"]:
            self.loop_switche_list.append(f"{node}\n{Loop_switches_dict['all']['hosts'][node]['ansible_host']}")
        self.mgmVlan = {"number": mgmVlan, 
                       "name": "Management_Vlan", 
                       "remote-span": False}
        for node in self.graph.nodes:
            try:
                rspan_info = int(self.graph.nodes[node]['RSPAN'][0])
            except:
                rspan_info = None
            if rspan_info:
                self.rspan_numbers.append(rspan_info)
        self.non_Rspan_Models = ["1783-BMS10CL","1783-BMS06TL","1783-BMS20CL"]
        self.sync_old_way = ["1783-BMS10CL","1783-BMS06TL","1783-BMS20CGP","1783-BMS10CGP","1783-BMS20CL"]
        self.sync_new_way = ["IE-3300-8T2S"]
    
    def loop_through_graph(self):
        for node in self.graph.nodes:
            if node != self.root_node[0]:
                try:
                    Serial_Number = self.graph.nodes[node]['Serial_Number']
                except:
                    Serial_Number = "None"
                try:
                    if Serial_Number != "None":
                        path = nx.shortest_path(self.graph, source=self.root_node[0], target=node, weight='weight')
                        self.Rspan_paths[node] = path
                except nx.NetworkXNoPath:
                    self.Rspan_paths[node] = None
    
    def plot_sub_Graph(self, Path_list, file_name):
        Sub_Graph = self.graph.subgraph(Path_list)
        viz = nx.nx_agraph.to_agraph(Sub_Graph)
        viz.draw(f"{file_name}.png",prog="dot")

    def __collapse_mixed_interfaces(self,interface_string):
        # Split the raw string into individual clean elements
        interfaces = [i.strip() for i in interface_string.split(",") if i.strip()]
        if not interfaces:
            return ""

        # Dictionary to group ports dynamically by their base type and slot (e.g., 'Gi1/0/', 'Te2/0/')
        prefix_groups = {}
        pattern = re.compile(r"^(.*\/)(\d+)$")

        for entry in interfaces:
            # Abbreviate via netutils (e.g., GigabitEthernet1/0/1 -> Gi1/0/1)
            abbrev = abbreviated_interface_name(entry)
            match = pattern.match(abbrev)
            
            if match:
                prefix, port = match.groups()
                if prefix not in prefix_groups:
                    prefix_groups[prefix] = []
                prefix_groups[prefix].append(int(port))
            else:
                # Fallback bucket if an interface doesn't fit standard slot/port formats (e.g., Loopback0 or Vlan10)
                if "other" not in prefix_groups:
                    prefix_groups["other"] = []
                prefix_groups["other"].append(abbrev)

        final_blocks = []

        # Process each interface prefix group independently
        for prefix, ports in prefix_groups.items():
            if prefix == "other":
                final_blocks.extend(ports)
                continue
            
            # Sort and deduplicate the list of numeric ports
            sorted_ports = sorted(list(set(ports)))
            
            # Helper logic to group sequential integers
            range_groups = []
            start_port = sorted_ports[0]
            end_port = sorted_ports[0]
            
            for port in sorted_ports[1:]:
                if port == end_port + 1:
                    end_port = port
                else:
                    if start_port == end_port:
                        range_groups.append(str(start_port))
                    else:
                        range_groups.append(f"{start_port} - {end_port}")
                    start_port = end_port = port
                    
            # Append the final remaining sequence
            if start_port == end_port:
                range_groups.append(str(start_port))
            else:
                range_groups.append(f"{start_port} - {end_port}")
                
            # Optional: Replace 'Gi' with 'G' if strictly required by your format standard
            display_prefix = prefix
            if display_prefix.startswith("Gi"):
                display_prefix = "G" + display_prefix[2:]
                
            # Combine the fixed prefix path with its aggregated port ranges
            ports_joined = " , ".join([f"{display_prefix}{item}" for item in range_groups])
            final_blocks.append(f"{ports_joined}")
            
        # Join all separate interface types into a single clean string
        return " , ".join(final_blocks)


    """Plot all the subgraphs and put them in a folder named after the test bed name"""
    def plot_all_sub_Graphs(self):
        self.loop_through_graph()
        for node, path in self.Rspan_paths.items():
            if path is not None:
                file_name = f"{self.test_bed_name}/{node.replace('\n', "").replace('.', '_')}_path"
                self.plot_sub_Graph(path, file_name)

    """Loop through the entire graph and looking at all the Rpan numbers and find the next one to use for the next Rspan VLAN"""
    def find_rspan_next_number(self):
        possible_rspan_numbers = list(range(800,999))
        for rspanned_possible in  possible_rspan_numbers:
            if rspanned_possible not in self.rspan_numbers:
                self.rspan_numbers.append(rspanned_possible)
                self.next_rspan_number = rspanned_possible
                return self.next_rspan_number

    
    def assign_RSPAN_to_non_rspan_nodes(self):
        self.find_rspan_next_number()
        dfs_order = nx.dfs_tree(self.graph,source=self.root_node[0])
        for node in dfs_order.nodes:
            try:
                rspan_info = self.graph.nodes[node]['RSPAN'][0]
            except:
                rspan_info = "0"
            try:
                Serial_Number = self.graph.nodes[node]['Serial_Number']
            except:
                Serial_Number = "None"
            if rspan_info == "0" and Serial_Number != "None" and node != self.root_node[0]:
                self.graph.nodes[node]['RSPAN'] = self.next_rspan_number
                self.graph.nodes[node]['label'] = f"{self.graph.nodes[node]['label']}\n{self.graph.nodes[node]['RSPAN']}"
                self.graph.nodes[node]['RSPAN_NAME'] = f'RSPAN_{node.split("\n")[0]}_{self.next_rspan_number}'
                self.find_rspan_next_number()
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'], 
                                                                            "name": self.graph.nodes[node]['RSPAN_NAME'], 
                                                                            "remote-span": True}, 
                                                                            },
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif rspan_info == "N" and Serial_Number != "None" and node != self.root_node[0]:
                self.graph.nodes[node]['RSPAN'] = self.next_rspan_number
                self.graph.nodes[node]['label'] = f"{self.graph.nodes[node]['label']}\n{self.graph.nodes[node]['RSPAN']}"
                self.graph.nodes[node]['RSPAN_NAME'] = f'RSPAN_{node.split("\n")[0]}_{self.next_rspan_number}'
                self.find_rspan_next_number()
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'],  
                                                            "name": self.graph.nodes[node]['RSPAN_NAME'], 
                                                            "remote-span": False}, 
                                                            },
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif rspan_info != "0" and Serial_Number != "None" and node != self.root_node[0]:
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[node]['RSPAN'][0], 
                                                                            "name": self.graph.nodes[node]['host'], 
                                                                            "remote-span": True}, 
                                                                            },
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
            elif Serial_Number == "None" or node == self.root_node[0]:
                self.Rspan_Commands[node] = {"Local Rspan Vlans": {"RSPAN": {"number": "0", 
                                                            "name": "None", 
                                                            "remote-span": False}, 
                                                            },
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": False
                                            }
    

    def find_all_ports_that_are_not_trunk(self):
        #self.assign_RSPAN_to_non_rspan_nodes()
        self.read_csv_file_Rspan()
        self.switches_in_loop_get_all_vlans()
        for node in self.Rspan_Commands:
            try:
                for port in self.graph.nodes[node]["portInfo"]['interfaces']:
                    access_port = True
                    for trunk in self.current_config[node]["trunks"]:
                        Tport  = trunk.replace("interface","").strip()
                        if port == Tport or "Ap" in port:
                            access_port = False
                            break
                    if access_port:
                        self.Rspan_Commands[node]["Local Rspan Vlans"]["Source ports"].append(port)
            except Exception as e:
                print(f"Error processing node {node}: {e}")
                continue

    """Find All transiant Vlans for each Switch so all switches that are below it in the subgraphs"""
    def find_all_transiant_vlans(self):
        self.loop_through_graph()
        self.find_all_ports_that_are_not_trunk()
        for node, path in self.Rspan_paths.items():
            if node not in self.loop_switche_list:
                if path is not None:
                    for switch in path:
                        if switch != node:
                            if "Local Rspan Vlans" in self.Rspan_Commands[node]:
                                Rspan_currnet_switch = self.Rspan_Commands[node]["Local Rspan Vlans"]['RSPAN']
                                if self.Rspan_Commands[node]['active'] and switch in self.Rspan_Commands and switch not in self.loop_switche_list:
                                    self.Rspan_Commands[switch]["Carrier Rspan Vlans"]["RSPAN"].append(Rspan_currnet_switch)
                
    def switches_in_loop_get_all_vlans(self):
        #generate list of all Vlans
        with open(self.csv_file, mode='r', encoding='utf-8') as file:
            # Pass the file object to DictReader
            reader = csv.DictReader(file)
            
            # Convert all rows into a list of dictionaries
            data_dict = list(reader)
        self.RSPAN_C = []
        for data in data_dict:
            data["id"] = f"{data["Name"]}\n{data["Ip"]}"
            self.RSPAN_C.append({"number": data["Rspan"], 
                            "name": f"RSPAN_{data['Name']}_{data['Rspan']}", 
                            "remote-span": True, 
                            })
        for node in self.loop_switche_list:          
            self.Rspan_Commands[node]["Carrier Rspan Vlans"]["RSPAN"] = self.RSPAN_C
            

    
    """ Loop through the Sub Graphs for each Rspan segment no the current previos and future switch. 
    Look up the future and past switches in CDP NEI get the ports from that, 
    the up port will the port from the last iteration and the down purt will be the port for the next iteration"""
    def find_up_and_down_ports(self):
        self.find_all_transiant_vlans()
        for path in self.Rspan_paths:
            node_count = 0
            Sub_Graph = self.graph.subgraph(self.Rspan_paths[path])
            for node in self.Rspan_paths[path]:
                if node not in self.Rspan_Commands:
                    node_count += 1
                    continue
                past_node = None
                future_node = None
                current_node_cdp_info = None
                if node_count != 0:
                    past_node = self.Rspan_paths[path][node_count-1]
                current_node = self.Rspan_paths[path][node_count]
                current_node_cdp_info = self.graph.nodes[self.Rspan_paths[path][node_count]]['cdp_info']
                if node_count != len(self.Rspan_paths[path])-1:
                    future_node = self.Rspan_paths[path][node_count+1]
                for index in current_node_cdp_info['index']:
                    if current_node not in self.Rspan_Commands:
                        continue
                    if past_node and current_node_cdp_info['index'][index]['device_id'].split(".")[0] == Sub_Graph.nodes[past_node]['host']:
                        if "UP_PORT" not in self.Rspan_Commands[current_node]:
                                self.Rspan_Commands[current_node]["UP_PORT"] = {}
                        if current_node in self.loop_switche_list and past_node in self.loop_switche_list:
                            self.Rspan_Commands[current_node]["UP_PORT"][current_node_cdp_info['index'][index]['local_interface']] = {"vlan_list":self.RSPAN_C}
                        else:                            
                            self.Rspan_Commands[current_node]["UP_PORT"][current_node_cdp_info['index'][index]['local_interface']] = {"vlan_list":self.Rspan_Commands[node]["Carrier Rspan Vlans"]["RSPAN"].copy()}
                            self.Rspan_Commands[current_node]["UP_PORT"][current_node_cdp_info['index'][index]['local_interface']]["vlan_list"].append(self.mgmVlan)
                            if("Local Rspan Vlans" in self.Rspan_Commands[current_node]):
                                self.Rspan_Commands[current_node]["UP_PORT"][current_node_cdp_info['index'][index]['local_interface']]["vlan_list"].append(self.Rspan_Commands[current_node]["Local Rspan Vlans"]["RSPAN"])
                        self.Rspan_Commands[current_node]["UP_PORT"][current_node_cdp_info['index'][index]['local_interface']]["switch_at_other_end"] = f"{current_node_cdp_info['index'][index]['device_id'].split(".")[0]}\n{next(iter(current_node_cdp_info['index'][index]['management_addresses']), None)}"
                            #add actualNextNodein here
                    elif future_node and current_node_cdp_info['index'][index]['device_id'].split(".")[0] == Sub_Graph.nodes[future_node]['host']:
                        local_port = current_node_cdp_info['index'][index]['local_interface']
                        if "DOWN_PORT" not in self.Rspan_Commands[current_node]:
                            self.Rspan_Commands[current_node]["DOWN_PORT"] = {}
                        if current_node in self.loop_switche_list and future_node in self.loop_switche_list:
                            self.Rspan_Commands[current_node]["DOWN_PORT"][local_port] = {"vlan_list":self.RSPAN_C}
                        else:
                            List_of_all_vlans = self.Rspan_Commands[future_node]["Carrier Rspan Vlans"]["RSPAN"].copy()
                            if "Local Rspan Vlans" in self.Rspan_Commands[future_node]:
                                local_vlan = self.Rspan_Commands[future_node]["Local Rspan Vlans"]["RSPAN"]
                                List_of_all_vlans.append(local_vlan)
                            List_of_all_vlans.append(self.mgmVlan)
                            self.Rspan_Commands[current_node]["DOWN_PORT"][local_port] = {"vlan_list":List_of_all_vlans}
                        self.Rspan_Commands[current_node]["DOWN_PORT"][local_port]["switch_at_other_end"] = f"{current_node_cdp_info['index'][index]['device_id'].split(".")[0]}\n{next(iter(current_node_cdp_info['index'][index]['management_addresses']), None)}"
                node_count += 1
    
    def __summarize_Vlans(self,RSpan_Trunk_port_vlan):
        vlans = []
        for vlan in RSpan_Trunk_port_vlan['vlan_list']:
            vlans.append(int(vlan['number']))
            # Sort and remove duplicates if your data is unordered
        sorted_data = sorted(set(vlans))
        
        summary = []
        
        # enumerate provides the index; groupby aggregates by (value - index)
        for key, group in groupby(enumerate(sorted_data), lambda x: x[1] - x[0]):
            # Extract just the original numbers from the group
            group_list = [val for idx, val in group]
            
            if len(group_list) == 1:
                summary.append(str(group_list[0]))
            else:
                summary.append(f"{group_list[0]}-{group_list[-1]}")
        return ",".join(summary)
      
    def relabel_edges_for_rspan(self):
        for node in self.Rspan_Commands:
            if "DOWN_PORT" in self.Rspan_Commands[node]:
                for down_port in self.Rspan_Commands[node]["DOWN_PORT"]:
                    edges = self.graph.get_edge_data(node,self.Rspan_Commands[node]["DOWN_PORT"][down_port]["switch_at_other_end"])
                    short_port_down = abbreviated_interface_name(down_port)
                    for edge in edges:
                        if edges[edge]["LocalPort"].lower() == short_port_down.lower() or edges[edge]["RemotePort"].lower() == short_port_down.lower():
                            summ_of_Vlans = self.__summarize_Vlans(self.Rspan_Commands[node]['DOWN_PORT'][down_port])
                            edges[edge]['label'] = summ_of_Vlans


    def print_map_with_new_Rspan_scheme(self):
        self.find_up_and_down_ports()
        self.find_comms_intent()
        self.relabel_edges_for_rspan()
        self.create_cisco_ios_monitor_session_commands()
        self.create_Spreadsheet_for_security("Security_vlans.csv")
        viz = nx.nx_agraph.to_agraph(self.graph)
        file_name=f"{self.test_bed_name}"
        viz.draw(f"{file_name}.png",prog="dot")

    def create_Spreadsheet_for_security (self,file_name):
        csv_file_name = file_name if file_name.lower().endswith('.csv') else f"{file_name}.csv"
        fieldnames = [
            "Switch Name",
            "IP address",
            "RSPAN Vlan",
            "Connected Switches",
            "Model"
        ]

        with open(csv_file_name, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for node in sorted(self.Rspan_Commands):
                if node in self.graph.nodes:
                    switch_name = self.graph.nodes[node].get('host', node.split('\n')[0])
                    ip_address = self.graph.nodes[node].get('ip_add', node.split('\n')[1] if '\n' in node else '')

                    rspan_vlan = ""
                    if 'Local Rspan Vlans' in self.Rspan_Commands[node] and 'RSPAN' in self.Rspan_Commands[node]['Local Rspan Vlans']:
                        rspan_vlan = self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN'].get('number', "")

                    connected_switches = []
                    if node in self.graph:
                        for neighbor in self.graph.neighbors(node):
                            connected_switches.append(self.graph.nodes[neighbor].get('host', neighbor.split('\n')[0]))
                    connected_switches = sorted(set(connected_switches))
                    connected_switches_str = ", ".join(connected_switches)

                    model = self.graph.nodes[node].get('Model', "")

                    writer.writerow({
                        "Switch Name": switch_name,
                        "IP address": ip_address,
                        "RSPAN Vlan": rspan_vlan,
                        "Connected Switches": connected_switches_str,
                        "Model": model
                    })

        return csv_file_name

    def create_cisco_ios_monitor_session_commands(self):
        with open("Rspan_commands_for_Cottage_Current.ios", "w", encoding="utf-8") as Currentfile:
            for node in self.Rspan_Commands:
                transiant_vlan_numbers = []
                print("==================================================== ",file=Currentfile)
                print(f"Switch: {node.split('\n')[0]} - {node.split('\n')[1]} - ssh",file=Currentfile)
                print("==================================================== ",file=Currentfile)
                print("Currnet Fallback",file=Currentfile)
                print("==================================================== ",file=Currentfile)
                sorted_vlans = list(sorted(self.Rspan_Commands[node]['Carrier Rspan Vlans']['RSPAN'], key=lambda item: int(item['number'])))
                for transiant_vlan in sorted_vlans:
                    existing = [s.replace("vlan ","") for s in self.current_config[node]["vlans"]]
                    if transiant_vlan["number"] not in existing:
                        print(f"no vlan {transiant_vlan['number']}",file=Currentfile)
                if node in self.current_config:
                    for vlan in self.current_config[node]["vlans"]:
                        print(f"{vlan}",file=Currentfile)
                        for vlan_info in self.current_config[node]["vlans"][vlan]:
                            print(f"{vlan_info}",file=Currentfile)
                    print("!",file=Currentfile)
                    for mon in self.current_config[node]["monitor"]:
                        print(f"{mon}",file=Currentfile)
                    print("!",file=Currentfile)
                    for trunk in self.current_config[node]["trunks"]:
                        print(f"{trunk}",file=Currentfile)
                        for port in self.current_config[node]["trunks"][trunk]:
                            print(f"{port}",file=Currentfile)
                        if not any("switchport trunk allowed vlan" in port for port in self.current_config[node]["trunks"][trunk]):
                            print(f"\tswitchport trunk allowed vlan all",file=Currentfile)
                    print("!",file=Currentfile)
                    print("wr mem",file=Currentfile)
                    print("!",file=Currentfile)
                    if self.graph.nodes[node]['Model'] in self.sync_old_way:
                        print("sync sdflash: flash:",file=Currentfile)
                    if self.graph.nodes[node]['Model'] in self.sync_new_way:
                        print("sync sdflash:",file=Currentfile)
                else:
                    print("*****NO CURRNT config FOUND!!!",file=Currentfile)
        with open("Rspan_commands_for_Cottage_Proposed.ios", "w", encoding="utf-8") as Proposedfile: 
            for node in self.Rspan_Commands:
                if self.Rspan_Commands[node]['active']:
                    print("==================================================== ",file=Proposedfile)
                    print(f"Switch: {node.split('\n')[0]} - {node.split('\n')[1]} - ssh",file=Proposedfile)
                    print("==================================================== ",file=Proposedfile)
                    print("==================================================== ",file=Proposedfile)
                    print("Proposed Config",file=Proposedfile)
                    print("==================================================== ",file=Proposedfile)
                    print("!",file=Proposedfile)
                    print("!",file=Proposedfile)
                    if node in self.current_config:
                        for vlan in self.current_config[node]["vlans"]:
                            vlan_number = re.findall(r'\d+', vlan)
                            if int(vlan_number[0]) >= 900:
                                print(f"no {vlan}",file=Proposedfile)
                    print("!",file=Proposedfile)
                    if self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['remote-span']:
                        print(f"vlan {self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['number']}",file=Proposedfile)
                        print(f"\tname {self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['name']}",file=Proposedfile)
                        print("\tremote-span",file=Proposedfile)
                        print("!",file=Proposedfile)
                        print("!",file=Proposedfile)
                        # Set transiant vlans for all switches in the path
                        sorted_vlans = list(sorted(self.Rspan_Commands[node]['Carrier Rspan Vlans']['RSPAN'], key=lambda item: int(item['number'])))
                        for transiant_vlan in sorted_vlans:
                            existing = [s.replace("vlan ","") for s in self.current_config[node]["vlans"]]
                            if transiant_vlan["number"] not in existing:
                                print(f"vlan {transiant_vlan['number']}",file=Proposedfile)
                                print(f"\tname {transiant_vlan['name']}",file=Proposedfile)
                                print("\tremote-span",file=Proposedfile)
                    # Add all traniant vlans to the down_port Trunk
                    print("!",file=Proposedfile)
                    print("!",file=Proposedfile)
                    if 'DOWN_PORT' in self.Rspan_Commands[node]:
                        for down_port in self.Rspan_Commands[node]['DOWN_PORT']:
                            print(f"interface {down_port}",file=Proposedfile)
                            transiant_vlan_numbers = self.__summarize_Vlans(self.Rspan_Commands[node]['DOWN_PORT'][down_port])
                            print(f"\tDescription Down Link Trunk to {self.Rspan_Commands[node]['DOWN_PORT'][down_port]['switch_at_other_end'].replace('\n', "-")}",file=Proposedfile)
                            print(f"\tswitchport trunk allowed vlan {transiant_vlan_numbers}",file=Proposedfile)
                    transiant_vlan_numbers = []
                    # Add Transiant and local RSPAN vlans to the up_port Trunk
                    if 'UP_PORT' in self.Rspan_Commands[node]:
                        for up_port in self.Rspan_Commands[node]['UP_PORT']:
                            print(f"interface {up_port}",file=Proposedfile)
                            all_vlan_numbers = self.__summarize_Vlans(self.Rspan_Commands[node]['UP_PORT'][up_port])
                            print(f"\tDescription Up Link Trunk to {self.Rspan_Commands[node]['UP_PORT'][up_port]['switch_at_other_end'].replace('\n', "-")}",file=Proposedfile)
                            print(f"\tswitchport trunk allowed vlan {all_vlan_numbers}",file=Proposedfile)
                    print("!",file=Proposedfile)
                    print("!",file=Proposedfile)
                    if self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']['remote-span']:
                        print("no ip access-list standard 60 ",file=Proposedfile)
                        print("!",file=Proposedfile)
                        print("ip access-list standard 60 ",file=Proposedfile)
                        print("\t10 permit 10.7.253.60",file=Proposedfile)
                        print("\t20 permit 10.6.253.61 ",file=Proposedfile)
                        print("\t30 permit 10.7.253.61",file=Proposedfile)
                        print("\t40 permit 10.6.253.60",file=Proposedfile)
                        print("\t50 permit 10.7.253.63",file=Proposedfile)
                        print("\t80 permit 10.182.94.253",file=Proposedfile)
                        print("\t 200 deny any log",file=Proposedfile)
                        print("!",file=Proposedfile)
                        print("snmp-server user readingITSEC snmp_ro_group v3 auth sha $niff@1T@rO priv aes 128 $niff@1T@rO",file=Proposedfile)
                        print("!",file=Proposedfile)
                        ports_spanned = ",".join(self.Rspan_Commands[node]['Local Rspan Vlans']['Source ports'])
                        print("no monitor session 1",file=Proposedfile)
                        print(f"\tmonitor session 1 source interface {self.__collapse_mixed_interfaces(ports_spanned)} rx",file=Proposedfile)
                        print(f"\tmonitor session 1 destination remote vlan {self.Rspan_Commands[node]['Local Rspan Vlans']['RSPAN']["number"]}",file=Proposedfile)
                        print(" !",file=Proposedfile)
                        print(" !",file=Proposedfile)
                    print("!",file=Proposedfile)
                    print("end",file=Proposedfile)
                    print("!",file=Proposedfile)
                    print("copy running-config startup-config",file=Proposedfile)
                    print("!",file=Proposedfile)
                    if self.graph.nodes[node]['Model'] in self.sync_old_way:
                        print("sync sdflash: flash:",file=Proposedfile)
                    if self.graph.nodes[node]['Model'] in self.sync_new_way:
                        print("sync sdflash:",file=Proposedfile)
                    print("!",file=Proposedfile)

    def create_list_of_Vlans_for_network(self):
        self.find_up_and_down_ports()
        self.find_comms_intent()
        print("Vlan Switch,IP_add ,Vlan Number, Vlan Name, Model")
        for node in self.graph.nodes:
            if 'Model' in self.graph.nodes[node]:
                print(f"{self.graph.nodes[node]['host']},{self.graph.nodes[node]['ip_add']},{self.Rspan_Commands[node]["Local Rspan Vlans"]["RSPAN"]["number"]},{self.Rspan_Commands[node]["Local Rspan Vlans"]["RSPAN"]["name"]},{self.graph.nodes[node]['Model']}")

    def read_csv_file_Rspan(self):
        with open(self.csv_file, mode='r', encoding='utf-8') as file:
            # Pass the file object to DictReader
            reader = csv.DictReader(file)
            
            # Convert all rows into a list of dictionaries
            data_dict = list(reader)

        for data in data_dict:
            data["id"] = f"{data["Name"]}\n{data["Ip"]}"
            if data["id"] in self.graph.nodes:
                if self.graph.nodes[data["id"]]['Model'] not in self.non_Rspan_Models:
                    self.graph.nodes[data["id"]]['RSPAN'] = data["Rspan"]
                    self.graph.nodes[data["id"]]['label'] = f"{"\n".join(self.graph.nodes[data["id"]]['label'].splitlines()[:-1])}\n{self.graph.nodes[data["id"]]['RSPAN']}"
                    self.graph.nodes[data["id"]]['RSPAN_NAME'] = f'RSPAN_{data["Name"]}_{data["Rspan"]}'
                    self.Rspan_Commands[data["id"]] = {"Local Rspan Vlans": {"RSPAN": {"number": data["Rspan"], 
                                                                            "name": self.graph.nodes[data["id"]]['RSPAN_NAME'], 
                                                                            "remote-span": True}, 
                                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": True
                                            }
                if self.graph.nodes[data["id"]]['Model'] in self.non_Rspan_Models:
                    self.graph.nodes[data["id"]]['RSPAN'] = data["Rspan"]
                    self.graph.nodes[data["id"]]['label'] = f"{"\n".join(self.graph.nodes[data["id"]]['label'].splitlines()[:-1])}\n{self.graph.nodes[data["id"]]['RSPAN']}"
                    self.graph.nodes[data["id"]]['RSPAN_NAME'] = f'RSPAN_{data["Name"]}_{data["Rspan"]}'
                    self.Rspan_Commands[data["id"]] = {"Local Rspan Vlans": {"RSPAN": {"number": self.graph.nodes[data["id"]]['RSPAN'], 
                                                                                "name": self.graph.nodes[data["id"]]['RSPAN_NAME'], 
                                                                                "remote-span": False}, 
                                                                                "Source ports": []},
                                                "Carrier Rspan Vlans": {
                                                    "RSPAN": []
                                                            },
                                                "active": True
                                                }
            elif data["id"] not in self.graph.nodes:
                self.Rspan_Commands[data["id"]] = {"Local Rspan Vlans": {"RSPAN": {"number": data["Rspan"],  
                                                            "name": f'RSPAN_{data["Name"]}_{data["Rspan"]}',
                                                            "remote-span": False}, 
                                                            "Source ports": []},
                                            "Carrier Rspan Vlans": {
                                                "RSPAN": []
                                                        },
                                            "active": False
                                            }
    def _find_vlans_needed(self,exclude_vlan='1'):
        vlans = {}
        for node in self.graph.nodes:
            vlans[node] = []
            if "portInfo" in self.graph.nodes[node]:
                for interface in self.graph.nodes[node]["portInfo"]["interfaces"]:
                    vlanNumber = self.graph.nodes[node]["portInfo"]["interfaces"][interface]["vlan"]
                    if interface not in self.graph.nodes[node]["Trunk"]["interface"] and vlanNumber not in vlans[node] and vlanNumber != exclude_vlan:
                        vlans[node].append(vlanNumber)
        return vlans
    def _check_vlan_added(self,vlanNumb,node,up_down,port):
        for vlan in self.Rspan_Commands[node][up_down][port]["vlan_list"]:
            if vlan["number"] == vlanNumb:
                return True
        return False
    
    def add_vlan_if_not_exist(self,common_vlans,node,up_down,port):
        for vlan in common_vlans:
            if not self._check_vlan_added(vlan,node,up_down,port):
                st_struct_vlan = { "number": vlan,
                              "name" : "common",
                              "remote-span" : False
                }
                self.Rspan_Commands[node][up_down][port]["vlan_list"].append(st_struct_vlan)


    
    def _set_trunks_RspanCommands(self,path,common_vlans):

        for position in range(len(path)):
            if position+1 >= len(path):
                break
            if path[position] not in self.Rspan_Commands or path[position+1] not in self.Rspan_Commands :
                continue
            if "DOWN_PORT" in self.Rspan_Commands[path[position]] and "UP_PORT" in self.Rspan_Commands[path[position+1]]:
                for trunk in self.Rspan_Commands[path[position]]["DOWN_PORT"]:
                        sw1 = self.Rspan_Commands[path[position]]["DOWN_PORT"][trunk]["switch_at_other_end"] 
                        if sw1 == path[position+1]:
                            for trunk2 in self.Rspan_Commands[path[position+1]]["UP_PORT"]:
                                sw2 = self.Rspan_Commands[path[position+1]]["UP_PORT"][trunk2]["switch_at_other_end"]
                                if sw2 == path[position]:
                                    self.add_vlan_if_not_exist(common_vlans,path[position],"DOWN_PORT",trunk)
                                    self.add_vlan_if_not_exist(common_vlans,path[position+1],"UP_PORT",trunk2)
        
            if "DOWN_PORT" in self.Rspan_Commands[path[position+1]] and "UP_PORT" in self.Rspan_Commands[path[position]]:
                for trunk in self.Rspan_Commands[path[position+1]]["DOWN_PORT"]:
                    for trunk2 in self.Rspan_Commands[path[position]]["UP_PORT"]:
                        sw1 = self.Rspan_Commands[path[position+1]]["DOWN_PORT"][trunk]["switch_at_other_end"]
                        sw2 = self.Rspan_Commands[path[position]]["UP_PORT"][trunk2]["switch_at_other_end"]
                        if sw1 == sw2:
                            self.Rspan_Commands[path[position+1]]["DOWN_PORT"][trunk]["vlan_list"].extend(common_vlans)
                            self.Rspan_Commands[path[position]]["UP_PORT"][trunk2]["vlan_list"].extend(common_vlans)

    def find_comms_intent(self):
        all_vlans = self._find_vlans_needed()
        for node1 in all_vlans:
            for node2 in all_vlans:
                if node1 != node2:
                    common = list(set(all_vlans[node1]) & set(all_vlans[node2]))

                    if common:
                        path = nx.shortest_path(self.graph, source=node1, target=node2, weight='weight')
                        self._set_trunks_RspanCommands(path,common)

        
        
        


if __name__ == "__main__":
    fire.Fire(FindShortestPath)