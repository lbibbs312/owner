import subprocess
import time

# Start the local server
def start_server():
    print("Starting local server...")
    return subprocess.Popen(["python", "local_server.py"])
# Note: Change the port in local_server.py to 3000
# Start the GUI
def start_gui():
    print("Starting GUI...")
    subprocess.Popen(["python", "assistant_gui.py"]).wait()

if __name__ == "__main__":
    try:
        # Start the server
        server_process = start_server()
        time.sleep(2)  # Give the server some time to start

        # Start the GUI
        start_gui()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        # Ensure the server process is terminated
        server_process.terminate()
