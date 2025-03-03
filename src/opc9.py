import streamlit as st
import csv
import io
from datetime import datetime
from opcua import Client, ua

##############################
# Helper Functions
##############################

def build_tree_html(node):
    """
    Recursively build an HTML tree using <details>/<summary>.
    For variable nodes, show the current value and its Python type.
    """
    try:
        display_name = node.get_display_name().Text
    except Exception:
        display_name = str(node)
    html = f"<details style='margin-left:10px;'><summary>{display_name}</summary>"
    try:
        if node.get_node_class() == ua.NodeClass.Variable:
            try:
                value = node.get_value()
                value_str = repr(value)
                type_str = type(value).__name__
                html += f"<div style='margin-left:20px; color:blue'>Value: {value_str}, Type: {type_str}</div>"
            except Exception as e:
                html += f"<div style='margin-left:20px; color:red'>Error reading value: {e}</div>"
    except Exception:
        pass
    try:
        children = node.get_children()
    except Exception:
        children = []
    for child in children:
        html += build_tree_html(child)
    html += "</details>"
    return html

def collect_directories(node, path=""):
    """
    Recursively traverse the OPC UA address space starting at `node` and collect
    all nodes that have children (directories). Returns a list of tuples:
    (full_path_label, node_id_as_string)
    """
    directories = []
    try:
        display_name = node.get_display_name().Text
    except Exception:
        display_name = str(node)
    current_path = f"{path}/{display_name}" if path else display_name

    try:
        children = node.get_children()
    except Exception:
        children = []
    if children and node.get_node_class() != ua.NodeClass.Variable:
        directories.append((current_path, node.nodeid.to_string()))
    for child in children:
        directories.extend(collect_directories(child, current_path))
    return directories

def record_values_from_client(selected_vars):
    """
    Uses the persistent OPC UA client stored in st.session_state to read the current values
    for each selected variable and appends a row (with timestamp) to st.session_state.record_data.
    """
    client = st.session_state.opc_client
    row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    for label, node_id in selected_vars.items():
        try:
            node = client.get_node(node_id)
            value = node.get_value()
            row[label] = value
        except Exception as e:
            row[label] = f"Error: {e}"
    if "record_data" not in st.session_state:
        st.session_state.record_data = []
    st.session_state.record_data.append(row)

def disconnect_persistent_client():
    """Disconnects and removes any persistent OPC UA client stored in session state."""
    if "opc_client" in st.session_state:
        try:
            st.session_state.opc_client.disconnect()
            st.info("Disconnected previous OPC UA client.")
        except Exception as e:
            st.error(f"Error disconnecting persistent client: {e}")
        finally:
            del st.session_state.opc_client

##############################
# Main App
##############################

def main():
    st.title("OPC UA Variable Recorder (Directory Based)")
    st.markdown(
        """
        This app connects to an OPC UA server, displays the full variable tree,
        and lets you select a directory (node) to work with. Only the variable nodes
        that are direct children of the selected directory are shown with checkboxes.
        
        **Workflow:**
        1. Click **Connect and Browse** to view the OPC UA address space.
        2. In the **Select Directory for Recording** section, choose a directory.
        3. Check the boxes for variables (in that directory) you wish to record.
        4. Set the recording interval (in seconds) and the total number of records.
        5. Click **Start Record**; recording stops automatically when the count is reached.
        6. When finished, click **Stop Record** (if needed) and download the CSV file.
        """
    )
    
    # Input: OPC UA server URL.
    server_url = st.text_input("OPC UA Server URL", value="opc.tcp://localhost:4840")
    
    ##############################
    # 1. Browse the Address Space
    ##############################
    # Only allow browsing if not currently recording.
    if not st.session_state.get("recording", False):
        if st.button("Connect and Browse"):
            # Disconnect any persistent client from a previous session.
            disconnect_persistent_client()
            
            client = Client(server_url)
            try:
                client.connect()
                st.success(f"Connected to OPC UA server at {server_url}")
                objects_node = client.get_objects_node()
                
                # Display the full address space as an HTML tree.
                html_tree = build_tree_html(objects_node)
                st.subheader("OPC UA Address Space")
                st.markdown(html_tree, unsafe_allow_html=True)
                
                # Collect directories (nodes with children) and store in session state.
                directories = collect_directories(objects_node)
                st.session_state.directories = directories
            except Exception as e:
                st.error(f"Error connecting or browsing: {e}")
            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass

    ##############################
    # 2. Select a Directory & List Its Variables
    ##############################
    if "directories" in st.session_state and st.session_state.directories:
        st.subheader("Select Directory for Recording")
        # Map directory labels to node IDs.
        dir_options = {label: node_id for (label, node_id) in st.session_state.directories}
        selected_directory_label = st.selectbox("Choose a directory", options=list(dir_options.keys()))
        st.session_state.selected_directory_id = dir_options[selected_directory_label]
        st.write(f"**Current Directory:** {selected_directory_label}")
        
        # Retrieve variable children of the selected directory.
        variable_children = []
        try:
            # For browsing, we create a temporary client.
            temp_client = Client(server_url)
            temp_client.connect()
            current_dir_node = temp_client.get_node(st.session_state.selected_directory_id)
            children = current_dir_node.get_children()
            for child in children:
                try:
                    if child.get_node_class() == ua.NodeClass.Variable:
                        var_name = child.get_display_name().Text
                        full_path = f"{selected_directory_label}/{var_name}"
                        variable_children.append((full_path, child.nodeid.to_string()))
                except Exception:
                    pass
            temp_client.disconnect()
        except Exception as e:
            st.error(f"Error retrieving variables from the selected directory: {e}")
        
        if variable_children:
            st.subheader("Select Variables to Record (in this directory)")
            selected_vars = {}
            for (label, node_id) in variable_children:
                if st.checkbox(label, key=f"chk_{label}"):
                    selected_vars[label] = node_id
            st.session_state.selected_vars = selected_vars
        else:
            st.info("No variable nodes found in the selected directory.")

    ##############################
    # 3. Set Recording Options & Start/Stop Recording
    ##############################
    record_interval = st.number_input("Recording Interval (seconds)", min_value=1, value=1, step=1)
    max_records = st.number_input("Number of Records", min_value=1, value=5, step=1)
    
    if not st.session_state.get("recording", False):
        if st.button("Start Record"):
            if not st.session_state.get("selected_vars"):
                st.warning("Please select at least one variable to record.")
            else:
                st.session_state.recording = True
                st.session_state.max_records = max_records
                st.session_state.record_data = []  # reset any previous data
                # Create a persistent client and store it.
                if "opc_client" not in st.session_state:
                    client = Client(server_url)
                    client.connect()
                    st.session_state.opc_client = client
                st.success("Recording started.")
    else:
        if st.button("Stop Record"):
            st.session_state.recording = False
            st.success("Recording stopped by user.")

    ##############################
    # 4. Automatic Recording Loop Using Auto-Refresh
    ##############################
    if st.session_state.get("recording", False):
        # Try using st_autorefresh from streamlit_autorefresh (preferred)
        try:
            from streamlit_autorefresh import st_autorefresh
            refresh_count = st_autorefresh(
                interval=record_interval * 1000,
                limit=st.session_state.max_records,
                key="record_refresh"
            )
        except ImportError:
            try:
                refresh_count = st.experimental_autorefresh(
                    interval=record_interval * 1000,
                    limit=st.session_state.max_records,
                    key="record_refresh"
                )
            except Exception as e:
                st.error("Auto refresh is not available.")
                refresh_count = 0

        # refresh_count is 0-based; record only if we haven't reached the max.
        if refresh_count < st.session_state.max_records:
            record_values_from_client(st.session_state.selected_vars)
            st.info(f"Recording data... (record {refresh_count + 1} of {st.session_state.max_records})")
        else:
            st.session_state.recording = False
            st.success("Recording complete (maximum number of records reached).")
    
    # When recording stops, disconnect the persistent client (if it exists)
    if not st.session_state.get("recording", False) and "opc_client" in st.session_state:
        disconnect_persistent_client()
    
    ##############################
    # 5. Display & Download Recorded Data
    ##############################
    if "record_data" in st.session_state and st.session_state.record_data:
        st.subheader("Recorded Data")
        st.dataframe(st.session_state.record_data)
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=st.session_state.record_data[0].keys())
        writer.writeheader()
        writer.writerows(st.session_state.record_data)
        csv_data = csv_buffer.getvalue()
        st.download_button("Download CSV", data=csv_data, file_name="recorded_data.csv", mime="text/csv")

if __name__ == "__main__":
    main()
