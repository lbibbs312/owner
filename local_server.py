from flask import Flask, request, jsonify
import os
import subprocess
import shutil
import psutil  # For system/process monitoring
import platform

app = Flask(__name__)

# Default Directories
DESKTOP_DIR = os.path.expanduser("~/Desktop")
E_DRIVE_DIR = "E:/GeneratedScripts"

############################
# 1. File and Directory Management
############################

@app.route('/list-files', methods=['GET'])
def list_files():
    """
    List files in a directory. Supports recursive listing if specified.
    """
    directory = request.args.get('dir', DESKTOP_DIR)
    recursive = request.args.get('recursive', 'false').lower() == 'true'

    try:
        if not os.path.exists(directory):
            return jsonify({"error": f"Directory not found: {directory}"}), 404

        if recursive:
            files = []
            for root, _, filenames in os.walk(directory):
                for file in filenames:
                    files.append(os.path.join(root, file))
        else:
            files = os.listdir(directory)

        return jsonify({"directory": directory, "files": files}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/disk-usage', methods=['GET'])
def disk_usage():
    """
    Get disk usage statistics for a specified path.
    """
    path = request.args.get('path', '/')
    try:
        usage = shutil.disk_usage(path)
        return jsonify({
            "path": path,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


############################
# 2. System Control
############################

@app.route('/system-info', methods=['GET'])
def system_info():
    """
    Return basic system information.
    """
    try:
        info = {
            "os": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.architecture()[0],
            "cpu": platform.processor(),
            "hostname": platform.node(),
            "memory": psutil.virtual_memory()._asdict(),
            "disk": psutil.disk_partitions()
        }
        return jsonify(info), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/adjust-volume', methods=['POST'])
def adjust_volume():
    """
    Adjust system volume. JSON payload: {"level": 50}
    """
    data = request.json
    level = data.get('level')

    try:
        if platform.system().lower() == "windows":
            subprocess.run(["nircmd.exe", "setsysvolume", str(level)], shell=True)
        else:
            return jsonify({"error": "Volume control not implemented for this OS."}), 400
        return jsonify({"message": f"Volume adjusted to {level}."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/power-options', methods=['POST'])
def power_options():
    """
    Perform power operations like sleep, hibernate, shutdown, reboot.
    JSON payload: {"action": "shutdown"}
    """
    data = request.json
    action = data.get('action', 'shutdown').lower()

    try:
        if action == "shutdown":
            subprocess.run("shutdown /s /f /t 0", shell=True)
        elif action == "reboot":
            subprocess.run("shutdown /r /f /t 0", shell=True)
        elif action == "hibernate":
            subprocess.run("shutdown /h", shell=True)
        elif action == "sleep":
            subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400

        return jsonify({"message": f"System action '{action}' performed."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


############################
# 3. Network Control
############################

@app.route('/list-networks', methods=['GET'])
def list_networks():
    """
    List all available network interfaces and their statuses.
    """
    try:
        interfaces = psutil.net_if_addrs()
        statuses = psutil.net_if_stats()
        network_data = {
            iface: {
                "addresses": [addr.address for addr in addrs],
                "is_up": statuses[iface].isup
            } for iface, addrs in interfaces.items()
        }
        return jsonify(network_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ping', methods=['GET'])
def ping():
    """
    Ping a host and return the result.
    """
    host = request.args.get('host', 'google.com')
    count = request.args.get('count', 4)

    try:
        result = subprocess.run(["ping", "-n", str(count), host], capture_output=True, text=True)
        return jsonify({"output": result.stdout}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


############################
# 4. Application Management
############################

@app.route('/launch-app', methods=['POST'])
def launch_app():
    """
    Launch an application.
    JSON payload: {"app": "notepad.exe"}
    """
    data = request.json
    app_name = data.get('app')

    try:
        subprocess.Popen(app_name, shell=True)
        return jsonify({"message": f"Launched {app_name}."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(port=5000)
