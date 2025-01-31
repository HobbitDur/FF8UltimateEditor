import subprocess
import threading

class IfritGuiLauncher:
    def __init__(self, exe_path, callback=None):
        """
        Initialize the ExeLauncher class.

        :param exe_path: Path to the .exe file to be launched.
        :param callback: A callable to be invoked when the process exits.
        """
        self.exe_path = exe_path
        self.callback = callback
        self.process = None
        self.thread = None

    def launch(self):
        """
        Launch the .exe file and start a monitoring thread.
        """
        try:
            self.process = subprocess.Popen([self.exe_path], shell=True)
            self.thread = threading.Thread(target=self._monitor_process, daemon=True)
            self.thread.start()
        except FileNotFoundError:
            print(f"The file '{self.exe_path}' was not found.")
        except Exception as e:
            print(f"An error occurred: {e}")

    def _monitor_process(self):
        """
        Wait for the process to exit and invoke the callback.
        """
        if self.process:
            self.process.wait()  # Wait for the process to terminate
            if self.callback:
                self.callback()

    def is_running(self):
        """
        Check if the process is still running.

        :return: True if the process is running, False otherwise.
        """
        if self.process:
            return self.process.poll() is None
        return False

    def terminate(self):
        """
        Terminate the running process, if any.
        """
        if self.is_running():
            self.process.terminate()

# Example usage
if __name__ == "__main__":
    def on_exit():
        print("Callback: The external program has exited.")

    exe_launcher = IfritGuiLauncher("C:\\path\\to\\your\\program.exe", callback=on_exit)
    exe_launcher.launch()

    # Simulate doing other work while the external process runs
    for i in range(10):
        if exe_launcher.is_running():
            print(f"Main program doing work... {i}")
        else:
            print("Program no longer running.")
        import time
        time.sleep(1)
