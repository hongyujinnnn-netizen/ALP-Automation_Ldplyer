from tkinter import filedialog, simpledialog
from tkinter import messagebox as MessageBox


class ToolsMixin:
    style = None

    def show_tools_center(self, section=None):
        """Show the tools center window."""
        pass

    def _append_adb_output(self, output):
        """Append output to the ADB output display."""
        pass

    def log(self, message, level="INFO"):
        """Log a message."""
        pass

    def show_adb_tools(self):
        """Route to the enhanced tools center ADB tab."""
        self.show_tools_center(section="adb")

    def adb_list_devices(self):
        """List ADB devices."""
        try:
            output = self.emulator.run_adb_command("adb devices")
            self._append_adb_output(output)
            MessageBox.showinfo("ADB Devices", output)
        except Exception as exc:
            MessageBox.showerror("Error", f"Failed to list devices: {exc}")

    def adb_shell(self):
        """Run an arbitrary shell command on the connected device."""
        command = simpledialog.askstring("ADB Shell", "Enter ADB shell command:")
        if command:
            try:
                output = self.emulator.run_adb_command(f"adb shell {command}")
                self._append_adb_output(f"adb shell {command}\n{output}")
                MessageBox.showinfo("ADB Shell Output", output)
            except Exception as exc:
                MessageBox.showerror("Error", f"Failed to execute command: {exc}")

    def adb_pull(self):
        """Pull files from the device using a dialog-driven workflow."""
        remote_path = simpledialog.askstring("ADB Pull", "Enter remote path (e.g., /sdcard/DCIM):")
        if not remote_path:
            return

        local_dir = filedialog.askdirectory(title="Select folder to store pulled files")
        if not local_dir:
            return

        try:
            output = self.emulator.run_adb_command(["adb", "pull", remote_path, local_dir], timeout=30)
            self._append_adb_output(f"adb pull {remote_path} {local_dir}\n{output}")
            MessageBox.showinfo("ADB Pull", output)
        except Exception as exc:
            MessageBox.showerror("ADB Pull", f"Failed to pull files: {exc}")

    def adb_push(self):
        """Push a file from the local machine to the device."""
        local_file = filedialog.askopenfilename(title="Select file to push")
        if not local_file:
            return

        remote_dir = simpledialog.askstring("ADB Push", "Enter remote directory (e.g., /sdcard/Download):")
        if not remote_dir:
            return

        try:
            output = self.emulator.run_adb_command(["adb", "push", local_file, remote_dir], timeout=30)
            self._append_adb_output(f"adb push {local_file} {remote_dir}\n{output}")
            MessageBox.showinfo("ADB Push", output)
        except Exception as exc:
            MessageBox.showerror("ADB Push", f"Failed to push file: {exc}")

    def show_documentation(self):
        """Show documentation."""
        MessageBox.showinfo(
            "Documentation",
            "LDPlayer Automation Manager\n\n"
            "Version: 2.0 Enhanced\n"
            "Features:\n"
            "- Multi-LDPlayer management\n"
            "- Task automation\n"
            "- Content scheduling\n"
            "- Performance monitoring\n\n"
            "For detailed documentation, please visit our website.",
        )

    def show_about(self):
        """Show about dialog."""
        MessageBox.showinfo(
            "About",
            "LDPlayer Automation Manager\n"
            "Version: 2.0 Enhanced\n\n"
            "(c) 2024 Automation Tools\n"
            "A powerful tool for managing LDPlayer instances\n"
            "and automating social media tasks.",
        )
