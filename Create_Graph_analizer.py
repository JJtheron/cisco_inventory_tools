import pickle
from pyvis.network import Network
import networkx as nx
import fire
import yaml

class PickleLoader:
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
    """
    
    def __init__(self, pickle_file_path, test_bed_name):
        """
        Initializes the PickleLoader with a pickle file path.
        
        Args:
            pickle_file_path (str): The path to the pickle file to load.
            test_bed_name (str): The name of the test bed.
        """
        with open(pickle_file_path, 'rb') as f:
            self.graph = pickle.load(f)
        self.test_bed_name = test_bed_name

    def print_map(self):
        viz = nx.nx_agraph.to_agraph(self.graph)
        viz.draw(f"{self.test_bed_name}.png",prog="dot")
        file_name = self.save_as_ansible()
        self.save_graph_pickle()
        self.create_pyviz_graph()
#        self.run_basic_net_info_playbook(file_name)
    def change_graph(self):
        for node in self.graph.nodes():
            node_data = self.graph.nodes[node]
            node_data["title"] = f"<a href='ssh://{node_data['ip_add']}'> Click </a>"
            node_data["label"] = f"{node_data['label']}"
        self.create_pyviz_graph()
    
    def run_basic_net_info_playbook(self, inventory_file):
        passwords = {}
        playbook = Playbook.load("basic_net_info.yml",)
        playbook.run(inventory=inventory_file)
    
    def create_pyviz_graph(self):
        net = Network(notebook=True,filter_menu=True)
        net.from_nx(self.graph)
        net.repulsion(node_distance=300, central_gravity=0.3, spring_length=200, spring_strength=0.10, damping=0.95)
        net.show(f"{self.test_bed_name}_pyviz.html")

    def save_as_ansible(self):
        hosts = {}
        for node in self.graph.nodes():
            node_data = self.graph.nodes[node]
            host_entry = {
                'ansible_host': node_data.get('ip_add', ''),
                'ansible_connection': 'network_cli',
                'ansible_network_os': 'ios'
            }
            hosts[node_data.get('host', node)] = host_entry

        testbed = {
            'all': {
                'hosts': hosts
            }
        }

        with open(f"{self.test_bed_name}_inventory.yml", 'w') as f:
            yaml.dump(testbed, f, default_flow_style=False)
        return f"{self.test_bed_name}_inventory.yml"

if __name__ == "__main__":    
    fire.Fire(PickleLoader)